"""Capítulos 11 a 13: módulos, experiencia de usuario y seguridad."""
from contenido_b import cod
from docgen import H, P, Lista, Tabla, Fig

C = "capturas/"
ANCHOS = [2100, 7260]


def ficha(id_: str, nombre: str, filas: list[list[str]]) -> Tabla:
    return Tabla(id_, f"Ficha del módulo: {nombre}", ["Atributo", "Detalle"], filas, ANCHOS, tam=17)


def pantalla(fid: str, ruta: str, titulo: str, demuestra: str, **kw) -> Fig:
    return Fig(fid, C + ruta, titulo,
               [f"Fuente: captura de la aplicación real en ejecución (PyQt6 sobre Oracle XE 11g); archivo docs/documentacion/capturas/{ruta}.",
                f"Demuestra: {demuestra}"], **kw)


def bloques() -> list:
    b: list = []
    b += [
        H(1, "11. Descripción de los módulos y funcionalidades"),
        P("Cada módulo se describe con una ficha y, cuando tiene interfaz, con una captura de la aplicación en ejecución. "
          "Las capturas del escritorio se obtuvieron ejecutando la ventana real (`app.main.build_window`) con las cuentas "
          "de demostración del README, en el contenedor de la aplicación con Qt en modo `offscreen`, y guardando el contenido "
          "de la ventana (`QWidget.grab`). Las de la APK son renderizados del código de Compose de la propia aplicación "
          "producidos por la prueba `CapturasTest`; no son fotografías de un teléfono físico. En todos los casos los "
          "datos que se ven son los de demostración del proyecto (`08_demo.sql`)."),
        P("En las capturas del escritorio aparecen dos elementos transitorios reales: un aviso emergente «Servicio "
          "Bluetooth en pausa» (el servicio estaba pausado en la base de demostración) y el aviso flotante «Nuevo SKU» "
          "con dos lecturas de SKU no registrados. No se alteraron datos para ocultarlos."),

        H(2, "11.1 Acceso y creación de cuenta (escritorio)"),
        ficha("t_m1", "Acceso", [
            ["Propósito y usuarios", "Autenticar a Administrador e Inventario y crear cuentas nuevas (quedan pendientes)."],
            ["Funcionalidades", "Usuario y contraseña con mostrar/ocultar, «Recordar usuario», «¿Olvidaste tu contraseña?» (pregunta de seguridad), «Crear cuenta» con indicador de fortaleza y correo obligatorio."],
            ["Entradas → proceso → salidas", "Usuario y contraseña → `auth.iniciar_sesion` verifica PBKDF2, cuenta bloqueos y audita → `Sesion` con rol y permisos, o error genérico, o pantalla Estado de cuenta."],
            ["Código y dependencias", "`views/acceso.py`, `views/estado_cuenta.py`, `auth.py`, `fortaleza.py`; Oracle (`USUARIOS`)."],
            ["Manejo de errores", "«Usuario o contraseña incorrectos.» sin distinguir la causa; bloqueo 30 s tras 5 intentos; el Operador recibe «Los operadores usan la app móvil.»"],
            ["Pruebas", "`test_auth.py`, `test_fortaleza.py`, `test_estado_cuenta.py`, `test_app.py::test_without_session_the_window_shows_only_the_login` (aprobadas en Oracle limpio)."],
            ["Resultado de verificación", "Verificado: captura de la pantalla real ([[f_acceso]]) y pruebas aprobadas."],
        ]),
        pantalla("f_acceso", "aplicacion/acceso/01_acceso.png", "Pantalla de acceso de la aplicación de escritorio.",
                 "la pantalla inicial real, con usuario, contraseña, recordar usuario, recuperación y alta de cuenta. Criterio: UI/UX y Funcionalidad."),
        cod("codigo_18_autenticacion", "`auth.iniciar_sesion`", "la verificación de contraseña, el contador de intentos con bloqueo y la auditoría de cada intento.", fid="c_auth"),

        H(2, "11.2 Dashboard"),
        ficha("t_m2", "Dashboard", [
            ["Propósito y usuarios", "Mostrar el avance del conteo continuo. Administrador e Inventario."],
            ["Funcionalidades", "Tarjetas de avance (%), productos contados, faltantes y sobrantes; gráfica de diferencia por categoría; última sincronización; tarjetas y gráficas personalizables («Personalizar dashboard»)."],
            ["Entradas → proceso → salidas", "Vistas `V_RESUMEN_CONTEO`, `V_ESTADO_BATCH` y consultas por categoría → `QueryRunner` en hilos → tarjetas y gráfica pyqtgraph."],
            ["Código y dependencias", "`views/dashboard.py`, `dashboard_paneles.py`, `dashboard_datos.py`, `rejilla_personal.py`, `db.py`."],
            ["Manejo de errores", "Estado «Cargando…» mientras responde Oracle; banner de error si Oracle falla."],
            ["Pruebas", "`test_dashboard_views.py`, `test_dashboard_personal.py`, `test_dashboard_motion.py`. En Oracle limpio fallan `test_kpis_del_conteo_continuo` (espera 6,2 % del seed de 60 SKU; con 120 SKU da 3,2 %) y dos pruebas de geometría/animación (ver 14.4)."],
            ["Resultado de verificación", "Verificado visualmente ([[f_dash_admin]]); las cifras mostradas (120 SKU, 100 contados, 83,3 %) son coherentes entre sí. Pruebas parcialmente fallidas por causas ajenas a la presentación."],
        ]),
        pantalla("f_dash_admin", "roles/administrador/01_dashboard.png", "Dashboard visto por el Administrador.",
                 "indicadores del conteo continuo, gráfica de diferencia por categoría, aviso emergente del servicio y aviso flotante «Nuevo SKU». Criterio: Funcionalidad y UI/UX."),

        H(2, "11.3 Inventario"),
        ficha("t_m3", "Inventario", [
            ["Propósito y usuarios", "Consultar lo conciliado por SKU. Administrador e Inventario."],
            ["Funcionalidades", "Cinco columnas (SKU, Producto, Categoría, Contada, Sistema); búsqueda por SKU o nombre; «Filtros»; «Exportar CSV» (`;`, UTF-8 con BOM); doble clic abre el detalle de lecturas (cantidad, operador, fecha UTC, vigente, nota y foto). La cantidad contada queda vacía si no hubo lectura."],
            ["Entradas → proceso → salidas", "Texto de búsqueda → `fetch_conciliacion` (hasta 1000 filas) en un hilo → tabla; `fetch_lecturas(sku)` para el detalle."],
            ["Código y dependencias", "`views/inventario.py`, `lecturas.py`, `visor_foto.py`, `db.py`."],
            ["Manejo de errores", "Mensaje de Oracle en el banner; estado vacío si no hay filas."],
            ["Pruebas", "`test_inventario_views.py` (aprobadas), `test_visor_foto.py` (aprobadas)."],
            ["Resultado de verificación", "Verificado visualmente ([[f_inv_admin]]): 120 SKU, 100 contados, 20 sin contar, como indica el pie de la tabla."],
        ]),
        pantalla("f_inv_admin", "roles/administrador/02_inventario.png", "Módulo Inventario con datos.",
                 "tabla de cinco columnas con búsqueda, filtros y exportación; pie con totales. Criterio: Funcionalidad."),

        H(2, "11.4 Gráficas"),
        ficha("t_m4", "Gráficas", [
            ["Propósito y usuarios", "Análisis visual. Solo el rol Inventario (en el código la sección se registra con `roles=(auth.INVENTARIO,)`; el Administrador no la ve)."],
            ["Funcionalidades", "Seis gráficas con filtro por categoría y cantidad de categorías; entre ellas «Avance por categoría», «SKUs contados vs. pendientes», «Lecturas por hora (UTC)» y «Top categorías por lecturas»; «Personalizar gráficas» y «Guardar PNG»; clic en una categoría filtra el inventario."],
            ["Entradas → proceso → salidas", "Filtros → `fetch_series` en hilo → gráficas pyqtgraph con movimiento."],
            ["Código y dependencias", "`views/charts.py`, `graficas_interactivas.py`, `graficas_motion.py`, `grafico_personal.py`, pyqtgraph 0.14."],
            ["Pruebas", "`test_charts_views.py`: en Oracle limpio fallan 2 de sus pruebas (una por cifras del seed de 60 SKU y otra de geometría)."],
            ["Resultado de verificación", "Verificado visualmente ([[f_graficas]]) con el usuario de rol Inventario."],
        ]),
        pantalla("f_graficas", "roles/inventario/03_graficas.png", "Módulo Gráficas (rol Inventario).",
                 "gráficas de avance por categoría, SKUs contados vs. pendientes y lecturas; filtros y exportación. Criterio: UI/UX y Funcionalidad."),

        H(2, "11.5 Sincronización (escritorio)"),
        ficha("t_m5", "Sincronización", [
            ["Propósito y usuarios", "Operar el servicio Bluetooth. Administrador e Inventario (el alta de SKU, solo el Administrador)."],
            ["Funcionalidades", "Estado del servicio (activo, en pausa), pausar y reanudar, indicadores de lecturas recibidas, pendientes y con error, flujo Android → Bluetooth → PC servidor → Oracle, aceptar o rechazar código, procesar ahora, reprocesar errores y errores con filtro por motivo."],
            ["Entradas → proceso → salidas", "Acciones del usuario → `ServicioRemoto` escribe la orden en `SERVICIO_BT`; el servicio responde en el siguiente `tick`; la vista se actualiza por señales."],
            ["Código y dependencias", "`views/sync.py`, `sync_ui.py`, `sync_datos.py`, `bluetooth_vivo.py`, `servicio_remoto.py`."],
            ["Manejo de errores", "Mensajes «El servicio Bluetooth no está corriendo» y «Bluetooth no disponible»; errores de lecturas en tabla propia."],
            ["Pruebas", "`test_sync_views.py`, `test_sync_centro.py`, `test_servicio.py` (aprobadas)."],
            ["Resultado de verificación", "Verificado visualmente: [[f_sync_admin]] (1240 × 800) y [[f_sync1920]] (1920 × 1080). En 1240 px de ancho la columna derecha de indicadores queda recortada por el borde de la ventana; a 1920 px se ve completa."],
        ]),
        pantalla("f_sync_admin", "roles/administrador/08_sincronizacion.png", "Módulo Sincronización con el servicio en pausa.",
                 "estado del servicio, botón «Reanudar servicio» e indicadores de flujo de datos. Criterio: Conectividad y UI/UX."),
        pantalla("f_sync1920", "aplicacion/resoluciones/sincronizacion_1920x1080.png", "Sincronización a 1920 × 1080.",
                 "el mismo módulo con espacio suficiente para todos los indicadores. Criterio: UI/UX y adaptabilidad."),

        H(2, "11.6 Solicitudes, Empleados y Roles y permisos"),
        ficha("t_m6", "Solicitudes", [
            ["Propósito y usuarios", "Aprobar o rechazar cuentas nuevas y solicitudes de contraseña. Administrador."],
            ["Funcionalidades", "Cuentas nuevas (PC o celular) con rol seleccionable según el origen; contraseñas por aprobar; historial de resoluciones."],
            ["Reglas", "Una cuenta del PC solo puede aprobarse como Inventario; una del celular, como Operador; rechazar exige motivo (≤ 300 caracteres)."],
            ["Código y pruebas", "`views/solicitudes.py`, `auth.aprobar/rechazar/resolver_clave`; `test_requests_only_allow_inventory_for_pc_and_operator_for_mobile` y `test_auth.py` (aprobadas)."],
            ["Resultado de verificación", "Verificado visualmente ([[f_solicitudes]]): dos cuentas pendientes (PC y celular) y el historial."],
        ]),
        pantalla("f_solicitudes", "roles/administrador/03_solicitudes.png", "Módulo Solicitudes.",
                 "cuentas pendientes con su origen, contraseñas por aprobar e historial. Criterio: Funcionalidad y Seguridad."),
        ficha("t_m7", "Empleados", [
            ["Propósito y usuarios", "Administrar cuentas existentes. Administrador."],
            ["Funcionalidades", "Tabla con avatar, correo, nombre, rol e insignia de estado; filtros por rol, estado y texto; suspender con motivo, reactivar, poner contraseña nueva (solo cuentas del PC) y desvincular teléfono. La fila del Administrador deshabilita rol y estado."],
            ["Código y pruebas", "`views/usuarios.py`; `test_usuarios_views.py` (incluye `test_movil_se_suspende_con_motivo_y_se_reactiva` y `test_administrador_no_se_puede_suspender`, aprobadas)."],
            ["Resultado de verificación", "Verificado visualmente ([[f_empleados]]): siete cuentas activas, con rol y estado."],
        ]),
        pantalla("f_empleados", "roles/administrador/04_empleados.png", "Módulo Empleados.",
                 "cuentas con rol y estado, filtros y acciones de administración. Criterio: Funcionalidad y Seguridad."),
        ficha("t_m8", "Roles y permisos", [
            ["Propósito y usuarios", "Definir qué ve y gestiona cada rol. Administrador."],
            ["Funcionalidades", "Matriz de 12 módulos por tres roles con niveles Sin acceso, Consulta y Gestión; la fila del Administrador está bloqueada; el guardado es inmediato y si falla se relee."],
            ["Código y pruebas", "`views/roles.py`, `permisos.py`; `test_roles_view.py`, `test_permisos.py` (aprobadas)."],
            ["Resultado de verificación", "Verificado visualmente ([[f_roles]]) y comparando con la barra lateral de cada rol (sección 13.2)."],
        ]),
        pantalla("f_roles", "roles/administrador/05_roles_y_permisos.png", "Módulo Roles y permisos.",
                 "la matriz rol × módulo con la columna del Administrador deshabilitada. Criterio: Seguridad."),

        H(2, "11.7 Auditoría, Configuración y Respaldos"),
        ficha("t_m9", "Auditoría", [
            ["Propósito y usuarios", "Rastro de quién hizo qué y cuándo. Administrador."],
            ["Funcionalidades", "Tabla de solo lectura con filtros por texto, usuario, módulo y rango de fechas; registra inicios de sesión (incluidos los fallidos), aprobaciones y cambios."],
            ["Código y pruebas", "`auditoria.py`, `views/auditoria.py`; `test_auditoria.py`, `test_auditoria_views.py`, `test_selector_fecha.py` (aprobadas)."],
            ["Resultado de verificación", "Verificado visualmente ([[f_auditoria]]); incluye los inicios de sesión generados por la captura de este documento y un intento fallido con «usuario inexistente»."],
        ]),
        pantalla("f_auditoria", "roles/administrador/06_auditoria.png", "Módulo Auditoría.",
                 "registro de accesos y acciones con filtros. Criterio: Seguridad."),
        ficha("t_m10", "Configuración", [
            ["Propósito y usuarios", "Ajustar el intervalo del lote y el tamaño máximo de foto. Administrador."],
            ["Funcionalidades", "Intervalo de procesamiento en minutos y tamaño máximo en MB; la carpeta de fotos se muestra y no se edita (se define con `FOTOS_DIR`); al guardar se reaplican los jobs de Oracle; el cambio queda auditado."],
            ["Código y pruebas", "`configuracion.py`, `views/configuracion.py`; `test_configuracion.py`, `test_configuracion_views.py` (aprobadas)."],
            ["Resultado de verificación", "Verificado visualmente ([[f_config]])."],
        ]),
        pantalla("f_config", "roles/administrador/07_configuracion.png", "Módulo Configuración.",
                 "parámetros editables y la carpeta de fotos de solo lectura. Criterio: Funcionalidad."),
        ficha("t_m11", "Respaldos", [
            ["Propósito y usuarios", "Copias de seguridad y restauración. Administrador."],
            ["Funcionalidades", "Crear respaldo `.zip` (manifiesto, una tabla por `.jsonl` y fotos); respaldo automático diario (hora y cantidad a conservar); restaurar escribiendo `RESTAURAR`, con pausa del servicio y respaldo previo."],
            ["Código y pruebas", "`btsync/respaldo.py`, `views/respaldos.py`; `test_respaldo.py`, `test_respaldos.py` (aprobadas) y `test_respaldos_views.py` (una prueba falla en Oracle limpio: `test_tras_restaurar_la_ventana_vuelve_al_login_con_el_aviso`, no diagnosticada)."],
            ["Resultado de verificación", "Verificado visualmente ([[f_resp]]): estado vacío «Aún no hay respaldos»; no se creó ni restauró ningún respaldo sobre la base de demostración para no alterarla."],
        ]),
        pantalla("f_resp", "roles/administrador/09_respaldos.png", "Módulo Respaldos (estado vacío).",
                 "creación manual, tabla vacía y programación del respaldo automático. Criterio: Funcionalidad y UI/UX (estado vacío)."),

        H(2, "11.8 Notificaciones y Perfil"),
        ficha("t_m12", "Notificaciones y Perfil", [
            ["Propósito y usuarios", "Avisar eventos y personalizar la cuenta. Administrador e Inventario."],
            ["Funcionalidades", "Campana con contador y hoja flotante: filtro Todas / Sin leer, «Marcar todas como leídas», «Ver» lleva al módulo. Perfil: foto con editor (rotar, zoom, recortar), tema claro/sistema/oscuro, idioma español/inglés, cambio de contraseña (el Administrador, directo; Inventario, pendiente de aprobación) y cerrar sesión."],
            ["Código y pruebas", "`views/bandeja.py`, `notificaciones.py`, `views/perfil.py`, `views/foto.py`; `test_notificaciones*.py`, `test_perfil*.py`, `test_idioma.py`, `test_tema_sistema.py`."],
            ["Resultado de verificación", "Verificado visualmente ([[f_notif]] y [[f_perfil]])."],
        ]),
        pantalla("f_notif", "aplicacion/navegacion/notificaciones_hoja.png", "Hoja flotante de notificaciones.",
                 "avisos con indicador de no leídos y acción «Ver». Criterio: UI/UX."),
        pantalla("f_perfil", "roles/administrador/20_perfil.png", "Módulo Perfil.",
                 "datos de la cuenta, seguridad, tema e idioma. Criterio: UI/UX y Seguridad."),

        H(2, "11.9 Captura móvil (APK Android)"),
        ficha("t_m13", "Cuentas, catálogo, captura y pendientes (móvil)", [
            ["Propósito y usuarios", "Contar sin red. Operador de Inventario."],
            ["Funcionalidades", "Acceso, creación de cuenta con pregunta de seguridad y recuperación; inicio con contador de lecturas por enviar; Catálogo con búsqueda; Contar con escáner de barras o QR o digitación, cantidad con +/−, dañados, foto de evidencia (cámara o galería) y nota; aviso «SKU fuera del catálogo»; Contado y Pendientes con estados Pendiente, Enviada y Confirmada; Notificaciones; Mi cuenta con tema e idioma."],
            ["Entradas → proceso → salidas", "SKU, cantidad, dañados, nota, foto → `CountViewModel.guardar` valida y escribe en la `Outbox` (Room) → lectura PENDIENTE y contador de pendientes."],
            ["Código y dependencias", "`ui/pantallas/*.kt`, `ui/CountViewModel.kt`, `data/Lectura.kt`, `auth/AuthRepository.kt`; Room 2.6.1, ZXing 4.3.0, Compose BOM 2024.06."],
            ["Manejo de errores", "Mensajes bajo cada campo, «Usuario o contraseña incorrectos», estado vacío «No hay productos en el catálogo»."],
            ["Pruebas", "`CountViewModelTest` (15), `OutboxTest`, `AuthRepositoryTest` (12), `CodigoEscaneadoTest`, `CompresorTest` y `CapturasTest` (29): 115 pruebas de la APK, todas aprobadas en la ejecución de este trabajo."],
            ["Resultado de verificación", "Verificado con renderizados de la propia app ([[f_mov1]], [[f_mov2]] y [[f_mov4]]); no se probó en un teléfono físico (no hay uno conectado)."],
        ]),
        Fig("f_mov1", C + "movil/movil_montaje_1_acceso.png", "Pantallas de acceso y cuenta de la APK.",
            ["Fuente: renderizados de CapturasTest (mobile/app/src/test/.../ui/CapturasTest.kt) a 1080 × 2340 px; originales en capturas/movil/originales/. No son fotografías de un teléfono físico.",
             "Demuestra: acceso, alta de cuenta con pregunta de seguridad, recuperación, error de acceso, bienvenida y cuenta pendiente. Criterio: UI/UX."], max_h=11300),
        Fig("f_mov2", C + "movil/movil_montaje_2_captura.png", "Pantallas de captura de la APK.",
            ["Fuente: renderizados de CapturasTest (originales en capturas/movil/originales/).",
             "Demuestra: inicio, catálogo, contar con escáner o digitación, SKU fuera del catálogo, contado y pendientes. Criterio: Funcionalidad y UI/UX."], max_h=11300),
        H(2, "11.10 Sincronización móvil"),
        ficha("t_m14", "Sincronización (móvil)", [
            ["Propósito y usuarios", "Subir lo contado al PC. Operador."],
            ["Funcionalidades", "Búsqueda de `gestion_inventario`, selección del PC (se recuerda), conexión sin claves ni códigos, envío con progreso (porcentaje y lecturas confirmadas), resultado, PC ocupado, sin conexión y reintentos (3)."],
            ["Código y dependencias", "`sync/SyncClient.kt`, `ui/SyncRunner.kt`, `ui/SincronizarActivity.kt`, `sync/PcConnector.kt`, `protocol/Protocol.kt`."],
            ["Pruebas", "`SyncClientTest` (16, con un PC falso `FakePc`), `SyncRunnerTest` (9), `ProtocolTest` (6): aprobadas."],
            ["Resultado de verificación", "Estados verificados con renderizados ([[f_mov3]]); el protocolo, con la ejecución de la sección 9.5. El enlace Bluetooth físico no se ejecutó en esta verificación."],
        ]),
        Fig("f_mov3", C + "movil/movil_montaje_3_sincronizacion.png", "Estados de la sincronización en la APK.",
            ["Fuente: renderizados de CapturasTest (originales en capturas/movil/originales/).",
             "Demuestra: buscar, conectar, enviar, listo, PC ocupado y sin conexión. Criterio: Conectividad y UI/UX (estados de carga y error)."], max_h=11300),
        Fig("f_mov4", C + "movil/movil_montaje_4_apariencia.png", "Notificaciones, cuenta, editor de foto y tema oscuro en la APK.",
            ["Fuente: renderizados de CapturasTest (originales en capturas/movil/originales/).",
             "Demuestra: avisos, perfil con preferencias, editor de foto y el tema oscuro. Criterio: UI/UX."], max_h=11300),
        H(2, "11.11 Servicio Bluetooth y batch de Oracle"),
        P("Estos dos módulos no tienen interfaz propia; su evidencia es la ejecución real descrita en la sección 9.5 y las "
          "pruebas del capítulo 14. El **servicio Bluetooth** (`btsync.servicio`) es el proceso que mantiene el perfil "
          "RFCOMM, crea una `Session` por teléfono, escribe su estado y latido en `SERVICIO_BT` y ejecuta el respaldo "
          "automático. El **batch** (`PKG_BATCH`) valida cada fila, calcula la lectura vigente y concilia `ACTUAL`; en la "
          "ejecución real procesó 123 lecturas con 1 error, sin duplicados."),
    ]

    # ------------------------------------------------------------------ 12
    b += [
        H(1, "12. Experiencia de usuario e interfaz gráfica"),
        P("El análisis se hizo con la aplicación ejecutándose. Se distingue lo observado en las capturas de lo que el "
          "código declara, y se señalan también los defectos encontrados."),
        H(2, "12.1 Diseño, jerarquía visual y navegación"),
        Lista([
            "**Estructura:** barra lateral izquierda con iconos y texto, cabecera con título, estado de Oracle y de Bluetooth y botón «Actualizar», y contenido en tarjetas. El pie de la barra muestra avatar, nombre, rol, tema y cerrar sesión; la campana está junto al título de la barra.",
            "**Identidad visual:** verde esmeralda (`#10B981` y tonos) como color de acción, fondo gris claro y tarjetas blancas; rojo y ámbar para faltantes y sobrantes. La tipografía es la sans-serif por defecto del sistema (en el contenedor donde se tomaron las capturas, DejaVu Sans): el proyecto no incorpora una fuente propia.",
            "**Iconografía:** iconos de trazo para cada módulo (`views/iconos.py`).",
            "**Consistencia:** mismas cabeceras, tablas con encabezado fijo, botones primarios verdes y secundarios con borde en todas las pantallas.",
            "**Navegación por teclado:** atajos para ir a un módulo por número y para enfocar el buscador (`MainWindow._instalar_atajos`).",
        ]),
        H(2, "12.2 Estados de carga, vacío y error"),
        Lista([
            "**Carga:** las tarjetas muestran «—» y «Cargando…» mientras Oracle responde ([[f_carga]]).",
            "**Vacío:** Respaldos muestra «Aún no hay respaldos» y la tabla «Sin datos» ([[f_resp]]); Solicitudes, «Sin datos» en la tabla de contraseñas ([[f_solicitudes]]); el catálogo móvil, «No hay productos en el catálogo» ([[f_mov2]]).",
            "**Error:** la APK muestra «PC ocupado» y «No se pudo conectar» con iconos y texto ([[f_mov3]]); el acceso muestra el mensaje de credenciales incorrectas ([[f_mov1]]); el escritorio muestra un aviso cuando el servicio está en pausa.",
            "**Confirmaciones y avisos:** avisos emergentes («Servicio Bluetooth en pausa»), confirmación al descartar un SKU nuevo y escritura de `RESTAURAR` para restaurar.",
        ]),
        pantalla("f_carga", "aplicacion/pantalla_principal/dashboard_estado_de_carga.png", "Dashboard en estado de carga.",
                 "el estado «Cargando…» con tarjetas provisionales mientras llegan los datos. Criterio: UI/UX (estados de carga)."),
        H(2, "12.3 Adaptabilidad a distintas resoluciones"),
        P("La ventana tiene un mínimo de 900 × 600 (`setMinimumSize`) y se probó a 900 × 600, 1240 × 800, 1366 × 768 "
          "y 1920 × 1080. A 900 px la barra lateral se contrae automáticamente a solo iconos ([[f_res900]]); "
          "también se puede contraer a mano ([[f_lateral]]). A 1920 × 1080 el contenido aprovecha el ancho disponible y muestra más filas "
          "([[f_res1920]])."),
        pantalla("f_res900", "aplicacion/resoluciones/dashboard_900x600.png", "Dashboard a 900 × 600 (mínimo).",
                 "contracción automática de la barra lateral y reacomodo de las tarjetas. Criterio: UI/UX y adaptabilidad."),
        pantalla("f_lateral", "aplicacion/navegacion/lateral_contraida.png", "Barra lateral contraída a 1240 × 800.",
                 "el modo de solo iconos que libera espacio horizontal. Criterio: UI/UX y adaptabilidad."),
        pantalla("f_res1920", "aplicacion/resoluciones/inventario_1920x1080.png", "Inventario a 1920 × 1080.",
                 "la tabla ocupando el ancho disponible con más filas visibles. Criterio: UI/UX y adaptabilidad."),
        pantalla("f_sync1366", "aplicacion/resoluciones/sincronizacion_1366x768.png", "Sincronización a 1366 × 768.",
                 "comportamiento del módulo más ancho en una pantalla de portátil común. Criterio: UI/UX y adaptabilidad."),
        P("La APK usa Jetpack Compose con Material 3; los renderizados se hicieron a 1080 × 2340 en vertical. **No se "
          "evaluó la orientación horizontal ni otros tamaños de teléfono o tableta**, por lo que la adaptabilidad "
          "móvil queda sin demostrar."),
        H(2, "12.4 Experiencia por rol"),
        P("La barra lateral muestra solo los módulos del rol: el Administrador ve nueve módulos más Perfil al pie y el rol "
          "Inventario cuatro más Perfil ([[f_roles_barras]]). El Operador no usa el escritorio. Las capturas de la sección 13.2 "
          "comparan ambas experiencias."),
        H(2, "12.5 Animaciones y movimiento"),
        P("El proyecto implementa transiciones de página, entradas escalonadas de tarjetas, gráficas con movimiento y "
          "arrastre de tarjetas en el Dashboard (`motion_global.py`, `graficas_motion.py`, `rejilla_personal.py`), "
          "controladas por la variable `APP_SIN_ANIMACIONES`. Las capturas se tomaron con las animaciones desactivadas "
          "para obtener el estado final; **no se grabó video ni GIF** de estas transiciones, de modo que su fluidez "
          "no se demuestra visualmente en este documento; solo existen pruebas automáticas "
          "(`test_dashboard_motion.py`, `test_motion_admin.py`, `test_sync_motion.py`)."),
        H(2, "12.6 Defectos y limitaciones observados"),
        Lista([
            "A 1240 × 800 el aviso emergente superior solapa el título y los chips de estado de la cabecera (se aprecia en las capturas de este documento); es transitorio.",
            "A 1240 × 800 el módulo Sincronización queda recortado a la derecha ([[f_sync_admin]]); a 1366 px y 1920 px se ve completo.",
            "El aviso flotante «Nuevo SKU» se superpone al contenido por diseño y tapa filas de la parte inferior derecha.",
            "La tipografía depende de la fuente del sistema; no hay fuente embebida.",
        ]),
    ]

    # ------------------------------------------------------------------ 13
    b += [
        H(1, "13. Seguridad y control de acceso"),
        H(2, "13.1 Medidas verificables"),
        Tabla("t_seg", "Medidas de seguridad implementadas y su evidencia",
              ["Medida", "Implementación", "Evidencia"],
              [["Autenticación (PC)", "Usuario y contraseña; contraseña guardada como `pbkdf2-sha256$200000$sal$hash` (`hashlib.pbkdf2_hmac`, sal de 16 bytes aleatorios); mensaje único ante error", "`auth.crear_hash`, `auth.iniciar_sesion` ([[c_auth]])"],
               ["Protección contra fuerza bruta", "5 intentos fallidos bloquean la cuenta 30 s; cada intento se audita", "`MAX_INTENTOS, BLOQUEO_S = 5, 30`; `test_auth.py`"],
               ["Autenticación (móvil)", "Cuenta local con PBKDF2-SHA256 y sal; recuperación con pregunta de seguridad; la contraseña nunca viaja al PC", "`auth/Claves.kt`, `AuthRepositoryTest`, docs/protocolo.md"],
               ["Autorización por rol", "Matriz `PERMISOS` rol × módulo × nivel; la barra lateral oculta lo que el rol no puede ver; `permisos.exigir` revalida en vivo antes de cambiar datos", "`permisos.py`, `test_permisos.py`, `test_roles_view.py`"],
               ["Cuentas con aprobación", "Toda cuenta nueva queda PENDIENTE; un solo Administrador; roles limitados por origen (PC → Inventario, móvil → Operador)", "`auth.ROLES_POR_ORIGEN`, `test_there_is_never_a_second_admin`"],
               ["Control de lecturas entrantes", "Solo una cuenta ACTIVO entrega lecturas; la cuenta queda vinculada al UUID del teléfono; un rol sin permiso `sync` es suspendido", "`Session`, `test_otro_telefono_con_el_mismo_usuario_no_entrega_lecturas`"],
               ["Conteo ciego", "El catálogo enviado al teléfono nunca incluye el stock del sistema", "`test_catalog_never_contains_system_stock`"],
               ["Validación de entradas", "Formato y CRC de cada línea, regex de cantidades y de usuario, longitudes máximas, tamaño y formato de fotos (JPEG, PNG, WebP; 2 MB)", "`protocol.py`, `session.py`, `test_fotos.py`"],
               ["Consultas parametrizadas", "Las consultas del escritorio usan variables de enlace (`:u`, `:c`, `:n`)", "`auth.py`, `db.py`"],
               ["Auditoría", "Quién, qué y cuándo en la misma transacción que el cambio", "`auditoria.py`, [[f_auditoria]]"],
               ["Secretos", "Credenciales en `.env` (no versionado); `.env.example` solo trae valores de desarrollo local", ".gitignore, README.md"]],
              [2200, 4300, 2860], "Elaboración propia a partir del código.", tam=16),
        cod("codigo_19_hash", "`auth.crear_hash`", "el derivado PBKDF2-HMAC-SHA256 con sal aleatoria de 16 bytes y 200 000 iteraciones.", fid="c_hash"),
        cod("codigo_20_permisos", "`_MATRIZ_INICIAL`, `INTOCABLES`, `alcanza`", "la matriz de 12 módulos y los niveles de acceso, con la fila del Administrador intocable.", fid="c_perm"),
        cod("codigo_21_exigir", "`permisos.exigir`", "la revalidación en vivo del nivel del rol antes de ejecutar una acción que cambia datos.", fid="c_exigir"),
        H(2, "13.2 Acceso según el rol"),
        P("La [[t_roles_pantallas]] compara lo que ve cada rol en el escritorio, comprobado con las capturas y con el "
          "resultado de `MainWindow.secciones()` impreso durante la captura. El Administrador ve nueve secciones más Perfil; el rol "
          "Inventario, cuatro más Perfil. El Operador no puede iniciar sesión en el escritorio: recibe «Los operadores usan la app móvil»."),
        Tabla("t_roles_pantallas", "Secciones visibles por rol (resultado de la ejecución)",
              ["Rol", "Secciones de la barra lateral", "Perfil"],
              [["Administrador (`admin`)", "Dashboard, Inventario, Solicitudes, Empleados, Roles y permisos, Auditoría, Configuración, Sincronización, Respaldos (+ campana de Notificaciones)", "Pie de la barra"],
               ["Inventario (`inventario`)", "Dashboard, Inventario, Gráficas, Sincronización (+ campana de Notificaciones)", "Pie de la barra"],
               ["Operador de Inventario", "No entra al escritorio; usa la app móvil (catálogo, contar, contado, pendientes, sincronizar, notificaciones, mi cuenta)", "Mi cuenta (móvil)"]],
              [2400, 5600, 1360], "Salida de capturar_pantallas.py: «admin ADMIN […]» e «inventario INVENTARIO […]»."),
        Fig("f_roles_barras", C + "roles/inventario/01_dashboard.png", "Experiencia del rol Inventario (cuatro secciones más Perfil).",
            ["Fuente: captura de la aplicación real con la cuenta `inventario` (docs/documentacion/capturas/roles/inventario/01_dashboard.png).",
             "Demuestra: la barra lateral restringida del rol Inventario frente a la del Administrador ([[f_dash_admin]]). Criterio: Seguridad y UI/UX."]),
        P("**Restricciones comprobadas:** el rol Inventario no tiene Solicitudes, Empleados, Roles y permisos, Auditoría, "
          "Configuración ni Respaldos en su barra, y no puede cambiar la matriz; el Administrador no ve el módulo "
          "Gráficas. La prueba de que un módulo sin permiso no se abre es `ir_a` (que ignora títulos fuera de `secciones()`) "
          "y `test_app.py::test_admin_sidebar_exact_order_and_profile_at_the_footer` junto con `test_inventory_sidebar_exact_order`."),
        H(2, "13.3 Límites de seguridad"),
        Lista([
            "El enlace Bluetooth por defecto no se cifra ni se empareja (D22); el modo con código (`BT_CON_CLAVE=1`) existe pero no se ejecutó aquí.",
            "La recuperación de contraseña por pregunta de seguridad es débil: quien conozca la respuesta entra (D23, D25).",
            "Desinstalar la APK borra la `Outbox` y las cuentas locales (D18).",
            "No se realizó una auditoría de seguridad ni pruebas de penetración; solo se documentan las medidas verificables.",
        ]),
    ]
    return b
