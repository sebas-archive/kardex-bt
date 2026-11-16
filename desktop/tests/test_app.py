"""La aplicación de escritorio: acceso, barras exactas, permisos, tema/idioma, perfil y empleados."""

from datetime import datetime

import pytest
from PyQt6.QtWidgets import QLineEdit

from app import auth, i18n, tema
from app.auth import ADMIN, INVENTARIO, OPERADOR, Sesion
from app.main import MainWindow, build_window
from app.views.acceso import AccesoView
from app.views.perfil import PerfilView
from app.views.solicitudes import SolicitudesView
from app.views.usuarios import UsuariosView
from fakes import FakeRemoto

ANA = Sesion("ana.gomez", "Ana Gómez", ADMIN, correo="ana@example.com")
LUIS = Sesion("luis", "Luis Ortiz", INVENTARIO, correo="luis@example.com")


@pytest.fixture
def puente():
    return FakeRemoto()


def abrir(qtbot, puente, sesion):
    """La ventana completa con la sesión dada; sin consultar Oracle para las pruebas de navegación."""
    ventana = build_window(puente, auto_refresh_ms=0)
    ventana.comprobar_oracle = lambda: None
    ventana.contar_notificaciones = lambda: None
    qtbot.addWidget(ventana)
    ventana.show()
    ventana.iniciar(sesion)
    return ventana


