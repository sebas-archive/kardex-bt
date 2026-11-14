"""Respaldos desde el escritorio (Fase 5, módulo ``respaldos``): crear, listar, restaurar todo y programar el
automático. El trabajo con el zip lo hace ``btsync.respaldo``; aquí van los permisos, la auditoría y la pausa del
servicio Bluetooth mientras se restaura.
"""

from __future__ import annotations

import time

from btsync import config, respaldo

from . import auditoria, configuracion, db, permisos, servicio
from .auth import ErrorDeAcceso, Sesion

JOBS = ("JOB_PROCESAR_CAPTURAS", "JOB_PURGA_TRANSITO")   # deshabilitados durante la restauración
NO_SE_DETUVO = "El servicio Bluetooth no se detuvo; inténtalo de nuevo"
Respaldo = respaldo.Respaldo


def _auditar(quien: Sesion, accion: str, detalle: str) -> None:
    with db._conexion() as conn:
        auditoria.registrar(conn.cursor(), quien.usuario, "respaldos", accion, detalle)
        conn.commit()


def crear(quien: Sesion) -> Respaldo:
    permisos.exigir(quien, "respaldos")
    with db._conexion() as conn:
        r = respaldo.crear(conn, quien.usuario, "manual")
    _auditar(quien, "Creó respaldo", r.archivo)
    return r


def listar(quien: Sesion) -> list[Respaldo]:
    permisos.exigir(quien, "respaldos", permisos.CONSULTA)
    return respaldo.listar()


def _esperar_pausa(esperar_s: float) -> bool:
    limite = time.monotonic() + esperar_s
    while True:
        if servicio.estado().estado in (servicio.PAUSADO, servicio.DETENIDO):
            return True
        if time.monotonic() >= limite:
            return False
        time.sleep(0.25)


def restaurar(quien: Sesion, archivo: str, esperar_s: float = 30) -> None:
    """Pausa el servicio (y espera a que termine lo que esté recibiendo), guarda un respaldo «previo» del estado
    actual y reemplaza todo por ``archivo``. El servicio queda pausado: se reanuda a mano."""
    permisos.exigir(quien, "respaldos")
    inicial = servicio.estado()
    if inicial.pausado is not None:   # siempre: un servicio que parece detenido puede volver (restart) a mitad
        servicio.pausar(quien)
    if not _esperar_pausa(esperar_s):
        if inicial.pausado is False:
            servicio.reanudar(quien)
        raise ErrorDeAcceso(NO_SE_DETUVO)
    with db._conexion() as conn:
        respaldo.crear(conn, quien.usuario, "previo")
        respaldo.restaurar(conn, archivo, jobs=JOBS)
    _auditar(quien, "Restauró respaldo", archivo)


def automatico() -> tuple[bool, str, int]:
    """(activo, hora HH:MM, cuántos conservar)."""
    with db._conexion() as conn:
        v = config.leer(conn.cursor())
    return v["respaldos.auto"] == "S", v["respaldos.hora"], int(v["respaldos.conservar"])


def guardar_automatico(quien: Sesion, activo: bool, hora: str, conservar: int) -> tuple[bool, str, int]:
    configuracion.guardar(quien, {"respaldos.auto": "S" if activo else "N", "respaldos.hora": hora,
                                  "respaldos.conservar": str(conservar)}, modulo="respaldos")
    return automatico()
