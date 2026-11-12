"""DESECHABLE (Tarea 9, paso 5): SyncController + BluezTransport + Oracle desde la terminal.

Hace lo mismo que hará el botón «Iniciar sincronización» de la app de escritorio: abre la ventana,
muestra el código de emparejamiento, recibe del teléfono y dispara el batch. Imprime cada cambio
de estado.

Uso (dentro del contenedor con Bluetooth):
  docker compose --profile spike run --rm bt-spike python server/spikes/controller_cli.py --spp
  ... controller_cli.py --check [--spp]   # abre y cierra la ventana contra el bluetoothd real y
                                          # comprueba que todo queda como estaba (sin teléfono)

--spp registra el UUID del puerto serie estándar: es el único al que se conectan las apps de
terminal serial. Sin --spp se registra el UUID propio de la aplicación (el que usará la APK).
"""

import argparse
import asyncio
import os
import queue
import signal
import sys
import time

from btsync.controller import CONFIRMAR_CODIGO, ERROR, IDLE, LISTO, SyncController
from btsync.store import Store
from btsync.transports import bluez
from btsync.transports.base import BluetoothUnavailable
from btsync.transports.bluez import BLUETOOTH_NAME, SERVICE_UUID, SPP_UUID, BluezTransport

_log_file = None


