"""Batch PL/SQL: procesar, recontar (D13), errores recuperables, huérfanas, purga y bitácora.

Todos los tests usan el escenario fijo (conteo ACTUAL, SKUs A1-A5).
"""

import datetime as dt
import os
import threading

import oracledb
import pytest

from conftest import connect, staging

T0 = 1731170400000  # 2024-11-09 16:40:00 UTC
C = "ACTUAL"


def procesar(db, *args):
    db.cursor().callproc("pkg_batch.procesar_pendientes", list(args))


def estado(db, id_transito):
    cur = db.cursor()
    cur.execute(
        "SELECT estado, mensaje_error FROM captura_transito WHERE id_transito = :i", i=id_transito
    )
    return cur.fetchone()


def registro(db, id_transito):
    cur = db.cursor()
    cur.execute(
        "SELECT id_conteo, sku, cantidad, operador, nota, vigente, fecha_captura "
        "FROM registros_procesados WHERE id_transito = :i",
        i=id_transito,
    )
    row = cur.fetchone()
    if row is None:
        return None
    keys = ("id_conteo", "sku", "cantidad", "operador", "nota", "vigente", "fecha_captura")
    return dict(zip(keys, row))


def vigente(db, id_transito):
    return registro(db, id_transito)["vigente"]


def scalar(db, sql, **binds):
    cur = db.cursor()
    cur.execute(sql, binds)
    return cur.fetchone()[0]


def test_valid_row_becomes_procesado_with_typed_fields(escenario, db):
    tid = staging(db, "tst-b1", 1, T0, C, "A1", "12.5", "Ana", "ok")
    procesar(db)
    assert estado(db, tid) == ("PROCESADO", None)
    r = registro(db, tid)
    del r["fecha_captura"]
    assert r == {
        "id_conteo": "ACTUAL", "sku": "A1",
        "cantidad": 12.5, "operador": "Ana", "nota": "ok", "vigente": "S",
    }


def test_capture_timestamp_is_utc_from_epoch_ms(escenario, db):
    tid = staging(db, "tst-b1", 1, T0, C, "A1", 1)
    procesar(db)
    assert registro(db, tid)["fecha_captura"] == dt.datetime(2024, 11, 9, 16, 40, 0)


def test_recount_same_location_latest_wins(escenario, db):
    old = staging(db, "tst-d1", 1, 1000, C, "A2", 40)
    new = staging(db, "tst-d2", 1, 2000, C, "A2", 45)
    procesar(db)
    assert (vigente(db, old), vigente(db, new)) == ("N", "S")
    assert registro(db, new)["cantidad"] == 45


def test_tie_same_timestamp_higher_id_transito_wins(escenario, db):
    first = staging(db, "tst-d1", 1, 5000, C, "A2", 40)
    second = staging(db, "tst-d2", 1, 5000, C, "A2", 45)
    assert second > first
    procesar(db)
    assert (vigente(db, first), vigente(db, second)) == ("N", "S")


def test_older_reading_arriving_later_does_not_override(escenario, db):
    newer = staging(db, "tst-d1", 1, 2000, C, "A2", 45)
    procesar(db)
    older = staging(db, "tst-d2", 1, 1000, C, "A2", 40)
    procesar(db)
    assert (vigente(db, newer), vigente(db, older)) == ("S", "N")


def test_same_sku_counted_by_two_people_keeps_only_the_latest(escenario, db):
    """Sin ubicaciones hay una lectura vigente por (conteo, SKU): la de Luis, posterior, reemplaza a la de Ana."""
    a = staging(db, "tst-d1", 1, T0, C, "A1", 60, "Ana")
    b = staging(db, "tst-d2", 1, T0 + 1000, C, "A1", 41, "Luis")
    procesar(db)
    assert (vigente(db, a), vigente(db, b)) == ("N", "S")


def test_unknown_sku_marks_error_and_batch_continues(escenario, db):
    bad = staging(db, "tst-b1", 1, T0, C, "ZZ9", 5)
    good = staging(db, "tst-b1", 2, T0 + 1, C, "A1", 5)
    procesar(db)
    assert estado(db, bad) == ("ERROR", "SKU_DESCONOCIDO")
    assert registro(db, bad) is None
    assert estado(db, good) == ("PROCESADO", None)


