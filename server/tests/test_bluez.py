"""BluezTransport sin hardware: un bus D-Bus falso hace de bluetoothd.

Lo que hace BlueZ (pedir que se confirme un código, entregar una conexión RFCOMM, autorizar un
servicio, cancelar) se simula llamando, en el bucle del transporte, a los mismos métodos a los
que delegan las interfaces D-Bus exportadas. El camino real por D-Bus se comprueba con el
celular (docs/spikes/bluez.md).
"""

import asyncio
import os
import socket
import threading
from types import SimpleNamespace

import pytest
from dbus_fast import DBusError, MessageType, Variant

from btsync.controller import (
    CONFIRMAR_CODIGO,
    ESPERANDO_EMPAREJAMIENTO,
    IDLE,
    LISTO,
    SyncController,
)
from btsync.protocol import parse
from btsync.transports import bluez
from btsync.transports.base import BluetoothUnavailable
from btsync.transports.bluez import (
    AGENT_PATH,
    PROFILE_PATH,
    RFCOMM_CHANNEL,
    SERVICE_UUID,
    SPP_UUID,
    BluezConnection,
    BluezTransport,
)
from test_controller import FakeStore, end, hello, rec, wait_for

ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
PHONE = "/org/bluez/hci0/dev_DC_D9_00_00_00_24"      # emparejado
STRANGER = "/org/bluez/hci0/dev_11_22_33_44_55_66"   # sin emparejar
HANDS_FREE = "0000111e-0000-1000-8000-00805f9b34fb"
REJECTED = "org.bluez.Error.Rejected"


def _variant(value):
    if isinstance(value, bool):
        return Variant("b", value)
    if isinstance(value, int):
        return Variant("u", value)
    if isinstance(value, list):
        return Variant("as", value)
    return Variant("s", value)


class FakeBus:
    """Hace de bus de sistema con bluetoothd detrás: registra las llamadas y guarda el adaptador."""

    def __init__(self, adapter, devices, fail):
        self.adapter = None if adapter is None else {
            "Powered": True, "PowerState": "on", "Discoverable": False,
            "DiscoverableTimeout": 180, "Pairable": True, "Alias": "PC de prueba",
            **adapter,
        }
        self.devices = devices
        self.fail = fail            # member -> (nombre del error, texto)
        self.calls = []
        self.exported = {}
        self.disconnected = False

    async def call(self, msg):
        msg._marshall(False)  # valida firma y cuerpo como lo haría el bus real
        self.calls.append(SimpleNamespace(
            path=msg.path, interface=msg.interface, member=msg.member, body=msg.body))
        await asyncio.sleep(0)
        if msg.member in self.fail:
            return self._error(*self.fail[msg.member])
        if msg.member == "GetAll":
            iface = msg.body[0]
            props = self.adapter if iface == ADAPTER_IFACE else self.devices.get(msg.path)
            if props is None:
                return self._error("org.freedesktop.DBus.Error.UnknownObject", "no existe")
            return self._ok([{k: _variant(v) for k, v in props.items()}])
        if msg.member == "Set":
            _iface, name, value = msg.body
            self.adapter[name] = value.value
        return self._ok([])

    @staticmethod
    def _ok(body):
        return SimpleNamespace(message_type=MessageType.METHOD_RETURN, body=body, error_name=None)

    @staticmethod
    def _error(name, text):
        return SimpleNamespace(message_type=MessageType.ERROR, body=[text], error_name=name)

    def export(self, path, interface):
        self.exported[path] = interface

    def unexport(self, path, interface=None):
        self.exported.pop(path, None)

    def disconnect(self):
        self.disconnected = True

    def members(self):
        return [c.member for c in self.calls]

    def last(self, member):
        return [c for c in self.calls if c.member == member][-1]


@pytest.fixture
def fake(monkeypatch):
    env = SimpleNamespace(
        bus=None, buses=[], connect_error=None, adapter={}, fail={},
        devices={PHONE: {"Paired": True}, STRANGER: {"Paired": False}},
        transports=[],
    )

    async def connect():
        if env.connect_error is not None:
            raise env.connect_error
        env.bus = FakeBus(env.adapter, env.devices, env.fail)
        env.buses.append(env.bus)
        return env.bus

    def make(**kwargs):
        transport = BluezTransport(**kwargs)
        env.transports.append(transport)
        return transport

    monkeypatch.setattr(bluez, "_connect_bus", connect)
    env.make = make
    yield env
    for transport in env.transports:
        transport.stop()


