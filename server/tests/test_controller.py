"""SyncController: el "disparador" de la sincronización, sin hardware (FakeTransport)."""

import asyncio
import os
import queue
import socket
import threading
import time

import pytest

from btsync.controller import (
    CONECTADO,
    CONFIRMAR_CODIGO,
    ERROR,
    ESPERANDO_EMPAREJAMIENTO,
    IDLE,
    LISTO,
    PROCESANDO,
    RECIBIENDO,
    SyncController,
)
from btsync.protocol import frame, parse
from btsync.store import Catalog, EstadoCuenta, Store
from btsync.transports.base import BluetoothUnavailable
from btsync.transports.tcp import TcpTransport
from conftest import OPERADOR_ACTIVO

NOW = 1731170400000
STATUS_KEYS = {"estado", "codigo", "recibidos", "restante_s", "ultimo_error"}


class FakeStore:
    """Store en memoria: lo justo para que una Session real funcione, y espía de run_batch."""

    def __init__(self, batch_error=None):
        self.rows, self.batch_calls, self.batch_error = [], [], batch_error

    def register_device(self, uuid, name): pass
    def sincronizar_cuenta(self, usuario, nombre, uuid): return EstadoCuenta("ACTIVO", "OPERADOR", None)
    def open_sync(self, uuid): return 1
    def close_sync(self, id, recibidos, aceptados): pass
    def last_seq(self, uuid): return len(self.rows)
    def catalog(self): return Catalog()
    def commit(self): pass
    def rollback(self): pass

    def insert_staging(self, uuid, seq, raw):
        self.rows.append((uuid, seq, raw))
        return True

    def run_batch(self, origen):
        self.batch_calls.append(origen)
        if self.batch_error:
            raise self.batch_error
        return (len(self.rows), 0)


class FakeConnection:
    """El test alimenta las líneas una a una; ``cut()`` simula que el teléfono se va."""

    def __init__(self):
        self._in, self.out = queue.Queue(), []

    def feed(self, *lines):
        for line in lines:
            self._in.put(line)

    def cut(self):
        self._in.put(None)

    def readline(self): return self._in.get(timeout=10)
    def write(self, data): self.out.append(data)
    def close(self): pass


class FakeTransport:
    def __init__(self, fail_with=None):
        self.fail_with = fail_with
        self.on_passkey = self.on_connection = None
        self.serving = False
        self.pairing_calls = self.serve_calls = self.stops = 0
        self.connections = []

    # --- contrato Transport
    def begin_pairing(self, on_passkey):
        self.pairing_calls += 1
        if self.fail_with:
            raise self.fail_with
        self.on_passkey = on_passkey

    def serve(self, on_connection):
        self.serve_calls += 1
        self.on_connection, self.serving = on_connection, True

    def stop(self):
        self.stops += 1
        self.serving = False
        for conn in self.connections:
            conn.cut()

    # --- lo que haría el Bluetooth real
    def pair(self, code):
        """BlueZ pide confirmar un código: se resuelve cuando el controlador decide."""
        result = {}
        thread = threading.Thread(
            target=lambda: result.update(accepted=asyncio.run(self.on_passkey(code))), daemon=True
        )
        thread.start()
        return thread, result

    def connect(self):
        conn = FakeConnection()
        self.connections.append(conn)
        threading.Thread(target=self.on_connection, args=(conn,), daemon=True).start()
        return conn


def wait_for(predicate, timeout=5.0, what="la condición"):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, f"no se cumplió {what}"
        time.sleep(0.01)


def hello(uuid="tst-ctl"):
    return frame(["HELLO", "3", uuid, "Teléfono de prueba"])


def acct(usuario=OPERADOR_ACTIVO):
    return frame(["ACCT", usuario, "Operador de prueba"])


def rec(seq, conteo="T-01", sku="A1", cant="1", operador="Ana"):
    return frame(["REC", str(seq), str(NOW + seq * 1000), conteo, sku, cant, operador, ""])


def end(n):
    return frame(["END", str(n)])


@pytest.fixture
def ctl():
    """(controlador, transporte, store, estados notificados) con un FakeTransport ya sirviendo."""

    def build(transport=None, store=None, discoverable_s=120):
        transport = transport or FakeTransport()
        store = store or FakeStore()
        changes = []
        controller = SyncController(transport, store, changes.append, discoverable_s=discoverable_s)
        built.append(controller)
        return controller, transport, store, changes

    built = []
    yield build
    for controller in built:
        controller.cancel()


def estados(changes):
    """Estados notificados, sin repetir los consecutivos (el progreso notifica el mismo estado)."""
    out = []
    for change in changes:
        if not out or out[-1] != change["estado"]:
            out.append(change["estado"])
    return out


def started(ctl, **kwargs):
    controller, transport, store, changes = ctl(**kwargs)
    controller.start()
    wait_for(lambda: transport.serving, what="que el transporte empiece a servir")
    return controller, transport, store, changes


