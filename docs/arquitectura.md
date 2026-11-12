# Arquitectura

Sistema de **toma de inventario físico sin red**: un operario cuenta productos con una APK Android (escáner de
códigos de barras o digitación), el teléfono guarda todo localmente y, cuando está cerca del PC, lo sube por
**Bluetooth**. El PC corre **una sola aplicación de escritorio** que recibe el conteo, lo guarda en **Oracle 11g**,
dispara el **batch PL/SQL** que lo concilia contra el stock del sistema y muestra y grafica diferencias, exactitud y
avance. Todo el lado PC corre en Docker.

Los diagramas son fuente PlantUML en [`uml/`](uml/) (índice en [`uml/README.md`](uml/README.md)) y se incrustan aquí
como SVG. El formato de línea del protocolo está en [`protocolo.md`](protocolo.md) y la prueba de Bluetooth desde
contenedor en [`spikes/bluez.md`](spikes/bluez.md).

## 1. Capas

```
 ┌────────────┐  Bluetooth   ┌──────────────────────────────────────────────┐   SQL*Net   ┌─────────────────────┐
 │ APK Android│ ───RFCOMM──▶ │ App de escritorio (un proceso, en Docker)    │ ──────────▶ │ Oracle XE 11g       │
 │  Outbox    │  líneas+CRC  │  btsync: Transport → Session → Store         │             │  CAPTURA_TRANSITO   │
 │  (Room)    │ ◀──ACK/NAK── │  SyncController (dispara el batch, D9)       │             │  PKG_BATCH (batch)  │
 └────────────┘              │  Vistas PyQt6 + pyqtgraph (lee V_* de Oracle)│ ◀────────── │  CONCILIACION, V_*  │
                             └──────────────────────────────────────────────┘             └─────────────────────┘
```

| Capa | Dónde | Qué hace |
|---|---|---|
| 1. Captura móvil | `mobile/` | Cuenta sin red. Guarda **siempre primero** en la `Outbox` (Room/SQLite); nada depende de la conexión. |
| 2. Recepción Bluetooth | `server/btsync` (`transports`, `session`) | Acepta una conexión RFCOMM, valida cada línea (CRC, formato, secuencia), hace COMMIT cada 25 y responde `ACK`/`NAK`. |
| 3. Staging y batch | Oracle (`CAPTURA_TRANSITO`, `PKG_BATCH`, `DBMS_SCHEDULER`) | Valida y mueve lo recibido a `REGISTROS_PROCESADOS`, decide la lectura vigente y calcula `CONCILIACION`. |
| 4. Presentación | `desktop/app` | Lee las vistas `V_*`, muestra tarjetas, tablas y cinco gráficas, y es el botón que abre la sincronización. |

Las capas 2 y 4 son **un solo proceso** (D11): el botón «Iniciar sincronización» activa el servidor Bluetooth interno
(`SyncController`), la ventana muestra el estado y, cuando la sesión termina, el **controlador** (no la sesión)
ejecuta el batch y la ventana refresca. No hay API HTTP.

### Cómo viaja un dato

1. El operario guarda `(conteo, ubicación, SKU, cantidad)` → fila `PENDIENTE` en la `Outbox` con el reloj del teléfono.
2. Al sincronizar, el móvil manda `HELLO`; el PC responde `READY|<último seq>|<hora del servidor>` y el catálogo.
3. El móvil envía `REC` en ventanas de 50; el PC inserta en `CAPTURA_TRANSITO` (clave `(uuid, seq)`: idempotente),
   hace COMMIT cada 25 y responde `ACK|n` (acumulativo). Un `NAK|n|motivo` hace retroceder al móvil a `n` (go-back-N).
4. `END` → `ACK` final → `BYE`. La sesión termina; el controlador corre `PKG_BATCH.procesar_pendientes('SYNC')`.
5. El batch valida, inserta en `REGISTROS_PROCESADOS`, recalcula cuál lectura vale por `(conteo, ubicación, SKU)` y
   concilia. La app de escritorio consulta las vistas y repinta.

## 2. Patrones

