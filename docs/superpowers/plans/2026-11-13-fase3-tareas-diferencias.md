# Fase 3: tareas de conteo asignables y diferencias. Plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: superpowers:executing-plans (el usuario eligió Native en la Fase 1). Pasos con casillas (`- [ ]`).

**Meta:**
- Inventario crea tareas de conteo desde el escritorio y las asigna a un operador: almacén, productos e instrucciones.
- El operador las ve en «Mis tareas» del móvil y las cuenta.
- Las diferencias que resultan se revisan en una pantalla nueva del escritorio.

**Arquitectura:**
- **Una tarea es un conteo** (`conteos`) con columnas nuevas. Sus productos son las filas de `stock_sistema`, con la cantidad de `existencias` del almacén elegido (0 si no hay fila). Por eso el job, la conciliación y la pantalla Inventario no cambian.
- **El estado no se guarda; se calcula** al consultar, a partir de las lecturas, la conciliación y los errores del staging. El escritorio y el receptor usan la misma función, `btsync/tareas.py`; el escritorio ya importa `btsync`.
- **El protocolo pasa a la versión 4:** `CATTAREA` reemplaza a `CATCONTEO`, y se añaden `CATITEM` y `INICIO`.

**Stack:** Python 3.12, PyQt6, python-oracledb, Oracle XE 11g, y en el móvil Kotlin, Room y Compose.

**Spec:** la especificación pegada por el usuario (rol Inventario, secciones 5 «Gestión de tareas de conteo» y 10 «Diferencias reportadas»; rol Operador, sección 2 «Mis tareas»), más el boceto aprobado el 2026-11-13.

## Decisiones acordadas
- El boceto está aprobado (Tareas, Diferencias, Mis tareas) con los 7 estados y sus reglas.
- Diferencias solo permite «Revisada» y «Pedir recuento». Los ajustes, entradas, salidas y movimientos van en una fase nueva (3b).
- Una tarea tiene un solo operador. Solo se puede reasignar mientras está ASIGNADA.

## Restricciones globales
- **Estados** (valor → texto en pantalla):
  - `ASIGNADA` → «Asignada»
  - `EN_PROGRESO` → «En progreso»
  - `ENVIADA_PARCIALMENTE` → «Enviada parcialmente»
  - `SINCRONIZADA` → «Sincronizada»
  - `CON_DIFERENCIAS` → «Con diferencias»
  - `CON_ERROR` → «Con error»
  - `CERRADA` → «Cerrada»
- **Orden de las reglas** (gana la primera que se cumple):
  1. El conteo está `CERRADO` → `CERRADA`.
  2. Hay registros en `ERROR` en el staging → `CON_ERROR`.
  3. Todos los productos están contados (y hay al menos uno):
     - hay algún FALTANTE o SOBRANTE → `CON_DIFERENCIAS`;
     - si no → `SINCRONIZADA`.
  4. Llegó alguna lectura → `ENVIADA_PARCIALMENTE`.
  5. El móvil avisó que la empezó → `EN_PROGRESO`.
  6. Si no → `ASIGNADA`.
- **Contado:** un producto de la tarea con una lectura vigente, sin un recuento pedido después de esa lectura.
- **Permisos:**
  - Crear, reasignar o cerrar exige `GESTION` en `tareas`.
  - Marcar revisada o pedir recuento exige `GESTION` en `diferencias`.
  - Ver cada pantalla exige `CONSULTA` en su módulo.
  - `tareas` y `diferencias` entran en `permisos.EN_USO`.
- **Al crear una tarea solo se ofrecen:**
  - almacenes activos;
  - productos de categorías activas;
  - operadores con rol `OPERADOR` y estado `ACTIVO`.
- **Conteo ciego (D12):** el móvil nunca recibe la cantidad de sistema.
- **Conteos sin operador:** los que existían antes (`CONT-2026-11`) se siguen enviando a todos los móviles como conteo general. En Tareas no aparecen; en Diferencias, sí.
- **Pruebas:** toda consulta a Oracle va fuera del hilo de la interfaz.
  - Las pruebas de tareas usan IDs `TT-*` sobre las tablas reales y los borran al terminar, igual que el escenario `T-01`.
  - Almacenes, categorías, existencias y cuentas usan las fixtures `*_tst`.
