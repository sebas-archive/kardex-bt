"""Capas flotantes dentro de la ventana principal: lecturas (capa 3) y visor de fotos (capa 4)."""

from datetime import datetime

import pytest
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from app import isla
from app.models import Lectura
from app.views import widgets
from app.views.capas import CapaFlotante, abrir_capa
from app.views.lecturas import COL_FOTO, DetalleLecturas
from app.views.visor_foto import VisorFoto, ver_fotos


class Ventana(QMainWindow):
    """Una ventana principal de mentira: barra lateral de 200 px y área de contenido a la derecha."""

    def __init__(self) -> None:
        super().__init__()
        raiz = QWidget()
        self.setCentralWidget(raiz)
        lat = QLabel("lateral", raiz)
        lat.setGeometry(0, 0, 200, 700)
        self._centro = QWidget(raiz)
        self._centro.setGeometry(200, 0, 900, 700)
        QVBoxLayout(self._centro).addWidget(QLabel("tabla de inventario"))
        self.resize(1100, 700)

    def area_contenido(self) -> QRect:
        return QRect(self._centro.mapTo(self, QPoint(0, 0)), self._centro.size())


def lectura(c, vigente, ruta=None, nota=None, dia=14):
    return Lectura(float(c), "ana", datetime(2026, 11, dia, 10, 5, 9), vigente, nota, ruta)


@pytest.fixture
def carpeta_fotos(tmp_path, monkeypatch):
    monkeypatch.setenv("FOTOS_DIR", str(tmp_path))
    for nombre, (w, h, color) in {"a.png": (1600, 900, "#2E7D32"), "c.png": (120, 80, "#C62828")}.items():
        img = QImage(w, h, QImage.Format.Format_RGB32)
        img.fill(QColor(color))
        assert img.save(str(tmp_path / nombre))
    return tmp_path


@pytest.fixture
def host(qtbot, monkeypatch, carpeta_fotos):
    monkeypatch.setattr("app.views.lecturas.db.fetch_lecturas", lambda sku: [
        lectura(60, False, "a.png", dia=12), lectura(80, False, dia=13), lectura(7, True, "c.png", "Dañado")])
    v = Ventana()
    qtbot.addWidget(v)
    v.show()
    return v


def abrir_lecturas(qtbot, host):
    panel = DetalleLecturas("A1", "Producto A1", None, categoria="Abarrotes")
    capa = abrir_capa(host, panel, area="contenido")
    qtbot.waitUntil(lambda: panel.tabla.rowCount() == 3, timeout=5000)
    return panel, capa


def test_las_lecturas_son_una_capa_dentro_de_la_ventana(qtbot, host):
    panel, capa = abrir_lecturas(qtbot, host)
    assert capa.parentWidget() is host and panel.parentWidget() is capa
    assert not capa.isWindow() and not panel.isWindow()                     # ninguna ventana del sistema
    assert not (capa.windowFlags() & Qt.WindowType.Tool)
    assert capa.geometry() == host.rect()                                    # cubre la ventana: velo
    r = capa.rect_panel()
    assert host.rect().contains(r)                                           # dentro de los límites
    assert r.center() == host.area_contenido().center()                      # centrado en el área de contenido
    assert panel.geometry() == r and panel.isVisible()
    assert host.childAt(r.center() + QPoint(0, 0)) is not None


def test_el_panel_se_adapta_al_redimensionar(qtbot, host):
    panel, capa = abrir_lecturas(qtbot, host)
    host.resize(900, 560)
    qtbot.waitUntil(lambda: capa.geometry() == host.rect(), timeout=2000)
    assert host.rect().contains(panel.geometry())
    host.resize(1400, 900)
    qtbot.waitUntil(lambda: capa.geometry() == host.rect(), timeout=2000)
    assert panel.geometry().center() == host.area_contenido().center() or host.rect().contains(panel.geometry())


def test_el_visor_queda_encima_y_las_lecturas_siguen_intactas(qtbot, host):
    panel, capa_lec = abrir_lecturas(qtbot, host)
    panel.tabla.selectRow(2)
    panel.tabla.verticalScrollBar().setValue(0)
    datos = list(panel._lecturas)
    capa_vis = ver_fotos(panel, panel._fotos()[0], 1)
    assert isinstance(capa_vis, CapaFlotante) and capa_vis.parentWidget() is host
    visor = capa_vis.panel
    assert isinstance(visor, VisorFoto)
    hijos = host.findChildren(CapaFlotante)
    assert hijos.index(capa_vis) > hijos.index(capa_lec)                    # orden de apilado: visor arriba
    assert host.childAt(capa_vis.rect_panel().center()) is not None
    # lo que está debajo no se destruyó ni se reinició
    assert panel.isVisible() and panel.tabla.currentRow() == 2 and panel._lecturas == datos
    assert capa_lec.esta_abierta()
    capa_vis.cerrar()
    qtbot.waitUntil(lambda: not capa_vis.esta_abierta(), timeout=2000)
    assert capa_lec.esta_abierta() and panel.tabla.currentRow() == 2 and panel.tabla.rowCount() == 3
    assert panel._lecturas == datos


