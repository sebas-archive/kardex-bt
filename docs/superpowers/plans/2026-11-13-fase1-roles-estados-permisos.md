# Fase 1: roles, estados de cuenta y permisos — Plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: usa superpowers:subagent-driven-development (recomendada) o superpowers:executing-plans para ejecutar este plan tarea por tarea. Los pasos usan casillas (`- [ ]`).

**Meta:** Que toda cuenta (escritorio o móvil) tenga un estado (PENDIENTE, ACTIVO, RECHAZADO, SUSPENDIDO) y un rol (Administrador, Inventario, Operador), que el administrador los gestione con motivo, y que una matriz de permisos editable en Oracle decida qué módulos ve cada rol.

**Arquitectura:** La tabla `usuarios` de Oracle pasa a ser la única fuente de cuentas, también las de operadores del móvil. El móvil envía `ACCT` al conectarse y recibe `ACCTST` con su estado; sin `ACTIVO` no se aceptan lecturas. La matriz de permisos vive en la tabla `permisos` y se consulta desde el módulo `permisos.py`, tanto en las vistas como en las funciones de `auth.py` que tocan datos.

**Stack:** Python 3.12, PyQt6, python-oracledb (thick), Oracle XE 11g; Kotlin, Jetpack Compose, Room; protocolo de líneas con CRC32 (`docs/protocolo.md`).

**Spec:** Especificación pegada por el usuario el 2026-11-13 (secciones "Vistas para usuarios sin rol asignado", "Roles y permisos", "Matriz de permisos", "Solicitudes pendientes") más las decisiones de esta conversación, resumidas abajo. No existe un documento aparte.

## Decisiones acordadas con el usuario

- Seguimos en Python/PyQt6 en el escritorio; no se rehace en C# WPF.
- Las cuentas de operadores viven en Oracle y las aprueba el administrador en Solicitudes.
- La matriz de permisos es una tabla de Oracle editable por el administrador y se valida en la interfaz y en el acceso a datos.
- Pantalla **RECHAZADO**: estado, **motivo**, botón **«Regresar al inicio de sesión»** (no «Cerrar sesión»). Igual para **SUSPENDIDO**.
- Pantalla **PENDIENTE**: estado, mensaje de espera, fecha de registro, botón «Cerrar sesión».
- El motivo lo escribe el administrador al pulsar Rechazar o Suspender; es obligatorio.
- Supuesto a confirmar al ejecutar: en el móvil el rol `OPERADOR` reemplaza a `CLASIFICADOR` y `SUPERVISOR`; las cuentas locales existentes se migran a `OPERADOR`.

## Restricciones globales

- Roles exactos: `ADMIN`, `INVENTARIO`, `OPERADOR`. Nombres en pantalla: «Administrador», «Inventario», «Operador de Inventario».
- Estados exactos: `PENDIENTE`, `ACTIVO`, `RECHAZADO`, `SUSPENDIDO`.
- Motivo: de 1 a 300 caracteres.
- Niveles de permiso exactos: `NINGUNO`, `CONSULTA`, `GESTION`.
- Los cuatro estados y su motivo aplican igual en escritorio y móvil.
- Todo acceso a Oracle sale del hilo de la interfaz (`QueryRunner`) y pasa por `db._conexion()`; en el servidor, por `connect_oracle`.
- No hacer commits ni push sin que el usuario lo pida.
- Pruebas: `docker compose run --rm pybase pytest server/tests -v`; `docker compose run --rm -e QT_QPA_PLATFORM=offscreen app pytest desktop/tests -v`; `docker compose --profile build run --rm apk-build ./gradlew testDebugUnitTest`.
- Subred Docker fija `10.250.0.0/24` ya aplicada en `docker-compose.yml`; no tocarla.

## Review Focus

