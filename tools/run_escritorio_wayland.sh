#!/usr/bin/env bash
# Abre la app de escritorio en esta sesión Wayland, usando la red interna de Compose para llegar a Oracle.
#
#   tools/run_escritorio_wayland.sh
#
# Por qué no usa `docker compose up app`: ese servicio publica Oracle en 127.0.0.1 y en este equipo el puerto
# 1521 quedó atascado. Por eso la app corre en la red `inventario-bt_default` y habla con `oracle:1521`.
# El Bluetooth no hace falta para abrir la ventana: la app lee el estado del servicio en Oracle.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

: "${WAYLAND_DISPLAY:?No hay WAYLAND_DISPLAY: abre la sesión gráfica Wayland (o usa XWayland y el compose normal)}"
: "${XDG_RUNTIME_DIR:?No hay XDG_RUNTIME_DIR: abre la sesión gráfica Wayland}"

if [ ! -f .env ]; then
  echo "Falta .env. Cópialo de .env.example:  cp .env.example .env" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
. ./.env
set +a
: "${DB_USER:?Falta DB_USER en .env}"
: "${DB_PASSWORD:?Falta DB_PASSWORD en .env}"

if ! docker image inspect inventario-bt-app:latest >/dev/null 2>&1; then
  echo "Falta la imagen de la app. Constrúyela una vez con:  docker compose build app" >&2
  exit 1
fi

# Icono en la barra de tareas: en Wayland el compositor lo busca por el app_id ("kardex-bt") en un
# .desktop del equipo; el contenedor no puede aportarlo. Se instala en ~/.local/share (solo del usuario).
DATOS="${XDG_DATA_HOME:-$HOME/.local/share}"
mkdir -p "$DATOS/icons/hicolor/scalable/apps" "$DATOS/applications"
cp desktop/app/recursos/icono.svg "$DATOS/icons/hicolor/scalable/apps/kardex-bt.svg"
cat > "$DATOS/applications/kardex-bt.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Kardex
Comment=Gestión de inventario con Bluetooth y Oracle
Exec=$RAIZ/tools/run_escritorio_wayland.sh
Icon=kardex-bt
Terminal=false
Categories=Office;
StartupWMClass=kardex-bt
EOF
command -v update-desktop-database >/dev/null && update-desktop-database "$DATOS/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATOS/icons/hicolor" 2>/dev/null || true

docker compose up -d oracle >/dev/null
for _ in $(seq 1 60); do
  estado="$(docker inspect -f '{{.State.Health.Status}}' inventario-bt-oracle-1 2>/dev/null || true)"
  [ "$estado" = "healthy" ] && break
  sleep 2
done

IMAGEN=inventario-bt-app-wayland:latest
if ! docker image inspect "$IMAGEN" >/dev/null 2>&1; then
  echo "Añadiendo el soporte de Wayland a la imagen (una sola vez)…"
  # BuildKit falla en este host por el directorio de actividad; el builder clásico sí funciona.
  DOCKER_BUILDKIT=0 docker build -t "$IMAGEN" - <<'EOF'
FROM inventario-bt-app:latest
USER root
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libwayland-cursor0 \
 && rm -rf /var/lib/apt/lists/*
USER 1000
EOF
fi

if docker ps --format '{{.Names}}' | grep -qx app-wayland; then
  echo "La app ya está abierta (contenedor app-wayland)."
  exit 0
fi
docker rm -f app-wayland >/dev/null 2>&1 || true

# El socket Wayland y el runtime del usuario se montan tal cual: el contenedor corre con UID 1000.
# Se lanza en segundo plano para que la ventana siga abierta aunque cierres esta terminal.
docker run -d --rm --name app-wayland --network inventario-bt_default \
  -e QT_QPA_PLATFORM=wayland \
  -e WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
  -e XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  -e DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus" \
  -e DB_DSN=oracle:1521/XE \
  -e DB_USER="$DB_USER" \
  -e DB_PASSWORD="$DB_PASSWORD" \
  -e ORA_SDTZ=+00:00 \
  -e PYTHONPATH=/work/server:/work/desktop \
  -e HOME=/tmp \
  -e XDG_CACHE_HOME=/tmp/.cache \
  -e XDG_CONFIG_HOME=/work/config \
  -e FOTOS_DIR=/work/fotos \
  -e RESPALDOS_DIR=/work/respaldos \
  -v "$RAIZ":/work \
  -v "$XDG_RUNTIME_DIR":"$XDG_RUNTIME_DIR" \
  -w /work "$IMAGEN" /bin/sh /work/docker/run-app.sh >/dev/null

sleep 2
if docker ps --format '{{.Names}}' | grep -qx app-wayland; then
  echo "App abierta en la ventana de tu escritorio (contenedor app-wayland)."
  echo "Para ver sus mensajes:  docker logs -f app-wayland"
  echo "Para cerrarla:          cierra la ventana o:  docker rm -f app-wayland"
else
  echo "La app terminó al arrancar. Últimos mensajes:" >&2
  docker logs app-wayland 2>&1 | tail -40 >&2 || true
  exit 1
fi
