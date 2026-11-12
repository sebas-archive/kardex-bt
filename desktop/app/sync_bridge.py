"""Puente entre el controlador de sincronización (hilos propios) y la interfaz Qt.

``SyncController`` avisa de cada cambio desde sus hilos; el puente lo convierte en la señal
``status_changed``, que Qt entrega en el hilo de la interfaz: ningún hilo del Bluetooth toca widgets.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from btsync.controller import LISTO, SyncController


class SyncBridge(QObject):
    status_changed = pyqtSignal(dict)  # el estado completo (ver SyncController.status)
    listo = pyqtSignal()               # una sincronización acaba de llegar a LISTO: hay datos nuevos

    def __init__(self, transport, store, discoverable_s: int = 120, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ultimo = "IDLE"
        self.status_changed.connect(self._detectar_listo)
        self._controller = SyncController(transport, store, self._on_change, discoverable_s=discoverable_s)

    # ------------------------------------------------------------------ API
    def start(self) -> None:
        self._controller.start()

    def confirm(self, accept: bool) -> None:
        self._controller.confirm(accept)

    def cancel(self) -> None:
        self._controller.cancel()

    def status(self) -> dict:
        return self._controller.status()

    # ------------------------------------------------------------- internos
    def _on_change(self, status: dict) -> None:
        """Lo llama el controlador desde sus hilos."""
        self.status_changed.emit(dict(status))

    @pyqtSlot(dict)
    def _detectar_listo(self, status: dict) -> None:
        """En el hilo de la interfaz: avisa solo en el paso a LISTO, no en cada repetición."""
        estado = status["estado"]
        if estado == LISTO and self._ultimo != LISTO:
            self.listo.emit()
        self._ultimo = estado
