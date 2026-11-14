"""Ventana principal de la aplicación de escritorio (``python -m app.main``)."""

from __future__ import annotations

import os
import sys
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from btsync import esquema
from btsync import tareas as tareas_bt
from btsync.store import Store
from btsync.transports.tcp import TcpTransport

from . import auditoria, auth, db, maestros, movimientos, permisos
from .models import Conteo
from .sync_bridge import SyncBridge
from .views.acceso import AccesoView
from .views.base import QueryRunner, StateBanner, estilo
from .views.charts import ChartsView
from .views.dashboard import DashboardView
from .views.estado_cuenta import EstadoCuentaView
from .views.ajustes import AjustesView
from .views.auditoria import AuditoriaView
from .views.diferencias import DiferenciasView
from .views.existencias import ExistenciasView
from .views.movimientos import MovimientosView
from .views.tareas import TareasView
from .views.iconos import icono
from .views.inventario import InventarioView
from .views.maestros import AlmacenesView, CategoriasView
from .views.perfil import PerfilView
from .views.roles import RolesView
from .views.solicitudes import SolicitudesView
from .views.sync import SyncView
from .views.usuarios import UsuariosView
from .views.widgets import Aviso, Transicion

# Texto y color del indicador de Bluetooth, según el estado del controlador.
ESTADO_BLUETOOTH = {
    "IDLE": ("apagado", ""),
    "ESPERANDO_EMPAREJAMIENTO": ("escuchando", "activo"),
    "CONFIRMAR_CODIGO": ("esperando el código", "activo"),
    "CONECTADO": ("celular conectado", "activo"),
    "RECIBIENDO": ("recibiendo", "activo"),
    "PROCESANDO": ("procesando", "activo"),
    "LISTO": ("listo", "ok"),
    "ERROR": ("error", "error"),
}


ANCHO_LATERAL, ANCHO_LATERAL_CONTRAIDA = 230, 68


