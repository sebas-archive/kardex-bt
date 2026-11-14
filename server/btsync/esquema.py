"""Cambios de esquema para bases creadas antes: la columna ``registros_procesados.danados``, la tabla ``fotos``,
``configuracion``, ``servicio_bt``, las notificaciones y el paquete ``pkg_batch`` del dominio continuo.

Una base nueva ya los trae (``db/init/01_schema.sql`` y ``03_pkg_batch.sql``). Una anterior los recibe aquí: lo llama
el escritorio al arrancar y la fixture de sesión de las pruebas del servidor. El paquete solo se recompila si el
compilado no conoce ``ALTA_SKU``, para no invalidarlo mientras el job lo usa.
"""

from __future__ import annotations

import re
from pathlib import Path

from .store import ddl_tolerante

PAQUETE = Path(__file__).resolve().parents[2] / "db" / "init" / "03_pkg_batch.sql"
_BLOQUE = re.compile(r"^(CREATE OR REPLACE PACKAGE.*?)^/\s*$", re.S | re.M)


def paquete_al_dia(cur) -> bool:
    cur.execute("SELECT COUNT(*) FROM user_source WHERE name = 'PKG_BATCH' AND type = 'PACKAGE BODY' "
                "AND UPPER(text) LIKE '%ALTA_SKU%'")   # marca de la última versión del paquete
    return cur.fetchone()[0] > 0


def _recompilar(cur) -> None:
    """Ejecuta el paquete (especificación y cuerpo) de ``03_pkg_batch.sql`` y falla si no compila."""
    texto = PAQUETE.read_text(encoding="utf-8")
    for bloque in _BLOQUE.findall(texto):
        cur.execute(bloque.strip())   # termina en «END pkg_batch;»: el punto y coma es parte del PL/SQL
    cur.execute("SELECT COUNT(*), MAX(line || ': ' || SUBSTR(text, 1, 200)) FROM user_errors WHERE name = 'PKG_BATCH'")
    errores, detalle = cur.fetchone()
    if errores:
        raise RuntimeError(f"PKG_BATCH no compila: {detalle}")


def migrar(conn) -> None:
    """Idempotente y tolerante a dos escritorios a la vez."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM user_tab_columns WHERE table_name = 'REGISTROS_PROCESADOS' "
                "AND column_name = 'DANADOS'")
    if not cur.fetchone()[0]:
        ddl_tolerante(cur, "ALTER TABLE registros_procesados ADD (danados NUMBER(12, 3))")
    cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'FOTOS'")
    if not cur.fetchone()[0]:
        ddl_tolerante(cur, """CREATE TABLE fotos (
            uuid_dispositivo  VARCHAR2(50 CHAR)  NOT NULL,
            seq               NUMBER             NOT NULL,
            ruta              VARCHAR2(200 CHAR) NOT NULL,
            bytes             NUMBER             NOT NULL,
            recibida          TIMESTAMP          DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT pk_fotos PRIMARY KEY (uuid_dispositivo, seq))""")
    from . import config, notificaciones, servicio

    config.migrar(conn)          # configuración general
    servicio.migrar(conn)        # estado del servicio Bluetooth
    notificaciones.migrar(conn)  # avisos
    if not paquete_al_dia(cur) and PAQUETE.exists():
        _recompilar(cur)
    conn.commit()
