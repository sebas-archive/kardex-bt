# Atajos de teclado — escritorio

Los globales están registrados en `MainWindow` (`desktop/app/main.py`). Cada vista puede añadir los suyos; los
buscadores se enfocan con `Ctrl+F`.

## Globales

| Atajo | Acción | Dónde |
|---|---|---|
| `F5` | Volver a consultar Oracle | `main.py` |
| `Ctrl+B` | Contraer/expandir la barra lateral | `main.py` |
| `Ctrl+F` | Enfocar el primer buscador de la vista activa | `main.py` |
| `Ctrl+1` … `Ctrl+9` | Abrir la 1.ª … 9.ª sección visible del rol | `main.py` |

La barra lateral cambia de tamaño con el botón de la cabecera o `Ctrl+B`; en ventanas angostas se colapsa sola a
iconos. El Perfil se abre desde el pie, no con un número.

## Acceso

| Gesto | Acción |
|---|---|
| Autofoco al abrir | El cursor queda en «Usuario» |
| `Enter` en usuario/contraseña | Enviar el formulario |
| Escribir | Validación en vivo con ✓/✕ y borde verde/rojo |
| `Enter` en «Crear cuenta» | Confirmar el registro |

## Tablas (Inventario, Solicitudes, Empleados, Notificaciones, Errores)

| Gesto | Acción |
|---|---|
| Clic | Seleccionar fila |
| `Ctrl+clic` | Sumar/restar fila a la selección |
| `Shift+clic` | Seleccionar un rango |
| `Ctrl+C` | Copiar las filas seleccionadas como TSV |
| Doble clic | Abrir el detalle (lecturas del SKU en Inventario) |
| Clic derecho | Menú contextual con las acciones de la fila |
| Arrastrar el borde de una columna | Redimensionar |
| Arrastrar el encabezado | Reordenar columnas (Inventario) |
| Hover sobre una fila | Acciones rápidas a la derecha (ver/copiar) |

## Gráficas

| Gesto | Acción |
|---|---|
| Hover sobre barra/punto | Tooltip con etiqueta y valor; el resto se atenúa |
| Clic en barra | Drill-down cuando la vista lo admite |
| Clic en la leyenda (dona/barra) | Oculta/muestra la serie |
| Botón «Explorar» | Activa zoom con la rueda y paneo con el botón derecho |
| Botón «Seleccionar rango» | Arrastra sobre la línea para leer un periodo |
| Botón «Guardar imagen…» | Exporta las gráficas a PNG |

## Drawer, modales y toasts

| Gesto | Acción |
|---|---|
| `Esc` | Cerrar drawer/modal |
| Clic en el fondo | Cerrar drawer |
| Clic en una tarjeta KPI | Abrir el panel lateral con el desglose |
| Hover en un toast | Pausa el cierre automático |
| Arrastrar un toast en horizontal | Descartarlo (si supera 80 px) |

## Visor de fotos

| Gesto | Acción |
|---|---|
| Rueda | Zoom alrededor del cursor (12 % – 800 %) |
| Arrastrar | Mover la foto |
| Doble clic | Ajustar a la ventana |
| `+` / `−` | Zoom |
| `0` | Ajustar |
| `1` | 100 % |
| `Esc` | Cerrar |

## Notas de accesibilidad

- Todo control tiene nombre accesible: los botones usan texto y los iconos de la sidebar llevan `tooltip`.
- El foco es visible: QSS `:focus` con borde verde de 1–2 px.
- No hay atajos de una sola tecla que interfieran con la escritura.
- Ninguna acción destructiva se ejecuta sin confirmación o sin toast de «Deshacer».
