"""Notificaciones tipo isla dinámica: cola, tipos, transformación, pausa, cierre, temas, idioma y subprocesos."""

import threading

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

from app import i18n, isla, tema
from app.isla import NotificationQueue, NotificationType as T
from app.isla.modelo import Notification


@pytest.fixture
def ventana(qtbot):
    v = QMainWindow()
    centro = QWidget()
    lay = QVBoxLayout(centro)
    etiqueta = QLabel("contenido")
    lay.addWidget(etiqueta)
    v.setCentralWidget(centro)
    v.resize(900, 600)
    v.etiqueta = etiqueta
    qtbot.addWidget(v)
    v.show()
    gestor = isla.instalar(v)
    v.gestor = gestor
    yield v
    i18n.set_idioma("es")


def esperar_ocioso(qtbot, g):
    qtbot.waitUntil(lambda: not g.widget.activa and g.pendientes() == 0, timeout=5000)


# ---------------------------------------------------------------- modelo
def test_duraciones_y_prioridades_por_tipo():
    assert (T.SUCCESS.duracion_ms, T.ERROR.duracion_ms, T.WARNING.duracion_ms, T.INFO.duracion_ms) == (3000, 5000, 4000, 3000)
    assert T.LOADING.duracion_ms is None
    assert Notification(1, T.LOADING, "x", duracion_ms=500).duracion_ms is None   # la carga nunca se cierra sola
    assert T.ERROR.prioridad > T.WARNING.prioridad > T.INFO.prioridad


def test_cola_da_prioridad_a_errores_y_respeta_el_orden():
    c = NotificationQueue()
    for i, tipo in enumerate([T.INFO, T.SUCCESS, T.ERROR, T.WARNING, T.ERROR]):
        c.agregar(Notification(i, tipo, f"n{i}"))
    assert [c.sacar().id for _ in range(5)] == [2, 4, 3, 0, 1]
    assert c.sacar() is None


# ---------------------------------------------------------------- tipos
@pytest.mark.parametrize("tipo, ms", [(T.SUCCESS, 3000), (T.ERROR, 5000), (T.WARNING, 4000), (T.INFO, 3000)])
def test_cada_tipo_se_muestra_y_se_cierra_sola(qtbot, ventana, tipo, ms):
    g = ventana.gestor
    g.notificar(tipo, "Hola")
    assert g.widget.isVisible() and g.widget.texto() == "Hola"
    assert 0 < g.widget.tiempo_restante_ms() <= ms
    g.widget._vida.setInterval(20)   # acelera la espera sin cambiar la lógica
    g.widget._vida.start()
    esperar_ocioso(qtbot, g)
    assert not g.widget.isVisible()


def test_carga_no_se_cierra_sola(qtbot, ventana):
    g = ventana.gestor
    g.notificar(T.LOADING, "Sincronizando inventario…")
    assert g.widget.tiempo_restante_ms() == -1
    QTest.qWait(150)
    assert g.widget.activa


def test_carga_se_transforma_en_exito_sin_nueva_capsula(qtbot, ventana):
    g = ventana.gestor
    id_ = g.notificar(T.LOADING, "Sincronizando inventario…")
    ocultas = []
    g.widget.oculta.connect(ocultas.append)
    g.actualizar(id_, T.SUCCESS, "Sincronización completada")
    assert g.widget.texto() == "Sincronización completada"
    assert g.widget._noti.tipo is T.SUCCESS and g.widget.id_actual == id_
    assert 0 < g.widget.tiempo_restante_ms() <= 3000
    assert ocultas == [] and g.pendientes() == 0


def test_carga_se_transforma_en_error(qtbot, ventana):
    g = ventana.gestor
    id_ = g.notificar(T.LOADING, "Sincronizando inventario…")
    g.actualizar(id_, T.ERROR, "Error al sincronizar", "ORA-12541")
    assert g.widget._noti.tipo is T.ERROR and g.widget._noti.detalle == "ORA-12541"
    assert g.widget.tiempo_restante_ms() > 3000


