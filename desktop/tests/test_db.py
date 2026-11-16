"""Capa de datos del escritorio contra el escenario fijo de conciliación.

Escenario de referencia (``server/tests/fixtures/escenario_conciliacion.sql``): A1 101 (sistema 100),
A2 45 (50), A3 23 (20), A4 sin contar (10), A5 4 (sistema 0). La lectura anterior de A1 (60) quedó
reemplazada. Todas las lecturas son de las 16:40 UTC.

Los SKU que no están en el catálogo ya **no** quedan en ERROR: quedan en ``NUEVO_SKU`` (aviso flotante);
``ZZ9`` es el SKU desconocido de prueba y el propio escenario limpia todo lo que se cree con él.
"""

import pytest

from app import db as dbq
from app.auth import ADMIN, INVENTARIO, ErrorDeAcceso, Sesion
from app.models import ErrorFila, EstadoBatch, FilaInventario, Lectura, NuevoSkuFila
from conftest import connect, staging

C = dbq.conteo_actual()
T0 = 1731170400000


@pytest.fixture
def contado(escenario):
    """El escenario con sus lecturas ya procesadas por el batch."""
    escenario.cargar_lecturas()
    dbq.procesar_ahora()
    return escenario


def _procesar(conn, uuid: str, seq: int, sku: str, cant) -> None:
    staging(conn, uuid, seq, T0, C, sku, cant)
    dbq.procesar_ahora()


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


def test_fetch_estado_batch_incluye_nuevos_y_descartados(contado):
    estado = dbq.fetch_estado_batch()
    assert isinstance(estado, EstadoBatch)
    assert estado.pendientes == 0 and estado.procesados >= 5
    assert estado.nuevos >= 0 and estado.descartados >= 0      # contadores nuevos, aunque la BD viva tenga filas
    assert estado.ultimo_run is not None and estado.ultimo_origen == "MANUAL"


def test_fetch_errores_trae_sku_y_motivo(contado):
    conn = connect()
    try:
        _procesar(conn, "tst-d1", 1, "A1", "abc")              # cantidad inválida: esto sí es un error real
        dbq.procesar_ahora()
    finally:
        conn.close()
    errores = {e.id_transito: e for e in dbq.fetch_errores()}
    error = next(e for e in errores.values() if e.sku == "A1" and e.mensaje_error == "CANTIDAD_INVALIDA")
    assert isinstance(error, ErrorFila)
    assert error.cantidad == "abc"
    assert error.uuid_dispositivo == "tst-d1" and error.seq == 1


def test_un_sku_desconocido_queda_en_nuevo_sku_no_en_error(contado):
    estado_antes = dbq.fetch_estado_batch()
    conn = connect()
    try:
        _procesar(conn, "tst-n1", 1, "zz9", 7)
    finally:
        conn.close()
    estado = dbq.fetch_estado_batch()
    assert estado.nuevos >= estado_antes.nuevos + 1          # cuenta como nuevo, no como error
    assert "ZZ9" not in {e.sku.upper() for e in dbq.fetch_errores()}
    nuevos = [f for f in dbq.fetch_nuevos_sku() if f.sku.upper() == "ZZ9"]
    assert len(nuevos) == 1
    assert isinstance(nuevos[0], NuevoSkuFila)
    assert nuevos[0].uuid_dispositivo == "tst-n1" and nuevos[0].seq == 1 and nuevos[0].cantidad == "7"
    assert nuevos[0].fecha_recepcion is not None


def test_fetch_nuevos_sku_ordena_por_fecha_y_agrupa_por_sku(contado):
    conn = connect()
    try:
        staging(conn, "tst-n2", 1, T0, C, "zz9", 2)
        staging(conn, "tst-n2", 2, T0 + 1000, C, "ZZ9", 3)
        dbq.procesar_ahora()
    finally:
        conn.close()
    nuevos = [f for f in dbq.fetch_nuevos_sku() if f.sku.upper() == "ZZ9"]
    assert len(nuevos) == 2
    assert [f.seq for f in nuevos] == [2, 1]                   # la más reciente primero
    assert {f.sku.upper() for f in nuevos} == {"ZZ9"}          # el SKU conserva lo que tecleó el operador


def _avisos_nuevo_sku() -> list[tuple[str, str, str]]:
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT texto, seccion, rol FROM notificaciones_tst "
                    "WHERE tipo = 'NUEVO_SKU' AND texto LIKE 'Nuevo SKU zz9:%' ORDER BY id")
        return cur.fetchall()
    finally:
        conn.close()


