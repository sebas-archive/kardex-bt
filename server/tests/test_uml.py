"""Los diagramas UML (docs/uml) son fuente: tienen forma válida y los de clases no inventan clases."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from check_uml import check_classes, declared_roots  # noqa: E402

UML = ROOT / "docs" / "uml"
CLASS_DIAGRAMS = ["01-clases-servidor.puml", "02-clases-escritorio.puml", "03-clases-android.puml"]


def pumls() -> list[Path]:
    return sorted(UML.glob("*.puml"))


def test_every_puml_has_start_end_and_title():
    archivos = pumls()
    assert len(archivos) == 22, f"se esperaban 22 diagramas y hay {len(archivos)}"
    for archivo in archivos:
        texto = archivo.read_text(encoding="utf-8")
        assert "@startuml" in texto, f"{archivo.name}: falta @startuml"
        assert "@enduml" in texto, f"{archivo.name}: falta @enduml"
        assert any(l.strip().startswith("title ") for l in texto.splitlines()), f"{archivo.name}: falta title"


def test_class_diagrams_match_code():
    for nombre in CLASS_DIAGRAMS:
        puml = UML / nombre
        raices = [ROOT / r for r in declared_roots(puml)]
        assert raices, f"{nombre}: falta la línea ' @code: <ruta>"
        assert check_classes(puml, raices) == [], f"{nombre}: clases que no existen en el código"


def test_check_classes_reports_a_missing_class(tmp_path):
    puml = tmp_path / "falso.puml"
    puml.write_text(
        "@startuml\ntitle Prueba\n' @code: server/btsync\nclass Message\nclass Fantasma\n@enduml\n",
        encoding="utf-8",
    )
    assert declared_roots(puml) == [Path("server/btsync")]
    assert check_classes(puml, [ROOT / "server" / "btsync"]) == ["Fantasma"]


TIPOS_UML = [
    "casos de uso", "clases", "objetos", "componentes", "despliegue", "paquetes", "estructura compuesta",
    "actividad", "secuencia", "comunicación", "máquina de estados", "visión general de interacción", "tiempos",
]


def test_index_lists_every_puml_and_nothing_else():
    indice = (UML / "README.md").read_text(encoding="utf-8")
    existentes = {p.name for p in pumls()}
    citados = set(re.findall(r"\b\d\d-[\w-]+\.puml\b", indice))
    assert existentes - citados == set(), f"diagramas que el índice no lista: {sorted(existentes - citados)}"
    assert citados - existentes == set(), f"el índice lista archivos que no existen: {sorted(citados - existentes)}"


def test_index_covers_all_applicable_uml_types():
    indice = (UML / "README.md").read_text(encoding="utf-8").lower()
    faltan = [t for t in TIPOS_UML if t not in indice]
    assert faltan == [], f"el índice no menciona estos tipos UML: {faltan}"
    # El diagrama de perfiles no aplica y el índice lo dice (en la misma línea).
    assert any("perfil" in l and "no aplica" in l for l in indice.splitlines()), "falta «perfiles: no aplica»"
