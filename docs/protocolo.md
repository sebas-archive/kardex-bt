# Protocolo móvil ↔ PC

Implementación de referencia: `server/btsync/protocol.py`. Los vectores de prueba compartidos con la app Android
están en `protocol-vectors.json`.

El sistema final usa la **versión 5 sin cambios de mensajes ni de campos**. Lo que cambió es el contenido: hay un
solo conteo continuo (`ACTUAL`) y un solo catálogo pseudo (`CATALOGO`).

## Formato de línea

- UTF-8, **una línea por mensaje**, terminada en `\n`.
- Campos separados por `|`. Al final, `*` y el **CRC32** en 8 dígitos hexadecimales mayúsculos, calculado sobre los
  bytes que preceden al último `*`.
- **Máximo 4000 bytes por línea**, sin el `\n` y con el CRC incluido.
- En campos de texto libre se codifican `%` → `%25`, `|` → `%7C`, `\r` → `%0D` y `\n` → `%0A` (el `%` se codifica
  primero y se decodifica en una sola pasada).

Ejemplo: `HELLO|5|dev-0001|Bodega Norte*788FF277`.

## Móvil → PC

| Mensaje | Campos |
|---|---|
| `HELLO` | `5` (versión del protocolo), `<uuid_dispositivo>`, `<nombre>` |
| `ACCT` | `<usuario>`, `<nombre>` — la cuenta del operador; va justo después de `HELLO` |
| `INICIO` | `<id>` — se tolera y **se ignora**; la app puede omitirlo |
| `REC` | `<seq>`, `<epoch_ms>`, `ACTUAL`, `<sku>`, `<cantidad>`, `<operador>`, `<nota>`, `<danados>` (vacío si no se indicó; nunca mayor que la cantidad) |
| `FOTO` | `<seq>`, `<parte>`, `<total>`, `<crc32>`, `<base64>` — una parte de la foto de la lectura `seq` (hasta 2700 caracteres de base64 por línea); `crc32` es el del archivo JPG completo |
| `END` | `<n_registros>` |

`cantidad` es decimal con punto, `^\d{1,9}(\.\d{1,3})?$`. `seq` empieza en 1 y es contiguo por dispositivo.

## PC → móvil

| Mensaje | Campos |
|---|---|
| `ACCTST` | `<usuario>`, `<estado>`, `<rol>`, `<motivo>` — estado de la cuenta: `PENDIENTE`, `ACTIVO`, `RECHAZADO` o `SUSPENDIDO`; `rol` y `motivo` pueden ir vacíos |
| `READY` | `<ultimo_seq_confirmado>`, `<epoch_ms_servidor>` |
| `CATTAREA` | `<id>`, `<nombre>`, `<texto1>`, `<texto2>`, `<estado>`, `<total_productos>`, `<contados>` — en el sistema final hay **una sola área**: `CATALOGO`, `Catálogo`, los dos campos de texto **vacíos**, estado `ABIERTO`, total de productos del catálogo y SKU con lectura vigente |
| `CATITEM` | `<id_catalogo>`, `<sku>`, `<recuento>` — un producto del catálogo; en el sistema final `recuento` es `N` (el campo se conserva por compatibilidad). Nunca lleva la cantidad del sistema (conteo ciego) |
| `CATPROD` | `<sku>`, `<nombre>`, `<categoria>`, `<unidad>` |
| `CAT_END` | (sin campos) |
| `ACK` | `<seq>` — acumulativo: todo `seq ≤ n` está persistido con COMMIT |
| `NAK` | `<seq_esperado>`, `<motivo>` |
| `BYE` | `<aceptados>`, `<rechazados>` |
| `FOTOOK` | `<seq>` — la foto llegó completa y quedó guardada |
| `FOTOERR` | `<seq>`, `<motivo>` — `CRC`, `FORMAT` (parte fuera de orden), `GRANDE` (más de 2 MB) o `SIN_LECTURA` |

El catálogo **nunca** lleva el stock del sistema (conteo ciego). El área `CATALOGO` es la única que se envía.

## NAK y retroceso (go-back-N)

Todo `NAK` lleva el `seq` que el servidor espera a continuación; el móvil retrocede y reenvía desde ahí. Motivos:
`CRC`, `FORMAT`, `LINEA_LARGA`, `SECUENCIA`, `DB_NO_DISPONIBLE`, `CUENTA_NO_ACTIVA` y `OCUPADO` (con `seq` 0). Tras un
`NAK` el servidor ignora en silencio los `REC` siguientes hasta recibir el `seq` esperado.

