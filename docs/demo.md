# Guion de demo (5 minutos)

Datos: el conteo `CONT-2026-11` de la semilla (58 SKU). La demo muestra el ciclo completo: **contar sin
red → disparar en el PC → subir → batch → conciliación → un faltante en pesos → cerrar el conteo**.

## Antes de empezar (2 minutos, sin público)

```bash
docker compose up -d --wait oracle
```

```bash
docker compose up -d app
```

- Celular: APK instalada (ver README), operador ya escrito, Bluetooth encendido y **modo avión con el Bluetooth
  encendido** (la demo es «sin wifi»). El PC no debe estar emparejado: es lo que se quiere mostrar.
- Deja ~10 productos listos para escanear (códigos de barras impresos, SKU = código).
- Opcional: partir de una base limpia (ver «Quiero empezar con la base limpia» en el README).

## Guion

| Min | Qué se hace | Qué se dice / qué se ve |
|---|---|---|
| 0:00 | Iniciar sesión en el PC (la primera cuenta es administradora) y mostrar el **Dashboard**: el conteo `CONT-2026-11` está sin contar. | «Hay 58 productos en el sistema; nadie ha contado nada.» Tarjetas en 0 % de avance. |
| 0:15 | En el celular: **crear cuenta** → queda *PENDIENTE*. En el PC el servicio Bluetooth ya está escuchando; en el celular: **Comprobar estado**. En el PC, **Solicitudes**: la cuenta llegó desde el celular → elegir *Operador de Inventario* → **Aprobar**. En el celular: **Comprobar estado** otra vez → entra. | «Nadie trabaja sin aprobación.» Si se rechaza o suspende, el celular muestra el motivo y «Regresar al inicio de sesión». |
| 0:30 | En el celular, en **modo avión**: elegir el conteo, **escanear** 3–4 códigos con la cámara y digitar 1 a mano. Recontar uno (se avisa «reemplaza la lectura anterior»). Mostrar **Pendientes**. | «Sin wifi ni red celular: todo queda guardado en el teléfono.» Cada lectura aparece `PENDIENTE`. |
| 1:30 | En el PC, pantalla **Sincronización**. | El servicio Bluetooth está *activo* y el PC se anuncia como `gestion_inventario` (no con el nombre del equipo), aunque se cierre la ventana. «Pausar» lo detiene sin cortar una sincronización en curso. |
| 2:00 | En el celular: **Sincronizar** (la primera vez se elige `gestion_inventario`; las siguientes conecta directo). | Sin código ni emparejamiento (D22). Barra de progreso; la app de escritorio muestra *recibiendo* y el contador de lectura. |
| 2:45 | Terminar: en el celular aparece el resultado (`BYE`: aceptadas/rechazadas); en el PC el estado pasa a *procesando* y luego *listo*. | «El batch de Oracle corrió fuera de la conexión; el celular no esperó.» Las lecturas del celular pasan a `CONFIRMADO`. |
| 3:15 | Pantallas **Dashboard** (avance, exactitud, valor faltante y sobrante) e **Inventario** (tabla con filtros). Abrir un SKU para ver sus lecturas. | «Se concilió contra el stock del sistema.» |
| 3:45 | Pantalla **Gráficas** y mostrar **un faltante con su valor en pesos** (gráfica *Mayores desvíos por SKU*, o filtrar por `Faltante` en Inventario). | Leer el SKU y el valor (formato `-$ 5.000`: negativo = faltante). |
| 4:15 | En **Sincronización**, abajo: las lecturas con error y su motivo (p. ej. SKU desconocido) y **Reprocesar errores** (administrador). | «Los errores no se pierden: se corrigen y se reprocesan.» |
| 4:30 | **Dashboard** → **Cerrar conteo** (administrador) → confirmar. | La confirmación avisa que es irreversible; los SKU sin contar pasan de `SIN_CONTAR` a `FALTANTE` y el avance llega a 100 %. |

## Plan B si falla el Bluetooth

El PC usa el transporte TCP y el teléfono simulado hace el conteo físico de `tools/truth.json` (el mismo flujo, sin radio):

```bash
BT_TRANSPORT=tcp docker compose up -d bluetooth app
```

Con el servicio por TCP (`BT_TRANSPORT=tcp docker compose up -d bluetooth`), en otra terminal:

```bash
python3 tools/fake_phone.py --host 127.0.0.1 --port 9000 --seed 42 --dirty --uuid demo-fake
```

`--dirty` agrega 3 lecturas con error y 3 recuentos (para mostrar las lecturas con error y el reemplazo). Códigos de salida:
0 todo confirmado, 1 algo pendiente, 2 sin conexión, 3 PC ocupado. En el ensayo del 2026-11-11 con estos mismos argumentos
(otro `--uuid`) entraron 89 líneas en 0,1 s, el batch dejó 86 lecturas procesadas y 3 errores, y la conciliación quedó con
60 de 60 SKU contados, exactitud 83,33 %, faltante −$ 143.400 y sobrante $ 1.303.200.

## Si algo falla en vivo

- El celular no conecta: revisar que la ventana siga abierta (120 s) y pasar al plan B.
- La ventana no se abre: revisar `DISPLAY` (README, solución de problemas).
- Para repetir la demo: base limpia (README) y reinstalar o limpiar los datos de la APK **solo si no hay lecturas pendientes**.
