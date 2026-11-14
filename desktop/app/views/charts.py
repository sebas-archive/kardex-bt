"""Pantalla «Gráficas»: seis gráficas básicas del conteo continuo, con filtros por categoría y por
cantidad de resultados del top. Sin clasificación ni etiquetas de faltante/sobrante en el inventario:
aquí solo se analiza el avance, el ritmo y la calidad de las lecturas.
"""

from __future__ import annotations

import math

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import auth, db
from ..i18n import registrar, t
from ..models import fmt_num, fmt_pct
from ..tema import colores
from . import widgets
from .base import QueryRunner, StateBanner
from .graficas_interactivas import HoverBarras, HoverLinea
from .widgets import Dona

registrar({
    "Avance por categoría": "Progress by category",
    "SKUs contados vs. pendientes": "Counted vs. pending SKUs",
    "Lecturas por hora (UTC)": "Readings per hour (UTC)",
    "Top categorías por lecturas": "Top categories by readings",
    "Unidades dañadas por categoría": "Damaged units by category",
    "Estado del batch": "Batch status",
    "Todas": "All",
    "Mostrar": "Show",
    "{n} categorías": "{n} categories",
    "Guardar PNG": "Save PNG",
    "Guardar las gráficas": "Save the charts",
    "Contados": "Counted",
    "Pendientes": "Pending",
    "Procesadas": "Processed",
    "Con error": "With error",
    "Sin datos": "No data",
    "Haz clic en una categoría para filtrar el inventario.": "Click a category to filter the inventory.",
})

ROJO, AMBAR, GRIS = "#F04438", "#F79009", "#98A2B3"
CHART_IDS = ("avance", "top", "danados", "batch")
EXTRA_IDS = ("dona", "hora")
TITULOS = {
    "avance": "Avance por categoría",
    "dona": "SKUs contados vs. pendientes",
    "hora": "Lecturas por hora (UTC)",
    "top": "Top categorías por lecturas",
    "danados": "Unidades dañadas por categoría",
    "batch": "Estado del batch",
}
FUENTE_CHICA = QFont("DejaVu Sans", 8)
# Clave de la gráfica → clave de la serie que devuelve db.fetch_series.
SERIE_DE = {"avance": "avance_categoria", "top": "top_categorias", "hora": "por_hora", "danados": "danados"}


def _entero(valor: float) -> str:
    return fmt_num(round(valor, 0))


def _etiqueta_corta(texto: str) -> str:
    return texto if len(texto) <= 10 else "…" + texto[-6:]


def _cargar(categoria: str | None, top: int) -> dict:
    """Corre en un hilo de trabajo: las seis series con los filtros de la pantalla."""
    return db.fetch_series(categoria, top)


class EjeFormato(pg.AxisItem):
    """Eje con el formato es-CO del tipo de dato de cada gráfica."""

    def __init__(self, orientation: str, formato) -> None:
        super().__init__(orientation)
        self._formato = formato
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        return [self._formato(float(v)) for v in values]