**Escritorio: MVC con trabajadores.** *Modelo*: dataclasses de `models.py` más Oracle (las consultas salen de las
vistas `V_*`, funciones `fetch_*` de `db.py`). *Vista*: las seis pestañas de `views/`. *Controlador*: `SyncBridge`
(traduce los cambios de estado del `SyncController`, que vive en hilos propios, a señales Qt) y `QueryRunner`
(corre cada consulta en un `QueryWorker` y entrega el resultado al hilo de la interfaz). **Ninguna consulta corre en el
hilo de la UI**; cada hilo de trabajo usa su propia conexión Oracle y toda conexión pasa por `connect_oracle`, que las
serializa (abrir conexiones en paralelo con el cliente «thick» de Oracle abortaba el proceso).

**Android: MVVM.** *Vista*: las `Activity` (`ui/*Activity.kt`, vistas armadas en código). *ViewModel*:
`CountViewModel` (reglas de guardado, `StateFlow` de operador/conteo/ubicación) y `SyncViewModel` + `SyncRunner`
(reintentos y estado de la sincronización). *Modelo*: `Outbox` y catálogo (Room), `SyncClient` y `Protocol`. La lógica
está en clases sin dependencia de pantallas, así que se prueba en la JVM.

**Transporte intercambiable.** `Transport`/`Connection` (`btsync.transports.base`) tienen dos implementaciones:
`BluezTransport` (Bluetooth real por D-Bus) y `TcpTransport` (pruebas y plan B). Una sesión no sabe cuál usa.

**Protocolo idéntico en dos lenguajes.** `protocol.py` y `Protocol.kt` pasan los mismos 7 vectores de
[`protocol-vectors.json`](protocol-vectors.json); si uno falla, el protocolo es inconsistente.

## 3. Decisiones de diseño

| # | Decisión | Por qué |
|---|---|---|
| D1 | Tema: toma de inventario físico de una bodega o tienda (SKU, categoría, ubicación, costo). | Elegido por el usuario; caso real de terminal que cuenta offline y sube en lote. |
| D2 | «Oracle X11» = Oracle XE 11g. | 11g no tiene `IDENTITY` ni funciones JSON: se usan secuencia + trigger y un formato de texto con `\|`. |
| D3 | La GUI usa X11: la app corre en contenedor y se dibuja en la pantalla del host por el socket X11. | Cumple «todo en Docker» con app de escritorio. |
| D4 | Móvil: solo Android. | iOS no permite RFCOMM clásico a apps normales. |
| D5 | Emparejamiento nativo BlueZ con código de 6 dígitos. | **Sustituida por D22 como modo por defecto**; sigue disponible (`require_pairing`). |
| D6 | Servicio RFCOMM registrado por D-Bus (`ProfileManager1`, UUID fijo). | `sdptool` está obsoleto; BlueZ entrega el socket ya conectado. |
| D7 | La app corre en un contenedor con `network_mode: host`, `NET_ADMIN/NET_RAW` y `/var/run/dbus`; `bluetoothd` queda en el host. | Patrón validado en el spike (Tarea 8). |
| D8 | Sin cifrado propio de aplicación. | **Sustituida por D22 en el modo por defecto**; con código, el enlace emparejado lo cifra BlueZ. |
| D9 | El batch corre **fuera de la sesión**: `BYE` cuenta lo aceptado en staging; luego el controlador ejecuta `run_batch('SYNC')`. Un job del Scheduler cada 60 s lo respalda. | El móvil no espera al batch y las pruebas de la sesión no dependen de PL/SQL. |
| D10 | `REGISTROS_PROCESADOS.CANTIDAD` es `NUMBER`. | Hace falta para sumar y conciliar. |
| D11 | El PC es **una** aplicación de escritorio. | Menos piezas; la demo sale de una sola ventana. |
| D12 | Conteo ciego: el catálogo enviado al móvil no incluye el stock del sistema. | El operario no ve el teórico para no sesgar el conteo. |
| D13 | Recontar reemplaza, las ubicaciones suman; vale la lectura más reciente y, a igual fecha, el `ID_TRANSITO` mayor. | Permite corregir sin duplicar, incluso entre dos celulares. |
| D14 | Código de barras = SKU; escáner ZXing embebido más digitación manual. | Sin Google Play Services: funciona sin red. |
| D15 | Reloj del móvil: `offset = hora del servidor − reloj del móvil` al recibir `READY`; se envía `ts_original + offset` y el original **no se modifica**; el offset no se acumula. | Sin red los relojes derivan y D13 depende de ellos. |
| D16 | Los errores no se pierden: quedan en `ERROR`, visibles, y se reprocesan tras corregir el catálogo. | Aparece un producto sin alta y el administrador lo registra después. |
| D17 | UML completo en PlantUML (22 diagramas, 13 tipos). | A pedido del usuario; una prueba evita que las clases se desvíen del código. |
| D18 | Identidad del dispositivo = UUID de instalación, con `allowBackup="false"`. | Android no da una MAC propia. Reinstalar crea un dispositivo nuevo con `seq` desde 1. |
| D19 | Una sincronización a la vez; las demás reciben `NAK\|0\|OCUPADO`. | Evita que un segundo teléfono pise el estado del primero. |
| D20 | Operador obligatorio (máx. 60) y nota (máx. 255); el batch trunca sin marcar error. | Es lo que soporta el modelo de datos; el móvil ya limita. |
| D21 | Nombre Bluetooth visible `gestion_inventario` mientras la ventana está abierta; después recupera el del PC. | El operario busca la aplicación, no el equipo. |
| D22 | **Sin emparejamiento ni claves**: socket RFCOMM inseguro, agente silencioso, el teléfono recuerda al PC y conecta directo. | Quita pasos al operario. Costo de seguridad abajo. |

