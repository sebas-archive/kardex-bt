"""Visor de fotografías (estilo Apple Photos) y ventana de lecturas rediseñada. No necesitan Oracle: las lecturas
se simulan en la capa de acceso a datos y las fotos son archivos reales en una carpeta temporal."""

from datetime import datetime

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow

from app import i18n, isla, tema
from app.models import Lectura
from app.views.lecturas import COL_FOTO, DetalleLecturas
from app.views.visor_foto import ESCALA_MAXIMA, FotoLectura, VisorFoto


def esperar(qtbot, condicion, ms=5000):
    qtbot.waitUntil(condicion, timeout=ms)


@pytest.fixture
def carpeta_fotos(tmp_path, monkeypatch):
    monkeypatch.setenv("FOTOS_DIR", str(tmp_path))
    for nombre, (w, h, color) in {"a.png": (1600, 900, "#2E7D32"), "b.png": (600, 1000, "#1565C0"),
                                 "c.png": (120, 80, "#C62828")}.items():
        img = QImage(w, h, QImage.Format.Format_RGB32)
        img.fill(QColor(color))
        assert img.save(str(tmp_path / nombre))
    return tmp_path


def fotos():
    return [FotoLectura(ruta=r, producto="Producto A1", sku="A1", cantidad=str(c), operador="ana", fecha=f,
                        nota=n) for r, c, f, n in (("a.png", 60, "2026-11-14 10:00:00", "Estante 3"),
                                                   ("b.png", 101, "2026-11-14 11:00:00", ""),
                                                   ("c.png", 7, "2026-11-14 12:00:00", "Dañado"))]


@pytest.fixture
def visor(qtbot, carpeta_fotos):
    v = VisorFoto(None, fotos(), 0)
    qtbot.addWidget(v)
    v.show()
    esperar(qtbot, lambda: v.lienzo.tiene_foto())
    return v


# ------------------------------------------------------------------ visor
def test_carga_la_foto_real_y_la_ajusta_sin_deformar(visor):
    l = visor.lienzo
    zona = l._interior()
    assert l._mapa.width() == 1600 and l._mapa.height() == 900           # la foto del archivo, sin tocar
    assert l.escala() == pytest.approx(min(zona.width() / 1600, zona.height() / 900, 2.0), rel=1e-3)
    assert visor.lbl_titulo.text() == "Producto A1"
    assert "SKU A1" in visor.lbl_sub.text() and "ana" in visor.lbl_sub.text() and "2026-11-14 10:00:00" in visor.lbl_sub.text()


def test_zoom_botones_rueda_y_restablecer(qtbot, visor):
    l = visor.lienzo
    ajustada = l.escala()
    visor.btn_mas.click()
    assert l.escala() == pytest.approx(ajustada * 1.25)
    visor.btn_menos.click()
    assert l.escala() == pytest.approx(ajustada)
    visor.btn_cien.click()
    assert l.escala() == pytest.approx(1.0)
    l.acercar(100)
    assert l.escala() <= ESCALA_MAXIMA
    visor.btn_ajustar.click()
    assert l.escala() == pytest.approx(ajustada)
    # rueda: el punto bajo el cursor se queda donde está
    visor.btn_cien.click()
    ancla = QPointF(l._centro().x() + 150, l._centro().y() + 60)
    antes = (ancla - l._centro() - l._off) / l.escala()
    l.acercar(1.5, ancla, animar=False)
    despues = (ancla - l._centro() - l._off) / l.escala()
    assert (antes - despues).manhattanLength() < 1.0


def test_girar_90_y_restablecer(visor):
    l = visor.lienzo
    visor.btn_girar.click()
    assert l.giros() == 1 and l._tam_giro() == (900, 1600)
    zona = l._interior()
    assert l.escala() == pytest.approx(min(zona.width() / 900, zona.height() / 1600, 2.0), rel=1e-3)   # cabe girada
    visor.btn_girar.click()
    visor.btn_mas.click()
    visor.btn_reset.click()
    assert l.giros() == 0 and l._ajustada
    assert l.escala() == pytest.approx(l._escala_ajuste())


def test_el_paneo_no_deja_la_foto_fuera(visor):
    l = visor.lienzo
    visor.btn_cien.click()
    l._off = l._limitar(QPointF(99999, -99999), l.escala())
    ex = (1600 * 1.0 - l._interior().width()) / 2 + 40
    assert abs(l._off.x()) <= ex + 1e-6


