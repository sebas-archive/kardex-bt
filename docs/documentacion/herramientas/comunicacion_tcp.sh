#!/usr/bin/env bash
# Demostración REAL del flujo de comunicación, contra el Oracle LIMPIO (oracle_limpio.sh, puerto 1522):
#   teléfono simulado (tools/fake_phone.py, mismo protocolo que la APK) --TCP--> servicio btsync.servicio --> Oracle --> batch.
# Se usa el transporte TCP (plan B documentado del proyecto) porque en este equipo no hay un teléfono emparejado.
# Salida íntegra en docs/documentacion/anexos/registros/comunicacion_tcp.txt.
# Uso (raíz del repositorio): docs/documentacion/herramientas/comunicacion_tcp.sh <ruta_a_.env>
set -uo pipefail
ENV_FILE=${1:?ruta del .env}
REPO=$(pwd)
OUT=docs/documentacion/anexos/registros/comunicacion_tcp.txt
set -a; . "$ENV_FILE"; set +a
BASE=(--rm --network host --user "$(id -u):$(id -g)" -v "$REPO":/work -w /work
  -e DB_DSN=127.0.0.1:1522/XE -e DB_USER="$DB_USER" -e DB_PASSWORD="$DB_PASSWORD" -e ORA_SDTZ=+00:00
  -e PYTHONPATH=/work/server -e HOME=/tmp -e FOTOS_DIR=/tmp/fotos-doc -e RESPALDOS_DIR=/tmp/respaldos-doc)
PY=inventario-bt-pybase
sql() { docker run "${BASE[@]}" --entrypoint python $PY docs/documentacion/herramientas/consulta_estado.py; }
phone() { docker run "${BASE[@]}" --entrypoint python $PY tools/fake_phone.py --host 127.0.0.1 --port 9100 "$@"; }
upd() { docker run "${BASE[@]}" --entrypoint python $PY -c "
import os, oracledb
oracledb.init_oracle_client()
c = oracledb.connect(user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], dsn=os.environ['DB_DSN'])
cur = c.cursor(); cur.execute(\"UPDATE usuarios SET estado='ACTIVO', rol='OPERADOR' WHERE usuario='operador.demo'\"); c.commit()
print('Administrador aprueba la cuenta operador.demo (equivale a «Aprobar» en Solicitudes):', cur.rowcount, 'fila')
"; }

exec > "$OUT" 2>&1
echo "# Evidencia de comunicación — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
docker rm -f servicio-tcp-doc >/dev/null 2>&1
docker run -d --name servicio-tcp-doc --network host --user "$(id -u):$(id -g)" -v "$REPO":/work -w /work \
  -e DB_DSN=127.0.0.1:1522/XE -e DB_USER="$DB_USER" -e DB_PASSWORD="$DB_PASSWORD" -e ORA_SDTZ=+00:00 \
  -e PYTHONPATH=/work/server -e HOME=/tmp -e FOTOS_DIR=/tmp/fotos-doc -e RESPALDOS_DIR=/tmp/respaldos-doc \
  -e BT_TRANSPORT=tcp -e BT_TCP_PORT=9100 $PY python -m btsync.servicio >/dev/null
sleep 8
echo; echo "## 1. Primera sincronización: la cuenta del teléfono aún no está aprobada"
phone --seed 42 --dirty --cuenta operador.demo --uuid doc-phone-0001; echo "rc=$?"
sql | sed -n '1,8p'
echo; echo "## 2. El Administrador aprueba la cuenta"
upd
echo; echo "## 3. Sincronización con reintento ante corte (outbox persistente) y lecturas con error"
phone --seed 42 --dirty --cuenta operador.demo --uuid doc-phone-0001 --state-file /tmp/outbox-doc.json --delay-ms 15; echo "rc=$?"
sleep 70
echo; echo "## 4. Estado de Oracle tras el batch"
sql
echo; echo "## 5. Registro del servicio (últimas líneas)"
docker logs --tail 25 servicio-tcp-doc 2>&1
docker rm -f servicio-tcp-doc >/dev/null 2>&1
