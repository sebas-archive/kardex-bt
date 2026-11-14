# Gestos táctiles — APK Android

Especificación para la app Kotlin (`mobile/`). En esta entrega se implementó el escritorio; esta hoja fija el contrato
para que la APK se sienta igual. Cada gesto indica su feedback visual y háptico.

## Convenciones

- Objetivo táctil mínimo: 48 dp.
- Un gesto nunca es la única forma de hacer algo: siempre hay un botón o menú equivalente.
- El swipe se descubre con un asa/chevron visible y un primer uso con pista textual.
- El háptico se dispara al **cruzar** el umbral, no en cada píxel.

## Login / crear cuenta

| Gesto | Acción | Feedback | Háptico |
|---|---|---|---|
| Tap en campo | Enfocar; el formulario sube para no quedar bajo el teclado | Borde primario + ícono de validación | Selection tick |
| Escribir | Validación en vivo | ✓ verde / ✕ roja con shake del campo inválido | — |
| Tap en «Entrar» | Enviar | Botón → spinner → ✓ y entrada con fade | Medium al éxito; Heavy al error |
| Long press en «¿Olvidaste tu contraseña?» | Copiar el texto de ayuda | Tooltip | Light |
| Swipe atrás | Volver al inicio | Slide horizontal | Light |

## Catálogo

| Gesto | Acción | Feedback | Háptico |
|---|---|---|---|
| Tap en producto | Abrir el detalle y pasar a Contar con el SKU puesto | Card se eleva; transición lateral | Light |
| Escribir en el buscador | Filtrar por SKU o nombre | Resultados con debounce | — |
| Long press | Copiar el SKU | Tooltip y destello | Long press |
| Pull to refresh | Pedir catálogo al PC (abre Sincronizar) | Logo del sistema girando | Light |
| Scroll | Lista con inercia | FAB de Contar aparece/desaparece según dirección | — |

## Contar / Escanear

| Gesto | Acción | Feedback | Háptico |
|---|---|---|---|
| Tap en «Escanear» | Abrir cámara | Overlay con marco y línea láser en loop | Light |
| Pinch sobre la cámara | Zoom | Zoom óptico/digital suave | — |
| Tap en la cámara | Enfocar en el punto | Círculo de enfoque animado | Light |
| Código detectado | Leer SKU y sumar | Flash verde + ✓ grande + card que sube con spring | Medium |
| Código no detectado | Avisar | Shake del marco + mensaje flotante | Heavy |
| Tap en flash | Encender/apagar | Ícono con toggle animado | Selection tick |
| Swipe izquierda en un renglón | Quitar la lectura | Fila se va; «Deshacer» 5 s | Medium |
| Long press en renglón | Editar cantidad / nota | Menú contextual | Long press |
| Tap en «Guardar» | Guardar sin red | Botón → spinner → ✓; contador de pendientes | Medium |

## Sincronizar

| Gesto | Acción | Feedback | Háptico |
|---|---|---|---|
| Tap en «Sincronizar» | Buscar el PC y enviar | Paquetes viajan del móvil al PC; barra con gradiente | Light |
| Tap en la barra | Expandir el detalle de registros enviados | Lista con stagger | Selection tick |
| Swipe down en el panel de detalle | Colapsar | Spring | Light |
| Éxito | Confirmar | ✓ grande + confetti + resumen | Heavy (doble pulso) |
| Fallo | Reintentar | Panel rojo sube desde abajo; shake | Heavy (triple pulso) |
| Tap en «Reintentar» de un registro | Reintento individual | Spinner local | Medium |
| Swipe izquierda en la cola | Descartar un registro | Se va con fade | Medium |

## Notificaciones

| Gesto | Acción | Feedback | Háptico |
|---|---|---|---|
| Tap | Abrir la pantalla relacionada (y marcarla leída) | Transición lateral | Light |
| Tap en «Marcar todas» | Marcar todos los avisos | Check + toast | Medium |

## Bottom sheets (todas las vistas)

| Gesto | Acción |
|---|---|
| Arrastrar el asa | Expandir/colapsar entre peek, half y full |
| Swipe up | Subir un nivel |
| Swipe down | Bajar un nivel; en peek, cerrar |
| Tap en backdrop | Cerrar |
| Scroll interno | No interfiere con el arrastre (solo el asa captura el gesto) |

## Guía de hápticos

| Tipo | Cuándo | Ejemplos |
|---|---|---|
| Light | Navegación, taps normales, hover táctil | Cambiar de tab, abrir una tarjeta |
| Selection tick | Cambios de estado pequeños | Toggle, chip, slider, flash |
| Medium | Acción completada con valor | Escaneo exitoso, guardado, sync, marcar leída |
| Heavy | Acción destructiva o error crítico | Eliminar foto, error de sync |
| Long press | Inicio de selección o menú | Mantener una tarjeta |
| Drag start/end | Agarrar/soltar | Reordenar prioridad, cola de sync |
| Success | Confirmación final | Doble pulso corto |
| Error | Fallo | Triple pulso corto |

## Estado de implementación

La APK (`mobile/`) ya tiene catálogo, escáner, bandeja, sincronización, foto, tema e idioma. Los gestos de swipe y
bottom sheets son la capa táctil de referencia; el escritorio cubre el equivalente con hover, clic derecho, atajos y
arrastre donde el dominio lo permite.
