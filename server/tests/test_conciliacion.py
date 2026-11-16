"""Conciliación del conteo continuo ACTUAL y vistas.

Valores exactos del escenario fijo (ver server/tests/fixtures/escenario_conciliacion.sql):
lecturas A1 60 (Ana) y luego A1 101 (Luis, recuento que la reemplaza), A2 45, A3 23, A5 4;
stock A1 100, A2 50, A3 20, A4 10, A5 0. A4 no tiene lectura.
"""

import threading

import pytest

from conftest import connect, staging

C = "ACTUAL"
T0 = 1731170400000
SKUS = ("A1", "A2", "A3", "A4", "A5")

# sku: (cant_sistema, cant_contada, diferencia, diferencia_pct) — sin clasificación ni valor.
ESPERADO = {
    "A1": (100, 101, 1, 1.00),
    "A2": (50, 45, -5, -10.00),
    "A3": (20, 23, 3, 15.00),
    "A4": (10, None, None, None),
    "A5": (0, 4, 4, None),
}
# skus_totales (60 de la semilla + 5 del escenario), contados, avance_pct, ok, faltantes, sobrantes,
# exactitud_pct, valor_faltante, valor_sobrante.
RESUMEN = (65, 4, 6.15, 0, 1, 3, 0, 5000, 13800)


def procesar(db):
    db.cursor().callproc("pkg_batch.procesar_pendientes")


def conciliacion(db, conteo=C):
    cur = db.cursor()
    cur.execute(
        "SELECT sku, cant_sistema, cant_contada, diferencia, diferencia_pct "
        "FROM conciliacion WHERE id_conteo = :c AND sku IN ('A1','A2','A3','A4','A5')",
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
    assert conciliacion(db) == ESPERADO


def test_resumen_matches_scenario_exactly(contado, db):
    assert resumen(db) == RESUMEN


def test_recount_updates_conciliation(contado, db):
    assert conciliacion(db)["A2"] == (50, 45, -5, -10.00)
    staging(db, "tst-c1", 1, T0 + 60_000, C, "A2", 50)  # más reciente que la lectura de 45
    procesar(db)
    assert conciliacion(db)["A2"] == (50, 50, 0, 0.00)
    assert conciliacion(db)["A1"] == ESPERADO["A1"]  # lo demás no cambia


def test_counted_sku_with_zero_stock_is_conciliated(contado, db):
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM stock_sistema WHERE id_conteo = :c AND sku = 'A5'", c=C)
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT cantidad_sistema FROM stock_sistema WHERE id_conteo = :c AND sku = 'A5'", c=C)
    assert cur.fetchone()[0] == 0
    assert conciliacion(db)["A5"] == (0, 4, 4, None)


def test_un_counted_sku_has_null_count_and_difference(contado, db):
    assert conciliacion(db)["A4"] == (10, None, None, None)


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
        "SELECT sku, valor_diferencia, nombre, categoria, diferencia, cant_sistema, cant_contada "
        "FROM v_top_desvios WHERE id_conteo = :c",
        c=C,
    )
    rows = [r for r in cur if r[0] in SKUS]
    assert [(r[0], r[1]) for r in rows] == [
        ("A3", 9000), ("A2", -5000), ("A5", 2800), ("A1", 2000), ("A4", 0),
    ]
    assert rows[0][2:] == ("Producto A3", "Aseo", 3, 20, 23)


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
            "SELECT pendientes, procesando, procesados, errores, nuevos, descartados, "
            "       ultimo_run, ultimo_origen FROM v_estado_batch"
        )
        return cur.fetchone()

    antes = estado_batch()
    staging(db, "tst-c1", 1, T0, C, "ZZ9", 1)       # SKU desconocido: quedará en NUEVO_SKU (no error)
    staging(db, "tst-c1", 2, T0, C, "A1", 1)        # quedará PROCESADO
    procesar(db)
    staging(db, "tst-c1", 3, T0, C, "A2", 1)        # se queda PENDIENTE
    ahora = estado_batch()
    assert (ahora[0] - antes[0], ahora[1] - antes[1], ahora[2] - antes[2], ahora[3] - antes[3],
            ahora[4] - antes[4], ahora[5] - antes[5]) == (1, 0, 1, 0, 1, 0)
    assert ahora[6] is not None and ahora[7] == "MANUAL"


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
    assert conciliacion(db) == ESPERADO
    assert resumen(db) == RESUMEN


def test_seed_conteo_is_conciliated_from_the_start(db):
    """Recién creada la base, el conteo ACTUAL ya tiene sus SKUs (todavía sin contar)."""
    cur = db.cursor()
    cur.execute("SELECT skus_totales FROM v_resumen_conteo WHERE id_conteo = 'ACTUAL'")
    assert cur.fetchone()[0] >= 60
