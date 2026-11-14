# Verificación integral — task-6

Fecha: 2026-11-14 17:42 -05:00 (America/Bogota) / 22:42 UTC.
Repositorio: `/home/t1an/movil oracle bluetooth`, HEAD `f7cd59e` más los cambios sin confirmar de la implementación.
Entorno: los tres servicios de `docker-compose.yml` (Oracle XE 11g, `bluetooth`, `app`) y el perfil `apk-build`
para Android. El verificador no editó código de producto; este informe es el único archivo creado por él.

## 1. Suites

Se ejecutaron en serie, nunca en paralelo.

### Servidor

```text
docker compose run -T --rm pybase pytest server/tests -v
EXIT=0
216 passed in 49.70s
```

(Reejecutada a pedido del Lead; la corrida anterior dio 216 en 51.24 s.)

### Escritorio

```text
docker compose run -T --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -v
EXIT=0
166 passed in 58.46s
```

Reejecutada tras la corrección de F1 (task-7). Antes de la corrección dio 164 en 58.08 s y 164 en 59.90 s; los
dos tests nuevos son de Empleados (`desktop/tests/test_usuarios_views.py`).

### Móvil

La primera corrida no ejecutó pruebas (`testDebugUnitTest UP-TO-DATE`), así que se forzó la reejecución:

```text
docker compose --profile build run -T --rm apk-build ./gradlew testDebugUnitTest --rerun-tasks
EXIT=0
BUILD SUCCESSFUL in 44s
```

Resultado leído de `mobile/app/build/test-results/testDebugUnitTest/*.xml`:

```text
tests=110 failures=0 errors=0 skipped=0
```

El contenedor `apk-build` usa `eclipse-temurin:17-jdk-jammy` (JDK 17), como exige la tarea.

## 2. Base de datos

Consultas con `oracledb` en modo thick dentro de `pybase` (Oracle 11g exige Instant Client).

| Comprobación | Resultado |
|---|---|
| `conteos` | 1 fila: `ACTUAL`, `Conteo continuo`, `ABIERTO` |
| `productos` | 60 |
| `stock_sistema` | 60 |
| `conciliacion` | 60 (0 con `cant_contada`; todas sin lectura) |
| `permisos` | 36 = 3 roles × 12 módulos |
| `configuracion` | 6 claves |
| `servicio_bt` | 1 fila, `ESPERANDO_EMPAREJAMIENTO`, `pausado='N'`, latido vigente |
| `captura_transito` / `registros_procesados` | 0 / 0 (limpios) |
| `usuarios` | 0 (la primera cuenta se crea en el primer uso) |

Matriz de permisos comprobada en Oracle:

- `ADMIN`: `GESTION` en los doce módulos.
- `INVENTARIO`: `GESTION` en `dashboard`, `inventario`, `graficas`, `sync`, `notificaciones`, `perfil`; `NINGUNO` en el resto.
- `OPERADOR`: `CONSULTA` en `notificaciones`, `GESTION` en `sync`, `NINGUNO` en el resto.

Configuración vigente:

```text
fotos.dir=/work/fotos          fotos.max_mb=2        lote.intervalo_min=1
respaldos.auto=S               respaldos.conservar=7 respaldos.hora=23:00
```

Esquema: `USUARIOS` tiene `CORREO`, `PREGUNTA`, `RESPUESTA_HASH`, `FOTO`, `TEMA`, `IDIOMA` y `CLAVE_MOTIVO`;
`CONCILIACION` no tiene `CLASIFICACION` ni `VALOR_DIFERENCIA`. No existen tablas de almacenes, tareas,
diferencias, movimientos, ajustes, existencias ni categorías.

Contenedores:

```text
inventario-bt-oracle-1      Up ... (healthy)   127.0.0.1:1521->1521/tcp
inventario-bt-bluetooth-1   Up
inventario-bt-app-1         Up                  (ventana del escritorio abierta)
```

El servicio Bluetooth se reanuncia cada 120 s; el log «ventana cerrada» se refiere a esa ventana de
visibilidad, no a la ventana del escritorio, y vuelve a registrarse de inmediato.