@pytest.mark.parametrize(
    "cant, esperado",
    [
        ("-1", "CANTIDAD_INVALIDA"),
        ("1,5", "CANTIDAD_INVALIDA"),
        ("1.2345", "CANTIDAD_INVALIDA"),
    ],
)
def test_other_validation_errors(escenario, db, cant, esperado):
    tid = staging(db, "tst-b1", 1, T0, C, "A1", cant)
    procesar(db)
    assert estado(db, tid) == ("ERROR", esperado)
    assert registro(db, tid) is None


def test_reprocesar_errores_after_adding_product(escenario, db):
    tid = staging(db, "tst-b1", 1, T0, C, "ZZ9", 7)
    procesar(db)
    assert estado(db, tid) == ("ERROR", "SKU_DESCONOCIDO")
    db.cursor().execute(
        "INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit) "
        "VALUES ('ZZ9', 'Producto dado de alta después', 'Aseo', 'UND', 100)"
    )
    db.commit()
    db.cursor().callproc("pkg_batch.reprocesar_errores", [C])
    assert estado(db, tid) == ("PROCESADO", None)
    assert registro(db, tid)["cantidad"] == 7


def test_operator_and_note_roundtrip(escenario, db):
    tid = staging(db, "tst-b1", 1, T0, C, "A1", 1, "Ñandú|Pérez", "a|b\nc%ñ😀")
    procesar(db)
    r = registro(db, tid)
    assert (r["operador"], r["nota"]) == ("Ñandú|Pérez", "a|b\nc%ñ😀")


def test_long_note_and_operator_are_truncated(escenario, db):
    tid = staging(db, "tst-b1", 1, T0, C, "A1", 1, "ñ" * 80, "é" * 300)
    procesar(db)
    assert estado(db, tid) == ("PROCESADO", None)
    r = registro(db, tid)
    assert (r["operador"], r["nota"]) == ("ñ" * 60, "é" * 255)


def test_empty_operator_and_note_are_null(escenario, db):
    tid = staging(db, "tst-b1", 1, T0, C, "A1", 1, "", "")
    procesar(db)
    r = registro(db, tid)
    assert (r["operador"], r["nota"]) == (None, None)


def test_quantity_parses_with_dot_under_comma_nls(escenario, db):
    db.cursor().execute("ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.'")
    tid = staging(db, "tst-b1", 1, T0, C, "A1", "12.5")
    procesar(db)
    assert estado(db, tid) == ("PROCESADO", None)
    assert scalar(
        db, "SELECT COUNT(*) FROM registros_procesados WHERE id_transito = :i AND cantidad = 12.5", i=tid
    ) == 1


def test_stale_procesando_row_is_recovered_and_fresh_one_is_not(escenario, db):
    stale = staging(db, "tst-b1", 1, T0, C, "A1", 1)
    fresh = staging(db, "tst-b1", 2, T0 + 1, C, "A2", 1)
    cur = db.cursor()
    cur.execute(
        "UPDATE captura_transito SET estado = 'PROCESANDO', "
        "fecha_reclamo = SYSTIMESTAMP - INTERVAL '10' MINUTE WHERE id_transito = :i", i=stale,
    )
    cur.execute(
        "UPDATE captura_transito SET estado = 'PROCESANDO', "
        "fecha_reclamo = SYSTIMESTAMP - INTERVAL '1' MINUTE WHERE id_transito = :i", i=fresh,
    )
    db.commit()
    procesar(db)
    assert estado(db, stale) == ("PROCESADO", None)
    assert estado(db, fresh)[0] == "PROCESANDO"
    assert registro(db, fresh) is None


def test_two_concurrent_batches_process_each_row_once(escenario, db):
    skus = ("A1", "A2", "A3", "A4", "A5")
    for i in range(200):
        staging(db, "tst-conc", i + 1, T0 + i, C, skus[i % 5], i % 7)
    barrier = threading.Barrier(2)
    errors = []

    def worker():
        conn = connect()
        try:
            barrier.wait(timeout=30)
            conn.cursor().callproc("pkg_batch.procesar_pendientes", ["MANUAL"])
        except Exception as exc:  # p. ej. ORA-00001 sobre ID_TRANSITO
            errors.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert errors == []
    assert scalar(db, "SELECT COUNT(*) FROM registros_procesados WHERE id_conteo = :c", c=C) == 200
    assert scalar(
        db, "SELECT COUNT(DISTINCT id_transito) FROM registros_procesados WHERE id_conteo = :c", c=C
    ) == 200
    assert scalar(
        db, "SELECT COUNT(*) FROM captura_transito WHERE uuid_dispositivo = 'tst-conc' AND estado = 'PROCESADO'"
    ) == 200
    # Una sola lectura vigente por SKU: 5 grupos.
    assert scalar(
        db, "SELECT COUNT(*) FROM registros_procesados WHERE id_conteo = :c AND vigente = 'S'", c=C
    ) == 5
    assert scalar(
        db, "SELECT SUM(procesados) FROM log_batch WHERE id > :m", m=escenario.log_mark
    ) == 200