1. Dos administradores resuelven a la vez la misma solicitud: el segundo debe recibir «Esta solicitud ya fue resuelta», sin sobrescribir el motivo ni el rol.
2. Quien edita la matriz no puede quitarse a sí mismo (ni al rol Administrador) el acceso a Usuarios, Solicitudes y Permisos: no puede quedar un sistema sin quien lo administre.
3. Operador suspendido con lecturas en el búfer del móvil: el PC responde `NAK|<seq>|CUENTA_NO_ACTIVA`, las lecturas siguen en el búfer y se envían al reactivarlo.
4. Motivo con `|`, saltos de línea, `%` o más de 300 caracteres: el protocolo lo transporta sin romper la línea (usa `encode_text`) y la interfaz lo recorta o rechaza con un mensaje.
5. Usuario del móvil con el mismo nombre que una cuenta de escritorio: el PC responde `ACCTST` con `RECHAZADO` y motivo «Ese usuario ya existe en el PC», sin tocar la cuenta existente.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `db/init/01_schema.sql` (modificar) | `usuarios` con `estado`, `motivo`, `resuelto_por`, `resuelto`, `origen`; rol `OPERADOR` |
| `db/init/06_permisos.sql` (crear) | Tabla `permisos` y su matriz inicial |
| `desktop/app/auth.py` (modificar) | Estados, rol Operador, aprobar, rechazar, suspender, reactivar, historial, `migrar()` |
| `desktop/app/permisos.py` (crear) | Módulos, niveles, `nivel`, `puede`, `matriz`, `guardar` |
| `desktop/app/views/estado_cuenta.py` (crear) | Pantalla de PENDIENTE, RECHAZADO y SUSPENDIDO |
| `desktop/app/views/solicitudes.py` (modificar) | Aprobar con rol, rechazar con motivo, historial |
| `desktop/app/views/usuarios.py` (modificar) | Filtros por rol y estado, suspender con motivo, reactivar |
| `desktop/app/views/roles.py` (crear) | Vista «Roles y permisos» |
| `desktop/app/main.py`, `views/acceso.py` (modificar) | Cableado: pantalla de estado y visibilidad por permisos |
| `server/btsync/protocol.py`, `store.py`, `session.py` (modificar) | Mensajes `ACCT`/`ACCTST` y bloqueo de `REC` |
| `docs/protocolo.md`, `docs/protocol-vectors.json` (modificar) | Contrato compartido con Android |
| `mobile/.../auth/*`, `sync/SyncClient.kt`, `ui/pantallas/*` (modificar) | Rol Operador, estado local, pantallas de estado |

---

### Tarea 1: Esquema de Oracle y migración

**Archivos:**
- Modificar: `db/init/01_schema.sql` (tabla `usuarios`, líneas 172-185)
- Crear: `db/init/06_permisos.sql`
- Modificar: `desktop/app/auth.py` (`ROLES`, `NOMBRE_ROL`, `migrar`)
- Prueba: `desktop/tests/test_auth.py`, `desktop/tests/conftest.py` (la fixture `cuentas` crea `usuarios_tst`; debe reflejar el esquema nuevo)

**Interfaces:**
- Produce: columnas `estado VARCHAR2(10) DEFAULT 'PENDIENTE' NOT NULL` con `CHECK` en los cuatro estados, `motivo VARCHAR2(300 CHAR)`, `resuelto_por VARCHAR2(30 CHAR)`, `resuelto TIMESTAMP`, `origen VARCHAR2(10 CHAR) DEFAULT 'ESCRITORIO' NOT NULL` (`ESCRITORIO` o `MOVIL`). El `CHECK` de `rol` acepta `ADMIN`, `INVENTARIO`, `OPERADOR` o NULL. Se elimina `activo`. `auth.OPERADOR = "OPERADOR"`, `auth.ROLES = (ADMIN, INVENTARIO, OPERADOR)`, `auth.ESTADOS`.
- Tabla `permisos(rol VARCHAR2(12), modulo VARCHAR2(30), nivel VARCHAR2(10))`, clave primaria `(rol, modulo)`, `nivel IN ('NINGUNO','CONSULTA','GESTION')`.

- [ ] **Paso 1: Prueba que falla.** En `test_auth.py`, `test_migrar_convierte_activo_en_estado`: crea la tabla con el esquema viejo (con `activo`), inserta tres filas (rol NULL, rol `INVENTARIO` con `activo='S'`, rol `INVENTARIO` con `activo='N'`), llama a `migrar()` y afirma que los estados son `PENDIENTE`, `ACTIVO`, `SUSPENDIDO`, que la columna `ACTIVO` ya no existe y que `migrar()` llamada otra vez no cambia nada.
- [ ] **Paso 2:** Ejecuta `pytest desktop/tests/test_auth.py::test_migrar_convierte_activo_en_estado -v`. Esperado: FALLA (`estado` no existe).
- [ ] **Paso 3:** Actualiza `01_schema.sql` con las columnas y los `CHECK`; crea `06_permisos.sql` con la tabla y los `INSERT` de la matriz inicial de la Tarea 3. Reescribe `migrar()` para ser idempotente: añade columnas faltantes, deriva `estado` desde `rol` y `activo`, amplía el `CHECK` de `rol` y borra `activo`.
- [ ] **Paso 4:** Ajusta la fixture `cuentas` en `conftest.py` al esquema nuevo. Ejecuta `pytest desktop/tests/test_auth.py -v`. Esperado: la prueba nueva pasa; las antiguas que usan `activo` fallan hasta la Tarea 2 (anótalas, no las toques aún).

