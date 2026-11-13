"""Piezas comunes de las vistas: contrato, ejecución de consultas fuera de la UI y avisos de estado."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, Protocol

from PyQt6.QtCore import QObject, QPointF, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from ..workers import QueryWorker

ESTILO = """
QMainWindow, QWidget { background: #0A0A0A; color: #EDEDED; font-size: 13px; }
QWidget#marco { background: #161616; }
QWidget#contenido { background: transparent; }
QToolTip { background: #262626; color: #EDEDED; border: 1px solid #333333; padding: 6px 8px; }

/* Barra lateral: sin fondo propio, se funde con el marco exterior (#161616) */
QFrame#lateral, QFrame#lateral QWidget { background: transparent; border: none; }
QFrame#lateral QLabel { background: transparent; }
QLabel#marca { font-size: 16px; font-weight: 700; color: #FFFFFF; }
QPushButton#nav { text-align: left; padding: 10px 12px; border: none; border-radius: 8px; background: transparent;
                  color: #A3A3A3; font-weight: 600; }
QPushButton#nav:hover { background: rgba(255,255,255,0.06); color: #FFFFFF; }
QPushButton#nav:checked { background: rgba(255,255,255,0.10); color: #FFFFFF; }
QPushButton#nav:focus { border: 1px solid #5B5B5B; }
QFrame#lateral[contraida="true"] QPushButton#nav { text-align: center; padding: 10px 0; }
QPushButton#iconoLateral { border: none; border-radius: 8px; background: transparent; min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; padding: 0; }
QPushButton#iconoLateral:hover { background: rgba(255,255,255,0.08); }
QPushButton#iconoLateral:focus { border: 1px solid #5B5B5B; }
QFrame#pieCuenta { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; }
QFrame#pieCuenta[contraida="true"] { border: none; background: transparent; }
QFrame#pieCuenta QLabel, QFrame#pieCuenta QWidget { background: transparent; }
QPushButton#cuenta { border: none; background: transparent; text-align: left; border-radius: 8px; }
QPushButton#cuenta:hover { background: rgba(255,255,255,0.06); }
QFrame#pieCuenta QLabel#avatar { background: #10B981; color: #04130E; border-radius: 18px; font-weight: 700; font-size: 14px; }
QLabel#usuarioNombre { font-weight: 600; color: #FFFFFF; }
QLabel#usuarioRol { color: #8A8A8A; font-size: 12px; }

/* Lienzo principal encajado en el marco */
QFrame#lienzo { background: #0A0A0A; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; }

/* Encabezado de cada página */
QLabel#tituloPagina { font-size: 22px; font-weight: 600; background: transparent; }
QLabel#chipEstado { background: #1C1C1C; color: #A3A3A3; border-radius: 12px; padding: 0px 12px; font-size: 12px; }
QLabel#chipEstado[estado="ok"] { background: #10261F; color: #34D399; }
QLabel#chipEstado[estado="activo"] { background: #1F2350; color: #A5B4FC; }
QLabel#chipEstado[estado="error"] { background: #3A1512; color: #F87171; }

/* Tarjetas */
QFrame#card { background: #111111; border: 1px solid #232323; border-radius: 12px; }
QFrame#card QLabel { background: transparent; }
QLabel#cardTitulo { color: #8A8A8A; font-size: 12px; }
QLabel#cardValor { font-size: 26px; font-weight: 600; }
QLabel#cardDetalle { color: #8A8A8A; font-size: 11px; }
QLabel#seccion { font-size: 14px; font-weight: 600; background: transparent; }
QLabel#subtitulo, QLabel#ayuda { color: #8A8A8A; background: transparent; }
QLabel#insignia { border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600; color: #A3A3A3; background: #1C1C1C; }
QLabel#insignia[estado="ABIERTO"], QLabel#insignia[estado="ADMIN"] { background: #10261F; color: #34D399; }
QLabel#insignia[estado="CERRADO"] { background: #1C1C1C; color: #A3A3A3; }
QLabel#insignia[estado="INVENTARIO"] { background: #1F2350; color: #A5B4FC; }
QLabel#resumen { color: #A3A3A3; background: transparent; }
QLabel#estadoSync { font-size: 19px; font-weight: 600; background: transparent; }
QLabel#codigoSync { font-size: 54px; font-weight: 700; font-family: "DejaVu Sans Mono"; color: #34D399; background: transparent; }
QLabel#errorFormulario { color: #F87171; background: transparent; }
QLabel#avisoFormulario { color: #34D399; background: transparent; }

/* Acceso */
QFrame#panelMarca { background: #0F2A24; border: none; }
QFrame#panelMarca QLabel { color: #FFFFFF; background: transparent; }
QLabel#tituloAcceso { font-size: 22px; font-weight: 600; background: transparent; }
QFrame#card QStackedWidget, QWidget#formulario { background: #111111; }
QPushButton#enlace { border: none; background: transparent; color: #34D399; font-weight: 600; padding: 4px; }
QPushButton#enlace:hover { color: #6EE7B7; background: transparent; }

/* Avisos de estado */
QFrame#aviso { background: #2B2410; border: 1px solid #5C4A16; border-radius: 10px; }
QFrame#aviso[error="true"] { background: #3A1512; border: 1px solid #7A2A24; }
QFrame#aviso QLabel { background: transparent; }

/* Botones */
QPushButton { padding: 7px 16px; border: 1px solid #2E2E2E; border-radius: 8px; background: #111111; font-weight: 600; }
QPushButton:hover { background: #1C1C1C; }
QPushButton:pressed { background: #232323; }
QPushButton:disabled { color: #6E6E6E; background: #1C1C1C; border-color: #232323; }
QPushButton#primario { background: #10B981; color: #04130E; border: none; padding: 9px 20px; }
QPushButton#primario:hover { background: #34D399; }
QPushButton#primario:disabled { background: #1E3A32; color: #6E6E6E; }
QPushButton#peligro { color: #F87171; border-color: #7A2A24; }
QPushButton#peligro:hover { background: #3A1512; }
QPushButton#chip { border-radius: 14px; padding: 5px 14px; background: #111111; border: 1px solid #2E2E2E; font-weight: 600; }
QPushButton#chip:hover { background: #1C1C1C; }
QPushButton#chip:checked { background: #10B981; color: #04130E; border-color: #10B981; }

/* Tablas y campos */
QTableView, QTableWidget { background: #111111; border: 1px solid #232323; border-radius: 10px; gridline-color: #1C1C1C;
                           selection-background-color: #10261F; selection-color: #FFFFFF; }
QHeaderView::section { background: #0F0F0F; padding: 8px 6px; border: none; border-bottom: 1px solid #232323;
                       font-weight: 600; color: #A3A3A3; }
QLineEdit, QComboBox, QSpinBox { padding: 7px 10px; border: 1px solid #2E2E2E; border-radius: 8px; background: #111111; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 2px solid #10B981; padding: 6px 9px; }
QComboBox::drop-down, QSpinBox::up-button, QSpinBox::down-button { border: none; width: 22px; background: transparent; }
QComboBox QAbstractItemView { background: #111111; border: 1px solid #2E2E2E; selection-background-color: #10261F;
                              selection-color: #EDEDED; outline: none; }
QProgressBar { border: none; background: #232323; border-radius: 4px; height: 8px; }
QProgressBar::chunk { background: #10B981; border-radius: 4px; }
QScrollArea { border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2E2E2E; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


_FLECHAS: dict[str, str] = {}


def estilo() -> str:
    """``ESTILO`` más las flechas de los desplegables y de los campos numéricos.

    Qt deja de dibujar esas flechas en cuanto un control lleva hoja de estilo, y solo acepta una imagen: se pintan
    una vez (necesita la ``QApplication`` ya creada) en una carpeta temporal y se referencian desde aquí.
    """
    if not _FLECHAS:
        carpeta = Path(tempfile.mkdtemp(prefix="inventario-estilo-"))
        for nombre, puntos in (("abajo", ((3, 5), (7, 9), (11, 5))), ("arriba", ((3, 9), (7, 5), (11, 9)))):
            imagen = QPixmap(14, 14)
            imagen.fill(Qt.GlobalColor.transparent)
            pintor = QPainter(imagen)
            pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
            pintor.setPen(QPen(QColor("#8A8A8A"), 1.8, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
            pintor.drawPolyline(*[QPointF(x, y) for x, y in puntos])
            pintor.end()
            ruta = carpeta / f"{nombre}.png"
            imagen.save(str(ruta))
            _FLECHAS[nombre] = ruta.as_posix()
    return ESTILO + f"""
QComboBox::down-arrow {{ image: url({_FLECHAS["abajo"]}); width: 14px; height: 14px; margin-right: 8px; }}
QSpinBox::up-arrow {{ image: url({_FLECHAS["arriba"]}); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url({_FLECHAS["abajo"]}); width: 10px; height: 10px; }}
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
