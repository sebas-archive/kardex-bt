"""Categorías, almacenes y existencias (Fase 2).

- **Categorías**: el nombre es la clave y es el mismo texto que guarda ``productos.categoria``. Renombrar actualiza
  los productos en la misma transacción. Desactivar no borra nada: la categoría deja de ofrecerse para registros nuevos.
- **Almacenes**: código (``ALM-01``), nombre y ubicación; también se activan y desactivan.
- **Existencias**: cantidad por producto × almacén. Estado: ``AGOTADO`` (0), ``STOCK_BAJO`` (menos que
  ``productos.stock_minimo``) o ``DISPONIBLE``. En esta fase solo se consultan; entradas, salidas y ajustes las
  moverán en las siguientes.

Escribir exige ``GESTION`` en el módulo ``categorias`` (lo comprueba ``permisos.exigir`` en vivo). Como todo lo que
toca Oracle, estas funciones se llaman fuera del hilo de la interfaz; los errores para la persona son ``ErrorDeAcceso``.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass

import oracledb

from . import auditoria, db, permisos
from .auth import ErrorDeAcceso, Sesion

CATEGORIAS, ALMACENES, EXISTENCIAS = "categorias", "almacenes", "existencias"   # las pruebas usan *_tst
AGOTADO, STOCK_BAJO, DISPONIBLE = "AGOTADO", "STOCK_BAJO", "DISPONIBLE"
NOMBRE_ESTADO = {AGOTADO: "Agotado", STOCK_BAJO: "Stock bajo", DISPONIBLE: "Disponible"}
MINIMO_INICIAL = 10
ALMACENES_INICIALES = (("ALM-01", "Bodega Norte", "Sede principal"), ("ALM-02", "Bodega Sur", "Sede sur"))
_CODIGO = re.compile(r"[A-Z0-9-]{1,20}")


@dataclass(frozen=True)
class Categoria:
    nombre: str
    activa: bool
    productos: int


@dataclass(frozen=True)
class Almacen:
    codigo: str
    nombre: str
    ubicacion: str
    activo: bool


@dataclass(frozen=True)
class Existencia:
    sku: str
    producto: str
    categoria: str
    codigo_almacen: str
    almacen: str
    cantidad: float
    minimo: float
    estado: str
    almacen_activo: bool = True
    categoria_activa: bool = True


# ------------------------------------------------------------------ consultas
def listar_categorias(solo_activas: bool = False) -> list[Categoria]:
    """Todas, o solo las activas (las que se ofrecen al registrar algo nuevo)."""
    with db._conexion() as conn:
        cur = conn.cursor()
        filtro = "WHERE c.activa = 'S'" if solo_activas else ""
        cur.execute(f"SELECT c.nombre, c.activa, (SELECT COUNT(*) FROM productos p WHERE p.categoria = c.nombre) "
                    f"FROM {CATEGORIAS} c {filtro} ORDER BY c.nombre")
        return [Categoria(n, a == "S", int(k)) for n, a, k in cur]


def listar_almacenes(solo_activos: bool = False) -> list[Almacen]:
    """Todos, o solo los activos (los que se ofrecen al registrar algo nuevo)."""
    with db._conexion() as conn:
        cur = conn.cursor()
        filtro = "WHERE activo = 'S'" if solo_activos else ""
        cur.execute(f"SELECT codigo, nombre, NVL(ubicacion, ''), activo FROM {ALMACENES} {filtro} ORDER BY codigo")
        return [Almacen(c, n, u or "", a == "S") for c, n, u, a in cur]


def listar_existencias() -> list[Existencia]:
    """Una fila por producto × almacén con existencias registradas (un producto sin fila en un almacén no aparece)."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT p.sku, p.nombre, p.categoria, a.codigo, a.nombre, e.cantidad, p.stock_minimo, "
            f"CASE WHEN e.cantidad <= 0 THEN '{AGOTADO}' WHEN e.cantidad < p.stock_minimo THEN '{STOCK_BAJO}' "
            f"ELSE '{DISPONIBLE}' END, a.activo, NVL(c.activa, 'S') "
            f"FROM {EXISTENCIAS} e JOIN productos p ON p.sku = e.sku JOIN {ALMACENES} a ON a.codigo = e.codigo_almacen "
            f"LEFT JOIN {CATEGORIAS} c ON c.nombre = p.categoria "
            f"ORDER BY a.codigo, p.nombre")
        return [Existencia(s, n, c, ca, an, float(q), float(m), est, aa == "S", cc == "S")
                for s, n, c, ca, an, q, m, est, aa, cc in cur]


