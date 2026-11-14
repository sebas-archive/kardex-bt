"""Tareas de conteo y diferencias (Fase 3), lo que hace Inventario desde el escritorio.

Una tarea es un conteo con almacén, operador e instrucciones; sus productos son sus filas de ``stock_sistema``, con
la cantidad que había en ``existencias`` de ese almacén al crearla (0 si no había fila). El estado se calcula al
consultar (``btsync.tareas``); aquí solo se crean, reasignan y cierran.

Diferencias: las filas FALTANTE o SOBRANTE de la conciliación. Inventario puede marcarlas revisadas o pedir que se
recuenten; esa acción vale hasta que llegue una lectura nueva del producto, y entonces vuelve a «Pendiente».

Crear, reasignar y cerrar exigen ``GESTION`` en ``tareas``; revisar y pedir recuento, ``GESTION`` en ``diferencias``.
Como todo lo que toca Oracle, estas funciones se llaman fuera del hilo de la interfaz.
"""

from __future__ import annotations

from dataclasses import dataclass

import oracledb

from btsync import tareas as bt
from btsync.tareas import ResumenTarea

from . import auth, db, maestros, movimientos, permisos
from .auth import ErrorDeAcceso, Sesion

PREFIJO = "T-"   # las pruebas usan «TT-»
PENDIENTE, REVISADA, RECUENTO = "PENDIENTE", "REVISADA", "RECUENTO"
AJUSTADA, AJUSTE_PENDIENTE = "AJUSTADA", "AJUSTE_PENDIENTE"   # hay un ajuste (Fase 3b) de esa diferencia
NOMBRE_REVISION = {PENDIENTE: "Pendiente", REVISADA: "Revisada", RECUENTO: "Recuento pedido", AJUSTADA: "Ajustada",
                   AJUSTE_PENDIENTE: "Ajuste pendiente"}
NOMBRE_TIPO = {"FALTANTE": "Faltante", "SOBRANTE": "Sobrante"}

_YA_NO_EXISTE = "Esa tarea ya no existe. Actualiza la lista."


# ------------------------------------------------------------------ consultas
def listar_tareas() -> list[ResumenTarea]:
    with db._conexion() as conn:
        return bt.listar(conn.cursor())


def operadores_disponibles() -> list[tuple[str, str]]:
    """(usuario, nombre) de las cuentas OPERADOR activas: a quién se puede asignar una tarea."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT usuario, nombre FROM {auth.TABLA} WHERE rol = :r AND estado = :e ORDER BY nombre",
                    r=auth.OPERADOR, e=auth.ACTIVO)
        return [(u, n) for u, n in cur]


def productos_disponibles() -> list[tuple[str, str, str]]:
    """(sku, nombre, categoría) de los productos de categorías activas."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT p.sku, p.nombre, p.categoria FROM productos p "
                    f"JOIN {maestros.CATEGORIAS} c ON c.nombre = p.categoria AND c.activa = 'S' "
                    f"ORDER BY p.categoria, p.nombre")
        return [(s, n, c) for s, n, c in cur]


def avance(id_tarea: str) -> list[tuple[str, str, bool, float | None]]:
    """Por producto de la tarea: (sku, nombre, contado, cantidad de la lectura vigente o None)."""
    pendiente = bt.RECUENTO_PENDIENTE.format(c="s.id_conteo", s="s.sku")
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT s.sku, p.nombre, (SELECT SUM(r.cantidad) FROM registros_procesados r "
                    f"WHERE r.id_conteo = s.id_conteo AND r.sku = s.sku AND r.vigente = 'S'), "
                    f"CASE WHEN {pendiente} THEN 1 ELSE 0 END "
                    f"FROM stock_sistema s JOIN productos p ON p.sku = s.sku WHERE s.id_conteo = :c ORDER BY s.sku",
                    c=id_tarea)
        return [(sku, nombre, cantidad is not None and not recontar, db._f(cantidad))
                for sku, nombre, cantidad, recontar in cur]


@dataclass(frozen=True)
class Diferencia:
    id_conteo: str
    sku: str
    producto: str
    almacen: str
    sistema: float
    contado: float
    diferencia: float
    tipo: str          # FALTANTE o SOBRANTE
    observacion: str   # la nota de la lectura vigente
    estado: str        # PENDIENTE, REVISADA o RECUENTO


_VIGENTES = "FROM registros_procesados r WHERE r.id_conteo = k.id_conteo AND r.sku = k.sku AND r.vigente = 'S'"


