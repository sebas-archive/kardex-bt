"""Redacción final de la prosa del documento (revisión con la skill /humanizer).

Los textos de los módulos ``contenido_*`` conservan los hechos y las referencias; este módulo sustituye la redacción de
los párrafos y de algunas listas por una versión más directa y sin muletillas. Cada clave es el comienzo del texto original;
si un texto no aparece aquí se emite tal cual. Las referencias ``[[id]]`` se resuelven a «Figura N» o «Tabla N» al construir.
"""

PARRAFOS = {
    "El sistema **Kardex** (inventario físico offline: ":
        "El proyecto, llamado Kardex (inventario físico offline: APK → Bluetooth → Oracle → aplicación de escritorio), permite contar "
        "inventario con un teléfono Android sin conexión de red. El conteo viaja por Bluetooth hasta un computador con Linux, "
        "se guarda en Oracle 11g y un proceso por lotes (_batch_) escrito en PL/SQL lo concilia contra el stock del sistema. "
        "Una aplicación de escritorio muestra el resultado en tableros, tablas y gráficas. El conteo es continuo: no existe un "
        "cierre de inventario y las cifras se recalculan cada vez que el _batch_ procesa lecturas nuevas.",
    "El problema que resuelve es la toma de i":
        "Está pensado para bodegas y tiendas sin red confiable. Allí el operador no puede depender de un servidor para registrar "
        "cada lectura, pero lo que cuenta debe llegar completo, sin duplicados y con trazabilidad hasta el equipo central. "
        "Intervienen tres roles: el Operador de Inventario, que usa solo el móvil, y los roles Inventario y Administrador, "
        "que usan solo el escritorio.",
    "La solución se compone de cuatro piezas:":
        "Son cuatro piezas. La APK está escrita en Kotlin con Jetpack Compose, Room y ZXing. El servicio Bluetooth, en Python, "
        "recibe los datos por RFCOMM y los deja en una tabla de tránsito. Oracle XE 11g aloja el paquete `PKG_BATCH`, las vistas "
        "`V_*` y los trabajos de `DBMS_SCHEDULER`. La aplicación de escritorio usa PyQt6 y pyqtgraph. Todo lo que corre en el "
        "computador va en contenedores Docker, y el servicio Bluetooth y el escritorio solo se comunican a través de la base de datos.",
    "La comunicación usa un protocolo propio ":
        "Entre el teléfono y el servicio se usa un protocolo propio de líneas de texto con CRC32. El servidor confirma de forma "
        "acumulativa (`ACK`), rechaza con `NAK` para que el móvil retroceda (_go-back-N_) y reanuda desde el último número de "
        "secuencia guardado; la clave única `(uuid, seq)` impide los duplicados. Al elaborar este documento se ejecutaron 115 "
        "pruebas de la APK sin fallos, 230 de 238 del servidor y 454 de 464 del escritorio en una base limpia (los 18 fallos se "
        "analizan en el capítulo 14). También se hizo una sincronización real de extremo a extremo con el transporte TCP del "
        "proyecto y se capturó la aplicación de escritorio en ejecución con los dos roles que la usan.",
    "El trabajo se desarrolla en la asignatur":
        "La asignatura es Computación móvil, del programa de Ingeniería de software de la Universidad Manuela Beltrán. El "
        "proyecto reúne tres temas que el curso suele tratar por separado: captura de datos en un dispositivo móvil, "
        "comunicación inalámbrica de corto alcance y procesamiento por lotes sobre una base de datos empresarial.",
    "En un conteo físico, el operador recorre":
        "En un conteo físico el operador recorre estanterías con el dispositivo en la mano. Si cada lectura exige red, una zona "
        "sin cobertura detiene el trabajo; si se anota en papel, aparecen errores de transcripción y demoras. El proyecto parte "
        "de una decisión de diseño documentada (D1): el terminal cuenta sin red y sube lo contado por lotes cuando está cerca "
        "del computador.",
    "La solución desacopla la captura de la c":
        "Separar la captura de la conectividad tiene un costo: la sincronización debe resolver el orden de las lecturas, los "
        "duplicados, los cortes, los relojes desfasados y las cuentas no autorizadas. Los capítulos 9 y 10 explican cómo lo "
        "hace el protocolo y el capítulo 14 presenta las pruebas que se ejecutaron.",
    "Están dentro del alcance: la captura móv":
        "Dentro del alcance están la captura móvil con escáner de barras y QR, las cuentas locales del operador, el protocolo "
        "Bluetooth versión 5, la persistencia en Oracle, el _batch_ de conciliación, el escritorio con doce módulos controlados "
        "por permisos, los respaldos y la auditoría. Quedan fuera iOS (D4), Windows como anfitrión del servicio Bluetooth, los "
        "almacenes o ubicaciones múltiples (D24), el cierre de inventario y la valoración monetaria de las diferencias.",
    "El capítulo 3 enuncia los objetivos; el ":
        "El capítulo 3 enuncia los objetivos y el 4 plantea el problema. Los capítulos 5 y 6 describen el sistema y sus "
        "requisitos, y del 7 al 10 se documentan arquitectura, datos, comunicación y flujos. El 11 recorre los módulos, el 12 y "
        "el 13 tratan la interfaz y la seguridad, y el 14 presenta las pruebas. El 15 es el manual de instalación; el 16 y el 17 "
        "comparan los resultados con los objetivos y con la rúbrica. Cierran las conclusiones, el trabajo futuro, las "
        "referencias y los anexos.",
    "Diseñar, implementar y documentar un sis":
        "Diseñar, implementar y documentar un sistema de inventario físico que capture lecturas sin conexión en un dispositivo "
        "Android, las transfiera por Bluetooth a un computador, las almacene y concilie en Oracle con un proceso por lotes "
        "PL/SQL y las presente en una aplicación de escritorio con control de acceso por roles.",
    "El proyecto no documenta una organizació":
        "El proyecto no documenta una organización cliente ni cifras de un procedimiento anterior, así que este capítulo se "
        "limita a lo que se deduce del diseño y de las decisiones de `docs/arquitectura.md`. La necesidad de fondo es contar "
        "productos donde la conectividad no está garantizada y consolidar el resultado en una base central que no reciba "
        "duplicados ni lecturas de personas no autorizadas.",
    "Bluetooth clásico (RFCOMM) se eligió por":
        "Se eligió Bluetooth clásico (RFCOMM) porque no necesita infraestructura de red y viene en cualquier teléfono Android. "
        "Oracle 11g sigue como destino porque es el motor del escenario académico; como no tiene `IDENTITY` ni funciones JSON, "
        "se usan secuencias, disparadores y un formato de texto con separador `|` (D2). El _batch_ corre en PL/SQL dentro de la "
        "base para quedar junto a los datos y poder programarse con `DBMS_SCHEDULER`. El escritorio usa PyQt6 por sus hilos y "
        "señales, que permiten consultar Oracle sin congelar la ventana.",
    "El sistema está formado por **dos aplica":
        "El sistema tiene dos aplicaciones (la APK y el escritorio), un servicio (el servicio Bluetooth, que corre aparte de la "
        "ventana) y una base de datos (Oracle XE 11g). Las entradas son las lecturas del operador (SKU, cantidad, dañados, "
        "nota y foto opcional) y las acciones de los usuarios del escritorio. El procesamiento tiene tres etapas: validación y "
        "confirmación en el servicio, conciliación por lotes en Oracle y consulta desde el escritorio. De ahí salen el "
        "inventario conciliado, los indicadores del _dashboard_, las gráficas, el CSV, los respaldos y la auditoría.",
    "El [[f_arq]] muestra las cuatro capas":
        "La [[f_arq]] muestra las cuatro capas y los canales reales entre ellas. Solo la captura móvil funciona sin red; las "
        "demás dependen de Oracle.",
    "La [[t_modulos]] resume los módulos.":
        "La [[t_modulos]] resume los módulos. La matriz de permisos maneja doce: `dashboard`, `inventario`, `graficas`, `sync`, "
        "`notificaciones`, `perfil`, `solicitudes`, `usuarios`, `permisos`, `auditoria`, `configuracion` y `respaldos`. El "
        "capítulo 11 describe cada uno.",
    "Cada teléfono guarda sus datos en SQLite":
        "Cada teléfono guarda sus datos en SQLite (Room): `Outbox`, catálogo y cuentas locales. El computador guarda todo en "
        "Oracle XE 11g; las fotos de evidencia quedan en `fotos/<uuid>/<seq>.jpg` y los respaldos `.zip` en `respaldos/`. Fuera "
        "del código del proyecto están BlueZ (`bluetoothd`, que vive en el anfitrión), el bus D-Bus del sistema, el servidor "
        "gráfico X11 o Wayland y Docker.",
    "Los requisitos se extrajeron del código ":
        "Los requisitos salen del código y de la documentación del proyecto, y todos están implementados. En la columna de "
        "verificación, el nombre de una prueba remite a una prueba automática existente en el repositorio y una figura, a una "
        "captura obtenida para este documento.",
    "El [[f_cu]] presenta los actores":
        "La [[f_cu]] muestra los actores, el límite del sistema y las relaciones `include` y `extend`, contrastadas con la "
        "implementación. El Scheduler de Oracle figura como actor porque inicia el procesamiento por lotes sin intervención humana.",
    "El sistema combina tres estilos que se p":
        "Tres estilos conviven en el código. En conjunto, el sistema es una arquitectura por capas repartida en procesos "
        "(captura móvil, recepción, base de datos y presentación) cuyos únicos canales son RFCOMM, D-Bus y SQL*Net. El "
        "escritorio sigue MVC con trabajadores: el modelo son los _dataclasses_ de `models.py` y las consultas de `db.py`, las "
        "vistas están en `desktop/app/views/` y el controlador es `QueryRunner`, que ejecuta cada consulta en un `QueryWorker` "
        "y devuelve el resultado al hilo de la interfaz. Android sigue MVVM: las pantallas Compose de `ui/pantallas/` no guardan "
        "estado, `CountViewModel` y `SyncRunner` exponen estados, y el modelo lo forman `Outbox`, el catálogo en Room, "
        "`SyncClient` y `Protocol`.",
    "No se etiqueta la arquitectura como un ú":
        "Se evita llamar al sistema «MVC» o «MVVM» sin más porque cada cliente aplica un patrón distinto; los archivos citados y "
        "las figuras de código de este capítulo respaldan la clasificación.",
    "Las capas 2 y 4 son **dos procesos**":
        "Las capas 2 y 4 son dos procesos distintos, de modo que la recepción sigue activa aunque se cierre la ventana del "
        "escritorio. Solo se comunican por Oracle: el servicio escribe su estado y su latido en `SERVICIO_BT` y el escritorio "
        "lo lee cada 2 s con `ServicioRemoto`. Es un acoplamiento débil buscado (D11, D29).",
    "El [[f_desp]] (en página horizontal)":
        "La [[f_desp]], en página horizontal, muestra dónde corre cada componente. Docker Compose define tres servicios "
        "permanentes (`oracle`, `app` y `bluetooth`) y cuatro de apoyo, activados por perfiles (`pybase`, `apk-build`, "
        "`plantuml` y `bt-spike`). `app` y `bluetooth` usan `network_mode: host`, `NET_ADMIN`/`NET_RAW` y el bus D-Bus del "
        "anfitrión, porque `bluetoothd` no corre en contenedor (D7). El teléfono y el computador solo se hablan por Bluetooth clásico.",
    "El [[f_comp]] muestra los componentes y ":
        "La [[f_comp]] muestra los componentes y sus interfaces (`Transport`, RFCOMM, D-Bus, SQL*Net). `SyncController` depende "
        "de la interfaz `Transport` y no de una implementación, así que `BluezTransport` y `TcpTransport` son intercambiables "
        "(plan B por TCP). La [[f_paq]] agrega las dependencias entre paquetes de Python y de Kotlin: las vistas del "
        "escritorio no importan el servicio Bluetooth y solo comparten `Store.connect_oracle`.",
    "El [[f_clases]] (siguiente página horizo":
        "La [[f_clases]] presenta las clases de la librería `btsync`: `Message`, `Rec` y `FrameError` para el protocolo, `Store` "
        "para la persistencia, `Session` para cada conversación con un teléfono, `SyncController` como máquina de estados y los "
        "transportes. Las clases del escritorio y de la APK están en el Anexo B ([[f_clases_pc]] y [[f_clases_android]]).",
    "La [[t_hilos]] identifica los hilos":
        "La [[t_hilos]] enumera los hilos y mecanismos asíncronos que hay en el código. En el escritorio ninguna consulta a "
        "Oracle corre en el hilo de la interfaz, y en Android la red y el disco pasan a `Dispatchers.IO`.",
    "Para la rúbrica de arquitectura, el punt":
        "En términos de la rúbrica, el código demuestra dos cosas: el escritorio no se bloquea por consultas y la APK no hace "
        "red en su hilo principal. La [[f_estados]] muestra la máquina de estados del controlador, que coordina estas piezas.",
    "El motor es **Oracle Database 11g Expres":
        "El motor es Oracle Database 11g Express Edition 11.2.0.2.0, verificado con `v$version` en el contenedor "
        "`gvenzl/oracle-xe:11-slim`. Las aplicaciones Python se conectan con python-oracledb 26.1.0 en modo _thick_ y el "
        "Instant Client 19.23, que Oracle 11g exige. La conexión de la aplicación y la del servicio usan el usuario `app`; "
        "sus credenciales viven en `.env` y no se reproducen en este documento. Los datos persisten en un volumen Docker "
        "(`oracle-data`). La [[c_conn]] muestra cómo se abre cada conexión.",
    "El esquema tiene 17 tablas:":
        "El esquema tiene 17 tablas: catorce las crea `db/init/01_schema.sql` y tres las crea la propia aplicación al arrancar "
        "(`AUDITORIA`, `NOTIFICACIONES` y `NOTIFICACIONES_LEIDAS`). La [[t_tablas]] resume las principales con sus claves y la "
        "[[f_er]] muestra todas con sus relaciones. La tabla de _staging_ aparece en detalle en la [[c_sql1]].",
    "El proyecto implementa cuatro canales de":
        "El proyecto usa cuatro canales de datos. No hay REST ni WebSockets: el código no tiene ninguna interfaz HTTP. Los "
        "canales son Bluetooth clásico RFCOMM entre la APK y el servicio, D-Bus entre el servicio y BlueZ, SQL*Net entre las "
        "aplicaciones Python y Oracle, y un transporte TCP alterno para pruebas y demostraciones (`BT_TRANSPORT=tcp`). Entre "
        "el servicio y el escritorio no hay un canal directo: se coordinan mediante la tabla `SERVICIO_BT`.",
    "Cada mensaje es una línea UTF-8 terminad":
        "Un mensaje es una línea UTF-8 terminada en `\\n`, con los campos separados por `|`. Al final se agregan `*` y el CRC32 "
        "de los bytes anteriores, en ocho dígitos hexadecimales mayúsculos. El máximo es de 4000 bytes por línea. Dentro de los "
        "campos de texto, `%`, `|`, `\\r` y `\\n` se codifican como `%25`, `%7C`, `%0D` y `%0A`. Con la herramienta del "
        "proyecto (`python -m btsync.protocol --frame`) se obtiene, por ejemplo, `HELLO|5|dev-0001|Bodega Norte*788FF277`. "
        "La [[c_frame]] muestra la construcción y la validación de la trama.",
    "El [[f_sec5]] sigue el recorrido":
        "La [[f_sec5]] sigue un conteo desde la `Outbox` hasta la consulta en el escritorio. Para cada `REC` la sesión valida, "
        "en este orden, longitud, CRC, formato, cuenta activa y secuencia. Un `seq` menor al esperado es un duplicado y se "
        "ignora (lo cubre el siguiente `ACK`); uno mayor indica un hueco y provoca un único `NAK|esperado|SECUENCIA`; uno "
        "igual se inserta. El bucle de la sesión está en la [[c_bucle]], la validación de cada `REC` en la [[c_onrec]], la "
        "confirmación en la [[c_ack]] y el perfil RFCOMM que recibe la conexión en la [[c_perfil]].",
    "Si la conexión se corta antes del `COMMIT`":
        "Si la conexión se corta antes del `COMMIT`, el servidor hace `ROLLBACK` y conserva solo lo confirmado. Al reconectar, "
        "el móvil recibe `READY|<último seq>` y reconcilia su `Outbox`: lo confirmado pasa a `CONFIRMADO` y lo enviado sin "
        "confirmar vuelve a `PENDIENTE`. `SyncRunner` reintenta la conexión hasta tres veces. La [[f_sec6]] describe el caso "
        "probado con 30 lecturas y la sección 9.5 muestra la misma situación en una ejecución real. Del lado móvil, "
        "`SyncClient` ([[c_async]]), `SyncRunner` ([[c_arunner]]) y la `Outbox` ([[c_aout]]) implementan esta parte.",
    "En este equipo no hay un teléfono empare":
        "En este equipo no hay un teléfono emparejado (`adb devices` no lista dispositivos), así que la evidencia de "
        "comunicación usa el transporte TCP del proyecto con el teléfono simulado `tools/fake_phone.py`, que habla el mismo "
        "protocolo que la APK. La prueba se hizo contra un Oracle independiente y limpio (puerto 1522) para no alterar los datos "
        "de demostración. El enlace Bluetooth físico no se verificó en esta ejecución; la capa Bluetooth se comprueba con las "
        "pruebas de `BluezTransport` (con un bus D-Bus falso) y con la prueba de campo que el proyecto documenta en "
        "`docs/spikes/bluez.md`.",
    "**Resultado de la sincronización.**":
        "Con la cuenta sin aprobar, el PC respondió que estaba pendiente y no aceptó lecturas ([[f_com1]]). Tras la "
        "aprobación, el teléfono envió 126 lecturas y el servicio contestó `BYE|126|0`. El _batch_ procesó 123, dejó 1 en "
        "`ERROR` (`CANTIDAD_INVALIDA`) y 2 en `NUEVO_SKU`, sin filas duplicadas ([[f_com2]]).",
    "**Corte y reanudación.**":
        "Un segundo teléfono simulado se terminó con `SIGKILL` a los 4 s y en Oracle quedaron 50 filas confirmadas. Al "
        "relanzarlo con el mismo _outbox_, el servicio informó el último `seq` y el teléfono envió solo las 70 restantes "
        "(`BYE|70|0`): 120 filas en total y ninguna duplicada ([[f_cor1]] y [[f_cor2]]).",
    "Por decisión de diseño (D22) el modo por":
        "Por decisión de diseño (D22), el modo por defecto no empareja ni cifra el enlace: el teléfono recuerda al PC y conecta "
        "directo. Quien esté al alcance (unos 10 m) podría conectarse y enviar lecturas falsas mientras el servicio esté activo. "
        "Lo limitan el aceptar un solo teléfono a la vez, la validación de cada línea, la exigencia de una cuenta aprobada y "
        "vinculada al UUID del teléfono, y la posibilidad de que el Administrador pause el servicio. Existe un modo con código "
        "de emparejamiento (`BT_CON_CLAVE=1`) que no se ejecutó en esta verificación. Por eso no se afirma que la "
        "comunicación sea segura en el sentido de la confidencialidad.",
    "Este capítulo describe los procesos de e":
        "Este capítulo describe los procesos de extremo a extremo con sus validaciones y errores. Los diagramas de secuencia "
        "de los flujos de datos están en el capítulo 9; aquí se agregan los de actividades y de estados.",
    "El [[f_act]] reparte las responsabilidade":
        "La [[f_act]] reparte las responsabilidades en carriles: el móvil, la sesión del servicio, el controlador y Oracle. "
        "Muestra el ciclo de lectura de `REC` con su validación, la confirmación cada 25 inserciones y el procesamiento por "
        "lotes con recuperación de filas huérfanas. El conteo visto desde el teléfono está en la [[f_act2]].",
    "Una fila de tránsito recorre":
        "Una fila de tránsito pasa por `PENDIENTE → PROCESANDO → PROCESADO | ERROR | NUEVO_SKU | DESCARTADO` ([[f_est2]]). Una "
        "cuenta pasa por `PENDIENTE → ACTIVO | RECHAZADO` y `ACTIVO ⇄ SUSPENDIDO` ([[f_est3]]). Ambos diagramas coinciden con "
        "las restricciones `CHECK` del esquema.",
    "Cada módulo se describe con una ficha y,":
        "Cada módulo se describe con una ficha y, si tiene interfaz, con una captura de la aplicación en ejecución. Las "
        "capturas del escritorio se tomaron ejecutando la ventana real (`app.main.build_window`) con las cuentas de "
        "demostración del README, en el contenedor de la aplicación con Qt en modo `offscreen`, y guardando el contenido de la "
        "ventana con `QWidget.grab`. Las de la APK son renderizados del código Compose de la propia aplicación que produce la "
        "prueba `CapturasTest`; no son fotografías de un teléfono. Los datos visibles son los de demostración del proyecto "
        "(`08_demo.sql`).",
    "En las capturas del escritorio aparecen":
        "En las capturas del escritorio aparecen dos elementos transitorios reales: un aviso emergente «Servicio Bluetooth en "
        "pausa» (el servicio estaba pausado en la base de demostración) y el aviso flotante «Nuevo SKU», con dos lecturas de "
        "SKU no registrados. No se alteraron datos para ocultarlos.",
    "Estos dos módulos no tienen interfaz pro":
        "Estos dos módulos no tienen interfaz propia, y su evidencia es la ejecución descrita en la sección 9.5 y las pruebas "
        "del capítulo 14. El servicio Bluetooth (`btsync.servicio`) mantiene el perfil RFCOMM, crea una `Session` por teléfono, "
        "escribe su estado y su latido en `SERVICIO_BT` y ejecuta el respaldo automático; su código se recorre en la sección "
        "7.7. El _batch_ (`PKG_BATCH`) valida cada fila, calcula la lectura vigente y concilia `ACTUAL`; en la ejecución real "
        "procesó 123 lecturas con 1 error y sin duplicados.",
    "El análisis se hizo con la aplicación ej":
        "El análisis se hizo con la aplicación en ejecución. Se separa lo observado en las capturas de lo que el código "
        "declara, y se anotan también los defectos encontrados.",
    "La ventana tiene un mínimo de 900 × 600":
        "La ventana tiene un mínimo de 900 × 600 (`setMinimumSize`) y se probó a 900 × 600, 1240 × 800, 1366 × 768 y "
        "1920 × 1080. A 900 px la barra lateral se contrae sola a iconos ([[f_res900]]); también se puede contraer a mano "
        "([[f_lateral]]). A 1920 × 1080 el contenido aprovecha el ancho y muestra más filas ([[f_res1920]]). La [[f_sync1366]] "
        "muestra el módulo más ancho, Sincronización, en una pantalla de portátil común.",
    "La APK usa Jetpack Compose con Material ":
        "La APK usa Jetpack Compose con Material 3 y sus renderizados se hicieron a 1080 × 2340 en vertical. No se evaluó la "
        "orientación horizontal ni otros tamaños de teléfono o tableta, por lo que la adaptabilidad móvil queda sin demostrar.",
    "La barra lateral muestra solo los módulo":
        "La barra lateral muestra solo los módulos del rol: el Administrador ve nueve módulos más Perfil al pie, y el rol "
        "Inventario cuatro más Perfil ([[f_roles_barras]]). El Operador no usa el escritorio. La sección 13.2 compara ambas "
        "experiencias.",
    "El proyecto implementa transiciones de p":
        "El proyecto tiene transiciones de página, entrada escalonada de tarjetas, gráficas con movimiento y arrastre de "
        "tarjetas en el Dashboard (`motion_global.py`, `graficas_motion.py`, `rejilla_personal.py`), que se controlan con la "
        "variable `APP_SIN_ANIMACIONES`. Las capturas se tomaron con las animaciones apagadas para obtener el estado final. No "
        "se grabó video ni GIF, así que la fluidez de las transiciones no queda demostrada visualmente en este documento; "
        "solo hay pruebas automáticas (`test_dashboard_motion.py`, `test_motion_admin.py`, `test_sync_motion.py`).",
    "La [[t_roles_pantallas]] compara":
        "La [[t_roles_pantallas]] compara lo que ve cada rol en el escritorio, según las capturas y el resultado de "
        "`MainWindow.secciones()` impreso durante la captura. El Administrador ve nueve secciones más Perfil y el rol Inventario "
        "cuatro más Perfil. El Operador no puede iniciar sesión en el escritorio y recibe «Los operadores usan la app móvil».",
    "**Restricciones comprobadas:**":
        "Restricciones comprobadas: la barra del rol Inventario no incluye Solicitudes, Empleados, Roles y permisos, "
        "Auditoría, Configuración ni Respaldos, y ese rol no puede cambiar la matriz. El Administrador, en cambio, no ve el "
        "módulo Gráficas. Que un módulo sin permiso no se abra lo garantiza `ir_a`, que ignora los títulos fuera de "
        "`secciones()`, y lo comprueban `test_app.py::test_admin_sidebar_exact_order_and_profile_at_the_footer` y "
        "`test_inventory_sidebar_exact_order`.",
    "Se distinguen tres tipos de evidencia.":
        "Hay tres tipos de evidencia. Primero, las pruebas que ya existen en el repositorio: `server/tests` (pytest contra "
        "Oracle), `desktop/tests` (pytest-qt con Qt `offscreen`, contra Oracle) y `mobile/app/src/test` (JUnit en la JVM). "
        "Segundo, las pruebas ejecutadas al elaborar este documento el 17 de noviembre de 2026, con los comandos del capítulo 15 "
        "y los scripts de `docs/documentacion/herramientas/`; su salida completa está en `docs/documentacion/anexos/registros/`. "
        "Tercero, las verificaciones visuales sobre las capturas de la aplicación en ejecución. No se midió la cobertura de "
        "código ni los tiempos de transferencia, de modo que no se reporta ninguna cifra de cobertura ni de rendimiento.",
    "Se usaron dos bases porque las pruebas":
        "Se usaron dos bases porque las pruebas están escritas para la base limpia de la semilla del proyecto; el Oracle de "
        "trabajo tiene 13 meses de datos de demostración y rompe más aserciones numéricas. La tabla compara las dos "
        "ejecuciones. Las suites se corrieron en serie porque comparten base (como exige el propio proyecto) y no se modificó "
        "ningún archivo de producto para que pasaran.",
    "En la base limpia fallan 8 pruebas":
        "En la base limpia fallan 8 pruebas del servidor y 10 del escritorio. No se corrigió ningún archivo, para no alterar "
        "el producto evaluado, y se clasifican así:",
    "Con la base de demostración los fallos s":
        "Con la base de demostración los fallos suben a 11 en el servidor y 15 en el escritorio, porque además cambian las "
        "sumas por categoría y por operador. Los registros completos permiten comprobarlo.",
    "Los comandos de este capítulo provienen":
        "Los comandos de este capítulo vienen del `README.md` y del `docker-compose.yml` del proyecto, y se usaron en la "
        "verificación (contenedores `oracle`, `bluetooth` y `app` y las suites de prueba). Si la ruta del proyecto tiene "
        "espacios (`/home/t1an/movil oracle bluetooth`), hay que entrecomillarla.",
    "Las variables se definen en el archivo ":
        "Las variables se definen en `.env`, copiado de `.env.example`, que trae valores de desarrollo local y no se "
        "reproduce aquí. El archivo `.env` no se versiona.",
    "**Cuentas.** Con los datos de demostr":
        "Cuentas. Con los datos de demostración existen `admin` (Administrador) e `inventario`, con la contraseña de "
        "demostración que indica el README; `laura.mora` y `sofia.vega` quedan pendientes en Solicitudes. En una base sin "
        "demostración (borrando `08_demo.sql` antes de crearla), la primera cuenta del PC pasa a ser el Administrador.",
    "Las mejoras se priorizan en el capítulo ":
        "Las mejoras se priorizan en el capítulo 19; ninguna está implementada.",
    "La [[t_rubrica]] presenta una":
        "La [[t_rubrica]] presenta una autoevaluación técnica razonada. No es la calificación oficial, que asigna el "
        "evaluador. Se usa la escala de la rúbrica (Excelente 5,0; Satisfactorio 4,0; En desarrollo 3,0; Insuficiente de 1,0 "
        "a 2,0) con valores intermedios solo cuando la evidencia cumple parte de un nivel superior.",
    "**Cálculo ponderado indicativo:**":
        "Cálculo ponderado indicativo: 0,25 × 4,2 + 0,25 × 4,3 + 0,20 × 4,5 + 0,15 × 4,0 + 0,15 × 4,5 = 4,3 sobre 5,0. Es un "
        "resumen de la autoevaluación: depende de las valoraciones intermedias de arriba, que son juicios de los autores del "
        "documento y no mediciones.",
    "Los anexos reúnen las evidencias complet":
        "Los anexos reúnen las evidencias completas. Los archivos originales (capturas, diagramas fuente y renderizados, "
        "registros de ejecución y scripts) están en `docs/documentacion/` del repositorio y se enumeran en "
        "`INDICE_EVIDENCIAS.md`.",
    "La matriz relaciona cada criterio de la":
        "La matriz relaciona cada criterio de la rúbrica con lo que debe demostrarse, el componente, la evidencia técnica, las "
        "capturas, las pruebas y el resultado de la verificación. Las referencias son a figuras y tablas de este documento.",
}