def log(text: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    if _log_file:
        _log_file.write(line + "\n")
        _log_file.flush()


async def adapter_now(adapter: str) -> dict:
    """Estado del adaptador leído con un bus nuevo (independiente del transporte)."""
    bus = await bluez._connect_bus()
    try:
        return await bluez._get_all(bus, f"/org/bluez/{adapter}", "org.bluez.Adapter1")
    finally:
        bus.disconnect()


def summary(a: dict, uuid: str) -> str:
    return (f"Alias={a.get('Alias')!r} Discoverable={a.get('Discoverable')} "
            f"DiscoverableTimeout={a.get('DiscoverableTimeout')} "
            f"Pairable={a.get('Pairable')} servicio_registrado={uuid in a.get('UUIDs', [])}")


def check(args, uuid: str) -> int:
    """Abre y cierra la ventana sin esperar a nadie. El PC es visible menos de un segundo."""
    before = asyncio.run(adapter_now(args.adapter))
    log(f"ANTES   {summary(before, uuid)}")

    async def nobody(code):
        return False

    transport = BluezTransport(args.adapter, uuid, discoverable_s=args.window, alias=args.name,
                               require_pairing=args.con_clave)
    try:
        transport.begin_pairing(nobody)
        transport.serve(lambda conn: None)
    except BluetoothUnavailable as exc:
        transport.stop()
        after = asyncio.run(adapter_now(args.adapter))
        log(f"BLUETOOTH NO DISPONIBLE: {exc}")
        log(f"CERRADO {summary(after, uuid)}")
        return 2
    during = asyncio.run(adapter_now(args.adapter))
    log(f"ABIERTO {summary(during, uuid)}")
    transport.stop()
    keys = ("Discoverable", "DiscoverableTimeout", "Pairable", "Alias")
    dirty = before.get("Alias") == args.name  # una copia anterior murió sin limpiar
    if dirty:
        log("AVISO: el adaptador ya estaba con el nombre de la aplicación (copia anterior sin limpiar); "
            "se espera que quede en los valores por defecto")

    def restored(after: dict) -> bool:
        if dirty:
            return after.get("Alias") != args.name and after.get("Discoverable") is False
        return all(after.get(k) == before.get(k) for k in keys)

    # BlueZ aplica el cambio de nombre de forma asíncrona: se espera a que el adaptador se asiente.
    deadline = time.monotonic() + 5
    while True:
        after = asyncio.run(adapter_now(args.adapter))
        if restored(after) or time.monotonic() > deadline:
            break
        time.sleep(0.2)
    log(f"CERRADO {summary(after, uuid)}")

    ok = (
        during.get("Discoverable") is True
        and during.get("Alias") == args.name
        and during.get("DiscoverableTimeout") == args.window
        and uuid in during.get("UUIDs", [])
        and uuid not in after.get("UUIDs", [])
        and restored(after)
    )
    log("--check: OK, la ventana se abre y todo vuelve a quedar como estaba" if ok
        else "--check: FALLO, revisa las tres líneas de arriba")
    return 0 if ok else 1


def db_report(store: Store) -> None:
    cur = store._connection().cursor()
    cur.execute("SELECT pendientes, procesando, procesados, errores, ultimo_origen FROM v_estado_batch")
    log(f"STAGING (pendientes, procesando, procesados, errores, último origen): {cur.fetchone()}")
    cur.execute(
        "SELECT * FROM (SELECT uuid_dispositivo, seq, estado, mensaje_error, datos_raw "
        "FROM captura_transito ORDER BY id_transito DESC) WHERE ROWNUM <= 5"
    )
    for row in cur.fetchall():
        log(f"  fila: {row}")
    cur.execute(
        "SELECT * FROM (SELECT id_conteo, cod_ubicacion, sku, cantidad, operador, vigente "
        "FROM registros_procesados ORDER BY id_registro DESC) WHERE ROWNUM <= 5"
    )
    for row in cur.fetchall():
        log(f"  lectura procesada: {row}")


def main() -> int:
    global _log_file
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--adapter", default="hci0")
    parser.add_argument("--spp", action="store_true", help="usar el UUID de puerto serie (apps de terminal)")
    parser.add_argument("--yes", action="store_true", help="aceptar el código sin preguntar")
    parser.add_argument("--con-clave", action="store_true",
                        help="exigir emparejamiento con código de 6 dígitos (por defecto: sin claves)")
    parser.add_argument("--window", type=int, default=120, help="segundos visible y esperando")
    parser.add_argument("--name", default=BLUETOOTH_NAME, help="nombre Bluetooth visible para el teléfono")
    parser.add_argument("--check", action="store_true", help="abrir y cerrar contra BlueZ, sin teléfono")
    parser.add_argument("--log", default=".superpowers/paso5-controller.log")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
    _log_file = open(args.log, "a", encoding="utf-8")
    uuid = SPP_UUID if args.spp else SERVICE_UUID
    bluez._log = lambda text: log(f"[bluez] {text}")  # que el transporte también escriba en el log
    log(f"=== controller_cli.py {' '.join(sys.argv[1:])} (servicio {uuid}) ===")

    if args.check:
        return check(args, uuid)

    # `docker stop` envía SIGTERM, y Python como proceso 1 lo ignora (y a los 10 s Docker lo mata):
    # sin este manejador el adaptador se quedaba visible y con el nombre cambiado.
    def terminar(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminar)

    store = Store(os.environ["DB_DSN"], os.environ["DB_USER"], os.environ["DB_PASSWORD"])
    changes: queue.Queue = queue.Queue()

    def on_change(status: dict) -> None:
        log(f"ESTADO {status}")
        changes.put(status)

    controller = SyncController(
        BluezTransport(args.adapter, uuid, discoverable_s=args.window, alias=args.name,
                       require_pairing=args.con_clave), store, on_change,
        discoverable_s=args.window,
    )
    controller.start()
    final = None
    try:
        while final is None:
            status = changes.get()
            if status["estado"] == CONFIRMAR_CODIGO:
                log(f">>> CÓDIGO DE EMPAREJAMIENTO: {status['codigo']} <<<")
                if args.yes:
                    accept = True
                else:
                    answer = input("¿El celular muestra el mismo código? [Enter = sí, n = no]: ").strip().lower()
                    accept = answer in ("", "s", "si", "sí", "y", "yes")
                log(f"respuesta en el PC: {'aceptar' if accept else 'rechazar'}")
                controller.confirm(accept)
            elif status["estado"] in (LISTO, ERROR, IDLE):
                final = status
    except KeyboardInterrupt:
        log("Ctrl-C: cancelando")
    finally:
        controller.cancel()

    log(f"FIN {final}")
    try:
        db_report(store)
    except Exception as exc:
        log(f"no se pudo leer la base: {exc!r}")
    return 0 if final and final["estado"] == LISTO else 1


if __name__ == "__main__":
    sys.exit(main())
