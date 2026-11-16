"""Lógica de fuerza de contraseña (guía visual, no la política del backend)."""

from app.fortaleza import AVISO_COMUN, etiqueta, evaluar


def test_vacia():
    r = evaluar("")
    assert r.vacia and r.puntaje == 0 and r.etiqueta == "Vacía"
    assert all(not cumple for _texto, cumple in r.reglas) and r.aviso is None


def test_debil_y_regular():
    r = evaluar("abc")
    assert not r.vacia and r.puntaje <= 1 and r.etiqueta == "Débil"
    r = evaluar("Clave1")
    assert r.puntaje <= 2 and r.etiqueta in ("Débil", "Regular")


def test_fuerte_cumple_las_cuatro_reglas():
    r = evaluar("ClaveSegura#2026")
    assert r.puntaje == 4 and r.etiqueta == "Fuerte"
    assert all(cumple for _texto, cumple in r.reglas)
    assert r.aviso is None and not r.comun and not r.secuencia and not r.repeticion


def test_patron_comun_baja_el_puntaje():
    r = evaluar("Password1234")
    assert r.comun and r.puntaje == 1 and r.etiqueta == "Regular"
    assert r.aviso == AVISO_COMUN


def test_secuencia_baja_el_puntaje():
    r = evaluar("abcd1234EFGH")
    assert r.secuencia and r.puntaje == 1
    assert r.aviso == AVISO_COMUN


def test_repeticion_baja_el_puntaje():
    r = evaluar("aaaaaaaaaaaa")
    assert r.repeticion and r.puntaje == 1
    assert r.aviso == AVISO_COMUN


def test_etiquetas_por_puntaje():
    assert etiqueta(0) == "Débil"
    assert etiqueta(1) == "Regular"
    assert etiqueta(2) == "Buena"
    assert etiqueta(3) == "Fuerte"
    assert etiqueta(4) == "Fuerte"
    assert etiqueta(0, vacia=True) == "Vacía"
