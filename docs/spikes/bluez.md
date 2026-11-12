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

---

# Tarea 9: `BluezTransport` (código de producción)

`server/btsync/transports/bluez.py` implementa el contrato `Transport` con lo que este spike
demostró. Qué hizo con cada hallazgo:

| Hallazgo | Decisión en `BluezTransport` |
|---|---|
| 1. `Channel` obligatorio | Canal 22 para el UUID propio; el SPP usa el canal por defecto de BlueZ |
| 2. Las apps de terminal solo usan SPP | El transporte registra **un** UUID (`service_uuid`). Producción: el propio. La prueba manual usa `controller_cli.py --spp` |
| 3 y 4. `AuthorizeService` de todos los perfiles, en cada conexión | Solo se autoriza el UUID propio y solo a dispositivos emparejados; lo demás (manos libres, A2DP…) se rechaza con `org.bluez.Error.Rejected`. El dispositivo **no** se marca `Trusted` |
| 5. El código puede empezar por cero | `f"{passkey:06d}"` |
| 6. `DiscoverableTimeout` no cierra el emparejamiento | `stop()` retira perfil y agente y deja `Discoverable`, `DiscoverableTimeout` y `Pairable` como estaban; lo llama el controlador al vencer el plazo |
| 7. La app de terminal envía `\r\n` | La conexión convierte `\r\n` en `\n`: no hace falta configurar la app |
| 9. rfkill | `BluetoothUnavailable` con el mensaje «…ejecuta: rfkill unblock bluetooth». El transporte **no** enciende el adaptador |
| 11. El descriptor | `dbus-fast` 5.2.0 nunca cierra los descriptores recibidos (se revisó su código): el transporte se adueña del `fd` sin duplicarlo. El `os.dup` del spike dejaba uno abierto por conexión |

**Nombre Bluetooth (D21):** mientras la ventana está abierta el adaptador se llama
`gestion_inventario` (`Adapter1.Alias`); al cerrar recupera su nombre. BlueZ aplica el cambio de
nombre de forma asíncrona: justo después de `stop()` todavía puede leerse el nombre anterior.

Además: una segunda conexión mientras hay una activa recibe `NAK|0|OCUPADO` (D19); si el teléfono
cancela el emparejamiento (`Agent1.Cancel`) el controlador deja de mostrar el código y sigue
esperando; un emparejamiento sin código (`RequestAuthorization`) se rechaza.

## Verificado

- **Sin hardware** (`docker compose run --rm pybase pytest server/tests/test_bluez.py -v` → 25 passed):
  con un bus D-Bus falso que hace de `bluetoothd`, incluido el ciclo completo con `SyncController`.
- **Contra el BlueZ real, con el adaptador bloqueado por rfkill** (2026-11-10, sin celular):

  ```text
  $ docker compose --profile spike run --rm -T --no-deps bt-spike python server/spikes/controller_cli.py --check
  00:55:28 ANTES   Discoverable=False DiscoverableTimeout=180 Pairable=True servicio_registrado=False
  [bluez] ventana cerrada: servicio y agente retirados
  00:55:28 BLUETOOTH NO DISPONIBLE: El Bluetooth está bloqueado. En el host ejecuta: rfkill unblock bluetooth
  00:55:28 CERRADO Discoverable=False DiscoverableTimeout=180 Pairable=True servicio_registrado=False
  ```

- **Contra el BlueZ real, con la radio encendida y sin celular** (2026-11-10):

  ```text
  $ docker compose --profile spike run --rm -T --no-deps bt-spike python server/spikes/controller_cli.py --check --spp
  01:45:28 ANTES   Alias='T0poL' Discoverable=False DiscoverableTimeout=180 Pairable=True servicio_registrado=False
  01:45:28 ABIERTO Alias='gestion_inventario' Discoverable=True DiscoverableTimeout=120 Pairable=True servicio_registrado=True
  01:45:28 CERRADO Alias='T0poL' Discoverable=False DiscoverableTimeout=180 Pairable=True servicio_registrado=False
  01:45:28 --check: OK, la ventana se abre y todo vuelve a quedar como estaba
  ```

  Lo mismo sin `--spp` (UUID propio, canal 22): `servicio_registrado=True` con la ventana abierta.
- **Cierre por tiempo en el BlueZ real**: una ventana de 300 s sin conexiones terminó sola en
  `IDLE` con `TIEMPO_AGOTADO: nadie se conectó en 300 s`, y el adaptador quedó no visible y sin
  el servicio (hallazgo 6 del spike, resuelto).

## Paso 5 con el celular: hecho (2026-11-11)

Corrida real con el HUAWEI P9 lite, `SyncController` + `BluezTransport` + Oracle, UUID serie
(`--spp`) y una app de terminal serial. Del log (`.superpowers/paso5-controller.log`, horas UTC):

```text
01:58:28 ESTADO ESPERANDO_EMPAREJAMIENTO (ventana 600 s)
01:59:20 ESTADO CONFIRMAR_CODIGO  >>> CÓDIGO DE EMPAREJAMIENTO: 480378 <<<
01:59:30 respuesta en el PC: aceptar            → ESPERANDO_EMPAREJAMIENTO (Paired, Bonded)
02:00:56 ESTADO CONECTADO                       (el celular abrió la conexión RFCOMM)
02:04:50 ESTADO RECIBIENDO                      (HELLO)
02:12:59 ESTADO RECIBIENDO recibidos=1          (REC)
02:14:13 ESTADO PROCESANDO → LISTO              (END; el batch corrió con origen SYNC)
02:14:13 fila: ('p9lite', 1, 'PROCESADO', None, 'REC|1|1794358578881|CONT-2026-11|A-01|7701234000001|5|Ana|')
02:14:13 lectura procesada: ('CONT-2026-11', 'A-01', '7701234000001', 5.0, 'Ana', 'S')
```

