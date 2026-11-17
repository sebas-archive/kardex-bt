"""Motion de las pantallas administrativas (Solicitudes, Empleados, Roles y permisos, Auditoría, Respaldos y Perfil).

Encienden el movimiento real (``widgets.ANIMAR = True``) y comprueban lo que importa de verdad: que el dato mostrado
es el real desde el primer instante (la animación solo lo representa), que cada animación **termina en el estado
final exacto** (sin capas huérfanas, sin efectos puestos, sin opacidades parciales), que es seguro con vistas
destruidas o navegación repetida y que con las animaciones apagadas no se crea nada.
"""

import time
from datetime import datetime, timedelta

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QFrame, QWidget

from app import auditoria, auth
from app.auth import ADMIN, INVENTARIO, Sesion, Solicitud, Usuario
from app.permisos import CONSULTA, MODULOS, NINGUNO
from app.views import motion, motion_global, widgets
from app.views.auditoria import AuditoriaView
from app.views.base import QueryRunner
from app.views.perfil import PerfilView
from app.views.respaldos import RespaldosView
from app.views.roles import RolesView
from app.views.solicitudes import SolicitudesView
from app.views.usuarios import UsuariosView
from btsync.respaldo import Respaldo

ANA = Sesion("ana.gomez", "Ana Gómez", ADMIN, correo="ana@example.com")
LUIS = Sesion("luis", "Luis Ortiz", INVENTARIO, correo="luis@example.com")
AHORA = datetime(2026, 11, 17, 10, 0, 0)


@pytest.fixture
def con_movimiento(monkeypatch):
    monkeypatch.setattr(widgets, "ANIMAR", True)
    motion.fijar_reducido(False)
    yield
    motion.fijar_reducido(None)


def mostrar(qtbot, vista, ancho=1100, alto=760):
    qtbot.addWidget(vista)
    vista.resize(ancho, alto)
    vista.show()
    qtbot.waitExposed(vista)
    return vista


def hay_capa(tabla) -> bool:
    capa = getattr(tabla, "_capa_filas", None)
    return capa is not None and not sip.isdeleted(capa)


def con_efecto(vista: QWidget) -> list[QWidget]:
    return [w for w in vista.findChildren(QWidget) if isinstance(w.graphicsEffect(), motion.EfectoMovimiento)]


def en_reposo(qtbot, vista: QWidget, tablas=()) -> None:
    """Espera a que ninguna entrada ni transición de filas siga en curso y comprueba que no queda nada puesto."""
    qtbot.waitUntil(lambda: not con_efecto(vista) and not any(hay_capa(t) for t in tablas), timeout=6000)
    for w in vista.findChildren(QWidget):
        efecto = w.graphicsEffect()
        assert not isinstance(efecto, motion.EfectoMovimiento), w


def usuario(nombre, estado=auth.PENDIENTE, rol=None, origen="ESCRITORIO", clave=False):
    return Usuario(nombre, nombre.title(), rol, estado, origen=origen, clave_solicitada=clave,
                   registrado=AHORA, correo=f"{nombre}@example.com")


# ----------------------------------------------------------------------------- piezas compartidas
def test_claves_unicas_conserva_orden_y_desambigua():
    assert motion_global.claves_unicas(["a", "b", "a", "a", "c"]) == ["a", "b", "a#2", "a#3", "c"]
    assert motion_global.claves_unicas([]) == []


def test_sin_animaciones_no_se_crea_ningun_efecto_ni_capa(qtbot, monkeypatch):
    monkeypatch.setattr(widgets, "ANIMAR", False)
    v = mostrar(qtbot, SolicitudesView())
    v._sesion = ANA
    v._mostrar(([usuario("ana")], []))
    assert v.filas_cuentas() == [("ana", "Ana", "ana@example.com", "PC", "17/11/2026")]
    v._mostrar(([], []))
    assert v.filas_cuentas() == []
    motion_global.entrada_pagina(v)
    qtbot.wait(50)
    assert not con_efecto(v) and not any(hay_capa(t) for t in v._vivas)


