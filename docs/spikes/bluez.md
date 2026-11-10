# Spike: Bluetooth (BlueZ) desde un contenedor Docker

Tarea 8 del plan. Fecha: 2026-11-10. Código desechable: `server/spikes/bluez_echo.py`
(no forma parte de `btsync` ni de la app de escritorio).

## Resultado

**Funciona dentro de Docker, con las flags del plan y sin ningún plan B.** No hizo falta
política D-Bus adicional, ni `privileged: true`, ni sacar la app al host. El requisito
«todo en Docker» se mantiene y D5, D6 y D7 quedan confirmadas con los ajustes de la sección
[Hallazgos para la Tarea 9](#hallazgos-para-la-tarea-9).

| Objetivo | Resultado | Evidencia en el log |
|---|---|---|
| (a) Hacerse visible y emparejable | OK | `CAMBIO hci0: {'Discoverable': True}`; el celular encontró «T0poL» |
| (b) Mostrar el código de 6 dígitos | OK | `>>> CODIGO DE EMPAREJAMIENTO: 039047 <<<`, luego `Bonded` y `Paired` |
| (c) Registrar el UUID y recibir una conexión RFCOMM | OK por el UUID SPP; el UUID del proyecto se registró pero **no** recibió conexión (ver hallazgo 2) | `PERFIL SPP: NewConnection … fd=8->9` |
| (d) Eco de lo que llega | OK | `<- b'hola\r\n'` / `-> b'eco: hola\r\n'` |

## Entorno

- Host: CachyOS (kernel 7.3.1), KDE, BlueZ **5.87**, `dbus-broker` como bus de sistema, Docker 29.9.3, Compose 5.7.0.
- Adaptador: `hci0`, alias «T0poL». `bluetoothd` corre en el host; el contenedor no tiene BlueZ.
- Contenedor: imagen `pybase` + `dbus-fast` 5.2.0 (extra `bluez` de `server/pyproject.toml`), Python 3.12, usuario `1000:1000` (no root).
- Celular: HUAWEI P9 lite (Android) con una app de terminal serial Bluetooth clásico.

## Flags finales de compose

Servicio `bt-spike` (perfil `spike`) tal como se probó con el celular:

```yaml
  bt-spike:
    profiles: ["spike"]
    build:
      context: .
      dockerfile: docker/pybase/Dockerfile
      args:
        EXTRAS: "dev,bluez"          # instala dbus-fast
    user: "${PUID:-1000}:${PGID:-1000}"
    working_dir: /work
    network_mode: host
    cap_add: [NET_ADMIN, NET_RAW]
    stdin_open: true
    tty: true
    volumes:
      - ./:/work
      - /var/run/dbus:/var/run/dbus
    environment:
      DB_DSN: 127.0.0.1:1521/XE      # con red host no existe el nombre "oracle"
      DB_USER: ${DB_USER}
      DB_PASSWORD: ${DB_PASSWORD}
      PYTHONPATH: /work/server
```

`docker/pybase/Dockerfile` ganó `ARG EXTRAS=dev`; `pybase` se construye igual que antes.

**Lo único imprescindible es el montaje `/var/run/dbus:/var/run/dbus`.** La comprobación en seco
(`--check`: leer el adaptador, registrar agente y perfiles) también pasó con red `bridge`,
`--cap-drop ALL` y solo ese montaje. `network_mode: host` y `cap_add` no aportan nada al camino
D-Bus: el proceso corre como uid 1000 (las capacidades añadidas no son efectivas para un usuario
no root) y el socket RFCOMM llega ya conectado como descriptor de archivo. La prueba completa con
el celular **solo** se hizo con las flags del plan; la configuración mínima no se probó de extremo
a extremo.

## Qué funcionó

1. **D-Bus sin política extra.** La política que instala BlueZ en el host
   (`/usr/share/dbus-1/system.d/bluetooth.conf`) permite `send_destination="org.bluez"` a cualquier
   usuario, y a root (bluetoothd) llamar a `org.bluez.Agent1` y `org.bluez.Profile1`. El uid 1000
   del contenedor se autentica por las credenciales del socket.
2. **Agente** `org.bluez.Agent1` exportado con `dbus-fast`, registrado con capacidad `DisplayYesNo`
   y `RequestDefaultAgent`. `RequestConfirmation(device, passkey)` recibió el código, lo mostró y
   esperó la respuesta del usuario (14 s) sin que BlueZ cancelara.
3. **Adaptador**: `Pairable=True`, `DiscoverableTimeout=120`, `Discoverable=True` por
   `org.freedesktop.DBus.Properties.Set`. BlueZ lo devolvió solo a no visible a los ~120 s.
4. **Perfil RFCOMM**: `ProfileManager1.RegisterProfile(path, uuid, {Role: "server", …})`.
   Ambos UUID aparecen en `Adapter1.UUIDs` (y en `bluetoothctl show` del host).
5. **`NewConnection(device, fd, props)`**: con `MessageBus(negotiate_unix_fd=True)` el argumento
   `h` llega como descriptor real. Se usó con `os.dup`, `os.read` y `os.write` sin crear ningún
   socket `AF_BLUETOOTH` en el contenedor. `props` llegó vacío.
6. **Oracle desde red host**: con `network_mode: host`, `oracledb` conecta a `127.0.0.1:1521/XE`
   (el puerto que publica el servicio `oracle`).

## Hallazgos para la Tarea 9

1. **Hay que pasar `Channel`.** Para un UUID que BlueZ no conoce, `RegisterProfile` sin la opción
   `Channel` registra el servicio pero **no abre ningún listener RFCOMM** (`src/profile.c`: el canal
   solo sale de la tabla de perfiles conocidos o de la opción). El spike usa `Channel = 22` (uint16)
   para el UUID del proyecto. El SPP estándar sí trae canal por defecto.
2. **Las apps de terminal serial solo conectan al UUID SPP** (`00001101-0000-1000-8000-00805f9b34fb`).
   Por eso el spike registra dos perfiles y la conexión entró por `PERFIL SPP`. Consecuencias:
   - El paso 5 de la Tarea 9 (prueba manual con la app de terminal) necesita que el transporte
     registre también el SPP, o que `controller_cli.py` use `BluezTransport(service_uuid=<SPP>)`.
   - **Sin verificar:** una conexión real al UUID del proyecto
     (`7a1c0b52-4f0e-4d6a-9c3b-5e2a6d9f1b01`, canal 22). El código de BlueZ es el mismo, pero la
     primera prueba real será la app Android propia (Tareas 14 y 15).
3. **El agente por defecto recibe `AuthorizeService` de todos los perfiles, no solo del nuestro.**
   Tras emparejar, el celular pidió Manos libres (`0000111e`) y A2DP (`0000110d`) y el spike los
   autorizó. `BluezTransport` debe autorizar solo sus UUID y rechazar el resto con
   `org.bluez.Error.Rejected`; de lo contrario el PC queda como dispositivo de audio del celular.
   Mientras el agente del spike está registrado sustituye al de KDE; al retirarlo vuelve el de KDE.
4. **`AuthorizeService` se llama en cada conexión** mientras el dispositivo no sea `Trusted`
   (el perfil tiene autorización activada por defecto). Hay que implementarlo en el agente o
   registrar el perfil con `RequireAuthorization = false`.
5. **El código puede empezar por cero**: `passkey` es un entero (`39047`); se muestra con
   `f"{passkey:06d}"` → `039047`.
6. **`DiscoverableTimeout` limita el descubrimiento, no el emparejamiento.** El PC dejó de ser
   visible a las 20:20:40 y el emparejamiento llegó a las 20:20:51 y se completó (el celular ya lo
   había encontrado). Para cumplir «si nadie empareja a tiempo vuelve a `IDLE`», el controlador debe
   cerrar la ventana por su cuenta: retirar agente y perfil (o `Pairable=False`) al vencer el plazo.
7. **La app de terminal envía `\r\n`.** El protocolo termina las líneas en `\n`; para la prueba
   manual hay que configurar la app para enviar solo LF, o el `\r` quedará pegado al CRC.
8. **El emparejamiento vive en el host** (`/var/lib/bluetooth`), no en el contenedor: sobrevive a
   `--rm`. El celular quedó emparejado (`Paired=True`, `Trusted=False`). Para repetir la prueba del
   código: `bluetoothctl remove <MAC>` en el host y «Olvidar» en el celular.
9. **rfkill**: al empezar el adaptador estaba `PowerState: off-blocked` (bloqueo por software).
   Se encendió desde el escritorio antes de la prueba. `BluetoothUnavailable` debería cubrir ese
   estado con un mensaje claro (`rfkill unblock bluetooth`).
10. **El reloj del contenedor está en UTC** (las horas del log van 5 h por delante de la hora local).
11. **El fd**: el spike duplica el descriptor (`os.dup`) antes de salir del manejador y trabaja con
    la copia. No se comprobó si `dbus-fast` cierra el original.

## No verificado

- Conexión del celular al UUID del proyecto (hallazgo 2).
- La prueba completa con la configuración mínima (sin `network_mode: host` ni `cap_add`).
- Encender el adaptador desde el contenedor (`Powered=True`) y el comportamiento con rfkill activo.
- Rechazar el código en el PC (`n`), el aviso `Cancel`, y un segundo celular a la vez (D19).
- La limpieza tras Ctrl-C en la corrida real (volver a no visible, restaurar `DiscoverableTimeout`
  a 180, retirar perfiles y agente). En `--check` sí se comprobó que se retiran agente y perfiles.
- La integración con Qt/X11 en el mismo contenedor (Tarea 13).

## Log

Corrida real del paso 4 (`.superpowers/spike-bluez.log`; direcciones MAC enmascaradas, horas en UTC):

```text
$ docker compose --profile spike run --rm bt-spike python server/spikes/bluez_echo.py
20:18:37 === bluez_echo.py  uid=1000 pid=1 ===
20:18:37 D-Bus de sistema conectado como :1.3143
20:18:37 Adaptador hci0: T0poL [B8:1E:XX:XX:XX:D0] Powered=True PowerState=on Discoverable=False Pairable=True DiscoverableTimeout=180
20:18:37 Agente registrado (DisplayYesNo) y puesto por defecto
20:18:37 Perfil APP registrado: uuid=7a1c0b52-4f0e-4d6a-9c3b-5e2a6d9f1b01 canal=22
20:18:37 Perfil SPP registrado: uuid=00001101-0000-1000-8000-00805f9b34fb canal=por defecto de BlueZ
20:18:37 Adapter1.UUIDs contiene APP (7a1c0b52-4f0e-4d6a-9c3b-5e2a6d9f1b01): True
20:18:37 Adapter1.UUIDs contiene SPP (00001101-0000-1000-8000-00805f9b34fb): True
20:18:37 CAMBIO hci0: {'Discoverable': True}
20:18:37 VISIBLE como «T0poL» [B8:1E:XX:XX:XX:D0] durante 120 s. Empareja desde el celular. Ctrl-C para terminar.
20:20:40 CAMBIO hci0: {'Discoverable': False}
20:20:51 AGENTE: RequestConfirmation de HUAWEI P9 lite [DC:D9:XX:XX:XX:24] Paired=False Trusted=False
20:20:51 AGENTE: >>> CODIGO DE EMPAREJAMIENTO: 039047 <<<
20:21:05 AGENTE: aceptado en el PC
20:21:05 CAMBIO dev_DC_D9_XX_XX_XX_24: {'Bonded': True}
20:21:06 CAMBIO dev_DC_D9_XX_XX_XX_24: {'Paired': True}
20:21:06 AGENTE: AuthorizeService uuid=0000111e-0000-1000-8000-00805f9b34fb de HUAWEI P9 lite [DC:D9:XX:XX:XX:24] Paired=True Trusted=False -> autorizado
20:21:07 AGENTE: AuthorizeService uuid=0000110d-0000-1000-8000-00805f9b34fb de HUAWEI P9 lite [DC:D9:XX:XX:XX:24] Paired=True Trusted=False -> autorizado
20:21:44 AGENTE: AuthorizeService uuid=00001101-0000-1000-8000-00805f9b34fb de HUAWEI P9 lite [DC:D9:XX:XX:XX:24] Paired=True Trusted=False -> autorizado
20:21:44 PERFIL SPP: NewConnection de HUAWEI P9 lite [DC:D9:XX:XX:XX:24] Paired=True Trusted=False fd=8->9 props={}
20:21:46 ECO SPP: <- b'hola\r\n'
20:21:46 ECO SPP: -> b'eco: hola\r\n'
```

Comprobación en seco previa (solo D-Bus, sin tocar la radio):

```text
$ docker compose --profile spike run --rm -T bt-spike python server/spikes/bluez_echo.py --check
20:16:18 D-Bus de sistema conectado como :1.2840
20:16:18 Agente registrado (DisplayYesNo) y puesto por defecto
20:16:18 Perfil APP registrado: uuid=7a1c0b52-4f0e-4d6a-9c3b-5e2a6d9f1b01 canal=22
20:16:18 Perfil SPP registrado: uuid=00001101-0000-1000-8000-00805f9b34fb canal=por defecto de BlueZ
20:16:18 --check: D-Bus OK (lectura, agente y perfiles). No se tocó la radio.
20:16:18 Limpieza hecha: perfiles y agente retirados
```

## Cómo repetirlo

```bash
docker compose --profile spike build bt-spike
docker compose --profile spike run --rm bt-spike python server/spikes/bluez_echo.py
```

Opciones del script: `--check` (solo D-Bus), `--yes` (acepta el código sin preguntar),
`--no-spp` (registra solo el UUID del proyecto), `--log RUTA`.
