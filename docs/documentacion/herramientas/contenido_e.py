"""Referencias y anexos (incluye el índice de evidencias y la matriz de trazabilidad con la rúbrica)."""
import re

from contenido_d import android_por_clase, por_archivo, _leer
from docgen import H, P, Lista, Tabla, Fig, Horizontal, Cmd

R = "diagramas/renderizados/"

REFERENCIAS = [
    "Android Open Source Project. (s. f.). _Bluetooth overview_. Android Developers. https://developer.android.com/develop/connectivity/bluetooth",
    "Android Open Source Project. (s. f.). _Jetpack Compose_. Android Developers. https://developer.android.com/jetpack/compose",
    "Android Open Source Project. (s. f.). _Save data in a local database using Room_. Android Developers. https://developer.android.com/training/data-storage/room",
    "BlueZ Project. (s. f.). _BlueZ: Official Linux Bluetooth protocol stack_. https://www.bluez.org/",
    "Bluetooth SIG. (s. f.). _Bluetooth specifications_. https://www.bluetooth.com/specifications/specs/",
    "D-Bus Project. (s. f.). _D-Bus specification_. freedesktop.org. https://dbus.freedesktop.org/doc/dbus-specification.html",
    "Docker, Inc. (s. f.). _Docker Compose overview_. Docker Docs. https://docs.docker.com/compose/",
    "Google. (s. f.). _Material Design 3_. https://m3.material.io/",
    "JetBrains. (s. f.). _Kotlin documentation_. https://kotlinlang.org/docs/home.html",
    "JetBrains. (s. f.). _Asynchronous Flow_. Kotlin Docs. https://kotlinlang.org/docs/flow.html",
    "Journeyapps. (s. f.). _ZXing Android Embedded_ [Repositorio]. GitHub. https://github.com/journeyapps/zxing-android-embedded",
    "Moriarty, K., Kaliski, B., & Rusch, A. (2017). _PKCS #5: Password-Based Cryptography Specification Version 2.1_ (RFC 8018). Internet Engineering Task Force. https://www.rfc-editor.org/rfc/rfc8018",
    "Oracle. (s. f.). _Oracle Database 11g Release 2 documentation_. https://docs.oracle.com/cd/E11882_01/index.htm",
    "Oracle. (s. f.). _python-oracledb documentation_. https://python-oracledb.readthedocs.io/",
    "PlantUML. (s. f.). _PlantUML language reference guide_. https://plantuml.com/",
    "PyQtGraph. (s. f.). _PyQtGraph documentation_. https://www.pyqtgraph.org/",
    "pytest-dev. (s. f.). _pytest documentation_. https://docs.pytest.org/",
    "Python Software Foundation. (s. f.). _Python 3.12 documentation_. https://docs.python.org/3.12/",
    "Python Software Foundation. (s. f.). _zlib: Compression compatible with gzip_ (zlib.crc32). Python 3.12 documentation. https://docs.python.org/3.12/library/zlib.html",
    "Riverbank Computing. (s. f.). _PyQt6 reference guide_. https://www.riverbankcomputing.com/static/Docs/PyQt6/",
    "Roborazzi. (s. f.). _Roborazzi_ [Repositorio]. GitHub. https://github.com/takahirom/roborazzi",
    "The Qt Company. (s. f.). _Qt 6 documentation_. https://doc.qt.io/qt-6/",
]


def _criterio(f: Fig) -> str:
    for d in f.detalle:
        m = re.search(r"Criterio: ([^.]+)\.?", d)
        if m:
            return m.group(1).strip()
    return ""


def _tipo(f: Fig) -> str:
    if f.imagen.startswith("diagramas/"):
        return "Diagrama PlantUML"
    if "capturas/codigo/" in f.imagen:
        return "Captura de código"
    if "capturas/pruebas/" in f.imagen:
        return "Registro de ejecución"
    if "capturas/movil/" in f.imagen:
        return "Render de la APK"
    return "Captura de la aplicación"


def indice(figuras: list[Fig], refs: dict[str, str]) -> list[list[str]]:
    filas = []
    for i, f in enumerate(figuras, 1):
        filas.append([f"E-{i:03d}", refs[f.id].replace("Figura ", ""), f"`{f.imagen}`", _tipo(f), re.sub(r"\.$", "", f.titulo), _criterio(f)])
    return filas