- Sin commits hasta que el usuario los pida.
- **Comandos:**
  - Escritorio: `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -q`
  - Servidor: `docker compose run --rm app pytest server/tests -q`
  - Móvil: `docker compose --profile build run --rm apk-build ./gradlew testDebugUnitTest`

## Review Focus
1. **Tarea a medio contar con recuento pedido.** Pedir recuento de un producto ya contado lo devuelve a «no contado»: la tarea baja de `CON_DIFERENCIAS` a `ENVIADA_PARCIALMENTE`. La siguiente lectura de ese producto la cierra otra vez y su diferencia vuelve a «Pendiente».
2. **Reasignar o crear con datos que otro cambió.** Si otro usuario desactivó el operador o el almacén entre abrir el diálogo y guardar, sale un mensaje («ya no está activo»), no un ORA-.
3. **Lectura de un producto que no está en la tarea.** Entra como SOBRANTE (regla existente), se ve en Diferencias y no cambia el avance de la tarea (contados ≤ total).
4. **Móvil con catálogo v3 o sin tareas.** Al actualizarse, la base local migra (Room 2 → 3) sin perder las lecturas pendientes. Un operador sin tareas ve «No tienes tareas asignadas», no una pantalla en blanco.
5. **`INICIO` de una tarea ajena o cerrada.** El receptor lo ignora (no la marca) y no corta la sesión.

---

### Task 1: `btsync/tareas.py`: esquema, estado y catálogo por operador
**Archivos:**
- Crear: `server/btsync/tareas.py` y `db/init/08_tareas.sql` (el mismo DDL, para bases nuevas).
- Modificar: `server/btsync/store.py`, para que `catalog(usuario)` envíe las tareas de ese usuario más los conteos generales y para añadir `marcar_iniciada(usuario, id_tarea)`.
- Pruebas: `server/tests/test_tareas.py`, más `test_store.py` para el catálogo. `migrar()` se llama en la fixture de sesión de `server/tests/conftest.py`.

**Produce:**
- Constantes `ASIGNADA … CERRADA`, `ESTADOS` (en el orden de la tabla) y `NOMBRE_ESTADO`.
- `estado_tarea(cerrada: bool, total: int, contados: int, lecturas: int, diferencias: int, errores: int, iniciada: bool) -> str`: función pura con el orden de las restricciones globales.
- `@dataclass(frozen=True) ResumenTarea(id, nombre, almacen, operador, instrucciones, total, contados, estado, creada)`.
- `listar(cur, operador: str | None = None) -> list[ResumenTarea]`: solo los conteos con `operador` no nulo, de más reciente a más antigua.
- `migrar(conn) -> None`: idempotente y tolerante a dos escritorios (`db.ddl_tolerante`, que se mueve a `btsync/store.py` como `ddl_tolerante` y lo reexporta `app/db.py`). Crea:
  - en `conteos`, las columnas `almacen VARCHAR2(20 CHAR)`, `operador VARCHAR2(30 CHAR)`, `instrucciones VARCHAR2(500 CHAR)`, `iniciada TIMESTAMP`, `creada_por VARCHAR2(30 CHAR)` y `creada TIMESTAMP DEFAULT SYSTIMESTAMP`;
  - la secuencia `seq_tareas`;
  - la tabla `revisiones (id_conteo, sku, accion CHECK IN ('REVISADA','RECUENTO'), nota VARCHAR2(300 CHAR), por VARCHAR2(30 CHAR), fecha TIMESTAMP DEFAULT SYSTIMESTAMP, PK (id_conteo, sku))`, donde la última acción reemplaza a la anterior.
- `Store.catalog(usuario: str | None) -> Catalog`:
  - `Catalog.tareas: list[tuple[id, nombre, almacen, instrucciones, estado, total, contados]]`;
  - `Catalog.items: list[tuple[id_tarea, sku, recuento 'S'|'N']]`;
  - si la cuenta no está activa (`usuario=None`), solo van los conteos generales;
  - los conteos generales llevan almacén `""`, estado `""` y total y contados `0`.
- `Store.marcar_iniciada(usuario, id_tarea) -> None`: hace `UPDATE … SET iniciada = NVL(iniciada, SYSTIMESTAMP) WHERE id_conteo = :t AND operador = :u AND estado = 'ABIERTO'`. Si no coincide ninguna fila, no hace nada.

