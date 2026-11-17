"""Pantalla «Solicitudes»: cuentas nuevas y solicitudes de contraseña, para aprobar o rechazar con motivo.

Una cuenta del móvil solo puede aprobarse como Operador de Inventario; una del PC, solo como Inventario. No se
puede aprobar ni promover a Administrador: solo existe uno y ya está creado. El motivo del rechazo es obligatorio.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QInputDialog, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import auth
from ..i18n import t
from . import motion_global
from .base import QueryRunner, StateBanner

RESULTADO = {auth.ACTIVO: "Aprobada", auth.RECHAZADO: "Rechazada"}
ORIGEN = {"ESCRITORIO": "PC", "MOVIL": "Celular"}


def _tabla(encabezados: tuple[str, ...]) -> QTableWidget:
    tabla = QTableWidget(0, len(encabezados))
    tabla.setHorizontalHeaderLabels([t(e) for e in encabezados])
    tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tabla.verticalHeader().hide()
    tabla.verticalHeader().setDefaultSectionSize(34)
    tabla.horizontalHeader().setStretchLastSection(True)
    return tabla


def pedir_motivo(padre: QWidget, titulo: str, pregunta: str) -> str | None:
    """Pide el motivo (obligatorio). ``None`` si se cancela o se deja vacío: entonces no se hace nada."""
    texto, ok = QInputDialog.getText(padre, t(titulo), t(pregunta))
    texto = (texto or "").strip()
    return texto[:auth.MAX_MOTIVO] if ok and texto else None


class SolicitudesView(QWidget):
    cambiaron = pyqtSignal(int)   # cuántas solicitudes esperan respuesta
    aviso = pyqtSignal(str, str)  # (texto, tipo) para el toast de la ventana

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._nuevas: list[auth.Usuario] = []
        self._claves: list[auth.Usuario] = []
        self._error = ""

        ayuda = QLabel(t("Quien se registra (en el PC o en el celular) espera aquí. Elige su rol y apruébala, o "
                         "recházala con un motivo que verá al intentar entrar. Los cambios de contraseña de Perfil "
                         "también se aprueban aquí."))
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)

        self.tabla_cuentas = _tabla(("Usuario", "Nombre", "Correo", "Origen", "Registro"))
        self.combo_rol = QComboBox()
        self.btn_aprobar_cuenta = QPushButton(t("Aprobar"))
        self.btn_rechazar_cuenta = QPushButton(t("Rechazar…"))
        self.tabla_claves = _tabla(("Usuario", "Nombre", "Rol", "Origen"))
        self.btn_aprobar = QPushButton(t("Aprobar contraseña"))
        self.btn_rechazar_clave = QPushButton(t("Rechazar…"))
        self.tabla_historial = _tabla(("Usuario", "Nombre", "Resultado", "Rol", "Motivo", "Por"))
        # Identidad de las filas: aprobar o rechazar se ve como una fila que sale de su tabla y otra que entra al historial.
        self._vivas = {tabla: motion_global.FilasVivas(tabla)
                       for tabla in (self.tabla_cuentas, self.tabla_claves, self.tabla_historial)}
        self._ayuda, self._rotulos = ayuda, []
        self._actividad = motion_global.Actividad(self, self._runner)
        motion_global.instalar_realces(self.combo_rol)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(10)
        raiz.addWidget(ayuda)
        raiz.addWidget(self.banner)
        for titulo, tabla, widgets in (
                ("Cuentas nuevas", self.tabla_cuentas,
                 (QLabel(t("Rol:")), self.combo_rol, self.btn_aprobar_cuenta, self.btn_rechazar_cuenta)),
                ("Contraseñas por aprobar", self.tabla_claves, (self.btn_aprobar, self.btn_rechazar_clave)),
                ("Historial", self.tabla_historial, ())):
            rotulo = QLabel(t(titulo))
            rotulo.setObjectName("seccion")
            self._rotulos.append(rotulo)
            acciones = QHBoxLayout()
            for widget in widgets:
                acciones.addWidget(widget)
            acciones.addStretch(1)
            raiz.addWidget(rotulo)
            if widgets:
                raiz.addLayout(acciones)
            raiz.addWidget(tabla, 1)

        self.tabla_cuentas.itemSelectionChanged.connect(self._ajustar)
        self.tabla_claves.itemSelectionChanged.connect(self._ajustar)
        self.btn_aprobar_cuenta.clicked.connect(self._aprobar)
        self.btn_rechazar_cuenta.clicked.connect(self._rechazar)
        self.btn_aprobar.clicked.connect(lambda: self._resolver_clave(True))
        self.btn_rechazar_clave.clicked.connect(lambda: self._resolver_clave(False))
        self._ajustar()

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._mostrar(([], []))
        self.refresh()

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("solicitudes", "GESTION"):
            return
        self._runner.run(_cargar, self._mostrar, self.banner.show_error, key="solicitudes")

    def pendientes(self) -> int:
        return len(self._nuevas) + len(self._claves)

    def filas_cuentas(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla_cuentas.item(f, c).text() for c in range(5)) for f in range(self.tabla_cuentas.rowCount())]

    def filas_claves(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla_claves.item(f, c).text() for c in range(4)) for f in range(self.tabla_claves.rowCount())]

    def filas_historial(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla_historial.item(f, c).text() for c in range(6)) for f in range(self.tabla_historial.rowCount())]

    def elegir_cuenta(self, usuario: str) -> None:
        for fila, u in enumerate(self._nuevas):
            if u.usuario == usuario:
                self.tabla_cuentas.selectRow(fila)
        self._ajustar()

    def elegir_clave(self, usuario: str) -> None:
        for fila, u in enumerate(self._claves):
            if u.usuario == usuario:
                self.tabla_claves.selectRow(fila)

    # ------------------------------------------------------------- internos
    def _llenar(self, tabla: QTableWidget, filas: list[tuple[str, ...]], claves: list[str]) -> None:
        """Escribe las filas completas y solo después deja que la capa de movimiento anime lo que cambió."""
        vivas = self._vivas[tabla]
        antes = vivas.capturar()
        tabla.setRowCount(len(filas))
        for f, fila in enumerate(filas):
            for c, texto in enumerate(fila):
                tabla.setItem(f, c, QTableWidgetItem(texto))
        tabla.resizeColumnsToContents()
        vivas.revelar(antes, claves, ["\x1f".join(fila) for fila in filas])

    def entrada_motion(self) -> None:
        """Entrada de la pantalla (la llama ``motion_global.entrada_pagina``): ayuda, estado y cada sección en cascada."""
        piezas = [self._ayuda, self.banner, *self._rotulos, self.combo_rol, self.btn_aprobar_cuenta,
                  self.btn_rechazar_cuenta, self.btn_aprobar, self.btn_rechazar_clave]
        motion_global.entrada_cascada(piezas, list(self._vivas.values()))

    def _mostrar(self, datos: tuple[list[auth.Usuario], list[auth.Solicitud]]) -> None:
        usuarios, historial = datos
        self.banner.clear()
        cuenta, clave = self._cuenta(), self._clave()
        self._nuevas = [u for u in usuarios if u.estado == auth.PENDIENTE]
        self._claves = [u for u in usuarios if u.estado == auth.ACTIVO and u.clave_solicitada]
        self._llenar(self.tabla_cuentas, [
            (u.usuario, u.nombre, u.correo or "", t(ORIGEN.get(u.origen, u.origen)),
             f"{u.registrado:%d/%m/%Y}" if u.registrado else "") for u in self._nuevas],
            [u.usuario for u in self._nuevas])
        self._llenar(self.tabla_claves, [
            (u.usuario, u.nombre, t(auth.NOMBRE_ROL[u.rol]) if u.rol else "", t(ORIGEN.get(u.origen, u.origen)))
            for u in self._claves], [u.usuario for u in self._claves])
        self._llenar(self.tabla_historial, [
            (h.usuario, h.nombre, t(RESULTADO.get(h.estado, h.estado)),
             t(auth.NOMBRE_ROL[h.rol]) if h.rol else "", h.motivo or "", h.resuelto_por or "") for h in historial],
            [f"{h.usuario}|{h.estado}|{h.motivo or ''}" for h in historial])
        self.tabla_cuentas.clearSelection()
        self.tabla_claves.clearSelection()
        if cuenta is not None:
            self.elegir_cuenta(cuenta.usuario)
        if clave is not None:
            self.elegir_clave(clave.usuario)
        self._ajustar()
        if self._error:
            self.banner.show_error(self._error)
            self._error = ""
        self.cambiaron.emit(self.pendientes())

    def _cuenta(self) -> auth.Usuario | None:
        fila = self.tabla_cuentas.currentRow()
        return self._nuevas[fila] if 0 <= fila < len(self._nuevas) and self.tabla_cuentas.selectedItems() else None

    def _clave(self) -> auth.Usuario | None:
        fila = self.tabla_claves.currentRow()
        return self._claves[fila] if 0 <= fila < len(self._claves) and self.tabla_claves.selectedItems() else None

    def _ajustar(self) -> None:
        cuenta = self._cuenta()
        hay_cuenta, hay_clave = cuenta is not None, self._clave() is not None
        roles = auth.ROLES_POR_ORIGEN.get(cuenta.origen, ()) if cuenta else ()
        actuales = [self.combo_rol.itemData(i) for i in range(self.combo_rol.count())]
        if actuales != list(roles):
            self.combo_rol.clear()
            for rol in roles:
                self.combo_rol.addItem(t(auth.NOMBRE_ROL[rol]), rol)
            if auth.INVENTARIO in roles:
                self.combo_rol.setCurrentIndex(self.combo_rol.findData(auth.INVENTARIO))
        for boton in (self.btn_aprobar_cuenta, self.btn_rechazar_cuenta):
            boton.setEnabled(hay_cuenta)
        for boton in (self.btn_aprobar, self.btn_rechazar_clave):
            boton.setEnabled(hay_clave)

    def _con(self, usuario: auth.Usuario | None, operacion, *extra) -> None:
        if usuario is not None:
            self._runner.run(operacion, lambda _: self.refresh(), self._fallo, self._sesion, usuario.usuario, *extra)

    def _fallo(self, mensaje: str) -> None:
        self._error = mensaje
        self.refresh()

    def _aprobar(self) -> None:
        self._con(self._cuenta(), auth.aprobar, self.combo_rol.currentData())

    def _rechazar(self) -> None:
        cuenta = self._cuenta()
        if cuenta is None:
            return
        motivo = pedir_motivo(self, "Rechazar cuenta",
                              f"¿Por qué rechazas la cuenta de {cuenta.nombre}? (lo verá al intentar entrar)")
        if motivo is not None:
            self._con(cuenta, auth.rechazar, motivo)

    def _resolver_clave(self, aprobar: bool) -> None:
        clave = self._clave()
        if clave is None:
            return
        motivo = ""
        if not aprobar:
            motivo = pedir_motivo(self, "Rechazar contraseña",
                                  f"¿Por qué rechazas la solicitud de contraseña de {clave.nombre}? (lo verá al entrar)") or ""
            if not motivo:
                return
        self._con(clave, auth.resolver_clave, aprobar, motivo)


def _cargar() -> tuple[list[auth.Usuario], list[auth.Solicitud]]:
    """Cuentas e historial en una sola llamada fuera del hilo de la interfaz."""
    return auth.listar(), auth.historial_solicitudes()
