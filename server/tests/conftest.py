"""Fixtures compartidas de las pruebas del servidor.

La conexión se toma de DB_DSN, DB_USER y DB_PASSWORD (las define el servicio `pybase`).
"""

import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace

import oracledb
import pytest

SCHEDULER_JOB = "JOB_PROCESAR_CAPTURAS"
FIXTURES = Path(__file__).parent / "fixtures"
# Marca persistente para reparar una corrida anterior que murió con el job apagado. Vive en logs/
# (ignorado por git y montado en /work) para sobrevivir a `docker compose run --rm`.
_SCHEDULER_MARCA = Path(__file__).resolve().parents[2] / "logs" / ".scheduler_off.json"


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

# Lecturas ya procesadas que existían ANTES de la primera limpieza: la suite corre contra la base del
# stack vivo, así que son datos REALES del usuario y no se borran nunca. Las filas que escriben los
# tests (todas posteriores al arranque de la sesión) sí se limpian.
_PROTEGIDOS: set[int] | None = None
# Marca de LOG_BATCH al empezar la sesión: al terminar se borran las corridas de las pruebas.
_LOG_MARK: int | None = None


def _conexion_purga() -> oracledb.Connection:
    """Una sola conexión para las limpiezas de antes y después de cada prueba: abrir y cerrar una por llamada
    agota los procesos de Oracle XE (ORA-12516) cuando la suite crece."""
    global _purga
    if _purga is None or not _purga.is_healthy():
        _purga = connect()
    return _purga


def _filas_reales(conn: oracledb.Connection) -> set[int]:
    """IDs de REGISTROS_PROCESADOS que no son de las pruebas: las lecturas reales del stack vivo.

    Incluye las que ya existían al empezar la sesión y las que lleguen durante ella desde un dispositivo
    real (uuid distinto de los de prueba): la limpieza de los tests nunca las borra.
    """
    global _PROTEGIDOS, _LOG_MARK
    cur = conn.cursor()
    if _PROTEGIDOS is None:
        cur.execute("SELECT id_registro FROM registros_procesados WHERE id_conteo = 'ACTUAL'")
        _PROTEGIDOS = {int(fila[0]) for fila in cur}
        cur.execute("SELECT NVL(MAX(id), 0) FROM log_batch")
        _LOG_MARK = int(cur.fetchone()[0])
    donde = " OR ".join(f"t.uuid_dispositivo LIKE :p{i}" for i in range(len(TEST_DEVICE_PATTERNS)))
    cur.execute(
        "SELECT r.id_registro FROM registros_procesados r WHERE r.id_conteo = 'ACTUAL' "
        "AND EXISTS (SELECT 1 FROM captura_transito t WHERE t.id_transito = r.id_transito "
        f"AND NOT ({donde}))",
        {f"p{i}": patron for i, patron in enumerate(TEST_DEVICE_PATTERNS)},
    )
    return _PROTEGIDOS | {int(fila[0]) for fila in cur}


def _borrar_lecturas_de_prueba(conn: oracledb.Connection) -> None:
    """Borra las lecturas procesadas por los tests y conserva las reales (por lotes: 11g sin IN gigante)."""
    cur = conn.cursor()
    reales = _filas_reales(conn)
    cur.execute("SELECT id_registro FROM registros_procesados WHERE id_conteo = 'ACTUAL'")
    sobrantes = [int(fila[0]) for fila in cur if int(fila[0]) not in reales]
    for inicio in range(0, len(sobrantes), 500):
        lote = sobrantes[inicio:inicio + 500]
        marcas = ",".join(f":{i + 1}" for i in range(len(lote)))
        cur.execute(f"DELETE FROM registros_procesados WHERE id_registro IN ({marcas})", lote)


def _borrar_bitacora_de_prueba(conn: oracledb.Connection) -> None:
    """Borra las corridas de LOG_BATCH que dejaron los tests (las reales anteriores a la sesión se conservan)."""
    if _LOG_MARK is None:
        return
    conn.cursor().execute("DELETE FROM log_batch WHERE id > :m", m=_LOG_MARK)


