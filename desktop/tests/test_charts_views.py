"""Pantalla Gráficas: seis gráficas, filtros por categoría y cantidad, y guardado PNG."""

import pytest

from app.auth import PREGUNTAS
from app.views.charts import CHART_IDS, EXTRA_IDS, ChartsView

CLAVE = "conteo2026"


def esperar(qtbot, condicion):
    qtbot.waitUntil(condicion, timeout=15000)


@pytest.fixture(autouse=True)
def disposicion_limpia():
    """Lo que cada persona eligió en Gráficas se guarda en QSettings: cada prueba empieza sin nada."""
    from app import graficas_prefs
    ajustes = graficas_prefs._ajustes()
    ajustes.remove("graficas")
    yield
    ajustes.remove("graficas")


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
    assert len(v.plots) == 10 and v.dona is not None and v.anillo is not None and v.dona_buenas is not None
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


# ------------------------------------------------------------------ gráficas como widgets (personalizables)
SEIS = ["avance", "dona", "hora", "top", "danados", "batch"]


def test_por_defecto_las_seis_en_dos_columnas(vista):
    v, _ana = vista
    assert v.rejilla.ids() == SEIS and v.items() == [(c, "M") for c in SEIS]
    assert not v.en_edicion() and v.btn_personalizar.isVisibleTo(v) and not v.barra_edicion.isVisibleTo(v)


def test_personalizar_muestra_la_barra_y_listo_la_oculta(vista):
    v, _ana = vista
    v.btn_personalizar.click()
    assert v.en_edicion() and v.barra_edicion.isVisibleTo(v) and not v.btn_personalizar.isVisibleTo(v)
    v.btn_listo.click()
    assert not v.en_edicion() and not v.barra_edicion.isVisibleTo(v)


def test_quitar_una_grafica_la_saca_de_la_rejilla_y_los_datos_siguen_llegando(qtbot, vista):
    v, _ana = vista
    v.quitar_grafica("avance")
    assert v.rejilla.ids() == SEIS[1:]
    v.refresh()   # la gráfica quitada no se destruye: sus datos se siguen cargando sin error
    esperar(qtbot, lambda: bool(v.bar_data("avance")))
    v.agregar_grafica("avance")
    assert v.rejilla.ids() == SEIS[1:] + ["avance"]
    assert v.bar_data("avance")


def test_no_se_puede_repetir_ni_inventar_una_grafica(vista):
    v, _ana = vista
    assert not v.agregar_grafica("avance") and not v.agregar_grafica("no_existe")
    assert v.rejilla.ids() == SEIS


def test_quitar_todas_muestra_el_aviso_y_deshabilita_nada_mas_que_lo_justo(vista):
    v, _ana = vista
    for c in SEIS:
        v.quitar_grafica(c)
    assert v.rejilla.ids() == [] and v.vacio.isVisibleTo(v) and v.btn_agregar.isEnabled()
    v.agregar_grafica("hora")
    assert not v.vacio.isVisibleTo(v) and v.rejilla.ids() == ["hora"]


def test_con_todas_puestas_no_hay_nada_que_agregar(vista):
    from app import graficas_prefs as gp
    v, _ana = vista
    assert v.btn_agregar.isEnabled()        # las siete nuevas están por añadir
    for c in gp.EXTRAS:
        assert v.agregar_grafica(c)
    assert v.rejilla.ids() == SEIS + list(gp.EXTRAS) and not v.btn_agregar.isEnabled()
    v.quitar_grafica("top")
    assert v.btn_agregar.isEnabled()