- [ ] **Pruebas RED:**
  - `test_estado_tarea_*`: una por regla, más «cerrada gana a error» y «error gana a completa».
  - `test_listar_cuenta_contados_y_estado`: tarea `TT-1` con A1 y A2.
    - Sin lecturas → `ASIGNADA`, 0/2.
    - Con `iniciada` → `EN_PROGRESO`.
    - Lectura de A1 procesada → `ENVIADA_PARCIALMENTE`, 1/2.
    - A2 igual al sistema → `SINCRONIZADA` 2/2, o distinto → `CON_DIFERENCIAS`.
    - `cerrar_conteo` → `CERRADA`.
  - `test_recuento_pedido_descuenta_hasta_nueva_lectura` (Review Focus 1).
  - `test_lectura_fuera_de_la_tarea_no_suma_avance` (Review Focus 3).
  - `test_error_en_staging_da_con_error`.
  - `test_catalogo_solo_trae_tareas_del_operador_y_generales`.
  - `test_marcar_iniciada_ignora_ajena_y_cerrada` (Review Focus 5).
  - `test_migrar_idempotente`.
- [ ] Implementar y dejar GREEN; correr la suite del servidor.

### Task 2: protocolo v4 en el receptor y en el móvil
**Archivos:**
- Receptor: modificar `server/btsync/protocol.py` (`PROTOCOL_VERSION = "4"`; `_MIN_PARTS`: `CATTAREA` 8, `CATITEM` 4 e `INICIO` 2, sin `CATCONTEO`) y `server/btsync/session.py`.
  - El catálogo se envía con `catalog(usuario if cuenta_activa else None)`.
  - En el bucle principal, `INICIO|id` → `store.marcar_iniciada(usuario, id)`, solo si la cuenta está activa. No lleva ACK y no corta la sesión.
- Comunes: `docs/protocol-vectors.json` y `docs/protocolo.md`.
- Móvil:
  - modificar `protocol/Protocol.kt`;
  - en `data/Catalogo.kt`, `TareaEntity` sustituye a `ConteoEntity`, y se añaden `ItemTareaEntity` e `InicioEntity`;
  - en `data/AppDatabase.kt`, la versión 3 y `MIGRACION_2_3`;
  - en `sync/SyncClient.kt`: lee `CATTAREA`/`CATITEM`; tras el catálogo, si la cuenta está activa, envía `INICIO` por cada tarea iniciada en el teléfono cuyo estado en el catálogo sea `ASIGNADA`; después, las lecturas.
- Pruebas: `server/tests/test_protocol.py` y `test_session.py`; en el móvil, `ProtocolTest`, `SyncClientTest` (con `FakePc`) y `MigracionTest`.

**Produce (móvil):**
- `TareaEntity(id, nombre, almacen, instrucciones, estado, total: Int, contados: Int)` en la tabla `tareas`.
- `ItemTareaEntity(idTarea, sku, recuento: Boolean)` en `items_tarea`, con PK (idTarea, sku).
- `InicioEntity(idTarea)` en `inicios`. Es local y no se borra al reemplazar el catálogo.
- `Catalog(tareas, items, productos)`.
- `CatalogRepository`:
  - `tareas(): List<TareaEntity>`, `items(idTarea): List<ItemTareaEntity>`;
  - `marcarIniciada(id)`, `iniciadas(): Set<String>`;
  - se conservan `productos()` y `producto(sku)`.
- `MIGRACION_2_3`: borra `conteos` y crea `tareas`, `items_tarea` e `inicios`. `lecturas` no se toca.

- [ ] **Pruebas RED:**
  - vectores nuevos de `CATTAREA`, `CATITEM` e `INICIO` en los dos lados;
  - `HELLO` de la versión 3 → `NAK FORMAT`;
  - la sesión envía las tareas del operador;
  - `INICIO` con la cuenta activa marca la tarea; con la cuenta suspendida, no;
  - `SyncClientTest`: el catálogo con tareas e items queda en Room y el `INICIO` sale antes de las lecturas;
  - `MigracionTest`: de 2 a 3 con lecturas pendientes, que siguen ahí (Review Focus 4).
