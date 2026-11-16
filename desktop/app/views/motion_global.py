"""Motion global del rediseño: curvas con intención, escalonado, cruce de tema, cambio de pila, popups y presión.

Lenguaje de movimiento tipo Apple: salidas suaves, resorte moderado (nunca rebote grande), tiempos distintos por
rol y nada que supere 500 ms. Todo pasa por ``motion.animar`` → con ``APP_SIN_ANIMACIONES=1`` salta al estado
final: el dato y el estado nunca dependen de una animación. Ningún efecto cambia el layout ni la lógica.
"""

from __future__ import annotations

from typing import Callable

from PyQt6 import sip
from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PyQt6.QtWidgets import QAbstractScrollArea, QGraphicsOpacityEffect, QTableWidget, QWidget

from . import diseno, motion, widgets
from .motion import RAPIDO, animar, detener

# Curvas nombradas por intención.
ENTRADA = QEasingCurve.Type.OutCubic     # algo que aparece: llega rápido y se asienta
SALIDA = QEasingCurve.Type.InCubic       # algo que se va: acelera hacia fuera
ASENTAR = QEasingCurve.Type.InOutCubic   # cambio de estado entre dos posiciones
MUY_RAPIDO, MEDIO = 90, 260              # presión de botón (< 100 ms) y cruce de pantallas
_NO_ANIMAN = ("nav", "iconoLateral", "cuenta")   # la barra lateral conserva su propio feedback


def resorte(sobrepaso: float = 1.15) -> QEasingCurve:
    """Resorte moderado. ``sobrepaso`` 1.0 = sin rebote; 1.7 = el de Qt (demasiado para una app de datos)."""
    curva = QEasingCurve(QEasingCurve.Type.OutBack)
    curva.setOvershoot(sobrepaso)
    return curva


def escalonar(pasos: list[Callable[[], None]], intervalo: int = 28, tope: int = 8) -> None:
    """Dispara acciones en cascada. Pasados ``tope`` elementos el resto entra a la vez (nunca > ~250 ms de espera)."""
    if not widgets.ANIMAR:
        for paso in pasos:
            paso()
        return
    for i, paso in enumerate(pasos):
        QTimer.singleShot(min(i, tope) * intervalo, paso)


class _Velo(QWidget):
    """Capa sobre un widget que pinta una imagen o un color y se desvanece. No atrapa el ratón."""

    def __init__(self, padre: QWidget, imagen=None, color: QColor | None = None, alfa: float = 1.0) -> None:
        super().__init__(padre)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._imagen, self._color, self._alfa = imagen, color, alfa
        self._avance, self._distancia = 0.0, 0
        self.setGeometry(padre.rect())
        self.show()
        self.raise_()

    def poner_alfa(self, valor: float) -> None:
        self._alfa = max(0.0, min(1.0, valor))
        self.update()

    def desliza(self, v: float) -> None:
        self._avance = v
        self.poner_alfa(1.0 - v)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setOpacity(self._alfa)
        if self._imagen is not None:
            p.drawPixmap(int(-self._distancia * self._avance), 0, self._imagen)
        elif self._color is not None:
            p.fillRect(self.rect(), self._color)


def cruce_tema(ventana: QWidget, aplicar: Callable[[], None], ms: int = 240) -> None:
    """Cambio de tema sin salto: congela la imagen actual, aplica el tema y la funde hacia la nueva."""
    if not widgets.ANIMAR or not ventana.isVisible():
        aplicar()
        return
    velo = _Velo(ventana, ventana.grab())
    aplicar()
    velo.setGeometry(ventana.rect())
    velo.raise_()
    animar(velo, 1.0, 0.0, ms, velo.poner_alfa, velo.deleteLater, ASENTAR)


def cambiar_pila(pila, indice: int, distancia: int = 18, ms: int = MEDIO) -> None:
    """``QStackedWidget.setCurrentIndex`` con cruce: la página anterior se desvanece y se desliza al salir."""
    actual = pila.currentIndex()
    if indice == actual:
        return
    if not widgets.ANIMAR or not pila.isVisible():
        pila.setCurrentIndex(indice)
        return
    imagen = pila.grab()
    pila.setCurrentIndex(indice)
    velo = _Velo(pila, imagen)
    velo._distancia = distancia if indice > actual else -distancia
    animar(velo, 0.0, 1.0, ms, velo.desliza, velo.deleteLater, ENTRADA)


