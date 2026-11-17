"""Motion design de Sincronización: el movimiento nace de eventos reales, respeta el movimiento reducido, no deja
animaciones vivas al salir de la pantalla y nunca cambia el dato ni el layout."""

from datetime import datetime

import pytest
from PyQt6.QtCore import QEvent, QPointF, QVariantAnimation
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtWidgets import QApplication, QWidget

from app import db, tema
from app.auth import ADMIN, PREGUNTAS
from app.models import ErrorFila
from app.views import motion, sync_ui, widgets
from app.views.sync import SyncView
from fakes import FakeRemoto

CLAVE = "conteo2026"


@pytest.fixture(autouse=True)
def con_animaciones(monkeypatch):
    """Estas pruebas necesitan las animaciones reales; el movimiento reducido se restablece al terminar."""
    monkeypatch.setattr(widgets, "ANIMAR", True)
    motion.fijar_reducido(False)
    yield
    motion.fijar_reducido(None)


@pytest.fixture
def admin(cuentas):
    return cuentas.registrar("ana.gomez", "Ana Gómez", CLAVE, CLAVE, correo="ana@example.com",
                             pregunta=PREGUNTAS[0], respuesta="firulais")


def _vista(qtbot, sesion, **status):
    r = FakeRemoto(**status)
    v = SyncView(r)
    qtbot.addWidget(v)
    v.resize(1300, 1700)
    v.show()
    v._sesion = sesion      # sin consultar Oracle: las pruebas de movimiento no dependen de los datos
    return v, r


def _enlaces_activos():
    nodos = [{"tono": "ok", "estado": "x", "detalle": ""} for _ in range(4)]
    return nodos, ["activo", "activo", "activo"], ["", "", ""]


# ------------------------------------------------------------------ sistema compartido
def test_interpolador_no_recrea_la_animacion_si_el_destino_no_cambia(qtbot):
    w = QWidget()
    qtbot.addWidget(w)
    pasos = []
    m = sync_ui.Interpolador(w, lambda: pasos.append(1), 200)
    m.ir_a(x=1.0)
    primera = m._anim
    m.ir_a(x=1.0)
    assert m._anim is primera
    qtbot.waitUntil(lambda: abs(m("x") - 1.0) < 1e-6, timeout=2000)


def test_interpolador_parte_del_valor_actual_al_cambiar_de_destino(qtbot):
    w = QWidget()
    qtbot.addWidget(w)
    m = sync_ui.Interpolador(w, lambda: None, 400)
    m.fijar(x=0.0)
    m.ir_a(x=1.0)
    qtbot.wait(120)
    mitad = m("x")
    assert 0.0 < mitad < 1.0
    m.ir_a(x=0.0)           # vuelve atrás sin saltar
    assert abs(m("x") - mitad) < 0.2
    qtbot.waitUntil(lambda: m("x") < 0.01, timeout=2000)


def test_duraciones_respetan_la_naturaleza_de_cada_interaccion():
    d = motion.Dur
    assert d.HOVER < d.ENTRADA < d.PANTALLA < d.GRAFICA
    assert 120 <= d.HOVER <= 180 and 250 <= d.ENTRADA <= 450 and 400 <= d.GRAFICA <= 700


def test_movimiento_reducido_acorta_y_apaga_lo_decorativo():
    assert motion.decorativo() and motion.dur(500) == int(500 * widgets.FACTOR_TIEMPO)
    motion.fijar_reducido(True)
    assert not motion.decorativo()
    assert motion.dur(500) <= 160 and motion.desp(10) < 10


# ------------------------------------------------------------------ contadores
def test_odometro_duracion_segun_el_cambio_y_sin_reiniciar_si_es_igual(qtbot):
    assert sync_ui.Odometro.duracion_para(1) < sync_ui.Odometro.duracion_para(50) < sync_ui.Odometro.duracion_para(5000)
    assert sync_ui.Odometro.duracion_para(10 ** 9) <= 780
    o = sync_ui.Odometro(0)
    qtbot.addWidget(o)
    o.show()
    o.set_valor(7)
    anim = o._anim
    assert o.valor() == 7 and o.texto() == "7"
    o.set_valor(7)                       # mismo valor: no reinicia
    assert o._anim is anim
    qtbot.waitUntil(lambda: o._p >= 1.0, timeout=3000)
    assert o._prev == o._txt             # sin columnas fantasma al terminar


