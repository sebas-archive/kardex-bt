"""Tareas de conteo (Fase 3). Una tarea es un conteo (``conteos``) con almacén, operador e instrucciones; sus
productos son sus filas de ``stock_sistema`` (cantidad tomada de ``existencias`` al crearla).

El estado no se guarda: se calcula al consultar a partir de las lecturas, la conciliación y el staging, así nunca
queda desfasado. Lo usan el receptor (catálogo para el móvil) y el escritorio (pantallas de Inventario).

``revisiones`` guarda la última acción de Inventario sobre una diferencia: ``REVISADA`` o ``RECUENTO``. Una
revisión cuenta mientras no llegue una lectura más nueva de ese producto.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .store import ddl_tolerante

ASIGNADA, EN_PROGRESO, ENVIADA_PARCIALMENTE = "ASIGNADA", "EN_PROGRESO", "ENVIADA_PARCIALMENTE"
SINCRONIZADA, CON_DIFERENCIAS, CERRADA, CON_ERROR = "SINCRONIZADA", "CON_DIFERENCIAS", "CERRADA", "CON_ERROR"
ESTADOS = (ASIGNADA, EN_PROGRESO, ENVIADA_PARCIALMENTE, SINCRONIZADA, CON_DIFERENCIAS, CERRADA, CON_ERROR)
NOMBRE_ESTADO = {
    ASIGNADA: "Asignada", EN_PROGRESO: "En progreso", ENVIADA_PARCIALMENTE: "Enviada parcialmente",
    SINCRONIZADA: "Sincronizada", CON_DIFERENCIAS: "Con diferencias", CERRADA: "Cerrada", CON_ERROR: "Con error",
}


def estado_tarea(cerrada: bool, total: int, contados: int, lecturas: int, diferencias: int, errores: int,
                 iniciada: bool) -> str:
    """Gana la primera regla que se cumple, en este orden."""
    if cerrada:
        return CERRADA
    if errores:
        return CON_ERROR
    if total and contados >= total:
        return CON_DIFERENCIAS if diferencias else SINCRONIZADA
    if lecturas:
        return ENVIADA_PARCIALMENTE
    return EN_PROGRESO if iniciada else ASIGNADA


@dataclass(frozen=True)
class ResumenTarea:
    id: str
    nombre: str
    almacen: str
    operador: str
    instrucciones: str
    total: int
    contados: int
    estado: str
    creada: datetime | None


# Un producto de la tarea está pendiente de recuento si su última acción es RECUENTO y no llegó una lectura después.
RECUENTO_PENDIENTE = """EXISTS (SELECT 1 FROM revisiones v WHERE v.id_conteo = {c} AND v.sku = {s} AND v.accion = 'RECUENTO'
        AND NOT EXISTS (SELECT 1 FROM registros_procesados r2 WHERE r2.id_conteo = v.id_conteo AND r2.sku = v.sku
                        AND r2.vigente = 'S' AND r2.fecha_procesado > v.fecha))"""

_LISTAR = f"""
SELECT c.id_conteo, c.nombre, NVL(c.almacen, ' '), c.operador, NVL(c.instrucciones, ' '), c.estado, c.iniciada, c.creada,
       (SELECT COUNT(*) FROM stock_sistema s WHERE s.id_conteo = c.id_conteo),
       (SELECT COUNT(*) FROM stock_sistema s WHERE s.id_conteo = c.id_conteo
           AND EXISTS (SELECT 1 FROM registros_procesados r WHERE r.id_conteo = s.id_conteo AND r.sku = s.sku
                       AND r.vigente = 'S')
           AND NOT {RECUENTO_PENDIENTE.format(c="s.id_conteo", s="s.sku")}),
       (SELECT COUNT(*) FROM registros_procesados r WHERE r.id_conteo = c.id_conteo),
       (SELECT COUNT(*) FROM conciliacion k WHERE k.id_conteo = c.id_conteo
           AND k.clasificacion IN ('FALTANTE', 'SOBRANTE')),
       (SELECT COUNT(*) FROM captura_transito x WHERE x.estado = 'ERROR'
           AND REGEXP_SUBSTR(x.datos_raw, '([^|]*)(\\||$)', 1, 4, NULL, 1) = c.id_conteo)
  FROM conteos c
 WHERE c.operador IS NOT NULL AND (:o IS NULL OR c.operador = :o)
 ORDER BY c.creada DESC NULLS LAST, c.id_conteo DESC"""


def listar(cur, operador: str | None = None) -> list[ResumenTarea]:
    """Las tareas (conteos con operador), de la más reciente a la más antigua; solo las de ``operador`` si se da."""
    cur.execute(_LISTAR, o=operador)
    return [ResumenTarea(id_, nombre, almacen.strip(), oper, instr.strip(), int(total), int(contados),
                         estado_tarea(estado == "CERRADO", int(total), int(contados), int(lecturas), int(dif),
                                      int(err), iniciada is not None), creada)
            for id_, nombre, almacen, oper, instr, estado, iniciada, creada, total, contados, lecturas, dif, err in cur]


def items(cur, ids: list[str]) -> list[tuple[str, str, str]]:
    """(id_tarea, sku, 'S'|'N' pendiente de recuento) de las tareas dadas. Nunca la cantidad del sistema."""
    if not ids:
        return []
    marcas = ", ".join(f":t{i}" for i in range(len(ids)))
    cur.execute(f"SELECT s.id_conteo, s.sku, CASE WHEN {RECUENTO_PENDIENTE.format(c='s.id_conteo', s='s.sku')} "
                f"THEN 'S' ELSE 'N' END FROM stock_sistema s WHERE s.id_conteo IN ({marcas}) "
                f"ORDER BY s.id_conteo, s.sku", {f"t{i}": v for i, v in enumerate(ids)})
    return [(a, b, c) for a, b, c in cur]


_COLUMNAS = (("ALMACEN", "almacen VARCHAR2(20 CHAR)"), ("OPERADOR", "operador VARCHAR2(30 CHAR)"),
             ("INSTRUCCIONES", "instrucciones VARCHAR2(500 CHAR)"), ("INICIADA", "iniciada TIMESTAMP"),
             ("CREADA_POR", "creada_por VARCHAR2(30 CHAR)"), ("CREADA", "creada TIMESTAMP DEFAULT SYSTIMESTAMP"))


def migrar(conn) -> None:
    """Columnas de tarea en ``conteos``, la secuencia ``seq_tareas`` y la tabla ``revisiones``. Idempotente y
    tolerante a otro escritorio haciendo lo mismo a la vez."""
    cur = conn.cursor()
    cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'CONTEOS'")
    columnas = {r[0] for r in cur}
    for nombre, definicion in _COLUMNAS:
        if nombre not in columnas:
            ddl_tolerante(cur, f"ALTER TABLE conteos ADD ({definicion})")
    cur.execute("SELECT COUNT(*) FROM user_sequences WHERE sequence_name = 'SEQ_TAREAS'")
    if not cur.fetchone()[0]:
        ddl_tolerante(cur, "CREATE SEQUENCE seq_tareas START WITH 1 NOCACHE")
    cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'REVISIONES'")
    if not cur.fetchone()[0]:
        ddl_tolerante(cur, """CREATE TABLE revisiones (
            id_conteo VARCHAR2(30 CHAR) NOT NULL,
            sku       VARCHAR2(30 CHAR) NOT NULL,
            accion    VARCHAR2(10 CHAR) NOT NULL,
            nota      VARCHAR2(300 CHAR),
            por       VARCHAR2(30 CHAR) NOT NULL,
            fecha     TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT pk_revisiones PRIMARY KEY (id_conteo, sku),
            CONSTRAINT ck_revisiones_accion CHECK (accion IN ('REVISADA', 'RECUENTO')))""")
    conn.commit()
