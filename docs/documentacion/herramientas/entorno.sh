#!/usr/bin/env bash
# Registra el estado del entorno de ejecución (contenedores, versiones). Uso: entorno.sh > anexos/registros/entorno.txt
echo "# Entorno de ejecución — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
echo "## Contenedores del proyecto (docker ps)"
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' | grep -E "NAMES|inventario-bt|oracle-limpio"
echo
echo "## Versiones dentro de la imagen de la aplicación de escritorio (inventario-bt-app)"
docker run --rm --entrypoint sh inventario-bt-app -c 'python --version; pip list 2>/dev/null | grep -i -E "^(pyqt6 |pyqtgraph|oracledb|dbus-fast|pytest |pytest-qt|numpy)"; ls /opt/oracle'
echo
echo "## Oracle Database"
docker exec inventario-bt-oracle-1 sh -c 'echo "SELECT banner FROM v\$version WHERE ROWNUM=1;" | sqlplus -s / as sysdba' 2>&1 | head -6
echo
echo "## Host"
uname -srm
docker --version
