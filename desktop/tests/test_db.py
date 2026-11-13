"""Capa de datos de la app de escritorio, contra el escenario fijo T-01.

Lecturas: A1 60 Ana y luego A1 101 Luis (recuento), A2 45 Ana, A3 23 Ana, A5 4 Luis;
stock A1 100, A2 50, A3 20, A4 10 (A5 no está en la foto). Ver server/tests/fixtures.
"""

import threading

import oracledb
import pytest

from app import db as dbq
from app.models import ResumenConteo
from conftest import connect, staging

C = "T-01"
T0 = 1731170400000


@pytest.fixture
def contado(escenario):
    """El escenario con sus 5 lecturas ya procesadas por el batch."""
    escenario.cargar_lecturas()
    dbq.procesar_ahora()
    return escenario


def test_fetch_resumen_matches_scenario(contado):
    assert dbq.fetch_resumen(C) == ResumenConteo(C, 5, 4, 80.0, 1, 1, 2, 25.0, -5000.0, 11800.0)


def test_fetch_resumen_unknown_conteo_is_none(contado):
    assert dbq.fetch_resumen("NO-EXISTE") is None


def test_fetch_conteos_lists_the_scenario(contado):
    by_id = {c.id_conteo: c for c in dbq.fetch_conteos()}
    assert by_id[C].estado == "ABIERTO" and by_id[C].nombre == "Conteo de prueba"
    assert "CONT-2026-11" in by_id  # el de la semilla


def test_fetch_conciliacion_filter_faltante_returns_only_a2(contado):
    rows = dbq.fetch_conciliacion(C, clasificacion="FALTANTE", categoria=None, texto=None)
    assert [r.sku for r in rows] == ["A2"]
    a2 = rows[0]
    assert (a2.nombre, a2.categoria) == ("Producto A2", "Abarrotes")
    assert (a2.cant_sistema, a2.cant_contada, a2.diferencia) == (50, 45, -5)
    assert (a2.diferencia_pct, a2.valor_diferencia, a2.clasificacion) == (-10.0, -5000.0, "FALTANTE")


def test_fetch_conciliacion_text_filter_a3_returns_one_row(contado):
    assert [r.sku for r in dbq.fetch_conciliacion(C, None, None, "A3")] == ["A3"]
    assert [r.sku for r in dbq.fetch_conciliacion(C, None, None, "producto a3")] == ["A3"]  # sin mayúsculas
    assert [r.sku for r in dbq.fetch_conciliacion(C, None, None, None)] == ["A1", "A2", "A3", "A4", "A5"]
    assert dbq.fetch_conciliacion(C, None, None, "100%") == []  # el % no es comodín


def test_fetch_conciliacion_category_filter_and_limit(contado):
    assert [r.sku for r in dbq.fetch_conciliacion(C, None, "Aseo", None)] == ["A3", "A4"]
    assert [r.sku for r in dbq.fetch_conciliacion(C, None, None, None, limit=2)] == ["A1", "A2"]


def test_top_desvios_order_a3_a2_a5_a1_a4(contado):
    assert [r.sku for r in dbq.fetch_top_desvios(C)] == ["A3", "A2", "A5", "A1", "A4"]
    top2 = dbq.fetch_top_desvios(C, n=2)
    assert [(r.sku, r.valor_diferencia) for r in top2] == [("A3", 9000.0), ("A2", -5000.0)]
    assert dbq.fetch_top_desvios(C)[-1].valor_diferencia is None  # SIN_CONTAR al final


def test_dif_por_categoria_values(contado):
    assert dbq.fetch_dif_por_categoria(C) == [("Abarrotes", -3000.0), ("Aseo", 9000.0), ("Lácteos", 2800.0)]


def test_distribucion_counts(contado):
    assert dbq.fetch_distribucion(C) == {"OK": 1, "FALTANTE": 1, "SOBRANTE": 2, "SIN_CONTAR": 1}


def test_actividad_by_operator(contado):
    por_operador = {}
    for operador, hora, registros in dbq.fetch_actividad(C):
        por_operador[operador] = por_operador.get(operador, 0) + registros
        assert hora.startswith("2024-11-09 16:")  # las lecturas son de 16:40 UTC
    assert por_operador == {"Ana": 3, "Luis": 2}


def test_fetch_lecturas_a1_returns_the_recount_as_the_current_one(contado):
    lecturas = dbq.fetch_lecturas(C, "A1")
    assert [(l.cantidad, l.operador, l.vigente) for l in lecturas] == [
        (60.0, "Ana", False),      # la primera lectura quedó reemplazada
        (101.0, "Luis", True),     # el recuento es la que vale
    ]
    assert dbq.fetch_lecturas(C, "A4") == []  # nadie contó A4


def test_cerrar_conteo_turns_sin_contar_into_faltante(contado):
    dbq.cerrar_conteo(C)
    assert dbq.fetch_resumen(C) == ResumenConteo(C, 5, 5, 100.0, 1, 2, 2, 20.0, -10000.0, 11800.0)
    assert {c.id_conteo: c.estado for c in dbq.fetch_conteos()}[C] == "CERRADO"
    assert dbq.fetch_distribucion(C)["SIN_CONTAR"] == 0


