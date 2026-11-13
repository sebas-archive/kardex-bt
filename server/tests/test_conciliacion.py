"""Conciliación contra el stock del sistema, cierre de conteo y vistas.

Valores exactos del escenario fijo T-01 (ver server/tests/fixtures/escenario_conciliacion.sql):
lecturas A1 60 (Ana) y luego A1 101 (Luis, recuento que la reemplaza), A2 45, A3 23, A5 4; stock A1 100, A2 50, A3 20, A4 10.
"""

import threading

import oracledb
import pytest

from conftest import connect, staging

C = "T-01"
T0 = 1731170400000

# sku: (cant_sistema, cant_contada, diferencia, diferencia_pct, valor_diferencia, clasificacion)
ABIERTO = {
    "A1": (100, 101, 1, 1.00, 2000, "OK"),
    "A2": (50, 45, -5, -10.00, -5000, "FALTANTE"),
    "A3": (20, 23, 3, 15.00, 9000, "SOBRANTE"),
    "A4": (10, 0, None, None, None, "SIN_CONTAR"),
    "A5": (0, 4, 4, None, 2800, "SOBRANTE"),
}
CERRADO = {**ABIERTO, "A4": (10, 0, -10, -100.00, -5000, "FALTANTE")}
# skus_totales, contados, avance_pct, ok, faltantes, sobrantes, exactitud_pct, valor_faltante, valor_sobrante
RESUMEN_ABIERTO = (5, 4, 80.00, 1, 1, 2, 25.00, -5000, 11800)
RESUMEN_CERRADO = (5, 5, 100.00, 1, 2, 2, 20.00, -10000, 11800)


def procesar(db):
    db.cursor().callproc("pkg_batch.procesar_pendientes")


def conciliacion(db, conteo=C):
    cur = db.cursor()
    cur.execute(
        "SELECT sku, cant_sistema, cant_contada, diferencia, diferencia_pct, valor_diferencia, clasificacion "
        "FROM conciliacion WHERE id_conteo = :c",
        c=conteo,
    )
    return {row[0]: tuple(row[1:]) for row in cur}


def resumen(db, conteo=C):
    cur = db.cursor()
    cur.execute(
        "SELECT skus_totales, contados, avance_pct, ok, faltantes, sobrantes, exactitud_pct, "
        "valor_faltante, valor_sobrante FROM v_resumen_conteo WHERE id_conteo = :c",
        c=conteo,
    )
    return cur.fetchone()


@pytest.fixture
def contado(escenario, db):
    """El escenario con sus 5 lecturas ya procesadas por el batch."""
    escenario.cargar_lecturas()
    procesar(db)
    return escenario


def test_conciliacion_matches_scenario_exactly(contado, db):
    assert conciliacion(db) == ABIERTO


def test_resumen_matches_scenario_exactly(contado, db):
    assert resumen(db) == RESUMEN_ABIERTO


def test_cerrar_conteo_turns_sin_contar_into_faltante(contado, db):
    db.cursor().callproc("pkg_batch.cerrar_conteo", [C])
    assert conciliacion(db) == CERRADO
    assert resumen(db) == RESUMEN_CERRADO
    cur = db.cursor()
    cur.execute("SELECT estado, fecha_cierre FROM conteos WHERE id_conteo = :c", c=C)
    estado, fecha_cierre = cur.fetchone()
    assert estado == "CERRADO" and fecha_cierre is not None


def test_tolerance_boundary_is_inclusive(escenario, db):
    # A1: sistema 100, tolerancia 2 % -> hasta 2 unidades de diferencia es OK.
    staging(db, "tst-c1", 1, T0, C, "A1", 102)
    procesar(db)
    assert conciliacion(db)["A1"] == (100, 102, 2, 2.00, 4000, "OK")
    staging(db, "tst-c1", 2, T0 + 1000, C, "A1", 103)  # recuento
    procesar(db)
    assert conciliacion(db)["A1"] == (100, 103, 3, 3.00, 6000, "SOBRANTE")


def test_recount_updates_conciliation(contado, db):
    assert conciliacion(db)["A2"][5] == "FALTANTE"
    staging(db, "tst-c1", 1, T0 + 60_000, C, "A2", 50)  # más reciente que la lectura de 45
    procesar(db)
    assert conciliacion(db)["A2"] == (50, 50, 0, 0.00, 0, "OK")
    assert conciliacion(db)["A1"] == ABIERTO["A1"]  # lo demás no cambia


def test_counted_sku_missing_from_snapshot_is_sobrante_with_system_zero(contado, db):
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM stock_sistema WHERE id_conteo = :c AND sku = 'A5'", c=C)
    assert cur.fetchone()[0] == 0  # A5 no está en la foto de stock...
    assert conciliacion(db)["A5"] == (0, 4, 4, None, 2800, "SOBRANTE")  # ...y aun así se concilia


def test_v_dif_categoria_values(contado, db):
    cur = db.cursor()
    cur.execute(
        "SELECT categoria, diferencia, valor_diferencia FROM v_dif_categoria WHERE id_conteo = :c", c=C
    )
    assert {r[0]: (r[1], r[2]) for r in cur} == {
        "Abarrotes": (-4, -3000),
        "Aseo": (3, 9000),
        "Lácteos": (4, 2800),
    }


