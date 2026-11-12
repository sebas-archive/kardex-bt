# Inventario físico offline: APK → Bluetooth → Oracle (batch) → App de escritorio — Plan de implementación

> **Para agentes:** REQUIRED SUB-SKILL: usar superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementar este plan tarea por tarea. Los pasos usan checkboxes (`- [ ]`).

**Goal:** Un sistema de **toma de inventario físico** con dos aplicaciones: una **APK Android** con la que un operario cuenta productos por ubicación (escaneando código de barras o digitando el SKU) sin wifi y envía el conteo por Bluetooth (RFCOMM); y **una única aplicación de escritorio en el PC** que recibe el conteo, lo guarda en Oracle, dispara el batch PL/SQL que lo **concilia contra el stock del sistema**, y muestra y grafica diferencias, exactitud y avance. El lado PC corre en Docker.

**Architecture:** 4 capas del PDF (móvil → recepción BT → Oracle staging + batch PL/SQL → vistas), pero las capas 2 y 4 son **una sola app de escritorio y un solo proceso**: el botón «Iniciar sincronización» activa el servidor Bluetooth interno (`SyncController`), muestra el código de emparejamiento en la misma ventana y, **cuando la sesión termina**, el controlador (no la sesión) dispara el batch y la ventana refresca las gráficas. No hay API HTTP ni servicio aparte. El protocolo es de líneas de texto con CRC32, ACK acumulativo con retroceso (go-back-N) e idempotencia `(dispositivo, seq)`, idéntico en Python y Kotlin (vectores de prueba compartidos). El transporte es intercambiable: `BluezTransport` (real) y `TcpTransport` (pruebas, sin hardware). Una sola sincronización activa a la vez.

**Tech Stack:** Docker Compose · Oracle Database XE 11g (`gvenzl/oracle-xe:11-slim`) · Python 3.12 + `python-oracledb` (modo thick, Instant Client) + `dbus-fast` · PyQt6 + pyqtgraph (X11 desde contenedor) · Android Kotlin (Room, MVVM, ZXing embedded) compilado en Docker · PlantUML en Docker · pytest / pytest-qt / JUnit.

**Spec:** No hay documento de diseño aparte (se omitió el brainstorming a pedido del usuario). Las decisiones están en «Decisiones de diseño». Las marcadas **(supuesto)** deben confirmarse antes de ejecutar.

## Decisiones de diseño

| # | Decisión | Por qué / riesgo |
|---|---|---|
| D1 | **Tema: toma de inventario físico** de una bodega/tienda de abarrotes (SKU, categoría, ubicación, costo unitario). **(supuesto)** | Elegido por el usuario. Caso real de terminal que cuenta offline y sube en lote a una base central. |
| D2 | **"Oracle X11" = Oracle XE 11g** **(supuesto)**. Si querías un Oracle moderno, solo cambia la imagen y vuelves a poder usar `IDENTITY` y thin mode. | 11g NO tiene columnas `IDENTITY` (el DDL del PDF no corre) ni funciones JSON: se usan secuencia + trigger y un formato de texto con `\|`. |
| D3 | **La GUI usa X11**: la app corre en contenedor y se dibuja en tu pantalla por el socket X11 (XWayland, `DISPLAY=:0`). | Cumple "todo en docker" con app de escritorio. |
| D4 | **Móvil: solo Android** (Kotlin, APK). **(supuesto)** | iOS no permite RFCOMM clásico a apps normales. |
| D5 | **Emparejamiento nativo BlueZ (SSP)**: el PC se hace visible un tiempo limitado, BlueZ genera un código de 6 dígitos, la app de escritorio lo muestra y el usuario confirma ahí y en el móvil. | **Reemplazada por D22 como modo por defecto; sigue disponible con `require_pairing=True`.** Es literalmente "da un código, empareja y empieza a subir". |
| D6 | **Servicio RFCOMM registrado por D-Bus** (`ProfileManager1.RegisterProfile`, UUID fijo), no con `sdptool`. | `sdptool` está obsoleto; BlueZ entrega el socket ya conectado. |
| D7 | **Contenedor de la app de escritorio** (`app`) con Bluetooth: `network_mode: host`, `cap_add: [NET_ADMIN, NET_RAW]`, montar `/var/run/dbus`; además DISPLAY/X11 (D3). `bluetoothd` queda en el host. | Patrón conocido; **riesgo alto**, por eso existe el spike (Tarea 8), que puede adelantarse en paralelo sin bloquear las Tareas 1–7. |
| D8 | **Sin cifrado propio de aplicación**: el cifrado lo da el enlace BlueZ emparejado; solo se aceptan dispositivos emparejados. | El PDF pide cifrar el canal RFCOMM; YAGNI para HMAC propio. | **(Reemplazada por D22 en el modo por defecto.)**
| D9 | **El batch corre fuera de la sesión.** `Session` termina en `BYE` (que cuenta lo *aceptado en staging*, no lo procesado); luego `SyncController` ejecuta `Store.run_batch('SYNC')`. Además existe el job `DBMS_SCHEDULER` cada 60 s (del PDF) como respaldo. | El móvil no espera al batch, y los tests de la sesión no dependen del paquete PL/SQL. |
| D10 | `REGISTROS_PROCESADOS.CANTIDAD` es `NUMBER` (el PDF usa `VARCHAR2`). | Hace falta para sumar y conciliar. |
| D11 | **El PC es UNA app de escritorio** (a pedido del usuario): servidor BT, disparador de batch, tablas y gráficas en un proceso; la lógica BT vive en la librería `server/btsync` instalada en la imagen de la app. Sin API HTTP. | Menos piezas; la demo sale de una sola ventana. El BT corre en hilos propios y avisa por señales Qt. |
| D12 | **Conteo ciego**: el catálogo que se envía al móvil NO incluye el stock del sistema. | Práctica estándar: el operario no ve el teórico para no sesgar el conteo. |
| D13 | **Recontar reemplaza, ubicaciones suman.** Para `(conteo, ubicación, SKU)` vale la lectura con `FECHA_CAPTURA` más reciente; **si empatan, gana el `ID_TRANSITO` mayor** (global, asignado al llegar al staging; `seq` es por dispositivo y no sirve para desempatar). El total de un SKU es la suma de sus ubicaciones vigentes. | Permite corregir un conteo sin duplicar, incluso entre dos celulares, y contar el mismo SKU en varias estanterías. |
| D14 | **Código de barras = SKU** **(supuesto)**; escáner offline con ZXing embebido (sin Google Play Services) más digitación manual. | Evita dependencias de Google; el móvil funciona sin red. |
| D15 | **Reloj del móvil**: al recibir `READY` el móvil calcula `offset = epoch_ms_servidor − reloj_del_móvil_ahora` y envía `ts = ts_original + offset`. El `ts_original` (reloj del móvil al capturar) se guarda **sin modificar** en la `Outbox`; el offset se recalcula en cada sincronización y nunca se acumula. **Límite conocido:** asume que nadie cambió la hora del móvil entre la captura y la sincronización, y no compensa la latencia (≈ 1 s). | Sin red los relojes derivan y D13 depende de ellos. |
| D16 | **Errores no se pierden**: una fila con SKU/ubicación desconocidos o conteo cerrado queda en `ERROR` visible en la GUI y se puede **reprocesar** tras corregir el catálogo. | Flujo real: aparece un producto sin alta y el administrador lo registra después. |
| D17 | **UML completo en PlantUML** (22 diagramas, 13 tipos; perfiles no aplica), escrito al final contra el código real y renderizado en Docker. | A pedido del usuario. PlantUML cubre todos los tipos; un chequeo automático evita que las clases del diagrama se desvíen del código. |
| D18 | **Identidad del dispositivo = UUID de instalación**, generado en el primer arranque, guardado en el almacenamiento privado de la app con `allowBackup="false"`. Reinstalar crea un dispositivo nuevo con `seq` desde 1. | No hay MAC propia accesible en Android. Si tras reinstalar se vuelve a enviar un conteo ya cargado, D13 lo **reemplaza** en vez de duplicarlo. El README advierte no desinstalar con lecturas pendientes (la `Outbox` se pierde). |
| D19 | **Una sincronización a la vez**: el transporte acepta una sola conexión activa; las demás reciben `NAK\|0\|OCUPADO` y se cierran. `SyncController.status()` es único. | Evita que un segundo teléfono pise el estado y la barra de progreso del primero. La demo con dos celulares se hace en serie. |
| D20 | **Operador y notas**: el operador se captura en una pantalla del móvil (obligatorio antes de guardar, máx. 60 caracteres, se recuerda); la nota tiene máx. 255 caracteres. El batch **trunca** a 60 y 255 caracteres sin marcar error. | Es lo que el modelo de datos soporta; el truncado es una red de seguridad, el móvil ya limita. |
| D21 | **Nombre Bluetooth visible: `gestion_inventario`** (a pedido del usuario). Mientras la ventana de sincronización está abierta el adaptador usa ese nombre (`Adapter1.Alias`); al cerrarla recupera el del PC. | El operario busca la aplicación, no el nombre del equipo. No se cambia de forma permanente el nombre Bluetooth del PC. Un teléfono ya emparejado puede seguir mostrando el nombre anterior hasta que se vuelva a emparejar. |
| D22 | **Sin emparejamiento ni claves** (a pedido del usuario; reemplaza a D5 y D8 como modo por defecto). El servicio RFCOMM no exige autenticación ni autorización: un teléfono que nunca se emparejó se conecta con un socket «inseguro» (`createInsecureRfcommSocketToServiceRecord`), sin código ni diálogos. La app recuerda la dirección del PC tras elegirlo una vez y desde entonces conecta directo, sin buscar, cuando el PC está escuchando. Si una app fuerza el emparejamiento, lo atiende un agente silencioso (`NoInputNoOutput`, «Just Works») que no muestra código ni pide permisos y solo autoriza el servicio propio. El modo con código de 6 dígitos sigue disponible (`BluezTransport(require_pairing=True)`, `controller_cli.py --con-clave`). | Quita pasos al operario. **Costo de seguridad:** sin autenticación el enlace no va cifrado y cualquiera al alcance (~10 m) puede conectarse y subir lecturas falsas mientras la ventana esté abierta. Mitigaciones actuales: el PC solo acepta con la ventana abierta por el administrador, de a un teléfono, y valida cada línea. Si hace falta más, una lista de dispositivos autorizados (aprobar el UUID de instalación desde la app de escritorio) es compatible con este diseño. |

## Constraints globales

