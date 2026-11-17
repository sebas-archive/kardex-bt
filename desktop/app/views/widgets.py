"""Piezas visuales compartidas: tarjetas con cifras que cuentan, anillos, barras, pasos, avisos y transiciones.

Regla de todas: el **dato** queda disponible de inmediato (``texto()``, ``valor()``…) y solo el dibujo se anima.
Así una prueba o un refresco nunca dependen de que una animación haya terminado. ``ANIMAR`` las apaga todas
(variable de entorno ``APP_SIN_ANIMACIONES=1``): lo usan las pruebas y las capturas de pantalla.
"""

from __future__ import annotations

import math
import os
from typing import Callable

from PyQt6 import sip
from PyQt6.QtCore import QEasingCurve, QEvent, QPoint, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QStackedLayout, QToolButton, QVBoxLayout,
                             QWidget)

from .. import tema
from .. import i18n

def _sistema_pide_menos_movimiento() -> bool:
    """«Reducir movimiento» del escritorio (GNOME/Cinnamon: ``enable-animations`` = false). Sin gsettings, no aplica."""
    if os.environ.get("APP_SIN_ANIMACIONES") == "0":
        return False   # forzado a mano (pruebas del movimiento real)
    import shutil
    import subprocess
    if shutil.which("gsettings") is None:
        return False
    try:
        salida = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"],
                                capture_output=True, text=True, timeout=0.6).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return salida == "false"


ANIMAR = os.environ.get("APP_SIN_ANIMACIONES") != "1" and not _sistema_pide_menos_movimiento()

# Paleta (la misma familia de colores de la app del celular). ``refrescar_paleta`` la pone al día con el tema.
VERDE, VERDE_OSCURO = "#10B981", "#0B8A62"
TINTA, TINTA_SUAVE, LINEA, FONDO, PISTA = "#EDEDED", "#8A8A8A", "#2E2E2E", "#0A0A0A", "#1F1F1F"


def refrescar_paleta() -> None:
    """Actualiza los colores que se usan al pintar a mano (se llama al aplicar un tema)."""
    global VERDE, VERDE_OSCURO, TINTA, TINTA_SUAVE, LINEA, FONDO, PISTA
    c = tema.colores()
    VERDE, VERDE_OSCURO = c["acento"], c["acento_suave"]
    TINTA, TINTA_SUAVE = c["texto"], c["texto_suave"]
    LINEA, FONDO, PISTA = c["borde"], c["fondo"], c["tarjeta_alt"]
COLOR_CLASIFICACION = {"OK": "#12B76A", "FALTANTE": "#F04438", "SOBRANTE": "#F79009", "SIN_CONTAR": "#98A2B3"}
NOMBRE_CLASIFICACION = {"OK": "OK", "FALTANTE": "Faltante", "SOBRANTE": "Sobrante", "SIN_CONTAR": "Sin contar"}


def animar(dueno: QWidget, inicio: float, fin: float, ms: int, al_cambiar: Callable[[float], None],
           al_terminar: Callable[[], None] | None = None,
           curva: QEasingCurve.Type = QEasingCurve.Type.OutCubic) -> QVariantAnimation | None:
    """Lleva un número de ``inicio`` a ``fin`` llamando a ``al_cambiar``. Sin animaciones, salta al final."""
    if not ANIMAR or ms <= 0:
        al_cambiar(fin)
        if al_terminar:
            al_terminar()
        return None
    anim = QVariantAnimation(dueno)
    anim.setStartValue(float(inicio))
    anim.setEndValue(float(fin))
    anim.setDuration(ms)
    anim.setEasingCurve(curva)
    anim.valueChanged.connect(lambda v: al_cambiar(float(v)))
    if al_terminar:
        anim.finished.connect(al_terminar)
    anim.finished.connect(anim.deleteLater)
    anim.start()
    return anim


def _ms(ms: int) -> int:
    """Duración efectiva: con «reducir movimiento» las transiciones esenciales se acortan (``motion.dur``)."""
    from . import motion
    return motion.dur(ms)


def _px(px: float) -> float:
    """Desplazamiento efectivo: con «reducir movimiento» casi no hay recorrido (``motion.desp``)."""
    from . import motion
    return motion.desp(px)


def _decorativo() -> bool:
    """¿Se permiten ciclos continuos (respiración, destellos)? No con movimiento reducido."""
    from . import motion
    return motion.decorativo()


def _detener(anim: QVariantAnimation | None) -> None:
    if anim is not None:
        try:
            anim.stop()
        except RuntimeError:  # ya la borró Qt al terminar
            pass


