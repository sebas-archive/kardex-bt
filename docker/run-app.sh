#!/bin/sh
# Arranca la app de escritorio dejando un rastro de su arranque, para que no falle en silencio.
# Escribe cabecera, salida y final en $LOG_DIR/app.log (por defecto /work/logs) y, a la vez, en
# `docker compose logs app`.
# Propaga el código de salida de Python: con `restart: on-failure:5` en el compose, solo los fallos
# se reintentan solos (cerrar la ventana sale con 0 y la app queda parada).
set -u

LOG_DIR=${APP_LOG_DIR:-/work/logs}
LOG=$LOG_DIR/app.log
RC=/tmp/app-rc

mkdir -p "$LOG_DIR"
rm -f "$RC"

# Cap del log: con `restart: on-failure:5` cada caída deja varios arranques; si supera 5 MiB se
# conservan solo los últimos 1 MiB (suficiente para diagnosticar) en vez de crecer sin límite.
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 5242880 ]; then
  tail -c 1048576 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

# Delata el fallo clásico: si el shell que lanzó compose no exportó XAUTHORITY, el compose monta /dev/null
# como cookie (/tmp/.Xauthority-host) y Qt no puede autenticarse contra el servidor X.
cookie=$( [ -s "${XAUTHORITY:-/dev/null}" ] && echo ok || echo 'VACÍA (¿XAUTHORITY sin exportar en el shell que lanzó compose?)' )

echo "=== $(date -u '+%Y-%m-%dT%H:%M:%SZ') arranque uid=$(id -u) DISPLAY=${DISPLAY:-<sin definir>} XAUTHORITY=${XAUTHORITY:-<sin definir>} cookie=$cookie ===" | tee -a "$LOG"

( python -u -m app.main 2>&1; echo $? > "$RC" ) | tee -a "$LOG"

rc=$(cat "$RC" 2>/dev/null || true)
[ -n "$rc" ] || rc=1

echo "=== $(date -u '+%Y-%m-%dT%H:%M:%SZ') fin rc=$rc ===" | tee -a "$LOG"
exit "$rc"
