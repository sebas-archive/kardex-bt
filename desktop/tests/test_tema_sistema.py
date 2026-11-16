"""«Sistema» sigue la preferencia real del SO aunque Qt no la informe (X11 sin portal, Docker)."""

import pytest
from PyQt6.QtWidgets import QApplication

from app import tema


@pytest.fixture
def app_qt(qtbot):
    app = QApplication.instance()
    yield app
    tema._SISTEMA = None
    tema.aplicar(app, "sistema")


@pytest.mark.parametrize("portal, esperado", [("oscuro", "oscuro"), ("claro", "claro")])
def test_sistema_ignora_la_paleta_propia(app_qt, monkeypatch, portal, esperado):
    """Con el esquema de Qt desconocido, «Sistema» no puede copiar el último tema aplicado por la propia app."""
    monkeypatch.setattr(tema, "_esquema_qt", lambda app: None)
    monkeypatch.setattr(tema, "_esquema_portal", lambda: portal)
    contrario = "claro" if esperado == "oscuro" else "oscuro"
    tema.aplicar(app_qt, contrario)
    assert tema.aplicar(app_qt, "sistema") == esperado
    assert tema.es_oscuro() == (esperado == "oscuro")


def test_sistema_prefiere_el_esquema_de_qt(app_qt, monkeypatch):
    monkeypatch.setattr(tema, "_esquema_qt", lambda app: "oscuro")
    monkeypatch.setattr(tema, "_esquema_portal", lambda: "claro")
    tema.aplicar(app_qt, "claro")
    assert tema.aplicar(app_qt, "sistema") == "oscuro"
