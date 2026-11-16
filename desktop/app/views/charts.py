"""Pantalla «Gráficas»: seis gráficas básicas del conteo continuo, con filtros por categoría y por
cantidad de resultados del top. Sin clasificación ni etiquetas de faltante/sobrante en el inventario:
aquí solo se analiza el avance, el ritmo y la calidad de las lecturas.
"""

from __future__ import annotations

import math

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtWidgets import (QSizePolicy,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import auth, db
from .. import graficas_prefs as prefs
from ..dashboard_prefs import NOMBRE_TAMANO
from ..i18n import registrar, t
from ..models import fmt_num, fmt_pct
from ..tema import colores
from . import widgets
from .base import QueryRunner, StateBanner
from .graficas_interactivas import HoverBarras, HoverLinea
from .iconos import icono
from .rejilla_personal import Baldosa, RejillaPersonal
from .widgets import Anillo, Dona

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
    "Personalizar gráficas": "Customize charts",
    "Añadir gráfica": "Add chart",
    "Restaurar predeterminado": "Restore default",
    "Listo": "Done",
    "Arrastra para reordenar y la esquina ◢ para cambiar el tamaño. Usa ⋯ para quitar la gráfica.":
        "Drag to reorder and the ◢ corner to resize. Use ⋯ to remove a chart.",
    "Quitar de Gráficas": "Remove from Charts",
    "Tamaño": "Size",
    "No hay gráficas. Pulsa «Personalizar gráficas» y luego «Añadir gráfica».":
        "No charts. Press “Customize charts” and then “Add chart”.",
    "Ya están todas las gráficas": "All charts are already shown",
    "Avance global": "Overall progress",
    "Lecturas acumuladas": "Cumulative readings",
    "Lecturas por día": "Readings per day",
    "Lecturas por operador": "Readings per operator",
    "SKUs pendientes por categoría": "Pending SKUs by category",
    "SKUs más leídos": "Most-read SKUs",
    "Unidades buenas vs. dañadas": "Good vs. damaged units",
    "SKUs contados": "Counted SKUs",
    "Buenas": "Good",
    "Dañadas": "Damaged",
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
    "global": "Avance global",
    "acumulado": "Lecturas acumuladas",
    "dia": "Lecturas por día",
    "operadores": "Lecturas por operador",
    "pendientes": "SKUs pendientes por categoría",
    "skus": "SKUs más leídos",
    "buenas": "Unidades buenas vs. dañadas",
}
FUENTE_CHICA = QFont("DejaVu Sans", 8)
# Clave de la gráfica → clave de la serie que devuelve db.fetch_series.
SERIE_DE = {"avance": "avance_categoria", "top": "top_categorias", "hora": "por_hora", "danados": "danados",
            "dia": "por_dia", "operadores": "operadores", "pendientes": "pendientes", "skus": "skus"}
