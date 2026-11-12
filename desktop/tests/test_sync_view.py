"""Sincronización (el «disparador») y Monitoreo, con un transporte falso y la base real."""

import threading

import pytest
from PyQt6.QtWidgets import QMessageBox

from app import db as dbq
from app.main import MainWindow, build_window
from app.sync_bridge import SyncBridge
from app.views.monitor import MonitorView
from app.views.sync import SyncView
from btsync.transports.base import BluetoothUnavailable
from conftest import connect, staging
from fakes import FakeStore, FakeTransport, end, hello, rec

C = "T-01"
T0 = 1731170400000


def esperar(qtbot, condicion, timeout=15000):
    qtbot.waitUntil(condicion, timeout=timeout)


@pytest.fixture
def puente():
    transport, store = FakeTransport(), FakeStore()
    bridge = SyncBridge(transport, store, discoverable_s=60)
    yield bridge, transport, store
    bridge.cancel()


@pytest.fixture
def vista(qtbot, puente):
    bridge, transport, store = puente
    view = SyncView(bridge)
    qtbot.addWidget(view)
    return view, bridge, transport, store


def test_start_button_starts_bridge_and_shows_waiting(qtbot, vista):
    view, bridge, transport, _ = vista
    assert view.lbl_estado.text().startswith("Listo para sincronizar") and view.btn_iniciar.isEnabled()
    view.btn_iniciar.click()
    esperar(qtbot, lambda: view.lbl_estado.text().startswith("Esperando al celular"))
    esperar(qtbot, lambda: transport.serving)
    assert (transport.pairing_calls, transport.serve_calls) == (1, 1)
    assert "gestion_inventario" in view.lbl_ayuda.text()
    assert view.btn_iniciar.text() == "Cancelar"
    esperar(qtbot, lambda: view.lbl_restante.text().startswith("Ventana abierta: "))
    assert view.lbl_codigo.isHidden() and view.btn_aceptar.isHidden() and view.btn_rechazar.isHidden()


def test_confirm_state_shows_code_and_buttons(qtbot, vista):
    view, bridge, transport, _ = vista
    view.btn_iniciar.click()
    esperar(qtbot, lambda: transport.serving)
    transport.pair("123456")
    esperar(qtbot, lambda: view.lbl_codigo.text() == "123456")
    assert not view.lbl_codigo.isHidden()
    assert view.lbl_codigo.font().pointSize() >= 28                     # «grande»
    assert not view.btn_aceptar.isHidden() and view.btn_aceptar.isEnabled()
    assert not view.btn_rechazar.isHidden() and view.btn_rechazar.isEnabled()
    assert "Confirma" in view.lbl_estado.text()


def test_accept_button_confirms_true(qtbot, vista):
    view, bridge, transport, _ = vista
    view.btn_iniciar.click()
    esperar(qtbot, lambda: transport.serving)
    hilo, resultado = transport.pair("654321")
    esperar(qtbot, lambda: not view.btn_aceptar.isHidden())
    view.btn_aceptar.click()
    hilo.join(timeout=5)
    assert resultado == {"accepted": True}
    esperar(qtbot, lambda: view.lbl_codigo.isHidden())
    assert view.lbl_estado.text().startswith("Esperando al celular")     # sigue esperando la conexión


def test_reject_button_confirms_false(qtbot, vista):
    view, bridge, transport, _ = vista
    view.btn_iniciar.click()
    esperar(qtbot, lambda: transport.serving)
    hilo, resultado = transport.pair("111222")
    esperar(qtbot, lambda: not view.btn_rechazar.isHidden())
    view.btn_rechazar.click()
    hilo.join(timeout=5)
    assert resultado == {"accepted": False}
    esperar(qtbot, lambda: view.lbl_estado.text().startswith("Listo para sincronizar"))
    assert view.btn_iniciar.isEnabled() and view.btn_iniciar.text() == "Iniciar sincronización"


def test_bluetooth_unavailable_shows_message_not_crash(qtbot):
    transport = FakeTransport(fail_with=BluetoothUnavailable("El Bluetooth está bloqueado. En el host ejecuta: rfkill unblock bluetooth"))
    bridge = SyncBridge(transport, FakeStore())
    view = SyncView(bridge)
    qtbot.addWidget(view)
    try:
        view.btn_iniciar.click()                    # no debe lanzar
        esperar(qtbot, lambda: "Bluetooth no disponible" in view.lbl_estado.text())
        assert "rfkill unblock bluetooth" in view.lbl_aviso.text()
        assert view.btn_iniciar.isEnabled() and view.btn_iniciar.text() == "Iniciar sincronización"
    finally:
        bridge.cancel()


