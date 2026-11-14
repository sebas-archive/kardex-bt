"""Pantallas Movimientos y Ajustes, y «Ajustar existencia…» en Diferencias (Fase 3b)."""

from datetime import date, timedelta

import pytest

from app import db as dbq
from app.auth import ADMIN, INVENTARIO, Sesion
from app.main import build_window
from app.sync_bridge import SyncBridge
from app.views import ajustes as vaj
from app.views import diferencias as vdif
from app.views import movimientos as vmov
from app.views.ajustes import AjustesView
from app.views.diferencias import DiferenciasView
from app.views.movimientos import MovimientosView
from conftest import staging
from fakes import FakeStore, FakeTransport

ARROZ, AZUCAR = "7701234000001", "7701234000002"
HOY = date.today()
T0 = 1731170400000
_seq = iter(range(300_000, 399_999))


def esperar(qtbot, condicion, timeout=15000):
    qtbot.waitUntil(condicion, timeout=timeout)


def _sql(sql, **binds):
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute(sql, binds)
        filas = cur.fetchall() if cur.description else None
        conn.commit()
        return filas


def _cantidad(sku, almacen="ALM-01"):
    filas = _sql("SELECT cantidad FROM existencias_tst WHERE sku = :s AND codigo_almacen = :a", s=sku, a=almacen)
    return float(filas[0][0]) if filas else None


