"""Qué gráficas pone cada persona en «Gráficas», en qué orden y de qué tamaño (se recuerda por usuario).

Es la versión corta de ``dashboard_prefs``: las seis gráficas del conteo continuo se ven al principio y hay otras
siete para añadir; una de cada tipo como máximo.
"""

from __future__ import annotations

import json

from PyQt6.QtCore import QSettings

from .dashboard_prefs import COLS_MAX, LIMITES_ALTO     # los mismos límites que el dashboard

PREDETERMINADAS = ("avance", "dona", "hora", "top", "danados", "batch")   # las que se ven al principio
EXTRAS = ("global", "acumulado", "dia", "operadores", "pendientes", "skus", "buenas")   # solo si se añaden
IDS = PREDETERMINADAS + EXTRAS
TAMS = ("S", "M", "L")
TAM_INICIAL = "M"   # dos por fila


def predeterminado() -> list[tuple[str, str]]:
    return [(i, TAM_INICIAL) for i in PREDETERMINADAS]


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


def limitar_medidas(cols, alto) -> tuple[int, int]:
    """Una medida propia (columnas, alto en px) dentro de lo razonable; 0 = la del tamaño S/M/L."""
    try:
        cols, alto = max(0, int(cols or 0)), max(0, int(alto or 0))
    except (TypeError, ValueError):
        return 0, 0
    bajo, alto_max = LIMITES_ALTO["grafico"]
    return (min(cols, COLS_MAX) if cols else 0), (max(bajo, min(alto, alto_max)) if alto else 0)


def cargar_medidas(usuario: str) -> dict[str, tuple[int, int]]:
    """Las medidas propias guardadas (solo las gráficas que se redimensionaron con el asa)."""
    texto = _ajustes().value(_clave(usuario), "")
    try:
        datos = json.loads(str(texto)) if texto else {"items": []}
        medidas = {str(x["id"]): limitar_medidas(x.get("cols"), x.get("alto")) for x in datos["items"]}
    except (ValueError, KeyError, TypeError):
        return {}
    return {c: m for c, m in medidas.items() if c in IDS and any(m)}


def guardar(usuario: str, items: list[tuple[str, str]], medidas: dict[str, tuple[int, int]] | None = None) -> None:
    medidas = medidas or {}
    filas = []
    for c, t in items:
        fila = {"id": c, "tam": t}
        if any(medidas.get(c, (0, 0))):
            fila["cols"], fila["alto"] = medidas[c]
        filas.append(fila)
    ajustes = _ajustes()
    ajustes.setValue(_clave(usuario), json.dumps({"v": 1, "items": filas}))
    ajustes.sync()


def restaurar(usuario: str) -> list[tuple[str, str]]:
    ajustes = _ajustes()
    ajustes.remove(_clave(usuario))
    ajustes.sync()
    return predeterminado()
