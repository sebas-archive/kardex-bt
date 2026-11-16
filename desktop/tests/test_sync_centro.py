"""Centro de control de Sincronización: modelos derivados del estado real, datos de Oracle y componentes visuales."""

from datetime import datetime

import pytest

from app import db, sync_datos
from app.auth import ADMIN, PREGUNTAS
from app.models import ErrorFila
from app.servicio import UltimaSync
from app.views import sync as vista_sync
from app.views import sync_ui, widgets
from app.views.sync import SyncView, modelo_etapas, modelo_flujo
from conftest import connect, staging
from fakes import FakeRemoto

CLAVE = "conteo2026"
C = db.conteo_actual()
T0 = 1731170400000


def esperar(qtbot, condicion):
    qtbot.waitUntil(condicion, timeout=15000)


@pytest.fixture
def admin(cuentas):
    return cuentas.registrar("ana.gomez", "Ana Gómez", CLAVE, CLAVE, correo="ana@example.com",
                             pregunta=PREGUNTAS[0], respuesta="firulais")


def _vista(qtbot, sesion, **status):
    r = FakeRemoto(**status)
    v = SyncView(r)
    qtbot.addWidget(v)
    v.show()
    v.set_sesion(sesion)
    return v, r


def _st(estado, **extra):
    return {"estado": estado, "ultimo_error": None, "ultima": None, **extra}


# ------------------------------------------------------------------ modelos puros
def test_etapas_siguen_el_estado_real():
    assert modelo_etapas("ESPERANDO_EMPAREJAMIENTO") == (0, 0, None)
    assert modelo_etapas("CONECTADO") == (1, 1, None)
    assert modelo_etapas("RECIBIENDO") == (2, 2, None)
    assert modelo_etapas("PROCESANDO") == (3, 3, None)
    assert modelo_etapas("LISTO") == (None, 5, None)
    assert modelo_etapas("PAUSADO") == (None, 0, None)
    assert modelo_etapas("DETENIDO") == (None, 0, None)


def test_etapas_marcan_el_error_donde_ocurrio():
    assert modelo_etapas("ERROR", 2) == (None, 2, 2)
    assert modelo_etapas("ERROR", None) == (None, 0, 0)


def test_flujo_con_bluetooth_pausado_no_mueve_paquetes():
    m = modelo_flujo(_st("PAUSADO"), True, False, None, None, None)
    assert m["enlaces"][:2] == ["off", "off"] and "activo" not in m["enlaces"][:2]
    assert m["nodos"][1]["tono"] == "pausa" and m["error"] is None


def test_flujo_recibiendo_activa_los_dos_primeros_enlaces():
    ultima = UltimaSync(datetime.now(), 3, "Pixel")
    m = modelo_flujo(_st("RECIBIENDO", ultima=ultima), True, False, None, None, None)
    assert m["enlaces"] == ["activo", "activo", "enlazado"]
    assert m["nodos"][0]["detalle"] == "Pixel" and m["nodos"][0]["tono"] == "ok"


def test_flujo_procesando_activa_solo_oracle():
    m = modelo_flujo(_st("PROCESANDO"), True, False, None, None, None)
    assert m["enlaces"] == ["enlazado", "enlazado", "activo"]
    assert modelo_flujo(_st("PAUSADO"), True, True, None, None, None)["enlaces"][2] == "activo"  # «Procesar ahora»


def test_flujo_error_no_representa_transferencia_exitosa():
    m = modelo_flujo(_st("ERROR", ultimo_error="BATCH: x"), True, False, None, None, None)
    assert m["error"] == 2 and m["enlaces"][:2] == ["off", "off"] and m["nodos"][2]["tono"] == "error"
    m = modelo_flujo(_st("ERROR", ultimo_error="SESION: x"), True, False, None, None, None)
    assert m["error"] == 1
    m = modelo_flujo(_st("RECIBIENDO"), False, False, None, None, None)   # Oracle caído
    assert m["error"] == 3 and m["enlaces"][2] == "off"


def test_velocidad_proporcional_al_trafico_real():
    lento = modelo_flujo(_st("RECIBIENDO"), True, False, None, None, 1.0)["velocidad"]
    rapido = modelo_flujo(_st("RECIBIENDO"), True, False, None, None, 20.0)["velocidad"]
    assert modelo_flujo(_st("RECIBIENDO"), True, False, None, None, None)["velocidad"] == 1.0
    assert lento < rapido <= 2.5


