# Índice de la documentación

Punto de entrada a toda la documentación del proyecto *Kardex: inventario físico offline (APK → Bluetooth → Oracle → aplicación de
escritorio)*. Para una visión general empiece por el [README principal](../README.md).

## Documento técnico

| Documento | Descripción |
|---|---|
| [`documentacion/Documento_Tecnico_Proyecto.docx`](documentacion/Documento_Tecnico_Proyecto.docx) | Documento técnico principal (Word, 128 páginas, APA 7) con los diagramas incrustados |
| [`documentacion/Documento_Tecnico_Proyecto.pdf`](documentacion/Documento_Tecnico_Proyecto.pdf) | El mismo documento en PDF |
| [`documentacion/Documento_Tecnico_Proyecto.md`](documentacion/Documento_Tecnico_Proyecto.md) | Versión Markdown fuente |
| [`documentacion/INDICE_EVIDENCIAS.md`](documentacion/INDICE_EVIDENCIAS.md) | Cada figura y su archivo de origen |
| [`documentacion/README.md`](documentacion/README.md) | Cómo se construye el documento y qué contiene la carpeta |

## Diagramas

| Recurso | Ubicación |
|---|---|
| Vista con todas las imágenes, descripciones e instrucciones de edición | [`documentacion/diagramas/README.md`](documentacion/diagramas/README.md) |
| Inventario técnico (tipo, tamaño, origen, dónde se usa) | [`documentacion/diagramas/inventario.md`](documentacion/diagramas/inventario.md) |
| Fuentes PlantUML (16) | [`documentacion/diagramas/plantuml/`](documentacion/diagramas/plantuml/) |
| Imágenes renderizadas PNG y SVG (16 + 16) | [`documentacion/diagramas/renderizados/`](documentacion/diagramas/renderizados/) |
| Los 22 diagramas UML de 13 tipos: fuentes | [`uml/`](uml/README.md) |
| Los 22 diagramas UML: imágenes SVG y PNG | [`img/uml/`](img/uml/) |

## Instalación, ejecución y operación

| Tema | Dónde |
|---|---|
| Requisitos, puesta en marcha, APK, solución de problemas | [README principal](../README.md) |
| Docker Compose, imágenes y variables de entorno | [`../docker/README.md`](../docker/README.md) |
| Base de datos: esquema, `PKG_BATCH`, jobs, migraciones | [`../db/README.md`](../db/README.md) |
| Guion de demo de 5 minutos | [`demo.md`](demo.md) |
| Bluetooth desde contenedor (experimento) | [`spikes/bluez.md`](spikes/bluez.md) |

## Diseño y especificaciones

| Documento | Contenido |
|---|---|
| [`arquitectura.md`](arquitectura.md) | Capas, patrones, decisiones de diseño (D1…), límites conocidos y los diagramas UML |
| [`protocolo.md`](protocolo.md) y [`protocol-vectors.json`](protocol-vectors.json) | Protocolo de líneas móvil ↔ PC y vectores de prueba compartidos |
| [`interactividad/`](interactividad/00-entorno-y-decisiones.md) | Atajos, gestos móviles, estados, flujos, checklist por vista y motion del escritorio (9 archivos) |
| [`rediseno/SEGUIMIENTO.md`](rediseno/SEGUIMIENTO.md) | Seguimiento del rediseño de la interfaz |
| [`superpowers/plans/`](superpowers/plans/), [`superpowers/specs/`](superpowers/specs/) | Planes de implementación por fase y diseños |

## Pruebas y evidencias