def test_actividad_barre_solo_mientras_el_runner_tiene_trabajo_real(qtbot, con_movimiento):
    padre = mostrar(qtbot, QFrame(), 300, 120)
    runner = QueryRunner(padre)
    actividad = motion_global.Actividad(padre, runner, espera=10)
    runner.run(lambda: time.sleep(0.5), lambda _r: None)
    qtbot.waitUntil(actividad.isVisible, timeout=3000)
    assert actividad.height() == 2 and actividad.y() == padre.height() - 2        # línea de 2 px en el borde inferior
    qtbot.waitUntil(lambda: not actividad.isVisible(), timeout=5000)
    runner.run(lambda: None, lambda _r: None)                                       # consulta instantánea: no parpadea
    qtbot.wait(200)
    assert not actividad.isVisible()


# ----------------------------------------------------------------------------- Solicitudes
def test_solicitudes_aprobar_saca_la_fila_con_transicion_y_el_dato_es_inmediato(qtbot, con_movimiento):
    v = mostrar(qtbot, SolicitudesView())
    v._sesion = ANA
    nuevas = [usuario("ana"), usuario("beto"), usuario("cata")]
    v._mostrar((nuevas, []))
    en_reposo(qtbot, v, v._vivas)
    resuelta = Solicitud("beto", "Beto", auth.ACTIVO, INVENTARIO, None, "ana.gomez", AHORA)
    v._mostrar(([nuevas[0], nuevas[2]], [resuelta]))
    # el dato ya es el real aunque la transición siga en curso…
    assert [f[0] for f in v.filas_cuentas()] == ["ana", "cata"]
    assert [f[0] for f in v.filas_historial()] == ["beto"]
    assert hay_capa(v.tabla_cuentas)                                                # …y la fila saliente se anima
    en_reposo(qtbot, v, v._vivas)
    assert [f[0] for f in v.filas_cuentas()] == ["ana", "cata"]


def test_solicitudes_refrescos_iguales_no_recrean_animaciones(qtbot, con_movimiento):
    v = mostrar(qtbot, SolicitudesView())
    v._sesion = ANA
    datos = ([usuario("ana"), usuario("beto")], [])
    v._mostrar(datos)
    en_reposo(qtbot, v, v._vivas)
    v._mostrar(datos)
    assert not any(hay_capa(t) for t in v._vivas)


def test_solicitudes_entrada_escalonada_termina_en_su_sitio_y_es_repetible(qtbot, con_movimiento):
    v = mostrar(qtbot, SolicitudesView())
    v._sesion = ANA
    v._mostrar(([usuario("ana"), usuario("beto")], []))
    en_reposo(qtbot, v, v._vivas)
    for _ in range(3):                                                              # navegación repetida
        motion_global.entrada_pagina(v)
    qtbot.wait(20)
    assert con_efecto(v)                                                            # arrancan ocultas…
    en_reposo(qtbot, v, v._vivas)                                                   # …y terminan sin efectos
    assert [f[0] for f in v.filas_cuentas()] == ["ana", "beto"]


def test_vista_destruida_a_mitad_de_la_entrada_no_falla(qtbot, con_movimiento):
    v = mostrar(qtbot, SolicitudesView())
    v._sesion = ANA
    v._mostrar(([usuario("ana")], []))
    motion_global.entrada_pagina(v)
    v._mostrar(([], []))
    sip.delete(v)
    qtbot.wait(700)                                                                 # los temporizadores pendientes caen en vacío