class ChartsView(QWidget):
    filtro = pyqtSignal(str, str)   # drill-down: (tipo, etiqueta)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._cargado = False
        self._datos: dict[str, list] = {c: [] for c in CHART_IDS}
        self._series: dict[str, list] = {c: [] for c in EXTRA_IDS}
        self._barras: dict[str, pg.BarGraphItem] = {}
        self._anims: dict[str, object] = {}
        self._hovers: dict[str, object] = {}
        self._color = colores()

        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.combo_categoria = QComboBox()
        self.combo_categoria.addItem(t("Todas"))
        self.combo_categoria.setMinimumWidth(170)
        self.combo_top = QComboBox()
        for n in (3, 5, 10, 20):
            self.combo_top.addItem(t("{n} categorías", n=n), n)
        self.combo_top.setCurrentIndex(2)
        self.btn_guardar = QPushButton(t("Guardar PNG"))
        self.btn_guardar.setToolTip(t("Guarda todas las gráficas en un PNG"))
        filtros = QHBoxLayout()
        for texto, campo in ((t("Categoría"), self.combo_categoria), (t("Mostrar"), self.combo_top)):
            etiqueta = QLabel(texto)
            etiqueta.setObjectName("subtitulo")
            filtros.addWidget(etiqueta)
            filtros.addWidget(campo)
        filtros.addStretch(1)
        filtros.addWidget(self.btn_guardar)

        self.plots: dict[str, pg.PlotWidget] = {}
        self.dona = Dona({"contados": self._color["acento"], "pendientes": self._color["texto_suave"]},
                         {"contados": t("Contados"), "pendientes": t("Pendientes")})
        rejilla = QGridLayout()
        rejilla.setSpacing(12)
        orden = (("avance", 0, 0), ("dona", 0, 1), ("hora", 1, 0), ("top", 1, 1),
                 ("danados", 2, 0), ("batch", 2, 1))
        for chart_id, fila, columna in orden:
            marco = QFrame()
            marco.setObjectName("card")
            lay = QVBoxLayout(marco)
            lay.setContentsMargins(10, 10, 10, 10)
            titulo = QLabel(t(TITULOS[chart_id]))
            titulo.setObjectName("seccion")
            if chart_id == "dona":
                titulo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                lay.addWidget(titulo)
                lay.addWidget(self.dona)
            else:
                formato = fmt_pct if chart_id == "avance" else _entero
                plot = pg.PlotWidget(axisItems={"left": EjeFormato("left", formato)})
                plot.setTitle(t(TITULOS[chart_id]), size="11pt", color=self._color["texto"])
                plot.setBackground(self._color["tarjeta"])
                for eje in ("left", "bottom"):
                    plot.getAxis(eje).setPen(pg.mkPen(self._color["texto_suave"]))
                    plot.getAxis(eje).setTextPen(pg.mkPen(self._color["texto_tenue"]))
                plot.setMinimumHeight(250)
                plot.setMenuEnabled(False)
                plot.setMouseEnabled(False, False)
                plot.hideButtons()
                plot.showGrid(y=True, alpha=0.15)
                plot.getAxis("bottom").setTickFont(FUENTE_CHICA)
                lay.addWidget(plot)
                self.plots[chart_id] = plot
            rejilla.addWidget(marco, fila, columna)

        self._contenido = QWidget()
        raiz = QVBoxLayout(self._contenido)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(12)
        raiz.addLayout(filtros)
        raiz.addWidget(self.banner)
        pista = QLabel(t("Haz clic en una categoría para filtrar el inventario."))
        pista.setObjectName("ayuda")
        raiz.addWidget(pista)
        raiz.addLayout(rejilla)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(self._contenido)
        exterior = QVBoxLayout(self)
        exterior.setContentsMargins(0, 0, 0, 0)
        exterior.addWidget(desplazable)

        self.combo_categoria.currentIndexChanged.connect(lambda _: self.refresh())
        self.combo_top.currentIndexChanged.connect(lambda _: self.refresh())
        self.btn_guardar.clicked.connect(self._elegir_archivo)

    # ------------------------------------------------------------------ API
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._cargado = False
        else:
            self.refresh()

    def refresh(self) -> None:
        if self._sesion is None:
            return
        if not self._cargado:
            self.banner.show_loading()
        categoria = self.combo_categoria.currentText()
        self._runner.run(_cargar, self._mostrar, self.banner.show_error,
                         None if categoria == t("Todas") else categoria,
                         int(self.combo_top.currentData() or 10), key="graficas")

    def bar_data(self, chart_id: str) -> list[tuple[str, float]]:
        return list(self._datos[chart_id])

    def serie(self, chart_id: str) -> list:
        return list(self._series[chart_id])

    def alturas_dibujadas(self, chart_id: str) -> list[float]:
        barras = self._barras.get(chart_id)
        return [] if barras is None else [float(h) for h in barras.opts["height"]]

    def guardar_imagen(self, ruta: str) -> bool:
        return self._contenido.grab().save(str(ruta))

    # ------------------------------------------------------------- internos
    def _mostrar(self, datos: dict) -> None:
        self._cargado = True
        actual = self.combo_categoria.currentText()
        self.combo_categoria.blockSignals(True)
        self.combo_categoria.clear()
        self.combo_categoria.addItem(t("Todas"))
        self.combo_categoria.addItems(datos.get("_categorias", []))
        self.combo_categoria.setCurrentIndex(max(self.combo_categoria.findText(actual), 0))
        self.combo_categoria.blockSignals(False)
        self._pintar(datos)
        if any(datos.get(SERIE_DE.get(c, c)) for c in CHART_IDS + EXTRA_IDS):
            self.banner.clear()
        else:
            self.banner.show_empty(t("Sin datos"))

    def _pintar(self, datos: dict) -> None:
        formatos = {"avance": fmt_pct, "top": _entero, "danados": _entero}
        for chart_id in ("avance", "top", "danados"):
            nuevos = list(datos.get(SERIE_DE[chart_id], []))
            if nuevos == self._datos[chart_id] and chart_id in self._barras:
                continue
            self._datos[chart_id] = nuevos
            self._dibujar(chart_id, nuevos, formatos[chart_id])
        for chart_id in EXTRA_IDS:
            nuevos = list(datos.get(SERIE_DE.get(chart_id, chart_id), []))
            if nuevos == self._series[chart_id] and nuevos:
                continue
            self._series[chart_id] = nuevos
        self.dona.set_datos(self._series["dona"])
        self._linea(self._series["hora"])
        self._batch(list(datos.get("batch", [])), list(datos.get("batch_errores", [])))

    def _preparar(self, chart_id: str) -> pg.PlotWidget:
        plot = self.plots[chart_id]
        plot.clear()
        self._barras.pop(chart_id, None)
        return plot

    def _dibujar(self, chart_id: str, datos: list[tuple[str, float]], formato) -> None:
        plot = self._preparar(chart_id)
        eje = plot.getAxis("bottom")
        if not datos:
            eje.setTicks([[]])
            return
        xs, valores = list(range(len(datos))), [v for _, v in datos]
        if chart_id == "avance":
            colores_barras = [self._color["acento"]] * len(datos)
        else:
            colores_barras = [self._color["acento"] if v > 0 else self._color["texto_suave"] for v in valores]
        barras = pg.BarGraphItem(x=xs, height=[0.0] * len(xs), width=0.6, pen=pg.mkPen(None),
                                 brushes=[pg.mkBrush(color) for color in colores_barras])
        plot.addItem(barras)
        self._barras[chart_id] = barras
        hover = self._hovers.get(chart_id)
        if hover is None:
            hover = HoverBarras(plot, formato, self._clic_categoria)
            self._hovers[chart_id] = hover
        hover.set_datos([e for e, _ in datos], valores, colores_barras, barras)
        muchas = len(datos) > 6
        mayor = max(abs(v) for v in valores) or 1.0
        for x, valor in zip(xs, valores):
            if muchas and abs(valor) < 0.06 * mayor:
                continue
            texto = pg.TextItem(formato(valor), color=self._color["texto"], anchor=(0.5, 1.0))
            texto.setPos(x, valor)
            plot.addItem(texto)
        eje.setTicks([[(x, _etiqueta_corta(e) if muchas else e) for x, (e, _) in enumerate(datos)]])
        plot.setXRange(-0.8, len(datos) - 0.2, padding=0)
        maximo = max(valores + [0.0])
        tope = 100.0 if chart_id == "avance" else maximo * 1.25 + 0.5
        plot.setYRange(0, tope, padding=0)
        paso = max(1, math.ceil(tope / 5))
        plot.getAxis("left").setTickSpacing(major=paso, minor=paso)
        widgets._detener(self._anims.get(chart_id))
        self._anims[chart_id] = widgets.animar(self, 0.0, 1.0, 700,
                                               lambda f: barras.setOpts(height=[v * f for v in valores]))

    def _linea(self, datos: list[tuple[str, float]]) -> None:
        plot = self._preparar("hora")
        if not datos:
            plot.getAxis("bottom").setTicks([[]])
            return
        xs, valores = list(range(len(datos))), [v for _, v in datos]
        from PyQt6.QtGui import QColor

        relleno = QColor(self._color["acento"])
        relleno.setAlpha(45)
        curva = pg.PlotDataItem(xs, [0.0] * len(xs), pen=pg.mkPen(self._color["acento"], width=3), fillLevel=0,
                                brush=pg.mkBrush(relleno), symbol="o", symbolSize=8,
                                symbolBrush=pg.mkBrush(self._color["acento"]), symbolPen=pg.mkPen(self._color["tarjeta"]))
        plot.addItem(curva)
        un_dia = len({h[:10] for h, _ in datos}) == 1
        plot.getAxis("bottom").setTicks([[(x, h[-5:] if un_dia else h[5:]) for x, (h, _) in enumerate(datos)]])
        plot.setXRange(-0.5, max(len(xs) - 0.5, 0.5), padding=0)
        maximo = max(valores + [1.0])
        plot.setYRange(0, maximo * 1.2 + 1, padding=0)
        paso = max(1, math.ceil(maximo / 5))
        plot.getAxis("left").setTickSpacing(major=paso, minor=paso)
        hover = self._hovers.get("hora")
        if hover is None:
            hover = HoverLinea(plot, [], [], lambda _e, _v: None)
            self._hovers["hora"] = hover
        hover.set_datos([h for h, _ in datos], valores)
        widgets._detener(self._anims.get("hora"))
        self._anims["hora"] = widgets.animar(self, 0.0, 1.0, 750,
                                             lambda f: curva.setData(xs, [v * f for v in valores]))

    def _batch(self, procesadas: list[tuple[str, float]], errores: list[tuple[str, float]]) -> None:
        plot = self._preparar("batch")
        self._datos["batch"] = list(procesadas)
        self._series["batch_errores"] = list(errores)
        eje = plot.getAxis("bottom")
        if not procesadas:
            eje.setTicks([[]])
            return
        xs = list(range(len(procesadas)))
        valores = [v for _, v in procesadas]
        fallos = [v for _, v in errores]
        barras = pg.BarGraphItem(x=[x - 0.19 for x in xs], height=[0.0] * len(xs), width=0.34,
                                 brush=pg.mkBrush(self._color["acento"]), pen=pg.mkPen(None))
        barras_err = pg.BarGraphItem(x=[x + 0.19 for x in xs], height=[0.0] * len(xs), width=0.34,
                                     brush=pg.mkBrush(self._color["error"]), pen=pg.mkPen(None))
        plot.addItem(barras)
        plot.addItem(barras_err)
        self._barras["batch"] = barras
        eje.setTicks([[(x, _etiqueta_corta(e)) for x, (e, _) in enumerate(procesadas)]])
        plot.setXRange(-0.8, len(xs) - 0.2, padding=0)
        maximo = max(valores + fallos + [1.0])
        plot.setYRange(0, maximo * 1.25 + 0.5, padding=0)
        paso = max(1, math.ceil(maximo / 5))
        plot.getAxis("left").setTickSpacing(major=paso, minor=paso)
        hover = self._hovers.get("batch")
        if hover is None:
            hover = HoverBarras(plot, _entero, lambda _e, _v: None)
            self._hovers["batch"] = hover
        hover.set_datos([e for e, _ in procesadas], valores, [self._color["acento"]] * len(xs), barras)
        widgets._detener(self._anims.get("batch"))

        def paso_anim(f: float) -> None:
            barras.setOpts(height=[v * f for v in valores])
            barras_err.setOpts(height=[v * f for v in fallos])

        self._anims["batch"] = widgets.animar(self, 0.0, 1.0, 700, paso_anim)

    def _clic_categoria(self, etiqueta: str, _valor: float) -> None:
        self.filtro.emit("categoria", etiqueta)

    def _elegir_archivo(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, t("Guardar las gráficas"), "graficas.png", "PNG (*.png)")
        if ruta:
            self.guardar_imagen(ruta)
