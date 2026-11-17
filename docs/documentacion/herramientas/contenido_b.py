"""Capítulos 7 a 10: arquitectura, modelo de datos, conectividad y flujos de operación."""
import json
from pathlib import Path

from docgen import H, P, Lista, Tabla, Fig, Horizontal, Cmd

R = "diagramas/renderizados/"
_IDX = {e["id"]: e for e in json.loads((Path(__file__).resolve().parents[1] / "anexos" / "indice_codigo.json").read_text(encoding="utf8"))}


def cod(nombre: str, funcion: str, desc: str, fid: str | None = None, **kw) -> Fig:
    """Figura de código: el pie lleva archivo, líneas, función, qué demuestra y el criterio relacionado."""
    e = _IDX[nombre]
    return Fig(fid or "c" + nombre[6:8], e["imagen"], e["titulo"] + ".",
               [f"Archivo: {e['archivo']} (líneas {e['ini']}–{e['fin']}). Función o elemento: {funcion}.",
                f"Demuestra: {desc} Criterio: {e['criterio']}."], **kw)


def bloques() -> list:
    b: list = []

    # ------------------------------------------------------------------ 7
    b += [
        H(1, "7. Arquitectura del software"),
        H(2, "7.1 Estilo arquitectónico"),
        P("El sistema combina tres estilos que se pueden demostrar en el código. Primero, una **arquitectura por capas "
          "distribuida en procesos** (captura móvil, recepción, base de datos y presentación) cuyos únicos canales son "
          "RFCOMM, D-Bus y SQL\\*Net. Segundo, **MVC con trabajadores** en el escritorio: el modelo son los _dataclasses_ de "
          "`models.py` y las consultas de `db.py`; las vistas están en `desktop/app/views/`; y el controlador es "
          "`QueryRunner`, que ejecuta cada consulta en un `QueryWorker` y devuelve el resultado al hilo de la interfaz. "
          "Tercero, **MVVM** en Android: las pantallas Compose (`ui/pantallas/`) no tienen estado propio, `CountViewModel` "
          "y `SyncRunner` exponen estados, y el modelo está formado por `Outbox`, el catálogo en Room, `SyncClient` y `Protocol`."),
        P("No se etiqueta la arquitectura como un único patrón porque el código muestra una combinación; la evidencia de "
          "cada afirmación son los archivos citados y las capturas de código de las figuras de este capítulo."),
        H(2, "7.2 Arquitectura lógica"),
        Tabla("t_capas", "Capas lógicas y sus responsabilidades",
              ["Capa", "Ubicación", "Responsabilidad", "Dependencias"],
              [["1. Captura móvil", "`mobile/`", "Contar sin red. Guarda siempre primero en la `Outbox` (Room/SQLite). Cuentas locales.", "Room, ZXing, Compose"],
               ["2. Recepción Bluetooth", "`server/btsync` (`transports`, `session`, `controller`)", "Acepta una conexión RFCOMM, valida cada línea (CRC, formato, secuencia), hace COMMIT cada 25 y responde `ACK`/`NAK`. El controlador ejecuta el _batch_ al terminar.", "BlueZ por D-Bus, `oracledb`"],
               ["3. Staging y _batch_", "Oracle: `CAPTURA_TRANSITO`, `PKG_BATCH`, `DBMS_SCHEDULER`", "Valida y mueve lo recibido a `REGISTROS_PROCESADOS`, decide la lectura vigente y calcula `CONCILIACION`.", "—"],
               ["4. Presentación", "`desktop/app`", "Lee las vistas `V_*`, muestra tarjetas, tablas y gráficas, y ve y pausa el servicio Bluetooth.", "PyQt6, pyqtgraph, `oracledb`"]],
              [1800, 2400, 3600, 1560], "docs/arquitectura.md, verificado contra el código."),
        P("Las capas 2 y 4 son **dos procesos**: la recepción sigue activa aunque se cierre la ventana del escritorio. Se "
          "comunican solo por Oracle: el servicio escribe su estado y latido en `SERVICIO_BT` y el escritorio lo lee cada "
          "2 s (`ServicioRemoto`). Este acoplamiento débil es una decisión explícita (D11, D29)."),
        H(2, "7.3 Arquitectura física"),
        P("El [[f_desp]] (en página horizontal) muestra dónde corre cada componente. Docker Compose define tres servicios "
          "permanentes (`oracle`, `app` y `bluetooth`) y cuatro de apoyo por perfiles (`pybase`, `apk-build`, `plantuml` y "
          "`bt-spike`). `app` y `bluetooth` usan `network_mode: host`, `NET_ADMIN`/`NET_RAW` y el bus D-Bus del "
          "anfitrión, porque `bluetoothd` no corre en contenedor (D7). Android y el computador se hablan solo por "
          "Bluetooth clásico."),
        Horizontal([
            Fig("f_desp", R + "04_despliegue.png", "Diagrama de despliegue.",
                ["Fuente: elaboración propia. PlantUML: diagramas/plantuml/04_despliegue.puml.",
                 "Demuestra: ubicación física de cada componente y enlaces (RFCOMM, D-Bus, X11, SQL*Net). Criterio: Arquitectura y código fuente."]),
        ]),
        H(2, "7.4 Arquitectura de componentes"),
        P("El [[f_comp]] muestra los componentes y las interfaces verdaderas (`Transport`, RFCOMM, D-Bus, SQL\\*Net). "
          "`SyncController` depende de la interfaz `Transport`, no de una implementación concreta, de modo que "
          "`BluezTransport` y `TcpTransport` son intercambiables (plan B por TCP). El [[f_paq]] muestra las "
          "dependencias entre paquetes de Python y de Kotlin: las vistas del escritorio no importan el servicio "
          "Bluetooth; solo comparten `Store.connect_oracle`."),
        Horizontal([
            Fig("f_comp", R + "03_componentes.png", "Diagrama de componentes.",
                ["Fuente: elaboración propia. PlantUML: diagramas/plantuml/03_componentes.puml.",
                 "Demuestra: módulos de software, dependencias e interfaces. Criterio: Arquitectura y código fuente."]),
            Fig("f_paq", R + "07b_paquetes.png", "Diagrama de paquetes y dependencias.",
                ["Fuente: elaboración propia. PlantUML: diagramas/plantuml/07b_paquetes.puml.",
                 "Demuestra: dependencias entre `btsync`, `desktop.app` y `mobile`. Criterio: Arquitectura y código fuente."]),
        ]),
        P("El [[f_clases]] (siguiente página horizontal) presenta las clases de la librería `btsync`: `Message`, `Rec` y "
          "`FrameError` (protocolo), `Store` (persistencia en Oracle), `Session` (una conversación con un teléfono), "
          "`SyncController` (máquina de estados) y los transportes. Las clases del escritorio y de la APK están en los "
          "anexos (figuras [[f_clases_pc]] y [[f_clases_android]])."),
        Horizontal([
            Fig("f_clases", R + "07_clases_paquetes.png", "Diagrama de clases de la librería btsync.",
                ["Fuente: elaboración propia. PlantUML: diagramas/plantuml/07_clases_paquetes.puml (fuente original: docs/uml/01-clases-servidor.puml).",
                 "Demuestra: clases reales del servidor y sus relaciones. Criterio: Arquitectura y código fuente."]),
        ]),
        H(2, "7.5 Organización del código fuente"),
        Tabla("t_codigo", "Directorios y archivos principales",
              ["Archivo o directorio", "Responsabilidad", "Elementos importantes", "Relación con otros módulos"],
              [["`server/btsync/protocol.py` (192 líneas)", "Formato de línea y CRC32", "`frame`, `parse`, `Rec`, `FrameError`, `PROTOCOL_VERSION = \"5\"`", "Lo usan `Session` y `fake_phone.py`; espejo de `Protocol.kt`"],
               ["`server/btsync/session.py` (279)", "Una conversación con un teléfono", "`Session.run`, `_on_rec`, `_on_foto`, `_commit_and_ack`", "Usa `Store` y `Connection`"],
               ["`server/btsync/controller.py` (294)", "Estados del ciclo de sincronización", "`SyncController.start/confirm/cancel`, `_on_connection`", "Crea sesiones; dispara `Store.run_batch`"],
               ["`server/btsync/store.py` (338)", "Acceso a Oracle", "`connect_oracle`, `insert_staging`, `last_seq`, `catalog`, `run_batch`", "Lo usan sesión, controlador y escritorio"],
               ["`server/btsync/servicio.py` (207)", "Proceso del servicio", "`Servicio.tick`, `crear_transporte`, `main`", "Publica estado en `SERVICIO_BT`"],
               ["`server/btsync/transports/` (3 archivos)", "RFCOMM y TCP", "`BluezTransport`, `TcpTransport`, `Transport`, `Connection`", "BlueZ por D-Bus (`dbus-fast`)"],
               ["`server/btsync/respaldo.py` (466)", "Respaldo y restauración", "`.zip` con `manifest.json`, `.jsonl` por tabla y fotos", "Lo usan servicio y pantalla Respaldos"],
               ["`desktop/app/main.py` (1075)", "Ventana principal y arranque", "`MainWindow`, `build_window`, `main`", "Registra las vistas y el `ServicioRemoto`"],
               ["`desktop/app/views/` (≈40 archivos)", "Vistas (MVC)", "`dashboard`, `inventario`, `sync`, `usuarios`, `roles`, `respaldos`…", "Consultan por `QueryRunner`"],
               ["`desktop/app/auth.py` (673), `permisos.py` (159)", "Cuentas y permisos", "`iniciar_sesion`, `aprobar`, `exigir`, `INTOCABLES`", "Todas las vistas administrativas"],
               ["`desktop/app/db.py` (498), `workers.py` (47)", "Consultas y trabajadores", "`fetch_*`, `QueryWorker`", "Vistas `V_*` de Oracle"],
               ["`db/init/*.sql` (8 archivos)", "Esquema, semilla, `PKG_BATCH`, jobs, vistas, permisos, configuración, demo", "`01_schema.sql` … `08_demo.sql`", "Se ejecutan al crear Oracle"],
               ["`mobile/app/src/main/java/…/inventario/` (≈60 archivos Kotlin)", "APK Android", "`ui/` (Compose, ViewModel), `sync/`, `protocol/`, `data/`, `auth/`", "Usa el protocolo del servidor"],
               ["`tools/` (6 archivos)", "Utilidades", "`fake_phone.py`, `gen_seed.py`, `gen_demo.py`, `render_uml.sh`", "Pruebas y demostración"],
               ["`server/tests`, `desktop/tests`, `mobile/app/src/test`", "Pruebas automáticas", "20 + 38 archivos de prueba Python; JUnit en Kotlin", "Ver capítulo 14"]],
              [2600, 1900, 2800, 2060], "Elaboración propia a partir del repositorio (conteo de líneas con `wc -l`).", tam=16),
        P("La [[c_entrada]] y la [[c_entrada2]] muestran los dos puntos de arranque: la ventana de escritorio y el servicio Bluetooth, que son procesos distintos. La [[c_compose]] recoge cómo se despliega el servicio `bluetooth` y la [[c_addview]], cómo cada vista se registra con su módulo y se oculta según la sesión."),
        cod("codigo_01_entrada_escritorio", "`main()`", "el arranque de la aplicación: tema, migraciones de Oracle, ventana y bucle de eventos.", fid="c_entrada"),
        cod("codigo_02_entrada_servicio", "`main()`", "el arranque del servicio Bluetooth como proceso independiente de la ventana.", fid="c_entrada2"),
        cod("codigo_03_configuracion_compose", "servicio `bluetooth`", "la configuración de despliegue: red de host, capacidades, volúmenes, reinicio y variables de entorno.", fid="c_compose"),
        cod("codigo_04_composicion_ventana", "`MainWindow.add_view`", "cómo cada vista se registra con su módulo y se oculta según la sesión y el rol.", fid="c_addview"),
        H(2, "7.6 Patrones de diseño"),
        Lista([
            "**Estrategia (Transport):** `Transport`/`Connection` tienen dos implementaciones, `BluezTransport` y `TcpTransport`; la sesión no sabe cuál usa.",
            "**Máquina de estados:** `SyncController` pasa por `IDLE`, `ESPERANDO_EMPAREJAMIENTO`, `CONECTADO`, `RECIBIENDO`, `PROCESANDO`, `LISTO` y `ERROR` ([[f_estados]]).",
            "**Repositorio:** `Store` (Python) y `Outbox`/DAO de Room (Kotlin) encapsulan el acceso a datos.",
            "**Observador:** señales y ranuras de Qt (`ServicioRemoto.listo`, `refresh_requested`) y `Flow`/`StateFlow` en Android.",
            "**Idempotencia:** la clave única `(uuid_dispositivo, seq)` hace seguro reenviar una lectura.",
        ]),
        H(2, "7.7 Gestión de concurrencia"),
        P("La [[t_hilos]] identifica los hilos y mecanismos asíncronos que existen en el código. Ninguna consulta a Oracle "
          "se ejecuta en el hilo de la interfaz del escritorio; en Android, la red y el disco se mueven a "
          "`Dispatchers.IO`."),
        Tabla("t_hilos", "Hilos, procesos y mecanismos de comunicación",
              ["Componente", "Hilo o mecanismo", "Qué ejecuta", "Cómo vuelve a la interfaz o al llamador"],
              [["Escritorio", "Hilo principal de Qt", "Dibujo, eventos y navegación", "—"],
               ["Escritorio", "`QThreadPool` (hasta `MAX_HILOS = 8`)", "`QueryWorker.run`: consultas a Oracle, una conexión por hilo", "Señales `finished`/`failed` entregadas al hilo de la UI por `QueryRunner`; una `key` descarta resultados viejos"],
               ["Escritorio", "`ServicioRemoto` (temporizador de 2 s)", "Lee `SERVICIO_BT` mediante `QueryRunner`", "Señal `listo` → `refresh_requested`"],
               ["Servicio", "Hilo principal del proceso", "`Servicio.correr`: `tick()` cada 1 s (latido, pausa, estado)", "Escribe en `SERVICIO_BT`"],
               ["Servicio", "Hilo `bluez-bus` con bucle `asyncio`", "Llamadas D-Bus de BlueZ y registro del perfil RFCOMM", "`asyncio.run_coroutine_threadsafe` con plazo `_CALL_TIMEOUT`"],
               ["Servicio", "Hilo del transporte (uno por teléfono conectado) y hilo de tareas periódicas", "`Session.run` (la llama `SyncController._on_connection` desde el hilo del transporte); respaldo automático", "Eventos `on_event` y excepciones capturadas sin detener la recepción"],
               ["Oracle", "`DBMS_SCHEDULER`", "`JOB_PROCESAR_CAPTURAS` (cada minuto por defecto) y `JOB_PURGA_TRANSITO` (diario)", "Resultados en tablas; `LOG_BATCH`"],
               ["Android", "Corrutinas, `flowOn(Dispatchers.IO)`", "`SyncClient.sync` devuelve `Flow<SyncProgress>`; `PcConnector.conectar` en `Dispatchers.IO`", "`SyncRunner` traduce a `SyncEstado` que observa la pantalla"],
               ["Ambos", "`connect_oracle` con candado", "Serializa `oracledb.connect()`", "Evita `ORA-24550` observado con varios hilos y el Instant Client 19"]],
              [1300, 2400, 3300, 2360], "Elaboración propia a partir del código; ver las figuras de código de esta sección.", tam=16),
        P("`QueryWorker` ([[c_worker]]) ejecuta la consulta en un hilo del pool y `QueryRunner` ([[c_runner]]) entrega el resultado a la interfaz y descarta los obsoletos. `ServicioRemoto` ([[c_remoto]]) sondea Oracle y emite señales. En el servicio, el controlador crea una sesión por conexión y rechaza a un segundo teléfono ([[c_ctrl]]), y `Servicio.tick` mantiene el latido y la pausa ([[c_tick]])."),
        cod("codigo_15_hilos_worker", "`QueryWorker`", "una tarea `QRunnable` que ejecuta la consulta en un hilo del pool y emite señales con el resultado o el error.", fid="c_worker"),
        cod("codigo_16_hilos_runner", "`QueryRunner.run`", "el despacho de consultas fuera del hilo de la interfaz y el descarte de resultados obsoletos por clave.", fid="c_runner"),
        cod("codigo_17_remoto", "`ServicioRemoto`", "la puerta hacia el servicio Bluetooth: sondeo periódico de Oracle y conversión del estado en señales Qt.", fid="c_remoto"),
        cod("codigo_13_controlador_conexion", "`SyncController._on_connection`", "la creación de una sesión por conexión, el rechazo de un segundo teléfono (`OCUPADO`) y el cambio de estado.", fid="c_ctrl"),
        cod("codigo_14_servicio_tick", "`Servicio.tick`", "el latido y la gestión de pausa que mantienen visible el estado del servicio en Oracle.", fid="c_tick"),
        P("Para la rúbrica de arquitectura, el punto que el código sí demuestra es que la interfaz del escritorio no se "
          "bloquea con consultas, y que la APK no hace red en su hilo principal. La [[f_estados]] ofrece la máquina de "
          "estados del controlador, el mecanismo que coordina estas piezas."),
        Horizontal([
            Fig("f_estados", R + "09_estados.png", "Máquina de estados del controlador de sincronización.",
                ["Fuente: elaboración propia. PlantUML: diagramas/plantuml/09_estados.puml.",
                 "Demuestra: estados reales de `SyncController` y sus transiciones. Criterio: Arquitectura y código fuente."]),
        ]),
        H(2, "7.8 Gestión de errores"),
        Lista([
            "**Protocolo:** cada línea inválida produce `NAK|<seq esperado>|<motivo>` con motivos `CRC`, `FORMAT`, `LINEA_LARGA`, `SECUENCIA`, `DB_NO_DISPONIBLE`, `CUENTA_NO_ACTIVA` y `OCUPADO`.",
            "**Base de datos:** si Oracle no está disponible durante la sesión, `Session._db_unavailable` responde `NAK DB_NO_DISPONIBLE`; `connect_oracle` reintenta hasta tres veces ante `ORA-12516`.",
            "**Lecturas inválidas:** el _batch_ las deja en `ERROR` con mensaje (por ejemplo `CANTIDAD_INVALIDA`) y no entran a la conciliación hasta reprocesarlas.",
            "**Interfaz:** `StateBanner` y avisos muestran errores de Oracle o del servicio; el servicio no se detiene si falla una tarea periódica.",
        ]),
    ]

    # ------------------------------------------------------------------ 8
    b += [
        H(1, "8. Modelo de datos y base de datos"),
        H(2, "8.1 Motor, conexión y persistencia"),
        P("El motor es **Oracle Database 11g Express Edition 11.2.0.2.0** (verificado con `v$version` en el contenedor "
          "`gvenzl/oracle-xe:11-slim`). Las aplicaciones Python se conectan con **python-oracledb 26.1.0 en modo _thick_** "
          "mediante el Instant Client 19.23, porque Oracle 11g lo exige. La conexión de la aplicación y del servicio "
          "se abre con el usuario `app`; las credenciales viven en el archivo `.env` y nunca se incluyen en este "
          "documento. La persistencia es un volumen Docker (`oracle-data`)."),
        cod("codigo_11_store_conexion", "`connect_oracle`", "la apertura de conexiones serializada con candado y el reintento ante `ORA-12516`.", fid="c_conn"),
        H(2, "8.2 Tablas y relaciones"),
        P("El esquema tiene 17 tablas: catorce creadas por `db/init/01_schema.sql` y tres que crea la propia aplicación al "
          "arrancar (`AUDITORIA`, `NOTIFICACIONES` y `NOTIFICACIONES_LEIDAS`). La [[t_tablas]] resume las principales con sus "
          "claves; el [[f_er]] muestra todas con sus relaciones."),
        Tabla("t_tablas", "Tablas principales del esquema",
              ["Tabla", "Clave primaria", "Claves foráneas y restricciones", "Campos relevantes y propósito"],
              [["`CONTEOS`", "`ID_CONTEO`", "`CHECK ESTADO = 'ABIERTO'`", "Una sola fila `ACTUAL` («Conteo continuo»), siempre abierta"],
               ["`PRODUCTOS`", "`SKU`", "—", "Nombre, categoría, unidad, `COSTO_UNIT` `NUMBER(12,2)`"],
               ["`STOCK_SISTEMA`", "`(ID_CONTEO, SKU)`", "FK a `CONTEOS` y `PRODUCTOS`", "`CANTIDAD_SISTEMA` `NUMBER(12,3)`; el operador nunca la ve"],
               ["`DISPOSITIVOS`", "`UUID`", "—", "Nombre y última sincronización de cada teléfono"],
               ["`CAPTURA_TRANSITO`", "`ID_TRANSITO`", "`UNIQUE (UUID_DISPOSITIVO, SEQ)`; `CHECK` de estado (`PENDIENTE`, `PROCESANDO`, `PROCESADO`, `ERROR`, `NUEVO_SKU`, `DESCARTADO`)", "`DATOS_RAW` `VARCHAR2(4000 BYTE)`: la línea `REC` sin CRC"],
               ["`REGISTROS_PROCESADOS`", "`ID_REGISTRO`", "`UNIQUE (ID_TRANSITO)`, FK a tránsito", "`CANTIDAD`, `DANADOS`, `VIGENTE` `CHAR(1)`, `FECHA_CAPTURA`"],
               ["`CONCILIACION`", "`(ID_CONTEO, SKU)`", "FK a `CONTEOS` y `PRODUCTOS`", "`CANT_SISTEMA`, `CANT_CONTADA`, `DIFERENCIA`, `DIFERENCIA_PCT`"],
               ["`FOTOS`, `SYNC_SESIONES`, `LOG_BATCH`", "id o clave compuesta", "FK a tránsito o dispositivos", "Ruta de foto, sesiones de sincronización y corridas del _batch_"],
               ["`USUARIOS`", "`USUARIO`", "`CHECK` de `ROL`, `ESTADO`, `ORIGEN`, `TEMA`, `IDIOMA`; correo obligatorio si `ORIGEN <> 'MOVIL'`", "`CLAVE_HASH`, `INTENTOS`, `BLOQUEADO_HASTA`, pregunta y respuesta (hash)"],
               ["`PERMISOS`", "`(ROL, MODULO)`", "`CHECK NIVEL IN (NINGUNO, CONSULTA, GESTION)`", "36 filas: 3 roles × 12 módulos"],
               ["`CONFIGURACION`, `SERVICIO_BT`", "`CLAVE`; `ID`", "—", "Seis claves de configuración; estado, latido y pausa del servicio (fila única)"],
               ["`AUDITORIA`, `NOTIFICACIONES`, `NOTIFICACIONES_LEIDAS`", "id", "Creadas por la app", "Rastro de cambios y avisos por rol o usuario"]],
              [2200, 1500, 2900, 2760], "db/init/01_schema.sql y docs/uml/04-modelo-datos.puml.", tam=16),
        Horizontal([
            Fig("f_er", R + "10_modelo_datos.png", "Diagrama del modelo de datos de Oracle (conteo continuo ACTUAL).",
                ["Fuente: elaboración propia a partir de db/init/01_schema.sql. PlantUML: diagramas/plantuml/10_modelo_datos.puml.",
                 "Demuestra: tablas, llaves y cardinalidades reales. Criterio: Funcionalidad / Arquitectura."]),
        ]),
        cod("codigo_22_sql_tabla_transito", "`CREATE TABLE captura_transito`", "la tabla de _staging_ con su clave única `(uuid, seq)` y los estados de una lectura.", fid="c_sql1"),
        H(2, "8.3 Vistas, trabajos y consultas principales"),
        Tabla("t_vistas", "Vistas, trabajos programados y consultas",
              ["Elemento", "Tipo", "Para qué se usa"],
              [["`V_RESUMEN_CONTEO`", "Vista", "Avance, contados, faltantes, sobrantes (`fetch_resumen`)"],
               ["`V_DIF_CATEGORIA`, `V_TOP_DESVIOS`", "Vista", "Diferencia por categoría y mayores desvíos (definidas en `05_views.sql`; las gráficas de la app calculan sus series con `fetch_por_categoria` y `fetch_series`)"],
               ["`V_ACTIVIDAD`", "Vista", "Lecturas por operador (`fetch_actividad`)"],
               ["`V_ESTADO_BATCH`", "Vista", "Última corrida y pendientes (`fetch_estado_batch`)"],
               ["`V_NUEVOS_SKU`, `V_ERRORES_CAPTURA`", "Vista", "Lecturas con SKU nuevo y con error (`fetch_nuevos_sku`, `fetch_errores`)"],
               ["`JOB_PROCESAR_CAPTURAS`", "Trabajo `DBMS_SCHEDULER`", "Ejecuta `PKG_BATCH.procesar_pendientes` (`FREQ=MINUTELY;INTERVAL=1` por defecto)"],
               ["`JOB_PURGA_TRANSITO`", "Trabajo `DBMS_SCHEDULER`", "Purga filas de tránsito procesadas (`FREQ=DAILY`)"],
               ["`PKG_BATCH`", "Paquete PL/SQL", "`procesar_pendientes`, `conciliar`, `reprocesar_errores`, `purgar_transito`, `alta_sku`, `alta_y_procesar`, `descartar_nuevo_sku`"]],
              [3000, 2000, 4360], "db/init/03_pkg_batch.sql, 04_jobs.sql, 05_views.sql y desktop/app/db.py."),
        P("La inserción idempotente en la tabla de tránsito está en la [[c_ins]] y la validación PL/SQL de cada fila, en la [[c_batch]]."),
        cod("codigo_10_store_insert", "`Store.insert_staging`", "la inserción idempotente: devuelve `False` si `(uuid, seq)` ya existía, sin duplicar.", fid="c_ins"),
        cod("codigo_23_sql_batch", "`procesar_fila` en `PKG_BATCH`", "la validación PL/SQL de cada lectura: SKU conocido, cantidad y dañados válidos; si no, queda en `ERROR`.", fid="c_batch"),
        H(2, "8.4 Operaciones de escritura, transacciones y errores"),
        P("Las escrituras ocurren en el servicio, en el _batch_, en la auditoría y en la restauración. La matriz de permisos se siembra con el script de la [[c_sql2]]."),
        Lista([
            "**Escritura del servicio:** `insert_staging` por lectura y `COMMIT` cada 25 inserciones o al `END`; un corte antes del `COMMIT` provoca `ROLLBACK` de las filas no confirmadas.",
            "**Escritura del _batch_:** cada fila se reclama (`PENDIENTE → PROCESANDO`), se inserta en `REGISTROS_PROCESADOS`, se recalcula la lectura vigente y se marca `PROCESADO`; las filas `PROCESANDO` de más de 5 minutos se devuelven a `PENDIENTE`.",
            "**Auditoría:** el escritorio escribe en `AUDITORIA` dentro de la misma transacción que cada cambio (D28).",
            "**Restauración:** se ejecuta en una transacción, tras pausar el servicio y guardar un respaldo previo (D29).",
            "**Errores de conexión:** el escritorio muestra «Oracle no está listo» y reintenta; el servicio responde `NAK DB_NO_DISPONIBLE`.",
        ]),
        cod("codigo_24_sql_permisos", "bloque `BEGIN … INSERT INTO permisos`", "la matriz de permisos inicial (rol × módulo × nivel) sembrada en Oracle.", fid="c_sql2"),
    ]

    # ------------------------------------------------------------------ 9
    b += [
        H(1, "9. Conectividad y comunicación de datos"),
        H(2, "9.1 Mecanismos de comunicación implementados"),
        P("El proyecto implementa cuatro canales de datos y no usa REST ni WebSockets: no existe ninguna interfaz HTTP "
          "en el código. Los canales son Bluetooth clásico RFCOMM entre la APK y el servicio, D-Bus entre el servicio "
          "y BlueZ, SQL\\*Net entre las aplicaciones Python y Oracle, y un transporte TCP alterno que se usa en "
          "pruebas y como plan B de demostración (`BT_TRANSPORT=tcp`). Entre el servicio y el escritorio no hay canal "
          "directo: coordinan por la tabla `SERVICIO_BT`."),
        Tabla("t_canales", "Canales de comunicación",
              ["Canal", "Participantes", "Protocolo", "Dirección", "Datos"],
              [["Bluetooth RFCOMM", "APK ↔ servicio `bluetooth` (vía BlueZ)", "Líneas UTF-8 con `|` y CRC32 (versión 5)", "Bidireccional", "`HELLO`, `ACCT`, `REC`, `FOTO`, `END` ↔ `ACCTST`, `READY`, catálogo, `ACK`, `NAK`, `BYE`"],
               ["D-Bus (`org.bluez`)", "Servicio ↔ `bluetoothd`", "D-Bus del sistema (`dbus-fast`)", "Bidireccional", "`RegisterProfile`, `NewConnection(fd)`, alias y visibilidad del adaptador"],
               ["SQL\\*Net 1521", "Servicio y escritorio ↔ Oracle", "Oracle Net (`oracledb`, modo thick)", "Bidireccional", "INSERT en tránsito, llamadas a `PKG_BATCH`, SELECT sobre vistas, `SERVICIO_BT`"],
               ["TCP (alterno)", "Teléfono simulado ↔ servicio", "El mismo protocolo de líneas", "Bidireccional", "Pruebas y demostración; `TcpTransport`"]],
              [1500, 2200, 2300, 1100, 2260], "server/btsync/transports, docs/protocolo.md y docs/arquitectura.md."),
        H(2, "9.2 Formato de mensajes"),
        P("Cada mensaje es una línea UTF-8 terminada en `\\n`. Los campos se separan con `|`; al final se añaden `*` y el CRC32 "
          "de los bytes anteriores en ocho dígitos hexadecimales mayúsculos. La longitud máxima es de 4000 bytes. Los "
          "caracteres `%`, `|`, `\\r` y `\\n` dentro de campos de texto se codifican como `%25`, `%7C`, `%0D` y `%0A`. "
          "Ejemplo calculado con la herramienta del proyecto (`python -m btsync.protocol --frame`): "
          "`HELLO|5|dev-0001|Bodega Norte*788FF277`."),
        Tabla("t_msg", "Mensajes del protocolo (versión 5)",
              ["Sentido", "Mensaje", "Campos", "Validación o efecto"],
              [["Móvil → PC", "`HELLO`", "versión, `uuid_dispositivo`, nombre", "Versión distinta de 5: `NAK|0|FORMAT`"],
               ["Móvil → PC", "`ACCT`", "usuario, nombre", "Usuario `[a-z0-9._-]{3,30}`, nombre de 1 a 60; crea la cuenta PENDIENTE si no existe"],
               ["Móvil → PC", "`REC`", "`seq`, `epoch_ms`, `ACTUAL`, `sku`, `cantidad`, `operador`, `nota`, `danados`", "Cantidad `^\\d{1,9}(\\.\\d{1,3})?$`; `seq` contiguo por dispositivo"],
               ["Móvil → PC", "`FOTO`", "`seq`, parte, total, `crc32`, base64", "Hasta 2700 caracteres por parte; CRC del archivo; máximo 2 MB"],
               ["Móvil → PC", "`END`", "`n_registros`", "Cierra el envío; `COMMIT` y `ACK` final"],
               ["PC → móvil", "`ACCTST`", "usuario, estado, rol, motivo", "Sin estado `ACTIVO` no se aceptan lecturas"],
               ["PC → móvil", "`READY`", "último `seq` confirmado, hora del servidor", "El móvil reconcilia su `Outbox` y corrige su reloj (D15)"],
               ["PC → móvil", "`CATTAREA`, `CATITEM`, `CATPROD`, `CAT_END`", "catálogo sin stock", "Conteo ciego (D12)"],
               ["PC → móvil", "`ACK`", "`seq`", "Acumulativo: todo `seq ≤ n` persistido con `COMMIT`"],
               ["PC → móvil", "`NAK`", "`seq` esperado, motivo", "El móvil retrocede a ese `seq` (_go-back-N_)"],
               ["PC → móvil", "`BYE`", "aceptados, rechazados", "Fin de la sesión; no informa del resultado del _batch_"]],
              [1200, 2400, 3000, 2760], "docs/protocolo.md contrastado con server/btsync/protocol.py.", tam=17),
        cod("codigo_05_protocolo_trama", "`frame`, `parse`", "la construcción de la trama con CRC32 y la validación de longitud, CRC y número de campos que produce `FrameError`.", fid="c_frame"),
        H(2, "9.3 Secuencia, validación y confirmación"),
        P("El [[f_sec5]] sigue el recorrido de un conteo desde la `Outbox` hasta la consulta del escritorio. La sesión "
          "valida cada `REC` en este orden: longitud, CRC, formato, cuenta activa y secuencia. Si el `seq` es menor al "
          "esperado es un duplicado y se ignora (lo cubre el siguiente `ACK`); si es mayor hay un hueco y se envía un "
          "único `NAK|esperado|SECUENCIA`; si es igual, se inserta."),
        Fig("f_sec5", R + "05_secuencia_flujo_datos.png", "Diagrama de secuencia del flujo principal de datos.",
            ["Fuente: elaboración propia a partir de session.py, controller.py y store.py. PlantUML: diagramas/plantuml/05_secuencia_flujo_datos.puml.",
             "Demuestra: el recorrido real de los datos del teléfono a Oracle y su consulta. Criterio: Conectividad y comunicación."],
            max_h=9900),
        cod("codigo_07_sesion_bucle", "`Session._run`", "el bucle de lectura y el despacho por tipo de mensaje dentro de una sesión.", fid="c_bucle"),
        cod("codigo_08_sesion_rec", "`Session._on_rec`", "la validación de secuencia, la inserción en staging y el `NAK` con retroceso.", fid="c_onrec"),
        cod("codigo_09_sesion_ack", "`Session._commit_and_ack`", "el `COMMIT` y el envío del `ACK` acumulativo; el `ROLLBACK` silencioso ante fallos.", fid="c_ack"),
        cod("codigo_12_bluez_perfil", "`_Profile`", "la interfaz D-Bus que BlueZ invoca (`NewConnection`) cuando un teléfono se conecta al perfil RFCOMM.", fid="c_perfil"),
        H(2, "9.4 Reintentos, cortes y reanudación"),
        P("Si la conexión se corta antes del `COMMIT`, el servidor hace `ROLLBACK` y conserva solo lo confirmado. Al "
          "reconectar, el móvil recibe `READY|<último seq>` y reconcilia su `Outbox`: lo confirmado pasa a `CONFIRMADO` y lo "
          "enviado sin confirmar vuelve a `PENDIENTE`. `SyncRunner` reintenta la conexión hasta tres veces. El [[f_sec6]] "
          "describe el caso probado con 30 lecturas, y la sección 9.5 muestra la misma situación ejecutada realmente."),
        Fig("f_sec6", R + "06_secuencia_comunicacion.png", "Diagrama de secuencia de comunicación: corte, READY y retroceso go-back-N.",
            ["Fuente: elaboración propia a partir de la prueba `test_connection_cut_after_30_rec_keeps_25`. PlantUML: diagramas/plantuml/06_secuencia_comunicacion.puml.",
             "Demuestra: mensajes, confirmaciones, NAK y reanudación sin duplicados. Criterio: Conectividad y comunicación."]),
        cod("codigo_25_android_sync", "`SyncClient.session`", "el lado móvil del protocolo: lectura de `READY`, `ACCTST` y catálogo, y envío de `REC` en ventanas.", fid="c_async"),
        cod("codigo_26_android_runner", "`SyncRunner.ejecutar`", "los estados de la sincronización (`Conectando`, `Reintentando`, `Cortado`, `Listo`…) y el reintento de conexión.", fid="c_arunner"),
        cod("codigo_27_android_outbox", "`Outbox.tomarParaEnviar`, `reemplazar`, `reconciliar`", "cómo la bandeja local pasa lecturas por `PENDIENTE`, `ENVIADO` y `CONFIRMADO`, y se reconcilia con `READY`.", fid="c_aout"),
        H(2, "9.5 Evidencia de funcionamiento real"),
        P("En este equipo no hay un teléfono emparejado (`adb devices` no lista dispositivos), por lo que la evidencia "
          "de comunicación usa el **transporte TCP** del proyecto con el **teléfono simulado** `tools/fake_phone.py`, que "
          "habla el mismo protocolo que la APK. La prueba se ejecutó contra un Oracle independiente y limpio (puerto "
          "1522) para no alterar los datos de demostración. No se afirma que el enlace Bluetooth físico se haya "
          "verificado en esta ejecución; la capa Bluetooth se comprueba con las pruebas de `BluezTransport` (con un bus "
          "D-Bus falso) y con la prueba de campo documentada en `docs/spikes/bluez.md`."),
        P("**Resultado de la sincronización.** Con la cuenta sin aprobar, el PC respondió que está pendiente y no aceptó "
          "lecturas ([[f_com1]]). Tras la aprobación, el teléfono envió 126 lecturas; el servicio respondió "
          "`BYE|126|0` y el _batch_ procesó 123, dejó 1 en `ERROR` (`CANTIDAD_INVALIDA`) y 2 en `NUEVO_SKU`, sin filas "
          "duplicadas ([[f_com2]])."),
        Fig("f_com1", "capturas/pruebas/registro_06_comunicacion_a.png", "Ejecución real: cuenta pendiente, aprobación y envío de 126 lecturas.",
            ["Fuente: docs/documentacion/anexos/registros/comunicacion_tcp.txt (generado por herramientas/comunicacion_tcp.sh, 17-nov-2026).",
             "Demuestra: validación de la cuenta y confirmación `BYE`. Criterio: Conectividad y comunicación."]),
        Fig("f_com2", "capturas/pruebas/registro_07_comunicacion_b.png", "Ejecución real: estado de Oracle tras el batch.",
            ["Fuente: comunicacion_tcp.txt. Consulta de solo lectura con herramientas/consulta_estado.py.",
             "Demuestra: persistencia posterior, ausencia de duplicados y conciliación calculada. Criterio: Conectividad y comunicación."],
            max_h=8000),
        P("**Corte y reanudación.** Un segundo teléfono simulado fue terminado con `SIGKILL` a los 4 s: en Oracle quedaron "
          "50 filas confirmadas. Al relanzar con el mismo _outbox_, el servicio respondió con el último `seq` y el "
          "teléfono envió solo las 70 restantes (`BYE|70|0`): 120 filas en total, 0 duplicadas ([[f_cor1]] y "
          "[[f_cor2]])."),
        Fig("f_cor1", "capturas/pruebas/registro_08_corte.png", "Ejecución real: corte del envío con SIGKILL y reanudación.",
            ["Fuente: anexos/registros/comunicacion_corte.txt (herramientas/comunicacion_corte.sh).",
             "Demuestra: reintento y reanudación desde el último `seq` confirmado. Criterio: Conectividad y comunicación."]),
        Fig("f_cor2", "capturas/pruebas/registro_09_corte_final.png", "Ejecución real: estado final tras la reanudación, sin duplicados.",
            ["Fuente: comunicacion_corte.txt.",
             "Demuestra: integridad `(uuid, seq)` tras un corte. Criterio: Conectividad y comunicación."]),
        H(2, "9.6 Seguridad y límites del canal"),
        P("Por decisión de diseño (D22) el modo por defecto **no empareja ni cifra** el enlace: el teléfono recuerda al PC y "
          "conecta directo. Quien esté al alcance (~10 m) podría conectarse y enviar lecturas falsas mientras el servicio "
          "esté activo; las mitigaciones documentadas son aceptar un solo teléfono a la vez, validar cada línea, exigir "
          "una cuenta aprobada y vinculada al UUID del teléfono, y permitir al Administrador pausar el servicio. Existe un "
          "modo con código de emparejamiento (`BT_CON_CLAVE=1`) que no se ejecutó en esta verificación. Por todo ello no "
          "se afirma que la comunicación sea «segura» en sentido de confidencialidad."),
        Tabla("t_fallas", "Escenarios de falla y mecanismo de tolerancia",
              ["Escenario", "Mecanismo", "Prueba o evidencia"],
              [["Línea dañada (CRC)", "`NAK|n|CRC` y retroceso", "`test_bad_crc_naks_expected_seq_and_survives`"],
               ["Hueco en la secuencia", "Un solo `NAK|n|SECUENCIA`; se ignoran las siguientes", "`test_seq_gap_naks_once_and_ignores_followers`"],
               ["Línea mayor de 4000 bytes", "`NAK|…|LINEA_LARGA`", "`test_line_over_4000_bytes_naks_linea_larga`"],
               ["Corte a mitad del lote", "`ROLLBACK`, `READY` y reenvío", "`test_connection_cut_after_30_rec_keeps_25`; sección 9.5"],
               ["Duplicado en una nueva sesión", "Clave única `(uuid, seq)`", "`test_duplicate_rec_in_new_session_is_not_inserted`"],
               ["Oracle no disponible", "`NAK DB_NO_DISPONIBLE`", "`test_oracle_down_replies_nak_db_unavailable`"],
               ["Cuenta pendiente", "`NAK CUENTA_NO_ACTIVA`; el móvil conserva las lecturas", "`test_rec_con_cuenta_pendiente_recibe_nak_cuenta_no_activa`; sección 9.5"],
               ["Otro teléfono con el mismo usuario", "Estado `SUSPENDIDO` por vínculo al UUID", "`test_otro_telefono_con_el_mismo_usuario_no_entrega_lecturas`"],
               ["Segunda sincronización simultánea", "`NAK|0|OCUPADO`", "`test_bluez.py`, `test_e2e_tcp.py`"]],
              [2800, 3300, 3260], "server/tests/test_session.py, test_bluez.py y test_e2e_tcp.py; ejecución del capítulo 14."),
    ]

    # ------------------------------------------------------------------ 10
    b += [
        H(1, "10. Flujos de operación del sistema"),
        P("Este capítulo describe los procesos de extremo a extremo con sus validaciones y errores. Los diagramas de "
          "secuencia de los flujos de datos se encuentran en el capítulo 9; aquí se añaden los diagramas de actividades y "
          "de estados."),
        Tabla("t_flujos", "Procesos principales de extremo a extremo",
              ["Proceso", "Actor y componentes", "Entradas y pasos", "Validaciones y errores", "Resultado"],
              [["F1 · Acceso en el PC", "Admin/Inventario; `AccesoView`, `auth`", "Usuario y contraseña → hash PBKDF2 → sesión con permisos de Oracle", "Mensaje genérico ante usuario o clave erróneos; bloqueo de 30 s tras 5 intentos; el Operador no entra al PC; cuenta no activa → Estado de cuenta", "Ventana con las secciones del rol"],
               ["F2 · Captura móvil", "Operador; `ContarScreen`, `CountViewModel`, `Outbox`", "SKU (escáner o digitado), cantidad, dañados, nota, foto → Guardar", "Cantidad válida, dañados ≤ cantidad, longitudes máximas (operador 60, nota 255); SKU desconocido se guarda pendiente", "Lectura PENDIENTE en `Outbox`"],
               ["F3 · Sincronización", "Operador; `SyncRunner`, `Session`", "Pulsar Sincronizar → búsqueda → `HELLO` … `BYE`", "CRC, formato, secuencia, cuenta activa, PC ocupado, corte", "Lecturas CONFIRMADO y filas en tránsito"],
               ["F4 · Procesamiento", "Scheduler o controlador; `PKG_BATCH`", "Filas PENDIENTE → reclamar → validar → insertar → vigente → conciliar", "SKU desconocido → `NUEVO_SKU`; datos inválidos → `ERROR`; huérfanas se recuperan", "`CONCILIACION` de `ACTUAL`"],
               ["F5 · Consulta", "Admin/Inventario; vistas y `QueryRunner`", "Abrir Dashboard, Inventario o Gráficas → SELECT en hilo de trabajo", "Estado de error de Oracle visible; resultados obsoletos descartados", "Tarjetas, tablas, gráficas, CSV"],
               ["F6 · SKU nuevo", "Administrador; `aviso_nuevo_sku`, `PKG_BATCH.alta_y_procesar`", "Aviso flotante → nombre y categoría → Crear y procesar", "Nombre y categoría obligatorios; confirmación antes de descartar", "Producto creado y lectura reflejada, o lectura descartada"],
               ["F7 · Aprobación de cuentas", "Administrador; `SolicitudesView`", "Cuenta pendiente → Aprobar con rol o Rechazar con motivo", "Rol restringido por origen; motivo ≤ 300 caracteres; auditoría", "Cuenta ACTIVO o RECHAZADO"],
               ["F8 · Respaldo y restauración", "Administrador; `respaldo.py`", "Crear `.zip`; restaurar escribiendo `RESTAURAR`", "Se pausa el servicio y se guarda un respaldo previo; una transacción", "Datos restaurados; sesión cerrada"]],
              [1500, 1900, 2400, 2400, 1160], "Elaboración propia a partir del código y de la documentación del proyecto.", tam=16),
        H(2, "10.1 Del teléfono al batch: diagrama de actividades"),
        P("El [[f_act]] reparte las responsabilidades en carriles: el móvil, la sesión del servicio, el controlador y Oracle. "
          "Muestra el ciclo de lectura de `REC` con validación, la confirmación cada 25 y el procesamiento por lotes con "
          "recuperación de filas huérfanas."),
        Fig("f_act", R + "08_actividades.png", "Diagrama de actividades: de la subida al ACK y el batch PKG_BATCH.PROCESAR_PENDIENTES.",
            ["Fuente: elaboración propia. PlantUML: diagramas/plantuml/08_actividades.puml.",
             "Demuestra: flujo real de validación, confirmación y conciliación. Criterio: Funcionalidad y requisitos."],
            max_h=9900),
        Fig("f_act2", R + "08b_actividad_conteo_movil.png", "Diagrama de actividades del conteo en el móvil.",
            ["Fuente: elaboración propia. PlantUML: diagramas/plantuml/08b_actividad_conteo_movil.puml.",
             "Demuestra: el flujo del operador desde el acceso hasta la sincronización. Criterio: Funcionalidad y requisitos."],
            max_h=9900),
        H(2, "10.2 Estados de una lectura y de una cuenta"),
        P("Una fila de tránsito recorre `PENDIENTE → PROCESANDO → PROCESADO | ERROR | NUEVO_SKU | DESCARTADO` "
          "([[f_est2]]). Una cuenta pasa por `PENDIENTE → ACTIVO | RECHAZADO` y `ACTIVO ⇄ SUSPENDIDO` ([[f_est3]]). Ambos "
          "diagramas coinciden con las restricciones `CHECK` del esquema."),
        Fig("f_est2", R + "09b_estados_fila_transito.png", "Estados de una fila de CAPTURA_TRANSITO.",
            ["Fuente: elaboración propia. PlantUML: diagramas/plantuml/09b_estados_fila_transito.puml.",
             "Demuestra: ciclo de vida de una lectura en el staging. Criterio: Arquitectura y código fuente."]),
        Fig("f_est3", R + "09c_estados_cuenta.png", "Estados de una cuenta de usuario.",
            ["Fuente: elaboración propia. PlantUML: diagramas/plantuml/09c_estados_cuenta.puml.",
             "Demuestra: ciclo de vida de una cuenta y su acceso. Criterio: Seguridad / Funcionalidad."]),
    ]
    return b
