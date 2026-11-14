"""El servicio Bluetooth independiente (Fase 5): un bucle que mantiene abierta la recepción, escribe su estado en
``SERVICIO_BT`` y obedece la pausa y la respuesta al código que deja el escritorio."""

import pytest

from btsync import servicio
from btsync.controller import CONFIRMAR_CODIGO, ESPERANDO_EMPAREJAMIENTO, IDLE, RECIBIENDO, SyncController
from conftest import connect
from test_controller import FakeStore, FakeTransport, acct, end, hello, rec, wait_for


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def tabla(monkeypatch):
    monkeypatch.setattr(servicio, "TABLA", "servicio_bt_tst")
    conn = connect()
    servicio.migrar(conn)
    conn.cursor().execute("DELETE FROM servicio_bt_tst")
    conn.commit()
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def armar(tabla):
    creados = []

    def build(transport=None, discoverable_s=120):
        transport = transport or FakeTransport()
        ctl = SyncController(transport, FakeStore(), lambda s: None, discoverable_s=discoverable_s)
        reloj = Reloj()
        s = servicio.Servicio(ctl, connect, reloj=reloj)
        s.arrancar()
        creados.append(ctl)
        return s, ctl, transport, reloj

    yield build
    for ctl in creados:
        ctl.cancel()


def fila(conn):
    conn.commit()   # ver lo último que confirmó el servicio
    cur = conn.cursor()
    cur.execute("SELECT estado, codigo, recibidos, pausado, respuesta, listos, "
                "(SYSDATE - CAST(latido AS DATE)) * 86400 FROM servicio_bt_tst WHERE id = 1")
    return cur.fetchone()


def poner(conn, **valores):
    sets = ", ".join(f"{k} = :{k}" for k in valores)
    conn.cursor().execute(f"UPDATE servicio_bt_tst SET {sets} WHERE id = 1", valores)
    conn.commit()


def test_el_primer_tick_abre_la_recepcion_y_escribe_el_latido(armar, tabla):
    s, ctl, _t, _r = armar()
    s.tick()
    assert ctl.status()["estado"] == ESPERANDO_EMPAREJAMIENTO
    estado, _codigo, _rec, pausado, _resp, _listos, hace = fila(tabla)
    assert estado == ESPERANDO_EMPAREJAMIENTO and pausado == "N" and hace < 5


def test_vencida_la_ventana_la_vuelve_a_abrir(armar, tabla):
    s, ctl, _t, _r = armar(discoverable_s=0.2)
    s.tick()
    wait_for(lambda: ctl.status()["estado"] == IDLE, what="que venza la ventana")
    s.tick()
    assert ctl.status()["estado"] == ESPERANDO_EMPAREJAMIENTO


def test_pausar_en_reposo_y_reanudar(armar, tabla):
    s, ctl, transport, _r = armar()
    s.tick()
    poner(tabla, pausado="S")
    s.tick()
    assert ctl.status()["estado"] == IDLE and not transport.serving
    assert fila(tabla)[0] == "PAUSADO"
    s.tick()
    assert fila(tabla)[0] == "PAUSADO" and ctl.status()["estado"] == IDLE   # sigue en pausa
    poner(tabla, pausado="N")
    s.tick()
    assert ctl.status()["estado"] == ESPERANDO_EMPAREJAMIENTO and fila(tabla)[0] == ESPERANDO_EMPAREJAMIENTO


def test_pausar_no_corta_una_sincronizacion_en_curso(armar, tabla):
    s, ctl, transport, _r = armar()
    s.tick()
    conn = transport.connect()
    conn.feed(hello(), acct(), rec(1))
    wait_for(lambda: ctl.status()["estado"] == RECIBIENDO, what="que empiece a recibir")
    poner(tabla, pausado="S")
    s.tick()
    assert fila(tabla)[0] == "PAUSANDO" and ctl.status()["estado"] == RECIBIENDO
    conn.feed(end(1))
    wait_for(lambda: any(b"BYE" in linea for linea in conn.out), what="el BYE")
    wait_for(lambda: ctl.status()["estado"] in ("LISTO", IDLE), what="el fin de la sincronización")
    s.tick()
    assert fila(tabla)[0] == "PAUSADO" and fila(tabla)[5] == 1     # una sincronización completa más


def test_codigo_de_emparejamiento_se_acepta_desde_la_fila(armar, tabla):
    s, ctl, transport, _r = armar()
    s.tick()
    hilo, resultado = transport.pair("123456")
    wait_for(lambda: ctl.status()["estado"] == CONFIRMAR_CODIGO, what="el código")
    s.tick()
    assert fila(tabla)[:2] == (CONFIRMAR_CODIGO, "123456")
    poner(tabla, respuesta="S")
    s.tick()
    hilo.join(5)
    assert resultado == {"accepted": True} and fila(tabla)[4] is None


def test_un_error_de_transporte_espera_antes_de_reintentar(armar, tabla):
    from btsync.transports.base import BluetoothUnavailable

    s, ctl, transport, reloj = armar(transport=FakeTransport(fail_with=BluetoothUnavailable("sin adaptador")))
    s.tick()
    wait_for(lambda: ctl.status()["estado"] == "ERROR", what="el error")
    s.tick()
    assert fila(tabla)[0] == "ERROR" and transport.pairing_calls == 1
    reloj.t += servicio.REINTENTO_S + 1
    s.tick()
    assert transport.pairing_calls == 2


def test_oracle_caido_en_un_tick_no_tumba_el_servicio(armar, tabla, monkeypatch):
    s, ctl, _t, _r = armar()
    s.tick()

    def caida():
        raise RuntimeError("ORA-12541: TNS:no listener")

    monkeypatch.setattr(s, "_conectar", caida)
    s._conn = None
    s.tick()                                   # no lanza
    monkeypatch.setattr(s, "_conectar", connect)
    s.tick()
    assert fila(tabla)[6] < 5


def test_arrancar_conserva_la_pausa(armar, tabla):
    s, ctl, _t, _r = armar()
    s.tick()
    poner(tabla, pausado="S")
    s2, ctl2, _t2, _r2 = armar()
    s2.tick()
    assert ctl2.status()["estado"] == IDLE and fila(tabla)[0] == "PAUSADO"


def test_una_tarea_periodica_lenta_no_congela_el_latido(armar, tabla):
    import threading
    import time

    s, _ctl, _t, _r = armar()
    soltar, corridas = threading.Event(), []

    def lenta():
        corridas.append(1)
        soltar.wait(5)

    s.periodicas.append(lenta)
    inicio = time.monotonic()
    s.tick()
    s.tick()                                   # la anterior sigue corriendo: no se lanza otra
    assert time.monotonic() - inicio < 1 and corridas == [1]
    assert fila(tabla)[6] < 5
    soltar.set()
    wait_for(lambda: not s.ocupado(), what="que termine la tarea")
    s.tick()
    wait_for(lambda: corridas == [1, 1], what="la siguiente corrida")
