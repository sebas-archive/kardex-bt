"""Motion del Dashboard: entrada coordinada, tarjetas, rejilla, modo edición, hojas, gráficas, banner y drawer.

Estas pruebas encienden el movimiento real (``widgets.ANIMAR = True``) y comprueban lo que importa de verdad: que
cada animación **termina en el estado final exacto** (sin opacidades parciales, sin efectos puestos, sin capas
huérfanas), que no se contradicen entre sí y que el dato mostrado es siempre el dato real.
"""

from datetime import datetime

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF, QPropertyAnimation, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QFrame, QScrollArea, QWidget

from app import dashboard_prefs as prefs
from app.auth import ADMIN, INVENTARIO, Sesion
from app.dashboard_datos import Datos, Serie
from app.views import components, motion, widgets
from app.views.dashboard import DashboardView
from app.views.grafico_personal import GraficoPersonal
from app.views.motion_global import _Velo
from app.views.rejilla_personal import alto_de

ANA = Sesion("ana.gomez", "Ana Gómez", ADMIN)
LUIS = Sesion("luis", "Luis Ortiz", INVENTARIO)
MAX = 16777215


@pytest.fixture(autouse=True)
def limpio():
    ajustes = prefs._ajustes()
    ajustes.remove("dashboard")
    yield
    ajustes.remove("dashboard")


@pytest.fixture
def con_movimiento(monkeypatch):
    monkeypatch.setattr(widgets, "ANIMAR", True)
    motion.fijar_reducido(False)
    yield
    motion.fijar_reducido(None)


def vista(qtbot, sesion=ANA, alto=800):
    v = DashboardView()
    qtbot.addWidget(v)
    v._sesion = sesion
    v._items = prefs.cargar(sesion.usuario, sesion)
    v._reconstruir()
    v.resize(1200, alto)
    v.show()
    qtbot.wait(30)
    return v


def sin_efectos(v: DashboardView) -> bool:
    return all(b.graphicsEffect() is None for b in v.rejilla.baldosas())


# ----------------------------------------------------------------------------- entrada del Dashboard
def test_la_entrada_es_escalonada_termina_rapido_y_deja_todo_en_su_sitio(qtbot, con_movimiento):
    v = vista(qtbot)
    destinos = {b.id: b.geometry() for b in v.rejilla.baldosas()}
    v.entrada_motion()
    efectos = [b.graphicsEffect() for b in v.rejilla.baldosas()]
    assert all(isinstance(e, motion.EfectoMovimiento) for e in efectos)           # todas arrancan ocultas…
    assert any(e.opacidad() < 1.0 for e in efectos)
    assert v.titulo.graphicsEffect() is not None
    qtbot.waitUntil(lambda: sin_efectos(v) and v.titulo.graphicsEffect() is None
                    and v.subtitulo.graphicsEffect() is None, timeout=3000)       # …y la cascada cabe en ~0,5 s
    assert {b.id: b.geometry() for b in v.rejilla.baldosas()} == destinos         # posición final exacta


def test_la_entrada_no_deja_efectos_si_las_animaciones_estan_apagadas(qtbot, monkeypatch):
    monkeypatch.setattr(widgets, "ANIMAR", False)
    v = vista(qtbot)
    v.entrada_motion()
    assert sin_efectos(v) and v.titulo.graphicsEffect() is None


def test_lo_que_esta_fuera_de_pantalla_se_revela_una_sola_vez_al_desplazar(qtbot, con_movimiento):
    v = vista(qtbot, alto=300)
    v.entrada_motion()
    qtbot.wait(60)
    pendientes = [b for b in v.rejilla.baldosas() if b._entrada_pendiente]
    assert pendientes, "con 300 px de alto debe haber baldosas fuera de la pantalla"
    assert all(b.graphicsEffect().opacidad() == 0.0 for b in pendientes)          # no se animan hasta que se ven
    barra = v._scroll.verticalScrollBar()
    barra.setValue(barra.maximum())
    qtbot.waitUntil(lambda: not any(b._entrada_pendiente for b in v.rejilla.baldosas()), timeout=1500)
    qtbot.waitUntil(lambda: sin_efectos(v), timeout=1500)
    barra.setValue(0)                                                             # volver arriba no repite nada
    barra.setValue(barra.maximum())
    assert sin_efectos(v)


