# Verificación

Comandos y criterios para comprobar el sistema final. La corrida completa la hace el Lead al cerrar la implementación; esta carpeta no fija resultados que no se hayan ejecutado.

## Suites

```bash
docker compose run --rm pybase pytest server/tests -v
```

```bash
docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -v
```

```bash
docker compose --profile build run --rm apk-build ./gradlew testDebugUnitTest
```

## UML

```bash
tools/render_uml.sh
docker compose run --rm pybase pytest server/tests/test_uml.py -v
```

El render deja un SVG por cada `.puml` en `docs/img/uml/`; la prueba comprueba que hay 22 diagramas, que el índice
los cita todos y que las clases de los diagramas 01–03 existen en el código.

## Criterios de interacción

- `APP_SIN_ANIMACIONES=1` no cambia ningún dato: solo evita la animación.
- Toda acción nueva responde en menos de 100 ms; ninguna transición supera 500 ms.
- El foco es visible y `Esc` cierra drawers, modales y el visor de fotos.
- Las tablas del inventario son de solo lectura y muestran cinco columnas: SKU, Producto, Categoría, Contada y
  Sistema.
- El cambio de tema e idioma se aplica en el acto y se conserva al volver a entrar con la misma cuenta.

## Capturas

Las capturas del escritorio se retiraron junto con la herramienta que las generaba. Las 28 capturas de la APK
están en [`../img/movil/`](../img/movil/) y corresponden a la interfaz final (Catálogo, Notificaciones y editor de foto
incluidos); se regeneran con `CapturasTest`.
