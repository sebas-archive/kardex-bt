"""Capítulos 14 a 19: pruebas, instalación, resultados, rúbrica, conclusiones y trabajo futuro."""
import re
from pathlib import Path

from contenido_b import cod
from docgen import H, P, Lista, Tabla, Fig, Horizontal, Cmd

REG = Path(__file__).resolve().parents[1] / "anexos" / "registros"


def _leer(n: str) -> str:
    return (REG / n).read_text(encoding="utf8", errors="replace")


def totales(log: str) -> tuple[int, int]:
    """(aprobadas, fallidas) tomadas de la línea final de pytest («N failed, M passed in …»)."""
    m = re.search(r"=+ (?:(\d+) failed, )?(\d+) passed", log)
    return int(m.group(2)), int(m.group(1) or 0)


def por_archivo(log: str) -> list[list[str]]:
    d: dict[str, list[int]] = {}
    for m in re.finditer(r"^(\S+?\.py)::\S+\s+(PASSED|FAILED)", log, re.M):
        d.setdefault(m.group(1).split("/")[-1], [0, 0])[0 if m.group(2) == "PASSED" else 1] += 1
    return [[f"`{k}`", str(v[0]), str(v[1]), str(v[0] + v[1]), "Aprobado" if v[1] == 0 else "Con fallos"] for k, v in sorted(d.items())]


def android_por_clase() -> list[list[str]]:
    filas = []
    for l in _leer("pruebas_android.txt").splitlines():
        m = re.match(r"com\.sebasarchive\.kardex\.(\S+)\s+tests=(\d+) fallos=(\d+) errores=(\d+)", l)
        if m:
            ok = m.group(3) == "0" and m.group(4) == "0"
            filas.append([f"`{m.group(1)}`", m.group(2), m.group(3), m.group(4), "Aprobado" if ok else "Con fallos"])
    return filas


