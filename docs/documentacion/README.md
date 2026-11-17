# Documento técnico y evidencias

Documentación académica integral del proyecto: el documento técnico (Word, PDF y Markdown), los diagramas PlantUML con sus
imágenes, las capturas de la aplicación y del código, los registros de ejecución y las herramientas que lo generan.

| Contenido | Ubicación |
|---|---|
| Documento técnico (Word, 128 páginas, formato APA 7) | [`Documento_Tecnico_Proyecto.docx`](Documento_Tecnico_Proyecto.docx) |
| Documento técnico (PDF) | [`Documento_Tecnico_Proyecto.pdf`](Documento_Tecnico_Proyecto.pdf) |
| Documento técnico (Markdown fuente) | [`Documento_Tecnico_Proyecto.md`](Documento_Tecnico_Proyecto.md) |
| Índice de evidencias (cada figura ↔ su archivo) | [`INDICE_EVIDENCIAS.md`](INDICE_EVIDENCIAS.md) |
| Diagramas: fuentes `.puml` y renderizados `.png`/`.svg` | [`diagramas/`](diagramas/README.md) |
| Capturas de la aplicación (acceso, navegación, resoluciones, por rol) | [`capturas/aplicacion/`](capturas/aplicacion/), [`capturas/roles/`](capturas/roles/) |
| Capturas de código | [`capturas/codigo/`](capturas/codigo/) |
| Capturas de la APK | [`capturas/movil/`](capturas/movil/) |
| Registros de ejecución (pruebas, comunicación TCP y corte, entorno) | [`anexos/registros/`](anexos/registros/) |
| Herramientas de generación | [`herramientas/`](herramientas/) |

## Cómo está construido el documento

Cada figura aparece con el formato APA 7: número encima, título en cursiva debajo, imagen centrada, *Nota* con la fuente y un
párrafo breve «Demuestra». Las imágenes de los diagramas se insertan desde [`diagramas/renderizados/`](diagramas/renderizados/)
(PNG); el índice de evidencias relaciona cada figura con su archivo.

| Herramienta | Función |
|---|---|
| `construir_documento.py` | Arma el DOCX **sobre la plantilla original**, lo convierte a PDF con LibreOffice en Docker (imagen local `soffice-local`), calcula el índice con sus páginas y escribe el Markdown y el índice de evidencias |
| `docgen.py`, `contenido_a.py` … `contenido_e.py`, `redaccion.py` | Generador de OOXML y contenido de los capítulos |
| `renderizar_diagramas.sh` | Renderiza los `.puml` a SVG y PNG con PlantUML 1.2024.7 |
| `preparar_puml.py` | Copia desde `docs/uml` los diagramas que corresponden a los diez tipos pedidos |
| `capturar_*.py`, `capturar.sh` | Capturas de pantallas y de código |
| `pruebas*.sh`, `comunicacion_*.sh`, `entorno.sh` | Ejecutan las suites y la comunicación y guardan la salida íntegra en `anexos/registros/` |

Reconstruir el documento (desde la raíz del repositorio; requiere Docker, `pdftotext` y la plantilla `.docx` original):

```bash
python3 -I docs/documentacion/herramientas/construir_documento.py "<plantilla.docx>" docs/documentacion
```

Si solo cambia un diagrama: edite su `.puml`, ejecute `docs/documentacion/herramientas/renderizar_diagramas.sh` y reconstruya. El
Markdown resultante debe quedar idéntico salvo que cambie el texto.

## Diagramas

Inventario, imágenes y fuentes: [`diagramas/README.md`](diagramas/README.md) y [`diagramas/inventario.md`](diagramas/inventario.md).
