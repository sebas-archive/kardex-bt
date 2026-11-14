"""Fixtures de las pruebas de escritorio.

Reutilizan las del servidor (escenario fijo T-01, conexión, limpieza) en vez de duplicarlas: una sola definición
del escenario y de sus valores exactos. Las cuentas de prueba viven en ``usuarios_tst`` y la matriz en
``permisos_tst``: las pruebas nunca tocan las cuentas reales.
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
escenario = server_conftest.escenario          # escenario T-01, SKUs A1-A5
scheduler_off = server_conftest.scheduler_off  # autouse: el job de 60 s no procesa a mitad de un test

# Utilidades para los tests: `from conftest import staging, connect`.
staging = server_conftest.staging
connect = server_conftest.connect
_tablas_notificaciones_tst = server_conftest._tablas_notificaciones_tst
notificaciones_de_prueba = server_conftest.notificaciones_de_prueba
configuracion_de_prueba = server_conftest.configuracion_de_prueba


import pytest  # noqa: E402

_DDL_USUARIOS_TST = """
CREATE TABLE usuarios_tst (
    usuario          VARCHAR2(30 CHAR)  NOT NULL,
    nombre           VARCHAR2(60 CHAR)  NOT NULL,
    correo           VARCHAR2(120 CHAR),
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
    pregunta         VARCHAR2(200 CHAR),
    respuesta_hash   VARCHAR2(200 CHAR),
    foto             VARCHAR2(200 CHAR),
    tema             VARCHAR2(10 CHAR)  DEFAULT 'sistema',
    idioma           VARCHAR2(2 CHAR)   DEFAULT 'es',
    clave_motivo     VARCHAR2(300 CHAR),
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
    """Cuentas de prueba en una tabla aparte (``usuarios_tst``), vacía en cada test."""
    from app import auth, db

    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM user_tab_columns WHERE table_name = 'USUARIOS_TST' AND column_name = 'CORREO'")
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


@pytest.fixture(autouse=True)
def _notificaciones_tst_limpias(notificaciones_de_prueba):
    """Fuerza el aislamiento de notificaciones en todas las pruebas (el alias no conserva bien autouse)."""
    yield


@pytest.fixture(autouse=True)
def _configuracion_tst_limpia(configuracion_de_prueba):
    yield


@pytest.fixture(autouse=True)
def idioma_es():
    """Cada prueba empieza en español (el idioma es estado global y algunas pruebas lo cambian)."""
    from app import i18n
    i18n.set_idioma("es")
    yield
    i18n.set_idioma("es")


@pytest.fixture(scope="session")
def _tabla_auditoria_tst():
    """Crea ``auditoria_tst`` una vez por corrida (las pruebas nunca escriben en la auditoría real)."""
    from app import auditoria, db

    original = auditoria.TABLA
    auditoria.TABLA = "auditoria_tst"
    try:
        auditoria.migrar()
    finally:
        auditoria.TABLA = original
    with db._conexion() as conn:
        conn.commit()


@pytest.fixture(autouse=True)
def auditoria_db(monkeypatch, _tabla_auditoria_tst):
    """Toda prueba audita en ``auditoria_tst``, vacía al empezar."""
    from app import auditoria, db

    monkeypatch.setattr(auditoria, "TABLA", "auditoria_tst")
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM auditoria_tst")
        conn.commit()
    yield auditoria


@pytest.fixture(scope="session")
def _tabla_config_tst():
    from app import db
    from btsync import config

    original = config.TABLA
    config.TABLA = "configuracion_tst"
    try:
        with db._conexion() as conn:
            config.migrar(conn)
    finally:
        config.TABLA = original


@pytest.fixture(autouse=True)
def config_tst(monkeypatch, _tabla_config_tst):
    """Toda prueba lee y escribe la configuración en ``configuracion_tst``, vacía (valen los iniciales)."""
    from app import db
    from btsync import config

    monkeypatch.setattr(config, "TABLA", "configuracion_tst")
    with db._conexion() as conn:
        conn.cursor().execute("DELETE FROM configuracion_tst")
        conn.commit()


def _jobs_tst(*jobs: tuple[str, str]) -> None:
    """(Re)crea jobs ``_TST`` deshabilitados. Su acción es inofensiva: aunque alguien los habilite, no tocan datos."""
    from app import db

    with db._conexion() as conn:
        cur = conn.cursor()
        for job, intervalo in jobs:
            _borrar_job(cur, job)
            cur.execute("BEGIN DBMS_SCHEDULER.CREATE_JOB(job_name => :j, job_type => 'PLSQL_BLOCK', "
                        "job_action => 'BEGIN NULL; END;', repeat_interval => :i, enabled => FALSE); END;",
                        j=job, i=intervalo)
        conn.commit()


def _borrar_job(cur, job: str) -> None:
    cur.execute("SELECT COUNT(*) FROM user_scheduler_jobs WHERE job_name = :j", j=job)
    if cur.fetchone()[0]:
        cur.execute("BEGIN DBMS_SCHEDULER.DROP_JOB(:j, force => TRUE); END;", j=job)


@pytest.fixture
def config_db(monkeypatch, config_tst):
    """La configuración de prueba y dos jobs ``_TST`` deshabilitados en lugar de los reales (las pruebas nunca
    cambian el lote de verdad). Se borran al terminar."""
    from app import configuracion, db

    monkeypatch.setattr(configuracion, "JOB_LOTE", "JOB_PROCESAR_TST")
    monkeypatch.setattr(configuracion, "JOB_PURGA", "JOB_PURGA_TST")
    _jobs_tst(("JOB_PROCESAR_TST", "FREQ=SECONDLY;INTERVAL=60"), ("JOB_PURGA_TST", "FREQ=DAILY"))
    yield configuracion
    with db._conexion() as conn:
        conn.rollback()
        for job in ("JOB_PROCESAR_TST", "JOB_PURGA_TST"):
            _borrar_job(conn.cursor(), job)


@pytest.fixture
def servicio_db(monkeypatch):
    """El estado del servicio Bluetooth en ``servicio_bt_tst`` (vacía al empezar)."""
    from app import db
    from btsync import servicio as bt

    monkeypatch.setattr(bt, "TABLA", "servicio_bt_tst")
    with db._conexion() as conn:
        bt.migrar(conn)
        conn.cursor().execute("DELETE FROM servicio_bt_tst")
        conn.commit()

    def poner(hace_s=0, **valores):
        """Escribe la fila como lo haría el servicio, con un latido de hace ``hace_s`` segundos."""
        fila = {"estado": "ESPERANDO_EMPAREJAMIENTO", "pausado": "N", **valores}
        with db._conexion() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM servicio_bt_tst")
            columnas = ", ".join(fila)
            marcas = ", ".join(f":{k}" for k in fila)
            cur.execute(f"INSERT INTO servicio_bt_tst (id, {columnas}, latido) "
                        f"VALUES (1, {marcas}, SYSTIMESTAMP - NUMTODSINTERVAL(:hace, 'SECOND'))", {**fila, "hace": hace_s})
            conn.commit()

    def leer(columna):
        with db._conexion() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT {columna} FROM servicio_bt_tst WHERE id = 1")
            return cur.fetchone()[0]

    return poner, leer


@pytest.fixture(scope="session")
def _tablas_respaldo_tst():
    """Dos tablas ``RESP_*_TST`` (padre e hija), creadas una vez: los respaldos de prueba solo ven estas."""
    from app import db

    with db._conexion() as conn:
        cur = conn.cursor()
        for t in ("RESP_HIJA_TST", "RESP_PADRE_TST"):
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=t)
            if cur.fetchone()[0]:
                cur.execute(f"DROP TABLE {t}")
        cur.execute("CREATE TABLE resp_padre_tst (id NUMBER PRIMARY KEY, nombre VARCHAR2(80 CHAR))")
        cur.execute("CREATE TABLE resp_hija_tst (id NUMBER PRIMARY KEY, padre_id NUMBER REFERENCES resp_padre_tst (id))")
        conn.commit()


