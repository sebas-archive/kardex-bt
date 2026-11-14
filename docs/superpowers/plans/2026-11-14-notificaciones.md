# Notificaciones. Plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: superpowers:executing-plans (el usuario eligió Native en la Fase 1). Pasos con casillas (`- [ ]`).

**Meta:** una pantalla «Notificaciones» y la campana del encabezado con el número de notificaciones sin leer. Una notificación avisa que algo pasó, se lee y se marca como leída. **No es una solicitud:** «Solicitudes» sigue siendo la pantalla donde se aprueba o rechaza; una solicitud nueva solo genera además una notificación que lleva ahí.

**Arquitectura:**
- `server/btsync/notificaciones.py` (lo usan el servicio y el escritorio): tablas `NOTIFICACIONES` y `NOTIFICACIONES_LEIDAS`; `crear(cur, tipo, texto, seccion, rol=None, usuario=None, clave=None) -> bool`, sin commit propio, en la misma transacción que el evento.
- `desktop/app/notificaciones.py`: `listar(quien)`, `sin_leer(quien)`, `marcar_leida(quien, id)`, `marcar_todas(quien)`.
- Vista `views/notificaciones.py` (`NotificacionesView`), sección «Notificaciones» (módulo nuevo `notificaciones`: Administrador e Inventario GESTION, Operador NINGUNO). La campana cuenta las sin leer y abre la sección.

**Spec:** pedido del usuario el 2026-11-14 («haz una vista de notificaciones, ojo que solicitudes no es lo mismo que notificaciones»), con el boceto y las respuestas aprobadas: todos los eventos propuestos, las solicitudes también notifican, campana + pantalla.

## Restricciones globales
- **Destino:** una notificación va a un **rol** (la ven todas las cuentas de ese rol) o a un **usuario**. Cada persona marca como leídas las suyas; leer no afecta a las demás.
- **`clave`** (opcional) evita duplicados: `(tipo, clave)` es único; una segunda `crear` con la misma clave devuelve `False` y no inserta.
- **Eventos, textos y destino** (`seccion` = título de la pantalla a la que lleva «Ver», o vacío):

  | tipo | cuándo | destino | texto | sección |
  |---|---|---|---|---|
  | `AJUSTE_PENDIENTE` | `solicitar_ajuste` deja PENDIENTE | ADMIN | «Ajuste crítico por aprobar: {producto}, {delta} ({nombre})» | Ajustes |
  | `AJUSTE_RESUELTO` | `aprobar`/`rechazar` | el responsable | «Tu ajuste de {producto} fue aprobado por {nombre}» / «… fue rechazado por {nombre}: {motivo}» | Ajustes |
  | `STOCK_BAJO` / `AGOTADO` | una salida o un ajuste aplicado (o aprobado) cruza el mínimo o llega a 0 | INVENTARIO | «Stock bajo: {producto} en {almacén} ({n} de mínimo {m})» / «Agotado: {producto} en {almacén}» | Existencias |
  | `SINCRONIZACION` | el controlador termina el batch de una sincronización | ADMIN e INVENTARIO | «Sincronización recibida: {dispositivo}, {n} lecturas» + « · {e} con error» si hubo | Sincronización |
  | `SERVICIO_DETENIDO` | el escritorio ve DETENIDO tras haberlo visto activo | ADMIN (clave = `desde` del servicio: una por arranque) | «El servicio Bluetooth se detuvo» | Sincronización |
  | `RESPALDO` / `RESPALDO_FALLO` | el automático crea uno o falla | ADMIN | «Respaldo automático creado: {archivo}» / «Falló el respaldo automático: {error}» | Respaldos |
  | `SOLICITUD` | cuenta nueva (PC o móvil) o pedido de clave | ADMIN | «Nueva solicitud de cuenta: {nombre}» / «{nombre} pidió restablecer su contraseña» | Solicitudes |

- Una notificación que falla al crearse **nunca** hace fallar el evento que la causó en el servicio (sincronización, respaldo); en el escritorio va en la misma transacción que el cambio (como la auditoría).
- La pantalla: lista de la más reciente a la más vieja, filtro «Todas | Sin leer», «Marcar todas como leídas», ● en las sin leer, «Ver» abre la sección y marca esa como leída. Toda consulta fuera del hilo de la interfaz. Se muestran las últimas 200.
- Sin commits hasta que el usuario los pida.
- **Comandos:** `docker compose run --rm app pytest server/tests -q` · `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -q`

