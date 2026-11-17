#!/usr/bin/env bash
# Pruebas unitarias de la APK (JVM, sin dispositivo) en el contenedor de compilación del proyecto (JDK 17 + Gradle).
# Equivale a: docker compose --profile build run --rm apk-build ./gradlew testDebugUnitTest --rerun-tasks
# Uso (raíz del repositorio): docs/documentacion/herramientas/pruebas_android.sh
set -uo pipefail
REPO=$(pwd)
LOG=docs/documentacion/anexos/registros/pruebas_android.txt
date -u +"inicio %Y-%m-%dT%H:%M:%SZ" > "$LOG"
docker run --rm --network host --user "$(id -u):$(id -g)" -v "$REPO":/work -v inventario-bt_gradle-home:/gradle-home \
  -w /work/mobile inventario-bt-apk-build ./gradlew testDebugUnitTest --rerun-tasks --console=plain >> "$LOG" 2>&1
echo "EXIT=$?" >> "$LOG"
python3 -I - >> "$LOG" 2>&1 <<'PY'
import glob, xml.etree.ElementTree as ET
t = f = e = s = 0
for p in sorted(glob.glob("mobile/app/build/test-results/testDebugUnitTest/*.xml")):
    r = ET.parse(p).getroot()
    t += int(r.get("tests")); f += int(r.get("failures")); e += int(r.get("errors")); s += int(r.get("skipped"))
    print(f'{r.get("name"):70s} tests={r.get("tests")} fallos={r.get("failures")} errores={r.get("errors")}')
print(f"TOTAL tests={t} failures={f} errors={e} skipped={s}")
PY
echo terminado >> "$LOG"