- Rutas con espacios: el proyecto vive en `/home/t1an/movil oracle bluetooth`; entrecomillar rutas en todos los scripts.
- Oracle 11g: sin `GENERATED AS IDENTITY`, sin `JSON_*`, sin `FETCH FIRST`, sin thin mode de python-oracledb (usar `oracledb.init_oracle_client()`).
- **Longitudes en caracteres, no en bytes**: todas las columnas de texto se declaran `VARCHAR2(n CHAR)`, salvo `DATOS_RAW VARCHAR2(4000 BYTE)`.
- **Números con punto**: el batch convierte con `TO_NUMBER(x, '999999999D999', 'NLS_NUMERIC_CHARACTERS=''.,''')`, nunca con el NLS de la sesión.
- **Fechas en UTC**: `FECHA_CAPTURA = TIMESTAMP '1970-01-01 00:00:00' + NUMTODSINTERVAL(epoch_ms / 1000, 'SECOND')`. `1731170400000` es `2024-11-09 16:40:00`.
- UUID del servicio RFCOMM: `7a1c0b52-4f0e-4d6a-9c3b-5e2a6d9f1b01`.
- Protocolo: UTF-8, una línea por mensaje terminada en `\n`, **máximo 4000 bytes por línea** (incluye el CRC), campos separados por `|`, y al final `*` + CRC32 en 8 hex mayúsculas calculado sobre los bytes anteriores al `*`. En campos de texto libre, `|`, `%`, `\r`, `\n` se codifican como porcentaje (`%7C`, `%25`, `%0D`, `%0A`).
- Móvil → PC: `HELLO|1|<uuid_dispositivo>|<nombre>`, `REC|<seq>|<epoch_ms>|<id_conteo>|<ubicacion>|<sku>|<cantidad>|<operador>|<nota>`, `END|<n_registros>`. `cantidad` es decimal con punto, `^\d{1,9}(\.\d{1,3})?$`. `seq` empieza en 1 y es contiguo por dispositivo.
- PC → móvil: `READY|<ultimo_seq_confirmado>|<epoch_ms_servidor>`, `CATCONTEO|<id>|<nombre>`, `CATUBIC|<cod>|<zona>|<descripcion>`, `CATPROD|<sku>|<nombre>|<categoria>|<unidad>`, `CAT_END`, `ACK|<seq>`, `NAK|<seq_esperado>|<motivo>`, `BYE|<aceptados>|<rechazados>`. Solo se envían conteos `ABIERTO`.
- **ACK acumulativo**: `ACK|n` significa que todo `seq ≤ n` está persistido con COMMIT.
- **NAK y retroceso (go-back-N)**: todo `NAK` lleva el `seq` que el servidor espera a continuación; el móvil retrocede y reenvía desde ahí. Motivos: `CRC`, `FORMAT`, `LINEA_LARGA`, `SECUENCIA`, `DB_NO_DISPONIBLE`, `OCUPADO` (con `seq` 0). Tras un `NAK` el servidor **ignora en silencio** los `REC` siguientes hasta recibir el `seq` esperado, y no vuelve a enviar `NAK` por ellos.
- **Secuencia**: con `esperado = último_persistido + 1`: `seq < esperado` es duplicado (no se inserta; se cubre con el siguiente `ACK`); `seq = esperado` se inserta; `seq > esperado` (hueco) provoca un único `NAK|esperado|SECUENCIA`.
- **`BYE|<aceptados>|<rechazados>`**: `aceptados` = filas nuevas insertadas en esa sesión; `rechazados` = cantidad de `NAK` enviados en esa sesión. Los duplicados no cuentan en ninguno. No informa del resultado del batch.
- `DATOS_RAW` = la línea `REC` sin el CRC.
- Sincronización: tras `READY` el PC envía el catálogo completo; el móvil envía hasta 50 `REC` sin ACK; el servidor hace COMMIT cada 25 registros insertados o al `END`, y recién entonces envía `ACK`.
- **Conciliación** (batch): `CONCILIACION` contiene la **unión** de los SKU de `STOCK_SISTEMA` del conteo y los SKU con lecturas vigentes (si no está en la foto, `CANT_SISTEMA = 0`). `contada = Σ cantidad` de filas vigentes. `DIFERENCIA = contada − sistema`; `DIFERENCIA_PCT = DIFERENCIA / sistema × 100` a 2 decimales (`NULL` si `sistema = 0`); `VALOR_DIFERENCIA = DIFERENCIA × COSTO_UNIT` (negativo = faltante). `OK` si `|DIFERENCIA| ≤ sistema × TOLERANCIA_PCT / 100` (límite inclusivo); si no, `FALTANTE` (contada < sistema) o `SOBRANTE`; con `sistema = 0` y `contada > 0` es `SOBRANTE`. SKU del sistema sin lecturas en conteo abierto: `SIN_CONTAR`, con `CANT_CONTADA = 0` y `DIFERENCIA`, `DIFERENCIA_PCT` y `VALOR_DIFERENCIA` en `NULL`; al cerrar el conteo pasa a `FALTANTE` con `CANT_CONTADA = 0`.
- **Resumen** (`V_RESUMEN_CONTEO`): `skus_totales` = filas de `CONCILIACION`; `contados` = filas que no son `SIN_CONTAR`; `avance_pct = contados / skus_totales × 100`; `exactitud_pct = OK / contados × 100`; `valor_faltante` = Σ `VALOR_DIFERENCIA` de las `FALTANTE`; `valor_sobrante` = Σ de las `SOBRANTE`. Todos los porcentajes a 2 decimales.
- Control interno (sin HTTP): `SyncController` en el mismo proceso que la GUI. Estados: `IDLE, ESPERANDO_EMPAREJAMIENTO, CONFIRMAR_CODIGO, CONECTADO, RECIBIENDO, PROCESANDO, LISTO, ERROR`.
- Rendimiento objetivo del PDF: inserción media < 50 ms por registro en staging (se mide y se reporta tal cual, aunque no se cumpla).
- **Formato en la GUI (es-CO)**: porcentajes con una coma decimal y un decimal (`80,0 %`); pesos con punto de miles y sin decimales (`$ 11.800`, `-$ 5.000`).

## Convención de comandos de prueba

- **Servidor/BD:** `docker compose run --rm pybase pytest server/tests/<archivo>.py -v` (el servicio `pybase` monta el proyecto en `/work` y trae `DB_DSN`, `DB_USER`, `DB_PASSWORD`). «PASS» = el comando termina con código 0, sin `failed` ni `skipped`; «FAIL» = sale con código 1 por los tests nuevos (`ImportError`, `ORA-00942` o `AssertionError`), no por errores de configuración.
- **Escritorio:** `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests/<archivo>.py -v`.
- **Android:** `docker compose --profile build run --rm apk-build ./gradlew testDebugUnitTest --tests '<Clase>'` → `BUILD SUCCESSFUL`.
- **Fixture de conciliación** (`server/tests/fixtures/escenario_conciliacion.sql`, se crea en la Tarea 6 y la reutilizan las Tareas 7, 10 y 11; **los tests no usan la semilla**):

  | Tabla | Contenido exacto |
  |---|---|
  | `CONTEOS` | `T-01`, `ABIERTO` |
  | `UBICACIONES` | `U1` zona `Z1`, `U2` zona `Z1`, `U3` zona `Z2` |
  | `PRODUCTOS` (sku, categoría, costo, tolerancia %) | `A1` Abarrotes 2000 2; `A2` Abarrotes 1000 0; `A3` Aseo 3000 0; `A4` Aseo 500 0; `A5` Lácteos 700 0 |
  | `STOCK_SISTEMA` de `T-01` | `A1` 100, `A2` 50, `A3` 20, `A4` 10 (`A5` **no** está) |
  | Lecturas (ubic, sku, cantidad, operador) | `U1 A1 60 Ana`, `U2 A1 41 Luis`, `U1 A2 45 Ana`, `U1 A3 23 Ana`, `U2 A5 4 Luis` |

  Resultado esperado de la conciliación abierta: `A1` contada 101, dif +1, +1,00 %, valor +2000, `OK`; `A2` 45, −5, −10,00 %, −5000, `FALTANTE`; `A3` 23, +3, +15,00 %, +9000, `SOBRANTE`; `A4` 0, `NULL`, `NULL`, `NULL`, `SIN_CONTAR`; `A5` sistema 0, contada 4, +4, `NULL`, +2800, `SOBRANTE`. Resumen: `skus_totales 5`, `contados 4`, `avance_pct 80,00`, `OK 1`, `FALTANTE 1`, `SOBRANTE 2`, `exactitud_pct 25,00`, `valor_faltante -5000`, `valor_sobrante 11800`. Tras cerrar el conteo: `A4` pasa a contada 0, dif −10, −100,00 %, −5000, `FALTANTE`, y el resumen queda `contados 5`, `avance_pct 100,00`, `FALTANTE 2`, `exactitud_pct 20,00`, `valor_faltante -10000`, `valor_sobrante 11800`.

## Review Focus (modos de fallo que las pruebas deben fijar)

1. **Corte a mitad de lote**: con 30 `REC` enviados y corte, quedan **25** filas (las confirmadas con COMMIT), el último `ACK` fue `ACK|25` y al reconectar `READY|25|…` permite reanudar sin duplicados. (Tareas 4, 5)
2. **Línea corrupta o hueco de secuencia**: `NAK|<esperado>|CRC` o `SECUENCIA` una sola vez, sin insertar, la conexión sigue viva y el reenvío desde `esperado` completa el lote. (Tareas 3, 4)
3. **Texto raro y notas largas** (`|`, saltos de línea, tildes, emoji, más de 255 caracteres): llega idéntico a la BD, o se trunca a 255 (nota) / 60 (operador) caracteres sin error. (Tareas 3, 6)
4. **Recontar entre dos celulares**: dos lecturas del mismo `(conteo, ubicación, SKU)` cuentan una vez, gana la más reciente y, a igual `FECHA_CAPTURA`, el `ID_TRANSITO` mayor; el mismo SKU en dos ubicaciones suma. (Tarea 6)
5. **SKU/ubicación desconocidos, conteo cerrado, cantidad inválida o fila `PROCESANDO` huérfana**: la fila queda en `ERROR` con mensaje (o vuelve a `PENDIENTE` si lleva más de 5 minutos en `PROCESANDO`), el lote sigue y `REPROCESAR_ERRORES` la procesa tras corregir el catálogo. (Tarea 6)
6. **Concurrencia y caídas**: dos ejecuciones simultáneas del batch procesan cada fila una vez y la conciliación queda igual a la de una sola; Oracle caído responde `NAK|…|DB_NO_DISPONIBLE` sin tumbar el servidor; un segundo teléfono recibe `NAK|0|OCUPADO`; si nadie empareja a tiempo el PC deja de ser visible y vuelve a `IDLE`. (Tareas 4, 5, 6, 9)

## Estructura de archivos

```
docker-compose.yml  .env.example  README.md
docker/pybase/Dockerfile            # Python 3.12 + Instant Client (compartida)
db/init/01_schema.sql 02_seed.sql 03_pkg_batch.sql 04_jobs.sql 05_views.sql
server/pyproject.toml               # paquete btsync (deps: oracledb; extras: dev, bluez)
server/btsync/{__init__.py,protocol.py,store.py,session.py,controller.py}   # librería, se instala en la imagen de la app
server/btsync/transports/{base.py,tcp.py,bluez.py}
server/spikes/{bluez_echo.py,controller_cli.py}                             # desechables
server/tests/{conftest.py,fixtures/escenario_conciliacion.sql}
tools/{gen_seed.py,truth.json,fake_phone.py,check_uml.py,render_uml.sh}
desktop/Dockerfile
desktop/app/{main.py,db.py,models.py,workers.py,sync_bridge.py,views/{base,sync,conteo,conciliacion,charts,perfil,monitor}.py}
desktop/tests/
mobile/                              # proyecto Android (Kotlin) + Dockerfile de build
docs/{arquitectura.md,protocolo.md,protocol-vectors.json,spikes/bluez.md,demo.md}
docs/uml/*.puml  docs/uml/README.md   # 22 diagramas fuente (PlantUML)
docs/img/uml/*.svg  docs/img/         # generados / capturas
```

---

## Hitos

- **M1 (Tareas 1–7)**: flujo completo sin Bluetooth ni móvil ni hardware: teléfono simulado por TCP → Oracle → batch → conciliación.
- **M2 (Tareas 8–9)**: Bluetooth real. **La Tarea 8 necesita el celular y puede hacerse en paralelo (otra sesión) en cualquier momento; no bloquea las Tareas 1–7.** Conviene adelantarla pronto: si falla, cambia el requisito "todo en Docker".
- **M3 (Tareas 10–13)**: app de escritorio con conteo, conciliación, gráficas, monitoreo y botón de sincronizar.
- **M4 (Tareas 14–15)**: APK propia con escáner.
- **M5 (Tareas 16–18)**: diagramas UML, documentación, demo y verificación final.

---

### Tarea 1: Andamiaje Docker, Oracle 11g y paquete Python

**Files:**
- Create: `docker-compose.yml`, `.env.example`, `docker/pybase/Dockerfile`, `server/pyproject.toml`, `server/btsync/__init__.py`, `server/tests/conftest.py`, `README.md`, `.gitignore`
- Test: `server/tests/test_oracle_connect.py`

