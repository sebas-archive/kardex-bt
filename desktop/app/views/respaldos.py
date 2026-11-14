"""Pantalla «Respaldos» (solo el Administrador): crear uno ahora, la lista, restaurar todo y el automático.

Restaurar pide escribir RESTAURAR. Al terminar emite ``restaurado``: la ventana cierra la sesión (las cuentas
pudieron cambiar) y avisa que el servicio Bluetooth quedó en pausa.
"""

from __future__ import annotations

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from btsync.respaldo import respaldos_dir

from .. import auth, respaldos
from ..i18n import registrar, t
from .base import QueryRunner, StateBanner

registrar({
    "Un respaldo guarda todos los datos y las fotos en un archivo .zip de la carpeta de respaldos.":
        "A backup saves all data and photos in a .zip file in the backups folder.",
    "Crear respaldo ahora": "Create backup now",
    "Restaurar…": "Restore…",
    "Abrir carpeta": "Open folder",
    "Automático: todos los días a las": "Automatic: every day at",
    "conservar los últimos": "keep the last",
    "Guardar": "Save",
    "Fecha": "Date",
    "Tamaño": "Size",
    "Fotos": "Photos",
    "Hecho por": "Made by",
    "Sí": "Yes",
    "No": "No",
    "Automático": "Automatic",
    "Antes de restaurar": "Before restoring",
    "Restaurar respaldo": "Restore backup",
    "Se reemplazará todo (datos y fotos) por el respaldo {archivo}. Antes se guarda un respaldo del estado "
    "actual y se pausa el servicio Bluetooth. Escribe {clave} para continuar.":
        "Everything (data and photos) will be replaced by the backup {archivo}. A backup of the current state "
        "is saved first and the Bluetooth service is paused. Type {clave} to continue.",
    "Restaurar": "Restore",
    "Cancelar": "Cancel",
    "Aún no hay respaldos.": "There are no backups yet.",
    "Creando respaldo…": "Creating backup…",
    "Respaldo creado: {archivo}": "Backup created: {archivo}",
    "Restaurando… (se pausa el servicio Bluetooth)": "Restoring… (the Bluetooth service is paused)",
    "Respaldo automático guardado.": "Automatic backup saved.",
    "Restaurando": "Restoring",
    "Se restauró el respaldo. Vuelve a iniciar sesión; el servicio Bluetooth quedó en pausa.":
        "The backup was restored. Sign in again; the Bluetooth service is paused.",
})

ENCABEZADOS = ("Fecha", "Tamaño", "Fotos", "Hecho por")
CLAVE = "RESTAURAR"


def _tamano(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB".replace(".", ",")
    return f"{max(1, round(n / 1024))} KB"


class DialogoRestaurar(QDialog):
    """Confirmación fuerte: Aceptar solo se habilita al escribir exactamente RESTAURAR."""

    def __init__(self, padre, archivo: str) -> None:
        super().__init__(padre)
        self.setWindowTitle(t("Restaurar respaldo"))
        texto = QLabel(t("Se reemplazará todo (datos y fotos) por el respaldo {archivo}. Antes se guarda un "
                         "respaldo del estado actual y se pausa el servicio Bluetooth. Escribe {clave} para "
                         "continuar.", archivo=archivo, clave=CLAVE))
        texto.setWordWrap(True)
        self.txt = QLineEdit()
        self.botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.botones.button(QDialogButtonBox.StandardButton.Ok).setText(t("Restaurar"))
        self.botones.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.botones.button(QDialogButtonBox.StandardButton.Cancel).setText(t("Cancelar"))
        self.txt.textChanged.connect(
            lambda valor: self.botones.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valor == CLAVE))
        self.botones.accepted.connect(self.accept)
        self.botones.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(texto)
        lay.addWidget(self.txt)
        lay.addWidget(self.botones)


