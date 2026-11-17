# Motion de las pantallas administrativas

Pantallas: Solicitudes, Empleados, Roles y permisos, Auditoría, Respaldos y Perfil (Sincronización es la referencia y no
se tocó). Pruebas: `desktop/tests/test_motion_admin.py`. Antecedentes: `07-motion-sincronizacion.md`.

## 1. Auditoría de la referencia (Sincronización)

No hay un segundo motor: toda la app anima con `widgets.animar` (un `QVariantAnimation` que salta al estado final con
`APP_SIN_ANIMACIONES=1`). Sobre él hay tres capas ya existentes, que se reutilizaron sin duplicar:

| Capa | Archivo | Qué aporta |
|---|---|---|
| Sistema de movimiento | `motion.py` | `Dur` (hover 150, pulsación 130, entrada 360, salida 240, estado 320, pantalla 420, expansión 440, gráfica 560 ms), `EfectoMovimiento` (opacidad, desplazamiento, escala y sombra en canales independientes), `entrar`/`salir`, `hacer_interactiva`, `cruzar_texto`, `desvanecer`, `sacudir`, `destello`, `dur`/`desp`/`decorativo` para movimiento reducido |
| Motion global | `motion_global.py` | curvas por intención (`ENTRADA` OutCubic, `SALIDA` InCubic, `ASENTAR` InOutCubic, `resorte` OutBack ≤1.15), `capturar_filas`/`revelar_filas` (filas que entran, salen, se mueven o cambian), `entrada_filas`, `cuenta_texto`, `desplegar`, `Aureola` (foco/hover de campos), `BarridoCarga`, `cambiar_pila`, `cruce_tema` |
| Acabado global | `vigilante.py` | presión de todos los botones, fundido de menús y diálogos, fundido de datos nuevos en tablas, «Sin datos» |
| Componentes de Sincronización | `sync_ui.py` | `Interpolador` (una sola animación para varios valores), `FlujoDatos` (único reloj ~30 fps), `Pildora`, `BotonPremium`, `Odometro`, `Esqueleto`, `EstadoVacio`, `entrada_escalonada`; ciclos solo con el widget visible y detenidos en `hideEvent` |

Entrada de Sincronización (`sync.py`): héroe con `entrar(dy=18, escala=0.965, Dur.EXPANSION)` a los 240 ms, luego cajas
a 520 ms + 80 ms por pieza (`dy=8`, `Dur.ENTRADA`). El estado cambia con `cruzar_texto`; los datos, con `Odometro` y
`Interpolador`. Limpieza: tokens por widget (`_entrada_tok`), `sip.isdeleted` en cada paso y el efecto se quita al terminar.
Movimiento reducido: `motion.reducido()` (`APP_MOVIMIENTO_REDUCIDO=1` o GNOME) acorta y casi elimina recorridos;
`APP_SIN_ANIMACIONES=1` salta a estados finales.

Problemas encontrados en el sistema compartido (corregidos):

- `motion.entrar` → `arrancar` escribía en un `EfectoMovimiento` ya destruido si otra capa reemplazaba el efecto antes
  de su turno.
- `motion_global.desplegar` hacía lo mismo con su efecto de opacidad (el banner de estado compite con `entrar` por el
  único efecto que admite un widget). Eso producía «wrapped C/C++ object … has been deleted» y arrastraba fallos entre
  pruebas con animaciones activas (10 fallos + 5 errores en `test_app.py` → 0 excepciones).

## 2. Piezas nuevas (justificadas)

Todas en `motion_global.py`, sin motor nuevo:

| Pieza | Para qué |
|---|---|
| `FilasVivas(tabla)` | Guarda clave y huella por fila: `capturar()` → cambiar la tabla → `revelar(antes, claves, huellas)`. Es el patrón de Inventario hecho reutilizable; instala el hover/selección con transición |
| `claves_unicas` | Dos filas con la misma clave se pisarían en la capa de filas |
| `entrada_cascada(piezas, tablas, extra)` | Coreografía de entrada de pantalla (la de Inventario generalizada). Salta piezas ocultas o con otro efecto en curso |
| `Actividad(padre, runner)` | Línea de 2 px que barre mientras el `QueryRunner` tiene trabajo real; espera 160 ms antes de aparecer (una consulta instantánea no parpadea) |
| `instalar_realces(*campos)` | `Aureola` en varios campos |
| `QueryRunner.trabajo` (`base.py`) | Señal con las consultas en curso: el indicador sigue al runner en lugar de contar por su cuenta (un resultado obsoleto descartado no llama a nadie) |
| `motion.destello(radio=…)` | El flash respeta las esquinas del widget y no hace nada sin animaciones |
| Tooltips (`vigilante.py`) | Fundido de 110 ms como los menús |

## 3. Por pantalla

| Pantalla | Entrada | Datos / filas | Interacción |
|---|---|---|---|
| Solicitudes | ayuda, estado, secciones y botones en cascada; filas reveladas | clave = usuario; aprobar/rechazar = la fila sale de su tabla y entra al historial (huella con el contenido) | realce del selector de rol, barrido de actividad, presión global |
| Empleados | ayuda, estado, filtros y acciones; filas reveladas | clave = usuario; filtrar solo mueve/oculta filas; suspender/reactivar cruza solo esa fila (huella con el estado) | realce de búsqueda y selectores, barrido de actividad |
| Roles y permisos | ayuda, estado y matriz | los 24 selectores conservan su identidad al refrescar (antes se reconstruían); lo que cambia se destella (verde; rojo si se revierte un guardado fallido) sin re-guardar | destello inmediato al cambiar un permiso, realce de selectores, barrido |
| Auditoría | ayuda, estado y filtros; filas reveladas | clave = contenido del registro (un registro histórico no cambia): al filtrar solo entran/salen filas, ninguna se reescribe ni reordena; un registro nuevo entra sin mover los demás | realce de filtros, barrido |
| Respaldos | ayuda, botones y controles; lista revelada | clave = archivo; el respaldo nuevo entra sin mover los demás | barrido en la tarjeta mientras crea, restaura o guarda (la interfaz no se bloquea; el resultado va a la Isla como antes), realce del campo de confirmación |
| Perfil (Administrador e Inventario) | descripción y tarjetas en cascada | mismo `PerfilView` para ambos roles: `set_sesion` decide qué se ve y la entrada solo anima lo visible | realce de contraseñas, sacudida de la tarjeta si el cambio se rechaza, destello verde si se acepta, fundido del avatar al cambiar/quitar la foto |
| Sincronización | sin cambios (referencia) | — | — |

Nada cambia reglas de negocio, permisos, autenticación, Oracle, Bluetooth, respaldos ni textos: los datos se escriben
completos y primero; la animación es una capa que se dibuja encima.

## 4. Pendiente / límites

- Verificación visual: solo con fotogramas offscreen (no se abrió la app en una pantalla real).
- El selector segmentado de Perfil (tema/idioma) sigue cambiando al instante; un resalte deslizante requeriría una capa
  propia sobre el QSS.
- Sincronización no se refactorizó para consumir `FilasVivas`/`entrada_cascada`; sus componentes propios (`Interpolador`,
  `entrada_escalonada`) cumplen lo mismo para sus widgets a medida.
- Pruebas con animaciones activas: `test_charts_follow_the_system_scheme_when_it_changes` y
  `test_tras_restaurar_la_ventana_vuelve_al_login_con_el_aviso` fallan igual en `main` (preexistentes), así como 14
  pruebas que dependen de los datos de Oracle del entorno (`test_db`, `test_dashboard_*`).
