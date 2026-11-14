"""Pantalla «Auditoría» (Fase 4)."""

from datetime import date, timedelta

from app import db as dbq
from app.auth import ADMIN, INVENTARIO, Sesion
from app.main import build_window
from app.sync_bridge import SyncBridge
from app.views.auditoria import AuditoriaView
from fakes import FakeStore, FakeTransport

import pytest


def esperar(qtbot, condicion, timeout=15000):
    qtbot.waitUntil(condicion, timeout=timeout)


@pytest.fixture
def gente(cuentas, maestros_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    luis = cuentas.iniciar_sesion("luis", "conteo2026")
    maestros_db.crear_categoria(luis, "Tst Congelados")
    cuentas.suspender(ana, "luis", "Vacaciones")
    return ana, luis


def _vista(qtbot, sesion):
    vista = AuditoriaView()
    qtbot.addWidget(vista)
    vista.set_sesion(sesion)
    esperar(qtbot, lambda: len(vista.filas()) > 0)
    return vista


def test_admin_ve_todo_y_filtra(qtbot, gente):
    ana, _luis = gente
    vista = _vista(qtbot, ana)
    primera = vista.filas()[0]
    assert primera[1:] == ("Ana Gómez", "Usuarios", "Suspendió cuenta", "luis — «Vacaciones»")
    acciones = [f[3] for f in vista.filas()]
    assert {"Aprobó cuenta", "Inicio de sesión", "Creó categoría", "Suspendió cuenta"} <= set(acciones)
    vista.combo_modulo.setCurrentIndex(vista.combo_modulo.findData("categorias"))
    assert [f[3] for f in vista.filas()] == ["Creó categoría"]
    vista.combo_modulo.setCurrentIndex(0)
    vista.combo_usuario.setCurrentIndex(vista.combo_usuario.findData("luis"))
    assert {f[2] for f in vista.filas()} <= {"Acceso", "Categorías y almacenes"}
    vista.combo_usuario.setCurrentIndex(0)
    vista.txt_buscar.setText("congelados")
    assert [f[3] for f in vista.filas()] == ["Creó categoría"]
    vista.txt_buscar.setText("")
    vista.fecha_desde.setDate(vista.fecha_desde.date().addDays(40))     # desde el futuro: nada
    assert vista.filas() == [] and "coincide" in vista.banner.text()


def test_inventario_solo_ve_la_operacion(qtbot, cuentas, maestros_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    luis = cuentas.iniciar_sesion("luis", "conteo2026")
    maestros_db.crear_categoria(luis, "Tst Congelados")
    vista = _vista(qtbot, luis)
    assert {f[2] for f in vista.filas()} == {"Categorías y almacenes"}


def test_seccion_auditoria_segun_permisos(qtbot):
    ventana = build_window(SyncBridge(FakeTransport(), FakeStore()), auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    ventana.iniciar(Sesion("ana", "Ana", ADMIN))
    assert "Auditoría" in ventana.secciones()
    ventana.cerrar_sesion()
    ventana.iniciar(Sesion("luis", "Luis Ortiz", INVENTARIO))
    assert "Auditoría" in ventana.secciones()
    ventana.cerrar_sesion()
    ventana.iniciar(Sesion("x", "X", INVENTARIO, (("historial", "NINGUNO"), ("perfil", "GESTION"))))
    assert "Auditoría" not in ventana.secciones()