def test_v_top_desvios_order(contado, db):
    cur = db.cursor()
    cur.execute(
        "SELECT sku, valor_diferencia, clasificacion, nombre, categoria, diferencia "
        "FROM v_top_desvios WHERE id_conteo = :c",
        c=C,
    )
    rows = cur.fetchall()
    assert [(r[0], r[1]) for r in rows] == [
        ("A3", 9000), ("A2", -5000), ("A5", 2800), ("A1", 2000), ("A4", None),
    ]
    assert rows[0][2:] == ("SOBRANTE", "Producto A3", "Aseo", 3)


def test_v_actividad_counts_by_operator(contado, db):
    cur = db.cursor()
    cur.execute(
        "SELECT operador, SUM(registros), COUNT(DISTINCT hora) FROM v_actividad "
        "WHERE id_conteo = :c GROUP BY operador",
        c=C,
    )
    assert {r[0]: (r[1], r[2]) for r in cur} == {"Ana": (3, 1), "Luis": (2, 1)}


def test_v_estado_batch_counts(escenario, db):
    def estado_batch():
        cur = db.cursor()
        cur.execute(
            "SELECT pendientes, procesando, procesados, errores, ultimo_run, ultimo_origen FROM v_estado_batch"
        )
        return cur.fetchone()

    antes = estado_batch()
    staging(db, "tst-c1", 1, T0, C, "ZZ9", 1)       # quedará en ERROR
    staging(db, "tst-c1", 2, T0, C, "A1", 1)        # quedará PROCESADO
    procesar(db)
    staging(db, "tst-c1", 3, T0, C, "A2", 1)        # se queda PENDIENTE
    ahora = estado_batch()
    assert (ahora[0] - antes[0], ahora[1] - antes[1], ahora[2] - antes[2], ahora[3] - antes[3]) == (1, 0, 1, 1)
    assert ahora[4] is not None and ahora[5] == "MANUAL"


def test_concurrent_batches_leave_same_conciliation_as_single_run(escenario, db):
    escenario.cargar_lecturas()
    barrier = threading.Barrier(4)
    errors = []

    def worker(proc, args, repeat):
        conn = connect()
        try:
            barrier.wait(timeout=30)
            for _ in range(repeat):
                conn.cursor().callproc(proc, args)
        except Exception as exc:  # p. ej. ORA-00001 sobre la PK de CONCILIACION
            errors.append(exc)
        finally:
            conn.close()

    threads = [
        threading.Thread(target=worker, args=("pkg_batch.procesar_pendientes", [], 1)),
        threading.Thread(target=worker, args=("pkg_batch.procesar_pendientes", [], 1)),
        threading.Thread(target=worker, args=("pkg_batch.conciliar", [C], 5)),
        threading.Thread(target=worker, args=("pkg_batch.conciliar", [C], 5)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert errors == []
    assert conciliacion(db) == ABIERTO
    assert resumen(db) == RESUMEN_ABIERTO


def test_reading_after_close_is_error_and_close_is_stable(contado, db):
    db.cursor().callproc("pkg_batch.cerrar_conteo", [C])
    tid = staging(db, "tst-c1", 1, T0 + 60_000, C, "A4", 10)  # llega tarde
    procesar(db)
    cur = db.cursor()
    cur.execute("SELECT estado, mensaje_error FROM captura_transito WHERE id_transito = :i", i=tid)
    assert cur.fetchone() == ("ERROR", "CONTEO_NO_ABIERTO")
    db.cursor().callproc("pkg_batch.conciliar", [C])   # recalcular no revive el SIN_CONTAR
    db.cursor().callproc("pkg_batch.cerrar_conteo", [C])  # y cerrar dos veces no rompe nada
    assert conciliacion(db) == CERRADO


def test_cerrar_conteo_processes_pending_readings_first(escenario, db):
    escenario.cargar_lecturas()  # recibidas pero aún sin procesar
    db.cursor().callproc("pkg_batch.cerrar_conteo", [C])
    cur = db.cursor()
    cur.execute(
        "SELECT estado, COUNT(*) FROM captura_transito WHERE uuid_dispositivo = 'tst-escenario' GROUP BY estado"
    )
    assert cur.fetchall() == [("PROCESADO", 5)]
    assert conciliacion(db) == CERRADO


def test_cerrar_conteo_unknown_raises(db):
    with pytest.raises(oracledb.DatabaseError, match="ORA-20002"):
        db.cursor().callproc("pkg_batch.cerrar_conteo", ["NO-EXISTE"])


def test_seed_conteo_is_conciliated_from_the_start(db):
    """Recién creada la base, el conteo de la semilla ya muestra sus SKUs (todavía sin contar)."""
    cur = db.cursor()
    cur.execute("SELECT skus_totales FROM v_resumen_conteo WHERE id_conteo = 'CONT-2026-11'")
    assert cur.fetchone()[0] >= 58  # los 58 SKU de la foto de stock
