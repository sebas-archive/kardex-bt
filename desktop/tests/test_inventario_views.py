"""Pantalla Inventario: cinco columnas, buscador, CSV y detalle de lecturas con foto."""

import csv

import pytest

from app import db
from app.auth import PREGUNTAS
from app.views.inventario import COLUMNAS, DetalleLecturas, InventarioView

CLAVE = "conteo2026"


def esperar(qtbot, condicion):
    qtbot.waitUntil(condicion, timeout=15000)


@pytest.fixture
def contado(escenario):
    from app import db
    escenario.cargar_lecturas()
    db.procesar_ahora()
    return escenario


@pytest.fixture
def vista(qtbot, cuentas, contado):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", CLAVE, CLAVE, correo="ana@example.com",
                            pregunta=PREGUNTAS[0], respuesta="firulais")
    v = InventarioView()
    qtbot.addWidget(v)
    v.set_sesion(ana)
    esperar(qtbot, lambda: v.tabla.rowCount() >= 65)
    return v, ana


def test_cinco_columnas_y_sin_diferencia(vista):
    v, _ana = vista
    assert COLUMNAS == ("SKU", "Producto", "Categoría", "Contada", "Sistema")
    assert [v.tabla.horizontalHeaderItem(i).text() for i in range(v.tabla.columnCount())] == list(COLUMNAS)
    filas = {f[0]: f for f in v.filas()}
    assert filas["A1"][3] == "101" and filas["A1"][4] == "100"
    assert filas["A4"][3] == ""            # sin lectura: vacío, no 0
    assert filas["A4"][4] == "10"
    assert filas["A5"][3] == "4" and filas["A5"][4] == "0"


def test_buscador(qtbot, vista):
    v, _ana = vista
    v.buscar("A3")
    esperar(qtbot, lambda: len(v.filas()) == 1)
    assert v.filas()[0][0] == "A3"
    v.limpiar_filtros()
    esperar(qtbot, lambda: len(v.filas()) >= 65)


def test_exportar_csv(vista, tmp_path):
    v, _ana = vista
    ruta = tmp_path / "inventario.csv"
    v.exportar_csv(ruta)
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.reader(fh, delimiter=";"))
    assert filas[0] == list(COLUMNAS)
    por_sku = {f[0]: f for f in filas[1:]}
    assert por_sku["A1"] == ["A1", "Producto A1", "Abarrotes", "101", "100"]
    assert por_sku["A4"][3] == ""


def test_detalle_de_lecturas(qtbot, vista):
    v, _ana = vista
    v.abrir_detalle("A1")
    d = v.detalle
    qtbot.addWidget(d)
    esperar(qtbot, lambda: d.tabla.rowCount() == 2)
    assert [d.tabla.horizontalHeaderItem(i).text() for i in range(6)] == [
        "Cantidad", "Operador", "Fecha (UTC)", "Vigente", "Nota", "Foto"]
    assert d.tabla.item(0, 0).text() == "60" and d.tabla.item(1, 0).text() == "101"
    assert d.tabla.item(1, 3).text() == "Sí" and d.tabla.item(0, 3).text() == "No"


def test_ver_foto_abre_el_visor(qtbot, vista, monkeypatch):
    """El botón «Ver foto» debe llamar a ver_foto con la ruta y el título del SKU (sin NameError)."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM fotos WHERE uuid_dispositivo = 'tst-escenario' AND seq = 1")
        cur.execute("INSERT INTO fotos (uuid_dispositivo, seq, ruta, bytes) "
                    "VALUES ('tst-escenario', 1, 'evidencia.jpg', 97)")
        conn.commit()
    llamadas = []
    monkeypatch.setattr("app.views.inventario.ver_foto",
                        lambda padre, ruta, titulo="": llamadas.append((ruta, titulo)))
    v, _ana = vista
    v.abrir_detalle("A1")
    d = v.detalle
    qtbot.addWidget(d)
    esperar(qtbot, lambda: d.tabla.rowCount() == 2 and d.tabla.cellWidget(0, 5) is not None)
    d.tabla.cellWidget(0, 5).click()
    assert llamadas == [("evidencia.jpg", "A1 · Producto A1")]
