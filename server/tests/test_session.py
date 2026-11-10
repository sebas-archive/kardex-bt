from collections import deque

import oracledb
import pytest

from btsync.protocol import frame, parse
from btsync.session import Session
from btsync.store import Store
from conftest import connect

NOW = 1731170400000
UUID = "tst-sess-1"
CONTEO = "CONT-2026-11"


class FakeConnection:
    """Conexión en memoria: entrega las líneas guardadas y luego None (corte)."""

    def __init__(self, lines):
        self._in = deque(lines)
        self.out: list[bytes] = []
        self.closed = False

    def readline(self):
        return self._in.popleft() if self._in else None

    def write(self, data: bytes) -> None:
        self.out.append(data)

    def close(self) -> None:
        self.closed = True


def hello(uuid=UUID) -> bytes:
    return frame(["HELLO", "1", uuid, "Bodega Test"])


def rec(seq: int, nota: str = "") -> bytes:
    return frame(["REC", str(seq), str(NOW + seq), CONTEO, "A-01", "7701234000001", "1", "Ana", nota])


def end(n: int) -> bytes:
    return frame(["END", str(n)])


def run(store, lines, uuid=UUID):
    conn = FakeConnection(lines)
    events = []
    Session(conn, store, lambda name, data: events.append((name, data)), now_ms=lambda: NOW).run()
    return conn, events


def sent(conn):
    return [parse(b) for b in conn.out]


def rows(db, uuid=UUID, estado=None):
    cur = db.cursor()
    sql = "SELECT COUNT(*) FROM captura_transito WHERE uuid_dispositivo = :u"
    binds = {"u": uuid}
    if estado:
        sql += " AND estado = :e"
        binds["e"] = estado
    cur.execute(sql, binds)
    return cur.fetchone()[0]


def test_happy_path_sends_ready_catalog_acks_and_bye(store, db):
    conn, events = run(store, [hello(), rec(1), rec(2), rec(3), end(3)])
    out = sent(conn)
    assert (out[0].kind, out[0].fields) == ("READY", ["0", str(NOW)])
    kinds = [m.kind for m in out]
    assert "CATCONTEO" in kinds and "CATUBIC" in kinds and "CATPROD" in kinds
    assert kinds.index("CAT_END") > kinds.index("CATPROD")
    assert (out[-2].kind, out[-2].fields) == ("ACK", ["3"])
    assert (out[-1].kind, out[-1].fields) == ("BYE", ["3", "0"])
    assert rows(db, estado="PENDIENTE") == 3
    cur = db.cursor()
    cur.execute("SELECT datos_raw FROM captura_transito WHERE uuid_dispositivo = :u AND seq = 1", u=UUID)
    assert cur.fetchone()[0] == rec(1).decode().split("*")[0]
    assert [e[0] for e in events][0] == "hello" and events[-1] == ("done", {"aceptados": 3, "rechazados": 0})


def test_catalog_never_contains_system_stock(store):
    conn_db = connect()
    cur = conn_db.cursor()
    cur.execute("DELETE FROM stock_sistema WHERE id_conteo LIKE 'TST-%'")
    cur.execute("DELETE FROM conteos WHERE id_conteo LIKE 'TST-%'")
    cur.execute("INSERT INTO conteos (id_conteo, nombre, estado) VALUES ('TST-OPEN', 'Abierto', 'ABIERTO')")
    cur.execute("INSERT INTO conteos (id_conteo, nombre, estado) VALUES ('TST-CLOSED', 'Cerrado', 'CERRADO')")
    cur.execute(
        "INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) "
        "VALUES ('TST-OPEN', (SELECT MIN(sku) FROM productos), 987654.321)"
    )
    conn_db.commit()
    try:
        conn, _ = run(store, [hello(), end(0)])
        out = sent(conn)
        conteos = [m.fields[0] for m in out if m.kind == "CATCONTEO"]
        assert "TST-OPEN" in conteos and "CONT-2026-11" in conteos
        assert "TST-CLOSED" not in conteos
        assert all(len(m.fields) == 4 for m in out if m.kind == "CATPROD")
        assert b"987654" not in b"".join(conn.out)
    finally:
        cur.execute("DELETE FROM stock_sistema WHERE id_conteo LIKE 'TST-%'")
        cur.execute("DELETE FROM conteos WHERE id_conteo LIKE 'TST-%'")
        conn_db.commit()
        conn_db.close()