def test_fetch_nuevos_sku_deja_el_aviso_en_la_campana_y_no_lo_duplica(contado):
    """El backfill del sondeo cubre «la app estaba cerrada»: el aviso llega a Notificaciones y la clave lo
    hace idempotente (el sondeo pasa cada pocos segundos)."""
    conn = connect()
    try:
        _procesar(conn, "tst-n3", 1, "zz9", 6)
    finally:
        conn.close()
    dbq.fetch_nuevos_sku()
    dbq.fetch_nuevos_sku()
    assert _avisos_nuevo_sku() == [
        ("Nuevo SKU zz9: decide «Crear y procesar» o «No crear» en Sincronización.", "Sincronización", "ADMIN")]


def test_fetch_nuevos_sku_sigue_sin_la_tabla_de_notificaciones(contado, monkeypatch):
    """Instalación vieja (sin NOTIFICACIONES): el aviso flotante del escritorio no se puede perder."""
    from btsync import notificaciones as bn

    monkeypatch.setattr(bn, "TABLA", "notificaciones_que_no_existe")
    conn = connect()
    try:
        _procesar(conn, "tst-n4", 1, "zz9", 2)
    finally:
        conn.close()
    assert "ZZ9" in {f.sku.upper() for f in dbq.fetch_nuevos_sku()}



def test_nuevo_sku_alta_crea_el_producto_y_procesa_la_lectura(contado, auditoria_db):
    conn = connect()
    try:
        _procesar(conn, "tst-d2", 1, "zz9", 7)
        admin = Sesion("ana.gomez", "Ana Gómez", ADMIN)
        dbq.nuevo_sku_alta(admin, "zz9", "Producto nuevo", "Aseo")
        conn.commit()
        cur = conn.cursor()
        cur.execute("SELECT nombre, categoria FROM productos WHERE sku = 'ZZ9'")
        assert cur.fetchone() == ("Producto nuevo", "Aseo")
        cur.execute("SELECT cantidad_sistema FROM stock_sistema WHERE id_conteo = :c AND sku = 'ZZ9'", c=C)
        assert cur.fetchone() == (0,)
        cur.execute("SELECT accion, detalle FROM auditoria_tst ORDER BY id DESC")
        accion, detalle = cur.fetchone()
        assert accion == "Dió de alta un SKU" and "lectura procesada" in detalle
    finally:
        conn.close()
    assert "ZZ9" not in {f.sku.upper() for f in dbq.fetch_nuevos_sku()}
    fila = next(f for f in dbq.fetch_conciliacion("ZZ9"))
    assert (fila.cant_sistema, fila.cant_contada) == (0.0, 7.0)


def test_nuevo_sku_alta_normaliza_el_sku_y_exige_administrador(contado):
    with pytest.raises(ErrorDeAcceso, match="Administrador"):
        dbq.nuevo_sku_alta(Sesion("luis", "Luis Ortiz", INVENTARIO), "zz9", "Otro", "Aseo")
    with pytest.raises(ErrorDeAcceso, match="obligatorios"):
        dbq.nuevo_sku_alta(Sesion("ana.gomez", "Ana Gómez", ADMIN), "zz9", "", "Aseo")


def test_descartar_nuevo_sku_no_lo_cuenta_y_es_idempotente(contado, auditoria_db):
    conn = connect()
    try:
        _procesar(conn, "tst-d3", 1, "zz9", 5)
    finally:
        conn.close()
    admin = Sesion("ana.gomez", "Ana Gómez", ADMIN)
    dbq.descartar_nuevo_sku(admin, "zz9")
    estado = dbq.fetch_estado_batch()
    assert "ZZ9" not in {f.sku.upper() for f in dbq.fetch_nuevos_sku()}
    assert estado.descartados >= 1
    assert dbq.fetch_conciliacion("ZZ9") == []                 # descartada: no crea producto ni cuenta
    dbq.descartar_nuevo_sku(admin, "ZZ9")                      # sin filas NUEVO_SKU: no-op, no falla
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT accion, detalle FROM auditoria_tst ORDER BY id DESC")
        accion, detalle = cur.fetchone()
    assert accion == "Descartó una lectura de nuevo SKU" and detalle == "ZZ9"


def test_descartar_nuevo_sku_exige_administrador(contado):
    with pytest.raises(ErrorDeAcceso, match="Administrador"):
        dbq.descartar_nuevo_sku(Sesion("luis", "Luis Ortiz", INVENTARIO), "ZZ9")


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