- [ ] Implementar y dejar GREEN en las suites del servidor y del móvil.

### Task 3: `app/tareas.py`, las operaciones del escritorio
**Archivos:**
- Crear: `desktop/app/tareas.py`.
- Modificar: `desktop/app/permisos.py` (`EN_USO`) y `desktop/app/main.py`, que llama a `btsync.tareas.migrar` dentro de una conexión de `db`.
- Pruebas: `desktop/tests/test_tareas.py`, con una fixture `tareas_db` en `conftest.py` sobre `maestros_db` que borra los `TT-*` y sus `stock_sistema`, `registros_procesados`, `conciliacion`, `revisiones` y `captura_transito`.

**Consume:** `btsync.tareas.listar`, `ResumenTarea`, `NOMBRE_ESTADO`, y las constantes de tabla de `maestros` y `auth.TABLA`.

**Produce:**
- `listar_tareas() -> list[ResumenTarea]`.
- `operadores_disponibles() -> list[tuple[usuario, nombre]]`.
- `productos_disponibles() -> list[tuple[sku, nombre, categoria]]`: los de categorías activas.
- `crear_tarea(quien, nombre, almacen, operador, skus: list[str], instrucciones) -> str`: devuelve el id `T-001`, con `LPAD(seq_tareas.NEXTVAL, 3, '0')`.
  - Inserta `conteos` (`ABIERTO`) y una fila de `stock_sistema` por cada SKU, con la cantidad de `existencias` de ese almacén o 0.
  - Valida el nombre (1–100 caracteres), las instrucciones (≤500), al menos un producto, y que el almacén y el operador sigan activos (Review Focus 2).
- `reasignar(quien, id_tarea, operador) -> None`: solo si el estado es `ASIGNADA`. Si no: «Solo se puede reasignar una tarea que aún no empezó.»
- `cerrar(quien, id_tarea) -> None`: `permisos.exigir` y luego `db.cerrar_conteo`.
- `avance(id_tarea) -> list[tuple[sku, nombre, contado: bool, cantidad: float | None]]`.
- `@dataclass(frozen=True) Diferencia(id_conteo, sku, producto, almacen, sistema, contado, diferencia, tipo, observacion, estado)`:
  - `tipo` es `FALTANTE` o `SOBRANTE`;
  - `estado` es `PENDIENTE`, `REVISADA` o `RECUENTO`, y la revisión cuenta solo si es igual o posterior a la última lectura vigente.
- `listar_diferencias() -> list[Diferencia]`: las filas FALTANTE/SOBRANTE de `conciliacion` de todos los conteos; la observación es la nota de la lectura vigente.
- `marcar_revisada(quien, id_conteo, sku, nota) -> None`.
- `pedir_recuento(quien, id_conteo, sku) -> None`: solo con el conteo `ABIERTO`. Si no: «La tarea ya está cerrada.»
- Los errores para la persona son `ErrorDeAcceso`. Si otro usuario borró o cerró algo mientras tanto: «ya no existe. Actualiza la lista.»

- [ ] **Pruebas RED:**
  - `crear_tarea` toma la cantidad de existencias, o 0 si no hay fila;
  - rechaza un almacén inactivo, un operador suspendido, la lista vacía y el nombre vacío;
  - Inventario crea y el Administrador no (llamando a la función directamente);
  - `reasignar` funciona en `ASIGNADA` y se rechaza en `ENVIADA_PARCIALMENTE`;
  - `listar_diferencias`, `marcar_revisada` y `pedir_recuento` con sus estados;
  - una revisión anterior a una lectura nueva vuelve a `PENDIENTE`;
  - pedir recuento en una tarea cerrada se rechaza;
  - el Administrador no revisa.
- [ ] Implementar y dejar GREEN.

### Task 4: pantallas del escritorio, Tareas y Diferencias
**Archivos:**
- Crear: `desktop/app/views/tareas.py` (`TareasView`, `TareaDialog`) y `desktop/app/views/diferencias.py` (`DiferenciasView`).
- Modificar: `main.py`, para añadir «Tareas de conteo» (módulo `tareas`) y «Diferencias» (módulo `diferencias`) después de «Inventario», y `views/iconos.py`.
- Pruebas: `desktop/tests/test_tareas_views.py`.