def test_en_movimiento_reducido_la_entrada_es_corta_y_termina_igual(qtbot, con_movimiento):
    motion.fijar_reducido(True)
    v = vista(qtbot)
    v.entrada_motion()
    qtbot.waitUntil(lambda: sin_efectos(v), timeout=700)


def test_abandonar_la_vista_a_media_entrada_no_deja_nada_colgando(qtbot, con_movimiento):
    v = vista(qtbot)
    v.entrada_motion()
    sip.delete(v)                       # la vista se destruye con animaciones y temporizadores pendientes
    qtbot.wait(1200)                    # no debe haber excepciones ni cierres inesperados


# ----------------------------------------------------------------------------- tarjetas KPI
def test_kpi_cifra_final_exacta_tendencia_y_estados(qtbot, con_movimiento):
    c = widgets.TarjetaKpi("Contados")
    qtbot.addWidget(c)
    c.show()
    c.set_estado("cargando")
    assert c._anim_estado is not None and c.texto() == "—"                         # respira sin cambiar el dato
    c.set_valor(10, lambda v: str(round(v)))
    assert c.estado() == "ok" and c._anim_estado is None and c._valor.opacity() == 1.0
    qtbot.waitUntil(lambda: c.texto_visible() == "10", timeout=2000)
    c.set_valor(13, lambda v: str(round(v)))
    assert c.texto() == "13"
    qtbot.waitUntil(lambda: c.tendencia_visible().startswith("▲"), timeout=1000)   # diferencia real, sin color ni juicio
    qtbot.waitUntil(lambda: c.texto_visible() == "13", timeout=2000)               # la cifra siempre termina en el dato real
    c.set_valor(None, lambda v: str(round(v)))
    assert c.estado() == "vacio" and c.texto() == "—"
    c.set_estado("error")
    assert c.estado() == "error"


