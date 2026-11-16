"""Pantalla «Dashboard»: el avance del conteo continuo, el estado del batch y una gráfica de referencia.

No hay cierres: el conteo siempre está abierto y este panel se recalcula con cada sincronización.
"""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QSizePolicy, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from .. import auth, db
from ..i18n import registrar, t
from ..models import fmt_num, fmt_pct
from ..tema import colores
from . import widgets
from .base import QueryRunner, StateBanner
from .graficas_interactivas import HoverBarras
from .widgets import VERDE, TarjetaKpi

registrar({
    "Conteo continuo": "Continuous count",
    "Avance del inventario físico, sin cierres ni tareas. Se actualiza con cada sincronización.":
        "Progress of the physical inventory, with no closures or tasks. It updates with every sync.",
    "Avance": "Progress",
    "Contados": "Counted",
    "Faltantes": "Short",
    "Sobrantes": "Over",
    "Diferencia en unidades por categoría": "Difference in units by category",
    "Estado del batch": "Batch status",
    "Sin datos": "No data",
    "SKU contados": "SKUs counted",
    "de": "of",
    "SKU": "SKU",
    "Valor": "Value",
    "Desglose": "Breakdown",
    "Alcance": "Scope",
    "Haz clic en una barra para filtrar el inventario por esa categoría.":
        "Click a bar to filter the inventory by that category.",
    "Todavía no se ha procesado ninguna sincronización.": "No synchronization has been processed yet.",
    "Último procesamiento": "Last run",
    "lecturas procesadas": "readings processed",
    "con error": "with error",
    "pendientes": "pending",
})

TARJETAS = (
    ("avance", "Avance", VERDE),
    ("contados", "Contados", VERDE),
    ("faltantes", "Faltantes", "#F04438"),
    ("sobrantes", "Sobrantes", "#F79009"),
)


def _cargar():
    """Corre en un hilo de trabajo: resumen, estado del batch y diferencia por categoría."""
    return db.fetch_resumen(), db.fetch_estado_batch(), db.fetch_por_categoria()


def _fmt_entero(valor: float) -> str:
    return fmt_num(round(valor, 0))


