"""Transporte Bluetooth real: RFCOMM a través de BlueZ, hablando con ``bluetoothd`` por D-Bus.

``bluetoothd`` vive en el host; este proceso (en un contenedor) solo necesita el bus de sistema
(``/var/run/dbus`` montado). No se crea ningún socket Bluetooth aquí: BlueZ entrega cada conexión
RFCOMM ya aceptada como un descriptor de archivo. Diseño y evidencias: docs/spikes/bluez.md.

Dos modos (``require_pairing``):

* **Sin claves** (por defecto, D22): el servicio no exige autenticación ni autorización. Un teléfono
  que nunca se emparejó puede conectarse (Android: ``createInsecureRfcommSocketToServiceRecord``);
  no hay código ni agente propio. La protección es que el PC solo acepta mientras la ventana está
  abierta y de a una conexión.
* **Con emparejamiento** (``require_pairing=True``, D5/D8): el PC registra un agente que muestra el
  código de 6 dígitos y solo acepta dispositivos emparejados, y solo para el servicio propio.

Ciclo de vida (lo maneja ``SyncController``)::

    begin_pairing  →  conecta al bus, (con emparejamiento: registra el agente del código),
                      le pone al adaptador el nombre de la aplicación y lo hace visible y emparejable
    serve          →  registra el servicio RFCOMM (perfil) y empieza a recibir conexiones
    stop           →  rechaza lo pendiente, corta la conexión activa, retira perfil y agente,
                      y deja el adaptador como estaba (también su nombre)

Todo lo que toca D-Bus corre en un bucle asyncio propio, en un hilo aparte. Cada conexión se
atiende en otro hilo, uno a la vez (D19).
"""

import asyncio
import concurrent.futures
import os
import select
import sys
import threading
from typing import Awaitable, Callable

from dbus_fast import BusType, DBusError, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

from ..protocol import frame
from .base import BluetoothUnavailable, Connection

SERVICE_UUID = "7a1c0b52-4f0e-4d6a-9c3b-5e2a6d9f1b01"  # el servicio de esta aplicación
SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"      # puerto serie estándar (apps de terminal)
# Para un UUID que BlueZ no conoce hay que fijar el canal: sin él registra el servicio pero no
# abre ningún listener RFCOMM. El perfil serie estándar ya trae el suyo.
RFCOMM_CHANNEL = 22
# Nombre Bluetooth con el que el PC aparece en el teléfono mientras la ventana está abierta.
BLUETOOTH_NAME = "gestion_inventario"

AGENT_PATH = "/com/sebasarchive/kardex/agent"
PROFILE_PATH = "/com/sebasarchive/kardex/profile"

_BLUEZ = "org.bluez"
_PROPS = "org.freedesktop.DBus.Properties"
_ADAPTER = "org.bluez.Adapter1"
_DEVICE = "org.bluez.Device1"
_AGENT_MANAGER = "org.bluez.AgentManager1"
_PROFILE_MANAGER = "org.bluez.ProfileManager1"
_REJECTED = "org.bluez.Error.Rejected"
_NO_BLUETOOTHD = ("org.freedesktop.DBus.Error.ServiceUnknown", "org.freedesktop.DBus.Error.NameHasNoOwner")

_READ_CAP = 65536   # tope de una línea en memoria; el protocolo admite 4000 bytes
_CALL_TIMEOUT = 20  # segundos que se espera a BlueZ antes de darlo por no disponible


def _log(text: str) -> None:
    print(f"[bluez] {text}", file=sys.stderr, flush=True)


async def _connect_bus():
    """Bus de sistema con paso de descriptores (por ahí llega el socket RFCOMM)."""
    return await MessageBus(bus_type=BusType.SYSTEM, negotiate_unix_fd=True).connect()


async def _call(bus, path: str, interface: str, member: str, signature: str = "", body=None):
    reply = await bus.call(Message(
        destination=_BLUEZ, path=path, interface=interface, member=member,
        signature=signature, body=body or [],
    ))
    if reply.message_type == MessageType.ERROR:
        raise DBusError(reply.error_name, reply.body[0] if reply.body else "")
    return reply.body