async def accept_any(code):
    return True


def opened(fake, on_passkey=accept_any, on_connection=lambda conn: None, **kwargs):
    kwargs.setdefault("require_pairing", True)  # el modo por defecto (sin claves) se prueba aparte
    transport = fake.make(**kwargs)
    transport.begin_pairing(on_passkey)
    transport.serve(on_connection)
    return transport


def on_loop(transport, coro):
    """Ejecuta en el bucle del transporte, como lo haría una llamada entrante de BlueZ."""
    return asyncio.run_coroutine_threadsafe(coro, transport._loop)


def phone_socket():
    """(extremo del teléfono, fd que BlueZ entregaría al transporte en NewConnection)."""
    ours, theirs = socket.socketpair()
    fd = os.dup(theirs.fileno())
    theirs.close()
    ours.settimeout(5)
    return ours, fd


# ------------------------------------------------------------- abrir y cerrar
def test_begin_and_serve_register_agent_profile_and_make_visible(fake):
    opened(fake)
    bus = fake.bus
    assert bus.last("RegisterAgent").body == [AGENT_PATH, "DisplayYesNo"]
    assert bus.last("RequestDefaultAgent").body == [AGENT_PATH]
    assert bus.adapter["Discoverable"] is True and bus.adapter["Pairable"] is True
    assert bus.adapter["DiscoverableTimeout"] == 120
    assert bus.adapter["Alias"] == "gestion_inventario"  # el nombre que ve el teléfono
    # El nombre ya está puesto cuando el PC se hace visible.
    sets = [c.body[1] for c in bus.calls if c.member == "Set"]
    assert sets.index("Alias") < sets.index("Discoverable")
    path, uuid, options = bus.last("RegisterProfile").body
    assert (path, uuid) == (PROFILE_PATH, SERVICE_UUID)
    assert {k: v.value for k, v in options.items()} == {
        "Name": "InventarioBT", "Role": "server",
        "RequireAuthentication": True, "RequireAuthorization": True,  # BlueZ ya lo exigía por defecto
        "Channel": RFCOMM_CHANNEL,
    }
    assert options["Channel"].signature == "q" and RFCOMM_CHANNEL == 22
    assert set(bus.exported) == {AGENT_PATH, PROFILE_PATH}
    # El agente existe antes de que el PC sea visible.
    members = bus.members()
    assert members.index("RegisterAgent") < len(members) - 1 - members[::-1].index("Set")


def test_spp_uuid_registers_without_channel(fake):
    opened(fake, service_uuid=SPP_UUID.upper())
    _path, uuid, options = fake.bus.last("RegisterProfile").body
    assert uuid == SPP_UUID
    assert "Channel" not in options  # BlueZ ya conoce el canal del perfil serie estándar


def test_stop_restores_adapter_unregisters_and_can_reopen(fake):
    fake.adapter = {"DiscoverableTimeout": 180, "Pairable": False}
    transport = opened(fake)
    first = fake.bus
    transport.stop()
    assert first.members()[-6:] == ["UnregisterProfile", "Set", "Set", "Set", "Set", "UnregisterAgent"]
    assert (first.adapter["Discoverable"], first.adapter["DiscoverableTimeout"], first.adapter["Pairable"]) == (
        False, 180, False)
    assert first.adapter["Alias"] == "PC de prueba"  # el PC recupera su nombre
    restored = [c.body[1] for c in first.calls if c.member == "Set"][-4:]
    assert restored.index("Discoverable") < restored.index("Alias")  # primero deja de ser visible
    assert first.exported == {} and first.disconnected
    transport.stop()  # idempotente
    assert first.members().count("UnregisterAgent") == 1

    transport.begin_pairing(accept_any)
    transport.serve(lambda conn: None)
    assert fake.bus is not first and fake.bus.adapter["Discoverable"] is True


