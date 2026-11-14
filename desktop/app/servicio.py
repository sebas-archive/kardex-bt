"""El servicio Bluetooth visto desde el escritorio (Fase 5): leer su estado en ``SERVICIO_BT`` y pausarlo, reanudarlo
o responder al código de emparejamiento. El servicio corre aparte (``btsync.servicio``); cerrar el escritorio no lo
detiene. Si su latido tiene más de ``LATIDO_MAX_S`` segundos (o no hay fila) el estado es ``DETENIDO``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from btsync import servicio as bt

from . import auditoria, db, permisos
from .auth import Sesion

LATIDO_MAX_S = 10
DETENIDO, PAUSADO, PAUSANDO = bt.DETENIDO, bt.PAUSADO, bt.PAUSANDO


@dataclass(frozen=True)
class UltimaSync:
    fin: datetime
    recibidos: int
    dispositivo: str


@dataclass(frozen=True)
class EstadoServicio:
    estado: str
    codigo: str | None = None
    recibidos: int = 0
    ultimo_error: str | None = None
    desde: datetime | None = None
    latido_s: float | None = None
    listos: int = 0
    ultima: UltimaSync | None = None
    pausado: bool | None = None   # lo que pidió el escritorio; None: no hay fila (el servicio nunca arrancó)

    def como_dict(self) -> dict:
        return {"estado": self.estado, "codigo": self.codigo, "recibidos": self.recibidos,
                "ultimo_error": self.ultimo_error, "desde": self.desde, "listos": self.listos,
                "ultima": self.ultima}


def estado() -> EstadoServicio:
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT s.fin, s.recibidos, NVL(d.nombre, s.uuid_dispositivo) FROM sync_sesiones s "
                    "LEFT JOIN dispositivos d ON d.uuid = s.uuid_dispositivo WHERE s.fin IS NOT NULL "
                    "ORDER BY s.fin DESC, s.id DESC")
        f = cur.fetchone()
        ultima = None if f is None else UltimaSync(f[0], int(f[1]), f[2])
        cur.execute(f"SELECT estado, codigo, recibidos, ultimo_error, desde, listos, "
                    f"(CAST(SYSTIMESTAMP AS DATE) - CAST(latido AS DATE)) * 86400, pausado FROM {bt.TABLA} WHERE id = 1")
        r = cur.fetchone()
    if r is None:
        return EstadoServicio(DETENIDO, ultima=ultima)
    est, codigo, recibidos, error, desde, listos, hace, pausado = r
    if hace is None or float(hace) > LATIDO_MAX_S:
        return EstadoServicio(DETENIDO, desde=desde, latido_s=None if hace is None else float(hace),
                              listos=int(listos), ultima=ultima, pausado=pausado == "S")
    return EstadoServicio(est, codigo, int(recibidos), error, desde, float(hace), int(listos), ultima,
                          pausado == "S")


def _escribir(quien: Sesion, sql: str, accion: str, **binds) -> None:
    permisos.exigir(quien, "sync")
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE {bt.TABLA} SET {sql} WHERE id = 1", binds)
        if cur.rowcount == 0:
            conn.rollback()
            from .auth import ErrorDeAcceso

            raise ErrorDeAcceso("El servicio Bluetooth nunca ha arrancado en este PC.")
        auditoria.registrar(cur, quien.usuario, "bluetooth", accion)
        conn.commit()


def pausar(quien: Sesion) -> None:
    _escribir(quien, "pausado = 'S'", "Pausó servicio")


def reanudar(quien: Sesion) -> None:
    _escribir(quien, "pausado = 'N'", "Reanudó servicio")


def responder_codigo(quien: Sesion, aceptar: bool) -> None:
    _escribir(quien, "respuesta = :r", "Aceptó código" if aceptar else "Rechazó código", r="S" if aceptar else "N")


def avisar_detenido(desde: datetime | None) -> bool:
    """Notifica al Administrador que el servicio se detuvo: una sola vez por arranque del servicio (la clave es su
    ``desde``), aunque lo vean caer varios escritorios."""
    from btsync import notificaciones

    with db._conexion() as conn:
        creada = notificaciones.crear(conn.cursor(), "SERVICIO_DETENIDO", "El servicio Bluetooth se detuvo",
                                      "Sincronización", rol="ADMIN",
                                      clave=desde.isoformat() if desde is not None else "sin-arranque")
        conn.commit()
    return creada