**Interfaces:**
- Produces:
  - Servicio `oracle`: imagen `gvenzl/oracle-xe:11-slim`, publica `127.0.0.1:1521`, servicio `XE`, usuario `app` (`APP_USER`, `APP_USER_PASSWORD` desde `.env`), `./db/init:/container-entrypoint-initdb.d`, healthcheck con `healthcheck.sh`. Los scripts de init corren como `SYS`: cada `.sql` empieza con `ALTER SESSION SET CURRENT_SCHEMA = app;` y el primero otorga a `app` `CREATE SEQUENCE, CREATE TRIGGER, CREATE VIEW, CREATE JOB`.
  - Servicio `pybase` (perfil `dev`, no arranca con `up`): construye `docker/pybase`, monta `./:/work`, `working_dir: /work`, `depends_on: oracle (healthy)`, entorno `DB_DSN=oracle:1521/XE`, `DB_USER`, `DB_PASSWORD`, `PYTHONPATH=/work/server`; instala `server/` en modo editable con extras `dev`.
  - `server/pyproject.toml`: paquete `btsync`, Python ≥ 3.12, dependencias `oracledb`; extras `dev = [pytest]` y `bluez = [dbus-fast]`; `[tool.pytest.ini_options] testpaths = ["tests"]`.
  - `conftest.py`: fixtures `db` (conexión thick con `DB_DSN/DB_USER/DB_PASSWORD`, rollback al final) y `scheduler_off` (autouse: si existe `JOB_PROCESAR_CAPTURAS`, lo deshabilita al inicio de la sesión de tests y lo rehabilita al final; sin efecto si aún no existe). Evita que el job de 60 s procese filas en medio de un test.

- [ ] **Step 1:** `git init`; escribir `.env.example` (`ORACLE_PASSWORD`, `APP_USER=app`, `APP_USER_PASSWORD`, `DB_USER`, `DB_PASSWORD`) y copiarlo a `.env`; escribir `docker-compose.yml`, `docker/pybase/Dockerfile` (`python:3.12-slim` + `libaio1` + Instant Client Basic Lite 19.x descargado de Oracle sin login + `ldconfig`) y `pyproject.toml`.
- [ ] **Step 2: Escribir tests** en `test_oracle_connect.py`: `test_server_version_is_11_2` (`SELECT banner FROM v$version` contiene `"11.2"`); `test_database_charset_is_al32utf8` (`NLS_CHARACTERSET = 'AL32UTF8'`); `test_btsync_package_importable` (`import btsync`).
- [ ] **Step 3:** Con la BD apagada: `docker compose run --rm pybase pytest server/tests/test_oracle_connect.py -v` → FAIL (conexión rechazada en los dos primeros; el tercero pasa).
- [ ] **Step 4:** `docker compose up -d --wait oracle` (la primera vez puede tardar varios minutos) y repetir el comando de pruebas → PASS (3 tests). Si hay `DPI-1050` o `ORA-28040`, bajar a Instant Client 12.2 (mismo patrón de descarga).
- [ ] **Step 5: Commit** `chore: docker scaffold, oracle 11g and python package`.

---

### Tarea 2: Esquema Oracle y datos semilla de inventario

**Files:**
- Create: `db/init/01_schema.sql`, `db/init/02_seed.sql`, `tools/gen_seed.py`, `tools/truth.json`
- Test: `server/tests/test_schema.py`

**Interfaces:**
- Produces tablas (PK numéricas por secuencia + trigger `BEFORE INSERT`; textos `VARCHAR2(n CHAR)`):
  - `CONTEOS(ID_CONTEO VARCHAR2(30) PK, NOMBRE, ESTADO CHECK IN ('ABIERTO','CERRADO'), FECHA_INICIO, FECHA_CIERRE)`
  - `PRODUCTOS(SKU VARCHAR2(30) PK, NOMBRE, CATEGORIA, UNIDAD, COSTO_UNIT NUMBER(12,2), TOLERANCIA_PCT NUMBER(5,2) DEFAULT 0)`
  - `UBICACIONES(COD_UBICACION PK, ZONA, DESCRIPCION)`
  - `STOCK_SISTEMA(ID_CONTEO FK, SKU FK, CANTIDAD_SISTEMA NUMBER(12,3), PK(ID_CONTEO, SKU))`
  - `DISPOSITIVOS(UUID PK, NOMBRE, ULTIMA_SYNC)`
  - `CAPTURA_TRANSITO(ID_TRANSITO, UUID_DISPOSITIVO, SEQ, DATOS_RAW VARCHAR2(4000 BYTE), ESTADO CHECK IN ('PENDIENTE','PROCESANDO','PROCESADO','ERROR') DEFAULT 'PENDIENTE', MENSAJE_ERROR VARCHAR2(400 CHAR), FECHA_RECEPCION TIMESTAMP DEFAULT SYSTIMESTAMP, FECHA_RECLAMO TIMESTAMP, UNIQUE(UUID_DISPOSITIVO, SEQ))`, índice en `ESTADO`
  - `REGISTROS_PROCESADOS(ID_REGISTRO, ID_TRANSITO FK **UNIQUE**, ID_CONTEO FK, COD_UBICACION FK, SKU FK, CANTIDAD NUMBER(12,3), OPERADOR VARCHAR2(60 CHAR), NOTA VARCHAR2(255 CHAR), FECHA_CAPTURA TIMESTAMP, VIGENTE CHAR(1) CHECK IN ('S','N'), FECHA_PROCESADO TIMESTAMP DEFAULT SYSTIMESTAMP)`, índice en `(ID_CONTEO, COD_UBICACION, SKU)`
  - `CONCILIACION(ID_CONTEO FK, SKU FK, CANT_SISTEMA, CANT_CONTADA, DIFERENCIA, DIFERENCIA_PCT, VALOR_DIFERENCIA, CLASIFICACION CHECK IN ('OK','FALTANTE','SOBRANTE','SIN_CONTAR'), FECHA_CALCULO, PK(ID_CONTEO, SKU))`
  - `SYNC_SESIONES(ID, UUID_DISPOSITIVO, INICIO, FIN, RECIBIDOS, ACEPTADOS)`, `LOG_BATCH(ID, INICIO, FIN, PROCESADOS, ERRORES, ORIGEN)`
- `tools/gen_seed.py --seed 42` genera de forma reproducible `db/init/02_seed.sql` y `tools/truth.json` (el stock físico "real" por `(ubicación, SKU)`, del que parte `fake_phone.py`): **60 SKUs** en 5 categorías (Abarrotes, Aseo, Bebidas, Lácteos, Ferretería) con costos en COP y tolerancias distintas por categoría; **12 ubicaciones** en 3 zonas (A, B, C); 1 conteo `ABIERTO` (`CONT-2026-11`) cuya foto de `STOCK_SISTEMA` tiene **58 filas** (los 2 SKUs restantes existen en el catálogo pero no en la foto, para ejercitar `SOBRANTE` con sistema 0); la verdad física difiere del sistema en ~15 % de los SKUs.

- [ ] **Step 1: Escribir tests:** `test_seed_counts` (60 en `PRODUCTOS`, 58 en `STOCK_SISTEMA` de `CONT-2026-11`, 12 en `UBICACIONES`, 1 conteo `ABIERTO`, 0 en `CAPTURA_TRANSITO`); `test_duplicate_device_seq_rejected` (segundo insert con `(uuid, seq)` igual → `ORA-00001`); `test_invalid_estado_rejected` (`ESTADO='X'` → `ORA-02290`); `test_id_autogenerated` (dos inserts sin ID dan `ID_TRANSITO` n y n+1); `test_varchar_limits_are_in_characters` (`OPERADOR` de 60 `Ñ` se inserta; de 61 → `ORA-12899`); `test_gen_seed_is_deterministic` (dos corridas con `--seed 42` producen archivos idénticos); `test_truth_json_covers_all_seeded_skus` (los 60 SKUs tienen entrada, incluidos los 2 fuera de la foto).
- [ ] **Step 2:** `docker compose run --rm pybase pytest server/tests/test_schema.py -v` → FAIL (`ORA-00942`: las tablas no existen).
- [ ] **Step 3:** Escribir `01_schema.sql` y `gen_seed.py`; ejecutar `docker compose run --rm pybase python tools/gen_seed.py --seed 42` para producir `02_seed.sql` y `truth.json`.
- [ ] **Step 4:** Recrear la BD (`docker compose down -v && docker compose up -d --wait oracle`) y repetir el comando de pruebas → PASS (7 tests).
- [ ] **Step 5: Commit** `feat(db): inventory schema and deterministic seed`.

---

### Tarea 3: Protocolo (Python) con vectores compartidos

**Files:**
- Create: `server/btsync/protocol.py`, `docs/protocol-vectors.json`, `docs/protocolo.md`
- Test: `server/tests/test_protocol.py`

**Interfaces:**
- Produces:
  - `class FrameError(Exception)` con `.reason: str` (`"CRC"` | `"FORMAT"` | `"LINEA_LARGA"`)
  - `encode_text(s: str) -> str`, `decode_text(s: str) -> str`
  - `frame(fields: list[str]) -> bytes` (los campos van **ya codificados** salvo que se use `encode_text`; agrega `*CRC` y `\n`)
  - `parse(line: bytes) -> Message` con `Message = dataclass(kind: str, fields: list[str])`, campos ya decodificados. Valida: longitud ≤ 4000 bytes, CRC y número mínimo de campos por tipo (`HELLO` 4, `REC` 9, `READY` 3, `ACK` 2, `NAK` 3, `BYE` 3, `END` 2).
  - `Rec = dataclass(seq:int, ts_ms:int, id_conteo:str, ubicacion:str, sku:str, cantidad:str, operador:str, nota:str)` con `Rec.from_message(m: Message) -> Rec`, `Rec.to_raw() -> str` (la línea sin CRC)
  - `main(argv: list[str]) -> int`: `python -m btsync.protocol --frame CAMPO…` imprime la línea con CRC; `--parse LINEA` imprime el tipo y los campos.
- Vectores exactos (en `protocol-vectors.json`; los usan Python y Kotlin):

  | Mensaje | Línea completa (sin `\n`) |
  |---|---|
  | `HELLO` | `HELLO\|1\|dev-0001\|Bodega Norte*78D353E4` |
  | `READY` | `READY\|0\|1731170400000*F1735906` |
  | `REC` simple | `REC\|1\|1731170400000\|CONT-2026-11\|A-01\|7701234000011\|12.5\|Ana\|ok*5DCB72C4` |
  | `REC` con texto raro | `REC\|2\|1731170401000\|CONT-2026-11\|A-01\|7701234000012\|3\|Ñandú%7C%25\|a%7Cb%0Ac%25😀*CAE52190` (operador decodificado `Ñandú\|%`, nota `a\|b\nc%😀`) |
  | `ACK` | `ACK\|3*6A8544FA` |
  | `NAK` ocupado | `NAK\|0\|OCUPADO*2C549C0A` |
  | `BYE` | `BYE\|3\|0*57FD7793` |

- [ ] **Step 1: Escribir tests:** `test_frame_matches_all_vectors` (`frame(campos)` produce exactamente cada línea de la tabla + `\n`); `test_parse_matches_all_vectors` (`parse` devuelve el tipo y los campos decodificados esperados); `test_text_roundtrip_special_chars` (`decode_text(encode_text("a|b\nc%ñ😀")) == "a|b\nc%ñ😀"` y el codificado no contiene `|` ni `\n`); `test_crc_mismatch_raises_crc` (cambiar el último dígito de `ACK|3*6A8544FA` a `B` → `FrameError.reason == "CRC"`); `test_too_few_fields_raises_format` (`REC|1|2` con CRC correcto → `reason == "FORMAT"`); `test_line_over_4000_bytes_raises_linea_larga`; `test_rec_to_raw_excludes_crc` (`Rec.from_message(parse(vector REC simple)).to_raw()` es `REC|1|1731170400000|CONT-2026-11|A-01|7701234000011|12.5|Ana|ok`); `test_cli_frame_prints_vector` (`python -m btsync.protocol --frame HELLO 1 dev-0001 "Bodega Norte"` imprime la línea del vector `HELLO`).
- [ ] **Step 2:** `docker compose run --rm pybase pytest server/tests/test_protocol.py -v` → FAIL (`ImportError`).
- [ ] **Step 3:** Implementar `protocol.py` (CRC32 con `zlib.crc32`). `docs/protocolo.md` copia el formato y los mensajes de «Constraints globales».
- [ ] **Step 4:** Mismo comando → PASS (8 tests).
- [ ] **Step 5: Commit** `feat(server): wire protocol with shared vectors`.

---

### Tarea 4: Repositorio Oracle y sesión de sincronización (sobre transporte abstracto)

**Files:**
- Create: `server/btsync/store.py`, `server/btsync/session.py`, `server/btsync/transports/base.py`
- Test: `server/tests/test_store.py`, `server/tests/test_session.py`

