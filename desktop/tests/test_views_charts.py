"""Gráficas y Perfil de datos, con el escenario fijo T-01.

Valores esperados: dif. por categoría Abarrotes -3000, Aseo 9000, Lácteos 2800; desvíos A3 9000,
A2 -5000, A5 2800, A1 2000 (A4 sin valor); distribución OK 1, FALTANTE 1, SOBRANTE 2, SIN_CONTAR 1;
zona Z1 100 %, Z2 0 %; actividad Ana 3, Luis 2.
"""

import threading

import pyqtgraph as pg
import pytest

from app import db as dbq
from app.models import fmt_pct
from app.models import fmt_cop
from app.views.charts import CHART_IDS, ChartsView, _etiqueta_eje, _fmt_corto
from app.views.perfil import PerfilView
from conftest import staging, connect

C = "T-01"
T0 = 1731170400000


def esperar(qtbot, condicion, timeout=15000):
    qtbot.waitUntil(condicion, timeout=timeout)


@pytest.fixture
def contado(escenario):
    escenario.cargar_lecturas()
    dbq.procesar_ahora()
    return escenario


@pytest.fixture
def graficas(qtbot, contado):
    vista = ChartsView()
    qtbot.addWidget(vista)
    vista.set_conteo(C)
    esperar(qtbot, lambda: vista.bar_data("categoria") != [])
    esperar(qtbot, lambda: all(vista.bar_data(c) for c in CHART_IDS))
    return vista


@pytest.fixture
def perfil(qtbot, contado):
    vista = PerfilView()
    qtbot.addWidget(vista)
    vista.set_conteo(C)
    esperar(qtbot, lambda: vista.estadisticas().get("Lecturas procesadas", "—") != "—")
    return vista


def test_bar_data_categoria(graficas):
    assert graficas.bar_data("categoria") == [("Abarrotes", -3000.0), ("Aseo", 9000.0), ("Lácteos", 2800.0)]


def test_bar_data_desvios_order(graficas):
    # A4 (SIN_CONTAR) no tiene valor: no se dibuja.
    assert graficas.bar_data("desvios") == [("A3", 9000.0), ("A2", -5000.0), ("A5", 2800.0), ("A1", 2000.0)]


def test_bar_data_distribucion(graficas):
    assert graficas.bar_data("distribucion") == [
        ("OK", 1.0), ("FALTANTE", 1.0), ("SOBRANTE", 2.0), ("SIN_CONTAR", 1.0)]


def test_bar_data_zona(graficas):
    zonas = dict(graficas.bar_data("zona"))
    assert zonas["Z1"] == 100.0 and zonas["Z2"] == 0.0  # las zonas A, B y C de la semilla también aparecen


def test_bar_data_actividad(graficas):
    assert graficas.bar_data("actividad") == [("Ana", 3.0), ("Luis", 2.0)]


def test_charts_draw_one_bar_per_datum(graficas):
    for chart_id in CHART_IDS:
        barras = [i for i in graficas.plots[chart_id].getPlotItem().items if isinstance(i, pg.BarGraphItem)]
        assert len(barras) == 1, chart_id
        assert len(barras[0].opts["x"]) == len(graficas.bar_data(chart_id)), chart_id
    assert graficas.plots["categoria"].getPlotItem().titleLabel.text.startswith("Diferencia por categoría")


def test_perfil_lists_four_classifications_and_category_tolerances(perfil):
    reglas = perfil.clasificaciones()
    assert list(reglas) == ["OK", "FALTANTE", "SOBRANTE", "SIN_CONTAR"]
    assert "tolerancia" in reglas["OK"].lower()
    assert "cierra" in reglas["SIN_CONTAR"].lower() and "faltante" in reglas["SIN_CONTAR"].lower()
    tolerancias = perfil.tolerancias()
    assert set(tolerancias) >= {"Abarrotes", "Aseo", "Bebidas", "Ferretería", "Lácteos"}
    assert "2 %" in tolerancias["Abarrotes"]            # A1 (y la semilla) toleran 2 %
    assert tolerancias["Ferretería"] == "0,5 %"         # la semilla: todos los SKU igual
    assert tolerancias["Lácteos"] in ("0 %", "0–0 %") or tolerancias["Lácteos"].startswith("0")
    assert "campos" in perfil.titulos_de_seccion()[0].lower()
    assert any(f[0] == "Valor" for f in perfil.campos())


