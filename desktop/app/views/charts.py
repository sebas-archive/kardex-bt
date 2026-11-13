"""Pantalla «Gráficas»: seis gráficas del conteo, con filtro por categoría y por cantidad de SKU.

Tres de barras (``CHART_IDS``: diferencia por categoría, mayores desvíos y lecturas por operador) y tres más
(``EXTRA_IDS``: dona de clasificación, histograma de diferencia en % y lecturas por hora). Las barras crecen al
cambiar los datos; ``bar_data`` y ``serie`` devuelven siempre el dato final, no el cuadro de la animación.
"""

from __future__ import annotations

import math

import pyqtgraph as pg
from PyQt6.QtCore import Qt
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

from .. import db
from ..models import fmt_cop, fmt_num
from . import widgets
from .base import QueryRunner, StateBanner
from .widgets import NOMBRE_CLASIFICACION, VERDE, Dona

pg.setConfigOptions(antialias=True, background="#111111", foreground="#D4D4D4")

CHART_IDS = ("categoria", "desvios", "actividad")
EXTRA_IDS = ("dona", "histograma", "linea")
TITULOS = {
    "categoria": "Diferencia por categoría ($)",
    "desvios": "Mayores desvíos por SKU ($)",
    "actividad": "Lecturas por operador",
    "dona": "Reparto de los SKU",
    "linea": "Lecturas por hora",
    "histograma": "SKU según su diferencia en %",
}
ORDEN_CLASIFICACION = ("OK", "FALTANTE", "SOBRANTE", "SIN_CONTAR")
COLOR_CLASIFICACION = {"OK": "#12b76a", "FALTANTE": "#f04438", "SOBRANTE": "#f79009", "SIN_CONTAR": "#98a2b3"}
ROJO, AMBAR, GRIS = "#f04438", "#f79009", "#98a2b3"
# Tramos del histograma de diferencia %: (etiqueta, color).
TRAMOS = (("< -20 %", ROJO), ("-20 a -5 %", ROJO), ("-5 a 0 %", "#f97066"), ("0 %", "#12b76a"),
          ("0 a 5 %", "#fdb022"), ("5 a 20 %", AMBAR), ("> 20 %", AMBAR))


class EjeFormato(pg.AxisItem):
    """Eje con los números en formato es-CO (pesos con punto de miles, porcentajes, enteros)."""

    def __init__(self, orientation: str, formato) -> None:
        super().__init__(orientation)
        self._formato = formato
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        return [self._formato(v) for v in values]


def _entero(v: float) -> str:
    return fmt_num(round(v, 3))


FORMATO_EJE = {"categoria": fmt_cop, "desvios": fmt_cop, "actividad": _entero, "linea": _entero, "histograma": _entero}
CONTEOS = ("actividad", "linea", "histograma")  # valores enteros: el eje no muestra 0,5

FUENTE_CHICA = QFont("DejaVu Sans", 8)
MUCHAS_BARRAS = 6  # con más barras que esto las etiquetas se abrevian para que no se encimen


def _fmt_corto(valor: float) -> str:
    """Pesos en formato corto para etiquetas apretadas: 1029000 → «$ 1,0 M», -155800 → «-$ 156 mil»."""
    signo, v = ("-" if valor < 0 else ""), abs(valor)
    if v >= 1_000_000:
        return f"{signo}$ {v / 1_000_000:.1f}".replace(".", ",") + " M"
    if v >= 10_000:
        return f"{signo}$ {v / 1_000:.0f} mil"
    return fmt_cop(valor)


def _etiqueta_eje(etiqueta: str) -> str:
    """Un código de barras de 13 dígitos no cabe bajo una barra: se deja el final, «…0037»."""
    return etiqueta if len(etiqueta) <= 8 else "…" + etiqueta[-4:]


def _palabra_corta(etiqueta: str) -> str:
    """Un nombre largo (una categoría) se corta para que no se encime con el vecino: «Cuidado pe…»."""
    return etiqueta if len(etiqueta) <= 10 else etiqueta[:9] + "…"


def _tramo(pct: float) -> int:
    """Índice en ``TRAMOS`` de una diferencia en %."""
    if pct == 0:
        return 3
    if pct < 0:
        return 0 if pct < -20 else 1 if pct < -5 else 2
    return 4 if pct <= 5 else 5 if pct <= 20 else 6