**Interfaces:**
- Consumes: `protocol` (Tarea 3), esquema (Tarea 2).
- Produces:
  - `class Catalog` dataclass: `conteos: list[tuple[str,str]]`, `ubicaciones: list[tuple[str,str,str]]`, `productos: list[tuple[str,str,str,str]]`.
  - `class Store`: `__init__(dsn: str, user: str, password: str)`; `register_device(uuid: str, name: str) -> None` (idempotente); `last_seq(uuid: str) -> int` (0 si no existe); `insert_staging(uuid: str, seq: int, raw: str) -> bool` (False si duplicado; no hace commit); `commit() -> None`; `rollback() -> None`; `catalog() -> Catalog` (solo conteos `ABIERTO`; **sin stock**); `run_batch(origen: str) -> tuple[int, int]` (`(procesados, errores)` del run; la implementa la Tarea 6, aquí solo existe la firma que lanza `NotImplementedError`); `open_sync(uuid: str) -> int`; `close_sync(id: int, recibidos: int, aceptados: int) -> None`.
  - `transports/base.py`: `class Connection(Protocol)`: `readline() -> bytes | None` (None = cierre), `write(data: bytes) -> None`, `close() -> None`. `class Transport(Protocol)`: `serve(on_connection: Callable[[Connection], None]) -> None`, `stop() -> None`. **Contrato:** como máximo una conexión activa; las demás reciben `frame(["NAK","0","OCUPADO"])` y se cierran (D19).
  - `class Session`: `__init__(conn: Connection, store: Store, on_event: Callable[[str, dict], None], now_ms: Callable[[], int] = time_ms)`; `run() -> None`. Eventos: `("hello", {"uuid","nombre"})`, `("progress", {"recibidos": int})`, `("done", {"aceptados": int, "rechazados": int})`. **La sesión nunca llama a `run_batch`** (D9).

- [ ] **Step 1: Escribir tests** (`Connection` falso en memoria, `now_ms` inyectado = `1731170400000`; `Store` real sobre Oracle con `rollback` de limpieza): en `test_store.py`: `test_last_seq_zero_for_unknown_device`; `test_insert_staging_returns_false_on_duplicate`; `test_register_device_is_idempotent`; `test_catalog_has_only_open_conteos`. En `test_session.py`: `test_happy_path_sends_ready_catalog_acks_and_bye` (HELLO + 3 REC + END → la salida empieza con `READY|0|1731170400000`, incluye `CAT_END`, y termina con `ACK|3` y `BYE|3|0`; 3 filas `PENDIENTE` en `CAPTURA_TRANSITO`); `test_catalog_never_contains_system_stock` (ninguna línea de catálogo contiene la cantidad de `STOCK_SISTEMA`; un conteo `CERRADO` no aparece); `test_duplicate_rec_in_new_session_is_not_inserted` (el mismo `seq 1` en una segunda sesión → `BYE|0|0` y sigue habiendo 1 fila); `test_reconnect_ready_returns_last_seq` (tras persistir 1–3, la nueva sesión recibe `READY|3|…`); `test_bad_crc_naks_expected_seq_and_survives` (REC 1 correcto, REC 2 con CRC alterado → `NAK|2|CRC`; reenviar REC 2 correcto → `ACK|2`); `test_seq_gap_naks_once_and_ignores_followers` (se envían 1, 2, 4, 5, 6 → exactamente un `NAK|3|SECUENCIA`, 2 filas; luego se reenvía 3–6 → 6 filas y `ACK|6`); `test_line_over_4000_bytes_naks_linea_larga`; `test_connection_cut_after_30_rec_keeps_25` (30 REC y `readline() → None` → 25 filas, último `ACK|25`); `test_oracle_down_replies_nak_db_unavailable` (`Store` que lanza `oracledb.DatabaseError` → `NAK|<esperado>|DB_NO_DISPONIBLE` y la sesión termina sin excepción); `test_session_never_calls_run_batch` (`Store` espía: `run_batch` no se invoca).
- [ ] **Step 2:** `docker compose run --rm pybase pytest server/tests/test_store.py server/tests/test_session.py -v` → FAIL (`ImportError`).
- [ ] **Step 3:** Implementar `Store` (reconexión simple ante error de conexión) y `Session` (`HELLO → READY + catálogo → REC* → END → BYE`; `esperado`, go-back-N y COMMIT cada 25 según «Constraints globales»; en `END` hace COMMIT, envía el último `ACK` y `BYE`).
- [ ] **Step 4:** Mismo comando → PASS (14 tests).
- [ ] **Step 5: Commit** `feat(server): session logic and oracle store`.

---

### Tarea 5: Transporte TCP, teléfono simulado y prueba de extremo a extremo

**Files:**
- Create: `server/btsync/transports/tcp.py`, `tools/fake_phone.py`
- Test: `server/tests/test_e2e_tcp.py`

**Interfaces:**
- Consumes: `Transport`, `Connection`, `Session`, `Store` (Tarea 4), `tools/truth.json` (Tarea 2).
- Produces: `TcpTransport(host: str, port: int)` que implementa `Transport` (una conexión activa; las demás reciben `NAK|0|OCUPADO`); `tools/fake_phone.py --host H --port P --seed S [--dirty] [--skew-ms N] [--operator NAME] [--uuid ID] [--state-file F]`: cuenta cada `(ubicación, SKU)` de `truth.json` con ~3 % de error de conteo, guarda su outbox en `--state-file` (JSON, conserva el `ts_original` sin tocar), reanuda desde `READY|seq`, aplica go-back-N ante `NAK`, y calcula `offset` con la hora de `READY` (D15). `--dirty` agrega un SKU desconocido, una ubicación inexistente y recuentos repetidos.

- [ ] **Step 1: Escribir tests** (servidor TCP en un puerto libre dentro del test; `fake_phone` como subproceso): `test_full_count_end_to_end` (con `--seed 42` y `--uuid dev-e2e`: filas en `CAPTURA_TRANSITO` = número de pares `(ubicación, SKU)` de `truth.json`, y el `BYE` del teléfono es `BYE|<N>|0`); `test_phone_killed_midway_and_resumed_no_duplicates` (matar el proceso a mitad, relanzar con el mismo `--state-file`: total final = N, sin duplicados y sin `ORA-00001`); `test_clock_skew_is_corrected` (con `--skew-ms 600000`, el `ts` de cada `REC` guardado queda a ≤ 2000 ms de la hora del servidor); `test_retry_does_not_apply_offset_twice` (con corte y reintento, el `ts` de las filas reenviadas queda también a ≤ 2000 ms, no a 1 200 000 ms); `test_second_connection_while_busy_gets_nak_ocupado` (con una conexión abierta sin cerrar, la segunda lee exactamente `NAK|0|OCUPADO*2C549C0A`); `test_insert_latency_reported` (imprime ms/registro medio; solo afirma `< 250` para no ser frágil: el objetivo del PDF es `< 50` y se reporta tal cual).
- [ ] **Step 2:** `docker compose run --rm pybase pytest server/tests/test_e2e_tcp.py -v -s` → FAIL (`ImportError` de `TcpTransport`).
- [ ] **Step 3:** Implementar `TcpTransport` y `fake_phone.py`.
- [ ] **Step 4:** Mismo comando → PASS (6 tests) y la latencia medida aparece en la salida.
- [ ] **Step 5: Commit** `feat: tcp transport and fake phone e2e`.

---

### Tarea 6: Batch PL/SQL — procesar, recontar, reprocesar y purgar

**Files:**
- Create: `db/init/03_pkg_batch.sql`, `db/init/04_jobs.sql`, `server/tests/fixtures/escenario_conciliacion.sql`
- Modify: `server/btsync/store.py` (`run_batch` real), `server/tests/conftest.py` (fixture `escenario` que carga el SQL de la tabla de «Convención de comandos de prueba» y lo borra al terminar)
- Test: `server/tests/test_batch.py`

**Interfaces:**
- Produces (paquete `PKG_BATCH`):
  - `PROCESAR_PENDIENTES(p_origen VARCHAR2 DEFAULT 'MANUAL', p_timeout_min NUMBER DEFAULT 5)`:
    1. **Recuperar huérfanas**: `PROCESANDO` con `FECHA_RECLAMO` de más de `p_timeout_min` minutos vuelven a `PENDIENTE`.
    2. **Reclamar** con un único `UPDATE … SET ESTADO='PROCESANDO', FECHA_RECLAMO=SYSTIMESTAMP WHERE ESTADO='PENDIENTE'` + `COMMIT`.
    3. **Por fila**, en su propio bloque `BEGIN … EXCEPTION`: parsear con `REGEXP_SUBSTR(raw, '([^|]*)(\||$)', 1, n, NULL, 1)` (tolera campos vacíos) y `UTL_URL.UNESCAPE(x, 'UTF-8')` en operador y nota; validar → errores `SKU_DESCONOCIDO`, `UBICACION_DESCONOCIDA`, `CONTEO_NO_ABIERTO`, `CANTIDAD_INVALIDA` (negativa, con coma, más de 3 decimales); truncar operador a 60 y nota a 255 caracteres; insertar en `REGISTROS_PROCESADOS` y poner `PROCESADO` **en la misma transacción** (la fila con error queda `ERROR` + `MENSAJE_ERROR`, el lote sigue).
    4. **Recalcular `VIGENTE`** del grupo completo `(conteo, ubicación, SKU)` tras cada inserción (D13: `FECHA_CAPTURA` desc, `ID_TRANSITO` desc).
    5. Escribir una fila en `LOG_BATCH` (`PROCESADOS`, `ERRORES`, `ORIGEN`). `COMMIT` cada 100 filas.
  - `REPROCESAR_ERRORES(p_id_conteo VARCHAR2 DEFAULT NULL)`: devuelve a `PENDIENTE` las filas `ERROR` (del conteo indicado, o todas) y llama a `PROCESAR_PENDIENTES('REPROCESO')`.
  - `PURGAR_TRANSITO(p_dias NUMBER DEFAULT 7)`: borra solo filas `PROCESADO` con más de `p_dias` días.
- `04_jobs.sql`: `JOB_PROCESAR_CAPTURAS` (`FREQ=SECONDLY;INTERVAL=60`) y `JOB_PURGA_TRANSITO` (`FREQ=DAILY`).
- `Store.run_batch(origen: str) -> tuple[int, int]` llama a `PROCESAR_PENDIENTES(origen)` y devuelve `(PROCESADOS, ERRORES)` de la última fila de `LOG_BATCH`.
- Esta tarea **no** llama a `CONCILIAR` (la Tarea 7 lo añade).