## 4. Límites conocidos

- **D15 (reloj):** asume que nadie cambió la hora del móvil entre la captura y la sincronización, y no compensa la
  latencia de la conexión (≈ 1 s).
- **D22 (seguridad):** sin autenticación el enlace no va cifrado; cualquiera al alcance (~10 m) puede conectarse y
  subir lecturas falsas **mientras la ventana de sincronización esté abierta**. Mitigaciones: la ventana la abre el
  administrador y dura 120 s, solo acepta un teléfono a la vez y cada línea se valida. Si hace falta más, aprobar el
  UUID de instalación de cada dispositivo desde la app de escritorio es compatible con este diseño.
- **D18:** desinstalar la APK borra la `Outbox`: las lecturas no enviadas se pierden.
- **D4:** iPhone no está soportado.
- **Cliente Android sin tiempo límite de lectura:** si el PC acepta la conexión y deja de responder sin cerrarla, el
  teléfono espera hasta que Android detecte la caída del enlace. Cancelar la pantalla cierra el socket.
- **minSdk 23** (Android 6): el plan decía 26, pero un HUAWEI P9 lite no pasa de Android 7.
- **Bluetooth desde contenedor** exige `network_mode: host` y el bus D-Bus del host (`bluetoothd` no corre en Docker).
- **Oracle XE 11g** solo existe para x86_64.

## 5. Diagramas UML

### 5.1 Estructura

**01 · Clases del servidor.** La librería `btsync`: el controlador crea una sesión por conexión y ambos usan el
transporte y el repositorio Oracle.
![01 · Clases del servidor](img/uml/01-clases-servidor.svg)

**02 · Clases de la app de escritorio.** Seis vistas que consultan por `QueryRunner` y una puerta (`SyncBridge`) hacia el
controlador.
![02 · Clases de escritorio](img/uml/02-clases-escritorio.svg)

**03 · Clases de la APK.** MVVM: pantallas, `CountViewModel`, `SyncRunner`, `SyncClient`, `Protocol` y la `Outbox`.
![03 · Clases de Android](img/uml/03-clases-android.svg)

**04 · Modelo de datos.** Las diez tablas de Oracle, con sus claves y cardinalidades.
![04 · Modelo de datos](img/uml/04-modelo-datos.svg)

**05 · Instantánea de objetos.** Una lectura del escenario `T-01`, de la línea `REC` a la fila de conciliación.
![05 · Objetos](img/uml/05-objetos-instantanea.svg)