def _cargar(id_conteo: str, categoria: str | None = None, top: int = 10) -> dict:
    """Corre en un hilo de trabajo: los datos de las seis gráficas (``categoria`` y ``top`` son los filtros)."""
    por_categoria = db.fetch_dif_por_categoria(id_conteo)
    desvios = [f for f in db.fetch_top_desvios(id_conteo, 1000) if f.valor_diferencia is not None
               and (categoria is None or f.categoria == categoria)]
    distribucion = db.fetch_distribucion(id_conteo)
    por_operador: dict[str, int] = {}
    por_hora: dict[str, int] = {}
    for operador, hora, registros in db.fetch_actividad(id_conteo):
        por_operador[operador] = por_operador.get(operador, 0) + registros
        por_hora[hora] = por_hora.get(hora, 0) + registros
    tramos = [0] * len(TRAMOS)
    for f in db.fetch_conciliacion(id_conteo, categoria=categoria):
        if f.diferencia_pct is not None:
            tramos[_tramo(f.diferencia_pct)] += 1
    return {
        "categoria": [(c, float(v)) for c, v in por_categoria],
        "desvios": [(f.sku, float(f.valor_diferencia)) for f in desvios[:top]],
        "actividad": [(o, float(n)) for o, n in sorted(por_operador.items(), key=lambda kv: (-kv[1], kv[0]))],
        "dona": [(k, float(distribucion[k])) for k in ORDEN_CLASIFICACION],
        "histograma": [(TRAMOS[i][0], n) for i, n in enumerate(tramos)],
        "linea": [(h, float(n)) for h, n in sorted(por_hora.items())],
        "_categorias": [c for c, _ in por_categoria],
    }


def _sin_datos(datos: dict) -> bool:
    return not any(datos[c] for c in ("categoria", "desvios", "actividad"))


def _vacio() -> dict:
    return {**{c: [] for c in CHART_IDS + EXTRA_IDS}, "_categorias": []}


