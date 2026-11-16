# Guion de demo (5 minutos)

Datos: el conteo continuo `ACTUAL` de la semilla (120 SKU; con `08_demo.sql` ya trae 30 días de historia y las cuentas `admin`/`inventario`, clave `Demo1234`). La demo muestra el ciclo completo: **contar sin red →
subir por Bluetooth → batch → conciliación → inventario y gráficas → alta de un SKU → reproceso**. No hay cierre de
conteo: el sistema siempre está contando.

## Antes de empezar (2 minutos, sin público)

```bash
docker compose up -d --wait oracle
```

```bash
docker compose up -d bluetooth app
```

- Celular: APK instalada (ver README), Bluetooth encendido y **modo avión con el Bluetooth encendido** (la demo es
  «sin wifi»). El PC no debe estar emparejado: es lo que se quiere mostrar.
- Deja ~10 productos listos para escanear (códigos de barras impresos, SKU = código).
- Opcional: partir de una base limpia (ver «Quiero empezar con la base limpia» en el README).

## Guion

| Min | Qué se hace | Qué se dice / qué se ve |
|---|---|---|
| 0:00 | Crear la primera cuenta del PC (queda como Administrador y Activa) e iniciar sesión; mostrar el **Dashboard**. | «Hay 120 productos en el sistema.» Con los datos de demo el avance parte en ~83 %; sin `08_demo.sql`, en 0 %. |
| 0:15 | En el celular: **Crear cuenta** (usuario, nombre, correo opcional y pregunta de seguridad) → queda *PENDIENTE*. En el PC, **Solicitudes**: aprobar como *Operador de Inventario*. En el celular: **Comprobar estado** → entra. | «Nadie trabaja sin aprobación.» Si se rechaza o suspende, el celular muestra el motivo. |
| 0:30 | En el celular, en **modo avión**: **Catálogo**, abrir un producto, **escanear** 3–4 códigos y digitar 1 a mano. Recontar uno (se avisa que reemplaza la lectura anterior). Mostrar **Pendientes**. | «Sin wifi ni red celular: todo queda guardado en el teléfono.» Cada lectura aparece `PENDIENTE`. |
| 1:30 | En el PC, pantalla **Sincronización**. | El servicio está *activo* y el PC se anuncia como `gestion_inventario`, aunque se cierre la ventana. «Pausar» lo detiene sin cortar una sincronización en curso. |
| 2:00 | En el celular: **Sincronizar** (la primera vez se elige `gestion_inventario`; las siguientes conecta directo). | Sin código ni emparejamiento (D22). Barra de progreso; el escritorio muestra *recibiendo* y el contador de lecturas. |
| 2:45 | Terminar: en el celular aparece el resultado (`BYE`: aceptadas/rechazadas); en el PC el estado pasa a *procesando* y luego *listo*. | «El batch de Oracle corrió fuera de la conexión; el celular no esperó.» Las lecturas del celular pasan a `CONFIRMADO`. |
| 3:15 | Pantallas **Dashboard** (avance, contados, procesadas, errores) e **Inventario** (SKU, producto, categoría, contada, sistema). Abrir un SKU para ver sus lecturas y la foto. | «Se concilió contra el stock del sistema; el inventario no clasifica ni muestra diferencia.» |
| 3:45 | Pantalla **Gráficas**: avance por categoría, contados vs. pendientes, lecturas por hora, por operador, mayores diferencias y unidades dañadas. | «El Dashboard puede usar la diferencia como referencia; el inventario no la muestra.» |
| 4:15 | En **Sincronización**, abajo: una lectura con error (`SKU_DESCONOCIDO`), **Dar de alta el SKU** (nombre y categoría; queda con stock 0) y **Reprocesar errores**. | «Los errores no se pierden: se corrigen, se da de alta el producto y se reprocesan.» |
| 4:45 | **Perfil**: cambiar tema a oscuro y idioma a inglés, y volver. Cerrar sesión. | «El tema y el idioma son de cada usuario; se aplican al instante.» |

## Plan B si falla el Bluetooth

El PC usa el transporte TCP y el teléfono simulado hace el conteo físico de `tools/truth.json` (el mismo flujo, sin
radio):

```bash
BT_TRANSPORT=tcp docker compose up -d bluetooth app
```

Con el servicio por TCP, en otra terminal:

```bash
python3 tools/fake_phone.py --host 127.0.0.1 --port 9000 --seed 42 --dirty --uuid demo-fake
```

`--dirty` agrega lecturas con error y recuentos (para mostrar el error y el reemplazo). Códigos de salida:
0 todo confirmado, 1 algo pendiente, 2 sin conexión, 3 PC ocupado. Los números exactos dependen de la semilla y de
la corrida; lo que importa es que el celular simulado reciba `BYE` y la conciliación de `ACTUAL` quede actualizada.

## Si algo falla en vivo

- El celular no conecta: revisar que el servicio siga activo y pasar al plan B.
- La ventana no se abre: revisar `DISPLAY` (README, solución de problemas).
- Para repetir la demo: base limpia (README) y reinstalar o limpiar los datos de la APK **solo si no hay lecturas
  pendientes**.