class MainWindow(QMainWindow):
    """Acceso (sin sesión) o la aplicación: barra lateral con las secciones y, a la derecha, la página elegida.

    Las secciones se registran con ``add_view`` con su módulo de la matriz de permisos: solo aparecen si el rol
    de la sesión puede consultarlo (``Sesion.puede``, con los permisos leídos al entrar).
    ``refresh_requested`` pide a todas que vuelvan a consultar (el temporizador, «Actualizar», F5 y el fin de una
    sincronización lo emiten). Cada vista recibe el conteo elegido (``set_conteo``) y, si lo implementa, la sesión
    (``set_sesion``) para ajustar lo que su rol puede hacer.
    """

    refresh_requested = pyqtSignal()
    cerrando = pyqtSignal()        # la ventana se está cerrando: hay que cortar la sincronización abierta
    sesion_cambiada = pyqtSignal(object)  # auth.Sesion al entrar, None al salir

    def __init__(self, auto_refresh_ms: int = 5000, sesion: auth.Sesion | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gestión de inventario")
        self.setMinimumSize(900, 600)
        self.resize(1240, 800)
        self.setStyleSheet(estilo())
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._conteo_actual: str | None = None
        self._conteos_cargados = False
        self._secciones: list[tuple[str, QWidget, QPushButton, str]] = []  # (título, vista, botón, módulo)
        self._avisos: list[Aviso] = []
        self._indice_previo = 0

        # ------------------------------------------------------------ barra lateral
        self.marca = QLabel("Inventario")
        self.marca.setObjectName("marca")
        self.btn_colapsar = QPushButton()
        self.btn_colapsar.setObjectName("iconoLateral")
        self.btn_colapsar.setIcon(icono("panel"))
        self.btn_colapsar.setToolTip("Contraer o expandir la barra (Ctrl+B)")
        self.btn_colapsar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_avisos = QPushButton()
        self.btn_avisos.setObjectName("iconoLateral")
        self.btn_avisos.setIcon(icono("campana"))
        self.btn_avisos.setToolTip("Sin solicitudes por revisar")
        self.btn_avisos.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_avisos.hide()                   # solo el administrador recibe avisos
        self._nav = QVBoxLayout()
        self._nav.setSpacing(2)
        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self.lbl_avatar = QLabel("")
        self.lbl_avatar.setObjectName("avatar")
        self.lbl_avatar.setFixedSize(36, 36)
        self.lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_usuario = QLabel("")
        self.lbl_usuario.setObjectName("usuarioNombre")
        self.lbl_rol = QLabel("")
        self.lbl_rol.setObjectName("usuarioRol")
        textos = QVBoxLayout()
        textos.setSpacing(0)
        textos.addWidget(self.lbl_usuario)
        textos.addWidget(self.lbl_rol)
        self.btn_cuenta = QPushButton()          # foto + nombre: abre el perfil
        self.btn_cuenta.setObjectName("cuenta")
        self.btn_cuenta.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cuenta.setToolTip("Abrir mi perfil")
        self.btn_cuenta.setMinimumHeight(48)
        en_cuenta = QHBoxLayout(self.btn_cuenta)
        en_cuenta.setContentsMargins(6, 4, 6, 4)
        en_cuenta.setSpacing(10)
        en_cuenta.addWidget(self.lbl_avatar)
        self._textos_cuenta = QWidget()
        self._textos_cuenta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._textos_cuenta.setLayout(textos)
        en_cuenta.addWidget(self._textos_cuenta, 1)
        self.btn_salir = QPushButton()
        self.btn_salir.setObjectName("iconoLateral")
        self.btn_salir.setIcon(icono("salir"))
        self.btn_salir.setToolTip("Cerrar sesión")
        self.btn_salir.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pie = QFrame()
        self._pie.setObjectName("pieCuenta")
        self._en_pie = QBoxLayout(QBoxLayout.Direction.LeftToRight, self._pie)
        self._en_pie.setContentsMargins(4, 4, 4, 4)
        self._en_pie.setSpacing(2)
        self._en_pie.addWidget(self.btn_cuenta, 1)
        self._en_pie.addWidget(self.btn_salir)
        lateral = QFrame()
        lateral.setObjectName("lateral")
        self._lateral = lateral
        lateral.setFixedWidth(ANCHO_LATERAL)
        self._cabecera = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._cabecera.setSpacing(2)
        self._cabecera.addWidget(self.marca, 1)
        self._cabecera.addWidget(self.btn_avisos)
        self._cabecera.addWidget(self.btn_colapsar)
        cabecera = self._cabecera
        en_lateral = QVBoxLayout(lateral)
        en_lateral.setContentsMargins(10, 16, 10, 12)
        en_lateral.setSpacing(6)
        en_lateral.addLayout(cabecera)
        en_lateral.addSpacing(14)
        en_lateral.addLayout(self._nav)
        en_lateral.addStretch(1)
        en_lateral.addWidget(self._pie)
        self._colapsada = False

        # ------------------------------------------------------------ encabezado y páginas
        self.lbl_titulo = QLabel("")
        self.lbl_titulo.setObjectName("tituloPagina")
        self.combo_conteo = QComboBox()
        self.combo_conteo.setMinimumWidth(280)
        self.combo_conteo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)  # no cortar nombres largos
        self.chip_oracle = QLabel("Oracle: conectando…")
        self.chip_bluetooth = QLabel("Bluetooth: apagado")
        for chip in (self.chip_oracle, self.chip_bluetooth):
            chip.setObjectName("chipEstado")
            chip.setFixedHeight(24)
        self.lbl_actualizado = QLabel("")
        self.lbl_actualizado.setObjectName("subtitulo")
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_actualizar.setToolTip("Volver a consultar (F5)")
        encabezado = QHBoxLayout()
        encabezado.setSpacing(10)
        encabezado.addWidget(self.lbl_titulo)
        encabezado.addStretch(1)
        encabezado.addWidget(self.chip_oracle)
        encabezado.addWidget(self.chip_bluetooth)
        encabezado.addWidget(self.combo_conteo)
        encabezado.addWidget(self.btn_actualizar)
        self.banner = StateBanner()
        self.banner.retry.connect(self._cargar_conteos)
        self.paginas = QStackedWidget()
        contenido = QWidget()
        contenido.setObjectName("contenido")
        en_contenido = QVBoxLayout(contenido)
        en_contenido.setContentsMargins(24, 18, 24, 18)
        en_contenido.setSpacing(12)
        en_contenido.addLayout(encabezado)
        en_contenido.addWidget(self.banner)
        en_contenido.addWidget(self.paginas, 1)
        self._transicion = Transicion(self.paginas)

        # Marco exterior continuo (#161616): la barra se funde con él y el contenido queda encajado en un lienzo
        # redondeado. Margen arriba, derecha y abajo; a la izquierda ninguno (la barra toca el borde).
        lienzo = QFrame()
        lienzo.setObjectName("lienzo")
        en_lienzo = QVBoxLayout(lienzo)
        en_lienzo.setContentsMargins(0, 0, 0, 0)
        en_lienzo.addWidget(contenido)
        aplicacion = QWidget()
        aplicacion.setObjectName("marco")
        en_aplicacion = QHBoxLayout(aplicacion)
        en_aplicacion.setContentsMargins(0, 10, 10, 10)
        en_aplicacion.setSpacing(0)
        en_aplicacion.addWidget(lateral)
        en_aplicacion.addWidget(lienzo, 1)

        # ------------------------------------------------------------ acceso | aplicación
        self.acceso = AccesoView()
        self.estado_cuenta = EstadoCuentaView()
        self._raiz = QStackedWidget()
        self._raiz.addWidget(self.acceso)
        self._raiz.addWidget(aplicacion)
        self._raiz.addWidget(self.estado_cuenta)
        self.setCentralWidget(self._raiz)

        self.acceso.entro.connect(self.iniciar)
        self.acceso.sin_acceso.connect(self.mostrar_estado_cuenta)
        self.estado_cuenta.volver.connect(self._volver_al_acceso)
        self.btn_salir.clicked.connect(self.cerrar_sesion)
        self.btn_cuenta.clicked.connect(lambda: self.ir_a("Perfil"))
        self.btn_colapsar.clicked.connect(self.alternar_lateral)
        self.btn_avisos.clicked.connect(lambda: self.ir_a("Solicitudes"))
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self.alternar_lateral)
        self.combo_conteo.currentIndexChanged.connect(self._conteo_cambiado)
        self.btn_actualizar.clicked.connect(lambda: self.refresh_requested.emit())
        QShortcut(QKeySequence("F5"), self, activated=lambda: self.refresh_requested.emit())
        self.refresh_requested.connect(self._cargar_conteos)

        self._timer = QTimer(self)
        if auto_refresh_ms > 0:
            self._timer.setInterval(auto_refresh_ms)
            self._timer.timeout.connect(lambda: self.refresh_requested.emit() if self._sesion else None)
            self._timer.start()
        if sesion is not None:
            self.iniciar(sesion)

    # ------------------------------------------------------------------ sesión
    def sesion(self) -> auth.Sesion | None:
        return self._sesion

    def iniciar(self, sesion: auth.Sesion) -> None:
        """Entra a la aplicación con esa sesión: muestra las secciones de su rol y carga los datos."""
        self._sesion = sesion
        self.lbl_usuario.setText(sesion.nombre)
        self.lbl_avatar.setText(sesion.nombre[:1].upper())
        self.btn_avisos.setVisible(sesion.puede("solicitudes", "GESTION"))
        self.lbl_rol.setText(auth.NOMBRE_ROL[sesion.rol])
        for _titulo, vista, boton, modulo in self._secciones:
            boton.setVisible(not boton.property("fuera") and sesion.puede(modulo))
            if hasattr(vista, "set_sesion"):
                vista.set_sesion(sesion)
        self._raiz.setCurrentIndex(1)
        visibles = [t for t in self.secciones() if not next(b for tt, _v, b, _m in self._secciones if tt == t).property("fuera")]
        if visibles:   # la primera que su rol puede ver (el Dashboard puede estar en «Sin acceso»)
            self.ir_a(visibles[0])
        self.sesion_cambiada.emit(sesion)
        self._cargar_conteos()

    def mostrar_estado_cuenta(self, cuenta: auth.CuentaSinAcceso) -> None:
        """La cuenta no puede entrar (pendiente, rechazada o suspendida): se muestra su estado, sin abrir sesión."""
        self.estado_cuenta.mostrar(cuenta)
        self._raiz.setCurrentWidget(self.estado_cuenta)

    def _volver_al_acceso(self) -> None:
        self.acceso.limpiar()
        self._raiz.setCurrentWidget(self.acceso)

    def cerrar_sesion(self) -> None:
        self._sesion = None
        for _titulo, vista, _boton, _modulo in self._secciones:
            if hasattr(vista, "set_sesion"):
                vista.set_sesion(None)
        self.acceso.limpiar()
        self._raiz.setCurrentIndex(0)
        self.sesion_cambiada.emit(None)

    def alternar_lateral(self) -> None:
        """Contrae la barra a solo iconos o la expande con los nombres."""
        self._colapsada = not self._colapsada
        c = self._colapsada
        self._lateral.setFixedWidth(ANCHO_LATERAL_CONTRAIDA if c else ANCHO_LATERAL)
        self.marca.setVisible(not c)
        self._textos_cuenta.setVisible(not c)
        for _t, _v, boton, _s in self._secciones:
            boton.setText("" if c else f"  {boton.toolTip()}")
        for marco in (self._lateral, self._pie):
            marco.setProperty("contraida", c)
        # Contraída todo se apila y se centra; expandida, el título a la izquierda y los botones a la derecha.
        self._cabecera.setDirection(QBoxLayout.Direction.TopToBottom if c else QBoxLayout.Direction.LeftToRight)
        for boton in (self.btn_avisos, self.btn_colapsar):
            self._cabecera.setAlignment(boton, Qt.AlignmentFlag.AlignHCenter if c else Qt.AlignmentFlag.AlignRight)
        self._en_pie.setDirection(QBoxLayout.Direction.TopToBottom if c else QBoxLayout.Direction.LeftToRight)
        self._en_pie.setAlignment(self.btn_cuenta, Qt.AlignmentFlag.AlignHCenter if c else Qt.AlignmentFlag.AlignVCenter)
        self.btn_cuenta.setMinimumWidth(48 if c else 0)
        self.btn_cuenta.setMaximumWidth(48 if c else 16777215)
        for marco in (self._lateral, self._pie):
            marco.style().unpolish(marco)
            marco.style().polish(marco)

    def poner_avisos(self, cantidad: int) -> None:
        """La campana avisa cuántas solicitudes (cuentas o contraseñas) espera el administrador."""
        self.btn_avisos.setIcon(icono("campana_aviso" if cantidad else "campana"))
        self.btn_avisos.setToolTip(f"{cantidad} solicitud{'es' if cantidad != 1 else ''} por revisar" if cantidad else "Sin solicitudes por revisar")

    def lateral_contraida(self) -> bool:
        return self._colapsada

    # ------------------------------------------------------------------ secciones
    def add_view(self, view: QWidget, title: str, modulo: str, en_barra: bool = True) -> None:
        """Registra una sección en la barra lateral y la incluye en el refresco."""
        boton = QPushButton(f"  {title}")
        boton.setIcon(icono(title))
        boton.setToolTip(title)
        boton.setObjectName("nav")
        boton.setCheckable(True)
        boton.setCursor(Qt.CursorShape.PointingHandCursor)
        boton.clicked.connect(lambda _=False, t=title: self.ir_a(t))
        self._grupo.addButton(boton)
        self._nav.addWidget(boton)
        self.paginas.addWidget(view)
        self._secciones.append((title, view, boton, modulo))
        if not en_barra:
            boton.setProperty("fuera", True)  # el perfil se abre desde el pie, no desde la lista
            boton.hide()
        self.refresh_requested.connect(view.refresh)
        if self._sesion is not None:
            boton.setVisible(en_barra and self._sesion.puede(modulo))
            if hasattr(view, "set_sesion"):
                view.set_sesion(self._sesion)
        if self._conteos_cargados:
            view.set_conteo(self._conteo_actual)
        if len(self._secciones) == 1:
            boton.setChecked(True)
            self.lbl_titulo.setText(title)

    def secciones(self) -> list[str]:
        """Las secciones que ve quien tiene la sesión abierta, en el orden de la barra lateral."""
        if self._sesion is None:
            return []
        return [titulo for titulo, _v, _b, modulo in self._secciones if self._sesion.puede(modulo)]

    def seccion_actual(self) -> str:
        return self.lbl_titulo.text()

    def vista(self, titulo: str) -> QWidget:
        return next(v for t, v, _b, _s in self._secciones if t == titulo)

    def ir_a(self, titulo: str) -> None:
        """Abre una sección. Las que el rol no puede consultar no se abren."""
        if titulo not in self.secciones():
            return
        indice = next(i for i, s in enumerate(self._secciones) if s[0] == titulo)
        anterior = self.paginas.currentWidget()
        if anterior is not None and indice != self._indice_previo and self.isVisible():
            self._transicion.lanzar(anterior.grab(), 1 if indice > self._indice_previo else -1)
        self._indice_previo = indice
        self.paginas.setCurrentIndex(indice)
        self._secciones[indice][2].setChecked(True)
        self.lbl_titulo.setText(titulo)
        # El conteo solo importa en las páginas que muestran datos de un conteo.
        self.combo_conteo.setVisible(titulo in ("Dashboard", "Inventario", "Gráficas"))

    # ------------------------------------------------------------------ conteo, estado y avisos
    def select_conteo(self, id_conteo: str) -> None:
        indice = self.combo_conteo.findData(id_conteo)
        if indice >= 0:
            self.combo_conteo.setCurrentIndex(indice)

    def conteo_actual(self) -> str | None:
        return self._conteo_actual

    def conectar_puente(self, bridge: SyncBridge) -> None:
        """Refleja el estado del Bluetooth en el encabezado y avisa cuando termina una sincronización."""
        bridge.status_changed.connect(self._estado_bluetooth)
        bridge.listo.connect(lambda: self.avisar(self._texto_listo(bridge.status()["recibidos"])))
        self._estado_bluetooth(bridge.status())

    def avisar(self, texto: str, tipo: str = "ok") -> None:
        """Muestra un aviso flotante que sube desde la esquina inferior derecha y se va solo."""
        self._avisos = [a for a in self._avisos if self._vivo(a)]
        aviso = Aviso(texto, tipo, self)
        ocupados = sum(a.height() + 10 for a in self._avisos)
        aviso.mostrar(self.height() - aviso.height() - 24 - ocupados)
        self._avisos.append(aviso)

    def avisos_visibles(self) -> list[str]:
        return [a.texto for a in self._avisos if self._vivo(a)]

    # ------------------------------------------------------------- internos
    @staticmethod
    def _vivo(aviso: Aviso) -> bool:
        try:
            return not aviso.isHidden()
        except RuntimeError:  # Qt ya lo destruyó al cerrarse
            return False

    @staticmethod
    def _texto_listo(recibidos: int) -> str:
        return f"Sincronización lista: {recibidos} {'lectura recibida' if recibidos == 1 else 'lecturas recibidas'}"

    def _poner_chip(self, chip: QLabel, texto: str, estado: str) -> None:
        chip.setText(texto)
        chip.setProperty("estado", estado)
        chip.style().unpolish(chip)
        chip.style().polish(chip)

    def _estado_bluetooth(self, status: dict) -> None:
        texto, estado = ESTADO_BLUETOOTH.get(status["estado"], (status["estado"].lower(), ""))
        self._poner_chip(self.chip_bluetooth, f"Bluetooth: {texto}", estado)

    def _cargar_conteos(self) -> None:
        if self._sesion is None:
            return  # sin sesión no se consulta nada
        if not self._conteos_cargados:
            self.banner.show_loading()
        self._runner.run(db.fetch_conteos, self._conteos_listos, self._conteos_fallo, key="conteos")

    def _conteos_fallo(self, mensaje: str) -> None:
        self._poner_chip(self.chip_oracle, "Oracle: sin conexión", "error")
        self.banner.show_error(mensaje)

    def _conteos_listos(self, conteos: list[Conteo]) -> None:
        self._conteos_cargados = True
        self._poner_chip(self.chip_oracle, "Oracle: conectado", "ok")
        self.lbl_actualizado.setText(f"Actualizado {datetime.now():%H:%M:%S}")
        self.btn_actualizar.setToolTip(f"Volver a consultar (F5) · actualizado {datetime.now():%H:%M:%S}")
        previo = self._conteo_actual
        if not conteos:
            self.banner.show_empty("Sin datos")
            self.combo_conteo.blockSignals(True)
            self.combo_conteo.clear()
            self.combo_conteo.blockSignals(False)
            self._aplicar_conteo(None)
            return
        self.banner.clear()
        elegido = previo if any(c.id_conteo == previo for c in conteos) else next(
            (c.id_conteo for c in conteos if c.estado == "ABIERTO"), conteos[0].id_conteo)
        self.combo_conteo.blockSignals(True)
        self.combo_conteo.clear()
        for c in conteos:
            self.combo_conteo.addItem(f"{c.id_conteo} — {c.nombre}", c.id_conteo)
        self.combo_conteo.setCurrentIndex(self.combo_conteo.findData(elegido))
        self.combo_conteo.blockSignals(False)
        if elegido != previo:
            self._aplicar_conteo(elegido)

    def _conteo_cambiado(self, indice: int) -> None:
        self._aplicar_conteo(self.combo_conteo.itemData(indice))

    def _aplicar_conteo(self, id_conteo: str | None) -> None:
        self._conteo_actual = id_conteo
        for _titulo, vista, _boton, _modulo in self._secciones:
            vista.set_conteo(id_conteo)

    def closeEvent(self, evento) -> None:
        self._timer.stop()
        self.cerrando.emit()
        super().closeEvent(evento)


