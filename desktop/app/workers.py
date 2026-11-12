"""Trabajo fuera del hilo de la interfaz.

Uso::

    worker = QueryWorker(db.fetch_resumen, id_conteo)
    worker.signals.finished.connect(mostrar)   # se entrega en el hilo de la interfaz
    worker.signals.failed.connect(avisar_error)
    QThreadPool.globalInstance().start(worker)

Quien lance el worker debe conservar una referencia a él hasta que termine (el worker no se
autodestruye, para que sus señales lleguen).
"""

from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal


class WorkerSignals(QObject):
    finished = pyqtSignal(object)  # el resultado de la función
    failed = pyqtSignal(str)       # el mensaje del error (p. ej. «ORA-12541: …»)


class QueryWorker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # cualquier fallo llega a la UI como texto, nunca la tumba
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(result)