@contextmanager
def _sin_duplicados(mensaje: str):
    """Si otro usuario creó lo mismo entre la comprobación y el INSERT, ORA-00001 llega como el mensaje de siempre."""
    try:
        yield
    except oracledb.IntegrityError as exc:
        if "ORA-00001" in str(exc):
            raise ErrorDeAcceso(mensaje) from None
        raise


def _exigir_fila(cur, que: str) -> None:
    if cur.rowcount == 0:   # otro usuario la borró o la renombró mientras tanto
        raise ErrorDeAcceso(f"{que} ya no existe. Actualiza la lista.")


# ------------------------------------------------------------------ categorías
def _nombre_categoria(nombre: str) -> str:
    nombre = (nombre or "").strip()
    if not nombre or len(nombre) > 40:
        raise ErrorDeAcceso("Escribe el nombre de la categoría (máximo 40 caracteres).")
    return nombre


def _categoria_existe(cur, nombre: str, salvo: str | None = None) -> bool:
    cur.execute(f"SELECT COUNT(*) FROM {CATEGORIAS} WHERE UPPER(nombre) = UPPER(:n) AND nombre <> NVL(:s, CHR(0))",
                n=nombre, s=salvo)
    return cur.fetchone()[0] > 0


def crear_categoria(quien: Sesion, nombre: str) -> None:
    permisos.exigir(quien, "categorias")
    nombre = _nombre_categoria(nombre)
    with db._conexion() as conn:
        cur = conn.cursor()
        if _categoria_existe(cur, nombre):
            raise ErrorDeAcceso("Esa categoría ya existe.")
        with _sin_duplicados("Esa categoría ya existe."):
            cur.execute(f"INSERT INTO {CATEGORIAS} (nombre) VALUES (:n)", n=nombre)
        auditoria.registrar(cur, quien.usuario, "categorias", "Creó categoría", nombre)
        conn.commit()


def renombrar_categoria(quien: Sesion, actual: str, nuevo: str) -> None:
    """Cambia el nombre y, en la misma transacción, el de todos los productos de esa categoría."""
    permisos.exigir(quien, "categorias")
    nuevo = _nombre_categoria(nuevo)
    with db._conexion() as conn:
        cur = conn.cursor()
        if _categoria_existe(cur, nuevo, salvo=actual):
            raise ErrorDeAcceso("Esa categoría ya existe.")
        with _sin_duplicados("Esa categoría ya existe."):
            cur.execute(f"UPDATE {CATEGORIAS} SET nombre = :n WHERE nombre = :a", n=nuevo, a=actual)
        _exigir_fila(cur, "Esa categoría")
        cur.execute("UPDATE productos SET categoria = :n WHERE categoria = :a", n=nuevo, a=actual)
        auditoria.registrar(cur, quien.usuario, "categorias", "Renombró categoría", f"{actual} → {nuevo}")
        conn.commit()


def activar_categoria(quien: Sesion, nombre: str, activa: bool) -> None:
    permisos.exigir(quien, "categorias")
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE {CATEGORIAS} SET activa = :a WHERE nombre = :n", a="S" if activa else "N", n=nombre)
        _exigir_fila(cur, "Esa categoría")
        auditoria.registrar(cur, quien.usuario, "categorias", "Activó categoría" if activa else "Desactivó categoría", nombre)
        conn.commit()