def listar_diferencias() -> list[Diferencia]:
    """Las diferencias de todos los conteos, de la tarea más reciente a la más antigua y, dentro, por valor."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT k.id_conteo, k.sku, p.nombre, NVL(c.almacen, ' '), k.cant_sistema, k.cant_contada, k.diferencia,
                   k.clasificacion,
                   (SELECT MAX(r.nota) KEEP (DENSE_RANK LAST ORDER BY r.fecha_procesado) {_VIGENTES}),
                   v.accion, v.fecha, (SELECT MAX(r.fecha_procesado) {_VIGENTES}),
                   (SELECT MAX(CASE x.estado WHEN 'APLICADO' THEN 2 WHEN 'PENDIENTE' THEN 1 ELSE 0 END)
                      FROM {movimientos.TABLA} x WHERE x.tipo = 'AJUSTE' AND x.id_conteo = k.id_conteo AND x.sku = k.sku)
              FROM conciliacion k
              JOIN productos p ON p.sku = k.sku
              JOIN conteos c ON c.id_conteo = k.id_conteo
              LEFT JOIN revisiones v ON v.id_conteo = k.id_conteo AND v.sku = k.sku
             WHERE k.clasificacion IN ('FALTANTE', 'SOBRANTE')
             ORDER BY c.creada DESC NULLS LAST, k.id_conteo DESC, ABS(k.valor_diferencia) DESC NULLS LAST, k.sku""")
        filas = []
        for id_, sku, nombre, almacen, sistema, contado, dif, tipo, nota, accion, fecha, ultima, ajuste in cur:
            vigente = accion is not None and (ultima is None or ultima <= fecha)
            estado = {2: AJUSTADA, 1: AJUSTE_PENDIENTE}.get(ajuste or 0, accion if vigente else PENDIENTE)
            filas.append(Diferencia(id_, sku, nombre, almacen.strip(), db._f(sistema) or 0.0, db._f(contado) or 0.0,
                                    db._f(dif) or 0.0, tipo, nota or "", estado))
        return filas