## 3. E2E mínimo del batch

Se insertó una línea `REC` cruda en `captura_transito` (el servicio guarda la línea **sin** el CRC; se comprobó
que `server/btsync/session.py` recorta el `*CRC` antes de `insert_staging`). Después se llamó
`pkg_batch.procesar_pendientes('MANUAL')`:

```text
REC|1|1794695267882|ACTUAL|7701234000001|21|verificador|e2e aceptacion|
stock antes: 18
staging: PROCESADO, sin error
registros_procesados: 7701234000001, 21, verificador, vigente='S'
conciliacion: cant_sistema=18, cant_contada=21, diferencia=3, diferencia_pct=16.67
```

Limpieza en el mismo script: se borraron el registro y la fila de staging, se borró el `log_batch` de la corrida,
se recalculó `conciliacion` y se verificó:

```text
staging restante: 0
registros restantes: 0
conciliacion del SKU: cant_contada=NULL
conciliacion con lectura: 0
```

(Un primer intento incluyó el CRC en `datos_raw` y el batch lo rechazó con `DANADOS_INVALIDO`; es el
comportamiento esperado porque el CRC no forma parte de la línea que se deposita en staging. No es un fallo del
producto.)

## 4. Aceptación de la especificación

Evidencia: pruebas automáticas y código; no se confió en los informes de los implementadores.

| # | Requisito | Evidencia | Resultado |
|---|---|---|---|
| 1 | Barra del Administrador en orden exacto, Perfil en el pie | `desktop/tests/test_app.py::test_admin_sidebar_exact_order_and_profile_at_the_footer` | Pasa |
| 2 | Barra de Inventario en orden exacto | `test_inventory_sidebar_exact_order` | Pasa |
| 3 | Sin Tareas, Diferencias, Movimientos, Ajustes, Existencias, Categorías ni Almacenes | `test_no_removed_screens_are_registered`; `desktop/app/views/` sin esas vistas; Oracle sin esas tablas | Pasa |
| 4 | Dashboard continuo, sin botón Cerrar conteo ni insignia | `test_dashboard_views.py::test_no_hay_boton_de_cierre_ni_insignia`; `dashboard.py` | Pasa |
| 5 | Inventario de 5 columnas, sin diferencia, porcentaje ni clasificación | `test_inventario_views.py::test_cinco_columnas_y_sin_diferencia`; `COLUMNAS == ("SKU","Producto","Categoría","Contada","Sistema")` | Pasa |
| 6 | Empleados con avatar, correo, nombre, rol e insignia; fila Admin deshabilitada; cuentas del móvil suspendibles | `test_users_table_shows_avatar_email_name_role_and_badge`; `test_usuarios_views.py::test_movil_se_suspende_con_motivo_y_se_reactiva`; `usuarios.py` | Pasa (F1 resuelto) |
| 7 | Solicitudes sin ADMIN, aprobación limitada por origen y motivo obligatorio | `test_requests_only_allow_inventory_for_pc_and_operator_for_mobile`; `auth.ROLES_POR_ORIGEN`; `pedir_motivo` | Pasa |
| 8 | Roles: 12 filas, Administrador bloqueado entero, sin «próximamente» | `test_roles_view.py::test_roles_muestra_los_doce_modulos` y `test_la_fila_del_administrador_esta_deshabilitada_entera` | Pasa |
| 9 | Configuración: intervalo del lote y tamaño de foto; carpeta de fotos solo lectura | `test_configuracion_views.py::test_muestra_los_valores_y_la_carpeta_de_fotos_sin_editar` | Pasa |
| 10 | Perfil: foto con editor, tema claro/sistema/oscuro e idioma es/en | `test_perfil.py`, `test_app.py::test_theme_and_language_apply_and_persist_in_the_session` | Pasa |
| 11 | Sincronización: errores con motivo, alta de SKU (solo Administrador), reprocesar | `test_sync_views.py::test_muestra_el_error_con_sku_y_motivo`, `test_alta_de_sku_solo_administrador`, `test_reprocesar_sin_errores_no_falla` | Pasa |
| 12 | Protocolo 5 y pseudo-catálogo `CATALOGO` | `PROTOCOL_VERSION = "5"`; `test_session.py::test_sesion_envia_un_pseudo_catalogo_y_todos_los_productos`; `Protocol.kt` VERSION 5 | Pasa |
| 13 | Correo obligatorio en cuentas del PC y opcional en el móvil | `test_auth.py` (validación), `test_access_has_email_and_show_password`; `USUARIOS.CORREO`; `AuthRepositoryTest.test_correo_es_opcional_y_solo_dato_de_perfil` | Pasa |
| 14 | Recuperación del Administrador con pregunta de seguridad | `test_auth.py::test_admin_recovers_with_the_security_question`; `auth.recuperar` | Pasa |
| 15 | Un solo Administrador; nunca se crea ni se promueve otro | `test_auth.py::test_there_is_never_a_second_admin`; `_validar_rol_para`; `ROLES_POR_ORIGEN` | Pasa |
| 16 | Operador: pregunta de seguridad y sin cambio de contraseña en Mi cuenta | `AuthRepositoryTest.test_forgot_password_resets_with_the_security_answer`; `PerfilScreen.kt` (sin cambio de contraseña); `CapturasTest.mi_cuenta` | Pasa |

