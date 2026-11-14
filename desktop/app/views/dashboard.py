"""Pantalla «Dashboard»: cómo va el conteo elegido, en cuatro cifras, una gráfica y el reparto de los SKU."""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from .. import auth, db, tareas
from ..models import fmt_cop, fmt_pct
from . import widgets
from .base import QueryRunner, StateBanner
from .widgets import COLOR_CLASIFICACION, NOMBRE_CLASIFICACION, VERDE, BarraSegmentada, TarjetaKpi

pg.setConfigOptions(antialias=True, background="#111111", foreground="#D4D4D4")

# (clave, título, color de la cifra)
TARJETAS = (
    ("avance", "Avance", VERDE),
    ("exactitud", "Exactitud", VERDE),
    ("valor_faltante", "Valor faltante", COLOR_CLASIFICACION["FALTANTE"]),
    ("valor_sobrante", "Valor sobrante", "#B54708"),
)


def _cargar(id_conteo: str):
    """Corre en un hilo de trabajo: (resumen, estado del conteo, diferencia por categoría, estado del batch)."""
    resumen = db.fetch_resumen(id_conteo)
    estado = next((c.estado for c in db.fetch_conteos() if c.id_conteo == id_conteo), None)
    return resumen, estado, db.fetch_dif_por_categoria(id_conteo), db.fetch_estado_batch()


