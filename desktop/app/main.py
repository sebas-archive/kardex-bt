"""Ventana principal de la aplicación de escritorio (``python -m app.main``).

Acceso (sin sesión), Estado de cuenta (solo cuentas que no pueden entrar) y la aplicación con su barra lateral.
Cada sección se registra con el módulo de la matriz de permisos: solo aparece si el rol puede consultarlo. Las
barras son exactas por rol; el Perfil se abre desde el pie, no ocupa un lugar en la lista.

El conteo es continuo y único (``ACTUAL``): no hay selector de conteos ni cierre. La aplicación de escritorio no
recibe Bluetooth: lee el estado del servicio en Oracle y puede pausarlo o reanudarlo desde Sincronización.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QIcon, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import auth, configuracion, db, i18n, notificaciones, permisos, tema
from .servicio_remoto import ServicioRemoto
from .views.acceso import AccesoView
from .views.auditoria import AuditoriaView
from .views.aviso_nuevo_sku import AvisoNuevoSku, DialogoNuevoSku
from .views.base import QueryRunner, StateBanner, estilo
from .views.charts import ChartsView
from .views.configuracion import ConfiguracionView
from .views.dashboard import DashboardView
from .views.estado_cuenta import EstadoCuentaView
from .views.foto import pixmap_avatar
from .views.iconos import icono
from .views.inventario import InventarioView
from .views.notificaciones import NotificacionesView
from .views.perfil import PerfilView
from .views.respaldos import RespaldosView
from .views.roles import RolesView
from .views.solicitudes import SolicitudesView
from .views.sync import SyncView
from .views.usuarios import UsuariosView
from .views.bandeja import HojaNotificaciones, PopoverNotificaciones
from .views.isla import isla
from .views import motion_global, vigilante
from .views.widgets import Transicion

ANCHO_LATERAL, ANCHO_LATERAL_CONTRAIDA = 230, 68
ANCHO_MAXIMO_CONTENIDO = 1440
MARGEN_LATERAL = 24


def _ping() -> bool:
    with db._conexion() as conn:
        conn.cursor().execute("SELECT 1 FROM dual")
    return True


class MainWindow(QMainWindow):
    """Acceso o la aplicación: barra lateral con las secciones y, a la derecha, la página elegida."""

    refresh_requested = pyqtSignal()
    cerrando = pyqtSignal()
    sesion_cambiada = pyqtSignal(object)

    def __init__(self, auto_refresh_ms: int = 5000, sesion: auth.Sesion | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._aplicar_tema_idioma("sistema", "es")
        self.setWindowTitle(i18n.t("Gestión de inventario"))
        self.setMinimumSize(900, 600)
        self.resize(1240, 800)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._secciones: list[tuple[str, QWidget, QPushButton, str, tuple[str, ...] | None]] = []
        self._oracle_caido = False
        self._id_sync: int | None = None   # proceso «Sincronizando…» abierto en la Isla
        self._bt_antes = ""
        self._sin_leer = 0
        self._colapsada = False
        self._colapso_manual = False
        self._auto_colapsada = False
        self._registrar_vistas: Callable[[], None] | None = None
        self._firma_construida: tuple[str, str] | None = None   # (tema resuelto, idioma) con que están hechas las vistas
        # Aviso flotante «Nuevo SKU»: sondeo propio (2,8 s) y sin solapar consultas.
        self._nuevos_sku: list = []
        self._consultando_nuevos = False
        self._nuevo_sku_en_curso = False
        self._aviso_automatico = auto_refresh_ms > 0   # en las pruebas (0) no se sondea en segundo plano

        # ------------------------------------------------------------ barra lateral
        self.marca = QLabel(i18n.t("Inventario"))
        self.marca.setObjectName("marca")
        self.marca.setToolTip(i18n.t("Volver al inicio"))
        self.btn_colapsar = QPushButton()
        self.btn_colapsar.setObjectName("iconoLateral")
        self.btn_colapsar.setIcon(icono("panel"))
        self.btn_colapsar.setToolTip(i18n.t("Contraer o expandir la barra (Ctrl+B)"))
        self.btn_colapsar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_avisos = QPushButton()
        self.btn_avisos.setObjectName("iconoLateral")
        self.btn_avisos.setIcon(icono("campana"))
        self.btn_avisos.setToolTip(i18n.t("Sin notificaciones sin leer"))
        self.btn_avisos.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_avisos.hide()

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
        self.btn_cuenta = QPushButton()
        self.btn_cuenta.setObjectName("cuenta")
        self.btn_cuenta.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cuenta.setToolTip(i18n.t("Abrir mi perfil"))
        self.btn_cuenta.setMinimumHeight(48)
        self._en_cuenta = QHBoxLayout(self.btn_cuenta)
        self._en_cuenta.setContentsMargins(6, 4, 6, 4)
        self._en_cuenta.setSpacing(10)
        self._en_cuenta.addWidget(self.lbl_avatar)
        self._textos_cuenta = QWidget()
        self._textos_cuenta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._textos_cuenta.setLayout(textos)
        self._en_cuenta.addWidget(self._textos_cuenta, 1)
        self.btn_tema = QPushButton()
        self.btn_tema.setObjectName("iconoLateral")
        self.btn_tema.setIcon(icono("contraste"))
        self.btn_tema.setToolTip(i18n.t("Tema"))
        self.btn_tema.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_tema_acciones = {}
        self.btn_salir = QPushButton()
        self.btn_salir.setObjectName("iconoLateral")
        self.btn_salir.setIcon(icono("salir"))
        self.btn_salir.setToolTip(i18n.t("Cerrar sesión"))
        self.btn_salir.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pie = QFrame()
        self._pie.setObjectName("pieCuenta")
        self._en_pie = QBoxLayout(QBoxLayout.Direction.LeftToRight, self._pie)
        self._en_pie.setContentsMargins(4, 4, 4, 4)
        self._en_pie.setSpacing(2)
        self._en_pie.addWidget(self.btn_cuenta, 1)
        self._en_pie.addWidget(self.btn_tema)
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
        en_lateral = QVBoxLayout(lateral)
        en_lateral.setContentsMargins(10, 16, 10, 12)
        en_lateral.setSpacing(6)
        en_lateral.addLayout(self._cabecera)
        en_lateral.addSpacing(14)
        en_lateral.addLayout(self._nav)
        en_lateral.addStretch(1)
        en_lateral.addWidget(self._pie)

        # ------------------------------------------------------------ encabezado y páginas
        self.lbl_titulo = QLabel("")
        self.lbl_titulo.setObjectName("tituloPagina")
        self.chip_oracle = QLabel(i18n.t("Oracle: conectando…"))
        self.chip_bluetooth = QLabel(i18n.t("Bluetooth: apagado"))
        for chip in (self.chip_oracle, self.chip_bluetooth):
            chip.setObjectName("chipEstado")
            chip.setFixedHeight(24)
        self.lbl_actualizado = QLabel("")
        self.lbl_actualizado.setObjectName("subtitulo")
        self.btn_actualizar = QPushButton(i18n.t("Actualizar"))
        self.btn_actualizar.setToolTip(i18n.t("Volver a consultar (F5)"))
        fila_titulo = QHBoxLayout()
        fila_titulo.setSpacing(10)
        fila_titulo.addWidget(self.lbl_titulo)
        fila_titulo.addWidget(self.lbl_actualizado)
        fila_titulo.addStretch(1)
        fila_titulo.addWidget(self.chip_oracle)
        fila_titulo.addWidget(self.chip_bluetooth)
        fila_titulo.addWidget(self.btn_actualizar)
        encabezado = QVBoxLayout()
        encabezado.setSpacing(8)
        encabezado.addLayout(fila_titulo)
        self.banner = StateBanner()
        self.banner.retry.connect(self.comprobar_oracle)
        self.paginas = QStackedWidget()
        contenido = QWidget()
        contenido.setObjectName("contenido")
        self._centro = QWidget()
        self._centro.setObjectName("centro")
        self._en_centro = QVBoxLayout(self._centro)
        self._en_centro.setContentsMargins(MARGEN_LATERAL, 18, MARGEN_LATERAL, 18)
        self._en_centro.setSpacing(12)
        self._en_centro.addLayout(encabezado)
        self._en_centro.addWidget(self.banner)
        self._en_centro.addWidget(self.paginas, 1)
        en_contenido = QVBoxLayout(contenido)
        en_contenido.setContentsMargins(0, 0, 0, 0)
        en_contenido.addWidget(self._centro)
        self._contenido = contenido
        self._transicion = Transicion(self.paginas)

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
        isla.instalar(self)   # la Isla vive dentro de la ventana: es el único canal de avisos
        vigilante.instalar()  # estados vacíos de tablas y diálogos con el mismo acabado
        # Aviso flotante «Nuevo SKU»: overlay (no ocupa lugar en el layout) sobre el contenido, arriba a la derecha.
        self.aviso_nuevo_sku = AvisoNuevoSku(self)
        self.aviso_nuevo_sku.crear_solicitado.connect(self._crear_nuevo_sku)
        self.aviso_nuevo_sku.descartar_solicitado.connect(self._descartar_nuevo_sku)
        # Notificaciones flotantes: la campana abre el panel y «Ver todo» abre la vista extendida (sin pestaña).
        self.bandeja = PopoverNotificaciones(self)
        self.hoja_notificaciones = HojaNotificaciones(self)
        self.bandeja.ver_todo.connect(self.abrir_hoja_notificaciones)
        self.bandeja.ir_a.connect(self.ir_a)
        self.bandeja.cambiaron.connect(self.contar_notificaciones)
        self._instalar_atajos()

        self.acceso.entro.connect(self.iniciar)
        self.acceso.sin_acceso.connect(self.mostrar_estado_cuenta)
        self.estado_cuenta.volver.connect(self._volver_al_acceso)
        self.btn_salir.clicked.connect(self.cerrar_sesion)
        self.btn_tema.clicked.connect(self._menu_tema)
        self.btn_cuenta.clicked.connect(self.abrir_perfil)
        self.btn_colapsar.clicked.connect(self._alternar_manual)
        self.btn_avisos.clicked.connect(self._abrir_notificaciones)
        self.btn_actualizar.clicked.connect(self.refresh_requested.emit)
        self.refresh_requested.connect(self.comprobar_oracle)

        self._timer = QTimer(self)
        if auto_refresh_ms > 0:
            self._timer.setInterval(auto_refresh_ms)
            self._timer.timeout.connect(lambda: self.refresh_requested.emit() if self._sesion else None)
            self._timer.start()
        # Sondeo del aviso «Nuevo SKU»: solo con sesión abierta y solo si la app refresca sola (en pruebas, 0).
        self._timer_nuevos = QTimer(self)
        if self._aviso_automatico:
            self._timer_nuevos.setInterval(2800)
            self._timer_nuevos.timeout.connect(self._consultar_nuevos_sku)
        self.refresh_requested.connect(self.contar_notificaciones)
        if sesion is not None:
            self.iniciar(sesion)

    def area_contenido(self) -> QRect:
        """El área donde se muestra la sección actual (sin la barra lateral), en coordenadas de la ventana.
        Los paneles flotantes se centran aquí."""
        if not hasattr(self, "_centro") or not self._centro.isVisible():
            return self.rect()
        return QRect(self._centro.mapTo(self, QPoint(0, 0)), self._centro.size())

    def _instalar_atajos(self) -> None:
        """Atajos globales: F5 refresca, Ctrl+B contrae la barra, Ctrl+F busca y Ctrl+1..9 abren secciones."""
        QShortcut(QKeySequence("F5"), self, activated=self.refresh_requested.emit)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self._alternar_manual)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._buscar_en_vista)
        for numero in range(1, 10):
            QShortcut(QKeySequence(f"Ctrl+{numero}"), self,
                      activated=lambda n=numero: self._ir_a_numero(n))

    def _ir_a_numero(self, numero: int) -> None:
        visibles = [t for t, _v, b, _m, _r in self._secciones if b.isVisible() and not b.property("fuera")]
        if 0 < numero <= len(visibles):
            self.ir_a(visibles[numero - 1])

    def _buscar_en_vista(self) -> None:
        vista = self.paginas.currentWidget()
        if vista is None:
            return
        from PyQt6.QtWidgets import QLineEdit
        for campo in vista.findChildren(QLineEdit):
            if campo.isVisible() and campo.isEnabled():
                campo.setFocus(Qt.FocusReason.ShortcutFocusReason)
                campo.selectAll()
                return

    # ------------------------------------------------------------------ tema e idioma
    # ------------------------------------------------------------------ control de tema del pie
    ORDEN_TEMA = ("claro", "sistema", "oscuro")

    def _icono_tema(self, modo: str | None = None) -> str:
        return {"claro": "sol", "oscuro": "luna"}.get(modo or tema.modo(), "contraste")

    def _actualizar_boton_tema(self) -> None:
        modo = tema.modo()
        self.btn_tema.setIcon(icono(self._icono_tema(modo)))
        self.btn_tema.setToolTip(f"{i18n.t('Tema')}: {i18n.t(tema.NOMBRE_MODO.get(modo, modo))}")

    def _construir_menu_tema(self) -> QMenu:
        """Menú del pie con los tres modos; deja las acciones en ``_menu_tema_acciones`` (para pruebas)."""
        menu = QMenu(self)
        self._menu_tema_acciones = {}
        actual = tema.modo()
        for modo in self.ORDEN_TEMA:
            accion = menu.addAction(i18n.t(tema.NOMBRE_MODO[modo]))
            accion.setCheckable(True)
            accion.setChecked(modo == actual)
            accion.triggered.connect(lambda _marcada=False, m=modo: self._elegir_tema(m))
            self._menu_tema_acciones[modo] = accion
        return menu

    def _menu_tema(self) -> None:
        menu = self._construir_menu_tema()
        menu.exec(self.btn_tema.mapToGlobal(QPoint(0, -menu.sizeHint().height())))

    def _elegir_tema(self, modo: str) -> None:
        """Aplica el tema de inmediato y lo persiste por usuario; si falla la persistencia, solo avisa."""
        if modo not in self.ORDEN_TEMA:
            return
        self.cambiar_tema(modo)
        if self._sesion is None:
            return
        self._runner.run(auth.guardar_preferencias, lambda _v: None, self._tema_fallo,
                         self._sesion.usuario, modo, None, key="temaPie")

    def _tema_fallo(self, mensaje: str) -> None:
        self.avisar(f"{i18n.t('No se pudo guardar la preferencia.')} {mensaje}", "error")

    def _aplicar_tema_idioma(self, modo: str, idioma: str) -> None:
        i18n.set_idioma(idioma)
        tema.aplicar(QApplication.instance(), modo)

    def cambiar_tema(self, modo: str) -> None:
        """Aplica el tema de inmediato y lo recuerda en la sesión (Perfil ya lo guardó en Oracle)."""
        from dataclasses import replace

        def aplicar() -> None:
            tema.aplicar(QApplication.instance(), modo)
            if self._sesion is not None:
                self._sesion = replace(self._sesion, tema=modo)
            self.btn_colapsar.setIcon(icono("panel"))
            self.btn_salir.setIcon(icono("salir"))
            self.btn_avisos.setIcon(icono("campana_aviso" if self._sin_leer else "campana"))
            self._actualizar_boton_tema()
            self.aviso_nuevo_sku.reestilizar()
            self.update()
            QTimer.singleShot(0, self._reconstruir_vistas)

        motion_global.cruce_tema(self, aplicar)   # el tema cruza con un fundido en vez de saltar

    def esquema_del_sistema_cambio(self, *_args) -> None:
        """El SO pasó de claro a oscuro (o al revés): con «Sistema» elegido, la app lo sigue."""
        if tema.modo() == "sistema":
            self.cambiar_tema("sistema")

    def _firma_vistas(self) -> tuple[str, str]:
        return tema.resolver(tema.modo()), i18n.idioma()

    def cambiar_idioma(self, idioma: str) -> None:
        """Aplica el idioma de inmediato: vuelve a construir las vistas para que cada texto pase por ``t()``."""
        from dataclasses import replace
        i18n.set_idioma(idioma)
        if self._sesion is not None:
            self._sesion = replace(self._sesion, idioma=idioma)
        self._retraducir_cromo()
        QTimer.singleShot(0, self._reconstruir_vistas)

    def _retraducir_cromo(self) -> None:
        """Vuelve a poner en el idioma activo los textos fijos de la ventana (título, barra lateral, tooltips)."""
        self.setWindowTitle(i18n.t("Gestión de inventario"))
        self.marca.setText(i18n.t("Inventario"))
        self.marca.setToolTip(i18n.t("Volver al inicio"))
        self.btn_colapsar.setToolTip(i18n.t("Contraer o expandir la barra (Ctrl+B)"))
        self.btn_salir.setToolTip(i18n.t("Cerrar sesión"))
        self.btn_cuenta.setToolTip(i18n.t("Abrir mi perfil"))
        self.btn_actualizar.setText(i18n.t("Actualizar"))
        self.btn_actualizar.setToolTip(i18n.t("Volver a consultar (F5)"))
        self._actualizar_boton_tema()
        self.aviso_nuevo_sku.retraducir()
        if self._sesion is not None:
            self._poner_cuenta(self._sesion.nombre, i18n.t(auth.NOMBRE_ROL[self._sesion.rol]))

    def retranslate(self) -> None:
        self.cambiar_idioma(i18n.idioma())

    # ------------------------------------------------------------------ sesión
    def sesion(self) -> auth.Sesion | None:
        return self._sesion

    def iniciar(self, sesion: auth.Sesion) -> None:
        """Entra a la aplicación con esa sesión: aplica sus preferencias y muestra las secciones de su rol."""
        from dataclasses import replace

        tema_temporal, idioma_temporal = self.acceso.preferencias_temporales()
        sesion = replace(sesion, tema=tema_temporal or sesion.tema, idioma=idioma_temporal or sesion.idioma)
        self._sesion = sesion
        self.bandeja.set_sesion(sesion)
        vista_avisos = getattr(self, "_vista_avisos", None)
        if vista_avisos is not None and hasattr(vista_avisos, "set_sesion"):
            vista_avisos.set_sesion(sesion)
        self._aplicar_tema_idioma(sesion.tema, sesion.idioma)
        self._retraducir_cromo()
        if self._firma_construida is not None and self._firma_construida != self._firma_vistas():
            # Las vistas se crearon con el tema de invitado (claro) o el idioma de arranque; los colores y textos
            # que fijan al construirse (gráficas, tarjetas) ya no valen para esta cuenta.
            QTimer.singleShot(0, self._reconstruir_vistas)
        self._poner_cuenta(sesion.nombre, i18n.t(auth.NOMBRE_ROL[sesion.rol]))
        self._poner_avatar()
        self._actualizar_boton_tema()
        self.btn_avisos.setVisible(sesion.puede("notificaciones"))
        for titulo, vista, boton, modulo, roles in self._secciones:
            boton.setVisible(self._visible(sesion, modulo, roles) and not boton.property("fuera"))
            if hasattr(vista, "set_sesion"):
                vista.set_sesion(sesion)
        self._raiz.setCurrentIndex(1)
        visibles = [t for t, _v, b, _m, _r in self._secciones if b.isVisible() and not b.property("fuera")]
        if visibles:
            self.ir_a(visibles[0])
        self.sesion_cambiada.emit(sesion)
        self.comprobar_oracle()
        self.contar_notificaciones()
        if self._aviso_automatico:
            self._timer_nuevos.start()
            self._consultar_nuevos_sku()
        if sesion.aviso_clave:
            self.avisar(f"{i18n.t('Tu solicitud de contraseña fue rechazada:')} {sesion.aviso_clave}", "error")
            self._runner.run(auth.consumir_aviso_clave, lambda _: None, lambda _m: None, sesion.usuario)

    def mostrar_estado_cuenta(self, cuenta: auth.CuentaSinAcceso) -> None:
        """La cuenta no puede entrar (pendiente o rechazada): se muestra su estado, sin abrir sesión."""
        self.estado_cuenta.mostrar(cuenta)
        self._raiz.setCurrentWidget(self.estado_cuenta)

    def _volver_al_acceso(self) -> None:
        self.acceso.limpiar()
        self._raiz.setCurrentWidget(self.acceso)

    def cerrar_sesion(self) -> None:
        self._sesion = None
        self._timer_nuevos.stop()
        self._nuevos_sku = []
        self.aviso_nuevo_sku.ocultar()
        for _titulo, vista, _boton, _modulo, _roles in self._secciones:
            if hasattr(vista, "set_sesion"):
                vista.set_sesion(None)
        self.bandeja.set_sesion(None)
        self.hoja_notificaciones.cerrar()
        vista_avisos = getattr(self, "_vista_avisos", None)
        if vista_avisos is not None and hasattr(vista_avisos, "set_sesion"):
            vista_avisos.set_sesion(None)
        isla.quitar_estado("oracle")
        isla.quitar_estado("bluetooth")
        self._oracle_caido = False
        self.acceso.limpiar()
        self._raiz.setCurrentIndex(0)
        self.sesion_cambiada.emit(None)

    def _poner_avatar(self) -> None:
        if self._sesion is None:
            return
        mapa = pixmap_avatar(self._sesion.foto, 36)
        if mapa is not None:
            self.lbl_avatar.setPixmap(mapa)
            self.lbl_avatar.setText("")
        else:
            self.lbl_avatar.setPixmap(QPixmap())
            self.lbl_avatar.setText(self._sesion.nombre[:1].upper())

    def actualizar_avatar(self, ruta: str | None = None) -> None:
        from dataclasses import replace
        if self._sesion is not None:
            self._sesion = replace(self._sesion, foto=ruta)
        self._poner_avatar()

    def abrir_perfil(self) -> None:
        self.ir_a(i18n.t("Perfil"))

    def _abrir_notificaciones(self) -> None:
        """La campana: abre el panel flotante de notificaciones."""
        self.bandeja.abrir(self.btn_avisos)

    def abrir_hoja_notificaciones(self) -> None:
        """«Ver todo»: la vista extendida, flotante sobre la ventana."""
        if self._sesion is not None and self._sesion.puede("notificaciones"):
            self.hoja_notificaciones.abrir()

    def registrar_notificaciones(self, vista: QWidget) -> None:
        """La vista extendida vive en la hoja flotante: sin pestaña, pero con sesión y refresco como las demás."""
        self._vista_avisos = vista
        self.hoja_notificaciones.poner(vista)
        refrescar = getattr(vista, "refresh", None)
        if callable(refrescar):
            self.refresh_requested.connect(refrescar)
        if hasattr(vista, "set_sesion") and self._sesion is not None:
            vista.set_sesion(self._sesion)

    def _drill(self, tipo: str, valor: str) -> None:
        """Clic en una gráfica: lleva a Inventario con el filtro cuando la vista lo permite."""
        self.ir_a(i18n.t("Inventario"))
        vista = self.vista(i18n.t("Inventario"))
        if tipo in ("categoria", "categoría") and vista is not None:
            aplicar = getattr(vista, "aplicar_filtro", None)
            if callable(aplicar):
                aplicar(categoria=valor)
        elif tipo == "sku" and vista is not None:
            buscar = getattr(vista, "buscar", None)
            if callable(buscar):
                buscar(valor)
        self.avisar(f"{tipo}: {valor}", "info")

    # ------------------------------------------------------------------ secciones
    def add_view(self, view: QWidget, title: str, modulo: str, en_barra: bool = True,
                 roles: tuple[str, ...] | None = None, icono_id: str | None = None) -> QPushButton:
        """Registra una sección en la barra lateral y la incluye en el refresco."""
        boton = QPushButton("" if self._colapsada else f"  {title}")
        boton.setIcon(icono(icono_id or title))
        boton.setToolTip(title)
        boton.setObjectName("nav")
        boton.setCheckable(True)
        boton.setCursor(Qt.CursorShape.PointingHandCursor)
        boton.clicked.connect(lambda _=False, t=title: self.ir_a(t))
        self._grupo.addButton(boton)
        self._nav.addWidget(boton)
        self.paginas.addWidget(view)
        self._secciones.append((title, view, boton, modulo, roles))
        if not en_barra:
            boton.setProperty("fuera", True)
            boton.hide()
        refrescar = getattr(view, "refresh", None) or getattr(view, "refrescar", None)
        if callable(refrescar):
            self.refresh_requested.connect(refrescar)
        if self._sesion is not None:
            boton.setVisible(self._visible(self._sesion, modulo, roles) and not boton.property("fuera"))
            if hasattr(view, "set_sesion"):
                view.set_sesion(self._sesion)
        if len(self._secciones) == 1:
            boton.setChecked(True)
            self.lbl_titulo.setText(title)
        return boton

    @staticmethod
    def _visible(sesion: auth.Sesion, modulo: str, roles: tuple[str, ...] | None) -> bool:
        return sesion.puede(modulo) and (roles is None or sesion.rol in roles)

    def secciones(self) -> list[str]:
        """Las secciones que ve quien tiene la sesión abierta, en el orden de la barra lateral."""
        if self._sesion is None:
            return []
        return [titulo for titulo, _v, _b, modulo, roles in self._secciones
                if self._visible(self._sesion, modulo, roles)]

    def seccion_actual(self) -> str:
        return self.lbl_titulo.text()

    def vista(self, titulo: str) -> QWidget | None:
        return next((v for t, v, _b, _s, _r in self._secciones if t == titulo), None)

    def ir_a(self, titulo: str) -> None:
        """Abre una sección. Las que el rol no puede consultar no se abren."""
        if titulo == i18n.t("Notificaciones"):
            self.abrir_hoja_notificaciones()
            return
        if titulo not in self.secciones():
            return
        self.hoja_notificaciones.cerrar()
        indice = next(i for i, s in enumerate(self._secciones) if s[0] == titulo)
        anterior = self.paginas.currentWidget()
        if anterior is not None and self.isVisible():
            sentido = 1 if indice >= self.paginas.currentIndex() else -1
            self._transicion.lanzar(anterior.grab(), sentido)
        self.paginas.setCurrentIndex(indice)
        if anterior is not None and self.isVisible():
            QTimer.singleShot(0, lambda p=self.paginas.currentWidget(): motion_global.entrada_pagina(p))
        self._secciones[indice][2].setChecked(True)
        self.lbl_titulo.setText(titulo)
        self._cabecera_global(self._secciones[indice][1])
        self._actualizar_progreso_vista()

    # ------------------------------------------------------------------ notificaciones y avisos
    def contar_notificaciones(self) -> None:
        if self._sesion is None or not self._sesion.puede("notificaciones"):
            return
        self._runner.run(notificaciones.sin_leer, self.poner_avisos, lambda _m: None, self._sesion, key="campana")

    def poner_avisos(self, cantidad: int) -> None:
        self._sin_leer = cantidad
        self.btn_avisos.setIcon(icono("campana_aviso" if cantidad else "campana"))
        if cantidad:
            self.btn_avisos.setToolTip(i18n.t("1 notificación sin leer") if cantidad == 1
                                       else i18n.t("{n} notificaciones sin leer", n=cantidad))
        else:
            self.btn_avisos.setToolTip(i18n.t("Sin notificaciones sin leer"))

    # ------------------------------------------------------------------ aviso «Nuevo SKU»
    def _consultar_nuevos_sku(self) -> None:
        """Sondea las lecturas de SKU desconocido (NUEVO_SKU) sin solapar consultas y fuera del hilo de UI."""
        if self._sesion is None or self._consultando_nuevos:
            return
        self._consultando_nuevos = True
        self._runner.run(db.fetch_nuevos_sku, self._mostrar_nuevos_sku, self._fallo_nuevos_sku, key="nuevos-sku")

    def _mostrar_nuevos_sku(self, filas) -> None:
        self._consultando_nuevos = False
        if self._sesion is None:
            self.aviso_nuevo_sku.ocultar()
            return
        antes = {fila.id_transito for fila in self._nuevos_sku}
        self._nuevos_sku = list(filas or [])
        self.aviso_nuevo_sku.mostrar(self._nuevos_sku)
        # El backfill de ``fetch_nuevos_sku`` dejó el aviso en la campana: si el conjunto de pendientes
        # cambió, el contador sube ya, sin esperar al refresco global.
        if {fila.id_transito for fila in self._nuevos_sku} != antes:
            self.contar_notificaciones()

    def _fallo_nuevos_sku(self, _mensaje: str) -> None:
        """No se repite aquí el error de Oracle: el chip/aviso persistente ya lo informa cada 5 s."""
        self._consultando_nuevos = False

    def _crear_nuevo_sku(self, sku: str) -> None:
        """«Crear y procesar»: pide nombre y categoría y da de alta el SKU con su lectura."""
        if self._sesion is None or self._nuevo_sku_en_curso:
            return
        dialogo = DialogoNuevoSku(sku, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        sku, nombre, categoria = dialogo.datos()
        self._nuevo_sku_en_curso = True
        self.aviso_nuevo_sku.setEnabled(False)
        self._runner.run(db.nuevo_sku_alta, lambda _r: self._nuevo_sku_creado(sku),
                         self._nuevo_sku_fallo, self._sesion, sku, nombre, categoria, key="alta-nuevo-sku")

    def _nuevo_sku_creado(self, sku: str) -> None:
        self._nuevo_sku_en_curso = False
        self.aviso_nuevo_sku.setEnabled(True)
        self.aviso_nuevo_sku.olvidar(sku)
        isla.exito(i18n.t("SKU creado"), f"{sku} · {i18n.t('lectura procesada')}")
        self._refrescar_vista_actual()
        self._consultar_nuevos_sku()

    def _nuevo_sku_fallo(self, mensaje: str) -> None:
        """El aviso se queda para reintentar o descartar; el motivo va a la Isla."""
        self._nuevo_sku_en_curso = False
        self.aviso_nuevo_sku.setEnabled(True)
        isla.error(mensaje)

    def _descartar_nuevo_sku(self, sku: str) -> None:
        """«No crear»: confirma y descarta la lectura (no se cuenta)."""
        if self._sesion is None or self._nuevo_sku_en_curso:
            return
        sku = (sku or "").strip().upper()
        isla.confirmar(i18n.t("¿No tomar la lectura?"), i18n.t("El SKU {sku} no se contará.", sku=sku),
                       al_confirmar=lambda: self._ejecutar_descarte(sku), verbo=i18n.t("No crear"))

    def _ejecutar_descarte(self, sku: str) -> None:
        if self._sesion is None or self._nuevo_sku_en_curso:
            return
        self._nuevo_sku_en_curso = True
        self.aviso_nuevo_sku.setEnabled(False)
        self._runner.run(db.descartar_nuevo_sku, lambda _r: self._nuevo_sku_descartado(sku),
                         self._nuevo_sku_fallo, self._sesion, sku, key="descarte-nuevo-sku")

    def _nuevo_sku_descartado(self, sku: str) -> None:
        self._nuevo_sku_en_curso = False
        self.aviso_nuevo_sku.setEnabled(True)
        self.aviso_nuevo_sku.olvidar(sku)
        isla.info(i18n.t("Lectura descartada"), sku)
        self._refrescar_vista_actual()
        self._consultar_nuevos_sku()

    def _refrescar_vista_actual(self) -> None:
        """Tras crear o descartar, la pantalla abierta vuelve a leer sus datos (sin esperar al refresco global)."""
        vista = self.paginas.currentWidget()
        refrescar = getattr(vista, "refresh", None)
        if callable(refrescar):
            refrescar()

    def conectar_servicio(self, remoto: ServicioRemoto) -> None:
        """Refleja el estado del servicio Bluetooth en el encabezado y avisa cuando termina una sincronización."""
        remoto.status_changed.connect(self._estado_bluetooth)
        remoto.listo.connect(lambda: self._sync_listo(remoto.status()))
        self._estado_bluetooth(remoto.status())

    def tras_restaurar(self) -> None:
        self.cerrar_sesion()
        self.avisar(i18n.t("Respaldo restaurado. Reanuda el servicio Bluetooth cuando quieras."), "info")

    TIPO_ISLA = {"ok": "exito", "error": "error", "info": "info", "aviso": "advertencia", "warning": "advertencia"}

    def avisar(self, texto: str, tipo: str = "ok", duracion_ms: int | None = None) -> None:
        """Comunica algo a la persona por la Isla (arriba al centro). ``tipo``: ok, error, info o aviso."""
        getattr(isla, self.TIPO_ISLA.get(tipo, "info"))(texto, duracion_ms=duracion_ms)

    def avisos_visibles(self) -> list[str]:
        return isla.textos()

    def _sync_listo(self, status: dict) -> None:
        texto = self._texto_listo(status)
        if self._id_sync is not None:
            isla.actualizar(self._id_sync, "exito", texto)
            self._id_sync = None
        else:
            isla.exito(texto)

    @staticmethod
    def _texto_listo(status: dict) -> str:
        recibidos = status["ultima"].recibidos if status.get("ultima") is not None else 0
        if recibidos == 1:
            return i18n.t("Sincronización lista: 1 lectura recibida")
        return i18n.t("Sincronización lista: {n} lecturas recibidas", n=recibidos)

    def _poner_chip(self, chip: QLabel, texto: str, estado: str) -> None:
        chip.setText(texto)
        chip.setMinimumWidth(chip.sizeHint().width() + 4)   # el texto del chip nunca se recorta
        chip.setProperty("estado", estado)
        chip.style().unpolish(chip)
        chip.style().polish(chip)

    def _estado_bluetooth(self, status: dict) -> None:
        textos = {
            "IDLE": ("escuchando", "activo"), "ESPERANDO_EMPAREJAMIENTO": ("escuchando", "activo"),
            "CONFIRMAR_CODIGO": ("esperando el código", "activo"), "CONECTADO": ("celular conectado", "activo"),
            "RECIBIENDO": ("recibiendo", "activo"), "PROCESANDO": ("procesando", "activo"),
            "LISTO": ("listo", "ok"), "ERROR": ("error", "error"), "PAUSANDO": ("pausando", "activo"),
            "PAUSADO": ("en pausa", ""), "DETENIDO": ("servicio detenido", "error"),
        }
        estado = status["estado"]
        texto, tono = textos.get(estado, (estado.lower(), ""))
        self._poner_chip(self.chip_bluetooth, i18n.t("Bluetooth: {estado}", estado=i18n.t(texto)), tono)
        self._avisar_bluetooth(estado, status)

    def _avisar_bluetooth(self, estado: str, status: dict) -> None:
        """Bluetooth en la Isla: los estados que duran son persistentes y solo cambian cuando cambia la condición."""
        antes, self._bt_antes = self._bt_antes, estado
        if self._sesion is None:
            return
        if estado == "ERROR":
            isla.estado("bluetooth", "error", i18n.t("Error en el servicio Bluetooth"), status.get("ultimo_error") or "")
        elif estado == "DETENIDO":
            isla.estado("bluetooth", "advertencia", i18n.t("Servicio Bluetooth detenido"),
                        i18n.t("Los teléfonos no podrán enviar lecturas."))
        elif estado == "PAUSADO":
            isla.estado("bluetooth", "info", i18n.t("Servicio Bluetooth en pausa"))
        else:
            isla.quitar_estado("bluetooth")
        if estado in ("RECIBIENDO", "PROCESANDO") and self._id_sync is None:
            self._id_sync = isla.cargando(i18n.t("Sincronizando inventario"), i18n.t("Recibiendo lecturas del teléfono…"))
        elif estado == "ERROR" and self._id_sync is not None:
            isla.actualizar(self._id_sync, "error", i18n.t("Error en la sincronización"), status.get("ultimo_error") or "")
            self._id_sync = None
        if estado == "CONECTADO" and antes != "CONECTADO":
            isla.info(i18n.t("Celular conectado"), i18n.t("Listo para recibir el conteo."), clave="bt-conexion")
        elif antes in ("CONECTADO", "RECIBIENDO") and estado in ("IDLE", "ESPERANDO_EMPAREJAMIENTO"):
            isla.advertencia(i18n.t("Celular desconectado"), clave="bt-conexion")

    # ------------------------------------------------------------------ Oracle y encabezado
    def comprobar_oracle(self) -> None:
        if self._sesion is None:
            return
        self._runner.run(_ping, self._oracle_ok, self._oracle_fallo, key="oracle")

    def _oracle_ok(self, _valor) -> None:
        self._poner_chip(self.chip_oracle, i18n.t("Oracle: conectado"), "ok")
        ahora = datetime.now()
        self.lbl_actualizado.setText(i18n.t("Actualizado {hora}", hora=f"{ahora:%H:%M:%S}"))
        self.btn_actualizar.setToolTip(i18n.t("Volver a consultar (F5)"))
        self.banner.clear()
        if self._oracle_caido:
            self._oracle_caido = False
            isla.quitar_estado("oracle")
            isla.exito(i18n.t("Oracle conectado"), i18n.t("La conexión se restableció."))

    def _oracle_fallo(self, mensaje: str) -> None:
        self._poner_chip(self.chip_oracle, i18n.t("Oracle: sin conexión"), "error")
        self.banner.registrar(i18n.t("No se pudo consultar la base de datos: {mensaje}", mensaje=mensaje))
        self._oracle_caido = True
        isla.estado("oracle", "error", i18n.t("Oracle sin conexión"), mensaje)

    # ------------------------------------------------------------------ lateral
    def _alternar_manual(self) -> None:
        self._colapso_manual = True
        self._auto_colapsada = False
        self.alternar_lateral()

    TEXTO_CUENTA_MAX = 116   # ancho máximo del texto del pie; más allá se abrevia con «…»
    RESTO_PIE = 184          # lo que ocupan en el pie el avatar, los botones y los márgenes

    def _poner_cuenta(self, nombre: str, rol: str) -> None:
        """Nombre y rol en el pie: si no caben ni con el ancho máximo de la barra, se abrevian con «…» (y tooltip)."""
        for etiqueta, texto in ((self.lbl_usuario, nombre), (self.lbl_rol, rol)):
            etiqueta.ensurePolished()
            elidido = QFontMetrics(etiqueta.font()).elidedText(texto, Qt.TextElideMode.ElideRight, self.TEXTO_CUENTA_MAX)
            etiqueta.setText(elidido)
            etiqueta.setToolTip(texto if elidido != texto else "")
        self._ajustar_lateral()

    def _ancho_lateral(self) -> int:
        """El ancho que necesita la barra con la fuente real del sistema: nunca menos que el original ni más de 300."""
        ancho = ANCHO_LATERAL
        for _t, _v, boton, _m, _r in self._secciones:
            boton.ensurePolished()
            texto = QFontMetrics(boton.font()).horizontalAdvance(boton.toolTip() or boton.text().strip())
            ancho = max(ancho, texto + 12 + 3 + 20 + 12 + 20 + 16)      # relleno + borde + icono + hueco + márgenes + holgura
        for etiqueta in (self.lbl_usuario, self.lbl_rol):
            etiqueta.ensurePolished()
            ancho = max(ancho, QFontMetrics(etiqueta.font()).horizontalAdvance(etiqueta.text()) + self.RESTO_PIE)
        return min(300, ancho)

    def _ajustar_lateral(self) -> None:
        self._lateral.setFixedWidth(ANCHO_LATERAL_CONTRAIDA if self._colapsada else self._ancho_lateral())

    def alternar_lateral(self) -> None:
        self._colapsada = not self._colapsada
        c = self._colapsada
        self._aplicar_lateral(c)
        self._ajustar_lateral()
        QTimer.singleShot(0, self._centrar_contenido)

    def _aplicar_lateral(self, c: bool) -> None:
        self.marca.setVisible(not c)
        self._textos_cuenta.setVisible(not c)
        for _t, _v, boton, _m, _r in self._secciones:
            boton.setText("" if c else f"  {boton.toolTip()}")
        for marco in (self._lateral, self._pie):
            marco.setProperty("contraida", c)
            marco.style().unpolish(marco)
            marco.style().polish(marco)
        self._cabecera.setDirection(QBoxLayout.Direction.TopToBottom if c else QBoxLayout.Direction.LeftToRight)
        for boton in (self.btn_avisos, self.btn_colapsar):
            self._cabecera.setAlignment(boton, Qt.AlignmentFlag.AlignHCenter if c else Qt.AlignmentFlag.AlignRight)
        self._en_pie.setDirection(QBoxLayout.Direction.TopToBottom if c else QBoxLayout.Direction.LeftToRight)
        alineacion = Qt.AlignmentFlag.AlignHCenter if c else Qt.AlignmentFlag.AlignVCenter
        for boton in (self.btn_cuenta, self.btn_tema, self.btn_salir):
            self._en_pie.setAlignment(boton, alineacion)
        self._en_cuenta.setContentsMargins(0, 0, 0, 0) if c else self._en_cuenta.setContentsMargins(6, 4, 6, 4)
        self._en_cuenta.setSpacing(0 if c else 10)
        self.btn_cuenta.setMinimumWidth(36 if c else 0)
        self.btn_cuenta.setMaximumWidth(36 if c else 16777215)

    def lateral_contraida(self) -> bool:
        return self._colapsada

    # ------------------------------------------------------------------ reconstrucción
    def _reconstruir_vistas(self) -> None:
        """Vuelve a crear las vistas para aplicar un idioma o tema nuevo (cada texto se construye con ``t()``)."""
        if self._registrar_vistas is None:
            return
        actual = next((modulo for _t, vista, _b, modulo, _r in self._secciones
                       if vista is self.paginas.currentWidget()), None)
        for _titulo, vista, boton, _modulo, _roles in self._secciones:
            if hasattr(vista, "set_sesion"):
                vista.set_sesion(None)
            self.paginas.removeWidget(vista)
            vista.deleteLater()
            boton.deleteLater()
        self._secciones.clear()
        while self._nav.count():
            item = self._nav.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if self._registrar_vistas is not None:
            self._registrar_vistas()
        self._firma_construida = self._firma_vistas()
        self._aplicar_lateral(self._colapsada)
        self._ajustar_lateral()
        if self._sesion is not None:
            self.iniciar(self._sesion)
            titulo = next((t for t, _v, _b, modulo, _r in self._secciones if modulo == actual), None)
            if titulo is not None:
                self.ir_a(titulo)
        self._repulir_navegacion()

    def _repulir_navegacion(self) -> None:
        """Vuelve a aplicar la hoja de estilo a la barra: los botones recién creados tras un cambio de tema o idioma
        pueden quedar sin las reglas de ``#nav`` (texto centrado, iconos desalineados) hasta el siguiente repintado."""
        for _t, _v, boton, _m, _r in self._secciones:
            boton.style().unpolish(boton)
            boton.style().polish(boton)
            boton.updateGeometry()
        self._lateral.updateGeometry()
        self._lateral.update()
        QTimer.singleShot(0, self._repulir_navegacion_diferido)

    def _repulir_navegacion_diferido(self) -> None:
        for _t, _v, boton, _m, _r in self._secciones:
            boton.style().unpolish(boton)
            boton.style().polish(boton)
            boton.update()

    def _centrar_contenido(self) -> None:
        if not hasattr(self, "_centro"):
            return
        ancho = self._centro.width()
        sobra = max(0, ancho - ANCHO_MAXIMO_CONTENIDO)
        margen = MARGEN_LATERAL + sobra // 2
        self._en_centro.setContentsMargins(margen, 18, margen, 18)

    def _cabecera_global(self, vista: QWidget) -> None:
        """Las pantallas con ``cabecera_propia`` (Sincronización) dibujan su propio título, estados y «Actualizar»:
        la fila global se oculta para no repetirlos. El texto de ``lbl_titulo`` sigue siendo la sección actual."""
        self._cabecera_propia = bool(getattr(vista, "cabecera_propia", False))
        for w in (self.lbl_titulo, self.lbl_actualizado, self.chip_oracle, self.chip_bluetooth, self.btn_actualizar):
            w.setVisible(not self._cabecera_propia)
        if not self._cabecera_propia:
            self.lbl_actualizado.setVisible(self.width() >= 1000)

    def _actualizar_progreso_vista(self) -> None:
        """Sin indicador de scroll: se conserva el punto de extensión para las vistas que lo consulten."""

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        if not hasattr(self, "_raiz"):
            return
        self._centrar_contenido()
        if hasattr(self, "aviso_nuevo_sku") and self.aviso_nuevo_sku.isVisible():
            self.aviso_nuevo_sku.reubicar()
        self.lbl_actualizado.setVisible(self.width() >= 1000 and not getattr(self, "_cabecera_propia", False))   # en ventanas estrechas el encabezado prioriza lo esencial
        if not self._colapso_manual and self._raiz.currentIndex() == 1:
            if self.width() < 1060 and not self._colapsada:
                self._auto_colapsada = True
                self.alternar_lateral()
            elif self.width() > 1200 and self._colapsada and self._auto_colapsada:
                self._auto_colapsada = False
                self.alternar_lateral()
        QTimer.singleShot(0, self._centrar_contenido)
        if self.aviso_nuevo_sku.isVisible():
            QTimer.singleShot(0, self.aviso_nuevo_sku.reubicar)   # los márgenes del contenido se ajustan después

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        QTimer.singleShot(0, self._centrar_contenido)
        if self.aviso_nuevo_sku.isVisible():
            QTimer.singleShot(0, self.aviso_nuevo_sku.reubicar)

    def closeEvent(self, evento) -> None:
        self._timer.stop()
        self._timer_nuevos.stop()
        self.cerrando.emit()
        super().closeEvent(evento)


