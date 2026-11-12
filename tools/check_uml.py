"""Comprueba que las clases de un diagrama de clases PlantUML existen en el código.

Cada diagrama de clases declara su raíz de código en una línea ``' @code: server/btsync`` (varias
rutas separadas por comas). ``check_classes`` devuelve los nombres declarados en el diagrama
(``class``, ``abstract class``, ``interface``, ``enum``) que no aparecen como ``class``,
``interface`` u ``object`` en ningún ``.py`` o ``.kt`` de esas raíces. Así un diagrama no se
desvía del código sin que una prueba lo note.

Uso: ``python tools/check_uml.py docs/uml/01-clases-servidor.puml ...`` (sale con 1 si falta alguna).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CODE_SUFFIXES = {".py", ".kt"}
_RAICES = re.compile(r"^'\s*@code:\s*(.+?)\s*$", re.M)
# class Nombre / abstract class Nombre / interface Nombre / enum Nombre (el estereotipo y las llaves vienen después).
_EN_DIAGRAMA = re.compile(r"^\s*(?:abstract\s+)?(?:class|interface|enum)\s+([A-Za-z_]\w*)", re.M)
# Python: class X(...):   Kotlin: [data|sealed|abstract|open|enum] class X / interface X / object X
_EN_CODIGO = re.compile(
    r"^\s*(?:(?:data|sealed|abstract|open|enum|private|internal)\s+)*(?:class|interface|object)\s+([A-Za-z_]\w*)", re.M
)


def declared_roots(puml: Path) -> list[Path]:
    """Las rutas de la línea ``' @code:`` del diagrama (relativas a la raíz del repositorio)."""
    roots: list[Path] = []
    for linea in _RAICES.findall(puml.read_text(encoding="utf-8")):
        roots += [Path(parte.strip()) for parte in linea.split(",") if parte.strip()]
    return roots


def _classes_in_code(code_roots: list[Path]) -> set[str]:
    nombres: set[str] = set()
    for raiz in code_roots:
        archivos = [raiz] if raiz.is_file() else sorted(raiz.rglob("*"))
        for archivo in archivos:
            if archivo.suffix in CODE_SUFFIXES and "__pycache__" not in archivo.parts:
                nombres.update(_EN_CODIGO.findall(archivo.read_text(encoding="utf-8")))
    return nombres


def check_classes(puml: Path, code_roots: list[Path]) -> list[str]:
    """Nombres de clase del diagrama que no existen en el código, en orden de aparición y sin repetir."""
    existentes = _classes_in_code(code_roots)
    faltan: list[str] = []
    for nombre in _EN_DIAGRAMA.findall(puml.read_text(encoding="utf-8")):
        if nombre not in existentes and nombre not in faltan:
            faltan.append(nombre)
    return faltan


def main(argv: list[str] | None = None) -> int:
    argumentos = sys.argv[1:] if argv is None else argv
    raiz_repo = Path(__file__).resolve().parents[1]
    hay_error = False
    for ruta in argumentos:
        puml = Path(ruta)
        raices = [raiz_repo / r for r in declared_roots(puml)]
        if not raices:
            print(f"{puml}: no declara ' @code:")
            hay_error = True
            continue
        faltan = check_classes(puml, raices)
        if faltan:
            hay_error = True
            print(f"{puml}: clases que no existen en el código: {', '.join(faltan)}")
        else:
            print(f"{puml}: ok")
    return 1 if hay_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