# ----------------------------------------------------------------------------- Empleados
def test_empleados_filtrar_conserva_la_identidad_y_anima_solo_lo_que_cambia(qtbot, con_movimiento):
    v = mostrar(qtbot, UsuariosView())
    v._sesion = ANA
    todos = [usuario("ana", auth.ACTIVO, ADMIN), usuario("beto", auth.ACTIVO, INVENTARIO),
             usuario("cata", auth.SUSPENDIDO, INVENTARIO)]
    v._mostrar(todos)
    en_reposo(qtbot, v, [v.tabla])
    v.txt_buscar.setText("cata")
    assert [f[4] for f in v.filas()] == ["cata"]                                    # el resultado es inmediato
    assert hay_capa(v.tabla)
    en_reposo(qtbot, v, [v.tabla])
    v.txt_buscar.setText("")
    assert [f[4] for f in v.filas()] == ["ana", "beto", "cata"]
    en_reposo(qtbot, v, [v.tabla])


def test_empleados_suspender_cambia_la_huella_de_su_fila(qtbot, con_movimiento):
    v = mostrar(qtbot, UsuariosView())
    v._sesion = ANA
    v._mostrar([usuario("ana", auth.ACTIVO, ADMIN), usuario("beto", auth.ACTIVO, INVENTARIO)])
    en_reposo(qtbot, v, [v.tabla])
    antes = list(v._vivas.huellas)
    v._mostrar([usuario("ana", auth.ACTIVO, ADMIN), usuario("beto", auth.SUSPENDIDO, INVENTARIO)])
    assert v._vivas.claves == ["ana", "beto"]                                       # misma identidad de fila
    assert v._vivas.huellas[0] == antes[0] and v._vivas.huellas[1] != antes[1]      # solo la de beto cambió
    assert v.filas()[1][3] == "Suspendida"
    en_reposo(qtbot, v, [v.tabla])


# ----------------------------------------------------------------------------- Roles y permisos
def matriz(nivel=NINGUNO):
    return {(rol, clave): nivel for rol in auth.ROLES for clave, _n in MODULOS}


def test_roles_reutiliza_los_selectores_y_no_re_guarda_lo_que_solo_refleja(qtbot, con_movimiento, monkeypatch):
    v = mostrar(qtbot, RolesView())
    v._sesion = ANA
    guardados = []
    monkeypatch.setattr(v, "_guardar", lambda *a, **k: guardados.append(a))
    v._mostrar(matriz())
    combos = dict(v._combos)
    assert len(combos) == len(MODULOS) * len(auth.ROLES)
    nueva = matriz()
    nueva[(INVENTARIO, "dashboard")] = CONSULTA
    v._mostrar(nueva)
    assert all(v._combos[k] is c for k, c in combos.items())                       # misma identidad: nada se reconstruyó
    assert v.combo(INVENTARIO, "dashboard").currentData() == CONSULTA
    assert guardados == []                                                          # reflejar no es un cambio del usuario


def test_roles_cambiar_un_permiso_responde_al_instante_y_deja_la_celda_limpia(qtbot, con_movimiento, monkeypatch):
    v = mostrar(qtbot, RolesView())
    v._sesion = ANA
    v._mostrar(matriz())
    monkeypatch.setattr(v._runner, "run", lambda *a, **k: None)                    # sin tocar Oracle: solo la respuesta visual
    combo = v.combo(INVENTARIO, "dashboard")
    hijos = len(combo.findChildren(QWidget))
    combo.setCurrentIndex(combo.findData(CONSULTA))
    assert len(combo.findChildren(QWidget)) > hijos                                 # destello inmediato sobre la celda
    qtbot.waitUntil(lambda: len(combo.findChildren(QWidget)) == hijos, timeout=4000)
    assert combo.currentData() == CONSULTA and combo.graphicsEffect() is None


def test_roles_el_administrador_sigue_bloqueado_tras_actualizar(qtbot, con_movimiento):
    v = mostrar(qtbot, RolesView())
    v._sesion = ANA
    v._mostrar(matriz())
    v._mostrar(matriz(CONSULTA))
    assert not any(v.combo(ADMIN, clave).isEnabled() for clave, _n in MODULOS)
    assert v.combo(INVENTARIO, "dashboard").isEnabled()


def test_roles_entrada_termina_sin_efectos(qtbot, con_movimiento):
    v = mostrar(qtbot, RolesView())
    v._sesion = ANA
    v._mostrar(matriz())
    motion_global.entrada_pagina(v)
    en_reposo(qtbot, v)


