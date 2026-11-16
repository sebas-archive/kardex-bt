"""Dashboard personalizable: catálogo, persistencia por usuario, datos de los gráficos y la rejilla.

No dependen de Oracle: los datos de los gráficos se pasan en memoria con la misma forma que devuelven las consultas.
"""

from datetime import datetime

import pytest

from app import dashboard_prefs as prefs
from app.auth import ADMIN, INVENTARIO, Sesion
from app.dashboard_datos import construir, rango
from app.views import components
from app.views.dashboard import DashboardView
from app.views.rejilla_personal import colocar

ANA = Sesion("ana.gomez", "Ana Gómez", ADMIN)
LUIS = Sesion("luis", "Luis Ortiz", INVENTARIO)
AHORA = datetime(2026, 11, 15, 12, 0)


@pytest.fixture(autouse=True)
def limpio():
    ajustes = prefs._ajustes()
    ajustes.remove("dashboard")
    yield
    ajustes.remove("dashboard")


def vista(qtbot, sesion):
    v = DashboardView()
    qtbot.addWidget(v)
    v._sesion = sesion
    v._items = prefs.cargar(sesion.usuario, sesion)
    v._reconstruir()
    v.resize(1200, 800)
    v.show()
    return v


# ----------------------------------------------------------------------------- catálogo y permisos
def test_la_distribucion_inicial_es_la_del_dashboard_original():
    assert [i.clave for i in prefs.predeterminado()] == ["avance", "contados", "faltantes", "sobrantes",
                                                         "dif_categoria", "batch"]


def test_el_catalogo_solo_ofrece_lo_que_el_rol_puede_consultar():
    assert prefs.permitido(prefs.POR_CLAVE["actividad_reciente"], ANA)        # auditoría: solo administrador
    assert not prefs.permitido(prefs.POR_CLAVE["actividad_reciente"], LUIS)
    assert prefs.permitido(prefs.POR_CLAVE["avance"], LUIS)


def test_una_distribucion_guardada_con_algo_prohibido_se_depura_al_cargar():
    prefs.guardar("luis", [prefs.nuevo("avance"), prefs.nuevo("actividad_reciente"), prefs.Item("fantasma")])
    assert [i.clave for i in prefs.cargar("luis", LUIS)] == ["avance"]


def test_cada_widget_tiene_descripcion_categoria_y_tamano_valido():
    for d in prefs.CATALOGO:
        assert d.descripcion and d.categoria in prefs.CATEGORIAS and d.tam in d.tams
        if d.tipo == prefs.GRAFICO:
            assert d.tipo_defecto in d.tipos and set(d.tipos) <= set(prefs.TIPOS_GRAFICO)


# ----------------------------------------------------------------------------- persistencia por usuario
def test_la_distribucion_se_guarda_por_usuario_y_se_restaura():
    items = prefs.predeterminado() + [prefs.nuevo("sin_contar")]
    prefs.guardar("ana.gomez", items)
    assert [i.clave for i in prefs.cargar("ana.gomez", ANA)][-1] == "sin_contar"
    assert [i.clave for i in prefs.cargar("luis", LUIS)] == [i.clave for i in prefs.predeterminado()]   # no se mezcla
    assert [i.clave for i in prefs.restaurar("ana.gomez")] == [i.clave for i in prefs.predeterminado()]
    assert "sin_contar" not in [i.clave for i in prefs.cargar("ana.gomez", ANA)]


def test_una_preferencia_dañada_no_rompe_el_dashboard():
    prefs._ajustes().setValue("dashboard/ana.gomez", "{no es json")
    assert [i.clave for i in prefs.cargar("ana.gomez", ANA)] == [i.clave for i in prefs.predeterminado()]


# ----------------------------------------------------------------------------- datos reales de los gráficos
CRUDO = {
    "categorias": [("Abarrotes", -4.0), ("Aseo", 3.0), ("Lácteos", 4.0)],
    "series": {
        "por_hora": [("2026-11-15 09:00", 2.0), ("2026-11-15 09:30", 3.0), ("2026-11-15 10:10", 5.0),
                     ("2026-10-01 08:00", 7.0)],
        "top_categorias": [("Aseo", 5.0), ("Abarrotes", 9.0), ("Lácteos", 1.0)],
        "avance_categoria": [("Aseo", 50.0)],
        "danados": [],
        "batch": [("2026-11-15 11:00", 8.0), ("2026-11-14 11:00", 4.0)],
        "batch_errores": [("2026-11-15 11:00", 1.0), ("2026-11-14 11:00", 0.0)],
        "contados_pendientes": [("contados", 9.0), ("pendientes", 52.0)],
    },
    "actividad": [("ana", "2026-11-15 09:00", 3), ("luis", "2026-11-15 09:00", 1), ("ana", "2026-11-15 10:00", 2)],
}


