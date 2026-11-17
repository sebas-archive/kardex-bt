"""Copia a docs/documentacion/diagramas/plantuml los diagramas del proyecto (docs/uml) que corresponden a los diez
tipos pedidos, renumerándolos «Diagrama N». Las fuentes originales no se modifican. El diagrama 2 (arquitectura
general) es nuevo y vive directamente en la carpeta de destino."""
import re
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]          # docs/
ORIGEN = RAIZ / "uml"
DESTINO = RAIZ / "documentacion" / "diagramas" / "plantuml"

MAPA = {
    "01_casos_uso": ("10-casos-de-uso", "Diagrama 1"),
    "03_componentes": ("06-componentes", "Diagrama 3"),
    "04_despliegue": ("07-despliegue", "Diagrama 4"),
    "05_secuencia_flujo_datos": ("13-secuencia-sincronizacion", "Diagrama 5"),
    "06_secuencia_comunicacion": ("14-secuencia-corte-reanudacion", "Diagrama 6"),
    "07_clases_paquetes": ("01-clases-servidor", "Diagrama 7"),
    "08_actividades": ("12-actividad-batch", "Diagrama 8"),
    "09_estados": ("16-estados-sync-controller", "Diagrama 9"),
    "10_modelo_datos": ("04-modelo-datos", "Diagrama 10"),
    "07b_paquetes": ("08-paquetes", "Diagrama 7b"),
    "07c_clases_escritorio": ("02-clases-escritorio", "Diagrama 7c"),
    "07d_clases_android": ("03-clases-android", "Diagrama 7d"),
    "08b_actividad_conteo_movil": ("11-actividad-conteo-movil", "Diagrama 8b"),
    "09b_estados_fila_transito": ("17-estados-fila-transito", "Diagrama 9b"),
    "09c_estados_cuenta": ("19-estados-cuenta", "Diagrama 9c"),
}

shutil.copy(ORIGEN / "estilo.iuml", DESTINO / "estilo.iuml")
for nuevo, (viejo, nombre) in MAPA.items():
    texto = (ORIGEN / f"{viejo}.puml").read_text(encoding="utf8")
    texto = re.sub(r"^title \d+ · ", f"title {nombre} · ", texto, count=1, flags=re.M)
    (DESTINO / f"{nuevo}.puml").write_text(texto, encoding="utf8")
    print(nuevo, re.search(r"^title .*", texto, re.M).group(0))