def bloques() -> list:
    sl_p, sl_f = totales(_leer("pruebas_servidor_limpia.txt"))
    el_p, el_f = totales(_leer("pruebas_escritorio_limpia.txt"))
    sd_p, sd_f = totales(_leer("pruebas_servidor.txt"))
    ed_p, ed_f = totales(_leer("pruebas_escritorio.txt"))
    b: list = []

    # ------------------------------------------------------------------ 14
    b += [
        H(1, "14. Pruebas y validación"),
        H(2, "14.1 Qué es existente y qué se ejecutó"),
        P("Se distinguen tres tipos de evidencia. **(a) Pruebas existentes en el repositorio:** `server/tests` (pytest, "
          "contra Oracle), `desktop/tests` (pytest-qt, Qt `offscreen`, contra Oracle) y `mobile/app/src/test` (JUnit en la JVM). "
          "**(b) Pruebas ejecutadas durante la elaboración de este documento** el 17 de noviembre de 2026, con los comandos "
          "del capítulo 15 y los scripts de `docs/documentacion/herramientas/`; su salida íntegra está en "
          "`docs/documentacion/anexos/registros/`. **(c) Verificaciones manuales o visuales:** la inspección de las capturas "
          "de la aplicación en ejecución. No se midieron cobertura de código ni tiempos de transferencia, por lo que no se "
          "reporta ninguna cifra de cobertura ni de rendimiento."),
        H(2, "14.2 Resultados de las suites"),
        Tabla("t_suites", "Resultados de las suites ejecutadas (17-nov-2026)",
              ["Suite", "Base de datos", "Aprobadas", "Fallidas", "Total", "Evidencia"],
              [["Servidor (`pytest server/tests`)", "Oracle limpio (sin `08_demo.sql`)", str(sl_p), str(sl_f), str(sl_p + sl_f), "[[f_reg1]]"],
               ["Servidor", "Oracle de trabajo (con datos de demostración)", str(sd_p), str(sd_f), str(sd_p + sd_f), "[[f_reg4]]"],
               ["Escritorio (`pytest desktop/tests`)", "Oracle limpio", str(el_p), str(el_f), str(el_p + el_f), "[[f_reg2]]"],
               ["Escritorio", "Oracle de trabajo (demostración)", str(ed_p), str(ed_f), str(ed_p + ed_f), "[[f_reg5]]"],
               ["APK (`./gradlew testDebugUnitTest --rerun-tasks`)", "No usa Oracle", "115", "0", "115", "[[f_reg3]]"]],
              [2700, 2400, 1000, 900, 800, 1560], "Registros en docs/documentacion/anexos/registros/."),
        P("Se usaron dos bases porque las pruebas fueron escritas para la base **limpia** de la semilla del proyecto; el "
          "Oracle de trabajo contiene los 13 meses de datos de demostración y rompe más aserciones numéricas. Las dos "
          "ejecuciones se comparan en la tabla anterior. **Las suites fueron ejecutadas en serie** porque comparten base "
          "(como exige el propio proyecto) y no se modificó ningún archivo de producto para que pasaran."),
        Fig("f_reg1", "capturas/pruebas/registro_01_servidor_limpia.png", "Resultado de las pruebas del servidor (Oracle limpio).",
            ["Fuente: anexos/registros/pruebas_servidor_limpia.txt (herramientas/pruebas_limpia.sh). 230 aprobadas, 8 fallidas.",
             "Demuestra: ejecución real y fallos conocidos de las pruebas. Criterio: Funcionalidad y Documentación."]),
        Fig("f_reg2", "capturas/pruebas/registro_02_escritorio_limpia.png", "Resultado de las pruebas del escritorio (Oracle limpio).",
            ["Fuente: anexos/registros/pruebas_escritorio_limpia.txt. 454 aprobadas, 10 fallidas.",
             "Demuestra: ejecución real de las pruebas de la interfaz con Qt offscreen. Criterio: UI/UX y Funcionalidad."]),
        Fig("f_reg3", "capturas/pruebas/registro_03_android.png", "Resultado de las pruebas unitarias de la APK.",
            ["Fuente: anexos/registros/pruebas_android.txt (herramientas/pruebas_android.sh). 115 pruebas, 0 fallos.",
             "Demuestra: ejecución real de las pruebas Kotlin en la JVM. Criterio: Funcionalidad y Conectividad."]),
        Fig("f_reg4", "capturas/pruebas/registro_04_servidor_demo.png", "Pruebas del servidor sobre la base con datos de demostración.",
            ["Fuente: anexos/registros/pruebas_servidor.txt.",
             "Demuestra: el efecto de los datos de demostración sobre las aserciones. Criterio: Funcionalidad."]),
        Fig("f_reg5", "capturas/pruebas/registro_05_escritorio_demo.png", "Pruebas del escritorio sobre la base con datos de demostración.",
            ["Fuente: anexos/registros/pruebas_escritorio.txt.",
             "Demuestra: el mismo efecto en las pruebas de la interfaz. Criterio: Funcionalidad."]),
        H(2, "14.3 Casos de prueba representativos"),
        Horizontal([
            Tabla("t_casos", "Casos de prueba representativos y su resultado",
                  ["ID", "Nombre y objetivo", "Precondiciones y datos", "Pasos", "Resultado esperado", "Resultado obtenido", "Estado", "Evidencia"],
                  [["CP-01", "Vectores del protocolo (`test_frame_matches_all_vectors`, `test_parse_matches_all_vectors`): mismo formato en Python y Kotlin", "`docs/protocol-vectors.json`", "`frame` y `parse` de cada vector", "Salida idéntica al vector", "Idéntica en Python; `ProtocolTest` también aprobada", "Aprobado", "[[f_reg1]], [[f_reg3]]"],
                   ["CP-02", "CRC dañado (`test_crc_mismatch_raises_crc`, `test_bad_crc_naks_expected_seq_and_survives`)", "Sesión TCP con Oracle", "Enviar una línea con CRC alterado", "`FrameError(CRC)` / `NAK|n|CRC` y la sesión sigue", "Cumplido", "Aprobado", "[[f_reg1]]"],
                   ["CP-03", "Camino feliz (`test_happy_path_sends_ready_catalog_acks_and_bye`)", "Cuenta ACTIVO", "`HELLO`, `ACCT`, `REC`, `END`", "`READY`, catálogo, `ACK`, `BYE`", "Cumplido", "Aprobado", "[[f_reg1]]"],
                   ["CP-04", "Duplicado en sesión nueva (`test_duplicate_rec_in_new_session_is_not_inserted`)", "Lecturas ya persistidas", "Reenviar el mismo `(uuid, seq)`", "No se inserta fila nueva", "Cumplido", "Aprobado", "[[f_reg1]]"],
                   ["CP-05", "Corte a mitad del lote (`test_connection_cut_after_30_rec_keeps_25`)", "30 `REC` enviados", "Cortar tras 30; reconectar", "Quedan 25 filas; `READY|25`", "Cumplido", "Aprobado", "[[f_reg1]]"],
                   ["CP-06", "Hueco de secuencia (`test_seq_gap_naks_once_and_ignores_followers`)", "—", "Enviar `seq` 1 y 3", "Un solo `NAK|2|SECUENCIA`", "Cumplido", "Aprobado", "[[f_reg1]]"],
                   ["CP-07", "Conteo ciego (`test_catalog_never_contains_system_stock`)", "Producto con stock", "Pedir el catálogo", "Sin cantidad del sistema", "Cumplido", "Aprobado", "[[f_reg1]]"],
                   ["CP-08", "Cuenta pendiente (`test_rec_con_cuenta_pendiente_recibe_nak_cuenta_no_activa`)", "Cuenta PENDIENTE", "Enviar `REC`", "`NAK|seq|CUENTA_NO_ACTIVA`", "Cumplido", "Aprobado", "[[f_reg1]]; [[f_com1]]"],
                   ["CP-09", "Batch PL/SQL (`test_batch.py`)", "Filas en tránsito", "`procesar_pendientes`", "Procesadas, errores y vigentes correctos", "48 de 48 aprobadas", "Aprobado", "[[f_reg1]]"],
                   ["CP-10", "Sincronización real extremo a extremo (sección 9.5)", "Oracle limpio, servicio TCP, cuenta aprobada", "`fake_phone.py` con 126 lecturas", "`BYE|126|0`; filas procesadas; 0 duplicadas", "123 procesadas, 1 `ERROR`, 2 `NUEVO_SKU`, 0 duplicadas", "Aprobado", "[[f_com1]], [[f_com2]]"],
                   ["CP-11", "Corte y reanudación real (sección 9.5)", "Segundo teléfono simulado", "`SIGKILL` a los 4 s; relanzar", "Sin duplicados; reanuda del último `seq`", "50 + 70 = 120 filas, 0 duplicadas", "Aprobado", "[[f_cor1]], [[f_cor2]]"],
                   ["CP-12", "Barras por rol (`test_admin_sidebar_exact_order…`, `test_inventory_sidebar_exact_order`)", "Sesiones de prueba", "Abrir la ventana con cada rol", "Orden y secciones exactas del rol", "Cumplido; ver también capturas", "Aprobado", "[[f_dash_admin]], [[f_roles_barras]]"],
                   ["CP-13", "Aprobación por origen (`test_requests_only_allow_inventory_for_pc_and_operator_for_mobile`), un solo administrador (`test_there_is_never_a_second_admin`)", "Cuentas de prueba (`usuarios_tst`)", "Aprobar con un rol no permitido", "Se rechaza", "Cumplido", "Aprobado", "[[f_reg2]]"],
                   ["CP-14", "Conciliación y semilla (`test_resumen_matches_scenario_exactly`, `test_seed_counts`…)", "Semilla de 60 SKU esperada", "Cargar el escenario y comparar", "65 filas y 6,15 % (valores de la semilla antigua)", "La semilla actual tiene 120 SKU: 125 filas y 3,2 %", "Fallido", "[[f_reg1]]"],
                   ["CP-15", "Dashboard: orden de tarjetas y animación (`test_dashboard_personal.py`)", "Qt offscreen", "Simular hover y desplazamiento", "Cifra visible y barra de desplazamiento activa", "2 de 33 fallan en el entorno offscreen", "Fallido (parcial)", "[[f_reg2]]"],
                   ["CP-16", "Android: sincronización con PC falso (`SyncClientTest`, `SyncRunnerTest`)", "`FakePc` en la JVM", "16 + 9 escenarios", "Reintentos, rechazos y cortes tratados", "25 de 25 aprobadas", "Aprobado", "[[f_reg3]]"]],
                  [600, 2800, 1600, 1500, 1900, 2000, 900, 1660], "Resultados tomados de los registros de ejecución del 17-nov-2026.", tam=15),
        ]),
        H(2, "14.4 Fallos encontrados y su análisis"),
        P("En la base limpia fallan 8 pruebas del servidor y 10 del escritorio. **No se corrigió ningún archivo** para no "
          "alterar el producto evaluado; se clasifican así:"),
        Tabla("t_fallos", "Clasificación de las pruebas fallidas en Oracle limpio",
              ["Causa", "Pruebas", "Análisis"],
              [["Aserciones con cifras de la semilla antigua (60 SKU) mientras la actual crea 120 SKU en 8 categorías", "Servidor: `test_resumen_matches_scenario_exactly`, `test_concurrent_batches_leave_same_conciliation…`, `test_seed_counts`, `test_truth_json_covers_all_seeded_skus`, `test_sesion_envia_un_pseudo_catalogo…`, `test_catalog_is_a_single_pseudo_catalogo`, `test_tcp_transport_real_store_end_to_end`. Escritorio: `test_seis_graficas_y_sus_datos`, `test_kpis_del_conteo_continuo`, `test_fetch_resumen…`, `test_fetch_conciliacion_cinco_columnas`, `test_fetch_series_seis_graficas`", "Deriva entre las pruebas y `02_seed.sql`: los mensajes de error muestran 125 filas frente a 65 esperadas, `'120'` frente a `'60'`. El código evaluado funciona; las pruebas quedaron desactualizadas."],
               ["Diagrama UML 02 con una clase inexistente en el código", "Servidor: `test_class_diagrams_match_code`", "`02-clases-escritorio.puml` declara `Transicion`, que ya no existe en `desktop/app`. Es deriva documental."],
               ["Pruebas de geometría, desplazamiento y animación en el entorno `offscreen`", "Escritorio: `test_una_grafica_se_redimensiona_con_el_asa…`, `test_actividad_reciente_se_desplaza…`, `test_la_cifra_de_una_tarjeta_nunca_queda_invisible…`", "El resultado difiere del esperado (por ejemplo, el alto de una baldosa o el máximo de la barra de desplazamiento). No se diagnosticó si es del entorno sin pantalla o del código."],
               ["Preexistentes y no diagnosticadas", "Escritorio: `test_charts_follow_the_system_scheme_when_it_changes`, `test_tras_restaurar_la_ventana_vuelve_al_login_con_el_aviso`", "La primera ya estaba registrada como fallo preexistente; la segunda no se analizó."]],
              [2500, 3900, 2960], "Mensajes de error en anexos/registros/pruebas_*_limpia.txt.", tam=16),
        P("Con la base de demostración los fallos suben a 11 en el servidor y 15 en el escritorio, porque además cambian las "
          "sumas por categoría y por operador. Los registros completos permiten comprobarlo."),
        H(2, "14.5 Pruebas por categoría"),
        Tabla("t_cat", "Cobertura de categorías de prueba",
              ["Categoría", "Dónde existe", "Estado en esta verificación"],
              [["Unitarias", "`test_protocol.py` (11), `test_store.py`, `test_auth.py` (20), `ClavesTest`, `OutboxTest`, `CountViewModelTest`", "Ejecutadas; aprobadas salvo `test_store.py` (1 de 4, por la semilla)"],
               ["Integración con Oracle", "`test_batch.py` (48), `test_schema.py`, `test_conciliacion.py`, `test_oracle_connect.py`, `test_concurrent_connect.py`", "Ejecutadas; aprobadas salvo las de cifras de la semilla"],
               ["Comunicación", "`test_session.py` (22), `test_bluez.py` (36, con bus D-Bus falso), `test_e2e_tcp.py` (6), `SyncClientTest`", "Ejecutadas; aprobadas salvo 1 de catálogo"],
               ["Funcionales", "`test_respaldo.py` (19), `test_fotos.py` (14), `test_notificaciones.py` (8), `test_servicio.py` (9)", "Ejecutadas; aprobadas"],
               ["Interfaz y navegación", "`test_app.py`, `test_interactividad.py` (11), `test_capas.py`, vistas del escritorio", "Ejecutadas; 10 fallos en total en el escritorio"],
               ["Por rol", "`test_permisos.py` (18), `test_roles_view.py`, `test_app.py` (barras por rol), `test_usuarios_views.py`", "Ejecutadas; aprobadas"],
               ["Rendimiento", "No hay pruebas de rendimiento ni mediciones", "No aplica; no se afirma ninguna cifra"],
               ["Bluetooth físico", "Prueba de campo en `docs/spikes/bluez.md` (documentada por el proyecto)", "No ejecutada: no hay teléfono emparejado en este equipo"]],
              [2200, 4700, 2460], "Conteos tomados de los registros de ejecución."),
    ]

    # ------------------------------------------------------------------ 15
    b += [
        H(1, "15. Instalación, configuración y ejecución"),
        P("Los comandos de este capítulo provienen del `README.md` y del `docker-compose.yml` del proyecto y se ejecutaron "
          "o usaron en la verificación (contenedores `oracle`, `bluetooth`, `app` y las suites de prueba). Las rutas del "
          "proyecto pueden tener espacios (`/home/t1an/movil oracle bluetooth`): deben entrecomillarse."),
        H(2, "15.1 Requisitos"),
        Tabla("t_req", "Requisitos de hardware y software",
              ["Componente", "Requisito", "Observación"],
              [["Anfitrión", "Linux x86_64 con Docker y Docker Compose", "Oracle XE 11g solo existe para x86_64. Verificado: Linux 7.3.3 x86_64, Docker 29.9.3"],
               ["Bluetooth real", "BlueZ (`bluetoothd`) activo en el anfitrión y adaptador `hci0` encendido", "`bluetoothd` y `adb` viven en el anfitrión"],
               ["Pantalla", "Sesión X11 o Wayland con XWayland (`DISPLAY`)", "Sin XWayland: `tools/run_escritorio_wayland.sh`"],
               ["Teléfono", "Android 6.0 o superior (`minSdk 23`) con depuración USB", "Sin iPhone (D4)"],
               ["Oracle", "Oracle Database 11g Express Edition 11.2.0.2 (imagen `gvenzl/oracle-xe:11-slim`)", "Verificado con `v$version`"],
               ["Python", "3.12 (imagen `python:3.12-slim-bookworm`), `oracledb` 26.1.0, PyQt6 6.12.0, pyqtgraph 0.14.0, `dbus-fast` 5.2.0", "Versiones leídas dentro de la imagen de la app"],
               ["Oracle Instant Client", "19.23 Basic Lite (modo thick)", "Obligatorio para Oracle 11g"],
               ["Android", "Kotlin 1.9.24, AGP 8.5.2, Compose BOM 2024.06.00, Room 2.6.1, ZXing 4.3.0, `compileSdk`/`targetSdk` 34", "`mobile/build.gradle.kts`, `mobile/app/build.gradle.kts`"],
               ["Compilación Android", "JDK 17 + Android SDK + Gradle en el contenedor `apk-build`", "Sin instalar nada en el anfitrión"]],
              [1900, 4400, 3060], "README.md, docker/pybase/Dockerfile, build.gradle.kts y entorno.txt.", tam=17),
        H(2, "15.2 Variables de entorno"),
        P("Las variables se definen en el archivo `.env` (copiado de `.env.example`, que contiene valores de desarrollo "
          "local; no se reproducen aquí). El archivo `.env` no se versiona."),
        Tabla("t_env", "Variables de entorno",
              ["Variable", "Uso"],
              [["`ORACLE_PASSWORD`, `APP_USER`, `APP_USER_PASSWORD`", "Creación de la base y del usuario de aplicación en el contenedor Oracle"],
               ["`DB_USER`, `DB_PASSWORD`", "Credenciales con las que los contenedores Python se conectan"],
               ["`PUID`, `PGID`", "UID y GID con los que corren los contenedores Python"],
               ["`DB_DSN`", "Destino de Oracle (en Compose: `127.0.0.1:1521/XE` o `oracle:1521/XE`)"],
               ["`BT_TRANSPORT`, `BT_TCP_PORT`, `BT_CON_CLAVE`", "`bluez` (por defecto) o `tcp`; puerto TCP; emparejamiento con código (`1`)"],
               ["`FOTOS_DIR`, `RESPALDOS_DIR`", "Carpetas de fotos y de respaldos"],
               ["`DISPLAY`, `XAUTHORITY`", "Pantalla del anfitrión para la ventana del escritorio"]],
              [3600, 5760], "docker-compose.yml y .env.example (solo nombres)."),
        H(2, "15.3 Puesta en marcha (orden de inicio)"),
        Cmd(["cp .env.example .env"], "1. Preparar el entorno"),
        Cmd(["docker compose up -d --wait oracle"], "2. Base de datos (la primera vez crea el esquema, la semilla, `PKG_BATCH`, los jobs y las vistas; puede tardar varios minutos)"),
        Cmd(["docker compose up -d bluetooth app"], "3. Servicio Bluetooth y aplicación de escritorio"),
        Cmd(["tools/run_escritorio_wayland.sh"], "3b. Alternativa si la sesión es Wayland sin XWayland"),
        Cmd(["BT_TRANSPORT=tcp docker compose up -d bluetooth app"], "3c. Sin Bluetooth (pruebas y plan B de la demo)"),
        Cmd(["docker compose --profile build run --rm apk-build ./gradlew assembleDebug",
             "adb install -r mobile/app/build/outputs/apk/debug/app-debug.apk"], "4. Compilar e instalar la APK (teléfono conectado por USB)"),
        P("**Cuentas.** Con los datos de demostración existen `admin` (Administrador) e `inventario`, con la contraseña "
          "de demostración que indica el README; `laura.mora` y `sofia.vega` quedan pendientes en Solicitudes. Con una "
          "base sin demostración (borrando `08_demo.sql` antes de crearla) la primera cuenta del PC se convierte en el "
          "Administrador."),
        H(2, "15.4 Verificaciones iniciales"),
        Lista([
            "`docker compose ps` debe mostrar `oracle` como `healthy`, y `bluetooth` y `app` como `Up` (evidencia: [[f_entorno]]).",
            "`docker compose logs -f bluetooth` muestra «servicio Bluetooth en marcha»; `docker compose logs -f app` y `./logs/app.log` registran el arranque de la ventana.",
            "En el escritorio, la pantalla **Sincronización** muestra el estado del servicio; en el teléfono, el PC se anuncia como `gestion_inventario`.",
            "Pruebas: `docker compose run --rm pybase pytest server/tests -v`, `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -v` y `docker compose --profile build run --rm apk-build ./gradlew testDebugUnitTest`.",
        ]),
        Fig("f_entorno", "capturas/pruebas/registro_10_entorno.png", "Estado real de los contenedores y versiones del entorno.",
            ["Fuente: anexos/registros/entorno.txt (herramientas/entorno.sh).",
             "Demuestra: servicios en marcha y versiones de las tecnologías. Criterio: Documentación (instalación)."]),
        H(2, "15.5 Solución de problemas frecuentes"),
        Tabla("t_sol", "Síntomas y acciones (README del proyecto)",
              ["Síntoma", "Qué hacer"],
              [["«Bluetooth no disponible» / `NotReady`", "`rfkill list`; si hay `Soft blocked: yes`, `rfkill unblock bluetooth` y `bluetoothctl power on`; revisar `systemctl status bluetooth`."],
               ["«El servicio Bluetooth no está corriendo»", "`docker compose up -d bluetooth`; mensajes con `docker compose logs -f bluetooth`."],
               ["El celular no encuentra `gestion_inventario`", "El servicio debe estar activo y sin pausa; en Android 10 o anterior, la ubicación del teléfono debe estar encendida para buscar dispositivos."],
               ["«El PC está atendiendo a otro teléfono»", "Esperar: solo se sincroniza un teléfono a la vez (D19)."],
               ["`could not connect to display`", "Comprobar `echo $DISPLAY $XAUTHORITY` en la terminal que lanza `docker compose`; como último recurso, `xhost +local:` (revertir con `xhost -local:`)."],
               ["`ORA-12541`, `ORA-12514` o «connection refused»", "Oracle aún no está listo: `docker compose ps` y `docker compose logs oracle`."],
               ["`ORA-12516`", "Demasiadas conexiones al listener: `docker compose restart oracle` y volver a abrir la app."],
               ["`DPI-1050` u `ORA-28040`", "Cambiar `IC_DIR`, `IC_FILE` e `IC_FOLDER` en `docker/pybase/Dockerfile` al Instant Client 12.2 y reconstruir con `docker compose build pybase`."],
               ["`INSTALL_FAILED_OLDER_SDK`", "El teléfono es anterior a Android 6.0 (`minSdk 23`)."],
               ["Empezar con la base limpia", "`docker compose down`, `docker volume rm inventario-bt_oracle-data` y `docker compose up -d --wait oracle` (**borra todos los datos de Oracle**)."]],
              [3000, 6360], "README.md del proyecto.", tam=17),
    ]

    # ------------------------------------------------------------------ 16
    b += [
        H(1, "16. Resultados y análisis"),
        H(2, "16.1 Relación con los objetivos"),
        Tabla("t_obj", "Objetivos específicos y resultados comprobados",
              ["Objetivo", "Resultado comprobado", "Evidencia"],
              [["APK con catálogo, escáner, cuentas y `Outbox`", "Implementada; 115 pruebas aprobadas; pantallas renderizadas con el código real", "[[f_mov1]]–[[f_mov4]], [[f_reg3]]"],
               ["Protocolo con CRC, `ACK`, reanudación y retroceso", "Implementado y probado en Python y Kotlin con los mismos vectores", "[[c_frame]], [[f_sec6]], [[f_reg1]]"],
               ["Servicio Bluetooth independiente con persistencia idempotente", "Servicio en marcha en Docker; sesiones probadas; sincronización real por TCP sin duplicados. Enlace Bluetooth físico no ejecutado aquí", "[[f_com2]], [[f_cor2]], [[f_entorno]]"],
               ["_Batch_ PL/SQL de conciliación", "`test_batch.py` 48 de 48; ejecución real: 123 procesadas, 1 error, 2 SKU nuevos", "[[c_batch]], [[f_com2]]"],
               ["Escritorio sin bloqueo y con permisos por rol", "Consultas en hilos; dos roles verificados visualmente; matriz y barras probadas", "[[c_runner]], [[f_roles_barras]], [[f_roles]]"],
               ["Validación y documentación", "Este documento: [[N_DIAG]] diagramas PlantUML (10 obligatorios y 6 complementarios), [[N_COD]] capturas de código, [[N_APP]] figuras de la aplicación en ejecución y [[N_REG]] registros de ejecución", "Anexo C"]],
              [3000, 4300, 2060], "Elaboración propia."),
        H(2, "16.2 Funcionalidades comprobadas, limitaciones y problemas"),
        Lista([
            "**Comprobado en ejecución:** acceso, dashboard, inventario, gráficas (rol Inventario), sincronización, solicitudes, empleados, roles y permisos, auditoría, configuración, respaldos (vista vacía), notificaciones y perfil en el escritorio; sincronización de 126 lecturas y reanudación tras un corte por el transporte TCP; batch con conciliación; 115 pruebas de la APK.",
            "**Limitaciones:** no se ejecutó el enlace Bluetooth físico ni un teléfono real; no se probaron la orientación horizontal ni otros tamaños en Android; no se midió rendimiento; no se creó ni restauró un respaldo sobre la base de demostración; una sola sincronización a la vez; sin cifrado por defecto.",
            "**Problemas identificados:** 18 pruebas fallidas en Oracle limpio por deriva de cifras (semilla de 120 SKU), una clase UML inexistente tres pruebas de geometría sin diagnosticar y dos preexistentes (14.4); recorte del módulo Sincronización a 1240 px; solapamiento transitorio del aviso emergente con la cabecera.",
            "**Inconsistencias documentales halladas:** el README describe al Administrador con acceso a «todo», pero el módulo Gráficas solo se registra para el rol Inventario; `docs/verificacion.md` cita 60 productos y 216 + 166 + 110 pruebas, cifras anteriores a la semilla actual (120 SKU, 238 + 464 + 115 pruebas).",
            "**Código residual:** `desktop/app/views/iconos.py` conserva iconos de pantallas retiradas y `web/` es un directorio no rastreado ajeno al sistema (observaciones O3 y O4 de `docs/verificacion.md`).",
        ]),
        H(2, "16.3 Mejoras posibles"),
        P("Las mejoras se priorizan en el capítulo 19; aquí solo se aclara que ninguna de ellas está implementada."),
    ]

    # ------------------------------------------------------------------ 17
    b += [
        H(1, "17. Evaluación según la rúbrica"),
        P("La [[t_rubrica]] presenta una **autoevaluación técnica razonada**. No es la calificación oficial: el nivel "
          "lo asigna el evaluador. Se usa la escala de la rúbrica (Excelente 5,0; Satisfactorio 4,0; En desarrollo 3,0; "
          "Insuficiente 1,0–2,0) con valores intermedios solo cuando la evidencia cumple parte de un nivel superior."),
        Horizontal([
            Tabla("t_rubrica", "Autoevaluación frente a la rúbrica",
                  ["Criterio y peso", "Evidencias disponibles", "Fortalezas verificadas", "Debilidades o limitaciones", "Nivel estimado", "Justificación técnica"],
                  [["1. Funcionalidad y requisitos técnicos (25 %)", "Capítulos 6 y 11; capturas de 13 módulos; 115 pruebas de la APK; sincronización real", "Los 28 requisitos funcionales están implementados; captura, sincronización, batch y consulta funcionan de extremo a extremo en la ejecución real", "18 pruebas fallidas por deriva; sin Bluetooth físico ni teléfono real en esta verificación; sin prueba de rendimiento", "4,2 (entre Satisfactorio y Excelente)", "Cumple casi todos los requisitos con evidencia; los fallos son de pruebas desactualizadas y no de un módulo, pero el enlace físico no se demostró"],
                   ["2. Conectividad y comunicación de datos (25 %)", "Capítulo 9; secuencias; registros 06–09; pruebas de sesión, BlueZ y TCP", "CRC, `ACK`/`NAK`, reanudación, idempotencia y reintentos demostrados con un corte real; 36 pruebas de `BluezTransport`", "Enlace sin cifrado por defecto (D22); transporte físico no ejecutado aquí; sin medición de pérdidas", "4,3", "Maneja reintentos y desconexiones con evidencia; no se afirma «segura» porque el canal por defecto no cifra"],
                   ["3. Arquitectura y código fuente (20 %)", "Capítulos 7 y 8; diagramas 2, 3, 7; 29 capturas de código", "Capas, MVC con trabajadores, MVVM, transporte intercambiable; consultas fuera del hilo de la UI; código documentado con docstrings", "Archivos muy grandes (`sync_ui.py` 2223 líneas, `main.py` 1075); un diagrama UML desactualizado", "4,5", "Estructura clara y concurrencia correcta demostrable; la deriva de pruebas y los archivos extensos impiden el máximo"],
                   ["4. Experiencia de usuario y adaptabilidad (15 %)", "Capítulo 12; capturas a 900, 1240, 1366 y 1920 px; 4 montajes móviles", "Interfaz coherente, tema claro/oscuro, idioma, estados de carga, vacío y error, barra contraíble", "Solapamientos del aviso emergente; recorte de Sincronización a 1240 px; sin orientación horizontal, sin video de animaciones", "4,0", "Funcional, clara y pulida, con adaptación demostrada en el escritorio; la móvil solo en vertical"],
                   ["5. Documentación y presentación (15 %)", "Este documento, README, `docs/`, 16 diagramas PlantUML con fuente, índice de evidencias", "Manual de instalación y de arquitectura, diagramas de flujo y de secuencia, evidencias reproducibles con scripts", "Inconsistencias en la documentación previa (16.2); la exposición oral no se evalúa aquí", "4,5", "Documentación completa y trazable; el máximo depende de la demostración presencial"]],
                  [1700, 2400, 2700, 2500, 1000, 2660], "Elaboración propia. Autoevaluación; no sustituye la calificación del evaluador.", tam=15),
        ]),
        P("**Cálculo ponderado indicativo:** 0,25 × 4,2 + 0,25 × 4,3 + 0,20 × 4,5 + 0,15 × 4,0 + 0,15 × 4,5 = **4,3 / 5,0**. "
          "Se presenta solo como resumen de la autoevaluación: depende de las valoraciones intermedias asignadas arriba, "
          "que son juicios de los autores del documento, no mediciones."),
    ]

    # ------------------------------------------------------------------ 18
    b += [
        H(1, "18. Conclusiones"),
        Lista([
            "**Arquitectura.** El sistema separa captura, recepción, procesamiento y presentación en procesos distintos que solo se acoplan por Oracle y por un protocolo explícito; el código muestra MVC con trabajadores en el escritorio y MVVM en Android, y un transporte intercambiable que permitió probar la comunicación sin Bluetooth.",
            "**Funcionalidad.** Los 28 requisitos funcionales identificados están implementados y los flujos de extremo a extremo (captura, sincronización, conciliación y consulta) se ejecutaron realmente con resultados coherentes.",
            "**Comunicación.** El protocolo con CRC32, `ACK` acumulativo, `NAK` con retroceso y clave `(uuid, seq)` resistió un corte forzado sin pérdidas ni duplicados (50 + 70 filas). La seguridad del canal por defecto es limitada por diseño (D22) y no debe presentarse como confidencial.",
            "**Base de datos.** El modelo de 17 tablas con restricciones, vistas y un paquete PL/SQL mantiene la integridad; la clave única y el _staging_ separan la recepción del procesamiento.",
            "**Interfaz.** La aplicación de escritorio es coherente, se adapta de 900 a 1920 px y tiene estados de carga, vacío y error; quedan defectos menores de solapamiento y la adaptabilidad móvil sin demostrar.",
            "**Calidad y validación.** Se ejecutaron 799 pruebas aprobadas (230 + 454 + 115) en la base limpia; 18 fallan por pruebas desactualizadas y casos de geometría sin diagnosticar, lo que indica que el mantenimiento de las pruebas no siguió el de la semilla.",
            "**Alcance logrado.** El objetivo general se cumple en el ámbito verificado; el enlace Bluetooth físico, la orientación horizontal en Android y la medición de rendimiento quedan fuera de lo demostrado en este documento.",
        ]),
        H(1, "19. Trabajo futuro"),
        Tabla("t_futuro", "Mejoras posibles por prioridad (no implementadas)",
              ["Prioridad", "Mejora", "Motivo"],
              [["Alta", "Actualizar las pruebas con las cifras de la semilla de 120 SKU y corregir el diagrama UML 02", "Explican 12 de los 18 fallos y devolverían confiabilidad a la suite como puerta de calidad"],
               ["Alta", "Ejecutar y documentar la prueba de campo con un teléfono Android real y el adaptador Bluetooth, con captura de pantalla del teléfono", "Cierra la principal brecha de evidencia de conectividad física"],
               ["Alta", "Evaluar el emparejamiento con código o el cifrado de la aplicación como opción por defecto", "El canal por defecto no autentica ni cifra (D22)"],
               ["Media", "Diagnosticar las tres pruebas de geometría y la de restauración", "Descartar defectos reales de interfaz"],
               ["Media", "Grabar secuencias o GIF de transiciones y validar la orientación horizontal y otros tamaños en Android", "Demostrar fluidez y adaptabilidad móvil"],
               ["Media", "Corregir el solapamiento del aviso emergente con la cabecera y el recorte de Sincronización a 1240 px", "Defectos observados en las capturas"],
               ["Media", "Medir tiempos de transferencia y de procesamiento del _batch_ para lotes grandes", "Sustentar el requisito de rendimiento con datos"],
               ["Baja", "Dividir archivos muy extensos (`sync_ui.py`, `main.py`) y retirar el código residual", "Mantenibilidad"],
               ["Baja", "Soporte para varios teléfonos en paralelo", "Hoy hay una sola sincronización a la vez (D19)"]],
              [1100, 5000, 3260], "Elaboración propia."),
    ]
    return b