def test_la_diferencia_por_categoria_conserva_el_signo_y_el_orden():
    d = construir("dif_categoria", prefs.opciones_por_defecto(prefs.POR_CLAVE["dif_categoria"]), CRUDO, AHORA)
    assert d.etiquetas == ["Abarrotes", "Aseo", "Lácteos"] and d.series[0].valores == [-4.0, 3.0, 4.0] and d.semaforo


def test_orden_y_cantidad_de_elementos():
    o = {**prefs.opciones_por_defecto(prefs.POR_CLAVE["lecturas_categoria"]), "orden": "valor_desc", "top": 2}
    d = construir("lecturas_categoria", o, CRUDO, AHORA)
    assert d.etiquetas == ["Abarrotes", "Aseo"] and d.series[0].valores == [9.0, 5.0]


def test_el_periodo_filtra_por_fecha():
    base = prefs.opciones_por_defecto(prefs.POR_CLAVE["lecturas_tiempo"])
    todo = construir("lecturas_tiempo", {**base, "periodo": "todo", "agrupar": "dia"}, CRUDO, AHORA)
    hoy = construir("lecturas_tiempo", {**base, "periodo": "hoy", "agrupar": "hora"}, CRUDO, AHORA)
    assert sum(todo.series[0].valores) == 17.0
    assert sum(hoy.series[0].valores) == 10.0 and hoy.etiquetas == ["09:00", "10:00"]
    assert construir("lecturas_tiempo", {**base, "periodo": "30d", "agrupar": "dia"}, CRUDO, AHORA).etiquetas == ["15/11"]


def test_un_periodo_sin_datos_queda_vacio_en_vez_de_inventar():
    o = {**prefs.opciones_por_defecto(prefs.POR_CLAVE["lecturas_tiempo"]), "periodo": "personalizado",
         "desde": "2025-01-01", "hasta": "2025-01-31"}
    assert construir("lecturas_tiempo", o, CRUDO, AHORA).vacio


def test_rangos_de_periodo():
    assert rango({"periodo": "hoy"}, AHORA) == (datetime(2026, 11, 15), datetime(2026, 11, 16))
    assert rango({"periodo": "mes"}, AHORA)[0] == datetime(2026, 11, 1)
    assert rango({"periodo": "anio"}, AHORA)[0] == datetime(2026, 1, 1)
    assert rango({"periodo": "todo"}, AHORA) == (None, None)


def test_operadores_en_el_tiempo_apila_una_serie_por_operador():
    o = {**prefs.opciones_por_defecto(prefs.POR_CLAVE["operador_tiempo"]), "agrupar": "hora"}
    d = construir("operador_tiempo", o, CRUDO, AHORA)
    assert [s.nombre for s in d.series] == ["ana", "luis"] and d.etiquetas == ["09:00", "10:00"]
    assert d.series[0].valores == [3.0, 2.0] and d.series[1].valores == [1.0, 0.0]


def test_procesamiento_por_corrida_tiene_procesadas_y_con_error():
    d = construir("batch_corridas", prefs.opciones_por_defecto(prefs.POR_CLAVE["batch_corridas"]), CRUDO, AHORA)
    assert [s.nombre for s in d.series] == ["Procesadas", "Con error"] and d.series[1].valores == [0.0, 1.0]


# ----------------------------------------------------------------------------- rejilla
def test_colocar_respeta_columnas_y_salta_de_fila():
    rects, alto = colocar([(1, 100), (1, 100), (2, 100), (4, 50)], 1000, 4)
    assert [(r.x() > 0, r.y()) for r in rects[:2]] == [(False, 0), (True, 0)]
    assert rects[2].y() == 0 and rects[2].width() > rects[0].width()
    assert rects[3].y() == 114 and rects[3].width() == 1000 and alto == 164


def test_en_ventanas_estrechas_un_grande_ocupa_el_ancho():
    rects, _ = colocar([(2, 80), (2, 80)], 500, 2)
    assert rects[0].width() == 500 and rects[1].y() == 94


# ----------------------------------------------------------------------------- la vista
def test_agregar_y_quitar_widgets_persisten(qtbot):
    v = vista(qtbot, ANA)
    assert v.agregar_widget("sin_contar") is not None
    assert v.agregar_widget("sin_contar") is None                     # un indicador no se repite
    assert "sin_contar" in v.cards
    g = v.agregar_widget("lecturas_tiempo")
    assert g is not None and v.agregar_widget("lecturas_tiempo") is not None   # los gráficos sí se repiten
    assert [i.clave for i in prefs.cargar("ana.gomez", ANA)].count("lecturas_tiempo") == 2
    v.quitar_widget(g.id)
    assert [i.clave for i in prefs.cargar("ana.gomez", ANA)].count("lecturas_tiempo") == 1
    assert v.rejilla.baldosa(g.id) is None