# ------------------------------------------------------------------ almacenes
def _datos_almacen(nombre: str, ubicacion: str) -> tuple[str, str]:
    nombre, ubicacion = (nombre or "").strip(), (ubicacion or "").strip()
    if not nombre or len(nombre) > 60:
        raise ErrorDeAcceso("Escribe el nombre del almacén (máximo 60 caracteres).")
    if len(ubicacion) > 120:
        raise ErrorDeAcceso("La ubicación puede tener máximo 120 caracteres.")
    return nombre, ubicacion


def crear_almacen(quien: Sesion, codigo: str, nombre: str, ubicacion: str) -> None:
    permisos.exigir(quien, "categorias")
    codigo = (codigo or "").strip().upper()
    if not _CODIGO.fullmatch(codigo):
        raise ErrorDeAcceso("El código debe tener de 1 a 20 caracteres: letras, números o guion (p. ej. ALM-03).")
    nombre, ubicacion = _datos_almacen(nombre, ubicacion)
    with db._conexion() as conn:
        cur = conn.cursor()
        if _almacen_existe(cur, codigo):
            raise ErrorDeAcceso("Ese código de almacén ya existe.")
        with _sin_duplicados("Ese código de almacén ya existe."):
            cur.execute(f"INSERT INTO {ALMACENES} (codigo, nombre, ubicacion) VALUES (:c, :n, :u)", c=codigo, n=nombre, u=ubicacion)
        auditoria.registrar(cur, quien.usuario, "categorias", "Creó almacén", f"{codigo} · {nombre}")
        conn.commit()


def _almacen_existe(cur, codigo: str) -> bool:
    cur.execute(f"SELECT COUNT(*) FROM {ALMACENES} WHERE codigo = :c", c=codigo)
    return cur.fetchone()[0] > 0


def editar_almacen(quien: Sesion, codigo: str, nombre: str, ubicacion: str) -> None:
    permisos.exigir(quien, "categorias")
    nombre, ubicacion = _datos_almacen(nombre, ubicacion)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE {ALMACENES} SET nombre = :n, ubicacion = :u WHERE codigo = :c", n=nombre, u=ubicacion, c=codigo)
        _exigir_fila(cur, "Ese almacén")
        auditoria.registrar(cur, quien.usuario, "categorias", "Editó almacén", f"{codigo} · {nombre}")
        conn.commit()


def activar_almacen(quien: Sesion, codigo: str, activo: bool) -> None:
    permisos.exigir(quien, "categorias")
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE {ALMACENES} SET activo = :a WHERE codigo = :c", a="S" if activo else "N", c=codigo)
        _exigir_fila(cur, "Ese almacén")
        auditoria.registrar(cur, quien.usuario, "categorias", "Activó almacén" if activo else "Desactivó almacén", codigo)
        conn.commit()


# ------------------------------------------------------------------ esquema
def _existe(cur, tabla: str) -> bool:
    cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=tabla.upper())
    return cur.fetchone()[0] > 0


def _hay_columna(cur) -> bool:
    cur.execute("SELECT COUNT(*) FROM user_tab_columns WHERE table_name = 'PRODUCTOS' AND column_name = 'STOCK_MINIMO'")
    return cur.fetchone()[0] > 0


def _hay_indice(cur, nombre: str) -> bool:
    cur.execute("SELECT COUNT(*) FROM user_indexes WHERE index_name = :i", i=nombre.upper())
    return cur.fetchone()[0] > 0


def _sembrar_si_vacia(cur, tabla: str, sembrar) -> None:
    """Siembra solo si la tabla está vacía. El bloqueo hace que otro escritorio que arranca a la vez espere y, al
    volver a mirar, la encuentre llena: nunca se siembra dos veces."""
    cur.execute(f"LOCK TABLE {tabla} IN EXCLUSIVE MODE")
    cur.execute(f"SELECT COUNT(*) FROM {tabla}")
    if cur.fetchone()[0] == 0:
        sembrar()