def test_without_session_the_window_shows_only_the_login(qtbot, puente):
    ventana = build_window(puente, auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    ventana.show()
    assert ventana.sesion() is None and ventana.acceso.isVisible()
    assert not ventana.paginas.isVisible()
    assert ventana.secciones() == []


def test_admin_sidebar_exact_order_and_profile_at_the_footer(qtbot, puente):
    ventana = abrir(qtbot, puente, ANA)
    assert ventana.secciones() == ["Dashboard", "Inventario", "Solicitudes", "Empleados", "Roles y permisos",
                                   "Auditoría", "Configuración", "Sincronización", "Respaldos", "Notificaciones",
                                   "Perfil"]
    # Perfil no está en la lista: se abre desde el pie.
    visible = [titulo for titulo, _v, boton, _m, _r in ventana._secciones
               if boton.isVisible() and not boton.property("fuera")]
    assert visible == ["Dashboard", "Inventario", "Solicitudes", "Empleados", "Roles y permisos",
                       "Auditoría", "Configuración", "Sincronización", "Respaldos", "Notificaciones"]
    assert not ventana.btn_avisos.isHidden()
    ventana.btn_cuenta.click()
    assert ventana.seccion_actual() == "Perfil"


def test_inventory_sidebar_exact_order(qtbot, puente):
    ventana = abrir(qtbot, puente, LUIS)
    assert ventana.secciones() == ["Dashboard", "Inventario", "Gráficas", "Sincronización", "Notificaciones", "Perfil"]
    visible = [titulo for titulo, _v, boton, _m, _r in ventana._secciones
               if boton.isVisible() and not boton.property("fuera")]
    assert visible == ["Dashboard", "Inventario", "Gráficas", "Sincronización", "Notificaciones"]
    ventana.ir_a("Solicitudes")
    assert ventana.seccion_actual() == "Dashboard"
    assert not ventana.btn_avisos.isHidden()


def test_no_removed_screens_are_registered(qtbot, puente):
    ventana = abrir(qtbot, puente, ANA)
    for retirada in ("Tareas", "Tareas de conteo", "Diferencias", "Movimientos", "Ajustes", "Existencias",
                     "Categorías", "Almacenes"):
        assert retirada not in ventana.secciones()
        assert ventana.vista(retirada) is None


def test_profile_footer_shows_initial_and_photo_editor(qtbot, puente):
    ventana = abrir(qtbot, puente, ANA)
    perfil = ventana.vista("Perfil")
    assert isinstance(perfil, PerfilView)
    assert ventana.lbl_avatar.text() == "A"
    assert not perfil.btn_foto.isHidden() and not perfil.btn_quitar_foto.isHidden()
    assert perfil.combo_tema.count() == 3 and perfil.combo_idioma.count() == 2
    assert perfil.btn_cambiar.text() == "Cambiar contraseña"


def test_inventory_profile_requests_the_password_change(qtbot, puente):
    ventana = abrir(qtbot, puente, LUIS)
    perfil = ventana.vista("Perfil")
    assert perfil.btn_cambiar.text() == "Solicitar cambio de contraseña"
    assert "Solicitudes" in perfil.lbl_clave_ayuda.text()


def test_theme_and_language_apply_and_persist_in_the_session(qtbot, puente):
    ventana = abrir(qtbot, puente, ANA)
    ventana.cambiar_tema("claro")
    assert tema.modo() == "claro"
    ventana.cambiar_idioma("en")
    assert i18n.idioma() == "en"
    qtbot.wait(100)
    assert "Inventory" in ventana.secciones()
    assert ventana.lbl_titulo.text() in ("Dashboard", "Inventory")
    ventana.cambiar_idioma("es")
    ventana.cambiar_tema("sistema")
    assert i18n.idioma() == "es"


def test_logout_returns_to_access_and_clears_the_session(qtbot, puente):
    ventana = abrir(qtbot, puente, ANA)
    ventana.cerrar_sesion()
    assert ventana.sesion() is None and ventana.acceso.isVisible()
    assert ventana.secciones() == []


def test_access_has_email_and_show_password(qtbot):
    vista = AccesoView()
    qtbot.addWidget(vista)
    vista.show()
    assert vista.txt_correo.placeholderText() == "Correo electrónico"
    assert vista.txt_clave.echoMode() == QLineEdit.EchoMode.Password
    vista._accion_ojo.trigger()
    assert vista.txt_clave.echoMode() == QLineEdit.EchoMode.Normal
    vista._accion_ojo.trigger()
    assert vista.txt_clave.echoMode() == QLineEdit.EchoMode.Password
    assert vista.combo_pregunta.count() == len(auth.PREGUNTAS) + 1


def test_users_table_shows_avatar_email_name_role_and_badge(qtbot, monkeypatch):
    vista = UsuariosView()
    qtbot.addWidget(vista)
    vista._sesion = ANA
    usuarios = [
        auth.Usuario("ana.gomez", "Ana Gómez", ADMIN, auth.ACTIVO, None, "ESCRITORIO", False, datetime.now(), False,
                     "ana@example.com", None),
        auth.Usuario("luis", "Luis Ortiz", INVENTARIO, auth.SUSPENDIDO, "No trabaja aquí", "ESCRITORIO", False,
                     datetime.now(), False, "luis@example.com", "perfiles/luis.jpg"),
        auth.Usuario("op1", "Operaria Uno", OPERADOR, auth.ACTIVO, None, "MOVIL", False, datetime.now(), True,
                     None, None),
    ]
    monkeypatch.setattr(auth, "listar", lambda: usuarios)
    vista._mostrar(usuarios)
    assert vista.tabla.rowCount() == 3
    assert [f[0] for f in vista.filas()] == ["ana@example.com", "luis@example.com", "—"]
    assert vista.filas()[1][1] == "Luis Ortiz" and vista.filas()[1][3] == "Suspendida"
    vista.seleccionar("ana.gomez")
    vista._ajustar_botones()
    assert not vista.btn_estado.isEnabled()          # el Administrador no se suspende
    assert not vista.btn_clave.isHidden()            # su contraseña sí se puede restablecer (cuenta PC)
    vista.seleccionar("op1")
    vista._ajustar_botones()
    assert not vista.btn_estado.isHidden() and vista.btn_estado.isEnabled()
    assert vista.btn_estado.text() == "Suspender"
    assert vista.btn_clave.isHidden() and not vista.btn_telefono.isHidden()


def test_requests_only_allow_inventory_for_pc_and_operator_for_mobile(qtbot, monkeypatch):
    vista = SolicitudesView()
    qtbot.addWidget(vista)
    vista._sesion = ANA
    cuentas = [auth.Usuario("luis", "Luis", None, auth.PENDIENTE, None, "ESCRITORIO", False, datetime.now(), False,
                            "luis@example.com"),
               auth.Usuario("op1", "Operaria", None, auth.PENDIENTE, None, "MOVIL", False, datetime.now(), False, None)]
    monkeypatch.setattr("app.views.solicitudes.auth.listar", lambda: cuentas)
    monkeypatch.setattr("app.views.solicitudes.auth.historial_solicitudes", lambda: [])
    vista._mostrar((cuentas, []))
    assert vista.pendientes() == 2
    vista.elegir_cuenta("luis")
    assert [vista.combo_rol.itemData(i) for i in range(vista.combo_rol.count())] == [INVENTARIO]
    vista.elegir_cuenta("op1")
    assert [vista.combo_rol.itemData(i) for i in range(vista.combo_rol.count())] == [OPERADOR]
    # No hay forma de aprobar un ADMIN desde la interfaz.
    assert ADMIN not in [vista.combo_rol.itemData(i) for i in range(vista.combo_rol.count())]


def test_window_title_and_oracle_chip(qtbot, puente):
    ventana = abrir(qtbot, puente, ANA)
    assert ventana.windowTitle() == "Gestión de inventario"
    ventana._oracle_ok(True)
    assert ventana.chip_oracle.text() == "Oracle: conectado"
    ventana._oracle_fallo("ORA-12541")
    assert ventana.chip_oracle.text() == "Oracle: sin conexión"
    assert "ORA-12541" in ventana.banner.text()


def _tema_db(usuario: str) -> str:
    from app import auth as auth_mod, db
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT tema FROM {auth_mod.TABLA} WHERE usuario = :u", u=usuario)
        return cur.fetchone()[0]


def test_collapsed_footer_centers_avatar_theme_and_logout(qtbot, puente):
    ventana = abrir(qtbot, puente, ANA)
    qtbot.wait(50)
    ventana.btn_colapsar.click()
    qtbot.wait(50)
    assert ventana.lateral_contraida()
    pie = ventana._pie
    for boton in (ventana.btn_cuenta, ventana.btn_tema, ventana.btn_salir):
        assert not boton.isHidden()
        centro = boton.mapTo(pie, boton.rect().center()).x()
        assert abs(centro - pie.width() / 2) <= 2, (boton.objectName(), centro, pie.width())
    assert ventana._en_cuenta.contentsMargins().left() == 0
    ventana.btn_colapsar.click()
    qtbot.wait(50)
    assert ventana._en_cuenta.contentsMargins().left() == 6


def test_footer_theme_menu_applies_and_persists_per_user(qtbot, puente, cuentas):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026", "ana@example.com",
                            auth.PREGUNTAS[0], "Firulais")
    ventana = abrir(qtbot, puente, ana)
    ventana._construir_menu_tema()
    assert set(ventana._menu_tema_acciones) == {"claro", "sistema", "oscuro"}
    assert ventana._menu_tema_acciones["sistema"].isChecked()
    ventana._elegir_tema("claro")
    assert tema.modo() == "claro"
    assert "Claro" in ventana.btn_tema.toolTip()
    qtbot.waitUntil(lambda: _tema_db(ana.usuario) == "claro", timeout=5000)
    ventana._construir_menu_tema()
    assert ventana._menu_tema_acciones["claro"].isChecked()
    assert not ventana._menu_tema_acciones["sistema"].isChecked()
    ventana._elegir_tema("oscuro")
    assert tema.modo() == "oscuro"
    assert "Oscuro" in ventana.btn_tema.toolTip()
    qtbot.waitUntil(lambda: _tema_db(ana.usuario) == "oscuro", timeout=5000)