# ----------------------------------------------------------------------------- Auditoría
def entradas(n):
    return [auditoria.Entrada(i, AHORA - timedelta(minutes=i), "ana" if i % 2 else "beto", "Ana" if i % 2 else "Beto",
                              "usuarios", "Cuenta aprobada", f"detalle {i}") for i in range(n)]


def test_auditoria_filtrar_no_reescribe_filas_y_el_resultado_es_inmediato(qtbot, con_movimiento):
    v = mostrar(qtbot, AuditoriaView())
    v._sesion = ANA
    v._mostrar(entradas(30))
    en_reposo(qtbot, v, [v.tabla])
    assert v.tabla.rowCount() == 30
    v.txt_buscar.setText("detalle 7")
    assert v.tabla.rowCount() == 1 and v.filas()[0][4] == "detalle 7"
    assert hay_capa(v.tabla)
    en_reposo(qtbot, v, [v.tabla])
    v.txt_buscar.setText("")
    assert v.tabla.rowCount() == 30
    assert v.filas()[3][4] == "detalle 3"                                           # el orden y el contenido no se tocan
    en_reposo(qtbot, v, [v.tabla])


def test_auditoria_un_registro_nuevo_entra_y_los_existentes_no_se_mueven(qtbot, con_movimiento):
    v = mostrar(qtbot, AuditoriaView())
    v._sesion = ANA
    v._mostrar(entradas(10))
    en_reposo(qtbot, v, [v.tabla])
    antes = v.filas()
    nuevo = auditoria.Entrada(99, AHORA, "ana", "Ana", "usuarios", "Cuenta aprobada", "recién llegado")
    v._mostrar([nuevo] + entradas(10)[1:])                                          # mismo conjunto salvo el primero
    assert v.filas()[0][4] == "recién llegado" and v.filas()[1:] == antes[1:]
    en_reposo(qtbot, v, [v.tabla])


def test_auditoria_la_entrada_no_cambia_ningun_dato(qtbot, con_movimiento):
    v = mostrar(qtbot, AuditoriaView())
    v._sesion = ANA
    v._mostrar(entradas(12))
    esperado = v.filas()
    motion_global.entrada_pagina(v)
    en_reposo(qtbot, v, [v.tabla])
    assert v.filas() == esperado


# ----------------------------------------------------------------------------- Respaldos
def respaldo(i):
    return Respaldo(f"respaldo_{i}.zip", AHORA - timedelta(days=i), 1024 * (i + 1), 2, "ana", "manual")


def test_respaldos_el_respaldo_nuevo_entra_sin_mover_los_demas(qtbot, con_movimiento):
    v = mostrar(qtbot, RespaldosView())
    v._sesion = ANA
    v._mostrar([respaldo(1), respaldo(2)])
    en_reposo(qtbot, v, [v.tabla])
    v._mostrar([respaldo(0), respaldo(1), respaldo(2)])
    assert [v._lista[i].archivo for i in range(3)] == ["respaldo_0.zip", "respaldo_1.zip", "respaldo_2.zip"]
    assert v.tabla.rowCount() == 3 and hay_capa(v.tabla)
    en_reposo(qtbot, v, [v.tabla])


def test_respaldos_conserva_la_seleccion_y_la_entrada_termina_limpia(qtbot, con_movimiento):
    v = mostrar(qtbot, RespaldosView())
    v._sesion = ANA
    v._mostrar([respaldo(1), respaldo(2)])
    v.tabla.selectRow(1)
    v._mostrar([respaldo(0), respaldo(1), respaldo(2)])
    assert v._elegido() == "respaldo_2.zip" and v.btn_restaurar.isEnabled()
    motion_global.entrada_pagina(v)
    en_reposo(qtbot, v, [v.tabla])


