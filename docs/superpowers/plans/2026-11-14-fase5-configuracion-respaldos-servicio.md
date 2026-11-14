# Fase 5: configuración, respaldos y servicio Bluetooth independiente. Plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: superpowers:executing-plans (el usuario eligió Native en la Fase 1). Pasos con casillas (`- [ ]`).

**Meta:**
- El Administrador cambia desde una pantalla los valores que hoy están fijos en el código.
- El Administrador crea, lista y restaura respaldos (`.zip`), y programa uno automático diario.
- El receptor Bluetooth es un programa aparte que arranca con el sistema y recibe aunque el escritorio esté cerrado; el escritorio ve su estado y lo pausa o reanuda.

**Arquitectura:**
- **Lo compartido va en `server/btsync/`** (lo usan el servicio y el escritorio): `config.py` (tabla `CONFIGURACION`), `servicio.py` (el programa del receptor y su tabla `SERVICIO_BT`) y `respaldo.py` (crear, listar, podar y restaurar zips). El escritorio los envuelve con permisos y auditoría en `desktop/app/configuracion.py`, `desktop/app/servicio.py` y `desktop/app/respaldos.py`.
- **Servicio:** `python -m btsync.servicio` reutiliza `SyncController` sin cambiarlo. Un bucle de 1 s (`Servicio.tick()`) escribe el latido y el estado en `SERVICIO_BT`, lee la pausa y la respuesta al código de emparejamiento, vuelve a abrir la ventana de visibilidad cuando el controlador queda en reposo y lanza el respaldo automático. En Docker, servicio `bluetooth` con `restart: unless-stopped` (arranca con `docker compose up -d` y con el sistema).
- **El escritorio deja de tener receptor propio:** se borra `desktop/app/sync_bridge.py`; `ServicioRemoto` (QObject, mismas señales `status_changed(dict)` y `listo()`) lee `SERVICIO_BT` cada 2 s fuera del hilo de la interfaz. Cerrar la ventana o la sesión ya no detiene la recepción.
- **Respaldo:** un zip con `manifest.json`, `datos/<TABLA>.jsonl` y `fotos/…`. Restaurar reemplaza **todo** en una sola transacción de Oracle.

**Stack:** Python 3.12 + PyQt6 + python-oracledb + Oracle XE 11g (DBMS_SCHEDULER); Docker Compose. El móvil no cambia.

**Spec:**
- Especificación pegada por el usuario (módulos «Configuración general» y «Respaldos» de la matriz, ambos solo para el Administrador) y la Fase 5 del plan de fases («configuración, respaldos y servicio Bluetooth independiente»). No existe un documento aparte.
- El boceto se aprobó el 2026-11-14 con estas decisiones del usuario: respaldo en **zip** hecho por la app, restaurar **todo**, y **pausar** el servicio desde el escritorio.

## Restricciones globales
- **Claves de configuración** (`btsync.config.DEFAULTS`), con rango y valor inicial:

  | clave | rango | inicial | quién la usa |
  |---|---|---|---|
  | `ajustes.umbral_pct` | entero 1–100 | 10 | `movimientos.es_critico` |
  | `ajustes.umbral_valor` | entero 0–1 000 000 000 | 200000 | `movimientos.es_critico` |
  | `lote.intervalo_s` | entero 10–3600 | 60 | `JOB_PROCESAR_CAPTURAS` (`repeat_interval`) |
  | `staging.purga_dias` | entero 1–365 | 7 | `JOB_PURGA_TRANSITO` (`job_action`) |
  | `fotos.max_mb` | entero 1–10 | 2 | `Session` (`FOTOERR GRANDE`) |
  | `respaldos.auto` | `S`/`N` | `S` | servicio |
  | `respaldos.hora` | `HH:MM` 00:00–23:59 | `23:00` | servicio |
  | `respaldos.conservar` | entero 1–90 | 7 | poda de los automáticos |