class RespaldosView(QWidget):
    restaurado = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._lista: list[respaldos.Respaldo] = []
        self._auto_cargado: tuple | None = None

        ayuda = QLabel(t("Un respaldo guarda todos los datos y las fotos en un archivo .zip de la carpeta de respaldos."))
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("avisoFormulario")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.hide()

        self.btn_crear = QPushButton(t("Crear respaldo ahora"))
        self.btn_crear.setObjectName("primario")
        self.btn_restaurar = QPushButton(t("Restaurar…"))
        self.btn_restaurar.setObjectName("peligro")
        self.btn_carpeta = QPushButton(t("Abrir carpeta"))
        self.tabla = QTableWidget(0, len(ENCABEZADOS))
        self.tabla.setHorizontalHeaderLabels([t(c) for c in ENCABEZADOS])
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.verticalHeader().hide()
        self.tabla.horizontalHeader().setStretchLastSection(True)

        self.chk_auto = QCheckBox(t("Automático: todos los días a las"))
        self.txt_hora = QLineEdit()
        self.txt_hora.setMaximumWidth(70)
        self.txt_hora.setPlaceholderText("23:00")
        self.spin_conservar = QSpinBox()
        self.spin_conservar.setRange(1, 90)
        self.btn_guardar_auto = QPushButton(t("Guardar"))

        arriba = QHBoxLayout()
        arriba.addWidget(self.btn_crear)
        arriba.addStretch(1)
        abajo = QHBoxLayout()
        abajo.addStretch(1)
        abajo.addWidget(self.btn_restaurar)
        abajo.addWidget(self.btn_carpeta)
        auto = QHBoxLayout()
        auto.addWidget(self.chk_auto)
        auto.addWidget(self.txt_hora)
        auto.addSpacing(16)
        auto.addWidget(QLabel(t("conservar los últimos")))
        auto.addWidget(self.spin_conservar)
        auto.addStretch(1)
        auto.addWidget(self.btn_guardar_auto)

        tarjeta = QFrame()
        tarjeta.setObjectName("card")
        cuerpo = QVBoxLayout(tarjeta)
        cuerpo.setContentsMargins(20, 16, 20, 16)
        cuerpo.setSpacing(10)
        cuerpo.addLayout(arriba)
        cuerpo.addWidget(self.banner)
        cuerpo.addWidget(self.tabla, 1)
        cuerpo.addLayout(abajo)
        cuerpo.addLayout(auto)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(12)
        raiz.addWidget(ayuda)
        raiz.addWidget(self.lbl_error)
        raiz.addWidget(self.lbl_info)
        raiz.addWidget(tarjeta, 1)

        self.btn_crear.clicked.connect(self._crear)
        self.btn_restaurar.clicked.connect(self._restaurar)
        self.btn_carpeta.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(respaldos_dir().resolve()))))
        self.btn_guardar_auto.clicked.connect(self._guardar_auto)
        self.tabla.itemSelectionChanged.connect(self._habilitar)
        self._habilitar()

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        self._auto_cargado = None
        self.refresh()

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("respaldos"):
            return
        self._runner.run(respaldos.listar, self._mostrar, self.banner.show_error, self._sesion, key="lista")
        if not self._auto_sucio():
            self._runner.run(respaldos.automatico, self._mostrar_auto, lambda _m: None, key="auto")

    # ------------------------------------------------------------- pruebas
    def filas(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla.item(f, c).text() if self.tabla.item(f, c) else ""
                      for c in range(len(ENCABEZADOS))) for f in range(self.tabla.rowCount())]

    def _confirmar(self, archivo: str) -> bool:
        return DialogoRestaurar(self, archivo).exec() == QDialog.DialogCode.Accepted

    # ------------------------------------------------------------- internos
    def _mostrar(self, lista) -> None:
        self.banner.clear()
        elegido = self._elegido()
        self._lista = list(lista)
        self.tabla.setRowCount(len(self._lista))
        for f, r in enumerate(self._lista):
            hecho = t("Automático") if r.origen == "auto" else t("Antes de restaurar") if r.origen == "previo" else r.usuario
            for c, texto in enumerate((f"{r.fecha:%d/%m/%Y %H:%M}", _tamano(r.bytes), t("Sí") if r.fotos else t("No"),
                                       hecho)):
                self.tabla.setItem(f, c, QTableWidgetItem(texto))
            if elegido is not None and r.archivo == elegido:
                self.tabla.selectRow(f)
        if not self._lista:
            self.banner.show_empty(t("Aún no hay respaldos."))
        self.tabla.resizeColumnsToContents()
        self._habilitar()

    def _mostrar_auto(self, valores: tuple[bool, str, int]) -> None:
        activo, hora, conservar = valores
        self.chk_auto.setChecked(activo)
        self.txt_hora.setText(hora)
        self.spin_conservar.setValue(conservar)
        self._auto_cargado = valores

    def _auto_sucio(self) -> bool:
        return self._auto_cargado is not None and self._auto_cargado != (
            self.chk_auto.isChecked(), self.txt_hora.text(), self.spin_conservar.value())

    def _elegido(self) -> str | None:
        if self.tabla.selectionModel() is None:
            return None
        filas = self.tabla.selectionModel().selectedRows()
        return self._lista[filas[0].row()].archivo if filas and filas[0].row() < len(self._lista) else None

    def _habilitar(self) -> None:
        self.btn_restaurar.setEnabled(self._elegido() is not None)

    def _avisar(self, error: str = "", info: str = "") -> None:
        self.lbl_error.setText(error)
        self.lbl_error.setVisible(bool(error))
        self.lbl_info.setText(info)
        self.lbl_info.setVisible(bool(info))

    def _ocupado(self, si: bool) -> None:
        for b in (self.btn_crear, self.btn_guardar_auto):
            b.setEnabled(not si)
        self.btn_restaurar.setEnabled(not si and self._elegido() is not None)

    def _crear(self) -> None:
        if self._sesion is None:
            return
        self._avisar(info=t("Creando respaldo…"))
        self._ocupado(True)
        self._runner.run(respaldos.crear, self._creado, self._fallo, self._sesion)

    def _creado(self, r) -> None:
        self._ocupado(False)
        self._avisar(info=t("Respaldo creado: {archivo}", archivo=r.archivo))
        self.refresh()

    def _restaurar(self) -> None:
        archivo = self._elegido()
        if self._sesion is None or archivo is None or not self._confirmar(archivo):
            return
        self._avisar(info=t("Restaurando… (se pausa el servicio Bluetooth)"))
        self._ocupado(True)
        self._runner.run(respaldos.restaurar, self._restaurado, self._fallo, self._sesion, archivo)

    def _restaurado(self, _r) -> None:
        self._ocupado(False)
        self._avisar()
        self.restaurado.emit()

    def _guardar_auto(self) -> None:
        if self._sesion is None:
            return
        self._ocupado(True)
        self._runner.run(respaldos.guardar_automatico, self._auto_guardado, self._fallo, self._sesion,
                         self.chk_auto.isChecked(), self.txt_hora.text(), self.spin_conservar.value())

    def _auto_guardado(self, valores) -> None:
        self._ocupado(False)
        self._mostrar_auto(valores)
        self._avisar(info=t("Respaldo automático guardado."))

    def _fallo(self, mensaje: str) -> None:
        self._ocupado(False)
        self._avisar(error=mensaje)
