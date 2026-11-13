"""Pantalla «Solicitudes»: cuentas nuevas por aprobar o rechazar (con motivo), contraseñas olvidadas e historial."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QInputDialog, QLabel, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from .. import auth
from .base import QueryRunner, StateBanner

RESULTADO = {auth.ACTIVO: "Aprobada", auth.RECHAZADO: "Rechazada"}


def _tabla(encabezados: tuple[str, ...]) -> QTableWidget:
    tabla = QTableWidget(0, len(encabezados))
    tabla.setHorizontalHeaderLabels(list(encabezados))
    tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tabla.verticalHeader().hide()
    tabla.verticalHeader().setDefaultSectionSize(36)
    tabla.horizontalHeader().setStretchLastSection(True)
    return tabla


def pedir_motivo(padre: QWidget, titulo: str, pregunta: str) -> str | None:
    """Pide el motivo (obligatorio). ``None`` si se cancela o se deja vacío: entonces no se hace nada."""
    texto, ok = QInputDialog.getText(padre, titulo, pregunta)
    texto = (texto or "").strip()
    return texto if ok and texto else None


class SolicitudesView(QWidget):
    cambiaron = pyqtSignal(int)   # cuántas solicitudes esperan respuesta

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._nuevas: list[auth.Usuario] = []
        self._claves: list[auth.Usuario] = []

        ayuda = QLabel("Quien se registra (en el PC o en el celular) espera aquí: elige su rol y apruébala, o recházala "
                       "con un motivo que verá al intentar entrar. Quien olvidó su contraseña deja una nueva para aprobar.")
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)

        self.tabla_cuentas = _tabla(("Usuario", "Nombre", "Origen", "Registro"))
        self.combo_rol = QComboBox()   # se llena según el origen de la cuenta elegida (_ajustar)
        self.btn_aprobar_cuenta = QPushButton("Aprobar")
        self.btn_rechazar_cuenta = QPushButton("Rechazar…")
        self.tabla_claves = _tabla(("Usuario", "Nombre", "Rol"))
        self.btn_aprobar = QPushButton("Aprobar contraseña")
        self.btn_rechazar_clave = QPushButton("Rechazar")
        self.tabla_historial = _tabla(("Usuario", "Nombre", "Resultado", "Rol", "Motivo", "Por"))

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(10)
        raiz.addWidget(ayuda)
        raiz.addWidget(self.banner)
        rol = QLabel("Rol:")
        for titulo, tabla, widgets in (
                ("Cuentas nuevas", self.tabla_cuentas, (rol, self.combo_rol, self.btn_aprobar_cuenta, self.btn_rechazar_cuenta)),
                ("Contraseñas por aprobar", self.tabla_claves, (self.btn_aprobar, self.btn_rechazar_clave)),
                ("Historial", self.tabla_historial, ())):
            rotulo = QLabel(titulo)
            rotulo.setObjectName("seccion")
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
        self.btn_aprobar.clicked.connect(lambda: self._con(self._clave(), auth.resolver_clave, True))
        self.btn_rechazar_clave.clicked.connect(lambda: self._con(self._clave(), auth.resolver_clave, False))
        self._ajustar()

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:   # al salir no queda nada de la sesión anterior en pantalla
            self._mostrar(([], []))
        self.refresh()

    def set_conteo(self, id_conteo: str | None) -> None:
        """Las solicitudes no dependen del conteo."""

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("solicitudes", "GESTION"):
            return
        self._runner.run(_cargar, self._mostrar, self.banner.show_error, key="solicitudes")

    def pendientes(self) -> int:
        """Cuántas solicitudes esperan respuesta (para avisar en la barra)."""
        return len(self._nuevas) + len(self._claves)

    def filas_cuentas(self) -> list[tuple[str, str]]:
        return [(self.tabla_cuentas.item(f, 0).text(), self.tabla_cuentas.item(f, 1).text()) for f in range(self.tabla_cuentas.rowCount())]

    def filas_claves(self) -> list[tuple[str, str, str]]:
        return [tuple(self.tabla_claves.item(f, c).text() for c in range(3)) for f in range(self.tabla_claves.rowCount())]

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
    @staticmethod
    def _llenar(tabla: QTableWidget, filas: list[tuple[str, ...]]) -> None:
        tabla.setRowCount(len(filas))
        for f, fila in enumerate(filas):
            for c, texto in enumerate(fila):
                tabla.setItem(f, c, QTableWidgetItem(texto))
        tabla.resizeColumnsToContents()

    def _mostrar(self, datos: tuple[list[auth.Usuario], list[auth.Solicitud]]) -> None:
        usuarios, historial = datos
        self.banner.clear()
        # Se recuerda a la PERSONA elegida, no el número de fila: al refrescar puede llegar otra que se ordena antes.
        cuenta, clave = self._cuenta(), self._clave()
        self._nuevas = [u for u in usuarios if u.estado == auth.PENDIENTE]
        self._claves = [u for u in usuarios if u.estado == auth.ACTIVO and u.clave_solicitada]
        origen = {"ESCRITORIO": "PC", "MOVIL": "Celular"}
        self._llenar(self.tabla_cuentas, [(u.usuario, u.nombre, origen.get(u.origen, u.origen), f"{u.registrado:%d/%m/%Y}" if u.registrado else "")
                                          for u in self._nuevas])
        self._llenar(self.tabla_claves, [(u.usuario, u.nombre, auth.NOMBRE_ROL[u.rol]) for u in self._claves])
        self._llenar(self.tabla_historial, [
            (h.usuario, h.nombre, RESULTADO.get(h.estado, h.estado), auth.NOMBRE_ROL[h.rol] if h.rol else "",
             h.motivo or "", h.resuelto_por or "") for h in historial])
        self.tabla_cuentas.clearSelection()
        self.tabla_claves.clearSelection()
        if cuenta is not None:
            self.elegir_cuenta(cuenta.usuario)
        if clave is not None:
            self.elegir_clave(clave.usuario)
        self._ajustar()
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
        if [self.combo_rol.itemData(i) for i in range(self.combo_rol.count())] != list(roles):
            self.combo_rol.clear()   # del celular solo Operador; del PC, Administrador o Inventario
            for rol in roles:
                self.combo_rol.addItem(auth.NOMBRE_ROL[rol], rol)
            if auth.INVENTARIO in roles:
                self.combo_rol.setCurrentIndex(self.combo_rol.findData(auth.INVENTARIO))
        for boton in (self.btn_aprobar_cuenta, self.btn_rechazar_cuenta):
            boton.setEnabled(hay_cuenta)
        for boton in (self.btn_aprobar, self.btn_rechazar_clave):
            boton.setEnabled(hay_clave)

    def _con(self, usuario: auth.Usuario | None, operacion, *extra) -> None:
        if usuario is not None:
            self._runner.run(operacion, lambda _: self.refresh(), self.banner.show_error, self._sesion, usuario.usuario, *extra)

    def _aprobar(self) -> None:
        self._con(self._cuenta(), auth.aprobar, self.combo_rol.currentData())

    def _rechazar(self) -> None:
        cuenta = self._cuenta()
        if cuenta is None:
            return
        motivo = pedir_motivo(self, "Rechazar cuenta", f"¿Por qué rechazas la cuenta de {cuenta.nombre}? (lo verá al intentar entrar)")
        if motivo is not None:
            self._con(cuenta, auth.rechazar, motivo)


def _cargar() -> tuple[list[auth.Usuario], list[auth.Solicitud]]:
    """Cuentas e historial en una sola llamada fuera del hilo de la interfaz."""
    return auth.listar(), auth.historial_solicitudes()