LISTAS = {
    "**Falta de red durante el conteo:**": "Sin red durante el conteo, la captura no puede depender de un servidor; por eso la APK guarda primero en una base local (D1, D12).",
    "**Cortes de la conexión inalámbrica:**": "El enlace Bluetooth de corto alcance puede cortarse a mitad de un lote, y el protocolo reanuda desde el último `seq` confirmado.",
    "**Sesgo del conteo:**": "Si el operador viera la cantidad teórica podría ajustar lo que cuenta; por eso el catálogo que baja al teléfono nunca lleva el stock (conteo ciego, D12).",
    "**Productos no registrados:**": "Aparecen SKU que no están en el catálogo. En vez de perder la lectura, el Administrador decide si crea el producto o la descarta (D16).",
    "**Relojes desfasados:**": "Sin red el reloj del teléfono se desfasa; se corrige con la hora del servidor sin modificar la hora original (D15).",
    "**Control de acceso:**": "Solo las cuentas aprobadas entregan lecturas y cada rol ve únicamente sus módulos (D23 a D26).",
    "**Estructura:** barra lateral": "Hay una barra lateral izquierda con iconos y texto, una cabecera con el título, el estado de Oracle y de Bluetooth y el botón «Actualizar», y el contenido en tarjetas. El pie de la barra muestra avatar, nombre, rol, tema y cerrar sesión, y la campana está junto al título de la barra.",
    "**Identidad visual:**": "El color de acción es un verde esmeralda (`#10B981` y tonos) sobre fondo gris claro y tarjetas blancas; el rojo y el ámbar marcan faltantes y sobrantes. La tipografía es la sans-serif por defecto del sistema (en el contenedor donde se tomaron las capturas, DejaVu Sans), porque el proyecto no incorpora una fuente propia.",
    "**Iconografía:**": "Cada módulo tiene un icono de trazo (`views/iconos.py`).",
    "**Consistencia:**": "Las cabeceras, las tablas con encabezado fijo y los botones (primarios verdes, secundarios con borde) se repiten en todas las pantallas.",
    "**Navegación por teclado:**": "Por teclado hay atajos para ir a un módulo por número y para enfocar el buscador (`MainWindow._instalar_atajos`).",
    "**Carga:**": "Mientras Oracle responde, las tarjetas muestran «—» y «Cargando…» ([[f_carga]]).",
    "**Vacío:**": "Respaldos muestra «Aún no hay respaldos» y la tabla «Sin datos» ([[f_resp]]); Solicitudes usa «Sin datos» en la tabla de contraseñas ([[f_solicitudes]]); el catálogo móvil dice «No hay productos en el catálogo» ([[f_mov2]]).",
    "**Error:**": "La APK muestra «PC ocupado» y «No se pudo conectar» con icono y texto ([[f_mov3]]); el acceso muestra el mensaje de credenciales incorrectas ([[f_mov1]]); el escritorio avisa cuando el servicio está en pausa.",
    "**Confirmaciones y avisos:**": "Hay avisos emergentes («Servicio Bluetooth en pausa»), confirmación antes de descartar un SKU nuevo y la palabra `RESTAURAR` como confirmación para restaurar un respaldo.",
}

