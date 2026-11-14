"""Extremo a extremo sin hardware: teléfono simulado → TCP → Session → Oracle (staging)."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from btsync.protocol import frame, parse
from btsync.session import Session
from btsync.store import Store
from btsync.transports.tcp import TcpTransport
from conftest import OPERADOR_ACTIVO, purge_test_rows

ROOT = Path(__file__).resolve().parents[2]
UUID = "dev-e2e"
TRUTH = json.loads((ROOT / "tools" / "truth.json").read_text(encoding="utf-8"))
N = len(TRUTH["fisico"])  # una lectura por SKU
SKEW_MS = 600_000


class SpyStore(Store):
    """Cuenta los intentos de insertar un (uuid, seq) repetido (lo que daría ORA-00001)."""

    duplicate_attempts = 0

    def insert_staging(self, uuid, seq, raw):
        ok = super().insert_staging(uuid, seq, raw)
        if not ok:
            self.duplicate_attempts += 1
        return ok


@pytest.fixture
def server():
    purge_test_rows()
    store = SpyStore(os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"])
    transport = TcpTransport("127.0.0.1", 0)
    info = SimpleNamespace(transport=transport, store=store, sessions=[], errors=[])

    def on_connection(conn):
        rec = {"t0": time.perf_counter(), "first": None, "done": None, "aceptados": None}

        def on_event(name, data):
            now = time.perf_counter()
            if name == "progress" and rec["first"] is None:
                rec["first"] = now
            if name == "done":
                rec["done"], rec["aceptados"] = now, data["aceptados"]

        try:
            Session(conn, store, on_event).run()
        except Exception as exc:  # la sesión nunca debería dejar escapar nada
            info.errors.append(exc)
            raise
        finally:
            rec["t1"] = time.perf_counter()
            info.sessions.append(rec)

    transport.serve(on_connection)
    info.port = transport.port
    try:
        yield info
    finally:
        transport.stop()
        store.rollback()
        store.close()
        purge_test_rows()


def phone_cmd(port, state_file, *extra):
    return [
        sys.executable,
        str(ROOT / "tools" / "fake_phone.py"),
        "--host", "127.0.0.1",
        "--port", str(port),
        "--seed", "42",
        "--uuid", UUID,
        "--cuenta", OPERADOR_ACTIVO,
        "--state-file", str(state_file),
        *extra,
    ]


def run_phone(port, state_file, *extra):
    return subprocess.run(
        phone_cmd(port, state_file, *extra), capture_output=True, text=True, timeout=120
    )


def staged(db):
    """[(seq, epoch_ms del REC guardado)] del teléfono de prueba, por seq."""
    cur = db.cursor()
    cur.execute(
        "SELECT seq, datos_raw FROM captura_transito WHERE uuid_dispositivo = :u ORDER BY seq",
        u=UUID,
    )
    return [(int(seq), int(raw.split("|")[2])) for seq, raw in cur]


def count(db):
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM captura_transito WHERE uuid_dispositivo = :u", u=UUID)
    return cur.fetchone()[0]


def wait_idle(server, timeout=10.0):
    deadline = time.monotonic() + timeout
    while server.transport.busy:
        assert time.monotonic() < deadline, "el servidor no liberó la conexión cortada"
        time.sleep(0.02)


def kill_midway(server, db, state_file, *extra):
    """Lanza el teléfono lento, lo mata cuando ya hay filas confirmadas y devuelve cuántas quedaron."""
    proc = subprocess.Popen(
        phone_cmd(server.port, state_file, "--delay-ms", "30", *extra),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 60
        while count(db) < 25:
            assert proc.poll() is None, "el teléfono terminó antes de poder cortarlo"
            assert time.monotonic() < deadline, "no llegaron 25 filas a tiempo"
            time.sleep(0.02)
    finally:
        proc.kill()
        proc.wait()
    wait_idle(server)
    partial = count(db)
    assert 25 <= partial < N, f"el corte no fue a mitad: {partial} de {N}"
    assert partial % 25 == 0, "solo deben quedar filas confirmadas con COMMIT (bloques de 25)"
    return partial


def test_full_count_end_to_end(server, db, tmp_path):
    result = run_phone(server.port, tmp_path / "state.json")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == f"BYE|{N}|0"
    assert [seq for seq, _ in staged(db)] == list(range(1, N + 1))
    assert server.store.duplicate_attempts == 0
    assert server.errors == []


def test_phone_killed_midway_and_resumed_no_duplicates(server, db, tmp_path):
    state = tmp_path / "state.json"
    partial = kill_midway(server, db, state)

    result = run_phone(server.port, state)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == f"BYE|{N - partial}|0"
    assert [seq for seq, _ in staged(db)] == list(range(1, N + 1))
    assert server.store.duplicate_attempts == 0  # nunca se intentó un (uuid, seq) repetido
    assert server.errors == []


def test_clock_skew_is_corrected(server, db, tmp_path):
    state = tmp_path / "state.json"
    before_ms = time.time() * 1000
    result = run_phone(server.port, state, "--skew-ms", str(SKEW_MS))
    after_ms = time.time() * 1000
    assert result.returncode == 0, result.stderr

    originals = {l["seq"]: l["ts_original_ms"] for l in json.loads(state.read_text())["lecturas"]}
    # El reloj del teléfono realmente iba 10 minutos adelantado...
    assert all(before_ms + SKEW_MS - 1 <= ts <= after_ms + SKEW_MS + N for ts in originals.values())
    rows = staged(db)
    assert len(rows) == N
    for seq, ts in rows:
        # ...y lo guardado quedó en la hora del servidor (la captura real ± 2 s).
        assert abs(ts - (originals[seq] - SKEW_MS)) <= 2000, (seq, ts)
        assert before_ms - 2000 <= ts <= after_ms + 2000, (seq, ts)


def test_retry_does_not_apply_offset_twice(server, db, tmp_path):
    state = tmp_path / "state.json"
    kill_midway(server, db, state, "--skew-ms", str(SKEW_MS))
    originals = {l["seq"]: l["ts_original_ms"] for l in json.loads(state.read_text())["lecturas"]}

    result = run_phone(server.port, state, "--skew-ms", str(SKEW_MS))
    assert result.returncode == 0, result.stderr

    after = {l["seq"]: l["ts_original_ms"] for l in json.loads(state.read_text())["lecturas"]}
    assert after == originals  # la hora original nunca se reescribe
    rows = staged(db)
    assert len(rows) == N
    for seq, ts in rows:
        assert abs(ts - (originals[seq] - SKEW_MS)) <= 2000, (seq, ts)  # no 1 200 000 ms


def test_second_connection_while_busy_gets_nak_ocupado(server):
    first = socket.create_connection(("127.0.0.1", server.port), timeout=10)
    try:
        first.sendall(frame(["HELLO", "5", "dev-e2e-a", "Primero"]) + frame(["ACCT", OPERADOR_ACTIVO, "Operador de prueba"]))
        first_in = first.makefile("rb")
        assert parse(first_in.readline()).kind == "ACCTST"
        assert parse(first_in.readline()).kind == "READY"

        second = socket.create_connection(("127.0.0.1", server.port), timeout=10)
        try:
            second_in = second.makefile("rb")
            assert second_in.readline() == b"NAK|0|OCUPADO*2C549C0A\n"
            assert second_in.readline() == b""  # y el servidor cierra
        finally:
            second.close()

        # La primera conexión no se enteró: termina su sesión con normalidad.
        first.sendall(frame(["END", "0"]))
        kinds = []
        while not kinds or kinds[-1] != "BYE":
            line = first_in.readline()
            assert line, f"se cortó antes del BYE; llegó {kinds}"
            kinds.append(parse(line).kind)
    finally:
        first.close()
    assert server.errors == []


def test_insert_latency_reported(server, db, tmp_path):
    result = run_phone(server.port, tmp_path / "state.json")
    assert result.returncode == 0, result.stderr
    session = server.sessions[0]
    assert session["aceptados"] == N
    total_ms = (session["t1"] - session["t0"]) * 1000
    steady_ms = (session["done"] - session["first"]) * 1000
    per_record = total_ms / N
    print(
        f"\nLATENCIA staging por TCP: {per_record:.2f} ms/registro "
        f"(sesión completa con saludo y catálogo: {total_ms:.0f} ms para {N} registros); "
        f"solo REC→COMMIT→ACK: {steady_ms / (N - 1):.2f} ms/registro. Objetivo del PDF: < 50 ms."
    )
    assert per_record < 250