def test_odometro_no_deja_columnas_fantasma_al_bajar_de_miles_a_una_cifra(qtbot):
    o = sync_ui.Odometro(1280)
    qtbot.addWidget(o)
    o.show()
    o.set_valor(6)
    qtbot.waitUntil(lambda: o._p >= 1.0, timeout=3000)
    assert o.texto() == "6" and o._prev == "6"


# ------------------------------------------------------------------ flujo: tráfico real, nodos y ciclos
def test_sin_eventos_no_hay_paquetes_ni_reloj(qtbot):
    f = sync_ui.FlujoDatos()
    qtbot.addWidget(f)
    f.resize(900, 220)
    f.show()
    f.set_modelo([{"tono": "pausa", "estado": "", "detalle": ""}] * 4, ["off", "off", "off"], ["", "", ""])
    assert f.paquetes_vivos() == 0 and not f.reloj_activo()   # no se genera tráfico ficticio


def test_las_lecturas_reales_crean_paquetes_y_el_reloj_se_apaga_solo(qtbot):
    f = sync_ui.FlujoDatos()
    qtbot.addWidget(f)
    f.resize(900, 220)
    f.show()
    f.set_modelo([{"tono": "pausa", "estado": "", "detalle": ""}] * 4, ["off", "off", "off"], ["", "", ""])
    f.emitir_lecturas(3)
    assert f.paquetes_vivos() == 3 and f.reloj_activo()
    qtbot.waitUntil(lambda: f.paquetes_vivos() == 0 and not f.reloj_activo(), timeout=5000)


def test_cantidad_de_paquetes_acotada(qtbot):
    f = sync_ui.FlujoDatos()
    qtbot.addWidget(f)
    f.resize(900, 220)
    f.show()
    f.set_modelo(*_enlaces_activos())
    f.emitir_lecturas(500)
    f.confirmar_escritura(500)
    assert f.paquetes_vivos() <= 8 + 5     # tope por evento: no se acumula con una ráfaga grande
    qtbot.wait(300)
    assert len(f._paquetes) <= f.MAX_PAQUETES


def test_el_reloj_del_flujo_y_los_ciclos_se_detienen_al_salir_de_la_pantalla(qtbot):
    v = QWidget()
    qtbot.addWidget(v)
    f = sync_ui.FlujoDatos(v)
    ic = sync_ui.IconoBluetooth(v)
    et = sync_ui.Etapas(parent=v)
    v.resize(900, 600)
    v.show()
    f.set_modelo(*_enlaces_activos())
    ic.set_modo("activo")
    et.set_estado(2, 2)
    assert f.reloj_activo()
    qtbot.waitUntil(lambda: ic._ciclo.state() == QVariantAnimation.State.Running, timeout=2000)   # la luz sube y arrancan
    qtbot.waitUntil(lambda: ic._ciclo_orbita.state() == QVariantAnimation.State.Running, timeout=2000)
    assert et._halo.state() == QVariantAnimation.State.Running
    v.hide()                                  # se abandona la pantalla
    assert not f.reloj_activo()
    assert ic._ciclo.state() == QVariantAnimation.State.Stopped
    assert ic._ciclo_orbita.state() == QVariantAnimation.State.Stopped
    assert et._halo.state() == QVariantAnimation.State.Stopped


