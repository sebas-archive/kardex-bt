"""Idioma: textos y números cambian junto con el idioma activo (sin tocar Oracle)."""

import pytest

from app import i18n, models
from app.views.acceso import PanelMarca


@pytest.fixture(autouse=True)
def _restaurar_idioma():
    yield
    i18n.set_idioma("es")


def test_subtitulo_del_login_tiene_traduccion():
    i18n.set_idioma("en")
    assert i18n.t("Accede con tu cuenta del PC.") != "Accede con tu cuenta del PC."


def test_estados_de_bluetooth_traducidos():
    i18n.set_idioma("en")
    for estado in ("escuchando", "celular conectado", "en pausa", "servicio detenido", "recibiendo"):
        assert i18n.t(estado) != estado


def test_formatos_numericos_siguen_el_idioma():
    i18n.set_idioma("es")
    assert models.fmt_pct(83.33) == "83,3 %" and models.fmt_cop(11800) == "$ 11.800"
    assert i18n.miles(1234.5, 1) == "1.234,5"
    i18n.set_idioma("en")
    assert models.fmt_pct(83.33) == "83.3%" and models.fmt_cop(11800) == "$ 11,800"
    assert i18n.miles(1234.5, 1) == "1,234.5" and models.fmt_num(12.5) == "12.5"


def test_panel_de_marca_se_retraduce(qtbot):
    panel = PanelMarca()
    qtbot.addWidget(panel)
    i18n.set_idioma("en")
    panel.retraducir()
    assert panel.lbl_bienvenida.text() == "WELCOME"
    assert "Physical" in panel.lbl_imagen.text()