- **Carpeta de fotos:** en Configuración se **muestra** (`fotos_dir()`, de `FOTOS_DIR`), no se edita; con el texto «Se define al instalar (FOTOS_DIR). Las fotos ya guardadas no se mueven.»
- **Carpeta de respaldos:** `RESPALDOS_DIR` (por defecto `respaldos/`, `/work/respaldos` en Docker), fuera de git. Nombre del archivo: `respaldo-AAAAMMDD-HHMMSS-<origen>.zip`, `origen` ∈ `manual`, `auto`, `previo` (el que se hace antes de restaurar). La poda solo borra los `auto` y conserva los `respaldos.conservar` más recientes.
- **Qué entra en el respaldo:** todas las tablas del usuario de Oracle menos las que terminan en `_TST` y menos `SERVICIO_BT`; más la carpeta de fotos. `manifest.json`: `{"formato": 1, "fecha", "usuario", "origen", "tablas": {TABLA: {"columnas": [...], "filas": n}}, "secuencias": {SEQ: last_number}, "fotos": n}`. Los datos se leen en una transacción `SET TRANSACTION READ ONLY` (instantánea coherente). Los NUMBER se guardan como texto decimal exacto y los TIMESTAMP en ISO 8601; ida y vuelta sin pérdidas.
- **Restaurar:**
  - exige el servicio en `PAUSADO` (lo pausa y espera hasta 30 s; si no llega: «El servicio Bluetooth no se detuvo; inténtalo de nuevo»);
  - crea antes un respaldo `previo`;
  - deshabilita los dos jobs, borra e inserta todas las tablas en **una** transacción (borrar de hijas a padres e insertar de padres a hijas, orden sacado de `USER_CONSTRAINTS`), confirma, adelanta cada secuencia hasta al menos el `last_number` del manifiesto y vuelve a habilitar los jobs (también si algo falló);
  - las fotos se extraen a `<FOTOS_DIR>.nueva` y se cambian por la carpeta actual solo después del COMMIT;
  - se niega con «Este respaldo es de otra versión del sistema» si el formato no es 1, o si el respaldo trae una tabla o columna que la base no tiene (las columnas que la base tiene y el respaldo no toman su valor por defecto);
  - al terminar, el escritorio cierra la sesión (las cuentas pudieron cambiar) y deja el servicio pausado, con el aviso «Respaldo restaurado. Reanuda el servicio Bluetooth cuando quieras.».
- **Confirmación de restaurar:** un diálogo que pide escribir `RESTAURAR` exactamente; el botón Aceptar está deshabilitado hasta entonces.
- **`SERVICIO_BT`** (una fila, `id = 1`): `estado`, `codigo`, `recibidos`, `ultimo_error`, `desde` (arranque), `latido`, `pausado` (`S`/`N`), `respuesta` (`S`/`N`/NULL, al código). Estados que ve el escritorio: los de `SyncController` más `PAUSANDO`, `PAUSADO` y `DETENIDO` (latido de hace más de 10 s, o no hay fila).
- **Pausar no corta una sincronización en curso:** si el controlador está en `CONECTADO`, `RECIBIENDO` o `PROCESANDO`, el servicio pasa a `PAUSANDO` y llama a `cancel()` solo al llegar al reposo.
- **Permisos y auditoría:**
  - Configuración: `configuracion` (GESTION); auditoría `("configuracion", "Cambió configuración", "<clave>: <antes> → <después>")`, una fila por clave cambiada.
  - Respaldos: `respaldos` (GESTION); `("respaldos", "Creó respaldo" | "Restauró respaldo" | "Cambió respaldo automático", <archivo o detalle>)`. El respaldo automático audita con usuario `servicio`.
  - Servicio: `bluetooth` (GESTION); `("bluetooth", "Pausó servicio" | "Reanudó servicio" | "Aceptó código" | "Rechazó código", "")`.
  - `configuracion` y `respaldos` entran en `EN_USO`. La auditoría de Inventario no ve los módulos `configuracion` ni `respaldos`.
- **`DBMS_SCHEDULER.SET_ATTRIBUTE` confirma por su cuenta:** `configuracion.guardar` escribe valores y auditoría, hace COMMIT y después ajusta los jobs; si ajustar un job falla, el valor ya guardado se reaplica en el siguiente arranque del escritorio (`configuracion.aplicar_jobs()` en `main.py`).
- Toda consulta a Oracle, y toda lectura o escritura de zips, va fuera del hilo de la interfaz. Sin commits hasta que el usuario los pida.
- **Comandos:**
  - servidor: `docker compose run --rm app pytest server/tests -q`
  - escritorio: `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -q`

## Review Focus
1. **Restaurar mientras un teléfono sincroniza o el job procesa:** nada se mezcla. Se espera la pausa, los jobs quedan deshabilitados durante el reemplazo y se vuelven a habilitar siempre.
2. **Un respaldo dañado o de otra versión falla a mitad de la restauración:** la base queda exactamente como estaba (ROLLBACK), las fotos actuales siguen en su sitio y el respaldo `previo` existe.
3. **El servicio está caído (proceso muerto, sin latido):** el escritorio dice «El servicio Bluetooth no está corriendo», no el último estado que quedó escrito.
4. **Disco lleno o sin permiso al crear un respaldo:** no queda un `.zip` a medias en la lista (se escribe a `.parcial` y luego `os.replace`), y el mensaje lo dice.
5. **El servicio se reinicia varias veces el mismo día:** el respaldo automático sale una sola vez por día (lo decide la existencia de un `auto` con la fecha de hoy, no una variable en memoria).

