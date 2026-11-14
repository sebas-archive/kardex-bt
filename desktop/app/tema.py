"""Tema visual de la aplicación: claro, oscuro o el del sistema.

El QSS vive en ``views/base.py`` (tema oscuro, la identidad original). ``claro()`` lo deriva con un mapa de
colores en una sola pasada —así no se encadenan reemplazos— y añade los ajustes que no son un simple cambio de
color (el panel de marca del acceso sigue oscuro porque su texto es blanco).

``aplicar()`` es lo único que toca ``QApplication``: hoja de estilo y paleta nativa (diálogos, menús, tooltips).
Las vistas no tienen que hacer nada; para lo que se pinta a mano (pyqtgraph, degradados) se exponen
``es_oscuro()`` y ``colores()``.
"""

from __future__ import annotations

import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QGuiApplication, QPalette
from PyQt6.QtWidgets import QApplication

MODOS = ("claro", "sistema", "oscuro")
NOMBRE_MODO = {"claro": "Claro", "sistema": "Sistema", "oscuro": "Oscuro"}

_MODO = "sistema"

OSCURO = {
    "fondo": "#0A0A0A",
    "marco": "#161616",
    "lienzo": "#0A0A0A",
    "tarjeta": "#111111",
    "tarjeta_alt": "#0F0F0F",
    "texto": "#EDEDED",
    "texto_fuerte": "#FFFFFF",
    "texto_suave": "#8A8A8A",
    "texto_tenue": "#A3A3A3",
    "borde": "#232323",
    "borde_fuerte": "#2E2E2E",
    "acento": "#10B981",
    "acento_suave": "#34D399",
    "acento_texto": "#04130E",
    "error": "#F87171",
    "error_fondo": "#3A1512",
    "aviso": "#FBBF24",
    "aviso_fondo": "#2B2410",
    "seleccion": "#10261F",
    "grid": "#1C1C1C",
    "info_fondo": "#1F2350",
    "info": "#A5B4FC",
}

CLARO = {
    "fondo": "#F4F6F8",
    "marco": "#E9EDF2",
    "lienzo": "#FFFFFF",
    "tarjeta": "#FFFFFF",
    "tarjeta_alt": "#F7F8FA",
    "texto": "#1A1D21",
    "texto_fuerte": "#111827",
    "texto_suave": "#6B7280",
    "texto_tenue": "#5B6472",
    "borde": "#DFE3E8",
    "borde_fuerte": "#D1D7DE",
    "acento": "#059669",
    "acento_suave": "#047857",
    "acento_texto": "#FFFFFF",
    "error": "#B42318",
    "error_fondo": "#FDECEC",
    "aviso": "#8A5A00",
    "aviso_fondo": "#FFF8E1",
    "seleccion": "#E7F7F0",
    "grid": "#EDF0F3",
    "info_fondo": "#EEF0FF",
    "info": "#4338CA",
}

# Colores del QSS oscuro que cambian en el claro. Se aplican en una sola pasada (regex) para que un reemplazo
# no vuelva a tocar lo que acaba de escribir otro.
_A_CLARO = {
    "#0A0A0A": "#F4F6F8",
    "#161616": "#E9EDF2",
    "#111111": "#FFFFFF",
    "#0F0F0F": "#F7F8FA",
    "#121212": "#FFFFFF",
    "#1A1A1A": "#FFFFFF",
    "#1C1C1C": "#F0F2F5",
    "#232323": "#E2E5EA",
    "#262626": "#E5E7EB",
    "#2E2E2E": "#D5D9E0",
    "#333333": "#D5D9E0",
    "#343434": "#D5D9E0",
    "#383838": "#D5D9E0",
    "#3A3A3A": "#C9CED6",
    "#4A4A4A": "#9CA3AF",
    "#5B5B5B": "#6B7280",
    "#6E6E6E": "#9AA1AC",
    "#8A8A8A": "#6B7280",
    "#A3A3A3": "#5B6472",
    "#CFCFCF": "#374151",
    "#EDEDED": "#1A1D21",
    "#FFFFFF": "#111827",
    # verdes (acento)
    "#10B981": "#059669",
    "#34D399": "#047857",
    "#6EE7B7": "#047857",
    "#10261F": "#E7F7F0",
    "#133A2C": "#DCFCE7",
    "#132A22": "#DCFCE7",
    "#1E3A32": "#A7E3CF",
    "#2F6B57": "#A7DCC8",
    # rojos / avisos / información
    "#3A1512": "#FDECEC",
    "#7A2A24": "#F5B5B5",
    "#F87171": "#B42318",
    "#2B2410": "#FFF8E1",
    "#5C4A16": "#E6C97A",
    "#FBBF24": "#8A5A00",
    "#1F2350": "#EEF0FF",
    "#A5B4FC": "#4338CA",
    "#04130E": "#FFFFFF",   # texto sobre el botón primario (el fondo ya es #059669 en claro)
}

