"""Ventana principal de la aplicación de escritorio (``python -m app.main``)."""

from __future__ import annotations

import os
import sys
from datetime import datetime

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from btsync.store import Store
from btsync.transports.tcp import TcpTransport

from . import db
from .models import Conteo
from .sync_bridge import SyncBridge
from .views.base import ESTILO, QueryRunner, StateBanner
from .views.charts import ChartsView
from .views.conciliacion import ConciliacionView
from .views.conteo import ConteoView
from .views.monitor import MonitorView
from .views.perfil import PerfilView
from .views.sync import SyncView


class MainWindow(QMainWindow):
    """Selector de conteo, pestañas y auto-refresco.

    Las pestañas se registran con ``add_view``: la ventana funciona con las que existan.
    ``refresh_requested`` pide a todas que vuelvan a consultar (el temporizador, el botón
    «Actualizar» y el fin de una sincronización lo emiten).
    """

    refresh_requested = pyqtSignal()
    cerrando = pyqtSignal()  # la ventana se está cerrando: hay que cortar la sincronización abierta

    def __init__(self, auto_refresh_ms: int = 5000, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Inventario físico — gestion_inventario")
        self.setMinimumSize(720, 520)
        self.resize(1100, 720)
        self.setStyleSheet(ESTILO)
        self._runner = QueryRunner(self)
        self._conteo_actual: str | None = None
        self._conteos_cargados = False
        self._views: list[QWidget] = []

        self.combo_conteo = QComboBox()
        self.combo_conteo.setMinimumWidth(300)
        self.combo_conteo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)  # no cortar nombres largos
        self.lbl_actualizado = QLabel("")
        self.lbl_actualizado.setObjectName("subtitulo")
        self.btn_actualizar = QPushButton("Actualizar")
        self.banner = StateBanner()
        self.banner.retry.connect(self._cargar_conteos)
        self.tabs = QTabWidget()

        barra = QHBoxLayout()
        barra.addWidget(QLabel("Conteo:"))
        barra.addWidget(self.combo_conteo)
        barra.addStretch(1)
        barra.addWidget(self.lbl_actualizado)
        barra.addWidget(self.btn_actualizar)
        central = QWidget()
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(12, 12, 12, 12)
        raiz.addLayout(barra)
        raiz.addWidget(self.banner)
        raiz.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.combo_conteo.currentIndexChanged.connect(self._conteo_cambiado)
        self.btn_actualizar.clicked.connect(lambda: self.refresh_requested.emit())
        self.refresh_requested.connect(self._cargar_conteos)

        self._timer = QTimer(self)
        if auto_refresh_ms > 0:
            self._timer.setInterval(auto_refresh_ms)
            self._timer.timeout.connect(lambda: self.refresh_requested.emit())
            self._timer.start()
        self._cargar_conteos()

    # ------------------------------------------------------------------ API
    def add_view(self, view: QWidget, title: str, index: int | None = None) -> None:
        """Registra una pestaña y la incluye en el refresco. Recibe de inmediato el conteo elegido."""
        if index is None:
            self.tabs.addTab(view, title)
        else:
            self.tabs.insertTab(index, view, title)
        self._views.append(view)
        self.refresh_requested.connect(view.refresh)
        if self._conteos_cargados:
            view.set_conteo(self._conteo_actual)

    def select_conteo(self, id_conteo: str) -> None:
        indice = self.combo_conteo.findData(id_conteo)
        if indice >= 0:
            self.combo_conteo.setCurrentIndex(indice)

    def conteo_actual(self) -> str | None:
        return self._conteo_actual

    # ------------------------------------------------------------- internos
    def _cargar_conteos(self) -> None:
        if not self._conteos_cargados:
            self.banner.show_loading()
        self._runner.run(db.fetch_conteos, self._conteos_listos, self.banner.show_error, key="conteos")

    def _conteos_listos(self, conteos: list[Conteo]) -> None:
        self._conteos_cargados = True
        self.lbl_actualizado.setText(f"Actualizado {datetime.now():%H:%M:%S}")
        previo = self._conteo_actual
        if not conteos:
            self.banner.show_empty("Sin datos")
            self.combo_conteo.blockSignals(True)
            self.combo_conteo.clear()
            self.combo_conteo.blockSignals(False)
            self._aplicar_conteo(None)
            return
        self.banner.clear()
        elegido = previo if any(c.id_conteo == previo for c in conteos) else next(
            (c.id_conteo for c in conteos if c.estado == "ABIERTO"), conteos[0].id_conteo)
        self.combo_conteo.blockSignals(True)
        self.combo_conteo.clear()
        for c in conteos:
            self.combo_conteo.addItem(f"{c.id_conteo} — {c.nombre} ({c.estado})", c.id_conteo)
        self.combo_conteo.setCurrentIndex(self.combo_conteo.findData(elegido))
        self.combo_conteo.blockSignals(False)
        if elegido != previo:
            self._aplicar_conteo(elegido)

    def _conteo_cambiado(self, indice: int) -> None:
        self._aplicar_conteo(self.combo_conteo.itemData(indice))

    def _aplicar_conteo(self, id_conteo: str | None) -> None:
        self._conteo_actual = id_conteo
        for view in self._views:
            view.set_conteo(id_conteo)

    def closeEvent(self, evento) -> None:
        self._timer.stop()
        self.cerrando.emit()
        super().closeEvent(evento)


def build_window(bridge: SyncBridge, auto_refresh_ms: int = 5000) -> MainWindow:
    """La ventana completa: Sincronización, Conteo, Conciliación, Gráficas, Perfil y Monitoreo."""
    ventana = MainWindow(auto_refresh_ms=auto_refresh_ms)
    conteo, monitor = ConteoView(), MonitorView(bridge)
    ventana.add_view(SyncView(bridge), "Sincronización", index=0)
    ventana.add_view(conteo, "Conteo")
    ventana.add_view(ConciliacionView(), "Conciliación")
    ventana.add_view(ChartsView(), "Gráficas")
    ventana.add_view(PerfilView(), "Perfil")
    ventana.add_view(monitor, "Monitoreo")
    bridge.listo.connect(ventana.refresh_requested)                       # llegaron datos nuevos
    conteo.conteo_cerrado.connect(lambda _: ventana.refresh_requested.emit())
    monitor.datos_cambiados.connect(ventana.refresh_requested)
    ventana.cerrando.connect(bridge.cancel)
    return ventana


def crear_transporte():
    """``BT_TRANSPORT=bluez`` (por defecto: Bluetooth real) o ``tcp`` (pruebas y demo de respaldo)."""
    modo = os.environ.get("BT_TRANSPORT", "bluez").lower()
    if modo == "tcp":
        return TcpTransport(os.environ.get("BT_TCP_HOST", "127.0.0.1"), int(os.environ.get("BT_TCP_PORT", "9000")))
    if modo == "bluez":
        from btsync.transports.bluez import BluezTransport

        return BluezTransport(require_pairing=os.environ.get("BT_CON_CLAVE") == "1")
    raise SystemExit(f"BT_TRANSPORT inválido: {modo!r} (usa «bluez» o «tcp»)")


def main() -> int:
    app = QApplication(sys.argv)
    store = Store(os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"])
    puente = SyncBridge(crear_transporte(), store)
    ventana = build_window(puente)
    app.aboutToQuit.connect(puente.cancel)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
