"""Pantalla «Gráficas»: seis gráficas básicas del conteo continuo, con filtros por categoría y por
cantidad de resultados del top. Sin clasificación ni etiquetas de faltante/sobrante en el inventario:
aquí solo se analiza el avance, el ritmo y la calidad de las lecturas.

Movimiento (solo presentación; los datos y las consultas no cambian):

* las gráficas **evolucionan** desde su estado anterior en vez de reiniciarse (``graficas_motion``): cada barra y cada
  punto se empareja por etiqueta y parte de lo que mostraba;
* la rejilla se actualiza **de forma incremental** (añadir, quitar y cambiar de tamaño no reconstruyen las demás);
* entrada coordinada de la pantalla, modo edición con despliegue, menús flotantes y feedback de Guardar PNG.
"""

from __future__ import annotations

import math
from functools import partial

import pyqtgraph as pg
from PyQt6 import sip
from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QSizePolicy,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
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
from . import motion, motion_global, widgets
from .base import QueryRunner, StateBanner
from .graficas_interactivas import HoverBarras, HoverLinea
from .graficas_motion import GraficaBarras, GraficaLinea, etiqueta_corta
from .iconos import icono
from .menu_flotante import Entrada, MenuFlotante, separador, titulo
from .motion import Dur
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
    "Guardando…": "Saving…",
    "Guardado": "Saved",
    "No se pudo guardar": "Could not save",
    "Añadida": "Added",
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
LINEAS = ("hora", "acumulado")                                 # series en el tiempo: línea con área
BARRAS = ("avance", "top", "danados") + BARRAS_NUEVAS          # barras de una serie

# Coreografía de entrada (ms): cada pieza sube unos píxeles y se funde; nada cambia de sitio.
PASO_FILTROS, RETARDO_BALDOSAS, PASO_BALDOSAS, TOPE_BALDOSAS = 34, 150, 55, 5
_etiqueta_corta = etiqueta_corta