### Tarea 2: Estados y administración de cuentas en `auth.py`

**Archivos:**
- Modificar: `desktop/app/auth.py`
- Prueba: `desktop/tests/test_auth.py`

**Interfaces:**
- Consume: esquema de la Tarea 1.
- Produce (todas fuera del hilo de la interfaz):
  - `class CuentaSinAcceso(ErrorDeAcceso)` con atributos `usuario: str`, `nombre: str`, `estado: str`, `motivo: str | None`, `registrado: datetime`.
  - `@dataclass(frozen=True) class Usuario` con `usuario, nombre, rol, estado, motivo, origen, clave_solicitada` (sustituye a `activo`).
  - `@dataclass(frozen=True) class Solicitud` con `usuario, nombre, estado, rol, motivo, resuelto_por, resuelto: datetime`.
  - `consultar_cuenta(usuario: str) -> CuentaSinAcceso | None`; `aprobar(quien: Sesion, usuario: str, rol: str) -> None`; `rechazar(quien: Sesion, usuario: str, motivo: str) -> None`; `suspender(quien: Sesion, usuario: str, motivo: str) -> None`; `reactivar(quien: Sesion, usuario: str) -> None`; `historial_solicitudes() -> list[Solicitud]`.
  - `iniciar_sesion` lanza `CuentaSinAcceso` si la contraseña es correcta y el estado no es `ACTIVO`; si el rol es `OPERADOR` lanza `ErrorDeAcceso("Los operadores usan la app móvil.")`.
  - Se eliminan `activar`, `rechazar_cuenta` y `_exigir_admin` (lo sustituye `permisos`, Tarea 3).

- [ ] **Paso 1: Pruebas que fallan** (una por comportamiento, con los textos de la especificación): `test_login_pendiente_lanza_cuenta_sin_acceso` (estado, nombre y fecha en la excepción); `test_aprobar_asigna_rol_y_activa`; `test_rechazar_guarda_motivo_y_bloquea_el_login` (el login con clave correcta lanza `CuentaSinAcceso` con `estado == "RECHAZADO"` y el motivo); `test_motivo_obligatorio_y_maximo_300` (vacío, solo espacios y 301 caracteres dan `ErrorDeAcceso`); `test_suspender_y_reactivar`; `test_segunda_resolucion_falla` (aprobar una cuenta ya aprobada da «Esta solicitud ya fue resuelta»); `test_unico_admin_no_se_suspende`; `test_operador_no_entra_al_escritorio`; `test_historial_lista_resueltas_con_responsable`; `test_registrar_usuario_rechazado_dice_ya_existe`.
- [ ] **Paso 2:** Ejecuta `pytest desktop/tests/test_auth.py -v`. Esperado: FALLAN.
- [ ] **Paso 3:** Implementa las firmas anteriores. Las transiciones usan `UPDATE ... WHERE estado = 'PENDIENTE'` (aprobar y rechazar) o `estado = 'ACTIVO'` (suspender) y comprueban `cur.rowcount`; si es 0 lanzan «Esta solicitud ya fue resuelta». Mantén `cambiar_rol` para cuentas `ACTIVO`.
- [ ] **Paso 4:** Ejecuta `pytest desktop/tests/test_auth.py -v`. Esperado: PASAN todas.

### Tarea 3: Módulo de permisos

**Archivos:**
- Crear: `desktop/app/permisos.py`
- Modificar: `desktop/app/auth.py` (las funciones de administración llaman a `permisos.exigir`)
- Prueba: `desktop/tests/test_permisos.py` (crear)

