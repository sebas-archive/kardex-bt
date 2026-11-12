"""Vista «Gráficas»: cinco gráficos de barras (pyqtgraph) de la conciliación."""

from __future__ import annotations

import math

import pyqtgraph as pg
from PyQt6.QtWidgets import QFrame, QGridLayout, QScrollArea, QVBoxLayout, QWidget

from .. import db
from ..models import fmt_cop, fmt_num, fmt_pct
from .base import QueryRunner, StateBanner

pg.setConfigOptions(antialias=True, background="w", foreground="#1f2933")

CHART_IDS = ("categoria", "desvios", "distribucion", "zona", "actividad")
TITULOS = {
    "categoria": "Diferencia por categoría ($)",
    "desvios": "Mayores desvíos por SKU ($)",
    "distribucion": "SKU por clasificación",
    "zona": "Avance por zona (% de ubicaciones con lectura)",
    "actividad": "Lecturas por operador",
}
ORDEN_CLASIFICACION = ("OK", "FALTANTE", "SOBRANTE", "SIN_CONTAR")
COLOR_CLASIFICACION = {"OK": "#12b76a", "FALTANTE": "#f04438", "SOBRANTE": "#f79009", "SIN_CONTAR": "#98a2b3"}
ROJO, AMBAR, GRIS = "#f04438", "#f79009", "#98a2b3"


class EjeFormato(pg.AxisItem):
    """Eje con los números en formato es-CO (pesos con punto de miles, porcentajes, enteros)."""

    def __init__(self, orientation: str, formato) -> None:
        super().__init__(orientation)
        self._formato = formato
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        return [self._formato(v) for v in values]


FORMATO_EJE = {
    "categoria": fmt_cop,
    "desvios": fmt_cop,
    "distribucion": lambda v: fmt_num(round(v, 3)),
    "zona": lambda v: f"{v:.0f} %",
    "actividad": lambda v: fmt_num(round(v, 3)),
}
CONTEOS = ("distribucion", "actividad")  # valores enteros: el eje no debe mostrar 0,5 ni 1,5


def _cargar(id_conteo: str) -> dict[str, list[tuple[str, float]]]:
    """Corre en un hilo de trabajo: los datos de las cinco gráficas."""
    categoria = db.fetch_dif_por_categoria(id_conteo)
    desvios = [(f.sku, f.valor_diferencia) for f in db.fetch_top_desvios(id_conteo)
               if f.valor_diferencia is not None]
    distribucion = db.fetch_distribucion(id_conteo)
    zona = [(z, 100.0 * con / total if total else 0.0) for z, con, total in db.fetch_avance_zona(id_conteo)]
    por_operador: dict[str, int] = {}
    for operador, _hora, registros in db.fetch_actividad(id_conteo):
        por_operador[operador] = por_operador.get(operador, 0) + registros
    return {
        "categoria": [(c, float(v)) for c, v in categoria],
        "desvios": [(s, float(v)) for s, v in desvios],
        "distribucion": [(k, float(distribucion[k])) for k in ORDEN_CLASIFICACION],
        "zona": [(z, float(p)) for z, p in zona],
        "actividad": [(o, float(n)) for o, n in sorted(por_operador.items(), key=lambda kv: (-kv[1], kv[0]))],
    }


def _sin_datos(datos: dict) -> bool:
    return not any(datos[c] for c in ("categoria", "desvios", "zona", "actividad"))


