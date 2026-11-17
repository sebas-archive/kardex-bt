#!/usr/bin/env bash
# Ejecuta las suites del proyecto EN SERIE (comparten la misma base Oracle) y guarda la salida íntegra.
# Uso (desde la raíz del repositorio): docs/documentacion/herramientas/pruebas.sh <ruta_a_.env>
# Requiere el contenedor Oracle del proyecto en marcha (127.0.0.1:1521). Las credenciales no se imprimen.
set -uo pipefail
ENV_FILE=${1:?ruta del .env}
REPO=$(pwd)
LOGS=docs/documentacion/anexos/registros
mkdir -p "$LOGS"
set -a; . "$ENV_FILE"; set +a
COMUN=(--rm --network host --user "$(id -u):$(id -g)" -v "$REPO":/work
  -e DB_DSN=127.0.0.1:1521/XE -e DB_USER="$DB_USER" -e DB_PASSWORD="$DB_PASSWORD" -e ORA_SDTZ=+00:00
  -e PYTHONPATH=/work/server:/work/desktop -e HOME=/tmp -e XDG_CONFIG_HOME=/tmp/cfg-doc -e FOTOS_DIR=/work/fotos
  -e RESPALDOS_DIR=/tmp/respaldos-doc)

date -u +"inicio %Y-%m-%dT%H:%M:%SZ" > "$LOGS/pruebas_servidor.txt"
docker run "${COMUN[@]}" -w /work inventario-bt-pybase python -m pytest server/tests -v -p no:cacheprovider \
  >> "$LOGS/pruebas_servidor.txt" 2>&1
echo "EXIT=$?" >> "$LOGS/pruebas_servidor.txt"

date -u +"inicio %Y-%m-%dT%H:%M:%SZ" > "$LOGS/pruebas_escritorio.txt"
docker run "${COMUN[@]}" -w /work/desktop -e QT_QPA_PLATFORM=offscreen -e APP_SIN_ANIMACIONES=1 \
  inventario-bt-pybase-qt python -m pytest tests -v -p no:cacheprovider \
  >> "$LOGS/pruebas_escritorio.txt" 2>&1
echo "EXIT=$?" >> "$LOGS/pruebas_escritorio.txt"
echo terminado > "$LOGS/pruebas_fin.txt"
