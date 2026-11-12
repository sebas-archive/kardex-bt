"""Piezas comunes de las vistas: contrato, ejecución de consultas fuera de la UI y avisos de estado."""

from __future__ import annotations

from typing import Callable, Protocol

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from ..workers import QueryWorker

ESTILO = """
QMainWindow, QWidget { background: #f4f6f9; color: #1f2933; }
QTabWidget::pane { border: 1px solid #d9dee5; background: #f4f6f9; top: -1px; }
QTabBar::tab { padding: 8px 18px; background: #e6eaf0; border: 1px solid #d9dee5; border-bottom: none;
               border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
QTabBar::tab:selected { background: #ffffff; font-weight: 600; }
QFrame#card { background: #ffffff; border: 1px solid #d9dee5; border-radius: 10px; }
QFrame#card QLabel { background: transparent; }
QLabel#cardTitulo { color: #5b6573; font-size: 12px; }
QLabel#cardValor { font-size: 24px; font-weight: 600; }
QLabel#subtitulo { color: #5b6573; }
QFrame#aviso { background: #fff7e0; border: 1px solid #f0d58a; border-radius: 6px; }
QFrame#aviso[error="true"] { background: #fdecea; border: 1px solid #f1aeb5; }
QFrame#aviso QLabel { background: transparent; }
QPushButton { padding: 6px 14px; border: 1px solid #b8c1cc; border-radius: 6px; background: #ffffff; }
QPushButton:hover { background: #eef2f7; }
QPushButton:disabled { color: #98a2b3; background: #eceff3; }
QPushButton#peligro { color: #b42318; border-color: #f1aeb5; }
QTableView, QTableWidget { background: #ffffff; alternate-background-color: #f8fafc; border: 1px solid #d9dee5;
                           gridline-color: #e6eaf0; }
QHeaderView::section { background: #e6eaf0; padding: 6px; border: none; border-right: 1px solid #d9dee5; }
QLineEdit, QComboBox { padding: 5px 8px; border: 1px solid #b8c1cc; border-radius: 6px; background: #ffffff; }
"""


class RefreshableView(Protocol):
    """Lo que ``MainWindow.add_view`` espera de una pestaña (además de ser un QWidget)."""

    def refresh(self) -> None:
        """Vuelve a consultar y repinta. Nunca bloquea la interfaz."""

    def set_conteo(self, id_conteo: str | None) -> None:
        """Cambia el conteo mostrado (``None`` si no hay ninguno) y refresca."""


class _Entrega(QObject):
    """Vive en el hilo de la interfaz: recibe lo que termina un worker y lo pasa al runner."""

    def __init__(self, runner: "QueryRunner", worker: QueryWorker, key, token, on_done, on_error) -> None:
        super().__init__(runner)
        self.runner, self.worker, self.key, self.token = runner, worker, key, token
        self.on_done, self.on_error = on_done, on_error

    @pyqtSlot(object)
    def exito(self, resultado) -> None:
        self.runner._terminar(self, self.on_done, resultado)

    @pyqtSlot(str)
    def fallo(self, mensaje: str) -> None:
        self.runner._terminar(self, self.on_error, mensaje)


class QueryRunner(QObject):
    """Ejecuta funciones (consultas a Oracle) en el pool de hilos y entrega el resultado en la UI.

    Con ``key``, solo cuenta la última llamada de esa clave: un resultado viejo que llega tarde
    (por un refresco más reciente) se descarta.
    """

    def __init__(self, parent: QObject | None = None, pool: QThreadPool | None = None) -> None:
        super().__init__(parent)
        self._pool = pool or QThreadPool.globalInstance()
        self._activos: dict[int, tuple[QueryWorker, _Entrega]] = {}
        self._ultimo: dict[str, int] = {}
        self._token = 0

    @property
    def pendientes(self) -> int:
        return len(self._activos)

    def run(self, fn: Callable, on_done: Callable, on_error: Callable | None = None, *args,
            key: str | None = None, **kwargs) -> QueryWorker:
        self._token += 1
        if key is not None:
            self._ultimo[key] = self._token
        worker = QueryWorker(fn, *args, **kwargs)
        entrega = _Entrega(self, worker, key, self._token, on_done, on_error)
        self._activos[id(worker)] = (worker, entrega)  # se conservan hasta entregar (las señales deben llegar)
        worker.signals.finished.connect(entrega.exito)
        worker.signals.failed.connect(entrega.fallo)
        self._pool.start(worker)
        return worker

    def _terminar(self, entrega: _Entrega, callback: Callable | None, valor) -> None:
        self._activos.pop(id(entrega.worker), None)
        if entrega.key is not None and self._ultimo.get(entrega.key) != entrega.token:
            return  # llegó tarde: ya hay una consulta más reciente
        if callback is not None:
            callback(valor)


class StateBanner(QFrame):
    """Aviso de estado de una vista: «Cargando…», «Sin datos» o un error de BD con «Reintentar»."""

    retry = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("aviso")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self._label = QLabel()
        self._label.setWordWrap(True)
        self.btn_reintentar = QPushButton("Reintentar")
        self.btn_reintentar.clicked.connect(self.retry)
        lay.addWidget(self._label, 1)
        lay.addWidget(self.btn_reintentar)
        self.hide()

    def text(self) -> str:
        return self._label.text()

    def _mostrar(self, texto: str, error: bool) -> None:
        self._label.setText(texto)
        self.setProperty("error", error)
        self.style().unpolish(self)
        self.style().polish(self)
        self.btn_reintentar.setVisible(error)
        self.show()

    def show_loading(self) -> None:
        self._mostrar("Cargando…", False)

    def show_empty(self, texto: str = "Sin datos") -> None:
        self._mostrar(texto, False)

    def show_error(self, mensaje: str) -> None:
        self._mostrar(f"No se pudo consultar la base de datos: {mensaje}", True)

    def clear(self) -> None:
        self.hide()