def aparecer_popup(ventana: QWidget, ms: int = 150) -> None:
    """Menús, desplegables y popovers nacen con un fundido corto."""
    if not widgets.ANIMAR or ventana.property("aparecido"):
        return
    ventana.setProperty("aparecido", True)

    def poner(valor: float) -> None:
        if not sip.isdeleted(ventana):
            ventana.setWindowOpacity(valor)

    poner(0.0)
    animar(ventana, 0.0, 1.0, ms, poner, lambda: poner(1.0), ENTRADA)


class _Presion(QWidget):
    """Capa de feedback al pulsar: aclara/oscurece el botón en < 100 ms y vuelve al soltar."""

    def __init__(self, boton: QWidget) -> None:
        super().__init__(boton)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._v = 0.0
        self._anim: QVariantAnimation | None = None
        self.hide()

    def fijar(self, destino: float) -> None:
        if destino == 0.0 and self._v == 0.0:
            return
        detener(self._anim)
        if destino > 0:
            self.setGeometry(self.parentWidget().rect())
            self.show()
            self.raise_()
        self._anim = animar(self, self._v, destino, MUY_RAPIDO if destino else RAPIDO, self._paso,
                            None if destino else self.hide, ENTRADA)

    def _paso(self, v: float) -> None:
        self._v = v
        self.update()

    def paintEvent(self, _evento) -> None:
        if self._v <= 0.001:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        oscuro = widgets.tema.es_oscuro()
        p.setBrush(QColor(255, 255, 255, int(28 * self._v)) if oscuro else QColor(0, 0, 0, int(30 * self._v)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8.0, 8.0)


class _FiltroPresion(QObject):
    def __init__(self, capa: _Presion, boton: QWidget) -> None:
        super().__init__(boton)
        self._capa = capa

    def eventFilter(self, objeto, evento) -> bool:
        tipo = evento.type()
        if tipo == QEvent.Type.MouseButtonPress and objeto.isEnabled():
            self._capa.fijar(1.0)
        elif tipo in (QEvent.Type.MouseButtonRelease, QEvent.Type.Leave, QEvent.Type.Hide):
            self._capa.fijar(0.0)
        return False


def instalar_presion(boton: QWidget) -> None:
    """Feedback de presión en un botón (una sola vez por botón)."""
    if boton.property("presionInstalada") or boton.objectName() in _NO_ANIMAN:
        return
    boton.setProperty("presionInstalada", True)
    capa = _Presion(boton)
    boton._presion = capa  # type: ignore[attr-defined]
    boton.installEventFilter(_FiltroPresion(capa, boton))


def fundir_contenido(tabla: QAbstractScrollArea, ms: int = 220) -> None:
    """Datos nuevos en una tabla: un velo del color de fondo se desvanece sobre las filas (sin efectos anidados)."""
    if not widgets.ANIMAR or not tabla.isVisible() or tabla.property("sinFundido"):
        return
    visor = tabla.viewport()
    color = visor.palette().color(visor.backgroundRole())
    velo = _Velo(visor, color=QColor(color), alfa=0.6)
    animar(velo, 0.6, 0.0, ms, velo.poner_alfa, velo.deleteLater, ENTRADA)


def entrada_pagina(pagina: QWidget) -> None:
    """Al abrir una sección sus tarjetas «se revelan» en cascada: un velo del color del lienzo se desvanece sobre cada una.

    No mueve nada (el layout no cambia) ni toca los datos: solo cubre y descubre.
    """
    if not widgets.ANIMAR or not pagina.isVisible():
        return
    propia = getattr(pagina, "entrada_motion", None)    # una vista con su propia coreografía (p. ej. Inventario)
    if callable(propia):
        propia()
        return
    from PyQt6.QtWidgets import QFrame
    from .. import tema
    color = QColor(tema.colores()["lienzo"])
    tarjetas = [f for f in pagina.findChildren(QFrame) if f.objectName() == "card" and f.isVisible()
                and f.width() > 40 and f.height() > 30]
    tarjetas.sort(key=lambda f: (f.mapTo(pagina, f.rect().topLeft()).y(), f.mapTo(pagina, f.rect().topLeft()).x()))

    if not tarjetas:
        # Página sin tarjetas (tablas, formularios): un fundido corto de toda la página, sin deslizar nada.
        velo = _Velo(pagina, color=color, alfa=0.7)
        animar(velo, 0.7, 0.0, diseno.T_ENTRADA - 50, velo.poner_alfa, velo.deleteLater, ENTRADA)
        return

    # Cubiertas desde ya para que no parpadeen antes de su turno; cada una se destapa con su retardo.
    for i, tarjeta in enumerate(tarjetas[:24]):
        velo = _Velo(tarjeta, color=color, alfa=1.0)
        retraso = min(i, diseno.CASCADA_TOPE) * diseno.CASCADA_INTERVALO
        QTimer.singleShot(retraso, lambda v=velo: _destapar(v))


def _destapar(velo: "_Velo") -> None:
    if sip.isdeleted(velo):
        return
    animar(velo, 1.0, 0.0, diseno.T_ENTRADA + 60, velo.poner_alfa, velo.deleteLater, ENTRADA)


class BarridoCarga(QWidget):
    """Línea de 2 px que barre de izquierda a derecha mientras una consulta real está en curso.

    El temporizador solo corre mientras es visible: oculta, no gasta nada.
    """

    def __init__(self, padre: QWidget, margen: int = 0) -> None:
        super().__init__(padre)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._margen = margen              # separación a los lados (un campo redondeado no quiere la línea hasta la esquina)
        self._fase = 0.0
        self._anim: QVariantAnimation | None = None
        self.setFixedHeight(2)
        padre.installEventFilter(self)
        self.hide()

    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() == QEvent.Type.Resize and self.isVisible():
            self._anclar()
        return False

    def _anclar(self) -> None:
        padre = self.parentWidget()
        abajo = 3 if self._margen else 2
        self.setGeometry(self._margen, padre.height() - abajo, max(0, padre.width() - 2 * self._margen), 2)
        self.raise_()

    def iniciar(self) -> None:
        if not widgets.ANIMAR:
            return
        self._anclar()
        if self._anim is not None and self._anim.state() == QVariantAnimation.State.Running:
            return                          # ya está barriendo: una consulta nueva no reinicia el movimiento
        self.show()
        self.raise_()
        if self._anim is None:
            anim = QVariantAnimation(self)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setDuration(1100)
            anim.setLoopCount(-1)
            anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            anim.valueChanged.connect(self._paso)
            self._anim = anim
        self._anim.start()

    def detener(self) -> None:
        if self._anim is not None:
            self._anim.stop()
        self.hide()

    def _paso(self, v: float) -> None:
        self._fase = float(v)
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        ancho = self.width()
        largo = max(60, ancho * 0.28)
        x = -largo + (ancho + largo) * self._fase
        degradado = QLinearGradient(x, 0, x + largo, 0)
        verde = QColor(widgets.VERDE)
        transparente = QColor(verde)
        transparente.setAlpha(0)
        degradado.setColorAt(0.0, transparente)
        degradado.setColorAt(0.5, verde)
        degradado.setColorAt(1.0, transparente)
        p.fillRect(self.rect(), degradado)


# --------------------------------------------------------------------------- despliegue vertical
_SIN_TOPE = 16777215        # QWIDGETSIZE_MAX


def desplegar(panel: QWidget, visible: bool, ms: int | None = None) -> None:
    """Muestra u oculta un panel como una superficie que se despliega: la altura crece (o se contrae) y el contenido
    se funde con un desfase (entra un poco después de que el panel empiece a abrirse y sale antes de que termine de
    cerrarse). La posición final de los controles no cambia: solo se recorta la altura visible.

    Sin animaciones (o con la vista oculta) es un simple ``setVisible``. Es seguro volver a llamarla a mitad de camino:
    parte de la altura actual."""
    ms = diseno.T_PANTALLA if ms is None else ms
    detener(getattr(panel, "_despliegue", None))
    panel._despliegue_tok = token = object()          # type: ignore[attr-defined]

    def reposo(mostrar: bool) -> None:
        if sip.isdeleted(panel):
            return
        panel.setMaximumHeight(_SIN_TOPE)
        if isinstance(panel.graphicsEffect(), QGraphicsOpacityEffect):
            panel.setGraphicsEffect(None)
        panel._desplegando = False                     # type: ignore[attr-defined]
        panel.setVisible(mostrar)

    padre = panel.parentWidget()
    if not widgets.ANIMAR or padre is None or not padre.isVisible():
        reposo(visible)
        return
    estable = not getattr(panel, "_desplegando", False)
    if estable and visible == panel.isVisible():
        return
    destino = max(panel.sizeHint().height(), panel.minimumSizeHint().height(), 1)
    actual = panel.height() if panel.isVisible() else 0
    panel._desplegando = True                          # type: ignore[attr-defined]
    efecto, _ = motion.opacidad(panel)
    ms = motion.dur(ms)

    if visible:
        inicio = min(1.0, actual / destino)
        panel.setMaximumHeight(max(1, actual))
        efecto.setOpacity(efecto.opacity() if actual else 0.0)
        panel.setVisible(True)

        def paso(v: float) -> None:
            if sip.isdeleted(panel):
                return
            panel.setMaximumHeight(max(1, int(destino * v)))
            efecto.setOpacity(max(0.0, min(1.0, (v - 0.12) / 0.7)))
        curva = ENTRADA
    else:
        inicio = 0.0
        base, op0 = max(1, actual), efecto.opacity()

        def paso(v: float) -> None:
            if sip.isdeleted(panel):
                return
            panel.setMaximumHeight(max(1, int(base * (1 - v))))
            efecto.setOpacity(max(0.0, op0 * (1 - v / 0.55)))
        curva = ASENTAR

    def fin() -> None:
        if getattr(panel, "_despliegue_tok", None) is token:
            reposo(visible)

    panel._despliegue = animar(panel, inicio, 1.0, ms, paso, fin, curva)  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- realce de campos
class Aureola(QWidget):
    """Realce de un campo de texto o desplegable: un resplandor interior que crece al recibir el foco y se retira al
    perderlo, más un velo casi imperceptible al pasar el cursor. Solo pinta encima (no mueve el texto ni el cursor ni el
    borde propio del campo) y no atrapa el ratón. Si el campo está marcado ``invalido`` el resplandor toma el color de
    error: el estado sale del propio campo, no se inventa."""

    def __init__(self, campo: QWidget, radio: float = diseno.RADIO_CONTROL) -> None:
        super().__init__(campo)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._campo, self._radio = campo, radio
        self._foco, self._hover = 0.0, 0.0
        self._a_foco: QVariantAnimation | None = None
        self._a_hover: QVariantAnimation | None = None
        campo.installEventFilter(self)
        self.setGeometry(campo.rect())
        self.show()
        self.raise_()

    def _ir(self, atributo: str, destino: float, ms: int) -> None:
        anim = "_a_foco" if atributo == "_foco" else "_a_hover"
        detener(getattr(self, anim))

        def paso(v: float) -> None:
            setattr(self, atributo, v)
            self.update()
        setattr(self, anim, animar(self, getattr(self, atributo), destino, ms, paso, None, ENTRADA))

    def eventFilter(self, objeto, evento) -> bool:
        tipo = evento.type()
        if tipo == QEvent.Type.FocusIn:
            self._ir("_foco", 1.0, motion.dur(diseno.T_ENTRADA))
        elif tipo == QEvent.Type.FocusOut:
            self._ir("_foco", 0.0, motion.dur(diseno.T_ENTRADA))
        elif tipo == QEvent.Type.Enter:
            self._ir("_hover", 1.0, diseno.T_HOVER)
        elif tipo == QEvent.Type.Leave:
            self._ir("_hover", 0.0, diseno.T_HOVER)
        elif tipo == QEvent.Type.Resize:
            self.setGeometry(self._campo.rect())
        elif tipo == QEvent.Type.Show:
            self.raise_()
        return False

    def paintEvent(self, _evento) -> None:
        if self._foco <= 0.002 and self._hover <= 0.002:
            return
        from .. import tema
        c = tema.colores()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        marco = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._hover > 0.002 and self._foco < 0.98:
            velo = QColor(255, 255, 255) if tema.es_oscuro() else QColor(0, 0, 0)
            velo.setAlphaF(0.035 * self._hover * (1 - self._foco))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(velo)
            p.drawRoundedRect(marco, self._radio, self._radio)
        if self._foco > 0.002:
            tono = QColor(c["error"] if self._campo.property("invalido") else c["acento"])
            relleno = QColor(tono)
            relleno.setAlphaF(0.07 * self._foco)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(relleno)
            p.drawRoundedRect(marco, self._radio, self._radio)
            anillo = QColor(tono)
            anillo.setAlphaF(0.30 * self._foco)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(anillo)
            interior = max(2.0, self._radio - 3)
            p.drawRoundedRect(marco.adjusted(2.5, 2.5, -2.5, -2.5), interior, interior)


def instalar_realce(campo: QWidget) -> Aureola | None:
    """Instala (una sola vez) el realce de foco y hover en un ``QLineEdit`` o ``QComboBox`` (sin animaciones, nada)."""
    if not widgets.ANIMAR:
        return None
    previa = getattr(campo, "_aureola", None)
    if previa is not None:
        return previa
    campo._aureola = Aureola(campo)   # type: ignore[attr-defined]
    return campo._aureola             # type: ignore[attr-defined]


def marcar_invalido(campo: QWidget, invalido: bool) -> None:
    """Marca (o desmarca) un campo con la propiedad ``invalido`` que ya usa la hoja de estilo de la app."""
    if bool(campo.property("invalido")) == invalido:
        return
    campo.setProperty("invalido", invalido)
    campo.style().unpolish(campo)
    campo.style().polish(campo)
    aureola = getattr(campo, "_aureola", None)
    if aureola is not None:
        aureola.update()


# --------------------------------------------------------------------------- tablas: filas que se reacomodan
class InstantaneaFilas:
    """Foto de las filas visibles de una tabla antes de un cambio: la imagen del visor y, por clave de fila, su posición,
    una «huella» de su contenido (para saber si cambió) y su alto."""

    __slots__ = ("pix", "filas")

    def __init__(self, pix: QPixmap, filas: dict[str, tuple[int, str, int]]) -> None:
        self.pix, self.filas = pix, filas


def _filas_visibles(tabla: QTableWidget, claves: list[str], huellas: list[str]) -> dict[str, tuple[int, str, int]]:
    alto_visor = tabla.viewport().height()
    visibles: dict[str, tuple[int, str, int]] = {}
    fila = max(0, tabla.rowAt(0))
    while fila < min(tabla.rowCount(), len(claves)):
        y = tabla.rowViewportPosition(fila)
        if y >= alto_visor:
            break
        visibles[claves[fila]] = (y, huellas[fila], tabla.rowHeight(fila))
        fila += 1
    return visibles


class _CapaFilas(QWidget):
    """Capa opaca sobre el visor de la tabla que dibuja el paso de «antes» a «después» con tiras de las dos fotos:
    las filas que siguen se deslizan a su nuevo sitio, las que salen se funden donde estaban (las de abajo suben y
    las tapan) y las nuevas se funden en su lugar, escalonadas. Debajo, la tabla real ya está en su estado final; al
    terminar la capa desaparece sin que cambie ni un píxel. No atrapa el ratón."""

    def __init__(self, visor: QWidget, antes: InstantaneaFilas, despues: InstantaneaFilas, color: QColor) -> None:
        super().__init__(visor)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._antes, self._despues, self._color = antes, despues, color
        self._e = 0.0
        self._anim: QVariantAnimation | None = None
        self._quieto = motion.reducido()          # movimiento reducido: solo fundidos, sin desplazamiento
        self._orden_nuevas = {k: i for i, k in enumerate(k for k in despues.filas if k not in antes.filas)}
        self.setGeometry(visor.rect())
        self.show()
        self.raise_()

    def poner(self, v: float) -> None:
        self._e = v
        self.update()

    def _tira(self, p: QPainter, foto: InstantaneaFilas, y_origen: int, alto: int, y: float, alfa: float) -> None:
        if alfa <= 0.003:
            return
        k = foto.pix.devicePixelRatio()
        p.setOpacity(min(1.0, alfa))
        p.drawPixmap(QRectF(0, y, self.width(), alto), foto.pix, QRectF(0, y_origen * k, self.width() * k, alto * k))

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self._color)
        e, antes, despues = self._e, self._antes.filas, self._despues.filas
        for clave, (y0, _h0, alto) in antes.items():                       # 1) las que salen, al fondo
            if clave not in despues:
                self._tira(p, self._antes, y0, alto, y0, 1.0 - e)
        for clave, (y1, huella1, alto) in despues.items():                 # 2) las que siguen
            previa = antes.get(clave)
            if previa is None:
                continue
            y0, huella0, _alto0 = previa
            y = y1 if self._quieto else y0 + (y1 - y0) * e
            if huella0 != huella1:                                         # su contenido cambió: cruce de las dos tiras
                self._tira(p, self._antes, y0, alto, y, 1.0)
                self._tira(p, self._despues, y1, alto, y, e)
            else:
                self._tira(p, self._despues, y1, alto, y, 1.0)
        for clave, orden in self._orden_nuevas.items():                    # 3) las nuevas, escalonadas
            y1, _huella, alto = despues[clave]
            retraso = min(orden, 9) * 0.045
            k = max(0.0, min(1.0, (e - retraso) / (1.0 - retraso)))
            self._tira(p, self._despues, y1, alto, y1 + (0 if self._quieto else (1 - k) * 5), k)
        p.end()


