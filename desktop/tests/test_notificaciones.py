"""Notificaciones en el escritorio: avisos de cuentas/contraseñas y lectura por persona (no son solicitudes)."""

import pytest

from app import db as dbq
from app import notificaciones
from app.auth import INVENTARIO, PREGUNTAS
from btsync import notificaciones as bn

CLAVE = "conteo2026"


def _sql(sql, **binds):
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute(sql, binds)
        filas = cur.fetchall() if cur.description else None
        conn.commit()
        return filas


def _todas():
    return _sql("SELECT tipo, texto, seccion, rol, usuario FROM notificaciones_tst ORDER BY id")


@pytest.fixture
def gente(cuentas):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", CLAVE, CLAVE, correo="ana@example.com",
                            pregunta=PREGUNTAS[0], respuesta="firulais")
    cuentas.registrar("luis", "Luis Ortiz", CLAVE, CLAVE, correo="luis@example.com")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    return cuentas, ana, cuentas.iniciar_sesion("luis", CLAVE)


def test_cuenta_nueva_notifica_al_administrador(cuentas):
    cuentas.registrar("ana.gomez", "Ana Gómez", CLAVE, CLAVE, correo="ana@example.com",
                      pregunta=PREGUNTAS[0], respuesta="firulais")   # la primera: ADMIN, no es solicitud
    assert _todas() == []
    cuentas.registrar("pedro", "Pedro Ruiz", CLAVE, CLAVE, correo="pedro@example.com")
    assert _todas() == [("SOLICITUD", "Nueva solicitud de cuenta: Pedro Ruiz", "Solicitudes", "ADMIN", None)]


def test_pedido_de_clave_desde_acceso(gente):
    cuentas, _ana, _luis = gente
    _sql("DELETE FROM notificaciones_tst")
    cuentas.recuperar("luis", "nueva2027", "nueva2027")
    assert _todas() == [("SOLICITUD", "Luis Ortiz pidió restablecer su contraseña", "Solicitudes", "ADMIN", None)]


def test_cambio_desde_perfil_queda_pendiente(gente):
    cuentas, _ana, luis = gente
    _sql("DELETE FROM notificaciones_tst")
    cuentas.cambiar_clave("luis", CLAVE, "nueva2027", "nueva2027")
    assert _todas() == [("SOLICITUD", "Luis Ortiz pidió cambiar su contraseña", "Solicitudes", "ADMIN", None)]
    assert _sql("SELECT CASE WHEN clave_pendiente IS NOT NULL THEN 1 ELSE 0 END FROM usuarios_tst WHERE usuario = 'luis'") == [(1,)]


def test_listar_y_marcar_por_persona(gente):
    cuentas, ana, luis = gente
    _sql("DELETE FROM notificaciones_tst")
    with dbq._conexion() as conn:
        bn.crear(conn.cursor(), "INFO", "Aviso para Luis", "Inventario", usuario="luis")
        conn.commit()
    n = notificaciones
    assert n.sin_leer(luis) == 1
    assert [x.texto for x in n.listar(luis)] == ["Aviso para Luis"]
    n.marcar_leida(luis, n.listar(luis)[0].id)
    assert n.sin_leer(luis) == 0 and n.listar(luis)[0].leida
    assert n.sin_leer(ana) == 0


def test_marcar_todas(gente):
    _cuentas, ana, _luis = gente
    _sql("DELETE FROM notificaciones_tst")
    with dbq._conexion() as conn:
        bn.crear(conn.cursor(), "INFO", "Uno", "Notificaciones", rol="ADMIN")
        bn.crear(conn.cursor(), "INFO", "Dos", "Notificaciones", rol="ADMIN")
        conn.commit()
    assert notificaciones.sin_leer(ana) == 2
    notificaciones.marcar_todas(ana)
    assert notificaciones.sin_leer(ana) == 0
