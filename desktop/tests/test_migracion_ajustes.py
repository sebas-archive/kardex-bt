"""La migración de QSettings «GestionInventario» → «Kardex» copia una vez y nunca pisa lo ya elegido."""

from __future__ import annotations

import uuid

import pytest
from PyQt6.QtCore import QSettings

from app import migracion_ajustes


@pytest.fixture
def organizaciones():
    """Dos organizaciones de mentira por prueba: no se tocan las preferencias reales de quien corre las pruebas."""
    sufijo = uuid.uuid4().hex[:8]
    viejo, nuevo = f"PruebaVieja{sufijo}", f"PruebaNueva{sufijo}"
    yield viejo, nuevo
    for org in (viejo, nuevo):
        for app in migracion_ajustes.APLICACIONES:
            ajustes = QSettings(org, app)
            ajustes.clear()
            ajustes.sync()


def _guardar(org: str, app: str, **valores) -> None:
    ajustes = QSettings(org, app)
    for clave, valor in valores.items():
        ajustes.setValue(clave, valor)
    ajustes.sync()


def test_copia_las_claves_de_cada_aplicacion(organizaciones):
    viejo, nuevo = organizaciones
    _guardar(viejo, "Acceso", tema="oscuro", idioma="en")
    _guardar(viejo, "Dashboard", **{"u/ana": '["kpi"]'})
    copiadas = migracion_ajustes.migrar(viejo, nuevo)
    assert copiadas == 3
    assert QSettings(nuevo, "Acceso").value("tema") == "oscuro"
    assert QSettings(nuevo, "Acceso").value("idioma") == "en"
    assert QSettings(nuevo, "Dashboard").value("u/ana") == '["kpi"]'


def test_no_borra_las_claves_viejas(organizaciones):
    viejo, nuevo = organizaciones
    _guardar(viejo, "Interfaz", tema="claro")
    migracion_ajustes.migrar(viejo, nuevo)
    assert QSettings(viejo, "Interfaz").value("tema") == "claro"


def test_no_pisa_lo_que_ya_tiene_la_organizacion_nueva(organizaciones):
    viejo, nuevo = organizaciones
    _guardar(viejo, "Acceso", tema="oscuro")
    _guardar(nuevo, "Acceso", tema="claro")
    assert migracion_ajustes.migrar(viejo, nuevo) == 0
    assert QSettings(nuevo, "Acceso").value("tema") == "claro"


def test_es_idempotente(organizaciones):
    viejo, nuevo = organizaciones
    _guardar(viejo, "Graficas", **{"u/ana": "x"})
    assert migracion_ajustes.migrar(viejo, nuevo) == 1
    assert migracion_ajustes.migrar(viejo, nuevo) == 0


def test_sin_preferencias_viejas_no_hace_nada(organizaciones):
    viejo, nuevo = organizaciones
    assert migracion_ajustes.migrar(viejo, nuevo) == 0
    assert QSettings(nuevo, "Acceso").allKeys() == []


def test_las_organizaciones_por_defecto_son_las_del_renombrado():
    assert migracion_ajustes.ORGANIZACION_ANTERIOR == "GestionInventario"
    assert migracion_ajustes.ORGANIZACION == "Kardex"