def test_estado_bluetooth_y_motivos():
    assert vista_sync.estado_bluetooth("PAUSADO")[0] == "pausa"
    assert vista_sync.estado_bluetooth("ERROR", "SESION: x")[0] == "error"
    assert vista_sync.estado_bluetooth("ERROR", "BATCH: x")[0] == "ok"   # falló Oracle, no el canal
    assert vista_sync.motivo_legible("SKU_DESCONOCIDO") == "SKU desconocido"


# ------------------------------------------------------------------ componentes
def test_odometro_expone_el_dato_al_instante(qtbot, monkeypatch):
    monkeypatch.setattr(widgets, "ANIMAR", True)
    o = sync_ui.Odometro(0)
    qtbot.addWidget(o)
    o.set_valor(1234)
    assert o.valor() == 1234 and o.texto() == "1.234"   # aunque el dibujo aún ruede
    o.grab()


def test_escala_del_eje():
    assert sync_ui.escala_agradable(0) == 4 and sync_ui.escala_agradable(13) == 20
    assert sync_ui.escala_agradable(100) == 100 and sync_ui.escala_agradable(101) == 200


def test_grafica_sin_datos_muestra_estado_vacio_no_ceros(qtbot):
    g = sync_ui.GraficaActividad()
    qtbot.addWidget(g)
    g.resize(500, 260)
    g.set_actividad(sync_datos.Actividad("1h", 5, [0] * 12, [0] * 12, [0] * 12))
    assert g.vacia()
    g.grab()
    g.set_actividad(sync_datos.Actividad("1h", 5, [0, 3] + [0] * 10, [0, 2] + [0] * 10, [0] * 12))
    assert not g.vacia() and g.valores("recibidas")[1] == 3 and len(g.etiquetas()) == 12
    g.grab()


def test_etapas_widget_guarda_su_estado(qtbot):
    e = sync_ui.Etapas()
    qtbot.addWidget(e)
    e.set_estado(2, 2, None)
    assert e.estado() == (2, 2, None)
    e.set_estado(None, 2, 2)
    assert e.estado() == (None, 2, 2)
    e.resize(700, 90)
    e.grab()


# ------------------------------------------------------------------ datos reales de Oracle
def test_actividad_y_contadores_salen_de_oracle(admin, escenario):
    antes = sync_datos.fetch_contadores_dia()
    conn = connect()
    try:
        staging(conn, "tst-centro", 1, T0, C, "A1", 5)
        staging(conn, "tst-centro", 2, T0, C, "ZZ9", 1)
        db.procesar_ahora()
    finally:
        conn.close()
    act = sync_datos.fetch_actividad("15m")
    assert len(act.recibidas) == 15 and not act.vacia
    assert sum(act.recibidas) >= 2 and sum(act.procesadas) >= 1 and sum(act.errores) >= 1
    despues = sync_datos.fetch_contadores_dia()
    assert despues.recibidas >= antes.recibidas + 2 and despues.errores >= 1
    assert sync_datos.lecturas_por_minuto(act) > 0
    for rango, (minutos, paso, _) in sync_datos.RANGOS.items():
        assert len(sync_datos.fetch_actividad(rango).recibidas) == minutos // paso


def test_sin_actividad_no_hay_tasa():
    vacia = sync_datos.Actividad("1h", 5, [0] * 12, [0] * 12, [0] * 12)
    assert sync_datos.lecturas_por_minuto(vacia) is None and sync_datos.lecturas_por_minuto(None) is None


# ------------------------------------------------------------------ la pantalla
def test_pausado_y_activo_cambian_texto_icono_y_boton(qtbot, admin, escenario):
    v, r = _vista(qtbot, admin, estado="PAUSADO")
    assert v.lbl_estado.text() == "El servicio Bluetooth está pausado"
    assert v.btn_pausar.text() == "Reanudar servicio" and v.icono.modo() == "pausado"
    assert v.pill_bluetooth.tono() == "pausa" and v.flujo.enlaces()[:2] == ["off", "off"]
    assert v.etapas.estado() == (None, 0, None)
    v.btn_pausar.click()   # reanuda (el FakeRemoto pasa a ESPERANDO_EMPAREJAMIENTO)
    assert r.reanudaciones == ["ana.gomez"]
    assert v.btn_pausar.text() == "Pausar servicio" and v.icono.modo() == "buscando"
    assert v.lbl_ayuda.text() == "Buscando dispositivos..."
    r.poner(estado="RECIBIENDO", recibidos=7)
    assert v.icono.modo() == "activo" and v.etapas.estado() == (2, 2, None)
    assert v.flujo.enlaces()[:2] == ["activo", "activo"] and v.pill_bluetooth.tono() == "ok"


