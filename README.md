# Inventario físico offline: APK → Bluetooth → Oracle → App de escritorio

Un operario cuenta productos con una **APK Android** sin red (escáner de códigos de barras o digitando el SKU). Cuando
está cerca del PC, el conteo sube por **Bluetooth** a **una sola aplicación de escritorio** que lo guarda en
**Oracle 11g**, dispara el **batch PL/SQL** que lo concilia contra el stock del sistema y muestra y grafica las
diferencias. Todo el lado PC corre en Docker.

- Cómo está hecho (capas, decisiones D1–D22, límites y los 22 diagramas UML): [docs/arquitectura.md](docs/arquitectura.md)
- Guion de demo de 5 minutos: [docs/demo.md](docs/demo.md)
- Protocolo de líneas: [docs/protocolo.md](docs/protocolo.md) · Bluetooth desde contenedor: [docs/spikes/bluez.md](docs/spikes/bluez.md)
- Plan de implementación: `docs/superpowers/plans/2026-11-09-captura-movil-bluetooth-oracle.md`

> Las rutas del proyecto pueden tener espacios (`/home/t1an/movil oracle bluetooth`): entrecomíllalas.

## Requisitos del host

- Linux x86_64 con **Docker** y **Docker Compose** (Oracle XE 11g solo existe para x86_64).
- Para el **Bluetooth real**: BlueZ (`bluetoothd`) activo en el host y un adaptador (`hci0`) encendido.
  `bluetoothd` y `adb` viven en el host; el resto corre en contenedores.
- Para ver la ventana: una sesión gráfica X11 o Wayland con XWayland (`DISPLAY`).
- Para instalar la APK: `adb` en el host y un celular **Android 6.0 o superior** con la depuración USB activa.

## Puesta en marcha

```bash
cp .env.example .env
```

```bash
docker compose up -d --wait oracle
```

La primera vez descarga la imagen y crea la base con el esquema, la semilla (conteo `CONT-2026-11`, 58 SKU), el
paquete `PKG_BATCH`, los jobs del Scheduler y las vistas: puede tardar varios minutos.

```bash
docker compose up -d app
```

La aplicación de escritorio se abre **en tu pantalla** por X11 y muestra el acceso: crea tu cuenta (la primera queda como administrador) e inicia sesión. Con `up -d` no ves
sus mensajes; para verlos usa `docker compose logs -f app`. Para no usar Bluetooth (pruebas y plan B de la demo):

```bash
BT_TRANSPORT=tcp docker compose up -d app
```

### Compilar e instalar la APK

La APK se compila en Docker (JDK 17 + Android SDK + Gradle), sin instalar nada en el host:

```bash
docker compose --profile build run --rm apk-build ./gradlew assembleDebug
```

Con el celular conectado por USB:

```bash
adb install -r mobile/app/build/outputs/apk/debug/app-debug.apk
```

> **No desinstales la APK con lecturas pendientes:** la bandeja de salida vive en el teléfono y se borra con la
> aplicación (D18). Reinstalar crea un dispositivo nuevo con `seq` desde 1.
>
> **Toda cuenta nueva espera aprobación.** Las del PC (Administrador, Inventario) y las del teléfono (Operador de
> Inventario) quedan **PENDIENTES** hasta que el administrador las aprueba en **Solicitudes**; también puede rechazarlas
> o suspenderlas con un motivo que la persona ve al intentar entrar. La cuenta del teléfono llega al PC al sincronizar
> (su contraseña nunca sale del teléfono; se recupera con la pregunta de seguridad). Qué ve cada rol se ajusta en
> **Roles y permisos**.
>
> **Categorías, almacenes y existencias** (Fase 2) se crean solos al arrancar la app con datos de ejemplo: dos almacenes
> (`ALM-01`, `ALM-02`) y las existencias del conteo más reciente en `ALM-01`.
>
> **Tareas de conteo** (Fase 3): Inventario las crea en el PC (almacén, operador, productos e instrucciones) y el operador
> las ve en **Mis tareas** del celular tras sincronizar. El estado (Asignada, En progreso, Enviada parcialmente,
> Sincronizada, Con diferencias, Con error, Cerrada) se actualiza solo. Las diferencias se revisan en **Diferencias**.
> El celular y el PC deben tener la misma versión del protocolo (4): una APK anterior recibe «formato inválido».
>
> **Movimientos y ajustes** (Fase 3b): Inventario registra entradas y salidas en **Movimientos** (cambian la existencia
> al momento) y solicita ajustes en **Ajustes** o desde **Diferencias**. Un ajuste que cambia 10 % o más, o vale
> $200.000 o más, espera la aprobación del Administrador.
>
> **Fotos, dañados y auditoría** (Fase 4, protocolo 5): en «Contar» el operador puede indicar dañados y adjuntar una
> foto (cámara o galería). Las fotos viajan después de las lecturas y quedan en `fotos/` (carpeta del PC, fuera de git;
> otra ruta con `FOTOS_DIR`); en **Diferencias** el 📷 las abre. **Auditoría** muestra quién hizo qué y cuándo.
>
> **Solo se sincroniza un teléfono a la vez** (D19): un segundo teléfono recibe «PC ocupado» y debe esperar.

