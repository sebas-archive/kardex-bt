"""Configuración general: intervalo del lote, tamaño de foto y carpeta de fotos de solo lectura."""

import re

import pytest

from app import db as dbq
from app.auth import INVENTARIO, ErrorDeAcceso

ANA = ("ana.gomez", "Ana Gómez", "ana@example.com")
LUIS = ("luis", "Luis Ortiz", "luis@example.com")
CLAVE = "conteo2026"


def _sql(sql, **binds):
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute(sql, binds)
        filas = cur.fetchall() if cur.description else None
        conn.commit()
        return filas


@pytest.fixture
def gente(cuentas, config_db):
    from app.auth import PREGUNTAS

    ana = cuentas.registrar(ANA[0], ANA[1], CLAVE, CLAVE, correo=ANA[2],
                            pregunta=PREGUNTAS[0], respuesta="firulais")
    cuentas.registrar(LUIS[0], LUIS[1], CLAVE, CLAVE, correo=LUIS[2])
    cuentas.aprobar(ana, "luis", INVENTARIO)
    return config_db, ana, cuentas.iniciar_sesion("luis", CLAVE)


def _job(nombre):
    return _sql("SELECT repeat_interval, job_action FROM user_scheduler_jobs WHERE job_name = :j", j=nombre)[0]


def test_valores_iniciales(gente):
    c, _ana, _luis = gente
    v = c.valores()
    assert v["lote.intervalo_min"] == "1" and v["fotos.max_mb"] == "2"
    assert v["respaldos.hora"] == "23:00" and v["respaldos.conservar"] == "7"


@pytest.mark.parametrize("clave, valor, mensaje", [
    ("lote.intervalo_min", "0", "Procesar lecturas cada: entre 1 y 60 minutos"),
    ("lote.intervalo_min", "61", "Procesar lecturas cada: entre 1 y 60 minutos"),
    ("lote.intervalo_min", "abc", "Procesar lecturas cada: entre 1 y 60 minutos"),
    ("fotos.max_mb", "11", "Tamaño máximo de foto: entre 1 y 10 MB"),
    ("respaldos.conservar", "91", "Conservar respaldos automáticos: entre 1 y 90 respaldos"),
    ("respaldos.auto", "X", "valor válido"),
    ("respaldos.hora", "25:00", "valor válido"),
])
def test_fuera_de_rango_no_guarda(gente, clave, valor, mensaje):
    c, ana, _luis = gente
    with pytest.raises(ErrorDeAcceso, match=re.escape(mensaje) if "valor válido" not in mensaje else "valor válido"):
        c.guardar(ana, {"fotos.max_mb": "3", clave: valor})
    assert c.valores()["fotos.max_mb"] == "2"


def test_guardar_audita_cada_cambio(gente, auditoria_db):
    c, ana, _luis = gente
    c.guardar(ana, {"lote.intervalo_min": "5", "fotos.max_mb": "2"})
    filas = sorted((e.modulo, e.accion, e.detalle) for e in auditoria_db.listar(ana) if e.modulo == "configuracion")
    assert filas == [("configuracion", "Cambió configuración", "lote.intervalo_min: 1 → 5")]
    c.guardar(ana, {"lote.intervalo_min": "5"})          # sin cambios: sin filas nuevas
    assert len([e for e in auditoria_db.listar(ana) if e.modulo == "configuracion"]) == 1


def test_guardar_ajusta_el_job(gente):
    c, ana, _luis = gente
    c.guardar(ana, {"lote.intervalo_min": "5"})
    assert _job("JOB_PROCESAR_TST")[0] == "FREQ=MINUTELY;INTERVAL=5"
    assert _job("JOB_PROCESAR_TST")[1] == "BEGIN NULL; END;"


def test_la_carpeta_de_fotos_no_se_edita(gente):
    c, ana, _luis = gente
    with pytest.raises(ErrorDeAcceso, match="no se edita"):
        c.guardar(ana, {"fotos.dir": "/tmp/otra"})


def test_inventario_no_guarda(gente):
    c, _ana, luis = gente
    with pytest.raises(ErrorDeAcceso):
        c.guardar(luis, {"fotos.max_mb": "3"})
    assert c.valores()["fotos.max_mb"] == "2"
