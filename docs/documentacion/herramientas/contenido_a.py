"""Capítulos 1 a 6: resumen, introducción, objetivos, problema, descripción general y requisitos."""
from docgen import H, P, Lista, Tabla, Fig, Horizontal, Cmd

R = "diagramas/renderizados/"


def bloques() -> list:
    b: list = []

    # ------------------------------------------------------------------ 1
    b += [
        H(1, "1. Resumen ejecutivo"),
        P("El sistema **Inventario físico offline: APK → Bluetooth → Oracle → aplicación de escritorio** permite que un "
          "operador cuente productos con un teléfono Android sin conexión de red, que el conteo viaje por Bluetooth hasta un "
          "computador con Linux, que se almacene en Oracle 11g y que un proceso por lotes (_batch_) escrito en PL/SQL lo "
          "concilie contra el stock del sistema. Un único programa de escritorio presenta el resultado en tableros, tablas "
          "y gráficas. El conteo es **continuo**: no hay cierre de inventario, y la información se recalcula cada vez que el "
          "_batch_ procesa nuevas lecturas."),
        P("El problema que resuelve es la toma de inventario físico en bodegas o tiendas donde no hay red confiable: el "
          "operador no puede depender de un servidor para registrar cada lectura, pero necesita que lo contado llegue de "
          "forma íntegra, sin duplicados y con trazabilidad al equipo central. El sistema está dirigido a tres roles: "
          "el **Operador de Inventario** (solo móvil), el rol **Inventario** y el **Administrador** (solo escritorio)."),
        P("La solución se compone de cuatro piezas: (1) una aplicación Android escrita en Kotlin con Jetpack Compose, Room y "
          "ZXing; (2) un servicio Bluetooth en Python que recibe los datos por RFCOMM y los guarda en una tabla de tránsito; "
          "(3) una base Oracle XE 11g con el paquete `PKG_BATCH`, vistas `V_*` y trabajos de `DBMS_SCHEDULER`; y (4) una "
          "aplicación de escritorio en PyQt6 y pyqtgraph. Los componentes del lado del computador corren en contenedores "
          "Docker; la única interfaz entre el servicio Bluetooth y el escritorio es la propia base de datos."),
        P("La comunicación usa un protocolo propio de líneas de texto con CRC32, confirmaciones acumulativas (`ACK`), "
          "rechazos con retroceso (`NAK`, _go-back-N_), reanudación desde el último número de secuencia persistido y "
          "una clave única `(uuid, seq)` que impide duplicados. Los resultados técnicos comprobados durante la elaboración de "
          "este documento son: 115 pruebas unitarias de la APK sin fallos, 230 de 238 pruebas del servidor y 454 de 464 del "
          "escritorio aprobadas en una base limpia (los 18 fallos restantes se analizan en el capítulo 14), "
          "una sincronización real de extremo a extremo por el transporte TCP del proyecto, y capturas reales de las "
          "pantallas de escritorio de los dos roles que lo usan."),
    ]

    # ------------------------------------------------------------------ 2
    b += [
        H(1, "2. Introducción"),
        H(2, "2.1 Contexto del proyecto"),
        P("El trabajo se desarrolla en la asignatura Computación móvil del programa de Ingeniería de software de la "
          "Universidad Manuela Beltrán. El proyecto integra una aplicación móvil de captura de datos, una comunicación "
          "inalámbrica de corto alcance y un procesamiento por lotes sobre una base de datos empresarial, tres temas "
          "centrales de la computación móvil: captura en el borde, sincronización diferida y persistencia centralizada."),
        H(2, "2.2 Situación que origina la solución y problema identificado"),
        P("En un conteo físico, el operador recorre estanterías con un dispositivo en la mano. Si cada lectura exige red, "
          "una zona sin cobertura detiene el trabajo; si se registra en papel, aparecen errores de transcripción y demoras. "
          "El proyecto asume, como decisión de diseño documentada (D1), que el terminal cuenta sin red y sube lo contado "
          "por lotes cuando está cerca del computador."),
        H(2, "2.3 Importancia de la solución"),
        P("La solución desacopla la captura de la conectividad: guardar una lectura nunca depende de la red. A cambio, "
          "exige resolver con cuidado la sincronización: orden, duplicados, cortes, relojes desfasados y cuentas no "
          "autorizadas. Estos problemas se abordan en los capítulos 9 y 10 con un protocolo verificable y con pruebas "
          "automáticas que se ejecutaron para este documento."),
        H(2, "2.4 Alcance"),
        P("Están dentro del alcance: la captura móvil con escáner de códigos de barras y QR, las cuentas locales del "
          "operador, el protocolo Bluetooth de versión 5, la persistencia en Oracle, el _batch_ de conciliación, la "
          "aplicación de escritorio con doce módulos controlados por permisos, los respaldos y la auditoría. Quedan fuera: "
          "iOS (D4), Windows como sistema anfitrión del servicio Bluetooth, múltiples almacenes o ubicaciones (D24), el "
          "cierre de inventario y la valoración monetaria de diferencias."),
        H(2, "2.5 Organización del documento"),
        P("El capítulo 3 enuncia los objetivos; el 4 plantea el problema y su justificación; el 5 describe el sistema; el 6 "
          "analiza los requisitos; los capítulos 7 a 10 documentan arquitectura, datos, comunicación y flujos; el 11 "
          "describe cada módulo; los capítulos 12 y 13 tratan la experiencia de usuario y la seguridad; el 14, las pruebas; "
          "el 15, la instalación; los capítulos 16 y 17 presentan resultados y la evaluación frente a la rúbrica; y los "
          "capítulos 18 y 19 recogen conclusiones y trabajo futuro. Las referencias y los anexos cierran el documento."),
    ]

    # ------------------------------------------------------------------ 3
    b += [
        H(1, "3. Objetivos"),
        H(2, "3.1 Objetivo general"),
        P("Diseñar, implementar y documentar un sistema de inventario físico que capture lecturas sin conexión en un "
          "dispositivo Android, las transfiera por Bluetooth a un computador, las almacene y concilie en Oracle mediante "
          "un proceso por lotes PL/SQL y las presente en una aplicación de escritorio con control de acceso por roles."),
        H(2, "3.2 Objetivos específicos"),
        Lista([
            "Construir una aplicación Android con catálogo local, escáner de códigos de barras y QR, cuentas locales y una "
            "bandeja de salida (_Outbox_) persistente que guarde primero y sincronice después.",
            "Definir e implementar un protocolo de líneas con CRC32, confirmaciones acumulativas, reanudación y "
            "retroceso ante errores, probado con los mismos vectores en Python y Kotlin.",
            "Implementar un servicio Bluetooth independiente de la interfaz que registre un perfil RFCOMM mediante BlueZ y "
            "guarde cada lectura de forma idempotente en una tabla de tránsito de Oracle.",
            "Escribir en PL/SQL el _batch_ que valida las lecturas, determina la lectura vigente por SKU y calcula la "
            "conciliación contra el stock del sistema.",
            "Desarrollar una aplicación de escritorio con PyQt6 que consulte Oracle sin bloquear la interfaz y que restrinja "
            "cada módulo según una matriz de permisos rol × módulo.",
            "Validar el sistema con pruebas automáticas, una sincronización real de extremo a extremo y capturas de la "
            "aplicación en ejecución, y documentarlo con diagramas UML y manual de instalación.",
        ]),
    ]

    # ------------------------------------------------------------------ 4
    b += [
        H(1, "4. Planteamiento del problema y justificación"),
        H(2, "4.1 Situación que busca resolver el sistema"),
        P("El proyecto no documenta una organización cliente concreta ni cifras de un procedimiento anterior; por ello este "
          "capítulo se limita a lo que se desprende del diseño y de las decisiones registradas en `docs/arquitectura.md`. "
          "La necesidad es contar productos en un lugar sin conectividad garantizada y consolidar el resultado en una base "
          "de datos central que no debe recibir duplicados ni lecturas de personas no autorizadas."),
        H(2, "4.2 Dificultades del proceso y necesidades de los usuarios"),
        Lista([
            "**Falta de red durante el conteo:** la captura no puede depender de un servidor; por eso la APK guarda en una "
            "base local antes de cualquier envío (D1, D12).",
            "**Cortes de la conexión inalámbrica:** el enlace Bluetooth de corto alcance puede interrumpirse a mitad de un "
            "lote; el protocolo reanuda desde el último `seq` confirmado.",
            "**Sesgo del conteo:** si el operador viera la cantidad teórica del sistema, podría ajustar lo que cuenta; el "
            "catálogo que baja al teléfono nunca lleva el stock (conteo ciego, D12).",
            "**Productos no registrados:** aparecen SKU que no están en el catálogo; en lugar de perder la lectura, el "
            "Administrador decide si crea el producto o la descarta (D16).",
            "**Relojes desfasados:** sin red, el reloj del teléfono deriva; se corrige con la hora del servidor sin "
            "modificar la hora original (D15).",
            "**Control de acceso:** solo cuentas aprobadas pueden entregar lecturas y cada rol ve únicamente los módulos "
            "que le corresponden (D23 a D26).",
        ]),
        H(2, "4.3 Justificación de la solución tecnológica"),
        P("Bluetooth clásico (RFCOMM) se eligió porque no requiere infraestructura de red y está disponible en cualquier "
          "teléfono Android. Oracle 11g se mantiene como destino porque es el motor del escenario académico; sus "
          "limitaciones (sin `IDENTITY` ni funciones JSON) llevaron a usar secuencias, disparadores y un formato de texto "
          "con separador `|` (D2). El _batch_ se ejecuta en PL/SQL dentro de la base para acercar el procesamiento a los "
          "datos y poder programarlo con `DBMS_SCHEDULER`. El escritorio usa PyQt6 por su soporte de hilos y señales, que "
          "permite consultar Oracle sin congelar la ventana."),
    ]

    # ------------------------------------------------------------------ 5
    b += [
        H(1, "5. Descripción general del sistema"),
        H(2, "5.1 Propósito, aplicaciones y flujo general"),
        P("El sistema está formado por **dos aplicaciones** (la APK Android y la aplicación de escritorio), **un servicio** "
          "(el servicio Bluetooth, que corre aparte de la ventana) y **una base de datos** (Oracle XE 11g). Las entradas "
          "son las lecturas del operador (SKU, cantidad, dañados, nota y foto opcional) y las acciones de los usuarios "
          "del escritorio. El procesamiento ocurre en tres etapas: validación y confirmación en el servicio Bluetooth, "
          "_batch_ de conciliación en Oracle y consulta desde el escritorio. Las salidas son el inventario conciliado, "
          "los indicadores del _dashboard_, las gráficas, la exportación CSV, los respaldos y la auditoría."),
        P("El [[f_arq]] muestra las cuatro capas y los canales de comunicación reales entre ellas. La captura móvil "
          "es la única capa que funciona sin red; las demás dependen de Oracle."),
        Fig("f_arq", R + "02_arquitectura_general.png",
            "Arquitectura general del sistema: capas y canales de comunicación.",
            ["Fuente: elaboración propia a partir del código. Fuente PlantUML: docs/documentacion/diagramas/plantuml/02_arquitectura_general.puml.",
             "Demuestra: separación en capas y canales reales (RFCOMM, D-Bus, SQL*Net). Criterio: Arquitectura y código fuente."],
            max_h=9000),
        H(2, "5.2 Actores y roles"),
        Tabla("t_roles", "Roles del sistema y dónde ingresan", ["Rol", "Dónde entra", "Qué puede hacer"],
              [["**Operador de Inventario**", "Solo móvil", "Catálogo, contar, contado, pendientes, sincronizar, notificaciones y mi cuenta. No ve la cantidad del sistema ni entra al escritorio."],
               ["**Inventario**", "Solo escritorio", "Dashboard, inventario completo, gráficas, sincronización, notificaciones y perfil. No administra cuentas, permisos, configuración ni respaldos."],
               ["**Administrador**", "Solo escritorio", "Todo lo anterior más solicitudes, empleados, roles y permisos, auditoría, configuración y respaldos. Hay uno solo (D25) y su fila de permisos está bloqueada."],
               ["**Scheduler de Oracle**", "Proceso", "Ejecuta `JOB_PROCESAR_CAPTURAS` (cada minuto por defecto) y `JOB_PURGA_TRANSITO` (diario)."]],
              [1800, 1500, 6060], "README.md y docs/arquitectura.md del proyecto."),
        H(2, "5.3 Módulos del sistema"),
        P("La [[t_modulos]] resume los módulos. Los doce módulos de la matriz de permisos son `dashboard`, `inventario`, "
          "`graficas`, `sync`, `notificaciones`, `perfil`, `solicitudes`, `usuarios`, `permisos`, `auditoria`, "
          "`configuracion` y `respaldos`; cada uno se describe con detalle en el capítulo 11."),
        Horizontal([
            Tabla("t_modulos", "Módulos del sistema",
                  ["Módulo", "Propósito", "Funcionalidades", "Actores", "Componentes técnicos", "Estado"],
                  [["Captura móvil", "Contar sin red", "Catálogo, escáner de barras/QR, digitación, dañados, nota, foto, recontar, Outbox", "Operador", "`mobile/` · Compose, Room, ZXing, `CountViewModel`", "Implementado"],
                   ["Cuentas móviles", "Identificar al operador", "Registro, acceso, recuperación por pregunta, foto, tema, idioma", "Operador", "`auth/AuthRepository.kt` (PBKDF2)", "Implementado"],
                   ["Sincronización móvil", "Subir lo contado", "Búsqueda del PC, conexión, envío en ventanas, reintentos", "Operador", "`SyncClient`, `SyncRunner`, `Protocol.kt`", "Implementado"],
                   ["Servicio Bluetooth", "Recibir y validar", "Perfil RFCOMM, sesión, CRC, ACK/NAK, COMMIT cada 25, pausa", "Sistema", "`server/btsync` · `Session`, `SyncController`, `BluezTransport`", "Implementado"],
                   ["Batch Oracle", "Conciliar", "Validar, lectura vigente, conciliar `ACTUAL`, alta de SKU", "Scheduler / sistema", "`db/init/03_pkg_batch.sql`", "Implementado"],
                   ["Dashboard", "Ver avance", "Avance, contados, faltantes, sobrantes, diferencia por categoría", "Admin, Inventario", "`views/dashboard.py`", "Implementado"],
                   ["Inventario", "Consultar lo conciliado", "5 columnas, búsqueda, CSV, detalle con foto", "Admin, Inventario", "`views/inventario.py`", "Implementado"],
                   ["Gráficas", "Analizar", "Seis gráficas con filtros", "Inventario", "`views/charts.py`, pyqtgraph", "Implementado"],
                   ["Sincronización (PC)", "Operar el servicio", "Estado, pausar, reanudar, procesar, reprocesar errores, alta de SKU", "Admin, Inventario", "`views/sync.py`, `ServicioRemoto`", "Implementado"],
                   ["Solicitudes / Empleados / Roles", "Administrar cuentas", "Aprobar o rechazar, suspender, desvincular, matriz de permisos", "Administrador", "`auth.py`, `permisos.py`", "Implementado"],
                   ["Auditoría", "Rastrear cambios", "Quién, qué, cuándo; filtros", "Administrador", "`auditoria.py`", "Implementado"],
                   ["Configuración / Respaldos", "Mantener", "Intervalo del lote, tamaño de foto, respaldo `.zip`, restaurar", "Administrador", "`configuracion.py`, `btsync/respaldo.py`", "Implementado"],
                   ["Notificaciones / Perfil", "Avisar y personalizar", "Campana, foto, tema, idioma, contraseña", "Todos los del PC", "`bandeja.py`, `perfil.py`", "Implementado"]],
                  [1700, 1500, 3000, 1500, 3500, 1760], "Elaboración propia a partir del código y del README del proyecto.", tam=17),
        ]),
        H(2, "5.4 Almacenamiento y sistemas externos"),
        P("Cada teléfono guarda sus datos en SQLite (Room): `Outbox`, catálogo y cuentas locales. El computador guarda todo "
          "en Oracle XE 11g, más las fotos de evidencia (`fotos/<uuid>/<seq>.jpg`) y los respaldos `.zip` (`respaldos/`) "
          "en carpetas del proyecto. Los sistemas externos al código del proyecto son BlueZ (`bluetoothd`, que vive en el "
          "anfitrión), el bus D-Bus del sistema, el servidor gráfico X11 o Wayland y Docker."),
    ]

    # ------------------------------------------------------------------ 6
    b += [
        H(1, "6. Análisis de requisitos"),
        H(2, "6.1 Requisitos funcionales"),
        P("Los requisitos se extrajeron del código y de la documentación del proyecto; todos están en estado "
          "**Implementado**. Cuando se indica una prueba, es una prueba automática existente en el repositorio; cuando se "
          "indica una figura, es una captura obtenida durante este trabajo."),
        Horizontal([
            Tabla("t_rf1", "Requisitos funcionales (1 de 2)",
                  ["ID", "Nombre", "Descripción (entrada → proceso → resultado)", "Actor", "Módulo", "Verificación"],
                  [["RF-001", "Registrar cuenta del PC", "Usuario, nombre, correo, contraseña → la primera cuenta queda Administrador activo; las demás, pendientes", "Visitante", "`auth.registrar`", "`test_auth.py`"],
                   ["RF-002", "Iniciar sesión en el PC", "Usuario y contraseña → verifica hash; 5 intentos fallidos bloquean 30 s; audita", "Admin, Inventario", "`auth.iniciar_sesion`", "`test_auth.py`, [[f_acceso]]"],
                   ["RF-003", "Recuperar contraseña del Administrador", "Respuesta a la pregunta de seguridad → nueva contraseña inmediata", "Administrador", "`auth.recuperar`", "`test_auth.py`"],
                   ["RF-004", "Aprobar o rechazar solicitudes", "Cuenta pendiente → rol (PC: Inventario; móvil: Operador) o rechazo con motivo", "Administrador", "`views/solicitudes.py`", "`test_requests_only_allow…`, [[f_solicitudes]]"],
                   ["RF-005", "Gestionar empleados", "Suspender con motivo, reactivar, poner contraseña, desvincular teléfono", "Administrador", "`views/usuarios.py`", "`test_usuarios_views.py`, [[f_empleados]]"],
                   ["RF-006", "Editar matriz de permisos", "12 módulos × 3 niveles por rol; la fila del Administrador es intocable", "Administrador", "`permisos.py`", "`test_roles_view.py`, [[f_roles]]"],
                   ["RF-007", "Auditar cambios", "Cada cambio de datos escribe quién, qué y cuándo en la misma transacción", "Administrador", "`auditoria.py`", "`test_auditoria.py`, [[f_auditoria]]"],
                   ["RF-008", "Cuenta local del operador", "Registro, acceso y recuperación con pregunta de seguridad, en el teléfono", "Operador", "`auth/AuthRepository.kt`", "`AuthRepositoryTest`"],
                   ["RF-009", "Ver catálogo sin stock", "El PC envía productos sin cantidad del sistema → el teléfono los guarda", "Operador", "`Session`, `CatalogoScreen`", "`test_catalog_never_contains_system_stock`"],
                   ["RF-010", "Contar", "SKU por escáner (barras/QR) o digitado, cantidad, dañados, nota, foto → lectura en la Outbox", "Operador", "`CountViewModel`, `ContarScreen`", "`CountViewModelTest`"],
                   ["RF-011", "Recontar reemplaza", "Segunda lectura del mismo SKU sin enviar reemplaza a la pendiente; vale la vigente", "Operador", "`Outbox.reemplazar`", "`OutboxTest`"],
                   ["RF-012", "Guardar sin red", "Toda lectura se guarda primero en Room", "Operador", "`Outbox`", "`OutboxTest`"],
                   ["RF-013", "Sincronizar por Bluetooth", "Búsqueda del PC `gestion_inventario`, conexión RFCOMM, envío por protocolo v5", "Operador", "`SyncClient`", "`SyncClientTest`"],
                   ["RF-014", "Validar y confirmar", "CRC, longitud, formato, secuencia; COMMIT cada 25 y `ACK`; `NAK` con motivo", "Sistema", "`Session`", "`test_session.py`"]],
                  [800, 1500, 4000, 1300, 2000, 3360], "Elaboración propia.", tam=16),
        ]),
        Horizontal([
            Tabla("t_rf2", "Requisitos funcionales (2 de 2)",
                  ["ID", "Nombre", "Descripción (entrada → proceso → resultado)", "Actor", "Módulo", "Verificación"],
                  [["RF-015", "Reanudar y reintentar", "`READY` informa el último `seq`; ante `NAK` el móvil retrocede; 3 reintentos de conexión", "Sistema, Operador", "`Session`, `SyncRunner`", "`test_connection_cut_after_30_rec_keeps_25`, `SyncRunnerTest`"],
                   ["RF-016", "Conciliar por lotes", "Filas pendientes → validación, lectura vigente, `CONCILIACION` de `ACTUAL`", "Scheduler", "`PKG_BATCH`", "`test_batch.py`, `test_conciliacion.py`"],
                   ["RF-017", "Resolver SKU nuevo", "SKU fuera del catálogo → aviso «Nuevo SKU»: crear y procesar, o no crear", "Administrador", "`aviso_nuevo_sku.py`", "`test_nuevo_sku_views.py`, [[f_dash_admin]]"],
                   ["RF-018", "Reprocesar errores", "Lecturas en `ERROR` → nuevo intento tras corregir", "Admin", "`PKG_BATCH.reprocesar_errores`", "`test_sync_views.py`"],
                   ["RF-019", "Dashboard continuo", "Avance, contados, faltantes, sobrantes, diferencia por categoría", "Admin, Inventario", "`views/dashboard.py`", "`test_dashboard_views.py`, [[f_dash_admin]]"],
                   ["RF-020", "Inventario", "Cinco columnas, búsqueda, CSV (`;`, UTF-8 con BOM), detalle con foto", "Admin, Inventario", "`views/inventario.py`", "`test_inventario_views.py`, [[f_inv_admin]]"],
                   ["RF-021", "Gráficas", "Seis gráficas con filtro por categoría y cantidad de SKU", "Inventario", "`views/charts.py`", "`test_charts_views.py`, [[f_graficas]]"],
                   ["RF-022", "Operar el servicio", "Ver estado, pausar y reanudar el servicio Bluetooth; procesar ahora", "Admin, Inventario", "`ServicioRemoto`", "`test_servicio.py`, [[f_sync_admin]]"],
                   ["RF-023", "Notificaciones", "Campana con avisos por rol o usuario; marcar leídas", "Admin, Inventario", "`notificaciones.py`", "`test_notificaciones_views.py`"],
                   ["RF-024", "Perfil", "Foto con editor, tema claro/sistema/oscuro, idioma es/en, contraseña", "Admin, Inventario", "`views/perfil.py`", "`test_perfil.py`, [[f_perfil]]"],
                   ["RF-025", "Configuración", "Intervalo del lote y tamaño máximo de foto; reaplica los jobs", "Administrador", "`configuracion.py`", "`test_configuracion_views.py`"],
                   ["RF-026", "Respaldos", "Crear `.zip`, programar diario, restaurar con confirmación `RESTAURAR`", "Administrador", "`btsync/respaldo.py`", "`test_respaldo.py`, `test_respaldos.py`"],
                   ["RF-027", "Fotos de evidencia", "Foto por lectura en partes `FOTO`, `FOTOOK`/`FOTOERR`", "Operador", "`Session._on_foto`", "`test_fotos.py`"],
                   ["RF-028", "Una sincronización a la vez", "Segundo teléfono recibe `NAK|0|OCUPADO`", "Sistema", "`SyncController`", "`test_e2e_tcp.py`"]],
                  [800, 1500, 4000, 1300, 2000, 3360], "Elaboración propia.", tam=16),
        ]),
        H(2, "6.2 Requisitos no funcionales"),
        Horizontal([
            Tabla("t_rnf", "Requisitos no funcionales, cómo se abordan y evidencia",
                  ["Categoría", "Cómo se aborda técnicamente", "Evidencia", "Estado"],
                  [["Rendimiento", "El móvil envía hasta 50 `REC` sin esperar `ACK`; el servidor hace COMMIT cada 25; las consultas del escritorio salen de vistas `V_*` en un pool de 8 hilos como máximo.", "`Session`, `COMMIT_EVERY = 25`, `MAX_HILOS = 8`. No se midieron tiempos de transferencia: no se afirma ninguna cifra.", "Implementado; sin medición"],
                   ["Seguridad", "Contraseñas con PBKDF2-SHA256, 200 000 iteraciones y sal; bloqueo tras 5 intentos durante 30 s; permisos rol × módulo con revalidación en vivo; auditoría.", "`auth.py`, `permisos.exigir`, `test_auth.py`, `test_permisos.py`", "Implementado. Límite: el enlace Bluetooth por defecto no se cifra (D22)"],
                   ["Confiabilidad", "Clave única `(uuid, seq)`, `ACK` acumulativo, _go-back-N_, `ROLLBACK` si se corta antes del `COMMIT`, `READY` con el último `seq`.", "`test_connection_cut_after_30_rec_keeps_25`, `test_duplicate_rec_in_new_session_is_not_inserted`", "Implementado y probado"],
                   ["Disponibilidad", "El servicio Bluetooth es un proceso aparte con `restart: unless-stopped`; escribe un latido en `SERVICIO_BT`.", "`docker-compose.yml`, `servicio.py`", "Implementado"],
                   ["Mantenibilidad", "Capas (Transport → Session → Store), MVC en escritorio, MVVM en Android, 22 diagramas UML y pruebas que comprueban que las clases UML existen en el código.", "`server/tests/test_uml.py`", "Implementado (una prueba UML falla, ver 14.4)"],
                   ["Escalabilidad", "Una sola sincronización a la vez (D19); Oracle XE 11g tiene límites de procesos y memoria.", "Documentado en `docs/arquitectura.md` §4", "Limitada; no demostrada"],
                   ["Usabilidad / adaptabilidad", "Tema claro/oscuro, idioma es/en, estados vacíos y de error, barra lateral contraíble; ventana mínima 900 × 600.", "Capítulo 12 y capturas reales", "Implementado"],
                   ["Integridad de datos", "Llaves primarias y foráneas, restricciones `CHECK` en estados, roles, temas e idiomas.", "`db/init/01_schema.sql`, `test_schema.py`", "Implementado"],
                   ["Gestión de errores", "`NAK` con motivo, errores en `ERROR` con reproceso, mensajes en la interfaz, reintento ante `ORA-12516`.", "`protocol.py`, `store.connect_oracle`", "Implementado"],
                   ["Concurrencia", "Conexión por hilo, `connect_oracle` serializada con candado, `QThreadPool`, señales Qt.", "`workers.py`, `store.py`", "Implementado"]],
                  [1700, 5000, 4300, 1960], "Elaboración propia.", tam=16),
        ]),
        H(2, "6.3 Casos de uso"),
        P("El [[f_cu]] presenta los actores, los límites del sistema y las relaciones `include` y `extend` verificadas "
          "contra la implementación. El Scheduler de Oracle aparece como actor porque inicia el procesamiento por lotes "
          "sin intervención humana."),
        Fig("f_cu", R + "01_casos_uso.png", "Diagrama de casos de uso.",
            ["Fuente: elaboración propia. PlantUML: diagramas/plantuml/01_casos_uso.puml.",
             "Demuestra: actores, funcionalidades y límites del sistema. Criterio: Funcionalidad y requisitos."]),
        Tabla("t_cu", "Especificación resumida de los casos de uso principales",
              ["Caso", "Precondiciones", "Flujo principal", "Alternativos y excepciones", "Postcondición"],
              [["CU-01 Contar", "Operador con sesión y catálogo descargado", "Escanea o digita SKU → ingresa cantidad, dañados, nota → Guardar", "SKU fuera del catálogo: se guarda y queda pendiente de alta. Cantidad inválida: se rechaza en pantalla. Recontar reemplaza la pendiente.", "Lectura en `Outbox` como PENDIENTE"],
               ["CU-02 Sincronizar", "Lecturas pendientes; servicio activo; cuenta ACTIVO", "Buscar `gestion_inventario` → `HELLO`/`ACCT` → `READY` → `REC` → `END` → `BYE`", "PC ocupado: `NAK|0|OCUPADO`. Corte: reanuda desde `READY`. Cuenta no activa: `NAK CUENTA_NO_ACTIVA` y se conservan las lecturas.", "Lecturas CONFIRMADO; filas en `CAPTURA_TRANSITO`"],
               ["CU-03 Conciliar", "Filas PENDIENTE en tránsito", "`PKG_BATCH.procesar_pendientes` valida, inserta, marca vigente y concilia `ACTUAL`", "Dato inválido: fila `ERROR`. SKU desconocido: `NUEVO_SKU`.", "`CONCILIACION` actualizada"],
               ["CU-04 Aprobar cuenta", "Cuenta PENDIENTE; sesión de Administrador", "Solicitudes → Aprobar con rol permitido por el origen", "Rechazar exige motivo (≤ 300 caracteres).", "Cuenta ACTIVO o RECHAZADO; auditoría"],
               ["CU-05 Resolver SKU nuevo", "Lectura en `NUEVO_SKU`", "Aviso flotante → «Crear y procesar» (nombre, categoría)", "«No crear» confirma y descarta.", "Producto creado y lectura procesada, o descartada"],
               ["CU-06 Respaldar y restaurar", "Administrador", "Respaldos → Crear; o Restaurar escribiendo `RESTAURAR`", "Restaurar pausa el servicio y guarda un respaldo previo; cierra la sesión al terminar.", "Archivo `.zip` o base restaurada"]],
              [1100, 1700, 2600, 2400, 1560], "Elaboración propia a partir de README.md, docs/protocolo.md y el código.", tam=16),
    ]
    return b
