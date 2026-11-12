"""Ventana principal y vistas Conteo y Conciliación (escenario fijo T-01).

Los textos de las tarjetas son los del escenario: 80,0 % · 25,0 % · -$ 5.000 · $ 11.800 y, tras
cerrar el conteo, 100,0 % · 20,0 % · -$ 10.000.
"""

import threading

import pytest
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import QLabel, QMessageBox, QWidget

from app import db as dbq
from app.main import MainWindow
from app.models import fmt_cop, fmt_num, fmt_pct
from app.views.conciliacion import ConciliacionView
from app.views.conteo import ConteoView

C = "T-01"


def esperar(qtbot, condicion, que="la condición", timeout=15000):
    qtbot.waitUntil(condicion, timeout=timeout)


@pytest.fixture
def contado(escenario):
    escenario.cargar_lecturas()
    dbq.procesar_ahora()
    return escenario


@pytest.fixture
def ventana(qtbot, contado):
    """Ventana con las dos vistas, apuntando al conteo T-01 ya cargado."""
    win = MainWindow(auto_refresh_ms=0)
    qtbot.addWidget(win)
    conteo, conciliacion = ConteoView(), ConciliacionView()
    win.add_view(conteo, "Conteo")
    win.add_view(conciliacion, "Conciliación")
    esperar(qtbot, lambda: win.combo_conteo.findData(C) >= 0)
    win.select_conteo(C)
    esperar(qtbot, lambda: conteo.card_text("avance") == "80,0 %")
    esperar(qtbot, lambda: conciliacion.table.model().rowCount() == 5)
    win.conteo_view, win.conciliacion_view = conteo, conciliacion
    return win


def test_conteo_cards_show_scenario_kpis(ventana):
    v = ventana.conteo_view
    assert v.card_text("avance") == "80,0 %"
    assert v.card_text("exactitud") == "25,0 %"
    assert v.card_text("valor_faltante") == "-$ 5.000"
    assert v.card_text("valor_sobrante") == "$ 11.800"
    assert v.card_text("sin_contar") == "1"
    assert v.btn_cerrar.isEnabled()
    assert v.banner.isHidden()


def test_conciliacion_table_has_5_rows_and_filter_faltante_shows_1(qtbot, ventana):
    v = ventana.conciliacion_view
    modelo = v.table.model()
    assert [modelo.fila(i).sku for i in range(5)] == ["A1", "A2", "A3", "A4", "A5"]
    v.combo_clasificacion.setCurrentText("FALTANTE")
    esperar(qtbot, lambda: modelo.rowCount() == 1)
    assert modelo.fila(0).sku == "A2"
    v.combo_clasificacion.setCurrentText("Todas")
    esperar(qtbot, lambda: modelo.rowCount() == 5)


def test_conciliacion_cells_use_es_co_format_and_status_colors(ventana):
    modelo = ventana.conciliacion_view.table.model()
    fila = {modelo.fila(i).sku: i for i in range(modelo.rowCount())}

    def texto(sku, columna):
        return modelo.data(modelo.index(fila[sku], columna), Qt.ItemDataRole.DisplayRole)

    columnas = [modelo.headerData(c, Qt.Orientation.Horizontal) for c in range(modelo.columnCount())]
    assert columnas == ["SKU", "Producto", "Categoría", "Sistema", "Contada", "Diferencia", "Dif. %",
                        "Valor", "Clasificación"]
    assert [texto("A2", c) for c in range(9)] == [
        "A2", "Producto A2", "Abarrotes", "50", "45", "-5", "-10,0 %", "-$ 5.000", "FALTANTE"]
    assert texto("A4", 5) == "—" and texto("A4", 7) == "—"          # SIN_CONTAR: sin diferencia
    assert texto("A5", 6) == "—"                                      # sistema 0: sin porcentaje
    colores = {sku: modelo.data(modelo.index(fila[sku], 8), Qt.ItemDataRole.BackgroundRole).color().name()
               for sku in fila}
    assert len(set(colores.values())) == 4                           # OK / FALTANTE / SOBRANTE / SIN_CONTAR