def test_start_moves_idle_to_waiting(ctl):
    controller, transport, _, changes = ctl()
    assert controller.status() == {
        "estado": IDLE, "codigo": None, "recibidos": 0, "restante_s": 0, "ultimo_error": None,
    }
    controller.start()
    status = controller.status()
    assert status["estado"] == ESPERANDO_EMPAREJAMIENTO
    assert 118 <= status["restante_s"] <= 120
    wait_for(lambda: transport.serving, what="que el transporte empiece a servir")
    assert (transport.pairing_calls, transport.serve_calls) == (1, 1)
    assert set(changes[0]) == STATUS_KEYS


def test_passkey_callback_sets_confirm_state_and_code(ctl):
    controller, transport, _, changes = started(ctl)
    thread, result = transport.pair("123456")
    wait_for(lambda: controller.status()["estado"] == CONFIRMAR_CODIGO, what="CONFIRMAR_CODIGO")
    assert controller.status()["codigo"] == "123456"
    assert changes[-1]["estado"] == CONFIRMAR_CODIGO and changes[-1]["codigo"] == "123456"
    assert thread.is_alive()  # BlueZ sigue esperando la decisión del usuario

    controller.confirm(True)
    thread.join(timeout=5)
    assert result == {"accepted": True}
    status = controller.status()
    assert (status["estado"], status["codigo"]) == (ESPERANDO_EMPAREJAMIENTO, None)
    assert transport.serving  # sigue visible: falta que el teléfono se conecte


def test_confirm_false_rejects_pairing(ctl):
    controller, transport, _, _ = started(ctl)
    thread, result = transport.pair("654321")
    wait_for(lambda: controller.status()["estado"] == CONFIRMAR_CODIGO, what="CONFIRMAR_CODIGO")
    controller.confirm(False)
    thread.join(timeout=5)
    assert result == {"accepted": False}
    assert controller.status()["estado"] == IDLE
    assert controller.status()["codigo"] is None
    assert not transport.serving and transport.stops == 1


def test_timeout_returns_to_idle_and_stops_transport(ctl):
    controller, transport, _, _ = started(ctl, discoverable_s=1)
    thread, result = transport.pair("111111")  # nadie confirma
    wait_for(lambda: controller.status()["estado"] == CONFIRMAR_CODIGO, what="CONFIRMAR_CODIGO")
    wait_for(lambda: controller.status()["estado"] == IDLE, timeout=3, what="volver a IDLE a los 2 s")
    thread.join(timeout=5)
    assert result == {"accepted": False}  # el código pendiente se rechaza solo
    assert not transport.serving and transport.stops == 1
    assert controller.status()["restante_s"] == 0


def test_session_end_runs_batch_once_then_listo(ctl):
    controller, transport, store, changes = started(ctl)
    conn = transport.connect()
    conn.feed(hello(), acct(), rec(1), rec(2), rec(3), end(3))
    wait_for(lambda: controller.status()["estado"] == LISTO, what="LISTO")
    seen = estados(changes)
    assert seen[-3:] == [RECIBIENDO, PROCESANDO, LISTO]
    assert store.batch_calls == ["SYNC"]
    assert [parse(b).kind for b in conn.out][-1] == "BYE"  # el teléfono no espera al batch
    assert not transport.serving  # al terminar, el PC deja de aceptar
    assert controller.status()["ultimo_error"] is None


def test_batch_failure_reports_error_and_controller_keeps_running(ctl):
    store = FakeStore(batch_error=RuntimeError("ORA-12541: TNS:no listener"))
    controller, transport, _, _ = started(ctl, store=store)
    conn = transport.connect()
    conn.feed(hello(), acct(), rec(1), end(1))
    wait_for(lambda: controller.status()["estado"] == ERROR, what="ERROR")
    assert controller.status()["ultimo_error"].startswith("BATCH:")
    assert "ORA-12541" in controller.status()["ultimo_error"]
    assert len(store.rows) == 1  # lo recibido sigue en staging; lo procesará el job

    controller.start()  # el controlador sigue sirviendo
    assert controller.status()["estado"] == ESPERANDO_EMPAREJAMIENTO
    assert controller.status()["ultimo_error"] is None
    wait_for(lambda: transport.serving, what="que vuelva a servir")


def test_progress_event_updates_recibidos(ctl):
    controller, transport, _, changes = started(ctl)
    conn = transport.connect()
    conn.feed(hello(), acct(), rec(1), rec(2), rec(3))
    wait_for(lambda: controller.status()["recibidos"] == 3, what="recibidos == 3")
    assert controller.status()["estado"] == RECIBIENDO
    assert any(c["estado"] == RECIBIENDO and c["recibidos"] >= 1 for c in changes)
    conn.feed(end(3))
    wait_for(lambda: controller.status()["estado"] == LISTO, what="LISTO")
    assert controller.status()["recibidos"] == 3
    assert changes[-1]["recibidos"] == 3


def test_start_twice_is_idempotent(ctl):
    controller, transport, _, changes = started(ctl)
    controller.start()
    controller.start()
    time.sleep(0.1)
    assert (transport.pairing_calls, transport.serve_calls) == (1, 1)
    assert estados(changes) == [ESPERANDO_EMPAREJAMIENTO]
    assert len(changes) == 1


