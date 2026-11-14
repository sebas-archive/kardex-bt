"""Fotos como evidencia (Fase 4): el receptor arma las partes, comprueba el CRC, guarda el archivo y su ruta."""

import base64
import zlib

import pytest

from btsync.protocol import foto_lineas, frame
from conftest import connect
from test_session import FakeConnection, NOW, UUID, end, inicio, rec, rows, run, sent  # noqa: F401

JPEG = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 40 + b"\xff\xd9"   # 10 246 bytes: 4 partes


@pytest.fixture(autouse=True)
def carpeta(tmp_path, monkeypatch):
    monkeypatch.setenv("FOTOS_DIR", str(tmp_path / "fotos"))
    conn = connect()
    conn.cursor().execute("DELETE FROM fotos WHERE uuid_dispositivo LIKE 'tst-%'")
    conn.commit()
    yield tmp_path / "fotos"
    conn.cursor().execute("DELETE FROM fotos WHERE uuid_dispositivo LIKE 'tst-%'")
    conn.commit()
    conn.close()


def _fotos(seq=1):
    return [frame(x) for x in foto_lineas(seq, JPEG)]


def _fila(db, seq=1):
    cur = db.cursor()
    cur.execute("SELECT ruta, bytes FROM fotos WHERE uuid_dispositivo = :u AND seq = :s", u=UUID, s=seq)
    return cur.fetchall()


def test_foto_completa_se_guarda(store, db, carpeta):
    conn, _ = run(store, [*inicio(), rec(1), *_fotos(1), end(1)])
    out = [(m.kind, m.fields) for m in sent(conn)]
    assert ("FOTOOK", ["1"]) in out and out[-1][0] == "BYE"
    # La foto empieza: el PC confirma antes las lecturas pendientes (el móvil no espera al END para mandar fotos).
    assert out.index(("ACK", ["1"])) < out.index(("FOTOOK", ["1"]))
    assert _fila(db) == [(f"{UUID}/1.jpg", len(JPEG))]
    assert (carpeta / UUID / "1.jpg").read_bytes() == JPEG


def test_crc_malo_no_guarda_nada(store, db, carpeta):
    lineas = foto_lineas(1, JPEG)
    lineas[0][4] = "00000000"
    conn, _ = run(store, [*inicio(), rec(1), *[frame(x) for x in lineas], end(1)])
    assert ("FOTOERR", ["1", "CRC"]) in [(m.kind, m.fields) for m in sent(conn)]
    assert _fila(db) == [] and not (carpeta / UUID / "1.jpg").exists()


def test_foto_demasiado_grande(store, db, carpeta, monkeypatch):
    import btsync.session as sesion
    monkeypatch.setattr(sesion, "MAX_FOTO", 5_000)
    conn, _ = run(store, [*inicio(), rec(1), *_fotos(1), end(1)])
    out = [(m.kind, m.fields) for m in sent(conn)]
    assert out.count(("FOTOERR", ["1", "GRANDE"])) == 1 and _fila(db) == []
    assert out[-1][0] == "BYE"


def test_foto_repetida_no_duplica(store, db, carpeta):
    run(store, [*inicio(), rec(1), *_fotos(1), end(1)])
    conn, _ = run(store, [*inicio(), *_fotos(1), end(0)])      # el FOTOOK anterior se perdió: la reenvía
    assert ("FOTOOK", ["1"]) in [(m.kind, m.fields) for m in sent(conn)]
    assert len(_fila(db)) == 1


def test_corte_a_mitad_no_deja_nada(store, db, carpeta):
    run(store, [*inicio(), rec(1), *_fotos(1)[:2]])            # y luego readline() -> None
    assert _fila(db) == [] and not (carpeta / UUID).exists() or not any((carpeta / UUID).iterdir())


def test_foto_de_una_lectura_que_no_llego(store, db, carpeta):
    conn, _ = run(store, [*inicio(), *_fotos(9), end(0)])
    assert ("FOTOERR", ["9", "SIN_LECTURA"]) in [(m.kind, m.fields) for m in sent(conn)]
    assert _fila(db, 9) == []


def test_parte_fuera_de_orden(store, db, carpeta):
    lineas = _fotos(1)
    conn, _ = run(store, [*inicio(), rec(1), lineas[0], lineas[2], end(1)])
    assert ("FOTOERR", ["1", "FORMAT"]) in [(m.kind, m.fields) for m in sent(conn)]
    assert _fila(db) == []


def test_esquema_migrar_idempotente_y_recompila():
    from btsync import esquema
    conn = connect()
    try:
        esquema.migrar(conn)
        esquema.migrar(conn)
        assert esquema.paquete_al_dia(conn.cursor())
    finally:
        conn.close()


def test_la_purga_conserva_las_lecturas_con_foto(store, db, carpeta):
    run(store, [*inicio(), rec(1), rec(2), rec(3), *_fotos(1), end(3)])
    cur = db.cursor()
    cur.execute("UPDATE captura_transito SET estado = 'PROCESADO', fecha_recepcion = SYSTIMESTAMP - 30 "
                "WHERE uuid_dispositivo = :u", u=UUID)
    db.commit()
    cur.callproc("pkg_batch.purgar_transito", [7])
    cur.execute("SELECT seq FROM captura_transito WHERE uuid_dispositivo = :u ORDER BY seq", u=UUID)
    assert [r[0] for r in cur] == [1, 3]   # 1 tiene foto; 3 es el último seq (READY); 2 se purga


@pytest.mark.parametrize("uuid", ["../../fuera", "/tmp/absoluto", "tst-a/b", "tst-..\\x"])
def test_uuid_con_ruta_se_rechaza_en_el_saludo(store, db, carpeta, uuid):
    """El uuid termina en una ruta de disco: uno que sale de la carpeta de fotos no pasa del HELLO."""
    conn, events = run(store, [*inicio(uuid=uuid), rec(1), *_fotos(1), end(1)], uuid=uuid)
    assert [(m.kind, m.fields) for m in sent(conn)] == [("NAK", ["0", "FORMAT"])]
    assert events == []


def test_guardar_foto_no_escribe_fuera_de_la_carpeta(store, carpeta):
    with pytest.raises(ValueError):
        store.guardar_foto("../fuera", 1, JPEG)
    assert not (carpeta.parent / "fuera").exists()
