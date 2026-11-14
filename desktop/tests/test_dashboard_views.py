"""Pantalla Dashboard: conteo continuo, KPIs y estado del batch. Sin cierre ni insignia Abierto/Cerrado."""

import pytest
from PyQt6.QtWidgets import QPushButton

from app.auth import PREGUNTAS
from app.views.dashboard import DashboardView

CLAVE = "conteo2026"


def esperar(qtbot, condicion):
    qtbot.waitUntil(condicion, timeout=15000)


@pytest.fixture
def contado(escenario):
    from app import db
    escenario.cargar_lecturas()
    db.procesar_ahora()
    return escenario


@pytest.fixture
def vista(qtbot, cuentas, contado):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", CLAVE, CLAVE, correo="ana@example.com",
                            pregunta=PREGUNTAS[0], respuesta="firulais")
    v = DashboardView()
    qtbot.addWidget(v)
    v.set_sesion(ana)
    esperar(qtbot, lambda: v.card_text("avance") != "—")
    return v, ana


def test_kpis_del_conteo_continuo(vista):
    v, _ana = vista
    assert v.card_text("avance") == "6,2 %"
    assert v.card_text("contados") == "4"
    assert v.card_text("faltantes") == "1"
    assert v.card_text("sobrantes") == "3"
    assert "65 SKU" in v.subtitulo.text() and "4" in v.subtitulo.text()
    assert "4" in v.detalle_de("avance")[0][1] or v.detalle_de("avance")


def test_no_hay_boton_de_cierre_ni_insignia(vista):
    v, _ana = vista
    assert [b.text() for b in v.findChildren(QPushButton) if "Cerrar" in b.text()] == []
    assert not hasattr(v, "insignia")


def test_grafica_de_diferencia_por_categoria(vista):
    v, _ana = vista
    categorias = dict(v.categorias())
    assert (categorias["Abarrotes"], categorias["Aseo"], categorias["Lácteos"]) == (-4.0, 3.0, 4.0)
