#!/usr/bin/env bash
# Genera SVG y PNG de docs/uml/*.puml en docs/img/uml/ con PlantUML en Docker (servicio `plantuml`, perfil `docs`).
# -o es relativo a la carpeta de cada fuente (docs/uml), por eso «../img/uml». -failonerror: si un diagrama
# tiene un error de sintaxis el script termina con código distinto de 0 (sin él PlantUML dibuja el error y sigue).
# PNG a 130 dpi (misma resolución que los diagramas de docs/documentacion/diagramas).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p docs/img/uml
docker compose --profile docs run --rm -T plantuml -tsvg -failonerror -o ../img/uml uml/*.puml
docker compose --profile docs run --rm -T -e JAVA_TOOL_OPTIONS="-Duser.home=/tmp -DPLANTUML_LIMIT_SIZE=16000" plantuml -tpng -failonerror -Sdpi=130 -o ../img/uml uml/*.puml
