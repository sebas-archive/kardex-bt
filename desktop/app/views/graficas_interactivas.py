"""Hover y drill-down para las gráficas de pyqtgraph, con movimiento.

Las barras se atenúan **progresivamente** salvo la señalada; el tooltip aparece con un fundido y un desplazamiento mínimo,
sigue al cursor con una transición ligera y permanece mientras el cursor esté sobre el elemento. La línea gana una guía
vertical y un punto de lectura que se deslizan de dato en dato (siempre terminan exactamente sobre el dato real).
Todo pasa por ``QVariantAnimation`` reutilizadas (sin crear objetos por cada movimiento del ratón) y respeta
``APP_SIN_ANIMACIONES``: sin animaciones el hover y los tooltips funcionan igual, sin transición.
"""

from __future__ import annotations

from typing import Callable

import pyqtgraph as pg
from PyQt6 import sip
from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPointF, QSize, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtWidgets import QWidget

from . import widgets
from .graficas_motion import ALFA_ATENUADA

MS_HOVER, MS_TOOLTIP, MS_SEGUIR = 150, 120, 90


def posicion_tooltip(cursor: QPoint, tam: QSize, area: QSize) -> QPoint:
    """Dónde poner el tooltip junto al cursor: arriba a la derecha; si no cabe, a la izquierda o debajo; siempre dentro."""
    x = cursor.x() + 16
    y = cursor.y() - tam.height() - 10
    if x + tam.width() > area.width():
        x = cursor.x() - tam.width() - 16
    if y < 0:
        y = cursor.y() + 14
    x = max(4, min(x, max(4, area.width() - tam.width() - 4)))
    y = max(4, min(y, max(4, area.height() - tam.height() - 4)))
    return QPoint(x, y)


def _animacion(dueno: QObject, ms: int, curva: QEasingCurve.Type, paso: Callable) -> QVariantAnimation:
    """Una animación **reutilizable** (se detiene y se vuelve a lanzar): ni se acumulan objetos ni quedan huérfanas."""
    anim = QVariantAnimation(dueno)
    anim.setDuration(ms)
    anim.setEasingCurve(curva)
    anim.valueChanged.connect(paso)
    return anim


def _lanzar(anim: QVariantAnimation, ms: int, inicio, fin) -> None:
    anim.stop()
    anim.setDuration(widgets._ms(ms))
    anim.setStartValue(inicio)
    anim.setEndValue(fin)
    anim.start()


class TooltipGrafica(widgets.EtiquetaFundible):
    """Tooltip de una gráfica: aparece con opacidad y 4 px de desplazamiento, sigue al cursor con una transición ligera,
    cambia de contenido con un parpadeo suave y se retira con un fundido. Sin ``QGraphicsEffect`` (``EtiquetaFundible``)."""

    def __init__(self, padre: QWidget) -> None:
        super().__init__(padre)
        self.setObjectName("tooltipGrafica")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._quiere = False                    # ¿debe estar visible? (la salida es un fundido: el widget sigue un rato)
        self._fade = _animacion(self, MS_TOOLTIP, QEasingCurve.Type.OutCubic, self._paso_fade)
        self._fade.finished.connect(self._fin_fade)
        self._seguir = _animacion(self, MS_SEGUIR, QEasingCurve.Type.OutCubic, self._paso_seguir)
        self._cambio = _animacion(self, MS_TOOLTIP, QEasingCurve.Type.OutCubic, self._paso_cambio)
        self.hide()

    def esta_visible(self) -> bool:
        return self._quiere

    def _paso_fade(self, v) -> None:
        v = float(v)
        self.setOpacity(v)
        self.set_desp((1.0 - v) * widgets._px(4.0))

    def _fin_fade(self) -> None:
        if not self._quiere:
            self.hide()

    def _paso_seguir(self, p) -> None:
        self.move(int(round(p.x())), int(round(p.y())))

    def _paso_cambio(self, v) -> None:
        self.setOpacity(float(v))

    def mostrar(self, texto: str, cursor: QPoint, area: QSize) -> None:
        """Muestra (o actualiza) el tooltip junto al cursor, dentro de ``area``."""
        cambia = texto != self.text()
        if cambia:
            self.setText(texto)
            self.adjustSize()
        destino = posicion_tooltip(cursor, self.size(), area)
        if not self._quiere:
            self._seguir.stop()
            self._cambio.stop()
            self._quiere = True
            self.move(destino)
            self.show()
            self.raise_()
            if widgets.ANIMAR:
                _lanzar(self._fade, MS_TOOLTIP, self.opacity() if self.isVisible() else 0.0, 1.0)
            else:
                self._fade.stop()
                self.setOpacity(1.0)
                self.set_desp(0.0)
            return
        if not widgets.ANIMAR:
            self.move(destino)
            return
        if self._fade.state() == QVariantAnimation.State.Running and self._fade.endValue() == 0.0:
            _lanzar(self._fade, MS_TOOLTIP, self.opacity(), 1.0)     # volvió antes de que terminara de irse
        if cambia and self._fade.state() != QVariantAnimation.State.Running:
            _lanzar(self._cambio, MS_TOOLTIP, 0.55, 1.0)             # el contenido nuevo «respira» en vez de saltar
        if self.pos() != destino:
            _lanzar(self._seguir, MS_SEGUIR, QPointF(self.pos()), QPointF(destino))

    def ocultar(self, inmediato: bool = False) -> None:
        if not self._quiere and not self.isVisible():
            return
        self._quiere = False
        self._seguir.stop()
        self._cambio.stop()
        if inmediato or not widgets.ANIMAR or not self.isVisible():
            self._fade.stop()
            self.hide()
            return
        _lanzar(self._fade, MS_TOOLTIP, self.opacity(), 0.0)