def test_double_click_a1_opens_detail_with_two_readings(qtbot, ventana):
    v = ventana.conciliacion_view
    modelo = v.table.model()
    fila = next(i for i in range(modelo.rowCount()) if modelo.fila(i).sku == "A1")
    v.table.doubleClicked.emit(modelo.index(fila, 0))
    esperar(qtbot, lambda: v.detalle is not None and v.detalle.table.rowCount() == 2)
    celdas = [[v.detalle.table.item(r, c).text() for c in range(5)] for r in range(2)]
    assert celdas == [
        ["U1", "60", "Ana", "2024-11-09 16:40:00", "Sí"],
        ["U2", "41", "Luis", "2024-11-09 16:40:01", "Sí"],
    ]
    assert "A1" in v.detalle.windowTitle()


def test_cerrar_conteo_requires_confirmation_and_cancel_does_nothing(qtbot, ventana, monkeypatch):
    llamadas = []

    def pregunta(parent, titulo, texto, *args, **kwargs):
        llamadas.append((titulo, texto))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", pregunta)
    v = ventana.conteo_view
    v.btn_cerrar.click()
    assert len(llamadas) == 1 and "irreversible" in llamadas[0][1] and C in llamadas[0][1]
    qtbot.wait(300)
    assert v.card_text("avance") == "80,0 %" and v.btn_cerrar.isEnabled()
    assert {c.id_conteo: c.estado for c in dbq.fetch_conteos()}[C] == "ABIERTO"


