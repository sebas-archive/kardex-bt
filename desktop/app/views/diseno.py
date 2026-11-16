"""Tokens de diseño compartidos (una sola fuente para radios, espaciado y tiempos).

No introduce valores nuevos: documenta y centraliza los que la hoja de estilo (``base.py``) ya usa, para que el código
nuevo no invente medidas. Los colores NO viven aquí: salen de ``tema.colores()`` (identidad verde, claro/oscuro).
"""

from __future__ import annotations

# Radios (px): controles, tarjetas y superficies grandes.
RADIO_CONTROL, RADIO_TARJETA, RADIO_SUPERFICIE = 9, 14, 20

# Espaciado (px), escala de 4.
ESP_XS, ESP_S, ESP_M, ESP_L, ESP_XL = 4, 8, 12, 16, 24

# Tiempos (ms) por rol: coinciden con ``motion.RAPIDO/NORMAL/LENTO`` y con el tope de 500 ms.
T_PRESION, T_HOVER, T_ENTRADA, T_PANTALLA, T_TEMA = 90, 120, 200, 260, 240
T_MAX = 500

# Cascada de entrada de una página: retardo entre tarjetas y máximo de tarjetas que se escalonan.
CASCADA_INTERVALO, CASCADA_TOPE = 32, 6
