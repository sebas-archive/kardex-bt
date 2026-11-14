"""Configuración general: los valores que antes estaban fijos en el código, guardados en Oracle.

Una fila por clave en ``CONFIGURACION``; lo que no tiene fila vale lo de ``DEFAULTS``. La pantalla
Configuración edita ``lote.intervalo_min`` y ``fotos.max_mb``; ``fotos.dir`` es informativa (el servicio usa
``FOTOS_DIR``) y las claves ``respaldos.*`` las edita la pantalla Respaldos. El servicio Bluetooth lee el límite de
foto y la programación del respaldo automático.
"""

from __future__ import annotations

import re

from .store import ddl_tolerante

TABLA = "configuracion"   # las pruebas usan «configuracion_tst»

DEFAULTS: dict[str, str] = {
    "lote.intervalo_min": "1",
    "fotos.max_mb": "2",
    "fotos.dir": "/work/fotos",
    # Programación del respaldo automático (pantalla Respaldos, no Configuración).
    "respaldos.auto": "S",
    "respaldos.hora": "23:00",
    "respaldos.conservar": "7",
}

# clave -> (nombre en pantalla, mínimo, máximo, unidad) de las claves enteras.
RANGOS: dict[str, tuple[str, int, int, str]] = {
    "lote.intervalo_min": ("Procesar lecturas cada", 1, 60, "minutos"),
    "fotos.max_mb": ("Tamaño máximo de foto", 1, 10, "MB"),
    "respaldos.conservar": ("Conservar respaldos automáticos", 1, 90, "respaldos"),
}
HORA = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def valido(clave: str, texto: str) -> bool:
    """Si ``texto`` es un valor aceptable para ``clave`` (lo que guarda la pantalla ya pasó por aquí)."""
    if clave in RANGOS:
        _n, minimo, maximo, _u = RANGOS[clave]
        return re.fullmatch(r"\d{1,10}", texto) is not None and minimo <= int(texto) <= maximo
    if clave == "fotos.dir":
        return bool(texto) and len(texto) <= 200
    if clave == "respaldos.hora":
        return HORA.fullmatch(texto) is not None
    if clave == "respaldos.auto":
        return texto in ("S", "N")
    return False


def migrar(conn) -> None:
    """Crea la tabla si falta. Idempotente y tolerante a dos procesos a la vez."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=TABLA.upper())
    if not cur.fetchone()[0]:
        ddl_tolerante(cur, f"""CREATE TABLE {TABLA} (
            clave       VARCHAR2(40 CHAR)  PRIMARY KEY,
            valor       VARCHAR2(200 CHAR) NOT NULL,
            modificado  TIMESTAMP          DEFAULT SYSTIMESTAMP NOT NULL)""")
    conn.commit()


def leer(cur) -> dict[str, str]:
    """Todos los valores: los iniciales más lo guardado. Un valor guardado que no es válido (p. ej. llegó en un
    respaldo de otra época) vale el inicial: el servicio los usa sin pantalla de por medio."""
    cur.execute(f"SELECT clave, valor FROM {TABLA}")
    return {**DEFAULTS, **{clave: valor for clave, valor in cur if clave in DEFAULTS and valido(clave, valor)}}


def escribir(cur, cambios: dict[str, str]) -> None:
    """Guarda los valores dados (sin commit propio). Una clave que no está en ``DEFAULTS`` es un error de programa."""
    for clave, valor in cambios.items():
        if clave not in DEFAULTS:
            raise KeyError(clave)
        cur.execute(f"MERGE INTO {TABLA} c USING (SELECT :k clave FROM dual) x ON (c.clave = x.clave) "
                    f"WHEN MATCHED THEN UPDATE SET valor = :v, modificado = SYSTIMESTAMP "
                    f"WHEN NOT MATCHED THEN INSERT (clave, valor) VALUES (:k, :v)", k=clave, v=valor)
