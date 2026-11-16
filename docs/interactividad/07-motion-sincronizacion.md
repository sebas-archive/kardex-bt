# Motion design de «Sincronización»

Código: `desktop/app/views/motion.py` (sistema compartido), `sync_ui.py` (componentes) y `sync.py` (cableado a eventos
reales). Pruebas: `desktop/tests/test_sync_motion.py`.

## Sistema (`motion.py`)

| Pieza | Qué hace |
|---|---|
| `Dur` | Duraciones por naturaleza: hover 150, pulsación 130, entrada 360, salida 240, estado 320, pantalla 420, expansión 440, gráfica 560 ms. |
| `curva_resorte(sobre)` | `OutBack` con rebasamiento sutil (spring) para expansión y recuperación tras pulsar. |
| `reducido()` / `dur()` / `desp()` / `decorativo()` | Movimiento reducido (`APP_MOVIMIENTO_REDUCIDO=1` o animaciones apagadas en GNOME): sin partículas, ondas, paquetes ni ciclos continuos; transiciones esenciales más cortas y casi sin recorrido. |
| `EfectoMovimiento` | Un único `QGraphicsEffect` (opacidad, desplazamiento, escala, sombra ambiental) para entrada, hover y pulsación. Se instala solo mientras hay movimiento. |
| `entrar()` | Fade-in + desplazamiento (+ expansión) con retardo; re-entrante y seguro si el widget se oculta o se destruye. |
| `hacer_interactiva()` | Hover (elevación + sombra) y pulsación (compresión + spring) sin tocar el layout. |
| `cruzar_texto()` | Cross-fade de etiquetas. |
| `desvanecer()` | Fundido que reemplaza a uno anterior sobre el mismo widget (antes se pisaban y Qt abortaba). |

`sync_ui.Interpolador` lleva varios valores con nombre (color, nivel, escala…) hacia nuevos destinos con **una sola**
animación; no crea nada si el destino no cambió, así que un refresco de datos no recrea animaciones.

## Eventos reales → movimiento

| Evento real | Movimiento |
|---|---|
| `recibidos` del servicio sube en `status_changed` | `FlujoDatos.emitir_lecturas(n)`: hasta 8 paquetes Android → Bluetooth → PC; pulsos en los nodos. |
| `contadores.procesadas` sube al leer Oracle | `confirmar_escritura(n)`: paquetes PC → Oracle y destello en Oracle. |
| Estado `CONECTADO` / `PROCESANDO` | Pulso en Android / PC. |
| Estado `PAUSADO`/`PAUSANDO` | Ondas, partículas y halo se apagan progresivamente; enlaces a gris; paquetes se apagan. |
| Clic en «Reanudar servicio» | Botón con spinner, icono en «conectando», luz y ondas al confirmarse; si falla, se revierte y el botón marca error. |
| `ERROR` (`BATCH:` o servicio) / Oracle caído | Tramo en rojo con destello, insignia en el nodo, paso del stepper en rojo con shake. |
| Filas que salen de `V_ERRORES_CAPTURA` | Fila en verde con check dibujado y luego fade; las que siguen con error parpadean en rojo. |

No hay tráfico simulado: sin eventos no hay paquetes ni reloj. Mientras un enlace está `activo` (el servicio está
recibiendo de verdad) se mantiene un goteo ambiental cuya cadencia sale de la tasa real de lecturas por minuto.

## Rendimiento

Un único reloj de ~30 fps en `FlujoDatos` (con `QElapsedTimer`, velocidad independiente de los fotogramas) y ciclos
`QVariantAnimation` que solo corren con el widget visible; todos se detienen en `hideEvent`. Pintado medido (offscreen):
flujo con 11 paquetes ≈ 1,6 ms, icono con ondas y partículas ≈ 0,7 ms, etapas ≈ 0,5 ms, gráfica ≈ 0,7 ms por fotograma.
Las consultas a Oracle siguen en `QueryRunner` (hilos) y entregan por señal.

## Pendiente / límites conocidos

- El cambio de tema claro/oscuro repinta al instante (no hay transición global de tema).
- La preferencia de movimiento reducido del sistema solo se lee en GNOME (`gsettings`); en otros escritorios, usar
  `APP_MOVIMIENTO_REDUCIDO=1`.
- El sistema global de la Isla no se tocó: ya anima entrada, transformación de contenido (spinner → check) y salida.