def test_navegacion_entre_fotos_solo_las_que_existen(qtbot, visor):
    cambios = []
    visor.cambio_indice.connect(cambios.append)
    assert visor.indice == 0 and not visor.btn_ant.isEnabled() and visor.btn_sig.isEnabled()
    assert visor.lbl_contador.text() == "1 de 3"
    visor.btn_sig.click()
    esperar(qtbot, lambda: visor.lienzo._mapa.width() == 600)
    assert visor.indice == 1 and cambios == [1]
    visor.ir_a(2)
    esperar(qtbot, lambda: visor.lienzo._mapa.width() == 120)
    assert not visor.btn_sig.isEnabled()
    visor.ir_a(3)           # más allá de la última: no hay
    visor.ir_a(-1)
    assert visor.indice == 2
    QTest.keyClick(visor, Qt.Key.Key_Left)
    assert visor.indice == 1
    QTest.keyClick(visor, Qt.Key.Key_Left)
    QTest.keyClick(visor, Qt.Key.Key_Left)
    assert visor.indice == 0


def test_una_sola_foto_no_muestra_flechas(qtbot, carpeta_fotos):
    v = VisorFoto(None, fotos()[:1])
    qtbot.addWidget(v)
    v.show()
    assert v.btn_ant.isHidden() and v.btn_sig.isHidden() and v.lbl_contador.isHidden()


def test_el_panel_de_informacion_empieza_oculto(qtbot, visor):
    assert not visor.panel_visible() and visor.panel.isHidden()
    ancho = visor.lienzo._interior().width()
    QTest.keyClick(visor, Qt.Key.Key_I)
    assert visor.panel_visible() and not visor.panel.isHidden()
    assert visor.lienzo._interior().width() == ancho - 316          # la foto se hace a un lado, no queda tapada
    v = visor._valores
    assert (v["producto"].text(), v["sku"].text(), v["cantidad"].text(), v["operador"].text(), v["nota"].text()) == (
        "Producto A1", "A1", "60", "ana", "Estante 3")
    visor.ir_a(1)
    assert visor._valores["nota"].text() == "Sin nota"
    visor.btn_info.click()
    assert not visor.panel_visible()


def test_foto_inexistente_muestra_estado_no_imagen_ficticia(qtbot, carpeta_fotos):
    v = VisorFoto(None, [FotoLectura(ruta="no-existe.jpg", producto="X", sku="X1")])
    qtbot.addWidget(v)
    v.show()
    esperar(qtbot, lambda: v.lienzo._mensaje and "no está en la carpeta" in v.lienzo._mensaje)
    assert not v.lienzo.tiene_foto()


def test_archivo_que_no_es_imagen(qtbot, carpeta_fotos):
    (carpeta_fotos / "roto.png").write_bytes(b"no soy una imagen")
    v = VisorFoto(None, [FotoLectura(ruta="roto.png")])
    qtbot.addWidget(v)
    v.show()
    esperar(qtbot, lambda: v.lienzo._mensaje == "El archivo no es una imagen válida.")


def test_pide_cerrar_con_escape_y_boton(qtbot, carpeta_fotos):
    for cerrar in (lambda v: QTest.keyClick(v, Qt.Key.Key_Escape), lambda v: v.btn_cerrar.click()):
        v = VisorFoto(None, fotos())
        qtbot.addWidget(v)
        v.show()
        with qtbot.waitSignal(v.cerrar_pedido, timeout=1000):
            cerrar(v)


def test_visor_se_pinta_en_ambos_temas_y_en_ingles(qtbot, carpeta_fotos):
    try:
        for modo in ("claro", "oscuro"):
            tema.aplicar(QApplication.instance(), modo)
            i18n.set_idioma("en" if modo == "oscuro" else "es")
            v = VisorFoto(None, fotos())
            qtbot.addWidget(v)
            v.show()
            esperar(qtbot, lambda: v.lienzo.tiene_foto())
            assert not v.grab().toImage().isNull()
            assert v.btn_girar.toolTip() == ("Rotate 90°" if modo == "oscuro" else "Girar 90°")
            v.close()
    finally:
        i18n.set_idioma("es")
        tema.aplicar(QApplication.instance(), "sistema")


# ------------------------------------------------------------------ ventana de lecturas
def lectura(c, vigente, ruta=None, nota=None, dia=14, h=10):
    return Lectura(float(c), "ana", datetime(2026, 11, dia, h, 5, 9), vigente, nota, ruta)


@pytest.fixture
def con_lecturas(monkeypatch):
    def poner(lista):
        monkeypatch.setattr("app.views.lecturas.db.fetch_lecturas", lambda sku: lista)
    return poner