def test_cambiar_tamano_y_orden_se_guardan(qtbot):
    v = vista(qtbot, ANA)
    id_dif = next(i.id for i in v.items() if i.clave == "dif_categoria")
    v.cambiar_tam(id_dif, "M")
    assert v.rejilla.baldosa(id_dif).tam == "M"
    v.cambiar_tam(id_dif, "S")                                       # los gráficos pueden ser pequeños
    assert next(i for i in prefs.cargar("ana.gomez", ANA) if i.id == id_dif).tam == "S"
    id_batch = next(i.id for i in v.items() if i.clave == "batch")
    v.cambiar_tam(id_batch, "S")                                     # un panel no admite tamaño pequeño
    assert v.item(id_batch).tam == "L"
    v.mover_widget(id_dif, 0)
    assert v.rejilla.ids()[0] == id_dif
    assert prefs.cargar("ana.gomez", ANA)[0].id == id_dif


def test_arrastrar_y_soltar_reordena(qtbot):
    v = vista(qtbot, ANA)
    v.set_edicion(True)
    origen = v.rejilla.baldosa(v.rejilla.ids()[0])
    destino = v.rejilla.baldosa(v.rejilla.ids()[3])
    from PyQt6.QtCore import QPointF
    inicio = origen.mapToGlobal(origen.rect().center())
    fin = destino.mapToGlobal(destino.rect().center()) + destino.rect().center()
    v.rejilla._arrastre_inicio(origen, QPointF(inicio))
    v.rejilla._arrastre_mover(QPointF(fin))
    v.rejilla._arrastre_fin()
    assert v.rejilla.ids()[0] != origen.id and origen.id in v.rejilla.ids()
    assert [i.id for i in v.items()] == v.rejilla.ids()
    assert [i.id for i in prefs.cargar("ana.gomez", ANA)] == v.rejilla.ids()


def test_un_fallo_suelto_de_oracle_se_reintenta_y_no_deja_el_widget_vacio(monkeypatch):
    from app.views import dashboard as dash
    monkeypatch.setattr(dash.time, "sleep", lambda _s: None)
    llamadas = []

    def inestable():
        llamadas.append(1)
        if len(llamadas) < dash.INTENTOS:
            raise RuntimeError("ORA-12516")
        return "datos"

    assert dash._con_reintentos(inestable) == "datos" and len(llamadas) == dash.INTENTOS


def test_si_oracle_sigue_fallando_se_propaga_el_error_tras_los_reintentos(monkeypatch):
    from app.views import dashboard as dash
    monkeypatch.setattr(dash.time, "sleep", lambda _s: None)

    def roto():
        raise RuntimeError("ORA-12516")

    with pytest.raises(RuntimeError):
        dash._con_reintentos(roto)


def test_un_grafico_recien_agregado_dice_cargando_y_no_sin_datos(qtbot):
    v = vista(qtbot, ANA)
    item = v.agregar_widget("lecturas_tiempo")
    assert v._graficos[item.id].cargando                              # su consulta aún no ha vuelto
    v._fallo_carga("ORA-12516")
    assert not v._graficos[item.id].cargando                          # si falló, ya no finge que está cargando


def test_quitar_un_panel_no_deja_una_etiqueta_muerta_que_rompa_el_siguiente_widget(qtbot):
    """Regresión: tras quitar «Última sincronización», agregar cualquier widget lanzaba RuntimeError (QLabel borrado)
    y el widget nuevo se quedaba sin datos."""
    from types import SimpleNamespace
    from PyQt6.QtCore import QCoreApplication, QEvent
    v = vista(qtbot, ANA)
    v._resumen = SimpleNamespace(skus_totales=5, contados=4, avance_pct=80.0, ok=1, faltantes=1, sobrantes=2,
                                 exactitud_pct=25.0, sin_contar=1)
    v._batch = SimpleNamespace(ultimo_run=datetime(2026, 11, 15, 10, 0), procesados=3, errores=0, pendientes=0)
    v._crudo = {"categorias": [("A", 1.0)], "series": {"avance_categoria": [("A", 50.0)]}, "actividad": [],
                "auditoria": []}
    panel = next(i for i in v.items() if i.clave == "batch")
    v.quitar_widget(panel.id)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)    # Qt borra el QLabel
    nuevo = v.agregar_widget("avance_categoria")                                  # antes: RuntimeError
    assert nuevo is not None and not v.datos_de(nuevo.id).vacio
    assert [i.clave for i in prefs.cargar("ana.gomez", ANA)].count("avance_categoria") == 1