def test_access_two_panel_card_and_strength_meter(qtbot):
    vista = AccesoView()
    qtbot.addWidget(vista)
    vista.show()
    assert vista._tarjeta.objectName() == "tarjetaAcceso"
    assert vista._marca_panel.isVisible() and vista._panel_form.isVisible()
    assert vista.chk_recordar.text() == "Recordar usuario"
    assert not hasattr(vista, "btn_ir_a_registro_pie")   # no se repite la llamada en el pie
    vista.resize(1920, 1011)
    qtbot.wait(30)
    assert vista._marca_panel.isVisible() and vista._marca_panel.width() >= 300
    vista.txt_clave_nueva.setText("ClaveSegura#2026")
    assert vista.medidor.puntaje == 4
    assert "Fuerte" in vista.medidor.etiqueta()
    assert vista.medidor.lbl_aviso.isHidden()
    vista.txt_clave_nueva.setText("Password1234")
    assert vista.medidor.puntaje == 1
    assert not vista.medidor.lbl_aviso.isHidden()
    assert "patrón" in vista.medidor.lbl_aviso.text().lower()
    vista.txt_clave_nueva.setText("")
    assert vista.medidor.puntaje == 0 and "Vacía" in vista.medidor.etiqueta()


def test_access_remembers_the_username(qtbot):
    from PyQt6.QtCore import QSettings
    ajustes = QSettings("GestionInventario", "Acceso")
    ajustes.clear()
    vista = AccesoView()
    qtbot.addWidget(vista)
    vista.txt_usuario.setText("ana.gomez")
    vista.chk_recordar.setChecked(True)
    vista._guardar_recordado()
    otra = AccesoView()
    qtbot.addWidget(otra)
    assert otra.txt_usuario.text() == "ana.gomez" and otra.chk_recordar.isChecked()
    ajustes.clear()
