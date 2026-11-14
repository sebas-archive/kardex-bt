"""La aplicación de escritorio: acceso, secciones por rol, dashboard, inventario, sincronización y gráficas.

Escenario fijo T-01: A1 contada 101 (+1, +1 %, $ 2.000, OK; la primera lectura de 60 quedó reemplazada),
A2 45 (−5, −10 %, −$ 5.000, FALTANTE), A3 23 (+3, +15 %, $ 9.000, SOBRANTE), A4 sin contar,
A5 sistema 0 y contada 4 ($ 2.800, SOBRANTE, sin %). Lecturas: Ana 3, Luis 2, todas a las 16:40 UTC.
"""

import threading

import pyqtgraph as pg
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from app import auth, db as dbq
from app.auth import ADMIN, INVENTARIO, Sesion
from app.main import MainWindow, build_window
from app.models import fmt_pct
from app.views import widgets
from app.views.acceso import AccesoView
from app.views.charts import CHART_IDS, EXTRA_IDS, ChartsView, _etiqueta_eje, _fmt_corto
from app.views.dashboard import DashboardView
from app.views.inventario import InventarioView
from app.views.perfil import PerfilView
from app.views.solicitudes import SolicitudesView
from app.views.sync import SyncView
from app.views.usuarios import UsuariosView
from conftest import connect, staging
from fakes import FakeRemoto

C = "T-01"
T0 = 1731170400000
ANA = Sesion("ana.gomez", "Ana Gómez", ADMIN)
LUIS = Sesion("luis", "Luis Ortiz", INVENTARIO)


def esperar(qtbot, condicion, timeout=15000):
    qtbot.waitUntil(condicion, timeout=timeout)


@pytest.fixture
def contado(escenario):
    escenario.cargar_lecturas()
    dbq.procesar_ahora()
    return escenario


@pytest.fixture
def puente():
    """El servicio Bluetooth falso (corre aparte: la prueba decide su estado)."""
    return FakeRemoto()


def abrir(qtbot, puente, sesion):
    """La ventana completa con la sesión dada, ya en el conteo T-01."""
    ventana = build_window(puente, auto_refresh_ms=0, sesion=sesion)
    qtbot.addWidget(ventana)
    ventana.show()
    esperar(qtbot, lambda: ventana.combo_conteo.findData(C) >= 0)
    ventana.select_conteo(C)
    esperar(qtbot, lambda: ventana.vista("Dashboard").card_text("avance") == "80,0 %")
    return ventana