async def _get_all(bus, path: str, interface: str) -> dict:
    props = (await _call(bus, path, _PROPS, "GetAll", "s", [interface]))[0]
    return {name: value.value for name, value in props.items()}


class BluezConnection:
    """``Connection`` sobre el descriptor RFCOMM que entrega BlueZ. Se adueña del descriptor."""

    def __init__(self, fd: int) -> None:
        os.set_blocking(fd, True)
        self._fd = fd
        self._wake_r, self._wake_w = os.pipe()  # para desbloquear un readline desde otro hilo
        self._buf = bytearray()
        self._skipping = False
        self._closed = False
        self._lock = threading.Lock()

    def readline(self) -> bytes | None:
        while True:
            cut = self._buf.find(b"\n")
            if self._skipping:  # resto de una línea desmesurada: se descarta hasta su salto
                if cut < 0:
                    self._buf.clear()
                else:
                    del self._buf[: cut + 1]
                    self._skipping = False
                    continue
            elif cut >= 0:
                line = bytes(self._buf[: cut + 1])
                del self._buf[: cut + 1]
                if line.endswith(b"\r\n"):  # las apps de terminal serie envían CRLF
                    line = line[:-2] + b"\n"
                return line
            elif len(self._buf) >= _READ_CAP:
                # Se entrega el primer tramo (la sesión responde LINEA_LARGA) sin acumular más.
                chunk = bytes(self._buf)
                self._buf.clear()
                self._skipping = True
                return chunk
            data = self._read()
            if data is None:
                return None
            self._buf += data

    def _read(self) -> bytes | None:
        try:
            ready, _, _ = select.select([self._fd, self._wake_r], [], [])
            if self._wake_r in ready:
                return None
            data = os.read(self._fd, 4096)
        except (OSError, ValueError):
            return None
        return data or None

    def write(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            if self._closed:
                raise BrokenPipeError("la conexión Bluetooth está cerrada")
            view = view[os.write(self._fd, view):]

    def abort(self) -> None:
        """Corta desde otro hilo: el ``readline`` en curso devuelve ``None``."""
        with self._lock:
            if not self._closed:
                try:
                    os.write(self._wake_w, b"x")
                except OSError:
                    pass

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for fd in (self._fd, self._wake_r, self._wake_w):
                try:
                    os.close(fd)
                except OSError:
                    pass


# Las interfaces D-Bus solo traducen: toda la lógica está en BluezTransport (y ahí se prueba).
class _Agent(ServiceInterface):
    """org.bluez.Agent1: BlueZ le pregunta a este objeto durante el emparejamiento."""

    def __init__(self, owner: "BluezTransport") -> None:
        super().__init__("org.bluez.Agent1")
        self._owner = owner

    @method()
    def Release(self):
        pass

    @method()
    async def RequestConfirmation(self, device: "o", passkey: "u"):
        await self._owner._request_confirmation(device, passkey)

    @method()
    async def AuthorizeService(self, device: "o", uuid: "s"):
        await self._owner._authorize_service(device, uuid)

    @method()
    def RequestAuthorization(self, device: "o"):
        raise DBusError(_REJECTED, "solo se empareja confirmando el código")

    @method()
    def RequestPinCode(self, device: "o") -> "s":
        raise DBusError(_REJECTED, "solo se empareja confirmando el código")

    @method()
    def RequestPasskey(self, device: "o") -> "u":
        raise DBusError(_REJECTED, "solo se empareja confirmando el código")

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):
        pass

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s"):
        pass

    @method()
    def Cancel(self):
        self._owner._cancel_confirmations()


class _Profile(ServiceInterface):
    """org.bluez.Profile1: BlueZ entrega aquí cada conexión RFCOMM al servicio."""

    def __init__(self, owner: "BluezTransport") -> None:
        super().__init__("org.bluez.Profile1")
        self._owner = owner

    @method()
    def Release(self):
        pass

    @method()
    async def NewConnection(self, device: "o", fd: "h", properties: "a{sv}"):
        await self._owner._new_connection(device, fd)

    @method()
    def RequestDisconnection(self, device: "o"):
        self._owner._request_disconnection(device)


