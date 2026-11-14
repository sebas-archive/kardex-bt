# Estados, movimiento y componentes interactivos

## 1. Tokens de movimiento

Definidos en `desktop/app/views/motion.py`:

| Token | Valor | Uso |
|---|---|---|
| `RAPIDO` | 120 ms | Feedback de hover, salida de chips, cierre de toasts |
| `NORMAL` | 200 ms | Drawer, acciones de tarjeta, tooltips |
| `LENTO` | 320 ms | Entrada de página, cambio de sidebar, barra de lote |
| Feedback | < 100 ms | Cambio de color/estado; no espera animación |
| Máximo | 500 ms | Ninguna transición lo supera |

Curvas: `OutCubic` para la mayoría, `OutQuint` para el drawer, `OutBack` para el snap de la barra de lote.

`APP_SIN_ANIMACIONES=1` (que fijan las pruebas y las capturas) hace que cada animación salte al estado final: el dato
nunca depende del dibujo.

## 2. Estados por componente

| Componente | Normal | Hover | Focus | Active/Pressed | Disabled |
|---|---|---|---|---|---|
| Botón | Fondo #111, borde #2E2E2E | Fondo #1C1C1C, borde #3A3A3A | Borde #10B981 | Fondo #262626 | Texto #6E6E6E, fondo #1C1C1C |
| Botón primario | #10B981, texto #04130E | #34D399 | Borde blanco 1 px | #0B8A62 | #1E3A32 |
| Ítem de sidebar | Texto #A3A3A3 | Fondo blanco 7 %, texto blanco | — | Activo: borde izq. #10B981 + gradiente verde 16 % | — |
| Tarjeta KPI | Borde #232323 | Borde #2F6B57, sombra verde, cifra→detalle | — | — | — |
| Fila de tabla | Fondo alternado | Fondo blanco 4 % + acciones a la derecha | Fila seleccionada #10261F | — | — |
| Campo | Borde #2E2E2E | — | Borde 2 px #10B981 | — | — |
| Campo inválido | Borde #F87171 + ✕ | — | Borde 2 px #F87171 | — | — |
| Campo válido | Borde #10B981 + ✓ | — | Borde 2 px #10B981 | — | — |
| Chip | Fondo #111, borde #2E2E2E | #1C1C1C | — | Marcado: #10B981 | — |
| Toast | Fondo #262626, borde izq. de color | Pausa el cierre | — | Arrastre horizontal | — |
| Drawer | Panel #0F0F0F + backdrop difuminado | — | Foco atrapado en el panel | — | — |

## 3. Componentes nuevos

| Componente | Archivo | Qué hace |
|---|---|---|
| `TarjetaHover` | `components.py` | Elevación, glow, acciones rápidas que suben |
| `Drawer` | `components.py` | Panel lateral con backdrop difuminado y Esc/clic fuera |
| `Confirmacion` | `components.py` | Modal con «Entiendo», respiración del botón destructivo y shake |
| `TooltipRico` | `components.py` | Tooltip con título, cuerpo y filas; se fija con clic |
| `FiltrosActivos` / `ChipActivo` | `components.py` | Chips de filtros con entrada y salida animadas |
| `BarraLote` | `components.py` | Barra flotante de selección múltiple |
| `AccionesFila` | `components.py` | Acciones que se deslizan sobre la fila |
| `ScrollSuave` | `motion.py` | Rueda con inercia (190 ms) |
| `ProgresoScroll` | `motion.py` | Indicador vertical del borde derecho |
| `Diagrama` | `bluetooth_vivo.py` | Celular ↔ PC con paquetes y ondas |
| `BarrasTrafico` | `bluetooth_vivo.py` | Ecualizador de lecturas |
| `BotonReintentar` | `bluetooth_vivo.py` | Arco giratorio mientras reintenta |
| `LienzoFoto` | `foto.py` | Zoom/pan de la foto de evidencia |

## 4. Ejemplos de código

### 4.1 Drag & drop entre dos listas (Qt)

El escritorio no tiene un caso de negocio de arrastrar productos, así que no se fuerzan drops falsos. El patrón
queda documentado para una lista que lo admita:

```python
class ListaArrastrable(QListWidget):
    def __init__(self, aceptar_de: str, parent=None):
        super().__init__(parent)
        self.aceptar_de = aceptar_de
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

    def startDrag(self, acciones):
        item = self.currentItem()
        if item is None:
            return
        datos = QMimeData()
        datos.setData("application/x-producto", item.data(Qt.ItemDataRole.UserRole).encode())
        arrastre = QDrag(self)
        arrastre.setMimeData(datos)
        arrastre.setPixmap(self.grab(self.visualItemRect(item)))  # ghost
        arrastre.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, evento):
        if evento.mimeData().hasFormat("application/x-producto"):
            self.setProperty("drop", True)          # borde punteado animado por QSS
            self.style().unpolish(self); self.style().polish(self)
            evento.acceptProposedAction()

    def dropEvent(self, evento):
        self.setProperty("drop", False)
        self.style().unpolish(self); self.style().polish(self)
        datos = evento.mimeData().data("application/x-producto").data().decode()
        self.addItem(datos)                          # aquí iría la llamada a Oracle
        motion.destello(self)                        # flash del destino
        evento.acceptProposedAction()
```

