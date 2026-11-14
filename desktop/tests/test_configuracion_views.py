"""Pantalla Configuración (Fase 5)."""

import pytest
from PyQt6.QtWidgets import QLineEdit

from app.auth import INVENTARIO
from app.views.configuracion import ConfiguracionView
from btsync.store import fotos_dir


def esperar(qtbot, condicion):
    qtbot.waitUntil(condicion, timeout=15000)


@pytest.fixture
def vista(qtbot, cuentas, config_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    v = ConfiguracionView()
    qtbot.addWidget(v)
    v.set_sesion(ana)
    v.refresh()
    esperar(qtbot, lambda: v.campo("ajustes.umbral_pct").text() == "10")
    return v, ana


def test_muestra_los_valores_y_la_carpeta_de_fotos_sin_editar(vista):
    v, _ana = vista
    assert v.campo("staging.purga_dias").text() == "7" and v.campo("fotos.max_mb").text() == "2"
    carpeta = v.findChild(QLineEdit, "carpetaFotos")
    assert carpeta.isReadOnly() and carpeta.text() == str(fotos_dir())


def test_guardar_y_error_de_rango(qtbot, vista, config_db):
    v, _ana = vista
    v.campo("lote.intervalo_s").setText("5")
    v.btn_guardar.click()
    esperar(qtbot, lambda: "entre 10 y 3600" in v.banner_texto())
    assert config_db.valores()["lote.intervalo_s"] == "60"
    v.campo("lote.intervalo_s").setText("45")
    v.btn_guardar.click()
    esperar(qtbot, lambda: config_db.valores()["lote.intervalo_s"] == "45")