def capturar_filas(tabla: QTableWidget, claves: list[str], huellas: list[str]) -> InstantaneaFilas | None:
    """Primera mitad de una transición de filas: llamar ANTES de cambiar el contenido de la tabla. ``claves`` y
    ``huellas`` van alineadas con las filas actuales. Devuelve ``None`` si no hay nada que animar (sin animaciones o
    tabla oculta); entonces ``revelar_filas`` no hace nada."""
    if not widgets.ANIMAR or not tabla.isVisible() or tabla.viewport().height() <= 0:
        return None
    soltar_filas(tabla)
    resalte = getattr(tabla, "_resalte", None)
    if resalte is not None:
        resalte.ocultar()                       # que la foto no incluya el realce de hover
    return InstantaneaFilas(tabla.viewport().grab(), _filas_visibles(tabla, claves, huellas))


def revelar_filas(tabla: QTableWidget, antes: InstantaneaFilas | None, claves: list[str], huellas: list[str],
                  ms: int | None = None) -> None:
    """Segunda mitad: llamar DESPUÉS de cambiar el contenido. Anima solo lo que cambió (entran, salen, se mueven o
    cambian de contenido); si las filas visibles quedaron idénticas no hace nada."""
    resalte = getattr(tabla, "_resalte", None)
    if resalte is not None:
        resalte.restaurar()
    if antes is None or not widgets.ANIMAR or not tabla.isVisible():
        return
    visor = tabla.viewport()
    despues_filas = _filas_visibles(tabla, claves, huellas)
    if despues_filas == antes.filas:
        return
    cabecera = tabla.horizontalHeader()
    cabecera.resizeSections(cabecera.ResizeMode.ResizeToContents)        # anchos ya finales antes de la foto
    despues = InstantaneaFilas(visor.grab(), _filas_visibles(tabla, claves, huellas))
    color = QColor(visor.palette().color(visor.backgroundRole()))
    capa = _CapaFilas(visor, antes, despues, color)
    tabla._capa_filas = capa            # type: ignore[attr-defined]
    if resalte is not None:
        resalte.ocultar()
    tabla.verticalScrollBar().valueChanged.connect(lambda _v: soltar_filas(tabla))   # desplazar deja la tabla real

    def fin() -> None:
        if not sip.isdeleted(capa):
            capa.deleteLater()
        if not sip.isdeleted(tabla) and getattr(tabla, "_capa_filas", None) is capa:
            tabla._capa_filas = None            # type: ignore[attr-defined]
        if resalte is not None and not sip.isdeleted(resalte):
            resalte.restaurar()

    capa._anim = animar(capa, 0.0, 1.0, motion.dur(ms or diseno.T_PANTALLA - 20), capa.poner, fin, ENTRADA)