def test_leftover_state_from_a_killed_copy_is_not_taken_as_the_original(fake):
    """Una copia anterior murió sin limpiar (p. ej. `docker stop`): dejó el nombre de la
    aplicación, el PC visible y un tiempo de 600 s. La siguiente copia no debe darlo por
    "original" y devolverlo tal cual."""
    fake.adapter = {"Alias": "gestion_inventario", "Discoverable": True, "DiscoverableTimeout": 600}
    transport = opened(fake)
    transport.stop()
    adapter = fake.bus.adapter
    assert adapter["Discoverable"] is False
    assert adapter["DiscoverableTimeout"] == 180
    assert adapter["Alias"] == ""  # BlueZ: un nombre vacío vuelve al nombre del sistema


def test_bluetooth_name_is_configurable(fake):
    opened(fake, alias="bodega_norte")
    assert fake.bus.adapter["Alias"] == "bodega_norte"


def test_serve_before_begin_pairing_is_a_programming_error(fake):
    with pytest.raises(RuntimeError):
        fake.make().serve(lambda conn: None)


# --------------------------------------------------------- Bluetooth no disponible
def test_powered_off_and_blocked_explains_rfkill(fake):
    fake.adapter = {"Powered": False, "PowerState": "off-blocked"}
    with pytest.raises(BluetoothUnavailable, match="rfkill unblock bluetooth"):
        fake.make().begin_pairing(accept_any)
    assert "RegisterAgent" not in fake.bus.members() and "Set" not in fake.bus.members()
    assert fake.bus.disconnected


def test_powered_off_asks_to_turn_it_on(fake):
    fake.adapter = {"Powered": False, "PowerState": "off"}
    with pytest.raises(BluetoothUnavailable, match="apagado") as exc:
        fake.make().begin_pairing(accept_any)
    assert "rfkill" not in str(exc.value)


def test_missing_adapter(fake):
    fake.adapter = None
    with pytest.raises(BluetoothUnavailable, match=r"No hay adaptador Bluetooth \(hci7\)"):
        fake.make(adapter="hci7").begin_pairing(accept_any)
    assert fake.bus.disconnected


def test_bluetoothd_not_running(fake):
    fake.fail = {"GetAll": ("org.freedesktop.DBus.Error.ServiceUnknown", "The name org.bluez was not provided")}
    with pytest.raises(BluetoothUnavailable, match="bluetoothd"):
        fake.make().begin_pairing(accept_any)


def test_no_system_bus_mentions_the_dbus_mount(fake):
    fake.connect_error = FileNotFoundError(2, "No such file or directory")
    transport = fake.make()
    with pytest.raises(BluetoothUnavailable, match="/var/run/dbus"):
        transport.begin_pairing(accept_any)
    fake.connect_error = None
    transport.begin_pairing(accept_any)  # tras el fallo se puede volver a intentar
    assert fake.bus.adapter["Discoverable"] is True


def test_failure_halfway_rolls_back_what_was_registered(fake):
    fake.fail = {"RequestDefaultAgent": ("org.bluez.Error.DoesNotExist", "Does Not Exist")}
    with pytest.raises(BluetoothUnavailable, match="DoesNotExist"):
        fake.make(require_pairing=True).begin_pairing(accept_any)
    assert fake.bus.members()[-1] == "UnregisterAgent"
    assert fake.bus.adapter["Discoverable"] is False and fake.bus.disconnected


def test_profile_rejected_by_bluez_is_bluetooth_unavailable(fake):
    fake.fail = {"RegisterProfile": ("org.bluez.Error.AlreadyExists", "UUID already registered")}
    transport = fake.make(require_pairing=True)
    transport.begin_pairing(accept_any)
    with pytest.raises(BluetoothUnavailable, match="AlreadyExists"):
        transport.serve(lambda conn: None)
    transport.stop()
    assert fake.bus.members()[-1] == "UnregisterAgent" and "UnregisterProfile" not in fake.bus.members()


# ------------------------------------------------------------------ el agente
def test_passkey_is_shown_with_six_digits_and_acceptance_returns(fake):
    codes = []

    async def on_passkey(code):
        codes.append(code)
        return True

    transport = opened(fake, on_passkey=on_passkey)
    on_loop(transport, transport._request_confirmation(PHONE, 39047)).result(5)  # sin excepción = aceptado
    assert codes == ["039047"]