@pytest.fixture
def gente(cuentas, movimientos_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    _sql("UPDATE existencias_tst SET cantidad = 100 WHERE codigo_almacen = 'ALM-01' AND sku IN (:a, :b)", a=ARROZ, b=AZUCAR)
    return movimientos_db, ana, cuentas.iniciar_sesion("luis", "conteo2026")


def _vista(qtbot, clase, sesion, hay_filas=True):
    vista = clase()
    qtbot.addWidget(vista)
    vista.set_sesion(sesion)
    if hay_filas:
        esperar(qtbot, lambda: len(vista.filas()) > 0)
    else:
        qtbot.wait(800)
    return vista


# ------------------------------------------------------------------ Movimientos
def test_entrada_y_salida_con_el_dialogo(qtbot, gente, monkeypatch):
    _m, _ana, luis = gente
    vista = _vista(qtbot, MovimientosView, luis, hay_filas=False)
    assert "todavía no hay movimientos" in vista.banner.text().lower()
    vistos = {}

    def dialogo(_padre, tipo, almacenes, productos, inicial=None, error=""):
        vistos[tipo] = (almacenes, productos)
        if tipo == "ENTRADA":
            return ARROZ, "ALM-01", 50.0, HOY, "", "Compra proveedor"
        return ARROZ, "ALM-01", 3.0, HOY, "Venta", ""

    monkeypatch.setattr(vmov, "pedir_movimiento", dialogo)
    vista.btn_entrada.click()
    esperar(qtbot, lambda: len(vista.filas()) == 1)
    vista.btn_salida.click()
    esperar(qtbot, lambda: len(vista.filas()) == 2)
    salida, entrada = vista.filas()
    assert entrada[1:7] == ("Entrada", "Arroz 500 g", "Bodega Norte", "+50", "Compra proveedor", "Luis Ortiz")
    assert salida[1:5] == ("Salida", "Arroz 500 g", "Bodega Norte", "−3") and salida[5] == "Venta"
    assert _cantidad(ARROZ) == 147
    assert ("ALM-01", "Bodega Norte") in vistos["ENTRADA"][0]
    assert (ARROZ, "Arroz 500 g", "Abarrotes") in vistos["SALIDA"][1]


def test_filtros_de_movimientos(qtbot, gente):
    m, _ana, luis = gente
    m.registrar_entrada(luis, ARROZ, "ALM-01", 5, HOY - timedelta(days=10), "vieja")
    m.registrar_salida(luis, AZUCAR, "ALM-01", 2, HOY, "Daño", "")
    m.registrar_entrada(luis, AZUCAR, "ALM-02", 1, HOY, "")
    vista = _vista(qtbot, MovimientosView, luis)
    esperar(qtbot, lambda: len(vista.filas()) == 3)
    vista.combo_tipo.setCurrentIndex(vista.combo_tipo.findData("SALIDA"))
    assert [f[1] for f in vista.filas()] == ["Salida"]
    vista.combo_tipo.setCurrentIndex(0)
    vista.combo_almacen.setCurrentIndex(vista.combo_almacen.findData("ALM-02"))
    assert [f[3] for f in vista.filas()] == ["Bodega Sur"]
    vista.combo_almacen.setCurrentIndex(0)
    vista.fecha_desde.setDate(HOY - timedelta(days=1))
    assert len(vista.filas()) == 2
    vista.fecha_desde.setDate(HOY - timedelta(days=30))
    vista.txt_buscar.setText("arroz")
    assert [f[2] for f in vista.filas()] == ["Arroz 500 g"]
    vista.txt_buscar.setText("")
    vista.combo_responsable.setCurrentIndex(vista.combo_responsable.findData("luis"))
    assert len(vista.filas()) == 3
    vista.txt_buscar.setText("no-existe")
    assert vista.filas() == [] and "coincide" in vista.banner.text()


def test_salida_mayor_que_lo_que_hay_reabre_con_el_error(qtbot, gente, monkeypatch):
    _m, _ana, luis = gente
    vista = _vista(qtbot, MovimientosView, luis, hay_filas=False)
    escrito = (ARROZ, "ALM-01", 500.0, HOY, "Venta", "Pedido grande")
    llamadas = []

    def dialogo(_padre, tipo, _alm, _prods, inicial=None, error=""):
        llamadas.append((inicial, error))
        return escrito if len(llamadas) == 1 else None

    monkeypatch.setattr(vmov, "pedir_movimiento", dialogo)
    vista.btn_salida.click()
    esperar(qtbot, lambda: len(llamadas) == 2)
    assert llamadas[1][0] == escrito and "Solo hay 100" in llamadas[1][1]
    assert _cantidad(ARROZ) == 100


def test_admin_consulta_movimientos_sin_botones(qtbot, gente):
    m, ana, luis = gente
    m.registrar_entrada(luis, ARROZ, "ALM-01", 1, HOY, "")
    vista = _vista(qtbot, MovimientosView, ana)
    assert vista.btn_entrada.isHidden() and vista.btn_salida.isHidden()


# ------------------------------------------------------------------ Ajustes
def test_ajuste_critico_lo_aprueba_el_administrador(qtbot, gente, monkeypatch):
    m, ana, luis = gente
    inv = _vista(qtbot, AjustesView, luis, hay_filas=False)
    assert inv.btn_aprobar.isHidden() and inv.btn_rechazar.isHidden() and not inv.btn_nuevo.isHidden()
    monkeypatch.setattr(vaj, "pedir_ajuste", lambda *a, **k: (ARROZ, "ALM-01", 40.0, "Conteo de bodega"))
    inv.btn_nuevo.click()
    esperar(qtbot, lambda: len(inv.filas()) == 1)
    fila = inv.filas()[0]
    assert fila[1:9] == ("Arroz 500 g", "Bodega Norte", "100", "40", "−60", "Conteo de bodega",
                         "Pendiente de aprobación", "Luis Ortiz")
    assert "pendiente de aprobación" in inv.lbl_info.text().lower() and _cantidad(ARROZ) == 100

    admin = _vista(qtbot, AjustesView, ana)
    assert admin.btn_nuevo.isHidden() and not admin.btn_aprobar.isHidden()
    admin.seleccionar(m.listar()[0].id)
    assert admin.btn_aprobar.isEnabled()
    preguntas = []
    monkeypatch.setattr(vaj, "confirmar", lambda _p, texto: preguntas.append(texto) or True)
    admin.btn_aprobar.click()
    esperar(qtbot, lambda: bool(preguntas))
    assert "hoy hay 100" in preguntas[0] and "quedará en 40" in preguntas[0]
    esperar(qtbot, lambda: admin.filas()[0][7] == "Aplicado")
    assert _cantidad(ARROZ) == 40
    admin.seleccionar(m.listar()[0].id)
    assert not admin.btn_aprobar.isEnabled() and not admin.btn_rechazar.isEnabled()


def test_rechazar_ajuste_con_motivo(qtbot, gente, monkeypatch):
    m, ana, luis = gente
    m.solicitar_ajuste(luis, ARROZ, "ALM-01", 10, "Conteo")
    admin = _vista(qtbot, AjustesView, ana)
    admin.seleccionar(m.listar()[0].id)
    monkeypatch.setattr(vaj, "pedir_texto", lambda *a, **k: "Recontar primero")
    admin.btn_rechazar.click()
    esperar(qtbot, lambda: admin.filas()[0][7] == "Rechazado")
    assert "Recontar primero" in admin.filas()[0][6]


# ------------------------------------------------------------------ Diferencias → ajuste
def test_ajustar_existencia_desde_diferencias(qtbot, gente, monkeypatch):
    m, _ana, luis = gente
    from app import tareas
    _sql("INSERT INTO usuarios_tst (usuario, nombre, rol, clave_hash, estado, origen) "
         "VALUES ('pedro', 'Pedro Ruiz', 'OPERADOR', '-', 'ACTIVO', 'MOVIL')")
    id_tarea = tareas.crear_tarea(luis, "Tarea", "ALM-01", "pedro", [ARROZ], "")
    with dbq._conexion() as conn:
        n = next(_seq)
        staging(conn, "tst-tareas-esc", n, T0 + n * 1000, id_tarea, ARROZ, 97)
        conn.cursor().callproc("pkg_batch.procesar_pendientes")
    vista = _vista(qtbot, DiferenciasView, luis)
    vista.combo_tarea.setCurrentIndex(vista.combo_tarea.findData(id_tarea))
    vista.seleccionar(id_tarea, ARROZ)
    assert vista.btn_ajustar.isEnabled()
    vistos = []

    def dialogo(_padre, almacenes, productos, inicial=None, error="", **kw):
        vistos.append(inicial)
        return inicial

    monkeypatch.setattr(vdif, "pedir_ajuste", dialogo)
    vista.btn_ajustar.click()
    vista.combo_estado.setCurrentIndex(vista.combo_estado.findData(None))
    esperar(qtbot, lambda: ("Arroz 500 g", "Ajustada") in [(f[1], f[8]) for f in vista.filas()])
    assert vistos[0] == (ARROZ, "ALM-01", 97.0, f"Conteo {id_tarea}") and _cantidad(ARROZ) == 97
    vista.seleccionar(id_tarea, ARROZ)
    assert not vista.btn_ajustar.isEnabled()


def test_admin_no_ve_ajustar_en_diferencias(qtbot, gente):
    _m, ana, _luis = gente
    vista = _vista(qtbot, DiferenciasView, ana, hay_filas=False)
    assert vista.btn_ajustar.isHidden()


def test_secciones_de_la_fase_3b(qtbot):
    ventana = build_window(SyncBridge(FakeTransport(), FakeStore()), auto_refresh_ms=0)
    qtbot.addWidget(ventana)
    ventana.iniciar(Sesion("luis", "Luis Ortiz", INVENTARIO))
    assert {"Movimientos", "Ajustes"} <= set(ventana.secciones())
    ventana.cerrar_sesion()
    ventana.iniciar(Sesion("x", "X", INVENTARIO, (("movimientos", "NINGUNO"), ("ajustes", "CONSULTA"), ("perfil", "GESTION"))))
    assert "Movimientos" not in ventana.secciones() and "Ajustes" in ventana.secciones()
    ventana.cerrar_sesion()
    ventana.iniciar(Sesion("ana", "Ana", ADMIN))
    assert {"Movimientos", "Ajustes"} <= set(ventana.secciones())


# ------------------------------------------------------------------ correcciones de la revisión final
def test_producto_escrito_que_no_esta_en_la_lista_no_cuenta(qtbot):
    combo = vmov.combo_productos([(ARROZ, "Arroz 500 g", "Abarrotes"), (AZUCAR, "Azúcar 1 kg", "Abarrotes")])
    qtbot.addWidget(combo)
    combo.setCurrentIndex(1)
    assert vmov.producto_elegido(combo) == AZUCAR
    combo.setEditText("arro")                      # escribió sin elegir de la lista
    assert vmov.producto_elegido(combo) == ""


def test_ajuste_manual_consulta_la_existencia_en_el_dialogo(qtbot, gente, monkeypatch):
    m, _ana, luis = gente
    vista = _vista(qtbot, AjustesView, luis, hay_filas=False)
    recibido = {}
    monkeypatch.setattr(vaj, "pedir_ajuste", lambda *a, **k: recibido.update(k) or None)
    vista.btn_nuevo.click()
    esperar(qtbot, lambda: "consultar" in recibido)
    assert recibido["consultar"](ARROZ, "ALM-01") == (100.0, 2400.0)


def test_aprobar_cancelado_no_hace_nada(qtbot, gente, monkeypatch):
    m, ana, luis = gente
    m.solicitar_ajuste(luis, ARROZ, "ALM-01", 10, "Conteo")
    admin = _vista(qtbot, AjustesView, ana)
    admin.seleccionar(m.listar()[0].id)
    monkeypatch.setattr(vaj, "confirmar", lambda *a: False)
    admin.btn_aprobar.click()
    qtbot.wait(800)
    assert m.listar()[0].estado == m.PENDIENTE and _cantidad(ARROZ) == 100
