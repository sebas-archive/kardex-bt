"""Configuración general: lo que el Administrador cambia sin tocar el código.

El conteo es continuo: aquí solo se ajustan el intervalo del lote, el tamaño máximo de foto y se muestra
(no se edita) la carpeta de fotos. Los valores viven en ``CONFIGURACION`` (``btsync.config``); se validan,
se auditan en la misma transacción y, al cambiar el intervalo, se reaplica el job de DBMS_SCHEDULER.
"""

from __future__ import annotations

from btsync import config

from . import auditoria, db, permisos
from .auth import ErrorDeAcceso, Sesion

JOB_LOTE = "JOB_PROCESAR_CAPTURAS"   # las pruebas usan jobs «_TST» deshabilitados
JOB_PURGA = "JOB_PURGA_TRANSITO"     # la limpieza del staging no se configura desde la UI
CLAVES_PANTALLA = ("lote.intervalo_min", "fotos.max_mb")


def validar(cambios: dict[str, str]) -> dict[str, str]:
    """Los cambios normalizados; el primero fuera de rango lanza el error. ``fotos.dir`` no se edita."""
    limpios: dict[str, str] = {}
    for clave, valor in cambios.items():
        texto = str(valor).strip()
        if clave == "fotos.dir":
            raise ErrorDeAcceso("La carpeta de fotos la define la instalación y no se edita.")
        if not config.valido(clave, texto):
            rango = config.RANGOS.get(clave)
            if rango:
                nombre, minimo, maximo, unidad = rango
                raise ErrorDeAcceso(f"{nombre}: entre {minimo} y {maximo} {unidad}")
            raise ErrorDeAcceso(f"«{texto}» no es un valor válido para {clave}.")
        limpios[clave] = texto
    return limpios


def valores() -> dict[str, str]:
    with db._conexion() as conn:
        return config.leer(conn.cursor())


def carpeta_fotos(vigentes: dict[str, str] | None = None) -> str:
    """La carpeta de fotos tal como la ve la app (solo lectura)."""
    v = vigentes if vigentes is not None else valores()
    return v.get("fotos.dir") or ""


def guardar(quien: Sesion, cambios: dict[str, str], modulo: str = "configuracion") -> dict[str, str]:
    """Valida, guarda y audita lo que cambió; devuelve los valores vigentes."""
    permisos.exigir(quien, modulo)
    limpios = validar(cambios)
    with db._conexion() as conn:
        cur = conn.cursor()
        antes = config.leer(cur)
        cambiados = {k: v for k, v in limpios.items() if antes.get(k) != v}
        if cambiados:
            config.escribir(cur, cambiados)
            for clave, valor in cambiados.items():
                accion = "Cambió respaldo automático" if clave.startswith("respaldos.") else "Cambió configuración"
                auditoria.registrar(cur, quien.usuario, modulo, accion, f"{clave}: {antes.get(clave, '')} → {valor}")
        conn.commit()
        vigentes = config.leer(cur)
    if "lote.intervalo_min" in cambiados:
        aplicar_jobs(vigentes)
    return vigentes


def aplicar_jobs(vigentes: dict[str, str] | None = None) -> None:
    """Pone el intervalo del lote en el job (sin efecto si el job no existe)."""
    vigentes = vigentes or valores()
    if not vigentes.get("lote.intervalo_min"):
        return
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM user_scheduler_jobs WHERE job_name = :j", j=JOB_LOTE)
        if cur.fetchone()[0]:
            cur.callproc("DBMS_SCHEDULER.SET_ATTRIBUTE",
                         [JOB_LOTE, "repeat_interval", f"FREQ=MINUTELY;INTERVAL={int(vigentes['lote.intervalo_min'])}"])