---

### Task 1: configuración
**Archivos:**
- Crear `server/btsync/config.py`: `TABLA = "configuracion"` (pruebas: `configuracion_tst`), `DEFAULTS: dict[str, str]`, `migrar(conn)`, `leer(cur) -> dict[str, str]` (DEFAULTS más lo guardado), `escribir(cur, cambios: dict[str, str])` (MERGE, sin commit).
- `server/btsync/esquema.py::migrar` llama a `config.migrar`; un ORA-00955 al crear cuenta como «ya existe».
- `server/btsync/session.py`: el límite de foto sale de `fotos.max_mb` leído al empezar la sesión (`Store.config()`); se quita `MAX_FOTO` como constante fija.
- Crear `desktop/app/configuracion.py`: `validar(cambios) -> dict[str, str]` (lanza `ErrorDeAcceso` con el texto del rango, p. ej. «Procesar lecturas cada: entre 10 y 3600 segundos»), `guardar(quien, cambios)`, `aplicar_jobs()`, `valores() -> dict[str, str]`.
- `desktop/app/movimientos.py`: `es_critico` lee los umbrales de la configuración (se quitan `UMBRAL_PCT` y `UMBRAL_VALOR`).
- Crear `desktop/app/views/configuracion.py` (`ConfiguracionView`) con los tres grupos del boceto (Ajustes críticos, Sincronización, Fotos) y «Guardar»; sección «Configuración» (módulo `configuracion`) en `main.py`.
- Pruebas: `server/tests/test_config.py`, `desktop/tests/test_configuracion.py`, `test_configuracion_views.py`; el caso del umbral en `test_movimientos.py`.

**Produce:** `config.leer`, `config.escribir`, `config.DEFAULTS`, `Store.config() -> dict[str, str]`.

- [ ] **Pruebas RED:**
  - `leer` sin filas devuelve `DEFAULTS`; `escribir` y `leer` de nuevo; `migrar` dos veces seguidas no falla;
  - un valor fuera de rango o no numérico da `ErrorDeAcceso` con el texto del rango y no guarda nada;
  - guardar `ajustes.umbral_pct = 20`: un ajuste del 15 % deja de ser crítico;
  - guardar `lote.intervalo_s = 30`: `USER_SCHEDULER_JOBS.repeat_interval` del job de prueba pasa a `FREQ=SECONDLY;INTERVAL=30`; `staging.purga_dias = 3`: `job_action` llama a `purgar_transito(3)` (en las pruebas, jobs `_TST` deshabilitados creados por la fixture);
  - `fotos.max_mb = 1`: una foto de 1,5 MB recibe `FOTOERR GRANDE`;
  - una fila de auditoría por clave cambiada, con antes → después; guardar sin cambios no deja filas;
  - Inventario no guarda (`ErrorDeAcceso`) y no ve la sección; la vista muestra la carpeta de fotos sin poder editarla.
- [ ] Implementar y dejar GREEN; correr las suites del servidor y del escritorio.

### Task 2: el servicio Bluetooth
**Archivos:**
- Crear `server/btsync/servicio.py`:
  - `TABLA = "servicio_bt"` (pruebas: `servicio_bt_tst`), `migrar(conn)` (llamado desde `esquema.migrar`);
  - `class Servicio(controller: SyncController, store: Store, reloj=time.time)` con `tick() -> None` y `correr() -> NoReturn` (bucle de 1 s; al arrancar: `esquema.migrar`, fila con `desde = SYSTIMESTAMP`, `pausado` se conserva);
  - `main()` arma transporte y `Store` desde el entorno, igual que hoy `desktop/app/main.py::crear_transporte` (se mueve aquí como `crear_transporte()`).
- `tick()`: escribe estado y latido; con `pausado = 'N'` y el controlador en reposo, llama a `start()`; con `pausado = 'S'`, aplica la regla de «Pausar no corta» de las restricciones; con `respuesta` no nula y estado `CONFIRMAR_CODIGO`, llama a `confirm(respuesta == 'S')` y limpia `respuesta`; un fallo de Oracle en un tick se registra en el log y el siguiente tick reintenta (el servicio no se cae).
- `docker-compose.yml`: servicio `bluetooth` (misma imagen y entorno de `app` sin pantalla, `network_mode: host`, `/var/run/dbus`, `restart: unless-stopped`, `command: ["python", "-m", "btsync.servicio"]`, `RESPALDOS_DIR` y `FOTOS_DIR` bajo `/work`).
- Pruebas: `server/tests/test_servicio.py` con el `FakeTransport` de `test_controller.py`.