def test_passkey_rejected_on_the_pc_is_rejected_to_bluez(fake):
    async def on_passkey(code):
        return False

    transport = opened(fake, on_passkey=on_passkey)
    with pytest.raises(DBusError) as exc:
        on_loop(transport, transport._request_confirmation(PHONE, 123456)).result(5)
    assert exc.value.type == REJECTED


def test_bluez_cancel_withdraws_the_pending_code(fake):
    state = {"asked": threading.Event(), "cancelled": False}

    async def on_passkey(code):
        state["asked"].set()
        try:
            await asyncio.Event().wait()  # el usuario nunca responde
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    transport = opened(fake, on_passkey=on_passkey)
    pending = on_loop(transport, transport._request_confirmation(PHONE, 123456))
    assert state["asked"].wait(5)
    transport._loop.call_soon_threadsafe(transport._cancel_confirmations)  # Agent1.Cancel
    with pytest.raises(DBusError) as exc:
        pending.result(5)
    assert exc.value.type == REJECTED and state["cancelled"]


def test_authorize_service_only_for_our_uuid_and_paired_devices(fake):
    transport = opened(fake)

    def authorize(device, uuid):
        return on_loop(transport, transport._authorize_service(device, uuid)).result(5)

    authorize(PHONE, SERVICE_UUID)            # sin excepción = autorizado
    authorize(PHONE, SERVICE_UUID.upper())
    for device, uuid in ((PHONE, HANDS_FREE), (PHONE, SPP_UUID), (STRANGER, SERVICE_UUID)):
        with pytest.raises(DBusError) as exc:
            authorize(device, uuid)
        assert exc.value.type == REJECTED, (device, uuid)


# --------------------------------------------------------------- las conexiones
def test_new_connection_hands_a_line_connection_to_the_handler(fake):
    seen = []

    def handler(conn):
        seen.append(conn.readline())
        seen.append(conn.readline())
        conn.write(b"hola\n")
        seen.append(conn.readline())

    transport = opened(fake, on_connection=handler)
    phone, fd = phone_socket()
    on_loop(transport, transport._new_connection(PHONE, fd)).result(5)
    phone.sendall(b"HELLO|1|x|y*00000000\r\nREC")  # CRLF de las apps de terminal, y una línea partida
    phone.sendall(b"|resto\n")
    assert phone.recv(100) == b"hola\n"
    phone.close()  # el teléfono se va
    wait_for(lambda: len(seen) == 3, what="que el manejador termine")
    assert seen == [b"HELLO|1|x|y*00000000\n", b"REC|resto\n", None]
    wait_for(lambda: not transport.busy, what="que el transporte quede libre")
    with pytest.raises(OSError):
        os.fstat(fd)  # el transporte cerró el descriptor que le entregaron


def test_second_connection_while_busy_gets_nak_ocupado(fake):
    release = threading.Event()
    transport = opened(fake, on_connection=lambda conn: release.wait(10))
    first_phone, fd1 = phone_socket()
    on_loop(transport, transport._new_connection(PHONE, fd1)).result(5)
    wait_for(lambda: transport.busy, what="la primera conexión")

    second_phone, fd2 = phone_socket()
    on_loop(transport, transport._new_connection(PHONE, fd2)).result(5)
    reply = second_phone.makefile("rb")
    assert reply.readline() == b"NAK|0|OCUPADO*2C549C0A\n"
    assert reply.readline() == b""  # y se cierra
    assert transport.busy  # la primera sigue viva
    release.set()
    wait_for(lambda: not transport.busy, what="que termine la primera")
    first_phone.close()
    second_phone.close()


def test_unpaired_device_connection_is_closed_without_calling_the_handler(fake):
    called = []
    transport = opened(fake, on_connection=called.append)
    phone, fd = phone_socket()
    on_loop(transport, transport._new_connection(STRANGER, fd)).result(5)
    assert phone.recv(10) == b""
    assert called == [] and not transport.busy


def test_stop_cuts_the_active_connection(fake):
    got = []
    transport = opened(fake, on_connection=lambda conn: got.append(conn.readline()))
    phone, fd = phone_socket()
    on_loop(transport, transport._new_connection(PHONE, fd)).result(5)
    wait_for(lambda: transport.busy, what="la conexión")
    transport.stop()
    assert got == [None]  # el readline bloqueado se desbloquea como un corte
    assert phone.recv(10) == b"" and not transport.busy


