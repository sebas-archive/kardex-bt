"""Respaldos (Fase 5): un zip con todas las tablas y las fotos; restaurar reemplaza todo en una transacción.

Las pruebas usan su propio par de tablas ``RESP_*_TST`` (padre e hija con FK) y una secuencia: nunca tocan las reales.
"""

import json
import os
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal

import oracledb
import pytest

from btsync import config, respaldo, servicio
from conftest import connect

TABLAS = ["RESP_PADRE_TST", "RESP_HIJA_TST"]
FILAS_PADRE = [
    (1, "Arroz | 500 g\nsegunda línea", Decimal("1234.567"), datetime(2026, 11, 14, 8, 30, 15, 123456)),
    (2, None, Decimal("-0.001"), None),
]


def _sql(conn, sql, **binds):
    cur = conn.cursor()
    cur.execute(sql, binds)
    return cur.fetchall() if cur.description else None


@pytest.fixture(scope="module")
def _esquema():
    """Las tablas de prueba se crean una vez: una tabla recién creada no se puede leer en una instantánea de solo
    lectura durante unos segundos (ORA-01466), y ``crear`` lo reintentaría en cada prueba."""
    conn = connect()
    cur = conn.cursor()
    for t in reversed(TABLAS):
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=t)
        if cur.fetchone()[0]:
            cur.execute(f"DROP TABLE {t}")
    cur.execute("CREATE TABLE resp_padre_tst (id NUMBER PRIMARY KEY, nombre VARCHAR2(80 CHAR), "
                "monto NUMBER(12,3), fecha TIMESTAMP)")
    cur.execute("CREATE TABLE resp_hija_tst (id NUMBER PRIMARY KEY, padre_id NUMBER NOT NULL "
                "REFERENCES resp_padre_tst (id), nota VARCHAR2(40 CHAR) DEFAULT 'sin nota')")
    yield
    for t in reversed(TABLAS):
        cur.execute(f"DROP TABLE {t}")
    cur.execute("SELECT COUNT(*) FROM user_sequences WHERE sequence_name = 'SEQ_RESP_TST'")
    if cur.fetchone()[0]:
        cur.execute("DROP SEQUENCE seq_resp_tst")
    conn.close()


@pytest.fixture
def base(_esquema, tmp_path, monkeypatch):
    monkeypatch.setenv("RESPALDOS_DIR", str(tmp_path / "respaldos"))
    monkeypatch.setenv("FOTOS_DIR", str(tmp_path / "fotos"))
    (tmp_path / "fotos" / "tel-1").mkdir(parents=True)
    (tmp_path / "fotos" / "tel-1" / "3.jpg").write_bytes(b"\xff\xd8foto\xff\xd9")
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM resp_hija_tst")
    cur.execute("DELETE FROM resp_padre_tst")
    cur.execute("SELECT COUNT(*) FROM user_sequences WHERE sequence_name = 'SEQ_RESP_TST'")
    if cur.fetchone()[0]:
        cur.execute("DROP SEQUENCE seq_resp_tst")
    cur.execute("CREATE SEQUENCE seq_resp_tst START WITH 1")
    cur.setinputsizes(None, None, None, oracledb.DB_TYPE_TIMESTAMP)
    cur.executemany("INSERT INTO resp_padre_tst VALUES (:1, :2, :3, :4)", FILAS_PADRE)
    cur.executemany("INSERT INTO resp_hija_tst VALUES (:1, :2, :3)", [(10, 1, "a"), (11, 2, None)])
    for _ in range(5):
        cur.execute("SELECT seq_resp_tst.NEXTVAL FROM dual")
    conn.commit()
    monkeypatch.setattr(respaldo, "tablas_de_la_app", lambda cur: list(TABLAS))
    monkeypatch.setattr(respaldo, "AUDITORIA", "auditoria_sin_tabla_tst")   # nunca en la auditoría real
    yield conn, tmp_path
    conn.rollback()
    conn.close()


def _padres(conn):
    cur = conn.cursor()
    cur.outputtypehandler = respaldo.numeros_exactos
    cur.execute("SELECT id, nombre, monto, fecha FROM resp_padre_tst ORDER BY id")
    return [(int(a), b, c, d) for a, b, c, d in cur]