def test_listo_emits_refresh_requested(qtbot, puente):
    bridge, transport, store = puente
    ventana = build_window(bridge, auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    sync = ventana.tabs.widget(0)
    refrescos = []
    ventana.refresh_requested.connect(lambda: refrescos.append(sync.lbl_estado.text()))
    sync.btn_iniciar.click()
    esperar(qtbot, lambda: transport.serving)
    conn = transport.connect()
    conn.feed(hello(), rec(1), rec(2), rec(3), end(3))
    esperar(qtbot, lambda: sync.lbl_estado.text().startswith("Sincronización lista"))
    assert "3 lecturas" in sync.lbl_estado.text()
    esperar(qtbot, lambda: len(refrescos) >= 1)
    assert refrescos[0].startswith("Sincronización lista")        # se pide DESPUÉS de llegar a LISTO
    assert store.batch_calls == ["SYNC"]


def test_monitor_cards_reflect_estado_batch(qtbot, escenario, puente):
    escenario.cargar_lecturas()
    conn = connect()
    try:
        staging(conn, "tst-m1", 1, T0, C, "U1", "ZZ9", 1)       # quedará en ERROR
        dbq.procesar_ahora()
        staging(conn, "tst-m1", 2, T0, C, "U1", "A1", 1)        # se queda PENDIENTE
    finally:
        conn.close()
    bridge, _, _ = puente
    vista = MonitorView(bridge)
    qtbot.addWidget(vista)
    vista.refresh()
    esperar(qtbot, lambda: vista.card_text("errores") == "1")
    assert vista.card_text("pendientes") == "1"
    assert vista.card_text("procesados") == "5"                 # las 5 lecturas del escenario
    assert vista.lbl_ultimo_run.text().startswith("Último batch: ") and "(MANUAL)" in vista.lbl_ultimo_run.text()
    assert vista.tabla_errores.rowCount() == 1
    fila = [vista.tabla_errores.item(0, c).text() for c in range(4)]
    assert fila[1:] == ["tst-m1", "1", "SKU_DESCONOCIDO"]


def test_procesar_ahora_and_reprocesar_run_off_ui_thread(qtbot, puente, monkeypatch):
    bridge, _, _ = puente
    vista = MonitorView(bridge)
    qtbot.addWidget(vista)
    liberar, hilos = threading.Event(), {}

    def lento(nombre):
        def fn(*args):
            hilos[nombre] = threading.current_thread()
            liberar.wait(10)
        return fn

    monkeypatch.setattr(dbq, "procesar_ahora", lento("procesar"))
    monkeypatch.setattr(dbq, "reprocesar_errores", lento("reprocesar"))
    for boton, nombre in ((vista.btn_procesar, "procesar"), (vista.btn_reprocesar, "reprocesar")):
        liberar.clear()
        boton.click()
        esperar(qtbot, lambda: nombre in hilos)
        qtbot.wait(100)                                      # la UI sigue atendiendo eventos mientras corre
        assert not boton.isEnabled() and not vista.btn_procesar.isEnabled() and not vista.btn_reprocesar.isEnabled()
        liberar.set()
        esperar(qtbot, lambda: boton.isEnabled())
        assert hilos[nombre] is not threading.main_thread()


def test_sync_and_monitor_tabs_registered_in_expected_order(qtbot, puente):
    bridge, _, _ = puente
    ventana = build_window(bridge, auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    assert [ventana.tabs.tabText(i) for i in range(ventana.tabs.count())] == [
        "Sincronización", "Conteo", "Conciliación", "Gráficas", "Perfil", "Monitoreo"]


def test_progress_label_counts_received_lines(qtbot, vista):
    view, bridge, transport, _ = vista
    view.btn_iniciar.click()
    esperar(qtbot, lambda: transport.serving)
    conn = transport.connect()
    conn.feed(hello(), rec(1), rec(2), rec(3))
    esperar(qtbot, lambda: view.lbl_recibidos.text() == "Lecturas recibidas: 3")
    assert view.lbl_estado.text().startswith("Recibiendo")
    assert view.progreso.maximum() == 0                         # total desconocido: barra indeterminada
    conn.feed(end(3))
    esperar(qtbot, lambda: view.lbl_estado.text().startswith("Sincronización lista"))
    assert view.lbl_recibidos.text() == "Lecturas recibidas: 3"


def test_closing_the_window_cancels_the_sync(qtbot, puente):
    bridge, transport, _ = puente
    ventana = build_window(bridge, auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    ventana.tabs.widget(0).btn_iniciar.click()
    esperar(qtbot, lambda: transport.serving)
    ventana.close()
    esperar(qtbot, lambda: not transport.serving)
    assert bridge.status()["estado"] == "IDLE"


def test_monitor_shows_bluetooth_service_state(qtbot, puente):
    bridge, transport, _ = puente
    vista = MonitorView(bridge)
    qtbot.addWidget(vista)
    assert vista.lbl_servicio.text() == "Servicio Bluetooth: apagado (sin sincronización abierta)"
    bridge.start()
    esperar(qtbot, lambda: vista.lbl_servicio.text().startswith("Servicio Bluetooth: escuchando"))