Regla del encargo: el origen se atenúa al 50 % (`QGraphicsOpacityEffect`), el ghost sigue al cursor y el drop zone
se ilumina; al soltar, snap con `OutBack` y flash.

### 4.2 Swipe actions en tarjetas (Kotlin)

```kotlin
class SwipeAccionesCallback(
    private val alDeslizarDerecha: () -> Unit,
    private val alDeslizarIzquierda: () -> Unit
) : ItemTouchHelper.SimpleCallback(0, ItemTouchHelper.LEFT or ItemTouchHelper.RIGHT) {

    override fun onMove(rv: RecyclerView, vh: RecyclerView.ViewHolder, target: RecyclerView.ViewHolder) = false

    override fun onSwiped(vh: RecyclerView.ViewHolder, direccion: Int) {
        when (direccion) {
            ItemTouchHelper.RIGHT -> alDeslizarDerecha()
            ItemTouchHelper.LEFT -> alDeslizarIzquierda()
        }
    }

    override fun onChildDraw(c: Canvas, rv: RecyclerView, vh: RecyclerView.ViewHolder,
                             dx: Float, dy: Float, accion: Int, activo: Boolean) {
        val vista = vh.itemView
        val icono = if (dx > 0) R.drawable.ic_check else R.drawable.ic_close
        pintarFondo(c, vista, dx, if (dx > 0) Color.GREEN else Color.RED, icono)
        super.onChildDraw(c, rv, vh, dx, dy, accion, activo)
    }
}

// Umbral: al pasar 0,35 del ancho se dispara el háptico Medium y se anima el snap.
```

### 4.3 Gráficas con drill-down (Qt + pyqtgraph)

```python
hover = HoverBarras(plot, fmt_cop, al_clic=lambda etiqueta, valor: ventana._drill("categoria", etiqueta))
proxy = pg.SignalProxy(plot.scene().sigMouseMoved, rateLimit=30, slot=hover._mover)
```

- `_mover` mapea la escena a datos, elige la barra más cercana y muestra un `QLabel` junto al cursor.
- `_resaltar` cambia los brushes: la barra activa a 255 y las demás a 88 de alfa.
- `_clic` emite la etiqueta; la ventana navega a Inventario y aplica el filtro.
- La dona y la barra segmentada ocultan series al hacer clic en su leyenda.

### 4.4 Bottom sheets con varias alturas (Kotlin)

```kotlin
val sheet = findViewById<BottomSheet>(R.id.sheet)
val behavior = BottomSheetBehavior.from(sheet)
behavior.state = BottomSheetBehavior.STATE_COLLAPSED
behavior.peekHeight = 180.dp
behavior.isDraggable = true
behavior.addBottomSheetCallback(object : BottomSheetCallback() {
    override fun onSlide(bottomSheet: View, offset: Float) {
        backdrop.alpha = (offset.coerceIn(0f, 1f) * 0.6f)   // blur/veil progresivo
        if (offset > 0.7f) vibrar(Haptic.MEDIUM)            // al acercarse a full
    }
    override fun onStateChanged(bottomSheet: View, newState: Int) {
        if (newState == BottomSheetBehavior.STATE_HIDDEN) cerrar()
    }
})
```

Snap a peek/half/full con `peekHeight`, `halfExpandedRatio` y `expandedOffset`. El asa es la única zona que captura
el arrastre para que el scroll interno no se pelee con el gesto.

### 4.5 Edición inline en tablas (Qt)

```python
class ModeloEditable(QAbstractTableModel):
    def flags(self, index):
        return Qt.ItemFlag.ItemIsEditable | super().flags(index)

    def setData(self, index, valor, rol=Qt.ItemDataRole.EditRole):
        if rol != Qt.ItemDataRole.EditRole:
            return False
        # validar y persistir; si falla, dejar el valor anterior y emitir aviso
        self.dataChanged.emit(index, index, [rol])
        return True

tabla.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
tabla.setItemDelegateForColumn(2, DelegadoNumero(tabla))
```

En este proyecto las cantidades conciliadas son de solo lectura por diseño (las lecturas vienen del celular); el
doble clic abre el detalle en vez de editar. La edición inline se usa donde el dominio lo permite: formularios de
Empleados y campos de Configuración.

## 5. Reglas que se respetan

- Ninguna animación bloquea la interacción: todas son `QVariantAnimation` sobre propiedades, no `sleep`.
- El dato se actualiza antes de animar (`texto()`, `filas()`, `segmentos()`...).
- El foco siempre es visible y `Esc` cierra cualquier capa.
- Los estados vacíos, de carga y de error están centrados y tienen acción siguiente.