Quedó comprobado: código de 6 dígitos mostrado y confirmado, autorización del servicio, conexión,
las tres líneas escritas a mano con su CRC, ACK/BYE del protocolo, batch disparado por el
controlador y conciliación. **Sigue sin verificarse** la conexión al UUID propio de la aplicación
(canal 22): la app de terminal solo usa el serie estándar; la primera prueba con el UUID propio
será la APK (Tareas 14 y 15). Tampoco se registraron las líneas `[bluez]` de esa corrida (se
imprimían solo en la terminal); desde ahora `controller_cli.py` las guarda también en el log.

### Hallazgos de la corrida real

1. **El código se pide una sola vez**, en el primer emparejamiento. Después el celular queda
   `Paired` y `Bonded` y se conecta sin código, hasta que alguno de los dos lados lo olvide. El
   dispositivo sigue `Trusted: no`: el agente autoriza en cada conexión solo el servicio propio.
2. **Emparejar no es conectar.** El PC solo espera; quien abre la conexión RFCOMM es el teléfono
   (en esta prueba, desde la app de terminal). La APK lo hará sola al pulsar «Sincronizar».
3. **Una copia que muere sin limpiar dejaba el adaptador sucio** (visible, con el nombre
   `gestion_inventario` y 600 s) y la siguiente copia lo tomaba como estado original. Reproducido
   con `docker stop` (Python como proceso 1 ignora SIGTERM; Docker lo mata a los 10 s). Corregido:
   `BluezTransport` detecta ese estado y restaura a los valores por defecto (nombre del sistema,
   no visible, 180 s) y `controller_cli.py` atiende SIGTERM. `docker stop` ahora limpia en 0,3 s.
   **Para la app de escritorio (Tarea 13):** al cerrar la ventana hay que llamar a
   `SyncController.cancel()`.

## Modo sin claves (D22, 2026-11-11)

A pedido del usuario el modo por defecto **no empareja ni usa claves**: `BluezTransport(require_pairing=False)`.

- El perfil se registra con `RequireAuthentication=False` y `RequireAuthorization=False`; no se registra
  agente (el agente del sistema, KDE, queda intacto) y se acepta la conexión de un dispositivo que nunca se
  emparejó. El PC sigue anunciándose como `gestion_inventario` mientras la ventana está abierta.
- Del lado del teléfono tiene que usarse un socket **inseguro** (Android:
  `createInsecureRfcommSocketToServiceRecord`); con uno seguro Android fuerza el emparejamiento y el PC
  volvería a mostrar un código (ahora el del sistema, no el nuestro). Muchas apps de terminal serial solo
  ofrecen el socket seguro: por eso esta ruta se prueba de verdad con la APK (Tareas 14 y 15).
- `controller_cli.py --con-clave` restaura el modo anterior (código de 6 dígitos y solo dispositivos emparejados).
- Verificado contra el BlueZ real sin celular (`--check`, con y sin `--con-clave`): BlueZ acepta el registro del
  servicio sin autenticación, la ventana se abre y todo queda como estaba. **No verificado:** una conexión real
  de un teléfono sin emparejar (hace falta un socket inseguro en el teléfono).
- **Costo de seguridad:** el enlace no va cifrado y cualquier dispositivo al alcance puede conectarse mientras
  la ventana esté abierta (ver D22 en el plan).

### Cómo se hizo (referencia)

Pasos:

1. Encender el Bluetooth del PC (o `rfkill unblock bluetooth`) y tener Oracle arriba
   (`docker compose up -d --wait oracle`).
2. Comprobación sin celular (el PC es visible menos de un segundo):
   `docker compose --profile spike run --rm -T bt-spike python server/spikes/controller_cli.py --check --spp`
   → debe terminar en `--check: OK`.
3. Para ver el código de 6 dígitos hay que desemparejar antes: `bluetoothctl remove <MAC>` en el PC
   y «Olvidar» en el celular. Si se deja emparejado, el celular se conecta directo, sin código.
4. `docker compose --profile spike run --rm bt-spike python server/spikes/controller_cli.py --spp --window 300`
5. En la app de terminal serial del celular, conectar al PC (aparece como `gestion_inventario`;
   si ya estaba emparejado puede seguir saliendo con el nombre anterior) y enviar estas tres
   líneas, una por una:

   ```text
   HELLO|1|p9lite|P9*CDC3CB89
   REC|1|1794358578881|CONT-2026-11|A-01|7701234000001|5|Ana|*71B76C22
   END|1*883D1CF6
   ```

   Resultado esperado: tras `HELLO` llegan `READY|0|…` y el catálogo; tras `END`, `ACK|1` y
   `BYE|1|0`. El script imprime los estados hasta `LISTO` y la fila de `CAPTURA_TRANSITO` en
   `PROCESADO`. El registro queda en `.superpowers/paso5-controller.log`.

Si hay que repetirlo, el `seq` 1 de `p9lite` ya estará usado (el servidor responde `READY|1|…`):
hay que generar líneas nuevas con otro nombre de dispositivo
(`python -m btsync.protocol --frame HELLO 1 p9lite2 P9`, etc.).