- [ ] **Step 1: Escribir tests** (helper `staging(uuid, seq, ts_ms, conteo, ubic, sku, cant, operador="Ana", nota="")` que inserta la línea `REC` sin CRC en `CAPTURA_TRANSITO`; usan el fixture `escenario`):
  `test_valid_row_becomes_procesado_with_typed_fields` (`REC|1|1731170400000|T-01|U1|A1|12.5|Ana|ok` → `PROCESADO`; en `REGISTROS_PROCESADOS`: `CANTIDAD=12.5`, `ID_CONTEO='T-01'`, `COD_UBICACION='U1'`, `SKU='A1'`, `OPERADOR='Ana'`, `NOTA='ok'`, `VIGENTE='S'`);
  `test_capture_timestamp_is_utc_from_epoch_ms` (`FECHA_CAPTURA = TIMESTAMP '2024-11-09 16:40:00'`);
  `test_recount_same_location_latest_wins` (`d1/seq1` ts 1000 cant 40 y `d2/seq1` ts 2000 cant 45 en `(T-01,U1,A2)` → la de 45 `VIGENTE='S'`, la de 40 `'N'`);
  `test_tie_same_timestamp_higher_id_transito_wins` (mismo ts desde dos dispositivos → `'S'` para la de `ID_TRANSITO` mayor);
  `test_older_reading_arriving_later_does_not_override` (llega primero ts 2000 y después ts 1000 → sigue vigente la de 2000);
  `test_same_sku_two_locations_both_vigente` (`A1` 60 en `U1` y 41 en `U2` → ambas `'S'`);
  `test_unknown_sku_marks_error_and_batch_continues` (fila con `ZZ9` → `ERROR`, `MENSAJE_ERROR='SKU_DESCONOCIDO'`; la fila siguiente válida → `PROCESADO`);
  `test_other_validation_errors` (parametrizado: ubicación `U9` → `UBICACION_DESCONOCIDA`; conteo `T-99` → `CONTEO_NO_ABIERTO`; cantidad `-1` y `1,5` → `CANTIDAD_INVALIDA`);
  `test_reprocesar_errores_after_adding_product` (tras insertar `ZZ9` en `PRODUCTOS` y llamar al procedimiento, la fila pasa a `PROCESADO`);
  `test_operator_and_note_roundtrip` (operador `Ñandú|Pérez`, nota `a|b\nc%ñ😀` codificados en el raw llegan idénticos);
  `test_long_note_and_operator_are_truncated` (nota de 300 caracteres → 255; operador de 80 → 60; sin `ERROR`);
  `test_empty_operator_and_note_are_null`;
  `test_quantity_parses_with_dot_under_comma_nls` (con `ALTER SESSION SET NLS_NUMERIC_CHARACTERS=',.'`, `12.5` sigue dando 12.5);
  `test_stale_procesando_row_is_recovered_and_fresh_one_is_not` (una fila `PROCESANDO` con `FECHA_RECLAMO` de hace 10 min termina `PROCESADO`; otra de hace 1 min queda `PROCESANDO`);
  `test_two_concurrent_batches_process_each_row_once` (200 filas válidas, dos hilos llamando a la vez → 200 filas en `REGISTROS_PROCESADOS`, ninguna `ORA-00001` sobre `ID_TRANSITO`);
  `test_purge_deletes_only_old_processed` (`PROCESADO` de 8 días se borra; `ERROR` y `PENDIENTE` de 8 días y `PROCESADO` de 1 día se conservan);
  `test_log_batch_row_written` (`PROCESADOS`, `ERRORES` y `ORIGEN='MANUAL'` correctos);
  `test_scheduler_job_is_defined_every_60_seconds` (`JOB_PROCESAR_CAPTURAS` existe en `USER_SCHEDULER_JOBS` con `repeat_interval='FREQ=SECONDLY;INTERVAL=60'`).
- [ ] **Step 2:** `docker compose run --rm pybase pytest server/tests/test_batch.py -v` → FAIL (`ORA-06550`/`PLS-00201`: el paquete no existe).
- [ ] **Step 3:** Escribir los `.sql`, el fixture y `Store.run_batch`.
- [ ] **Step 4:** Recrear la BD (`docker compose down -v && docker compose up -d --wait oracle`); `docker compose run --rm pybase pytest server/tests -v` → PASS, incluidas las suites de las Tareas 2, 4 y 5 (el job de 60 s está deshabilitado por `scheduler_off`).
- [ ] **Step 5: Commit** `feat(db): batch processing, recount rule, error reprocessing, purge`.

---

### Tarea 7: Conciliación, cierre de conteo y vistas

**Files:**
- Create: `db/init/05_views.sql`
- Modify: `db/init/03_pkg_batch.sql` (agrega `CONCILIAR` y `CERRAR_CONTEO`; `PROCESAR_PENDIENTES` llama a `CONCILIAR` al final por cada conteo afectado)
- Test: `server/tests/test_conciliacion.py`

**Interfaces:**
- Produces:
  - `PKG_BATCH.CONCILIAR(p_id_conteo VARCHAR2)`: recalcula `CONCILIACION` con las reglas de «Constraints globales» (unión de `STOCK_SISTEMA` y SKUs con lecturas vigentes). Debe ser idempotente y seguro si dos batches la llaman a la vez.
  - `PKG_BATCH.CERRAR_CONTEO(p_id_conteo VARCHAR2)`: `ESTADO='CERRADO'`, `FECHA_CIERRE=SYSTIMESTAMP`, los `SIN_CONTAR` pasan a `FALTANTE`.
  - Vistas: `V_RESUMEN_CONTEO(ID_CONTEO, SKUS_TOTALES, CONTADOS, AVANCE_PCT, OK, FALTANTES, SOBRANTES, EXACTITUD_PCT, VALOR_FALTANTE, VALOR_SOBRANTE)`; `V_DIF_CATEGORIA(ID_CONTEO, CATEGORIA, DIFERENCIA, VALOR_DIFERENCIA)`; `V_TOP_DESVIOS(ID_CONTEO, SKU, NOMBRE, CATEGORIA, DIFERENCIA, VALOR_DIFERENCIA, CLASIFICACION)` ordenada por `ABS(VALOR_DIFERENCIA)` desc (los `NULL` al final); `V_AVANCE_ZONA(ID_CONTEO, ZONA, UBICACIONES_CON_LECTURA, UBICACIONES_TOTALES)`; `V_ACTIVIDAD(ID_CONTEO, OPERADOR, HORA, REGISTROS)`; `V_ESTADO_BATCH(PENDIENTES, PROCESANDO, PROCESADOS, ERRORES, ULTIMO_RUN, ULTIMO_ORIGEN)`.

- [ ] **Step 1: Escribir tests** (con el fixture `escenario` y las lecturas de la tabla de «Convención de comandos de prueba», cargadas con `staging` y `PROCESAR_PENDIENTES`):
  `test_conciliacion_matches_scenario_exactly` (las 5 filas con sus valores exactos de la tabla, incluida `A4` `SIN_CONTAR` con `NULL` en dif/pct/valor y `A5` con `CANT_SISTEMA=0`, `DIFERENCIA_PCT` `NULL`);
  `test_resumen_matches_scenario_exactly` (`5, 4, 80.00, 1, 1, 2, 25.00, -5000, 11800`);
  `test_cerrar_conteo_turns_sin_contar_into_faltante` (`A4`: contada 0, dif −10, pct −100.00, valor −5000, `FALTANTE`; resumen `5, 5, 100.00, 1, 2, 2, 20.00, -10000, 11800`; `ESTADO='CERRADO'`);
  `test_tolerance_boundary_is_inclusive` (en `A1` sistema 100 y tolerancia 2 %: contada 102 → `OK`; contada 103 → `SOBRANTE`);
  `test_recount_updates_conciliation` (recontar `A2` con 50 en `U1`, más reciente → `A2` pasa a `OK`);
  `test_counted_sku_missing_from_snapshot_is_sobrante_with_system_zero` (`A5`);
  `test_v_dif_categoria_values` (Abarrotes −3000, Aseo 9000, Lácteos 2800 en `VALOR_DIFERENCIA`);
  `test_v_top_desvios_order` (`A3`, `A2`, `A5`, `A1`, `A4` por `ABS(VALOR_DIFERENCIA)`: 9000, 5000, 2800, 2000, `NULL`);
  `test_v_avance_zona` (`Z1` 2 de 2, `Z2` 0 de 1);
  `test_v_actividad_counts_by_operator` (`Ana` 3 registros, `Luis` 2);
  `test_v_estado_batch_counts` (con 1 `PENDIENTE` y 1 `ERROR` sembradas, devuelve `PENDIENTES=1`, `ERRORES=1`);
  `test_concurrent_batches_leave_same_conciliation_as_single_run`.
- [ ] **Step 2:** `docker compose run --rm pybase pytest server/tests/test_conciliacion.py -v` → FAIL (`PLS-00302`: `CONCILIAR` no existe).
- [ ] **Step 3:** Escribir `CONCILIAR`, `CERRAR_CONTEO`, la llamada desde `PROCESAR_PENDIENTES` y `05_views.sql`.
- [ ] **Step 4:** Recrear BD; `docker compose run --rm pybase pytest server/tests -v` → PASS (todas las suites del servidor).
- [ ] **Step 5: Commit** `feat(db): conciliation, close count and views`.

---

### Tarea 8: SPIKE Bluetooth desde contenedor (necesita el celular; alto riesgo, desechable)

**Files:**
- Create: `server/spikes/bluez_echo.py` (desechable), `docs/spikes/bluez.md`
- Modify: `docker-compose.yml` (servicio `bt-spike`, perfil `spike`)

**Objetivo:** probar con tu móvil real que un contenedor puede (a) hacerse visible/emparejable, (b) mostrar el código de 6 dígitos de BlueZ, (c) registrar el UUID del servicio y recibir una conexión RFCOMM, (d) hacer eco de lo que llega. **Independiente de las Tareas 1–7: puede ejecutarse en paralelo y en cualquier momento.**

- [ ] **Step 1:** Verificar en el host `bluetoothctl show` → `Powered: yes`. Anotar la versión de BlueZ (5.87).
- [ ] **Step 2:** Servicio `bt-spike` (perfil `spike`) con imagen `pybase` + `dbus-fast`, `network_mode: host`, `cap_add: [NET_ADMIN, NET_RAW]`, volumen `/var/run/dbus:/var/run/dbus`.
- [ ] **Step 3:** `bluez_echo.py`: con `dbus-fast`, (1) registrar `Agent1` capacidad `DisplayYesNo` cuyo `RequestConfirmation(device, passkey)` imprime el código y acepta tras `input()`, (2) `Adapter1`: `Powered=True`, `Pairable=True`, `Discoverable=True` con `DiscoverableTimeout=120`, (3) `ProfileManager1.RegisterProfile` con el UUID del servicio y `Role=server`, (4) en `NewConnection(device, fd, props)` leer y devolver cada línea.
- [ ] **Step 4:** `docker compose --profile spike run --rm bt-spike python server/spikes/bluez_echo.py`. Con una app de terminal serial Bluetooth en el móvil: emparejar, confirmar el código en ambos, enviar `hola` y ver el eco. Resultado esperado: el código aparece en el log y `hola` vuelve al móvil.
- [ ] **Step 5:** Si falla por permisos/D-Bus/namespace, probar en orden: política D-Bus (`/etc/dbus-1/system.d/`) para el usuario del contenedor; `privileged: true`; en último caso ejecutar la app de escritorio en el host y dejar Docker solo para Oracle. Documentar el resultado.
- [ ] **Step 6:** Escribir `docs/spikes/bluez.md` con lo que funcionó, flags finales de compose y el log. **Esta nota fija D5–D7 para la Tarea 9.**
- [ ] **Step 7: Commit** `docs: bluez-in-docker spike results`.

> Si el spike obliga a correr algo fuera de Docker, avisar antes de seguir: cambia el requisito "todo en Docker".

---

### Tarea 9: Controlador de sincronización (en proceso) y transporte BlueZ real

**Files:**
- Create: `server/btsync/controller.py`, `server/btsync/transports/bluez.py`, `server/spikes/controller_cli.py` (desechable)
- Modify: `server/btsync/transports/base.py` (agrega `begin_pairing` a `Transport`)
- Test: `server/tests/test_controller.py`

**Interfaces:**
- Consumes: `Session`, `Store`, `Connection`, `Transport` (Tarea 4), `Store.run_batch` (Tarea 6) y los hallazgos de `docs/spikes/bluez.md` (Tarea 8).
- Produces:
  - `Transport` gana `begin_pairing(on_passkey: Callable[[str], Awaitable[bool]]) -> None`.
  - `class SyncController`: `__init__(transport: Transport, store: Store, on_change: Callable[[dict], None], discoverable_s: int = 120)`; `start() -> None`; `confirm(accept: bool) -> None`; `cancel() -> None`; `status() -> dict` con `{"estado": str, "codigo": str|None, "recibidos": int, "restante_s": int, "ultimo_error": str|None}`. Trabaja en hilos propios y llama a `on_change(status)` en cada transición. Al terminar una `Session` con éxito pasa a `PROCESANDO`, ejecuta `store.run_batch("SYNC")` y pasa a `LISTO` (D9). Una sola sincronización a la vez (D19).
  - `class BluetoothUnavailable(Exception)` lanzada por `BluezTransport` si no hay adaptador, está bloqueado o no hay D-Bus.
  - `BluezTransport(adapter: str = "hci0", service_uuid: str = "7a1c0b52-4f0e-4d6a-9c3b-5e2a6d9f1b01")`.