def test_movimiento_reducido_sin_paquetes_ondas_ni_particulas(qtbot):
    motion.fijar_reducido(True)
    f = sync_ui.FlujoDatos()
    qtbot.addWidget(f)
    f.resize(900, 220)
    f.show()
    f.set_modelo(*_enlaces_activos())
    f.emitir_lecturas(4)
    assert f.paquetes_vivos() == 0               # no hay paquetes; el estado del enlace sí se ve
    assert f.enlaces() == ["activo", "activo", "activo"]
    ic = sync_ui.IconoBluetooth()
    qtbot.addWidget(ic)
    ic.show()
    ic.set_modo("activo")
    assert ic._ciclo.state() != QVariantAnimation.State.Running      # sin ondas ni respiración continuas
    assert ic._ciclo_orbita.state() != QVariantAnimation.State.Running
    ic.set_modo("buscando")
    assert ic._ciclo.state() == QVariantAnimation.State.Running      # el arco de «conectando» es funcional: se conserva


def test_icono_apaga_el_halo_progresivamente_al_pausar(qtbot):
    ic = sync_ui.IconoBluetooth()
    qtbot.addWidget(ic)
    ic.show()
    ic.set_modo("activo")
    qtbot.waitUntil(lambda: ic.luz() > 0.95, timeout=3000)
    ic.set_modo("pausado")
    qtbot.wait(120)
    assert 0.0 < ic.luz() < 1.0                    # no se apaga de golpe
    qtbot.waitUntil(lambda: ic.luz() < 0.02, timeout=3000)
    qtbot.waitUntil(lambda: ic._ciclo.state() != QVariantAnimation.State.Running, timeout=2000)


def test_error_tine_de_rojo_el_tramo_y_se_recupera(qtbot):
    f = sync_ui.FlujoDatos()
    qtbot.addWidget(f)
    f.resize(900, 220)
    f.show()
    nodos, enlaces, etiquetas = _enlaces_activos()
    f.set_modelo(nodos, enlaces, etiquetas, 1.0, 3)       # error en Oracle → tramo PC → Oracle
    qtbot.waitUntil(lambda: f._m("r2") > 0.95 and f._m("e3") > 0.95, timeout=3000)
    assert f._m("r0") < 0.01 and f._m("r1") < 0.01
    f.set_modelo(nodos, enlaces, etiquetas, 1.0, None)    # recuperado
    qtbot.waitUntil(lambda: f._m("r2") < 0.02 and f._m("e3") < 0.02, timeout=3000)


# ------------------------------------------------------------------ botones
def test_boton_cargando_no_bloquea_el_clic_y_muestra_el_resultado(qtbot):
    b = sync_ui.BotonPremium("Reprocesar", icono=None)
    qtbot.addWidget(b)
    b.show()
    clics = []
    b.clicked.connect(lambda: clics.append(1))
    b.iniciar()
    assert b.girando() and b.isEnabled()
    qtbot.mouseClick(b, widgets.Qt.MouseButton.LeftButton)
    assert clics == [1]
    b.detener("exito")
    assert b.estado() == "exito"
    qtbot.waitUntil(lambda: b.estado() == "normal", timeout=3000)
    assert b.icon().isNull()                       # vuelve al estado original, sin spinner pegado


def test_boton_actualizar_gira_y_vuelve_a_su_posicion(qtbot):
    b = sync_ui.BotonActualizar("Actualizar")
    qtbot.addWidget(b)
    b.show()
    b.iniciar()
    assert b.girando() and not b.isEnabled()
    qtbot.wait(150)
    assert b._angulo != 0.0
    b.detener()
    assert b.isEnabled() and not b.girando()
    qtbot.waitUntil(lambda: b._angulo == 0.0, timeout=3000)


def test_boton_cambia_el_texto_con_cross_fade_pero_el_dato_es_inmediato(qtbot):
    b = sync_ui.BotonPremium("Pausar servicio", icono="pausaplay")
    qtbot.addWidget(b)
    b.show()
    b.set_texto("Reanudar servicio")
    assert b.text() == "Reanudar servicio"
    b.set_reproduccion(True)
    qtbot.waitUntil(lambda: b._m_icono("pausado") > 0.99, timeout=3000)


