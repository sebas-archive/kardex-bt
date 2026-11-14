"""Perfil: avatar, editor de foto (rotar, zoom, recorte y vista previa) y preferencias."""

from PyQt6.QtGui import QColor, QImage

from app import auth
from app.auth import ADMIN, INVENTARIO, Sesion
from app.views import foto
from app.views.foto import EditorFoto, borrar_perfil, guardar_perfil, pixmap_avatar, pixmap_inicial
from app.views.perfil import PerfilView

ANA = Sesion("ana.gomez", "Ana Gómez", ADMIN, correo="ana@example.com")


def _imagen(color="#336699", ancho=120, alto=80):
    imagen = QImage(ancho, alto, QImage.Format.Format_RGB32)
    imagen.fill(QColor(color))
    return imagen


def test_avatar_guarda_y_borra_en_la_carpeta_de_fotos(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("FOTOS_DIR", str(tmp_path))
    ruta = guardar_perfil("ana.gomez", _imagen())
    assert ruta == "perfiles/ana.gomez.jpg"
    assert (tmp_path / ruta).is_file()
    mapa = pixmap_avatar(ruta, 36)
    assert mapa is not None and not mapa.isNull()
    borrar_perfil(ruta)
    assert not (tmp_path / ruta).is_file()
    assert pixmap_avatar(ruta, 36) is None
    assert not pixmap_inicial("Ana", 36).isNull()


def test_editor_rota_hace_zoom_y_recorta_cuadrado(qtbot):
    editor = EditorFoto(_imagen())
    qtbot.addWidget(editor)
    editor.show()
    inicial = editor.resultado()
    assert inicial.width() == 512 and inicial.height() == 512 and not inicial.isNull()
    editor.lienzo.girar(True)
    editor.lienzo.poner_zoom(2.0)
    assert editor.lienzo.giro() == 90
    assert editor.lienzo.zoom() == 2.0
    recorte = editor.resultado()
    assert recorte.width() == 512 and recorte.height() == 512 and not recorte.isNull()
    assert editor.vista.pixmap() is not None
    editor._reset()
    assert editor.lienzo.zoom() == 1.0 and editor.lienzo.giro() == 0


def test_perfil_muestra_identidad_y_preferencias(qtbot, monkeypatch):
    from app import configuracion
    monkeypatch.setattr(configuracion, "valores", lambda: {"fotos.max_mb": "3"})
    vista = PerfilView()
    qtbot.addWidget(vista)
    vista.set_sesion(ANA)
    qtbot.waitUntil(lambda: vista._max_mb == 3, timeout=3000)
    assert vista.lbl_nombre.text() == "Ana Gómez"
    assert vista.lbl_usuario.text() == "@ana.gomez"
    assert vista.lbl_correo.text() == "ana@example.com"
    assert vista.lbl_avatar.pixmap() is not None and not vista.lbl_avatar.pixmap().isNull()
    assert [vista.combo_tema.itemData(i) for i in range(vista.combo_tema.count())] == ["claro", "sistema", "oscuro"]
    assert [vista.combo_idioma.itemData(i) for i in range(vista.combo_idioma.count())] == ["es", "en"]
    assert vista.btn_cambiar.text() == "Cambiar contraseña"
    assert vista._max_mb == 3


def test_perfil_de_inventario_pide_aprobacion(qtbot, monkeypatch):
    from app import configuracion
    monkeypatch.setattr(configuracion, "valores", lambda: {"fotos.max_mb": "2"})
    vista = PerfilView()
    qtbot.addWidget(vista)
    vista.set_sesion(Sesion("luis", "Luis Ortiz", INVENTARIO, correo="luis@example.com"))
    assert vista.btn_cambiar.text() == "Solicitar cambio de contraseña"
    assert "Solicitudes" in vista.lbl_clave_ayuda.text()
    assert not vista.btn_quitar_foto.isEnabled()          # sin foto no hay nada que quitar
