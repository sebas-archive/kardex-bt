"""Pantallas Tareas de conteo y Diferencias (Fase 3)."""

import pytest

from app import db as dbq
from app.auth import ADMIN, INVENTARIO, Sesion
from app.main import build_window
from app.views import diferencias as vdif
from app.views import tareas as vtar
from app.views.diferencias import DiferenciasView
from app.views.tareas import TareasView
from conftest import staging
from fakes import FakeRemoto

ARROZ, JABON = "7701234000001", "7701234000025"
T0 = 1731170400000
_seq = iter(range(50_000, 99_999))


def esperar(qtbot, condicion, timeout=15000):
    qtbot.waitUntil(condicion, timeout=timeout)


def _sql(sql, **binds):
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute(sql, binds)
        conn.commit()


def _leer(id_tarea, sku, cant, nota="", danados="", foto=None):
    with dbq._conexion() as conn:
        n = next(_seq)
        staging(conn, "tst-tareas-esc", n, T0 + n * 1000, id_tarea, sku, cant, nota=nota, danados=danados)
        if foto:
            conn.cursor().execute("INSERT INTO fotos (uuid_dispositivo, seq, ruta, bytes) VALUES ('tst-tareas-esc', :s, :r, 9)",
                                  s=n, r=foto)
            conn.commit()
        conn.cursor().callproc("pkg_batch.procesar_pendientes")