class HoverBarras(QObject):
    """Tooltip + resaltado progresivo + clic sobre una gráfica de barras.

    No dibuja las barras: calcula el realce de cada una (1 = señalada, el resto atenuado) y se lo entrega a quien las
    dibuja (``aplicar``), que lo compone con su transición de datos."""

    def __init__(self, plot: pg.PlotWidget, formato: Callable[[float], str],
                 al_clic: Callable[[str, float], None] | None = None, clicable: bool = True) -> None:
        super().__init__(plot)
        self._plot = plot
        self._formato = formato
        self._al_clic = al_clic
        self._clicable = clicable
        self.al_pulsar: Callable[[int], None] | None = None      # feedback de selección (lo pone quien dibuja)
        self._etiquetas: list[str] = []
        self._valores: list[float] = []
        self._detalle: list[str] | None = None
        self._aplicar: Callable[[list[float]], None] | None = None
        self._indice = -1
        self._alfas: list[float] = []
        self._desde: list[float] = []
        self._hasta: list[float] = []
        self.tooltip = TooltipGrafica(plot.viewport())
        self._anim = _animacion(self, MS_HOVER, QEasingCurve.Type.OutCubic, self._paso)
        self._ultimo_cursor = QPoint()
        self._proxy = pg.SignalProxy(plot.scene().sigMouseMoved, rateLimit=30, slot=self._mover)
        plot.scene().sigMouseClicked.connect(self._clic)
        plot.viewport().installEventFilter(self)

    # ------------------------------------------------------------------ datos
    def set_datos(self, etiquetas: list[str], valores: list[float],
                  aplicar: Callable[[list[float]], None] | None = None, detalle: list[str] | None = None) -> None:
        """Datos nuevos. Si el cursor sigue sobre la misma categoría, el realce y el tooltip se conservan (con su valor nuevo).

        ``detalle`` (opcional): el texto del valor de cada barra cuando no basta una cifra (el batch muestra sus dos series)."""
        actual = self._etiquetas[self._indice] if 0 <= self._indice < len(self._etiquetas) else None
        self._etiquetas, self._valores = list(etiquetas), list(valores)
        self._detalle = list(detalle) if detalle is not None else None
        if aplicar is not None:
            self._aplicar = aplicar
        self._anim.stop()
        nuevo = self._etiquetas.index(actual) if actual in self._etiquetas else -1
        self._indice = nuevo
        self._alfas = self._destino(nuevo)
        self._emitir()
        if nuevo >= 0 and self.tooltip.esta_visible():
            self.tooltip.mostrar(self._texto(nuevo), self._ultimo_cursor, self._plot.viewport().size())
        else:
            self.tooltip.ocultar(inmediato=True)

    def indice(self) -> int:
        return self._indice

    def alfas(self) -> list[float]:
        return list(self._alfas)

    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() == QEvent.Type.Leave:
            self._limpiar()
        return False

    # ------------------------------------------------------------------ realce
    def _destino(self, i: int) -> list[float]:
        n = len(self._etiquetas)
        return [1.0] * n if i < 0 else [1.0 if j == i else ALFA_ATENUADA for j in range(n)]

    def _emitir(self) -> None:
        if self._aplicar is not None:
            self._aplicar(list(self._alfas))

    def _paso(self, v) -> None:
        if sip.isdeleted(self):
            return
        f = float(v)
        self._alfas = [a + (b - a) * f for a, b in zip(self._desde, self._hasta)]
        self._emitir()

    def _apuntar(self, i: int) -> None:
        """Lleva el realce hacia la barra ``i`` (o a ninguna): transición de opacidad, sin saltos."""
        self._indice = i
        self._hasta = self._destino(i)
        if not widgets.ANIMAR:
            self._alfas = list(self._hasta)
            self._emitir()
            return
        self._desde = list(self._alfas) if len(self._alfas) == len(self._hasta) else [1.0] * len(self._hasta)
        _lanzar(self._anim, MS_HOVER, 0.0, 1.0)

    # ---------------------------------------------------------------- ratón
    def _indice_en(self, escena: QPointF) -> int:
        if not self._etiquetas:
            return -1
        punto = self._plot.plotItem.vb.mapSceneToView(escena)
        i = int(round(punto.x()))
        if 0 <= i < len(self._etiquetas) and abs(punto.x() - i) <= 0.55:
            return i
        return -1

    def _texto(self, i: int) -> str:
        valor = self._detalle[i] if self._detalle is not None else self._formato(self._valores[i])
        return f"<b>{self._etiquetas[i]}</b><br>{valor}"

    def _mover(self, evento) -> None:
        escena = evento[0]
        dentro = self._plot.mapFromScene(escena)
        if not self._plot.viewport().rect().contains(dentro):
            self._limpiar()
            return
        i = self._indice_en(escena)
        if i < 0:
            self._limpiar()
            return
        if i != self._indice:
            self._apuntar(i)
        self._ultimo_cursor = dentro
        self.tooltip.mostrar(self._texto(i), dentro, self._plot.viewport().size())

    def _limpiar(self) -> None:
        if self._indice >= 0:
            self._apuntar(-1)
        self.tooltip.ocultar()

    def _clic(self, evento) -> None:
        if evento.button() != Qt.MouseButton.LeftButton or self._al_clic is None:
            return
        i = self._indice_en(evento.scenePos())
        if i >= 0:
            if self._clicable and self.al_pulsar is not None:
                self.al_pulsar(i)
            self._al_clic(self._etiquetas[i], self._valores[i])