| Evidencia | Ubicación |
|---|---|
| Verificación integral (suites y resultados) | [`verificacion.md`](verificacion.md), [`interactividad/06-verificacion.md`](interactividad/06-verificacion.md) |
| Cómo ejecutar las pruebas de cada aplicación | [servidor](../server/README.md#pruebas), [escritorio](../desktop/README.md#pruebas), [móvil](../mobile/README.md#compilar-probar-e-instalar) |
| Registros de ejecución (pruebas, comunicación, entorno) | [`documentacion/anexos/registros/`](documentacion/anexos/registros/) |
| Evidencias de código (capturas) | [`documentacion/capturas/codigo/`](documentacion/capturas/codigo/), índice en [`documentacion/anexos/indice_codigo.json`](documentacion/anexos/indice_codigo.json) |
| Evidencias de ejecución (capturas de la aplicación) | [`documentacion/capturas/aplicacion/`](documentacion/capturas/aplicacion/), [`documentacion/capturas/roles/`](documentacion/capturas/roles/), [`documentacion/capturas/movil/`](documentacion/capturas/movil/) |
| Capturas de la APK (29) | [`img/movil/`](img/movil/) |

## Documentación por aplicación y módulo

Cada aplicación tiene su propio README, y los módulos importantes el suyo. El listado completo está en el
[inventario de README](#inventario-de-readme).

| Aplicación | README | Módulos documentados |
|---|---|---|
| Servidor / servicio Bluetooth | [`../server/README.md`](../server/README.md) | [`btsync`](../server/btsync/README.md), [`transports`](../server/btsync/transports/README.md) |
| Aplicación de escritorio | [`../desktop/README.md`](../desktop/README.md) | [`app`](../desktop/app/README.md), [`app/views`](../desktop/app/views/README.md) |
| Aplicación móvil (APK) | [`../mobile/README.md`](../mobile/README.md) | [paquete `inventario`](../mobile/app/src/main/java/com/sebasarchive/kardex/README.md) |
| Integración con Oracle | [`../db/README.md`](../db/README.md) | `init/`, `PKG_BATCH`, vistas, jobs |
| Entorno de ejecución | [`../docker/README.md`](../docker/README.md) | Compose, imágenes |
| Herramientas auxiliares | [`../tools/README.md`](../tools/README.md) | semilla, teléfono simulado, UML |

## Inventario de README

| Archivo README | Ubicación | Alcance | Contenido documentado |
|---|---|---|---|
| [README principal](../README.md) | `/` | Proyecto completo | Descripción, arquitectura, tecnologías, instalación, configuración, ejecución, roles, pruebas, diagramas, solución de problemas |
| [Índice de documentación](README.md) | `docs/` | Toda la documentación | Este índice y el inventario de README |
| [Documento técnico y evidencias](documentacion/README.md) | `docs/documentacion/` | Documento Word/PDF y evidencias | Contenido de la carpeta y cómo se reconstruye el documento |
| [Diagramas](documentacion/diagramas/README.md) | `docs/documentacion/diagramas/` | Diagramas PlantUML | 16 diagramas con imagen, fuente, descripción y cómo editarlos y renderizarlos |
| [Inventario de diagramas](documentacion/diagramas/inventario.md) | `docs/documentacion/diagramas/` | Diagramas PlantUML | Tipo UML, tamaño, origen y dónde se usa cada diagrama |
| [UML complementarios](uml/README.md) | `docs/uml/` | 22 diagramas UML de 13 tipos | Qué muestra cada uno y cómo regenerarlos |
| [Servidor](../server/README.md) | `server/` | Paquete `btsync` y su servicio | Procesos, arquitectura, variables, pruebas |
| [Módulos de `btsync`](../server/btsync/README.md) | `server/btsync/` | Librería de sincronización | Protocolo, sesión, controlador, store, servicio, respaldos; flujo de una sincronización |
| [Transportes](../server/btsync/transports/README.md) | `server/btsync/transports/` | Bluetooth (BlueZ) y TCP | Contrato `Transport`/`Connection`, modos de emparejamiento |
| [Escritorio](../desktop/README.md) | `desktop/` | Aplicación PyQt6 | Arquitectura, configuración, ejecución, pruebas |
| [Módulos de `app`](../desktop/app/README.md) | `desktop/app/` | Datos y negocio del escritorio | `db`, `auth`, `permisos`, `auditoria`, servicio remoto, preferencias |
| [Vistas](../desktop/app/views/README.md) | `desktop/app/views/` | Pantallas y componentes | Pantallas por módulo y rol, componentes compartidos, movimiento |
| [Móvil](../mobile/README.md) | `mobile/` | APK Android | Arquitectura, permisos, compilación, pruebas, uso |
| [Paquete `inventario`](../mobile/app/src/main/java/com/sebasarchive/kardex/README.md) | `mobile/app/src/main/java/com/sebasarchive/kardex/` | Código de la APK | Paquetes, bandeja de salida, flujo de sincronización |
| [Base de datos](../db/README.md) | `db/` | Oracle XE 11g | Modelo, scripts, `PKG_BATCH`, jobs, vistas, migraciones |
| [Docker](../docker/README.md) | `docker/` y `docker-compose.yml` | Entorno de ejecución | Servicios, imágenes, variables, comandos |
| [Herramientas](../tools/README.md) | `tools/` | Utilidades de desarrollo | Semilla, demo, teléfono simulado, UML |
