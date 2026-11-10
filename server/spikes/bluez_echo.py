"""SPIKE DESECHABLE (Tarea 8): eco RFCOMM con BlueZ desde un contenedor.

No es código de producción ni forma parte del paquete btsync. Comprueba que un
contenedor, hablando con el bluetoothd del host por el bus de sistema D-Bus, puede:
  (a) hacerse visible y emparejable,
  (b) mostrar el código de 6 dígitos del emparejamiento (Agent1, DisplayYesNo),
  (c) registrar el UUID del servicio (ProfileManager1.RegisterProfile) y recibir
      una conexión RFCOMM,
  (d) devolver cada línea que llega.

Uso:
  docker compose --profile spike run --rm bt-spike python server/spikes/bluez_echo.py
  ... bluez_echo.py --check   # solo D-Bus: registra agente y perfiles y sale (sin radio)
  ... bluez_echo.py --yes     # acepta el código sin preguntar (sin terminal interactiva)

Resultados: docs/spikes/bluez.md
"""

import argparse
import asyncio
import os
import re
import select
import signal
import sys
import threading
import time

from dbus_fast import BusType, DBusError, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

BLUEZ = "org.bluez"
PROPS = "org.freedesktop.DBus.Properties"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"

APP_UUID = "7a1c0b52-4f0e-4d6a-9c3b-5e2a6d9f1b01"  # UUID del servicio del proyecto
SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"  # Serial Port Profile estándar
APP_CHANNEL = 22  # sin "Channel" BlueZ NO abre un listener RFCOMM para un UUID desconocido

AGENT_PATH = "/spike/agent"
DISCOVERABLE_S = 120

_log_file = None


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    if _log_file:
        _log_file.write(line + "\n")
        _log_file.flush()


async def call(bus, path, iface, member, sig="", body=None, dest=BLUEZ):
    reply = await bus.call(
        Message(destination=dest, path=path, interface=iface, member=member,
                signature=sig, body=body or [])
    )
    if reply.message_type == MessageType.ERROR:
        raise DBusError(reply.error_name, reply.body[0] if reply.body else "")
    return reply.body


async def get_all(bus, path, iface):
    props = (await call(bus, path, PROPS, "GetAll", "s", [iface]))[0]
    return {k: v.value for k, v in props.items()}


async def set_prop(bus, path, iface, name, sig, value):
    await call(bus, path, PROPS, "Set", "ssv", [iface, name, Variant(sig, value)])


async def describe(bus, device_path) -> str:
    try:
        d = await get_all(bus, device_path, DEVICE_IFACE)
        return (f"{d.get('Alias', '?')} [{d.get('Address', '?')}] "
                f"Paired={d.get('Paired')} Trusted={d.get('Trusted')}")
    except Exception as e:  # el spike solo informa
        return f"{device_path} (sin propiedades: {e})"


def ask(prompt: str) -> "asyncio.Future[str]":
    """input() en un hilo daemon: no bloquea el bucle ni la salida del proceso."""
    loop = asyncio.get_running_loop()
    fut = loop.create_future()

    def worker():
        try:
            answer = input(prompt)
        except EOFError:
            answer = "__EOF__"
        loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result(answer))

    threading.Thread(target=worker, daemon=True).start()
    return fut


class Agent(ServiceInterface):
    def __init__(self, bus, auto_yes: bool):
        super().__init__("org.bluez.Agent1")
        self.bus = bus
        self.auto_yes = auto_yes

    async def _confirm(self, question: str) -> None:
        if self.auto_yes:
            log("AGENTE: aceptado automáticamente (--yes)")
            return
        answer = (await ask(f"{question} [Enter/s = aceptar, n = rechazar]: ")).strip().lower()
        if answer in ("", "s", "si", "sí", "y", "yes"):
            log("AGENTE: aceptado en el PC")
            return
        log(f"AGENTE: rechazado en el PC (respuesta {answer!r})")
        raise DBusError("org.bluez.Error.Rejected", "rechazado en el PC")

    @method()
    def Release(self):
        log("AGENTE: Release")

    @method()
    async def RequestConfirmation(self, device: "o", passkey: "u"):
        who = await describe(self.bus, device)
        log(f"AGENTE: RequestConfirmation de {who}")
        log(f"AGENTE: >>> CODIGO DE EMPAREJAMIENTO: {passkey:06d} <<<")
        await self._confirm("¿El celular muestra el mismo código?")

    @method()
    async def RequestAuthorization(self, device: "o"):
        who = await describe(self.bus, device)
        log(f"AGENTE: RequestAuthorization (emparejamiento sin código) de {who}")
        await self._confirm("¿Aceptar el emparejamiento sin código?")

    @method()
    async def AuthorizeService(self, device: "o", uuid: "s"):
        who = await describe(self.bus, device)
        log(f"AGENTE: AuthorizeService uuid={uuid} de {who} -> autorizado")

    @method()
    def RequestPinCode(self, device: "o") -> "s":
        log("AGENTE: RequestPinCode (emparejamiento antiguo con PIN) -> rechazado")
        raise DBusError("org.bluez.Error.Rejected", "solo SSP")

    @method()
    def RequestPasskey(self, device: "o") -> "u":
        log("AGENTE: RequestPasskey -> rechazado")
        raise DBusError("org.bluez.Error.Rejected", "solo SSP")

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):
        log(f"AGENTE: DisplayPasskey {passkey:06d} (digitados {entered})")

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s"):
        log(f"AGENTE: DisplayPinCode {pincode}")

    @method()
    def Cancel(self):
        log("AGENTE: Cancel (el otro lado canceló o se agotó el tiempo)")


