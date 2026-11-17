"""Genera capturas legibles del CÓDIGO FUENTE REAL del proyecto (resaltado con Pygments, con números de línea
reales y la ruta del archivo en la cabecera). No contiene código inventado: cada captura se obtiene leyendo el
archivo del repositorio en la ubicación indicada.

Uso (desde la raíz del repositorio):
    python capturar_codigo.py <carpeta_salida> <archivo_indice.json>
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pygments import highlight
from pygments.formatters import ImageFormatter
from pygments.lexers import get_lexer_for_filename

RAIZ = Path.cwd()
SALIDA = Path(sys.argv[1])
INDICE = Path(sys.argv[2])
FUENTE = "/usr/share/fonts/TTF/DejaVuSansMono.ttf"
FUENTE_B = "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf"
MAX_LINEAS = 52

# (id, archivo, localizador, titulo, criterio)
#   localizador: "py:Clase.metodo" | "py:funcion" | "kt:regex" | "txt:regex:N" (N líneas desde la coincidencia)
CAPTURAS = [
    ("codigo_01_entrada_escritorio", "desktop/app/main.py", "py:main", "Punto de entrada de la aplicación de escritorio", "Arquitectura y código"),
    ("codigo_02_entrada_servicio", "server/btsync/servicio.py", "py:main", "Punto de entrada del servicio Bluetooth", "Arquitectura y código"),
    ("codigo_03_configuracion_compose", "docker-compose.yml", r"txt:^  bluetooth:$:26", "Configuración del servicio «bluetooth» en Docker Compose", "Arquitectura / instalación"),
    ("codigo_04_composicion_ventana", "desktop/app/main.py", "py:MainWindow.add_view", "Composición de la ventana: registro de vistas y permisos", "Arquitectura y código"),
    ("codigo_05_protocolo_trama", "server/btsync/protocol.py", r"txt:^def frame:30", "Protocolo: construcción y validación de tramas (longitud, CRC32, formato)", "Conectividad"),
    ("codigo_07_sesion_bucle", "server/btsync/session.py", "py:Session._run", "Sesión: bucle de recepción y despacho de mensajes", "Conectividad"),
    ("codigo_08_sesion_rec", "server/btsync/session.py", "py:Session._on_rec", "Sesión: validación de secuencia, inserción y NAK (go-back-N)", "Conectividad"),
    ("codigo_09_sesion_ack", "server/btsync/session.py", r"txt:^    def _commit_and_ack:17", "Sesión: COMMIT y confirmación acumulativa ACK", "Conectividad"),
    ("codigo_10_store_insert", "server/btsync/store.py", "py:Store.insert_staging", "Persistencia: inserción idempotente en CAPTURA_TRANSITO", "Conectividad / datos"),
    ("codigo_11_store_conexion", "server/btsync/store.py", "py:connect_oracle", "Conexión con Oracle (python-oracledb)", "Conectividad / datos"),
    ("codigo_12_bluez_perfil", "server/btsync/transports/bluez.py", r"txt:^class _Profile:20", "Transporte Bluetooth: perfil RFCOMM registrado por D-Bus (BlueZ ProfileManager1)", "Conectividad"),
    ("codigo_13_controlador_conexion", "server/btsync/controller.py", "py:SyncController._on_connection", "Controlador: una sesión por conexión y D19 (PC ocupado)", "Arquitectura / concurrencia"),
    ("codigo_14_servicio_tick", "server/btsync/servicio.py", "py:Servicio.tick", "Servicio: latido, pausa y estado en SERVICIO_BT", "Arquitectura / concurrencia"),
    ("codigo_15_hilos_worker", "desktop/app/workers.py", "py:QueryWorker", "Concurrencia: QueryWorker (QRunnable) con señales Qt", "Arquitectura / concurrencia"),
    ("codigo_16_hilos_runner", "desktop/app/views/base.py", "py:QueryRunner.run", "Concurrencia: QueryRunner entrega el resultado al hilo de la UI", "Arquitectura / concurrencia"),
    ("codigo_17_remoto", "desktop/app/servicio_remoto.py", "py:ServicioRemoto", "Señales: ServicioRemoto convierte el estado de Oracle en señales Qt", "Arquitectura / señales"),
    ("codigo_18_autenticacion", "desktop/app/auth.py", "py:iniciar_sesion", "Autenticación: hash, bloqueo por intentos y auditoría", "Seguridad / funcionalidad"),
    ("codigo_19_hash", "desktop/app/auth.py", "py:crear_hash", "Contraseñas: PBKDF2 con sal", "Seguridad"),
    ("codigo_20_permisos", "desktop/app/permisos.py", r"txt:^NINGUNO, CONSULTA, GESTION:38", "Permisos: matriz inicial de 12 módulos y niveles Sin acceso / Consulta / Gestión", "Seguridad"),
    ("codigo_21_exigir", "desktop/app/permisos.py", "py:exigir", "Permisos: revalidación en vivo antes de cambiar datos", "Seguridad"),
    ("codigo_22_sql_tabla_transito", "db/init/01_schema.sql", r"txt:^CREATE TABLE captura_transito:23", "Modelo de datos: tabla de staging CAPTURA_TRANSITO", "Datos"),
    ("codigo_23_sql_batch", "db/init/03_pkg_batch.sql", r"txt:^    PROCEDURE procesar_fila:60", "PKG_BATCH: validación y proceso de una lectura", "Datos / funcionalidad"),
    ("codigo_24_sql_permisos", "db/init/06_permisos.sql", r"txt:^BEGIN:24", "Matriz de permisos rol × módulo (Oracle)", "Seguridad / datos"),
    ("codigo_25_android_sync", "mobile/app/src/main/java/co/edu/umariana/inventario/sync/SyncClient.kt", r"txt:^    private suspend fun FlowCollector<SyncProgress>.session:50", "Android: SyncClient, protocolo de sincronización (HELLO, READY, REC, ACK)", "Conectividad"),
    ("codigo_26_android_runner", "mobile/app/src/main/java/co/edu/umariana/inventario/ui/SyncRunner.kt", r"kt:^    fun ejecutar\(", "Android: SyncRunner con reintentos y estados", "Conectividad / UI"),
    ("codigo_27_android_outbox", "mobile/app/src/main/java/co/edu/umariana/inventario/data/Lectura.kt", r"txt:^    open fun tomarParaEnviar:42", "Android: Outbox (Room), envío y reconciliación tras un corte", "Conectividad / datos"),
    ("codigo_28_android_viewmodel", "mobile/app/src/main/java/co/edu/umariana/inventario/ui/CountViewModel.kt", r"kt:^    fun guardar\(", "Android (MVVM): CountViewModel guarda primero en la Outbox", "Arquitectura"),
    ("codigo_29_prueba_protocolo", "server/tests/test_protocol.py", "py:test_crc_mismatch_raises_crc", "Prueba representativa: CRC del protocolo", "Pruebas"),
    ("codigo_30_prueba_corte", "server/tests/test_session.py", r"py:test_connection_cut_after_30_rec_keeps_25", "Prueba representativa: reanudación / secuencia", "Pruebas"),
]


def rango_python(texto: str, nombre: str) -> tuple[int, int]:
    arbol = ast.parse(texto)
    partes = nombre.split(".")
    nodos = arbol.body
    nodo = None
    for p in partes:
        nodo = next((n for n in nodos if getattr(n, "name", None) == p), None)
        if nodo is None:
            raise SystemExit(f"no encuentro {nombre}")
        nodos = getattr(nodo, "body", [])
    ini = min([nodo.lineno] + [d.lineno for d in nodo.decorator_list]) if hasattr(nodo, "decorator_list") else nodo.lineno
    return ini, nodo.end_lineno


def rango_llaves(lineas: list[str], patron: str) -> tuple[int, int]:
    ini = next(i for i, l in enumerate(lineas) if re.search(patron, l))
    prof = 0
    abierto = False
    for j in range(ini, len(lineas)):
        for ch in lineas[j]:
            if ch == "{":
                prof += 1
                abierto = True
            elif ch == "}":
                prof -= 1
        if abierto and prof <= 0:
            return ini + 1, j + 1
    return ini + 1, min(len(lineas), ini + MAX_LINEAS)


def resolver(archivo: str, loc: str) -> tuple[int, int]:
    texto = (RAIZ / archivo).read_text(encoding="utf8")
    lineas = texto.splitlines()
    tipo, _, resto = loc.partition(":")
    if tipo == "py":
        return rango_python(texto, resto)
    if tipo == "kt":
        return rango_llaves(lineas, resto)
    patron, _, n = resto.rpartition(":")
    ini = next(i for i, l in enumerate(lineas) if re.search(patron, l, re.I))
    return ini + 1, min(len(lineas), ini + int(n))


def renderizar(archivo: str, ini: int, fin: int, titulo: str) -> Image.Image:
    lineas = (RAIZ / archivo).read_text(encoding="utf8").splitlines()
    fin = min(fin, ini + MAX_LINEAS - 1)
    trozo = "\n".join(lineas[ini - 1:fin]) + "\n"
    lexer = get_lexer_for_filename(archivo)
    fmt = ImageFormatter(font_name="DejaVu Sans Mono", font_size=17, line_numbers=True, line_number_start=ini,
                         style="friendly", image_pad=14, line_pad=3, line_number_bg="#f0f2f5",
                         line_number_fg="#6b7280", line_number_separator=True, line_number_pad=10)
    cuerpo = Image.open(__import__("io").BytesIO(highlight(trozo, lexer, fmt)))
    cuerpo = cuerpo.convert("RGB")
    ancho = max(cuerpo.width, 900)
    barra = 40
    img = Image.new("RGB", (ancho, cuerpo.height + barra), "#ffffff")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, ancho, barra], fill="#1f2937")
    f = ImageFont.truetype(FUENTE_B, 16)
    d.text((14, 10), f"{archivo}  ·  líneas {ini}–{fin}", font=f, fill="#e5e7eb")
    img.paste(cuerpo, (0, barra))
    d.rectangle([0, 0, ancho - 1, img.height - 1], outline="#9ca3af")
    return img


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    indice = []
    for ident, archivo, loc, titulo, criterio in CAPTURAS:
        ini, fin = resolver(archivo, loc)
        img = renderizar(archivo, ini, fin, titulo)
        destino = SALIDA / f"{ident}.png"
        img.save(destino)
        indice.append({"id": ident, "archivo": archivo, "ini": ini, "fin": min(fin, ini + MAX_LINEAS - 1),
                       "titulo": titulo, "criterio": criterio, "imagen": f"capturas/codigo/{destino.name}",
                       "ancho": img.width, "alto": img.height})
        print(destino.name, archivo, ini, fin, img.size)
    INDICE.write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
