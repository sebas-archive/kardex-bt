"""Pantallas Categorías, Almacenes y Existencias (Fase 2)."""

import pytest

from app import db as dbq
from app.auth import ADMIN, INVENTARIO, Sesion
from app.main import build_window
from app.views import maestros as vistas
from app.views.existencias import ExistenciasView
from app.views.maestros import AlmacenesView, CategoriasView
from fakes import FakeRemoto


def esperar(qtbot, condicion, timeout=15000):
    qtbot.waitUntil(condicion, timeout=timeout)


@pytest.fixture
def luis(cuentas, maestros_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    return cuentas.iniciar_sesion("luis", "conteo2026")


def _vista(qtbot, clase, sesion):
    vista = clase()
    qtbot.addWidget(vista)
    vista.set_sesion(sesion)
    esperar(qtbot, lambda: len(vista.filas()) > 0)
    return vista


def test_categorias_muestra_crea_y_desactiva(qtbot, luis, monkeypatch):
    vista = _vista(qtbot, CategoriasView, luis)
    abarrotes = next(f for f in vista.filas() if f[0] == "Abarrotes")
    assert abarrotes[2] == "Activa" and int(abarrotes[1]) > 0
    monkeypatch.setattr(vistas, "pedir_texto", lambda *a, **k: "Tst Congelados")
    vista.btn_nuevo.click()
    esperar(qtbot, lambda: any(f[0] == "Tst Congelados" for f in vista.filas()))
    vista.seleccionar("Tst Congelados")
    assert vista.btn_estado.text() == "Desactivar"
    vista.btn_estado.click()
    esperar(qtbot, lambda: ("Tst Congelados", "0", "Inactiva") in vista.filas())
    monkeypatch.setattr(vistas, "pedir_texto", lambda *a, **k: None)        # cancelar: no hace nada
    vista.btn_nuevo.click()
    qtbot.wait(200)


def test_almacenes_crea_y_edita(qtbot, luis, monkeypatch):
    vista = _vista(qtbot, AlmacenesView, luis)
    assert ("ALM-01", "Bodega Norte", "Sede principal", "Activo") in vista.filas()
    monkeypatch.setattr(vistas, "pedir_almacen", lambda *a, **k: ("ALM-09", "Tst Bodega", "Calle 1"))
    vista.btn_nuevo.click()
    esperar(qtbot, lambda: ("ALM-09", "Tst Bodega", "Calle 1", "Activo") in vista.filas())
    vista.seleccionar("ALM-09")
    monkeypatch.setattr(vistas, "pedir_almacen", lambda *a, **k: ("ALM-09", "Tst Bodega 2", ""))
    vista.btn_editar.click()
    esperar(qtbot, lambda: ("ALM-09", "Tst Bodega 2", "", "Activo") in vista.filas())


def test_error_del_modelo_se_muestra(qtbot, luis, monkeypatch):  # ahora en lbl_error (ver abajo)
    vista = _vista(qtbot, AlmacenesView, luis)
    monkeypatch.setattr(vistas, "pedir_almacen", lambda *a, **k: ("ALM-01", "Repetido", ""))
    vista.btn_nuevo.click()
    esperar(qtbot, lambda: "ya existe" in vista.lbl_error.text())


def test_admin_ve_categorias_sin_botones_de_gestion(qtbot, cuentas, maestros_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    vista = _vista(qtbot, CategoriasView, ana)
    assert vista.btn_nuevo.isHidden() and vista.btn_editar.isHidden() and vista.btn_estado.isHidden()


def test_existencias_filtra(qtbot, luis, maestros_db):
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT MIN(sku) FROM productos WHERE categoria = 'Abarrotes'")
        sku = cur.fetchone()[0]
        cur.execute("UPDATE existencias_tst SET cantidad = 0 WHERE sku = :s", s=sku)
        cur.execute("INSERT INTO existencias_tst (sku, codigo_almacen, cantidad) VALUES (:s, 'ALM-02', 50)", s=sku)
        conn.commit()
    vista = _vista(qtbot, ExistenciasView, luis)
    todas = len(vista.filas())
    vista.combo_almacen.setCurrentIndex(vista.combo_almacen.findData("ALM-02"))
    assert [(f[0], f[3], f[4], f[5]) for f in vista.filas()] == [(sku, "Bodega Sur", "50", "Disponible")]
    vista.combo_almacen.setCurrentIndex(0)
    vista.combo_estado.setCurrentIndex(vista.combo_estado.findData("AGOTADO"))
    assert sku in [f[0] for f in vista.filas()] and all(f[5] == "Agotado" for f in vista.filas())
    vista.combo_estado.setCurrentIndex(0)
    vista.combo_categoria.setCurrentIndex(vista.combo_categoria.findData("Abarrotes"))
    assert vista.filas() and all(f[2] == "Abarrotes" for f in vista.filas())
    vista.combo_categoria.setCurrentIndex(0)
    vista.txt_buscar.setText(sku)
    assert {f[0] for f in vista.filas()} == {sku}
    vista.txt_buscar.setText("")
    assert len(vista.filas()) == todas


def test_secciones_nuevas_segun_permisos(qtbot):
    ventana = build_window(FakeRemoto(), auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    ventana.iniciar(Sesion("luis", "Luis Ortiz", INVENTARIO))
    assert {"Categorías", "Almacenes", "Existencias", "Inventario"} <= set(ventana.secciones())
    ventana.cerrar_sesion()
    ventana.iniciar(Sesion("x", "X", INVENTARIO, (("existencias", "NINGUNO"), ("categorias", "NINGUNO"),
                                                   ("conteos", "CONSULTA"), ("perfil", "GESTION"))))
    assert "Existencias" not in ventana.secciones() and "Categorías" not in ventana.secciones()
    assert "Inventario" in ventana.secciones()
    ventana.cerrar_sesion()
    ventana.iniciar(Sesion("ana", "Ana", ADMIN))
    assert {"Categorías", "Almacenes", "Existencias"} <= set(ventana.secciones())   # el administrador consulta


def test_error_de_una_accion_no_parece_de_la_base_y_no_lo_borra_el_refresco(qtbot, luis, monkeypatch):
    vista = _vista(qtbot, CategoriasView, luis)
    monkeypatch.setattr(vistas, "pedir_texto", lambda *a, **k: "abarrotes")
    vista.btn_nuevo.click()
    esperar(qtbot, lambda: "ya existe" in vista.lbl_error.text())
    assert not vista.lbl_error.isHidden() and "base de datos" not in vista.lbl_error.text()
    vista.refresh()                                            # el refresco automático de cada 5 s
    qtbot.wait(500)
    assert "ya existe" in vista.lbl_error.text() and not vista.lbl_error.isHidden()
    monkeypatch.setattr(vistas, "pedir_texto", lambda *a, **k: "Tst Nueva")
    vista.btn_nuevo.click()                                    # una acción que sí funciona lo quita
    esperar(qtbot, lambda: vista.lbl_error.isHidden())


def test_existencias_avisa_cuando_no_hay_coincidencias(qtbot, luis):
    vista = _vista(qtbot, ExistenciasView, luis)
    vista.txt_buscar.setText("no-existe-nada")
    assert vista.filas() == [] and not vista.banner.isHidden() and "coincide" in vista.banner.text()
    vista.txt_buscar.setText("")
    assert vista.banner.isHidden()


def test_existencias_marca_inactivos(qtbot, luis, maestros_db):
    maestros_db.activar_almacen(luis, "ALM-01", False)
    vista = _vista(qtbot, ExistenciasView, luis)
    assert all(f[3] == "Bodega Norte (inactivo)" for f in vista.filas())
    assert vista.combo_almacen.itemText(vista.combo_almacen.findData("ALM-01")) == "Bodega Norte (inactivo)"


def test_existencias_conserva_la_fila_elegida_al_refrescar(qtbot, luis):
    vista = _vista(qtbot, ExistenciasView, luis)
    vista.tabla.selectRow(3)
    elegido = vista.filas()[3][0]
    vista.refresh()
    qtbot.wait(500)
    assert vista.tabla.selectedItems() and vista.filas()[vista.tabla.currentRow()][0] == elegido