Con `esperado = último_persistido + 1`:

- `seq < esperado`: duplicado, no se inserta (lo cubre el siguiente `ACK`).
- `seq = esperado`: se inserta.
- `seq > esperado` (hueco): un único `NAK|esperado|SECUENCIA`.

## Sincronización

1. El móvil envía `HELLO` y `ACCT`; el PC responde `ACCTST`, `READY` y luego el catálogo completo
   (`CATTAREA|CATALOGO`, `CATITEM` por producto, `CATPROD` por producto y `CAT_END`). Si después de `HELLO` no llega
   `ACCT`, el PC responde `NAK|0|FORMAT` y cierra.
2. Si la cuenta está activa, el móvil envía las lecturas (`REC`), hasta 50 sin esperar `ACK`. `INICIO` es opcional y
   el PC lo ignora.
3. El servidor hace COMMIT cada 25 registros insertados o al `END`, y recién entonces envía `ACK`.
4. Tras `END` el servidor envía `BYE|<aceptados>|<rechazados>`: `aceptados` son las filas nuevas insertadas en esa
   sesión y `rechazados` la cantidad de `NAK` enviados; los duplicados no cuentan. `BYE` no informa del resultado del
   batch (lo dispara el controlador después).

## Herramienta de línea de comandos

```bash
python -m btsync.protocol --frame REC 1 1731170400000 ACTUAL A-01 7701234000011 12.5 Ana ok
python -m btsync.protocol --parse 'ACK|3*6A8544FA'
```

`--frame` recibe el tipo y los campos en **texto plano** (los codifica solo).

## Cuentas y permisos

- Si la cuenta del móvil no existe en Oracle, el PC la crea **PENDIENTE** (origen `MOVIL`) para que el Administrador
  la apruebe en «Solicitudes». Solo puede quedar como **Operador de Inventario**.
- Solo una cuenta `ACTIVO` entrega lecturas. Con otro estado, el primer `REC` recibe
  `NAK|<seq>|CUENTA_NO_ACTIVA` y los demás se ignoran; el `BYE` cuenta ese rechazo. El móvil conserva las lecturas y
  las envía cuando la cuenta se active.
- El estado se lee al empezar y vale para toda la sesión: una aprobación a mitad de sesión rige desde la siguiente.
- Un usuario que ya existe como cuenta del PC (origen `ESCRITORIO`) no se toca: el móvil recibe
  `ACCTST|<usuario>|RECHAZADO||Ese usuario ya existe en el PC`.
- La cuenta queda **vinculada al teléfono** (UUID del `HELLO`) que la registró. Desde otro teléfono el PC responde
  `SUSPENDIDO` con el motivo «Esta cuenta está vinculada a otro teléfono…» y no acepta lecturas, hasta que el
  Administrador pulse **Desvincular teléfono** en «Empleados» (por ejemplo, tras reinstalar la app).
- Si la matriz quita al rol Operador la gestión de **Sincronización** (`sync`), el PC responde `SUSPENDIDO` con el
  motivo «Tu rol no tiene permiso para sincronizar…».
- `ACCT` se valida como en los clientes: usuario `[a-z0-9._-]{3,30}` y nombre de 1 a 60 caracteres; si no,
  `NAK|0|FORMAT`.
- La contraseña del Operador **no viaja** en el protocolo: vive en el teléfono. El Administrador no la resetea desde
  el PC; el Operador la recupera con su pregunta de seguridad local.

## Versiones

- **Versión 2 (sin ubicación):** la 1 llevaba la ubicación en el `REC` y el PC enviaba `CATUBIC`. La 2 las quitó: un
  `REC` tiene 8 partes y el catálogo no incluye ubicaciones. Un teléfono con otra versión recibe
  `NAK|0|FORMAT` y no se guarda nada.
- **Versión 3 (cuentas):** `HELLO`, `ACCT` y `ACCTST`; la cuenta del móvil llega al PC y queda pendiente. Los
  vectores incluyen `ACCT`, dos `ACCTST` y el `NAK` de cuenta no activa.
- **Versión 4 (catálogo por área):** `CATTAREA` + `CATITEM` para agrupar productos e `INICIO` para avisar que se
  empezó. En el sistema final el único grupo es el pseudo `CATALOGO`; `INICIO` se ignora.
- **Versión 5 (dañados y fotos):** el `REC` gana el campo `danados`; las fotos viajan después de las lecturas y antes
  del `END`, una a la vez, con `FOTOOK`/`FOTOERR`. Un `REC` de la versión 4 (8 partes) no se acepta.