def test_perfil_shows_error_rate_and_operator_counts(qtbot, contado):
    conn = connect()
    try:
        staging(conn, "tst-d1", 1, T0, C, "U1", "ZZ9", 1)     # SKU sin alta: ERROR
        dbq.procesar_ahora()
    finally:
        conn.close()
    vista = PerfilView()
    qtbot.addWidget(vista)
    vista.set_conteo(C)
    esperar(qtbot, lambda: vista.estadisticas().get("Filas con error", "—") != "—")
    est = vista.estadisticas()
    assert est["Lecturas procesadas"] == "5 (5 vigentes, 0 reemplazadas)"
    assert est["Por operador"] == "Ana 3 · Luis 2"
    assert est["Por dispositivo"] == "tst-escenario 5"
    assert est["Filas con error"] == f"1 de 6 ({fmt_pct(100 / 6)})"      # 1 de 6 = 16,7 %
    assert est["Fechas capturadas"] == "2024-11-09 16:40:00 → 2024-11-09 16:40:04 (UTC)"


@pytest.mark.parametrize("fabrica", [ChartsView, PerfilView])
def test_views_show_sin_datos_when_empty(qtbot, contado, fabrica):
    vista = fabrica()
    qtbot.addWidget(vista)
    vista.set_conteo(None)
    assert vista.banner.text() == "Sin datos" and not vista.banner.isHidden()
    vista.set_conteo("NO-EXISTE")                     # un conteo sin conciliación: sin datos, sin caerse
    esperar(qtbot, lambda: vista.banner.text() == "Sin datos")


@pytest.mark.parametrize("fabrica, funcion", [(ChartsView, "fetch_dif_por_categoria"), (PerfilView, "fetch_perfil")])
def test_views_show_error_banner_and_retry(qtbot, contado, monkeypatch, fabrica, funcion):
    original = getattr(dbq, funcion)
    estado = {"falla": True}

    def inestable(*args, **kwargs):
        if estado["falla"]:
            raise RuntimeError("ORA-12541: TNS:no listener")
        return original(*args, **kwargs)

    monkeypatch.setattr(dbq, funcion, inestable)
    vista = fabrica()
    qtbot.addWidget(vista)
    vista.set_conteo(C)
    esperar(qtbot, lambda: not vista.banner.isHidden() and "ORA-12541" in vista.banner.text())
    assert not vista.banner.btn_reintentar.isHidden()
    estado["falla"] = False
    vista.banner.btn_reintentar.click()
    esperar(qtbot, lambda: vista.banner.isHidden())


def test_no_query_runs_on_the_ui_thread(qtbot, contado, monkeypatch):
    hilos = {}
    nombres = ("fetch_dif_por_categoria", "fetch_top_desvios", "fetch_distribucion", "fetch_avance_zona",
               "fetch_actividad", "fetch_perfil", "fetch_tolerancias")
    for nombre in nombres:
        original = getattr(dbq, nombre)

        def envoltura(*a, _o=original, _n=nombre, **k):
            hilos.setdefault(_n, set()).add(threading.current_thread())
            return _o(*a, **k)

        monkeypatch.setattr(dbq, nombre, envoltura)
    graficas, perfil = ChartsView(), PerfilView()
    qtbot.addWidget(graficas)
    qtbot.addWidget(perfil)
    graficas.set_conteo(C)
    perfil.set_conteo(C)
    esperar(qtbot, lambda: all(graficas.bar_data(c) for c in CHART_IDS))
    esperar(qtbot, lambda: perfil.estadisticas().get("Lecturas procesadas", "—") != "—")
    assert set(hilos) == set(nombres)
    for nombre, conjunto in hilos.items():
        assert threading.main_thread() not in conjunto, f"{nombre} corrió en el hilo de la UI"


def test_short_formats_for_crowded_labels():
    assert _fmt_corto(1029000) == "$ 1,0 M" and _fmt_corto(-155800) == "-$ 156 mil"
    assert _fmt_corto(9000) == "$ 9.000" and _fmt_corto(-5000) == "-$ 5.000"
    assert _etiqueta_eje("7701234000037") == "…0037" and _etiqueta_eje("A3") == "A3"


def test_crowded_chart_abbreviates_labels_and_skips_tiny_bars(qtbot):
    """Con 10 SKU de 13 dígitos las etiquetas se encimaban (visto con los datos reales del conteo)."""
    vista = ChartsView()
    qtbot.addWidget(vista)
    datos = [("7701234000037", 1029000.0), ("7701234000036", 155800.0), ("7701234000049", -109200.0)]
    datos += [(f"770123400{i:04d}", 20000.0 + i) for i in range(7)]
    vista._dibujar("desvios", datos, fmt_cop)
    textos = [i.textItem.toPlainText() for i in vista.plots["desvios"].getPlotItem().items
              if isinstance(i, pg.TextItem)]
    assert len(textos) == 3                                  # las 7 barras diminutas no llevan etiqueta
    assert all(("mil" in t) or t.endswith(" M") for t in textos), textos
    ticks = vista.plots["desvios"].getAxis("bottom")._tickLevels[0]
    assert [t[1] for t in ticks][:3] == ["…0037", "…0036", "…0049"]
