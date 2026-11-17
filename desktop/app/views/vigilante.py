"""Acabado común de toda la aplicación, sin tocar cada pantalla.

- Tablas: cuando no tienen filas muestran «Sin datos» centrado (estado vacío) en lugar de un recuadro en blanco.
- Diálogos: márgenes y separación uniformes y un ancho mínimo razonable, también en los de Qt (``QInputDialog``…).

Se instala una vez como filtro de eventos de la aplicación y actúa cuando un widget se muestra por primera vez.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog, QLabel, QMenu, QPushButton, QTableView, QToolButton

from ..i18n import registrar, t
from . import motion_global

registrar({"Sin datos": "No data"})

_INSTALADO: "Vigilante | None" = None


class _Vacio(QLabel):
    """«Sin datos» sobre el área de una tabla sin filas. Vive dentro de la tabla: al destruirse ella, se desconecta sola."""

    def __init__(self, tabla: QTableView) -> None:
        super().__init__(str(tabla.property("textoVacio") or t("Sin datos")), tabla.viewport())
        self.setObjectName("tablaVacia")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._modelo = tabla.model()
        tabla.viewport().installEventFilter(self)
        if self._modelo is not None:
            for senal in (self._modelo.rowsInserted, self._modelo.rowsRemoved, self._modelo.modelReset,
                          self._modelo.layoutChanged):
                senal.connect(self.actualizar)
        self.actualizar()

    def actualizar(self, *_args) -> None:
        padre = self.parentWidget()
        if padre is None:
            return
        vacia = self._modelo is None or self._modelo.rowCount() == 0
        self.setGeometry(padre.rect())
        self.setVisible(vacia)
        if vacia:
            self.raise_()

    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() == QEvent.Type.Resize and self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())
        return False


def _instalar_vacio(tabla: QTableView) -> None:
    tabla.setProperty("vacioInstalado", True)
    _Vacio(tabla)


def _afinar_dialogo(dialogo: QDialog) -> None:
    dialogo.setProperty("afinado", True)
    if isinstance(dialogo, QFileDialog):
        return
    lay = dialogo.layout()
    if lay is None or lay.contentsMargins().left() > 12:
        return
    lay.setContentsMargins(24, 20, 24, 20)
    lay.setSpacing(max(lay.spacing(), 12))
    if dialogo.minimumWidth() < 440 and dialogo.width() < 520:
        dialogo.setMinimumWidth(460)


def _animar_tabla(tabla: QTableView) -> None:
    """Datos nuevos → las filas aparecen con un fundido corto (una vez por tanda de cambios)."""
    tabla.setProperty("fundidoInstalado", True)
    modelo = tabla.model()
    if modelo is None:
        return
    pendiente = QTimer(tabla)
    pendiente.setSingleShot(True)
    pendiente.setInterval(30)
    pendiente.timeout.connect(lambda: motion_global.fundir_contenido(tabla))
    for senal in (modelo.modelReset, modelo.rowsInserted):
        senal.connect(lambda *_a: pendiente.start())


class Vigilante(QObject):
    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() == QEvent.Type.Show:
            if isinstance(objeto, (QPushButton, QToolButton)) and not objeto.property("presionInstalada"):
                motion_global.instalar_presion(objeto)
            elif isinstance(objeto, QMenu) and objeto.isWindow():
                motion_global.aparecer_popup(objeto)
            elif objeto.isWidgetType() and objeto.isWindow() and objeto.metaObject().className() == "QTipLabel":
                motion_global.aparecer_popup(objeto, 110)      # los tooltips nacen con un fundido corto, como los menús
            if isinstance(objeto, QTableView) and not objeto.property("fundidoInstalado"):
                _animar_tabla(objeto)
            if isinstance(objeto, QTableView) and not objeto.property("vacioInstalado"):
                _instalar_vacio(objeto)
            elif isinstance(objeto, QDialog) and not objeto.property("afinado") and objeto.isWindow():
                _afinar_dialogo(objeto)
                # Los modales propios (translúcidos) ya traen su entrada; los estándar nacen con un fundido.
                if not objeto.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground):
                    motion_global.aparecer_popup(objeto, 180)
        return False


def instalar(app: QApplication | None = None) -> None:
    """Instala el filtro una sola vez para toda la aplicación."""
    global _INSTALADO
    app = app or QApplication.instance()
    if app is None or _INSTALADO is not None:
        return
    _INSTALADO = Vigilante(app)
    app.installEventFilter(_INSTALADO)
