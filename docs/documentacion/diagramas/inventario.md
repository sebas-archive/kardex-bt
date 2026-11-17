# Inventario de diagramas

Resumen técnico de cada diagrama: tipo UML, fuente, imágenes (con tamaño en píxeles) y de dónde proviene. Las imágenes
están en [`renderizados/`](renderizados/) y las fuentes en [`plantuml/`](plantuml/); la vista con las imágenes está en
[`README.md`](README.md).

| ID | Tipo UML | Fuente | PNG (px) | SVG | Origen |
|---|---|---|---|---|---|
| 01 | Casos de uso | `plantuml/01_casos_uso.puml` | `renderizados/01_casos_uso.png` (1362×1204) | `renderizados/01_casos_uso.svg` | docs/uml/10-casos-de-uso.puml |
| 02 | Componentes (capas) | `plantuml/02_arquitectura_general.puml` | `renderizados/02_arquitectura_general.png` (1462×1594) | `renderizados/02_arquitectura_general.svg` | Nuevo (solo existe aquí) |
| 03 | Componentes | `plantuml/03_componentes.puml` | `renderizados/03_componentes.png` (1893×1264) | `renderizados/03_componentes.svg` | docs/uml/06-componentes.puml |
| 04 | Despliegue | `plantuml/04_despliegue.puml` | `renderizados/04_despliegue.png` (1802×1046) | `renderizados/04_despliegue.svg` | docs/uml/07-despliegue.puml |
| 05 | Secuencia | `plantuml/05_secuencia_flujo_datos.puml` | `renderizados/05_secuencia_flujo_datos.png` (1850×2075) | `renderizados/05_secuencia_flujo_datos.svg` | docs/uml/13-secuencia-sincronizacion.puml |
| 06 | Secuencia | `plantuml/06_secuencia_comunicacion.puml` | `renderizados/06_secuencia_comunicacion.png` (1039×1861) | `renderizados/06_secuencia_comunicacion.svg` | docs/uml/14-secuencia-corte-reanudacion.puml |
| 07 | Clases | `plantuml/07_clases_paquetes.puml` | `renderizados/07_clases_paquetes.png` (1805×1411) | `renderizados/07_clases_paquetes.svg` | docs/uml/01-clases-servidor.puml |
| 07b | Paquetes | `plantuml/07b_paquetes.puml` | `renderizados/07b_paquetes.png` (1937×1250) | `renderizados/07b_paquetes.svg` | docs/uml/08-paquetes.puml |
| 07c | Clases | `plantuml/07c_clases_escritorio.puml` | `renderizados/07c_clases_escritorio.png` (2690×2173) | `renderizados/07c_clases_escritorio.svg` | docs/uml/02-clases-escritorio.puml |
| 07d | Clases | `plantuml/07d_clases_android.puml` | `renderizados/07d_clases_android.png` (2719×3207) | `renderizados/07d_clases_android.svg` | docs/uml/03-clases-android.puml |
| 08 | Actividad (carriles) | `plantuml/08_actividades.puml` | `renderizados/08_actividades.png` (2009×2506) | `renderizados/08_actividades.svg` | docs/uml/12-actividad-batch.puml |
| 08b | Actividad (carriles) | `plantuml/08b_actividad_conteo_movil.puml` | `renderizados/08b_actividad_conteo_movil.png` (1485×2424) | `renderizados/08b_actividad_conteo_movil.svg` | docs/uml/11-actividad-conteo-movil.puml |
| 09 | Máquina de estados | `plantuml/09_estados.puml` | `renderizados/09_estados.png` (2019×895) | `renderizados/09_estados.svg` | docs/uml/16-estados-sync-controller.puml |
| 09b | Máquina de estados | `plantuml/09b_estados_fila_transito.puml` | `renderizados/09b_estados_fila_transito.png` (1033×461) | `renderizados/09b_estados_fila_transito.svg` | docs/uml/17-estados-fila-transito.puml |
| 09c | Máquina de estados | `plantuml/09c_estados_cuenta.puml` | `renderizados/09c_estados_cuenta.png` (881×915) | `renderizados/09c_estados_cuenta.svg` | docs/uml/19-estados-cuenta.puml |
| 10 | Entidad-relación (`«table»`) | `plantuml/10_modelo_datos.puml` | `renderizados/10_modelo_datos.png` (2390×1190) | `renderizados/10_modelo_datos.svg` | docs/uml/04-modelo-datos.puml |

Los 16 pares se regeneran con `docs/documentacion/herramientas/renderizar_diagramas.sh` (ver [`README.md`](README.md#edición-y-renderizado)).

## Dónde se usan

| Diagrama | Documento técnico | README |
|---|---|---|
| 01 Casos de uso | Figura 2 | [README raíz](../../../README.md#roles-y-permisos) |
| 02 Arquitectura general | Figura 1 | [README raíz](../../../README.md#arquitectura-general), [`docs/README.md`](../../README.md) |
| 03 Componentes | Figura 4 | [`server/README.md`](../../../server/README.md), [`desktop/README.md`](../../../desktop/README.md) |
| 04 Despliegue | Figura 3 | [README raíz](../../../README.md#arquitectura-general), [`docker/README.md`](../../../docker/README.md) |
| 05 Secuencia de datos | Figura 24 | [`server/btsync/README.md`](../../../server/btsync/README.md) |
| 06 Secuencia de comunicación | Figura 29 | [`server/btsync/README.md`](../../../server/btsync/README.md) |
| 07 / 07b Clases y paquetes del servidor | Figuras 6 y 5 | [`server/btsync/README.md`](../../../server/btsync/README.md) |
| 07c Clases del escritorio | Figura 75 (anexo) | [`desktop/app/README.md`](../../../desktop/app/README.md) |
| 07d Clases de Android | Figura 76 (anexo) | [`mobile/README.md`](../../../mobile/README.md) |
| 08 / 08b Actividades | Figuras 37 y 38 | [`db/README.md`](../../../db/README.md), [`mobile/README.md`](../../../mobile/README.md) |
| 09 / 09b / 09c Estados | Figuras 16, 39 y 40 | [`server/btsync/README.md`](../../../server/btsync/README.md), [`db/README.md`](../../../db/README.md) |
| 10 Modelo de datos | Figura 18 | [`db/README.md`](../../../db/README.md) |

Los números de figura son los del documento técnico (capítulos y anexos); el detalle completo está en
[`../INDICE_EVIDENCIAS.md`](../INDICE_EVIDENCIAS.md).
