"""Motion global del rediseño: curvas con intención, escalonado, cruce de tema, cambio de pila, popups y presión.

Lenguaje de movimiento tipo Apple: salidas suaves, resorte moderado (nunca rebote grande), tiempos distintos por
rol y nada que supere 500 ms. Todo pasa por ``motion.animar`` → con ``APP_SIN_ANIMACIONES=1`` salta al estado
final: el dato y el estado nunca dependen de una animación. Ningún efecto cambia el layout ni la lógica.
"""

from __future__ import annotations

from typing import Callable

from PyQt6 import sip
from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QRectF, Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QColor, QLinearGradient, QPainter
from PyQt6.QtWidgets import QAbstractScrollArea, QWidget

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


def cruzar_contenido(widget: QWidget, aplicar: Callable[[], None], ms: int = 260) -> None:
    """Cambia el contenido de un widget sin salto: congela lo que se ve, aplica el cambio y funde la imagen vieja.

    Es el cruce de ``cruce_tema`` pero sobre cualquier contenedor (distribución del dashboard, categoría del catálogo).
    Sin animaciones, o con el widget oculto, el cambio es directo."""
    if not widgets.ANIMAR or not widget.isVisible():
        aplicar()
        return
    velo = _Velo(widget, widget.grab())
    try:
        aplicar()
    except Exception:
        velo.deleteLater()          # nunca queda una imagen congelada encima si el cambio falla
        raise
    velo.setGeometry(widget.rect())
    velo.raise_()
    animar(velo, 1.0, 0.0, motion.dur(ms), velo.poner_alfa, velo.deleteLater, ASENTAR)


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
    propia = getattr(pagina, "entrada_motion", None)
    if callable(propia):          # la página tiene su propia coreografía (Dashboard): no se duplica con velos genéricos
        propia()
        return
    from PyQt6.QtWidgets import QFrame
    from .. import tema
    color = QColor(tema.colores()["lienzo"])
    tarjetas = [f for f in pagina.findChildren(QFrame) if f.objectName() == "card" and f.isVisible()
                and f.width() > 40 and f.height() > 30]
    tarjetas.sort(key=lambda f: (f.mapTo(pagina, f.rect().topLeft()).y(), f.mapTo(pagina, f.rect().topLeft()).x()))

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

    def __init__(self, padre: QWidget) -> None:
        super().__init__(padre)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._fase = 0.0
        self._anim: QVariantAnimation | None = None
        self.setFixedHeight(2)
        self.hide()

    def iniciar(self) -> None:
        if not widgets.ANIMAR:
            return
        padre = self.parentWidget()
        self.setGeometry(0, padre.height() - 2, padre.width(), 2)
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


def reducido() -> bool:
    """Movimiento reducido: una sola fuente de verdad (la variable de entorno ya existente)."""
    return not widgets.ANIMAR


__all__ = ["ENTRADA", "SALIDA", "ASENTAR", "resorte", "escalonar", "cruce_tema", "cambiar_pila", "aparecer_popup",
           "instalar_presion", "fundir_contenido", "entrada_pagina", "BarridoCarga", "reducido", "motion"]
