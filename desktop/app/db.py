"""Consultas de la app de escritorio contra Oracle.

El conteo es **continuo y único** (``ACTUAL``): no hay varios conteos, cierres, almacenes ni tareas. Los
agregados salen de las vistas ``V_*`` y lo que no tiene vista se lee de las tablas.

**Ninguna función se debe llamar desde el hilo de la interfaz** (usar ``QueryWorker``/``QueryRunner``).

Conexiones: **una por hilo**, reutilizada entre consultas. Abrir una por consulta llegó a miles de
conexiones en pocos minutos y la XE respondía a veces ``ORA-12516``. Antes de reutilizarla se hace
``ping``; si falla, o cambian el DSN o las credenciales, se abre otra; tras cualquier error se
descarta (puede haber quedado con una transacción a medias).
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager

from btsync.store import DDL_YA_HECHO, connect_oracle, ddl_tolerante  # noqa: F401 (los usan los migrar())

from .models import (
    ErrorFila,
    EstadoBatch,
    FilaInventario,
    Lectura,
    ResumenConteo,
)

CONTEO = "ACTUAL"


# Conexión de cada hilo, por su identificador. No se usa ``threading.local``: PyQt crea y destruye el estado de Python
# de un hilo del pool en cada tarea, y lo guardado ahí se perdía entre consultas (cada una abría otra conexión).
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


# ------------------------------------------------------------------ conteo actual
def conteo_actual() -> str:
    """El identificador del único conteo: siempre ``ACTUAL``. Existe para no repetir la cadena en las vistas."""
    return CONTEO


def fetch_resumen() -> ResumenConteo | None:
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id_conteo, skus_totales, contados, avance_pct, ok, faltantes, sobrantes, exactitud_pct "
            "FROM v_resumen_conteo WHERE id_conteo = :c",
            c=CONTEO,
        )
        r = cur.fetchone()
    if r is None:
        return None
    return ResumenConteo(r[0], int(r[1]), int(r[2]), float(r[3]), int(r[4]), int(r[5]), int(r[6]), float(r[7]))


# ------------------------------------------------------------------ inventario
def fetch_conciliacion(texto: str | None = None, limit: int = 1000) -> list[FilaInventario]:
    """Producto a producto: cantidad contada (vacía si no hay lectura) y cantidad del sistema."""
    filtro, binds = "", {"c": CONTEO, "lim": limit}
    if texto and texto.strip():
        filtro = "AND (UPPER(k.sku) LIKE :t ESCAPE '\\' OR UPPER(p.nombre) LIKE :t ESCAPE '\\')"
        binds["t"] = _like(texto.strip())
    sql = (
        "SELECT * FROM ("
        " SELECT k.sku, p.nombre, p.categoria, k.cant_contada, k.cant_sistema"
        "   FROM conciliacion k JOIN productos p ON p.sku = k.sku"
        f"  WHERE k.id_conteo = :c {filtro}"
        "  ORDER BY k.sku) WHERE ROWNUM <= :lim"
    )
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(sql, binds)
        return [FilaInventario(r[0], r[1], r[2], _f(r[3]), _f(r[4])) for r in cur]


def fetch_lecturas(sku: str) -> list[Lectura]:
    """Todas las lecturas de un SKU, de la más antigua a la más reciente, marcando cuál es la vigente.

    La foto de evidencia se enlaza por la fila de staging original: ``registros_procesados.id_transito`` →
    ``captura_transito(uuid, seq)`` → ``fotos.ruta``.
    """
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT r.cantidad, r.operador, r.fecha_captura, r.vigente, r.nota, "
            "       (SELECT f.ruta FROM captura_transito t JOIN fotos f "
            "          ON f.uuid_dispositivo = t.uuid_dispositivo AND f.seq = t.seq "
            "         WHERE t.id_transito = r.id_transito) "
            "  FROM registros_procesados r "
            " WHERE r.id_conteo = :c AND r.sku = :s "
            " ORDER BY r.fecha_captura, r.id_registro",
            c=CONTEO, s=sku,
        )
        return [Lectura(_f(r[0]), r[1], r[2], r[3] == "S", r[4], r[5]) for r in cur]


# ------------------------------------------------------------------ batch y errores
def fetch_estado_batch() -> EstadoBatch:
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT pendientes, procesando, procesados, errores, ultimo_run, ultimo_origen FROM v_estado_batch")
        r = cur.fetchone()
    return EstadoBatch(int(r[0]), int(r[1]), int(r[2]), int(r[3]), r[4], r[5])


def fetch_errores(limit: int = 200) -> list[ErrorFila]:
    """Lecturas que el batch dejó en ERROR, con el SKU y el motivo ya interpretados por la vista."""
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM (SELECT id_transito, uuid_dispositivo, seq, sku, cantidad, mensaje_error, fecha_recepcion "
            "                 FROM v_errores_captura ORDER BY id_transito DESC) WHERE ROWNUM <= :n",
            n=limit,
        )
        return [ErrorFila(int(r[0]), r[1], int(r[2]), r[3] or "", r[4] or "", r[5], r[6]) for r in cur]


def procesar_ahora() -> None:
    with _conexion() as conn:
        conn.cursor().execute("BEGIN pkg_batch.procesar_pendientes('MANUAL'); END;")


def reprocesar_errores() -> None:
    """Devuelve a PENDIENTE las filas en ERROR y las procesa (sin cerrar nada: el conteo es continuo)."""
    with _conexion() as conn:
        conn.cursor().execute("BEGIN pkg_batch.reprocesar_errores(); END;")


def crear_producto(quien, sku: str, nombre: str, categoria: str) -> None:
    """Alta de un SKU desconocido (solo Administrador): producto + stock 0 en ``ACTUAL``.

    La lectura que estaba en error se procesa después con ``reprocesar_errores`` (lo llama la vista).
    """
    from . import auditoria
    from .auth import ErrorDeAcceso

    if not getattr(quien, "es_admin", False):
        raise ErrorDeAcceso("Solo el Administrador puede dar de alta un SKU.")
    sku, nombre, categoria = sku.strip().upper(), nombre.strip(), categoria.strip()
    if not sku or not nombre or not categoria:
        raise ErrorDeAcceso("El SKU, el nombre y la categoría son obligatorios.")
    if len(sku) > 30 or len(nombre) > 120 or len(categoria) > 40:
        raise ErrorDeAcceso("El SKU, el nombre o la categoría son demasiado largos.")
    with _conexion() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "BEGIN pkg_batch.alta_sku(:s, :n, :c, 'UND', 0); END;",
                s=sku, n=nombre, c=categoria,
            )
        except Exception as exc:
            texto = str(exc)
            if "ORA-20011" in texto or "SKU_YA_EXISTE" in texto:
                raise ErrorDeAcceso(f"El SKU {sku} ya existe.") from None
            if "ORA-20010" in texto:
                raise ErrorDeAcceso("No se pudo dar de alta: revisa el SKU, el nombre, la categoría y la unidad.") from None
            raise
        auditoria.registrar(cur, quien.usuario, "inventario", "Dió de alta un SKU", f"{nombre} ({sku})")
        conn.commit()


# ------------------------------------------------------------------ series de las gráficas
def fetch_actividad() -> list[tuple[str, str, int]]:
    """(operador, hora 'AAAA-MM-DD HH:MM' en UTC, lecturas) de ``V_ACTIVIDAD``."""
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT operador, TO_CHAR(hora, 'YYYY-MM-DD HH24:MI'), registros FROM v_actividad "
            "WHERE id_conteo = :c ORDER BY hora, operador",
            c=CONTEO,
        )
        return [(r[0], r[1], int(r[2])) for r in cur]


def fetch_por_categoria() -> list[tuple[str, float]]:
    """(categoría, diferencia en unidades). Negativa = faltante; positiva = sobrante.

    Es una referencia del Dashboard: el inventario no muestra diferencia, porcentaje ni clasificación.
    """
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT p.categoria, NVL(SUM(k.diferencia), 0) "
            "  FROM conciliacion k JOIN productos p ON p.sku = k.sku "
            " WHERE k.id_conteo = :c GROUP BY p.categoria ORDER BY p.categoria",
            c=CONTEO,
        )
        return [(r[0], float(r[1])) for r in cur]


def fetch_series(categoria: str | None = None, top: int = 10) -> dict:
    """Los datos de las seis gráficas, con los dos filtros de la pantalla.

    ``categoria`` limita las series que se pueden desglosar; ``top`` es cuántas categorías/runs se muestran.
    """
    filtro_cat, binds_cat = "", {}
    if categoria:
        filtro_cat, binds_cat = "AND p.categoria = :cat", {"cat": categoria}
    datos: dict = {}
    with _conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT categoria FROM productos ORDER BY categoria")
        datos["_categorias"] = [r[0] for r in cur]

        cur.execute(
            "SELECT p.categoria, COUNT(*), COUNT(k.cant_contada) "
            "  FROM conciliacion k JOIN productos p ON p.sku = k.sku "
            f" WHERE k.id_conteo = :c {filtro_cat} GROUP BY p.categoria ORDER BY p.categoria",
            c=CONTEO, **binds_cat,
        )
        datos["avance_categoria"] = [
            (r[0], (100.0 * int(r[2]) / int(r[1])) if int(r[1]) else 0.0) for r in cur
        ]

        cur.execute(
            "SELECT TO_CHAR(r.fecha_captura, 'YYYY-MM-DD HH24:MI'), COUNT(*) "
            "  FROM registros_procesados r JOIN productos p ON p.sku = r.sku "
            f" WHERE r.id_conteo = :c {filtro_cat} "
            " GROUP BY TO_CHAR(r.fecha_captura, 'YYYY-MM-DD HH24:MI') ORDER BY 1",
            c=CONTEO, **binds_cat,
        )
        datos["por_hora"] = [(r[0], float(r[1])) for r in cur]

        cur.execute(
            "SELECT * FROM (SELECT p.categoria, COUNT(*) FROM registros_procesados r "
            "  JOIN productos p ON p.sku = r.sku "
            f" WHERE r.id_conteo = :c {filtro_cat} GROUP BY p.categoria ORDER BY 2 DESC, 1) "
            " WHERE ROWNUM <= :n",
            c=CONTEO, n=top, **binds_cat,
        )
        datos["top_categorias"] = [(r[0], float(r[1])) for r in cur]

        cur.execute(
            "SELECT p.categoria, SUM(NVL(r.danados, 0)) "
            "  FROM registros_procesados r JOIN productos p ON p.sku = r.sku "
            f" WHERE r.id_conteo = :c AND r.vigente = 'S' AND NVL(r.danados, 0) > 0 {filtro_cat} "
            " GROUP BY p.categoria ORDER BY 2 DESC, 1",
            c=CONTEO, **binds_cat,
        )
        datos["danados"] = [(r[0], float(r[1])) for r in cur]

        cur.execute(
            "SELECT * FROM (SELECT TO_CHAR(inicio, 'YYYY-MM-DD HH24:MI'), procesados, errores "
            "                 FROM log_batch ORDER BY id DESC) WHERE ROWNUM <= :n",
            n=top,
        )
        filas = [(r[0], int(r[1]), int(r[2])) for r in cur][::-1]
        datos["batch"] = [(r[0], float(r[1])) for r in filas]
        datos["batch_errores"] = [(r[0], float(r[2])) for r in filas]

        cur.execute(
            "SELECT COUNT(*), COUNT(k.cant_contada) FROM conciliacion k "
            "  JOIN productos p ON p.sku = k.sku "
            f" WHERE k.id_conteo = :c {filtro_cat}",
            c=CONTEO, **binds_cat,
        )
        total, contados = cur.fetchone()
        datos["contados_pendientes"] = [("contados", float(contados)), ("pendientes", float(int(total) - int(contados)))]
        datos["dona"] = list(datos["contados_pendientes"])
    return datos
