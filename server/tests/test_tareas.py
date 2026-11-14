"""Tareas de conteo (Fase 3): estado calculado, avance y catálogo por operador.

Escenario propio: productos TA1 (sistema 10), TA2 (sistema 5) y TA3 (fuera de la tarea), tarea TT-1 asignada a
``tst-operador`` y TT-2 a otro operador. Todo con COMMIT real; se borra al terminar.
"""

import pytest

from btsync import tareas as t
from conftest import OPERADOR_ACTIVO, connect, staging

T0 = 1731170400000
UUID = "tst-tareas"


def _limpiar(cur) -> None:
    cur.execute("DELETE FROM revisiones WHERE id_conteo LIKE 'TT-%'")
    cur.execute("DELETE FROM conciliacion WHERE id_conteo LIKE 'TT-%'")
    cur.execute("DELETE FROM registros_procesados WHERE id_conteo LIKE 'TT-%'")
    cur.execute("DELETE FROM captura_transito WHERE uuid_dispositivo = :u", u=UUID)
    cur.execute("DELETE FROM stock_sistema WHERE id_conteo LIKE 'TT-%'")
    cur.execute("DELETE FROM conteos WHERE id_conteo LIKE 'TT-%'")
    cur.execute("DELETE FROM productos WHERE sku IN ('TA1', 'TA2', 'TA3')")


@pytest.fixture(scope="module")
def _conn():
    conn = connect()
    yield conn
    conn.close()


@pytest.fixture
def tarea(_conn):
    conn = _conn
    cur = conn.cursor()
    _limpiar(cur)
    for sku in ("TA1", "TA2", "TA3"):
        cur.execute("INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit, tolerancia_pct) "
                    "VALUES (:s, :n, 'Abarrotes', 'UND', 100, 0)", s=sku, n=f"Producto {sku}")
    cur.execute("INSERT INTO conteos (id_conteo, nombre, estado, almacen, operador, instrucciones) "
                "VALUES ('TT-1', 'Tarea uno', 'ABIERTO', 'ALM-01', :o, 'Solo estanteria A')", o=OPERADOR_ACTIVO)
    cur.execute("INSERT INTO conteos (id_conteo, nombre, estado, almacen, operador) "
                "VALUES ('TT-2', 'Tarea ajena', 'ABIERTO', 'ALM-02', 'tst-otro')")
    cur.execute("INSERT INTO conteos (id_conteo, nombre, estado) VALUES ('TT-G', 'Conteo general', 'ABIERTO')")
    cur.executemany("INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) VALUES (:1, :2, :3)",
                    [("TT-1", "TA1", 10), ("TT-1", "TA2", 5), ("TT-2", "TA1", 10)])
    conn.commit()
    seq = iter(range(1, 1000))

    def leer(sku, cant, conteo="TT-1"):
        n = next(seq)
        staging(conn, UUID, n, T0 + 1000 * n, conteo, sku, cant)
        cur.callproc("pkg_batch.procesar_pendientes")

    def una():
        return next(r for r in t.listar(cur) if r.id == "TT-1")

    try:
        yield type("Esc", (), {"conn": conn, "cur": cur, "leer": staticmethod(leer), "una": staticmethod(una)})
    finally:
        conn.rollback()
        _limpiar(cur)
        conn.commit()


# ------------------------------------------------------------------ estado_tarea (pura)
def _e(**kw):
    base = dict(cerrada=False, total=2, contados=0, lecturas=0, diferencias=0, errores=0, iniciada=False)
    return t.estado_tarea(**{**base, **kw})


def test_estado_tarea_asignada():
    assert _e() == t.ASIGNADA


def test_estado_tarea_en_progreso():
    assert _e(iniciada=True) == t.EN_PROGRESO


def test_estado_tarea_enviada_parcialmente():
    assert _e(iniciada=True, contados=1, lecturas=1) == t.ENVIADA_PARCIALMENTE


def test_estado_tarea_lectura_fuera_de_la_tarea_ya_es_parcial():
    assert _e(lecturas=1) == t.ENVIADA_PARCIALMENTE


def test_estado_tarea_sincronizada():
    assert _e(contados=2, lecturas=2) == t.SINCRONIZADA


def test_estado_tarea_con_diferencias():
    assert _e(contados=2, lecturas=2, diferencias=1) == t.CON_DIFERENCIAS


def test_estado_tarea_diferencia_sin_completar_sigue_parcial():
    assert _e(contados=1, lecturas=1, diferencias=1) == t.ENVIADA_PARCIALMENTE


def test_estado_tarea_con_error_gana_a_completa():
    assert _e(contados=2, lecturas=2, errores=1) == t.CON_ERROR


def test_estado_tarea_cerrada_gana_a_error():
    assert _e(cerrada=True, errores=3) == t.CERRADA


def test_estado_tarea_sin_productos_no_es_sincronizada():
    assert _e(total=0) == t.ASIGNADA


def test_estados_en_orden_y_con_nombre():
    assert t.ESTADOS == ("ASIGNADA", "EN_PROGRESO", "ENVIADA_PARCIALMENTE", "SINCRONIZADA", "CON_DIFERENCIAS",
                         "CERRADA", "CON_ERROR")
    assert t.NOMBRE_ESTADO[t.ENVIADA_PARCIALMENTE] == "Enviada parcialmente"
    assert set(t.NOMBRE_ESTADO) == set(t.ESTADOS)