def build_window(bridge: SyncBridge, auto_refresh_ms: int = 5000, sesion: auth.Sesion | None = None) -> MainWindow:
    """La ventana completa; cada sección se ve según la matriz de permisos del rol (entre paréntesis, su módulo)."""
    ventana = MainWindow(auto_refresh_ms=auto_refresh_ms)
    dashboard, sync, perfil = DashboardView(), SyncView(bridge), PerfilView()
    ventana.add_view(dashboard, "Dashboard", "dashboard")
    ventana.add_view(InventarioView(), "Inventario", "conteos")          # conciliación de los conteos
    ventana.add_view(TareasView(), "Tareas de conteo", "tareas")
    ventana.add_view(DiferenciasView(), "Diferencias", "diferencias")
    ventana.add_view(MovimientosView(), "Movimientos", "movimientos")
    ventana.add_view(AjustesView(), "Ajustes", "ajustes")
    ventana.add_view(AuditoriaView(), "Auditoría", "historial")
    ventana.add_view(ExistenciasView(), "Existencias", "existencias")
    ventana.add_view(CategoriasView(), "Categorías", "categorias")
    ventana.add_view(AlmacenesView(), "Almacenes", "categorias")
    ventana.add_view(sync, "Sincronización", "bluetooth")
    ventana.add_view(ChartsView(), "Gráficas", "reportes")
    solicitudes = SolicitudesView()
    solicitudes.cambiaron.connect(ventana.poner_avisos)
    ventana.add_view(solicitudes, "Solicitudes", "solicitudes")
    ventana.add_view(UsuariosView(), "Empleados", "usuarios")
    ventana.add_view(RolesView(), "Roles y permisos", "permisos")
    ventana.add_view(perfil, "Perfil", "perfil", en_barra=False)
    ventana.conectar_puente(bridge)
    bridge.listo.connect(ventana.refresh_requested)                       # llegaron datos nuevos
    dashboard.conteo_cerrado.connect(lambda _: ventana.refresh_requested.emit())
    dashboard.conteo_cerrado.connect(lambda id_conteo: ventana.avisar(f"Conteo {id_conteo} cerrado", "info"))
    sync.datos_cambiados.connect(ventana.refresh_requested)
    perfil.cerrar_sesion.connect(ventana.cerrar_sesion)
    ventana.sesion_cambiada.connect(lambda s: bridge.cancel() if s is None else None)  # al salir se cierra la recepción
    ventana.cerrando.connect(bridge.cancel)
    if sesion is not None:
        ventana.iniciar(sesion)
    return ventana


