#!/usr/bin/env bash
# Genera los SVG de docs/uml/*.puml en docs/img/uml/ con PlantUML en Docker (servicio `plantuml`, perfil `docs`).
# -o es relativo a la carpeta de cada fuente (docs/uml), por eso «../img/uml». -failonerror: si un diagrama
# tiene un error de sintaxis el script termina con código distinto de 0 (sin él PlantUML dibuja el error y sigue).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p docs/img/uml
docker compose --profile docs run --rm -T plantuml -tsvg -failonerror -o ../img/uml uml/*.puml
