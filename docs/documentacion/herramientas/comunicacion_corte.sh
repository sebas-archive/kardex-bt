#!/usr/bin/env bash
# Demostración REAL de un corte de la conexión y de la reanudación (READY con el último seq confirmado), contra el Oracle
# LIMPIO (puerto 1522) y el servicio btsync en TCP (puerto 9100). El teléfono simulado se mata con SIGKILL a mitad del
# envío (equivale a que se vaya del alcance del Bluetooth) y se vuelve a lanzar con el mismo outbox persistente.
# Salida: docs/documentacion/anexos/registros/comunicacion_corte.txt
# Uso (raíz del repositorio): docs/documentacion/herramientas/comunicacion_corte.sh <ruta_a_.env>
set -uo pipefail
ENV_FILE=${1:?ruta del .env}
REPO=$(pwd)
OUT=docs/documentacion/anexos/registros/comunicacion_corte.txt
set -a; . "$ENV_FILE"; set +a
BASE=(--rm --network host --user "$(id -u):$(id -g)" -v "$REPO":/work -w /work
  -e DB_DSN=127.0.0.1:1522/XE -e DB_USER="$DB_USER" -e DB_PASSWORD="$DB_PASSWORD" -e ORA_SDTZ=+00:00
  -e PYTHONPATH=/work/server -e HOME=/tmp -e FOTOS_DIR=/tmp/fotos-doc -e RESPALDOS_DIR=/tmp/respaldos-doc)
PY=inventario-bt-pybase
sql() { docker run "${BASE[@]}" --entrypoint python $PY docs/documentacion/herramientas/consulta_estado.py | sed -n "$1"; }
aprobar() { docker run "${BASE[@]}" --entrypoint python $PY -c "
import os, oracledb
oracledb.init_oracle_client()
c = oracledb.connect(user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], dsn=os.environ['DB_DSN'])
cur = c.cursor(); cur.execute(\"UPDATE usuarios SET estado='ACTIVO', rol='OPERADOR' WHERE usuario='operador.dos'\"); c.commit()
print('Administrador aprueba operador.dos:', cur.rowcount, 'fila')"; }
rm -f /tmp/outbox-corte.json
exec > "$OUT" 2>&1
echo "# Evidencia de corte y reanudación — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
docker rm -f servicio-tcp-doc >/dev/null 2>&1
docker run -d --name servicio-tcp-doc --network host --user "$(id -u):$(id -g)" -v "$REPO":/work -w /work \
  -e DB_DSN=127.0.0.1:1522/XE -e DB_USER="$DB_USER" -e DB_PASSWORD="$DB_PASSWORD" -e ORA_SDTZ=+00:00 \
  -e PYTHONPATH=/work/server -e HOME=/tmp -e FOTOS_DIR=/tmp/fotos-doc -e RESPALDOS_DIR=/tmp/respaldos-doc \
  -e BT_TRANSPORT=tcp -e BT_TCP_PORT=9100 $PY python -m btsync.servicio >/dev/null
sleep 8
echo "## 1. Registro de la cuenta del segundo teléfono (queda PENDIENTE) y aprobación"
python3 -I tools/fake_phone.py --host 127.0.0.1 --port 9100 --seed 7 --cuenta operador.dos --uuid doc-phone-0002 --state-file /tmp/outbox-corte.json
aprobar
sleep 3
echo
echo "## 2. Envío interrumpido: el teléfono se mata (SIGKILL) a los 4 s, a mitad del lote"
timeout -s KILL 4 python3 -I tools/fake_phone.py --host 127.0.0.1 --port 9100 --seed 7 --cuenta operador.dos --uuid doc-phone-0002 --state-file /tmp/outbox-corte.json --delay-ms 60
echo "rc=$? (137 = terminado por SIGKILL)"
sleep 3
echo "Lo persistido antes del corte:"
sql '1,6p'
echo
echo "## 3. Reconexión: el teléfono reanuda desde el READY del servidor (mismo outbox)"
python3 -I tools/fake_phone.py --host 127.0.0.1 --port 9100 --seed 7 --cuenta operador.dos --uuid doc-phone-0002 --state-file /tmp/outbox-corte.json
echo "rc=$?"
sleep 70
echo
echo "## 4. Estado final: sin duplicados"
sql '1,22p'
docker rm -f servicio-tcp-doc >/dev/null 2>&1