class DashboardView(QWidget):
    conteo_cerrado = pyqtSignal(str)   # compatibilidad: ya no existe el cierre de conteo
    filtro = pyqtSignal(str, str)      # clic en una barra: (categoría, etiqueta)
    detalle = pyqtSignal(str)          # clic en una tarjeta: clave del KPI

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._cargado = False
        self._categorias: list[tuple[str, float]] = []
        self._anim = None
        self._hover = None
        self._titulos = {clave: titulo for clave, titulo, _c in TARJETAS}
        self._colores = colores()

        self.titulo = QLabel(t("Conteo continuo"))
        self.titulo.setObjectName("seccion")
        self.subtitulo = QLabel(t("Avance del inventario físico, sin cierres ni tareas. Se actualiza con cada sincronización."))
        self.subtitulo.setObjectName("subtitulo")
        self.subtitulo.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        encabezado = QVBoxLayout()
        encabezado.setSpacing(2)
        encabezado.addWidget(self.titulo)
        encabezado.addWidget(self.subtitulo)

        self.cards: dict[str, TarjetaKpi] = {
            clave: TarjetaKpi(t(titulo), color if color == VERDE else self._colores["error" if clave == "faltantes" else "aviso"])
            for clave, titulo, color in TARJETAS
        }
        for clave, card in self.cards.items():
            card.clicked.connect(lambda c=clave: self.detalle.emit(c))
        rejilla = QGridLayout()
        rejilla.setSpacing(12)
        for columna, card in enumerate(self.cards.values()):
            rejilla.addWidget(card, 0, columna)
            rejilla.setColumnStretch(columna, 1)

        self.plot = pg.PlotWidget()
        self.plot.setBackground(self._colores["tarjeta"])
        for eje in ("left", "bottom"):
            self.plot.getAxis(eje).setPen(pg.mkPen(self._colores["texto_suave"]))
            self.plot.getAxis(eje).setTextPen(pg.mkPen(self._colores["texto_tenue"]))
        self.plot.setMinimumHeight(220)
        self.plot.setMaximumHeight(560)
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(False, False)
        self.plot.hideButtons()
        self.plot.showGrid(y=True, alpha=0.15)

        self.lbl_batch = QLabel("")
        self.lbl_batch.setObjectName("subtitulo")
        self.lbl_batch.setWordWrap(True)

        self._contenido = QWidget()
        raiz = QVBoxLayout(self._contenido)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(10)
        raiz.addLayout(encabezado)
        raiz.addWidget(self.banner)
        raiz.addLayout(rejilla)
        raiz.addWidget(self._tarjeta(t("Diferencia en unidades por categoría"), self.plot), 1)
        pista = QLabel(t("Haz clic en una barra para filtrar el inventario por esa categoría."))
        pista.setObjectName("ayuda")
        raiz.addWidget(pista)
        raiz.addWidget(self._tarjeta(t("Estado del batch"), self.lbl_batch))

        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(self._contenido)
        exterior = QVBoxLayout(self)
        exterior.setContentsMargins(0, 0, 0, 0)
        exterior.addWidget(desplazable)

    @staticmethod
    def _tarjeta(titulo: str, *contenido: QWidget) -> QFrame:
        tarjeta = QFrame()
        tarjeta.setObjectName("card")
        lay = QVBoxLayout(tarjeta)
        lay.setContentsMargins(14, 10, 14, 10)
        rotulo = QLabel(titulo)
        rotulo.setObjectName("seccion")
        rotulo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        lay.addWidget(rotulo)
        for pieza in contenido:
            lay.addWidget(pieza, 1)
        return tarjeta

    # ------------------------------------------------------------------ API
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._cargado = False
            self.banner.show_empty(t("Sin datos"))
        else:
            self.refresh()

    def refresh(self) -> None:
        if self._sesion is None:
            return
        if not self._cargado:
            self.banner.show_loading()
        self._runner.run(_cargar, self._mostrar, self.banner.show_error, key="dashboard")

    def card_text(self, clave: str) -> str:
        """El valor de una tarjeta (el final, aunque la cifra aún esté contando)."""
        return self.cards[clave].texto()

    def categorias(self) -> list[tuple[str, float]]:
        """Lo que muestra la gráfica: ``[(categoría, diferencia en unidades), …]``."""
        return list(self._categorias)

    def detalle_de(self, clave: str) -> list[tuple[str, str]]:
        """Pares etiqueta/valor que resumen un KPI para el panel lateral."""
        card = self.cards.get(clave)
        if card is None:
            return []
        filas = [(t("Valor"), card.texto())]
        if card.detalle():
            filas.append((t("Desglose"), card.detalle()))
        if self.subtitulo.text():
            filas.append((t("Alcance"), self.subtitulo.text()))
        return filas

    # ------------------------------------------------------------- internos
    def _mostrar(self, datos) -> None:
        resumen, batch, por_categoria = datos
        if resumen is None:
            self.banner.show_empty(t("Sin datos"))
            return
        self.banner.clear()
        self._cargado = True
        self.cards["avance"].set_valor(resumen.avance_pct, fmt_pct)
        self.cards["avance"].set_detalle(f"{resumen.contados} {t('de')} {resumen.skus_totales} {t('SKU')}")
        self.cards["contados"].set_valor(resumen.contados, _fmt_entero)
        self.cards["contados"].set_detalle(f"{t('SKU contados')}: {resumen.contados}")
        self.cards["faltantes"].set_valor(resumen.faltantes, _fmt_entero)
        self.cards["sobrantes"].set_valor(resumen.sobrantes, _fmt_entero)
        self.subtitulo.setText(f"{resumen.skus_totales} {t('SKU')} · {resumen.contados} {t('Contados').lower()}")

        if batch.ultimo_run is None:
            self.lbl_batch.setText(t("Todavía no se ha procesado ninguna sincronización."))
        else:
            texto = (f"{t('Último procesamiento')}: {batch.ultimo_run:%Y-%m-%d %H:%M} UTC · "
                     f"{batch.procesados} {t('lecturas procesadas')}")
            if batch.errores:
                texto += f" · {batch.errores} {t('con error')}"
            if batch.pendientes:
                texto += f" · {batch.pendientes} {t('pendientes')}"
            self.lbl_batch.setText(texto)

        nuevas = [(c, float(v)) for c, v in por_categoria]
        if nuevas != self._categorias:
            self._dibujar(nuevas)

    def _dibujar(self, datos: list[tuple[str, float]]) -> None:
        """Barras por categoría: rojo si falta, ámbar si sobra; crecen desde cero al cambiar."""
        self._categorias = list(datos)
        self.plot.clear()
        eje = self.plot.getAxis("bottom")
        if not datos:
            eje.setTicks([[]])
            return
        xs, valores = list(range(len(datos))), [v for _, v in datos]
        c = self._colores
        colores_barras = [c["error"] if v < 0 else c["aviso"] if v > 0 else c["texto_suave"] for v in valores]
        barras = pg.BarGraphItem(x=xs, height=[0.0] * len(xs), width=0.55, pen=pg.mkPen(None),
                                 brushes=[pg.mkBrush(color) for color in colores_barras])
        self.plot.addItem(barras)
        if self._hover is None:
            self._hover = HoverBarras(self.plot, fmt_num, self._barra_clic)
        self._hover.set_datos([etiqueta for etiqueta, _ in datos], valores, colores_barras, barras)
        for x, valor in zip(xs, valores):
            texto = pg.TextItem(fmt_num(valor), color=c["texto"], anchor=(0.5, 1.0 if valor >= 0 else 0.0))
            texto.setPos(x, valor)
            self.plot.addItem(texto)
        eje.setTicks([[(x, etiqueta) for x, (etiqueta, _) in zip(xs, datos)]])
        self.plot.setXRange(-0.7, len(xs) - 0.3, padding=0)
        minimo, maximo = min(0.0, *valores), max(0.0, *valores)
        margen = 0.22 * max(maximo - minimo, 1.0)
        self.plot.setYRange(minimo - (margen if minimo < 0 else 0.0), maximo + margen, padding=0)
        widgets._detener(self._anim)
        self._anim = widgets.animar(self, 0.0, 1.0, 700, lambda f: barras.setOpts(height=[v * f for v in valores]))

    def _barra_clic(self, etiqueta: str, _valor: float) -> None:
        self.filtro.emit("categoria", etiqueta)