def test_purge_deletes_only_old_processed(escenario, db):
    old_ok = staging(db, "tst-p1", 1, T0, C, "A1", 1)
    procesar(db)  # de verdad PROCESADO, con su registro
    old_err = staging(db, "tst-p1", 2, T0, C, "ZZ9", 1)
    procesar(db)
    old_pend = staging(db, "tst-p1", 3, T0, C, "A2", 1)
    new_ok = staging(db, "tst-p1", 4, T0, C, "A3", 1)
    cur = db.cursor()
    cur.execute("UPDATE captura_transito SET estado = 'PROCESADO' WHERE id_transito = :i", i=new_ok)
    cur.execute(
        "UPDATE captura_transito SET fecha_recepcion = SYSTIMESTAMP - INTERVAL '8' DAY "
        "WHERE id_transito IN (:a, :b, :c)", a=old_ok, b=old_err, c=old_pend,
    )
    cur.execute(
        "UPDATE captura_transito SET fecha_recepcion = SYSTIMESTAMP - INTERVAL '1' DAY "
        "WHERE id_transito = :i", i=new_ok,
    )
    db.commit()

    db.cursor().callproc("pkg_batch.purgar_transito", [7])

    assert estado(db, old_ok) is None                      # PROCESADO de 8 días: se borra
    assert estado(db, old_err)[0] == "ERROR"               # los errores se conservan
    assert estado(db, old_pend)[0] == "PENDIENTE"          # lo pendiente también
    assert estado(db, new_ok)[0] == "PROCESADO"            # PROCESADO reciente: se conserva
    # La lectura ya procesada sobrevive a la purga de su fila de tránsito.
    assert scalar(
        db, "SELECT COUNT(*) FROM registros_procesados WHERE id_conteo = :c AND sku = 'A1' "
            "AND id_transito IS NULL AND vigente = 'S'", c=C,
    ) == 1


def test_purge_keeps_highest_seq_per_device_so_ready_survives(escenario, db):
    """READY sale de MAX(seq): si la purga borrara todas las filas de un teléfono, el servidor
    volvería a responder READY|0 y el teléfono reenviaría todo su historial."""
    ids = [staging(db, "tst-p2", seq, T0, C, "A1", 1) for seq in (1, 2, 3)]
    cur = db.cursor()
    cur.execute(
        "UPDATE captura_transito SET estado = 'PROCESADO', "
        "fecha_recepcion = SYSTIMESTAMP - INTERVAL '30' DAY WHERE uuid_dispositivo = 'tst-p2'"
    )
    db.commit()
    db.cursor().callproc("pkg_batch.purgar_transito", [7])
    assert [estado(db, i) is None for i in ids] == [True, True, False]
    assert scalar(
        db, "SELECT NVL(MAX(seq), 0) FROM captura_transito WHERE uuid_dispositivo = 'tst-p2'"
    ) == 3


def test_log_batch_row_written(escenario, db):
    staging(db, "tst-b1", 1, T0, C, "A1", 1)
    staging(db, "tst-b1", 2, T0, C, "A2", 1)
    staging(db, "tst-b1", 3, T0, C, "ZZ9", 1)
    procesar(db)
    cur = db.cursor()
    cur.execute(
        "SELECT procesados, errores, origen, inicio, fin FROM log_batch WHERE id > :m ORDER BY id",
        m=escenario.log_mark,
    )
    rows = cur.fetchall()
    assert len(rows) == 1
    procesados, errores, origen, inicio, fin = rows[0]
    assert (procesados, errores, origen) == (2, 1, "MANUAL")
    assert inicio <= fin
    # Una corrida sin nada pendiente no deja fila (el job corre cada minuto).
    procesar(db)
    assert scalar(db, "SELECT COUNT(*) FROM log_batch WHERE id > :m", m=escenario.log_mark) == 1


