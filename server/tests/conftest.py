"""Fixtures compartidas de las pruebas del servidor.

La conexión se toma de DB_DSN, DB_USER y DB_PASSWORD (las define el servicio `pybase`).
"""

import os
from pathlib import Path
from types import SimpleNamespace

import oracledb
import pytest

SCHEDULER_JOB = "JOB_PROCESAR_CAPTURAS"
FIXTURES = Path(__file__).parent / "fixtures"


def connect() -> oracledb.Connection:
    """Abre una conexión thick (Oracle 11g exige Instant Client), serializada como en producción."""
    from btsync.store import connect_oracle

    return connect_oracle(os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"])


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
# Cuenta de operador ACTIVO con la que abren sesión las pruebas (protocolo 3: HELLO + ACCT).
OPERADOR_ACTIVO = "tst-operador"


_purga = None


def _conexion_purga() -> oracledb.Connection:
    """Una sola conexión para las limpiezas de antes y después de cada prueba: abrir y cerrar una por llamada
    agota los procesos de Oracle XE (ORA-12516) cuando la suite crece."""
    global _purga
    if _purga is None or not _purga.is_healthy():
        _purga = connect()
    return _purga


def purge_test_rows() -> None:
    conn = _conexion_purga()
    if True:
        cur = conn.cursor()
        # El conteo es único y global: cada prueba parte sin lecturas ni conciliación contaminada.
        # La base de pruebas no conserva datos de usuario (se recrea con db/init).
        cur.execute("DELETE FROM registros_procesados WHERE id_conteo = 'ACTUAL'")
        cur.execute("UPDATE conciliacion SET cant_contada = NULL, diferencia = NULL, "
                    "diferencia_pct = NULL, fecha_calculo = SYSTIMESTAMP WHERE id_conteo = 'ACTUAL'")
        for pattern in TEST_DEVICE_PATTERNS:
            cur.execute("DELETE FROM sync_sesiones WHERE uuid_dispositivo LIKE :p", p=pattern)
            cur.execute("DELETE FROM captura_transito WHERE uuid_dispositivo LIKE :p", p=pattern)
            cur.execute("DELETE FROM dispositivos WHERE uuid LIKE :p", p=pattern)
            cur.execute("DELETE FROM usuarios WHERE usuario LIKE :p", p=pattern)
        cur.execute("INSERT INTO usuarios (usuario, nombre, rol, clave_hash, estado, origen) "
                    "VALUES (:u, 'Operador de prueba', 'OPERADOR', '-', 'ACTIVO', 'MOVIL')", u=OPERADOR_ACTIVO)
        conn.commit()


@pytest.fixture(scope="session", autouse=True)
def operador_de_prueba():
    """Deja la cuenta OPERADOR_ACTIVO lista antes de cualquier prueba (también las que no usan ``store``) y, al
    terminar la corrida, borra las cuentas de prueba: no deben quedar en la tabla real (Empleados, primer admin)."""
    from btsync import esquema

    conn = connect()
    try:
        esquema.migrar(conn)   # danados, fotos, configuración, servicio y paquete PL/SQL al día
    finally:
        conn.close()
    purge_test_rows()
    yield
    conn = connect()
    try:
        conn.cursor().execute("DELETE FROM usuarios WHERE usuario LIKE 'tst-%'")
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
        s.close()
        purge_test_rows()


def _sql_sections(path: Path) -> dict[str, list[str]]:
    """Lee un .sql con secciones '-- @nombre' y devuelve sus sentencias (separadas por ';')."""
    lines: dict[str, list[str]] = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("-- @"):
            current = stripped[4:].strip()
            lines[current] = []
        elif stripped and not stripped.startswith("--") and current is not None:
            lines[current].append(line)
    return {
        name: [stmt.strip() for stmt in "\n".join(body).split(";") if stmt.strip()]
        for name, body in lines.items()
    }


@pytest.fixture
def escenario():
    """Carga el escenario fijo de conciliación (conteo ACTUAL) y lo borra al terminar.

    ``escenario.cargar_lecturas()`` deja las 5 lecturas de la tabla como staging PENDIENTE.
    """
    sections = _sql_sections(FIXTURES / "escenario_conciliacion.sql")
    conn = connect()
    cur = conn.cursor()

    def run(name: str) -> None:
        for stmt in sections[name]:
            cur.execute(stmt)
        conn.commit()

    cur.execute("SELECT NVL(MAX(id), 0) FROM log_batch")
    log_mark = cur.fetchone()[0]
    run("cleanup")
    run("setup")
    try:
        yield SimpleNamespace(cargar_lecturas=lambda: run("lecturas"), log_mark=log_mark)
    finally:
        conn.rollback()
        run("cleanup")
        cur.execute("DELETE FROM log_batch WHERE id > :m", m=log_mark)
        conn.commit()
        conn.close()


def staging(conn, uuid, seq, ts_ms, conteo, sku, cant, operador="Ana", nota="", danados="") -> int:
    """Inserta (con COMMIT) una línea REC sin CRC en CAPTURA_TRANSITO y devuelve su ID_TRANSITO."""
    from btsync.protocol import Rec

    raw = Rec(seq, ts_ms, conteo, sku, str(cant), operador, nota, str(danados)).to_raw()
    cur = conn.cursor()
    out = cur.var(int)
    cur.execute(
        "INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw) "
        "VALUES (:u, :s, :r) RETURNING id_transito INTO :id",
        u=uuid, s=seq, r=raw, id=out,
    )
    conn.commit()
    return int(out.getvalue()[0])


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
            conn.cursor().execute(
                "BEGIN DBMS_SCHEDULER.DISABLE(:j, force => TRUE); END;", j=SCHEDULER_JOB
            )
        try:
            yield
        finally:
            if was_enabled:
                conn.cursor().callproc("DBMS_SCHEDULER.ENABLE", [SCHEDULER_JOB])
    finally:
        conn.close()


@pytest.fixture(scope="session")
def _tabla_config_tst():
    from btsync import config

    conn = connect()
    original, config.TABLA = config.TABLA, "configuracion_tst"
    try:
        config.migrar(conn)
    finally:
        config.TABLA = original
        conn.close()


@pytest.fixture(autouse=True)
def configuracion_de_prueba(monkeypatch, _tabla_config_tst):
    """La configuración que leen las sesiones de prueba es ``configuracion_tst`` (nunca la real del usuario)."""
    from btsync import config

    monkeypatch.setattr(config, "TABLA", "configuracion_tst")


@pytest.fixture(scope="session")
def _tablas_notificaciones_tst():
    """Crea las tablas ``_tst`` una vez y deja abierta UNA conexión para vaciarlas (abrir una por prueba hace que
    el listener de la XE responda ORA-12516)."""
    from btsync import notificaciones

    conn = connect()
    originales = notificaciones.TABLA, notificaciones.TABLA_LEIDAS
    notificaciones.TABLA, notificaciones.TABLA_LEIDAS = "notificaciones_tst", "notificaciones_leidas_tst"
    try:
        notificaciones.migrar(conn)
    finally:
        notificaciones.TABLA, notificaciones.TABLA_LEIDAS = originales
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def notificaciones_de_prueba(monkeypatch, _tablas_notificaciones_tst):
    """Las pruebas notifican en ``notificaciones_tst`` (vacía al empezar), nunca en la tabla real."""
    from btsync import notificaciones

    monkeypatch.setattr(notificaciones, "TABLA", "notificaciones_tst")
    monkeypatch.setattr(notificaciones, "TABLA_LEIDAS", "notificaciones_leidas_tst")
    conn = _tablas_notificaciones_tst
    conn.cursor().execute("DELETE FROM notificaciones_leidas_tst")
    conn.cursor().execute("DELETE FROM notificaciones_tst")
    conn.commit()
