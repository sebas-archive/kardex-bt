# Fase 4: fotos como evidencia, dañados y auditoría. Plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: superpowers:executing-plans (el usuario eligió Native en la Fase 1). Pasos con casillas (`- [ ]`).

**Meta:**
- El operador adjunta a una lectura una foto (cámara o galería) y la cantidad de dañados.
- Las fotos viajan por Bluetooth después de las lecturas, se guardan en una carpeta del PC y Oracle guarda su ruta.
- Inventario las ve en Diferencias y en el avance de la tarea.
- Todo cambio de datos del escritorio y todo inicio de sesión queda en una auditoría que el Administrador consulta.

**Arquitectura:**
- **Protocolo 5:**
  - `REC` gana un campo final, `danados` (vacío si no hay).
  - Mensajes nuevos: `FOTO|seq|parte|total|crc32|base64` (móvil → PC), `FOTOOK|seq` y `FOTOERR|seq|motivo` (PC → móvil).
- **El job PL/SQL** lee `danados` y lo guarda en `registros_procesados.danados`.
- **Esquema y paquete:**
  - `server/btsync/esquema.py::migrar(conn)` añade la columna y la tabla `fotos`;
  - si el paquete compilado no conoce `danados`, lo recompila desde `db/init/03_pkg_batch.sql`;
  - lo llaman el escritorio al arrancar y la fixture de sesión del servidor.
- **Fotos:** el receptor junta las partes, comprueba el CRC, escribe `<FOTOS_DIR>/<uuid>/<seq>.jpg` y registra la fila en `fotos`.
  - `FOTOS_DIR` viene de una variable de entorno; por defecto es `fotos/` relativo al directorio de trabajo (`/work/fotos` en Docker), fuera de git.
  - La ruta que se guarda es relativa a `FOTOS_DIR`.
- **Auditoría:** `desktop/app/auditoria.py` escribe la fila **en la misma transacción** que el cambio auditado.

**Stack:** Python 3.12 + PyQt6 + python-oracledb + Oracle XE 11g; Kotlin + Room + Compose.

**Spec:**
- Operador §5: foto opcional desde cámara o galería, con miniatura; dañados; guardar en SQLite sin conexión.
- Operador §7: indicador de foto en el historial.
- Operador §8: cola separada, el texto con prioridad.
- Infraestructura: carpeta local con fotos comprimidas, ruta en Oracle, JPG reducido.
- Inventario §10: visor de evidencia.
- Administrador §7: auditoría (acciones de usuarios, movimientos, cambios de roles y permisos, fechas y responsables).
- El boceto se aprobó el 2026-11-14.

## Restricciones globales
- **Foto en el móvil:** como máximo 1280 px por el lado mayor, JPEG de calidad 70. Una foto por lectura, y reemplazarla sustituye la anterior. El PC rechaza fotos de más de 2 MB (`FOTOERR|seq|GRANDE`).
- **`FOTO`:**
  - cada parte lleva hasta 2700 caracteres de base64 (la línea queda bajo 4000 bytes);
  - `crc32` son 8 hex mayúsculas del archivo completo;
  - `parte` va de 1 a `total`.
- **Orden de envío:** el móvil envía fotos solo de lecturas ya confirmadas (ACK), después de que se confirman todas las lecturas de la sesión y antes de `END`. Una a la vez: espera `FOTOOK` o `FOTOERR` antes de la siguiente.
- **Si algo sale mal con una foto:**
  - `FOTOERR` por CRC: se reintenta en la próxima sesión;
  - `FOTOERR` por GRANDE: la foto queda RECHAZADA y no se reintenta;
  - si la conexión se corta a mitad, la foto se reenvía entera la próxima vez.
- **Dañados:** el mismo formato que la cantidad (`^\d{1,9}(\.\d{1,3})?$`) o vacío, y nunca mayor que la cantidad. En el PL/SQL: `DANADOS_INVALIDO`.
- **Acciones auditadas:** `(modulo, accion, detalle)`, con el `usuario` que actúa y la fecha. Se registran:
  - acceso (inicio de sesión correcto y fallido) y cuentas (aprobar, rechazar, suspender, reactivar, cambiar rol, desvincular teléfono, restablecer clave);
  - permisos (guardar), categorías y almacenes (las 6 escrituras);
  - tareas (crear, reasignar, cerrar), diferencias (revisada, recuento);
  - movimientos (entrada, salida), ajustes (solicitar, aprobar, rechazar).
