"""Hover y drill-down para las gráficas de pyqtgraph.

Las barras se atenúan al 60 % salvo la señalada, aparece un tooltip junto al cursor y un clic emite la etiqueta para
filtrar el resto de la vista. La línea gana una guía vertical y un punto de lectura.
"""

from __future__ import annotations

from typing import Callable

import pyqtgraph as pg
from PyQt6.QtCore import QEvent, QObject, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QWidget

from . import motion, widgets

def _atenuar(color: str, alpha: int) -> QColor:
    tono = QColor(color)
    tono.setAlpha(alpha)
    return tono


class HoverBarras(QObject):
    """Tooltip + resaltado + clic sobre una gráfica de barras."""

    def __init__(self, plot: pg.PlotWidget, formato: Callable[[float], str],
                 al_clic: Callable[[str, float], None] | None = None) -> None:
        super().__init__(plot)
        self._plot = plot
        self._formato = formato
        self._al_clic = al_clic
        self._etiquetas: list[str] = []
        self._valores: list[float] = []
        self._colores: list[str] = []
        self._barras: pg.BarGraphItem | None = None
        self._indice = -1
        self._label = QLabel(plot.viewport())
        self._label.setObjectName("tooltipGrafica")
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._label.hide()
        self._proxy = pg.SignalProxy(plot.scene().sigMouseMoved, rateLimit=30, slot=self._mover)
        plot.scene().sigMouseClicked.connect(self._clic)
        plot.viewport().installEventFilter(self)

    def set_datos(self, etiquetas: list[str], valores: list[float], colores: list[str],
                  barras: pg.BarGraphItem) -> None:
        self._etiquetas, self._valores, self._colores = list(etiquetas), list(valores), list(colores)
        self._barras = barras
        self._indice = -1
        self._label.hide()

    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() == QEvent.Type.Leave:
            self._limpiar()
        return False

    def _indice_en(self, escena: QPointF) -> int:
        if not self._etiquetas:
            return -1
        punto = self._plot.plotItem.vb.mapSceneToView(escena)
        i = int(round(punto.x()))
        if 0 <= i < len(self._etiquetas) and abs(punto.x() - i) <= 0.55:
            return i
        return -1

    def _mover(self, evento) -> None:
        escena = evento[0]
        if not self._plot.viewport().rect().contains(self._plot.mapFromScene(escena)):
            self._limpiar()
            return
        i = self._indice_en(escena)
        if i < 0:
            self._limpiar()
            return
        if i != self._indice:
            self._resaltar(i)
        self._label.setText(f"<b>{self._etiquetas[i]}</b><br>{self._formato(self._valores[i])}")
        self._label.adjustSize()
        dentro = self._plot.mapFromScene(escena)
        x = dentro.x() + 16
        y = dentro.y() - self._label.height() - 10
        if x + self._label.width() > self._plot.width():
            x = dentro.x() - self._label.width() - 16
        if y < 0:
            y = dentro.y() + 14
        self._label.move(max(4, x), max(4, y))
        self._label.show()
        self._label.raise_()

    def _resaltar(self, i: int) -> None:
        self._indice = i
        if self._barras is None:
            return
        brushes = []
        for j, color in enumerate(self._colores):
            brushes.append(pg.mkBrush(_atenuar(color, 255 if j == i else 88)))
        self._barras.setOpts(brushes=brushes)

    def _limpiar(self) -> None:
        if self._indice >= 0:
            self._indice = -1
            if self._barras is not None:
                self._barras.setOpts(brushes=[pg.mkBrush(c) for c in self._colores])
        self._label.hide()

    def _clic(self, evento) -> None:
        if evento.button() != Qt.MouseButton.LeftButton or self._al_clic is None:
            return
        i = self._indice_en(evento.scenePos())
        if i >= 0:
            self._al_clic(self._etiquetas[i], self._valores[i])


class HoverLinea(QObject):
    """Guía vertical, punto de lectura y click sobre una serie temporal."""

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
        self._label = QLabel(plot.viewport())
        self._label.setObjectName("tooltipGrafica")
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._label.hide()
        self._proxy = pg.SignalProxy(plot.scene().sigMouseMoved, rateLimit=30, slot=self._mover)
        plot.scene().sigMouseClicked.connect(self._clic)

    def set_datos(self, etiquetas: list[str], valores: list[float]) -> None:
        self._etiquetas, self._valores = list(etiquetas), list(valores)
        if self._guia.scene() is None:
            self._plot.addItem(self._guia, ignoreBounds=True)
        if self._punto.scene() is None:
            self._plot.addItem(self._punto, ignoreBounds=True)
        self._guia.hide()
        self._punto.hide()

    def _indice_en(self, escena: QPointF) -> int:
        if not self._etiquetas:
            return -1
        punto = self._plot.plotItem.vb.mapSceneToView(escena)
        i = int(round(punto.x()))
        return i if 0 <= i < len(self._etiquetas) else -1

    def _mover(self, evento) -> None:
        escena = evento[0]
        if not self._plot.viewport().rect().contains(self._plot.mapFromScene(escena)):
            self._limpiar()
            return
        i = self._indice_en(escena)
        if i < 0:
            self._limpiar()
            return
        self._guia.setPos(i)
        self._guia.show()
        self._punto.setData([i], [self._valores[i]])
        self._punto.show()
        self._label.setText(f"<b>{self._etiquetas[i]}</b><br>{self._valores[i]:.0f} {self._unidad}")
        self._label.adjustSize()
        dentro = self._plot.mapFromScene(escena)
        x = dentro.x() + 16
        y = dentro.y() - self._label.height() - 10
        if x + self._label.width() > self._plot.width():
            x = dentro.x() - self._label.width() - 16
        self._label.move(max(4, x), max(4, y))
        self._label.show()
        self._label.raise_()

    def _limpiar(self) -> None:
        self._guia.hide()
        self._punto.hide()
        self._label.hide()

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
