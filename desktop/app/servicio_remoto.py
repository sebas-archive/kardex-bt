"""El servicio Bluetooth (otro proceso) para la interfaz Qt: lee su estado cada ``intervalo_ms`` fuera del hilo de la
interfaz y lo publica con ``status_changed``. ``listo`` avisa cuando terminó otra sincronización (sube el contador
``listos``), y ``fallo`` cuando una acción (pausar, reanudar, responder) no se pudo hacer.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from . import servicio
from .auth import Sesion
from .views.base import QueryRunner


class ServicioRemoto(QObject):
    status_changed = pyqtSignal(dict)
    listo = pyqtSignal()
    fallo = pyqtSignal(str)

    def __init__(self, intervalo_ms: int = 2000, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._status = servicio.EstadoServicio(servicio.DETENIDO).como_dict()
        self._listos: int | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.sondear)
        if intervalo_ms > 0:
            self._timer.start(intervalo_ms)
            self.sondear()

    def status(self) -> dict:
        return dict(self._status)

    def sondear(self) -> None:
        self._runner.run(servicio.estado, self._recibir, lambda _m: None, key="estado")

    def pausar(self, sesion: Sesion) -> None:
        self._accion(servicio.pausar, sesion)

    def reanudar(self, sesion: Sesion) -> None:
        self._accion(servicio.reanudar, sesion)

    def responder(self, sesion: Sesion, aceptar: bool) -> None:
        self._accion(servicio.responder_codigo, sesion, aceptar)

    # ------------------------------------------------------------- internos
    def _accion(self, fn, *args) -> None:
        self._runner.run(fn, lambda _r: self.sondear(), self.fallo.emit, *args)

    def _recibir(self, estado: servicio.EstadoServicio) -> None:
        nuevo = estado.como_dict()
        if self._listos is not None and estado.listos > self._listos:
            self._status = nuevo
            self.status_changed.emit(self.status())
            self.listo.emit()
        elif nuevo != self._status:
            self._status = nuevo
            self.status_changed.emit(self.status())
        self._listos = estado.listos
