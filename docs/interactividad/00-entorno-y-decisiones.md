# Interactividad: entorno, decisiones y alcance

Documentación de la interacción del sistema final: escritorio PyQt6 + pyqtgraph sobre Linux, dentro de Docker y
dibujando por X11/XWayland; APK Android en Kotlin con Jetpack Compose. El conteo es continuo y no hay asignaciones
ni cierre.

## 1. Plataforma

- **Escritorio:** `desktop/`, PyQt6 + pyqtgraph, contenedor `app` con `network_mode: host`, socket X11 y D-Bus del
  host. En Wayland sin XWayland se usa `tools/run_escritorio_wayland.sh`.
- **Móvil:** `mobile/`, Kotlin + Jetpack Compose (Material 3), Room para la bandeja y el catálogo, ZXing para el
  escáner. Funciona sin red; las cuentas y la contraseña viven en el teléfono.
- **Servicio Bluetooth:** otro proceso (`btsync.servicio`) que sigue recibiendo con la ventana cerrada. La app de
  escritorio no habla Bluetooth: lee `SERVICIO_BT` y lo pausa o reanuda.
- **Oracle:** XE 11g en el contenedor `oracle`; el batch PL/SQL concilia `ACTUAL`.

## 2. Alcance de esta carpeta

| Documento | Qué contiene |
|---|---|
| [01-atajos.md](01-atajos.md) | Todos los atajos del escritorio. |
| [02-gestos-movil.md](02-gestos-movil.md) | Especificación táctil de la APK. |
| [03-estados-y-componentes.md](03-estados-y-componentes.md) | Tokens de motion, estados y componentes. |
| [04-flujos.md](04-flujos.md) | Flujos por pantalla. |
| [05-checklist-por-vista.md](05-checklist-por-vista.md) | Criterios de aceptación por vista. |
| [06-verificacion.md](06-verificacion.md) | Comandos y criterios de verificación. |

## 3. Decisiones de interacción

- Toda acción responde en menos de 100 ms; ninguna animación bloquea más de 500 ms.
- El dato se actualiza antes de animar: `APP_SIN_ANIMACIONES=1` salta al estado final y las pruebas no dependen del
  dibujo.
- El foco siempre es visible y `Esc` cierra cualquier capa (drawer, modal, visor de fotos).
- Las cantidades del inventario son de solo lectura: la fuente es el teléfono.
- Los estados vacíos, de carga y de error están centrados y ofrecen la acción siguiente.
- El tema (claro, sistema, oscuro) y el idioma (español, inglés) son de cada usuario y se aplican al instante.
- La foto de perfil se edita antes de guardar (rotar, zoom, cortar, vista previa); el avatar se muestra circular y
  el archivo se guarda cuadrado.