class ChartsView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._id: str | None = None
        self._cargado = False
        self._datos: dict[str, list[tuple[str, float]]] = {c: [] for c in CHART_IDS}

        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.plots: dict[str, pg.PlotWidget] = {}
        rejilla = QGridLayout()
        rejilla.setSpacing(12)
        posiciones = {"categoria": (0, 0, 1, 1), "desvios": (0, 1, 1, 1), "distribucion": (1, 0, 1, 1),
                      "zona": (1, 1, 1, 1), "actividad": (2, 0, 1, 2)}
        for chart_id in CHART_IDS:
            plot = pg.PlotWidget(axisItems={"left": EjeFormato("left", FORMATO_EJE[chart_id])})
            plot.setTitle(TITULOS[chart_id], size="11pt")
            plot.setMinimumHeight(230)
            plot.setMenuEnabled(False)
            plot.setMouseEnabled(False, False)
            plot.hideButtons()
            plot.showGrid(y=True, alpha=0.25)
            marco = QFrame()
            marco.setObjectName("card")
            lay = QVBoxLayout(marco)
            lay.setContentsMargins(8, 8, 8, 8)
            lay.addWidget(plot)
            self.plots[chart_id] = plot
            fila, col, alto, ancho = posiciones[chart_id]
            rejilla.addWidget(marco, fila, col, alto, ancho)

        contenido = QWidget()
        lay = QVBoxLayout(contenido)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.addWidget(self.banner)
        lay.addLayout(rejilla)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setWidget(contenido)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(desplazable)

    # ------------------------------------------------------------------ API
    def bar_data(self, chart_id: str) -> list[tuple[str, float]]:
        """Lo que muestra una gráfica: ``[(etiqueta, valor), …]`` en el orden dibujado."""
        return list(self._datos[chart_id])

    def set_conteo(self, id_conteo: str | None) -> None:
        self._id, self._cargado = id_conteo, False
        self._pintar({c: [] for c in CHART_IDS})
        self.refresh()

    def refresh(self) -> None:
        if self._id is None:
            self.banner.show_empty("Sin datos")
            return
        if not self._cargado:
            self.banner.show_loading()
        self._runner.run(_cargar, self._mostrar, self.banner.show_error, self._id, key="graficas")

    # ------------------------------------------------------------- internos
    def _mostrar(self, datos: dict) -> None:
        self._cargado = True
        self._pintar(datos)
        if _sin_datos(datos):
            self.banner.show_empty("Sin datos")
        else:
            self.banner.clear()

    def _pintar(self, datos: dict) -> None:
        formatos = {"categoria": fmt_cop, "desvios": fmt_cop, "distribucion": fmt_num,
                    "zona": fmt_pct, "actividad": fmt_num}
        for chart_id in CHART_IDS:
            self._datos[chart_id] = list(datos[chart_id])
            self._dibujar(chart_id, self._datos[chart_id], formatos[chart_id])

    def _color(self, chart_id: str, etiqueta: str, valor: float) -> str:
        if chart_id in ("categoria", "desvios"):
            return ROJO if valor < 0 else AMBAR if valor > 0 else GRIS
        if chart_id == "distribucion":
            return COLOR_CLASIFICACION[etiqueta]
        return "#2e90fa" if chart_id == "zona" else "#7a5af8"

    def _dibujar(self, chart_id: str, datos: list[tuple[str, float]], formato) -> None:
        plot = self.plots[chart_id]
        plot.clear()
        eje = plot.getAxis("bottom")
        if not datos:
            eje.setTicks([[]])
            return
        xs = list(range(len(datos)))
        plot.addItem(pg.BarGraphItem(
            x=xs, height=[v for _, v in datos], width=0.6,
            brushes=[pg.mkBrush(self._color(chart_id, e, v)) for e, v in datos], pen=pg.mkPen(None),
        ))
        for x, (_, valor) in zip(xs, datos):
            texto = pg.TextItem(formato(valor), color="#1f2933", anchor=(0.5, 1.0 if valor >= 0 else 0.0))
            texto.setPos(x, valor)
            plot.addItem(texto)
        eje.setTicks([[(x, etiqueta) for x, (etiqueta, _) in zip(xs, datos)]])
        plot.setXRange(-0.7, len(datos) - 0.3, padding=0)
        # Margen para las etiquetas de valor: arriba de las barras positivas y debajo de las negativas.
        valores = [v for _, v in datos]
        minimo, maximo = min(0.0, *valores), max(0.0, *valores)
        margen = 0.2 * max(maximo - minimo, 1.0)
        plot.setYRange(minimo - (margen if minimo < 0 else 0.0), maximo + margen, padding=0)
        if chart_id in CONTEOS:
            paso = max(1, math.ceil(maximo / 5))
            plot.getAxis("left").setTickSpacing(major=paso, minor=paso)