- **Pantalla «Auditoría»:** usa el módulo `historial`. El Administrador ve todo; Inventario ve solo los módulos de operación (`tareas`, `diferencias`, `movimientos`, `ajustes`, `categorias`).
- Toda consulta a Oracle va fuera del hilo de la interfaz, y también la lectura del archivo de la foto en el visor. Sin commits hasta que el usuario los pida.
- **Comandos:**
  - servidor: `docker compose run --rm app pytest server/tests -q`
  - escritorio: `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -q`
  - móvil: `docker compose --profile build run --rm apk-build ./gradlew testDebugUnitTest assembleDebug`

## Review Focus
1. **Se corta la conexión a mitad de una foto:** no queda archivo ni fila a medias en el PC, y la foto se reenvía completa la siguiente vez.
2. **El operador recuenta (reemplaza en sitio) una lectura que tenía foto, o le cambia la foto antes de enviarla:** sale la foto vigente, no la vieja.
3. **Una foto llega dos veces** (el `FOTOOK` se perdió): el PC la acepta otra vez sin duplicar la fila ni fallar.
4. **El paquete PL/SQL de una base anterior se recompila al arrancar sin perder datos.** Un `REC` de 8 partes (protocolo 4) ya no se acepta, por versión.
5. **Una acción que falla no deja fila de auditoría;** una que sale bien siempre la deja.

---

### Task 1: protocolo 5, lote y fotos en el receptor
**Archivos:**
- `server/btsync/protocol.py`: `Rec.danados`, `VERSION="5"`, `_MIN_PARTS` (`REC` 9, `FOTO` 6, `FOTOOK` 2, `FOTOERR` 3).
- Vectores en `docs/protocol-vectors.json` y `docs/protocolo.md`.
- Crear `server/btsync/esquema.py`.
- `db/init/01_schema.sql` (columna y tabla para bases nuevas) y `db/init/03_pkg_batch.sql` (leer el campo 9).
- `server/btsync/session.py`: recibir `FOTO`.
- `server/btsync/store.py`: `guardar_foto(uuid, seq, datos: bytes) -> str`, con MERGE.
- `server/tests/conftest.py`: `esquema.migrar`. Pruebas en `test_protocol.py`, `test_session.py`, `test_batch.py` y `test_fotos.py`.

**Produce:**
- `Rec(seq, ts_ms, id_conteo, sku, cantidad, operador, nota, danados="")`.
- `esquema.migrar(conn)`.
- `foto_lineas(seq: int, datos: bytes, tam=2700) -> list[list[str]]`, helper en `protocol.py` para pruebas y herramientas.
- `fotos_dir() -> Path` en `store.py`.

- [ ] **Pruebas RED:**
  - vectores `rec_danados` y `foto`; `HELLO` de la versión 4 → `NAK`;
  - el lote guarda `danados` y rechaza dañados mayores que la cantidad (`DANADOS_INVALIDO`);
  - la sesión arma una foto de 3 partes: `FOTOOK`, archivo en disco, fila en `fotos`;
  - CRC malo → `FOTOERR CRC` y nada en disco;
  - más de 2 MB → `FOTOERR GRANDE`;
  - foto repetida → `FOTOOK` sin duplicar (Review Focus 3);
  - corte a mitad → nada en disco (Review Focus 1);
  - `esquema.migrar` idempotente; recompila si falta `danados` (Review Focus 4).
- [ ] Implementar y dejar GREEN; correr la suite del servidor.