def crear_transporte():
    """``BT_TRANSPORT=bluez`` (por defecto: Bluetooth real) o ``tcp`` (pruebas y demo de respaldo)."""
    modo = os.environ.get("BT_TRANSPORT", "bluez").lower()
    if modo == "tcp":
        return TcpTransport(os.environ.get("BT_TCP_HOST", "127.0.0.1"), int(os.environ.get("BT_TCP_PORT", "9000")))
    if modo == "bluez":
        from btsync.transports.bluez import BluezTransport

        return BluezTransport(require_pairing=os.environ.get("BT_CON_CLAVE") == "1")
    raise SystemExit(f"BT_TRANSPORT inválido: {modo!r} (usa «bluez» o «tcp»)")


def main() -> int:
    app = QApplication(sys.argv)
    store = Store(os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"])
    auth.migrar()      # estados de cuenta y rol OPERADOR en bases creadas antes de existir
    permisos.migrar()  # tabla de la matriz y sus valores iniciales
    maestros.migrar()  # categorías, almacenes y existencias (Fase 2)
    with db._conexion() as conn:
        esquema.migrar(conn)     # dañados, tabla fotos y paquete PL/SQL al día (Fase 4)
        tareas_bt.migrar(conn)   # columnas de tarea en conteos y la tabla revisiones (Fase 3)
    movimientos.migrar()         # entradas, salidas y ajustes (Fase 3b)
    auditoria.migrar()           # quién hizo qué y cuándo (Fase 4)
    puente = SyncBridge(crear_transporte(), store)
    ventana = build_window(puente)
    app.aboutToQuit.connect(puente.cancel)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