**Interfaces:**
- Produce:
  - `NINGUNO, CONSULTA, GESTION = "NINGUNO", "CONSULTA", "GESTION"`.
  - `MODULOS: tuple[tuple[str, str], ...]`, pares `(clave, nombre en pantalla)` con los 20 renglones de la matriz de la especificación. Claves usadas por código existente: `dashboard`, `usuarios`, `roles`, `permisos`, `solicitudes`, `existencias`, `bluetooth`, `historial`, `perfil`.
  - `nivel(rol: str, modulo: str) -> str`; `puede(rol: str, modulo: str, minimo: str = CONSULTA) -> bool`; `matriz() -> dict[tuple[str, str], str]`; `guardar(quien: Sesion, rol: str, modulo: str, nivel_nuevo: str) -> None`; `exigir(quien: Sesion, modulo: str, minimo: str = GESTION) -> None` (lanza `ErrorDeAcceso("No tienes permiso para esto.")`).
  - `INTOCABLES`: `(ADMIN, "usuarios")`, `(ADMIN, "solicitudes")`, `(ADMIN, "permisos")`, siempre `GESTION`; `guardar` sobre ellos lanza `ErrorDeAcceso`.

- [ ] **Paso 1: Pruebas que fallan:** `test_matriz_inicial_coincide_con_la_especificacion` (Administrador: Gestión de usuarios `GESTION`; Inventario: usuarios `NINGUNO`; Operador: Tareas de conteo `GESTION` pero Gestión de usuarios `NINGUNO`; Administrador en Ajustes `GESTION`); `test_guardar_cambia_nivel_y_se_lee_de_nuevo`; `test_no_se_puede_quitar_acceso_intocable`; `test_solo_con_permiso_de_permisos_se_guarda`; `test_exigir_niega_a_inventario_gestionar_usuarios`; `test_nivel_de_modulo_inexistente_es_ninguno`.
- [ ] **Paso 2:** Ejecuta `pytest desktop/tests/test_permisos.py -v`. Esperado: FALLA (módulo no existe).
- [ ] **Paso 3:** Implementa `permisos.py` con consultas a la tabla `permisos` (en pruebas, tabla `permisos_tst` mediante una constante `TABLA` como en `auth.py`). Cablea `auth.aprobar`, `rechazar`, `suspender`, `reactivar`, `cambiar_rol` y `restablecer_clave` a `permisos.exigir(quien, "usuarios")`; `resolver_clave` a `"solicitudes"`.
- [ ] **Paso 4:** Ejecuta `pytest desktop/tests -v`. Esperado: PASA todo.

### Tarea 4: Vistas de escritorio

**Archivos:**
- Crear: `desktop/app/views/estado_cuenta.py`, `desktop/app/views/roles.py`
- Modificar: `desktop/app/views/solicitudes.py`, `desktop/app/views/usuarios.py`, `desktop/app/views/acceso.py`, `desktop/app/main.py` (`build_window`, `add_view`, `_secciones`)
- Prueba: `desktop/tests/test_estado_cuenta.py`, `test_solicitudes_view.py`, `test_roles_view.py`, `test_app.py` (crear o ampliar)

**Interfaces:**
- Consume: `auth.CuentaSinAcceso`, `auth.aprobar/rechazar/suspender/reactivar/historial_solicitudes`, `permisos.puede/matriz/guardar`.
- Produce:
  - `class EstadoCuentaView(QWidget)`: `mostrar(cuenta: auth.CuentaSinAcceso) -> None`; señal `volver = pyqtSignal()`. Textos exactos: `PENDIENTE` → «Tu cuenta espera aprobación del administrador», botón «Cerrar sesión»; `RECHAZADO` y `SUSPENDIDO` → «Motivo: {motivo}», botón «Regresar al inicio de sesión». Muestra nombre, usuario, estado y fecha de registro.
  - `add_view(vista, titulo, modulo: str, en_barra=True)` en `MainWindow` reemplaza `solo_admin`; un botón aparece solo si `permisos.puede(rol, modulo)`.
  - `SolicitudesView`: tabla de pendientes con combo de rol (`Administrador`, `Inventario`, `Operador de Inventario`), botones Aprobar y Rechazar (este abre un `QInputDialog` de motivo obligatorio) y debajo el historial (`historial_solicitudes`).
  - `UsuariosView`: filtros por rol y estado, búsqueda por nombre o usuario, botones Suspender (con motivo) y Reactivar.
  - `RolesView`: tabla módulos × roles con un combo `NINGUNO/CONSULTA/GESTION` por celda; las celdas intocables van deshabilitadas; cada cambio llama a `permisos.guardar`.