- [ ] **Step 1: Escribir tests** con un `FakeTransport` y un `Store` espía: `test_start_moves_idle_to_waiting`; `test_passkey_callback_sets_confirm_state_and_code` (`CONFIRMAR_CODIGO`, `codigo == "123456"`); `test_confirm_false_rejects_pairing` (vuelve a `IDLE`); `test_timeout_returns_to_idle_and_stops_transport` (con `discoverable_s=1`, a los 2 s el estado es `IDLE` y `transport.stop` fue llamado); `test_session_end_runs_batch_once_then_listo` (estados observados en orden: `RECIBIENDO`, `PROCESANDO`, `LISTO`; `run_batch` llamado una vez con `"SYNC"`); `test_batch_failure_reports_error_and_controller_keeps_running` (`run_batch` lanza → `ultimo_error` empieza con `"BATCH:"` y `start()` sigue funcionando); `test_progress_event_updates_recibidos`; `test_start_twice_is_idempotent`; `test_on_change_called_on_every_transition`; `test_bluetooth_unavailable_sets_error_state_with_message`.
- [ ] **Step 2:** `docker compose run --rm pybase pytest server/tests/test_controller.py -v` → FAIL (`ImportError`).
- [ ] **Step 3:** Implementar el controlador. `BluezTransport` (según el spike): `Agent1` con `RequestConfirmation` que llama a `on_passkey` y espera la respuesta; `Adapter1` visible y emparejable con timeout y vuelta a no visible al terminar; `RegisterProfile`; `NewConnection(fd)` envuelve el fd en un `Connection`; con emparejamiento (`require_pairing=True`) solo se aceptan dispositivos `Paired`; sin claves (D22, el modo por defecto) se acepta cualquiera; una conexión activa (D19).
- [ ] **Step 4:** Mismo comando → PASS (10 tests, sin hardware).
- [ ] **Step 5: Prueba manual con hardware:** `controller_cli.py` (usa `SyncController` + `BluezTransport` + `Store` e imprime cada `on_change`) con `docker compose --profile spike run --rm bt-spike python server/spikes/controller_cli.py`; ver el código, emparejar el móvil real, enviar a mano `HELLO|…` y `REC|…` con CRC válido (generados con `python -m btsync.protocol --frame …`) desde la app de terminal serial, y verificar con `SELECT * FROM CAPTURA_TRANSITO` la fila y luego `PROCESADO`. Pegar el resultado en `docs/spikes/bluez.md`.
- [ ] **Step 6: Commit** `feat(server): in-process sync controller and bluez transport`.

---

### Tarea 10: Capa de datos de la app de escritorio

**Files:**
- Create: `desktop/Dockerfile`, `desktop/app/db.py`, `desktop/app/models.py`, `desktop/app/workers.py`
- Modify: `docker-compose.yml` (servicio `app`: build con `desktop/Dockerfile` y contexto en la raíz, `network_mode: host`, `DB_DSN=localhost:1521/XE`; Bluetooth y X11 los completa la Tarea 13)
- Test: `desktop/tests/test_db.py`, `desktop/tests/test_workers.py`

**Interfaces:**
- Produces (`db.py`, sin tocar la UI): `fetch_conteos() -> list[Conteo]`, `fetch_resumen(id_conteo: str) -> ResumenConteo` (los campos de `V_RESUMEN_CONTEO`), `fetch_conciliacion(id_conteo: str, clasificacion: str|None, categoria: str|None, texto: str|None, limit: int = 1000) -> list[FilaConciliacion]`, `fetch_dif_por_categoria(id_conteo: str) -> list[tuple[str, float]]`, `fetch_top_desvios(id_conteo: str, n: int = 10) -> list[FilaConciliacion]`, `fetch_distribucion(id_conteo: str) -> dict[str, int]`, `fetch_avance_zona(id_conteo: str) -> list[tuple[str, int, int]]`, `fetch_actividad(id_conteo: str) -> list[tuple[str, str, int]]`, `fetch_lecturas(id_conteo: str, sku: str) -> list[Lectura]` (ubicación, cantidad, operador, fecha, vigente), `fetch_estado_batch() -> EstadoBatch`, `fetch_errores(limit: int = 100) -> list[ErrorFila]`, `cerrar_conteo(id_conteo: str) -> None`, `reprocesar_errores(id_conteo: str|None) -> None`, `procesar_ahora() -> None`.
- `workers.py`: `class QueryWorker(QRunnable)` que ejecuta una función en un hilo del pool y emite `finished(result)` / `failed(msg)`.
- `Dockerfile` (contexto en la raíz): `pybase` + `libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1 fonts-dejavu` + `PyQt6 pyqtgraph pytest-qt dbus-fast`, e instala `server/` (`pip install ./server`) para importar `btsync`.

- [ ] **Step 1: Escribir tests** (con el fixture de conciliación `T-01` cargado como en la Tarea 7): `test_fetch_resumen_matches_scenario` (`5, 4, 80.00, 1, 1, 2, 25.00, -5000, 11800`); `test_fetch_conciliacion_filter_faltante_returns_only_a2`; `test_fetch_conciliacion_text_filter_a3_returns_one_row`; `test_top_desvios_order_a3_a2_a5_a1_a4`; `test_dif_por_categoria_values` (Abarrotes −3000, Aseo 9000, Lácteos 2800); `test_distribucion_counts` (`OK 1, FALTANTE 1, SOBRANTE 2, SIN_CONTAR 1`); `test_avance_zona_counts` (`Z1` 2 de 2, `Z2` 0 de 1); `test_fetch_lecturas_a1_returns_two_rows` (`U1` 60 y `U2` 41, ambas vigentes); `test_cerrar_conteo_turns_sin_contar_into_faltante`; `test_reprocesar_errores_moves_error_rows_to_processed_after_fix`; `test_worker_emits_failed_on_oracle_error`.
- [ ] **Step 2:** `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests/test_db.py desktop/tests/test_workers.py -v` → FAIL (`ImportError`).
- [ ] **Step 3:** Implementar. Los agregados se piden a Oracle con las vistas de la Tarea 7 (no se traen miles de filas a Python para sumar).
- [ ] **Step 4:** Mismo comando → PASS (11 tests).
- [ ] **Step 5: Commit** `feat(desktop): data layer and workers`.

---

### Tarea 11: Ventana principal y vistas Conteo y Conciliación

**Files:**
- Create: `desktop/app/main.py`, `desktop/app/views/base.py`, `desktop/app/views/conteo.py`, `desktop/app/views/conciliacion.py`
- Test: `desktop/tests/test_views_conteo.py`

**Interfaces:**
- Consumes: `db.fetch_*` y `QueryWorker` (Tarea 10).
- Produces:
  - `class RefreshableView(Protocol)` en `views/base.py`: `refresh() -> None`; `set_conteo(id_conteo: str) -> None`.
  - `class MainWindow(QMainWindow)`: `add_view(view: QWidget, title: str, index: int | None = None) -> None` (registra la pestaña y la incluye en el refresco), `refresh_requested = pyqtSignal()`, selector de conteo, `QTimer` de auto-refresco de 5 s. **Esta tarea solo registra `Conteo` y `Conciliación`**; las Tareas 12 y 13 agregan las demás con `add_view` (la ventana funciona con las pestañas que existan).
  - `ConteoView`: tarjetas KPI (avance %, exactitud %, valor faltante, valor sobrante, SKUs sin contar) y botón **«Cerrar conteo»** con diálogo de confirmación que explica que es irreversible.
  - `ConciliacionView`: tabla (`QAbstractTableModel`) con color por clasificación, filtros por clasificación/categoría/texto, doble clic abre el detalle de lecturas por ubicación (`fetch_lecturas`), exportar CSV.
- Regla: ninguna consulta corre en el hilo de la UI; estados de carga («Cargando…»), vacío («Sin datos») y error de BD (banner con Reintentar).

- [ ] **Step 1: Escribir tests** (pytest-qt, escenario `T-01`): `test_conteo_cards_show_scenario_kpis` (textos exactos `80,0 %`, `25,0 %`, `-$ 5.000`, `$ 11.800` y `1` SKU sin contar); `test_conciliacion_table_has_5_rows_and_filter_faltante_shows_1`; `test_double_click_a1_opens_detail_with_two_readings`; `test_cerrar_conteo_requires_confirmation_and_cancel_does_nothing`; `test_confirmed_cerrar_conteo_updates_cards` (tras confirmar: `100,0 %`, `20,0 %`, `-$ 10.000`); `test_add_view_registers_tab_and_includes_it_in_refresh`; `test_empty_db_shows_sin_datos_not_crash`; `test_db_error_shows_banner_and_retry_works`; `test_window_small_and_large_without_clipping` (800×600 y 1920×1080: el selector, las pestañas y las tarjetas son visibles y no se solapan).
- [ ] **Step 2:** `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests/test_views_conteo.py -v` → FAIL (`ImportError`).
- [ ] **Step 3:** Implementar `MainWindow` y las dos vistas (MVC ligero: `db.py` modelo, vistas pasivas, `MainWindow` como controlador).
- [ ] **Step 4:** Mismo comando → PASS (9 tests).
- [ ] **Step 5: Revisión visual:** `docker compose run --rm -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix app python -m app.main` y revisar a mano con datos sembrados por el fixture; guardar capturas en `docs/img/`.
- [ ] **Step 6: Commit** `feat(desktop): main window, conteo and conciliacion views`.

---

### Tarea 12: Vistas Gráficas y Perfil de datos

**Files:**
- Create: `desktop/app/views/charts.py`, `desktop/app/views/perfil.py`
- Modify: `desktop/app/main.py` (registra ambas con `add_view`)
- Test: `desktop/tests/test_views_charts.py`

**Interfaces:**
- Consumes: `db.fetch_*`, `MainWindow.add_view`, `RefreshableView` (Tarea 11).
- Produces:
  - `ChartsView` con cinco gráficos (pyqtgraph): valor de diferencia por categoría, top 10 desvíos, distribución `OK/FALTANTE/SOBRANTE/SIN_CONTAR`, avance por zona y actividad por operador. Para poder probarlos expone `bar_data(chart_id: str) -> list[tuple[str, float]]` (`chart_id` ∈ `categoria`, `desvios`, `distribucion`, `zona`, `actividad`).
  - `PerfilView` (**"cómo es la info"**): esquema de campos del conteo con tipo y significado, definición de cada clasificación con su regla y la tolerancia por categoría, estadísticas (registros por operador y por dispositivo, % de filas con error, rango de fechas capturadas).