class HoverLinea(QObject):
    """Guía vertical, punto de lectura y clic sobre una serie temporal. La guía aparece con un fundido y, junto con el
    punto, se desliza de dato en dato; al terminar queda exactamente sobre el dato real."""

    rango = pyqtSignal(float, float)

    def __init__(self, plot: pg.PlotWidget, etiquetas: list[str], valores: list[float],
                 al_clic: Callable[[str, float], None] | None = None, unidad: str = "lecturas") -> None:
        super().__init__(plot)
        self._plot = plot
        self._etiquetas, self._valores = list(etiquetas), list(valores)
        self._al_clic = al_clic
        self._unidad = unidad
        self._guia = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#10B981", width=1, style=Qt.PenStyle.DashLine))
        self._punto = pg.ScatterPlotItem(size=11, brush=pg.mkBrush("#10B981"), pen=pg.mkPen("#0A0A0A", width=2))
        self._guia.hide()
        self._punto.hide()
        plot.addItem(self._guia, ignoreBounds=True)
        plot.addItem(self._punto, ignoreBounds=True)
        self.tooltip = TooltipGrafica(plot.viewport())
        self._activo = False                      # ¿hay una lectura señalada?
        self._indice = -1
        self._pos = QPointF()                     # dónde está dibujado el punto (x, y de datos); en reposo = el dato
        self._alfa = 0.0
        self._ultimo_cursor = QPoint()
        self._mov = _animacion(self, MS_SEGUIR + 20, QEasingCurve.Type.OutCubic, self._paso_mov)
        self._fundido = _animacion(self, MS_TOOLTIP, QEasingCurve.Type.OutCubic, self._paso_fundido)
        self._fundido.finished.connect(self._fin_fundido)
        self._proxy = pg.SignalProxy(plot.scene().sigMouseMoved, rateLimit=30, slot=self._mover)
        plot.scene().sigMouseClicked.connect(self._clic)
        plot.viewport().installEventFilter(self)

    # ------------------------------------------------------------------ datos
    def set_datos(self, etiquetas: list[str], valores: list[float]) -> None:
        actual = self._etiquetas[self._indice] if self._activo and 0 <= self._indice < len(self._etiquetas) else None
        self._etiquetas, self._valores = list(etiquetas), list(valores)
        if self._guia.scene() is None:
            self._plot.addItem(self._guia, ignoreBounds=True)
        if self._punto.scene() is None:
            self._plot.addItem(self._punto, ignoreBounds=True)
        nuevo = self._etiquetas.index(actual) if actual in self._etiquetas else -1
        if nuevo < 0:
            self._detener()
            return
        self._indice = nuevo                      # el cursor sigue sobre la misma lectura: se desliza a su valor nuevo
        self._ir_a(nuevo)
        if self.tooltip.esta_visible():
            self.tooltip.mostrar(self._texto(nuevo), self._ultimo_cursor, self._plot.viewport().size())

    def _detener(self) -> None:
        self._mov.stop()
        self._fundido.stop()
        self._activo, self._indice, self._alfa = False, -1, 0.0
        self._guia.hide()
        self._punto.hide()
        self.tooltip.ocultar(inmediato=True)

    def posicion(self) -> tuple[float, float]:
        return self._pos.x(), self._pos.y()

    def activo(self) -> bool:
        return self._activo

    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() == QEvent.Type.Leave:
            self._limpiar()
        return False

    # ------------------------------------------------------------------ movimiento
    def _poner_en(self, x: float, y: float) -> None:
        self._pos = QPointF(x, y)
        self._guia.setPos(x)
        self._punto.setData([x], [y])

    def _paso_mov(self, p) -> None:
        if not sip.isdeleted(self):
            self._poner_en(p.x(), p.y())

    def _paso_fundido(self, v) -> None:
        self._alfa = float(v)
        self._guia.setOpacity(self._alfa)
        self._punto.setOpacity(self._alfa)

    def _fin_fundido(self) -> None:
        if not self._activo:
            self._guia.hide()
            self._punto.hide()

    def _ir_a(self, i: int) -> None:
        destino = QPointF(float(i), float(self._valores[i]))
        if not self._activo:                       # aparece en su sitio y se funde (no viaja desde ninguna parte)
            self._activo = True
            self._mov.stop()
            self._poner_en(destino.x(), destino.y())
            self._guia.show()
            self._punto.show()
            if widgets.ANIMAR:
                _lanzar(self._fundido, MS_TOOLTIP, self._alfa, 1.0)
            else:
                self._fundido.stop()
                self._paso_fundido(1.0)
            return
        if self._fundido.state() == QVariantAnimation.State.Running and self._fundido.endValue() == 0.0:
            _lanzar(self._fundido, MS_TOOLTIP, self._alfa, 1.0)       # volvió antes de que terminara de irse
        if not widgets.ANIMAR:
            self._poner_en(destino.x(), destino.y())
        elif self._pos != destino:
            _lanzar(self._mov, MS_SEGUIR + 20, QPointF(self._pos), destino)

    # ---------------------------------------------------------------- ratón
    def _indice_en(self, escena: QPointF) -> int:
        if not self._etiquetas:
            return -1
        punto = self._plot.plotItem.vb.mapSceneToView(escena)
        i = int(round(punto.x()))
        return i if 0 <= i < len(self._etiquetas) else -1

    def _texto(self, i: int) -> str:
        return f"<b>{self._etiquetas[i]}</b><br>{self._valores[i]:.0f} {self._unidad}"

    def _mover(self, evento) -> None:
        escena = evento[0]
        dentro = self._plot.mapFromScene(escena)
        if not self._plot.viewport().rect().contains(dentro):
            self._limpiar()
            return
        i = self._indice_en(escena)
        if i < 0:
            self._limpiar()
            return
        self._indice = i
        self._ultimo_cursor = dentro
        self._ir_a(i)
        self.tooltip.mostrar(self._texto(i), dentro, self._plot.viewport().size())

    def _limpiar(self) -> None:
        if self._activo:
            self._activo = False
            self._mov.stop()
            if widgets.ANIMAR and self._guia.isVisible():
                _lanzar(self._fundido, MS_TOOLTIP, self._alfa, 0.0)
            else:
                self._fundido.stop()
                self._alfa = 0.0
                self._guia.hide()
                self._punto.hide()
        self.tooltip.ocultar()

    def _clic(self, evento) -> None:
        if evento.button() != Qt.MouseButton.LeftButton or self._al_clic is None:
            return
        i = self._indice_en(evento.scenePos())
        if i >= 0:
            self._al_clic(self._etiquetas[i], self._valores[i])


class ReglaTiempo:
    """Selección de un rango de tiempo arrastrando sobre la gráfica (highlight + lectura del rango)."""

    def __init__(self, plot: pg.PlotWidget, al_cambiar: Callable[[float, float], None] | None = None) -> None:
        self._plot = plot
        self._al_cambiar = al_cambiar
        self._region = pg.LinearRegionItem(brush=pg.mkBrush(16, 185, 129, 40),
                                           pen=pg.mkPen("#10B981", width=1, style=Qt.PenStyle.DashLine))
        self._region.setZValue(-10)
        self._region.hide()
        plot.addItem(self._region, ignoreBounds=True)
        self._region.sigRegionChanged.connect(self._cambio)
        self._activa = False

    def activar(self, activa: bool) -> None:
        self._activa = activa
        if activa and self._region.scene() is None:
            self._plot.addItem(self._region, ignoreBounds=True)
        self._region.setVisible(activa)

    def _cambio(self) -> None:
        if self._activa and self._al_cambiar is not None:
            a, b = self._region.getRegion()
            self._al_cambiar(float(a), float(b))