# Listas que se emiten como párrafos (clave: comienzo del primer elemento)
LISTAS_A_PARRAFOS = {
    "**Arquitectura.** El sistema separa": [
        "La arquitectura separa captura, recepción, procesamiento y presentación en procesos distintos que solo se acoplan por "
        "Oracle y por un protocolo explícito. El escritorio sigue MVC con trabajadores y Android, MVVM; el transporte "
        "intercambiable permitió probar la comunicación sin Bluetooth.",
        "Los 28 requisitos funcionales identificados están implementados, y los flujos de extremo a extremo (captura, "
        "sincronización, conciliación y consulta) se ejecutaron con resultados coherentes.",
        "El protocolo con CRC32, `ACK` acumulativo, `NAK` con retroceso y clave `(uuid, seq)` resistió un corte forzado sin "
        "pérdidas ni duplicados (50 + 70 filas). La seguridad del canal por defecto es limitada por diseño (D22) y no debe "
        "presentarse como confidencial.",
        "El modelo de 17 tablas, con sus restricciones, vistas y un paquete PL/SQL, mantiene la integridad de los datos. La "
        "clave única y la tabla de _staging_ separan la recepción del procesamiento.",
        "La aplicación de escritorio es coherente y se adapta de 900 a 1920 px, con estados de carga, vacío y error. Quedan "
        "solapamientos menores y la adaptabilidad móvil sin demostrar.",
        "En la base limpia se ejecutaron 799 pruebas aprobadas (230 + 454 + 115). Fallan 18, por pruebas desactualizadas y casos "
        "de geometría sin diagnosticar, lo que indica que el mantenimiento de las pruebas no siguió al de la semilla.",
        "El objetivo general se cumple en lo verificado. El enlace Bluetooth físico, la orientación horizontal en Android y la "
        "medición de rendimiento quedan fuera de lo que este documento demuestra.",
    ],
    "**Comprobado en ejecución:**": [
        "En ejecución se comprobaron el acceso, el dashboard, el inventario, las gráficas (rol Inventario), la sincronización, "
        "las solicitudes, los empleados, los roles y permisos, la auditoría, la configuración, los respaldos (solo la vista "
        "vacía), las notificaciones y el perfil del escritorio. También se sincronizaron 126 lecturas, se reanudó tras un corte "
        "por el transporte TCP, se ejecutó el _batch_ con su conciliación y se aprobaron las 115 pruebas de la APK.",
        "Entre las limitaciones, no se ejecutó el enlace Bluetooth físico ni se usó un teléfono real, no se probaron la "
        "orientación horizontal ni otros tamaños en Android, no se midió el rendimiento y no se creó ni restauró un respaldo "
        "sobre la base de demostración. Por diseño solo se sincroniza un teléfono a la vez y el enlace no se cifra por defecto.",
        "Los problemas identificados son 18 pruebas fallidas en Oracle limpio (cifras de la semilla de 120 SKU, una clase UML "
        "inexistente, tres pruebas de geometría sin diagnosticar y dos preexistentes; ver 14.4), el recorte del módulo "
        "Sincronización a 1240 px y el solapamiento transitorio del aviso emergente con la cabecera.",
        "La documentación previa tiene dos inconsistencias: el README describe al Administrador con acceso a «todo», pero el "
        "módulo Gráficas solo se registra para el rol Inventario, y `docs/verificacion.md` cita 60 productos y 216 + 166 + 110 "
        "pruebas, cifras anteriores a la semilla actual (120 SKU y 238 + 464 + 115 pruebas).",
        "Queda código residual: `desktop/app/views/iconos.py` conserva iconos de pantallas retiradas y `web/` es un directorio "
        "no rastreado ajeno al sistema (observaciones O3 y O4 de `docs/verificacion.md`).",
    ],
}


def parrafo(texto: str) -> str:
    for clave, nuevo in PARRAFOS.items():
        if texto.startswith(clave):
            return nuevo
    return texto


def item(texto: str) -> str:
    for clave, nuevo in LISTAS.items():
        if texto.startswith(clave):
            return nuevo
    return texto


def lista_a_parrafos(items: list[str]):
    for clave, parrafos in LISTAS_A_PARRAFOS.items():
        if items and items[0].startswith(clave):
            return parrafos
    return None