### Uso en una frase

En el celular: crear cuenta (queda pendiente: sincroniza una vez y apruébala en **Solicitudes** del PC) o iniciar sesión → **Mis tareas** → iniciar una → escanear el código de barras o el QR, o digitar → guardar (sin red). En el PC: **Iniciar
sincronización** (el PC se anuncia como `gestion_inventario` durante 120 s). En el celular: **Sincronizar**; la primera
vez se busca y se elige `gestion_inventario`, y desde entonces conecta directo, sin claves ni códigos (D22).

## Pruebas

```bash
docker compose run --rm pybase pytest server/tests -v
```

```bash
docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -v
```

```bash
docker compose --profile build run --rm apk-build ./gradlew testDebugUnitTest
```

Las suites del servidor y del escritorio borran por diseño el staging de los dispositivos de prueba (`tst-%`,
`dev-e2e%`). Los diagramas UML se regeneran con `tools/render_uml.sh` y los tests de clases los comprueba
`server/tests/test_uml.py`.

## Solución de problemas

| Síntoma | Qué hacer |
|---|---|
| «Bluetooth no disponible» / `NotReady` en la ventana de sincronización | El adaptador está bloqueado o apagado: `rfkill list`; si dice `Soft blocked: yes`, `rfkill unblock bluetooth`, y luego `bluetoothctl power on`. Comprueba `systemctl status bluetooth`. |
| El celular no encuentra `gestion_inventario` | La ventana de sincronización debe estar abierta en el PC (120 s). En Android 10 o anterior la **ubicación** del teléfono debe estar encendida para buscar dispositivos Bluetooth. |
| El celular dice «No se pudo conectar con el PC» | El PC está apagado, lejos, o la sincronización no está iniciada. La app reintenta 3 veces; vuelve a pulsar **Sincronizar** tras iniciarla en el PC. |
| «El PC está atendiendo a otro teléfono» | Hay otra sincronización en curso (D19). Espera a que termine. |
| `could not connect to display` / la ventana no aparece | Compose monta el socket X11 y la cookie de `$XAUTHORITY`: comprueba `echo $DISPLAY $XAUTHORITY` en la terminal desde la que lanzas `docker compose`. Como último recurso, `xhost +local:` da acceso X a los usuarios locales (revierte con `xhost -local:`). |
| `ORA-12541`, `ORA-12514` o «connection refused» al abrir la app | Oracle aún no está listo: `docker compose ps` debe mostrar `oracle` como `healthy`; si no, `docker compose logs oracle`. |
| `ORA-12516` | Demasiadas conexiones simultáneas al listener. La app usa una conexión por hilo; si ocurre, `docker compose restart oracle` y vuelve a abrir la app. |
| `DPI-1050` u `ORA-28040` al conectar | Incompatibilidad del Instant Client con Oracle 11g: cambia `IC_DIR`, `IC_FILE` e `IC_FOLDER` en `docker/pybase/Dockerfile` al Instant Client 12.2 (hay un comentario con el plan B) y reconstruye con `docker compose build pybase`. |
| `adb install` falla con `INSTALL_FAILED_OLDER_SDK` | El celular es anterior a Android 6.0 (la APK exige `minSdk 23`). |
| Tras cerrar la app a la fuerza el PC sigue llamándose `gestion_inventario` | La siguiente vez que se abre la ventana lo detecta y restaura el nombre; a mano: `bluetoothctl system-alias <nombre del PC>`. |
| Quiero empezar con la base limpia | `docker compose down`, `docker volume rm inventario-bt_oracle-data` y `docker compose up -d --wait oracle` (**borra todos los datos de Oracle**; `docker compose down -v` borra además la caché de Gradle). |

## Estructura

```
docker-compose.yml  .env.example
db/init/            esquema, semilla, PKG_BATCH, jobs, vistas (se ejecutan al crear Oracle)
server/btsync/      protocolo, sesión, controlador y transportes (BlueZ, TCP) — librería Python
desktop/app/        aplicación de escritorio (PyQt6 + pyqtgraph)
mobile/             APK Android (Kotlin, Room, ZXing) y su Dockerfile de compilación
tools/              datos semilla, teléfono simulado (fake_phone.py), verificación y render de UML
docs/               arquitectura, protocolo, demo, spikes, UML (docs/uml) y sus SVG (docs/img/uml)
```
