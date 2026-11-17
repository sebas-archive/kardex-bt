#!/usr/bin/env bash
# Ejecuta capturar_pantallas.py dentro de la imagen de la app de escritorio (Qt offscreen) contra el Oracle
# que ya corre en Docker (127.0.0.1:1521). Las credenciales salen del .env del proyecto y no se imprimen.
# Uso (desde la raíz del repositorio): docs/documentacion/herramientas/capturar.sh <ruta_a_.env> [carpeta_salida]
set -euo pipefail
ENV_FILE=${1:?ruta del .env}
OUT=${2:-docs/documentacion/capturas}
SCRIPT=${3:-capturar_pantallas.py}
REPO=$(pwd)
set -a; . "$ENV_FILE"; set +a
mkdir -p "$REPO/$OUT" /tmp/cfg-doc
docker run --rm --network host --user "$(id -u):$(id -g)" \
  -v "$REPO":/work -w /work \
  -e DB_DSN=127.0.0.1:1521/XE -e DB_USER="$DB_USER" -e DB_PASSWORD="$DB_PASSWORD" -e ORA_SDTZ=+00:00 \
  -e PYTHONPATH=/work/server:/work/desktop -e QT_QPA_PLATFORM=offscreen -e APP_SIN_ANIMACIONES=1 \
  -e HOME=/tmp -e XDG_CACHE_HOME=/tmp/.cache -e XDG_CONFIG_HOME=/tmp/cfg-doc -e FOTOS_DIR=/work/fotos \
  --entrypoint python inventario-bt-app -u docs/documentacion/herramientas/"$SCRIPT" "$OUT"
