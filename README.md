# Inventario físico offline: APK → Bluetooth → Oracle → App de escritorio

Un operador cuenta productos con una **APK Android** sin red (escáner de códigos de barras o digitando el SKU). Cuando
está cerca del PC, el conteo sube por **Bluetooth** al PC, que lo guarda en **Oracle 11g** y dispara el **batch
PL/SQL** que lo concilia contra el stock del sistema. Una sola **aplicación de escritorio** lo muestra. El conteo es **continuo**:
siempre está abierto y el inventario se actualiza a medida que el batch procesa las lecturas. Todo el lado PC corre en Docker sobre Linux.

- Cómo está hecho (capas, decisiones, tablas, matriz de permisos y los 22 diagramas UML): [docs/arquitectura.md](docs/arquitectura.md)
- Guion de demo de 5 minutos: [docs/demo.md](docs/demo.md)
- Protocolo de líneas: [docs/protocolo.md](docs/protocolo.md) · Bluetooth desde contenedor: [docs/spikes/bluez.md](docs/spikes/bluez.md)
- Interactividad del escritorio (atajos, gestos móviles, estados, flujos y checklist): [docs/interactividad/00-entorno-y-decisiones.md](docs/interactividad/00-entorno-y-decisiones.md)

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

La primera vez descarga la imagen y crea la base con el esquema, la semilla (conteo continuo `ACTUAL` con 58 SKU),
el paquete `PKG_BATCH`, los jobs del Scheduler y las vistas: puede tardar varios minutos. La semilla no trae cuentas:
la primera que crees queda como Administrador y Activa.

```bash
docker compose up -d bluetooth app
```

`bluetooth` es el **servicio de recepción**: corre aparte, recibe a los teléfonos aunque la ventana del escritorio esté
cerrada y vuelve a arrancar solo tras reiniciar el PC (si Docker arranca con el sistema). La pantalla
**Sincronización** muestra su estado y lo pausa o reanuda.

La aplicación de escritorio se abre **en tu pantalla** por X11 y muestra el acceso: crea la primera cuenta (queda como
Administrador y Activa) e inicia sesión. Con `up -d` no ves sus mensajes; para verlos usa `docker compose logs -f app`.

**Si tu sesión es Wayland sin XWayland** (no existe `/tmp/.X11-unix`), la ventana no puede abrirse por el compose
normal. En ese caso usa el lanzador incluido:

```bash
tools/run_escritorio_wayland.sh
```

Añade una capa de imagen con `libwayland-cursor0` (una sola vez), corre la app en la red interna de Compose para
llegar a `oracle:1521` y monta el socket Wayland de tu sesión. La ventana queda abierta en segundo plano; se cierra
cerrando la ventana o con `docker rm -f app-wayland`. El servicio Bluetooth no hace falta para abrirla: la app lee su
estado de Oracle.
El lanzador usa el mismo wrapper `docker/run-app.sh` que el servicio `app`, así que el arranque y el log
persistente (`./logs/app.log`) son los mismos.
Si el puerto publicado `127.0.0.1:1521` está atascado en tu Docker, este camino también lo evita.

Para no usar Bluetooth (pruebas y plan B de la demo):