def soltar_filas(tabla: QTableWidget) -> None:
    """Cancela una transición de filas en curso (la tabla real, ya en su estado final, queda a la vista)."""
    capa = getattr(tabla, "_capa_filas", None)
    if capa is not None and not sip.isdeleted(capa):
        detener(capa._anim)
        capa.hide()
        capa.deleteLater()
    tabla._capa_filas = None            # type: ignore[attr-defined]
    resalte = getattr(tabla, "_resalte", None)
    if resalte is not None and not sip.isdeleted(resalte):
        resalte.restaurar()


class _Banda(QWidget):
    """Banda de una fila (resalte o pulso de selección): un rectángulo translúcido que se mueve y se funde."""

    def __init__(self, visor: QWidget) -> None:
        super().__init__(visor)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._color = QColor(255, 255, 255, 255)
        self._alfa = 0.0
        self._anim: QVariantAnimation | None = None
        self.hide()

    def poner_alfa(self, v: float) -> None:
        self._alfa = max(0.0, v)
        self.setVisible(self._alfa > 0.004)
        self.update()

    def paintEvent(self, _evento) -> None:
        color = QColor(self._color)
        color.setAlphaF(min(1.0, self._alfa))
        QPainter(self).fillRect(self.rect(), color)


class ResalteFilas(QObject):
    """Hover y selección de una tabla de datos con transición: una banda que se desliza de fila en fila y se funde al
    entrar y salir, y un pulso breve al seleccionar una fila. Sustituye el hover instantáneo del QSS (solo existe con
    animaciones) y no toca la selección real ni el doble clic. Una sola capa por tabla: nada por celda."""

    def __init__(self, tabla: QTableWidget) -> None:
        super().__init__(tabla)
        from .. import tema
        self._tabla, self._visor = tabla, tabla.viewport()
        self._hover, self._pulso = _Banda(self._visor), _Banda(self._visor)
        self._hover._color = QColor(255, 255, 255) if tema.es_oscuro() else QColor(0, 0, 0)
        self._hover_k = 0.055 if tema.es_oscuro() else 0.045
        self._pulso._color = QColor(tema.colores()["acento"])
        self._fila = -1
        self._oculto = False
        self._visor.setMouseTracking(True)
        tabla.setMouseTracking(True)
        self._visor.installEventFilter(self)
        tabla.itemSelectionChanged.connect(self._seleccion)
        tabla.verticalScrollBar().valueChanged.connect(lambda _v: self._reubicar())
        tabla.setStyleSheet("QTableWidget::item:hover { background: transparent; }")

    def ocultar(self) -> None:
        self._oculto = True
        for banda in (self._hover, self._pulso):
            detener(banda._anim)
            banda.poner_alfa(0.0)

    def restaurar(self) -> None:
        self._oculto = False
        self._fila = -1
        self._reubicar()

    def _alfa_fila(self, fila: int) -> float:
        if fila < 0 or fila >= self._tabla.rowCount():
            return 0.0
        seleccionada = self._tabla.selectionModel().isRowSelected(fila, self._tabla.rootIndex())
        return self._hover_k * (0.35 if seleccionada else 1.0)

    def _colocar(self, banda: _Banda, fila: int, y: float | None = None) -> None:
        y = self._tabla.rowViewportPosition(fila) if y is None else y
        banda.setGeometry(0, int(round(y)), self._visor.width(), self._tabla.rowHeight(fila))
        banda.raise_()

    def _ir_a(self, fila: int, animado: bool = True) -> None:
        if self._oculto:
            return
        fila = fila if 0 <= fila < self._tabla.rowCount() else -1
        banda = self._hover
        detener(banda._anim)
        ms = motion.dur(diseno.T_HOVER)
        if fila < 0:                                         # el cursor salió de las filas: la banda se retira
            self._fila = -1
            banda._anim = animar(banda, banda._alfa, 0.0, ms if animado else 0, banda.poner_alfa, None, ENTRADA)
            return
        previa, self._fila = self._fila, fila
        destino = self._alfa_fila(fila)
        if previa < 0 or not animado or banda._alfa <= 0.004:       # aparece directamente sobre la fila
            self._colocar(banda, fila)
            banda._anim = animar(banda, banda._alfa, destino, ms if animado else 0, banda.poner_alfa, None, ENTRADA)
            return
        y0, y1, a0 = float(banda.y()), float(self._tabla.rowViewportPosition(fila)), banda._alfa

        def paso(v: float) -> None:
            self._colocar(banda, fila, y0 + (y1 - y0) * v)
            banda.poner_alfa(a0 + (destino - a0) * v)
        banda._anim = animar(banda, 0.0, 1.0, motion.dur(diseno.T_PRESION + 20), paso, None, ENTRADA)

    def _reubicar(self) -> None:
        if self._oculto or not self._visor.underMouse():
            return
        pos = self._visor.mapFromGlobal(self._visor.cursor().pos())
        self._ir_a(self._tabla.rowAt(pos.y()) if self._visor.rect().contains(pos) else -1, animado=False)

    def _seleccion(self) -> None:
        filas = self._tabla.selectionModel().selectedRows()
        if self._oculto or not filas:
            return
        self._colocar(self._pulso, filas[0].row())
        detener(self._pulso._anim)
        self._pulso._anim = animar(self._pulso, 0.20, 0.0, motion.dur(diseno.T_PANTALLA), self._pulso.poner_alfa,
                                   None, ENTRADA)
        if self._fila >= 0:
            self._hover.poner_alfa(self._alfa_fila(self._fila))

    def eventFilter(self, objeto, evento) -> bool:
        tipo = evento.type()
        if tipo == QEvent.Type.MouseMove:
            fila = self._tabla.rowAt(int(evento.position().y()))
            if fila != self._fila:
                self._ir_a(fila)
        elif tipo == QEvent.Type.Leave:
            self._ir_a(-1)
        elif tipo == QEvent.Type.Resize and self._fila >= 0:
            self._colocar(self._hover, self._fila)
        return False