class ChartsView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._id: str | None = None
        self._cargado = False
        self._datos: dict[str, list] = {c: [] for c in CHART_IDS}
        self._series: dict[str, list] = {c: [] for c in EXTRA_IDS}
        self._barras: dict[str, pg.BarGraphItem] = {}
        self._anims: dict[str, object] = {}

        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.combo_categoria = QComboBox()
        self.combo_categoria.addItem("Todas")
        self.combo_categoria.setMinimumWidth(170)
        self.combo_top = QComboBox()
        for n in (3, 5, 10, 20):
            self.combo_top.addItem(f"{n} SKU con mayor desvío", n)
        self.combo_top.setCurrentIndex(2)
        self.btn_guardar = QPushButton("Guardar imagen…")
        self.btn_guardar.setToolTip("Guarda todas las gráficas en un PNG")
        filtros = QHBoxLayout()
        for texto, campo in (("Categoría", self.combo_categoria), ("Mostrar", self.combo_top)):
            etiqueta = QLabel(texto)
            etiqueta.setObjectName("subtitulo")
            filtros.addWidget(etiqueta)
            filtros.addWidget(campo)
        filtros.addStretch(1)
        filtros.addWidget(self.btn_guardar)

        self.plots: dict[str, pg.PlotWidget] = {}
        self.dona = Dona(COLOR_CLASIFICACION, NOMBRE_CLASIFICACION)
        rejilla = QGridLayout()
        rejilla.setSpacing(12)
        # (id, fila, columna, columnas que ocupa)
        orden = (("dona", 0, 0, 1), ("categoria", 0, 1, 1), ("desvios", 1, 0, 1), ("histograma", 1, 1, 1),
                 ("actividad", 2, 0, 1), ("linea", 2, 1, 1))
        for chart_id, fila, col, ancho in orden:
            marco = QFrame()
            marco.setObjectName("card")
            lay = QVBoxLayout(marco)
            lay.setContentsMargins(10, 10, 10, 10)
            if chart_id == "dona":
                titulo = QLabel(TITULOS[chart_id])
                titulo.setObjectName("seccion")
                titulo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                lay.addWidget(titulo)
                lay.addWidget(self.dona)
            else:
                plot = pg.PlotWidget(axisItems={"left": EjeFormato("left", FORMATO_EJE[chart_id])})
                plot.setTitle(TITULOS[chart_id], size="11pt")
                plot.setMinimumHeight(250)
                plot.setMenuEnabled(False)
                plot.setMouseEnabled(False, False)
                plot.hideButtons()
                plot.showGrid(y=True, alpha=0.15)
                plot.getAxis("bottom").setTickFont(FUENTE_CHICA)
                lay.addWidget(plot)
                self.plots[chart_id] = plot
            rejilla.addWidget(marco, fila, col, 1, ancho)

        self._contenido = QWidget()
        lay = QVBoxLayout(self._contenido)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(12)
        lay.addLayout(filtros)
        lay.addWidget(self.banner)
        lay.addLayout(rejilla)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setWidget(self._contenido)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(desplazable)

        self.combo_categoria.currentIndexChanged.connect(lambda _: self.refresh())
        self.combo_top.currentIndexChanged.connect(lambda _: self.refresh())
        self.btn_guardar.clicked.connect(self._elegir_archivo)

    # ------------------------------------------------------------------ API
    def bar_data(self, chart_id: str) -> list[tuple[str, float]]:
        """Lo que muestra una gráfica de barras: ``[(etiqueta, valor), …]`` en el orden dibujado."""
        return list(self._datos[chart_id])

    def serie(self, chart_id: str) -> list:
        """Los datos de una de las gráficas de ``EXTRA_IDS``."""
        return list(self._series[chart_id])

    def alturas_dibujadas(self, chart_id: str) -> list[float]:
        """La altura con la que está dibujada ahora cada barra (durante la animación aún no es el dato)."""
        barras = self._barras.get(chart_id)
        return [] if barras is None else [float(h) for h in barras.opts["height"]]

    def guardar_imagen(self, ruta: str) -> bool:
        return self._contenido.grab().save(str(ruta))

    def set_conteo(self, id_conteo: str | None) -> None:
        self._id, self._cargado = id_conteo, False
        self.combo_categoria.blockSignals(True)
        self.combo_categoria.clear()
        self.combo_categoria.addItem("Todas")
        self.combo_categoria.blockSignals(False)
        self._pintar(_vacio())
        self.refresh()

    def refresh(self) -> None:
        if self._id is None:
            self.banner.show_empty("Sin datos")
            return
        if not self._cargado:
            self.banner.show_loading()
        categoria = self.combo_categoria.currentText()
        self._runner.run(_cargar, self._mostrar, self.banner.show_error, self._id,
                         None if categoria == "Todas" else categoria, self.combo_top.currentData(), key="graficas")

    # ------------------------------------------------------------- internos
    def _mostrar(self, datos: dict) -> None:
        self._cargado = True
        actual = self.combo_categoria.currentText()
        self.combo_categoria.blockSignals(True)
        self.combo_categoria.clear()
        self.combo_categoria.addItem("Todas")
        self.combo_categoria.addItems(datos["_categorias"])
        self.combo_categoria.setCurrentIndex(max(self.combo_categoria.findText(actual), 0))
        self.combo_categoria.blockSignals(False)
        self._pintar(datos)
        if _sin_datos(datos):
            self.banner.show_empty("Sin datos")
        else:
            self.banner.clear()

    def _pintar(self, datos: dict) -> None:
        formatos = {"categoria": fmt_cop, "desvios": fmt_cop, "actividad": fmt_num}
        for chart_id in CHART_IDS:
            nuevos = list(datos[chart_id])
            if nuevos == self._datos[chart_id] and chart_id in self._barras:
                continue  # sin cambios: no se redibuja (el refresco automático no hace «saltar» las barras)
            self._datos[chart_id] = nuevos
            self._dibujar(chart_id, nuevos, formatos[chart_id])
        dibujos = {"linea": self._linea, "histograma": self._histograma, "dona": self.dona.set_datos}
        for chart_id in EXTRA_IDS:
            nuevos = list(datos.get(chart_id, []))
            if nuevos == self._series[chart_id] and nuevos:
                continue
            self._series[chart_id] = nuevos
            dibujos[chart_id](nuevos)

    def _color(self, chart_id: str, etiqueta: str, valor: float) -> str:
        if chart_id in ("categoria", "desvios"):
            return ROJO if valor < 0 else AMBAR if valor > 0 else GRIS
        return VERDE

    def _crecer(self, chart_id: str, barras: pg.BarGraphItem, valores: list[float], extra=None) -> None:
        """Las barras suben desde cero hasta su valor (``extra(f)`` anima lo que las acompañe)."""
        widgets._detener(self._anims.get(chart_id))

        def paso(f: float) -> None:
            barras.setOpts(height=[v * f for v in valores])
            if extra:
                extra(f)

        self._anims[chart_id] = widgets.animar(self, 0.0, 1.0, 700, paso)

    def _ticks(self, plot: pg.PlotWidget, etiquetas: list[str], abreviar: bool) -> None:
        plot.getAxis("bottom").setTicks([[(x, _etiqueta_eje(e) if abreviar else e) for x, e in enumerate(etiquetas)]])

    def _dibujar(self, chart_id: str, datos: list[tuple[str, float]], formato) -> None:
        plot = self.plots[chart_id]
        plot.clear()
        self._barras.pop(chart_id, None)
        eje = plot.getAxis("bottom")
        if not datos:
            eje.setTicks([[]])
            return
        xs = list(range(len(datos)))
        valores = [v for _, v in datos]
        barras = pg.BarGraphItem(
            x=xs, height=[0.0] * len(datos), width=0.6,
            brushes=[pg.mkBrush(self._color(chart_id, e, v)) for e, v in datos], pen=pg.mkPen(None),
        )
        plot.addItem(barras)
        self._barras[chart_id] = barras
        muchas = len(datos) > MUCHAS_BARRAS
        mayor = max(abs(v) for v in valores) or 1.0
        for x, valor in zip(xs, valores):
            if muchas and abs(valor) < 0.06 * mayor:
                continue  # barra diminuta: la etiqueta se encimaría con las vecinas
            texto = pg.TextItem(
                (_fmt_corto(valor) if muchas and chart_id in ("categoria", "desvios") else formato(valor)),
                color="#EDEDED", anchor=(0.5, 1.0 if valor >= 0 else 0.0))
            if muchas:
                texto.setFont(FUENTE_CHICA)
            texto.setPos(x, valor)
            plot.addItem(texto)
        if chart_id == "categoria" and len(datos) > 4:
            plot.getAxis("bottom").setTicks([[(x, _palabra_corta(e)) for x, (e, _) in enumerate(datos)]])
        else:
            self._ticks(plot, [e for e, _ in datos], muchas)
        plot.setXRange(-0.8, len(datos) - 0.2, padding=0)
        # Margen para las etiquetas de valor: arriba de las barras positivas y debajo de las negativas.
        minimo, maximo = min(0.0, *valores), max(0.0, *valores)
        margen = 0.2 * max(maximo - minimo, 1.0)
        plot.setYRange(minimo - (margen if minimo < 0 else 0.0), maximo + margen, padding=0)
        if chart_id in CONTEOS:
            paso = max(1, math.ceil(maximo / 5))
            plot.getAxis("left").setTickSpacing(major=paso, minor=paso)
        self._crecer(chart_id, barras, valores)

    # ------------------------------------------------------ las gráficas nuevas
    def _preparar(self, chart_id: str, hay_datos: bool) -> pg.PlotWidget | None:
        plot = self.plots[chart_id]
        plot.clear()
        if not hay_datos:
            plot.getAxis("bottom").setTicks([[]])
            return None
        return plot

    def _linea(self, datos: list[tuple[str, float]]) -> None:
        plot = self._preparar("linea", bool(datos))
        if plot is None:
            return
        xs = list(range(len(datos)))
        valores = [v for _, v in datos]
        curva = pg.PlotDataItem(xs, [0.0] * len(xs), pen=pg.mkPen(VERDE, width=3), fillLevel=0,
                                brush=pg.mkBrush(14, 124, 102, 45), symbol="o", symbolSize=9,
                                symbolBrush=pg.mkBrush(VERDE), symbolPen=pg.mkPen("w"))
        plot.addItem(curva)
        un_dia = len({h[:10] for h, _ in datos}) == 1
        plot.getAxis("bottom").setTicks([[(x, h[-5:] if un_dia else h[5:]) for x, (h, _) in enumerate(datos)]])
        plot.setXRange(-0.5, max(len(xs) - 0.5, 0.5), padding=0)
        maximo = max(valores)
        plot.setYRange(0, maximo * 1.2 + 1, padding=0)
        paso = max(1, math.ceil(maximo / 5))
        plot.getAxis("left").setTickSpacing(major=paso, minor=paso)
        widgets._detener(self._anims.get("linea"))
        self._anims["linea"] = widgets.animar(self, 0.0, 1.0, 750, lambda f: curva.setData(xs, [v * f for v in valores]))

    def _histograma(self, datos: list[tuple[str, int]]) -> None:
        plot = self._preparar("histograma", any(n for _, n in datos))
        if plot is None:
            return
        xs = list(range(len(datos)))
        valores = [float(n) for _, n in datos]
        barras = pg.BarGraphItem(x=xs, height=[0.0] * len(xs), width=0.7, pen=pg.mkPen(None),
                                 brushes=[pg.mkBrush(color) for _, color in TRAMOS])
        plot.addItem(barras)
        for x, n in zip(xs, valores):
            if n:
                texto = pg.TextItem(fmt_num(n), color="#EDEDED", anchor=(0.5, 1.0))
                texto.setPos(x, n)
                plot.addItem(texto)
        self._ticks(plot, [e for e, _ in datos], False)
        plot.setXRange(-0.8, len(xs) - 0.2, padding=0)
        maximo = max(valores)
        plot.setYRange(0, maximo * 1.25 + 0.5, padding=0)
        paso = max(1, math.ceil(maximo / 5))
        plot.getAxis("left").setTickSpacing(major=paso, minor=paso)
        self._crecer("histograma", barras, valores)

    def _elegir_archivo(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar las gráficas", "graficas.png", "Imagen PNG (*.png)")
        if ruta:
            self.guardar_imagen(ruta)
