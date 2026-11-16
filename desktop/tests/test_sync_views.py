"""Pantalla Sincronización: errores reales, SKU nuevos (que ya no son error) y roles.

Un SKU que no está en el catálogo queda en ``NUEVO_SKU`` y se decide en el aviso flotante de la ventana; por eso
la tabla de errores solo muestra errores de verdad y el panel tiene el chip «Nuevos SKU».
"""

import pytest

from app import db
from app.auth import ADMIN, INVENTARIO, PREGUNTAS
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
    """Una lectura con un error real (cantidad inválida), ya procesada por el batch."""
    conn = connect()
    try:
        staging(conn, "tst-sync", 1, T0, C, "A1", "abc")
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
    esperar(qtbot, lambda: any("A1" in fila for fila in v.errores()))
    fila = next(f for f in v.errores() if "A1" in f)
    assert fila[2] == "A1" and fila[3] == "Cantidad inválida"


def test_acciones_por_rol(qtbot, error, cuentas):
    ana = error
    cuentas.registrar("luis", "Luis Ortiz", CLAVE, CLAVE, correo="luis@example.com")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    luis = cuentas.iniciar_sesion("luis", CLAVE)
    v = _vista(qtbot, ana)
    esperar(qtbot, lambda: bool(v.errores()))
    assert not v.btn_procesar.isHidden() and not v.btn_reprocesar.isHidden()
    v.set_sesion(luis)
    esperar(qtbot, lambda: bool(v.errores()))
    assert not v.btn_procesar.isHidden() and not v.btn_reprocesar.isHidden()


def test_un_sku_nuevo_no_aparece_como_error_y_suma_al_chip(qtbot, admin, escenario):
    """El SKU desconocido queda en NUEVO_SKU: ni tabla de errores ni contador de errores; sí chip «Nuevos SKU»."""
    antes = db.fetch_estado_batch()
    conn = connect()
    try:
        staging(conn, "tst-sync-nuevo", 1, T0, C, "zz9", 7)
        db.procesar_ahora()
    finally:
        conn.close()
    v = _vista(qtbot, admin)
    esperar(qtbot, lambda: v._batch is not None and v._batch.nuevos >= antes.nuevos + 1)
    assert v._batch.errores == antes.errores
    assert all(f[2].upper() != "ZZ9" for f in v.errores())    # SKU desconocido: nunca en la tabla de errores
    assert v.chip_nuevos.texto() == f"Nuevos SKU: {v._batch.nuevos}"
    assert "aviso flotante" in v.lbl_nuevos.text()


def test_reprocesar_sin_errores_no_falla(qtbot, admin, monkeypatch):
    """Con la tabla sin errores el botón se rehabilita; el reproceso se sustituye para no tocar la BD viva."""
    llamadas = []
    monkeypatch.setattr(db, "reprocesar_errores", lambda: llamadas.append("reproceso"))
    v = _vista(qtbot, admin)
    esperar(qtbot, lambda: v._batch is not None)
    v.btn_reprocesar.click()
    esperar(qtbot, lambda: v.btn_reprocesar.isEnabled())
    assert llamadas == ["reproceso"]