def test_crear_y_restaurar_devuelve_lo_mismo(base):
    conn, tmp = base
    r = respaldo.crear(conn, "ana.gomez", "manual")
    assert r.origen == "manual" and r.usuario == "ana.gomez" and r.fotos == 1 and r.bytes > 0
    assert r.archivo.startswith("respaldo-") and r.archivo.endswith("-manual.zip")
    _sql(conn, "DELETE FROM resp_hija_tst")
    _sql(conn, "UPDATE resp_padre_tst SET nombre = 'otro'")
    _sql(conn, "INSERT INTO resp_padre_tst (id) VALUES (99)")
    conn.commit()
    (tmp / "fotos" / "tel-1" / "3.jpg").unlink()
    (tmp / "fotos" / "nueva.jpg").write_bytes(b"x")
    respaldo.restaurar(conn, r.archivo)
    assert _padres(conn) == [(1, *FILAS_PADRE[0][1:]), (2, *FILAS_PADRE[1][1:])]
    assert _sql(conn, "SELECT id, padre_id, nota FROM resp_hija_tst ORDER BY id") == [(10, 1, "a"), (11, 2, None)]
    assert (tmp / "fotos" / "tel-1" / "3.jpg").read_bytes() == b"\xff\xd8foto\xff\xd9"
    assert not (tmp / "fotos" / "nueva.jpg").exists()


def test_la_secuencia_queda_por_delante(base):
    conn, _ = base
    r = respaldo.crear(conn, "ana.gomez", "manual")
    with zipfile.ZipFile(respaldo.respaldos_dir() / r.archivo) as z:
        guardado = json.loads(z.read("manifest.json"))["secuencias"]["SEQ_RESP_TST"]
    _sql(conn, "DROP SEQUENCE seq_resp_tst")
    _sql(conn, "CREATE SEQUENCE seq_resp_tst START WITH 1")
    respaldo.restaurar(conn, r.archivo)
    assert _sql(conn, "SELECT seq_resp_tst.NEXTVAL FROM dual")[0][0] >= guardado


def _zip_alterado(origen, destino, cambio):
    with zipfile.ZipFile(origen) as z:
        partes = {n: z.read(n) for n in z.namelist()}
    cambio(partes)
    with zipfile.ZipFile(destino, "w") as z:
        for n, b in partes.items():
            z.writestr(n, b)


def test_una_fila_invalida_no_cambia_nada(base):
    conn, tmp = base
    r = respaldo.crear(conn, "ana.gomez", "manual")
    origen = respaldo.respaldos_dir() / r.archivo

    def hija_huerfana(partes):
        partes["datos/RESP_HIJA_TST.jsonl"] += b'[12, {"n": "777"}, "huerfana"]\n'

    _zip_alterado(origen, respaldo.respaldos_dir() / "respaldo-20260101-000000-manual.zip", hija_huerfana)
    _sql(conn, "UPDATE resp_padre_tst SET nombre = 'actual' WHERE id = 1")
    conn.commit()
    (tmp / "fotos" / "actual.jpg").write_bytes(b"y")
    with pytest.raises(Exception):
        respaldo.restaurar(conn, "respaldo-20260101-000000-manual.zip")
    assert _sql(conn, "SELECT nombre FROM resp_padre_tst WHERE id = 1") == [("actual",)]
    assert _sql(conn, "SELECT COUNT(*) FROM resp_hija_tst") == [(2,)]
    assert (tmp / "fotos" / "actual.jpg").exists() and (tmp / "fotos" / "tel-1" / "3.jpg").exists()


@pytest.mark.parametrize("cambio", [
    lambda m: m.update(formato=2),
    lambda m: m["tablas"]["RESP_PADRE_TST"]["columnas"].append("NO_EXISTE"),
    lambda m: m["tablas"].update(TABLA_FANTASMA_TST={"columnas": ["A"], "filas": 0}),
])
def test_otra_version_se_rechaza_sin_tocar_nada(base, cambio):
    conn, _ = base
    r = respaldo.crear(conn, "ana.gomez", "manual")

    def alterar(partes):
        m = json.loads(partes["manifest.json"])
        cambio(m)
        partes["manifest.json"] = json.dumps(m).encode()

    _zip_alterado(respaldo.respaldos_dir() / r.archivo, respaldo.respaldos_dir() / "otro.zip", alterar)
    _sql(conn, "UPDATE resp_padre_tst SET nombre = 'actual' WHERE id = 1")
    conn.commit()
    with pytest.raises(respaldo.ErrorRespaldo, match="Este respaldo es de otra versión del sistema"):
        respaldo.restaurar(conn, "otro.zip")
    assert _sql(conn, "SELECT nombre FROM resp_padre_tst WHERE id = 1") == [("actual",)]


def test_columna_que_el_respaldo_no_trae_toma_su_valor_por_defecto(base):
    conn, _ = base
    r = respaldo.crear(conn, "ana.gomez", "manual")

    def sin_nota(partes):
        m = json.loads(partes["manifest.json"])
        m["tablas"]["RESP_HIJA_TST"]["columnas"] = ["ID", "PADRE_ID"]
        partes["manifest.json"] = json.dumps(m).encode()
        partes["datos/RESP_HIJA_TST.jsonl"] = b'[{"n": "10"}, {"n": "1"}]\n'

    _zip_alterado(respaldo.respaldos_dir() / r.archivo, respaldo.respaldos_dir() / "viejo.zip", sin_nota)
    respaldo.restaurar(conn, "viejo.zip")
    assert _sql(conn, "SELECT id, nota FROM resp_hija_tst") == [(10, "sin nota")]


