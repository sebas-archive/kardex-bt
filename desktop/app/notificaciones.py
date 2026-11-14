"""Notificaciones vistas desde el escritorio: las de la persona (las de su rol y las dirigidas a ella), cuáles leyó,
y marcarlas. Las crean los eventos (``btsync.notificaciones.crear``) en su misma transacción.

No son solicitudes: una solicitud se resuelve en «Solicitudes»; una notificación solo se lee.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from btsync import notificaciones as bn

from . import auth, db, permisos
from .auth import Sesion

LIMITE = 200


@dataclass(frozen=True)
class Notificacion:
    id: int
    fecha: datetime
    tipo: str
    texto: str
    seccion: str
    leida: bool


def _mias(alias: str = "n") -> str:
    return f"({alias}.usuario = :u OR ({alias}.usuario IS NULL AND {alias}.rol = :r))"


def _rol(cur, quien: Sesion) -> str | None:
    """El rol de ahora (no el de la sesión): un cambio de rol cambia lo que se ve."""
    cur.execute(f"SELECT rol FROM {auth.TABLA} WHERE usuario = :u", u=quien.usuario)
    fila = cur.fetchone()
    return fila[0] if fila else quien.rol


def listar(quien: Sesion) -> list[Notificacion]:
    permisos.exigir(quien, "notificaciones", permisos.CONSULTA)
    with db._conexion() as conn:
        cur = conn.cursor()
        rol = _rol(cur, quien)
        cur.execute(f"SELECT * FROM (SELECT n.id, n.fecha, n.tipo, n.texto, n.seccion, "
                    f"CASE WHEN l.usuario IS NULL THEN 0 ELSE 1 END FROM {bn.TABLA} n "
                    f"LEFT JOIN {bn.TABLA_LEIDAS} l ON l.id_notificacion = n.id AND l.usuario = :u "
                    f"WHERE {_mias()} ORDER BY n.fecha DESC, n.id DESC) WHERE ROWNUM <= {LIMITE}",
                    u=quien.usuario, r=rol)
        return [Notificacion(int(i), f, t, x, s or "", bool(lv)) for i, f, t, x, s, lv in cur]


def sin_leer(quien: Sesion) -> int:
    if not quien.puede("notificaciones"):
        return 0
    with db._conexion() as conn:
        cur = conn.cursor()
        rol = _rol(cur, quien)
        cur.execute(f"SELECT COUNT(*) FROM {bn.TABLA} n WHERE {_mias()} AND NOT EXISTS (SELECT 1 FROM "
                    f"{bn.TABLA_LEIDAS} l WHERE l.id_notificacion = n.id AND l.usuario = :u)",
                    u=quien.usuario, r=rol)
        return int(cur.fetchone()[0])


def marcar_leida(quien: Sesion, id_notificacion: int) -> None:
    permisos.exigir(quien, "notificaciones", permisos.CONSULTA)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"INSERT INTO {bn.TABLA_LEIDAS} (id_notificacion, usuario) SELECT :i, :u FROM dual "
                    f"WHERE NOT EXISTS (SELECT 1 FROM {bn.TABLA_LEIDAS} WHERE id_notificacion = :i AND usuario = :u)",
                    i=id_notificacion, u=quien.usuario)
        conn.commit()


def marcar_todas(quien: Sesion) -> None:
    permisos.exigir(quien, "notificaciones", permisos.CONSULTA)
    with db._conexion() as conn:
        cur = conn.cursor()
        rol = _rol(cur, quien)
        cur.execute(f"INSERT INTO {bn.TABLA_LEIDAS} (id_notificacion, usuario) SELECT n.id, :u FROM {bn.TABLA} n "
                    f"WHERE {_mias()} AND NOT EXISTS (SELECT 1 FROM {bn.TABLA_LEIDAS} l "
                    f"WHERE l.id_notificacion = n.id AND l.usuario = :u)", u=quien.usuario, r=rol)
        conn.commit()