def test_request_disconnection_cuts_the_active_connection(fake):
    got = []
    transport = opened(fake, on_connection=lambda conn: got.append(conn.readline()))
    phone, fd = phone_socket()
    on_loop(transport, transport._new_connection(PHONE, fd)).result(5)
    wait_for(lambda: transport.busy, what="la conexión")
    transport._loop.call_soon_threadsafe(transport._request_disconnection, PHONE)
    wait_for(lambda: got == [None], what="el corte")
    phone.close()


def test_connection_oversized_line_is_delivered_once_and_the_rest_skipped():
    phone, fd = phone_socket()
    conn = BluezConnection(fd)
    sender = threading.Thread(
        target=lambda: phone.sendall(b"x" * 70_000 + b"\nACK|3*6A8544FA\n"), daemon=True)
    sender.start()
    first = conn.readline()
    assert len(first) > 4000 and not first.endswith(b"\n")  # la sesión responderá LINEA_LARGA
    assert conn.readline() == b"ACK|3*6A8544FA\n"
    sender.join(5)
    conn.close()
    conn.close()  # cerrar dos veces no rompe nada
    with pytest.raises(OSError):
        conn.write(b"x")


def test_connection_write_to_a_gone_phone_raises_oserror():
    phone, fd = phone_socket()
    conn = BluezConnection(fd)
    phone.close()
    with pytest.raises(OSError):
        for _ in range(3):
            conn.write(b"ACK|3*6A8544FA\n")
    conn.close()


# ------------------------------------------------- con el controlador de verdad
def started(fake, require_pairing=True, **kwargs):
    transport = fake.make(require_pairing=require_pairing)
    store = FakeStore()
    changes = []
    controller = SyncController(transport, store, changes.append, **kwargs)
    controller.start()
    wait_for(lambda: fake.bus is not None and "RegisterProfile" in fake.bus.members(),
             what="que el transporte quede abierto")
    return controller, transport, store, changes


def test_controller_full_cycle_over_bluez_transport(fake):
    controller, transport, store, _ = started(fake)
    bus = fake.bus
    confirmation = on_loop(transport, transport._request_confirmation(PHONE, 39047))
    wait_for(lambda: controller.status()["estado"] == CONFIRMAR_CODIGO, what="CONFIRMAR_CODIGO")
    assert controller.status()["codigo"] == "039047"
    controller.confirm(True)
    confirmation.result(5)  # BlueZ recibe el "sí"

    phone, fd = phone_socket()
    on_loop(transport, transport._new_connection(PHONE, fd)).result(5)
    phone.sendall(hello() + rec(1) + rec(2) + end(2))
    replies, kinds = phone.makefile("rb"), []
    while not kinds or kinds[-1] != "BYE":
        kinds.append(parse(replies.readline()).kind)
    wait_for(lambda: controller.status()["estado"] == LISTO, what="LISTO")
    phone.close()

    assert store.batch_calls == ["SYNC"] and len(store.rows) == 2
    # Al terminar, el PC deja de ser visible y retira agente y perfil.
    assert "UnregisterProfile" in bus.members() and "UnregisterAgent" in bus.members()
    assert bus.adapter["Discoverable"] is False and bus.disconnected


def test_controller_timeout_closes_the_window_and_rejects_the_pending_code(fake):
    controller, transport, _, _ = started(fake, discoverable_s=1)
    bus = fake.bus
    confirmation = on_loop(transport, transport._request_confirmation(PHONE, 123456))
    wait_for(lambda: controller.status()["estado"] == CONFIRMAR_CODIGO, what="CONFIRMAR_CODIGO")
    wait_for(lambda: controller.status()["estado"] == IDLE, timeout=3, what="volver a IDLE")
    with pytest.raises(DBusError) as exc:
        confirmation.result(5)
    assert exc.value.type == REJECTED
    wait_for(lambda: bus.disconnected, what="que se cierre el bus")
    assert "UnregisterAgent" in bus.members() and bus.adapter["Discoverable"] is False