# ------------------------------------------------------------------ listar
def test_listar_cuenta_contados_y_estado(tarea):
    r = tarea.una()
    assert (r.almacen, r.operador, r.instrucciones, r.total, r.contados, r.estado) == \
        ("ALM-01", OPERADOR_ACTIVO, "Solo estanteria A", 2, 0, t.ASIGNADA)
    tarea.cur.execute("UPDATE conteos SET iniciada = SYSTIMESTAMP WHERE id_conteo = 'TT-1'")
    tarea.conn.commit()
    assert tarea.una().estado == t.EN_PROGRESO
    tarea.leer("TA1", 10)
    assert (tarea.una().contados, tarea.una().estado) == (1, t.ENVIADA_PARCIALMENTE)
    tarea.leer("TA2", 5)
    assert (tarea.una().contados, tarea.una().estado) == (2, t.SINCRONIZADA)
    tarea.leer("TA2", 3)   # recuento con diferencia: reemplaza la lectura anterior
    assert tarea.una().estado == t.CON_DIFERENCIAS
    tarea.cur.callproc("pkg_batch.cerrar_conteo", ["TT-1"])
    assert tarea.una().estado == t.CERRADA


def test_listar_filtra_por_operador_y_omite_conteos_sin_operador(tarea):
    ids = [r.id for r in t.listar(tarea.cur, operador=OPERADOR_ACTIVO)]
    assert "TT-1" in ids and "TT-2" not in ids
    assert "TT-G" not in [r.id for r in t.listar(tarea.cur)]


def test_recuento_pedido_descuenta_hasta_nueva_lectura(tarea):
    tarea.leer("TA1", 10)
    tarea.leer("TA2", 1)
    assert tarea.una().estado == t.CON_DIFERENCIAS
    tarea.cur.execute("INSERT INTO revisiones (id_conteo, sku, accion, por) VALUES ('TT-1', 'TA2', 'RECUENTO', 'x')")
    tarea.conn.commit()
    assert (tarea.una().contados, tarea.una().estado) == (1, t.ENVIADA_PARCIALMENTE)
    tarea.leer("TA2", 5)
    assert (tarea.una().contados, tarea.una().estado) == (2, t.SINCRONIZADA)


def test_lectura_fuera_de_la_tarea_no_suma_avance(tarea):
    tarea.leer("TA3", 4)
    r = tarea.una()
    assert (r.contados, r.total, r.estado) == (0, 2, t.ENVIADA_PARCIALMENTE)


def test_error_en_staging_da_con_error(tarea):
    tarea.leer("NO-EXISTE", 1)   # SKU_DESCONOCIDO
    assert tarea.una().estado == t.CON_ERROR


def test_migrar_idempotente(tarea):
    t.migrar(tarea.conn)
    t.migrar(tarea.conn)
    assert tarea.una().id == "TT-1"


# ------------------------------------------------------------------ catálogo y INICIO
def test_catalogo_solo_trae_tareas_del_operador_y_generales(store, tarea):
    cat = store.catalog(OPERADOR_ACTIVO)
    ids = [x[0] for x in cat.tareas]
    assert "TT-1" in ids and "TT-2" not in ids and "TT-G" in ids
    tt1 = next(x for x in cat.tareas if x[0] == "TT-1")
    assert tt1 == ("TT-1", "Tarea uno", "ALM-01", "Solo estanteria A", "ASIGNADA", 2, 0)
    general = next(x for x in cat.tareas if x[0] == "TT-G")
    assert general[2] == "" and general[4] == "" and general[5:] == (0, 0)
    assert sorted(i for i in cat.items if i[0] == "TT-1") == [("TT-1", "TA1", "N"), ("TT-1", "TA2", "N")]
    assert not [i for i in cat.items if i[0] == "TT-2"]
    assert "10" not in repr([i for i in cat.items if i[0] == "TT-1"])   # conteo ciego


def test_catalogo_sin_cuenta_activa_solo_generales(store, tarea):
    ids = [x[0] for x in store.catalog(None).tareas]
    assert "TT-G" in ids and not [i for i in ids if i.startswith("TT-") and i != "TT-G"]


def test_catalogo_marca_recuento(store, tarea):
    tarea.leer("TA2", 1)
    tarea.cur.execute("INSERT INTO revisiones (id_conteo, sku, accion, por) VALUES ('TT-1', 'TA2', 'RECUENTO', 'x')")
    tarea.conn.commit()
    assert ("TT-1", "TA2", "S") in store.catalog(OPERADOR_ACTIVO).items


def test_marcar_iniciada_ignora_ajena_y_cerrada(store, tarea):
    tarea.cur.execute("INSERT INTO conteos (id_conteo, nombre, estado, operador) "
                      "VALUES ('TT-3', 'Cerrada', 'CERRADO', :o)", o=OPERADOR_ACTIVO)
    tarea.conn.commit()
    for id_tarea in ("TT-1", "TT-2", "TT-3", "NO-EXISTE"):
        store.marcar_iniciada(OPERADOR_ACTIVO, id_tarea)
    store.commit()
    tarea.cur.execute("SELECT id_conteo FROM conteos WHERE id_conteo LIKE 'TT-%' AND iniciada IS NOT NULL")
    assert tarea.cur.fetchall() == [("TT-1",)]