def test_confirmed_cerrar_conteo_updates_cards(qtbot, ventana, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    hilos = []
    original = dbq.cerrar_conteo
    monkeypatch.setattr(dbq, "cerrar_conteo", lambda *a: (hilos.append(threading.current_thread()), original(*a))[1])
    v = ventana.conteo_view
    v.btn_cerrar.click()
    esperar(qtbot, lambda: v.card_text("avance") == "100,0 %")
    assert v.card_text("exactitud") == "20,0 %"
    assert v.card_text("valor_faltante") == "-$ 10.000"
    assert v.card_text("valor_sobrante") == "$ 11.800"
    assert v.card_text("sin_contar") == "0"
    assert not v.btn_cerrar.isEnabled() and "cerrado" in v.btn_cerrar.text().lower()
    assert hilos and hilos[0] is not threading.main_thread()      # cerrar corre fuera de la UI


def test_add_view_registers_tab_and_includes_it_in_refresh(qtbot, ventana):
    class Falsa(QWidget):
        def __init__(self):
            super().__init__()
            self.refrescos, self.conteos = 0, []

        def refresh(self):
            self.refrescos += 1

        def set_conteo(self, id_conteo):
            self.conteos.append(id_conteo)

    falsa = Falsa()
    ventana.add_view(falsa, "Prueba", index=0)
    assert ventana.tabs.tabText(0) == "Prueba" and ventana.tabs.widget(0) is falsa
    assert falsa.conteos == [C]                      # recibe el conteo ya seleccionado
    antes = falsa.refrescos
    ventana.refresh_requested.emit()
    assert falsa.refrescos == antes + 1
    ventana.select_conteo("CONT-2026-11")
    assert falsa.conteos[-1] == "CONT-2026-11"


def test_empty_db_shows_sin_datos_not_crash(qtbot, contado, monkeypatch):
    monkeypatch.setattr(dbq, "fetch_conteos", lambda: [])
    win = MainWindow(auto_refresh_ms=0)
    qtbot.addWidget(win)
    conteo, conciliacion = ConteoView(), ConciliacionView()
    win.add_view(conteo, "Conteo")
    win.add_view(conciliacion, "Conciliación")
    esperar(qtbot, lambda: win.banner.text() == "Sin datos")  # antes se ve «Cargando…»
    assert not win.banner.isHidden()
    esperar(qtbot, lambda: conteo.banner.text() == "Sin datos")
    assert conciliacion.banner.text() == "Sin datos" and conciliacion.table.model().rowCount() == 0
    assert win.combo_conteo.count() == 0


def test_db_error_shows_banner_and_retry_works(qtbot, ventana, monkeypatch):
    original = dbq.fetch_resumen
    estado = {"falla": True}

    def inestable(id_conteo):
        if estado["falla"]:
            raise RuntimeError("ORA-12541: TNS:no listener")
        return original(id_conteo)

    monkeypatch.setattr(dbq, "fetch_resumen", inestable)
    v = ventana.conteo_view
    v.refresh()
    esperar(qtbot, lambda: not v.banner.isHidden() and "ORA-12541" in v.banner.text())
    assert not v.banner.btn_reintentar.isHidden()
    estado["falla"] = False
    v.banner.btn_reintentar.click()
    esperar(qtbot, lambda: v.banner.isHidden())
    assert v.card_text("avance") == "80,0 %"


@pytest.mark.parametrize("ancho, alto", [(800, 600), (1920, 1080)])
def test_window_small_and_large_without_clipping(qtbot, ventana, ancho, alto):
    ventana.resize(ancho, alto)
    ventana.show()
    esperar(qtbot, lambda: ventana.isVisible() and ventana.width() == ancho)
    v = ventana.conteo_view
    ventana.tabs.setCurrentWidget(v)
    esperar(qtbot, lambda: v.isVisible())
    qtbot.wait(100)

    def rect(w):
        return QRect(w.mapTo(ventana, w.rect().topLeft()), w.size())

    marco = ventana.rect()
    visibles = [ventana.combo_conteo, ventana.tabs.tabBar(), v.btn_cerrar, *v.cards.values()]
    for w in visibles:
        assert w.isVisible() and marco.contains(rect(w)), (w, rect(w), marco)
    tarjetas = [rect(c) for c in v.cards.values()]
    for i, a in enumerate(tarjetas):
        assert not any(a.intersects(b) for b in tarjetas[i + 1:]), "tarjetas solapadas"
    for etiqueta in v.findChildren(QLabel):
        if etiqueta.isVisible() and etiqueta.text():
            assert etiqueta.sizeHint().width() <= etiqueta.width() + 1, etiqueta.text()  # texto sin recortar


def test_no_query_runs_on_the_ui_thread(qtbot, contado, monkeypatch):
    hilos = {}
    for nombre in ("fetch_conteos", "fetch_resumen", "fetch_conciliacion", "fetch_dif_por_categoria"):
        original = getattr(dbq, nombre)

        def envoltura(*a, _o=original, _n=nombre, **k):
            hilos.setdefault(_n, set()).add(threading.current_thread())
            return _o(*a, **k)

        monkeypatch.setattr(dbq, nombre, envoltura)
    win = MainWindow(auto_refresh_ms=0)
    qtbot.addWidget(win)
    conteo, conciliacion = ConteoView(), ConciliacionView()
    win.add_view(conteo, "Conteo")
    win.add_view(conciliacion, "Conciliación")
    esperar(qtbot, lambda: win.combo_conteo.findData(C) >= 0)
    win.select_conteo(C)
    esperar(qtbot, lambda: conteo.card_text("avance") == "80,0 %" and conciliacion.table.model().rowCount() == 5)
    assert set(hilos) == {"fetch_conteos", "fetch_resumen", "fetch_conciliacion", "fetch_dif_por_categoria"}
    for nombre, conjunto in hilos.items():
        assert threading.main_thread() not in conjunto, f"{nombre} corrió en el hilo de la UI"


def test_formatters_es_co():
    assert fmt_pct(80.0) == "80,0 %" and fmt_pct(25) == "25,0 %" and fmt_pct(-10) == "-10,0 %"
    assert fmt_cop(11800) == "$ 11.800" and fmt_cop(-5000) == "-$ 5.000" and fmt_cop(0) == "$ 0"
    assert fmt_cop(1234567.4) == "$ 1.234.567" and fmt_cop(-10000.0) == "-$ 10.000"
    assert fmt_num(45) == "45" and fmt_num(12.5) == "12,5" and fmt_num(0.125) == "0,125" and fmt_num(None) == "—"


def test_export_csv_writes_the_filtered_rows(qtbot, ventana, tmp_path):
    v = ventana.conciliacion_view
    ruta = tmp_path / "conciliacion.csv"
    v.exportar_csv(ruta)
    lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
    assert lineas[0] == "SKU;Producto;Categoría;Sistema;Contada;Diferencia;Dif. %;Valor;Clasificación"
    assert len(lineas) == 6
    assert lineas[2] == "A2;Producto A2;Abarrotes;50;45;-5;-10;-5000;FALTANTE"