- [ ] **Step 1: Escribir tests** (escenario `T-01`): `test_bar_data_categoria` (`[("Abarrotes", -3000), ("Aseo", 9000), ("Lácteos", 2800)]`); `test_bar_data_desvios_order` (`A3, A2, A5, A1`; `A4` no aparece porque su valor es `NULL`); `test_bar_data_distribucion` (`OK 1, FALTANTE 1, SOBRANTE 2, SIN_CONTAR 1`); `test_bar_data_zona` (`Z1 100.0`, `Z2 0.0`); `test_bar_data_actividad` (`Ana 3`, `Luis 2`); `test_perfil_lists_four_classifications_and_category_tolerances` (`A1`'s category muestra `2 %`); `test_perfil_shows_error_rate_and_operator_counts`; `test_views_show_sin_datos_when_empty`; `test_views_show_error_banner_and_retry`.
- [ ] **Step 2:** `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests/test_views_charts.py -v` → FAIL (`ImportError`).
- [ ] **Step 3:** Implementar ambas vistas.
- [ ] **Step 4:** Mismo comando → PASS (9 tests).
- [ ] **Step 5: Revisión visual:** abrir la app como en la Tarea 11 y comprobar que los cinco gráficos son legibles en 800×600 y en 1920×1080; guardar capturas en `docs/img/`.
- [ ] **Step 6: Commit** `feat(desktop): charts and data profile views`.

---

### Tarea 13: Vista Sincronización y Monitoreo (el "disparador")

**Files:**
- Create: `desktop/app/sync_bridge.py`, `desktop/app/views/sync.py`, `desktop/app/views/monitor.py`
- Modify: `desktop/app/main.py` (elige el transporte con `BT_TRANSPORT=bluez|tcp` y registra `Sincronización` en el índice 0 y `Monitoreo` al final con `add_view`), `docker-compose.yml` (servicio `app`: Bluetooth de la Tarea 8, `DISPLAY`, `XAUTHORITY`, volúmenes `/tmp/.X11-unix` y el archivo de `XAUTHORITY`)
- Test: `desktop/tests/test_sync_view.py`

**Interfaces:**
- Consumes: `SyncController`, `Transport`, `BluetoothUnavailable` (Tarea 9), `MainWindow.add_view` (Tarea 11) y `QueryWorker` (Tarea 10).
- Produces:
  - `class SyncBridge(QObject)`: señal `status_changed(dict)`; métodos `start()`, `confirm(accept: bool)`, `cancel()`. Envuelve a `SyncController` con `on_change` → `status_changed.emit`, así los hilos del BT nunca tocan widgets. Al llegar a `LISTO` emite `MainWindow.refresh_requested`.
  - `SyncView`: botón **«Iniciar sincronización»**, código de 6 dígitos grande, botones **Aceptar / Rechazar**, barra de progreso con `recibidos`, cuenta regresiva `restante_s` y estado en texto claro. Un solo progreso: si llega un segundo teléfono el controlador lo rechaza (D19) y la vista no cambia.
  - `MonitorView`: estado del servicio BT, tarjetas con pendientes / procesados / errores (de `V_ESTADO_BATCH`), último run del batch, tabla de errores recientes con botón **«Reprocesar errores»**, y botón **«Procesar ahora»** (ambos en un worker).

- [ ] **Step 1: Escribir tests** con un `FakeTransport`: `test_start_button_starts_bridge_and_shows_waiting`; `test_confirm_state_shows_code_and_buttons` (código `123456` visible en grande y botones habilitados); `test_accept_button_confirms_true`; `test_reject_button_confirms_false`; `test_bluetooth_unavailable_shows_message_not_crash` (texto «Bluetooth no disponible»); `test_listo_emits_refresh_requested`; `test_monitor_cards_reflect_estado_batch` (1 pendiente y 1 error sembrados); `test_procesar_ahora_and_reprocesar_run_off_ui_thread` (la UI sigue respondiendo mientras el worker corre); `test_sync_and_monitor_tabs_registered_in_expected_order`.
- [ ] **Step 2:** `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests/test_sync_view.py -v` → FAIL (`ImportError`).
- [ ] **Step 3:** Implementar y completar el servicio `app` en compose.
- [ ] **Step 4:** Mismo comando → PASS (9 tests).
- [ ] **Step 5: Prueba integrada sin móvil:** `BT_TRANSPORT=tcp docker compose up -d oracle app` con `DISPLAY` y X11; pulsar Iniciar en la ventana y ejecutar `docker compose run --rm pybase python tools/fake_phone.py --host localhost --port <puerto> --seed 42 --dirty --uuid dev-demo`. Ver: progreso, conciliación actualizada, 3 errores del conteo sucio en Monitoreo, gráficos refrescados. Resultado esperado: tras `LISTO`, `SELECT COUNT(*) FROM CAPTURA_TRANSITO WHERE ESTADO='ERROR'` = 3 (SKU desconocido, ubicación inexistente y su recuento inválido), y no hay `PENDIENTE`.
- [ ] **Step 6: Commit** `feat(desktop): sync trigger and monitor views`.

---

### Tarea 14: Android — núcleo (protocolo, Outbox, catálogo y cliente de sincronización)

**Files:**
- Create: proyecto `mobile/` (Kotlin, `minSdk 26`, paquete `com.sebasarchive.kardex`, `allowBackup="false"`), `mobile/Dockerfile` (JDK 17 + Android command-line tools), servicio `apk-build` en compose (perfil `build`); código sin UI: `Protocol.kt`, `Outbox.kt` (+ Room), `CatalogRepository.kt`, `SyncClient.kt`, `DeviceIdentity.kt`
- Test: `ProtocolTest.kt`, `OutboxTest.kt`, `SyncClientTest.kt`, `DeviceIdentityTest.kt`

**Interfaces:**
- Produces (Kotlin, mismos nombres que Python): `Protocol.frame(fields: List<String>): ByteArray`, `Protocol.parse(line: ByteArray): Message`, `Rec`; `Outbox` (Room, `LecturaEntity(seq PK autoincrement, tsOriginalMs, idConteo, ubicacion, sku, cantidad, operador, nota, estado: PENDIENTE|ENVIADO|CONFIRMADO)`; `insertar(l): Long`, `pendientesDesde(seq: Long): List<LecturaEntity>`, `confirmarHasta(seq: Long)`, `reemplazar(idConteo, ubicacion, sku, cantidad)`); `CatalogRepository` (conteos, ubicaciones y productos recibidos; **sin stock**; `reemplazarTodo(c: Catalog)`); `DeviceIdentity.get(context): String` (UUID generado una vez y persistido); `SyncClient.sync(socket: BluetoothSocketLike): Flow<SyncProgress>` con `BluetoothSocketLike` (interfaz con `input/output stream`) para probar sin radio. El cliente: envía `HELLO`, lee `READY|<seq>|<epoch_ms>`, calcula `offset` (D15) y envía `ts = tsOriginalMs + offset` **sin modificar** la fila; ventana de 50; ante `NAK|n|motivo` retrocede a `n` (go-back-N); ante `NAK|0|OCUPADO` termina con `SyncProgress.Busy`; marca `CONFIRMADO` hasta el `ACK` recibido; reintenta tras corte.

- [ ] **Step 1: Escribir tests JVM:** `ProtocolTest.test_frame_and_parse_match_all_shared_vectors` (lee `docs/protocol-vectors.json`, los **mismos** 7 vectores que Python: si falla en un lenguaje, el protocolo es inconsistente); `OutboxTest.test_confirmarHasta_marks_all_leq_seq`; `OutboxTest.test_reemplazar_updates_existing_reading_for_same_location_and_sku`; `SyncClientTest.test_sends_in_windows_of_50_and_marks_confirmed`; `SyncClientTest.test_go_back_n_on_nak_resends_from_expected_seq`; `SyncClientTest.test_resumes_from_ready_seq_after_cut`; `SyncClientTest.test_timestamps_use_server_offset` (reloj del móvil +600000 ms → `ts` enviado a ≤ 2000 ms del servidor); `SyncClientTest.test_retry_does_not_apply_offset_twice` (reintento tras corte; `tsOriginalMs` intacto en la `Outbox`); `SyncClientTest.test_busy_nak_ends_with_busy`; `DeviceIdentityTest.test_uuid_generated_once_and_persisted`.
- [ ] **Step 2:** `docker compose --profile build run --rm apk-build ./gradlew testDebugUnitTest` → FAIL (clases sin implementar).
- [ ] **Step 3:** Implementar. Guardar siempre en la `Outbox` primero; la sincronización usa corrutinas en un hilo de E/S.
- [ ] **Step 4:** Mismo comando → `BUILD SUCCESSFUL` con los 10 tests; `./gradlew assembleDebug` compila.
- [ ] **Step 5: Commit** `feat(mobile): protocol, outbox, catalog and sync client`.

---

### Tarea 15: Android — pantallas, escáner, permisos y prueba con el celular

**Files:**
- Create: pantallas y `CountViewModel.kt`, `SettingsStore.kt` (operador), integración ZXing embebido, manejo de permisos
- Test: `CountViewModelTest.kt`

**Interfaces:**
- Consumes: `Outbox`, `CatalogRepository`, `SyncClient`, `DeviceIdentity` (Tarea 14).
- Produces:
  - `CountViewModel`: `guardar(ubicacion: String, sku: String, cantidad: String, nota: String): SaveResult`, `ultimaLectura(ubicacion, sku): LecturaEntity?`, `operador: StateFlow<String>`, `setOperador(nombre: String)`. Reglas: operador obligatorio (máx. 60 caracteres, se recuerda), nota máx. 255, cantidad con el formato del protocolo, SKU fuera del catálogo = advertencia pero se puede guardar, recontar reemplaza.
  - Pantallas: **Operador** (primer uso y editable), **Elegir conteo y ubicación**, **Contar** (escáner ZXing o digitación del SKU, nombre del producto desde el catálogo, teclado numérico con +/−), **Contado en esta ubicación** (lista editable), **Pendientes** (con estado), **Sincronizar** (D22: conecta de inmediato al PC recordado con socket inseguro, sin emparejar ni códigos; la primera vez busca `gestion_inventario` y se elige; progreso, resultado `BYE`, reintento automático, mensaje claro si el PC está ocupado o apagado).
  - Permisos Android 12+: `BLUETOOTH_CONNECT`, `BLUETOOTH_SCAN`, cámara; rechazo con mensaje claro. El primer uso sin catálogo avisa que hay que sincronizar una vez con el PC.

- [ ] **Step 1: Escribir tests JVM:** `test_save_requires_operator_name`; `test_operator_over_60_chars_is_rejected`; `test_invalid_quantity_blocks_save` (`"1,5"`, `"-1"`, `"1.2345"`, `""`); `test_unknown_sku_warns_but_can_save`; `test_recount_replaces_previous_in_same_location`; `test_note_over_255_chars_is_rejected`; `test_operator_and_note_with_pipe_and_newline_are_encoded_in_rec`.
- [ ] **Step 2:** `docker compose --profile build run --rm apk-build ./gradlew testDebugUnitTest --tests '*CountViewModelTest'` → FAIL.
- [ ] **Step 3:** Implementar `CountViewModel` y las pantallas.
- [ ] **Step 4:** Mismo comando → `BUILD SUCCESSFUL` (7 tests); `./gradlew assembleDebug` genera `app-debug.apk`.
- [ ] **Step 5: Instalar y probar con hardware:** `adb install -r mobile/app/build/outputs/apk/debug/app-debug.apk` (adb del host). En modo avión, fijar el operador y contar ~30 productos en 3 ubicaciones (con escáner y a mano, incluyendo un recuento). Pulsar Iniciar en el PC, emparejar, sincronizar y verificar la conciliación en la app de escritorio. Probar corte: apagar el Bluetooth del móvil a mitad y reintentar; resultado esperado: `SELECT COUNT(*) FROM CAPTURA_TRANSITO` igual al número de lecturas guardadas, sin duplicados.
- [ ] **Step 6: Commit** `feat(mobile): inventory screens, scanner and permissions`.

---

### Tarea 16: UML — infraestructura y diagramas de estructura (01–09)

**Files:**
- Create: `docs/uml/01…09-*.puml`, `tools/check_uml.py`, `tools/render_uml.sh`
- Modify: `docker-compose.yml` (servicio `plantuml`, perfil `docs`, imagen `plantuml/plantuml` con tag fijado al ejecutar, volumen `./docs:/docs`)
- Test: `server/tests/test_uml.py`

**Interfaces:**
- Produces: `tools/check_uml.py` con `check_classes(puml: Path, code_roots: list[Path]) -> list[str]`: devuelve los nombres de clase de un diagrama de clases que **no existen** en el código (`class X` en Python o Kotlin). Cada diagrama de clases declara su raíz de código en una línea `' @code: server/btsync`. `tools/render_uml.sh` ejecuta `docker compose --profile docs run --rm plantuml -tsvg -failonerror -o img/uml uml/*.puml`.
- Se escribe **después** de las Tareas 4–15 para que los diagramas reflejen firmas reales. PlantUML porque cubre todos los tipos UML; Mermaid no tiene casos de uso, despliegue, estructura compuesta ni tiempos.

| Archivo | Tipo UML | Qué muestra |
|---|---|---|
| `01-clases-servidor.puml` | Clases | `Message`, `Rec`, `FrameError`, `Catalog`, `Store`, `Session`, `SyncController`, `«interface» Transport` y `Connection`, `BluezTransport`, `TcpTransport`, `BluetoothUnavailable` |
| `02-clases-escritorio.puml` | Clases | `MainWindow`, `SyncBridge`, `QueryWorker`, las seis vistas y el módulo `db` |
| `03-clases-android.puml` | Clases | `CountViewModel`, `CatalogRepository`, `Outbox`, `LecturaEntity`, `SyncClient`, `Protocol`, `SyncProgress`, `DeviceIdentity` |
| `04-modelo-datos.puml` | Clases con `«table»` (entidad-relación) | Todas las tablas con PK, FK y cardinalidades |
| `05-objetos-instantanea.puml` | Objetos | Una lectura real: línea `REC` → fila de `CAPTURA_TRANSITO` → `REGISTROS_PROCESADOS` → `CONCILIACION`, con los valores del escenario `T-01` |
| `06-componentes.puml` | Componentes | App Android, app de escritorio (vistas, `SyncBridge`, librería `btsync`), Oracle (`PKG_BATCH`, Scheduler), BlueZ, con interfaces provistas y requeridas (RFCOMM, SQL*Net, D-Bus) |
| `07-despliegue.puml` | Despliegue | Celular, PC host (`bluetoothd`, XWayland, Docker con `oracle`, `app`, `apk-build`), enlaces RFCOMM, socket D-Bus, socket X11, puerto 1521 |
| `08-paquetes.puml` | Paquetes | Módulos de `btsync`, `desktop.app` y `mobile`, y sus dependencias |
| `09-estructura-compuesta.puml` | Estructura compuesta | Interior de `SyncController`: puertos hacia el transporte, el repositorio y la GUI, y sus partes (sesión, agente de emparejamiento, temporizador) |

- [ ] **Step 1: Escribir tests** en `test_uml.py`: `test_every_puml_has_start_end_and_title` (sobre los archivos presentes); `test_class_diagrams_match_code` (`check_classes` sobre `01`, `02` y `03` con sus raíces `server/btsync`, `desktop/app`, `mobile/app/src/main` → lista vacía); `test_check_classes_reports_a_missing_class` (un `.puml` de prueba con la clase inventada `Fantasma` → devuelve `["Fantasma"]`).
- [ ] **Step 2:** `docker compose run --rm pybase pytest server/tests/test_uml.py -v` → FAIL (`ImportError`).
- [ ] **Step 3:** Implementar `check_uml.py` y `render_uml.sh`; añadir el servicio `plantuml`.
- [ ] **Step 4:** Escribir los `.puml` 01–09 con las firmas y los nombres reales del código ya implementado.
- [ ] **Step 5:** `tools/render_uml.sh` termina con código 0 y existen 9 SVG en `docs/img/uml/`. Abrir al menos `07` en el navegador y comprobar que es legible (texto no cortado, flechas sin cruces ilegibles); si no, dividir el diagrama.
- [ ] **Step 6:** `docker compose run --rm pybase pytest server/tests/test_uml.py -v` → PASS (3 tests).
- [ ] **Step 7: Commit** `docs: uml infrastructure and structure diagrams`.

---

### Tarea 17: UML — diagramas de comportamiento e interacción (10–22) e índice

**Files:**
- Create: `docs/uml/10…22-*.puml`, `docs/uml/README.md` (índice)
- Test: `server/tests/test_uml.py` (se amplía)

| Archivo | Tipo UML | Qué muestra |
|---|---|---|
| `10-casos-de-uso.puml` | Casos de uso | Actores Operario, Administrador y Scheduler de Oracle; casos: contar, escanear, recontar, sincronizar, confirmar código, conciliar, ver gráficas, cerrar conteo, reprocesar errores, exportar CSV, purgar tránsito, con `«include»`/`«extend»` |
| `11-actividad-conteo-movil.puml` | Actividad con carriles | Flujo del operario en el móvil, de elegir conteo a guardar y sincronizar |
| `12-actividad-batch.puml` | Actividad con carriles (Móvil / App / Oracle) | De la subida al `ACK`, y `PROCESAR_PENDIENTES` paso a paso: recuperar huérfanas, reclamar, parsear, validar, recontar, conciliar, registrar |
| `13-secuencia-sincronizacion.puml` | Secuencia | Emparejamiento → `HELLO` → `READY` → catálogo → `REC` → `ACK` → `END` → `BYE` → batch → refresco de la GUI |
| `14-secuencia-corte-reanudacion.puml` | Secuencia | Corte a mitad de lote, `READY\|25`, y reenvío con go-back-N sin duplicados |
| `15-secuencia-errores-y-cierre.puml` | Secuencia | Fila en `ERROR`, alta del producto, `REPROCESAR_ERRORES` y `CERRAR_CONTEO` |
| `16-estados-sync-controller.puml` | Máquina de estados | `IDLE … ERROR` con eventos y guardas (timeout, rechazo, corte, ocupado) |
| `17-estados-fila-transito.puml` | Máquina de estados | `PENDIENTE → PROCESANDO → PROCESADO \| ERROR → PENDIENTE`, incluida la recuperación de huérfanas |
| `18-estados-lectura-outbox.puml` | Máquina de estados | `PENDIENTE → ENVIADO → CONFIRMADO` y regreso a `PENDIENTE` tras un corte |
| `19-estados-conteo.puml` | Máquina de estados | `ABIERTO → CERRADO` y el efecto sobre la clasificación `SIN_CONTAR` |
| `20-comunicacion.puml` | Comunicación | Colaboración numerada entre `Session`, `Store`, `SyncController`, `PKG_BATCH` y `SyncBridge` |
| `21-vision-interaccion.puml` | Visión general de interacción | Flujo de alto nivel que enlaza los diagramas 13, 14 y 15 con decisiones |
| `22-tiempos.puml` | Tiempos | Ventana de 120 s de emparejamiento y ventana de 50 `REC` entre `ACK` |

El **diagrama de perfiles** no aplica (no se define ningún perfil UML propio); el índice lo dice explícitamente.

- [ ] **Step 1: Escribir tests** (se agregan a `test_uml.py`): `test_index_lists_every_puml_and_nothing_else` (los 22 archivos de `docs/uml/` están en `README.md` y viceversa); `test_index_covers_all_applicable_uml_types` (el índice menciona casos de uso, clases, objetos, componentes, despliegue, paquetes, estructura compuesta, actividad, secuencia, comunicación, máquina de estados, visión de interacción y tiempos, y dice que *perfiles* no aplica); `test_every_puml_has_start_end_and_title` (ahora sobre los 22).
- [ ] **Step 2:** `docker compose run --rm pybase pytest server/tests/test_uml.py -v` → FAIL (faltan `10`–`22` y el índice).
- [ ] **Step 3:** Escribir los `.puml` 10–22 con los nombres reales de mensajes y clases, y el índice `docs/uml/README.md` (tabla de las dos tablas de arriba más una frase de lectura por diagrama).
- [ ] **Step 4:** `tools/render_uml.sh` termina con código 0 y existen **22** SVG en `docs/img/uml/` (`ls docs/img/uml/*.svg | wc -l` → `22`). Abrir `13` y `16` en el navegador y comprobar legibilidad.
- [ ] **Step 5:** `docker compose run --rm pybase pytest server/tests/test_uml.py -v` → PASS (5 tests).
- [ ] **Step 6: Commit** `docs: uml behavior and interaction diagrams (22 in total)`.

---

### Tarea 18: Documentación, demo y verificación final

**Files:**
- Create/Modify: `README.md`, `docs/arquitectura.md`, `docs/demo.md`, `docs/img/`

- [ ] **Step 1:** `docs/arquitectura.md`: introducción por capas, **incrusta los 22 SVG de `docs/img/uml/`** agrupados en Estructura / Comportamiento / Interacción con una frase de lectura cada uno, decisiones D1–D20 con su justificación y los límites conocidos (D15), y el patrón MVC/MVVM de cada app.
- [ ] **Step 2:** `README.md`: requisitos del host, `docker compose up -d --wait oracle` y `docker compose up -d app` (la app se abre en tu pantalla por X11), cómo compilar e instalar la APK, y solución de problemas (Bluetooth bloqueado, `DISPLAY`, `ORA-xxxx`). Advertir **no desinstalar la APK con lecturas pendientes** (D18) y que solo se sincroniza un teléfono a la vez (D19).
- [ ] **Step 3:** `docs/demo.md`: guion de 5 minutos (contar offline con el escáner → disparar en el PC → código → subida → batch → conciliación → mostrar un faltante con su valor en pesos → cerrar conteo), con el plan B si falla el Bluetooth (modo TCP + `fake_phone.py`).
- [ ] **Step 4: Verificación completa:** desde cero, `docker compose down -v && docker compose up -d --wait oracle`; correr `docker compose run --rm pybase pytest server/tests -v`, `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -v` y `docker compose --profile build run --rm apk-build ./gradlew testDebugUnitTest`; ejecutar la demo con el móvil real y registrar el tiempo medio de inserción medido. **Reportar lo que falle o no se haya podido verificar, sin adornar.**
- [ ] **Step 5: Commit** `docs: architecture, readme and demo script`.

---

## Cobertura de la rúbrica

| Criterio (peso) | Dónde se cubre |
|---|---|
| Funcionalidad y requisitos técnicos (25 %) | Tareas 4–7, 9, 13–15: conteo, Bluetooth, Oracle, batch con conciliación y GUI de extremo a extremo; Tareas 5 y 18 lo demuestran |
| Conectividad y comunicación (25 %) | Protocolo con CRC, ACK acumulativo, go-back-N, reanudación, idempotencia, corrección de reloj y rechazo de segundo teléfono (Tareas 3–5, 9, 14); Review Focus 1, 2 y 6 |
| Arquitectura y código (20 %) | Capas separadas, transporte intercambiable, batch fuera de la sesión, MVC/MVVM, hilos fuera de la UI (Tareas 4, 9–15) |
| UX y adaptabilidad (15 %) | Tareas 11–13 y 15: estados de carga/error/vacío, prueba de redimensionado, confirmación al cerrar conteo, código de emparejamiento claro, escáner con alternativa manual |
| Documentación y presentación (15 %) | Tareas 16–18: 22 diagramas UML de 13 tipos, manual de arquitectura, instalación y despliegue, guion de demo |

## Auto-revisión

- **Cobertura del contexto:** móvil sin wifi → Tareas 14–15; BT al PC con servidor que "da un código y empareja" → Tareas 8, 9 y 13; dispara el batch con Oracle → Tareas 6, 7 y 9 (D9); app que muestra cómo es la info y grafica → Tareas 11 y 12; Oracle 11g → D2; todo en Docker → compose (`oracle`, `pybase`, `app`, `apk-build`, `plantuml`, `bt-spike`) con la excepción declarada de `bluetoothd` y `adb`, que viven en el host; móvil = APK y PC = una sola app de escritorio (D11); tema inventario (D1, D12–D16); UML completo (D17).
- **Contradicciones de la revisión resueltas:** (1) `Session` no corre el batch; `BYE` cuenta lo aceptado en staging y el controlador dispara el batch después (D9, Tareas 4 y 9); (2) `MainWindow` se crea con las pestañas que existen y las demás se agregan con `add_view` (Tareas 11–13); (3) el desempate de D13 usa `ID_TRANSITO`, global; (4) `CONCILIACION` es la unión de la foto de stock y los SKUs con lecturas, con el caso `A5` probado; (5) el spike de hardware pasó a la Tarea 8, fuera del tramo sin hardware, y se indica que puede correr en paralelo.
- **Huecos de la revisión resueltos:** UUID e identidad (D18); origen del operador (D20, Tarea 15); nota larga truncada a 255 y operador a 60; `VARCHAR2(n CHAR)` y `TO_NUMBER` con máscara fija; fila `PROCESANDO` huérfana recuperada tras 5 min y `UNIQUE(ID_TRANSITO)` como red de seguridad; offset de reloj sobre `tsOriginalMs` sin acumulación (D15); una sola sincronización a la vez (D19); hueco de `seq` con go-back-N; `pybase`, `pyproject.toml` y `python -m btsync.protocol` ahora se crean (Tareas 1 y 3).
- **Skill:** los pasos de prueba traen el comando y el resultado esperado; los valores exactos salen del fixture `escenario_conciliacion.sql` y de los 7 vectores del protocolo (no de la semilla); las Tareas 10, 12 y 13 originales se dividieron en 11/12/13, el Android en 14/15 y el UML en 16/17.
- **Riesgos abiertos:** D1, D2, D4 y D14 siguen siendo supuestos por confirmar; D7 (Bluetooth desde contenedor, validado solo en la Tarea 8); compatibilidad Instant Client 19 ↔ 11.2.0.2 (se prueba en la Tarea 1; plan B 12.2); D8 deja el cifrado al enlace BlueZ aunque el PDF pedía cifrar el canal; imagen XE 11g solo x86_64 (tu equipo lo es).
