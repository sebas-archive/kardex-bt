"""Perfil: composición responsiva, controles segmentados que gobiernan tema e idioma y campos de contraseña."""

import pytest
from PyQt6.QtWidgets import QBoxLayout, QLineEdit

from app import auth
from app.auth import ADMIN, Sesion
from app.views.perfil import ANCHO_MAXIMO, PerfilView

ANA = Sesion("ana.gomez", "Ana Gómez", ADMIN, correo="ana@example.com")


@pytest.fixture
def vista(qtbot, monkeypatch):
    monkeypatch.setattr(auth, "guardar_preferencias", lambda *a, **k: None)
    v = PerfilView()
    qtbot.addWidget(v)
    v.set_sesion(ANA)
    v.resize(1200, 800)
    v.show()
    return v


def test_conserva_los_datos_y_acciones(vista):
    assert vista.lbl_nombre.text() == "Ana Gómez" and vista.lbl_usuario.text() == "@ana.gomez"
    assert vista.lbl_correo.text() == "ana@example.com" and not vista._fila_correo.isHidden()
    for boton in (vista.btn_foto, vista.btn_quitar_foto, vista.btn_salir, vista.btn_cambiar):
        assert not boton.isHidden()
    assert vista.combo_tema.count() == 3 and vista.combo_idioma.count() == 2


def test_sin_correo_no_se_muestra_la_fila(qtbot, monkeypatch):
    monkeypatch.setattr(auth, "guardar_preferencias", lambda *a, **k: None)
    v = PerfilView()
    qtbot.addWidget(v)
    v.set_sesion(Sesion("luis", "Luis Ortiz", ADMIN))
    assert v._fila_correo.isHidden()


def test_el_control_segmentado_gobierna_el_combo_y_lo_refleja(vista):
    vista.seg_tema._botones[2].click()
    assert vista.combo_tema.currentData() == "oscuro"
    vista.combo_tema.setCurrentIndex(0)
    assert [b.isChecked() for b in vista.seg_tema._botones] == [True, False, False]
    vista.seg_idioma._botones[1].click()
    assert vista.combo_idioma.currentData() == "en"


def test_al_abrir_la_sesion_los_segmentos_reflejan_lo_guardado(qtbot, monkeypatch):
    monkeypatch.setattr(auth, "guardar_preferencias", lambda *a, **k: None)
    v = PerfilView()
    qtbot.addWidget(v)
    v.set_sesion(Sesion("ana.gomez", "Ana Gómez", ADMIN, tema="oscuro", idioma="en"))
    assert [b.isChecked() for b in v.seg_tema._botones] == [False, False, True]
    assert [b.isChecked() for b in v.seg_idioma._botones] == [False, True]


def test_los_campos_de_contrasena_se_pueden_mostrar_y_ocultar(vista):
    campo = vista.txt_nueva
    assert campo.echoMode() == QLineEdit.EchoMode.Password
    ojo = campo.actions()[-1]
    ojo.trigger()
    assert campo.echoMode() == QLineEdit.EchoMode.Normal
    ojo.trigger()
    assert campo.echoMode() == QLineEdit.EchoMode.Password


def test_la_composicion_se_adapta_al_ancho(vista, qtbot):
    vista.resize(1200, 800)
    qtbot.wait(50)
    assert vista._columnas.direction() == QBoxLayout.Direction.LeftToRight
    vista.resize(640, 800)
    qtbot.wait(50)
    assert vista._columnas.direction() == QBoxLayout.Direction.TopToBottom
    assert vista._lay_usuario.direction() == QBoxLayout.Direction.TopToBottom


def test_el_contenido_tiene_ancho_maximo(vista, qtbot):
    vista.resize(2400, 900)
    qtbot.wait(50)
    pagina = vista.btn_foto.parentWidget()
    while pagina is not None and pagina.maximumWidth() != ANCHO_MAXIMO:
        pagina = pagina.parentWidget()
    assert pagina is not None and pagina.width() <= ANCHO_MAXIMO