def test_duplicate_rec_in_new_session_is_not_inserted(store, db):
    run(store, [hello(), rec(1), end(1)])
    conn, _ = run(store, [hello(), rec(1), end(1)])
    out = sent(conn)
    assert (out[0].kind, out[0].fields) == ("READY", ["1", str(NOW)])
    assert (out[-1].kind, out[-1].fields) == ("BYE", ["0", "0"])
    assert rows(db) == 1


def test_reconnect_ready_returns_last_seq(store):
    run(store, [hello(), rec(1), rec(2), rec(3), end(3)])
    conn, _ = run(store, [hello(), end(0)])
    assert sent(conn)[0].fields == ["3", str(NOW)]


def test_bad_crc_naks_expected_seq_and_survives(store, db):
    good2 = rec(2)
    bad2 = good2[:-2] + (b"0" if good2[-2:-1] != b"0" else b"1") + b"\n"
    conn, _ = run(store, [hello(), rec(1), bad2, good2, end(2)])
    out = [(m.kind, m.fields) for m in sent(conn)]
    assert ("NAK", ["2", "CRC"]) in out
    assert out[-2] == ("ACK", ["2"])
    assert out[-1] == ("BYE", ["2", "1"])
    assert rows(db) == 2


def test_seq_gap_naks_once_and_ignores_followers(store, db):
    conn, _ = run(store, [hello(), rec(1), rec(2), rec(4), rec(5), rec(6), rec(3), rec(4), rec(5), rec(6), end(6)])
    out = [(m.kind, m.fields) for m in sent(conn)]
    assert out.count(("NAK", ["3", "SECUENCIA"])) == 1
    assert len([o for o in out if o[0] == "NAK"]) == 1
    assert out[-2] == ("ACK", ["6"])
    assert rows(db) == 6


def test_line_over_4000_bytes_naks_linea_larga(store, db):
    giant = frame(["REC", "2", str(NOW), CONTEO, "A-01", "7701234000001", "1", "Ana", "x" * 4100])
    assert len(giant) - 1 > 4000
    conn, _ = run(store, [hello(), rec(1), giant, rec(2), end(2)])
    out = [(m.kind, m.fields) for m in sent(conn)]
    assert ("NAK", ["2", "LINEA_LARGA"]) in out
    assert out[-2] == ("ACK", ["2"])
    assert rows(db) == 2


def test_connection_cut_after_30_rec_keeps_25(store, db):
    conn, _ = run(store, [hello()] + [rec(i) for i in range(1, 31)])  # y luego readline() -> None
    out = [(m.kind, m.fields) for m in sent(conn)]
    acks = [o for o in out if o[0] == "ACK"]
    assert acks[-1] == ("ACK", ["25"])
    assert ("ACK", ["30"]) not in out
    assert not any(o[0] == "BYE" for o in out)
    assert rows(db) == 25


def test_oracle_down_replies_nak_db_unavailable(db):
    class DownStore(Store):
        def insert_staging(self, uuid, seq, raw):
            raise oracledb.DatabaseError("ORA-03114: not connected to ORACLE")

    import os

    store = DownStore(os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"])
    try:
        conn, _ = run(store, [hello(), rec(1), rec(2), end(2)])
    finally:
        store.rollback()
        from conftest import purge_test_rows

        purge_test_rows()
    out = [(m.kind, m.fields) for m in sent(conn)]
    assert ("NAK", ["1", "DB_NO_DISPONIBLE"]) in out
    assert not any(o[0] == "BYE" for o in out)


def test_session_never_calls_run_batch(store, db):
    class SpyStore(Store):
        calls = 0

        def run_batch(self, origen):
            SpyStore.calls += 1
            return (0, 0)

    import os

    spy = SpyStore(os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"])
    try:
        run(spy, [hello(), rec(1), rec(2), end(2)])
        assert SpyStore.calls == 0
        assert rows(db, estado="PENDIENTE") == 2
    finally:
        spy.rollback()
        from conftest import purge_test_rows

        purge_test_rows()