def test_actualizar_una_carga_que_aun_esta_en_cola_muestra_solo_el_resultado(qtbot, ventana):
    g = ventana.gestor
    g.notificar(T.INFO, "Primera")
    id_ = g.notificar(T.LOADING, "Cargando…")
    g.actualizar(id_, T.SUCCESS, "Listo")
    assert g.textos() == ["Primera", "Listo"]


def test_actualizar_una_carga_cerrada_a_mano_igual_muestra_el_resultado(qtbot, ventana):
    g = ventana.gestor
    id_ = g.notificar(T.LOADING, "Cargando…")
    g.cerrar(id_)
    esperar_ocioso(qtbot, g)
    g.actualizar(id_, T.SUCCESS, "Listo")
    assert g.widget.texto() == "Listo"


# ---------------------------------------------------------------- cola
def test_varias_consecutivas_no_se_superponen_ni_se_pierden(qtbot, ventana):
    g = ventana.gestor
    vistos = []
    g.widget.oculta.connect(lambda _i: vistos.append(1))
    for n in range(4):
        g.notificar(T.INFO, f"Mensaje {n}", duracion_ms=30)
    assert g.widget.texto() == "Mensaje 0" and g.pendientes() == 3
    esperar_ocioso(qtbot, g)
    assert len(vistos) == 4


def test_error_adelanta_a_lo_demas_en_la_cola(qtbot, ventana):
    g = ventana.gestor
    g.notificar(T.INFO, "Uno")
    g.notificar(T.SUCCESS, "Dos")
    g.notificar(T.ERROR, "Fallo")
    assert g.textos() == ["Uno", "Dos", "Fallo"]
    g.widget.ocultar()
    qtbot.waitUntil(lambda: g.widget.texto() == "Fallo", timeout=3000)


def test_error_interrumpe_una_carga_y_la_carga_vuelve(qtbot, ventana):
    g = ventana.gestor
    carga = g.notificar(T.LOADING, "Sincronizando…")
    g.notificar(T.ERROR, "Fallo de conexión", duracion_ms=30)
    qtbot.waitUntil(lambda: g.widget.texto() == "Fallo de conexión", timeout=3000)
    qtbot.waitUntil(lambda: g.widget.texto() == "Sincronizando…", timeout=3000)
    assert g.widget.id_actual == carga


def test_duplicados_consecutivos_se_ignoran(qtbot, ventana):
    g = ventana.gestor
    g.notificar(T.ERROR, "Credenciales incorrectas")
    g.notificar(T.ERROR, "Credenciales incorrectas")
    g.notificar(T.ERROR, "Credenciales incorrectas")
    assert g.pendientes() == 0
    g.notificar(T.INFO, "Otra")
    g.notificar(T.INFO, "Otra")
    assert g.pendientes() == 1


def test_duplicado_de_carga_se_actualiza_a_traves_del_alias(qtbot, ventana):
    g = ventana.gestor
    a = g.notificar(T.LOADING, "Sincronizando…")
    b = g.notificar(T.LOADING, "Sincronizando…")
    g.actualizar(b, T.SUCCESS, "Hecho")
    assert g.widget.id_actual == a and g.widget.texto() == "Hecho"


