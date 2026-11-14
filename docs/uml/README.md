# Diagramas UML

Los diagramas están escritos en **PlantUML** (`*.puml`, fuente) y se dibujan a SVG en `../img/uml/`.
Son 22 diagramas de 13 tipos. Se escribieron contra el código real: los nombres de clases, mensajes, estados y
tablas son los del proyecto, y una prueba (`server/tests/test_uml.py`) comprueba que las clases de los diagramas
01, 02 y 03 existen en el código.

Regenerar los SVG (PlantUML 1.2024.7 en Docker, sin instalar nada en el host):

```bash
tools/render_uml.sh
```

Comprobar que los diagramas de clases no se desvían del código:

```bash
docker compose run --rm pybase pytest server/tests/test_uml.py -v
```

## Estructura (qué hay)

| Archivo | Tipo UML | Qué muestra |
|---|---|---|
| [01-clases-servidor.puml](01-clases-servidor.puml) | Clases | La librería `btsync`: `Message`, `Rec`, `FrameError`, `Store`, `Session`, `SyncController`, `Transport` y `Connection` con `BluezTransport` y `TcpTransport`. El controlador crea una sesión por conexión y ambos hablan con el transporte y con Oracle. |
| [02-clases-escritorio.puml](02-clases-escritorio.puml) | Clases | La app de escritorio: `MainWindow` con las vistas del rol, `ServicioRemoto`, `QueryRunner`/`QueryWorker` y el módulo `db`. Las vistas nunca consultan en el hilo de la interfaz. |
| [03-clases-android.puml](03-clases-android.puml) | Clases | La APK (MVVM): pantallas, cuentas locales (`AuthRepository`), `CountViewModel`, `SyncRunner`, `SyncClient`, `Protocol`, `Outbox` y el catálogo en Room. |
| [04-modelo-datos.puml](04-modelo-datos.puml) | Clases con `«table»` (entidad-relación) | Las 17 tablas de Oracle (14 de esquema y 3 que crea la app) con claves, llaves foráneas y cardinalidades. |
| [05-objetos-instantanea.puml](05-objetos-instantanea.puml) | Objetos | Una lectura de `ACTUAL`: de la línea `REC` a la fila de `CONCILIACION` (A-01: 100 en sistema, 101 contado, recuento vigente). |
| [06-componentes.puml](06-componentes.puml) | Componentes | APK, app de escritorio, Oracle y BlueZ, con las interfaces RFCOMM, D-Bus y SQL\*Net. |
| [07-despliegue.puml](07-despliegue.puml) | Despliegue | Celular, PC host y los contenedores Docker, con los enlaces RFCOMM, D-Bus, X11 y el puerto 1521. |
| [08-paquetes.puml](08-paquetes.puml) | Paquetes | Módulos de `btsync`, `desktop.app` y `mobile` y sus dependencias. |
| [09-estructura-compuesta.puml](09-estructura-compuesta.puml) | Estructura compuesta | El interior de `SyncController`: puertos hacia el transporte, el repositorio y la GUI, y sus partes. |

## Comportamiento (qué pasa)

| Archivo | Tipo UML | Qué muestra |
|---|---|---|
| [10-casos-de-uso.puml](10-casos-de-uso.puml) | Casos de uso | Operador, Inventario, Administrador y Scheduler de Oracle con sus casos, `«include»` y `«extend»`. |
| [11-actividad-conteo-movil.puml](11-actividad-conteo-movil.puml) | Actividad con carriles | El flujo del operador en el móvil: iniciar sesión, abrir el Catálogo, escanear (barras o QR), guardar y sincronizar. |
| [12-actividad-batch.puml](12-actividad-batch.puml) | Actividad con carriles (Móvil / App / Oracle) | De la subida al `ACK` y el batch `PROCESAR_PENDIENTES` sobre `ACTUAL` paso a paso. |
| [16-estados-sync-controller.puml](16-estados-sync-controller.puml) | Máquina de estados | `IDLE … ERROR` del controlador, con eventos y guardas (plazo, cancelación, corte, ocupado). |
| [17-estados-fila-transito.puml](17-estados-fila-transito.puml) | Máquina de estados | Una fila de `CAPTURA_TRANSITO`: `PENDIENTE → PROCESANDO → PROCESADO \| ERROR`, con recuperación de huérfanas. |
| [18-estados-lectura-outbox.puml](18-estados-lectura-outbox.puml) | Máquina de estados | Una lectura en el móvil: `PENDIENTE → ENVIADO → CONFIRMADO` y el regreso a `PENDIENTE` tras un corte. |
| [19-estados-cuenta.puml](19-estados-cuenta.puml) | Máquina de estados | `PENDIENTE → ACTIVO \| RECHAZADO`, `ACTIVO → SUSPENDIDO → ACTIVO`, y qué ve cada estado al entrar. |

## Interacción (quién habla con quién)

| Archivo | Tipo UML | Qué muestra |
|---|---|---|
| [13-secuencia-sincronizacion.puml](13-secuencia-sincronizacion.puml) | Secuencia | La sincronización completa: conexión, `HELLO`, `ACCT`, `READY`, catálogo `CATALOGO`, `REC` con `ACTUAL`, `ACK`, fotos, `BYE`, batch y refresco. |
| [14-secuencia-corte-reanudacion.puml](14-secuencia-corte-reanudacion.puml) | Secuencia | Corte a mitad de lote, `READY\|25` y reenvío con go-back-N sin duplicados. |
| [15-secuencia-errores-y-reproceso.puml](15-secuencia-errores-y-reproceso.puml) | Secuencia | Una fila en `ERROR`, el alta del SKU, `REPROCESAR_ERRORES` y la conciliación de `ACTUAL`. |
| [20-comunicacion.puml](20-comunicacion.puml) | Comunicación | La colaboración numerada entre `Session`, `Store`, `SyncController`, `PKG_BATCH` y `ServicioRemoto`. |
| [21-vision-interaccion.puml](21-vision-interaccion.puml) | Visión general de interacción | El flujo de alto nivel que enlaza los diagramas 13, 14 y 15 con sus decisiones. |
| [22-tiempos.puml](22-tiempos.puml) | Tiempos | El latido del servicio (1 s; `DETENIDO` a los 10 s) y la ventana de 50 `REC` entre `ACK`. |

## Tipos que no se dibujan

- **Perfiles:** no aplica. El proyecto no define ningún perfil UML propio (ni estereotipos con etiquetas
  propias): los `«estereotipos»` de los diagramas son solo anotaciones de lectura.
- Hay 13 de los 14 tipos de UML 2: los de la tabla anterior. PlantUML no tiene un diagrama de comunicación
  nativo; el 20 se dibuja con rectángulos y flechas numeradas, que es la misma colaboración.