### Task 2: móvil (dañados, foto, cola de fotos)
**Archivos:**
- `data/Lectura.kt`: campo `danados`; `reemplazar` actualiza también la nota y los dañados.
- Crear `data/Fotos.kt`: `FotoEntity(seq PK, archivo, estado PENDIENTE|ENVIADA|RECHAZADA)` y `FotoDao`.
- `data/AppDatabase.kt`: versión 4 y `MIGRACION_3_4`.
- `protocol/Protocol.kt` y `sync/SyncClient.kt`: tras el último ACK, enviar las fotos pendientes cuyas lecturas estén CONFIRMADO.
- Crear `fotos/Compresor.kt`: `comprimir(entrada: InputStream, destino: File, maxLado = 1280, calidad = 70)`.
- `ui/CountViewModel.kt`: `guardar(sku, cantidad, nota, danados = "", foto: File? = null)`; `SaveResult.DanadosInvalidos`.
- `ui/pantallas/ContarScreen.kt`: campo «Dañados», botones Cámara y Galería, miniatura y «Quitar».
- `ui/ContarActivity.kt`: `TakePicture` con FileProvider y `PickVisualMedia`; el manifiesto y `res/xml/rutas_fotos.xml`.
- Inicio: «N fotos por enviar». Lista de lecturas: 📷.
- Pruebas: `ProtocolTest`, `SyncClientTest` (FakePc acepta `FOTO`), `MigracionTest` (3 → 4), `CountViewModelTest`, `CompresorTest` y `CapturasTest`.

- [ ] **Pruebas RED:**
  - vectores;
  - la foto sale después de los ACK, en partes, y queda ENVIADA con `FOTOOK`;
  - `FOTOERR GRANDE` → RECHAZADA; `FOTOERR CRC` → sigue PENDIENTE;
  - corte → PENDIENTE;
  - recuento en sitio con foto nueva → sale la nueva (Review Focus 2);
  - dañados mayor que la cantidad → `DanadosInvalidos`;
  - el compresor deja el lado mayor ≤ 1280 en un JPEG válido;
  - la migración 3 → 4 conserva las lecturas;
  - captura de Contar con miniatura.
- [ ] Implementar, dejar GREEN y compilar el APK.

### Task 3: el escritorio muestra dañados y fotos
**Archivos:**
- `desktop/app/tareas.py`: `Diferencia` gana `danados: float | None` y `foto: str` (ruta relativa o «»); `avance` gana la ruta de la foto.
- Crear `desktop/app/views/foto.py`: `ver_foto(padre, ruta_relativa)`; el archivo se lee fuera del hilo de la interfaz.
- `views/diferencias.py` y `views/tareas.py`: columnas «Dañados» y «Foto» (📷); clic en la celda → `ver_foto`.
- `desktop/app/main.py`: `esquema.migrar`.
- Pruebas: `test_tareas.py` y `test_tareas_views.py`.

- [ ] **Pruebas RED:**
  - una lectura con dañados y foto aparece en la diferencia y en el avance;
  - clic en 📷 llama a `ver_foto` con la ruta;
  - sin foto, la celda queda vacía y el clic no hace nada;
  - si la foto falta en disco, el visor dice «La foto no está en la carpeta del PC».
- [ ] Implementar y dejar GREEN; correr la suite del escritorio; capturas.

### Task 4: auditoría
**Archivos:**
- Crear `desktop/app/auditoria.py`:
  - `TABLA = "auditoria"` (pruebas: `auditoria_tst`);
  - `registrar(cur, usuario, modulo, accion, detalle="")`, sin commit propio;
  - `listar(quien) -> list[Entrada]`, que filtra por rol;
  - `migrar()`.
- Llamar a `registrar` en `auth`, `permisos`, `maestros`, `tareas` y `movimientos`.
- Crear `views/auditoria.py` (`AuditoriaView`) y añadir la sección «Auditoría» (módulo `historial`) en `main.py`; `historial` entra en `EN_USO`.
- Pruebas: `test_auditoria.py` y `test_auditoria_views.py`; fixture `auditoria_db`, autouse en las fixtures de cuentas.

**Produce:** `@dataclass(frozen=True) Entrada(fecha, usuario, nombre, modulo, accion, detalle)`.

- [ ] **Pruebas RED:**
  - cada familia deja su fila con el texto esperado (parametrizado);
  - una acción rechazada no deja fila (Review Focus 5);
  - Inventario no ve las filas de usuarios ni de permisos;
  - filtros y búsqueda en la vista;
  - sección visible para el Administrador y para Inventario; no para un rol sin `historial`.
- [ ] Implementar y dejar GREEN; correr la suite del escritorio.

### Task 5: documentación
- [ ] En `docs/arquitectura.md`, la decisión D30.
- [ ] Actualizar `docs/protocolo.md` (versión 5) y el README.
- [ ] UML 04: `fotos`, `auditoria` y `danados`; 03: clases nuevas del móvil; 13: fotos en la secuencia. Regenerar los SVG y pasar `test_uml`.