class Profile(ServiceInterface):
    def __init__(self, bus, label: str):
        super().__init__("org.bluez.Profile1")
        self.bus = bus
        self.label = label

    @method()
    def Release(self):
        log(f"PERFIL {self.label}: Release")

    @method()
    async def NewConnection(self, device: "o", fd: "h", props: "a{sv}"):
        who = await describe(self.bus, device)
        own = os.dup(fd)  # copia propia: no depende de lo que dbus-fast haga con el fd original
        extra = {k: v.value for k, v in props.items()}
        log(f"PERFIL {self.label}: NewConnection de {who} fd={fd}->{own} props={extra}")
        threading.Thread(target=echo_loop, args=(own, self.label), daemon=True).start()

    @method()
    def RequestDisconnection(self, device: "o"):
        log(f"PERFIL {self.label}: RequestDisconnection {device}")


def echo_loop(fd: int, label: str) -> None:
    """Lee del socket RFCOMM (un fd ya conectado que entrega BlueZ) y devuelve cada línea."""
    buf = b""
    try:
        os.set_blocking(fd, True)
        while True:
            ready, _, _ = select.select([fd], [], [], 1.0)
            if not ready:
                if buf:  # llegó texto sin salto de línea: se devuelve igual
                    log(f"ECO {label}: (sin salto de línea) {buf!r}")
                    buf = _reply(fd, label, buf)
                continue
            data = os.read(fd, 4096)
            if not data:
                log(f"ECO {label}: el celular cerró la conexión")
                return
            log(f"ECO {label}: <- {data!r}")
            buf += data
            *lines, buf = re.split(rb"\r\n|\n|\r", buf)
            for line in lines:
                if line:
                    _reply(fd, label, line)
    except OSError as e:
        log(f"ECO {label}: conexión terminada ({e})")
    finally:
        os.close(fd)


def _reply(fd: int, label: str, line: bytes) -> bytes:
    out = b"eco: " + line + b"\r\n"
    os.write(fd, out)
    log(f"ECO {label}: -> {out!r}")
    return b""


def on_signal_message(msg) -> None:
    """Registra cambios de estado útiles (emparejado, conectado, visible)."""
    if (msg.message_type != MessageType.SIGNAL or msg.member != "PropertiesChanged"
            or not msg.path or not msg.path.startswith("/org/bluez")):
        return
    iface, changed = msg.body[0], msg.body[1]
    if iface not in (ADAPTER_IFACE, DEVICE_IFACE):
        return
    keys = ("Powered", "Discoverable", "Pairable", "Paired", "Bonded", "Connected", "Trusted")
    seen = {k: v.value for k, v in changed.items() if k in keys}
    if seen:
        log(f"CAMBIO {msg.path.rsplit('/', 1)[-1]}: {seen}")