class _Fundible:
    """Mixin de QLabel/QToolButton: opacidad y desplazamiento vertical propios, **sin** ``QGraphicsEffect``.

    Un efecto en el hijo se anida con el de la tarjeta/baldosa que lo contiene (entrada, hover, arrastre) y Qt lo dibuja
    mal. Aquí el widget solo se «congela» en una imagen mientras está a medio fundir; en reposo pinta como siempre, sin
    coste. La imagen se genera **fuera** del evento de pintado (``render`` dentro de ``paintEvent`` es recursivo en Qt) y
    se invalida si cambia el contenido, el tamaño o el estilo. ``opacity``/``setOpacity`` imitan la API de
    ``QGraphicsOpacityEffect``.
    """

    _alfa = 1.0
    _desp = 0.0
    _renderizando = False
    _cache: QPixmap | None = None

    def opacity(self) -> float:
        return self._alfa

    def _en_reposo(self) -> bool:
        return self._alfa >= 0.999 and abs(self._desp) < 0.05

    def _a_medias(self) -> None:
        """Se prepara la imagen congelada antes de pintar a medio fundir (siempre desde fuera de ``paintEvent``)."""
        if self._cache is None and not self._en_reposo():
            self._rehacer()
        self.update()                           # type: ignore[attr-defined]

    def setOpacity(self, valor: float) -> None:
        valor = max(0.0, min(1.0, float(valor)))
        if valor != self._alfa:
            self._alfa = valor
            self._a_medias()

    def set_desp(self, dy: float) -> None:
        if dy != self._desp:
            self._desp = float(dy)
            self._a_medias()

    def _rehacer(self) -> None:
        w, h = self.width(), self.height()      # type: ignore[attr-defined]
        if w <= 0 or h <= 0 or self._renderizando:
            return
        dpr = self.devicePixelRatioF()          # type: ignore[attr-defined]
        pm = QPixmap(math.ceil(w * dpr), math.ceil(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        self._renderizando = True
        try:
            self.render(pm, QPoint(), QRegion(), QWidget.RenderFlag.DrawWindowBackground)   # type: ignore[attr-defined]
        finally:
            self._renderizando = False
        self._cache = pm

    def _rehacer_y_pintar(self) -> None:
        if not sip.isdeleted(self):
            self._rehacer()
            self.update()                       # type: ignore[attr-defined]

    def event(self, evento) -> bool:
        tipo = evento.type()
        if tipo in _EVENTOS_QUE_INVALIDAN:
            self._cache = None                  # cambió algo que se ve (estilo, fuente, hover, tamaño…)
        return super().event(evento)            # type: ignore[misc]

    def paintEvent(self, evento) -> None:
        if self._renderizando or self._en_reposo():
            super().paintEvent(evento)          # type: ignore[misc]
            return
        if self._alfa <= 0.001:
            return
        if self._cache is None:                 # contenido nuevo a medio fundir: se rehace tras este fotograma
            QTimer.singleShot(0, self._rehacer_y_pintar)
            return
        p = QPainter(self)                      # type: ignore[arg-type]
        p.setOpacity(self._alfa)
        p.drawPixmap(QPointF(0.0, self._desp), self._cache)
        p.end()


_EVENTOS_QUE_INVALIDAN = frozenset({
    QEvent.Type.Resize, QEvent.Type.StyleChange, QEvent.Type.FontChange, QEvent.Type.EnabledChange,
    QEvent.Type.PaletteChange, QEvent.Type.LanguageChange, QEvent.Type.Enter, QEvent.Type.Leave,
    QEvent.Type.HoverEnter, QEvent.Type.HoverLeave, QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
    QEvent.Type.ToolTipChange, QEvent.Type.WindowIconChange,
})


class EtiquetaFundible(_Fundible, QLabel):
    """QLabel con opacidad y desplazamiento propios (cifras y detalle de las tarjetas, indicador de tendencia)."""

    def setText(self, texto: str) -> None:
        if texto != self.text():
            self._cache = None
        super().setText(texto)


class BotonFundible(_Fundible, QToolButton):
    """QToolButton con opacidad propia (menú ⋯ y quitar de las baldosas: aparecen y se van con un fundido)."""

    def setIcon(self, icono) -> None:
        self._cache = None
        super().setIcon(icono)


class TarjetaKpi(QFrame):
    """Tarjeta de un indicador: título y una cifra que cuenta hasta su valor.

    Al pasar el mouse la cifra se desliza hacia arriba y se funde con el detalle desglosado (``set_detalle``), y un clic
    avisa para abrir el panel lateral. El dato final (``texto``) está disponible aunque el dibujo esté animado.
    Estados (``set_estado``): ``cargando`` (la cifra respira), ``vacio``, ``error`` y ``ok``. La elevación y la presión
    las pone la baldosa que la contiene (un único ``EfectoMovimiento``); aquí no hay efectos gráficos que se anidarían.
    """

    clicked = pyqtSignal()
    DESLIZAMIENTO = 6.0     # px que se desplaza la cifra al ceder su sitio al detalle

    def __init__(self, titulo: str, color: str = VERDE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._final, self._numero, self._anim = "—", 0.0, None
        self._ultimo: float | None = None      # último valor real mostrado (para el indicador de tendencia)
        self._detalle_texto = ""
        self._volteada = False
        self._anim_volteo = None
        self._estado = "inicial"
        self._anim_estado: QVariantAnimation | None = None
        self._anim_tend = None
        self._titulo = QLabel(titulo)
        self._titulo.setObjectName("cardTitulo")
        self._valor = EtiquetaFundible("—")
        self._valor.setObjectName("cardValor")
        self._valor.setMinimumHeight(34)
        self._detalle = EtiquetaFundible("")
        self._detalle.setObjectName("cardDetalle")
        self._detalle.setMinimumHeight(34)
        self._detalle.setWordWrap(True)
        self._detalle.hide()
        self._pista = QLabel("↗  Ver detalle")
        self._pista.setObjectName("cardPista")
        self._pista.hide()
        # Compatibilidad: las «opacidades» son las propias etiquetas (misma API opacity()/setOpacity()).
        self._op_valor = self._valor
        self._op_detalle = self._detalle
        self._op_detalle.setOpacity(0.0)
        self._tendencia = EtiquetaFundible("")
        self._tendencia.setObjectName("cardDetalle")
        self._tendencia.setOpacity(0.0)
        self._tendencia.hide()
        self._capa = QStackedLayout()
        self._capa.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self._capa.addWidget(self._valor)
        self._capa.addWidget(self._detalle)
        cabecera = QHBoxLayout()
        cabecera.setContentsMargins(0, 0, 0, 0)
        cabecera.addWidget(self._titulo, 1)
        cabecera.addWidget(self._tendencia, 0, Qt.AlignmentFlag.AlignRight)
        texto = QVBoxLayout()
        texto.setSpacing(2)
        texto.addLayout(cabecera)
        texto.addLayout(self._capa)
        texto.addWidget(self._pista)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.addLayout(texto, 1)
        if color != VERDE:  # solo las cifras con significado (faltante, sobrante) llevan color
            self._valor.setStyleSheet(f"color: {color};")

    def texto(self) -> str:
        """El valor final, aunque la cifra todavía esté contando."""
        return self._final

    def texto_visible(self) -> str:
        return self._valor.text()

    def detalle(self) -> str:
        return self._detalle_texto

    def estado(self) -> str:
        return self._estado

    def tendencia_visible(self) -> str:
        """El texto del indicador de tendencia si está a la vista («▲ 3»), o ``""``."""
        return self._tendencia.text() if self._tendencia.isVisibleTo(self) and self._tendencia.opacity() > 0.01 else ""

    # ------------------------------------------------------------------ estados
    def set_estado(self, estado: str) -> None:
        """``cargando`` (la consulta sigue en curso), ``vacio`` (sin dato), ``error`` (falló) u ``ok`` (dato real)."""
        if estado == self._estado:
            return
        self._estado = estado
        _detener(self._anim_estado)
        self._anim_estado = None
        if estado == "cargando" and _decorativo() and self.isVisible():
            anim = QVariantAnimation(self)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setDuration(1300)
            anim.setLoopCount(-1)
            anim.setEasingCurve(QEasingCurve.Type.Linear)
            anim.valueChanged.connect(lambda v: self._valor.setOpacity(0.42 + 0.36 * math.sin(math.pi * float(v))))
            anim.start()
            self._anim_estado = anim
        elif estado == "ok":
            self._valor.setOpacity(1.0)
        elif estado in ("vacio", "error"):
            self._valor.setOpacity(0.55)
            if estado == "error" and ANIMAR and self.isVisible():
                from . import motion
                motion.sacudir(self, amplitud=3, ms=260)
        else:
            self._valor.setOpacity(1.0)

    def _normalizar(self) -> None:
        """Si el cursor ya no está encima, la tarjeta vuelve a mostrar la cifra.

        Qt no manda ``leaveEvent`` cuando la tarjeta se reubica o se oculta bajo el cursor (p. ej. al agregarla con el
        catálogo abierto): sin esto la cifra se quedaba a opacidad 0 para siempre.
        """
        if self.underMouse():
            return
        _detener(self._anim_volteo)
        self._volteada = False
        self._detalle.setVisible(False)
        self._detalle.setOpacity(0.0)
        self._detalle.set_desp(0.0)
        self._valor.set_desp(0.0)
        if self._anim_estado is None:            # si la cifra está respirando, el ciclo manda sobre su opacidad
            self._valor.setOpacity(1.0 if self._estado in ("ok", "inicial", "cargando") else 0.55)
        self._pista.hide()

    def set_detalle(self, texto: str) -> None:
        self._detalle_texto = texto
        self._detalle.setText(texto)
        self._detalle.setVisible(self._volteada and bool(texto))
        self._normalizar()

    def set_texto(self, texto: str) -> None:
        self._normalizar()
        _detener(self._anim)
        self._final, self._numero = texto, 0.0
        self._valor.setText(texto)

    def set_valor(self, numero: float | None, formato: Callable[[float], str]) -> None:
        """Muestra ``formato(numero)`` contando desde la cifra anterior; ``None`` deja «—» (estado vacío)."""
        if numero is None:
            self.set_texto("—")
            self._ultimo = None
            self.set_estado("vacio")
            return
        self.set_estado("ok")
        self._normalizar()
        _detener(self._anim)
        self._final = formato(numero)
        inicio, self._numero = self._numero, float(numero)
        previo, self._ultimo = self._ultimo, float(numero)
        if previo is not None and previo != float(numero):
            self._mostrar_tendencia(float(numero) - previo, formato)
        if self._final == self._valor.text():
            return
        ms = _ms(650 if previo is None else 480)
        self._anim = animar(self, inicio, float(numero), ms, lambda v: self._valor.setText(formato(v)),
                            lambda: self._valor.setText(self._final), QEasingCurve.Type.OutQuint)

    # ------------------------------------------------------------------ tendencia
    def _mostrar_tendencia(self, delta: float, formato: Callable[[float], str]) -> None:
        """«▲ 3» / «▼ 3» junto al título cuando el dato real cambia respecto al anterior; se va solo tras unos segundos.

        Es la diferencia real entre dos lecturas, sin interpretar si es bueno o malo (no lleva color)."""
        texto = f"{'▲' if delta > 0 else '▼'} {formato(abs(delta))}"
        _detener(self._anim_tend)
        self._tendencia.setText(texto)
        if not ANIMAR or not self.isVisible():
            self._tendencia.hide()
            return
        self._tendencia.show()
        salto = _px(4.0)
        self._tendencia.set_desp(salto)
        self._tendencia.setOpacity(0.0)
        self._anim_tend = animar(self, 0.0, 1.0, _ms(260),
                                 lambda v: (self._tendencia.setOpacity(v), self._tendencia.set_desp(salto * (1 - v))),
                                 lambda: QTimer.singleShot(3200, self._ocultar_tendencia),
                                 QEasingCurve.Type.OutCubic)

    def _ocultar_tendencia(self) -> None:
        if sip.isdeleted(self):
            return
        if not ANIMAR or not self.isVisible():
            self._tendencia.hide()
            return
        inicio = self._tendencia.opacity()
        _detener(self._anim_tend)
        self._anim_tend = animar(self, inicio, 0.0, _ms(320), self._tendencia.setOpacity, self._tendencia.hide,
                                 QEasingCurve.Type.InCubic)

    # ------------------------------------------------------------------ hover y clic
    def enterEvent(self, evento) -> None:
        self.setProperty("hover", True)
        self.style().unpolish(self)
        self.style().polish(self)
        if not ANIMAR:
            self._voltear(True)
        else:
            _detener(self._anim_volteo)
            self._anim_volteo = animar(self, 0.0, 1.0, _ms(240), lambda v: self._mezclar(v, True),
                                       curva=QEasingCurve.Type.OutCubic)
        self._pista.setVisible(bool(self._detalle_texto))
        super().enterEvent(evento)

    def leaveEvent(self, evento) -> None:
        self.setProperty("hover", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self._pista.hide()
        if not ANIMAR:
            self._voltear(False)
        else:
            _detener(self._anim_volteo)
            self._anim_volteo = animar(self, 0.0, 1.0, _ms(240), lambda v: self._mezclar(v, False),
                                       curva=QEasingCurve.Type.OutCubic)
        super().leaveEvent(evento)

    def _mezclar(self, v: float, hacia_detalle: bool) -> None:
        """La cifra sube y se funde mientras el detalle sube desde abajo (sin bloquear el dato)."""
        hay = bool(self._detalle_texto)
        self._detalle.setVisible(hay)
        if not hay:
            self._detalle.setOpacity(0.0)             # sin detalle que mostrar, la cifra nunca se desvanece
            self._detalle.set_desp(0.0)
            self._valor.set_desp(0.0)
            if self._anim_estado is None:
                self._valor.setOpacity(1.0 if self._estado in ("ok", "inicial") else 0.55)
            return
        x = v if hacia_detalle else 1.0 - v            # 0 = se ve la cifra, 1 = se ve el detalle
        if self._anim_estado is None:
            self._valor.setOpacity(1.0 - x)
        desliz = _px(self.DESLIZAMIENTO)
        self._valor.set_desp(-desliz * x)
        self._detalle.setOpacity(x)
        self._detalle.set_desp(desliz * (1.0 - x))

    def _voltear(self, hacia_detalle: bool) -> None:
        self._volteada = hacia_detalle and bool(self._detalle_texto)
        self._detalle.setVisible(self._volteada)
        self._detalle.setOpacity(1.0 if self._volteada else 0.0)
        self._detalle.set_desp(0.0)
        self._valor.set_desp(0.0)
        self._valor.setOpacity(0.0 if self._volteada else (1.0 if self._estado in ("ok", "inicial") else 0.55))

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        if self._estado == "cargando" and self._anim_estado is None:
            estado, self._estado = self._estado, "inicial"
            self.set_estado(estado)

    def hideEvent(self, evento) -> None:
        if self._anim_estado is not None:           # la respiración solo corre con la tarjeta a la vista
            _detener(self._anim_estado)
            self._anim_estado = None
            self._valor.setOpacity(1.0)
        self._normalizar()
        super().hideEvent(evento)

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(evento)


class Anillo(QWidget):
    """Anillo de porcentaje (0–100) que se llena hasta su valor, con la cifra en el centro."""

    def __init__(self, titulo: str, color: str = VERDE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._titulo, self._color = titulo, QColor(color)
        self._valor: float | None = None
        self._visible, self._anim = 0.0, None
        self._desde = 0.0              # de dónde parte la transición en curso
        self._asentado = 1.0           # 0 = la cifra va en camino (se atenúa); 1 = ya es el valor definitivo
        self.setMinimumSize(170, 210)

    def valor(self) -> float | None:
        return self._valor

    def valor_visible(self) -> float:
        return self._visible

    def en_transicion(self) -> bool:
        return self._asentado < 1.0

    def set_valor(self, valor: float | None) -> None:
        """Nuevo porcentaje real: el arco **parte del que se veía** y la cifra del centro lo acompaña. Mientras avanzan, la
        cifra va atenuada (un valor en camino no se presenta como definitivo) y recupera su tinta al asentarse."""
        nuevo = None if valor is None else float(valor)
        destino = nuevo or 0.0
        if nuevo == self._valor and (self._asentado < 1.0 or self._visible == destino):
            return                                    # el mismo dato (cada refresco lo repite): no se reinicia nada
        _detener(self._anim)
        primera = self._valor is None and self._visible == 0.0
        self._valor = nuevo
        self._desde, self._asentado = self._visible, 0.0
        self._anim = animar(self, self._visible, destino, _ms(900 if primera else 560), self._pintar_hasta,
                            self._asentar)

    def _asentar(self) -> None:
        self._visible = self._valor or 0.0
        self._asentado = 1.0
        self.update()

    def _pintar_hasta(self, v: float) -> None:
        self._visible = v
        destino = self._valor or 0.0
        recorrido = abs(destino - self._desde)
        self._asentado = 1.0 if recorrido < 1e-9 else max(0.0, min(1.0, 1.0 - abs(destino - v) / recorrido))
        self.update()

    def terminar(self) -> None:
        """Salta al valor definitivo (Guardar PNG exporta siempre el dato real, nunca uno a medias)."""
        _detener(self._anim)
        self._asentar()

    def revelar(self) -> None:
        """Repite la entrada: el arco vuelve a llenarse desde cero (la baldosa acaba de aparecer)."""
        _detener(self._anim)
        self._visible, self._desde, self._asentado = 0.0, 0.0, 0.0
        self._anim = animar(self, 0.0, self._valor or 0.0, _ms(900), self._pintar_hasta, self._asentar)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lado = min(self.width() - 24, self.height() - 52, 200)
        grosor = max(10.0, lado * 0.11)
        # El trazo se dibuja centrado en el borde de la caja: se deja medio grosor de margen para que no se recorte.
        caja = QRectF((self.width() - lado) / 2, 10 + grosor / 2, lado, lado)
        p.setPen(QPen(QColor(PISTA), grosor, cap=Qt.PenCapStyle.RoundCap))
        p.drawArc(caja, 0, 360 * 16)
        if self._valor is not None and self._visible > 0:
            p.setPen(QPen(self._color, grosor, cap=Qt.PenCapStyle.RoundCap))
            p.drawArc(caja, 90 * 16, -int(360 * 16 * min(self._visible, 100.0) / 100.0))
        tinta, suave = QColor(TINTA), QColor(TINTA_SUAVE)
        a = self._asentado                        # la cifra en camino va atenuada; al asentarse recupera su tinta
        p.setPen(QColor(int(suave.red() + (tinta.red() - suave.red()) * a),
                        int(suave.green() + (tinta.green() - suave.green()) * a),
                        int(suave.blue() + (tinta.blue() - suave.blue()) * a)))
        fuente = QFont(self.font())
        fuente.setPixelSize(int(lado * 0.2))
        fuente.setBold(True)
        p.setFont(fuente)
        texto = "—" if self._valor is None else i18n.porcentaje(self._visible)
        p.drawText(caja, Qt.AlignmentFlag.AlignCenter, texto)
        fuente.setPixelSize(13)
        fuente.setBold(False)
        p.setFont(fuente)
        p.setPen(QColor(TINTA_SUAVE))
        p.drawText(QRectF(0, caja.bottom() + grosor / 2 + 8, self.width(), 22), Qt.AlignmentFlag.AlignCenter, self._titulo)


def _mezclar_color(a: str, b: str, t: float) -> QColor:
    """Color intermedio entre ``a`` (t = 0) y ``b`` (t = 1)."""
    ca, cb = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(int(ca.red() + (cb.red() - ca.red()) * t), int(ca.green() + (cb.green() - ca.green()) * t),
                  int(ca.blue() + (cb.blue() - ca.blue()) * t))


class _SeriesAlternables:
    """Leyenda interactiva de Dona y BarraSegmentada: ocultar o mostrar una serie la **repliega o la recupera con una
    transición** (el resto y el total del centro la acompañan) en vez de saltar.

    ``_ocultas`` cambia al instante (es el dato, y lo que lee el resto de la pantalla); ``_factor`` es solo el dibujo:
    1 = visible, 0 = oculta, y entre ambos mientras dura la transición."""

    def _iniciar_vis(self) -> None:
        self._vis: dict[str, float] = {}
        self._vis_anim = None

    def _factor(self, clave: str) -> float:
        return self._vis.get(clave, 0.0 if clave in self._ocultas else 1.0)    # type: ignore[attr-defined]

    def _claves_serie(self) -> list[str]:              # pragma: no cover - lo define cada gráfica
        raise NotImplementedError

    def _alternar(self, clave: str) -> None:
        claves = self._claves_serie()
        antes = {c: self._factor(c) for c in claves}
        if clave in self._ocultas:                      # type: ignore[attr-defined]
            self._ocultas.discard(clave)                # type: ignore[attr-defined]
        else:
            self._ocultas.add(clave)                    # type: ignore[attr-defined]
        hasta = {c: 0.0 if c in self._ocultas else 1.0 for c in claves}   # type: ignore[attr-defined]
        _detener(self._vis_anim)

        def paso(v: float) -> None:
            if not sip.isdeleted(self):                 # type: ignore[arg-type]
                self._vis = {c: antes[c] + (hasta[c] - antes[c]) * v for c in hasta}
                self.update()                           # type: ignore[attr-defined]

        def fin() -> None:
            if not sip.isdeleted(self):                 # type: ignore[arg-type]
                self._vis = {}
                self.update()                           # type: ignore[attr-defined]

        self._vis_anim = animar(self, 0.0, 1.0, _ms(340), paso, fin)  # type: ignore[arg-type]
        self.update()                                   # type: ignore[attr-defined]


class BarraSegmentada(_SeriesAlternables, QWidget):
    """Una barra partida en segmentos proporcionales (crece de izquierda a derecha) con su leyenda debajo.

    Al hacer clic en una entrada de la leyenda se oculta o muestra esa serie (con atenuación de la leyenda).
    """

    alternada = pyqtSignal(str)

    def __init__(self, colores: dict[str, str], nombres: dict[str, str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._iniciar_vis()
        self._colores, self._nombres = colores, nombres or {}
        self._segmentos: list[tuple[str, int]] = []
        self._avance, self._anim = 1.0, None
        self._prev: dict[str, float] = {}      # cuánto se dibujaba de cada serie al empezar una transición
        self._mezcla = 1.0
        self._ocultas: set[str] = set()
        self._leyenda: list[tuple[QRectF, str]] = []
        self.setMinimumHeight(58)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def segmentos(self) -> list[tuple[str, int]]:
        return list(self._segmentos)

    def set_segmentos(self, segmentos: list[tuple[str, int]]) -> None:
        """Dato nuevo: si ya había segmentos, los reales anteriores se interpolan hacia los nuevos (sin vaciarse);
        la primera vez la barra crece desde la izquierda. El estado final es siempre exactamente ``segmentos``."""
        cambio = segmentos != self._segmentos
        previos = {c: self._n_vis(c, n) for c, n in self._segmentos} if self._segmentos else {}
        self._segmentos = list(segmentos)
        if cambio:
            _detener(self._anim)
            if previos:
                self._prev, self._mezcla, self._avance = previos, 0.0, 1.0
                self._anim = animar(self, 0.0, 1.0, _ms(460), self._mezclar)
            else:
                self._prev, self._mezcla, self._avance = {}, 1.0, 0.0
                self._anim = animar(self, 0.0, 1.0, _ms(700), self._pintar_hasta)
        self.update()

    def _n_vis(self, clave: str, n: float) -> float:
        if self._mezcla >= 1.0 or not self._prev:
            return n
        ant = self._prev.get(clave, 0.0)
        return ant + (n - ant) * self._mezcla

    def _mezclar(self, v: float) -> None:
        self._mezcla = v
        if v >= 1.0:
            self._prev = {}
        self.update()

    def _pintar_hasta(self, v: float) -> None:
        self._avance = v
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ancho, alto = self.width(), 16
        fondo = QPainterPath()
        fondo.addRoundedRect(QRectF(0, 4, ancho, alto), 8, 8)
        p.fillPath(fondo, QColor(PISTA))
        visibles = [(c, self._n_vis(c, n) * self._factor(c)) for c, n in self._segmentos if self._factor(c) > 0.001]
        total = sum(n for _, n in visibles)
        if total > 0:
            p.setClipPath(fondo)
            x = 0.0
            for clave, n in visibles:
                tramo = ancho * n / total * self._avance
                p.fillRect(QRectF(x, 4, tramo, alto), QColor(self._colores.get(clave, VERDE)))
                x += tramo
            p.setClipping(False)
        fuente = QFont(self.font())
        fuente.setPixelSize(12)
        p.setFont(fuente)
        self._leyenda = []
        x = 0.0
        for clave, n in self._segmentos:
            factor = self._factor(clave)
            tono = QColor(self._colores.get(clave, VERDE))
            tono.setAlpha(int(70 + 185 * factor))
            p.setBrush(tono)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x + 5, 40), 5, 5)
            p.setPen(_mezclar_color(TINTA_SUAVE, TINTA, factor))
            texto = f"{self._nombres.get(clave, clave)}  {n}"
            ancho_texto = p.fontMetrics().horizontalAdvance(texto)
            p.drawText(QRectF(x + 15, 30, 200, 20), Qt.AlignmentFlag.AlignVCenter, texto)
            self._leyenda.append((QRectF(x, 28, 18 + ancho_texto, 24), clave))
            x += 28 + ancho_texto

    def _claves_serie(self) -> list[str]:
        return [c for c, _ in self._segmentos]

    def mousePressEvent(self, evento) -> None:
        for caja, clave in self._leyenda:
            if caja.contains(evento.position()):
                self._alternar(clave)
                self.alternada.emit(clave)
                evento.accept()
                return
        super().mousePressEvent(evento)


class Dona(_SeriesAlternables, QWidget):
    """Gráfica de dona: los sectores se abren en abanico hasta su tamaño; el total va en el centro.

    Al pasar el cursor por un sector (o por su fila de la leyenda) ese sector crece un poco y los demás se atenúan; ocultar
    o mostrar una serie con la leyenda la repliega o la recupera con una transición y el total del centro la sigue."""

    alternada = pyqtSignal(str)       # clic en la leyenda: clave del sector que se oculta o muestra

    def __init__(self, colores: dict[str, str], nombres: dict[str, str] | None = None, parent: QWidget | None = None,
                 unidad: str = "SKU") -> None:
        super().__init__(parent)
        self._iniciar_vis()
        self._colores, self._nombres, self._unidad = colores, nombres or {}, unidad
        self._datos: list[tuple[str, float]] = []
        self._avance, self._anim = 1.0, None
        self._prev: dict[str, float] = {}
        self._mezcla = 1.0
        self._ocultas: set[str] = set()
        self._leyenda: list[tuple[QRectF, str]] = []
        self._sectores: list[tuple[str, float, float]] = []     # (clave, inicio, barrido) en grados, desde arriba, horario
        self._geo: tuple[float, float, float, float] | None = None   # centro x, y, radio del aro y grosor
        self._hover: str | None = None
        self._hov: dict[str, float] = {}            # realce de cada sector (0–1), con transición
        self._hov_desde: dict[str, float] = {}
        self._hov_hasta: dict[str, float] = {}
        self._a_hover = QVariantAnimation(self)     # una sola, reutilizada en cada cambio de hover
        self._a_hover.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._a_hover.valueChanged.connect(self._paso_hover)
        self.setMinimumHeight(230)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _claves_serie(self) -> list[str]:
        return [c for c, _ in self._datos]

    def hover(self) -> str | None:
        return self._hover

    def _apuntar(self, clave: str | None) -> None:
        if clave == self._hover:
            return
        self._hover = clave
        claves = [c for c, _ in self._datos]
        hasta = {c: 1.0 if c == clave else 0.0 for c in claves}
        if not ANIMAR:
            self._hov = hasta
            self.update()
            return
        self._hov_desde = {c: self._hov.get(c, 0.0) for c in claves}
        self._hov_hasta = hasta
        self._a_hover.stop()
        self._a_hover.setDuration(_ms(150))
        self._a_hover.setStartValue(0.0)
        self._a_hover.setEndValue(1.0)
        self._a_hover.start()

    def _paso_hover(self, v) -> None:
        f = float(v)
        self._hov = {c: d + (self._hov_hasta.get(c, 0.0) - d) * f for c, d in self._hov_desde.items()}
        self.update()

    def _sector_en(self, pos: QPointF) -> str | None:
        if self._geo is None:
            return None
        cx, cy, radio, grosor = self._geo
        dx, dy = pos.x() - cx, pos.y() - cy
        if abs(math.hypot(dx, dy) - radio) > grosor / 2 + 3:
            return None
        ang = math.degrees(math.atan2(dx, -dy)) % 360.0
        for clave, inicio, barrido in self._sectores:
            if inicio <= ang < inicio + barrido:
                return clave
        return None

    def mouseMoveEvent(self, evento) -> None:
        clave = next((c for caja, c in self._leyenda if caja.contains(evento.position())), None)
        self._apuntar(clave if clave is not None else self._sector_en(evento.position()))
        super().mouseMoveEvent(evento)

    def leaveEvent(self, evento) -> None:
        self._apuntar(None)
        super().leaveEvent(evento)

    def datos(self) -> list[tuple[str, float]]:
        return list(self._datos)

    def set_datos(self, datos: list[tuple[str, float]]) -> None:
        """Distribución nueva: los sectores reales anteriores se interpolan hacia los nuevos (el total del centro los
        sigue); la primera vez se abren en abanico. El estado final es exactamente ``datos``."""
        cambio = datos != self._datos
        previos = {c: self._v_vis(c, v) for c, v in self._datos} if self._datos else {}
        self._datos = list(datos)
        if cambio:
            _detener(self._anim)
            if previos:
                self._prev, self._mezcla, self._avance = previos, 0.0, 1.0
                self._anim = animar(self, 0.0, 1.0, _ms(520), self._mezclar)
            else:
                self._prev, self._mezcla, self._avance = {}, 1.0, 0.0
                self._anim = animar(self, 0.0, 1.0, _ms(850), self._pintar_hasta)
        self.update()

    def _v_vis(self, clave: str, v: float) -> float:
        if self._mezcla >= 1.0 or not self._prev:
            return v
        ant = self._prev.get(clave, 0.0)
        return ant + (v - ant) * self._mezcla

    def _mezclar(self, v: float) -> None:
        self._mezcla = v
        if v >= 1.0:
            self._prev = {}
        self.update()

    def _pintar_hasta(self, v: float) -> None:
        self._avance = v
        self.update()

    def terminar(self) -> None:
        """Salta al estado final real (sin transiciones a medias): lo usa Guardar PNG."""
        _detener(self._anim)
        _detener(self._vis_anim)
        self._a_hover.stop()
        self._prev, self._mezcla, self._avance, self._vis = {}, 1.0, 1.0, {}
        self.update()

    def revelar(self) -> None:
        """Repite la entrada: los sectores se abren de nuevo en abanico (la baldosa acaba de aparecer)."""
        _detener(self._anim)
        self._prev, self._mezcla, self._avance = {}, 1.0, 0.0
        self._anim = animar(self, 0.0, 1.0, _ms(850), self._pintar_hasta)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lado = min(self.height() - 20, self.width() * 0.42)
        caja = QRectF(16, (self.height() - lado) / 2, lado, lado)
        grosor = lado * 0.2
        aro = caja.adjusted(grosor / 2, grosor / 2, -grosor / 2, -grosor / 2)
        visibles = [(c, self._v_vis(c, v) * self._factor(c)) for c, v in self._datos if self._factor(c) > 0.001]
        total = sum(v for _, v in visibles)
        p.setPen(QPen(QColor(PISTA), grosor))
        p.drawArc(aro, 0, 360 * 16)
        angulo = 90.0
        self._geo = (aro.center().x(), aro.center().y(), aro.width() / 2, grosor)
        self._sectores = []
        atenuacion = max(self._hov.values(), default=0.0)       # cuánto hay de «algo señalado» (0 = nada)
        if total > 0:
            recorrido = 0.0
            for clave, v in visibles:
                barrido = 360.0 * v / total * self._avance
                realce = self._hov.get(clave, 0.0)
                color = QColor(self._colores.get(clave, VERDE))
                color.setAlphaF(1.0 - 0.5 * atenuacion * (1.0 - realce))
                p.setPen(QPen(color, grosor * (1.0 + 0.14 * realce), cap=Qt.PenCapStyle.FlatCap))
                p.drawArc(aro, int(angulo * 16), -int(barrido * 16))
                self._sectores.append((clave, recorrido, barrido))
                angulo -= barrido
                recorrido += barrido
        fuente = QFont(self.font())
        fuente.setPixelSize(int(lado * 0.2))
        fuente.setBold(True)
        p.setFont(fuente)
        p.setPen(QColor(TINTA))
        p.drawText(caja.adjusted(0, -8, 0, -8), Qt.AlignmentFlag.AlignCenter, f"{total * self._avance:.0f}")
        fuente.setPixelSize(12)
        fuente.setBold(False)
        p.setFont(fuente)
        p.setPen(QColor(TINTA_SUAVE))
        p.drawText(caja.adjusted(0, lado * 0.2, 0, lado * 0.2), Qt.AlignmentFlag.AlignCenter, self._unidad)
        # Leyenda a la derecha, con el porcentaje de cada sector.
        x, y = caja.right() + 24, caja.top() + max(0.0, (lado - 28 * len(self._datos)) / 2)
        fuente.setPixelSize(13)
        p.setFont(fuente)
        self._leyenda = []
        for clave, v in self._datos:
            factor = self._factor(clave)
            tono = QColor(self._colores.get(clave, VERDE))
            tono.setAlpha(int(70 + 185 * factor))
            realce = self._hov.get(clave, 0.0)
            if realce > 0.01:                                    # fila señalada: un fondo suave que aparece y se va
                fondo = QColor(TINTA)
                fondo.setAlpha(int(26 * realce))
                p.setBrush(fondo)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(QRectF(x - 6, y, max(40, self.width() - x - 14), 24), 7, 7)
            p.setBrush(tono)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(x, y + 4, 12, 12), 3, 3)
            p.setPen(_mezclar_color(TINTA_SUAVE, TINTA, factor))
            pct = f"{100 * v / total:.0f} %" if total > 0 else "—"
            p.drawText(QRectF(x + 20, y, self.width() - x - 24, 20), Qt.AlignmentFlag.AlignVCenter,
                       f"{self._nombres.get(clave, clave)}  ·  {v:.0f}  ({pct})")
            self._leyenda.append((QRectF(x, y, max(40, self.width() - x - 20), 24), clave))
            y += 28

    def mousePressEvent(self, evento) -> None:
        for caja, clave in self._leyenda:
            if caja.contains(evento.position()):
                self._alternar(clave)
                self.alternada.emit(clave)
                evento.accept()
                return
        super().mousePressEvent(evento)


class MapaUbicaciones(QWidget):
    """Mapa de calor de las ubicaciones: una fila por zona y una celda por ubicación, más intensa cuanto más se contó."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._datos: list[tuple[str, str, int]] = []
        self._avance, self._anim = 1.0, None
        self._prev: dict[str, float] = {}      # intensidad (SKU) que tenía cada ubicación al empezar la transición
        self._mezcla = 1.0
        self.setMinimumHeight(170)

    def datos(self) -> list[tuple[str, str, int]]:
        return list(self._datos)

    def set_datos(self, datos: list[tuple[str, str, int]]) -> None:
        cambio = datos != self._datos
        previos = {c: self._sk_vis(c, k) for c, _z, k in self._datos} if self._datos else {}
        self._datos = list(datos)
        zonas = len({z for _, z, _ in datos})
        self.setMinimumHeight(max(170, 30 + 62 * zonas))
        if cambio:
            _detener(self._anim)
            if previos:                       # cambio de filtro: la intensidad de cada celda se interpola
                self._prev, self._mezcla, self._avance = previos, 0.0, 1.0
                self._anim = animar(self, 0.0, 1.0, 460, self._mezclar)
            else:                             # primera vez: las celdas se revelan
                self._prev, self._mezcla, self._avance = {}, 1.0, 0.0
                self._anim = animar(self, 0.0, 1.0, 700, self._pintar_hasta)
        self.update()

    def _sk_vis(self, cod: str, skus: float) -> float:
        if self._mezcla >= 1.0 or not self._prev:
            return skus
        ant = self._prev.get(cod, 0.0)
        return ant + (skus - ant) * self._mezcla

    def _mezclar(self, v: float) -> None:
        self._mezcla = v
        if v >= 1.0:
            self._prev = {}
        self.update()

    def _pintar_hasta(self, v: float) -> None:
        self._avance = v
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        por_zona: dict[str, list[tuple[str, int]]] = {}
        for cod, zona, skus in self._datos:
            por_zona.setdefault(zona, []).append((cod, skus))
        if not por_zona:
            return
        maximo = max((s for _, _, s in self._datos), default=0) or 1
        columnas = max(len(v) for v in por_zona.values())
        margen, alto = 74, 52
        ancho = max(40.0, min(240.0, (self.width() - margen - 8) / columnas - 8))
        fuente = QFont(self.font())
        base, tope = QColor(PISTA), QColor(VERDE)
        for fila, (zona, celdas) in enumerate(sorted(por_zona.items())):
            y = 8 + fila * (alto + 10)
            fuente.setPixelSize(13)
            fuente.setBold(True)
            p.setFont(fuente)
            p.setPen(QColor(TINTA_SUAVE))
            p.drawText(QRectF(0, y, margen - 8, alto), Qt.AlignmentFlag.AlignVCenter, f"Zona {zona}")
            for col, (cod, skus) in enumerate(celdas):
                t = (self._sk_vis(cod, skus) / maximo) * self._avance
                color = QColor(int(base.red() + (tope.red() - base.red()) * t),
                               int(base.green() + (tope.green() - base.green()) * t),
                               int(base.blue() + (tope.blue() - base.blue()) * t))
                caja = QRectF(margen + col * (ancho + 8), y, ancho, alto)
                camino = QPainterPath()
                camino.addRoundedRect(caja, 10, 10)
                p.fillPath(camino, color)
                p.setPen(QColor("#FFFFFF" if t > 0.45 else TINTA))
                fuente.setPixelSize(12)
                fuente.setBold(True)
                p.setFont(fuente)
                p.drawText(caja.adjusted(0, 6, 0, -alto / 2), Qt.AlignmentFlag.AlignCenter, cod)
                fuente.setBold(False)
                p.setFont(fuente)
                p.drawText(caja.adjusted(0, alto / 2 - 4, 0, -6), Qt.AlignmentFlag.AlignCenter,
                           "sin contar" if skus == 0 else f"{skus} SKU")


class Chip(QPushButton):
    """Botón de filtro rápido con forma de píldora (se queda marcado)."""

    def __init__(self, texto: str = "", parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self.setObjectName("chip")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class Pasos(QWidget):
    """Las etapas de una sincronización en fila; la actual late y las anteriores quedan marcadas."""

    def __init__(self, nombres: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._nombres, self._actual, self._fase = list(nombres), None, 0.0
        self.setMinimumHeight(64)
        self._latido = QVariantAnimation(self)
        self._latido.setStartValue(0.0)
        self._latido.setEndValue(1.0)
        self._latido.setDuration(1400)
        self._latido.setLoopCount(-1)
        self._latido.valueChanged.connect(self._latir)

    def nombres(self) -> list[str]:
        return list(self._nombres)

    def actual(self) -> str | None:
        return self._actual

    def set_actual(self, nombre: str | None) -> None:
        self._actual = nombre if nombre in self._nombres else None
        ultimo = self._actual == self._nombres[-1]
        if ANIMAR and self._actual is not None and not ultimo and self.isVisible():
            self._latido.start()
        else:
            self._latido.stop()
            self._fase = 0.0
        self.update()

    def hideEvent(self, evento) -> None:
        self._latido.stop()
        super().hideEvent(evento)

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        self.set_actual(self._actual)

    def _latir(self, v) -> None:
        self._fase = float(v)
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(self._nombres)
        paso = self.width() / n
        indice = self._nombres.index(self._actual) if self._actual else -1
        cy, radio = 22.0, 13.0
        for i in range(n - 1):
            hecho = i < indice
            p.setPen(QPen(QColor(VERDE if hecho else LINEA), 3))
            p.drawLine(QPointF(paso * (i + 0.5) + radio + 4, cy), QPointF(paso * (i + 1.5) - radio - 4, cy))
        fuente = QFont(self.font())
        for i, nombre in enumerate(self._nombres):
            cx = paso * (i + 0.5)
            terminado = indice >= 0 and (i < indice or (i == indice and i == n - 1))
            if i == indice and not terminado:
                halo = QColor(VERDE)
                halo.setAlphaF(0.35 * (1 - self._fase))
                p.setBrush(halo)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(cx, cy), radio + 10 * self._fase, radio + 10 * self._fase)
            p.setBrush(QColor(VERDE if (terminado or i == indice) else "#111111"))
            p.setPen(QPen(QColor(VERDE if (terminado or i == indice) else LINEA), 2))
            p.drawEllipse(QPointF(cx, cy), radio, radio)
            fuente.setPixelSize(12)
            fuente.setBold(True)
            p.setFont(fuente)
            p.setPen(QColor("#04130E" if (terminado or i == indice) else TINTA_SUAVE))
            p.drawText(QRectF(cx - radio, cy - radio, 2 * radio, 2 * radio), Qt.AlignmentFlag.AlignCenter,
                       "✓" if terminado else str(i + 1))
            fuente.setBold(i == indice)
            p.setFont(fuente)
            p.setPen(QColor(TINTA if i <= indice else TINTA_SUAVE))
            p.drawText(QRectF(cx - paso / 2, cy + radio + 8, paso, 20), Qt.AlignmentFlag.AlignCenter, nombre)


class Indicador(QWidget):
    """El estado de la sincronización, dibujado: ondas (esperando), arco que gira (recibiendo), visto o alerta."""

    MODOS = ("reposo", "radar", "progreso", "listo", "error")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._modo, self._fase, self._entrada = "reposo", 0.0, 1.0
        self.setMinimumSize(190, 190)
        self._ciclo = QVariantAnimation(self)
        self._ciclo.setStartValue(0.0)
        self._ciclo.setEndValue(1.0)
        self._ciclo.setDuration(2200)
        self._ciclo.setLoopCount(-1)
        self._ciclo.valueChanged.connect(self._girar)

    def modo(self) -> str:
        return self._modo

    def set_modo(self, modo: str) -> None:
        if modo not in self.MODOS:
            raise ValueError(modo)
        if modo != self._modo:
            self._modo = modo
            animar(self, 0.0, 1.0, 450, self._entrar, curva=QEasingCurve.Type.OutBack)  # el icono «salta» al cambiar
        self._arrancar()
        self.update()

    def _arrancar(self) -> None:
        if ANIMAR and self._modo in ("radar", "progreso") and self.isVisible():
            self._ciclo.start()
        else:
            self._ciclo.stop()

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        self._arrancar()

    def hideEvent(self, evento) -> None:
        self._ciclo.stop()
        super().hideEvent(evento)

    def _girar(self, v) -> None:
        self._fase = float(v)
        self.update()

    def _entrar(self, v: float) -> None:
        self._entrada = v
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        centro = QPointF(self.width() / 2, self.height() / 2)
        radio = min(self.width(), self.height()) / 2 - 6
        azul = QColor("#3B5BDB")
        color = {"listo": QColor(COLOR_CLASIFICACION["OK"]), "error": QColor(COLOR_CLASIFICACION["FALTANTE"])}.get(self._modo, azul)
        if self._modo == "radar":
            for i in range(3):  # tres ondas desfasadas que crecen y se desvanecen
                f = (self._fase + i / 3) % 1.0
                onda = QColor(azul)
                onda.setAlphaF(0.30 * (1 - f))
                p.setBrush(onda)
                p.setPen(Qt.PenStyle.NoPen)
                r = radio * (0.45 + 0.55 * f)
                p.drawEllipse(centro, r, r)
        elif self._modo == "progreso":
            caja = QRectF(centro.x() - radio + 8, centro.y() - radio + 8, 2 * radio - 16, 2 * radio - 16)
            p.setPen(QPen(QColor(PISTA), 10))
            p.drawArc(caja, 0, 360 * 16)
            p.setPen(QPen(QColor(VERDE), 10, cap=Qt.PenCapStyle.RoundCap))
            p.drawArc(caja, int((90 - 360 * self._fase) * 16), -100 * 16)
        nucleo = radio * 0.44 * max(0.2, self._entrada)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(centro, nucleo, nucleo)
        p.setPen(QPen(QColor("#FFFFFF"), max(3.0, nucleo * 0.13), cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        s = nucleo * 0.42
        trazo = QPainterPath()
        if self._modo == "listo":
            trazo.moveTo(centro.x() - s, centro.y())
            trazo.lineTo(centro.x() - s * 0.25, centro.y() + s * 0.7)
            trazo.lineTo(centro.x() + s, centro.y() - s * 0.6)
        elif self._modo == "error":
            trazo.moveTo(centro.x(), centro.y() - s)
            trazo.lineTo(centro.x(), centro.y() + s * 0.25)
            trazo.moveTo(centro.x(), centro.y() + s * 0.85)
            trazo.lineTo(centro.x(), centro.y() + s * 0.9)
        else:  # la runa de Bluetooth
            trazo.moveTo(centro.x() - s * 0.6, centro.y() - s * 0.55)
            trazo.lineTo(centro.x() + s * 0.55, centro.y() + s * 0.55)
            trazo.lineTo(centro.x(), centro.y() + s * 1.1)
            trazo.lineTo(centro.x(), centro.y() - s * 1.1)
            trazo.lineTo(centro.x() + s * 0.55, centro.y() - s * 0.55)
            trazo.lineTo(centro.x() - s * 0.6, centro.y() + s * 0.55)
        p.drawPath(trazo)