```bash
BT_TRANSPORT=tcp docker compose up -d bluetooth app
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
> **Toda cuenta nueva espera aprobación.** Las del PC quedan **PENDIENTES** hasta que el Administrador las apruebe en
> **Solicitudes**; solo la primera cuenta del PC es el Administrador y no se pueden crear más. Las del teléfono llegan
> al PC al sincronizar y solo pueden aprobarse como **Operador de Inventario**. Una cuenta rechazada o suspendida ve
> el motivo en la pantalla de estado. Las cuentas del PC piden correo obligatorio y único; las del teléfono lo aceptan
> opcional. El acceso es con usuario y contraseña: el correo es un dato de la cuenta. La contraseña del Operador es
> local y se recupera con su pregunta de seguridad.
>
> **El Operador no ve la cantidad del sistema.** El catálogo que baja al teléfono nunca lleva el stock; el conteo es
> ciego.
>
> **Solo se sincroniza un teléfono a la vez** (D19): un segundo teléfono recibe «PC ocupado» y debe esperar.

### Uso en una frase

En el celular: crear cuenta con usuario, nombre, correo opcional y pregunta de seguridad (queda pendiente: sincroniza
una vez y apruébala en **Solicitudes** del PC) o iniciar sesión → **Catálogo** → contar escaneando el código de barras
o el QR, o digitando el SKU → guardar (sin red). El PC se anuncia siempre como `gestion_inventario` mientras el
servicio `bluetooth` esté activo. En el celular: **Sincronizar**; la primera vez se busca y se elige
`gestion_inventario`, y desde entonces conecta directo, sin claves ni códigos (D22).

### Conteo continuo

El operador cuenta directamente del catálogo y el batch va conciliando contra `ACTUAL`. Si un SKU no tiene lectura, la cantidad contada se
muestra vacía (no en 0). El Dashboard muestra el avance (SKUs con lectura vigente sobre el total), el estado del batch y la diferencia por
categoría como referencia; el Inventario muestra SKU, producto, categoría, cantidad contada y cantidad del sistema,
sin diferencia, porcentaje ni clasificación en las filas. Las lecturas con problemas quedan en error y se ven en **Sincronización**; el Administrador puede dar de
alta el SKU desde el detalle del error y **Reprocesar errores**.

### Configuración y respaldos

En **Configuración** (Administrador) se cambian el intervalo del lote y el tamaño máximo de foto. La carpeta de fotos
se muestra pero no se edita. En **Respaldos** se crea un respaldo (`.zip` con todos los datos y las fotos, en
`respaldos/`, o `RESPALDOS_DIR`), se programa el automático diario y se **restaura**: escribe `RESTAURAR` para
confirmar; antes se pausa el servicio Bluetooth y se guarda un respaldo del estado actual («Antes de restaurar»). Al
terminar se cierra la sesión; reanuda el servicio en **Sincronización**.

## Roles y permisos

| Rol | Dónde entra | Qué puede hacer |
|---|---|---|
| **Administrador** | Solo escritorio | Todo: inventario completo, solicitudes, empleados, roles y permisos, auditoría, configuración, sincronización, respaldos, notificaciones y perfil. Hay **uno solo** y su fila de la matriz está bloqueada. |
| **Inventario** | Solo escritorio | Dashboard, inventario completo, gráficas, sincronización, notificaciones y perfil. No administra cuentas, permisos, configuración ni respaldos. |
| **Operador de Inventario** | Solo móvil | Catálogo, contar, contado, pendientes, sincronizar, notificaciones y mi cuenta. No ve la cantidad del sistema ni entra al escritorio. |

La captura es exclusiva del Operador: ni el Administrador ni Inventario cuentan desde el escritorio.

La matriz rol × módulo tiene **12 módulos**: Dashboard, Inventario, Gráficas, Sincronización, Notificaciones, Perfil,
Solicitudes, Empleados, Roles y permisos, Auditoría, Configuración y Respaldos. Los cambios rigen desde el próximo
inicio de sesión para la barra lateral y se revalidan en vivo en las acciones que cambian datos. **Perfil** se abre
desde el pie de la barra, y la campana aparece solo si el rol tiene acceso a Notificaciones.

## Foto, tema e idioma

En **Perfil** (escritorio) y **Mi cuenta** (móvil) cada usuario pone, edita o elimina su foto con un editor de rotar,
zoom, recortar y vista previa; el avatar se muestra circular y el archivo se guarda cuadrado. Se validan JPEG, PNG y
WebP; en el escritorio vale el tamaño máximo configurado (2 MB por defecto) y en el teléfono, 2 MB. El tema (claro, sistema u oscuro) y el idioma (español o inglés) se aplican de
inmediato y se guardan por usuario. El cambio de contraseña del Administrador es directo; el de Inventario queda
pendiente de aprobación en **Solicitudes**. El Operador recupera su contraseña localmente con la pregunta de seguridad
del teléfono; el Administrador no puede resetearla desde el PC. Si el Administrador olvida la suya, en **Acceso** usa
«¿Olvidaste tu contraseña?» y responde su pregunta de seguridad; se aplica al momento, sin pasar por Solicitudes.

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

Los diagramas UML se regeneran con `tools/render_uml.sh` y los tests de clases los comprueba
`server/tests/test_uml.py`.

## Solución de problemas

Si la ventana no aparece, el servicio `app` deja su arranque en `./logs/app.log` del host (y en `docker compose logs app`):
cabecera con `DISPLAY`/`XAUTHORITY`/estado de la cookie, salida de Python y `rc` final. Si falla al arrancar se
reintenta solo hasta 5 veces; cerrar la ventana la deja parada. Si el contenedor se paró con
`docker compose stop`/`down` verás una cabecera sin la línea `fin rc=`: es una parada externa, normal. Tras agotar
los 5 reintentos, corrige la causa y vuelve a arrancarla con `docker compose up -d app`. Si el contenedor se creó
con un entorno X inválido, recréalo desde una terminal con `DISPLAY` y `XAUTHORITY` válidos:
`docker compose up -d --force-recreate app`.

| Síntoma | Qué hacer |
|---|---|
| «Bluetooth no disponible» / `NotReady` en la ventana de sincronización | El adaptador está bloqueado o apagado: `rfkill list`; si dice `Soft blocked: yes`, `rfkill unblock bluetooth`, y luego `bluetoothctl power on`. Comprueba `systemctl status bluetooth`. |
| «El servicio Bluetooth no está corriendo» | Arráncalo: `docker compose up -d bluetooth`; sus mensajes: `docker compose logs -f bluetooth`. |
| El celular no encuentra `gestion_inventario` | El servicio `bluetooth` debe estar activo y sin pausa (pantalla **Sincronización**). En Android 10 o anterior la **ubicación** del teléfono debe estar encendida para buscar dispositivos Bluetooth. |
| El celular dice «No se pudo conectar con el PC» | El PC está apagado, lejos, o el servicio está detenido o en pausa. La app reintenta 3 veces; vuelve a pulsar **Sincronizar** tras reanudarlo. |
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
docs/               arquitectura, protocolo, demo, interactividad, spikes, UML (docs/uml) y sus SVG (docs/img/uml)
```
