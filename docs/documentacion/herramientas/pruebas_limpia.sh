#!/usr/bin/env bash
# Ejecuta las suites del servidor y del escritorio contra el Oracle LIMPIO (oracle_limpio.sh, puerto 1522),
# la base sin datos de demostración para la que están escritas las pruebas. Salida íntegra en anexos/registros.
# Uso (raíz del repositorio): docs/documentacion/herramientas/pruebas_limpia.sh <ruta_a_.env>
set -uo pipefail
ENV_FILE=${1:?ruta del .env}
REPO=$(pwd)
LOGS=docs/documentacion/anexos/registros
mkdir -p "$LOGS"
set -a; . "$ENV_FILE"; set +a
COMUN=(--rm --network host --user "$(id -u):$(id -g)" -v "$REPO":/work
  -e DB_DSN=127.0.0.1:1522/XE -e DB_USER="$DB_USER" -e DB_PASSWORD="$DB_PASSWORD" -e ORA_SDTZ=+00:00
  -e PYTHONPATH=/work/server:/work/desktop -e HOME=/tmp -e XDG_CONFIG_HOME=/tmp/cfg-doc2 -e FOTOS_DIR=/tmp/fotos-doc
  -e RESPALDOS_DIR=/tmp/respaldos-doc)

date -u +"inicio %Y-%m-%dT%H:%M:%SZ  (Oracle limpio, sin 08_demo.sql)" > "$LOGS/pruebas_servidor_limpia.txt"
docker run "${COMUN[@]}" -w /work inventario-bt-pybase python -m pytest server/tests -v -p no:cacheprovider \
  >> "$LOGS/pruebas_servidor_limpia.txt" 2>&1
echo "EXIT=$?" >> "$LOGS/pruebas_servidor_limpia.txt"

date -u +"inicio %Y-%m-%dT%H:%M:%SZ  (Oracle limpio, sin 08_demo.sql)" > "$LOGS/pruebas_escritorio_limpia.txt"
docker run "${COMUN[@]}" -w /work/desktop -e QT_QPA_PLATFORM=offscreen -e APP_SIN_ANIMACIONES=1 \
  inventario-bt-pybase-qt python -m pytest tests -v -p no:cacheprovider \
  >> "$LOGS/pruebas_escritorio_limpia.txt" 2>&1
echo "EXIT=$?" >> "$LOGS/pruebas_escritorio_limpia.txt"
echo terminado > "$LOGS/pruebas_limpia_fin.txt"