def build_window(remoto: ServicioRemoto, auto_refresh_ms: int = 5000, sesion: auth.Sesion | None = None) -> MainWindow:
    """La ventana completa; cada sección se ve según la matriz de permisos del rol."""
    ventana = MainWindow(auto_refresh_ms=auto_refresh_ms)

    def registrar() -> None:
        dashboard = DashboardView()
        inventario = InventarioView()
        graficas = ChartsView()
        sync = SyncView(remoto)
        solicitudes = SolicitudesView()
        empleados = UsuariosView()
        roles = RolesView()
        auditoria = AuditoriaView()
        configuracion_vista = ConfiguracionView()
        respaldos = RespaldosView()
        avisos = NotificacionesView()
        perfil = PerfilView()

        ventana.add_view(dashboard, i18n.t("Dashboard"), "dashboard", icono_id="Dashboard")
        ventana.add_view(inventario, i18n.t("Inventario"), "inventario", icono_id="Inventario")
        ventana.add_view(graficas, i18n.t("Gráficas"), "graficas", roles=(auth.INVENTARIO,), icono_id="Gráficas")
        ventana.add_view(solicitudes, i18n.t("Solicitudes"), "solicitudes", icono_id="Solicitudes")
        ventana.add_view(empleados, i18n.t("Empleados"), "usuarios", icono_id="Empleados")
        ventana.add_view(roles, i18n.t("Roles y permisos"), "permisos", icono_id="Roles y permisos")
        ventana.add_view(auditoria, i18n.t("Auditoría"), "auditoria", icono_id="Auditoría")
        ventana.add_view(configuracion_vista, i18n.t("Configuración"), "configuracion", icono_id="Configuración")
        ventana.add_view(sync, i18n.t("Sincronización"), "sync", icono_id="Sincronización")
        ventana.add_view(respaldos, i18n.t("Respaldos"), "respaldos", icono_id="Respaldos")
        ventana.registrar_notificaciones(avisos)   # flotante: se abre desde la campana, sin pestaña
        ventana.add_view(perfil, i18n.t("Perfil"), "perfil", en_barra=False, icono_id="Perfil")

        perfil.cerrar_sesion.connect(ventana.cerrar_sesion)
        perfil.tema_cambiado.connect(ventana.cambiar_tema)
        perfil.idioma_cambiado.connect(ventana.cambiar_idioma)
        perfil.foto_cambiada.connect(ventana.actualizar_avatar)
        if hasattr(solicitudes, "aviso"):
            solicitudes.aviso.connect(ventana.avisar)
        if hasattr(avisos, "ir_a"):
            avisos.ir_a.connect(ventana.ir_a)
        if hasattr(avisos, "cambiaron"):
            avisos.cambiaron.connect(ventana.contar_notificaciones)
        if hasattr(respaldos, "restaurado"):
            respaldos.restaurado.connect(ventana.tras_restaurar)
        if hasattr(sync, "datos_cambiados"):
            sync.datos_cambiados.connect(ventana.refresh_requested)
            sync.datos_cambiados.connect(ventana._consultar_nuevos_sku)   # llegó algo: el aviso se actualiza ya
        if hasattr(graficas, "filtro"):
            graficas.filtro.connect(ventana._drill)
        if hasattr(dashboard, "filtro"):
            dashboard.filtro.connect(ventana._drill)

    ventana._registrar_vistas = registrar
    registrar()
    ventana._firma_construida = ventana._firma_vistas()
    app = QApplication.instance()
    if app is not None:   # Qt avisa cuando el SO cambia de claro a oscuro (no en X11 sin portal)
        try:
            app.styleHints().colorSchemeChanged.connect(ventana.esquema_del_sistema_cambio)
        except AttributeError:
            pass
    ventana.conectar_servicio(remoto)
    remoto.listo.connect(ventana.refresh_requested)
    if sesion is not None:
        ventana.iniciar(sesion)
    return ventana


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Inventario BT")
    app.setDesktopFileName("inventario-bt")   # en Wayland la barra busca el icono por este nombre (.desktop del equipo)
    app.setWindowIcon(QIcon(str(Path(__file__).with_name("recursos") / "icono.svg")))
    app.setStyleSheet(estilo())
    try:                   # si Oracle aún no está listo, la ventana abre igual y muestra el error al entrar
        auth.migrar()      # columnas nuevas (correo, pregunta, foto, tema, idioma)
        permisos.migrar()  # 12 módulos y sus valores iniciales
        from btsync import esquema
        with db._conexion() as conn:
            esquema.migrar(conn)     # tablas del servicio, fotos, notificaciones y paquete del batch
        from . import auditoria
        auditoria.migrar()
        configuracion.aplicar_jobs()
    except Exception as exc:     # noqa: BLE001 — se informa en la pantalla, no se cae la aplicación
        print(f"Oracle no está listo: {exc}", file=sys.stderr)
    ventana = build_window(ServicioRemoto())
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
