"""Pantalla «Auditoría»: solo consulta; la ve el Administrador y Inventario no."""

from app.auth import ADMIN, INVENTARIO, PREGUNTAS, Sesion
from app.main import build_window
from app.views.auditoria import AuditoriaView
from fakes import FakeRemoto

CLAVE = "conteo2026"


def esperar(qtbot, condicion, timeout=15000):
    qtbot.waitUntil(condicion, timeout=timeout)


def _admin(cuentas):
    return cuentas.registrar("ana.gomez", "Ana Gómez", CLAVE, CLAVE, correo="ana@example.com",
                             pregunta=PREGUNTAS[0], respuesta="firulais")


def _vista(qtbot, sesion):
    vista = AuditoriaView()
    qtbot.addWidget(vista)
    vista.set_sesion(sesion)
    esperar(qtbot, lambda: len(vista.filas()) > 0)
    return vista


def test_admin_ve_y_filtra(qtbot, cuentas):
    ana = _admin(cuentas)
    cuentas.iniciar_sesion("ana.gomez", CLAVE)          # deja la acción «Inicio de sesión» en la auditoría
    cuentas.registrar("luis", "Luis Ortiz", CLAVE, CLAVE, correo="luis@example.com")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    cuentas.suspender(ana, "luis", "Vacaciones")
    vista = _vista(qtbot, ana)
    primera = vista.filas()[0]
    assert primera[1:] == ("Ana Gómez", "Usuarios", "Suspendió cuenta", "luis — «Vacaciones»")
    acciones = [f[3] for f in vista.filas()]
    assert {"Aprobó cuenta", "Inicio de sesión", "Suspendió cuenta"} <= set(acciones)
    vista.combo_modulo.setCurrentIndex(vista.combo_modulo.findData("usuarios"))
    assert [f[3] for f in vista.filas()][0] == "Suspendió cuenta"
    vista.combo_modulo.setCurrentIndex(0)
    vista.combo_usuario.setCurrentIndex(vista.combo_usuario.findData("luis"))
    assert {f[2] for f in vista.filas()} <= {"Acceso", "Usuarios"}
    vista.combo_usuario.setCurrentIndex(0)
    vista.txt_buscar.setText("vacaciones")
    assert [f[3] for f in vista.filas()] == ["Suspendió cuenta"]
    vista.txt_buscar.setText("")
    vista.fecha_desde.setDate(vista.fecha_desde.date().addDays(40))     # desde el futuro: nada
    assert vista.filas() == [] and "coincide" in vista.banner.text()


def test_inventario_no_ve_la_pantalla(qtbot, cuentas):
    ana = _admin(cuentas)
    cuentas.registrar("luis", "Luis Ortiz", CLAVE, CLAVE, correo="luis@example.com")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    ventana = build_window(FakeRemoto(), auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    ventana.iniciar(Sesion("ana.gomez", "Ana Gómez", ADMIN))
    assert "Auditoría" in ventana.secciones()
    ventana.cerrar_sesion()
    ventana.iniciar(cuentas.iniciar_sesion("luis", CLAVE))
    assert "Auditoría" not in ventana.secciones()