class BluezTransport:
    """Implementa ``Transport`` con el adaptador Bluetooth del host."""

    def __init__(
        self,
        adapter: str = "hci0",
        service_uuid: str = SERVICE_UUID,
        discoverable_s: int = 120,
        alias: str = BLUETOOTH_NAME,
        require_pairing: bool = False,
    ) -> None:
        self.adapter = adapter
        self.service_uuid = service_uuid.lower()
        self.discoverable_s = discoverable_s
        self.alias = alias
        self.require_pairing = require_pairing
        self._adapter_path = f"/org/bluez/{adapter}"
        self._op_lock = threading.RLock()    # begin_pairing / serve / stop, de a uno
        self._conn_lock = threading.Lock()   # protege _active
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._bus = None
        self._on_passkey: Callable[[str], Awaitable[bool]] | None = None
        self._on_connection: Callable[[Connection], None] | None = None
        self._original: dict = {}            # propiedades del adaptador que hay que devolver
        self._visible = False
        self._agent_registered = False
        self._profile_registered = False
        self._confirmations: set[asyncio.Future] = set()
        self._active: BluezConnection | None = None
        self._handler: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        """True mientras haya una sincronización en curso."""
        return self._active is not None

    # ------------------------------------------------------------------ API
    def begin_pairing(self, on_passkey: Callable[[str], Awaitable[bool]]) -> None:
        with self._op_lock:
            if self._loop is not None:
                raise RuntimeError("el transporte ya está abierto: llama antes a stop()")
            self._start_loop()
            try:
                self._run(self._begin(on_passkey))
            except BaseException:
                self._close_loop()  # _begin ya deshizo lo que alcanzó a registrar
                raise

    def serve(self, on_connection: Callable[[Connection], None]) -> None:
        with self._op_lock:
            if self._loop is None:
                raise RuntimeError("llama antes a begin_pairing()")
            self._run(self._serve(on_connection))

    def stop(self) -> None:
        if threading.current_thread() is self._thread:
            raise RuntimeError("stop() no se puede llamar desde el hilo del bus")
        with self._op_lock:
            if self._loop is None:
                return
            try:
                self._run(self._shutdown())
            except Exception as exc:
                _log(f"la limpieza no terminó bien: {exc!r}")
            self._close_loop()
            handler = self._handler
        if handler is not None and handler is not threading.current_thread():
            handler.join(timeout=5)

    # ------------------------------------------------------- hilo del bucle
    def _start_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="bluez-bus", daemon=True)
        self._thread.start()

    def _close_loop(self) -> None:
        loop, thread = self._loop, self._thread
        self._loop = self._thread = None
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        if not thread.is_alive():
            loop.close()

    def _run(self, coro):
        """Ejecuta una corrutina en el bucle del bus y espera su resultado."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(_CALL_TIMEOUT)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise BluetoothUnavailable(
                f"BlueZ no respondió en {_CALL_TIMEOUT} s. Revisa que bluetoothd esté corriendo en el host."
            ) from None

    # ------------------------------------------------------ abrir y cerrar
    async def _begin(self, on_passkey) -> None:
        self._on_passkey = on_passkey
        try:
            self._bus = await _connect_bus()
        except Exception as exc:
            raise BluetoothUnavailable(
                f"No se pudo conectar al D-Bus del sistema ({exc}). "
                "¿Está montado /var/run/dbus en el contenedor?"
            ) from exc
        try:
            adapter = await self._read_adapter()
            if not adapter.get("Powered"):
                if adapter.get("PowerState") == "off-blocked":
                    raise BluetoothUnavailable(
                        "El Bluetooth está bloqueado. En el host ejecuta: rfkill unblock bluetooth"
                    )
                raise BluetoothUnavailable("El Bluetooth está apagado. Enciéndelo y vuelve a intentar.")
            self._original = {
                name: adapter[name]
                for name in ("Discoverable", "DiscoverableTimeout", "Pairable", "Alias")
                if name in adapter
            }
            if adapter.get("Alias") == self.alias:
                # Una copia anterior murió sin limpiar (p. ej. `docker stop`) y dejó el nombre de la
                # aplicación puesto: ese estado no es el original. Se vuelve a los valores de
                # fábrica de BlueZ; un nombre vacío significa "el nombre del sistema".
                _log("el adaptador quedó con el nombre de la aplicación: se restaurará a los valores por defecto")
                self._original.update({"Discoverable": False, "DiscoverableTimeout": 180, "Alias": ""})

            if self.require_pairing:
                # Primero el agente: cuando el PC sea visible ya debe haber quien reciba el código.
                self._bus.export(AGENT_PATH, _Agent(self))
                await _call(self._bus, "/org/bluez", _AGENT_MANAGER, "RegisterAgent", "os",
                            [AGENT_PATH, "DisplayYesNo"])
                self._agent_registered = True
                # Por defecto: es el teléfono quien inicia el emparejamiento.
                await _call(self._bus, "/org/bluez", _AGENT_MANAGER, "RequestDefaultAgent", "o", [AGENT_PATH])

            self._visible = True
            await self._set_adapter("Alias", "s", self.alias)  # antes de hacerse visible
            await self._set_adapter("Pairable", "b", True)
            await self._set_adapter("DiscoverableTimeout", "u", self.discoverable_s)
            await self._set_adapter("Discoverable", "b", True)
        except BluetoothUnavailable:
            await self._shutdown()
            raise
        except DBusError as exc:
            await self._shutdown()
            raise BluetoothUnavailable(f"BlueZ rechazó la operación ({exc.type}: {exc.text})") from exc
        modo = "con emparejamiento" if self.require_pairing else "sin claves"
        _log(f"visible como «{self.alias}» ({modo}) durante {self.discoverable_s} s ({self.adapter})")

    async def _read_adapter(self) -> dict:
        try:
            return await _get_all(self._bus, self._adapter_path, _ADAPTER)
        except DBusError as exc:
            if exc.type in _NO_BLUETOOTHD:
                raise BluetoothUnavailable(
                    "El servicio Bluetooth (bluetoothd) no está corriendo en el host."
                ) from exc
            raise BluetoothUnavailable(f"No hay adaptador Bluetooth ({self.adapter})") from exc

    async def _set_adapter(self, name: str, signature: str, value) -> None:
        await _call(self._bus, self._adapter_path, _PROPS, "Set", "ssv",
                    [_ADAPTER, name, Variant(signature, value)])

    async def _serve(self, on_connection) -> None:
        options = {
            "Name": Variant("s", "InventarioBT"),
            "Role": Variant("s", "server"),
            # Sin claves (D22): ni autenticación ni autorización; con emparejamiento (D8): las dos.
            "RequireAuthentication": Variant("b", self.require_pairing),
            "RequireAuthorization": Variant("b", self.require_pairing),
        }
        if self.service_uuid != SPP_UUID:
            options["Channel"] = Variant("q", RFCOMM_CHANNEL)
        self._bus.export(PROFILE_PATH, _Profile(self))
        try:
            await _call(self._bus, "/org/bluez", _PROFILE_MANAGER, "RegisterProfile", "osa{sv}",
                        [PROFILE_PATH, self.service_uuid, options])
        except DBusError as exc:
            raise BluetoothUnavailable(
                f"BlueZ no aceptó el servicio Bluetooth ({exc.type}: {exc.text})"
            ) from exc
        self._profile_registered = True
        self._on_connection = on_connection
        _log(f"servicio RFCOMM registrado ({self.service_uuid})")

    async def _shutdown(self) -> None:
        """Deja todo como estaba. Se puede llamar más de una vez."""
        self._on_connection = None
        pending = list(self._confirmations)
        for task in pending:
            task.cancel()  # un código sin responder se rechaza
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for _ in range(2):
            await asyncio.sleep(0)  # deja salir las respuestas de rechazo antes de retirar el agente
        with self._conn_lock:
            active = self._active
        if active is not None:
            active.abort()

        bus, self._bus = self._bus, None
        if bus is None:
            return

        async def quiet(what: str, coro) -> None:
            try:
                await coro
            except Exception as exc:
                _log(f"limpieza, {what}: {exc!r}")

        if self._profile_registered:
            self._profile_registered = False
            await quiet("retirar el servicio", _call(
                bus, "/org/bluez", _PROFILE_MANAGER, "UnregisterProfile", "o", [PROFILE_PATH]))
        if self._visible:
            self._visible = False
            restore = {"Discoverable": False, "DiscoverableTimeout": 180, "Pairable": True, **self._original}
            for name, signature in (
                ("Discoverable", "b"), ("DiscoverableTimeout", "u"), ("Pairable", "b"), ("Alias", "s"),
            ):
                if name not in restore:
                    continue  # sin nombre original conocido no se toca
                await quiet(f"restaurar {name}", _call(
                    bus, self._adapter_path, _PROPS, "Set", "ssv",
                    [_ADAPTER, name, Variant(signature, restore[name])]))
        if self._agent_registered:
            self._agent_registered = False
            await quiet("retirar el agente", _call(
                bus, "/org/bluez", _AGENT_MANAGER, "UnregisterAgent", "o", [AGENT_PATH]))
        for path in (PROFILE_PATH, AGENT_PATH):
            try:
                bus.unexport(path)
            except Exception:
                pass
        try:
            bus.disconnect()
        except Exception as exc:
            _log(f"limpieza, cerrar el bus: {exc!r}")
        self._on_passkey = None
        _log("ventana cerrada: servicio y agente retirados")

    # --------------------------------------------- lo que pide BlueZ (bucle)
    async def _is_paired(self, device: str) -> bool:
        try:
            return bool((await _get_all(self._bus, device, _DEVICE)).get("Paired"))
        except Exception:
            return False

    async def _request_confirmation(self, device: str, passkey: int) -> None:
        """BlueZ pide confirmar el código que también muestra el teléfono."""
        code = f"{passkey:06d}"  # el código puede empezar por cero
        _log(f"código de emparejamiento {code} para {device}")
        if self._on_passkey is None:
            raise DBusError(_REJECTED, "no hay una sincronización abierta")
        task = asyncio.ensure_future(self._on_passkey(code))
        self._confirmations.add(task)
        try:
            accepted = await task
        except asyncio.CancelledError:
            accepted = False  # lo canceló el teléfono, BlueZ o stop()
        finally:
            self._confirmations.discard(task)
        if not accepted:
            _log("emparejamiento rechazado")
            raise DBusError(_REJECTED, "rechazado en el PC")
        _log("emparejamiento aceptado en el PC")

    def _cancel_confirmations(self) -> None:
        """Agent1.Cancel: el teléfono canceló o BlueZ dejó de esperar."""
        for task in list(self._confirmations):
            task.cancel()

    async def _authorize_service(self, device: str, uuid: str) -> None:
        """Mientras este agente es el del sistema recibe las peticiones de todos los perfiles:
        solo se autoriza el servicio propio (nunca audio, manos libres, etc.)."""
        if uuid.lower() != self.service_uuid or not await self._is_paired(device):
            _log(f"servicio {uuid} de {device}: rechazado")
            raise DBusError(_REJECTED, "servicio no autorizado")
        _log(f"servicio {uuid} de {device}: autorizado")

    async def _new_connection(self, device: str, fd: int) -> None:
        """Llega una conexión RFCOMM ya aceptada. dbus-fast no cierra ``fd``: es nuestro."""
        paired = (not self.require_pairing) or await self._is_paired(device)
        conn = None
        with self._conn_lock:
            busy = self._active is not None
            if paired and not busy and self._on_connection is not None:
                conn = self._active = BluezConnection(fd)
        if conn is None:
            if paired and busy:  # D19: una sincronización a la vez
                try:
                    os.set_blocking(fd, True)
                    os.write(fd, frame(["NAK", "0", "OCUPADO"]))
                except OSError:
                    pass
            _log(f"conexión de {device} rechazada ({'ocupado' if paired and busy else 'no emparejado o cerrado'})")
            os.close(fd)
            return
        _log(f"conexión de {device}")
        self._handler = threading.Thread(
            target=self._handle, args=(conn, self._on_connection), name="bluez-session", daemon=True
        )
        self._handler.start()

    def _handle(self, conn: BluezConnection, on_connection) -> None:
        try:
            on_connection(conn)
        except Exception as exc:  # un fallo de una sesión no debe tumbar el transporte
            _log(f"la sesión terminó con error: {exc!r}")
        finally:
            conn.close()
            with self._conn_lock:
                if self._active is conn:
                    self._active = None

    def _request_disconnection(self, device: str) -> None:
        with self._conn_lock:
            active = self._active
        if active is not None:
            active.abort()