# ------------------------------------------------------------------ la pantalla
def test_la_entrada_cinematica_ocurre_al_entrar_no_en_cada_refresco(qtbot, admin, monkeypatch):
    llamadas = []
    original = motion.entrar
    monkeypatch.setattr(motion, "entrar", lambda *a, **k: (llamadas.append(a[0]), original(*a, **k))[1])
    v, r = _vista(qtbot, admin)
    n = len(llamadas)
    assert n >= 12                          # cabecera, indicadores, panel, contadores, flujo, estadísticas, errores
    r.poner(estado="RECIBIENDO", recibidos=3)      # un refresco de datos no repite la entrada
    r.poner(estado="RECIBIENDO", recibidos=5)
    assert len(llamadas) == n
    v.hide()
    v.show()                                 # el usuario vuelve a la pantalla: la secuencia se repite
    assert len(llamadas) == 2 * n


def test_entrada_no_deja_efectos_encendidos_ni_widgets_ocultos_animandose(qtbot, admin):
    v, _ = _vista(qtbot, admin)
    v.hide()                                 # se sale antes de que terminen las entradas con retardo
    qtbot.wait(2600)
    for w in (v.hero, v.tarjeta_flujo, v.tarjeta_actividad, v.tarjeta_errores, *v._cajas_contadores, *v._cajas_stats,
              v.pill_oracle, v.btn_actualizar):
        assert w.graphicsEffect() is None    # nada queda a medias: sin efectos gráficos residuales


def test_lecturas_reales_del_servicio_mueven_el_flujo(qtbot, admin):
    v, r = _vista(qtbot, admin, estado="RECIBIENDO", recibidos=0)
    qtbot.wait(50)
    assert v.flujo.paquetes_vivos() == 0                    # sin lecturas nuevas no hay tráfico
    r.poner(estado="RECIBIENDO", recibidos=4)               # llegaron 4 lecturas
    assert v.flujo.paquetes_vivos() >= 4
    assert v.flujo._pulsos[0] > 0.9                         # el nodo Android pulsa al enviar


def test_reanudar_pasa_por_conectando_y_termina_con_exito(qtbot, admin):
    v, r = _vista(qtbot, admin, estado="PAUSADO")
    assert v.icono.modo() == "pausado"
    v.btn_pausar.click()                                     # FakeRemoto reanuda al instante
    assert v.icono.modo() == "buscando" and v.btn_pausar.text() == "Pausar servicio"
    assert v.btn_pausar.estado() == "exito"                  # el resultado real cierra la carga
    r.poner(estado="CONECTADO")
    assert v.icono.modo() == "activo"
    qtbot.waitUntil(lambda: v.icono.luz() > 0.9, timeout=3000)   # la luz activa llega progresivamente


def test_reanudar_fallido_revierte_lo_visual(qtbot, admin, monkeypatch):
    v, r = _vista(qtbot, admin, estado="PAUSADO")
    monkeypatch.setattr(r, "reanudar", lambda s: r.fallo.emit("No hay Bluetooth"))
    v.btn_pausar.click()
    assert v.icono.modo() == "pausado"                       # se revierte el icono
    assert v.btn_pausar.estado() == "error" and not v.btn_pausar.girando()
    assert v.btn_pausar.text() == "Reanudar servicio"
    qtbot.waitUntil(lambda: v.btn_pausar.estado() == "normal", timeout=3000)


def test_fila_resuelta_pasa_a_exito_y_las_que_siguen_se_resaltan(qtbot, admin):
    v, _ = _vista(qtbot, admin)
    ahora = datetime.now()
    uno = ErrorFila(1, "tel-1", 1, "ZZ1", "1", "SKU_DESCONOCIDO", ahora)
    dos = ErrorFila(2, "tel-1", 2, "ZZ2", "1", "CANTIDAD_INVALIDA", ahora)
    v._cargado = True
    v._aplicar_errores([uno, dos])
    hecho = []
    v.tabla_errores.desvanecer_filas([0], lambda: (hecho.append(1), v._aplicar_errores([dos])), exito=True)
    qtbot.waitUntil(lambda: v.tabla_errores.exito(0) > 0.9, timeout=3000)   # verde + check antes de irse
    qtbot.waitUntil(lambda: bool(hecho), timeout=4000)
    assert len(v.errores()) == 1 and v.tabla_errores.exito(0) == 0.0
    v.tabla_errores.resaltar_filas([0])
    qtbot.waitUntil(lambda: v.tabla_errores.destello(0) > 0.3, timeout=2000)
    qtbot.waitUntil(lambda: v.tabla_errores.destello(0) == 0.0, timeout=3000)


