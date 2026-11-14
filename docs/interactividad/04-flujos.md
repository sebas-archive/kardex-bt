# Flujos interactivos por pantalla

Diagramas de la interacción (no del modelo de datos). El estado final de cada acción se ve sin esperar animación; los
tiempos son los del sistema de motion (`docs/interactividad/03-estados-y-componentes.md`).

## 1. Login

```mermaid
flowchart TD
    A[Abrir app] --> B{Foco en Usuario}
    B --> C[Escribir usuario]
    C --> D{3–30 y válido}
    D -- sí --> E[✓ verde]
    D -- no --> F[✕ roja + borde]
    E --> G[Escribir contraseña]
    F --> G
    G --> H[Enter o Entrar]
    H --> I{Cliente válido}
    I -- no --> J[Error inline + shake]
    J --> G
    I -- sí --> K[Botón: Entrando...]
    K --> L{Oracle}
    L -- error --> M[Mensaje rojo + shake + reintentar]
    L -- cuenta pendiente --> N[Pantalla de estado]
    L -- ok --> O[✓ Listo → Dashboard]
```

## 2. Dashboard: KPI y drill-down

```mermaid
flowchart LR
    A[Dashboard] --> B[Hover KPI]
    B --> C[La cifra se voltea al desglose]
    A --> D[Clic en KPI]
    D --> E[Drawer con detalle]
    A --> F[Hover en barra]
    F --> G[Tooltip + resaltado; resto al 60 %]
    A --> H[Clic en barra]
    H --> I[Abrir Inventario]
    I --> J[Tabla]
    E --> L[Esc o clic fuera: cerrar]
```

## 3. Inventario y tablas

```mermaid
flowchart TD
    A[Inventario] --> B[Buscar por SKU o nombre]
    B --> C[Debounce 250 ms]
    C --> D[Consulta fuera del hilo]
    D --> E[Tabla + resumen]
    E --> F[Clic en fila]
    F --> G[Selección]
    G --> H{Cuántas}
    H -- 1 --> I[Hover: acciones ver/copiar]
    H -- 2+ --> J[Barra flotante de lote]
    I --> K[Doble clic: lecturas del SKU]
    I --> L[Clic derecho: menú contextual]
    J --> M[Copiar selección]
    E --> N[Ctrl+C: TSV + destello]
    E --> O[Exportar CSV: progreso animado]
```

## 4. Sincronización / Bluetooth

```mermaid
flowchart TD
    A[Servicio activo] --> B[Diagrama: celular ↔ PC]
    B --> C{Estado}
    C -- esperando --> D[Ondas de radar]
    C -- conectado/recibiendo --> E[Paquetes viajando + ecualizador]
    C -- listo --> F[✓ y última sincronización]
    C -- error --> G[Botón Reintentar con arco giratorio]
    B --> H[Hover en un equipo]
    H --> I[Tooltip con rol]
    B --> J[Clic en un equipo]
    J --> K[Drawer con estado y lecturas]
    G --> L[Pausar/reanudar servicio]
```

## 5. Búsqueda en la vista

```mermaid
flowchart TD
    A[Ctrl+F] --> B[Foco en el primer buscador de la vista]
    B --> C[Escribir]
    C --> D[Debounce 250 ms]
    D --> E[Tabla / lista filtrada]
    E --> F[Esc: quitar el foco]
```

## 6. Solicitudes

```mermaid
flowchart TD
    A[Solicitudes] --> B[Lista: cuentas pendientes y solicitudes de contraseña]
    B --> C[Abrir una solicitud]
    C --> D{¿Qué es?}
    D -- cuenta --> E[Elegir el rol permitido y aprobar]
    D -- cuenta --> F[Rechazar con motivo obligatorio]
    D -- contraseña --> G[Aprobar o rechazar con motivo]
    E --> H[Toast + refresco]
    F --> H
    G --> H
    B --> I{¿Ya fue resuelta?}
    I -- sí --> J[Aviso: ya fue resuelta]
```

## 7. Detalle de inventario y foto

```mermaid
flowchart TD
    A[Inventario] --> B[Doble clic en un SKU]
    B --> C[Detalle de lecturas: cantidad, operador, fecha UTC, vigente y nota]
    C --> D[«Ver foto» si hay evidencia]
    D --> E[Visor: rueda zoom al cursor, arrastrar, doble clic o 0 ajustar, Esc cerrar]
    C --> F[Sin lecturas: «Sin lecturas para este SKU»]
```

## 8. Notificaciones y toasts

```mermaid
flowchart TD
    A[Evento] --> B[Toast abajo a la derecha]
    B --> C{Hover}
    C -- sí --> D[Pausa el cierre]
    C -- no --> E[Cierre a los 4,2 s]
    B --> F[Arrastrar en horizontal]
    F --> G{> 80 px}
    G -- sí --> H[Descartar]
    G -- no --> I[Volver a su sitio]
    A --> J[Campana con número]
    J --> K[Pantalla Notificaciones]
    K --> L[Ver: navega y marca leída]
    K --> M[Marcar todas]
```

## 9. Navegación y encabezado

```mermaid
flowchart LR
    A[Sidebar] --> B[Clic en sección]
    B --> C[Transición de 320 ms]
    C --> D[Header se expande]
    A --> E[Ctrl+B o botón]
    E --> F[Colapsar con animación]
    G[Scroll hacia abajo] --> H[Header compacto]
    H --> I[Scroll hacia arriba: se expande]
    J[Ventana < 1060 px] --> K[Sidebar automática a iconos]
```
