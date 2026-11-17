"""Mini-biblioteca para escribir el Word SOBRE LA PLANTILLA original (no crea un documento desde cero).

Toma el ``word/document.xml`` de la plantilla, conserva la portada tal como está y sustituye el resto por el contenido
generado: capítulos con los estilos Heading1/2/3 de la plantilla, párrafos con interlineado doble y sangría de 1,27 cm,
tablas, figuras con pie, listas con la numeración de la plantilla, y una tabla de contenido real (campo TOC con
hiperenlaces y números de página calculados a partir del PDF).
El mismo contenido se vuelca a Markdown como fuente complementaria.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

EMU = 635                      # EMU por dxa (twip)
ANCHO_V = 9360                 # ancho útil vertical (dxa)
ANCHO_H = 12960                # ancho útil horizontal (dxa)
ALTO_V = 12960                 # alto útil vertical (dxa)
ALTO_H = 9360


def esc(t: str) -> str:
    return escape(t, {'"': "&quot;"})


# ---------------------------------------------------------------- bloques
@dataclass
class H:
    nivel: int
    texto: str
    salto: bool = True          # H1: página nueva


@dataclass
class P:
    texto: str
    sangria: bool = True


@dataclass
class Lista:
    items: list[str]


@dataclass
class Cmd:
    lineas: list[str]
    titulo: str = ""


@dataclass
class Tabla:
    id: str
    titulo: str
    cab: list[str]
    filas: list[list[str]]
    anchos: list[int]
    fuente: str = ""
    tam: int = 18               # medio punto: 18 = 9 pt


@dataclass
class Fig:
    id: str
    imagen: str                 # ruta relativa a docs/documentacion
    titulo: str
    detalle: list[str] = field(default_factory=list)   # líneas: «Archivo: …», «Descripción: …»
    max_w: int | None = None
    max_h: int | None = None


@dataclass
class Horizontal:
    bloques: list


@dataclass
class Salto:
    pass


# ---------------------------------------------------------------- inline
_PATRON = re.compile(r"(\*\*.+?\*\*|`.+?`|(?<![\w])_[^_\s][^_]*?_(?![\w]))")


def runs(texto: str, sz: int = 24, extra: str = "", mono_sz: int | None = None) -> str:
    salida = []
    for trozo in _PATRON.split(texto):
        if not trozo:
            continue
        rpr = f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>{extra}'
        if trozo.startswith("**") and trozo.endswith("**") and len(trozo) > 4:
            t, rpr = trozo[2:-2], f"<w:b/><w:bCs/>{rpr}"
        elif trozo.startswith("`") and trozo.endswith("`") and len(trozo) > 2:
            m = mono_sz or max(sz - 2, 16)
            t = trozo[1:-1]
            rpr = (f'<w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:cs="Courier New"/>'
                   f'<w:sz w:val="{m}"/><w:szCs w:val="{m}"/>{extra}')
        elif trozo.startswith("_") and trozo.endswith("_") and len(trozo) > 2:
            t, rpr = trozo[1:-1], f"<w:i/><w:iCs/>{rpr}"
        else:
            t = trozo
        salida.append(f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{esc(t)}</w:t></w:r>')
    return "".join(salida)


def plano(texto: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*|`(.+?)`|(?<![\w])_([^_\s][^_]*?)_(?![\w])", lambda m: m.group(1) or m.group(2) or m.group(3), texto)


# ---------------------------------------------------------------- generador
class Doc:
    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz                      # docs/documentacion
        self.xml: list[str] = []
        self.md: list[str] = []
        self.imagenes: list[tuple[str, Path]] = []     # (nombre en word/media, origen)
        self.rels: list[str] = []
        self.num_fig = 0
        self.num_tab = 0
        self.refs: dict[str, str] = {}
        self.bm = 100
        self.toc: list[tuple[int, str, str]] = []      # (nivel, texto, bookmark)
        self.docpr = 10
        self.contador_h = [0, 0, 0]
        self.horizontal = False

    # ---- numeración previa (para las referencias cruzadas)
    def numerar(self, bloques: list) -> None:
        f = t = 0
        for b in self._planos(bloques):
            if isinstance(b, Fig):
                f += 1
                self.refs[b.id] = f"Figura {f}"
            elif isinstance(b, Tabla):
                t += 1
                self.refs[b.id] = f"Tabla {t}"

    def _planos(self, bloques):
        for b in bloques:
            if isinstance(b, Horizontal):
                yield from self._planos(b.bloques)
            else:
                yield b

    def resolver(self, texto: str) -> str:
        return re.sub(r"\[\[(\w+)\]\]", lambda m: self.refs.get(m.group(1), f"«{m.group(1)}?»"), texto)

    # ---- emisión
    def agregar(self, bloques: list) -> None:
        for b in self._preparar(bloques):
            self._emitir(b)

    @staticmethod
    def _preparar(bloques: list) -> list:
        """Une secciones apaisadas contiguas y mete dentro de la sección apaisada el título que la precede
        (un título solo al final de una página vertical quedaría huérfano)."""
        res: list = []
        for b in bloques:
            if isinstance(b, Horizontal):
                if res and isinstance(res[-1], H) and res[-1].nivel >= 2:
                    b = Horizontal([res.pop()] + b.bloques)
                if res and isinstance(res[-1], Horizontal):
                    res[-1] = Horizontal(res[-1].bloques + b.bloques)
                    continue
            res.append(b)
        return res

    def _emitir(self, b) -> None:
        if isinstance(b, H):
            self._h(b)
        elif isinstance(b, P):
            self._p(b)
        elif isinstance(b, Lista):
            self._lista(b)
        elif isinstance(b, Cmd):
            self._cmd(b)
        elif isinstance(b, Tabla):
            self._tabla(b)
        elif isinstance(b, Fig):
            self._fig(b)
        elif isinstance(b, Horizontal):
            self._horizontal(b)
        elif isinstance(b, Salto):
            self.xml.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    # titulares
    def _h(self, h: H) -> None:
        texto = self.resolver(h.texto)
        self.bm += 1
        nombre = f"_Toc{self.bm:08d}"
        if h.nivel <= 2:
            self.toc.append((h.nivel, texto, nombre))
        estilo = f"Heading{h.nivel}"
        nuevo_pliego = h.nivel == 1 and re.match(r"(1|20|21)\. ", texto) is not None
        sb = "<w:pageBreakBefore/>" if nuevo_pliego else ""
        antes = 0 if nuevo_pliego else 360
        self.xml.append(
            f'<w:p><w:pPr><w:pStyle w:val="{estilo}"/>{sb}<w:spacing w:lineRule="auto" w:line="480" w:before="{antes}" w:after="0"/></w:pPr>'
            f'<w:bookmarkStart w:id="{self.bm}" w:name="{nombre}"/><w:r><w:rPr><w:bCs/></w:rPr><w:t xml:space="preserve">{esc(texto)}</w:t></w:r>'
            f'<w:bookmarkEnd w:id="{self.bm}"/></w:p>')
        self.md.append(f"\n{'#' * (h.nivel + 1)} {texto}\n")

    def _p(self, p: P) -> None:
        texto = self.resolver(p.texto)
        ind = '<w:ind w:firstLine="720"/>' if p.sangria else ""
        self.xml.append(
            f'<w:p><w:pPr><w:pStyle w:val="Normal"/><w:spacing w:lineRule="auto" w:line="480"/>{ind}</w:pPr>{runs(texto)}</w:p>')
        self.md.append(plano_md(texto) + "\n")

    def _lista(self, l: Lista) -> None:
        for it in l.items:
            t = self.resolver(it)
            self.xml.append(
                '<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
                f'<w:spacing w:lineRule="auto" w:line="360" w:after="60"/></w:pPr>{runs(t)}</w:p>')
            self.md.append(f"- {plano_md(t)}")
        self.md.append("")

    def _cmd(self, c: Cmd) -> None:
        if c.titulo:
            self.xml.append(
                f'<w:p><w:pPr><w:keepNext/><w:spacing w:before="120" w:after="40" w:line="240" w:lineRule="auto"/></w:pPr>{runs(c.titulo, 20, "<w:b/>")}</w:p>')
        for i, l in enumerate(c.lineas):
            kn = "<w:keepNext/>" if i < len(c.lineas) - 1 else ""
            self.xml.append(
                f'<w:p><w:pPr>{kn}<w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
                f'<w:ind w:left="144" w:right="144"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:cs="Courier New"/>'
                f'<w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr><w:t xml:space="preserve">{esc(l)}</w:t></w:r></w:p>')
        self.xml.append('<w:p><w:pPr><w:spacing w:before="0" w:after="120" w:line="120" w:lineRule="exact"/></w:pPr></w:p>')
        self.md.append("```bash\n" + "\n".join(c.lineas) + "\n```\n")

    # tablas
    def _tabla(self, t: Tabla) -> None:
        total = sum(t.anchos)
        titulo = self.resolver(t.titulo)
        etiqueta = self.refs[t.id]
        self.xml.append(
            f'<w:p><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="60" w:line="240" w:lineRule="auto"/></w:pPr>'
            f'{runs(etiqueta + ".", 20, "<w:b/>")}{runs(" " + titulo, 20, "<w:i/>")}</w:p>')
        grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in t.anchos)

        def celda(txt: str, w: int, cab: bool) -> str:
            sh = '<w:shd w:val="clear" w:color="auto" w:fill="E7E6E6"/>' if cab else ""
            partes = self.resolver(txt).split("\n")
            ps = "".join(
                f'<w:p><w:pPr><w:pStyle w:val="Normal"/><w:spacing w:before="20" w:after="20" w:line="240" w:lineRule="auto"/></w:pPr>'
                f'{runs(p, t.tam, "<w:b/>" if cab else "")}</w:p>' for p in partes)
            return f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{sh}</w:tcPr>{ps}</w:tc>'

        filas = ['<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>' +
                 "".join(celda(c, w, True) for c, w in zip(t.cab, t.anchos)) + "</w:tr>"]
        for f in t.filas:
            assert len(f) == len(t.anchos), (t.id, f)
            filas.append('<w:tr><w:trPr><w:cantSplit/></w:trPr>' + "".join(celda(c, w, False) for c, w in zip(f, t.anchos)) + "</w:tr>")
        self.xml.append(
            f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="{total}" w:type="dxa"/><w:jc w:val="center"/>'
            f'<w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="20" w:type="dxa"/><w:left w:w="70" w:type="dxa"/>'
            f'<w:bottom w:w="20" w:type="dxa"/><w:right w:w="70" w:type="dxa"/></w:tblCellMar>'
            f'<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" w:noHBand="0" w:noVBand="1"/></w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid>{"".join(filas)}</w:tbl>')
        fuente = f"Fuente: {t.fuente}" if t.fuente else ""
        self.xml.append(
            f'<w:p><w:pPr><w:spacing w:before="40" w:after="200" w:line="240" w:lineRule="auto"/></w:pPr>{runs(fuente, 16, "<w:i/>") if fuente else ""}</w:p>')
        self.md.append(f"**{etiqueta}.** _{plano_md(titulo)}_\n")
        self.md.append("| " + " | ".join(plano_md(c).replace("\n", "<br>") for c in t.cab) + " |")
        self.md.append("|" + "|".join("---" for _ in t.cab) + "|")
        for f in t.filas:
            self.md.append("| " + " | ".join(plano_md(self.resolver(c)).replace("\n", "<br>").replace("|", "\\|") for c in f) + " |")
        if fuente:
            self.md.append(f"\n_{fuente}_")
        self.md.append("")

    # figuras
    def _fig(self, f: Fig) -> None:
        ruta = self.raiz / f.imagen
        w, h = tamano_png(ruta)
        mw = f.max_w or (ANCHO_H if self.horizontal else ANCHO_V)
        mh = f.max_h or ((ALTO_H - 1500) if self.horizontal else (ALTO_V - 1500))
        ancho_dxa = min(mw, w * 15)            # como máximo el tamaño natural a 96 ppp (15 dxa por píxel)
        alto_dxa = int(ancho_dxa * h / w)
        if alto_dxa > mh:
            alto_dxa = mh
            ancho_dxa = int(mh * w / h)
        nombre = f"fig{len(self.imagenes) + 1:03d}{ruta.suffix}"
        self.imagenes.append((nombre, ruta))
        rid = f"rIdFig{len(self.imagenes)}"
        self.docpr += 1
        cx, cy = ancho_dxa * EMU, alto_dxa * EMU
        etiqueta = self.refs[f.id]
        self.xml.append(
            f'<w:p><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="60" w:line="240" w:lineRule="auto"/><w:jc w:val="center"/></w:pPr>'
            f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:effectExtent l="0" t="0" r="0" b="0"/><wp:docPr id="{self.docpr}" name="{esc(etiqueta)}" descr="{esc(f.titulo)}"/>'
            f'<wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            f'<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="{self.docpr}" name="{nombre}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            f'</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')
        det = [self.resolver(x) for x in f.detalle]
        cap = (f'<w:p><w:pPr><w:pStyle w:val="Caption"/>{"<w:keepNext/>" if det else ""}<w:spacing w:before="0" w:after="{40 if det else 240}" w:line="240" w:lineRule="auto"/><w:jc w:val="center"/></w:pPr>'
               f'{runs(etiqueta + ".", 18, "<w:b/><w:color w:val=\"000000\"/>")}{runs(" " + self.resolver(f.titulo), 18, "<w:color w:val=\"000000\"/>")}</w:p>')
        self.xml.append(cap)
        for i, d in enumerate(det):
            self.xml.append(
                f'<w:p><w:pPr><w:pStyle w:val="Caption"/>{"" if i == len(det) - 1 else "<w:keepNext/>"}<w:spacing w:before="0" w:after="{240 if i == len(det) - 1 else 20}" w:line="240" w:lineRule="auto"/><w:jc w:val="center"/></w:pPr>'
                f'{runs(d, 16, "<w:i w:val=\"0\"/><w:iCs w:val=\"0\"/><w:color w:val=\"404040\"/>")}</w:p>')
        self.rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{nombre}"/>')
        self.md.append(f"![{etiqueta}. {plano_md(self.resolver(f.titulo))}]({f.imagen})\n")
        self.md.append(f"**{etiqueta}.** {plano_md(self.resolver(f.titulo))}  ")
        for d in det:
            self.md.append(f"{plano_md(d)}  ")
        self.md.append("")

    # secciones horizontales
    def _horizontal(self, hz: Horizontal) -> None:
        self.xml.append(sect_par(horizontal=False))
        self.horizontal = True
        for b in hz.bloques:
            self._emitir(b)
        self.xml.append(sect_par(horizontal=True))
        self.horizontal = False


def plano_md(t: str) -> str:
    return re.sub(r"(?<![\w])_([^_\s][^_]*?)_(?![\w])", r"*\1*", t)


def tamano_png(ruta: Path) -> tuple[int, int]:
    with open(ruta, "rb") as f:
        cab = f.read(24)
    return struct.unpack(">II", cab[16:24])


def sect_par(horizontal: bool) -> str:
    """Párrafo que CIERRA una sección. Vertical o apaisada; ambas con el encabezado de la plantilla (número de página)."""
    if horizontal:
        pg = '<w:pgSz w:w="15840" w:h="12240" w:orient="landscape"/>'
        ref = '<w:headerReference w:type="default" r:id="rIdHdrH"/>'
    else:
        pg = '<w:pgSz w:w="12240" w:h="15840"/>'
        ref = '<w:headerReference w:type="default" r:id="rId4"/>'
    return (f'<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="20" w:lineRule="exact"/><w:sectPr>{ref}<w:type w:val="nextPage"/>{pg}'
            '<w:pgMar w:left="1440" w:right="1440" w:gutter="0" w:header="708" w:top="1440" w:footer="0" w:bottom="1440"/>'
            '<w:pgNumType w:fmt="decimal"/><w:docGrid w:type="default" w:linePitch="100" w:charSpace="0"/></w:sectPr></w:pPr></w:p>')


def tabla_contenido(entradas: list[tuple[int, str, str]], paginas: dict[str, int]) -> str:
    """Campo TOC real (\\o "1-2" \\h) con las entradas ya calculadas: Word las actualiza con F9."""
    salida = []
    for i, (nivel, texto, bm) in enumerate(entradas):
        pag = paginas.get(bm, 0) or ""
        ind = '<w:ind w:left="360"/>' if nivel == 2 else ""
        inicio = ""
        if i == 0:
            inicio = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> TOC \\o "1-2" \\h \\z \\u </w:instrText></w:r>'
                      '<w:r><w:fldChar w:fldCharType="separate"/></w:r>')
        sz = 22 if nivel == 2 else 22
        b = "" if nivel == 2 else "<w:b/>"
        salida.append(
            f'<w:p><w:pPr><w:pStyle w:val="TOC{nivel}"/><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9350"/></w:tabs>'
            f'<w:spacing w:before="0" w:after="{40 if nivel == 2 else 60}" w:line="264" w:lineRule="auto"/>{ind}</w:pPr>{inicio}'
            f'<w:hyperlink w:anchor="{bm}" w:history="1"><w:r><w:rPr>{b}<w:sz w:val="{sz}"/></w:rPr><w:t xml:space="preserve">{esc(texto)}</w:t></w:r>'
            f'<w:r><w:rPr><w:sz w:val="{sz}"/></w:rPr><w:tab/></w:r>'
            f'<w:r><w:rPr><w:sz w:val="{sz}"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:rPr><w:sz w:val="{sz}"/></w:rPr><w:instrText xml:space="preserve"> PAGEREF {bm} \\h </w:instrText></w:r>'
            f'<w:r><w:rPr><w:sz w:val="{sz}"/></w:rPr><w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:r><w:rPr><w:sz w:val="{sz}"/></w:rPr><w:t>{pag}</w:t></w:r>'
            f'<w:r><w:rPr><w:sz w:val="{sz}"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r></w:hyperlink></w:p>')
    salida.append('<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
    return "".join(salida)