def test_sin_permiso_de_escritura_no_queda_nada_a_medias(base, tmp_path, monkeypatch):
    conn, _ = base
    carpeta = tmp_path / "solo-lectura"
    carpeta.mkdir()
    os.chmod(carpeta, 0o500)
    monkeypatch.setenv("RESPALDOS_DIR", str(carpeta))
    try:
        with pytest.raises(OSError):
            respaldo.crear(conn, "ana.gomez", "manual")
        assert respaldo.listar() == [] and list(carpeta.iterdir()) == []
    finally:
        os.chmod(carpeta, 0o700)


def test_un_parcial_no_aparece_en_la_lista(base):
    conn, _ = base
    respaldo.respaldos_dir().mkdir(parents=True, exist_ok=True)
    (respaldo.respaldos_dir() / "respaldo-20260101-000000-manual.zip.parcial").write_bytes(b"PK a medias")
    (respaldo.respaldos_dir() / "roto.zip").write_bytes(b"no es un zip")
    assert respaldo.listar() == []


def test_podar_borra_solo_los_automaticos_mas_viejos(base):
    conn, _ = base
    base_t = datetime(2026, 11, 1, 23, 0)
    for i in range(4):
        respaldo.crear(conn, "servicio", "auto", ahora=base_t + timedelta(days=i))
    manual = respaldo.crear(conn, "ana.gomez", "manual", ahora=base_t - timedelta(days=5))
    borrados = respaldo.podar(2)
    assert borrados == ["respaldo-20261102-230000-auto.zip", "respaldo-20261101-230000-auto.zip"]
    assert [r.archivo for r in respaldo.listar()] == [
        "respaldo-20261104-230000-auto.zip", "respaldo-20261103-230000-auto.zip", manual.archivo]


# ------------------------------------------------------------------ automático (lo corre el servicio)
@pytest.fixture
def cfg():
    conn = connect()
    conn.cursor().execute("DELETE FROM configuracion_tst")
    conn.commit()
    yield conn
    conn.cursor().execute("DELETE FROM configuracion_tst")
    conn.commit()
    conn.close()


def test_automatico_una_vez_al_dia_despues_de_la_hora(base, cfg):
    conn, _ = base
    config.escribir(cfg.cursor(), {"respaldos.hora": "23:00", "respaldos.conservar": "2"})
    cfg.commit()
    ahora = [datetime(2026, 11, 14, 22, 59)]
    tarea = respaldo.Automatico(connect, reloj=lambda: ahora[0])
    tarea()
    assert respaldo.listar() == []                               # antes de la hora
    ahora[0] = datetime(2026, 11, 14, 23, 1)
    tarea()
    assert [r.origen for r in respaldo.listar()] == ["auto"]
    otra = respaldo.Automatico(connect, reloj=lambda: ahora[0])  # el servicio se reinició el mismo día
    ahora[0] = datetime(2026, 11, 14, 23, 30)
    otra()
    assert len(respaldo.listar()) == 1
    ahora[0] = datetime(2026, 11, 15, 23, 5)
    otra()
    assert len(respaldo.listar()) == 2


def test_automatico_desactivado_no_crea(base, cfg):
    config.escribir(cfg.cursor(), {"respaldos.auto": "N"})
    cfg.commit()
    respaldo.Automatico(connect, reloj=lambda: datetime(2026, 11, 14, 23, 30))()
    assert respaldo.listar() == []


def test_el_servicio_corre_el_automatico(base, cfg, monkeypatch):
    llamadas = []
    monkeypatch.setattr(servicio, "TABLA", "servicio_bt_tst")
    from btsync.controller import SyncController
    from test_controller import FakeStore, FakeTransport

    ctl = SyncController(FakeTransport(), FakeStore(), lambda s: None)
    s = servicio.Servicio(ctl, connect, periodicas=[lambda: llamadas.append(1)])
    s.arrancar()
    try:
        s.tick()
        deadline = __import__("time").monotonic() + 5
        while not llamadas and __import__("time").monotonic() < deadline:
            __import__("time").sleep(0.05)
    finally:
        ctl.cancel()
    assert llamadas == [1]


