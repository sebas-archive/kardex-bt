"""Migración única de las preferencias (QSettings) de la organización «GestionInventario» a «Kardex».

Al renombrar el producto cambió la organización con la que Qt guarda las preferencias (tema, idioma, preferencias del
dashboard y de las gráficas, usuario recordado). Sin esta copia cada equipo arrancaría con todo en blanco.

Solo **copia**: las claves viejas se dejan donde están (reversible) y una tienda nueva que ya tiene claves no se toca,
de modo que lo elegido después del renombrado nunca se pisa.
"""

from __future__ import annotations

from PyQt6.QtCore import QSettings

ORGANIZACION = "Kardex"
ORGANIZACION_ANTERIOR = "GestionInventario"
APLICACIONES = ("Acceso", "Dashboard", "Graficas", "Interfaz")   # las que la aplicación usa hoy


def migrar(origen: str = ORGANIZACION_ANTERIOR, destino: str = ORGANIZACION) -> int:
    """Copia las claves de ``origen`` a ``destino`` donde el destino aún no tiene nada. Devuelve cuántas copió."""
    copiadas = 0
    for aplicacion in APLICACIONES:
        viejo = QSettings(origen, aplicacion)
        nuevo = QSettings(destino, aplicacion)
        if nuevo.allKeys() or not viejo.allKeys():
            continue
        for clave in viejo.allKeys():
            nuevo.setValue(clave, viejo.value(clave))
            copiadas += 1
        nuevo.sync()
    return copiadas