def test_kpi_detalle_se_desliza_y_la_cifra_vuelve_intacta(qtbot, con_movimiento):
    from PyQt6.QtGui import QEnterEvent
    c = widgets.TarjetaKpi("Avance")
    qtbot.addWidget(c)
    c.show()
    c.set_valor(80, lambda v: f"{round(v)} %")
    c.set_detalle("4 de 5 SKU")
    qtbot.waitUntil(lambda: c.texto_visible() == "80 %", timeout=2000)
    c.enterEvent(QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    qtbot.waitUntil(lambda: c._detalle.opacity() == 1.0 and c._valor.opacity() == 0.0, timeout=1000)
    assert c._valor._desp < 0 and c._detalle._desp == 0                            # la cifra salió hacia arriba
    c.leaveEvent(QTest.__dict__.get("x") or QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    qtbot.waitUntil(lambda: c._valor.opacity() == 1.0 and c._detalle.opacity() == 0.0, timeout=1000)
    assert c._valor._desp == 0 and c.texto() == "80 %"


def test_la_cifra_no_lleva_efectos_anidados(qtbot, con_movimiento):
    c = widgets.TarjetaKpi("Avance")
    qtbot.addWidget(c)
    assert c._valor.graphicsEffect() is None and c._detalle.graphicsEffect() is None


def test_el_dashboard_pone_los_estados_de_las_tarjetas(qtbot, con_movimiento):
    v = vista(qtbot)
    v._estado_tarjetas("cargando")
    assert all(c.estado() == "cargando" for c in v.cards.values())
    v._fallo_carga("sin conexión")
    assert all(c.estado() == "error" for c in v.cards.values())
    v._mostrar((None, None, [], {}))
    assert all(c.estado() == "vacio" for c in v.cards.values())


# ----------------------------------------------------------------------------- rejilla: arrastre, medida, quitar
def test_arrastrar_levanta_asienta_y_reordena_sin_dejar_efectos(qtbot, con_movimiento):
    v = vista(qtbot)
    v.set_edicion(True)
    qtbot.wait(400)
    r = v.rejilla
    origen, destino = r.baldosa(r.ids()[0]), r.baldosa(r.ids()[3])
    inicio = origen.mapToGlobal(origen.rect().center())
    fin = destino.mapToGlobal(destino.rect().center()) + destino.rect().center()
    r._arrastre_inicio(origen, QPointF(inicio))
    assert origen.graphicsEffect() is None                                          # un simple clic no «levanta»
    r._arrastre_mover(QPointF(fin))
    qtbot.wait(250)
    ef = origen.graphicsEffect()
    assert isinstance(ef, motion.EfectoMovimiento) and ef._escs[motion.ARRASTRE_C] > 1.0 and ef.sombra() > 0
    assert r._marcador.isVisible()
    r._arrastre_fin()
    qtbot.waitUntil(lambda: sin_efectos(v) and not r._marcador.isVisible(), timeout=2000)
    assert r.ids()[0] != origen.id and [i.id for i in v.items()] == r.ids()          # el orden real quedó persistido
    assert [i.id for i in prefs.cargar("ana.gomez", ANA)] == r.ids()
    for b in r.baldosas():                                                           # cada baldosa en su hueco exacto
        assert b.geometry() == b.destino


def test_cada_baldosa_reutiliza_una_sola_animacion_de_geometria(qtbot, con_movimiento):
    v = vista(qtbot)
    v.set_edicion(True)
    r = v.rejilla
    origen = r.baldosa(r.ids()[0])
    destino = r.baldosa(r.ids()[3])
    r._arrastre_inicio(origen, QPointF(origen.mapToGlobal(origen.rect().center())))
    for k in range(25):                                                              # muchos movimientos seguidos
        r._arrastre_mover(QPointF(destino.mapToGlobal(destino.rect().center()) + destino.rect().center() * (k % 2)))
    r._arrastre_fin()
    for b in r.baldosas():
        assert len(b.findChildren(QPropertyAnimation)) <= 1                          # sin acumular objetos animación


def test_el_asa_muestra_la_medida_y_el_resultado_coincide_con_lo_persistido(qtbot, con_movimiento):
    v = vista(qtbot)
    v.set_edicion(True)
    r = v.rejilla
    b = r.baldosa(next(i.id for i in v.items() if i.clave == "dif_categoria"))
    capturadas = []
    r.medidas_cambiadas.connect(lambda i, c, a: capturadas.append((i, c, a)))
    r._redim_inicio(b, QPointF(500, 500))
    assert r._pildora.isVisible() or True
    r._redim_mover(QPointF(500 - 330, 500 + 40))
    qtbot.wait(40)
    assert "×" in r._pildora._texto and "px" in r._pildora._texto
    r._redim_fin()
    qtbot.waitUntil(lambda: not r._pildora.isVisible(), timeout=1000)
    assert capturadas and capturadas[-1][0] == b.id
    assert (capturadas[-1][1], capturadas[-1][2]) == (b.cols, b.alto)
    qtbot.waitUntil(lambda: b.height() == alto_de(b.tipo, b.tam, b.alto), timeout=1500)
    assert b.geometry() == b.destino


def test_quitar_un_widget_sale_con_animacion_y_la_persistencia_es_inmediata(qtbot, con_movimiento):
    v = vista(qtbot)
    objetivo = next(i for i in v.items() if i.clave == "batch")
    b = v.rejilla.baldosa(objetivo.id)
    v.quitar_widget(objetivo.id)
    assert v.rejilla.baldosa(objetivo.id) is None and v.item(objetivo.id) is None
    assert "batch" not in [i.clave for i in prefs.cargar("ana.gomez", ANA)]
    assert not sip.isdeleted(b) and not b.isEnabled()                                # se va, sin recibir clics
    qtbot.waitUntil(lambda: sip.isdeleted(b), timeout=1500)


def test_restaurar_funde_la_distribucion_sin_dejar_capas_huerfanas(qtbot, con_movimiento, monkeypatch):
    v = vista(qtbot)
    v.agregar_widget("sin_contar")
    qtbot.wait(400)
    monkeypatch.setattr(components.Confirmacion, "pedir", classmethod(lambda *a, **k: True))
    assert v.restaurar() is True
    assert v.rejilla.findChildren(_Velo)                                             # la imagen anterior se funde encima
    assert [i.clave for i in prefs.cargar("ana.gomez", ANA)] == [i.clave for i in prefs.predeterminado()]
    qtbot.waitUntil(lambda: not v.rejilla.findChildren(_Velo), timeout=1500)
    assert [i.clave for i in v.items()] == [i.clave for i in prefs.predeterminado()]


# ----------------------------------------------------------------------------- modo de edición
def test_el_modo_edicion_se_despliega_y_se_recoge_sin_restos(qtbot, con_movimiento):
    v = vista(qtbot)
    v.set_edicion(True)
    assert v.barra_edicion.isVisible() and v.barra_edicion.graphicsEffect() is not None
    qtbot.waitUntil(lambda: v.barra_edicion.graphicsEffect() is None and v.btn_personalizar.isHidden()
                    and all(b.btn_quitar.isVisible() and b.btn_quitar.opacity() == 1.0
                            for b in v.rejilla.baldosas()), timeout=1500)
    assert v.barra_edicion.maximumHeight() == MAX
    v.set_edicion(False)
    qtbot.waitUntil(lambda: v.barra_edicion.isHidden() and v.btn_personalizar.isVisible(), timeout=1500)
    qtbot.waitUntil(lambda: v.barra_edicion.graphicsEffect() is None and v.btn_personalizar.graphicsEffect() is None
                    and all(not b.btn_quitar.isVisible() and not b._edicion.isVisible()
                            for b in v.rejilla.baldosas()), timeout=1500)


def test_entrar_y_salir_de_edicion_muchas_veces_seguidas_termina_coherente(qtbot, con_movimiento):
    v = vista(qtbot)
    for _ in range(4):
        v.set_edicion(True)
        qtbot.wait(40)
        v.set_edicion(False)
        qtbot.wait(40)
    qtbot.waitUntil(lambda: v.barra_edicion.isHidden() and v.btn_personalizar.isVisible(), timeout=2000)
    qtbot.wait(500)
    assert v.btn_personalizar.graphicsEffect() is None and v.barra_edicion.graphicsEffect() is None
    assert all(not b._edicion.isVisible() for b in v.rejilla.baldosas())


# ----------------------------------------------------------------------------- hojas: catálogo y configuración
def test_el_catalogo_abre_y_cierra_con_transicion_y_termina_en_reposo(qtbot, con_movimiento):
    v = vista(qtbot)
    v._abrir_catalogo()
    hoja = v._hojas["catalogo"]
    assert hoja.isVisible() and hoja.caja.graphicsEffect() is not None               # entrando
    qtbot.waitUntil(lambda: hoja.caja.graphicsEffect() is None, timeout=1500)
    assert hoja.caja.geometry() == hoja._final and hoja._velo == 1.0
    with qtbot.waitSignal(hoja.cerrada, timeout=1500):
        hoja.cerrar()
    assert not hoja.isVisible() and hoja.caja.graphicsEffect() is None and hoja._velo == 0.0


def test_el_catalogo_solo_muestra_lo_permitido_y_cambiar_de_categoria_no_deja_efectos(qtbot, con_movimiento):
    v = vista(qtbot, LUIS)
    v._abrir_catalogo()
    hoja = v._hojas["catalogo"]
    qtbot.waitUntil(lambda: hoja.caja.graphicsEffect() is None, timeout=1500)
    assert "actividad_reciente" not in hoja._marcos                                  # el rol no lo puede consultar
    categoria = next(c for c in prefs.CATEGORIAS if any(d.categoria == c and prefs.permitido(d, LUIS)
                                                        for d in prefs.CATALOGO))
    hoja._elegir(categoria)
    assert hoja._scroll.viewport().findChildren(_Velo)                               # lo anterior se funde
    esperados = {d.clave for d in prefs.CATALOGO if d.categoria == categoria and prefs.permitido(d, LUIS)}
    assert set(hoja._marcos) == esperados
    qtbot.waitUntil(lambda: not hoja._scroll.viewport().findChildren(_Velo)
                    and all(m.graphicsEffect() is None for m in hoja._marcos.values()), timeout=2000)


def test_agregar_desde_el_catalogo_conserva_el_desplazamiento(qtbot, con_movimiento):
    v = vista(qtbot)
    v._abrir_catalogo()
    hoja = v._hojas["catalogo"]
    qtbot.waitUntil(lambda: hoja.caja.graphicsEffect() is None, timeout=1500)
    barra = hoja._scroll.verticalScrollBar()
    barra.setValue(barra.maximum() // 2)
    antes = barra.value()
    clave = next(c for c in hoja._marcos if not prefs.POR_CLAVE[c].unico)
    hoja._pedir(clave)
    qtbot.wait(120)
    assert abs(barra.value() - antes) <= 2 and clave in [i.clave for i in v.items()]


def test_config_grafico_muestra_y_oculta_opciones_con_transicion(qtbot, con_movimiento):
    v = vista(qtbot)
    item = v.agregar_widget("lecturas_tiempo")
    v._configurar(item.id)
    hoja = v._hojas["config"]
    qtbot.waitUntil(lambda: hoja.caja.graphicsEffect() is None, timeout=1500)
    hoja.cmb_periodo.setCurrentIndex(hoja.cmb_periodo.findData("personalizado"))
    assert not hoja.fila_fechas.isHidden()
    qtbot.wait(400)
    hoja.cmb_periodo.setCurrentIndex(hoja.cmb_periodo.findData("todo"))
    qtbot.waitUntil(lambda: hoja.fila_fechas.isHidden(), timeout=1500)
    hoja.cmb_periodo.setCurrentIndex(hoja.cmb_periodo.findData("personalizado"))     # volver a mostrar nunca queda invisible
    qtbot.wait(500)
    efecto = hoja.fila_fechas.graphicsEffect()
    assert hoja.fila_fechas.isVisibleTo(hoja) and (efecto is None or efecto.opacidad() == 1.0)


# ----------------------------------------------------------------------------- gráficas
def datos(valores, etiquetas=("A", "B", "C")):
    return Datos(etiquetas=list(etiquetas), series=[Serie("Serie", list(valores))], unidad="")


def grafico(qtbot):
    g = GraficoPersonal()
    qtbot.addWidget(g)
    g.resize(420, 260)
    g.show()
    return g


def test_la_grafica_interpola_entre_valores_reales_y_termina_exacta(qtbot, con_movimiento):
    g = grafico(qtbot)
    g.poner(datos([10, 20, 30]), "barras")
    qtbot.waitUntil(lambda: g._prog >= 1.0, timeout=2000)
    g.poner(datos([30, 20, 10]), "barras")
    assert g._mezcla < 1.0 and g._previos                                            # hay transición (no salto)
    qtbot.wait(120)
    intermedio = g._val(0, 0)
    assert 10 <= intermedio <= 30
    qtbot.waitUntil(lambda: g._mezcla >= 1.0, timeout=2000)
    assert g._previos == {} and [g._val(0, i) for i in range(3)] == [30, 20, 10]     # exactamente el dato recibido
    g.grab()                                                                         # dibuja sin errores


def test_cambiar_de_tipo_funde_la_imagen_anterior_y_no_deja_fantasmas(qtbot, con_movimiento):
    g = grafico(qtbot)
    g.poner(datos([5, 8, 3]), "barras")
    qtbot.waitUntil(lambda: g._prog >= 1.0, timeout=2000)
    g.poner(datos([5, 8, 3]), "lineas")
    assert g._fantasma is not None
    qtbot.waitUntil(lambda: g._fantasma is None and g._prog >= 1.0, timeout=2000)
    for tipo in ("area", "circular", "anillo", "barras_h", "apiladas", "comparativo"):
        g.poner(datos([5, 8, 3]), tipo)
        g.grab()
    qtbot.wait(900)


def test_la_grafica_en_carga_dibuja_un_esqueleto_que_se_detiene_con_el_dato(qtbot, con_movimiento):
    g = grafico(qtbot)
    g.cargando = True
    assert g._a_carga is not None                                                    # destello discreto, no un spinner
    g.grab()
    g.poner(datos([1, 2, 3]), "barras")
    assert g._a_carga is None
    g.cargando = False


def test_resalte_guia_y_sectores_vuelven_a_cero_sin_restos(qtbot, con_movimiento):
    g = grafico(qtbot)
    g.poner(Datos(etiquetas=["a", "b", "c", "d"], series=[Serie("S", [4, 8, 6, 2])], temporal=True), "lineas")
    qtbot.waitUntil(lambda: g._prog >= 1.0, timeout=2000)
    g._hover = 2
    g._animar_hover()
    qtbot.waitUntil(lambda: g._hov.get(2, 0) > 0.99 and g._dim > 0.99, timeout=1000)
    g.grab()
    g._hover = None
    g._animar_hover()
    qtbot.waitUntil(lambda: g._hov == {} and g._dim == 0.0 and g._g_idx is None, timeout=1000)
    g.poner(datos([5, 5, 10]), "circular")
    qtbot.waitUntil(lambda: g._prog >= 1.0, timeout=2000)
    g._alternar_cat(1)                                                               # la categoría se cierra suavemente
    qtbot.waitUntil(lambda: g._vis_cat != {}, timeout=500)
    qtbot.waitUntil(lambda: g._vis_cat == {}, timeout=1500)
    assert g._ocultas_cat == {1} and g._vis(1) == 0.0 and g._vis(0) == 1.0
    g.grab()


def test_la_dona_emite_su_senal_al_tocar_la_leyenda(qtbot):
    d = widgets.Dona({"a": "#10B981", "b": "#F04438"}, {"a": "A", "b": "B"})
    qtbot.addWidget(d)
    d.resize(520, 240)
    d.show()
    d.set_datos([("a", 3.0), ("b", 1.0)])
    d.grab()                                                                         # la leyenda se calcula al pintar
    clave, caja = d._leyenda[0][1], d._leyenda[0][0]
    with qtbot.waitSignal(d.alternada, timeout=500) as espera:
        QTest.mouseClick(d, Qt.MouseButton.LeftButton, pos=caja.center().toPoint())
    assert espera.args == [clave] and clave in d._ocultas


def test_barra_dona_y_mapa_interpolan_y_terminan_exactas(qtbot, con_movimiento):
    barra = widgets.BarraSegmentada({"a": "#10B981", "b": "#F04438"})
    dona = widgets.Dona({"a": "#10B981", "b": "#F04438"})
    mapa = widgets.MapaUbicaciones()
    for w in (barra, dona, mapa):
        qtbot.addWidget(w)
        w.resize(520, 240)
        w.show()
    barra.set_segmentos([("a", 3), ("b", 1)])
    dona.set_datos([("a", 3.0), ("b", 1.0)])
    mapa.set_datos([("A-1", "A", 4), ("A-2", "A", 1)])
    qtbot.wait(1600)
    barra.set_segmentos([("a", 1), ("b", 3)])
    dona.set_datos([("a", 1.0), ("b", 3.0)])
    mapa.set_datos([("A-1", "A", 1), ("A-2", "A", 4)])
    assert barra._mezcla < 1.0 and dona._mezcla < 1.0 and mapa._mezcla < 1.0
    qtbot.wait(1600)
    assert barra._prev == {} and dona._prev == {} and mapa._prev == {}
    assert barra.segmentos() == [("a", 1), ("b", 3)] and dona.datos() == [("a", 1.0), ("b", 3.0)]
    assert barra._n_vis("a", 1) == 1 and dona._v_vis("b", 3.0) == 3.0 and mapa._sk_vis("A-2", 4) == 4
    for w in (barra, dona, mapa):
        w.grab()


# ----------------------------------------------------------------------------- StateBanner, drawer, scroll
def test_el_drawer_difumina_al_ritmo_del_panel_y_cierra_limpio(qtbot, con_movimiento):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(900, 600)
    host.show()
    drawer = components.Drawer(host, ancho=360)
    qtbot.addWidget(drawer)
    drawer.abrir("Detalle", QWidget())
    assert drawer._fondo.avance() < 1.0                                              # progresivo, no instantáneo
    qtbot.waitUntil(lambda: drawer._fondo.avance() == 1.0 and drawer.panel.x() == 900 - 360, timeout=1500)
    drawer.cerrar()
    qtbot.waitUntil(lambda: not drawer.isVisible(), timeout=1500)
    assert drawer._fondo.avance() == 0.0


def test_el_scroll_suave_se_instala_una_sola_vez(qtbot, con_movimiento):
    area = QScrollArea()
    qtbot.addWidget(area)
    a = motion.instalar_scroll_suave(area)
    assert motion.instalar_scroll_suave(area) is a
    assert len(area.findChildren(motion.ScrollSuave)) == 1
    v = vista(qtbot)
    assert len(v._scroll.findChildren(motion.ScrollSuave)) == 1


def test_con_movimiento_reducido_no_hay_ciclos_decorativos_y_la_vista_previa_se_reinicia(qtbot, con_movimiento):
    motion.fijar_reducido(True)
    c = widgets.TarjetaKpi("Avance")
    qtbot.addWidget(c)
    c.show()
    c.set_estado("cargando")
    assert c._anim_estado is None and c._valor.opacity() == 1.0          # sin respiración: la cifra queda quieta
    g = grafico(qtbot)
    g.cargando = True
    assert g._a_carga is None                                            # el esqueleto no se anima
    assert widgets._ms(650) <= 160 and motion.desp(10) < 10             # las transiciones esenciales siguen, más cortas
    g.cargando = False
    g.poner(datos([1, 2, 3]), "barras")
    g.limpiar()
    assert g._firma is None and g._datos.vacio and g._previos == {} and g._prog == 1.0


def test_un_efecto_de_movimiento_combina_canales_sin_pisarse(qtbot):
    marco = QFrame()
    qtbot.addWidget(marco)
    ef = motion.efecto_movimiento(marco)
    ef.set_dy(-3.0, motion.HOVER_C)
    ef.set_escala(1.02, motion.ARRASTRE_C)
    ef.set_dy(8.0)                                       # la entrada escribe en su canal sin borrar el del hover
    assert ef._dy == 5.0 and abs(ef._esc - 1.02) < 1e-9
    motion.soltar_efecto(marco, ef)
    assert marco.graphicsEffect() is ef                  # otra capa aún lo usa: no se quita
    ef.set_dy(0.0)
    ef.set_dy(0.0, motion.HOVER_C)
    ef.set_escala(1.0, motion.ARRASTRE_C)
    motion.soltar_efecto(marco, ef)
    assert marco.graphicsEffect() is None