def _entero(valor: float) -> str:
    return fmt_num(round(valor, 0))


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
        self._graficas: dict[str, GraficaBarras | GraficaLinea] = {}   # un controlador de movimiento por gráfica
        self._hovers: dict[str, object] = {}
        self._color = colores()
        self._menu_abierto: MenuFlotante | None = None

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
        for campo in (self.combo_categoria, self.combo_top):
            motion_global.instalar_realce(campo)            # feedback inmediato del selector (foco y hover)
        filtros = QHBoxLayout()
        self._piezas_filtro: list[QWidget] = []
        for texto, campo in ((t("Categoría"), self.combo_categoria), (t("Mostrar"), self.combo_top)):
            etiqueta = QLabel(texto)
            etiqueta.setObjectName("subtitulo")
            filtros.addWidget(etiqueta)
            filtros.addWidget(campo)
            self._piezas_filtro += [etiqueta, campo]
        filtros.addStretch(1)
        filtros.addWidget(self.btn_guardar)
        self._piezas_filtro.append(self.btn_guardar)

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
            etiqueta_titulo = QLabel(t(TITULOS[chart_id]))
            etiqueta_titulo.setObjectName("seccion")
            etiqueta_titulo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            lay.setContentsMargins(16, 14, 16, 12)
            lay.addWidget(etiqueta_titulo)
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
                self._crear_grafica(chart_id, plot, formato)
            self._marcos[chart_id] = marco

        self._contenido = QWidget()
        raiz = QVBoxLayout(self._contenido)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(12)
        raiz.addLayout(filtros)
        raiz.addWidget(self.banner)
        self.pista = QLabel(t("Haz clic en una categoría para filtrar el inventario."))
        self.pista.setObjectName("ayuda")
        self.btn_personalizar = QPushButton(" " + t("Personalizar gráficas"))
        self.btn_personalizar.setIcon(icono("sliders", tam=16))
        self.btn_personalizar.setCursor(Qt.CursorShape.PointingHandCursor)
        encabezado = QHBoxLayout()
        encabezado.addWidget(self.pista, 1)
        encabezado.addWidget(self.btn_personalizar)
        raiz.addLayout(encabezado)

        self.barra_edicion = QFrame()
        self.barra_edicion.setObjectName("barraEdicion")
        fila = QHBoxLayout(self.barra_edicion)
        fila.setContentsMargins(14, 8, 8, 8)
        fila.setSpacing(8)
        ayuda_edicion = QLabel(t("Arrastra para reordenar y la esquina ◢ para cambiar el tamaño. Usa ⋯ para quitar la gráfica."))
        ayuda_edicion.setObjectName("ayuda")
        # Confirmación discreta de que lo hecho ya quedó guardado (aparece y se va sola; no es un aviso ni pide nada).
        self.lbl_guardado = widgets.EtiquetaFundible(t("Guardado"))
        self.lbl_guardado.setObjectName("ayuda")
        self.lbl_guardado.setOpacity(0.0)
        self._t_guardado = QTimer(self)
        self._t_guardado.setSingleShot(True)
        self._t_guardado.timeout.connect(self._apagar_guardado)
        self._a_guardado = None
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
        fila.addWidget(self.lbl_guardado)
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
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._contenido)
        exterior = QVBoxLayout(self)
        exterior.setContentsMargins(0, 0, 0, 0)
        exterior.addWidget(self._scroll)

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

    # ------------------------------------------------------- controladores
    def _crear_grafica(self, chart_id: str, plot: pg.PlotWidget, formato) -> None:
        """Un controlador de movimiento por gráfica, creado **una vez**: los ítems de pyqtgraph se conservan y se
        transforman con cada dato nuevo (antes se destruían y se reconstruían desde cero)."""
        c = self._color
        if chart_id in LINEAS:
            self._graficas[chart_id] = GraficaLinea(plot, c["acento"], c["tarjeta"])
            self._hovers[chart_id] = HoverLinea(plot, [], [], lambda _e, _v: None)
        elif chart_id == "batch":
            g = GraficaBarras(plot, formato, c["texto"], colores_serie=(c["acento"], c["error"]), ancho=0.34,
                              desplazamientos=(-0.19, 0.19), cifras=False)
            self._graficas[chart_id] = g
            hover = HoverBarras(plot, _entero, None, clicable=False)
            hover.al_pulsar = g.pulsar
            self._hovers[chart_id] = hover
        else:
            g = GraficaBarras(plot, formato, c["texto"])
            self._graficas[chart_id] = g
            con_clic = chart_id in CON_CLIC
            hover = HoverBarras(plot, formato, self._clic_categoria if con_clic else (lambda _e, _v: None),
                                clicable=con_clic)
            hover.al_pulsar = g.pulsar
            self._hovers[chart_id] = hover

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
        """Entra o sale del modo edición: la barra se despliega, el botón «Personalizar» se funde y las baldosas revelan
        (o retiran) sus asas y menús ⋯ en cascada corta. Las acciones responden desde el primer instante."""
        self._edicion = si
        self.rejilla.set_edicion(si)
        motion_global.desplegar(self.barra_edicion, si)
        self._fundir_personalizar(not si)

    def _fundir_personalizar(self, visible: bool) -> None:
        b = self.btn_personalizar
        if not widgets.ANIMAR or not self.isVisible():
            b.setVisible(visible)
            return
        if visible:
            b.show()
            motion.entrar(b, dy=4, ms_=motion.dur(Dur.ESTADO), radio=8)
        else:
            motion.salir(b, ms_=140, escala=0.98, radio=8,
                         al_terminar=lambda: None if sip.isdeleted(b) or not self._edicion else b.hide())

    def en_edicion(self) -> bool:
        return self._edicion

    def agregar_grafica(self, chart_id: str) -> bool:
        """Añade una gráfica **sin reconstruir la rejilla**: solo la baldosa nueva aparece (fundido) y las demás se
        reacomodan; las que ya estaban conservan su contenido y sus animaciones."""
        if chart_id not in prefs.IDS or any(c == chart_id for c, _t in self._items):
            return False
        self._items.append((chart_id, prefs.TAM_INICIAL))
        b = self._baldosa(chart_id, prefs.TAM_INICIAL)
        self.rejilla.setVisible(True)
        self.rejilla.agregar(b)
        self._marcos[chart_id].show()
        self._revelar_grafica(chart_id, 120)          # su visualización se dibuja cuando la baldosa ya asoma
        self._actualizar_estado()
        self._persistir()
        return True

    def quitar_grafica(self, chart_id: str) -> None:
        """Quita una gráfica: su baldosa se va con una salida suave y el espacio se contrae. El marco (con su gráfica)
        sobrevive para seguir recibiendo datos, como antes."""
        if all(c != chart_id for c, _t in self._items):
            return
        self._items = [(c, tam) for c, tam in self._items if c != chart_id]
        self._medidas.pop(chart_id, None)
        self.rejilla.quitar(chart_id, al_destruir=self._soltar_marco)
        self._actualizar_estado()
        self._persistir()

    def _soltar_marco(self, baldosa: Baldosa) -> None:
        """Antes de destruir una baldosa: su marco (gráfica y datos) pasa al contenedor, oculto."""
        marco = baldosa.contenido
        if marco.parent() is baldosa:                 # si la gráfica ya volvió a otra baldosa, no se toca
            marco.hide()
            marco.setParent(self._contenido)
        if not self._items:
            self.rejilla.hide()

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
        self._poner_baldosas(transicion=True)           # la distribución anterior se funde hacia la predeterminada

    def bar_data(self, chart_id: str) -> list[tuple[str, float]]:
        return list(self._datos[chart_id])

    def serie(self, chart_id: str) -> list:
        return list(self._series[chart_id])

    def alturas_dibujadas(self, chart_id: str) -> list[float]:
        grafica = self._graficas.get(chart_id)
        return grafica.alturas() if isinstance(grafica, GraficaBarras) else []

    def terminar_animaciones(self) -> None:
        """Lleva todo al estado final real: tooltips fuera, gráficas y entradas terminadas. Lo usa Guardar PNG para que
        la imagen exporte siempre el dato definitivo y no un fotograma de una transición."""
        for g in self._graficas.values():
            g.terminar()
        for w in (self.dona, self.anillo, self.dona_buenas):
            w.terminar()
        for h in self._hovers.values():
            h.tooltip.ocultar(inmediato=True)
        for b in self.rejilla.baldosas():
            motion.cancelar_entrada(b)

    def guardar_imagen(self, ruta: str) -> bool:
        """Guarda un PNG con todas las gráficas **en su estado final** (las transiciones en curso se completan antes)."""
        self.terminar_animaciones()
        return self._contenido.grab().save(str(ruta))

    # ------------------------------------------------------------- internos
    def _baldosa(self, chart_id: str, tam: str) -> Baldosa:
        cols, alto = self._medidas.get(chart_id, (0, 0))
        b = Baldosa(chart_id, "grafico", tam, self._marcos[chart_id], cols, alto)
        b.menu_pedido.connect(self._menu)
        b.quitar.connect(self.quitar_grafica)
        return b

    def _soltar_marcos(self) -> None:
        for marco in self._marcos.values():
            marco.hide()
            marco.setParent(self._contenido)

    def _poner_baldosas(self, transicion: bool = False) -> None:
        """Arma la rejilla entera (al cargar la sesión o restaurar). Los marcos (con sus gráficas) sobreviven: se sueltan
        antes de que la rejilla destruya las baldosas, así los datos siguen llegando aunque una gráfica esté quitada.
        Añadir y quitar una gráfica ya **no** pasa por aquí: es incremental (``agregar_grafica``/``quitar_grafica``)."""
        self.rejilla.poner(lambda: [self._baldosa(c, tam) for c, tam in self._items], transicion=transicion,
                           antes=self._soltar_marcos)
        for chart_id, _tam in self._items:
            self._marcos[chart_id].show()
        self._actualizar_estado()

    def _actualizar_estado(self) -> None:
        """Aviso de «sin gráficas», rejilla y botón de añadir según lo que haya puesto."""
        if self._items:
            if self.vacio.isVisible() and widgets.ANIMAR:
                self.vacio.hide()
            self.vacio.setVisible(False)
            self.rejilla.setVisible(True)
        elif not self.vacio.isVisible():
            self.vacio.setVisible(True)
            motion.entrar(self.vacio, dy=6, ms_=motion.dur(Dur.ESTADO), radio=8)
        self.btn_agregar.setEnabled(len(self._items) < len(prefs.IDS))

    def _persistir(self) -> None:
        if self._sesion is not None:
            prefs.guardar(self._sesion.usuario, self._items, self._medidas)
            self._senal_guardado()

    # Confirmación discreta de guardado: «Guardado» aparece junto a los botones de edición y se va sola. Es solo
    # presentación: el guardado ya ocurrió (sin retardos) antes de mostrarla.
    def _senal_guardado(self) -> None:
        if not self._edicion:
            return
        motion.detener(self._a_guardado)
        self._t_guardado.start(1500)
        if widgets.ANIMAR and self.isVisible():
            self._a_guardado = motion.animar(self.lbl_guardado, self.lbl_guardado.opacity(), 1.0, motion.dur(150),
                                             self.lbl_guardado.setOpacity)
        else:
            self.lbl_guardado.setOpacity(1.0)

    def _apagar_guardado(self) -> None:
        motion.detener(self._a_guardado)
        if widgets.ANIMAR and self.isVisible():
            self._a_guardado = motion.animar(self.lbl_guardado, self.lbl_guardado.opacity(), 0.0, motion.dur(320),
                                             self.lbl_guardado.setOpacity)
        else:
            self.lbl_guardado.setOpacity(0.0)

    def _orden_cambiado(self, ids: list[str]) -> None:
        tam = dict(self._items)
        self._items = [(i, tam[i]) for i in ids if i in tam]
        self._persistir()

    # ------------------------------------------------------------------ menús
    def _menu(self, chart_id: str) -> None:
        """Menú ⋯ de la baldosa, pegado a su botón: tamaño y quitar (las mismas acciones de siempre)."""
        tam_actual = dict(self._items).get(chart_id)
        entradas = [titulo(t("Tamaño"))]
        for x in prefs.TAMS:
            entradas.append(Entrada(f"tam:{x}", t(NOMBRE_TAMANO[x]), marcada=tam_actual == x and chart_id not in self._medidas))
        if chart_id in self._medidas:
            entradas.append(Entrada("personalizado", t("Personalizado"), marcada=True, habilitada=False))
        entradas += [separador(), Entrada("quitar", t("Quitar de Gráficas"), peligro=True)]
        baldosa = self.rejilla.baldosa(chart_id)
        ancla = baldosa.btn_menu if baldosa is not None else self
        self._abrir_menu(entradas, ancla.mapToGlobal(QPoint(ancla.width(), ancla.height())), True,
                         partial(self._accion_menu, chart_id))

    def _accion_menu(self, chart_id: str, clave: str) -> None:
        if clave.startswith("tam:"):
            self.cambiar_tam(chart_id, clave[4:])
        elif clave == "quitar":
            self.quitar_grafica(chart_id)

    def _menu_agregar(self) -> None:
        """Catálogo de gráficas: las 13, con las que ya están marcadas y sin poder repetirse."""
        puestas = {c for c, _t in self._items}
        entradas = [Entrada(c, t(TITULOS[c]), marcada=c in puestas, habilitada=c not in puestas,
                            nota=t("Añadida") if c in puestas else "") for c in prefs.IDS]
        ancla = self.btn_agregar
        self._abrir_menu(entradas, ancla.mapToGlobal(QPoint(0, ancla.height())), False, self.agregar_grafica)

    def _abrir_menu(self, entradas: list[Entrada], punto: QPoint, derecha: bool, accion) -> MenuFlotante:
        if self._menu_abierto is not None and not sip.isdeleted(self._menu_abierto):
            self._menu_abierto.close()
        m = MenuFlotante(self, entradas)
        m.elegida.connect(accion)
        self._menu_abierto = m
        m.abrir(punto, derecha)
        return m

    # ------------------------------------------------------------------ datos
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
        for chart_id in BARRAS:
            nuevos = list(datos.get(SERIE_DE[chart_id], []))
            if nuevos == self._datos[chart_id] and self._graficas[chart_id].finales():
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

    def _dibujar(self, chart_id: str, datos: list[tuple[str, float]], formato) -> None:
        """Barras de una serie: las que siguen parten de su altura anterior, las nuevas entran y las que ya no están
        salen. La escala del eje se ajusta con la misma transición."""
        valores = [v for _, v in datos]
        if chart_id == "avance":
            colores_barras = [self._color["acento"]] * len(datos)
        else:
            colores_barras = [self._color["acento"] if v > 0 else self._color["texto_suave"] for v in valores]
        maximo = max(valores + [0.0])
        tope = 110.0 if chart_id == "avance" else maximo * 1.25 + 0.5
        paso = 20 if chart_id == "avance" else max(1, math.ceil(tope / 5))
        grafica = self._graficas[chart_id]
        grafica.poner([(e, (v,)) for e, v in datos], colores_barras, tope, paso)
        self._hovers[chart_id].set_datos([e for e, _ in datos], valores, grafica.poner_alfas)

    def _linea(self, chart_id: str, datos: list[tuple[str, float]]) -> None:
        """Línea y área: la serie anterior se transforma en la nueva; con lecturas nuevas la línea se alarga."""
        valores = [v for _, v in datos]
        maximo = max(valores + [1.0])
        self._graficas[chart_id].poner(datos, maximo * 1.2 + 1, max(1, math.ceil(maximo / 5)))
        self._hovers[chart_id].set_datos([h for h, _ in datos], valores)

    def _batch(self, procesadas: list[tuple[str, float]], errores: list[tuple[str, float]]) -> None:
        """Estado del batch: procesadas (verde) y con error (rojo) evolucionan juntas, cada serie desde su valor anterior."""
        self._datos["batch"] = list(procesadas)
        self._series["batch_errores"] = list(errores)
        valores = [v for _, v in procesadas]
        fallos = [v for _, v in errores]
        maximo = max(valores + fallos + [1.0])
        datos = [(e, (v, fallos[i] if i < len(fallos) else 0.0)) for i, (e, v) in enumerate(procesadas)]
        grafica = self._graficas["batch"]
        grafica.poner(datos, [self._color["acento"]] * len(datos), maximo * 1.25 + 0.5, max(1, math.ceil(maximo / 5)))
        detalle = [f"{t('Procesadas')}: {_entero(v)}<br>{t('Con error')}: {_entero(f)}" for _, (v, f) in datos]
        self._hovers["batch"].set_datos([e for e, _ in procesadas], valores, grafica.poner_alfas, detalle)

    def _clic_categoria(self, etiqueta: str, _valor: float) -> None:
        self.filtro.emit("categoria", etiqueta)

    # ------------------------------------------------------------------ entrada
    def entrada_motion(self) -> None:
        """Coreografía de entrada al abrir la sección (la llama ``motion_global.entrada_pagina``): filtros, estado, pista
        y «Personalizar» suben unos píxeles y se funden en cascada; después las baldosas, y cada visualización se dibuja
        cuando su marco ya asoma (no queda un marco vacío esperando). Nada cambia de sitio."""
        if not widgets.ANIMAR or not self.isVisible():
            return
        for i, pieza in enumerate(self._piezas_filtro):
            motion.entrar(pieza, retardo=i * PASO_FILTROS // 2, dy=6, ms_=motion.dur(280), radio=9)
        base = len(self._piezas_filtro) * PASO_FILTROS // 2
        extras = [self.pista, self.btn_personalizar] if self.btn_personalizar.isVisible() else [self.pista]
        if self.banner.isVisible():
            extras.insert(0, self.banner)
        for i, pieza in enumerate(extras):
            motion.entrar(pieza, retardo=base + i * PASO_FILTROS, dy=5, ms_=motion.dur(260), radio=8)
        QTimer.singleShot(0, self._entrada_baldosas)      # tras el layout: así se sabe cuáles se ven

    def _en_pantalla(self, b: Baldosa) -> bool:
        vista = self._scroll.viewport()
        origen = b.destino.topLeft() if not b.destino.isEmpty() else b.pos()
        y = self.rejilla.mapTo(vista, origen).y()
        return y < vista.height() and y + max(b.height(), 1) > 0

    def _entrada_baldosas(self) -> None:
        if sip.isdeleted(self) or not self.isVisible():
            return
        orden = sorted(self.rejilla.baldosas(), key=lambda b: (b.destino.y(), b.destino.x()))
        k = 0
        for b in orden:
            if not self._en_pantalla(b):
                continue                                   # lo que está fuera de la pantalla no se anima
            retardo = RETARDO_BALDOSAS + min(k, TOPE_BALDOSAS) * PASO_BALDOSAS
            motion.entrar(b, retardo=retardo, dy=10, ms_=Dur.ENTRADA, radio=14)
            self._revelar_grafica(b.id, retardo + 90)      # la gráfica se dibuja cuando su marco ya asoma
            k += 1

    def _revelar_grafica(self, chart_id: str, retardo: int) -> None:
        """Repite la entrada de una visualización (la baldosa acaba de aparecer)."""
        if not widgets.ANIMAR:
            return
        grafica = self._graficas.get(chart_id)
        if grafica is not None:
            grafica.revelar(retardo)
            return
        widget = {"dona": self.dona, "global": self.anillo, "buenas": self.dona_buenas}.get(chart_id)
        if widget is not None:
            QTimer.singleShot(retardo, partial(self._revelar_widget, widget))

    @staticmethod
    def _revelar_widget(widget) -> None:
        if not sip.isdeleted(widget) and widget.isVisible():
            widget.revelar()

    # ------------------------------------------------------------- Guardar PNG
    def _elegir_archivo(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, t("Guardar las gráficas"), "graficas.png", "PNG (*.png)")
        if ruta:
            self.exportar(ruta)

    def exportar(self, ruta: str) -> None:
        """Guardar PNG con feedback: «Guardando…» (el botón se desactiva), luego el resultado y de vuelta al reposo. La
        captura corre en el siguiente ciclo del bucle de eventos, así el estado se ve antes de que ocurra."""
        self._estado_guardar("guardando")
        QTimer.singleShot(0, partial(self._terminar_exportar, ruta))

    def _terminar_exportar(self, ruta: str) -> None:
        if sip.isdeleted(self):
            return
        try:
            ok = self.guardar_imagen(ruta)
        except OSError:
            ok = False
        self._estado_guardar("ok" if ok else "error")
        QTimer.singleShot(1800, self._reposo_guardar)

    def _reposo_guardar(self) -> None:
        if not sip.isdeleted(self):
            self._estado_guardar("reposo")

    def _estado_guardar(self, estado: str) -> None:
        texto = {"reposo": "Guardar PNG", "guardando": "Guardando…", "ok": "Guardado ✓",
                 "error": "No se pudo guardar"}[estado]
        self.btn_guardar.setProperty("estado", estado)
        self.btn_guardar.setEnabled(estado != "guardando")
        self.btn_guardar.setText(t(texto) if estado != "ok" else t("Guardado") + " ✓")