def test_escape_cierra_primero_el_visor_y_luego_las_lecturas(qtbot, host):
    panel, capa_lec = abrir_lecturas(qtbot, host)
    capa_vis = ver_fotos(panel, panel._fotos()[0], 0)
    visor = capa_vis.panel
    visor.setFocus()
    QTest.keyClick(visor, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not capa_vis.esta_abierta(), timeout=2000)
    assert capa_lec.esta_abierta()
    panel.setFocus()
    QTest.keyClick(panel, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not capa_lec.esta_abierta(), timeout=2000)


def test_boton_x_cierra_el_panel_actual(qtbot, host):
    panel, capa = abrir_lecturas(qtbot, host)
    panel.btn_cerrar.click()
    qtbot.waitUntil(lambda: not capa.esta_abierta(), timeout=2000)


def test_clic_fuera_cierra_pero_dentro_no(qtbot, host):
    panel, capa = abrir_lecturas(qtbot, host)
    QTest.mouseClick(capa, Qt.MouseButton.LeftButton, pos=capa.rect_panel().center())        # dentro
    assert capa.esta_abierta()
    QTest.mouseClick(panel.tabla.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(40, 20))   # dentro del panel
    assert capa.esta_abierta()
    QTest.mouseClick(capa, Qt.MouseButton.LeftButton, pos=QPoint(4, 4))                       # fuera: el velo
    qtbot.waitUntil(lambda: not capa.esta_abierta(), timeout=2000)


def test_la_capa_de_arriba_se_come_los_clics(qtbot, host):
    panel, capa_lec = abrir_lecturas(qtbot, host)
    capa_vis = ver_fotos(panel, panel._fotos()[0], 0)
    QTest.mouseClick(capa_vis, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))      # velo del visor: cierra solo el visor
    qtbot.waitUntil(lambda: not capa_vis.esta_abierta(), timeout=2000)
    assert capa_lec.esta_abierta()


def test_con_animaciones_abre_y_cierra(qtbot, host, monkeypatch):
    monkeypatch.setattr(widgets, "ANIMAR", True)
    panel = DetalleLecturas("A1", "Producto A1", None, categoria="Abarrotes")
    capa = abrir_capa(host, panel, area="contenido")
    assert capa._estado == "abriendo" and not panel.isVisible()                  # se anima una foto del panel
    qtbot.waitUntil(lambda: capa._estado == "abierta", timeout=3000)
    assert panel.isVisible()
    assert not capa.grab().toImage().isNull()
    capa.cerrar()
    assert capa._estado == "cerrando"
    qtbot.waitUntil(lambda: not capa.esta_abierta() and capa._estado == "cerrada", timeout=3000)


def test_visor_abre_desde_la_miniatura_animado(qtbot, host, monkeypatch):
    monkeypatch.setattr(widgets, "ANIMAR", True)
    panel, capa_lec = abrir_lecturas(qtbot, host)
    qtbot.waitUntil(lambda: capa_lec._estado == "abierta", timeout=3000)
    boton = panel.tabla.cellWidget(0, COL_FOTO).boton
    origen = QRect(boton.mapToGlobal(QPoint(0, 0)), boton.size())
    capa_vis = ver_fotos(panel, panel._fotos()[0], 0, origen)
    qtbot.wait(120)
    assert not capa_vis.grab().toImage().isNull()
    qtbot.waitUntil(lambda: capa_vis._estado == "abierta", timeout=3000)
    assert capa_lec.esta_abierta()


def test_la_isla_de_notificaciones_sigue_encima_de_las_capas(qtbot, host):
    g = isla.instalar(host)
    isla.info("Hola")
    panel, capa = abrir_lecturas(qtbot, host)
    hijos = host.children()
    assert hijos.index(g.widget) > hijos.index(capa)


def test_el_foco_vuelve_a_la_capa_de_abajo(qtbot, host):
    panel, capa_lec = abrir_lecturas(qtbot, host)
    capa_vis = ver_fotos(panel, panel._fotos()[0], 0)
    capa_vis.cerrar()
    qtbot.waitUntil(lambda: not capa_vis.esta_abierta(), timeout=2000)
    qtbot.waitUntil(lambda: capa_lec.panel.hasFocus() or capa_lec.panel.isAncestorOf(host.focusWidget() or capa_lec),
                    timeout=1000)