def test_error_marca_etapa_y_nodo(qtbot, admin, escenario):
    v, r = _vista(qtbot, admin, estado="RECIBIENDO")
    r.poner(estado="ERROR", ultimo_error="SESION: se cortó")
    assert v.etapas.estado() == (None, 2, 2) and v.flujo.error() == 1
    assert v.icono.modo() == "error" and v.pill_bluetooth.tono() == "error"


def test_tabla_con_errores_y_estado_vacio(qtbot, admin, escenario):
    v, _ = _vista(qtbot, admin)
    esperar(qtbot, lambda: v._batch is not None)
    assert v.pila.currentWidget() is v.vacio
    assert v.vacio.lbl_titulo.text() == "Todo está en orden"
    assert v.lbl_cuenta.text() == "Sin errores pendientes"
    errs = [ErrorFila(1, "tel-1", 4, "ZZ1", "2", "SKU_DESCONOCIDO", datetime.now())]
    v._aplicar_errores(errs)
    assert v.pila.currentWidget() is v.tabla_errores
    assert v.lbl_cuenta.text() == "1 error pendiente"
    fila = v.errores()[0]
    assert fila == ("tel-1", "4", "ZZ1", "SKU desconocido", f"{errs[0].fecha_recepcion:%d/%m/%Y %H:%M}",
                    "Con error", "Dar de alta")
    v._aplicar_errores([])
    assert v.pila.currentWidget() is v.vacio


def test_filas_resueltas_se_desvanecen_y_no_se_quitan_las_demas(qtbot, admin, escenario, monkeypatch):
    monkeypatch.setattr(widgets, "ANIMAR", True)
    v, _ = _vista(qtbot, admin)
    esperar(qtbot, lambda: v._batch is not None)
    uno = ErrorFila(1, "tel-1", 1, "ZZ1", "1", "SKU_DESCONOCIDO", datetime.now())
    dos = ErrorFila(2, "tel-1", 2, "ZZ2", "1", "CANTIDAD_INVALIDA", datetime.now())
    v._aplicar_errores([uno, dos])
    v.tabla_errores.desvanecer_filas([0], lambda: v._aplicar_errores([dos]))
    esperar(qtbot, lambda: len(v.errores()) == 1)
    assert v.errores()[0][2] == "ZZ2"


def test_oracle_caido_se_ve_en_la_pildora(qtbot, admin, escenario, monkeypatch):
    def falla(rango):
        raise RuntimeError("sin conexión")

    monkeypatch.setattr(vista_sync, "_cargar_todo", falla)
    v, _ = _vista(qtbot, admin)
    esperar(qtbot, lambda: v.pill_oracle.tono() == "error")
    assert v.flujo.error() == 3 and not v.btn_actualizar.girando()


def test_cambiar_rango_pide_los_datos_de_ese_rango(qtbot, admin, escenario):
    v, _ = _vista(qtbot, admin)
    esperar(qtbot, lambda: v.grafica.actividad() is not None)
    v.botones_rango["24h"].click()
    esperar(qtbot, lambda: v.grafica.actividad() is not None and v.grafica.actividad().rango == "24h")
    assert len(v.grafica.valores("recibidas")) == 24


def test_la_ventana_no_repite_su_cabecera_en_sincronizacion(qtbot):
    from app.auth import Sesion
    from app.main import build_window

    ventana = build_window(FakeRemoto(), auto_refresh_ms=0)
    ventana.comprobar_oracle = lambda: None
    ventana.contar_notificaciones = lambda: None
    qtbot.addWidget(ventana)
    ventana.show()
    ventana.iniciar(Sesion("ana.gomez", "Ana Gómez", ADMIN, correo="ana@example.com"))
    ventana.ir_a("Sincronización")
    assert ventana.seccion_actual() == "Sincronización"
    assert not ventana.btn_actualizar.isVisible() and not ventana.chip_oracle.isVisible()
    ventana.ir_a("Dashboard")
    assert ventana.btn_actualizar.isVisible() and ventana.chip_oracle.isVisible()