def errores(id_tarea: str) -> list[tuple[str, str]]:
    """(sku, motivo) de las lecturas de la tarea que el job rechazó: por qué está «Con error»."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT REGEXP_SUBSTR(datos_raw, '([^|]*)(\\||$)', 1, 5, NULL, 1), NVL(mensaje_error, '?') "
                    "FROM captura_transito WHERE estado = 'ERROR' "
                    "AND REGEXP_SUBSTR(datos_raw, '([^|]*)(\\||$)', 1, 4, NULL, 1) = :c ORDER BY id_transito", c=id_tarea)
        return [(sku or "", motivo) for sku, motivo in cur]


# ------------------------------------------------------------------ validaciones
def _id_tarea(prefijo: str, n: int) -> str:
    """``T-007``, ``T-1234``: al menos tres dígitos, sin cortar (LPAD de Oracle cortaría a ``T-123``)."""
    return f"{prefijo}{n:03d}"


def validar_tarea(nombre: str, almacen: str, operador: str, skus: list[str], instrucciones: str) -> str | None:
    """El primer problema de los datos de una tarea nueva, o ``None``. Lo usa también el diálogo antes de cerrarse."""
    nombre, instrucciones = (nombre or "").strip(), (instrucciones or "").strip()
    if not nombre or len(nombre) > 100:
        return "Escribe el nombre de la tarea (máximo 100 caracteres)."
    if not almacen:
        return "Elige el almacén."
    if not operador:
        return "Elige el operador."
    if not skus:
        return "Elige al menos un producto."
    if len(instrucciones) > 500:
        return "Las instrucciones pueden tener máximo 500 caracteres."
    return None


def _exigir_operador(cur, operador: str) -> None:
    cur.execute(f"SELECT COUNT(*) FROM {auth.TABLA} WHERE usuario = :u AND rol = :r AND estado = :e",
                u=operador, r=auth.OPERADOR, e=auth.ACTIVO)
    if not cur.fetchone()[0]:
        raise ErrorDeAcceso("Ese operador ya no está activo. Actualiza la lista.")


def _estado(cur, id_tarea: str) -> str:
    r = next((x for x in bt.listar(cur) if x.id == id_tarea), None)
    if r is None:
        raise ErrorDeAcceso(_YA_NO_EXISTE)
    return r.estado


# ------------------------------------------------------------------ escrituras de tareas
def crear_tarea(quien: Sesion, nombre: str, almacen: str, operador: str, skus: list[str], instrucciones: str) -> str:
    """Crea la tarea ASIGNADA y devuelve su id (``T-001``)."""
    permisos.exigir(quien, "tareas")
    nombre, instrucciones = (nombre or "").strip(), (instrucciones or "").strip()
    skus = list(dict.fromkeys(skus))
    problema = validar_tarea(nombre, almacen, operador, skus, instrucciones)
    if problema:
        raise ErrorDeAcceso(problema)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {maestros.ALMACENES} WHERE codigo = :a AND activo = 'S'", a=almacen)
        if not cur.fetchone()[0]:
            raise ErrorDeAcceso("Ese almacén ya no está activo. Actualiza la lista.")
        _exigir_operador(cur, operador)
        marcas = ", ".join(f":s{i}" for i in range(len(skus)))
        cur.execute(f"SELECT COUNT(*) FROM productos p JOIN {maestros.CATEGORIAS} c ON c.nombre = p.categoria "
                    f"AND c.activa = 'S' WHERE p.sku IN ({marcas})", {f"s{i}": s for i, s in enumerate(skus)})
        if cur.fetchone()[0] != len(skus):
            raise ErrorDeAcceso("Hay productos de una categoría inactiva o que ya no existen. Actualiza la lista.")
        cur.execute("SELECT seq_tareas.NEXTVAL FROM dual")
        id_tarea = _id_tarea(PREFIJO, int(cur.fetchone()[0]))
        cur.execute("INSERT INTO conteos (id_conteo, nombre, estado, almacen, operador, instrucciones, creada_por) "
                    "VALUES (:i, :n, 'ABIERTO', :a, :o, :t, :q)",
                    i=id_tarea, n=nombre, a=almacen, o=operador, t=instrucciones or None, q=quien.usuario)
        cur.executemany(f"INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) SELECT :c, :s, "
                        f"NVL((SELECT cantidad FROM {maestros.EXISTENCIAS} WHERE sku = :s AND codigo_almacen = :a), 0) "
                        f"FROM dual", [dict(c=id_tarea, s=s, a=almacen) for s in skus])
        conn.commit()
        return id_tarea


def reasignar(quien: Sesion, id_tarea: str, operador: str) -> None:
    permisos.exigir(quien, "tareas")
    with db._conexion() as conn:
        cur = conn.cursor()
        if _estado(cur, id_tarea) != bt.ASIGNADA:
            raise ErrorDeAcceso("Solo se puede reasignar una tarea que aún no empezó.")
        _exigir_operador(cur, operador)
        cur.execute("UPDATE conteos SET operador = :o WHERE id_conteo = :i AND estado = 'ABIERTO'", o=operador, i=id_tarea)
        conn.commit()


def cerrar(quien: Sesion, id_tarea: str) -> None:
    """Procesa lo pendiente, cierra y concilia (irreversible): lo que no se contó cuenta como 0."""
    permisos.exigir(quien, "tareas")
    with db._conexion() as conn:
        _estado(conn.cursor(), id_tarea)
    db.cerrar_conteo(id_tarea)


# ------------------------------------------------------------------ diferencias
def _exigir_diferencia(cur, id_conteo: str, sku: str) -> tuple[str, bool]:
    """(estado del conteo, si el producto está en la lista de una tarea con operador) si la diferencia existe."""
    cur.execute("SELECT c.estado, CASE WHEN c.operador IS NOT NULL AND EXISTS (SELECT 1 FROM stock_sistema s "
                "WHERE s.id_conteo = k.id_conteo AND s.sku = k.sku) THEN 1 ELSE 0 END "
                "FROM conciliacion k JOIN conteos c ON c.id_conteo = k.id_conteo "
                "WHERE k.id_conteo = :c AND k.sku = :s AND k.clasificacion IN ('FALTANTE', 'SOBRANTE')",
                c=id_conteo, s=sku)
    fila = cur.fetchone()
    if fila is None:
        raise ErrorDeAcceso("Esa diferencia ya no existe. Actualiza la lista.")
    return fila[0], bool(fila[1])


_MERGE = """MERGE INTO revisiones v USING (SELECT :c id_conteo, :s sku FROM dual) x
            ON (v.id_conteo = x.id_conteo AND v.sku = x.sku)
          WHEN MATCHED THEN UPDATE SET accion = :a, nota = :n, por = :p, fecha = SYSTIMESTAMP
          WHEN NOT MATCHED THEN INSERT (id_conteo, sku, accion, nota, por) VALUES (:c, :s, :a, :n, :p)"""


def _registrar(cur, id_conteo: str, sku: str, accion: str, nota: str | None, por: str) -> None:
    binds = dict(c=id_conteo, s=sku, a=accion, n=nota, p=por)
    try:
        cur.execute(_MERGE, binds)
    except oracledb.IntegrityError:   # otro usuario insertó la misma fila a la vez: ahora existe y se actualiza
        cur.execute(_MERGE, binds)


def marcar_revisada(quien: Sesion, id_conteo: str, sku: str, nota: str) -> None:
    permisos.exigir(quien, "diferencias")
    nota = (nota or "").strip()
    if len(nota) > 300:
        raise ErrorDeAcceso("La nota puede tener máximo 300 caracteres.")
    with db._conexion() as conn:
        cur = conn.cursor()
        _exigir_diferencia(cur, id_conteo, sku)
        _registrar(cur, id_conteo, sku, REVISADA, nota or None, quien.usuario)
        conn.commit()


def pedir_recuento(quien: Sesion, id_conteo: str, sku: str) -> None:
    """El producto vuelve a «por contar» en la tarea; el móvil lo marca en su próxima sincronización."""
    permisos.exigir(quien, "diferencias")
    with db._conexion() as conn:
        cur = conn.cursor()
        estado, en_lista = _exigir_diferencia(cur, id_conteo, sku)
        if estado != "ABIERTO":
            raise ErrorDeAcceso("La tarea ya está cerrada: no se puede recontar.")
        if not en_lista:   # el teléfono solo marca para recontar los productos de la lista de su tarea
            raise ErrorDeAcceso("Este producto no está en la lista de la tarea: el teléfono no lo mostraría. "
                                "Avisa al operador directamente.")
        _registrar(cur, id_conteo, sku, RECUENTO, None, quien.usuario)
        conn.commit()