# ---------------------------------------------------------------- interacción
def test_cierre_manual_con_clic(qtbot, ventana):
    g = ventana.gestor
    g.notificar(T.SUCCESS, "Datos guardados")
    QTest.mouseClick(g.widget, Qt.MouseButton.LeftButton, pos=QPoint(g.widget.width() // 2, g.widget.height() // 2))
    esperar_ocioso(qtbot, g)
    assert not g.widget.isVisible()


def test_cerrar_por_id(qtbot, ventana):
    g = ventana.gestor
    id_ = g.notificar(T.INFO, "Hola")
    g.cerrar(id_)
    esperar_ocioso(qtbot, g)


def test_el_cursor_encima_pausa_el_temporizador(qtbot, ventana):
    g = ventana.gestor
    g.notificar(T.INFO, "Hola", duracion_ms=400)
    w = g.widget
    entrada = QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5))
    QApplication.sendEvent(w, entrada)
    assert w.pausada and w.tiempo_restante_ms() == -1
    QTest.qWait(600)
    assert w.activa                       # sigue ahí: no corrió el tiempo
    from PyQt6.QtCore import QEvent
    QApplication.sendEvent(w, QEvent(QEvent.Type.Leave))
    assert w.tiempo_restante_ms() > 0     # al salir se reanuda
    esperar_ocioso(qtbot, g)


# ---------------------------------------------------------------- layout, temas, idioma, hilos
def test_no_altera_la_distribucion_ni_el_tamano(qtbot, ventana):
    antes = (ventana.size(), ventana.etiqueta.geometry(), ventana.centralWidget().geometry())
    ventana.gestor.notificar(T.ERROR, "Credenciales incorrectas", "Revisa tu usuario y tu contraseña.")
    QTest.qWait(50)
    assert (ventana.size(), ventana.etiqueta.geometry(), ventana.centralWidget().geometry()) == antes
    w = ventana.gestor.widget
    assert w.parentWidget() is ventana and not w.isWindow()
    centro = w.geometry().center().x()
    assert abs(centro - ventana.width() / 2) <= 2
    assert w.geometry().top() >= -w.height() and w.geometry().bottom() < 140


@pytest.mark.parametrize("modo", ["claro", "oscuro"])
def test_se_pinta_en_ambos_temas(qtbot, ventana, modo):
    tema.aplicar(QApplication.instance(), modo)
    try:
        for tipo in T:
            ventana.gestor.notificar(tipo, "Texto de prueba", "detalle")
            imagen = ventana.gestor.widget.grab().toImage()
            assert not imagen.isNull()
            ventana.gestor.widget.cerrar_ya()
            ventana.gestor.limpiar()
    finally:
        tema.aplicar(QApplication.instance(), "sistema")


def test_traduce_al_ingles(qtbot, ventana):
    i18n.set_idioma("en")
    ventana.gestor.notificar(T.SUCCESS, "Sincronización completada")
    assert ventana.gestor.widget.texto() == "Sync completed"
    ventana.gestor.limpiar()
    ventana.gestor.notificar(T.SUCCESS, "Bienvenido, {nombre}", nombre="Ana")
    assert ventana.gestor.widget.texto() == "Welcome, Ana"


def test_api_global_y_desde_otro_hilo(qtbot, ventana):
    ids = []
    hilo = threading.Thread(target=lambda: ids.append(isla.cargando("Sincronizando inventario…")))
    hilo.start()
    hilo.join()
    qtbot.waitUntil(lambda: ventana.gestor.widget.activa, timeout=3000)
    assert ventana.gestor.widget.texto() == "Sincronizando inventario…"
    hilo = threading.Thread(target=lambda: isla.actualizar(ids[0], T.SUCCESS, "Sincronización completada"))
    hilo.start()
    hilo.join()
    qtbot.waitUntil(lambda: ventana.gestor.widget.texto() == "Sincronización completada", timeout=3000)


def test_sin_ventana_no_falla():
    antes = isla._gestor
    isla._gestor = None
    try:
        assert isinstance(isla.exito("x"), int)
        isla.actualizar(isla.cargando("y"), T.ERROR, "z")
    finally:
        isla._gestor = antes


def test_ventana_destruida_no_deja_referencias(qtbot):
    v = QMainWindow()
    qtbot.addWidget(v)
    g = isla.instalar(v)
    g.notificar(T.LOADING, "x")
    v.close()
    v.deleteLater()
    qtbot.waitUntil(lambda: isla.gestor() is None, timeout=3000)
    isla.exito("no debe lanzar")
