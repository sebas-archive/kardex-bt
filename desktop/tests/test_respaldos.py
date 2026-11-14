"""Respaldos desde el escritorio (Fase 5): crear, listar, restaurar todo y el automático."""

import pytest

from app import db as dbq
from app.auth import INVENTARIO, PREGUNTAS, ErrorDeAcceso


def _sql(sql, **binds):
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute(sql, binds)
        filas = cur.fetchall() if cur.description else None
        conn.commit()
        return filas


def _habilitados():
    return dict(_sql("SELECT job_name, enabled FROM user_scheduler_jobs WHERE job_name LIKE 'JOB_RESP_%'"))


@pytest.fixture
def gente(cuentas, respaldos_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026", correo="ana@example.com",
                            pregunta=PREGUNTAS[0], respuesta="firulais")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026", correo="luis@example.com")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    return respaldos_db, ana, cuentas.iniciar_sesion("luis", "conteo2026")


def test_crear_y_listar(gente, auditoria_db):
    r, ana, _luis = gente
    hecho = r.crear(ana)
    assert [x.archivo for x in r.listar(ana)] == [hecho.archivo] and hecho.origen == "manual"
    assert [(e.modulo, e.accion, e.detalle) for e in auditoria_db.listar(ana) if e.modulo == "respaldos"] == [
        ("respaldos", "Creó respaldo", hecho.archivo)]


def test_inventario_no_crea_ni_restaura(gente):
    r, ana, luis = gente
    hecho = r.crear(ana)
    with pytest.raises(ErrorDeAcceso):
        r.crear(luis)
    with pytest.raises(ErrorDeAcceso):
        r.restaurar(luis, hecho.archivo)


def test_restaurar_con_el_servicio_que_no_se_detiene(gente, servicio_db):
    r, ana, _luis = gente
    poner, leer = servicio_db
    hecho = r.crear(ana)
    _sql("UPDATE resp_padre_tst SET nombre = 'actual'")
    poner(estado="RECIBIENDO")                       # un teléfono sincroniza y el servicio no llega a PAUSADO
    with pytest.raises(ErrorDeAcceso, match="El servicio Bluetooth no se detuvo; inténtalo de nuevo"):
        r.restaurar(ana, hecho.archivo, esperar_s=0.5)
    assert _sql("SELECT nombre FROM resp_padre_tst") == [("actual",)]
    assert leer("pausado") == "N"                    # se deja como estaba
    assert [x.origen for x in r.listar(ana)] == ["manual"]


def test_restaurar_bien(gente, servicio_db, auditoria_db):
    r, ana, _luis = gente
    poner, leer = servicio_db
    hecho = r.crear(ana)
    _sql("UPDATE resp_padre_tst SET nombre = 'actual'")
    poner(estado="PAUSADO", pausado="S")
    r.restaurar(ana, hecho.archivo)
    assert _sql("SELECT nombre FROM resp_padre_tst") == [("original",)]
    assert sorted(x.origen for x in r.listar(ana)) == ["manual", "previo"]
    assert _habilitados() == {"JOB_RESP_A_TST": "TRUE", "JOB_RESP_B_TST": "TRUE"}
    assert leer("pausado") == "S"
    assert ("respaldos", "Restauró respaldo", hecho.archivo) in [
        (e.modulo, e.accion, e.detalle) for e in auditoria_db.listar(ana)]


def test_restaurar_sin_servicio_corriendo_no_espera(gente, servicio_db):
    r, ana, _luis = gente
    hecho = r.crear(ana)                             # sin fila: el servicio nunca arrancó (DETENIDO)
    r.restaurar(ana, hecho.archivo, esperar_s=0.5)
    assert _sql("SELECT nombre FROM resp_padre_tst") == [("original",)]


def test_restaurar_con_error_deja_los_jobs_habilitados(gente, servicio_db, monkeypatch):
    from btsync import respaldo

    r, ana, _luis = gente
    poner, _ = servicio_db
    hecho = r.crear(ana)
    poner(estado="PAUSADO", pausado="S")
    original = respaldo._insertar

    def falla(*a, **k):
        raise RuntimeError("ORA-00001: falló a mitad")

    monkeypatch.setattr(respaldo, "_insertar", falla)
    with pytest.raises(RuntimeError):
        r.restaurar(ana, hecho.archivo)
    monkeypatch.setattr(respaldo, "_insertar", original)
    assert _habilitados() == {"JOB_RESP_A_TST": "TRUE", "JOB_RESP_B_TST": "TRUE"}
    assert _sql("SELECT nombre FROM resp_padre_tst") == [("original",)]


def test_guardar_automatico(gente, auditoria_db):
    r, ana, luis = gente
    with pytest.raises(ErrorDeAcceso, match="valor válido"):
        r.guardar_automatico(ana, True, "25:00", 7)
    r.guardar_automatico(ana, False, "22:30", 5)
    assert r.automatico() == (False, "22:30", 5)
    detalles = sorted(e.detalle for e in auditoria_db.listar(ana) if e.accion == "Cambió respaldo automático")
    assert detalles == ["respaldos.auto: S → N", "respaldos.conservar: 7 → 5", "respaldos.hora: 23:00 → 22:30"]
    with pytest.raises(ErrorDeAcceso):
        r.guardar_automatico(luis, True, "23:00", 7)


@pytest.mark.parametrize("estado, hace", [("DETENIDO", 60), ("PAUSADO", 0)])
def test_restaurar_siempre_deja_la_pausa_escrita(gente, servicio_db, estado, hace):
    """Un servicio que parece detenido (latido viejo) o una fila PAUSADO vieja tras «Reanudar» no basta: si el
    servicio vuelve, debe encontrar la pausa."""
    r, ana, _luis = gente
    poner, leer = servicio_db
    hecho = r.crear(ana)
    poner(hace_s=hace, estado=estado, pausado="N")
    r.restaurar(ana, hecho.archivo, esperar_s=0.5)
    assert leer("pausado") == "S"