**Produce:** `Servicio`, `servicio.TABLA`, columnas de `SERVICIO_BT` (restricciones globales), `servicio.crear_transporte()`.

- [ ] **Pruebas RED:**
  - el primer tick abre la ventana (`ESPERANDO_EMPAREJAMIENTO`) y escribe latido y estado;
  - vencida la ventana sin conexión, el siguiente tick la vuelve a abrir;
  - `pausado = 'S'` en reposo → `cancel()` y estado `PAUSADO`; durante `RECIBIENDO` → `PAUSANDO`, la sesión termina con BYE y luego `PAUSADO` (Review Focus 1);
  - `pausado = 'N'` → reanuda;
  - código de emparejamiento: la fila muestra `CONFIRMAR_CODIGO` y el código; `respuesta = 'S'` lo acepta y queda NULL;
  - Oracle caído en un tick: no lanza y el siguiente tick escribe.
- [ ] Implementar y dejar GREEN; correr la suite del servidor.

### Task 3: el escritorio usa el servicio
**Archivos:**
- Crear `desktop/app/servicio.py`: `@dataclass(frozen=True) EstadoServicio(estado, codigo, recibidos, ultimo_error, desde, latido_s)`; `estado() -> EstadoServicio` (`DETENIDO` según las restricciones); `pausar(quien)`, `reanudar(quien)`, `responder_codigo(quien, aceptar: bool)`, auditados.
- Crear `desktop/app/servicio_remoto.py`: `ServicioRemoto(QObject)` con `status_changed(dict)` y `listo()` (cada vez que el estado leído pasa a `LISTO` desde otro), sondeo cada 2 s con `QueryRunner`, y `status() -> dict`.
- Borrar `desktop/app/sync_bridge.py`. `main.py`: sin transporte ni `SyncBridge`; `build_window(remoto: ServicioRemoto, …)`; cerrar la ventana o la sesión no toca el servicio.
- `views/sync.py`: quita «Iniciar recepción» y la cuenta regresiva. Muestra la línea de estado del boceto («Servicio Bluetooth activo · visible como «gestion_inventario» · desde 14/11 08:00», o «Pausado», o «El servicio Bluetooth no está corriendo»), y los botones «Pausar»/«Reanudar» y, con código, «Aceptar código»/«Rechazar». Lo demás (errores, reprocesar) queda igual.
- Pruebas: `desktop/tests/test_servicio.py`; `fakes.py` gana `FakeRemoto`; se adaptan las pruebas de `test_app.py` que usan `puente` (la de «cerrar la ventana cancela la sincronización» pasa a «cerrar la ventana no pausa el servicio»).

**Consume:** las columnas de `SERVICIO_BT` (Task 2).
**Produce:** `servicio.pausar`, `servicio.reanudar` y `servicio.estado`, que usa la Task 4 al restaurar.

- [ ] **Pruebas RED:**
  - con latido de hace 3 s se ve el estado escrito; con 11 s, o sin fila, `DETENIDO` (Review Focus 3);
  - pausar escribe `pausado = 'S'` y una fila de auditoría; reanudar, `'N'`;
  - un rol sin GESTION en `bluetooth` no pausa;
  - la vista muestra cada uno de los tres textos y alterna Pausar/Reanudar; con `CONFIRMAR_CODIGO` muestra el código y «Aceptar código» escribe `respuesta = 'S'`;
  - cerrar la sesión no escribe `pausado`.
- [ ] Implementar y dejar GREEN; correr la suite del escritorio.

### Task 4: respaldos (núcleo y automático)
**Archivos:**
- Crear `server/btsync/respaldo.py`:
  - `respaldos_dir() -> Path`;
  - `@dataclass(frozen=True) Respaldo(archivo: str, fecha: datetime, bytes: int, fotos: int, usuario: str, origen: str)`;
  - `crear(conn, usuario, origen, tablas: list[str] | None = None) -> Respaldo`;
  - `listar() -> list[Respaldo]` (más reciente primero; lee solo `manifest.json` de cada zip e ignora los que no lo tienen);
  - `podar(conservar: int) -> list[str]`;
  - `restaurar(conn, archivo, tablas: list[str] | None = None) -> None`;
  - `tablas_de_la_app(cur) -> list[str]`.