**Sigue el patrón de** `views/maestros.py` y `views/existencias.py`:
- `QueryRunner` para las consultas;
- `StateBanner` para «sin datos» o «sin coincidencias»;
- errores de una acción por la vía de Fase 2, sin el prefijo de la base y sin que el refresco los borre;
- la fila elegida se conserva al refrescar.

**Produce:**
- `pedir_tarea(padre, almacenes, operadores, productos) -> tuple[nombre, almacen, operador, skus, instrucciones] | None` y `pedir_operador(padre, operadores, actual) -> str | None` como funciones del módulo, para sustituirlas en las pruebas.
- `TareasView`:
  - expone `filas()`, `combo_estado`, `combo_operador`, `btn_nuevo`, `btn_reasignar`, `btn_cerrar` y `tabla_avance`;
  - columnas: Tarea, Almacén, Operador, Productos, Avance «7/12» y Estado;
  - el panel de avance muestra la tarea elegida;
  - «Reasignar» solo se habilita en `ASIGNADA` y «Cerrar» en lo que no está `CERRADA`.
- `DiferenciasView`:
  - expone `filas()`, `combo_tarea`, `combo_tipo`, `combo_estado` (por defecto «Pendientes») y los botones `btn_revisada` y `btn_recuento`;
  - columnas: Tarea, Producto, Almacén, Sistema, Contado, Dif., Tipo, Observación y Estado;
  - «Revisada» pide una nota opcional con `pedir_texto`, que se reutiliza de `views/maestros.py`.
- En el diálogo de nueva tarea, el filtro de categoría limita la lista de productos con casillas. Tiene «Marcar todos» y «Ninguno».

- [ ] **Pruebas RED:**
  - la tabla y los filtros;
  - crear con el diálogo sustituido aparece como `ASIGNADA`;
  - reasignar y cerrar;
  - el Administrador ve Tareas y Diferencias sin botones;
  - un rol sin `tareas` no ve la sección;
  - Diferencias: marcar revisada la saca de «Pendientes», y pedir recuento muestra «Recuento pedido»;
  - un error de acción («ya no está activo») se ve y no lo borra el refresco.
- [ ] Implementar y dejar GREEN; correr la suite completa del escritorio; sacar las capturas offscreen y revisarlas.

### Task 5: «Mis tareas» en el móvil
**Archivos:**
- Renombrar: `ElegirScreen.kt` a `pantallas/TareasScreen.kt` y `ElegirActivity` a `TareasActivity`, actualizando el manifiesto y `HomeActivity`.
- Modificar: `CountViewModel.kt`.
  - `tareas()` reemplaza a `conteos()`; `hayCatalogo()` usa las tareas.
  - `iniciarTarea(id)` llama a `marcarIniciada` y a `elegirConteo(id)`.
- Pruebas: `CountViewModelTest` y `CapturasTest` (captura de «Mis tareas» con datos y vacía).

**Pantalla:**
- **Título:** «Mis tareas».
- **Tarjeta por tarea:**
  - `id · almacén · contados/total · estado` (texto en español), con las instrucciones debajo si las hay;
  - el botón dice «Iniciar» si no está en `inicios`, o «Continuar» si ya está;
  - los conteos generales se muestran como «Conteo general» y sin avance.
- **Sin tareas:** «No tienes tareas asignadas», con el botón «Sincronizar con el PC».
- **Recuentos:** si la tarea tiene items con `recuento`, una línea «N productos por recontar».

- [ ] **Pruebas RED:**
  - `iniciarTarea` registra el inicio y elige el conteo;
  - `hayCatalogo` da falso si no hay tareas;
  - la captura vacía muestra el texto de «sin tareas».
- [ ] Implementar, dejar GREEN y compilar `assembleDebug`.

### Task 6: documentación
- [ ] En `docs/arquitectura.md`, la decisión D28: tarea = conteo, estado calculado, protocolo v4.
- [ ] Actualizar `docs/protocolo.md` y el README (pantallas nuevas).
- [ ] Actualizar los UML 04 (modelo de datos: columnas de `conteos`, `revisiones`) y la secuencia de sincronización, si muestra `CATCONTEO`. Regenerar sus SVG y pasar `test_uml`.
