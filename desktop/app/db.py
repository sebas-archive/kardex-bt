"""Consultas de la app de escritorio.

Los agregados salen de las vistas de Oracle (``V_*``): nunca se traen filas a Python para sumar.
Lo que no tiene vista (filas de conciliación, lecturas de un SKU, errores, conteos) se lee de
las tablas. **Ninguna función se debe llamar desde el hilo de la interfaz** (usar ``QueryWorker``).

Conexiones: **una por hilo**, reutilizada entre consultas. Abrir una por consulta llegó a miles de
conexiones en pocos minutos y la XE 11g respondía a veces ``ORA-12516``. Antes de reutilizarla se
hace ``ping``; si falla, o cambian el DSN o las credenciales, se abre otra; tras cualquier error se
descarta (puede haber quedado con una transacción a medias). Se abren siempre con
``btsync.store.connect_oracle``: varios hilos llamando a ``oracledb.connect`` a la vez abortan el
Instant Client.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import datetime

from btsync.store import DDL_YA_HECHO, connect_oracle, ddl_tolerante  # noqa: F401 (las usan los migrar())

from .models import (
    Conteo,
    ErrorFila,
    EstadoBatch,
    FilaConciliacion,
    Lectura,
    ResumenConteo,
)


# Conexión de cada hilo, por su identificador. No se usa ``threading.local``: PyQt crea y destruye el estado de Python
# de un hilo del pool en cada tarea, y lo guardado ahí se perdía entre consultas (cada una abría otra conexión).
# Los hilos del pool no caducan (``QueryRunner``), así que hay a lo sumo una conexión por hilo vivo.
_conexiones: dict[int, tuple[object, tuple[str, str, str]]] = {}
_candado = threading.Lock()


def _cerrar(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


def conexion_del_hilo():
    """La conexión guardada para este hilo, o ``None``."""
    with _candado:
        entrada = _conexiones.get(threading.get_ident())
    return None if entrada is None else entrada[0]


def liberar_conexion() -> None:
    """Cierra la conexión de este hilo (la próxima consulta abrirá otra)."""
    with _candado:
        entrada = _conexiones.pop(threading.get_ident(), None)
    if entrada is not None:
        _cerrar(entrada[0])


def _obtener():
    clave = (os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"])
    with _candado:
        entrada = _conexiones.get(threading.get_ident())
    conn = None
    if entrada is not None:
        conn, clave_guardada = entrada
        try:
            if clave_guardada != clave:
                raise ValueError("otro destino")
            conn.ping()
        except Exception:
            liberar_conexion()
            conn = None
    if conn is None:
        conn = connect_oracle(*clave)
        with _candado:
            _conexiones[threading.get_ident()] = (conn, clave)
    return conn


@contextmanager
def _conexion():
    conn = _obtener()
    try:
        yield conn
    except BaseException:
        liberar_conexion()  # tras un error la conexión puede quedar inutilizable o con una transacción abierta
        raise


def _f(valor) -> float | None:
    return None if valor is None else float(valor)


def _like(texto: str) -> str:
    """Patrón LIKE para «contiene»: ``%`` y ``_`` del usuario no son comodines."""
    escapado = texto.upper().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


def _fila_conciliacion(r) -> FilaConciliacion:
    return FilaConciliacion(
        sku=r[0], nombre=r[1], categoria=r[2], cant_sistema=_f(r[3]), cant_contada=_f(r[4]),
        diferencia=_f(r[5]), diferencia_pct=_f(r[6]), valor_diferencia=_f(r[7]), clasificacion=r[8],
    )


def fetch_conteos() -> list[Conteo]:
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id_conteo, nombre, estado FROM conteos ORDER BY fecha_inicio DESC, id_conteo")
        return [Conteo(*row) for row in cur]


def fetch_resumen(id_conteo: str) -> ResumenConteo | None:
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id_conteo, skus_totales, contados, avance_pct, ok, faltantes, sobrantes, "
            "exactitud_pct, valor_faltante, valor_sobrante FROM v_resumen_conteo WHERE id_conteo = :c",
            c=id_conteo,
        )
        r = cur.fetchone()
    if r is None:
        return None
    return ResumenConteo(r[0], int(r[1]), int(r[2]), float(r[3]), int(r[4]), int(r[5]), int(r[6]),
                         float(r[7]), float(r[8]), float(r[9]))


# Órdenes permitidos de la conciliación: la clave viene de la vista, el SQL sale de aquí (nunca se concatena lo recibido).
_ORDENES = {
    "sku": "k.sku",
    "valor": "ABS(k.valor_diferencia) DESC NULLS LAST, k.sku",
    "pct": "ABS(k.diferencia_pct) DESC NULLS LAST, k.sku",
}


def fetch_conciliacion(
    id_conteo: str,
    clasificacion: str | None = None,
    categoria: str | None = None,
    texto: str | None = None,
    limit: int = 1000,
    solo_diferencia: bool = False,
    valor_min: float | None = None,
    orden: str = "sku",
) -> list[FilaConciliacion]:
    """Filas de la conciliación con los filtros de la vista.

    ``solo_diferencia`` deja fuera lo que cuadra y lo no contado; ``valor_min`` exige |valor de la diferencia| ≥ ese
    monto (falte o sobre); ``orden`` es ``sku``, ``valor`` (mayor |valor| primero) o ``pct`` (mayor |%| primero).
    """
    if orden not in _ORDENES:
        raise ValueError(f"orden inválido: {orden!r}")
    filtros, binds = [], {"c": id_conteo, "lim": limit}
    if solo_diferencia:
        filtros.append("AND k.diferencia IS NOT NULL AND k.diferencia <> 0")
    if valor_min:
        filtros.append("AND ABS(k.valor_diferencia) >= :vmin")
        binds["vmin"] = valor_min
    if clasificacion:
        filtros.append("AND k.clasificacion = :cl")
        binds["cl"] = clasificacion
    if categoria:
        filtros.append("AND p.categoria = :cat")
        binds["cat"] = categoria
    if texto and texto.strip():
        filtros.append("AND (UPPER(k.sku) LIKE :t ESCAPE '\\' OR UPPER(p.nombre) LIKE :t ESCAPE '\\')")
        binds["t"] = _like(texto.strip())
    sql = (
        "SELECT * FROM ("
        " SELECT k.sku, p.nombre, p.categoria, k.cant_sistema, k.cant_contada, k.diferencia,"
        "        k.diferencia_pct, k.valor_diferencia, k.clasificacion"
        "   FROM conciliacion k JOIN productos p ON p.sku = k.sku"
        f"  WHERE k.id_conteo = :c {' '.join(filtros)}"
        f"  ORDER BY {_ORDENES[orden]}) WHERE ROWNUM <= :lim"
    )
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(sql, binds)
        return [_fila_conciliacion(r) for r in cur]


def fetch_dif_por_categoria(id_conteo: str) -> list[tuple[str, float]]:
    """(categoría, valor de la diferencia en pesos) de V_DIF_CATEGORIA."""
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT categoria, valor_diferencia FROM v_dif_categoria WHERE id_conteo = :c ORDER BY categoria",
            c=id_conteo,
        )
        return [(r[0], float(r[1])) for r in cur]


def fetch_top_desvios(id_conteo: str, n: int = 10) -> list[FilaConciliacion]:
    """Los ``n`` SKU con mayor |valor de la diferencia| (V_TOP_DESVIOS); los SIN_CONTAR van al final."""
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM ("
            " SELECT t.sku, t.nombre, t.categoria, k.cant_sistema, k.cant_contada, t.diferencia,"
            "        k.diferencia_pct, t.valor_diferencia, t.clasificacion"
            "   FROM v_top_desvios t JOIN conciliacion k ON k.id_conteo = t.id_conteo AND k.sku = t.sku"
            "  WHERE t.id_conteo = :c"
            "  ORDER BY ABS(t.valor_diferencia) DESC NULLS LAST, t.sku) WHERE ROWNUM <= :n",
            c=id_conteo, n=n,
        )
        return [_fila_conciliacion(r) for r in cur]


def fetch_distribucion(id_conteo: str) -> dict[str, int]:
    """Cantidad de SKU por clasificación, a partir de V_RESUMEN_CONTEO."""
    resumen = fetch_resumen(id_conteo)
    if resumen is None:
        return {"OK": 0, "FALTANTE": 0, "SOBRANTE": 0, "SIN_CONTAR": 0}
    return {"OK": resumen.ok, "FALTANTE": resumen.faltantes, "SOBRANTE": resumen.sobrantes,
            "SIN_CONTAR": resumen.sin_contar}


def fetch_actividad(id_conteo: str) -> list[tuple[str, str, int]]:
    """(operador, hora 'AAAA-MM-DD HH:MM' en UTC, lecturas) de V_ACTIVIDAD."""
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT operador, TO_CHAR(hora, 'YYYY-MM-DD HH24:MI'), registros FROM v_actividad "
            "WHERE id_conteo = :c ORDER BY hora, operador",
            c=id_conteo,
        )
        return [(r[0], r[1], int(r[2])) for r in cur]


def fetch_lecturas(id_conteo: str, sku: str) -> list[Lectura]:
    """Todas las lecturas de un SKU, de la más antigua a la más reciente, marcando cuál es la vigente."""
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT cantidad, operador, fecha_captura, vigente, nota "
            "FROM registros_procesados WHERE id_conteo = :c AND sku = :s "
            "ORDER BY fecha_captura, id_registro",
            c=id_conteo, s=sku,
        )
        return [Lectura(float(r[0]), r[1], r[2], r[3] == "S", r[4]) for r in cur]


def fetch_estado_batch() -> EstadoBatch:
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT pendientes, procesando, procesados, errores, ultimo_run, ultimo_origen FROM v_estado_batch")
        r = cur.fetchone()
    ultimo_run: datetime | None = r[4]
    return EstadoBatch(int(r[0]), int(r[1]), int(r[2]), int(r[3]), ultimo_run, r[5])


def fetch_errores(limit: int = 100) -> list[ErrorFila]:
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM (SELECT id_transito, uuid_dispositivo, seq, mensaje_error, datos_raw, "
            "fecha_recepcion FROM captura_transito WHERE estado = 'ERROR' ORDER BY id_transito DESC) "
            "WHERE ROWNUM <= :n",
            n=limit,
        )
        return [ErrorFila(int(r[0]), r[1], int(r[2]), r[3], r[4], r[5]) for r in cur]


def cerrar_conteo(id_conteo: str) -> None:
    """Procesa lo pendiente, cierra el conteo y lo concilia (irreversible)."""
    with _conexion() as conn:
        conn.cursor().callproc("pkg_batch.cerrar_conteo", [id_conteo])


def reprocesar_errores(id_conteo: str | None = None) -> None:
    """Devuelve a PENDIENTE las filas en ERROR (de un conteo o todas) y las procesa."""
    with _conexion() as conn:
        conn.cursor().callproc("pkg_batch.reprocesar_errores", [id_conteo])


def procesar_ahora() -> None:
    with _conexion() as conn:
        conn.cursor().callproc("pkg_batch.procesar_pendientes", ["MANUAL"])