def test_on_change_called_on_every_transition(ctl):
    controller, transport, _, changes = started(ctl)
    thread, _ = transport.pair("123456")
    wait_for(lambda: controller.status()["estado"] == CONFIRMAR_CODIGO, what="CONFIRMAR_CODIGO")
    controller.confirm(True)
    thread.join(timeout=5)
    conn = transport.connect()
    wait_for(lambda: controller.status()["estado"] == CONECTADO, what="CONECTADO")
    conn.feed(hello(), acct(), rec(1), rec(2), end(2))
    wait_for(lambda: controller.status()["estado"] == LISTO, what="LISTO")
    assert estados(changes) == [
        ESPERANDO_EMPAREJAMIENTO,
        CONFIRMAR_CODIGO,
        ESPERANDO_EMPAREJAMIENTO,
        CONECTADO,
        RECIBIENDO,
        PROCESANDO,
        LISTO,
    ]
    assert all(set(change) == STATUS_KEYS for change in changes)
    assert changes[-1] == controller.status()


def test_bluetooth_unavailable_sets_error_state_with_message(ctl):
    transport = FakeTransport(fail_with=BluetoothUnavailable("No hay adaptador Bluetooth (hci0)"))
    controller, _, _, changes = ctl(transport=transport)
    controller.start()  # no debe lanzar
    wait_for(lambda: controller.status()["estado"] == ERROR, what="ERROR")
    assert controller.status()["ultimo_error"] == "No hay adaptador Bluetooth (hci0)"
    assert estados(changes) == [ESPERANDO_EMPAREJAMIENTO, ERROR]
    assert not transport.serving


def test_cut_before_end_keeps_waiting_and_does_not_run_batch(ctl):
    """Un corte no cierra la ventana: el teléfono reintenta solo y debe poder reconectarse."""
    controller, transport, store, _ = started(ctl)
    first = transport.connect()
    first.feed(hello(), acct(), rec(1), rec(2))
    wait_for(lambda: controller.status()["recibidos"] == 2, what="recibidos == 2")
    first.cut()
    wait_for(lambda: controller.status()["estado"] == ESPERANDO_EMPAREJAMIENTO, what="volver a esperar")
    assert controller.status()["ultimo_error"].startswith("CORTE:")
    assert store.batch_calls == [] and transport.serving

    second = transport.connect()  # el reintento
    second.feed(hello(), acct(), end(0))
    wait_for(lambda: controller.status()["estado"] == LISTO, what="LISTO")
    assert store.batch_calls == ["SYNC"]
    assert controller.status()["ultimo_error"] is None


def test_cancel_mid_session_returns_to_idle_without_batch(ctl):
    controller, transport, store, _ = started(ctl)
    conn = transport.connect()
    conn.feed(hello(), acct(), rec(1))
    wait_for(lambda: controller.status()["recibidos"] == 1, what="recibidos == 1")
    controller.cancel()
    assert controller.status()["estado"] == IDLE
    assert not transport.serving
    time.sleep(0.1)
    assert store.batch_calls == []
    assert controller.status()["estado"] == IDLE  # la sesión cortada no revive el ciclo


def test_tcp_transport_real_store_end_to_end(escenario, db):
    """Lo mismo con piezas reales: TCP + Oracle. Al llegar a LISTO el batch ya concilió."""
    store = Store(os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"])
    transport = TcpTransport("127.0.0.1", 0)
    changes = []
    controller = SyncController(transport, store, changes.append)
    controller.start()
    try:
        wait_for(lambda: transport.port != 0, what="que TCP escuche")
        lecturas = [("A1", "60", "Ana"), ("A1", "101", "Luis"), ("A2", "45", "Ana"),
                    ("A3", "23", "Ana"), ("A5", "4", "Luis")]
        with socket.create_connection(("127.0.0.1", transport.port), timeout=10) as sock:
            sock.sendall(hello("tst-ctl-tcp") + acct())
            for i, (sku, cant, operador) in enumerate(lecturas, start=1):
                sock.sendall(rec(i, sku=sku, cant=cant, operador=operador))
            sock.sendall(end(len(lecturas)))
            replies = sock.makefile("rb")
            kinds = []
            while not kinds or kinds[-1] != "BYE":
                kinds.append(parse(replies.readline()).kind)
        wait_for(lambda: controller.status()["estado"] == LISTO, timeout=15, what="LISTO")
    finally:
        controller.cancel()
        store.rollback()

    assert controller.status()["recibidos"] == 5 and controller.status()["ultimo_error"] is None
    cur = db.cursor()
    cur.execute(
        "SELECT skus_totales, contados, avance_pct, ok, faltantes, sobrantes, exactitud_pct, "
        "valor_faltante, valor_sobrante FROM v_resumen_conteo WHERE id_conteo = 'T-01'"
    )
    assert cur.fetchone() == (5, 4, 80.00, 1, 1, 2, 25.00, -5000, 11800)
    cur.execute("SELECT origen FROM log_batch WHERE id > :m", m=escenario.log_mark)
    assert cur.fetchall() == [("SYNC",)]
