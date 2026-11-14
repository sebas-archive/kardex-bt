"""Configuración general (Fase 5): el Administrador cambia los valores que antes estaban fijos."""

import re

import pytest

from app import db as dbq
from app.auth import INVENTARIO, ErrorDeAcceso

ARROZ = "7701234000001"   # costo 2400


def _sql(sql, **binds):
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute(sql, binds)
        filas = cur.fetchall() if cur.description else None
        conn.commit()
        return filas


@pytest.fixture
def gente(cuentas, config_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    return config_db, ana, cuentas.iniciar_sesion("luis", "conteo2026")


def _job(nombre):
    return _sql("SELECT repeat_interval, job_action FROM user_scheduler_jobs WHERE job_name = :j", j=nombre)[0]


def test_valores_iniciales(gente):
    c, _ana, _luis = gente
    assert c.valores()["ajustes.umbral_pct"] == "10" and c.valores()["staging.purga_dias"] == "7"


@pytest.mark.parametrize("clave, valor, mensaje", [
    ("ajustes.umbral_pct", "0", "Cambio de existencia desde: entre 1 y 100 %"),
    ("ajustes.umbral_pct", "101", "Cambio de existencia desde: entre 1 y 100 %"),
    ("ajustes.umbral_valor", "-1", "Diferencia de valor desde: entre 0 y 1.000.000.000 $"),
    ("lote.intervalo_s", "9", "Procesar lecturas cada: entre 10 y 3600 segundos"),
    ("lote.intervalo_s", "abc", "Procesar lecturas cada: entre 10 y 3600 segundos"),
    ("staging.purga_dias", "366", "Conservar lecturas recibidas: entre 1 y 365 días"),
    ("fotos.max_mb", "11", "Tamaño máximo de foto: entre 1 y 10 MB"),
])
def test_fuera_de_rango_no_guarda(gente, clave, valor, mensaje):
    c, ana, _luis = gente
    with pytest.raises(ErrorDeAcceso, match=re.escape(mensaje)):
        c.guardar(ana, {"fotos.max_mb": "3", clave: valor})
    assert c.valores()["fotos.max_mb"] == "2"


def test_guardar_audita_cada_cambio(gente, auditoria_db):
    c, ana, _luis = gente
    c.guardar(ana, {"ajustes.umbral_pct": "20", "fotos.max_mb": "2", "lote.intervalo_s": "30"})
    filas = sorted((e.modulo, e.accion, e.detalle) for e in auditoria_db.listar(ana) if e.modulo == "configuracion")
    assert filas == [("configuracion", "Cambió configuración", "ajustes.umbral_pct: 10 → 20"),
                     ("configuracion", "Cambió configuración", "lote.intervalo_s: 60 → 30")]
    c.guardar(ana, {"ajustes.umbral_pct": "20"})          # sin cambios: sin filas nuevas
    assert len([e for e in auditoria_db.listar(ana) if e.modulo == "configuracion"]) == 2


def test_guardar_ajusta_los_jobs(gente):
    c, ana, _luis = gente
    c.guardar(ana, {"lote.intervalo_s": "30", "staging.purga_dias": "3"})
    assert _job("JOB_PROCESAR_TST")[0] == "FREQ=SECONDLY;INTERVAL=30"
    assert "purgar_transito(3)" in _job("JOB_PURGA_TST")[1]


def test_inventario_no_guarda(gente):
    c, _ana, luis = gente
    with pytest.raises(ErrorDeAcceso):
        c.guardar(luis, {"fotos.max_mb": "3"})
    assert c.valores()["fotos.max_mb"] == "2"


def test_el_umbral_decide_si_un_ajuste_es_critico(gente, movimientos_db):
    c, ana, luis = gente
    _sql("UPDATE existencias_tst SET cantidad = 100 WHERE sku = :s AND codigo_almacen = 'ALM-01'", s=ARROZ)
    assert movimientos_db.solicitar_ajuste(luis, ARROZ, "ALM-01", 85, "Merma") == movimientos_db.PENDIENTE  # 15 %
    _sql(f"DELETE FROM {movimientos_db.TABLA}")
    c.guardar(ana, {"ajustes.umbral_pct": "20"})
    assert movimientos_db.solicitar_ajuste(luis, ARROZ, "ALM-01", 85, "Merma") == movimientos_db.APLICADO