def resaltar_filas(tabla: QTableWidget) -> ResalteFilas | None:
    """Instala (una sola vez) el hover/selección con transición en una tabla de datos. Sin animaciones no hace nada
    (queda el hover nativo del QSS)."""
    if not widgets.ANIMAR:
        return None
    previo = getattr(tabla, "_resalte", None)
    if previo is None:
        previo = tabla._resalte = ResalteFilas(tabla)   # type: ignore[attr-defined]
    return previo


# --------------------------------------------------------------------------- cifras dentro de un texto
def cuenta_texto(etiqueta, valores: tuple[int, ...], formato: Callable[[tuple[int, ...], tuple[int, ...]], str],
                 ms: int = 240) -> None:
    """Pone en ``etiqueta`` el texto ``formato(valores, valores)`` y, si la etiqueta es visible, lleva cada número que
    cambió desde su valor anterior hasta el nuevo (los que no cambiaron no se mueven). ``formato(actual, final)`` recibe
    los números del fotograma y los finales (para que la estructura del texto dependa de los finales y no parpadee).
    El texto final nunca depende de la animación: se escribe al terminar y también al empezar la siguiente."""
    detener(getattr(etiqueta, "_cuenta", None))
    mostrado = getattr(etiqueta, "_cuenta_mostrado", None)
    final = formato(valores, valores)
    if (not widgets.ANIMAR or mostrado is None or mostrado == valores or not etiqueta.isVisible()
            or len(mostrado) != len(valores)):
        etiqueta._cuenta_mostrado = valores               # type: ignore[attr-defined]
        etiqueta.setText(final)
        return
    inicio = tuple(mostrado)

    def paso(v: float) -> None:
        actual = tuple(round(a + (b - a) * v) if a != b else b for a, b in zip(inicio, valores))
        etiqueta._cuenta_mostrado = actual                # type: ignore[attr-defined]
        etiqueta.setText(formato(actual, valores))

    def fin() -> None:
        if not sip.isdeleted(etiqueta):
            etiqueta._cuenta_mostrado = valores           # type: ignore[attr-defined]
            etiqueta.setText(final)

    etiqueta._cuenta = animar(etiqueta, 0.0, 1.0, motion.dur(ms), paso, fin, ENTRADA)   # type: ignore[attr-defined]


def reducido() -> bool:
    """Movimiento reducido: una sola fuente de verdad (la variable de entorno ya existente)."""
    return not widgets.ANIMAR


__all__ = ["ENTRADA", "SALIDA", "ASENTAR", "resorte", "escalonar", "cruce_tema", "cambiar_pila", "aparecer_popup",
           "instalar_presion", "fundir_contenido", "entrada_pagina", "BarridoCarga", "reducido", "motion",
           "desplegar", "instalar_realce", "marcar_invalido", "capturar_filas", "revelar_filas", "soltar_filas",
           "resaltar_filas", "cuenta_texto", "entrada_filas"]


def entrada_filas(tabla: QTableWidget, claves: list[str], huellas: list[str]) -> None:
    """Revela las filas actuales de una tabla en cascada (primera carga o regreso a la pantalla): todas cuentan como
    nuevas. No toca los datos; la tabla real ya está completa debajo."""
    if not widgets.ANIMAR or not tabla.isVisible() or not claves:
        return
    soltar_filas(tabla)
    revelar_filas(tabla, InstantaneaFilas(QPixmap(), {}), claves, huellas, diseno.T_PANTALLA)
