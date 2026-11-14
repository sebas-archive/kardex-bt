"""Pantalla Respaldos (Fase 5)."""

import pytest
from PyQt6.QtWidgets import QDialogButtonBox

from app.auth import INVENTARIO, PREGUNTAS, Sesion
from app.main import build_window
from app.views.respaldos import DialogoRestaurar, RespaldosView
from fakes import FakeRemoto


def esperar(qtbot, condicion):
    qtbot.waitUntil(condicion, timeout=15000)


@pytest.fixture
def vista(qtbot, cuentas, respaldos_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026", correo="ana@example.com",
                            pregunta=PREGUNTAS[0], respuesta="firulais")
    respaldos_db.crear(ana)
    v = RespaldosView()
    qtbot.addWidget(v)
    v.set_sesion(ana)
    esperar(qtbot, lambda: len(v.filas()) == 1)
    return v, ana


def test_el_dialogo_pide_escribir_restaurar(qtbot):
    d = DialogoRestaurar(None, "respaldo-20261114-230000-auto.zip")
    qtbot.addWidget(d)
    aceptar = d.botones.button(QDialogButtonBox.StandardButton.Ok)
    assert not aceptar.isEnabled()
    d.txt.setText("restaurar")
    assert not aceptar.isEnabled()
    d.txt.setText("RESTAURAR")
    assert aceptar.isEnabled()


def test_lista_y_crear(qtbot, vista):
    v, _ana = vista
    assert v.filas()[0][2:] == ("Sí", "ana.gomez") or v.filas()[0][2:] == ("No", "ana.gomez")
    v.btn_crear.click()
    esperar(qtbot, lambda: len(v.filas()) == 2)


def test_hecho_por_dice_automatico_y_antes_de_restaurar(qtbot, vista):
    from app import db
    from btsync import respaldo

    v, _ana = vista
    with db._conexion() as conn:
        respaldo.crear(conn, "servicio", "auto")
        respaldo.crear(conn, "ana.gomez", "previo")
    v.refresh()
    esperar(qtbot, lambda: len(v.filas()) == 3)
    assert {f[3] for f in v.filas()} >= {"Automático", "Antes de restaurar"}


def test_restaurar_emite_restaurado(qtbot, vista, servicio_db, monkeypatch):
    v, _ana = vista
    poner, _ = servicio_db
    poner(estado="PAUSADO", pausado="S")
    monkeypatch.setattr(v, "_confirmar", lambda archivo: True)
    v.tabla.selectRow(0)
    with qtbot.waitSignal(v.restaurado, timeout=15000):
        v.btn_restaurar.click()


def test_tras_restaurar_la_ventana_vuelve_al_login_con_el_aviso(qtbot, cuentas, respaldos_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026", correo="ana@example.com",
                            pregunta=PREGUNTAS[0], respuesta="firulais")
    ventana = build_window(FakeRemoto(), auto_refresh_ms=0, sesion=ana)
    qtbot.addWidget(ventana)
    assert "Respaldos" in ventana.secciones()
    ventana.vista("Respaldos").restaurado.emit()
    assert ventana.sesion() is None
    assert any("Bluetooth" in aviso or "pausa" in aviso for aviso in ventana.avisos_visibles())
    _sin_consultas_pendientes(qtbot, ventana)


def _sin_consultas_pendientes(qtbot, ventana):
    """Que ninguna pantalla reciba resultados después de destruir la ventana (la prueba siguiente los vería)."""
    vistas = [v for _t, v, _b, _m, _r in ventana._secciones]
    esperar(qtbot, lambda: all(getattr(v, "_runner", None) is None or v._runner.pendientes == 0 for v in vistas))


def test_inventario_no_ve_respaldos(qtbot):
    ventana = build_window(FakeRemoto(), auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    ventana.iniciar(Sesion("luis", "Luis Ortiz", INVENTARIO))
    assert "Respaldos" not in ventana.secciones() and "Configuración" not in ventana.secciones()
