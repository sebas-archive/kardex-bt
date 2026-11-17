#!/usr/bin/env bash
# Levanta un SEGUNDO Oracle XE 11g, independiente del de trabajo (puerto 127.0.0.1:1522, sin volumen), con el
# esquema y la semilla del proyecto pero SIN db/init/08_demo.sql. Sirve para ejecutar las suites contra la base
# limpia para la que fueron escritas (60 productos), sin tocar los datos de demostración del Oracle principal.
# Uso: oracle_limpio.sh <ruta_a_.env>     (se elimina con: docker rm -f oracle-limpio-doc)
set -euo pipefail
ENV_FILE=${1:?ruta del .env}
REPO=$(pwd)
set -a; . "$ENV_FILE"; set +a
INIT=$(mktemp -d)
for f in "$REPO"/db/init/0[1-7]_*.sql; do cp "$f" "$INIT/"; done
chmod -R a+rX "$INIT"
docker rm -f oracle-limpio-doc >/dev/null 2>&1 || true
docker run -d --name oracle-limpio-doc -p 127.0.0.1:1522:1521 \
  -e ORACLE_PASSWORD="$ORACLE_PASSWORD" -e APP_USER="$APP_USER" -e APP_USER_PASSWORD="$APP_USER_PASSWORD" \
  -v "$INIT":/container-entrypoint-initdb.d:ro \
  --health-cmd healthcheck.sh --health-interval 10s --health-retries 60 --health-start-period 60s \
  gvenzl/oracle-xe:11-slim
echo "directorio de init: $INIT"
