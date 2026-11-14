"""Pantalla Configuración: intervalo del lote, tamaño de foto y carpeta de fotos de solo lectura."""

import pytest
from PyQt6.QtWidgets import QLineEdit

from app.auth import PREGUNTAS
from app.views.configuracion import ConfiguracionView

CLAVE = "conteo2026"


def esperar(qtbot, condicion):
    qtbot.waitUntil(condicion, timeout=15000)


@pytest.fixture
def vista(qtbot, cuentas, config_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", CLAVE, CLAVE, correo="ana@example.com",
                            pregunta=PREGUNTAS[0], respuesta="firulais")
    v = ConfiguracionView()
    qtbot.addWidget(v)
    v.set_sesion(ana)
    v.refresh()
    esperar(qtbot, lambda: v.campo("lote.intervalo_min").text() == "1")
    return v, ana


def test_muestra_los_valores_y_la_carpeta_de_fotos_sin_editar(vista):
    v, _ana = vista
    assert v.campo("fotos.max_mb").text() == "2"
    carpeta = v.findChild(QLineEdit, "carpetaFotos")
    assert carpeta.isReadOnly() and carpeta.text()


def test_guardar_y_error_de_rango(qtbot, vista, config_db):
    v, _ana = vista
    v.campo("lote.intervalo_min").setText("99")
    v.btn_guardar.click()
    esperar(qtbot, lambda: "entre 1 y 60" in v.banner_texto())
    assert config_db.valores()["lote.intervalo_min"] == "1"
    v.campo("lote.intervalo_min").setText("5")
    v.btn_guardar.click()
    esperar(qtbot, lambda: config_db.valores()["lote.intervalo_min"] == "5")
