"""Pantalla Sincronización: errores, roles y alta de SKU desconocido (solo Administrador)."""

import pytest
from PyQt6.QtWidgets import QDialog

from app import db
from app.auth import ADMIN, INVENTARIO, PREGUNTAS, Sesion
from app.views import sync as vista_sync
from app.views.sync import SyncView
from conftest import connect, staging
from fakes import FakeRemoto

CLAVE = "conteo2026"
C = db.conteo_actual()
T0 = 1731170400000


def esperar(qtbot, condicion):
    qtbot.waitUntil(condicion, timeout=15000)


@pytest.fixture
def admin(cuentas):
    return cuentas.registrar("ana.gomez", "Ana Gómez", CLAVE, CLAVE, correo="ana@example.com",
                             pregunta=PREGUNTAS[0], respuesta="firulais")


@pytest.fixture
def error(admin, escenario):
    conn = connect()
    try:
        staging(conn, "tst-sync", 1, T0, C, "ZZ9", 7)
        db.procesar_ahora()
    finally:
        conn.close()
    return admin


def _vista(qtbot, sesion):
    v = SyncView(FakeRemoto())
    qtbot.addWidget(v)
    v.show()
    v.set_sesion(sesion)
    return v


def test_muestra_el_error_con_sku_y_motivo(qtbot, error):
    v = _vista(qtbot, error)
    esperar(qtbot, lambda: any("ZZ9" in fila for fila in v.errores()))
    fila = next(f for f in v.errores() if "ZZ9" in f)
    assert fila[2] == "ZZ9" and fila[3] == "SKU desconocido"


def test_acciones_por_rol(qtbot, error, cuentas):
    ana = error
    cuentas.registrar("luis", "Luis Ortiz", CLAVE, CLAVE, correo="luis@example.com")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    luis = cuentas.iniciar_sesion("luis", CLAVE)
    v = _vista(qtbot, ana)
    esperar(qtbot, lambda: bool(v.errores()))
    assert not v.btn_procesar.isHidden() and not v.btn_reprocesar.isHidden() and not v.btn_alta.isHidden()
    v.set_sesion(luis)
    esperar(qtbot, lambda: bool(v.errores()))
    assert not v.btn_procesar.isHidden() and not v.btn_reprocesar.isHidden()
    assert v.btn_alta.isHidden()


def test_alta_de_sku_solo_administrador(qtbot, error, monkeypatch):
    v = _vista(qtbot, error)
    esperar(qtbot, lambda: bool(v.errores()))
    v.tabla_errores.selectRow(0)
    assert v.btn_alta.isEnabled()
    monkeypatch.setattr(vista_sync.AltaSku, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(vista_sync.AltaSku, "datos", lambda self: ("ZZ9", "Producto nuevo", "Aseo"))
    v.btn_alta.click()
    # El alta corre en un worker y el reproceso en otro: hay que esperar a que la conciliación
    # incluya el SKU (no basta con que la fila de error deje de estarlo).
    esperar(qtbot, lambda: bool(db.fetch_conciliacion("ZZ9")))
    fila = db.fetch_conciliacion("ZZ9")[0]
    assert (fila.cant_sistema, fila.cant_contada) == (0.0, 7.0)


def test_reprocesar_sin_errores_no_falla(qtbot, error):
    v = _vista(qtbot, error)
    esperar(qtbot, lambda: bool(v.errores()))
    v.btn_reprocesar.click()
    esperar(qtbot, lambda: v.btn_reprocesar.isEnabled())
