# `btsync.transports`: cómo llegan los bytes

La sesión ([`../session.py`](../session.py)) solo conoce una `Connection` orientada a líneas; quién acepta las conexiones
es un `Transport`. Así el mismo protocolo corre sobre Bluetooth real o sobre TCP (pruebas y plan B de la demo).

| Archivo | Contenido |
|---|---|
| [`base.py`](base.py) | Contratos: `Connection` (`readline`, `write`, `close`), `Transport` (`begin_pairing`, `serve`, `stop`) y la excepción `BluetoothUnavailable` (el mensaje se muestra tal cual al usuario) |
| [`bluez.py`](bluez.py) | `BluezTransport`: RFCOMM mediante BlueZ por **D-Bus** (`dbus-fast`); `BluezConnection`; agentes `_Agent` y `_Profile` |
| [`tcp.py`](tcp.py) | `TcpTransport` y `TcpConnection`: el mismo contrato sobre un socket TCP |

## Contrato (D19)

Como máximo **una conexión activa**. Mientras haya una, las demás reciben `NAK|0|OCUPADO` y se cierran. `serve` no bloquea;
`on_connection` se llama en un hilo del transporte por conexión; `stop` corta la activa y se puede volver a `serve`.

## `BluezTransport`

- `bluetoothd` vive en el host; el contenedor solo necesita `/var/run/dbus` montado. No crea sockets Bluetooth: BlueZ entrega
  cada conexión RFCOMM ya aceptada como un descriptor de archivo.
- Constantes: `SERVICE_UUID = 7a1c0b52-4f0e-4d6a-9c3b-5e2a6d9f1b01`, canal RFCOMM 22 y nombre visible `gestion_inventario`.
- `begin_pairing` hace visible el PC con ese nombre; `stop` lo restaura. Si falta adaptador, está bloqueado o no hay D-Bus,
  lanza `BluetoothUnavailable`.
- **Sin claves** (por defecto, D22): acepta teléfonos no emparejados y atiende cualquier emparejamiento con un agente
  silencioso (*Just Works*). **Con emparejamiento** (`require_pairing=True`, variable `BT_CON_CLAVE=1`): muestra un código
  de 6 dígitos y solo acepta dispositivos emparejados; el código llega a la GUI con `on_passkey`.
- Diseño y evidencias del experimento: [`../../../docs/spikes/bluez.md`](../../../docs/spikes/bluez.md).

## `TcpTransport`

`TcpTransport(host, port)`; con `port=0` el sistema elige un puerto libre (propiedad `port`). No empareja. La propiedad
`busy` indica si hay una sincronización en curso. Se usa con `BT_TRANSPORT=tcp` y con `tools/fake_phone.py`:

```bash
BT_TRANSPORT=tcp docker compose up -d bluetooth
python tools/fake_phone.py --host 127.0.0.1 --port 9000 --seed 42   # opciones: python tools/fake_phone.py --help
```

Selección del transporte: `servicio.crear_transporte()` ([`../servicio.py`](../servicio.py)), según `BT_TRANSPORT`.

## Pruebas relacionadas

`server/tests/test_bluez.py` (bus D-Bus falso), `test_e2e_tcp.py`, `test_concurrent_connect.py` y `test_controller.py`.