- [ ] **Paso 1: Pruebas que fallan** (pytest-qt, `QT_QPA_PLATFORM=offscreen`): `test_pendiente_muestra_espera_y_cerrar_sesion`; `test_rechazado_muestra_motivo_y_regresar_al_inicio` (el botón dice «Regresar al inicio de sesión» y NO existe uno que diga «Cerrar sesión»); `test_suspendido_igual_que_rechazado`; `test_solicitudes_rechazar_sin_motivo_no_llama_a_auth`; `test_solicitudes_aprobar_usa_el_rol_del_combo`; `test_historial_se_muestra_con_responsable`; `test_roles_celda_intocable_deshabilitada`; `test_inventario_no_ve_botones_de_admin`; `test_login_de_cuenta_rechazada_abre_estado_cuenta` (con la fake de `desktop/tests/fakes.py`).
- [ ] **Paso 2:** Ejecuta `pytest desktop/tests -k "estado_cuenta or solicitudes or roles or app" -v`. Esperado: FALLAN.
- [ ] **Paso 3:** Implementa las vistas con el estilo de `widgets.py` y `base.py` (`QueryRunner`, `StateBanner`). En `acceso.py`, al capturar `CuentaSinAcceso` en el login y tras un registro que devuelve `None` (usa `consultar_cuenta`), emite la señal que `main.py` conecta con `EstadoCuentaView`; `volver` regresa al formulario de inicio de sesión.
- [ ] **Paso 4:** Ejecuta `pytest desktop/tests -v`. Esperado: PASA todo. Lanza `docker compose up -d app` y revisa a mano las tres pantallas de estado.

### Tarea 5: Protocolo y servidor (`ACCT` / `ACCTST`)

**Archivos:**
- Modificar: `server/btsync/protocol.py`, `server/btsync/store.py`, `server/btsync/session.py`, `docs/protocolo.md`, `docs/protocol-vectors.json`
- Prueba: `server/tests/test_protocol.py`, `server/tests/test_controller.py`, `server/tests/test_e2e_tcp.py`

**Interfaces:**
- Produce:
  - Mensaje móvil → PC `ACCT|<usuario>|<nombre>` y PC → móvil `ACCTST|<usuario>|<estado>|<rol>|<motivo>` (`rol` y `motivo` pueden venir vacíos). `_MIN_PARTS`: `ACCT: 3`, `ACCTST: 5`. `PROTOCOL_VERSION = "3"`. Orden: `HELLO`, `ACCT`, y el PC responde `ACCTST` antes del catálogo.
  - Motivo de `NAK` nuevo: `CUENTA_NO_ACTIVA`, con el `seq` esperado.
  - `@dataclass(frozen=True) class EstadoCuenta` con `estado: str`, `rol: str | None`, `motivo: str | None` y `Store.sincronizar_cuenta(usuario: str, nombre: str) -> EstadoCuenta`: crea la fila como `PENDIENTE`, `origen='MOVIL'`, `clave_hash='-'` si no existe; si existe con `origen='ESCRITORIO'` devuelve `EstadoCuenta("RECHAZADO", None, "Ese usuario ya existe en el PC")` sin modificar nada; si existe con `origen='MOVIL'` devuelve su estado actual.

- [ ] **Paso 1: Pruebas que fallan:** `test_acct_acctst_round_trip_con_crc` (con un vector nuevo en `protocol-vectors.json`, incluido un motivo con `|` y salto de línea); `test_sincronizar_cuenta_crea_pendiente`; `test_sincronizar_cuenta_idempotente`; `test_usuario_igual_a_cuenta_de_escritorio_se_rechaza`; `test_rec_con_cuenta_pendiente_recibe_nak_cuenta_no_activa`; `test_rec_con_cuenta_activa_se_acepta`; `test_rec_sin_acct_previo_recibe_nak`; `test_e2e_aprobar_a_mitad_de_sesion_no_cambia_la_sesion_en_curso` (la nueva autorización rige desde la siguiente sesión).
- [ ] **Paso 2:** Ejecuta `docker compose run --rm pybase pytest server/tests -v`. Esperado: FALLAN las nuevas.
- [ ] **Paso 3:** Implementa los mensajes y `Store.sincronizar_cuenta` (por `connect_oracle`, con `MERGE` o `INSERT` más captura de `ORA-00001` para dos conexiones simultáneas); en `session.py` guarda el estado tras `ACCT` y rechaza `REC` si no es `ACTIVO`. Actualiza `docs/protocolo.md`.
- [ ] **Paso 4:** Ejecuta `docker compose run --rm pybase pytest server/tests -v`. Esperado: PASA todo.

