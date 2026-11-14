"""Auditoría: quién hizo qué y cuándo. Solo se consulta; no se edita ni se borra.

Cada función que cambia datos llama a ``registrar`` con su propio cursor, **dentro de la misma
transacción** que el cambio: si el cambio falla no queda fila, y si sale bien siempre la hay. También
se registran los inicios de sesión, correctos y fallidos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from . import auth, db

TABLA = "auditoria"   # las pruebas usan «auditoria_tst»
NOMBRE_MODULO = {
    "acceso": "Acceso",
    "usuarios": "Usuarios",
    "permisos": "Permisos",
    "solicitudes": "Solicitudes",
    "configuracion": "Configuración",
    "respaldos": "Respaldos",
    "sync": "Sincronización",
    "inventario": "Inventario",
    "productos": "Productos",
    "notificaciones": "Notificaciones",
    "perfil": "Perfil",
}


@dataclass(frozen=True)
class Entrada:
    id: int
    fecha: datetime
    usuario: str
    nombre: str
    modulo: str
    accion: str
    detalle: str


def registrar(cur, usuario: str, modulo: str, accion: str, detalle: str = "") -> None:
    """Añade la fila con el cursor de quien cambia los datos (sin commit propio: confirma quien llama)."""
    cur.execute(f"INSERT INTO {TABLA} (id, usuario, modulo, accion, detalle) "
                f"VALUES (seq_auditoria.NEXTVAL, :u, :m, :a, :d)",
                u=usuario[:30], m=modulo, a=accion[:60], d=(detalle or "")[:400] or None)


def producto(cur, sku: str) -> str:
    """«Arroz 500 g (7701234000001)» para el detalle; solo el código si el producto ya no existe."""
    cur.execute("SELECT nombre FROM productos WHERE sku = :s", s=sku)
    fila = cur.fetchone()
    return f"{fila[0]} ({sku})" if fila else sku


def listar(quien: auth.Sesion) -> list[Entrada]:
    """Lo más reciente primero. El acceso lo decide la matriz (módulo ``auditoria``)."""
    if not quien.puede("auditoria"):
        raise auth.ErrorDeAcceso("No tienes permiso para ver la auditoría.")
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT a.id, a.fecha, a.usuario, NVL(u.nombre, a.usuario), a.modulo, a.accion, a.detalle "
                    f"FROM {TABLA} a LEFT JOIN {auth.TABLA} u ON u.usuario = a.usuario "
                    f"ORDER BY a.fecha DESC, a.id DESC")
        return [Entrada(int(i), f, u, n, m, a, d or "") for i, f, u, n, m, a, d in cur]


def migrar() -> None:
    """La secuencia y la tabla, si faltan. Idempotente y tolerante a dos escritorios a la vez."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM user_sequences WHERE sequence_name = 'SEQ_AUDITORIA'")
        if not cur.fetchone()[0]:
            db.ddl_tolerante(cur, "CREATE SEQUENCE seq_auditoria START WITH 1 NOCACHE")
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=TABLA.upper())
        if not cur.fetchone()[0]:
            db.ddl_tolerante(cur, f"""CREATE TABLE {TABLA} (
                id       NUMBER             NOT NULL,
                fecha    TIMESTAMP          DEFAULT SYSTIMESTAMP NOT NULL,
                usuario  VARCHAR2(30 CHAR)  NOT NULL,
                modulo   VARCHAR2(20 CHAR)  NOT NULL,
                accion   VARCHAR2(60 CHAR)  NOT NULL,
                detalle  VARCHAR2(400 CHAR),
                CONSTRAINT pk_{TABLA} PRIMARY KEY (id))""")
            db.ddl_tolerante(cur, f"CREATE INDEX ix_{TABLA}_fecha ON {TABLA} (fecha)")
        conn.commit()