BARRAS_NUEVAS = ("dia", "operadores", "pendientes", "skus")   # barras verticales como «top», pero de otra serie
CON_CLIC = ("avance", "top", "danados", "pendientes")          # las que filtran el inventario por categoría
SIN_PLOT = ("dona", "global", "buenas")                        # se dibujan con un widget propio, no con pyqtgraph


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
        self._datos: dict[str, list] = {c: [] for c in CHART_IDS + BARRAS_NUEVAS}
        self._series: dict[str, list] = {c: [] for c in EXTRA_IDS + ("acumulado", "buenas")}
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
        self.anillo = Anillo(t("SKUs contados"), self._color["acento"])
        self.dona_buenas = Dona({"buenas": self._color["acento"], "danadas": self._color["error"]},
                                {"buenas": t("Buenas"), "danadas": t("Dañadas")}, unidad="uds")
        self._marcos: dict[str, QFrame] = {}
        for chart_id in prefs.IDS:
            marco = QFrame()
            marco.setObjectName("card")
            lay = QVBoxLayout(marco)
            lay.setContentsMargins(10, 10, 10, 10)
            titulo = QLabel(t(TITULOS[chart_id]))
            titulo.setObjectName("seccion")
            titulo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            lay.setContentsMargins(16, 14, 16, 12)
            lay.addWidget(titulo)
            if chart_id in SIN_PLOT:
                lay.addWidget({"dona": self.dona, "global": self.anillo, "buenas": self.dona_buenas}[chart_id])
            else:
                formato = fmt_pct if chart_id == "avance" else _entero
                plot = pg.PlotWidget(axisItems={"left": EjeFormato("left", formato)})
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
            self._marcos[chart_id] = marco

        self._contenido = QWidget()
        raiz = QVBoxLayout(self._contenido)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(12)
        raiz.addLayout(filtros)
        raiz.addWidget(self.banner)
        pista = QLabel(t("Haz clic en una categoría para filtrar el inventario."))
        pista.setObjectName("ayuda")
        self.btn_personalizar = QPushButton(" " + t("Personalizar gráficas"))
        self.btn_personalizar.setIcon(icono("sliders", tam=16))
        self.btn_personalizar.setCursor(Qt.CursorShape.PointingHandCursor)
        encabezado = QHBoxLayout()
        encabezado.addWidget(pista, 1)
        encabezado.addWidget(self.btn_personalizar)
        raiz.addLayout(encabezado)

        self.barra_edicion = QFrame()
        self.barra_edicion.setObjectName("barraEdicion")
        fila = QHBoxLayout(self.barra_edicion)
        fila.setContentsMargins(14, 8, 8, 8)
        fila.setSpacing(8)
        ayuda_edicion = QLabel(t("Arrastra para reordenar y la esquina ◢ para cambiar el tamaño. Usa ⋯ para quitar la gráfica."))
        ayuda_edicion.setObjectName("ayuda")
        self.btn_agregar = QPushButton(" " + t("Añadir gráfica"))
        self.btn_restaurar = QPushButton(" " + t("Restaurar predeterminado"))
        self.btn_listo = QPushButton(" " + t("Listo"))
        self.btn_listo.setObjectName("primario")
        self.btn_agregar.setIcon(icono("plus", tam=16))
        self.btn_restaurar.setIcon(icono("rotate_ccw", tam=16))
        self.btn_listo.setIcon(icono("check", color="#04130E", tam=16))
        for b in (self.btn_agregar, self.btn_restaurar, self.btn_listo):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        fila.addWidget(ayuda_edicion, 1)
        fila.addWidget(self.btn_agregar)
        fila.addWidget(self.btn_restaurar)
        fila.addWidget(self.btn_listo)
        self.barra_edicion.hide()
        raiz.addWidget(self.barra_edicion)

        self.vacio = QLabel(t("No hay gráficas. Pulsa «Personalizar gráficas» y luego «Añadir gráfica»."))
        self.vacio.setObjectName("ayuda")
        self.vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vacio.hide()
        raiz.addWidget(self.vacio)
        self.rejilla = RejillaPersonal()
        self.rejilla.redimensionable = True          # asa en la esquina: ancho por columnas y alto libre
        self.rejilla.orden_cambiado.connect(self._orden_cambiado)
        self.rejilla.medidas_cambiadas.connect(self._medidas_cambiadas)
        raiz.addWidget(self.rejilla)
        raiz.addStretch(1)
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
        self.btn_personalizar.clicked.connect(lambda: self.set_edicion(True))
        self.btn_listo.clicked.connect(lambda: self.set_edicion(False))
        self.btn_agregar.clicked.connect(self._menu_agregar)
        self.btn_restaurar.clicked.connect(self.restaurar)
        self._items: list[tuple[str, str]] = prefs.predeterminado()   # (gráfica, tamaño), en el orden en pantalla
        self._medidas: dict[str, tuple[int, int]] = {}                # medida propia (columnas, alto) si se redimensionó
        self._edicion = False
        self._poner_baldosas()

    # ------------------------------------------------------------------ API
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._cargado = False
        else:
            self._items = prefs.cargar(sesion.usuario)
            self._medidas = prefs.cargar_medidas(sesion.usuario)
            self._poner_baldosas()
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

    # ----------------------------------------------------- personalización
    def items(self) -> list[tuple[str, str]]:
        return list(self._items)

    def set_edicion(self, si: bool) -> None:
        self._edicion = si
        self.rejilla.set_edicion(si)
        self.barra_edicion.setVisible(si)
        self.btn_personalizar.setVisible(not si)

    def en_edicion(self) -> bool:
        return self._edicion

    def agregar_grafica(self, chart_id: str) -> bool:
        if chart_id not in prefs.IDS or any(c == chart_id for c, _t in self._items):
            return False
        self._items.append((chart_id, prefs.TAM_INICIAL))
        self._poner_baldosas()
        self._persistir()
        return True

    def quitar_grafica(self, chart_id: str) -> None:
        if all(c != chart_id for c, _t in self._items):
            return
        self._items = [(c, tam) for c, tam in self._items if c != chart_id]
        self._medidas.pop(chart_id, None)
        self._poner_baldosas()
        self._persistir()

    def cambiar_tam(self, chart_id: str, tam: str) -> None:
        if tam not in prefs.TAMS:
            return
        self._items = [(c, tam if c == chart_id else x) for c, x in self._items]
        self._medidas.pop(chart_id, None)               # un tamaño S/M/L descarta la medida propia
        self.rejilla.cambiar_tam(chart_id, tam, reiniciar=True)
        self._persistir()

    def poner_medidas(self, chart_id: str, cols: int, alto: int) -> None:
        """Medida propia: ``cols`` columnas y ``alto`` px (0 = la del tamaño)."""
        if all(c != chart_id for c, _t in self._items):
            return
        medida = prefs.limitar_medidas(cols, alto)
        if any(medida):
            self._medidas[chart_id] = medida
        else:
            self._medidas.pop(chart_id, None)
        self.rejilla.poner_medidas(chart_id, *medida)
        self._persistir()

    def _medidas_cambiadas(self, chart_id: str, cols: int, alto: int) -> None:
        self._medidas[chart_id] = (cols, alto)
        self._persistir()

    def restaurar(self) -> None:
        if self._sesion is not None:
            self._items = prefs.restaurar(self._sesion.usuario)
        else:
            self._items = prefs.predeterminado()
        self._medidas = {}
        self._poner_baldosas()

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
    def _poner_baldosas(self) -> None:
        """Arma la rejilla con las gráficas elegidas. Los marcos (con sus gráficas) sobreviven: se sueltan antes de
        que la rejilla destruya las baldosas, así los datos siguen llegando aunque una gráfica esté quitada."""
        for marco in self._marcos.values():
            marco.hide()
            marco.setParent(self._contenido)
        baldosas = []
        for chart_id, tam in self._items:
            cols, alto = self._medidas.get(chart_id, (0, 0))
            b = Baldosa(chart_id, "grafico", tam, self._marcos[chart_id], cols, alto)
            b.menu_pedido.connect(self._menu)
            b.quitar.connect(self.quitar_grafica)
            baldosas.append(b)
        self.rejilla.poner(baldosas)
        for chart_id, _tam in self._items:
            self._marcos[chart_id].show()
        self.vacio.setVisible(not self._items)
        self.rejilla.setVisible(bool(self._items))
        faltan = len(self._items) < len(prefs.IDS)
        self.btn_agregar.setEnabled(faltan)

    def _persistir(self) -> None:
        if self._sesion is not None:
            prefs.guardar(self._sesion.usuario, self._items, self._medidas)

    def _orden_cambiado(self, ids: list[str]) -> None:
        tam = dict(self._items)
        self._items = [(i, tam[i]) for i in ids if i in tam]
        self._persistir()

    def _menu(self, chart_id: str) -> None:
        tam_actual = dict(self._items).get(chart_id)
        m = QMenu(self)
        tam = m.addMenu(t("Tamaño"))
        for x in prefs.TAMS:
            a = tam.addAction(t(NOMBRE_TAMANO[x]), lambda v=x: self.cambiar_tam(chart_id, v))
            a.setCheckable(True)
            a.setChecked(tam_actual == x and chart_id not in self._medidas)
        if chart_id in self._medidas:
            a = tam.addAction(t("Personalizado"))
            a.setCheckable(True)
            a.setChecked(True)
            a.setEnabled(False)
        m.addSeparator()
        m.addAction(t("Quitar de Gráficas"), lambda: self.quitar_grafica(chart_id))
        m.exec(QCursor.pos())

    def _menu_agregar(self) -> None:
        puestas = {c for c, _t in self._items}
        m = QMenu(self)
        for chart_id in prefs.IDS:
            if chart_id not in puestas:
                m.addAction(t(TITULOS[chart_id]), lambda c=chart_id: self.agregar_grafica(c))
        if m.isEmpty():
            m.addAction(t("Ya están todas las gráficas")).setEnabled(False)
        m.exec(self.btn_agregar.mapToGlobal(self.btn_agregar.rect().bottomLeft()))

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
        if any(datos.get(SERIE_DE.get(c, c)) for c in CHART_IDS + EXTRA_IDS + BARRAS_NUEVAS):
            self.banner.clear()
        else:
            self.banner.show_empty(t("Sin datos"))

    def _pintar(self, datos: dict) -> None:
        formatos = {"avance": fmt_pct}
        for chart_id in ("avance", "top", "danados") + BARRAS_NUEVAS:
            nuevos = list(datos.get(SERIE_DE[chart_id], []))
            if nuevos == self._datos[chart_id] and chart_id in self._barras:
                continue
            self._datos[chart_id] = nuevos
            self._dibujar(chart_id, nuevos, formatos.get(chart_id, _entero))
        for chart_id in EXTRA_IDS:
            nuevos = list(datos.get(SERIE_DE.get(chart_id, chart_id), []))
            if nuevos == self._series[chart_id] and nuevos:
                continue
            self._series[chart_id] = nuevos
        self.dona.set_datos(self._series["dona"])
        self._linea("hora", self._series["hora"])
        acumulado, total = [], 0.0
        for etiqueta, v in self._series["hora"]:
            total += v
            acumulado.append((etiqueta, total))
        self._series["acumulado"] = acumulado
        self._linea("acumulado", acumulado)
        pares = dict(datos.get("contados_pendientes", []))
        todos = sum(pares.values())
        self.anillo.set_valor(100.0 * pares.get("contados", 0.0) / todos if todos else None)
        self._series["buenas"] = list(datos.get("buenas", []))
        self.dona_buenas.set_datos(self._series["buenas"])
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
            hover = HoverBarras(plot, formato, self._clic_categoria if chart_id in CON_CLIC else (lambda _e, _v: None))
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
        tope = 110.0 if chart_id == "avance" else maximo * 1.25 + 0.5
        plot.setYRange(0, tope, padding=0)
        paso = 20 if chart_id == "avance" else max(1, math.ceil(tope / 5))
        plot.getAxis("left").setTickSpacing(major=paso, minor=paso)
        widgets._detener(self._anims.get(chart_id))
        self._anims[chart_id] = widgets.animar(self, 0.0, 1.0, 700,
                                               lambda f: barras.setOpts(height=[v * f for v in valores]))

    def _linea(self, chart_id: str, datos: list[tuple[str, float]]) -> None:
        plot = self._preparar(chart_id)
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
        hover = self._hovers.get(chart_id)
        if hover is None:
            hover = HoverLinea(plot, [], [], lambda _e, _v: None)
            self._hovers[chart_id] = hover
        hover.set_datos([h for h, _ in datos], valores)
        widgets._detener(self._anims.get(chart_id))
        self._anims[chart_id] = widgets.animar(self, 0.0, 1.0, 750,
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
