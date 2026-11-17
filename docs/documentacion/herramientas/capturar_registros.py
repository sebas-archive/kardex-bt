"""Convierte registros REALES de ejecución (docs/documentacion/anexos/registros/*.txt) en imágenes tipo terminal.
No edita el texto: solo recorta por líneas y colorea (verde PASSED, rojo FAILED). Uso: capturar_registros.py <salida>"""
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path.cwd() / "docs" / "documentacion"
REG = RAIZ / "anexos" / "registros"
SALIDA = Path(sys.argv[1])
F = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSansMono.ttf", 17)
FB = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf", 17)


def lineas_de(archivo: str, rangos: list[tuple[int, int]] | None, ultimas: int | None) -> list[str]:
    todas = (REG / archivo).read_text(encoding="utf8", errors="replace").splitlines()
    if ultimas:
        return [l[:112] for l in todas[-ultimas:]]
    out: list[str] = []
    for a, b in rangos or [(1, len(todas))]:
        out += [l[:112] for l in todas[a - 1:b]]
    return out


def pintar(lineas: list[str], titulo: str, destino: Path) -> None:
    ancho_car = int(F.getlength("M"))
    ancho = max(1000, max(len(l) for l in lineas) * ancho_car + 40)
    alto_l = 23
    img = Image.new("RGB", (ancho, 40 + alto_l * len(lineas) + 20), "#0f172a")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, ancho, 36], fill="#1e293b")
    for i, c in enumerate(("#ef4444", "#f59e0b", "#22c55e")):
        d.ellipse([14 + i * 22, 11, 26 + i * 22, 23], fill=c)
    d.text((90, 8), titulo, font=FB, fill="#e2e8f0")
    for i, l in enumerate(lineas):
        color = "#e2e8f0"
        if "PASSED" in l or re.search(r"\b\d+ passed\b", l) and "failed" not in l or l.startswith("BUILD SUCCESSFUL"):
            color = "#4ade80"
        if "FAILED" in l or " failed" in l:
            color = "#f87171"
        if l.startswith("#") or l.startswith("##") or l.startswith("-- "):
            color = "#fbbf24"
        d.text((20, 46 + i * alto_l), l, font=F, fill=color)
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino)
    print(destino.name, img.size)


CAPTURAS = [
    ("registro_01_servidor_limpia", "$ docker run … inventario-bt-pybase python -m pytest server/tests -v   (Oracle limpio)", "pruebas_servidor_limpia.txt", None, 22),
    ("registro_02_escritorio_limpia", "$ docker run … inventario-bt-pybase-qt python -m pytest tests -v   (Oracle limpio)", "pruebas_escritorio_limpia.txt", None, 16),
    ("registro_03_android", "$ ./gradlew testDebugUnitTest --rerun-tasks   (resumen por clase)", "pruebas_android.txt", None, 28),
    ("registro_04_servidor_demo", "pytest server/tests -v   (Oracle de trabajo con datos de demostración)", "pruebas_servidor.txt", None, 17),
    ("registro_05_escritorio_demo", "pytest desktop/tests -v   (Oracle de trabajo con datos de demostración)", "pruebas_escritorio.txt", None, 22),
    ("registro_06_comunicacion_a", "comunicacion_tcp.sh · teléfono simulado → servicio btsync (TCP) → Oracle", "comunicacion_tcp.txt", [(1, 19)], None),
    ("registro_07_comunicacion_b", "comunicacion_tcp.sh · estado de Oracle tras el batch", "comunicacion_tcp.txt", [(20, 60)], None),
    ("registro_08_corte", "comunicacion_corte.sh · corte con SIGKILL y reanudación", "comunicacion_corte.txt", [(1, 22)], None),
    ("registro_09_corte_final", "comunicacion_corte.sh · estado final, sin duplicados", "comunicacion_corte.txt", [(23, 50)], None),
    ("registro_10_entorno", "entorno.sh · contenedores y versiones", "entorno.txt", None, None),
]

if __name__ == "__main__":
    for ident, titulo, archivo, rangos, ultimas in CAPTURAS:
        pintar(lineas_de(archivo, rangos, ultimas), titulo, SALIDA / f"{ident}.png")