def migrar() -> None:
    """Crea lo que falte y siembra **solo tablas vacías** (nunca pisa lo que la persona ya editó). Idempotente, y
    aguanta que otro escritorio arranque a la vez (``db.ddl_tolerante`` y siembra con bloqueo)."""
    with db._conexion() as conn:
        cur = conn.cursor()
        if not _hay_columna(cur):
            db.ddl_tolerante(cur, f"ALTER TABLE productos ADD (stock_minimo NUMBER(12, 3) DEFAULT {MINIMO_INICIAL} NOT NULL)")
        if not _existe(cur, CATEGORIAS):
            db.ddl_tolerante(cur, f"""CREATE TABLE {CATEGORIAS} (
                nombre  VARCHAR2(40 CHAR) NOT NULL,
                activa  CHAR(1) DEFAULT 'S' NOT NULL,
                CONSTRAINT pk_{CATEGORIAS} PRIMARY KEY (nombre),
                CONSTRAINT ck_{CATEGORIAS}_activa CHECK (activa IN ('S', 'N')))""")
        # Sin distinguir mayúsculas también en la base: dos usuarios a la vez no pueden crear «Bebidas» y «BEBIDAS».
        if not _hay_indice(cur, f"ux_{CATEGORIAS}_up"):
            db.ddl_tolerante(cur, f"CREATE UNIQUE INDEX ux_{CATEGORIAS}_up ON {CATEGORIAS} (UPPER(nombre))",
                             tambien=("ORA-01408",))   # ya hay un índice sobre esa expresión
        if not _existe(cur, ALMACENES):
            db.ddl_tolerante(cur, f"""CREATE TABLE {ALMACENES} (
                codigo     VARCHAR2(20 CHAR) NOT NULL,
                nombre     VARCHAR2(60 CHAR) NOT NULL,
                ubicacion  VARCHAR2(120 CHAR),
                activo     CHAR(1) DEFAULT 'S' NOT NULL,
                CONSTRAINT pk_{ALMACENES} PRIMARY KEY (codigo),
                CONSTRAINT ck_{ALMACENES}_activo CHECK (activo IN ('S', 'N')))""")
        if not _existe(cur, EXISTENCIAS):
            db.ddl_tolerante(cur, f"""CREATE TABLE {EXISTENCIAS} (
                sku             VARCHAR2(30 CHAR) NOT NULL,
                codigo_almacen  VARCHAR2(20 CHAR) NOT NULL,
                cantidad        NUMBER(12, 3) DEFAULT 0 NOT NULL,
                CONSTRAINT pk_{EXISTENCIAS} PRIMARY KEY (sku, codigo_almacen),
                CONSTRAINT fk_{EXISTENCIAS}_sku FOREIGN KEY (sku) REFERENCES productos (sku),
                CONSTRAINT fk_{EXISTENCIAS}_alm FOREIGN KEY (codigo_almacen) REFERENCES {ALMACENES} (codigo),
                CONSTRAINT ck_{EXISTENCIAS}_cant CHECK (cantidad >= 0))""")
        _sembrar_si_vacia(cur, CATEGORIAS, lambda: cur.execute(
            f"INSERT INTO {CATEGORIAS} (nombre) SELECT DISTINCT categoria FROM productos"))
        _sembrar_si_vacia(cur, ALMACENES, lambda: cur.executemany(
            f"INSERT INTO {ALMACENES} (codigo, nombre, ubicacion) VALUES (:1, :2, :3)", list(ALMACENES_INICIALES)))
        # Datos de ejemplo: todo en el primer almacén, con el stock del sistema del conteo más reciente.
        _sembrar_si_vacia(cur, EXISTENCIAS, lambda: cur.execute(
            f"INSERT INTO {EXISTENCIAS} (sku, codigo_almacen, cantidad) "
            f"SELECT p.sku, :a, NVL((SELECT s.cantidad_sistema FROM stock_sistema s WHERE s.sku = p.sku AND s.id_conteo = "
            f"(SELECT id_conteo FROM (SELECT id_conteo FROM conteos ORDER BY fecha_inicio DESC) WHERE ROWNUM = 1)), 0) "
            f"FROM productos p", a=ALMACENES_INICIALES[0][0]))
        conn.commit()