## 5. Hallazgo F1 — resuelto

### El Administrador no podía suspender ni reactivar cuentas del móvil desde Empleados

- Detectado en `desktop/app/views/usuarios.py:185`: `self.btn_estado.setVisible(not movil)`.
- El Lead confirmó que era un bug de `desktop-core` (task-7), no de `desktop-views`.
- Corrección aplicada por `desktop-core`: el botón queda visible y habilitado para cuentas `MOVIL` e `INVENTARIO`,
  y deshabilitado solo para el Administrador; `btn_clave` sigue oculto para `MOVIL` (la contraseña del Operador no
  se reinicia desde el PC).
- Cobertura nueva: `desktop/tests/test_usuarios_views.py::test_movil_se_suspende_con_motivo_y_se_reactiva` y
  `test_administrador_no_se_puede_suspender`.
- Suite del escritorio tras la corrección: `166 passed in 58.46s`.
- Comprobación Qt offscreen posterior:

```text
op1 OPERADOR btn_estado visible= True enabled= True texto= Suspender tooltip= ''
  btn_clave visible= False btn_telefono visible= True
ana.gomez ADMIN btn_estado visible= True enabled= False texto= Suspender
  tooltip= 'El Administrador no se puede suspender.'
  btn_clave visible= True btn_telefono visible= False
```

## 6. Observaciones (no bloqueantes)

- O1. `JOB_PROCESAR_CAPTURAS` estaba `DISABLED` al iniciar la verificación (residuo probable de una corrida de
  pruebas anterior; `db/init/04_jobs.sql` lo crea habilitado y `server/tests/test_batch.py` verifica su
  definición). Se habilitó y quedó `TRUE/SCHEDULED` con `FREQ=MINUTELY;INTERVAL=1`. No se tocó código.
- O2. El botón «Cambiar rol» de Empleados queda siempre deshabilitado. Es consecuente con un solo Administrador y
  con roles fijados por origen (PC → Inventario, móvil → Operador), pero la documentación aún lista «cambiar rol»;
  conviene alinear la documentación o retirar el botón.
- O3. `web/` sigue como directorio no rastreado y no participa en `docker-compose.yml`; el sistema entregado es
  escritorio + APK. Es un residuo de la etapa anterior, no una dependencia.
- O4. `desktop/app/views/iconos.py` conserva iconos de las pantallas retiradas; es código muerto, no visible.

## 7. Veredicto

Las tres suites pasan (216 + 166 + 110), la base y el e2e del batch son correctos y los 16 puntos de aceptación
pasan, incluido F1 tras la corrección y la revalidación de `desktop-core`. **Veredicto: APTO.** La tarea `task-6`
queda completa.