def test_resumen_tabla_y_badges(qtbot, con_lecturas):
    con_lecturas([lectura(60, False, dia=13), lectura(101, True, "a.png", "Estante 3")])
    d = DetalleLecturas("A1", "Producto A1", None, categoria="Abarrotes")
    qtbot.addWidget(d)
    d.show()
    esperar(qtbot, lambda: d.tabla.rowCount() == 2)
    assert d.lbl_nombre.text() == "Producto A1" and d.lbl_sku.text() == "SKU A1" and d.lbl_categoria.text() == "Abarrotes"
    assert (d.ind_total.cifra.text(), d.ind_vigente.cifra.text(), d.ind_no_vigentes.cifra.text()) == ("2", "101", "1")
    assert d.ind_ultima.cifra.text() == "2026-11-14" and "10:05" in d.ind_ultima.toolTip()
    assert "Contado" in d.estado.text()
    assert d.tabla.item(0, 3).text() == "No" and d.tabla.item(1, 3).text() == "Sí"
    assert d.tabla.cellWidget(0, COL_FOTO) is None and d.tabla.cellWidget(1, COL_FOTO) is not None
    assert d.tabla.isVisible() and d.vacio.isHidden()


def test_estado_vacio(qtbot, con_lecturas):
    con_lecturas([])
    d = DetalleLecturas("A9", "Producto A9", None, categoria="Abarrotes")
    qtbot.addWidget(d)
    d.show()
    esperar(qtbot, lambda: not d.vacio.isHidden())
    assert d.tabla.isHidden()
    assert "Sin contar" in d.estado.text() and d.ind_total.cifra.text() == "0"
    # el escritorio no registra lecturas: no hay botón de acción
    assert not d.vacio.findChildren(__import__("PyQt6.QtWidgets", fromlist=["QPushButton"]).QPushButton)


def test_miniatura_real_y_apertura_del_visor_con_navegacion(qtbot, con_lecturas, carpeta_fotos, monkeypatch):
    con_lecturas([lectura(60, False, "a.png", dia=12), lectura(80, False, dia=13), lectura(7, True, "c.png")])
    llamadas = []
    monkeypatch.setattr("app.views.lecturas.ver_fotos",
                        lambda padre, fotos, indice=0, origen=None, al_cambiar=None: llamadas.append((fotos, indice, al_cambiar)))
    d = DetalleLecturas("A1", "Producto A1", None)
    qtbot.addWidget(d)
    d.show()
    esperar(qtbot, lambda: d.tabla.rowCount() == 3)
    boton = d.tabla.cellWidget(0, COL_FOTO).boton
    esperar(qtbot, lambda: not boton.icon().isNull() and boton.icon().availableSizes() != [])
    d.tabla.cellWidget(2, COL_FOTO).boton.click()
    fotos_, indice, al_cambiar = llamadas[0]
    assert [f.ruta for f in fotos_] == ["a.png", "c.png"] and indice == 1       # la lectura sin foto no está
    al_cambiar(0)                                                               # al navegar, la fila se selecciona
    assert d.tabla.currentRow() == 0


def test_la_ventana_no_se_reinicia_al_ver_fotos(qtbot, con_lecturas, carpeta_fotos, monkeypatch):
    con_lecturas([lectura(60, True, "a.png")])
    monkeypatch.setattr("app.views.lecturas.ver_fotos", lambda *a, **k: None)
    d = DetalleLecturas("A1", "Producto A1", None)
    qtbot.addWidget(d)
    d.show()
    esperar(qtbot, lambda: d.tabla.rowCount() == 1)
    d.tabla.selectRow(0)
    d.tabla.cellWidget(0, COL_FOTO).boton.click()
    assert d.tabla.currentRow() == 0 and d.tabla.rowCount() == 1


def test_detalles_y_nota(qtbot, con_lecturas):
    con_lecturas([lectura(5, True, nota="Caja abierta")])
    d = DetalleLecturas("A1", "Producto A1", None)
    qtbot.addWidget(d)
    d.show()
    esperar(qtbot, lambda: d.tabla.rowCount() == 1)
    d.ver_detalles(0)
    assert d._popup.valores["Nota"].text() == "Caja abierta" and d._popup.valores["Cantidad"].text() == "5"
    d._popup.close()


def test_error_de_consulta_se_muestra_con_reintentar(qtbot, monkeypatch):
    def falla(sku):
        raise RuntimeError("ORA-12541")
    monkeypatch.setattr("app.views.lecturas.db.fetch_lecturas", falla)
    d = DetalleLecturas("A1", "Producto A1", None)
    qtbot.addWidget(d)
    d.show()
    esperar(qtbot, lambda: "ORA-12541" in d.banner.text())


@pytest.mark.parametrize("modo", ["claro", "oscuro"])
def test_lecturas_en_ambos_temas(qtbot, con_lecturas, carpeta_fotos, modo):
    tema.aplicar(QApplication.instance(), modo)
    try:
        con_lecturas([lectura(60, False, dia=13), lectura(101, True, "a.png")])
        d = DetalleLecturas("A1", "Producto A1", None, categoria="Abarrotes")
        qtbot.addWidget(d)
        d.show()
        esperar(qtbot, lambda: d.tabla.rowCount() == 2)
        assert not d.grab().toImage().isNull()
    finally:
        tema.aplicar(QApplication.instance(), "sistema")