def bloques(figuras: list[Fig], refs: dict[str, str]) -> list:
    b: list = []
    # ------------------------------------------------------------------ Referencias
    b += [H(1, "20. Referencias")]
    for r in REFERENCIAS:
        b.append(P(r, sangria=False))
    b += [
        P("Documentación del propio proyecto consultada: `README.md`, `docs/arquitectura.md`, `docs/protocolo.md`, "
          "`docs/verificacion.md`, `docs/uml/` y `docs/spikes/bluez.md`.", sangria=False),
    ]

    # ------------------------------------------------------------------ Anexos
    b += [
        H(1, "21. Anexos"),
        P("Los anexos reúnen las evidencias completas. Los archivos originales (capturas, diagramas fuente y renderizados, "
          "registros de ejecución y scripts) están en `docs/documentacion/` del repositorio y se enumeran en "
          "`INDICE_EVIDENCIAS.md`.", sangria=False),
        H(2, "21.1 Anexo A. Resultados de las pruebas por archivo"),
        Tabla("t_a1", "Servidor: resultados por archivo (Oracle limpio)", ["Archivo", "Aprobadas", "Fallidas", "Total", "Estado"],
              por_archivo(_leer("pruebas_servidor_limpia.txt")), [3800, 1300, 1300, 1300, 1660], "anexos/registros/pruebas_servidor_limpia.txt", tam=17),
        Tabla("t_a2", "Escritorio: resultados por archivo (Oracle limpio)", ["Archivo", "Aprobadas", "Fallidas", "Total", "Estado"],
              por_archivo(_leer("pruebas_escritorio_limpia.txt")), [3800, 1300, 1300, 1300, 1660], "anexos/registros/pruebas_escritorio_limpia.txt", tam=17),
        Tabla("t_a3", "APK: resultados por clase de prueba", ["Clase", "Pruebas", "Fallos", "Errores", "Estado"],
              android_por_clase(), [4800, 1100, 1100, 1100, 1260], "anexos/registros/pruebas_android.txt", tam=17),
        H(2, "21.2 Anexo B. Diagramas complementarios"),
        P("Los dos diagramas de clases siguientes son de gran tamaño: impresos a página completa quedan a escala reducida y su "
          "texto no es legible en papel. Por eso se adjuntan como SVG vectorial (`diagramas/renderizados/07c_clases_escritorio.svg` "
          "y `07d_clases_android.svg`), que se pueden ampliar sin pérdida de calidad; el PNG incrustado tiene alta resolución "
          "y admite zoom en el visor.", sangria=False),
        Horizontal([
            Fig("f_clases_pc", R + "07c_clases_escritorio.png", "Diagrama de clases de la aplicación de escritorio.",
                ["Fuente: elaboración propia. PlantUML: diagramas/plantuml/07c_clases_escritorio.puml (original docs/uml/02-clases-escritorio.puml). SVG en diagramas/renderizados/.",
                 "Demuestra: MainWindow, vistas, QueryRunner, ServicioRemoto y el módulo db. Criterio: Arquitectura y código fuente."]),
            Fig("f_clases_android", R + "07d_clases_android.png", "Diagrama de clases de la APK Android (MVVM).",
                ["Fuente: elaboración propia. PlantUML: diagramas/plantuml/07d_clases_android.puml (original docs/uml/03-clases-android.puml). SVG en diagramas/renderizados/.",
                 "Demuestra: pantallas, CountViewModel, SyncRunner, SyncClient, Protocol y la Outbox. Criterio: Arquitectura y código fuente."]),
        ]),
        H(2, "21.3 Anexo C. Índice de evidencias"),
        P("Cada figura del documento se corresponde con un archivo del repositorio. El mismo índice se entrega en "
          "`INDICE_EVIDENCIAS.md`.", sangria=False),
        Horizontal([
            Tabla("t_a4", "Índice de evidencias", ["ID", "Figura", "Archivo", "Tipo", "Descripción", "Criterio relacionado"],
                  indice(figuras, refs), [800, 800, 4300, 1700, 3400, 1960], "Generado automáticamente al construir el documento.", tam=14),
        ]),
        H(2, "21.4 Anexo D. Configuración no sensible"),
        Tabla("t_a5", "Servicios de Docker Compose (`docker-compose.yml`)", ["Servicio", "Imagen o construcción", "Configuración relevante"],
              [["`oracle`", "`gvenzl/oracle-xe:11-slim`", "Puerto `127.0.0.1:1521`; volumen `oracle-data`; `db/init` en solo lectura; _healthcheck_ `healthcheck.sh`"],
               ["`app`", "`desktop/Dockerfile` (sobre `pybase`)", "`network_mode: host`; `NET_ADMIN`/`NET_RAW`; `restart: on-failure:5`; X11 y D-Bus montados; `XDG_CONFIG_HOME=/work/config`"],
               ["`bluetooth`", "`docker/pybase/Dockerfile` (extras `bluez`)", "`network_mode: host`; `restart: unless-stopped`; comando `python -m btsync.servicio`"],
               ["`pybase` (perfil `dev`)", "`docker/pybase/Dockerfile` (extras `dev,bluez`)", "Pruebas del servidor"],
               ["`apk-build` (perfil `build`)", "`mobile/Dockerfile`", "JDK 17, Android SDK y Gradle; volumen `gradle-home`"],
               ["`plantuml` (perfil `docs`)", "`plantuml/plantuml:1.2024.7`", "Renderiza `docs/uml/*.puml` a SVG"],
               ["`bt-spike` (perfil `spike`)", "`docker/pybase/Dockerfile`", "Prueba desechable de BlueZ desde contenedor"]],
              [2200, 3000, 4160], "docker-compose.yml.", tam=16),
        Tabla("t_a6", "Constantes técnicas relevantes", ["Constante", "Valor", "Dónde"],
              [["Versión del protocolo", "5", "`protocol.py` (`PROTOCOL_VERSION`)"],
               ["Longitud máxima de línea", "4000 bytes", "`protocol.py` (`MAX_LINE_BYTES`)"],
               ["Parte de foto", "2700 caracteres base64", "`protocol.py` (`FOTO_PARTE`)"],
               ["`COMMIT` cada", "25 inserciones", "`session.py` (`COMMIT_EVERY`)"],
               ["Ventana de envío", "50 `REC` sin `ACK`", "`fake_phone.py` (`WINDOW`) y `SyncClient`"],
               ["Iteraciones PBKDF2", "200 000", "`auth.py` (`ITERACIONES`)"],
               ["Bloqueo por intentos", "5 intentos, 30 s", "`auth.py` (`MAX_INTENTOS`, `BLOQUEO_S`)"],
               ["Hilos de consulta", "8 como máximo", "`views/base.py` (`MAX_HILOS`)"],
               ["Sondeo del servicio", "2 s (escritorio) y 1 s (`tick`)", "`servicio_remoto.py`, `servicio.py`"],
               ["Job del _batch_", "`FREQ=MINUTELY;INTERVAL=1`", "`db/init/04_jobs.sql`"]],
              [3000, 2400, 3960], "Código fuente del proyecto.", tam=17),
        H(2, "21.5 Anexo E. Regeneración de las evidencias"),
        P("Todas las evidencias de este documento se pueden regenerar con los scripts de `docs/documentacion/herramientas/`, "
          "ejecutados desde la raíz del repositorio con el Oracle del proyecto en marcha.", sangria=False),
        Tabla("t_a7", "Scripts de evidencias", ["Script", "Qué genera"],
              [["`capturar.sh` + `capturar_pantallas.py`, `capturar_extra.py`", "Capturas reales de la aplicación de escritorio (Qt offscreen) para los roles Administrador e Inventario y varias resoluciones"],
               ["`capturar_codigo.py`", "Capturas del código fuente con Pygments, con ruta y líneas reales"],
               ["`renderizar_diagramas.sh`", "SVG y PNG de los `.puml` con PlantUML 1.2024.7 en Docker"],
               ["`pruebas.sh`, `pruebas_limpia.sh`, `pruebas_android.sh`", "Ejecución y registro de las suites"],
               ["`oracle_limpio.sh`", "Segundo Oracle XE sin datos de demostración (puerto 1522)"],
               ["`comunicacion_tcp.sh`, `comunicacion_corte.sh`", "Sincronización real y corte con reanudación por el transporte TCP"],
               ["`preparar_capturas_movil.py`, `capturar_registros.py`, `entorno.sh`", "Montajes de la APK, imágenes de los registros y versiones del entorno"],
               ["`construir_documento.py`", "Este documento (DOCX sobre la plantilla, PDF y Markdown) y el índice de evidencias"]],
              [4200, 5160], "docs/documentacion/herramientas/.", tam=17),
    ]

    # ------------------------------------------------------------------ Matriz (apaisada, última sección)
    b += [
        H(2, "21.6 Anexo F. Matriz de trazabilidad con la rúbrica"),
        P("La matriz relaciona cada criterio de la rúbrica con los requisitos que debe demostrar, el componente, la evidencia "
          "técnica, las capturas, las pruebas y el resultado de la verificación. Las referencias son a figuras y tablas de "
          "este documento.", sangria=False),
        Horizontal([
            Tabla("t_matriz", "Matriz de trazabilidad con la rúbrica de evaluación",
                  ["Criterio (peso)", "Requisito que se debe demostrar", "Funcionalidad o componente", "Evidencia técnica", "Captura de código", "Captura de ejecución", "Prueba relacionada", "Resultado"],
                  [["1. Funcionalidad y requisitos (25 %)", "Captura de datos sin red", "RF-009 a RF-012; `CountViewModel`, `Outbox`", "Cap. 6 y 11.9; [[t_rf1]]", "[[c_addview]]", "[[f_mov2]]", "`CountViewModelTest`, `OutboxTest` (115 de 115 en la APK)", "Verificado"],
                   ["", "Conectividad con la base de datos y batch", "RF-014, RF-016; `Session`, `PKG_BATCH`", "Cap. 8 y 9; [[f_er]]", "[[c_batch]], [[c_ins]]", "[[f_com2]]", "`test_batch.py` (48 de 48)", "Verificado"],
                   ["", "Módulos del escritorio operativos", "RF-001 a RF-007, RF-017 a RF-026", "Cap. 11; [[t_modulos]]", "[[c_auth]]", "[[f_dash_admin]] a [[f_perfil]]", "Suites del escritorio (454 de 464 en Oracle limpio)", "Verificado, con fallos de pruebas (14.4)"],
                   ["2. Conectividad y comunicación (25 %)", "Transferencia con validación y confirmación", "RF-013, RF-014; protocolo v5", "Cap. 9; [[t_msg]]", "[[c_frame]], [[c_onrec]], [[c_ack]]", "[[f_com1]], [[f_com2]]", "`test_session.py` (22 de 23), `test_e2e_tcp.py` (6 de 6)", "Verificado por TCP"],
                   ["", "Reintentos y desconexiones", "RF-015; `SyncRunner`, `READY`, go-back-N", "[[f_sec6]]; [[t_fallas]]", "[[c_arunner]], [[c_aout]]", "[[f_cor1]], [[f_cor2]]", "`test_connection_cut_after_30_rec_keeps_25`; `SyncRunnerTest`", "Verificado por TCP"],
                   ["", "Enlace Bluetooth y seguridad del canal", "`BluezTransport`; D22", "Cap. 9.6", "[[c_perfil]]", "No ejecutado en esta verificación (sin teléfono)", "`test_bluez.py` (36 de 36, bus falso)", "Parcial"],
                   ["3. Arquitectura y código (20 %)", "Estructura MVC/MVVM y capas", "`views/`, `ui/pantallas/`, `btsync`", "Cap. 7; [[f_arq]], [[f_comp]], [[f_clases]]", "[[c_entrada]], [[c_addview]], [[c_compose]]", "—", "`test_uml.py` (4 de 5)", "Verificado"],
                   ["", "Hilos sin congelar la interfaz", "`QueryWorker`, `QueryRunner`, `Dispatchers.IO`", "[[t_hilos]]", "[[c_worker]], [[c_runner]], [[c_remoto]]", "[[f_carga]]", "`test_workers.py` (5 de 5)", "Verificado"],
                   ["4. UI/UX y adaptabilidad (15 %)", "Interfaz clara, estados de carga y error", "Cap. 12", "[[f_carga]], [[f_mov3]]", "—", "[[f_dash_admin]], [[f_mov1]]", "Verificación visual manual", "Verificado"],
                   ["", "Adaptación a resoluciones y roles", "Barra lateral contraíble; roles", "[[t_roles_pantallas]]", "—", "[[f_res900]], [[f_res1920]], [[f_roles_barras]]", "`test_app.py` (barras por rol)", "Verificado (móvil: solo vertical)"],
                   ["5. Documentación y presentación (15 %)", "Manual de arquitectura e instalación", "Cap. 7 y 15", "[[t_req]], [[t_sol]]", "—", "[[f_entorno]]", "Comandos verificados contra README y `docker-compose.yml`", "Verificado"],
                   ["", "Diagramas de flujo y de secuencia", "16 diagramas PlantUML", "[[f_sec5]], [[f_sec6]], [[f_act]]", "—", "—", "`test_uml.py::test_every_puml_has_start_end_and_title`", "Verificado"]],
                  [1500, 1800, 1900, 1650, 1500, 1500, 1900, 1210], "Elaboración propia.", tam=14),
        ]),
    ]
    return b
