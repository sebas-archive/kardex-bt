#!/usr/bin/env bash
# Renderiza docs/documentacion/diagramas/plantuml/*.puml a SVG y PNG (PlantUML 1.2024.7 en Docker, la misma imagen
# que usa el proyecto en tools/render_uml.sh). -failonerror: un error de sintaxis termina el script con código ≠ 0.
# Uso (raíz del repositorio): docs/documentacion/herramientas/renderizar_diagramas.sh
set -euo pipefail
D=$(pwd)/docs/documentacion/diagramas
run() { docker run --rm --user "$(id -u):$(id -g)" -e JAVA_TOOL_OPTIONS="-Duser.home=/tmp -DPLANTUML_LIMIT_SIZE=16000" \
  -v "$D":/d -w /d plantuml/plantuml:1.2024.7 "$@" 2>&1 | grep -v "^Picked up" || true; }
run -tsvg -failonerror -o ../renderizados plantuml/*.puml
run -tpng -failonerror -Sdpi=130 -o ../renderizados plantuml/*.puml
python3 -I - <<'PY'
import glob, struct
for f in sorted(glob.glob("docs/documentacion/diagramas/renderizados/*.png")):
    w, h = struct.unpack(">II", open(f, "rb").read()[16:24])
    print(f"{f.split('/')[-1]:34s} {w:5d}x{h:5d}px  natural {round(w*72/130):5d}x{round(h*72/130):5d}pt")
PY
