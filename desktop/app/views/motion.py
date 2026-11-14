"""Movimiento, scroll y feedback de la capa de interactividad.

Todo pasa por ``widgets.animar`` y respeta ``APP_SIN_ANIMACIONES=1`` (las pruebas y las capturas): el dato y el
estado final nunca dependen de una animación. Los tiempos siguen la regla del encargo: feedback < 100 ms, transiciones
de 150–300 ms, nada bloquea más de 500 ms.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QObject, QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QLayout,
    QTableView,
    QTableWidget,
    QWidget,
)

from . import widgets

# Tokens de movimiento (ms) y curva por defecto.
RAPIDO, NORMAL, LENTO = 120, 200, 320
CURVA = QEasingCurve.Type.OutCubic
CURVA_SUAVE = QEasingCurve.Type.OutQuint
VERDE = "#10B981"
TINTA_SUAVE = "#8A8A8A"


def animar(dueno: QObject, inicio: float, fin: float, ms: int, paso: Callable[[float], None],
           fin_cb: Callable[[], None] | None = None,
           curva: QEasingCurve.Type = CURVA) -> QVariantAnimation | None:
    """Atajo de ``widgets.animar`` con los tokens de esta capa."""
    return widgets.animar(dueno, inicio, fin, ms, paso, fin_cb, curva)


def detener(anim: QVariantAnimation | None) -> None:
    widgets._detener(anim)


def opacidad(widget: QWidget) -> tuple[QGraphicsOpacityEffect, bool]:
    """Efecto de opacidad reutilizable (Qt solo admite uno por widget)."""
    efecto = widget.graphicsEffect()
    if isinstance(efecto, QGraphicsOpacityEffect):
        return efecto, False
    efecto = QGraphicsOpacityEffect(widget)
    efecto.setOpacity(1.0)
    widget.setGraphicsEffect(efecto)
    return efecto, True


def desvanecer(widget: QWidget, desde: float, hasta: float, ms: int = NORMAL,
               fin_cb: Callable[[], None] | None = None) -> QVariantAnimation | None:
    """Funde un widget entre dos opacidades (sin tocar su visibilidad)."""
    efecto, _ = opacidad(widget)
    efecto.setOpacity(desde)
    return animar(widget, desde, hasta, ms, efecto.setOpacity, fin_cb)


def sombra(widget: QWidget, color: str = "#000000", blur: int = 0, dy: int = 0, alpha: int = 0) -> QGraphicsDropShadowEffect:
    """Sombra elevada; se crea perezosamente para no pagar el costo en widgets que nunca se tocan."""
    efecto = widget.graphicsEffect()
    if not isinstance(efecto, QGraphicsDropShadowEffect):
        efecto = QGraphicsDropShadowEffect(widget)
        efecto.setOffset(0, dy)
        efecto.setBlurRadius(blur)
        tono = QColor(color)
        tono.setAlpha(alpha)
        efecto.setColor(tono)
        widget.setGraphicsEffect(efecto)
    return efecto


def elevar(widget: QWidget, activo: bool, ms: int = NORMAL, color: str = VERDE) -> QVariantAnimation | None:
    """Hover de tarjeta: borde con glow (QSS) + sombra que crece y se tiñe del color primario."""
    efecto = sombra(widget, color, 0, 0, 0)
    if not widgets.ANIMAR:
        efecto.setBlurRadius(26 if activo else 0)
        efecto.setOffset(0, 6 if activo else 0)
        tono = QColor(color)
        tono.setAlpha(110 if activo else 0)
        efecto.setColor(tono)
        return None

    def paso(v: float) -> None:
        efecto.setBlurRadius(26 * v)
        efecto.setOffset(0, 7 * v)
        tono = QColor(color)
        tono.setAlpha(int(120 * v))
        efecto.setColor(tono)

    inicio = efecto.blurRadius() / 26 if efecto.blurRadius() else 0.0
    return animar(widget, inicio, 1.0 if activo else 0.0, ms, paso, curva=CURVA)


def sacudir(contenedor: QWidget, amplitud: int = 7, ms: int = 330) -> None:
    """Sacudida corta de un contenedor con layout (error de validación, confirmación bloqueada)."""
    lay = contenedor.layout()
    if lay is None or not widgets.ANIMAR:
        return
    base = lay.contentsMargins()
    if not hasattr(contenedor, "_sacudida"):
        contenedor._sacudida = None  # type: ignore[attr-defined]
    detener(getattr(contenedor, "_sacudida", None))

    def paso(v: float) -> None:
        lay.setContentsMargins(base.left() + int(v), base.top(), base.right() - int(v), base.bottom())

    # 0 → +a → −a → +a/2 → 0
    pasos = [0.0, 1.0, -1.0, 0.45, 0.0]
    grupo = QVariantAnimation(contenedor)
    grupo.setStartValue(0.0)
    grupo.setEndValue(float(len(pasos) - 1))
    grupo.setDuration(ms)
    grupo.setEasingCurve(QEasingCurve.Type.Linear)

    def cambiar(v: float) -> None:
        i = min(int(v), len(pasos) - 2)
        f = v - i
        paso(pasos[i] + (pasos[i + 1] - pasos[i]) * f)

    grupo.valueChanged.connect(cambiar)
    grupo.finished.connect(lambda: lay.setContentsMargins(base))
    grupo.finished.connect(grupo.deleteLater)
    contenedor._sacudida = grupo  # type: ignore[attr-defined]
    grupo.start()


def destello(widget: QWidget, color: str = VERDE, ms: int = 420) -> None:
    """Flash breve sobre el área copiada / el destino de un drop."""
    objetivo = widget.viewport() if isinstance(widget, QAbstractScrollArea) else widget
    capa = QWidget(objetivo)
    capa.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    capa.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    capa.setStyleSheet(f"background: rgba({_rgb(color)}, 0.28); border-radius: 6px;")
    capa.setGeometry(objetivo.rect())
    capa.show()
    capa.raise_()
    efecto, _ = opacidad(capa)
    efecto.setOpacity(0.9)
    animar(capa, 0.9, 0.0, ms, efecto.setOpacity, capa.deleteLater, QEasingCurve.Type.OutCubic)


def _rgb(color: str) -> str:
    tono = QColor(color)
    return f"{tono.red()}, {tono.green()}, {tono.blue()}"


class ScrollSuave(QObject):
    """Rueda con inercia: cada gesto se convierte en una animación corta de la barra (no un salto por muesca).

    Se instala solo en áreas de datos (QScrollArea, tablas). Las gráficas de pyqtgraph tienen su propio zoom con la
    rueda y no se tocan.
    """

    def __init__(self, area: QAbstractScrollArea) -> None:
        super().__init__(area)
        self._area = area
        self._anims: dict[object, QVariantAnimation] = {}
        area.viewport().installEventFilter(self)
        area.viewport().setCursor(area.viewport().cursor())

    def _barra(self, vertical: bool):
        return self._area.verticalScrollBar() if vertical else self._area.horizontalScrollBar()

    def _mover(self, vertical: bool, delta: int) -> bool:
        barra = self._barra(vertical)
        if barra.maximum() <= barra.minimum():
            return False
        paso = max(1, barra.singleStep()) * 3
        objetivo = barra.value() - delta * paso / 120
        objetivo = max(barra.minimum(), min(barra.maximum(), objetivo))
        if abs(objetivo - barra.value()) < 1:
            return False
        detener(self._anims.get(barra))
        inicio = barra.value()
        self._anims[barra] = animar(self._area, inicio, objetivo, 190, lambda v: barra.setValue(int(round(v))),
                                    None, QEasingCurve.Type.OutCubic)
        return True

    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() == QEvent.Type.Wheel and widgets.ANIMAR:
            dy = evento.angleDelta().y() or evento.pixelDelta().y()
            dx = evento.angleDelta().x() or evento.pixelDelta().x()
            movido = False
            if dy:
                movido = self._mover(True, dy) or movido
            if dx:
                movido = self._mover(False, dx) or movido
            if movido:
                evento.accept()
                return True
        return super().eventFilter(objeto, evento)


def instalar_scroll_suave(area: QAbstractScrollArea) -> ScrollSuave | None:
    """Instala la rueda con inercia una sola vez por área."""
    if not isinstance(area, (QTableView, QTableWidget)) and type(area).__module__.startswith("pyqtgraph"):
        return None
    if getattr(area, "_scroll_suave", None) is not None:
        return area._scroll_suave  # type: ignore[attr-defined]
    suave = ScrollSuave(area)
    area._scroll_suave = suave  # type: ignore[attr-defined]
    return suave


class ProgresoScroll(QWidget):
    """Indicador vertical del borde derecho: cuánto se ha recorrido la lista activa."""

    def __init__(self, padre: QWidget) -> None:
        super().__init__(padre)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedWidth(4)
        self._valor = 0
        self._minimo = 0
        self._maximo = 0
        self._pagina = 0
        self._visible = 0.0
        self._anim: QVariantAnimation | None = None
        self.hide()

    def set_rango(self, valor: int, minimo: int, maximo: int, pagina: int = 0) -> None:
        self._valor, self._minimo, self._maximo, self._pagina = valor, minimo, maximo, pagina
        hay = maximo > minimo
        if hay and self.isHidden():
            self.show()
            self.raise_()
        objetivo = 1.0 if hay else 0.0
        if abs(self._visible - objetivo) > 0.01:
            detener(self._anim)
            self._anim = animar(self, self._visible, objetivo, RAPIDO, self._fundir)
        self.update()

    def _fundir(self, v: float) -> None:
        self._visible = v
        self.setVisible(v > 0.02)
        self.update()

    def paintEvent(self, _evento) -> None:
        if self._visible <= 0.01 or self._maximo <= self._minimo:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        alto = self.height()
        pista = QColor("#2E2E2E")
        pista.setAlpha(int(90 * self._visible))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pista)
        p.drawRoundedRect(QRectF(1, 0, 2, alto), 1, 1)
        avance = (self._valor - self._minimo) / max(1, self._maximo - self._minimo)
        contenido = self._maximo - self._minimo + max(1, self._pagina)
        pulgar = max(26.0, alto * max(1, self._pagina) / max(1, contenido)) if self._pagina else max(26.0, alto * 0.22)
        y = (alto - pulgar) * avance
        tono = QColor(VERDE)
        tono.setAlpha(int(230 * self._visible))
        p.setBrush(tono)
        p.drawRoundedRect(QRectF(1, y, 2, pulgar), 1, 1)


def conectar_progreso(vista: QWidget, indicador: ProgresoScroll) -> None:
    """Conecta la primera área desplazable visible de una vista al indicador de progreso."""
    areas = vista.findChildren(QAbstractScrollArea)
    for area in areas:
        if area.verticalScrollBar().maximum() <= 0:
            continue
        barra = area.verticalScrollBar()
        barra.valueChanged.connect(lambda v, b=barra: indicador.set_rango(v, b.minimum(), b.maximum(), b.pageStep()))
        barra.rangeChanged.connect(lambda _mn, _mx, b=barra: indicador.set_rango(b.value(), b.minimum(), b.maximum(), b.pageStep()))
        indicador.set_rango(barra.value(), barra.minimum(), barra.maximum(), barra.pageStep())
        return


class MenuContexto:
    """Menú contextual con la misma piel del resto de la app (hover, atajo visible, separadores)."""

    @staticmethod
    def abrir(padre: QWidget, punto: QPointF, acciones: list[tuple[str, Callable[[], None] | None, str]]) -> None:
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(padre)
        menu.setObjectName("menuContexto")
        for texto, fn, atajo in acciones:
            if texto == "-":
                menu.addSeparator()
                continue
            accion = QAction(texto, menu)
            if atajo:
                accion.setShortcut(atajo)
            if fn is not None:
                accion.triggered.connect(lambda _=False, f=fn: QTimer.singleShot(0, f))
            else:
                accion.setEnabled(False)
            menu.addAction(accion)
        punto = punto.toPoint() if hasattr(punto, "toPoint") else punto
        menu.exec(padre.mapToGlobal(punto))
