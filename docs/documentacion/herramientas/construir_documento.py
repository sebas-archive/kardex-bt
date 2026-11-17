"""Construye el DOCX SOBRE LA PLANTILLA original, el PDF (LibreOffice en Docker) y el Markdown fuente.

Uso (desde la raíz del repositorio):
    python docs/documentacion/herramientas/construir_documento.py <plantilla.docx> <salida_dir>
Pasos: 1) arma el contenido; 2) escribe el DOCX con la portada de la plantilla y el índice; 3) lo convierte a PDF y lee
las páginas de cada título; 4) vuelve a escribir el DOCX con los números de página correctos y genera PDF y Markdown.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contenido_a, contenido_b, contenido_c, contenido_d, contenido_e   # noqa: E402
from docgen import Doc, Fig, Horizontal, H, tabla_contenido, sect_par   # noqa: E402

PLANTILLA = Path(sys.argv[1])
SALIDA = Path(sys.argv[2]).resolve()
RAIZ = Path("docs/documentacion").resolve()
NOMBRE = "Documento_Tecnico_Proyecto"
TMP = SALIDA / "_build"


def todas_las_figuras(bloques) -> list[Fig]:
    for b in bloques:
        if isinstance(b, Fig):
            yield b
        elif isinstance(b, Horizontal):
            yield from todas_las_figuras(b.bloques)


def armar() -> tuple[Doc, list]:
    cuerpo = contenido_a.bloques() + contenido_b.bloques() + contenido_c.bloques() + contenido_d.bloques()
    doc = Doc(RAIZ)
    prev = contenido_e.bloques([], {})
    doc.numerar(cuerpo + prev)
    figs = list(todas_las_figuras(cuerpo + prev))
    # contadores usados en el texto
    doc.refs["N_DIAG"] = str(sum(1 for f in figs if f.imagen.startswith("diagramas/")))
    doc.refs["N_COD"] = str(sum(1 for f in figs if "capturas/codigo/" in f.imagen))
    doc.refs["N_REG"] = str(sum(1 for f in figs if "capturas/pruebas/" in f.imagen))
    doc.refs["N_APP"] = str(sum(1 for f in figs if f.imagen.startswith("capturas/") and "codigo/" not in f.imagen and "pruebas/" not in f.imagen))
    bloques = cuerpo + contenido_e.bloques(figs, doc.refs)
    return doc, bloques, figs


def portada(tpl_xml: str) -> tuple[str, str, str]:
    """(inicio hasta la portada inclusive, sectPr final, cierre). Añade el subtítulo bajo el título."""
    ini = tpl_xml.index("<w:body>") + len("<w:body>")
    marca = tpl_xml.index("TABLA DE CONTENIDO")
    corte = tpl_xml.rfind("<w:p>", 0, marca)
    cabecera, cover = tpl_xml[:ini], tpl_xml[ini:corte]
    sect = re.search(r"<w:sectPr>.*?</w:sectPr>(?=</w:body>)", tpl_xml, re.S).group(0)
    # subtítulo justo después de la 2.ª línea del título («Bluetooth hacia Oracle»)
    i = cover.index("Bluetooth hacia Oracl")
    fin = cover.index("</w:p>", i) + len("</w:p>")
    sub = ('<w:p><w:pPr><w:pStyle w:val="Normal"/><w:spacing w:lineRule="auto" w:line="480"/><w:jc w:val="center"/></w:pPr>'
           '<w:r><w:rPr><w:b/><w:bCs/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>'
           '<w:t>Documento técnico y documentación integral del sistema</w:t></w:r></w:p>')
    cover = cover[:fin] + sub + cover[fin:]
    # la portada debe caber en una página: se quitan tres párrafos vacíos del espaciado (el diseño no cambia)
    vacio = re.compile(r'<w:p><w:pPr>(?:(?!</w:p>).)*?</w:pPr><w:r><w:rPr><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:r></w:p>', re.S)
    cover = vacio.sub("", cover, count=3)
    return cabecera, cover, sect


def escribir_docx(doc: Doc, bloques: list, paginas: dict[str, int], destino: Path) -> None:
    doc.xml, doc.md, doc.imagenes, doc.rels, doc.toc = [], [], [], [], []
    doc.bm, doc.docpr = 100, 10
    doc.agregar(bloques)
    # El último bloque es apaisado: su cierre de sección pasa a ser el sectPr final del cuerpo.
    final_apaisado = False
    if doc.xml and doc.xml[-1] == sect_par(True):
        doc.xml.pop()
        final_apaisado = True

    tpl = TMP / "tpl"
    xml = (tpl / "word" / "document.xml").read_text(encoding="utf8")
    cabecera, cover, sect = portada(xml)
    toc_titulo = ('<w:p><w:pPr><w:pStyle w:val="Normal"/><w:pageBreakBefore/><w:spacing w:lineRule="auto" w:line="480"/><w:jc w:val="center"/>'
                  '<w:rPr><w:b/><w:bCs/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:pPr><w:r><w:rPr><w:b/><w:bCs/><w:sz w:val="22"/>'
                  '<w:szCs w:val="22"/></w:rPr><w:t>TABLA DE CONTENIDO</w:t></w:r></w:p>')
    toc = tabla_contenido(doc.toc, paginas)
    if final_apaisado:
        sect = ('<w:sectPr><w:headerReference w:type="default" r:id="rIdHdrH"/><w:pgSz w:w="15840" w:h="12240" w:orient="landscape"/>'
                '<w:pgMar w:left="1440" w:right="1440" w:gutter="0" w:header="708" w:top="1440" w:footer="0" w:bottom="1440"/>'
                '<w:pgNumType w:fmt="decimal"/><w:docGrid w:type="default" w:linePitch="100" w:charSpace="0"/></w:sectPr>')
    nuevo = cabecera + cover + toc_titulo + toc + "".join(doc.xml) + sect + "</w:body></w:document>"

    # paquete: copia de la plantilla + contenido nuevo
    paquete = TMP / "pkg"
    if paquete.exists():
        shutil.rmtree(paquete)
    shutil.copytree(tpl, paquete)
    (paquete / "word" / "document.xml").write_text(nuevo, encoding="utf8")
    media = paquete / "word" / "media"
    for nombre, origen in doc.imagenes:
        shutil.copy(origen, media / nombre)
    # relaciones
    rels = (paquete / "word" / "_rels" / "document.xml.rels").read_text(encoding="utf8")
    extra = "".join(doc.rels) + '<Relationship Id="rIdHdrH" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header4.xml"/>'
    rels = rels.replace("</Relationships>", extra + "</Relationships>")
    (paquete / "word" / "_rels" / "document.xml.rels").write_text(rels, encoding="utf8")
    # encabezado apaisado: el de la plantilla con la tabla del ancho de la página horizontal
    h = (paquete / "word" / "header2.xml").read_text(encoding="utf8")
    for a, b in (('w:w="9360"', 'w:w="12960"'), ('w:w="3116"', 'w:w="4320"'), ('w:w="3118"', 'w:w="4320"'), ('w:w="3126"', 'w:w="4320"')):
        h = h.replace(a, b)
    (paquete / "word" / "header4.xml").write_text(h, encoding="utf8")
    ct = (paquete / "[Content_Types].xml").read_text(encoding="utf8")
    if "/word/header4.xml" not in ct:
        ct = ct.replace("</Types>", '<Override PartName="/word/header4.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/></Types>')
    (paquete / "[Content_Types].xml").write_text(ct, encoding="utf8")
    # propiedades
    core = (paquete / "docProps" / "core.xml").read_text(encoding="utf8")
    core = core.replace("<dc:title></dc:title>", "<dc:title>Aplicación captura Móvil y Procesamiento Batch Bluetooth hacia Oracle: documento técnico</dc:title>")
    core = re.sub(r"(<dcterms:modified[^>]*>)[^<]*", r"\g<1>" + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), core)
    (paquete / "docProps" / "core.xml").write_text(core, encoding="utf8")
    # zip (Content_Types primero)
    if destino.exists():
        destino.unlink()
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(paquete / "[Content_Types].xml", "[Content_Types].xml")
        for f in sorted(paquete.rglob("*")):
            if f.is_file() and f.name != "[Content_Types].xml":
                z.write(f, f.relative_to(paquete).as_posix())


def a_pdf(docx: Path) -> Path:
    subprocess.run(["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp", "-v", f"{docx.parent}:/w", "soffice-local", "soffice", "--headless",
                    "--convert-to", "pdf", "--outdir", "/w", f"/w/{docx.name}"], check=True, capture_output=True)
    return docx.with_suffix(".pdf")


def paginas_de(pdf: Path, entradas: list[tuple[int, str, str]]) -> dict[str, int]:
    texto = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
    paginas = texto.split("\f")
    res: dict[str, int] = {}
    inicio = 0
    for nivel, t, bm in entradas:
        clave = re.sub(r"\s+", " ", t).strip()
        for i in range(inicio, len(paginas)):
            hallado = False
            for l in paginas[i].splitlines():
                l2 = re.sub(r"\s+", " ", l).strip()
                if "..." in l2 or re.search(r"\.{3,}", l2):
                    continue
                if l2 == clave or (len(clave) > 40 and l2.startswith(clave[:40])):
                    hallado = True
                    break
            if hallado:
                res[bm] = i + 1
                inicio = i
                break
        else:
            print("AVISO: no se encontró el título en el PDF:", t)
    return res


def principal() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    if TMP.exists():
        shutil.rmtree(TMP)
    (TMP / "tpl").mkdir(parents=True)
    with zipfile.ZipFile(PLANTILLA) as z:
        z.extractall(TMP / "tpl")
    doc, bloques, figs = armar()
    docx = SALIDA / f"{NOMBRE}.docx"
    escribir_docx(doc, bloques, {}, docx)
    pdf = a_pdf(docx)
    paginas = paginas_de(pdf, doc.toc)
    escribir_docx(doc, bloques, paginas, docx)           # segunda pasada: índice con sus páginas
    pdf = a_pdf(docx)
    paginas2 = paginas_de(pdf, doc.toc)
    if paginas2 != paginas:
        print("AVISO: las páginas cambiaron en la segunda pasada; se escribe una tercera")
        escribir_docx(doc, bloques, paginas2, docx)
        pdf = a_pdf(docx)
    # Markdown fuente
    portada_md = ["# Aplicación captura Móvil y Procesamiento Batch Bluetooth hacia Oracle",
                  "", "**Documento técnico y documentación integral del sistema**", "",
                  "Jose Camilo Pérez Daza · Sebastian Fernando Revelo Meneses", "",
                  "Ingeniería de software, Universidad Manuela Beltrán · Computación móvil · Prof. Robert Osorio Torres", "",
                  "Bogotá D.C. · 17 de noviembre del año 2026", ""]
    (SALIDA / f"{NOMBRE}.md").write_text("\n".join(portada_md + doc.md) + "\n", encoding="utf8")
    # índice de evidencias
    filas = contenido_e.indice(figs, doc.refs)
    linea = ["# Índice de evidencias", "",
             "Cada figura del documento técnico corresponde a un archivo de este directorio (`docs/documentacion/`).", "",
             "| ID | Figura | Archivo | Tipo | Descripción | Criterio relacionado |", "|---|---|---|---|---|---|"]
    linea += ["| " + " | ".join(c.replace("|", "\\|") for c in f) + " |" for f in filas]
    linea += ["", "## Fuentes PlantUML", ""]
    for p in sorted((RAIZ / "diagramas" / "plantuml").glob("*.puml")):
        linea.append(f"- `diagramas/plantuml/{p.name}` → `diagramas/renderizados/{p.stem}.svg` y `.png`")
    linea += ["", "## Registros de ejecución", ""]
    for p in sorted((RAIZ / "anexos" / "registros").glob("*.txt")):
        linea.append(f"- `anexos/registros/{p.name}`")
    (SALIDA / "INDICE_EVIDENCIAS.md").write_text("\n".join(linea) + "\n", encoding="utf8")
    shutil.rmtree(TMP, ignore_errors=True)
    print("docx:", docx, docx.stat().st_size, "| pdf:", pdf, pdf.stat().st_size, "| figuras:", len(figs), "| títulos:", len(doc.toc))


if __name__ == "__main__":
    principal()
