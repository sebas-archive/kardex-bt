# Checklist de aceptación por vista

Lista de comprobación para la corrida final. No fija resultados: la suite confirma cada punto.

## Global

- [ ] Hover, foco, pressed y disabled visibles en todos los controles.
- [ ] Feedback en menos de 100 ms; ninguna animación supera 500 ms.
- [ ] `APP_SIN_ANIMACIONES=1` no cambia ningún dato.
- [ ] Buscador de la vista con `Ctrl+F` y navegación con `Ctrl+1…9`.
- [ ] Drawer con backdrop y `Esc`.
- [ ] Toasts apilables, arrastrables y con acción.
- [ ] `F5` refresca y `Ctrl+B` contrae la barra.
- [ ] Header compacto al hacer scroll y progreso de scroll.
- [ ] Sidebar colapsable y auto-colapsada en ventanas angostas.
- [ ] Contenido centrado con ancho máximo y padding simétrico.
- [ ] Sin scroll horizontal no intencional.

## Acceso y estado de cuenta

- [ ] Login con usuario y contraseña (mostrar/ocultar), Enter y error genérico.
- [ ] Crear cuenta con correo obligatorio en PC e insignia de pendiente.
- [ ] «¿Olvidaste tu contraseña?»: el Administrador se recupera con su pregunta; Inventario deja la solicitud.
- [ ] Bloqueo de 30 s tras cinco intentos.
- [ ] Estado de cuenta con motivo y fecha; «Comprobar estado» en el móvil.

## Dashboard

- [ ] Avance continuo (SKUs con lectura vigente / total) y contados.
- [ ] Lecturas procesadas, errores y estado del batch.
- [ ] Gráfica de diferencia por categoría como referencia.
- [ ] Sin botón de cierre, sin insignia de estado y sin asignaciones.

## Inventario

- [ ] Columnas SKU, Producto, Categoría, Contada y Sistema.
- [ ] Buscador por SKU o nombre; sin filtros de otra dimensión.
- [ ] Cantidad contada vacía si no hay lectura.
- [ ] Exportar CSV con las cinco columnas, `;`, UTF-8 con BOM.
- [ ] Detalle con cantidad, operador, fecha UTC, vigente, nota y foto.
- [ ] Sin diferencia, porcentaje, clasificación ni etiquetas.

## Gráficas

- [ ] Seis gráficas: avance por categoría, contados vs. pendientes, lecturas por hora, por operador, mayores
      diferencias y unidades dañadas.
- [ ] Filtros por categoría y cantidad de SKU.
- [ ] Hover, resaltado y leyenda interactiva.

## Sincronización

- [ ] Estado del servicio, pausar/reanudar y última sincronización.
- [ ] Código de emparejamiento en grande con Aceptar/Rechazar cuando el teléfono lo pide.
- [ ] Procesar ahora y Reprocesar errores.
- [ ] Errores con filtro por motivo y alta de SKU desde el detalle (solo Administrador).
- [ ] Barra de progreso y lecturas recibidas.

## Solicitudes

- [ ] Cuentas pendientes y solicitudes de contraseña.
- [ ] Aprobar/rechazar con motivo de máximo 300 caracteres.
- [ ] Aviso si la solicitud ya fue resuelta.

## Empleados

- [ ] Fila con avatar, correo, nombre completo, rol e insignia de estado.
- [ ] Filtros por rol, estado y texto.
- [ ] Cambiar rol, suspender con motivo, reactivar, contraseña nueva (solo PC) y desvincular teléfono.
- [ ] Fila del Administrador deshabilitada para rol y estado.

## Roles y permisos

- [ ] Matriz de 12 módulos × 3 roles.
- [ ] Administrador con fila bloqueada; Inventario solo sus seis pantallas; Operador con Consulta en Notificaciones
      y Gestión en Sincronización.
- [ ] Guardado inmediato; si falla, error y relectura.

## Auditoría, Configuración y Respaldos

- [ ] Auditoría con filtros por fecha, módulo y texto; no se edita.
- [ ] Configuración solo con intervalo del lote y tamaño máximo de foto; carpeta de fotos de solo lectura.
- [ ] Respaldos: crear, restaurar con `RESTAURAR`, abrir carpeta y programar el diario.
- [ ] Restaurar pausa el servicio, guarda un respaldo previo y cierra la sesión.

## Notificaciones y Perfil

- [ ] Campana solo con acceso al módulo; filtro Todas / Sin leer y «Marcar todas».
- [ ] Perfil con inicial o foto y editor (rotar, zoom, cortar, vista previa).
- [ ] Eliminar foto con confirmación.
- [ ] Tema claro/sistema/oscuro e idioma español/inglés, aplicados al instante y guardados por cuenta.

## APK

- [ ] Acceso, Estado de cuenta, Inicio, Notificaciones, Catálogo, Contar, Contado, Pendientes, Sincronizar y Mi
      cuenta.
- [ ] Catálogo con búsqueda y sin cantidad del sistema.
- [ ] Contar con SKU, cantidad, dañados, nota y foto; aviso de SKU desconocido y de lectura repetida.
- [ ] Recuperación local con pregunta de seguridad; «Mi cuenta» sin cambio de contraseña.
- [ ] Tema e idioma por usuario; foto con editor.