# ------------------------------------------------------------------ acceso
def test_without_session_the_window_shows_only_the_login(qtbot, puente):
    ventana = build_window(puente, auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    ventana.show()
    assert ventana.sesion() is None and ventana.acceso.isVisible()
    assert not ventana.paginas.isVisible()                      # nada de la aplicación se ve ni se consulta
    assert ventana.secciones() == []


def test_register_then_login_enters_the_app(qtbot, cuentas, contado, puente):
    ventana = build_window(puente, auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    ventana.show()
    acceso = ventana.acceso
    acceso.btn_ir_a_registro.click()
    assert acceso.formularios.currentIndex() == 1
    acceso.txt_nombre.setText("Ana Gómez")
    acceso.txt_usuario_nuevo.setText("ana.gomez")
    acceso.txt_clave_nueva.setText("conteo2026")
    assert acceso.lbl_fuerza.text() == "Aceptable"
    acceso.txt_confirmacion.setText("conteo2027")
    acceso.btn_crear.click()
    esperar(qtbot, lambda: "no coinciden" in acceso.lbl_error.text())
    assert ventana.sesion() is None
    acceso.txt_confirmacion.setText("conteo2026")
    acceso.btn_crear.click()
    esperar(qtbot, lambda: ventana.sesion() is not None)
    assert ventana.sesion() == ANA                               # la primera cuenta es administradora
    assert ventana.paginas.isVisible() and ventana.lbl_usuario.text() == "Ana Gómez" and ventana.lbl_rol.text() == "Administrador"
    assert acceso.txt_clave_nueva.text() == ""                   # no quedan contraseñas escritas

    ventana.btn_salir.click()
    assert ventana.sesion() is None and acceso.isVisible()
    acceso.txt_usuario.setText("ana.gomez")
    acceso.txt_clave.setText("malaclave1")
    acceso.btn_entrar.click()
    esperar(qtbot, lambda: "incorrectos" in acceso.lbl_error.text())
    acceso.txt_clave.setText("conteo2026")
    acceso.btn_entrar.click()
    esperar(qtbot, lambda: ventana.sesion() == ANA)


def test_sections_depend_on_the_role(qtbot, contado, puente):
    ventana = abrir(qtbot, puente, LUIS)
    assert ventana.secciones() == ["Dashboard", "Inventario", "Tareas de conteo", "Diferencias", "Movimientos", "Ajustes",
                                   "Auditoría", "Existencias", "Categorías", "Almacenes", "Sincronización", "Gráficas",
                                   "Perfil"]
    assert ventana.seccion_actual() == "Dashboard" and ventana.lbl_rol.text() == "Inventario"
    ventana.ir_a("Empleados")                                     # reservada al administrador: no se abre
    assert ventana.seccion_actual() == "Dashboard"
    dashboard, sync = ventana.vista("Dashboard"), ventana.vista("Sincronización")
    assert dashboard.btn_cerrar.isHidden() and sync.btn_procesar.isHidden() and sync.btn_reprocesar.isHidden()

    assert ventana.btn_avisos.isHidden()
    for reservada in ("Solicitudes", "Empleados", "Roles y permisos"):
        assert reservada not in ventana.secciones()

    ventana.cerrar_sesion()
    ventana.iniciar(ANA)
    assert {"Solicitudes", "Empleados", "Roles y permisos", "Configuración"} <= set(ventana.secciones())
    assert not dashboard.btn_cerrar.isHidden() and not sync.btn_procesar.isHidden()
    ventana.ir_a("Empleados")
    assert ventana.seccion_actual() == "Empleados" and ventana.paginas.currentWidget() is ventana.vista("Empleados")


def test_sidebar_collapses_and_profile_opens_from_the_footer(qtbot, contado, puente):
    ventana = abrir(qtbot, puente, ANA)
    assert ventana.lbl_avatar.text() == "A" and not ventana.lateral_contraida()
    assert not ventana.btn_avisos.isHidden()                     # el administrador ve la campana
    ventana.btn_cuenta.click()                                   # foto y nombre abren el perfil
    assert ventana.seccion_actual() == "Perfil"
    ancho = ventana._lateral.width()
    ventana.btn_colapsar.click()
    assert ventana.lateral_contraida() and ventana._lateral.width() < ancho and ventana.marca.isHidden()
    ventana.btn_colapsar.click()
    assert not ventana.lateral_contraida() and ventana._lateral.width() == ancho


def test_navigation_shows_each_page_and_toasts_work(qtbot, contado, puente):
    ventana = abrir(qtbot, puente, ANA)
    assert ventana.chip_bluetooth.text() == "Bluetooth: escuchando" and ventana.chip_oracle.text() == "Oracle: conectado"
    for titulo in ventana.secciones():
        ventana.ir_a(titulo)
        assert ventana.seccion_actual() == titulo and ventana.paginas.currentWidget().isVisible()
    assert ventana.combo_conteo.isHidden()                       # en Empleados el conteo no aplica
    ventana.ir_a("Inventario")
    assert not ventana.combo_conteo.isHidden()
    ventana.avisar("Sincronización lista: 3 lecturas recibidas")
    assert ventana.avisos_visibles() == ["Sincronización lista: 3 lecturas recibidas"]


# ------------------------------------------------------------------ dashboard
def test_dashboard_shows_the_scenario_figures(qtbot, contado, puente):
    v = abrir(qtbot, puente, ANA).vista("Dashboard")
    assert v.card_text("avance") == "80,0 %"
    assert v.card_text("exactitud") == "25,0 %"
    assert v.card_text("valor_faltante") == "-$ 5.000"
    assert v.card_text("valor_sobrante") == "$ 11.800"
    assert v.barra_clasificacion.segmentos() == [("OK", 1), ("FALTANTE", 1), ("SOBRANTE", 2), ("SIN_CONTAR", 1)]
    assert v.categorias() == [("Abarrotes", -3000.0), ("Aseo", 9000.0), ("Lácteos", 2800.0)]
    assert v.insignia.text() == "Abierto" and v.btn_cerrar.isEnabled() and v.banner.isHidden()
    assert "5 lecturas procesadas" in v.lbl_sync.text()


def test_closing_the_count_needs_confirmation_and_updates_the_figures(qtbot, cuentas, contado, puente, monkeypatch,
                                                                    auditoria_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")   # cerrar exige la cuenta viva
    v = abrir(qtbot, puente, ana).vista("Dashboard")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    v.btn_cerrar.click()
    assert v.card_text("avance") == "80,0 %" and v.btn_cerrar.isEnabled()      # cancelar no hace nada
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    v.btn_cerrar.click()
    esperar(qtbot, lambda: v.card_text("avance") == "100,0 %")
    assert v.card_text("exactitud") == "20,0 %" and v.card_text("valor_faltante") == "-$ 10.000"
    assert not v.btn_cerrar.isEnabled() and v.btn_cerrar.text() == "Conteo cerrado" and v.insignia.text() == "Cerrado"
    # Cerrar desde el Dashboard queda en la auditoría igual que desde Tareas.
    assert [(e.usuario, e.modulo, e.accion, e.detalle) for e in auditoria_db.listar(ana)][:1] == [
        ("ana.gomez", "tareas", "Cerró conteo", C)]


def test_kpi_card_reports_final_text_while_the_number_animates(qtbot, monkeypatch):
    monkeypatch.setattr(widgets, "ANIMAR", True)
    tarjeta = widgets.TarjetaKpi("Avance")
    qtbot.addWidget(tarjeta)
    tarjeta.set_valor(80.0, fmt_pct)
    assert tarjeta.texto() == "80,0 %"                           # el valor final se conoce de inmediato
    esperar(qtbot, lambda: tarjeta.texto_visible() == "80,0 %")  # y el número termina ahí tras contar


def test_custom_widgets_paint_in_every_state(qtbot):
    piezas = [widgets.Anillo("Avance"), widgets.BarraSegmentada(widgets.COLOR_CLASIFICACION), widgets.Dona(widgets.COLOR_CLASIFICACION),
              widgets.Pasos(["Uno", "Dos", "Tres"]), widgets.Indicador(), widgets.TarjetaKpi("Avance")]
    anillo, barra, dona, pasos, indicador, tarjeta = piezas
    for pieza in piezas:
        qtbot.addWidget(pieza)
        assert not pieza.grab().isNull()
    anillo.set_valor(62.5)
    barra.set_segmentos([("OK", 3), ("FALTANTE", 1), ("SIN_CONTAR", 0)])
    dona.set_datos([("OK", 3.0), ("FALTANTE", 1.0)])
    tarjeta.set_valor(1500.0, lambda v: f"$ {v:.0f}")
    for nombre in ("Uno", "Tres", None):
        pasos.set_actual(nombre)
        assert not pasos.grab().isNull()
    for modo in widgets.Indicador.MODOS:
        indicador.set_modo(modo)
        assert not indicador.grab().isNull()
    for pieza in piezas:
        assert not pieza.grab().isNull()


# ------------------------------------------------------------------ inventario
@pytest.fixture
def inventario(qtbot, contado):
    vista = InventarioView()
    qtbot.addWidget(vista)
    vista.set_conteo(C)
    esperar(qtbot, lambda: vista.table.model().rowCount() == 5)
    return vista


def visibles(vista):
    return [vista.modelo.fila(i).sku for i in range(vista.modelo.rowCount())]


def test_inventory_table_uses_es_co_format(inventario):
    modelo = inventario.modelo
    fila = [modelo.data(modelo.index(1, c)) for c in range(modelo.columnCount())]
    assert fila == ["A2", "Producto A2", "Abarrotes", "50", "45", "-5", "-10,0 %", "-$ 5.000", "FALTANTE"]
    sin_contar = [modelo.data(modelo.index(3, c)) for c in range(modelo.columnCount())]
    assert sin_contar[5:] == ["—", "—", "—", "SIN_CONTAR"]
    assert inventario.lbl_resumen.text() == "5 SKU · faltante -$ 5.000 · sobrante $ 11.800 · neto $ 8.800"


def test_inventory_chips_show_counts_and_filter(qtbot, inventario):
    v = inventario
    assert [v.chips[c].text() for c in ("Todas", "OK", "FALTANTE", "SOBRANTE", "SIN_CONTAR")] == [
        "Todas  5", "OK  1", "Faltante  1", "Sobrante  2", "Sin contar  1"]
    v.chips["SOBRANTE"].click()
    esperar(qtbot, lambda: visibles(v) == ["A3", "A5"])
    v.chips["Todas"].click()
    esperar(qtbot, lambda: len(visibles(v)) == 5)


def test_inventory_search_and_category(qtbot, inventario):
    v = inventario
    v.txt_buscar.setText("producto a3")
    esperar(qtbot, lambda: visibles(v) == ["A3"])
    v.txt_buscar.clear()
    esperar(qtbot, lambda: len(visibles(v)) == 5)
    v.combo_categoria.setCurrentText("Aseo")
    esperar(qtbot, lambda: visibles(v) == ["A3", "A4"])


def test_double_click_opens_the_readings_of_a_product(qtbot, inventario):
    inventario.abrir_detalle("A1")
    detalle = inventario.detalle
    esperar(qtbot, lambda: detalle.table.rowCount() == 2)
    assert [detalle.table.horizontalHeaderItem(c).text() for c in range(detalle.table.columnCount())] == [
        "Cantidad", "Operador", "Fecha (UTC)", "Vigente", "Nota"]
    assert [detalle.table.item(1, c).text() for c in (0, 1, 3)] == ["101", "Luis", "Sí"]
    assert detalle.table.item(0, 3).text() == "No (reemplazada)"


def test_inventory_exports_what_is_shown(qtbot, inventario, tmp_path):
    inventario.chips["FALTANTE"].click()
    esperar(qtbot, lambda: visibles(inventario) == ["A2"])
    ruta = tmp_path / "inventario.csv"
    inventario.exportar_csv(ruta)
    lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
    assert lineas[0].startswith("SKU;Producto;Categoría") and lineas[1:] == ["A2;Producto A2;Abarrotes;50;45;-5;-10;-5000;FALTANTE"]


# ------------------------------------------------------------------ gráficas
@pytest.fixture
def graficas(qtbot, contado):
    vista = ChartsView()
    qtbot.addWidget(vista)
    vista.set_conteo(C)
    esperar(qtbot, lambda: all(vista.bar_data(c) for c in CHART_IDS) and vista.serie("linea") != [])
    return vista


def test_six_charts_with_the_scenario_data(graficas):
    assert CHART_IDS == ("categoria", "desvios", "actividad") and EXTRA_IDS == ("dona", "histograma", "linea")
    assert graficas.bar_data("categoria") == [("Abarrotes", -3000.0), ("Aseo", 9000.0), ("Lácteos", 2800.0)]
    assert graficas.bar_data("desvios") == [("A3", 9000.0), ("A2", -5000.0), ("A5", 2800.0), ("A1", 2000.0)]
    assert graficas.bar_data("actividad") == [("Ana", 3.0), ("Luis", 2.0)]
    assert graficas.serie("dona") == [("OK", 1.0), ("FALTANTE", 1.0), ("SOBRANTE", 2.0), ("SIN_CONTAR", 1.0)]
    assert graficas.serie("linea") == [("2024-11-09 16:00", 5.0)]
    histograma = dict(graficas.serie("histograma"))
    assert histograma["-20 a -5 %"] == 1 and histograma["0 a 5 %"] == 1 and histograma["5 a 20 %"] == 1 and sum(histograma.values()) == 3
    for chart_id in CHART_IDS:                                   # una barra por dato
        barras = [i for i in graficas.plots[chart_id].getPlotItem().items if isinstance(i, pg.BarGraphItem)]
        assert len(barras) == 1 and len(barras[0].opts["x"]) == len(graficas.bar_data(chart_id)), chart_id


def test_charts_filter_by_category_and_top_n(qtbot, graficas):
    v = graficas
    assert [v.combo_categoria.itemText(i) for i in range(v.combo_categoria.count())] == ["Todas", "Abarrotes", "Aseo", "Lácteos"]
    v.combo_categoria.setCurrentText("Abarrotes")
    esperar(qtbot, lambda: v.bar_data("desvios") == [("A2", -5000.0), ("A1", 2000.0)])
    assert v.bar_data("categoria") == [("Abarrotes", -3000.0), ("Aseo", 9000.0), ("Lácteos", 2800.0)]  # el resumen no se filtra
    v.combo_categoria.setCurrentText("Todas")
    v.combo_top.setCurrentIndex(v.combo_top.findData(3))
    esperar(qtbot, lambda: v.bar_data("desvios") == [("A3", 9000.0), ("A2", -5000.0), ("A5", 2800.0)])


def test_bars_keep_their_data_while_they_grow(qtbot, contado, monkeypatch):
    monkeypatch.setattr(widgets, "ANIMAR", True)
    vista = ChartsView()
    qtbot.addWidget(vista)
    vista.set_conteo(C)
    esperar(qtbot, lambda: vista.bar_data("categoria") != [])
    assert vista.bar_data("categoria") == [("Abarrotes", -3000.0), ("Aseo", 9000.0), ("Lácteos", 2800.0)]
    esperar(qtbot, lambda: vista.alturas_dibujadas("categoria") == [-3000.0, 9000.0, 2800.0])


def test_crowded_chart_abbreviates_labels():
    assert _fmt_corto(1029000) == "$ 1,0 M" and _fmt_corto(-155800) == "-$ 156 mil" and _fmt_corto(-5000) == "-$ 5.000"
    assert _etiqueta_eje("7701234000037") == "…0037" and _etiqueta_eje("A3") == "A3"


@pytest.mark.parametrize("fabrica", [ChartsView, DashboardView, InventarioView])
def test_views_show_sin_datos_and_database_errors(qtbot, contado, monkeypatch, fabrica):
    vista = fabrica()
    qtbot.addWidget(vista)
    vista.set_conteo(None)
    assert vista.banner.text() == "Sin datos" and not vista.banner.isHidden()
    original, estado = dbq.fetch_dif_por_categoria, {"falla": True}

    def inestable(*args, **kwargs):
        if estado["falla"]:
            raise RuntimeError("ORA-12541: TNS:no listener")
        return original(*args, **kwargs)

    monkeypatch.setattr(dbq, "fetch_dif_por_categoria", inestable)
    vista.set_conteo(C)
    esperar(qtbot, lambda: not vista.banner.isHidden() and "ORA-12541" in vista.banner.text())
    estado["falla"] = False
    vista.banner.btn_reintentar.click()                          # «Reintentar» vuelve a consultar
    esperar(qtbot, lambda: vista.banner.isHidden())


def test_no_query_runs_on_the_ui_thread(qtbot, contado, puente, monkeypatch):
    hilos = {}
    nombres = ("fetch_conteos", "fetch_resumen", "fetch_conciliacion", "fetch_dif_por_categoria", "fetch_top_desvios",
               "fetch_distribucion", "fetch_actividad", "fetch_estado_batch", "fetch_errores")
    for nombre in nombres:
        original = getattr(dbq, nombre)

        def envoltura(*a, _o=original, _n=nombre, **k):
            hilos.setdefault(_n, set()).add(threading.current_thread())
            return _o(*a, **k)

        monkeypatch.setattr(dbq, nombre, envoltura)
    ventana = abrir(qtbot, puente, ANA)
    esperar(qtbot, lambda: all(ventana.vista("Gráficas").bar_data(c) for c in CHART_IDS))
    esperar(qtbot, lambda: ventana.vista("Inventario").modelo.rowCount() == 5)
    esperar(qtbot, lambda: set(hilos) == set(nombres))
    for nombre, conjunto in hilos.items():
        assert threading.main_thread() not in conjunto, f"{nombre} corrió en el hilo de la interfaz"


# ------------------------------------------------------------------ sincronización (servicio aparte, Fase 5)
@pytest.fixture
def sync(qtbot, puente):
    vista = SyncView(puente)
    qtbot.addWidget(vista)
    vista.set_sesion(ANA)
    return vista, puente


def test_sync_shows_the_service_state(qtbot, sync):
    vista, remoto = sync
    assert vista.lbl_estado.text().startswith("Servicio Bluetooth activo · visible como «gestion_inventario»")
    assert "gestion_inventario" in vista.lbl_ayuda.text() and vista.pasos.actual() == "Esperando"
    assert vista.indicador.modo() == "radar" and vista.lbl_codigo.isHidden() and vista.btn_aceptar.isHidden()
    assert vista.lbl_ultima.text() == "Aún no ha llegado ninguna sincronización."
    remoto.poner(estado="DETENIDO")
    assert vista.lbl_estado.text() == "El servicio Bluetooth no está corriendo"
    assert "docker compose up -d bluetooth" in vista.lbl_ayuda.text() and vista.btn_pausar.isHidden()
    remoto.poner(estado="PAUSANDO")
    assert vista.lbl_estado.text().startswith("Pausando") and vista.btn_pausar.text() == "Reanudar"


def test_pausar_y_reanudar_el_servicio(qtbot, sync):
    vista, remoto = sync
    assert vista.btn_pausar.text() == "Pausar" and not vista.btn_pausar.isHidden()
    vista.btn_pausar.click()
    assert remoto.pausas == ["ana.gomez"] and vista.lbl_estado.text().startswith("Servicio Bluetooth en pausa")
    assert vista.btn_pausar.text() == "Reanudar"
    vista.btn_pausar.click()
    assert remoto.reanudaciones == ["ana.gomez"] and vista.btn_pausar.text() == "Pausar"


def test_sin_gestion_en_bluetooth_no_hay_pausa(qtbot, puente):
    vista = SyncView(puente)
    qtbot.addWidget(vista)
    vista.set_sesion(Sesion("x", "X", INVENTARIO, (("bluetooth", "CONSULTA"), ("perfil", "GESTION"))))
    assert vista.btn_pausar.isHidden()


def test_el_codigo_se_acepta_desde_el_pc(qtbot, sync):
    vista, remoto = sync
    remoto.poner(estado="CONFIRMAR_CODIGO", codigo="123456")
    assert vista.lbl_codigo.text() == "123456" and not vista.btn_aceptar.isHidden()
    vista.btn_aceptar.click()
    assert remoto.respuestas == [True]


def test_a_full_sync_shows_progress_and_refreshes_everything(qtbot, contado, puente):
    ventana = abrir(qtbot, puente, ANA)
    vista = ventana.vista("Sincronización")
    refrescos = []
    ventana.refresh_requested.connect(lambda: refrescos.append(1))
    puente.poner(estado="RECIBIENDO", recibidos=3)
    assert vista.lbl_recibidos.text() == "Lecturas recibidas: 3" and vista.lbl_estado.text().startswith("Recibiendo")
    assert ventana.chip_bluetooth.text() == "Bluetooth: recibiendo"
    puente.terminar_sync(3, "Bodega 1")
    assert vista.lbl_ultima.text().startswith("Última sincronización: Bodega 1, 3 lecturas")
    esperar(qtbot, lambda: len(refrescos) >= 1)                  # llegaron datos: las páginas vuelven a consultar
    assert ventana.avisos_visibles() == ["Sincronización lista: 3 lecturas recibidas"]


def test_bluetooth_unavailable_shows_a_message_not_a_crash(qtbot, sync):
    vista, remoto = sync
    remoto.poner(estado="ERROR", ultimo_error="Bluetooth bloqueado. Ejecuta: rfkill unblock bluetooth")
    assert "Bluetooth no disponible" in vista.lbl_estado.text()
    assert "rfkill unblock bluetooth" in vista.lbl_aviso.text() and vista.indicador.modo() == "error"


def test_sync_lists_error_rows_and_reprocesses_them_off_the_ui_thread(qtbot, escenario, sync, monkeypatch):
    vista, *_ = sync
    escenario.cargar_lecturas()
    conn = connect()
    try:
        staging(conn, "tst-m1", 1, T0, C, "ZZ9", 1)              # SKU_DESCONOCIDO
        staging(conn, "tst-m2", 1, T0, C, "A1", "1,5")           # CANTIDAD_INVALIDA
        dbq.procesar_ahora()
    finally:
        conn.close()
    vista.refresh()
    esperar(qtbot, lambda: len(vista.errores()) == 2)
    assert [vista.combo_motivo.itemText(i) for i in range(vista.combo_motivo.count())] == [
        "Todos los motivos", "CANTIDAD_INVALIDA", "SKU_DESCONOCIDO"]
    vista.combo_motivo.setCurrentText("SKU_DESCONOCIDO")
    assert [e[:3] for e in vista.errores()] == [("tst-m1", "1", "SKU_DESCONOCIDO")]
    assert "2 con error" in vista.lbl_ultimo_run.text()

    hilos, cambios = [], []
    original = dbq.reprocesar_errores
    monkeypatch.setattr(dbq, "reprocesar_errores", lambda *a: (hilos.append(threading.current_thread()), original(*a))[1])
    vista.datos_cambiados.connect(lambda: cambios.append(1))
    vista.btn_reprocesar.click()
    assert not vista.btn_reprocesar.isEnabled() and not vista.btn_procesar.isEnabled()   # no se lanza otra a la vez
    esperar(qtbot, lambda: cambios == [1])
    assert hilos and threading.main_thread() not in hilos and vista.btn_reprocesar.isEnabled()


def test_closing_the_window_or_logging_out_does_not_pause_the_service(qtbot, contado, puente):
    ventana = abrir(qtbot, puente, ANA)
    ventana.cerrar_sesion()                    # el servicio corre aparte: sigue recibiendo sin sesión abierta
    ventana.iniciar(ANA)
    ventana.close()
    assert puente.pausas == [] and puente.status()["estado"] == "ESPERANDO_EMPAREJAMIENTO"


# ------------------------------------------------------------------ perfil y usuarios
def test_profile_shows_the_session_and_changes_the_password(qtbot, cuentas):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    vista = PerfilView()
    qtbot.addWidget(vista)
    vista.set_sesion(ana)
    assert (vista.lbl_nombre.text(), vista.lbl_usuario.text(), vista.lbl_rol.text()) == ("Ana Gómez", "@ana.gomez", "Administrador")
    salidas = []
    vista.cerrar_sesion.connect(lambda: salidas.append(1))
    vista.btn_salir.click()
    assert salidas == [1]
    vista.txt_actual.setText("otra12345")
    vista.txt_nueva.setText("nueva2027")
    vista.txt_confirmacion.setText("nueva2027")
    vista.btn_cambiar.click()
    esperar(qtbot, lambda: "actual no es correcta" in vista.lbl_resultado.text())
    vista.txt_actual.setText("conteo2026")
    vista.btn_cambiar.click()
    esperar(qtbot, lambda: vista.lbl_resultado.text() == "Contraseña cambiada.")
    assert vista.txt_nueva.text() == "" and cuentas.iniciar_sesion("ana.gomez", "nueva2027") == ana


def _respuesta(monkeypatch, texto, ok=True):
    """El diálogo de texto (motivo o contraseña) responde ``texto`` sin abrirse."""
    monkeypatch.setattr("PyQt6.QtWidgets.QInputDialog.getText", lambda *a, **k: (texto, ok))


def test_admin_manages_accounts_from_the_users_page(qtbot, cuentas, monkeypatch):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    cuentas.registrar("marta", "Marta Ruiz", "conteo2026", "conteo2026")    # pendiente: vive en Solicitudes
    vista = UsuariosView()
    qtbot.addWidget(vista)
    vista.set_sesion(ana)
    esperar(qtbot, lambda: vista.filas() == [("ana.gomez", "Ana Gómez", "Administrador", "Activa"),
                                             ("luis", "Luis Ortiz", "Inventario", "Activa")])
    assert not vista.btn_rol.isEnabled()                         # sin fila elegida no hay acción
    vista.seleccionar("luis")
    assert vista.btn_rol.text() == "Hacer administrador" and vista.btn_estado.text() == "Suspender"
    _respuesta(monkeypatch, "", ok=True)                         # sin motivo no se suspende
    vista.btn_estado.click()
    qtbot.wait(200)
    assert vista.filas()[1][3] == "Activa"
    _respuesta(monkeypatch, "Vacaciones")
    vista.btn_estado.click()
    esperar(qtbot, lambda: vista.filas()[1][3] == "Suspendida")
    with pytest.raises(auth.CuentaSinAcceso):
        cuentas.iniciar_sesion("luis", "conteo2026")
    vista.seleccionar("luis")
    assert vista.btn_estado.text() == "Reactivar"
    vista.btn_estado.click()
    esperar(qtbot, lambda: vista.filas()[1][3] == "Activa")
    vista.restablecer("luis", "nueva2027")
    esperar(qtbot, lambda: vista._runner.pendientes == 0)   # corre en otro hilo: que termine antes de usar la clave
    vista.seleccionar("luis")
    vista.btn_rol.click()
    esperar(qtbot, lambda: vista.filas()[1][2] == "Administrador")
    assert cuentas.iniciar_sesion("luis", "nueva2027").rol == ADMIN
    vista.seleccionar("ana.gomez")
    vista.btn_rol.click()
    esperar(qtbot, lambda: vista.filas()[0][2] == "Inventario")


def test_users_page_filters_by_role_state_and_text(qtbot, cuentas, monkeypatch):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    for usuario, nombre in (("luis", "Luis Ortiz"), ("marta", "Marta Ruiz")):
        cuentas.registrar(usuario, nombre, "conteo2026", "conteo2026")
        cuentas.aprobar(ana, usuario, INVENTARIO)
    cuentas.suspender(ana, "marta", "Licencia")
    vista = UsuariosView()
    qtbot.addWidget(vista)
    vista.set_sesion(ana)
    esperar(qtbot, lambda: len(vista.filas()) == 3)
    vista.combo_estado.setCurrentIndex(vista.combo_estado.findData(auth.SUSPENDIDO))
    assert [f[0] for f in vista.filas()] == ["marta"]
    vista.combo_estado.setCurrentIndex(0)
    vista.combo_rol.setCurrentIndex(vista.combo_rol.findData(ADMIN))
    assert [f[0] for f in vista.filas()] == ["ana.gomez"]
    vista.combo_rol.setCurrentIndex(0)
    vista.txt_buscar.setText("ortiz")
    assert [f[0] for f in vista.filas()] == ["luis"]


def test_users_page_stays_empty_for_a_non_admin(qtbot, cuentas):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    luis = Sesion("luis", "Luis Ortiz", INVENTARIO)
    vista = UsuariosView()
    qtbot.addWidget(vista)
    vista.set_sesion(luis)
    qtbot.wait(300)
    assert vista.filas() == []                                   # ni siquiera consulta la lista


def test_new_account_waits_for_the_admin_and_a_forgotten_password_is_approved(qtbot, cuentas, monkeypatch):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    acceso = AccesoView()
    qtbot.addWidget(acceso)
    acceso.show()
    acceso.btn_ir_a_registro.click()
    acceso.txt_nombre.setText("Luis Ortiz")
    acceso.txt_usuario_nuevo.setText("luis")
    acceso.txt_clave_nueva.setText("conteo2026")
    acceso.txt_confirmacion.setText("conteo2026")
    entradas, estados = [], []
    acceso.entro.connect(entradas.append)
    acceso.sin_acceso.connect(estados.append)
    acceso.btn_crear.click()
    esperar(qtbot, lambda: bool(estados))
    assert entradas == [] and estados[0].estado == auth.PENDIENTE and estados[0].nombre == "Luis Ortiz"

    vista = SolicitudesView()
    qtbot.addWidget(vista)
    vista.set_sesion(ana)
    esperar(qtbot, lambda: vista.filas_cuentas() == [("luis", "Luis Ortiz")])
    assert vista.pendientes() == 1 and not vista.btn_aprobar_cuenta.isEnabled()
    vista.elegir_cuenta("luis")
    vista.combo_rol.setCurrentIndex(vista.combo_rol.findData(INVENTARIO))
    vista.btn_aprobar_cuenta.click()
    esperar(qtbot, lambda: vista.filas_cuentas() == [])
    assert cuentas.iniciar_sesion("luis", "conteo2026").rol == INVENTARIO
    esperar(qtbot, lambda: vista.filas_historial() == [("luis", "Luis Ortiz", "Aprobada", "Inventario", "", "ana.gomez")])

    acceso.btn_ir_a_olvido.click()
    assert acceso.formularios.currentIndex() == 2
    acceso.txt_usuario_olvido.setText("luis")
    acceso.txt_clave_olvido.setText("nueva2027")
    acceso.txt_confirmacion_olvido.setText("nueva2027")
    acceso.btn_pedir_clave.click()
    esperar(qtbot, lambda: "Solicitud enviada" in acceso.lbl_error.text())
    vista.refresh()
    esperar(qtbot, lambda: vista.filas_claves() == [("luis", "Luis Ortiz", "Inventario")])
    vista.elegir_clave("luis")
    vista.btn_aprobar.click()
    esperar(qtbot, lambda: vista.filas_claves() == [])
    assert cuentas.iniciar_sesion("luis", "nueva2027").usuario == "luis"


def test_solicitudes_rechazar_pide_motivo(qtbot, cuentas, monkeypatch):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    vista = SolicitudesView()
    qtbot.addWidget(vista)
    vista.set_sesion(ana)
    esperar(qtbot, lambda: vista.filas_cuentas() == [("luis", "Luis Ortiz")])
    vista.elegir_cuenta("luis")
    llamadas = []
    with monkeypatch.context() as m:                             # solo aquí: la fixture cuentas también usa monkeypatch
        m.setattr(auth, "rechazar", lambda *a: llamadas.append(a))
        for respuesta in (("   ", True), ("Duplicada", False)):  # vacío o cancelado: no se llama a auth
            _respuesta(m, *respuesta)
            vista.btn_rechazar_cuenta.click()
        qtbot.wait(200)
    assert llamadas == []
    _respuesta(monkeypatch, "Duplicada")
    vista.elegir_cuenta("luis")
    vista.btn_rechazar_cuenta.click()
    esperar(qtbot, lambda: vista.filas_historial() == [("luis", "Luis Ortiz", "Rechazada", "", "Duplicada", "ana.gomez")])


def test_login_de_cuenta_rechazada_abre_estado_cuenta(qtbot, cuentas, puente):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.rechazar(ana, "luis", "Duplicada")
    ventana = build_window(puente, auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    ventana.show()
    ventana.acceso.txt_usuario.setText("luis")
    ventana.acceso.txt_clave.setText("conteo2026")
    ventana.acceso.btn_entrar.click()
    esperar(qtbot, lambda: ventana.estado_cuenta.isVisible())
    assert ventana.sesion() is None
    assert ventana.estado_cuenta.lbl_motivo.text() == "Motivo: Duplicada"
    assert ventana.estado_cuenta.btn_volver.text() == "Regresar al inicio de sesión"
    ventana.estado_cuenta.btn_volver.click()
    assert ventana.acceso.isVisible() and ventana.acceso.txt_clave.text() == ""


def test_la_sesion_lleva_los_permisos_de_oracle(qtbot, cuentas, permisos_db, puente):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    permisos_db.guardar(ana, INVENTARIO, "reportes", permisos_db.NINGUNO)
    luis = cuentas.iniciar_sesion("luis", "conteo2026")
    assert not luis.puede("reportes") and luis.puede("existencias")
    ventana = build_window(puente, auto_refresh_ms=0, sesion=luis)
    qtbot.addWidget(ventana)
    assert "Gráficas" not in ventana.secciones() and "Inventario" in ventana.secciones()


# ------------------------------------------------------------------ correcciones de la revisión final
def _movil(usuario, estado="PENDIENTE", rol=None):
    with dbq._conexion() as conn:
        conn.cursor().execute("INSERT INTO usuarios_tst (usuario, nombre, rol, clave_hash, estado, origen) "
                              "VALUES (:u, 'Operador Móvil', :r, '-', :e, 'MOVIL')", u=usuario, r=rol, e=estado)
        conn.commit()


def test_solicitudes_conserva_a_la_persona_elegida_al_refrescar(qtbot, cuentas):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("marta", "Marta Ruiz", "conteo2026", "conteo2026")
    vista = SolicitudesView()
    qtbot.addWidget(vista)
    vista.set_sesion(ana)
    esperar(qtbot, lambda: vista.filas_cuentas() == [("marta", "Marta Ruiz")])
    vista.elegir_cuenta("marta")
    cuentas.registrar("alba", "Alba Pérez", "conteo2026", "conteo2026")   # llega otra que se ordena antes
    vista.refresh()
    esperar(qtbot, lambda: len(vista.filas_cuentas()) == 2)
    vista.btn_aprobar_cuenta.click()
    esperar(qtbot, lambda: vista.filas_cuentas() == [("alba", "Alba Pérez")])   # se aprobó a Marta, no a Alba


def test_solicitudes_ofrece_roles_segun_el_origen(qtbot, cuentas):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("marta", "Marta Ruiz", "conteo2026", "conteo2026")
    _movil("op.movil")
    vista = SolicitudesView()
    qtbot.addWidget(vista)
    vista.set_sesion(ana)
    esperar(qtbot, lambda: len(vista.filas_cuentas()) == 2)
    roles = lambda: [vista.combo_rol.itemData(i) for i in range(vista.combo_rol.count())]
    vista.elegir_cuenta("op.movil")
    assert roles() == [auth.OPERADOR]
    vista.elegir_cuenta("marta")
    assert roles() == [ADMIN, INVENTARIO] and vista.combo_rol.currentData() == INVENTARIO


def test_empleados_operador_no_se_hace_admin_y_se_desvincula(qtbot, cuentas):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    _movil("op.movil", estado="ACTIVO", rol="OPERADOR")
    with dbq._conexion() as conn:
        conn.cursor().execute("UPDATE usuarios_tst SET uuid_dispositivo = 'tel-1' WHERE usuario = 'op.movil'")
        conn.commit()
    vista = UsuariosView()
    qtbot.addWidget(vista)
    vista.set_sesion(ana)
    esperar(qtbot, lambda: len(vista.filas()) == 2)
    vista.seleccionar("op.movil")
    assert vista.btn_rol.isHidden()
    assert not vista.btn_telefono.isHidden() and vista.btn_telefono.isEnabled()
    vista.btn_telefono.click()
    esperar(qtbot, lambda: not vista.btn_telefono.isEnabled())
    vista.seleccionar("ana.gomez")
    assert not vista.btn_rol.isHidden() and vista.btn_telefono.isHidden()


def test_sin_dashboard_entra_a_la_primera_seccion_permitida(qtbot, puente):
    ventana = build_window(puente, auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    sin_dashboard = Sesion("luis", "Luis Ortiz", INVENTARIO, (("dashboard", "NINGUNO"), ("existencias", "GESTION"),
                                                              ("perfil", "GESTION")))
    ventana.iniciar(sin_dashboard)
    assert ventana.seccion_actual() == "Existencias"      # «Inventario» (conciliación) es el módulo «conteos», sin acceso aquí
    assert ventana.paginas.currentWidget() is ventana.vista("Existencias")


def test_al_cerrar_sesion_se_vacian_las_vistas_de_administracion(qtbot, cuentas, puente):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("marta", "Marta Ruiz", "conteo2026", "conteo2026")
    ventana = build_window(puente, auto_refresh_ms=0, sesion=ana)
    qtbot.addWidget(ventana)
    esperar(qtbot, lambda: bool(ventana.vista("Empleados").filas() and ventana.vista("Solicitudes").filas_cuentas()))
    ventana.cerrar_sesion()
    assert ventana.vista("Empleados").filas() == [] and ventana.vista("Solicitudes").filas_cuentas() == []
    assert ventana.vista("Solicitudes").filas_historial() == [] and ventana.vista("Roles y permisos").tabla.rowCount() == 0