# ------------------------------------------------------------------ revisión final: restauración robusta
@pytest.fixture
def jobs_tst(base):
    """JOB_RA_TST habilitado y JOB_RB_TST deshabilitado, con acciones inofensivas; se borran al terminar."""
    conn, _ = base
    cur = conn.cursor()
    for job, activo in (("JOB_RA_TST", "TRUE"), ("JOB_RB_TST", "FALSE")):
        cur.execute("SELECT COUNT(*) FROM user_scheduler_jobs WHERE job_name = :j", j=job)
        if cur.fetchone()[0]:
            cur.execute("BEGIN DBMS_SCHEDULER.DROP_JOB(:j, force => TRUE); END;", j=job)
        cur.execute(f"BEGIN DBMS_SCHEDULER.CREATE_JOB(job_name => :j, job_type => 'PLSQL_BLOCK', "
                    f"job_action => 'BEGIN NULL; END;', start_date => SYSTIMESTAMP + 1, "
                    f"repeat_interval => 'FREQ=DAILY', enabled => {activo}); END;", j=job)
    yield ("JOB_RA_TST", "JOB_RB_TST")
    for job in ("JOB_RA_TST", "JOB_RB_TST"):
        conn.cursor().execute("BEGIN DBMS_SCHEDULER.DROP_JOB(:j, force => TRUE); END;", j=job)


def _estados_jobs(conn):
    return dict(_sql(conn, "SELECT job_name, enabled FROM user_scheduler_jobs WHERE job_name IN ('JOB_RA_TST', 'JOB_RB_TST')"))


def test_restaurar_deja_los_jobs_como_estaban(base, jobs_tst):
    conn, _ = base
    r = respaldo.crear(conn, "ana.gomez", "manual")
    respaldo.restaurar(conn, r.archivo, jobs=jobs_tst)
    assert _estados_jobs(conn) == {"JOB_RA_TST": "TRUE", "JOB_RB_TST": "FALSE"}


def test_si_fallan_las_fotos_los_jobs_vuelven_y_no_queda_carpeta_nueva(base, jobs_tst, monkeypatch):
    conn, tmp = base
    r = respaldo.crear(conn, "ana.gomez", "manual")

    def falla(z, destino):
        destino.mkdir(parents=True)
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(respaldo, "_extraer_fotos", falla)
    with pytest.raises(Exception):
        respaldo.restaurar(conn, r.archivo, jobs=jobs_tst)
    assert _estados_jobs(conn) == {"JOB_RA_TST": "TRUE", "JOB_RB_TST": "FALSE"}
    assert not (tmp / "fotos.nueva").exists()


def test_otra_sesion_con_cambios_sin_confirmar_no_se_mezcla(base):
    conn, _ = base
    r = respaldo.crear(conn, "ana.gomez", "manual")
    otra = connect()
    try:
        otra.cursor().execute("UPDATE resp_padre_tst SET nombre = 'de otro escritorio' WHERE id = 2")
        with pytest.raises(respaldo.ErrorRespaldo, match="Otra sesión está usando los datos"):
            respaldo.restaurar(conn, r.archivo, espera_s=1)
    finally:
        otra.rollback()
        otra.close()
    assert len(_padres(conn)) == 2


def test_un_job_que_sigue_corriendo_impide_restaurar(base, jobs_tst, monkeypatch):
    conn, _ = base
    r = respaldo.crear(conn, "ana.gomez", "manual")
    monkeypatch.setattr(respaldo, "_jobs_corriendo", lambda conn, jobs: ["JOB_RA_TST"])
    with pytest.raises(respaldo.ErrorRespaldo, match="El procesamiento de lecturas sigue en curso"):
        respaldo.restaurar(conn, r.archivo, jobs=jobs_tst, espera_s=0.5)
    assert _estados_jobs(conn) == {"JOB_RA_TST": "TRUE", "JOB_RB_TST": "FALSE"}


def test_una_secuencia_rara_no_deja_las_fotos_viejas(base):
    conn, tmp = base
    r = respaldo.crear(conn, "ana.gomez", "manual")

    def secuencia_rara(partes):
        m = json.loads(partes["manifest.json"])
        m["secuencias"] = {"SEQ_RESP_TST": "abc"}
        partes["manifest.json"] = json.dumps(m).encode()

    _zip_alterado(respaldo.respaldos_dir() / r.archivo, respaldo.respaldos_dir() / "raro.zip", secuencia_rara)
    (tmp / "fotos" / "nueva.jpg").write_bytes(b"x")
    respaldo.restaurar(conn, "raro.zip")
    assert not (tmp / "fotos" / "nueva.jpg").exists() and (tmp / "fotos" / "tel-1" / "3.jpg").exists()
    assert not (tmp / "fotos.nueva").exists()


def test_restaurar_no_gasta_numeros_de_una_secuencia_que_va_por_delante(base):
    conn, _ = base
    r = respaldo.crear(conn, "ana.gomez", "manual")
    antes = _sql(conn, "SELECT seq_resp_tst.NEXTVAL FROM dual")[0][0]
    respaldo.restaurar(conn, r.archivo)
    assert _sql(conn, "SELECT seq_resp_tst.NEXTVAL FROM dual")[0][0] == antes + 1
