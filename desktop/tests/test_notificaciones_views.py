"""Pantalla «Notificaciones» y la campana del encabezado."""

from app import db as dbq
from app import notificaciones
from app.auth import INVENTARIO, PREGUNTAS
from app.main import build_window
from app.views.notificaciones import NotificacionesView
from btsync import notificaciones as bn
import pytest
from fakes import FakeRemoto

CLAVE = "conteo2026"


def esperar(qtbot, condicion):
    qtbot.waitUntil(condicion, timeout=15000)


def _crear(texto, seccion="Inventario", rol="ADMIN", tipo="PRUEBA", clave=None):
    with dbq._conexion() as conn:
        bn.crear(conn.cursor(), tipo, texto, seccion, rol=rol, clave=clave)
        conn.commit()


def _admin(cuentas):
    return cuentas.registrar("ana.gomez", "Ana Gómez", CLAVE, CLAVE, correo="ana@example.com",
                             pregunta=PREGUNTAS[0], respuesta="firulais")


def _vista(qtbot, sesion):
    v = NotificacionesView()
    qtbot.addWidget(v)
    v.set_sesion(sesion)
    return v


def test_lista_con_punto_en_las_sin_leer_y_filtro(qtbot, cuentas):
    ana = _admin(cuentas)
    _crear("Aviso viejo")
    _crear("Aviso nuevo", seccion="")
    v = _vista(qtbot, ana)
    esperar(qtbot, lambda: len(v.filas()) == 2)
    assert [f[0] for f in v.filas()] == ["●", "●"]
    assert v.filas()[0][2] == "Aviso nuevo"
    notificaciones.marcar_leida(ana, notificaciones.listar(ana)[0].id)
    v.refresh()
    esperar(qtbot, lambda: [f[0] for f in v.filas()] == ["", "●"])
    v.combo_filtro.setCurrentText("Sin leer")
    assert [f[2] for f in v.filas()] == ["Aviso viejo"]


def test_ver_lleva_a_la_seccion_y_la_marca_leida(qtbot, cuentas):
    ana = _admin(cuentas)
    _crear("Uno sin sección", seccion="")
    _crear("Dos con sección", seccion="Inventario")
    v = _vista(qtbot, ana)
    esperar(qtbot, lambda: len(v.filas()) == 2)
    destinos = []
    v.ir_a.connect(destinos.append)
    assert not v.boton_ver(1)
    v.boton_ver(0).click()
    assert destinos == ["Inventario"]
    esperar(qtbot, lambda: notificaciones.sin_leer(ana) == 1)


def test_marcar_todas(qtbot, cuentas):
    ana = _admin(cuentas)
    _crear("Uno")
    _crear("Dos")
    v = _vista(qtbot, ana)
    esperar(qtbot, lambda: len(v.filas()) == 2)
    v.btn_todas.click()
    esperar(qtbot, lambda: notificaciones.sin_leer(ana) == 0)


def test_la_campana_cuenta_las_sin_leer_y_abre_la_pantalla(qtbot, cuentas):
    ana = _admin(cuentas)
    _crear("Nueva solicitud de cuenta: Pedro Ruiz", seccion="Solicitudes")
    ventana = build_window(FakeRemoto(), auto_refresh_ms=0, sesion=ana)
    qtbot.addWidget(ventana)
    assert not ventana.btn_avisos.isHidden() and "Notificaciones" not in ventana.secciones()
    esperar(qtbot, lambda: ventana.btn_avisos.toolTip() == "1 notificación sin leer")
    ventana.btn_avisos.click()                      # la campana abre el panel flotante
    assert ventana.bandeja.isVisible()
    esperar(qtbot, lambda: any("Pedro Ruiz" in f for f in ventana.bandeja.filas()))
    ventana.bandeja.btn_ver_todo.click()            # «Ver todo» abre la vista extendida, también flotante
    assert not ventana.bandeja.isVisible() and not ventana.hoja_notificaciones.isHidden()
    ventana.hoja_notificaciones.cerrar()
    assert ventana.hoja_notificaciones.isHidden()
    _sin_consultas_pendientes(qtbot, ventana)


def test_inventario_tambien_tiene_notificaciones(qtbot, cuentas):
    ana = _admin(cuentas)
    cuentas.registrar("luis", "Luis Ortiz", CLAVE, CLAVE, correo="luis@example.com")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    ventana = build_window(FakeRemoto(), auto_refresh_ms=0, sesion=cuentas.iniciar_sesion("luis", CLAVE))
    qtbot.addWidget(ventana)
    assert "Notificaciones" not in ventana.secciones() and not ventana.btn_avisos.isHidden()
    _sin_consultas_pendientes(qtbot, ventana)


def _sin_consultas_pendientes(qtbot, ventana):
    vistas = [v for _t, v, _b, _m, _r in ventana._secciones]
    esperar(qtbot, lambda: all(getattr(v, "_runner", None) is None or v._runner.pendientes == 0 for v in vistas)
            and ventana._runner.pendientes == 0)