@pytest.fixture
def respaldos_db(monkeypatch, tmp_path, _tablas_respaldo_tst, servicio_db, config_tst):
    """Respaldos en ``tmp_path`` sobre las tablas de prueba, con jobs ``_TST`` inofensivos y el servicio de prueba."""
    from app import db, respaldos
    from btsync import respaldo

    monkeypatch.setenv("RESPALDOS_DIR", str(tmp_path / "respaldos"))
    monkeypatch.setenv("FOTOS_DIR", str(tmp_path / "fotos"))
    monkeypatch.setattr(respaldo, "tablas_de_la_app", lambda cur: ["RESP_PADRE_TST", "RESP_HIJA_TST"])
    monkeypatch.setattr(respaldos, "JOBS", ("JOB_RESP_A_TST", "JOB_RESP_B_TST"))
    _jobs_tst(("JOB_RESP_A_TST", "FREQ=DAILY"), ("JOB_RESP_B_TST", "FREQ=DAILY"))
    with db._conexion() as conn:   # habilitados (su acción no hace nada): restaurar debe dejarlos así
        for job in ("JOB_RESP_A_TST", "JOB_RESP_B_TST"):
            conn.cursor().callproc("DBMS_SCHEDULER.ENABLE", [job])
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM resp_hija_tst")
        cur.execute("DELETE FROM resp_padre_tst")
        cur.execute("INSERT INTO resp_padre_tst VALUES (1, 'original')")
        conn.commit()
    yield respaldos
    with db._conexion() as conn:
        conn.rollback()
        for job in ("JOB_RESP_A_TST", "JOB_RESP_B_TST"):
            _borrar_job(conn.cursor(), job)