def test_solo_las_filas_nuevas_entran_con_animacion(qtbot, admin):
    v, _ = _vista(qtbot, admin)
    ahora = datetime.now()
    uno = ErrorFila(1, "tel-1", 1, "ZZ1", "1", "SKU_DESCONOCIDO", ahora)
    dos = ErrorFila(2, "tel-1", 2, "ZZ2", "1", "CANTIDAD_INVALIDA", ahora)
    v._cargado = True
    v._aplicar_errores([uno])
    assert v.tabla_errores.entrada(0) < 1.0                  # la primera fila entra
    qtbot.waitUntil(lambda: v.tabla_errores.entrada(0) == 1.0, timeout=3000)
    v._aplicar_errores([uno, dos])
    assert v.tabla_errores.entrada(0) == 1.0                 # la ya vista no se anima de nuevo
    assert v.tabla_errores.entrada(1) < 1.0                  # la nueva sí


def test_esqueleto_hasta_que_llegan_los_datos(qtbot, admin):
    v, _ = _vista(qtbot, admin)
    assert v.pila.currentWidget() is v.esqueleto
    v._aplicar_errores([])
    assert v.pila.currentWidget() is v.vacio


def test_tarjeta_eleva_en_hover_sin_mover_el_layout_y_suelta_el_efecto(qtbot, admin):
    v, _ = _vista(qtbot, admin)
    qtbot.wait(2600)                                         # termina la entrada cinematica
    caja = v._cajas_contadores[0]
    antes = (caja.geometry(), v._cajas_contadores[1].geometry())
    QApplication.sendEvent(caja, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    qtbot.waitUntil(lambda: isinstance(caja.graphicsEffect(), motion.EfectoMovimiento) and caja.graphicsEffect().sombra() > 0.9,
                    timeout=2000)
    assert (caja.geometry(), v._cajas_contadores[1].geometry()) == antes     # el hover no altera el layout
    QApplication.sendEvent(caja, QEvent(QEvent.Type.Leave))
    qtbot.waitUntil(lambda: caja.graphicsEffect() is None, timeout=2000)     # reposo: ningún efecto encendido


def test_cruzar_texto_deja_el_texto_final(qtbot):
    from PyQt6.QtWidgets import QLabel
    e = QLabel("uno")
    qtbot.addWidget(e)
    e.show()
    motion.cruzar_texto(e, "dos")
    motion.cruzar_texto(e, "tres")                           # un segundo cambio durante el primero no rompe nada
    qtbot.waitUntil(lambda: e.text() == "tres", timeout=2000)
    qtbot.waitUntil(lambda: e.graphicsEffect() is None, timeout=2000)


def test_dos_fundidos_seguidos_sobre_la_misma_etiqueta_no_rompen(qtbot):
    from PyQt6.QtWidgets import QLabel
    e = QLabel("x")
    qtbot.addWidget(e)
    e.show()
    motion.desvanecer(e, 0.2, 1.0, 200)
    motion.desvanecer(e, 0.2, 1.0, 200)                      # solapados: antes borraban el efecto del segundo
    qtbot.wait(450)
    assert e.graphicsEffect() is None


@pytest.mark.parametrize("modo", ["claro", "oscuro"])
def test_la_pantalla_se_dibuja_en_ambos_temas(qtbot, admin, modo):
    tema.aplicar(QApplication.instance(), modo)
    v, r = _vista(qtbot, admin, estado="RECIBIENDO", recibidos=2)
    r.poner(estado="RECIBIENDO", recibidos=6)
    qtbot.wait(900)
    assert not v.grab().isNull()
    tema.aplicar(QApplication.instance(), "oscuro")