## Review Focus
1. **Dos personas del mismo rol:** una marca como leída y la otra la sigue viendo sin leer.
2. **Un evento del escritorio que falla** (ajuste rechazado por permiso, salida sin existencia) no deja notificación.
3. **La sincronización o el respaldo siguen bien aunque crear la notificación falle** (tabla ausente u Oracle caído en ese instante).
4. **El servicio se cae y dos escritorios lo ven:** sale una sola notificación de «se detuvo» por cada arranque del servicio.
5. **Stock que ya estaba bajo** y baja más: no se repite «Stock bajo» en cada salida (solo al cruzar).

---

### Task 1: modelo y eventos del servidor
**Archivos:** crear `server/btsync/notificaciones.py` (`TABLA`, `TABLA_LEIDAS`, pruebas `_tst`; `migrar(conn)` llamado desde `esquema.migrar`; `crear`); `store.py`: `Store.notificar_sincronizacion(errores: int)` (lee la última `sync_sesiones` cerrada y `dispositivos`) y la notificación `SOLICITUD` en `sincronizar_cuenta` al crear la cuenta PENDIENTE; `controller.py`: tras `run_batch` llama a `notificar_sincronizacion` en un `try` (best effort); `respaldo.Automatico`: `RESPALDO` y `RESPALDO_FALLO`. Fakes: `notificar_sincronizacion` no hace nada.
- [ ] **Pruebas RED** (`server/tests/test_notificaciones.py`): `crear` con rol y con usuario; clave repetida no duplica; una sincronización completa con el `Store` real deja «Sincronización recibida: Bodega Test, 2 lecturas» para ADMIN e INVENTARIO; con `notificar_sincronizacion` que lanza, el controlador llega igual a LISTO (Review Focus 3); el automático deja `RESPALDO`, y si `crear` del zip falla deja `RESPALDO_FALLO`; una cuenta nueva del móvil deja `SOLICITUD`.
- [ ] Implementar, GREEN, suite del servidor.

### Task 2: eventos del escritorio y lectura
**Archivos:** crear `desktop/app/notificaciones.py` (`Notificacion(id, fecha, tipo, texto, seccion, leida)`); llamar a `crear` en `movimientos` (pendiente, resuelto, stock bajo/agotado al cruzar) y en `auth` (`registrar` que deja PENDIENTE, `solicitar_clave`); `permisos`: módulo `notificaciones` (G, G, N) en la matriz y en `EN_USO`. Fixture `notificaciones_db` autouse con tablas `_tst`.
- [ ] **Pruebas RED** (`desktop/tests/test_notificaciones.py`): cada evento de la tabla deja su texto y destino (parametrizado); una salida rechazada no deja nada (Review Focus 2); dos cuentas INVENTARIO: una marca leída y la otra sigue con 1 sin leer (Review Focus 1); `marcar_todas`; stock que ya estaba bajo no repite (Review Focus 5); Inventario no ve las de ADMIN.
- [ ] Implementar, GREEN, suite del escritorio.

### Task 3: pantalla y campana
**Archivos:** crear `views/notificaciones.py`; `main.py`: sección «Notificaciones», la campana para todo rol con el módulo, `poner_avisos` cuenta las sin leer (sondeo con el refresco de la ventana) y abre «Notificaciones»; `ServicioRemoto`/`main`: al pasar de un estado activo a DETENIDO, `crear(SERVICIO_DETENIDO, clave=desde)` (Review Focus 4); icono «Notificaciones».
- [ ] **Pruebas RED** (`desktop/tests/test_notificaciones_views.py`): la lista con ● y el filtro; «Ver» va a la sección y la marca leída; «Marcar todas»; la campana muestra el número y abre la pantalla; Inventario ve la sección; dos `ServicioRemoto` que ven caer el mismo servicio dejan una sola notificación.
- [ ] Implementar, GREEN, suites; actualizar `docs/arquitectura.md` (D32) y UML 04 (dos tablas); `test_uml`.
