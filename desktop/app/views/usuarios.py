"""Pantalla «Empleados»: las cuentas aprobadas o suspendidas, con filtros por rol, estado y texto.

Aquí se cambia el rol, se suspende una cuenta (con motivo) o se reactiva, y se pone una contraseña nueva.
Las cuentas pendientes o rechazadas viven en «Solicitudes».
"""

from __future__ import annotations

from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import auth
from .base import QueryRunner, StateBanner
from .solicitudes import pedir_motivo

ENCABEZADOS = ("Usuario", "Nombre", "Rol", "Estado", "Motivo")
TEXTO_ESTADO = {auth.ACTIVO: "Activa", auth.SUSPENDIDO: "Suspendida"}


class UsuariosView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._todos: list[auth.Usuario] = []
        self._usuarios: list[auth.Usuario] = []     # los que se ven con los filtros actuales

        ayuda = QLabel("Las personas con cuenta aprobada. Aquí se cambia el rol, se suspende una cuenta (con motivo) o "
                       "se reactiva, y se pone una contraseña nueva. Las cuentas nuevas se aprueban en «Solicitudes».")
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setPlaceholderText("Buscar por nombre o usuario")
        self.combo_rol = QComboBox()
        self.combo_rol.addItem("Todos los roles", None)
        for rol in auth.ROLES:
            self.combo_rol.addItem(auth.NOMBRE_ROL[rol], rol)
        self.combo_estado = QComboBox()
        self.combo_estado.addItem("Todos los estados", None)
        for estado, texto in TEXTO_ESTADO.items():
            self.combo_estado.addItem(texto, estado)
        filtros = QHBoxLayout()
        filtros.addWidget(self.txt_buscar, 1)
        filtros.addWidget(self.combo_rol)
        filtros.addWidget(self.combo_estado)

        self.tabla = QTableWidget(0, len(ENCABEZADOS))
        self.tabla.setHorizontalHeaderLabels(list(ENCABEZADOS))
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(36)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.btn_rol = QPushButton("Cambiar rol")
        self.btn_estado = QPushButton("Suspender")
        self.btn_clave = QPushButton("Poner contraseña nueva…")
        self.btn_telefono = QPushButton("Desvincular teléfono")
        self.btn_telefono.setToolTip("La cuenta del celular queda libre para el próximo teléfono que sincronice con ella.")
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
        if sesion is None:   # al salir no queda nada de la sesión anterior en pantalla
            self._mostrar([])
        self.refresh()

    def set_conteo(self, id_conteo: str | None) -> None:
        """Las cuentas no dependen del conteo."""

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("usuarios"):
            return
        self._runner.run(auth.listar, self._mostrar, self.banner.show_error, key="usuarios")

    def seleccionar(self, usuario: str) -> None:
        for fila, u in enumerate(self._usuarios):
            if u.usuario == usuario:
                self.tabla.selectRow(fila)

    def filas(self) -> list[tuple[str, str, str, str]]:
        """Usuario, nombre, rol y estado de cada fila visible."""
        return [tuple(self.tabla.item(f, c).text() for c in range(4)) for f in range(self.tabla.rowCount())]

    def restablecer(self, usuario: str, nueva: str) -> None:
        self._accion(auth.restablecer_clave, usuario, nueva)

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
                          and (not texto or texto in u.usuario.lower() or texto in u.nombre.lower())]
        self.tabla.setRowCount(len(self._usuarios))
        for fila, u in enumerate(self._usuarios):
            celdas = (u.usuario, u.nombre, auth.NOMBRE_ROL.get(u.rol, u.rol), TEXTO_ESTADO[u.estado], u.motivo or "")
            for columna, valor in enumerate(celdas):
                item = QTableWidgetItem(valor)
                if u.estado != auth.ACTIVO:
                    item.setForeground(QBrush(QColor("#6E6E6E")))
                self.tabla.setItem(fila, columna, item)
        self.tabla.resizeColumnsToContents()
        if elegido is not None:
            self.seleccionar(elegido.usuario)
        self._ajustar_botones()

    def _ajustar_botones(self) -> None:
        u = self._elegido()
        for boton in (self.btn_rol, self.btn_estado, self.btn_clave):
            boton.setEnabled(u is not None)
        movil = u is not None and u.origen == "MOVIL"
        self.btn_rol.setVisible(not movil)          # un operador del celular no cambia de rol (no entra al PC)
        self.btn_clave.setVisible(not movil)        # su contraseña vive en el teléfono
        self.btn_telefono.setVisible(movil)
        self.btn_telefono.setEnabled(movil and u.telefono)
        if u is not None:
            self.btn_rol.setText("Pasar a inventario" if u.rol == auth.ADMIN else "Hacer administrador")
            self.btn_rol.setEnabled(u.estado == auth.ACTIVO)
            self.btn_estado.setText("Suspender" if u.estado == auth.ACTIVO else "Reactivar")

    def _accion(self, operacion, *args) -> None:
        self._runner.run(operacion, lambda _: self.refresh(), self.banner.show_error, self._sesion, *args)

    def _cambiar_rol(self) -> None:
        u = self._elegido()
        if u is not None:
            self._accion(auth.cambiar_rol, u.usuario, auth.INVENTARIO if u.rol == auth.ADMIN else auth.ADMIN)

    def _cambiar_estado(self) -> None:
        u = self._elegido()
        if u is None:
            return
        if u.estado == auth.SUSPENDIDO:
            self._accion(auth.reactivar, u.usuario)
            return
        motivo = pedir_motivo(self, "Suspender cuenta", f"¿Por qué suspendes la cuenta de {u.nombre}? (lo verá al intentar entrar)")
        if motivo is not None:
            self._accion(auth.suspender, u.usuario, motivo)

    def _desvincular(self) -> None:
        u = self._elegido()
        if u is not None:
            self._accion(auth.desvincular_telefono, u.usuario)

    def _pedir_clave(self) -> None:
        u = self._elegido()
        if u is None:
            return
        nueva, ok = QInputDialog.getText(self, "Contraseña nueva", f"Contraseña nueva para {u.nombre} (mínimo 8, con letras y números):",
                                         QLineEdit.EchoMode.Password)
        if ok:
            self.restablecer(u.usuario, nueva)