### Tarea 6: App móvil

**Archivos:**
- Modificar: `mobile/.../auth/Usuario.kt` (entidad y `Rol`), `auth/AuthRepository.kt`, `data/AppDatabase.kt` (migración de Room), `protocol/Protocol.kt`, `sync/SyncClient.kt`, `ui/AuthActivity.kt`, `ui/pantallas/AuthScreen.kt`
- Crear: `mobile/.../ui/pantallas/EstadoCuentaScreen.kt`
- Prueba: `mobile/app/src/test/...` (junto a las pruebas existentes de `AuthRepository`, `Protocol` y `SyncClient`)

**Interfaces:**
- Consume: vectores de `docs/protocol-vectors.json` y mensajes de la Tarea 5.
- Produce:
  - `Rol.OPERADOR = "OPERADOR"` (único rol; se quitan `CLASIFICADOR` y `SUPERVISOR` del registro; migración de Room: filas existentes pasan a `OPERADOR`); `object EstadoCuenta { PENDIENTE, ACTIVO, RECHAZADO, SUSPENDIDO }`.
  - `UsuarioEntity` gana `estado: String = EstadoCuenta.PENDIENTE`, `motivo: String? = null`.
  - `AuthRepository.aplicarEstado(usuario: String, estado: String, rol: String?, motivo: String?)` y `AuthResult` / `Sesion` expone `estado` y `motivo`.
  - `Protocol`: codifica `ACCT` y decodifica `ACCTST` con los mismos vectores que el servidor.
  - `SyncClient`: envía `ACCT` tras `HELLO`, aplica `ACCTST` con `aplicarEstado`, y si el estado no es `ACTIVO` no envía `REC` (las lecturas quedan en el búfer).
  - `EstadoCuentaScreen(estado, nombre, usuario, motivo, registrado, alComprobar, alSalir)`: mismos textos y botones que el escritorio. En PENDIENTE: «Comprobar estado» (abre una sincronización solo de cuenta) y «Cerrar sesión». En RECHAZADO y SUSPENDIDO: «Regresar al inicio de sesión».

- [ ] **Paso 1: Pruebas que fallan:** `ProtocolTest.acctYAcctstCoincidenConLosVectores`; `AuthRepositoryTest.registroNuevoQuedaPendiente`; `aplicarEstadoActivoDejaEntrar`; `aplicarEstadoRechazadoGuardaElMotivo`; `SyncClientTest.conCuentaSuspendidaNoEnviaRegistrosYLosConserva`; `SyncClientTest.conCuentaActivaEnviaRegistros`; `migracionDeRolesLlevaClasificadorYSupervisorAOperador`.
- [ ] **Paso 2:** Ejecuta `docker compose --profile build run --rm apk-build ./gradlew testDebugUnitTest`. Esperado: FALLAN las nuevas.
- [ ] **Paso 3:** Implementa lo anterior. En `AuthActivity`, tras un inicio de sesión correcto, enruta a `EstadoCuentaScreen` si `estado != ACTIVO`; si es `ACTIVO`, entra al flujo normal.
- [ ] **Paso 4:** Ejecuta `gradlew testDebugUnitTest` y `gradlew assembleDebug`. Esperado: PASAN y compila.

### Tarea 7: Documentación y verificación de extremo a extremo

**Archivos:**
- Modificar: `docs/arquitectura.md`, `docs/demo.md`, `README.md`, `docs/uml/04-modelo-datos.puml` (y regenerar su SVG con `tools/render_uml.sh`)

- [ ] **Paso 1:** Documenta los estados, roles, matriz y mensajes `ACCT`/`ACCTST`; añade al guion de `demo.md` el flujo «registrar operador en el móvil → PENDIENTE → aprobar en Solicitudes → ACTIVO → sincronizar».
- [ ] **Paso 2:** Ejecuta las tres suites completas (comandos en Restricciones globales). Esperado: todo en verde.
- [ ] **Paso 3:** Prueba manual con `docker compose up -d` y el emulador: registra un operador, apruébalo, suspéndelo con motivo y confirma que el móvil muestra la pantalla con ese motivo y «Regresar al inicio de sesión».