@pytest.fixture
def gente(cuentas, tareas_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    for usuario, nombre in (("pedro", "Pedro Ruiz"), ("rosa", "Rosa Gil")):
        _sql("INSERT INTO usuarios_tst (usuario, nombre, rol, clave_hash, estado, origen) "
             "VALUES (:u, :n, 'OPERADOR', '-', 'ACTIVO', 'MOVIL')", u=usuario, n=nombre)
    return tareas_db, ana, cuentas.iniciar_sesion("luis", "conteo2026")


def _vista(qtbot, clase, sesion, hay_filas=True):
    vista = clase()
    qtbot.addWidget(vista)
    vista.set_sesion(sesion)
    if hay_filas:
        esperar(qtbot, lambda: len(vista.filas()) > 0)
    else:
        qtbot.wait(800)
    return vista


def _fila(vista, id_tarea):
    return next(f for f in vista.filas() if f[0] == id_tarea)


# ------------------------------------------------------------------ Tareas
def test_crear_tarea_con_el_dialogo(qtbot, gente, monkeypatch):
    _t, _ana, luis = gente
    vista = _vista(qtbot, TareasView, luis, hay_filas=False)
    assert "no hay tareas" in vista.banner.text().lower()
    vistos = {}

    def dialogo(_padre, almacenes, operadores, productos, inicial=None, error=""):
        vistos.update(almacenes=almacenes, operadores=operadores, productos=productos)
        return "Bodega norte", "ALM-01", "pedro", [ARROZ, JABON], "Solo estantería A"

    monkeypatch.setattr(vtar, "pedir_tarea", dialogo)
    vista.btn_nuevo.click()
    esperar(qtbot, lambda: len(vista.filas()) == 1)
    id_tarea, almacen, operador, productos, avance, estado = vista.filas()[0]
    assert (almacen, operador, productos, avance, estado) == ("Bodega Norte", "Pedro Ruiz", "2", "0/2", "Asignada")
    assert ("ALM-01", "Bodega Norte") in vistos["almacenes"] and ("pedro", "Pedro Ruiz") in vistos["operadores"]
    assert (ARROZ, "Arroz 500 g", "Abarrotes") in vistos["productos"]


def test_avance_reasignar_y_cerrar(qtbot, gente, monkeypatch):
    t, _ana, luis = gente
    id_tarea = t.crear_tarea(luis, "Tarea", "ALM-01", "pedro", [ARROZ, JABON], "")
    vista = _vista(qtbot, TareasView, luis)
    vista.seleccionar(id_tarea)
    esperar(qtbot, lambda: vista.tabla_avance.rowCount() == 2)
    assert vista.btn_reasignar.isEnabled() and vista.btn_cerrar.isEnabled()
    monkeypatch.setattr(vtar, "pedir_operador", lambda _p, operadores, actual: "rosa")
    vista.btn_reasignar.click()
    esperar(qtbot, lambda: _fila(vista, id_tarea)[2] == "Rosa Gil")

    _leer(id_tarea, ARROZ, 3)
    vista.refresh()
    esperar(qtbot, lambda: _fila(vista, id_tarea)[4:] == ("1/2", "Enviada parcialmente"))
    vista.seleccionar(id_tarea)
    assert not vista.btn_reasignar.isEnabled()                    # ya empezó: no se reasigna
    esperar(qtbot, lambda: vista.avance_filas() == [(ARROZ, "Arroz 500 g", "Sí", "3", ""),
                                                    (JABON, "Jabón de Barra 300 g", "No", "", "")])
    monkeypatch.setattr(vtar, "confirmar", lambda *a: True)
    vista.btn_cerrar.click()
    esperar(qtbot, lambda: _fila(vista, id_tarea)[5] == "Cerrada")
    vista.seleccionar(id_tarea)
    assert not vista.btn_cerrar.isEnabled()


def test_cerrar_cancelado_no_hace_nada(qtbot, gente, monkeypatch):
    t, _ana, luis = gente
    id_tarea = t.crear_tarea(luis, "Tarea", "ALM-01", "pedro", [ARROZ], "")
    vista = _vista(qtbot, TareasView, luis)
    vista.seleccionar(id_tarea)
    monkeypatch.setattr(vtar, "confirmar", lambda *a: False)
    vista.btn_cerrar.click()
    qtbot.wait(500)
    assert _fila(vista, id_tarea)[5] == "Asignada"


def test_filtros_de_tareas(qtbot, gente):
    t, _ana, luis = gente
    _sql("UPDATE existencias_tst SET cantidad = 1 WHERE codigo_almacen = 'ALM-01' AND sku = :s", s=ARROZ)
    a = t.crear_tarea(luis, "Una", "ALM-01", "pedro", [ARROZ], "")
    b = t.crear_tarea(luis, "Otra", "ALM-01", "rosa", [ARROZ], "")
    _leer(b, ARROZ, 1)
    vista = _vista(qtbot, TareasView, luis)
    esperar(qtbot, lambda: len(vista.filas()) == 2)
    vista.combo_operador.setCurrentIndex(vista.combo_operador.findData("pedro"))
    assert [f[0] for f in vista.filas()] == [a]
    vista.combo_operador.setCurrentIndex(0)
    vista.combo_estado.setCurrentIndex(vista.combo_estado.findData("SINCRONIZADA"))
    assert [f[0] for f in vista.filas()] == [b]


def test_error_de_accion_se_ve_y_el_refresco_no_lo_borra(qtbot, gente, monkeypatch):
    _t, _ana, luis = gente
    vista = _vista(qtbot, TareasView, luis, hay_filas=False)
    respuestas = iter([("Tarea", "ALM-01", "nadie", [ARROZ], ""), None])   # luego cancela el diálogo reabierto
    monkeypatch.setattr(vtar, "pedir_tarea", lambda *a, **k: next(respuestas))
    vista.btn_nuevo.click()
    esperar(qtbot, lambda: "ya no está activo" in vista.lbl_error.text())
    vista.refresh()
    qtbot.wait(500)
    assert "ya no está activo" in vista.lbl_error.text() and not vista.lbl_error.isHidden()


def test_admin_consulta_tareas_y_diferencias_sin_botones(qtbot, gente):
    t, ana, luis = gente
    t.crear_tarea(luis, "Tarea", "ALM-01", "pedro", [ARROZ], "")
    tareas = _vista(qtbot, TareasView, ana)
    assert tareas.btn_nuevo.isHidden() and tareas.btn_reasignar.isHidden() and tareas.btn_cerrar.isHidden()
    difs = _vista(qtbot, DiferenciasView, ana, hay_filas=False)
    assert difs.btn_revisada.isHidden() and difs.btn_recuento.isHidden()


def test_secciones_de_la_fase_3_segun_permisos(qtbot):
    ventana = build_window(FakeRemoto(), auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    ventana.iniciar(Sesion("luis", "Luis Ortiz", INVENTARIO))
    assert {"Tareas de conteo", "Diferencias"} <= set(ventana.secciones())
    ventana.cerrar_sesion()
    ventana.iniciar(Sesion("x", "X", INVENTARIO, (("tareas", "NINGUNO"), ("diferencias", "CONSULTA"), ("perfil", "GESTION"))))
    assert "Tareas de conteo" not in ventana.secciones() and "Diferencias" in ventana.secciones()
    ventana.cerrar_sesion()
    ventana.iniciar(Sesion("ana", "Ana", ADMIN))
    assert {"Tareas de conteo", "Diferencias"} <= set(ventana.secciones())


# ------------------------------------------------------------------ Diferencias
@pytest.fixture
def con_diferencia(gente):
    t, ana, luis = gente
    _sql("UPDATE existencias_tst SET cantidad = 10 WHERE codigo_almacen = 'ALM-01' AND sku IN (:a, :b)", a=ARROZ, b=JABON)
    id_tarea = t.crear_tarea(luis, "Tarea", "ALM-01", "pedro", [ARROZ, JABON], "")
    _leer(id_tarea, ARROZ, 7, nota="caja rota")
    _leer(id_tarea, JABON, 12)
    return t, ana, luis, id_tarea


def test_diferencias_muestra_y_filtra(qtbot, con_diferencia):
    _t, _ana, luis, id_tarea = con_diferencia
    vista = _vista(qtbot, DiferenciasView, luis)
    mias = [f for f in vista.filas() if f[0] == id_tarea]
    assert (id_tarea, "Arroz 500 g", "ALM-01", "10", "7", "-3", "Faltante", "caja rota", "Pendiente", "", "") in mias
    assert (id_tarea, "Jabón de Barra 300 g", "ALM-01", "10", "12", "+2", "Sobrante", "", "Pendiente", "", "") in mias
    vista.combo_tipo.setCurrentIndex(vista.combo_tipo.findData("SOBRANTE"))
    assert all(f[6] == "Sobrante" for f in vista.filas())
    vista.combo_tipo.setCurrentIndex(0)
    vista.combo_tarea.setCurrentIndex(vista.combo_tarea.findData(id_tarea))
    assert {f[0] for f in vista.filas()} == {id_tarea}


def test_marcar_revisada_la_saca_de_pendientes(qtbot, con_diferencia, monkeypatch):
    _t, _ana, luis, id_tarea = con_diferencia
    vista = _vista(qtbot, DiferenciasView, luis)
    vista.combo_tarea.setCurrentIndex(vista.combo_tarea.findData(id_tarea))
    vista.seleccionar(id_tarea, ARROZ)
    monkeypatch.setattr(vdif, "pedir_texto", lambda *a, **k: "Se rompió una caja")
    vista.btn_revisada.click()
    esperar(qtbot, lambda: [f[1] for f in vista.filas()] == ["Jabón de Barra 300 g"])
    vista.combo_estado.setCurrentIndex(vista.combo_estado.findData(None))     # Todos
    assert ("Arroz 500 g", "Revisada") in [(f[1], f[8]) for f in vista.filas()]


def test_pedir_recuento(qtbot, con_diferencia):
    _t, _ana, luis, id_tarea = con_diferencia
    vista = _vista(qtbot, DiferenciasView, luis)
    vista.combo_tarea.setCurrentIndex(vista.combo_tarea.findData(id_tarea))
    vista.combo_estado.setCurrentIndex(vista.combo_estado.findData(None))
    vista.seleccionar(id_tarea, JABON)
    vista.btn_recuento.click()
    esperar(qtbot, lambda: ("Jabón de Barra 300 g", "Recuento pedido") in [(f[1], f[8]) for f in vista.filas()])


def test_diferencias_sin_coincidencias_avisa(qtbot, con_diferencia):
    _t, _ana, luis, id_tarea = con_diferencia
    vista = _vista(qtbot, DiferenciasView, luis)
    vista.combo_tarea.setCurrentIndex(vista.combo_tarea.findData(id_tarea))
    vista.combo_estado.setCurrentIndex(vista.combo_estado.findData("RECUENTO"))
    assert vista.filas() == [] and not vista.banner.isHidden() and "coincide" in vista.banner.text()


# ------------------------------------------------------------------ correcciones de la revisión final
def test_sin_almacenes_activos_no_abre_el_dialogo(qtbot, gente, monkeypatch):
    _t, _ana, luis = gente
    _sql("UPDATE almacenes_tst SET activo = 'N'")
    vista = _vista(qtbot, TareasView, luis, hay_filas=False)
    llamadas = []
    monkeypatch.setattr(vtar, "pedir_tarea", lambda *a, **k: llamadas.append(a) or None)
    vista.btn_nuevo.click()
    esperar(qtbot, lambda: "No hay almacenes activos" in vista.lbl_error.text())
    assert llamadas == []


def test_rechazo_del_pc_reabre_el_dialogo_con_lo_escrito(qtbot, gente, monkeypatch):
    _t, _ana, luis = gente
    vista = _vista(qtbot, TareasView, luis, hay_filas=False)
    escrito = ("Tarea larga de escribir", "ALM-01", "nadie", [ARROZ, JABON], "Con cuidado")
    llamadas = []

    def dialogo(_padre, _alm, _ops, _prods, inicial=None, error=""):
        llamadas.append((inicial, error))
        return escrito if len(llamadas) == 1 else None

    monkeypatch.setattr(vtar, "pedir_tarea", dialogo)
    vista.btn_nuevo.click()
    esperar(qtbot, lambda: len(llamadas) == 2)
    assert llamadas[0] == (None, "")
    assert llamadas[1][0] == escrito and "ya no está activo" in llamadas[1][1]


def test_avance_explica_las_lecturas_con_error(qtbot, gente):
    t, _ana, luis = gente
    id_tarea = t.crear_tarea(luis, "Tarea", "ALM-01", "pedro", [ARROZ], "")
    _leer(id_tarea, "7709990001234", 3)
    vista = _vista(qtbot, TareasView, luis)
    esperar(qtbot, lambda: _fila(vista, id_tarea)[5] == "Con error")
    vista.seleccionar(id_tarea)
    esperar(qtbot, lambda: "SKU_DESCONOCIDO" in vista.lbl_errores.text() and "7709990001234" in vista.lbl_errores.text())
    assert not vista.lbl_errores.isHidden()



# ------------------------------------------------------------------ Fase 4: dañados y fotos
def test_foto_en_diferencias_y_en_el_avance(qtbot, gente, monkeypatch):
    t, _ana, luis = gente
    _sql("UPDATE existencias_tst SET cantidad = 10 WHERE codigo_almacen = 'ALM-01' AND sku IN (:a, :b)", a=ARROZ, b=JABON)
    id_tarea = t.crear_tarea(luis, "Tarea", "ALM-01", "pedro", [ARROZ, JABON], "")
    _leer(id_tarea, ARROZ, 7, nota="caja rota", danados="2", foto="tst-tareas-esc/77.jpg")
    _leer(id_tarea, JABON, 12)
    abiertas = []
    monkeypatch.setattr(vdif, "ver_foto", lambda _p, ruta, *a: abiertas.append(ruta))
    monkeypatch.setattr(vtar, "ver_foto", lambda _p, ruta, *a: abiertas.append(ruta))

    difs = _vista(qtbot, DiferenciasView, luis)
    difs.combo_tarea.setCurrentIndex(difs.combo_tarea.findData(id_tarea))
    filas = {f[1]: f for f in difs.filas()}
    assert filas["Arroz 500 g"][9:] == ("2", "📷") and filas["Jabón de Barra 300 g"][9:] == ("", "")
    fila_arroz = [f[1] for f in difs.filas()].index("Arroz 500 g")
    fila_jabon = [f[1] for f in difs.filas()].index("Jabón de Barra 300 g")
    difs.tabla.cellClicked.emit(fila_jabon, 10)            # sin foto: no abre nada
    difs.tabla.cellClicked.emit(fila_arroz, 9)             # otra columna: tampoco
    difs.tabla.cellClicked.emit(fila_arroz, 10)
    assert abiertas == ["tst-tareas-esc/77.jpg"]

    tareas_v = _vista(qtbot, TareasView, luis)
    tareas_v.seleccionar(id_tarea)
    esperar(qtbot, lambda: tareas_v.tabla_avance.rowCount() == 2)
    assert tareas_v.avance_filas()[0][4] == "📷"
    tareas_v.tabla_avance.cellClicked.emit(0, 4)
    assert abiertas[-1] == "tst-tareas-esc/77.jpg"
