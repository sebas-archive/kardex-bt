"""Qué gráficas pone cada persona en «Gráficas», en qué orden y de qué tamaño (se recuerda por usuario).

Es la versión corta de ``dashboard_prefs``: aquí no hay catálogo de widgets nuevos, solo las seis gráficas del
conteo continuo, una de cada tipo como máximo.
"""

from __future__ import annotations

import json

from PyQt6.QtCore import QSettings

IDS = ("avance", "dona", "hora", "top", "danados", "batch")   # las seis gráficas, en su orden inicial
TAMS = ("S", "M", "L")
TAM_INICIAL = "M"   # dos por fila


def predeterminado() -> list[tuple[str, str]]:
    return [(i, TAM_INICIAL) for i in IDS]


def normalizar(items) -> list[tuple[str, str]]:
    """Descarta lo desconocido y lo repetido, y repara los tamaños."""
    salida: list[tuple[str, str]] = []
    for clave, tam in items:
        if clave in IDS and all(clave != c for c, _t in salida):
            salida.append((clave, tam if tam in TAMS else TAM_INICIAL))
    return salida


def _ajustes() -> QSettings:
    return QSettings("GestionInventario", "Graficas")


def _clave(usuario: str) -> str:
    return f"graficas/{usuario}"


def cargar(usuario: str) -> list[tuple[str, str]]:
    """La disposición guardada; sin nada guardado (o dañada), las seis en dos columnas."""
    texto = _ajustes().value(_clave(usuario), "")
    if not texto:
        return predeterminado()
    try:
        datos = json.loads(str(texto))
        return normalizar([(str(x["id"]), str(x.get("tam", TAM_INICIAL))) for x in datos["items"]])
    except (ValueError, KeyError, TypeError):
        return predeterminado()


def guardar(usuario: str, items: list[tuple[str, str]]) -> None:
    ajustes = _ajustes()
    ajustes.setValue(_clave(usuario), json.dumps({"v": 1, "items": [{"id": c, "tam": t} for c, t in items]}))
    ajustes.sync()


def restaurar(usuario: str) -> list[tuple[str, str]]:
    ajustes = _ajustes()
    ajustes.remove(_clave(usuario))
    ajustes.sync()
    return predeterminado()