class EjePesos(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [fmt_cop(v) for v in values]


class DashboardView(QWidget):
    conteo_cerrado = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._id: str | None = None
        self._cargado = False
        self._sesion: auth.Sesion | None = None
        self._estado: str | None = None
        self._categorias: list[tuple[str, float]] = []
        self._anim = None

        self.titulo = QLabel("Conteo")
        self.titulo.setObjectName("seccion")
        self.insignia = QLabel("")
        self.insignia.setObjectName("insignia")
        self.insignia.hide()
        self.subtitulo = QLabel("")
        self.subtitulo.setObjectName("subtitulo")
        self.btn_cerrar = QPushButton("Cerrar conteo")
        self.btn_cerrar.setObjectName("peligro")
        self.btn_cerrar.setToolTip("Solo un administrador puede cerrar un conteo")
        self.btn_cerrar.clicked.connect(self._pedir_cierre)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        encabezado = QHBoxLayout()
        encabezado.addWidget(self.titulo)
        encabezado.addWidget(self.insignia)
        encabezado.addWidget(self.subtitulo)
        encabezado.addStretch(1)
        encabezado.addWidget(self.btn_cerrar)

        self.cards: dict[str, TarjetaKpi] = {clave: TarjetaKpi(titulo, color) for clave, titulo, color in TARJETAS}
        fila_cards = QHBoxLayout()
        fila_cards.setSpacing(12)
        for card in self.cards.values():
            fila_cards.addWidget(card, 1)

        self.plot = pg.PlotWidget(axisItems={"left": EjePesos("left")})
        self.plot.setMinimumHeight(240)
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(False, False)
        self.plot.hideButtons()
        self.plot.showGrid(y=True, alpha=0.15)
        tarjeta_grafica = self._tarjeta("Diferencia por categoría ($)", self.plot)

        self.barra_clasificacion = BarraSegmentada(COLOR_CLASIFICACION, NOMBRE_CLASIFICACION)
        self.lbl_sync = QLabel("")
        self.lbl_sync.setObjectName("subtitulo")
        self.lbl_sync.setWordWrap(True)
        tarjeta_reparto = self._tarjeta("Cómo quedaron los SKU", self.barra_clasificacion, self.lbl_sync)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(14)
        raiz.addLayout(encabezado)
        raiz.addWidget(self.banner)
        raiz.addLayout(fila_cards)
        raiz.addWidget(tarjeta_grafica, 1)
        raiz.addWidget(tarjeta_reparto)
        self._ajustar_cierre()

    @staticmethod
    def _tarjeta(titulo: str, *contenido: QWidget) -> QFrame:
        tarjeta = QFrame()
        tarjeta.setObjectName("card")
        lay = QVBoxLayout(tarjeta)
        lay.setContentsMargins(16, 14, 16, 14)
        rotulo = QLabel(titulo)
        rotulo.setObjectName("seccion")
        lay.addWidget(rotulo)
        for pieza in contenido:
            lay.addWidget(pieza)
        return tarjeta

    # ------------------------------------------------------------------ API
    def card_text(self, clave: str) -> str:
        """El valor de una tarjeta (el final, aunque la cifra aún esté contando)."""
        return self.cards[clave].texto()

    def categorias(self) -> list[tuple[str, float]]:
        """Lo que muestra la gráfica: ``[(categoría, valor de la diferencia), …]``."""
        return list(self._categorias)

    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        self._ajustar_cierre()

    def set_conteo(self, id_conteo: str | None) -> None:
        self._id, self._cargado, self._estado = id_conteo, False, None
        for card in self.cards.values():
            card.set_texto("—")
            card.set_detalle("")
        self.barra_clasificacion.set_segmentos([])
        self._dibujar([])
        self.titulo.setText("Conteo")
        self.subtitulo.setText("")
        self.lbl_sync.setText("")
        self.insignia.hide()
        self._ajustar_cierre()
        self.refresh()

    def refresh(self) -> None:
        if self._id is None:
            self.banner.show_empty("Sin datos")
            return
        if not self._cargado:
            self.banner.show_loading()
        self._runner.run(_cargar, self._mostrar, self.banner.show_error, self._id, key="dashboard")

    # ------------------------------------------------------------- internos
    def _ajustar_cierre(self) -> None:
        """Cerrar un conteo es cosa del administrador, y solo si el conteo está abierto."""
        es_admin = self._sesion is not None and self._sesion.es_admin
        self.btn_cerrar.setVisible(es_admin)
        self.btn_cerrar.setEnabled(es_admin and self._estado == "ABIERTO")
        self.btn_cerrar.setText("Conteo cerrado" if self._estado == "CERRADO" else "Cerrar conteo")

    def _mostrar(self, datos) -> None:
        resumen, estado, por_categoria, batch = datos
        if resumen is None:
            self.banner.show_empty("Sin datos")
            return
        self.banner.clear()
        self._cargado, self._estado = True, estado
        self.cards["avance"].set_valor(resumen.avance_pct, fmt_pct)
        self.cards["exactitud"].set_valor(resumen.exactitud_pct, fmt_pct)
        self.cards["valor_faltante"].set_valor(resumen.valor_faltante, fmt_cop)
        self.cards["valor_sobrante"].set_valor(resumen.valor_sobrante, fmt_cop)
        self.cards["avance"].set_detalle(f"{resumen.contados} de {resumen.skus_totales} SKU contados")
        self.cards["exactitud"].set_detalle(f"{resumen.ok} de {resumen.contados} cuadran")
        self.cards["valor_faltante"].set_detalle(f"{resumen.faltantes} SKU con faltante")
        self.cards["valor_sobrante"].set_detalle(f"{resumen.sobrantes} SKU con sobrante")
        self.barra_clasificacion.set_segmentos([("OK", resumen.ok), ("FALTANTE", resumen.faltantes),
                                                ("SOBRANTE", resumen.sobrantes), ("SIN_CONTAR", resumen.sin_contar)])
        self.titulo.setText(f"Conteo {resumen.id_conteo}")
        self.subtitulo.setText(f"{resumen.skus_totales} SKU, {resumen.contados} contados")
        self.insignia.setText("Abierto" if estado == "ABIERTO" else "Cerrado" if estado == "CERRADO" else (estado or ""))
        self.insignia.setProperty("estado", estado or "")
        self.insignia.style().unpolish(self.insignia)
        self.insignia.style().polish(self.insignia)
        self.insignia.setVisible(bool(estado))
        self.lbl_sync.setText(
            "Todavía no se ha procesado ninguna sincronización." if batch.ultimo_run is None else
            f"Último procesamiento: {batch.ultimo_run:%Y-%m-%d %H:%M} UTC · {batch.procesados} lecturas procesadas"
            + (f" · {batch.errores} con error" if batch.errores else "") + (f" · {batch.pendientes} pendientes" if batch.pendientes else ""))
        nuevas = [(c, float(v)) for c, v in por_categoria]
        if nuevas != self._categorias:
            self._dibujar(nuevas)
        self._ajustar_cierre()

    def _dibujar(self, datos: list[tuple[str, float]]) -> None:
        """Barras por categoría: rojo si falta, ámbar si sobra; crecen desde cero al cambiar."""
        self._categorias = list(datos)
        self.plot.clear()
        eje = self.plot.getAxis("bottom")
        if not datos:
            eje.setTicks([[]])
            return
        xs, valores = list(range(len(datos))), [v for _, v in datos]
        barras = pg.BarGraphItem(
            x=xs, height=[0.0] * len(xs), width=0.55, pen=pg.mkPen(None),
            brushes=[pg.mkBrush(COLOR_CLASIFICACION["FALTANTE"] if v < 0 else COLOR_CLASIFICACION["SOBRANTE"] if v > 0 else "#3A3A3A") for v in valores])
        self.plot.addItem(barras)
        for x, v in zip(xs, valores):
            texto = pg.TextItem(fmt_cop(v), color="#EDEDED", anchor=(0.5, 1.0 if v >= 0 else 0.0))
            texto.setPos(x, v)
            self.plot.addItem(texto)
        eje.setTicks([[(x, c) for x, (c, _) in zip(xs, datos)]])
        self.plot.setXRange(-0.7, len(xs) - 0.3, padding=0)
        minimo, maximo = min(0.0, *valores), max(0.0, *valores)
        margen = 0.22 * max(maximo - minimo, 1.0)
        self.plot.setYRange(minimo - (margen if minimo < 0 else 0.0), maximo + margen, padding=0)
        widgets._detener(self._anim)
        self._anim = widgets.animar(self, 0.0, 1.0, 700, lambda f: barras.setOpts(height=[v * f for v in valores]))

    def _pedir_cierre(self) -> None:
        if self._id is None:
            return
        respuesta = QMessageBox.question(
            self,
            "Cerrar conteo",
            f"Cerrar el conteo {self._id} es irreversible: los SKU que nadie contó pasarán a faltante "
            "y ya no se aceptarán más lecturas.\n\n¿Cerrarlo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        self.btn_cerrar.setEnabled(False)
        self.btn_cerrar.setText("Cerrando…")
        id_conteo = self._id
        self._runner.run(tareas.cerrar_conteo, lambda _: self._cerrado(id_conteo), self._error_cierre,
                         self._sesion, id_conteo)

    def _cerrado(self, id_conteo: str) -> None:
        self.conteo_cerrado.emit(id_conteo)
        self.refresh()

    def _error_cierre(self, mensaje: str) -> None:
        self.banner.show_error(mensaje)
        self.refresh()
