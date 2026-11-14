"""Pantalla Gráficas: seis gráficas, filtros por categoría y cantidad, y guardado PNG."""

import pytest

from app.auth import PREGUNTAS
from app.views.charts import CHART_IDS, EXTRA_IDS, ChartsView

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
    v = ChartsView()
    qtbot.addWidget(v)
    v.set_sesion(ana)
    esperar(qtbot, lambda: bool(v.bar_data("avance")))
    return v, ana


def test_seis_graficas_y_sus_datos(vista):
    v, _ana = vista
    assert set(CHART_IDS) == {"avance", "top", "danados", "batch"}
    assert set(EXTRA_IDS) == {"dona", "hora"}
    assert len(v.plots) == 5 and v.dona is not None
    assert dict(v.bar_data("top"))["Abarrotes"] == 3.0
    assert sum(valor for _c, valor in v.serie("dona")) == 65.0
    assert v.serie("hora") and v.serie("hora")[0][1] == 5.0
    assert v.bar_data("batch")[-1][1] == 5.0


def test_filtros_categoria_y_cantidad(qtbot, vista):
    v, _ana = vista
    v.combo_categoria.setCurrentText("Aseo")
    esperar(qtbot, lambda: dict(v.bar_data("top")) == {"Aseo": 1.0})
    v.combo_categoria.setCurrentText("Todas")
    v.combo_top.setCurrentIndex(0)          # 3 categorías
    esperar(qtbot, lambda: len(v.bar_data("top")) <= 3)


def test_guardar_png(vista, tmp_path):
    v, _ana = vista
    ruta = tmp_path / "graficas.png"
    assert v.guardar_imagen(ruta) and ruta.exists() and ruta.stat().st_size > 0
