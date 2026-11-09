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

Ejemplo: `HELLO|1|dev-0001|Bodega Norte*78D353E4`.

## Móvil → PC

| Mensaje | Campos |
|---|---|
| `HELLO` | `1`, `<uuid_dispositivo>`, `<nombre>` |
| `REC` | `<seq>`, `<epoch_ms>`, `<id_conteo>`, `<ubicacion>`, `<sku>`, `<cantidad>`, `<operador>`, `<nota>` |
| `END` | `<n_registros>` |

`cantidad` es decimal con punto, `^\d{1,9}(\.\d{1,3})?$`. `seq` empieza en 1 y es contiguo por
dispositivo.

## PC → móvil

| Mensaje | Campos |
|---|---|
| `READY` | `<ultimo_seq_confirmado>`, `<epoch_ms_servidor>` |
| `CATCONTEO` | `<id>`, `<nombre>` |
| `CATUBIC` | `<cod>`, `<zona>`, `<descripcion>` |
| `CATPROD` | `<sku>`, `<nombre>`, `<categoria>`, `<unidad>` |
| `CAT_END` | (sin campos) |
| `ACK` | `<seq>` — acumulativo: todo `seq ≤ n` está persistido con COMMIT |
| `NAK` | `<seq_esperado>`, `<motivo>` |
| `BYE` | `<aceptados>`, `<rechazados>` |

Solo se envían conteos en estado `ABIERTO`, y **nunca** el stock del sistema (conteo ciego).

## NAK y retroceso (go-back-N)

Todo `NAK` lleva el `seq` que el servidor espera a continuación; el móvil retrocede y reenvía
desde ahí. Motivos: `CRC`, `FORMAT`, `LINEA_LARGA`, `SECUENCIA`, `DB_NO_DISPONIBLE` y `OCUPADO`
(con `seq` 0). Tras un `NAK` el servidor ignora en silencio los `REC` siguientes hasta recibir
el `seq` esperado.

Con `esperado = último_persistido + 1`:

- `seq < esperado`: duplicado, no se inserta (lo cubre el siguiente `ACK`).
- `seq = esperado`: se inserta.
- `seq > esperado` (hueco): un único `NAK|esperado|SECUENCIA`.

## Sincronización

1. El móvil envía `HELLO`; el PC responde `READY` y luego el catálogo completo (`CAT*`) y `CAT_END`.
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
