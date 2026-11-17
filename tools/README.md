# `tools/`: herramientas auxiliares

Scripts de desarrollo; no forman parte de la aplicación. Se ejecutan desde la raíz del repositorio.

| Herramienta | Para qué sirve | Uso |
|---|---|---|
| [`gen_seed.py`](gen_seed.py) | Genera de forma reproducible la semilla: `db/init/02_seed.sql` (conteo `ACTUAL`, 120 SKU, stock del sistema) y `tools/truth.json` (stock físico «real» por SKU) | `python tools/gen_seed.py --seed 42` |
| [`gen_demo.py`](gen_demo.py) | Genera `db/init/08_demo.sql`: cuentas, 13 meses de historia, sincronizaciones, dañados y errores para ver todas las pantallas | `python tools/gen_demo.py --seed 42` (usar la misma semilla que `gen_seed.py`) |
| [`truth.json`](truth.json) | Verdad física que cuenta el teléfono simulado | generado por `gen_seed.py` |
| [`fake_phone.py`](fake_phone.py) | **Teléfono simulado**: hace el conteo de `truth.json` y lo sincroniza por TCP como la APK (bandeja en un JSON, reanuda desde `READY`, ventanas de 50, go-back-N, corrige la hora con la del servidor) | `python tools/fake_phone.py --host 127.0.0.1 --port 9000 --seed 42` (con `BT_TRANSPORT=tcp`; `--help` lista `--dirty`, `--cuenta`, `--delay-ms`, …) |
| [`check_uml.py`](check_uml.py) | Comprueba que las clases de un diagrama de clases existen en el código (línea `' @code: ruta` del `.puml`); sale con código 1 si falta alguna | `python tools/check_uml.py docs/uml/01-clases-servidor.puml` |
| [`render_uml.sh`](render_uml.sh) | Renderiza `docs/uml/*.puml` a SVG y PNG en `docs/img/uml/` con PlantUML 1.2024.7 en Docker | `tools/render_uml.sh` |
| [`run_escritorio_wayland.sh`](run_escritorio_wayland.sh) | Abre la app de escritorio en una sesión Wayland sin XWayland, por la red interna de Compose | `tools/run_escritorio_wayland.sh` |

## Probar la sincronización sin celular

```bash
docker compose up -d --wait oracle
BT_TRANSPORT=tcp docker compose up -d bluetooth       # el servicio escucha TCP en 127.0.0.1:9000
python tools/fake_phone.py --host 127.0.0.1 --port 9000 --seed 42
```

La cuenta del teléfono simulado (`--cuenta`, por defecto `operador.demo`) debe estar `ACTIVO` en el PC; si el PC responde que está
pendiente, el script se detiene y pide aprobarla en **Solicitudes**. Resultado esperado: las lecturas aparecen en **Inventario** y **Sincronización** del escritorio.

Documentación relacionada: [`docs/demo.md`](../docs/demo.md) (guion de demo), [`docs/verificacion.md`](../docs/verificacion.md) y los diagramas en
[`docs/documentacion/diagramas/`](../docs/documentacion/diagramas/README.md).