def test_bluez_cancel_returns_the_controller_to_waiting(fake):
    """El teléfono cancela el emparejamiento: el PC deja de mostrar el código y sigue esperando."""
    controller, transport, _, _ = started(fake)
    confirmation = on_loop(transport, transport._request_confirmation(PHONE, 123456))
    wait_for(lambda: controller.status()["estado"] == CONFIRMAR_CODIGO, what="CONFIRMAR_CODIGO")
    transport._loop.call_soon_threadsafe(transport._cancel_confirmations)  # Agent1.Cancel
    with pytest.raises(DBusError):
        confirmation.result(5)
    wait_for(lambda: controller.status()["estado"] == ESPERANDO_EMPAREJAMIENTO, what="volver a esperar")
    assert controller.status()["codigo"] is None
    controller.confirm(True)  # un clic tardío ya no hace nada
    assert controller.status()["estado"] == ESPERANDO_EMPAREJAMIENTO
    controller.cancel()


# ------------------------------------------- modo sin claves (D22, el predeterminado)
def test_default_is_open_mode_without_pairing():
    assert BluezTransport().require_pairing is False
    assert BluezTransport(require_pairing=True).require_pairing is True


def test_open_mode_has_no_agent_and_the_profile_needs_no_authentication(fake):
    transport = opened(fake, require_pairing=False)
    bus = fake.bus
    members = bus.members()
    assert "RegisterAgent" not in members and "RequestDefaultAgent" not in members
    assert set(bus.exported) == {PROFILE_PATH}  # el agente del sistema (KDE) queda intacto
    options = bus.last("RegisterProfile").body[2]
    assert options["RequireAuthentication"].value is False
    assert options["RequireAuthorization"].value is False
    # Sigue anunciándose, para que el teléfono lo encuentre la primera vez.
    assert bus.adapter["Alias"] == "gestion_inventario" and bus.adapter["Discoverable"] is True
    transport.stop()
    assert "UnregisterAgent" not in bus.members() and "UnregisterProfile" in bus.members()
    assert bus.adapter["Alias"] == "PC de prueba" and bus.adapter["Discoverable"] is False
    assert bus.exported == {} and bus.disconnected


def test_pairing_mode_still_requires_authentication_and_authorization(fake):
    opened(fake)  # el helper usa require_pairing=True
    options = fake.bus.last("RegisterProfile").body[2]
    assert options["RequireAuthentication"].value is True
    assert options["RequireAuthorization"].value is True


def test_open_mode_accepts_a_device_that_never_paired(fake):
    got = []
    transport = opened(fake, require_pairing=False, on_connection=lambda conn: got.append(conn.readline()))
    phone, fd = phone_socket()
    on_loop(transport, transport._new_connection(STRANGER, fd)).result(5)  # STRANGER: Paired=False
    phone.sendall(b"HELLO|1|x|y*00000000\n")
    wait_for(lambda: got == [b"HELLO|1|x|y*00000000\n"], what="que el manejador lea la línea")
    phone.close()
    wait_for(lambda: not transport.busy, what="que el transporte quede libre")


def test_open_mode_second_connection_is_still_busy(fake):
    release = threading.Event()
    transport = opened(fake, require_pairing=False, on_connection=lambda conn: release.wait(10))
    first_phone, fd1 = phone_socket()
    on_loop(transport, transport._new_connection(STRANGER, fd1)).result(5)
    wait_for(lambda: transport.busy, what="la primera conexión")
    second_phone, fd2 = phone_socket()
    on_loop(transport, transport._new_connection(STRANGER, fd2)).result(5)
    assert second_phone.makefile("rb").readline() == b"NAK|0|OCUPADO*2C549C0A\n"
    release.set()
    wait_for(lambda: not transport.busy, what="que termine la primera")
    first_phone.close()
    second_phone.close()


def test_open_mode_never_asks_for_a_code_and_a_full_sync_works(fake):
    controller, transport, store, changes = started(fake, require_pairing=False)
    phone, fd = phone_socket()
    on_loop(transport, transport._new_connection(STRANGER, fd)).result(5)
    phone.sendall(hello() + rec(1) + rec(2) + end(2))
    replies, kinds = phone.makefile("rb"), []
    while not kinds or kinds[-1] != "BYE":
        kinds.append(parse(replies.readline()).kind)
    wait_for(lambda: controller.status()["estado"] == LISTO, what="LISTO")
    phone.close()
    assert CONFIRMAR_CODIGO not in [c["estado"] for c in changes]
    assert store.batch_calls == ["SYNC"] and len(store.rows) == 2
