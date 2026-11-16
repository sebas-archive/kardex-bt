"""Fuerza de una contraseña: la misma guía del componente, sin dependencias externas.

No es la política del backend (``auth._validar_clave`` sigue exigiendo 8 caracteres con letras y números):
es una ayuda visual para que la persona elija una contraseña mejor. Un patrón común, una secuencia o una
repetición baja el puntaje aunque se cumplan las cuatro reglas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LONGITUD_MINIMA = 12
ETIQUETAS = ("Vacía", "Débil", "Regular", "Buena", "Fuerte")
AVISO_COMUN = "Patrón comúnmente adivinado"

_REGLAS = (
    (f"{LONGITUD_MINIMA} caracteres o más", "longitud"),
    ("Mayúscula y minúscula", "mayusculas"),
    ("Al menos un número", "numero"),
    ("Al menos un símbolo", "simbolo"),
)

_COMUNES = (
    "password", "passw0rd", "qwerty", "qwertyuiop", "admin", "administrador", "123456", "12345678",
    "1234", "1111", "0000", "abcd", "abc123", "letmein", "iloveyou", "contraseña", "contrasena",
    "welcome", "monkey", "dragon", "football", "master", "login",
)
_SECUENCIAS = ("0123456789", "abcdefghijklmnopqrstuvwxyz", "qwertyuiop", "asdfghjkl", "zxcvbnm")
_RUN = re.compile(r"(.)\1{3}", re.IGNORECASE)


@dataclass(frozen=True)
class Resultado:
    puntaje: int                 # 0-4
    etiqueta: str                # Vacía, Débil, Regular, Buena o Fuerte
    vacia: bool
    reglas: tuple[tuple[str, bool], ...]   # (texto, cumple)
    aviso: str | None            # patrón común, run o secuencia
    comun: bool
    secuencia: bool
    repeticion: bool


def etiqueta(puntaje: int, vacia: bool = False) -> str:
    if vacia:
        return ETIQUETAS[0]
    return ("Débil", "Regular", "Buena", "Fuerte", "Fuerte")[max(0, min(4, puntaje))]


def _tiene_secuencia(texto: str) -> bool:
    bajo = texto.lower()
    for base in _SECUENCIAS:
        for i in range(len(base) - 3):
            trozo = base[i:i + 4]
            if trozo in bajo or trozo[::-1] in bajo:
                return True
    return False


def _tiene_repeticion(texto: str) -> bool:
    return bool(_RUN.search(texto))


def _es_comun(texto: str) -> bool:
    bajo = texto.lower()
    return any(patron in bajo for patron in _COMUNES)


def evaluar(clave: str) -> Resultado:
    """Evalúa ``clave`` con las cuatro reglas y los patrones predecibles."""
    clave = clave or ""
    vacia = not clave
    cumplidas = (
        (f"{LONGITUD_MINIMA} caracteres o más", len(clave) >= LONGITUD_MINIMA),
        ("Mayúscula y minúscula", any(c.islower() for c in clave) and any(c.isupper() for c in clave)),
        ("Al menos un número", any(c.isdigit() for c in clave)),
        ("Al menos un símbolo", any(not c.isalnum() for c in clave)),
    )
    comun = _es_comun(clave)
    secuencia = _tiene_secuencia(clave)
    repeticion = _tiene_repeticion(clave)
    aviso = AVISO_COMUN if (comun or secuencia or repeticion) else None

    if vacia:
        puntaje = 0
    else:
        puntaje = sum(1 for _texto, cumple in cumplidas if cumple)
        if comun or secuencia or repeticion:
            puntaje = min(puntaje, 1)
        if len(clave) < 8:
            puntaje = min(puntaje, 1)
        puntaje = max(0, min(4, puntaje))

    return Resultado(puntaje, etiqueta(puntaje, vacia), vacia, cumplidas, aviso, comun, secuencia, repeticion)


def reglas() -> tuple[tuple[str, str], ...]:
    """(texto, clave interna) de las cuatro reglas, para que la vista las traduzca."""
    return _REGLAS