async def main() -> int:
    global _log_file
    ap = argparse.ArgumentParser(description="Spike desechable: eco RFCOMM con BlueZ")
    ap.add_argument("--adapter", default="hci0")
    ap.add_argument("--check", action="store_true",
                    help="solo comprueba D-Bus (agente y perfiles) y sale; no enciende ni hace visible")
    ap.add_argument("--yes", action="store_true", help="acepta el emparejamiento sin preguntar")
    ap.add_argument("--no-spp", action="store_true", help="no registrar el UUID SPP estándar")
    ap.add_argument("--log", default=".superpowers/spike-bluez.log")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
    _log_file = open(args.log, "a", encoding="utf-8")
    log(f"=== bluez_echo.py {' '.join(sys.argv[1:])} uid={os.getuid()} pid={os.getpid()} ===")

    adapter = f"/org/bluez/{args.adapter}"
    bus = await MessageBus(bus_type=BusType.SYSTEM, negotiate_unix_fd=True).connect()
    log(f"D-Bus de sistema conectado como {bus.unique_name}")

    a = await get_all(bus, adapter, ADAPTER_IFACE)
    log(f"Adaptador {args.adapter}: {a.get('Alias')} [{a.get('Address')}] Powered={a.get('Powered')} "
        f"PowerState={a.get('PowerState')} Discoverable={a.get('Discoverable')} "
        f"Pairable={a.get('Pairable')} DiscoverableTimeout={a.get('DiscoverableTimeout')}")
    original_timeout = a.get("DiscoverableTimeout", 180)

    bus.add_message_handler(on_signal_message)
    await call(bus, "/org/freedesktop/DBus", "org.freedesktop.DBus", "AddMatch", "s",
               ["type='signal',sender='org.bluez',interface='org.freedesktop.DBus.Properties',"
                "member='PropertiesChanged'"], dest="org.freedesktop.DBus")

    # (1) Agente DisplayYesNo, por defecto mientras el spike vive.
    bus.export(AGENT_PATH, Agent(bus, args.yes))
    await call(bus, "/org/bluez", "org.bluez.AgentManager1", "RegisterAgent", "os",
               [AGENT_PATH, "DisplayYesNo"])
    await call(bus, "/org/bluez", "org.bluez.AgentManager1", "RequestDefaultAgent", "o", [AGENT_PATH])
    log("Agente registrado (DisplayYesNo) y puesto por defecto")

    # (3) Perfiles RFCOMM en rol servidor.
    profiles = [("/spike/profile/app", "APP", APP_UUID, {
        "Name": Variant("s", "InventarioBT"),
        "Role": Variant("s", "server"),
        "Channel": Variant("q", APP_CHANNEL),
        "RequireAuthentication": Variant("b", True),
    })]
    if not args.no_spp:
        # Las apps de terminal serial de Android solo conectan al UUID SPP estándar.
        profiles.append(("/spike/profile/spp", "SPP", SPP_UUID, {
            "Name": Variant("s", "InventarioBT SPP"),
            "Role": Variant("s", "server"),
            "RequireAuthentication": Variant("b", True),
        }))
    registered = []
    for path, label, uuid, opts in profiles:
        bus.export(path, Profile(bus, label))
        await call(bus, "/org/bluez", "org.bluez.ProfileManager1", "RegisterProfile", "osa{sv}",
                   [path, uuid, opts])
        registered.append(path)
        log(f"Perfil {label} registrado: uuid={uuid} canal={opts['Channel'].value if 'Channel' in opts else 'por defecto de BlueZ'}")

    uuids = (await get_all(bus, adapter, ADAPTER_IFACE)).get("UUIDs", [])
    for _, label, uuid, _ in profiles:
        log(f"Adapter1.UUIDs contiene {label} ({uuid}): {uuid in uuids}")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    rc = 0
    try:
        if args.check:
            log("--check: D-Bus OK (lectura, agente y perfiles). No se tocó la radio.")
        else:
            # (2) Encendido, emparejable y visible por tiempo limitado.
            if not a.get("Powered"):
                try:
                    await set_prop(bus, adapter, ADAPTER_IFACE, "Powered", "b", True)
                    for _ in range(50):
                        if (await get_all(bus, adapter, ADAPTER_IFACE)).get("Powered"):
                            break
                        await asyncio.sleep(0.1)
                except DBusError as e:
                    log(f"ERROR al encender el adaptador: {e.type}: {e.text}")
                if not (await get_all(bus, adapter, ADAPTER_IFACE)).get("Powered"):
                    log("El adaptador sigue apagado. Si está bloqueado, en el host: rfkill unblock bluetooth")
                    return 2
            await set_prop(bus, adapter, ADAPTER_IFACE, "Pairable", "b", True)
            await set_prop(bus, adapter, ADAPTER_IFACE, "DiscoverableTimeout", "u", DISCOVERABLE_S)
            await set_prop(bus, adapter, ADAPTER_IFACE, "Discoverable", "b", True)
            a = await get_all(bus, adapter, ADAPTER_IFACE)
            log(f"VISIBLE como «{a.get('Alias')}» [{a.get('Address')}] durante {DISCOVERABLE_S} s. "
                "Empareja desde el celular. Ctrl-C para terminar.")
            await stop.wait()
            log("Señal recibida: terminando")
    except DBusError as e:
        log(f"ERROR D-Bus: {e.type}: {e.text}")
        rc = 1
    finally:
        # Deja el adaptador como estaba (no visible, timeout original) y retira lo registrado.
        for what, coro in (
            ("Discoverable=False", set_prop(bus, adapter, ADAPTER_IFACE, "Discoverable", "b", False)),
            ("DiscoverableTimeout original", set_prop(bus, adapter, ADAPTER_IFACE,
                                                       "DiscoverableTimeout", "u", original_timeout)),
        ):
            if args.check:
                coro.close()
                continue
            try:
                await coro
            except DBusError as e:
                log(f"limpieza {what}: {e.type}: {e.text}")
        for path in registered:
            try:
                await call(bus, "/org/bluez", "org.bluez.ProfileManager1", "UnregisterProfile", "o", [path])
            except DBusError as e:
                log(f"limpieza UnregisterProfile {path}: {e.type}: {e.text}")
        try:
            await call(bus, "/org/bluez", "org.bluez.AgentManager1", "UnregisterAgent", "o", [AGENT_PATH])
        except DBusError as e:
            log(f"limpieza UnregisterAgent: {e.type}: {e.text}")
        log("Limpieza hecha: perfiles y agente retirados")
        bus.disconnect()
    return rc


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except DBusError as e:
        log(f"ERROR D-Bus: {e.type}: {e.text}")
        sys.exit(1)
    except Exception as e:  # p. ej. no existe el socket del bus
        log(f"ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
