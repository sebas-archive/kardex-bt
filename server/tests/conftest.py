"""Fixtures compartidas de las pruebas del servidor.

La conexión se toma de DB_DSN, DB_USER y DB_PASSWORD (las define el servicio `pybase`).
"""

import os

import oracledb
import pytest

SCHEDULER_JOB = "JOB_PROCESAR_CAPTURAS"

_client_ready = False


def connect() -> oracledb.Connection:
    """Abre una conexión thick (Oracle 11g exige Instant Client)."""
    global _client_ready
    if not _client_ready:
        oracledb.init_oracle_client()
        _client_ready = True
    return oracledb.connect(
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dsn=os.environ["DB_DSN"],
    )


@pytest.fixture
def db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


# Los tests que usan Store/Session/e2e escriben con conexiones propias (COMMIT real), así que
# limpian por prefijo de dispositivo; las filas reales de la app nunca usan estos prefijos.
TEST_DEVICE_PATTERNS = ("tst-%", "dev-e2e%")


def purge_test_rows() -> None:
    conn = connect()
    try:
        cur = conn.cursor()
        for pattern in TEST_DEVICE_PATTERNS:
            cur.execute("DELETE FROM sync_sesiones WHERE uuid_dispositivo LIKE :p", p=pattern)
            cur.execute("DELETE FROM captura_transito WHERE uuid_dispositivo LIKE :p", p=pattern)
            cur.execute("DELETE FROM dispositivos WHERE uuid LIKE :p", p=pattern)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def store():
    from btsync.store import Store

    purge_test_rows()
    s = Store(os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"])
    try:
        yield s
    finally:
        s.rollback()
        purge_test_rows()


def _job_enabled(conn: oracledb.Connection) -> bool | None:
    """True/False según el estado del job; None si el job aún no existe."""
    cur = conn.cursor()
    cur.execute(
        "SELECT enabled FROM user_scheduler_jobs WHERE job_name = :j", j=SCHEDULER_JOB
    )
    row = cur.fetchone()
    return None if row is None else row[0] == "TRUE"


@pytest.fixture(scope="session", autouse=True)
def scheduler_off():
    """Deshabilita el job de 60 s durante las pruebas para que no procese filas a mitad de un test.

    Sin efecto si la BD no responde o si el job todavía no existe.
    """
    try:
        conn = connect()
    except (oracledb.Error, oracledb.InterfaceError):
        yield
        return
    try:
        was_enabled = _job_enabled(conn) is True
        if was_enabled:
            conn.cursor().callproc("DBMS_SCHEDULER.DISABLE", [SCHEDULER_JOB])
        try:
            yield
        finally:
            if was_enabled:
                conn.cursor().callproc("DBMS_SCHEDULER.ENABLE", [SCHEDULER_JOB])
    finally:
        conn.close()