def test_cada_usuario_tiene_su_propio_dashboard(qtbot):
    a = vista(qtbot, ANA)
    a.agregar_widget("sin_contar")
    b = vista(qtbot, LUIS)
    assert "sin_contar" not in [i.clave for i in b.items()]
    assert "sin_contar" in [i.clave for i in vista(qtbot, ANA).items()]       # al volver, ana recupera lo suyo


def test_un_rol_sin_permiso_no_puede_agregar_el_widget(qtbot):
    v = vista(qtbot, LUIS)
    assert v.agregar_widget("actividad_reciente") is None


def test_restaurar_pide_confirmacion_y_vuelve_a_lo_inicial(qtbot, monkeypatch):
    v = vista(qtbot, ANA)
    v.agregar_widget("sin_contar")
    monkeypatch.setattr(components.Confirmacion, "pedir", classmethod(lambda *a, **k: False))
    assert v.restaurar() is False and "sin_contar" in [i.clave for i in v.items()]
    monkeypatch.setattr(components.Confirmacion, "pedir", classmethod(lambda *a, **k: True))
    assert v.restaurar() is True
    assert [i.clave for i in v.items()] == [i.clave for i in prefs.predeterminado()]
    assert [i.clave for i in prefs.cargar("ana.gomez", ANA)] == [i.clave for i in prefs.predeterminado()]


def test_cambiar_opciones_de_un_grafico_y_duplicarlo(qtbot):
    v = vista(qtbot, ANA)
    g = v.agregar_widget("lecturas_tiempo")
    v.cambiar_opciones(g.id, tipo="barras", periodo="7d")
    guardado = next(i for i in prefs.cargar("ana.gomez", ANA) if i.id == g.id)
    assert guardado.opciones["tipo"] == "barras" and guardado.opciones["periodo"] == "7d"
    copia = v.duplicar_widget(g.id)
    assert copia is not None and copia.id != g.id and copia.opciones["tipo"] == "barras"
    assert v.duplicar_widget(next(i.id for i in v.items() if i.clave == "avance")) is None   # un indicador no se duplica


def test_el_dashboard_original_conserva_su_api(qtbot):
    v = vista(qtbot, ANA)
    assert set(v.cards) == {"avance", "contados", "faltantes", "sobrantes"}
    assert v.categorias() == []
    assert not [b for b in v.findChildren(__import__("PyQt6.QtWidgets", fromlist=["QPushButton"]).QPushButton)
                if "Cerrar" in b.text()]


def test_la_cifra_de_una_tarjeta_nunca_queda_invisible_tras_un_hover_sin_leave(qtbot, monkeypatch):
    """Regresión: el cursor entra antes de que lleguen los datos y Qt no manda ``leaveEvent`` al reubicarla."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QEnterEvent
    from app.views import widgets
    monkeypatch.setattr(widgets, "ANIMAR", True)
    c = widgets.TarjetaKpi("Avance")
    qtbot.addWidget(c)
    c.show()
    c.enterEvent(QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    qtbot.wait(400)                                                  # la animación de volteo termina
    c.set_valor(100, lambda v: str(round(v)))
    c.set_detalle("")
    qtbot.wait(800)
    assert c._op_valor.opacity() == 1.0 and c.texto_visible() == "100"


def test_un_fundido_de_entrada_no_deja_efecto_puesto(qtbot, monkeypatch):
    """Regresión: la baldosa nueva conservaba un efecto de opacidad que se anidaba con el de sus cifras (en blanco)."""
    from app.views import motion, widgets
    monkeypatch.setattr(widgets, "ANIMAR", True)
    w = widgets.TarjetaKpi("Avance")
    qtbot.addWidget(w)
    w.show()
    motion.desvanecer(w, 0.0, 1.0, 100)
    qtbot.waitUntil(lambda: w.graphicsEffect() is None, timeout=2000)


def test_el_catalogo_cuenta_cuantas_veces_esta_cada_widget(qtbot):
    from PyQt6.QtWidgets import QLabel, QPushButton, QWidget
    from app.views.dashboard_paneles import CatalogoWidgets
    ventana = QWidget()
    qtbot.addWidget(ventana)
    cat = CatalogoWidgets(ventana)
    cat.abrir_con(None, ["avance", "batch_corridas", "batch_corridas"])
    botones = [b.text() for b in cat.findChildren(QPushButton)]
    assert "Ya agregado" in botones and "Agregar otro" in botones          # un indicador no se repite; un gráfico sí
    assert any("En tu dashboard: 2" in l.text() for l in cat.findChildren(QLabel))