_HEX = re.compile(r"#[0-9A-Fa-f]{6}")
_RGBA_BLANCO = re.compile(r"rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*([0-9.]+)\s*\)")


def _a_claro(qss: str) -> str:
    qss = _HEX.sub(lambda m: _A_CLARO.get(m.group(0).upper(), m.group(0)), qss)
    qss = _RGBA_BLANCO.sub(lambda m: f"rgba(15, 23, 42, {m.group(1)})", qss)
    # El panel de marca del acceso es verde oscuro en ambos temas: su texto debe seguir claro.
    qss += """
QFrame#panelMarca { background: #0F2A24; }
QFrame#panelMarca QLabel { color: #FFFFFF; }
QFrame#lateral QLabel#marca { color: #111827; }
QFrame#pieCuenta QLabel#avatar { color: #FFFFFF; }
QLabel#codigoSync { color: #047857; }
QPushButton#primario { color: #FFFFFF; }
QPushButton#primario:hover { color: #FFFFFF; }
"""
    return qss


def resolver(modo: str) -> str:
    """``claro`` u ``oscuro`` para un modo; ``sistema`` mira la preferencia del sistema operativo."""
    if modo == "claro":
        return "claro"
    if modo == "oscuro":
        return "oscuro"
    app = QApplication.instance()
    if app is not None:
        try:
            esquema = app.styleHints().colorScheme()
            if hasattr(Qt.ColorScheme, "Dark") and esquema == Qt.ColorScheme.Dark:
                return "oscuro"
            if hasattr(Qt.ColorScheme, "Light") and esquema == Qt.ColorScheme.Light:
                return "claro"
        except (AttributeError, RuntimeError):
            pass
        try:
            return "oscuro" if app.palette().color(QPalette.ColorRole.Window).lightness() < 128 else "claro"
        except RuntimeError:
            pass
    return "oscuro"


def modo() -> str:
    return _MODO


def es_oscuro() -> bool:
    return resolver(_MODO) == "oscuro"


def colores() -> dict[str, str]:
    """Los colores vigentes, para lo que se pinta sin QSS (pyqtgraph, degradados, iconos)."""
    return dict(CLARO if resolver(_MODO) == "claro" else OSCURO)


def qss(modo_pedido: str | None = None) -> str:
    from .views.base import estilo
    base = estilo()
    return _a_claro(base) if resolver(modo_pedido or _MODO) == "claro" else base


def _paleta(claro: bool) -> QPalette:
    c = CLARO if claro else OSCURO
    p = QPalette()
    for papel, color in (
            (QPalette.ColorRole.Window, c["fondo"]),
            (QPalette.ColorRole.WindowText, c["texto"]),
            (QPalette.ColorRole.Base, c["tarjeta"]),
            (QPalette.ColorRole.AlternateBase, c["tarjeta_alt"]),
            (QPalette.ColorRole.Text, c["texto"]),
            (QPalette.ColorRole.Button, c["tarjeta"]),
            (QPalette.ColorRole.ButtonText, c["texto"]),
            (QPalette.ColorRole.ToolTipBase, c["tarjeta"]),
            (QPalette.ColorRole.ToolTipText, c["texto"]),
            (QPalette.ColorRole.Highlight, c["acento"]),
            (QPalette.ColorRole.HighlightedText, c["acento_texto"]),
            (QPalette.ColorRole.PlaceholderText, c["texto_suave"]),
    ):
        p.setColor(papel, QColor(color))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(c["texto_suave"]))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(c["texto_suave"]))
    return p


def aplicar(app: QApplication | QGuiApplication | None, modo_pedido: str = "sistema") -> str:
    """Aplica el tema a toda la aplicación. Devuelve el modo resuelto (``claro`` u ``oscuro``)."""
    global _MODO
    _MODO = modo_pedido if modo_pedido in MODOS else "sistema"
    resuelto = resolver(_MODO)
    if app is not None:
        app.setStyleSheet(qss(_MODO))
        try:
            app.setPalette(_paleta(resuelto == "claro"))
        except RuntimeError:
            pass
    try:   # los widgets que se pintan a mano leen estos colores
        from .views import widgets
        widgets.refrescar_paleta()
    except ImportError:
        pass
    return resuelto


def aplicar_tema(app: QApplication | QGuiApplication | None, modo_pedido: str = "sistema") -> str:
    """Alias de ``aplicar`` (el nombre que usa ``main.py``)."""
    return aplicar(app, modo_pedido)