**06 · Componentes.** APK, app de escritorio, Oracle y BlueZ unidos por RFCOMM, D-Bus y SQL\*Net.
![06 · Componentes](img/uml/06-componentes.svg)

**07 · Despliegue.** Qué corre en el celular, en el host y en cada contenedor, y por qué enlaces se hablan.
![07 · Despliegue](img/uml/07-despliegue.svg)

**08 · Paquetes.** Módulos de `btsync`, `desktop.app` y `mobile` y sus dependencias.
![08 · Paquetes](img/uml/08-paquetes.svg)

**09 · Estructura compuesta.** El interior de `SyncController`: puertos y partes.
![09 · Estructura compuesta](img/uml/09-estructura-compuesta.svg)

### 5.2 Comportamiento

**10 · Casos de uso.** Operario, Administrador y Scheduler de Oracle, con sus casos.
![10 · Casos de uso](img/uml/10-casos-de-uso.svg)

**11 · Actividad: conteo en el móvil.** Del operador y la ubicación a guardar y sincronizar.
![11 · Actividad móvil](img/uml/11-actividad-conteo-movil.svg)

**12 · Actividad: de la subida al batch.** Quién hace qué desde el `REC` hasta la conciliación.
![12 · Actividad batch](img/uml/12-actividad-batch.svg)

**16 · Estados del controlador.** De `IDLE` a `LISTO`/`ERROR`, con plazo, corte y cancelación.
![16 · Estados del controlador](img/uml/16-estados-sync-controller.svg)

**17 · Estados de una fila de tránsito.** `PENDIENTE → PROCESANDO → PROCESADO | ERROR`, con huérfanas y reproceso.
![17 · Estados de la fila de tránsito](img/uml/17-estados-fila-transito.svg)

**18 · Estados de una lectura en la Outbox.** `PENDIENTE → ENVIADO → CONFIRMADO` y la vuelta tras un corte.
![18 · Estados de la lectura](img/uml/18-estados-lectura-outbox.svg)

**19 · Estados del conteo.** `ABIERTO → CERRADO` y qué pasa con `SIN_CONTAR`.
![19 · Estados del conteo](img/uml/19-estados-conteo.svg)

### 5.3 Interacción

**13 · Secuencia: sincronización completa.** Ventana, conexión, `HELLO`, `READY`, catálogo, `REC`, `ACK`, `BYE`, batch y
refresco.
![13 · Secuencia de sincronización](img/uml/13-secuencia-sincronizacion.svg)

**14 · Secuencia: corte y reanudación.** `READY|25` y go-back-N sin duplicados.
![14 · Corte y reanudación](img/uml/14-secuencia-corte-reanudacion.svg)

**15 · Secuencia: errores y cierre.** Fila en `ERROR`, alta del producto, reproceso y cierre del conteo.
![15 · Errores y cierre](img/uml/15-secuencia-errores-y-cierre.svg)

**20 · Comunicación.** La colaboración numerada entre `Session`, `Store`, `SyncController`, `PKG_BATCH` y `SyncBridge`.
![20 · Comunicación](img/uml/20-comunicacion.svg)

**21 · Visión general de interacción.** El flujo de alto nivel que enlaza 13, 14 y 15.
![21 · Visión de interacción](img/uml/21-vision-interaccion.svg)

**22 · Tiempos.** La ventana de 120 s y la ventana de 50 `REC` entre `ACK`.
![22 · Tiempos](img/uml/22-tiempos.svg)

El diagrama de **perfiles** no aplica: el proyecto no define ningún perfil UML propio.

## 6. Capturas de la aplicación de escritorio

| | |
|---|---|
| ![Sincronización en reposo](img/escritorio-sync-reposo.png) | ![Esperando conexión](img/escritorio-sync-esperando.png) |
| ![Conteo](img/escritorio-conteo.png) | ![Conciliación](img/escritorio-conciliacion.png) |
| ![Gráficas](img/escritorio-graficas.png) | ![Monitoreo](img/escritorio-monitoreo.png) |