def test_respaldos_no_bloquea_la_interfaz_mientras_trabaja(qtbot, con_movimiento, monkeypatch):
    v = mostrar(qtbot, RespaldosView())
    v._sesion = ANA
    v._ocupado(True)
    assert not v.btn_crear.isEnabled()
    v._ocupado(False)
    assert v.btn_crear.isEnabled()
    assert v._actividad.parentWidget() is v._tarjeta


# ----------------------------------------------------------------------------- Perfil (los dos roles)
@pytest.fixture
def sin_oracle(monkeypatch):
    monkeypatch.setattr(auth, "guardar_preferencias", lambda *a, **k: None)


@pytest.mark.parametrize("sesion", [ANA, LUIS], ids=["administrador", "inventario"])
def test_perfil_entrada_para_ambos_roles_termina_limpia(qtbot, con_movimiento, sin_oracle, sesion):
    v = PerfilView()
    v.set_sesion(sesion)
    mostrar(qtbot, v, 1200, 800)
    esperado = (v.lbl_nombre.text(), v.btn_cambiar.text(), v.lbl_clave_ayuda.text(), v.lbl_rol.text())
    motion_global.entrada_pagina(v)
    qtbot.wait(20)
    assert {v._tarjeta_usuario, v._tarjeta_clave, v._tarjeta_pref} <= set(con_efecto(v))
    en_reposo(qtbot, v)
    assert (v.lbl_nombre.text(), v.btn_cambiar.text(), v.lbl_clave_ayuda.text(), v.lbl_rol.text()) == esperado


def test_perfil_las_diferencias_de_rol_se_conservan(qtbot, con_movimiento, sin_oracle):
    a, b = PerfilView(), PerfilView()
    a.set_sesion(ANA)
    b.set_sesion(LUIS)
    mostrar(qtbot, a)
    mostrar(qtbot, b)
    assert a.btn_cambiar.text() == "Cambiar contraseña"
    assert b.btn_cambiar.text() == "Solicitar cambio de contraseña"
    assert "aprobar el cambio en Solicitudes" in b.lbl_clave_ayuda.text()
    for v in (a, b):                                                                # mismos controles para los dos roles
        assert all(not x.isHidden() for x in (v.btn_foto, v.btn_salir, v.btn_cambiar, v.seg_tema, v.seg_idioma))


def test_perfil_un_cambio_de_contrasena_rechazado_sacude_la_tarjeta_y_termina_en_su_sitio(qtbot, con_movimiento,
                                                                                         sin_oracle):
    v = PerfilView()
    v.set_sesion(LUIS)
    mostrar(qtbot, v, 1200, 800)
    margenes = v._tarjeta_clave.layout().contentsMargins()
    v._clave_fallo("La contraseña actual no coincide.")
    assert v.btn_cambiar.isEnabled()
    qtbot.waitUntil(lambda: v._tarjeta_clave.layout().contentsMargins() == margenes, timeout=4000)


def test_perfil_foto_cruza_el_avatar_y_deja_la_opacidad_plena(qtbot, con_movimiento, sin_oracle, monkeypatch):
    v = PerfilView()
    v.set_sesion(ANA)
    mostrar(qtbot, v, 1200, 800)
    v._cruzar_avatar()
    assert v.lbl_avatar.graphicsEffect() is not None
    qtbot.waitUntil(lambda: v.lbl_avatar.graphicsEffect() is None, timeout=4000)


# ----------------------------------------------------------------------------- tooltips
def test_los_tooltips_nacen_con_un_fundido(qtbot, con_movimiento):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel
    from app.views import vigilante

    class QTipLabel(QLabel):          # el plugin offscreen no muestra tooltips reales: misma clase y tipo de ventana
        pass

    vigilante.instalar()
    punta = QTipLabel("hola")
    punta.setWindowFlags(Qt.WindowType.ToolTip)
    qtbot.addWidget(punta)
    punta.show()
    qtbot.wait(20)
    assert punta.property("aparecido")                                              # el filtro global lo tomó
    qtbot.wait(400)
    assert punta.windowOpacity() in (0.0, 1.0)                                      # offscreen no admite opacidad de ventana
    assert not punta.isHidden()
