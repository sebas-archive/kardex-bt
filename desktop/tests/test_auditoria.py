"""Auditoría: toda acción que cambia datos y todo inicio de sesión deja una fila con quién, qué y cuándo.

El Administrador la ve; Inventario no (matriz: ``auditoria``). No hay tareas, almacenes, cierres ni ajustes.
"""

import pytest

from app import auditoria, configuracion
from app import db as dbq
from app.auth import ADMIN, INVENTARIO, PREGUNTAS, ErrorDeAcceso

CLAVE = "conteo2026"


def _ultima(auditoria_db, quien):
    return [(e.usuario, e.modulo, e.accion, e.detalle) for e in auditoria_db.listar(quien)][0]


@pytest.fixture
def gente(cuentas, config_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", CLAVE, CLAVE, correo="ana@example.com",
                            pregunta=PREGUNTAS[0], respuesta="firulais")
    cuentas.registrar("luis", "Luis Ortiz", CLAVE, CLAVE, correo="luis@example.com")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    return cuentas, ana, cuentas.iniciar_sesion("luis", CLAVE)


def test_inicio_de_sesion_correcto_y_fallido(gente, auditoria_db):
    cuentas, ana, _luis = gente
    with pytest.raises(ErrorDeAcceso):
        cuentas.iniciar_sesion("luis", "mala-clave")
    with pytest.raises(ErrorDeAcceso):
        cuentas.iniciar_sesion("nadie", "x")
    acciones = [(e.usuario, e.accion, e.detalle) for e in auditoria_db.listar(ana)]
    assert ("nadie", "Inicio de sesión fallido", "usuario inexistente") in acciones
    assert ("luis", "Inicio de sesión fallido", "contraseña incorrecta") in acciones
    assert ("luis", "Inicio de sesión", "") in acciones


def test_cuentas_y_permisos(gente, auditoria_db, permisos_db):
    cuentas, ana, _luis = gente
    cuentas.registrar("marta", "Marta Paz", CLAVE, CLAVE, correo="marta@example.com")
    cuentas.rechazar(ana, "marta", "No trabaja aquí")
    assert _ultima(auditoria_db, ana) == ("ana.gomez", "usuarios", "Rechazó cuenta", "marta — «No trabaja aquí»")
    cuentas.suspender(ana, "luis", "Vacaciones")
    assert _ultima(auditoria_db, ana) == ("ana.gomez", "usuarios", "Suspendió cuenta", "luis — «Vacaciones»")
    cuentas.reactivar(ana, "luis")
    assert _ultima(auditoria_db, ana)[2:] == ("Reactivó cuenta", "luis")
    permisos_db.guardar(ana, INVENTARIO, "sync", "CONSULTA")
    ultima = _ultima(auditoria_db, ana)
    assert (ultima[1], ultima[2]) == ("permisos", "Cambió permiso") and "sync" not in ultima[3]


def test_configuracion_auditada(gente, auditoria_db, config_db):
    _cuentas, ana, _luis = gente
    configuracion.guardar(ana, {"lote.intervalo_min": "5"})
    assert _ultima(auditoria_db, ana) == ("ana.gomez", "configuracion", "Cambió configuración",
                                          "lote.intervalo_min: 1 → 5")


def test_inventario_no_ve_la_auditoria(gente, auditoria_db):
    _cuentas, _ana, luis = gente
    with pytest.raises(ErrorDeAcceso):
        auditoria.listar(luis)


def test_producto_para_el_detalle(gente, escenario):
    _cuentas, _ana, _luis = gente
    with dbq._conexion() as conn:
        assert auditoria.producto(conn.cursor(), "A1") == "Producto A1 (A1)"
        assert auditoria.producto(conn.cursor(), "NO-EXISTE") == "NO-EXISTE"
