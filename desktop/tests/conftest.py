"""Fixtures de las pruebas de escritorio.

Reutilizan las del servidor (escenario fijo T-01, conexión, limpieza) en vez de duplicarlas:
una sola definición del escenario y de sus valores exactos.
"""

import importlib.util
import os
from pathlib import Path

# Las pruebas comprueban el estado final de cada vista: sin animaciones no hay que esperar a que terminen.
# Las que prueban la animación en sí la vuelven a activar (monkeypatch de ``widgets.ANIMAR``).
os.environ.setdefault("APP_SIN_ANIMACIONES", "1")

_SERVER_CONFTEST = Path(__file__).resolve().parents[2] / "server" / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location("server_conftest", _SERVER_CONFTEST)
server_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server_conftest)

# Fixtures (pytest las recoge por nombre desde este módulo).
escenario = server_conftest.escenario          # conteo T-01, ubicaciones U1-U3, SKUs A1-A5
scheduler_off = server_conftest.scheduler_off  # autouse: el job de 60 s no procesa a mitad de un test

# Utilidades para los tests: `from conftest import staging, connect`.
staging = server_conftest.staging
connect = server_conftest.connect


import pytest  # noqa: E402

_DDL_USUARIOS_TST = """
CREATE TABLE usuarios_tst (
    usuario          VARCHAR2(30 CHAR)  NOT NULL,
    nombre           VARCHAR2(60 CHAR)  NOT NULL,
    rol              VARCHAR2(12 CHAR),
    clave_hash       VARCHAR2(200 CHAR) NOT NULL,
    clave_pendiente  VARCHAR2(200 CHAR),
    estado           VARCHAR2(10 CHAR)  DEFAULT 'PENDIENTE' NOT NULL,
    motivo           VARCHAR2(300 CHAR),
    resuelto_por     VARCHAR2(30 CHAR),
    resuelto         TIMESTAMP,
    origen           VARCHAR2(10 CHAR)  DEFAULT 'ESCRITORIO' NOT NULL,
    uuid_dispositivo VARCHAR2(50 CHAR),
    intentos         NUMBER             DEFAULT 0 NOT NULL,
    bloqueado_hasta  TIMESTAMP,
    creado           TIMESTAMP          DEFAULT SYSTIMESTAMP,
    CONSTRAINT pk_usuarios_tst PRIMARY KEY (usuario),
    CONSTRAINT ck_usuarios_tst_rol CHECK (rol IS NULL OR rol IN ('ADMIN', 'INVENTARIO', 'OPERADOR')),
    CONSTRAINT ck_usuarios_tst_estado CHECK (estado IN ('PENDIENTE', 'ACTIVO', 'RECHAZADO', 'SUSPENDIDO'))
)"""


@pytest.fixture
def permisos_db(monkeypatch):
    """Matriz de permisos de prueba en ``permisos_tst``, con los valores iniciales en cada test."""
    from app import db, permisos

    monkeypatch.setattr(permisos, "TABLA", "permisos_tst")
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'PERMISOS_TST'")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM permisos_tst")
            conn.commit()
    permisos.migrar()   # crea la tabla si falta y pone los valores iniciales
    return permisos


@pytest.fixture
def cuentas(monkeypatch, permisos_db):
    """Cuentas de prueba en una tabla aparte (``usuarios_tst``), vacía en cada test.

    Las pruebas nunca tocan la tabla real ``usuarios``: ahí están las cuentas de quien usa la aplicación.
    """
    from app import auth, db

    # Se usa la conexión del hilo (la misma de la aplicación): abrir una por prueba satura el listener de la XE.
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM user_tab_columns WHERE table_name = 'USUARIOS_TST' AND column_name = 'UUID_DISPOSITIVO'")
        if cur.fetchone()[0] == 0:                        # no existe o es de un esquema anterior: se rehace
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'USUARIOS_TST'")
            if cur.fetchone()[0]:
                cur.execute("DROP TABLE usuarios_tst")
            cur.execute(_DDL_USUARIOS_TST)
        cur.execute("DELETE FROM usuarios_tst")
        conn.commit()
    monkeypatch.setattr(auth, "TABLA", "usuarios_tst")
    monkeypatch.setattr(auth, "ITERACIONES", 1_000)  # pocas vueltas: la prueba no mide la lentitud del hash
    return auth


@pytest.fixture
def maestros_db(monkeypatch, cuentas):
    """Categorías, almacenes y existencias de prueba en tablas ``*_tst``, recién sembradas en cada test."""
    from app import db, maestros

    for constante, tabla in (("CATEGORIAS", "categorias_tst"), ("ALMACENES", "almacenes_tst"), ("EXISTENCIAS", "existencias_tst")):
        monkeypatch.setattr(maestros, constante, tabla)
    with db._conexion() as conn:
        cur = conn.cursor()
        for tabla in ("existencias_tst", "almacenes_tst", "categorias_tst"):
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=tabla.upper())
            if cur.fetchone()[0]:
                cur.execute(f"DROP TABLE {tabla}")
        conn.commit()
    maestros.migrar()
    return maestros


def _limpiar_tareas_tst(cur) -> None:
    for tabla in ("revisiones", "conciliacion", "registros_procesados", "stock_sistema"):
        cur.execute(f"DELETE FROM {tabla} WHERE id_conteo LIKE 'TT-%'")
    cur.execute("DELETE FROM captura_transito WHERE uuid_dispositivo = 'tst-tareas-esc'")
    cur.execute("DELETE FROM conteos WHERE id_conteo LIKE 'TT-%'")


@pytest.fixture
def tareas_db(monkeypatch, maestros_db):
    """Tareas de conteo sobre las tablas reales con ids ``TT-*`` (se borran antes y después) y almacenes,
    categorías, existencias y cuentas de prueba (``*_tst``)."""
    from app import db, tareas
    from btsync import tareas as bt

    monkeypatch.setattr(tareas, "PREFIJO", "TT-")
    with db._conexion() as conn:
        bt.migrar(conn)
        _limpiar_tareas_tst(conn.cursor())
        conn.commit()
    yield tareas
    with db._conexion() as conn:
        conn.rollback()
        _limpiar_tareas_tst(conn.cursor())
        conn.commit()
