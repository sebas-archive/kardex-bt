"""Capa de datos del escritorio contra el escenario fijo de conciliación.

Escenario de referencia (``server/tests/fixtures/escenario_conciliacion.sql``): A1 101 (sistema 100),
A2 45 (50), A3 23 (20), A4 sin contar (10), A5 4 (sistema 0). La lectura anterior de A1 (60) quedó
reemplazada. Todas las lecturas son de las 16:40 UTC.
"""

import pytest

from app import db as dbq
from app.auth import ADMIN, INVENTARIO, ErrorDeAcceso, Sesion
from app.models import ErrorFila, EstadoBatch, FilaInventario, Lectura
from conftest import connect, staging

C = dbq.conteo_actual()
T0 = 1731170400000


@pytest.fixture
def contado(escenario):
    """El escenario con sus lecturas ya procesadas por el batch."""
    escenario.cargar_lecturas()
    dbq.procesar_ahora()
    return escenario


def test_el_conteo_es_uno_solo_y_se_llama_actual():
    assert dbq.conteo_actual() == "ACTUAL"


def test_fetch_resumen_del_conteo_continuo(contado):
    r = dbq.fetch_resumen()
    assert r is not None
    assert (r.skus_totales, r.contados, r.avance_pct) == (65, 4, 6.15)
    assert (r.faltantes, r.sobrantes) == (1, 3)
    assert r.sin_contar == 61


def test_fetch_conciliacion_cinco_columnas(contado):
    filas = {f.sku: f for f in dbq.fetch_conciliacion()}
    assert set(filas) >= {"A1", "A2", "A3", "A4", "A5"} and len(filas) == 65
    a1, a2, a4, a5 = filas["A1"], filas["A2"], filas["A4"], filas["A5"]
    assert isinstance(a1, FilaInventario)
    assert (a1.cant_sistema, a1.cant_contada) == (100.0, 101.0)
    assert (a2.cant_sistema, a2.cant_contada) == (50.0, 45.0)
    assert a4.cant_contada is None              # sin lectura: vacío, no 0
    assert (a5.cant_sistema, a5.cant_contada) == (0.0, 4.0)


def test_fetch_conciliacion_busca_por_sku_o_nombre_y_limita(contado):
    assert [f.sku for f in dbq.fetch_conciliacion("A3")] == ["A3"]
    assert [f.sku for f in dbq.fetch_conciliacion("producto a2")] == ["A2"]
    assert dbq.fetch_conciliacion("100%") == []   # el % no es comodín
    assert len(dbq.fetch_conciliacion(limit=2)) == 2


def test_fetch_lecturas_marca_la_vigente_y_la_foto(contado):
    lecturas = dbq.fetch_lecturas("A1")
    assert isinstance(lecturas[0], Lectura)
    assert [(l.cantidad, l.operador, l.vigente) for l in lecturas] == [(60.0, "Ana", False), (101.0, "Luis", True)]
    assert dbq.fetch_lecturas("A4") == []


def test_fetch_estado_batch(contado):
    estado = dbq.fetch_estado_batch()
    assert isinstance(estado, EstadoBatch)
    assert estado.pendientes == 0 and estado.procesados >= 5
    assert estado.ultimo_run is not None and estado.ultimo_origen == "MANUAL"


def test_fetch_errores_trae_sku_y_motivo(contado):
    conn = connect()
    try:
        staging(conn, "tst-d1", 1, T0, C, "ZZ9", 7)
        dbq.procesar_ahora()
    finally:
        conn.close()
    errores = {e.id_transito: e for e in dbq.fetch_errores()}
    error = next(e for e in errores.values() if e.sku == "ZZ9")
    assert isinstance(error, ErrorFila)
    assert error.mensaje_error == "SKU_DESCONOCIDO" and error.cantidad == "7"
    assert error.uuid_dispositivo == "tst-d1" and error.seq == 1


def test_crear_producto_inserta_stock_cero_y_reprocesa(contado):
    conn = connect()
    try:
        staging(conn, "tst-d2", 1, T0, C, "ZZ9", 7)
        dbq.procesar_ahora()
        admin = Sesion("ana.gomez", "Ana Gómez", ADMIN)
        dbq.crear_producto(admin, "ZZ9", "Producto nuevo", "Aseo")
        conn.commit()
        cur = conn.cursor()
        cur.execute("SELECT nombre, categoria FROM productos WHERE sku = 'ZZ9'")
        assert cur.fetchone() == ("Producto nuevo", "Aseo")
        cur.execute("SELECT cantidad_sistema FROM stock_sistema WHERE id_conteo = :c AND sku = 'ZZ9'", c=C)
        assert cur.fetchone() == (0,)
        dbq.reprocesar_errores()
        assert "ZZ9" not in {e.sku for e in dbq.fetch_errores()}
    finally:
        conn.close()
    fila = next(f for f in dbq.fetch_conciliacion("ZZ9"))
    assert (fila.cant_sistema, fila.cant_contada) == (0.0, 7.0)


def test_crear_producto_solo_administrador(contado):
    with pytest.raises(ErrorDeAcceso, match="Administrador"):
        dbq.crear_producto(Sesion("luis", "Luis Ortiz", INVENTARIO), "ZZ8", "Otro", "Aseo")


def test_fetch_actividad_por_operador(contado):
    por_operador: dict[str, int] = {}
    for operador, hora, registros in dbq.fetch_actividad():
        por_operador[operador] = por_operador.get(operador, 0) + registros
        assert hora.startswith("2024-11-09 16:")
    assert por_operador == {"Ana": 3, "Luis": 2}


def test_fetch_por_categoria_es_la_diferencia_en_unidades(contado):
    datos = dict(dbq.fetch_por_categoria())
    assert (datos["Abarrotes"], datos["Aseo"], datos["Lácteos"]) == (-4.0, 3.0, 4.0)


def test_fetch_series_seis_graficas(contado):
    datos = dbq.fetch_series()
    assert {"Abarrotes", "Aseo", "Lácteos"} <= set(datos["_categorias"])
    assert len(datos["avance_categoria"]) == len(datos["_categorias"])
    assert all(0.0 <= pct <= 100.0 for _c, pct in datos["avance_categoria"])
    assert dict(datos["contados_pendientes"]) == {"contados": 4.0, "pendientes": 61.0}
    assert datos["dona"] == datos["contados_pendientes"]
    assert len(datos["por_hora"]) == 1 and datos["por_hora"][0][1] == 5.0
    assert dict(datos["top_categorias"])["Abarrotes"] == 3.0
    assert datos["danados"] == []
    assert datos["batch"] and datos["batch"][-1][1] == 5.0
    assert len(datos["batch"]) == len(datos["batch_errores"])


def test_fetch_series_filtra_por_categoria(contado):
    datos = dbq.fetch_series("Aseo", top=1)
    assert [c for c, _ in datos["avance_categoria"]] == ["Aseo"]
    assert [c for c, _ in datos["top_categorias"]] == ["Aseo"]
    assert dict(datos["contados_pendientes"])["contados"] == 1.0
    assert dict(datos["contados_pendientes"])["pendientes"] >= 1.0
