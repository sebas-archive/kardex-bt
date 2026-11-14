"""Configuración general (Fase 5): el Administrador cambia los valores que antes estaban fijos en el código.

Los valores viven en ``CONFIGURACION`` (``btsync.config``). Aquí se validan, se auditan (una fila por clave cambiada,
en la misma transacción) y se aplican a los dos jobs de DBMS_SCHEDULER. Ajustar un job confirma por su cuenta, así que
va después del COMMIT; si fallara, ``aplicar_jobs()`` (al arrancar el escritorio) lo deja al día.
"""

from __future__ import annotations

import re

from btsync import config

from . import auditoria, db, permisos
from .auth import ErrorDeAcceso, Sesion

JOB_LOTE = "JOB_PROCESAR_CAPTURAS"   # las pruebas usan jobs «_TST» deshabilitados
JOB_PURGA = "JOB_PURGA_TRANSITO"

RANGOS = config.RANGOS
_HORA = config.HORA


def _miles(n: int) -> str:
    """200.000 y 1.000.000.000 con punto; los números de 4 cifras o menos, sin él (3600 segundos)."""
    return f"{n:,}".replace(",", ".") if n >= 10_000 else str(n)


def validar(cambios: dict[str, str]) -> dict[str, str]:
    """Los cambios normalizados (sin espacios ni ceros a la izquierda); el primero fuera de rango lanza el error."""
    limpios: dict[str, str] = {}
    for clave, valor in cambios.items():
        texto = str(valor).strip()
        if clave in RANGOS:
            nombre, minimo, maximo, unidad = RANGOS[clave]
            if not re.fullmatch(r"\d{1,10}", texto) or not minimo <= int(texto) <= maximo:
                raise ErrorDeAcceso(f"{nombre}: entre {_miles(minimo)} y {_miles(maximo)} {unidad}")
            texto = str(int(texto))
        elif clave == "respaldos.hora":
            if not _HORA.fullmatch(texto):
                raise ErrorDeAcceso("Hora del respaldo automático: HH:MM, entre 00:00 y 23:59")
        elif clave == "respaldos.auto":
            if texto not in ("S", "N"):
                raise ErrorDeAcceso("Respaldo automático: sí o no")
        else:
            raise ErrorDeAcceso(f"«{clave}» no es un valor de la configuración.")
        limpios[clave] = texto
    return limpios


def valores() -> dict[str, str]:
    with db._conexion() as conn:
        return config.leer(conn.cursor())


def guardar(quien: Sesion, cambios: dict[str, str], modulo: str = "configuracion") -> dict[str, str]:
    """Valida, guarda y audita lo que cambió; devuelve los valores vigentes. ``modulo`` es el permiso que se exige
    (la pantalla Respaldos guarda las claves ``respaldos.*`` con el suyo)."""
    permisos.exigir(quien, modulo)
    limpios = validar(cambios)
    with db._conexion() as conn:
        cur = conn.cursor()
        antes = config.leer(cur)
        cambiados = {k: v for k, v in limpios.items() if antes[k] != v}
        if cambiados:
            config.escribir(cur, cambiados)
            for clave, valor in cambiados.items():
                accion = "Cambió respaldo automático" if clave.startswith("respaldos.") else "Cambió configuración"
                auditoria.registrar(cur, quien.usuario, modulo, accion, f"{clave}: {antes[clave]} → {valor}")
        conn.commit()
        vigentes = config.leer(cur)
    if {"lote.intervalo_s", "staging.purga_dias"} & cambiados.keys():
        aplicar_jobs(vigentes)
    return vigentes


def aplicar_jobs(vigentes: dict[str, str] | None = None) -> None:
    """Pone el intervalo del lote y los días de purga en los jobs (sin efecto si un job no existe)."""
    vigentes = vigentes or valores()
    with db._conexion() as conn:
        cur = conn.cursor()
        for job, atributo, valor in (
                (JOB_LOTE, "repeat_interval", f"FREQ=SECONDLY;INTERVAL={int(vigentes['lote.intervalo_s'])}"),
                (JOB_PURGA, "job_action", f"BEGIN pkg_batch.purgar_transito({int(vigentes['staging.purga_dias'])}); END;")):
            cur.execute("SELECT COUNT(*) FROM user_scheduler_jobs WHERE job_name = :j", j=job)
            if cur.fetchone()[0]:
                cur.callproc("DBMS_SCHEDULER.SET_ATTRIBUTE", [job, atributo, valor])