def test_store_run_batch_returns_counts_of_its_own_run(escenario, store, db):
    staging(db, "tst-b1", 1, T0, C, "A1", 1)
    staging(db, "tst-b1", 2, T0, C, "A2", 1)
    staging(db, "tst-b1", 3, T0, C, "ZZ9", 1)
    assert store.run_batch("SYNC") == (2, 1)
    assert scalar(
        db, "SELECT origen FROM log_batch WHERE id = (SELECT MAX(id) FROM log_batch)"
    ) == "SYNC"
    assert store.run_batch("SYNC") == (0, 0)  # nada pendiente


def test_scheduler_job_is_defined_every_60_seconds(db):
    cur = db.cursor()
    cur.execute(
        "SELECT repeat_interval, job_action FROM user_scheduler_jobs "
        "WHERE job_name = 'JOB_PROCESAR_CAPTURAS'"
    )
    row = cur.fetchone()
    assert row is not None, "falta JOB_PROCESAR_CAPTURAS"
    assert row[0] == "FREQ=MINUTELY;INTERVAL=1"
    assert "procesar_pendientes" in row[1].lower()
    cur.execute("SELECT COUNT(*) FROM user_scheduler_jobs WHERE job_name = 'JOB_PURGA_TRANSITO'")
    assert cur.fetchone()[0] == 1


# ------------------------------------------------------------------ Fase 4: dañados
def _danados(db, id_transito):
    cur = db.cursor()
    cur.execute("SELECT danados FROM registros_procesados WHERE id_transito = :i", i=id_transito)
    fila = cur.fetchone()
    return None if fila is None else fila[0]


def test_danados_se_guardan(escenario, db):
    i = staging(db, "tst-dan", 1, T0, C, "A1", "10", danados="2.5")
    j = staging(db, "tst-dan", 2, T0 + 1, C, "A2", "4")
    procesar(db)
    assert estado(db, i)[0] == "PROCESADO" and float(_danados(db, i)) == 2.5
    assert _danados(db, j) is None


@pytest.mark.parametrize("danados", ["11", "abc", "-1"])
def test_danados_invalidos_o_mayores_que_la_cantidad(escenario, db, danados):
    i = staging(db, "tst-dan", 1, T0, C, "A1", "10", danados=danados)
    procesar(db)
    assert estado(db, i) == ("ERROR", "DANADOS_INVALIDO")


# ------------------------------------------------------------------ alta de SKU
def test_alta_sku_creates_stock_zero_and_reprocesa(escenario, db):
    tid = staging(db, "tst-alta", 1, T0, C, "ZZ9", 7)
    procesar(db)
    assert estado(db, tid) == ("ERROR", "SKU_DESCONOCIDO")

    db.cursor().callproc("pkg_batch.alta_sku", ["ZZ9", "Producto nuevo", "Aseo", "UND", 100])
    cur = db.cursor()
    cur.execute("SELECT cantidad_sistema FROM stock_sistema WHERE id_conteo = 'ACTUAL' AND sku = 'ZZ9'")
    assert cur.fetchone()[0] == 0

    db.cursor().callproc("pkg_batch.reprocesar_errores")
    assert estado(db, tid) == ("PROCESADO", None)
    cur.execute("SELECT cant_sistema, cant_contada, diferencia FROM conciliacion "
                "WHERE id_conteo = 'ACTUAL' AND sku = 'ZZ9'")
    assert cur.fetchone() == (0, 7, 7)


def test_alta_sku_duplicado_falla(escenario, db):
    with pytest.raises(oracledb.DatabaseError, match="ORA-20011"):
        db.cursor().callproc("pkg_batch.alta_sku", ["A1", "Otro nombre", "Aseo", "UND", 1])


def test_v_errores_captura_solo_lecturas(escenario, db):
    tid = staging(db, "tst-err", 1, T0, C, "ZZ9", 5)
    procesar(db)
    cur = db.cursor()
    cur.execute(
        "INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw, estado, mensaje_error) "
        "VALUES ('tst-err', 2, 'FOTO|1|1|1|ABCD|', 'ERROR', 'GRANDE')"
    )
    db.commit()
    cur.execute("SELECT id_transito, sku, cantidad, mensaje_error FROM v_errores_captura "
                "WHERE uuid_dispositivo = 'tst-err' ORDER BY id_transito")
    assert cur.fetchall() == [(tid, "ZZ9", "5", "SKU_DESCONOCIDO")]
