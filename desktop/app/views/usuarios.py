"""Pantalla «Empleados»: cuentas aprobadas o suspendidas, con avatar, correo, nombre, rol e insignia de estado.

Aquí se suspende (con motivo) o reactiva una cuenta, se pone una contraseña nueva a las cuentas del PC y se
desvincula el teléfono de las del celular. Las cuentas pendientes o rechazadas viven en «Solicitudes».
La fila del Administrador solo se consulta: no cambia de rol ni se suspende.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import auth
from ..i18n import t
from . import components
from .base import QueryRunner, StateBanner
from .isla import isla
from .foto import icono_avatar
from .solicitudes import pedir_motivo

ENCABEZADOS = ("", "Correo", "Nombre", "Rol", "Estado")
TEXTO_ESTADO = {auth.ACTIVO: "Activa", auth.SUSPENDIDO: "Suspendida"}


class UsuariosView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._todos: list[auth.Usuario] = []
        self._usuarios: list[auth.Usuario] = []
        self._error = ""

        ayuda = QLabel(t("Las personas con cuenta aprobada. Aquí se suspende una cuenta (con motivo) o se reactiva, "
                         "se pone una contraseña nueva a las cuentas del PC y se desvincula el teléfono. Las cuentas "
                         "nuevas se aprueban en «Solicitudes»."))
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setPlaceholderText(t("Buscar por nombre, usuario o correo"))
        self.combo_rol = QComboBox()
        self.combo_rol.addItem(t("Todos los roles"), None)
        for rol in auth.ROLES:
            self.combo_rol.addItem(t(auth.NOMBRE_ROL[rol]), rol)
        self.combo_estado = QComboBox()
        self.combo_estado.addItem(t("Todos los estados"), None)
        for estado, texto in TEXTO_ESTADO.items():
            self.combo_estado.addItem(t(texto), estado)
        filtros = QHBoxLayout()
        filtros.addWidget(self.txt_buscar, 1)
        filtros.addWidget(self.combo_rol)
        filtros.addWidget(self.combo_estado)

        self.tabla = QTableWidget(0, len(ENCABEZADOS))
        self.tabla.setHorizontalHeaderLabels([t(e) for e in ENCABEZADOS])
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(46)
        self.tabla.setIconSize(QSize(28, 28))
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.setColumnWidth(0, 44)
        self.btn_rol = QPushButton(t("Cambiar rol"))
        self.btn_estado = QPushButton(t("Suspender"))
        self.btn_clave = QPushButton(t("Poner contraseña nueva…"))
        self.btn_telefono = QPushButton(t("Desvincular teléfono"))
        self.btn_telefono.setToolTip(t("La cuenta del celular queda libre para el próximo teléfono que sincronice con ella."))
        acciones = QHBoxLayout()
        for boton in (self.btn_rol, self.btn_estado, self.btn_clave, self.btn_telefono):
            acciones.addWidget(boton)
        acciones.addStretch(1)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(12)
        raiz.addWidget(ayuda)
        raiz.addWidget(self.banner)
        raiz.addLayout(filtros)
        raiz.addLayout(acciones)
        raiz.addWidget(self.tabla, 1)

        self.tabla.itemSelectionChanged.connect(self._ajustar_botones)
        self.txt_buscar.textChanged.connect(self._filtrar)
        self.combo_rol.currentIndexChanged.connect(self._filtrar)
        self.combo_estado.currentIndexChanged.connect(self._filtrar)
        self.btn_rol.clicked.connect(self._cambiar_rol)
        self.btn_estado.clicked.connect(self._cambiar_estado)
        self.btn_clave.clicked.connect(self._pedir_clave)
        self.btn_telefono.clicked.connect(self._desvincular)
        self._ajustar_botones()

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._mostrar([])
        self.refresh()

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("usuarios"):
            return
        self._runner.run(auth.listar, self._mostrar, self.banner.show_error, key="usuarios")

    def seleccionar(self, usuario: str) -> None:
        for fila, u in enumerate(self._usuarios):
            if u.usuario == usuario:
                self.tabla.selectRow(fila)

    def filas(self) -> list[tuple[str, str, str, str, str]]:
        """Correo, nombre, rol, estado y usuario de cada fila visible."""
        salida = []
        for f, u in enumerate(self._usuarios):
            insignia = self.tabla.cellWidget(f, 4)
            estado = insignia.text() if isinstance(insignia, QLabel) else t(TEXTO_ESTADO[u.estado])
            salida.append((self.tabla.item(f, 1).text(), self.tabla.item(f, 2).text(),
                           self.tabla.item(f, 3).text(), estado, u.usuario))
        return salida

    def restablecer(self, usuario: str, nueva: str) -> None:
        self._accion(auth.restablecer_clave, usuario, nueva, exito=t("Contraseña restablecida"))

    # ------------------------------------------------------------- internos
    def _elegido(self) -> auth.Usuario | None:
        fila = self.tabla.currentRow()
        return self._usuarios[fila] if 0 <= fila < len(self._usuarios) and self.tabla.selectedItems() else None

    def _mostrar(self, usuarios: list[auth.Usuario]) -> None:
        self.banner.clear()
        self._todos = [u for u in usuarios if u.estado in TEXTO_ESTADO]   # pendientes y rechazadas: «Solicitudes»
        self._filtrar()

    def _filtrar(self) -> None:
        elegido = self._elegido()
        texto = self.txt_buscar.text().strip().lower()
        rol, estado = self.combo_rol.currentData(), self.combo_estado.currentData()
        self._usuarios = [u for u in self._todos
                          if (rol is None or u.rol == rol) and (estado is None or u.estado == estado)
                          and (not texto or texto in u.usuario.lower() or texto in u.nombre.lower()
                               or texto in (u.correo or "").lower())]
        self.tabla.setRowCount(len(self._usuarios))
        for fila, u in enumerate(self._usuarios):
            avatar = QTableWidgetItem()
            avatar.setIcon(QIcon(icono_avatar(u.foto, u.nombre, 28)))
            avatar.setToolTip(f"@{u.usuario}")
            self.tabla.setItem(fila, 0, avatar)
            self.tabla.setItem(fila, 1, QTableWidgetItem(u.correo or "—"))
            self.tabla.setItem(fila, 2, QTableWidgetItem(u.nombre))
            self.tabla.setItem(fila, 3, QTableWidgetItem(t(auth.NOMBRE_ROL.get(u.rol, u.rol or ""))))
            insignia = QLabel(t(TEXTO_ESTADO[u.estado]))
            insignia.setObjectName("insignia")
            insignia.setProperty("estado", u.estado)
            insignia.setAlignment(Qt.AlignmentFlag.AlignCenter)
            insignia.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            insignia.setContentsMargins(6, 0, 6, 0)
            self.tabla.setCellWidget(fila, 4, insignia)
        self.tabla.resizeColumnsToContents()
        self.tabla.setColumnWidth(0, 44)
        self.tabla.setColumnWidth(4, 96)
        if self._error:
            self.banner.show_error(self._error)
            self._error = ""
        elif not self._todos:
            self.banner.show_empty(t("Sin empleados todavía"))
        elif not self._usuarios:
            self.banner.show_empty(t("Ningún empleado coincide con el filtro"))
        else:
            self.banner.clear()
        if elegido is not None:
            self.seleccionar(elegido.usuario)
        self._ajustar_botones()

    def _ajustar_botones(self) -> None:
        u = self._elegido()
        es_admin = u is not None and u.rol == auth.ADMIN
        movil = u is not None and u.origen == "MOVIL"
        for boton in (self.btn_estado, self.btn_clave):
            boton.setEnabled(u is not None)
        self.btn_rol.setEnabled(False)
        self.btn_rol.setToolTip(t("Solo existe un Administrador; las cuentas del PC solo pueden ser de Inventario."))
        self.btn_estado.setEnabled(u is not None and not es_admin)
        self.btn_estado.setVisible(True)
        self.btn_estado.setText(t("Reactivar") if u is not None and u.estado == auth.SUSPENDIDO else t("Suspender"))
        self.btn_clave.setVisible(not movil)
        self.btn_clave.setEnabled(u is not None and not movil)
        self.btn_telefono.setVisible(movil)
        self.btn_telefono.setEnabled(movil and u.telefono)
        self.btn_estado.setToolTip(t("El Administrador no se puede suspender.") if es_admin else "")

    def _accion(self, operacion, *args, exito: str = "") -> None:
        def listo(_resultado) -> None:
            if exito:
                isla.exito(exito)
            self.refresh()
        self._runner.run(operacion, listo, self._fallo, self._sesion, *args)

    def _fallo(self, mensaje: str) -> None:
        self._error = mensaje
        self.refresh()

    def _cambiar_rol(self) -> None:
        # Con un solo Administrador, las cuentas del PC solo pueden ser Inventario y las del móvil Operador:
        # no hay un rol de destino distinto. Se deja el botón bloqueado y se explica.
        self.banner.show_empty(t("No hay otro rol disponible para esta cuenta."))
        isla.info(t("No hay otro rol disponible para esta cuenta."))

    def _cambiar_estado(self) -> None:
        u = self._elegido()
        if u is None:
            return
        if u.estado == auth.SUSPENDIDO:
            self._accion(auth.reactivar, u.usuario, exito=t("Cuenta reactivada"))
            return
        motivo = pedir_motivo(self, "Suspender cuenta",
                              f"¿Por qué suspendes la cuenta de {u.nombre}? (lo verá al intentar entrar)")
        if motivo is not None:
            self._accion(auth.suspender, u.usuario, motivo, exito=t("Cuenta suspendida"))

    def _desvincular(self) -> None:
        u = self._elegido()
        if u is None:
            return
        if not components.Confirmacion.pedir(self, t("Desvincular teléfono"),
                                             t("La cuenta quedará libre para el próximo teléfono que sincronice."),
                                             t("Desvincular")):
            return
        self._accion(auth.desvincular_telefono, u.usuario, exito=t("Teléfono desvinculado"))

    def _pedir_clave(self) -> None:
        u = self._elegido()
        if u is None:
            return
        nueva, ok = QInputDialog.getText(
            self, t("Contraseña nueva"),
            t("Contraseña nueva para {nombre} (mínimo 8, con letras y números):", nombre=u.nombre),
            QLineEdit.EchoMode.Password)
        if ok:
            self.restablecer(u.usuario, nueva)