def test_reprocesar_errores_moves_error_rows_to_processed_after_fix(contado):
    conn = connect()
    try:
        tid = staging(conn, "tst-d1", 1, T0, C, "ZZ9", 7)
        dbq.procesar_ahora()
        errores = {e.id_transito: e for e in dbq.fetch_errores()}
        assert errores[tid].mensaje_error == "SKU_DESCONOCIDO"
        assert (errores[tid].uuid_dispositivo, errores[tid].seq) == ("tst-d1", 1)
        assert errores[tid].datos_raw.startswith("REC|1|")

        conn.cursor().execute(
            "INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit) "
            "VALUES ('ZZ9', 'Producto dado de alta después', 'Aseo', 'UND', 100)"
        )
        conn.commit()
        dbq.reprocesar_errores(C)
        assert tid not in {e.id_transito for e in dbq.fetch_errores()}
        cur = conn.cursor()
        cur.execute("SELECT estado FROM captura_transito WHERE id_transito = :i", i=tid)
        assert cur.fetchone() == ("PROCESADO",)
    finally:
        conn.close()


def test_fetch_estado_batch_counts_pendientes_and_errores(contado):
    conn = connect()
    try:
        antes = dbq.fetch_estado_batch()
        staging(conn, "tst-d2", 1, T0, C, "ZZ9", 1)   # quedará en ERROR
        dbq.procesar_ahora()
        staging(conn, "tst-d2", 2, T0, C, "A1", 1)    # se queda PENDIENTE
        ahora = dbq.fetch_estado_batch()
    finally:
        conn.close()
    assert ahora.pendientes - antes.pendientes == 1
    assert ahora.errores - antes.errores == 1
    assert ahora.ultimo_run is not None and ahora.ultimo_origen == "MANUAL"


# ------------------------------------------------- una conexión por hilo (no una por consulta)
# Una consulta por conexión nueva llegó a 5.938 conexiones en pocos minutos de pruebas y la XE 11g
# respondió a veces ORA-12516 (el listener no encuentra manejador libre).
def test_connection_is_reused_in_the_same_thread(contado):
    dbq.fetch_conteos()
    primera = dbq._local.conn
    dbq.fetch_resumen(C)
    dbq.fetch_dif_por_categoria(C)
    assert dbq._local.conn is primera
    dbq.liberar_conexion()
    assert getattr(dbq._local, "conn", None) is None


def test_a_dead_connection_is_replaced_transparently(contado):
    dbq.fetch_conteos()
    muerta = dbq._local.conn
    muerta.close()                                    # p. ej. Oracle la cortó por inactividad
    assert dbq.fetch_resumen(C) is not None           # el ping falla y se reconecta sola
    assert dbq._local.conn is not muerta


def test_a_failure_discards_the_connection_and_changing_the_dsn_never_reuses_it(contado, monkeypatch):
    dbq.fetch_conteos()
    vieja = dbq._local.conn
    monkeypatch.setenv("DB_DSN", "127.0.0.1:1/XE")    # otro destino: nunca se reutiliza la conexión vieja
    with pytest.raises(oracledb.DatabaseError):
        dbq.fetch_conteos()
    assert getattr(dbq._local, "conn", None) is None
    monkeypatch.undo()
    assert dbq.fetch_resumen(C) is not None
    assert dbq._local.conn is not vieja


def test_many_threads_share_one_connection_each(contado, monkeypatch):
    conectadas = []
    original = dbq.connect_oracle
    monkeypatch.setattr(dbq, "connect_oracle", lambda *a: (conectadas.append(1), original(*a))[1])
    errores = []

    def trabajador():
        try:
            for _ in range(25):
                assert dbq.fetch_resumen(C).skus_totales == 5
        except Exception as exc:
            errores.append(exc)
        finally:
            dbq.liberar_conexion()

    hilos = [threading.Thread(target=trabajador) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)
    assert errores == []
    assert len(conectadas) == 8      # una por hilo, no una por consulta (eran 200)


def _skus(filas):
    return [f.sku for f in filas]


def test_fetch_conciliacion_only_rows_with_difference(contado):
    assert _skus(dbq.fetch_conciliacion(C, solo_diferencia=True)) == ["A1", "A2", "A3", "A5"]  # A4 (sin contar) no tiene diferencia


def test_fetch_conciliacion_minimum_value(contado):
    assert _skus(dbq.fetch_conciliacion(C, valor_min=5000)) == ["A2", "A3"]      # |valor| ≥ 5.000, falte o sobre


def test_fetch_conciliacion_order_is_a_whitelist(contado):
    assert _skus(dbq.fetch_conciliacion(C, orden="valor")) == ["A3", "A2", "A5", "A1", "A4"]   # mayor |valor| primero
    assert _skus(dbq.fetch_conciliacion(C, orden="pct")) == ["A3", "A2", "A1", "A4", "A5"]     # mayor |%| primero
    with pytest.raises(ValueError):
        dbq.fetch_conciliacion(C, orden="1; DROP TABLE conteos")  # el orden no se concatena tal cual
