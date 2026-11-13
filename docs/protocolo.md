# Protocolo móvil ↔ PC

Implementación de referencia: `server/btsync/protocol.py`. Los vectores de prueba compartidos
con la app Android están en `protocol-vectors.json`.

## Formato de línea

- UTF-8, **una línea por mensaje**, terminada en `\n`.
- Campos separados por `|`. Al final, `*` y el **CRC32** en 8 dígitos hexadecimales
  mayúsculos, calculado sobre los bytes que preceden al último `*`.
- **Máximo 4000 bytes por línea**, sin el `\n` y con el CRC incluido.
- En campos de texto libre se codifican `%` → `%25`, `|` → `%7C`, `\r` → `%0D` y `\n` → `%0A`
  (el `%` se codifica primero y se decodifica en una sola pasada).

Ejemplo: `HELLO|3|dev-0001|Bodega Norte*9545800D`.

## Móvil → PC

| Mensaje | Campos |
|---|---|
| `HELLO` | `3` (versión del protocolo), `<uuid_dispositivo>`, `<nombre>` |
| `ACCT` | `<usuario>`, `<nombre>` — la cuenta del operador; va justo después de `HELLO` |
| `REC` | `<seq>`, `<epoch_ms>`, `<id_conteo>`, `<sku>`, `<cantidad>`, `<operador>`, `<nota>` |
| `END` | `<n_registros>` |

`cantidad` es decimal con punto, `^\d{1,9}(\.\d{1,3})?$`. `seq` empieza en 1 y es contiguo por
dispositivo.

## PC → móvil

| Mensaje | Campos |
|---|---|
| `ACCTST` | `<usuario>`, `<estado>`, `<rol>`, `<motivo>` — estado de la cuenta: `PENDIENTE`, `ACTIVO`, `RECHAZADO` o `SUSPENDIDO`; `rol` y `motivo` pueden ir vacíos |
| `READY` | `<ultimo_seq_confirmado>`, `<epoch_ms_servidor>` |
| `CATCONTEO` | `<id>`, `<nombre>` |
| `CATPROD` | `<sku>`, `<nombre>`, `<categoria>`, `<unidad>` |
| `CAT_END` | (sin campos) |
| `ACK` | `<seq>` — acumulativo: todo `seq ≤ n` está persistido con COMMIT |
| `NAK` | `<seq_esperado>`, `<motivo>` |
| `BYE` | `<aceptados>`, `<rechazados>` |

Solo se envían conteos en estado `ABIERTO`, y **nunca** el stock del sistema (conteo ciego).

## NAK y retroceso (go-back-N)

Todo `NAK` lleva el `seq` que el servidor espera a continuación; el móvil retrocede y reenvía
desde ahí. Motivos: `CRC`, `FORMAT`, `LINEA_LARGA`, `SECUENCIA`, `DB_NO_DISPONIBLE`, `CUENTA_NO_ACTIVA` y `OCUPADO`
(con `seq` 0). Tras un `NAK` el servidor ignora en silencio los `REC` siguientes hasta recibir
el `seq` esperado.

Con `esperado = último_persistido + 1`:

- `seq < esperado`: duplicado, no se inserta (lo cubre el siguiente `ACK`).
- `seq = esperado`: se inserta.
- `seq > esperado` (hueco): un único `NAK|esperado|SECUENCIA`.

## Sincronización

1. El móvil envía `HELLO` y `ACCT`; el PC responde `ACCTST`, `READY` y luego el catálogo completo (`CAT*`) y `CAT_END`.
   Si después de `HELLO` no llega `ACCT`, el PC responde `NAK|0|FORMAT` y cierra.
2. El móvil envía hasta 50 `REC` sin esperar `ACK`.
3. El servidor hace COMMIT cada 25 registros insertados o al `END`, y recién entonces envía `ACK`.
4. Tras `END` el servidor envía `BYE|<aceptados>|<rechazados>`: `aceptados` son las filas nuevas
   insertadas en esa sesión y `rechazados` la cantidad de `NAK` enviados; los duplicados no cuentan.
   `BYE` no informa del resultado del batch (lo dispara el controlador después).

## Herramienta de línea de comandos

```bash
python -m btsync.protocol --frame REC 1 1731170400000 CONT-2026-11 A-01 7701234000011 12.5 Ana ok
python -m btsync.protocol --parse 'ACK|3*6A8544FA'
```

`--frame` recibe el tipo y los campos en **texto plano** (los codifica solo).

## Versión 2 (sin ubicación)

La versión 1 llevaba la ubicación en el `REC` y el PC enviaba `CATUBIC`. La **versión 2** las quitó: un `REC` tiene 8 partes
(`REC` más 7 campos) y el catálogo ya no incluye ubicaciones. El `HELLO` lleva la versión; un teléfono con la versión 1 recibe
`NAK|0|FORMAT` y no se guarda nada. Los 7 vectores de `protocol-vectors.json` se regeneraron para la versión 2.

## Versión 3 (cuentas de operador)

El móvil identifica la cuenta del operador con `ACCT|<usuario>|<nombre>` justo después de `HELLO`. Si la cuenta no existe en
Oracle, el PC la crea **PENDIENTE** (origen `MOVIL`) para que el administrador la apruebe en «Solicitudes». El PC responde
`ACCTST` con el estado, el rol y, si la rechazaron o suspendieron, el motivo (texto libre codificado como cualquier otro).

- Solo una cuenta `ACTIVO` entrega lecturas. Con otro estado, el primer `REC` recibe `NAK|<seq>|CUENTA_NO_ACTIVA` y los demás
  se ignoran; el `BYE` cuenta ese rechazo. El móvil conserva las lecturas en su búfer y las envía cuando la cuenta se active.
- El estado se lee al empezar y vale para toda la sesión: una aprobación a mitad de sesión rige desde la siguiente.
- Un usuario que ya existe como cuenta del PC (origen `ESCRITORIO`) no se toca: el móvil recibe
  `ACCTST|<usuario>|RECHAZADO||Ese usuario ya existe en el PC`.
- Para solo consultar el estado (botón «Comprobar estado» del móvil) basta `HELLO`, `ACCT` y `END|0`.
- La cuenta queda **vinculada al teléfono** (UUID del `HELLO`) que la registró. Desde otro teléfono el PC responde
  `SUSPENDIDO` con el motivo «Esta cuenta está vinculada a otro teléfono…» y no acepta lecturas, hasta que el
  administrador pulse **Desvincular teléfono** en «Empleados» (p. ej. tras reinstalar la app).
- Si la matriz quita al rol Operador la gestión de **Bluetooth**, el PC responde `SUSPENDIDO` con el motivo
  «Tu rol no tiene permiso para sincronizar…».
- `ACCT` se valida como en los clientes: usuario `[a-z0-9._-]{3,30}` y nombre de 1 a 60 caracteres; si no, `NAK|0|FORMAT`.

Los vectores de `protocol-vectors.json` (11) incluyen `ACCT`, dos `ACCTST` y el `NAK` de cuenta no activa.