- `tablas=None` significa `tablas_de_la_app`; las pruebas pasan su propio par de tablas `_TST` (padre e hija con FK y una secuencia), y nunca tocan las reales.
- Restaurar sigue las restricciones globales, salvo la pausa del servicio, que hace `desktop/app/respaldos.py` (Task 5). Adelantar una secuencia: `ALTER SEQUENCE … INCREMENT BY <falta>`, `NEXTVAL`, `INCREMENT BY 1`.
- `Servicio.tick()` (Task 2): con `respaldos.auto = 'S'`, pasada la `respaldos.hora`, y sin un `auto` de hoy en `listar()`: `crear(…, "servicio", "auto")`, `podar(...)` y la fila de auditoría.
- Pruebas: `server/tests/test_respaldo.py`; el caso automático en `test_servicio.py`.

**Produce:** `respaldo.crear`, `listar`, `podar`, `restaurar`, `Respaldo`.

- [ ] **Pruebas RED:**
  - crear y restaurar devuelve filas idénticas (NUMBER con decimales, TIMESTAMP, NULL, texto con `|` y saltos de línea) y las fotos;
  - tras restaurar, el siguiente `NEXTVAL` de la secuencia es mayor que el `last_number` del manifiesto;
  - una fila que viola una restricción a mitad de la restauración → excepción, las tablas quedan como antes y las fotos actuales siguen (Review Focus 2);
  - un manifiesto con `formato` 2, o con una columna que no existe → «Este respaldo es de otra versión del sistema», sin tocar nada;
  - escribir en una carpeta sin permiso → error, y ningún `.zip` ni `.parcial` en `listar()` (Review Focus 4);
  - `podar(2)` con 4 `auto` y 1 `manual` borra los 2 `auto` más viejos y deja el `manual`;
  - automático: antes de la hora no crea; después crea uno; un `Servicio` nuevo en el mismo día no crea otro (Review Focus 5).
- [ ] Implementar y dejar GREEN; correr la suite del servidor.

### Task 5: pantalla Respaldos
**Archivos:**
- Crear `desktop/app/respaldos.py`: `crear(quien) -> Respaldo`, `listar(quien) -> list[Respaldo]`, `restaurar(quien, archivo, esperar_s=30)` (pausa con `servicio.pausar`, espera `PAUSADO`, crea el `previo`, deshabilita jobs, `respaldo.restaurar`, habilita jobs y audita), `guardar_automatico(quien, activo: bool, hora: str, conservar: int)`.
- Crear `desktop/app/views/respaldos.py` (`RespaldosView`): la tabla del boceto («Hecho por» muestra «Automático», «Antes de restaurar» o el usuario), «Crear respaldo ahora», «Restaurar…» (el diálogo de `RESTAURAR`), «Abrir carpeta» (`QDesktopServices.openUrl`) y el grupo «Automático». Sección «Respaldos» (módulo `respaldos`) en `main.py`; tras restaurar, `MainWindow` cierra la sesión y muestra el aviso.
- Pruebas: `desktop/tests/test_respaldos.py` y `test_respaldos_views.py`, con `tablas` de prueba (monkeypatch de `respaldo.tablas_de_la_app`) y `RESPALDOS_DIR`/`FOTOS_DIR` en `tmp_path`.

**Consume:** `servicio.pausar` y `servicio.estado` (Task 3); `respaldo.*` (Task 4).

- [ ] **Pruebas RED:**
  - restaurar con el servicio que no llega a `PAUSADO` en `esperar_s` → «El servicio Bluetooth no se detuvo; inténtalo de nuevo» y nada cambia (Review Focus 1);
  - restaurar bien: existe un `previo`, los jobs quedan habilitados, hay una fila «Restauró respaldo» y el servicio sigue pausado;
  - restaurar con error: los jobs también quedan habilitados;
  - Inventario no crea ni restaura y no ve la sección;
  - en la vista: Aceptar deshabilitado hasta escribir `RESTAURAR`; la lista muestra los tres orígenes; tras restaurar la ventana vuelve al login con el aviso;
  - `guardar_automatico` valida la hora (`25:00` → error) y audita.
- [ ] Implementar y dejar GREEN; correr la suite del escritorio.

### Task 6: documentación
- [ ] `docs/arquitectura.md`: la decisión D31 (servicio aparte, configuración en Oracle, respaldo en zip con restauración total).
- [ ] README: arrancar el servicio (`docker compose up -d bluetooth`), `RESPALDOS_DIR`, y cómo restaurar.
- [ ] UML: 04 con `CONFIGURACION` y `SERVICIO_BT`; 06 y 07 con el proceso `btsync.servicio` separado del escritorio; 16 con `PAUSANDO`/`PAUSADO`. Regenerar los SVG y pasar `test_uml`.