def purge_test_rows() -> None:
    conn = _conexion_purga()
    if True:
        cur = conn.cursor()
        # El conteo es único y global: cada prueba parte sin lecturas ni conciliación contaminada.
        # La base de pruebas no conserva datos de usuario (se recrea con db/init) PERO el stack puede
        # ser el vivo: las filas que ya existían al empezar la sesión nunca se borran.
        _borrar_lecturas_de_prueba(conn)
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
    terminar la corrida, borra las cuentas de prueba: no deben quedar en la tabla real (Empleados, primer admin).

    Al terminar también se limpia lo que escribieron las pruebas (lecturas, tránsito y bitácora) y se recalcula
    CONCILIACION con las lecturas reales, que la limpieza nunca borra: la base del stack vivo queda como estaba.
    """
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
        purge_test_rows()
        _borrar_bitacora_de_prueba(conn)
        conn.cursor().execute("DELETE FROM usuarios WHERE usuario LIKE 'tst-%'")
        conn.commit()
        try:   # deja CONCILIACION como estaba (con las lecturas reales que la limpieza conservó)
            conn.cursor().execute("BEGIN pkg_batch.conciliar('ACTUAL'); END;")
            conn.commit()
        except oracledb.Error:
            pass
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


def _restaurar_job(job_name: str) -> None:
    """Re-habilita el job SIEMPRE (aunque la conexión de la sesión haya muerto); reintenta una vez."""
    for _ in range(2):
        try:
            conn = connect()
        except (oracledb.Error, oracledb.InterfaceError):
            continue
        try:
            conn.cursor().execute("BEGIN DBMS_SCHEDULER.ENABLE(:j); END;", j=job_name)
            conn.commit()
            return
        except oracledb.Error:
            continue
        finally:
            conn.close()


def _leer_marca_job() -> dict:
    try:
        return json.loads(_SCHEDULER_MARCA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _escribir_marca_job(estado: dict) -> None:
    try:
        _SCHEDULER_MARCA.parent.mkdir(parents=True, exist_ok=True)
        _SCHEDULER_MARCA.write_text(json.dumps(estado), encoding="utf-8")
    except OSError:
        pass


def _borrar_marca_job() -> None:
    try:
        _SCHEDULER_MARCA.unlink()
    except OSError:
        pass


@pytest.fixture(scope="session", autouse=True)
def scheduler_off():
    """Deshabilita el job de 60 s durante las pruebas para que no procese filas a mitad de un test.

    Un pytest interrumpido dejó ``JOB_PROCESAR_CAPTURAS`` apagado en la BD real: el ``finally`` no corre
    ante un kill duro / contenedor muerto / ``docker compose run`` cortado, y nada más lo vuelve a
    habilitar (``db/init`` solo corre al crear el volumen). Por eso:
      * si el job estaba habilitado al empezar, se re-habilita SIEMPRE en el ``finally`` y ante SIGTERM;
      * antes de deshabilitarlo se deja una marca en ``logs/`` (sobrevive a ``--rm`` porque ``/work`` es
        el repo montado) y la siguiente corrida la lee para devolver el job a su estado original aunque
        la anterior muriera.
    Solo se toca ``JOB_PROCESAR_CAPTURAS`` (``JOB_PURGA_TRANSITO`` no se re-habilita aquí).
    Sin efecto si la BD no responde o si el job todavía no existe.
    """
    try:
        conn = connect()
    except (oracledb.Error, oracledb.InterfaceError):
        yield
        return

    handler_previo = None
    try:
        # Reparación de una corrida anterior que murió con el job apagado.
        if _leer_marca_job().get("habilitado_antes") is True and _job_enabled(conn) is False:
            _restaurar_job(SCHEDULER_JOB)
        _borrar_marca_job()

        was_enabled = _job_enabled(conn) is True
        if was_enabled:
            conn.cursor().execute(
                "BEGIN DBMS_SCHEDULER.DISABLE(:j, force => TRUE); END;", j=SCHEDULER_JOB
            )
            conn.commit()
            _escribir_marca_job({"habilitado_antes": True})

            def _restaurar_al_terminar(signum, frame):   # SIGTERM: kill "limpio" del contenedor
                _restaurar_job(SCHEDULER_JOB)
                _borrar_marca_job()
                try:
                    signal.signal(signal.SIGTERM, handler_previo or signal.SIG_DFL)
                except (OSError, ValueError):
                    pass
                os.kill(os.getpid(), signal.SIGTERM)

            try:
                handler_previo = signal.signal(signal.SIGTERM, _restaurar_al_terminar)
            except (OSError, ValueError):   # fuera del hilo principal: quedan el finally y la marca
                handler_previo = None

        try:
            yield
        finally:
            if was_enabled:
                _restaurar_job(SCHEDULER_JOB)
                _borrar_marca_job()
            if handler_previo is not None:
                try:
                    signal.signal(signal.SIGTERM, handler_previo)
                except (OSError, ValueError):
                    pass
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