def test_graficas_nuevas_y_sus_datos(qtbot, vista):
    from app import graficas_prefs as gp
    v, _ana = vista
    for c in gp.EXTRAS:
        v.agregar_grafica(c)
    v.refresh()
    esperar(qtbot, lambda: bool(v.bar_data("operadores")))
    assert dict(v.bar_data("operadores")) == {"Ana": 3.0, "Luis": 2.0}
    assert sum(x for _e, x in v.bar_data("dia")) == 5.0
    assert sum(x for _e, x in v.bar_data("skus")) == 5.0
    assert v.serie("acumulado")[-1][1] == 5.0
    assert v.anillo.valor() is not None and 0 <= v.anillo.valor() <= 100
    assert dict(v.serie("buenas")).keys() == {"buenas", "danadas"}


def test_tamano_y_orden_se_recuerdan_por_usuario(qtbot, vista, cuentas):
    v, ana = vista
    v.cambiar_tam("hora", "L")
    v.quitar_grafica("dona")
    v.rejilla.mover("batch", 0)
    esperado = [("batch", "M"), ("avance", "M"), ("hora", "L"), ("top", "M"), ("danados", "M")]
    assert v.items() == esperado
    otra = ChartsView()                    # una ventana nueva de la misma persona recupera lo que dejó
    qtbot.addWidget(otra)
    otra.set_sesion(ana)
    assert otra.items() == esperado and otra.rejilla.ids() == [c for c, _t in esperado]
    assert otra.rejilla.baldosa("hora").tam == "L"


def test_restaurar_vuelve_a_las_seis_y_olvida_lo_guardado(qtbot, vista):
    v, ana = vista
    v.quitar_grafica("top")
    v.cambiar_tam("avance", "S")
    v.restaurar()
    assert v.items() == [(c, "M") for c in SEIS]
    otra = ChartsView()
    qtbot.addWidget(otra)
    otra.set_sesion(ana)
    assert otra.items() == [(c, "M") for c in SEIS]


def test_disposicion_guardada_danada_o_con_basura_se_repara():
    from app import graficas_prefs as gp
    gp._ajustes().setValue("graficas/x", "{no es json")
    assert gp.cargar("x") == gp.predeterminado()
    assert gp.normalizar([("avance", "Z"), ("avance", "S"), ("rara", "M"), ("top", "L")]) == [("avance", "M"), ("top", "L")]


def test_una_grafica_se_redimensiona_con_el_asa_y_la_medida_se_recuerda(qtbot, vista):
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    from app import graficas_prefs as gp
    v, ana = vista
    v.set_edicion(True)
    assert v.rejilla.redimensionable
    b = v.rejilla.baldosa("avance")
    ov = b._edicion
    alto0, ancho0 = b.height(), b.width()
    ini = QPoint(ov.width() - 10, ov.height() - 10)                  # dentro del asa
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, ini)
    QTest.mouseMove(ov, ini + QPoint(600, 100))
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, ini + QPoint(600, 100))
    assert b.height() == alto0 + 100 and b.width() > ancho0          # alto libre; ancho por columnas
    assert gp.cargar_medidas(ana.usuario)["avance"] == (b.cols, b.alto)
    assert ("avance", "M") in gp.cargar(ana.usuario)                 # el tamaño S/M/L sigue guardado
    v.cambiar_tam("avance", "M")                                     # elegir un tamaño descarta la medida propia
    assert gp.cargar_medidas(ana.usuario) == {} and v.rejilla.baldosa("avance").height() == alto0


def test_las_medidas_guardadas_se_limitan_y_los_diseños_viejos_siguen_cargando():
    from app import graficas_prefs as gp
    assert gp.limitar_medidas(9, 5000) == (gp.COLS_MAX, gp.LIMITES_ALTO["grafico"][1])
    assert gp.limitar_medidas("x", None) == (0, 0)
    gp.guardar("u", [("avance", "M"), ("dona", "S")])                # sin medidas: formato de siempre
    assert gp.cargar("u") == [("avance", "M"), ("dona", "S")] and gp.cargar_medidas("u") == {}
    gp.guardar("u", [("avance", "M")], {"avance": (3, 500)})
    assert gp.cargar_medidas("u") == {"avance": (3, 500)}
