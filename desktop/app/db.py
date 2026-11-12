"""Consultas de la app de escritorio.

Los agregados salen de las vistas de Oracle (``V_*``): nunca se traen filas a Python para sumar.
Lo que no tiene vista (filas de conciliación, detalle por ubicación, errores, conteos) se lee de
las tablas. Cada función abre su propia conexión y la cierra, así que se puede llamar desde
cualquier hilo de trabajo. **Ninguna se debe llamar desde el hilo de la interfaz** (usar
``QueryWorker``).

Toda conexión pasa por ``btsync.store.connect_oracle``: varios hilos llamando a
``oracledb.connect`` a la vez abortan el Instant Client.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime

from btsync.store import connect_oracle

from .models import Conteo, ErrorFila, EstadoBatch, FilaConciliacion, Lectura, ResumenConteo


@contextmanager
def _conexion():
    conn = connect_oracle(os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"])
    try:
        yield conn
    finally:
        conn.close()


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


def fetch_conciliacion(
    id_conteo: str,
    clasificacion: str | None = None,
    categoria: str | None = None,
    texto: str | None = None,
    limit: int = 1000,
) -> list[FilaConciliacion]:
    filtros, binds = [], {"c": id_conteo, "lim": limit}
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
        "  ORDER BY k.sku) WHERE ROWNUM <= :lim"
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


def fetch_avance_zona(id_conteo: str) -> list[tuple[str, int, int]]:
    """(zona, ubicaciones con lectura, ubicaciones de la zona) de V_AVANCE_ZONA."""
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT zona, ubicaciones_con_lectura, ubicaciones_totales FROM v_avance_zona "
            "WHERE id_conteo = :c ORDER BY zona",
            c=id_conteo,
        )
        return [(r[0], int(r[1]), int(r[2])) for r in cur]


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
    """Detalle por ubicación de un SKU: todas las lecturas, marcando cuál es la vigente."""
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT cod_ubicacion, cantidad, operador, fecha_captura, vigente, nota "
            "FROM registros_procesados WHERE id_conteo = :c AND sku = :s "
            "ORDER BY cod_ubicacion, fecha_captura, id_registro",
            c=id_conteo, s=sku,
        )
        return [Lectura(r[0], float(r[1]), r[2], r[3], r[4] == "S", r[5]) for r in cur]


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
