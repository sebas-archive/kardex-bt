"""Tareas de conteo y diferencias (Fase 3): operaciones del escritorio."""

import pytest

from app import db as dbq
from app.auth import INVENTARIO, ErrorDeAcceso
from btsync import tareas as bt
from conftest import staging

ARROZ, AZUCAR, JABON = "7701234000001", "7701234000002", "7701234000025"   # Abarrotes, Abarrotes, Aseo
T0 = 1731170400000


def _sql(sql, **binds):
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute(sql, binds)
        filas = cur.fetchall() if cur.description else None
        conn.commit()
        return filas


@pytest.fixture
def gente(cuentas, tareas_db):
    """Ana (ADMIN: consulta), Luis (INVENTARIO: gestiona) y Pedro (OPERADOR activo, cuenta del móvil)."""
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    for usuario, nombre, estado in (("pedro", "Pedro Ruiz", "ACTIVO"), ("marta", "Marta Paz", "SUSPENDIDO")):
        _sql("INSERT INTO usuarios_tst (usuario, nombre, rol, clave_hash, estado, origen) "
             "VALUES (:u, :n, 'OPERADOR', '-', :e, 'MOVIL')", u=usuario, n=nombre, e=estado)
    return tareas_db, ana, cuentas.iniciar_sesion("luis", "conteo2026")


_seq = iter(range(1, 100_000))


def _leer(id_tarea, sku, cant, nota="", danados="", foto=None):
    """Una lectura del móvil, procesada por el batch; con ``foto`` (ruta relativa) también llegó su foto."""
    with dbq._conexion() as conn:
        n = next(_seq)
        staging(conn, "tst-tareas-esc", n, T0 + n * 1000, id_tarea, sku, cant, nota=nota, danados=danados)
        if foto:
            conn.cursor().execute("INSERT INTO fotos (uuid_dispositivo, seq, ruta, bytes) VALUES ('tst-tareas-esc', :s, :r, 9)",
                                  s=n, r=foto)
            conn.commit()
        conn.cursor().callproc("pkg_batch.procesar_pendientes")


def _crear(t, luis, skus=(ARROZ, JABON), almacen="ALM-01", operador="pedro", nombre="Bodega norte"):
    return t.crear_tarea(luis, nombre, almacen, operador, list(skus), "Solo estantería A")


# ------------------------------------------------------------------ crear
def test_crear_tarea_toma_existencias_del_almacen(gente):
    t, _ana, luis = gente
    _sql("UPDATE existencias_tst SET cantidad = 37 WHERE sku = :s AND codigo_almacen = 'ALM-01'", s=ARROZ)
    id_tarea = _crear(t, luis)
    assert id_tarea.startswith("TT-") and len(id_tarea) == 6        # TT-001: tres dígitos
    stock = dict(_sql("SELECT sku, cantidad_sistema FROM stock_sistema WHERE id_conteo = :c", c=id_tarea))
    assert stock[ARROZ] == 37 and set(stock) == {ARROZ, JABON}
    r = next(x for x in t.listar_tareas() if x.id == id_tarea)
    assert (r.nombre, r.almacen, r.operador, r.instrucciones, r.total, r.estado) == \
        ("Bodega norte", "ALM-01", "pedro", "Solo estantería A", 2, bt.ASIGNADA)
    assert _sql("SELECT creada_por, estado FROM conteos WHERE id_conteo = :c", c=id_tarea) == [("luis", "ABIERTO")]


def test_crear_tarea_sin_fila_de_existencias_usa_cero(gente):
    t, _ana, luis = gente
    id_tarea = _crear(t, luis, skus=(ARROZ,), almacen="ALM-02")   # ALM-02 no tiene existencias sembradas
    assert _sql("SELECT cantidad_sistema FROM stock_sistema WHERE id_conteo = :c", c=id_tarea) == [(0,)]


@pytest.mark.parametrize("cambio, mensaje", [
    (dict(almacen="ALM-02"), "ya no está activo"),
    (dict(operador="marta"), "ya no está activo"),
    (dict(operador="luis"), "ya no está activo"),          # no es operador
    (dict(skus=()), "al menos un producto"),
    (dict(nombre="  "), "nombre"),
])
def test_crear_tarea_rechaza_datos_invalidos(gente, cambio, mensaje):
    t, _ana, luis = gente
    _sql("UPDATE almacenes_tst SET activo = 'N' WHERE codigo = 'ALM-02'")
    with pytest.raises(ErrorDeAcceso, match=mensaje):
        _crear(t, luis, **cambio)
    assert not t.listar_tareas()


def test_crear_tarea_rechaza_producto_de_categoria_inactiva(gente):
    t, _ana, luis = gente
    _sql("UPDATE categorias_tst SET activa = 'N' WHERE nombre = 'Aseo'")
    with pytest.raises(ErrorDeAcceso, match="categoría inactiva"):
        _crear(t, luis)


def test_admin_no_crea_ni_reasigna_ni_cierra(gente):
    t, ana, luis = gente
    with pytest.raises(ErrorDeAcceso, match="permiso"):
        _crear(t, ana)
    id_tarea = _crear(t, luis)
    for accion in (lambda: t.reasignar(ana, id_tarea, "pedro"), lambda: t.cerrar(ana, id_tarea)):
        with pytest.raises(ErrorDeAcceso, match="permiso"):
            accion()


def test_ofrece_solo_operadores_y_productos_disponibles(gente):
    t, _ana, _luis = gente
    _sql("UPDATE categorias_tst SET activa = 'N' WHERE nombre = 'Aseo'")
    assert t.operadores_disponibles() == [("pedro", "Pedro Ruiz")]
    productos = t.productos_disponibles()
    assert (ARROZ, "Arroz 500 g", "Abarrotes") in productos
    assert JABON not in [p[0] for p in productos]


# ------------------------------------------------------------------ reasignar y cerrar
def test_reasignar_solo_mientras_esta_asignada(gente):
    t, _ana, luis = gente
    _sql("INSERT INTO usuarios_tst (usuario, nombre, rol, clave_hash, estado, origen) "
         "VALUES ('rosa', 'Rosa Gil', 'OPERADOR', '-', 'ACTIVO', 'MOVIL')")
    id_tarea = _crear(t, luis)
    t.reasignar(luis, id_tarea, "rosa")
    assert next(x for x in t.listar_tareas() if x.id == id_tarea).operador == "rosa"
    with pytest.raises(ErrorDeAcceso, match="ya no está activo"):
        t.reasignar(luis, id_tarea, "marta")
    _leer(id_tarea, ARROZ, 5)
    with pytest.raises(ErrorDeAcceso, match="aún no empezó"):
        t.reasignar(luis, id_tarea, "pedro")


def test_reasignar_tarea_que_ya_no_existe(gente):
    t, _ana, luis = gente
    with pytest.raises(ErrorDeAcceso, match="ya no existe"):
        t.reasignar(luis, "TT-999", "pedro")


def test_cerrar_y_avance(gente):
    t, _ana, luis = gente
    id_tarea = _crear(t, luis)
    _leer(id_tarea, ARROZ, 4)
    assert t.avance(id_tarea) == [(ARROZ, "Arroz 500 g", True, 4.0, ""), (JABON, "Jabón de Barra 300 g", False, None, "")]
    t.cerrar(luis, id_tarea)
    assert next(x for x in t.listar_tareas() if x.id == id_tarea).estado == bt.CERRADA


# ------------------------------------------------------------------ diferencias
def _con_diferencias(t, luis):
    _sql("UPDATE existencias_tst SET cantidad = 10 WHERE codigo_almacen = 'ALM-01' AND sku IN (:a, :b)", a=ARROZ, b=JABON)
    id_tarea = _crear(t, luis)
    _leer(id_tarea, ARROZ, 7, nota="caja rota")
    _leer(id_tarea, JABON, 10)
    return id_tarea


def _difs(t, id_tarea):
    return [d for d in t.listar_diferencias() if d.id_conteo == id_tarea]


def test_listar_diferencias(gente):
    t, _ana, luis = gente
    id_tarea = _con_diferencias(t, luis)
    assert _difs(t, id_tarea) == [t.Diferencia(id_tarea, ARROZ, "Arroz 500 g", "ALM-01", 10.0, 7.0, -3.0, "FALTANTE",
                                                "caja rota", t.PENDIENTE, None, "")]


def test_marcar_revisada_y_pedir_recuento(gente):
    t, _ana, luis = gente
    id_tarea = _con_diferencias(t, luis)
    t.marcar_revisada(luis, id_tarea, ARROZ, "Se rompió una caja")
    assert _difs(t, id_tarea)[0].estado == t.REVISADA
    t.pedir_recuento(luis, id_tarea, ARROZ)
    assert _difs(t, id_tarea)[0].estado == t.RECUENTO
    r = next(x for x in t.listar_tareas() if x.id == id_tarea)
    assert (r.contados, r.estado) == (1, bt.ENVIADA_PARCIALMENTE)


def test_lectura_nueva_devuelve_la_diferencia_a_pendiente(gente):
    t, _ana, luis = gente
    id_tarea = _con_diferencias(t, luis)
    t.marcar_revisada(luis, id_tarea, ARROZ, "")
    _leer(id_tarea, ARROZ, 8)            # recontó y sigue faltando
    d = _difs(t, id_tarea)[0]
    assert (d.contado, d.estado) == (8.0, t.PENDIENTE)


def test_pedir_recuento_en_tarea_cerrada_se_rechaza(gente):
    t, _ana, luis = gente
    id_tarea = _con_diferencias(t, luis)
    t.cerrar(luis, id_tarea)
    with pytest.raises(ErrorDeAcceso, match="ya está cerrada"):
        t.pedir_recuento(luis, id_tarea, ARROZ)
    t.marcar_revisada(luis, id_tarea, ARROZ, "Cerrada y revisada")   # revisar sí se puede
    assert _difs(t, id_tarea)[0].estado == t.REVISADA


def test_admin_no_revisa_diferencias(gente):
    t, ana, luis = gente
    id_tarea = _con_diferencias(t, luis)
    for accion in (lambda: t.marcar_revisada(ana, id_tarea, ARROZ, ""), lambda: t.pedir_recuento(ana, id_tarea, ARROZ)):
        with pytest.raises(ErrorDeAcceso, match="permiso"):
            accion()


def test_revisar_diferencia_que_no_existe(gente):
    t, _ana, luis = gente
    with pytest.raises(ErrorDeAcceso, match="ya no existe"):
        t.marcar_revisada(luis, "TT-999", ARROZ, "")


# ------------------------------------------------------------------ correcciones de la revisión final
def test_id_de_tarea_no_se_corta_despues_de_999(tareas_db):
    assert tareas_db._id_tarea("T-", 7) == "T-007"
    assert tareas_db._id_tarea("T-", 1234) == "T-1234"


def test_validar_tarea_antes_de_enviar(tareas_db):
    v = tareas_db.validar_tarea
    assert v("Tarea", "ALM-01", "pedro", ["A1"], "") is None
    assert "nombre" in v("  ", "ALM-01", "pedro", ["A1"], "")
    assert "almacén" in v("Tarea", "", "pedro", ["A1"], "")
    assert "operador" in v("Tarea", "ALM-01", "", ["A1"], "")
    assert "al menos un producto" in v("Tarea", "ALM-01", "pedro", [], "")
    assert "500" in v("Tarea", "ALM-01", "pedro", ["A1"], "x" * 501)


def test_pedir_recuento_de_producto_fuera_de_la_tarea_se_rechaza(gente):
    t, _ana, luis = gente
    id_tarea = _con_diferencias(t, luis)
    _leer(id_tarea, AZUCAR, 4)                     # sobrante: no está en la lista de la tarea
    assert AZUCAR in [d.sku for d in _difs(t, id_tarea)]
    with pytest.raises(ErrorDeAcceso, match="no está en la lista de la tarea"):
        t.pedir_recuento(luis, id_tarea, AZUCAR)


def test_pedir_recuento_en_conteo_sin_operador_se_rechaza(gente):
    t, _ana, luis = gente
    id_tarea = _con_diferencias(t, luis)
    _sql("UPDATE conteos SET operador = NULL WHERE id_conteo = :c", c=id_tarea)
    with pytest.raises(ErrorDeAcceso, match="no está en la lista de la tarea"):
        t.pedir_recuento(luis, id_tarea, ARROZ)


def test_errores_de_la_tarea_dicen_por_que(gente):
    t, _ana, luis = gente
    id_tarea = _crear(t, luis)
    _leer(id_tarea, "7709990001234", 3)            # SKU desconocido
    assert t.errores(id_tarea) == [("7709990001234", "SKU_DESCONOCIDO")]



# ------------------------------------------------------------------ Fase 4: dañados y foto
def test_diferencia_y_avance_traen_danados_y_foto(gente):
    t, _ana, luis = gente
    _sql("UPDATE existencias_tst SET cantidad = 10 WHERE codigo_almacen = 'ALM-01' AND sku = :a", a=ARROZ)
    id_tarea = _crear(t, luis, skus=(ARROZ,))
    _leer(id_tarea, ARROZ, 7, nota="caja rota", danados="2", foto="tst-tareas-esc/1.jpg")
    d = _difs(t, id_tarea)[0]
    assert (d.danados, d.foto) == (2.0, "tst-tareas-esc/1.jpg")
    assert t.avance(id_tarea) == [(ARROZ, "Arroz 500 g", True, 7.0, "tst-tareas-esc/1.jpg")]


def test_recuento_sin_foto_no_hereda_la_foto_vieja(gente):
    t, _ana, luis = gente
    _sql("UPDATE existencias_tst SET cantidad = 10 WHERE codigo_almacen = 'ALM-01' AND sku = :a", a=ARROZ)
    id_tarea = _crear(t, luis, skus=(ARROZ,))
    _leer(id_tarea, ARROZ, 7, foto="tst-tareas-esc/vieja.jpg")
    _leer(id_tarea, ARROZ, 6)                         # recuento: la lectura vigente no tiene foto
    assert _difs(t, id_tarea)[0].foto == ""


def test_leer_foto_que_no_esta(tmp_path, monkeypatch):
    from app.views import foto
    monkeypatch.setenv("FOTOS_DIR", str(tmp_path))
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "1.jpg").write_bytes(b"\xff\xd8x")
    assert foto.leer_foto("a/1.jpg") == b"\xff\xd8x"
    with pytest.raises(ErrorDeAcceso, match="no está en la carpeta del PC"):
        foto.leer_foto("a/2.jpg")
    with pytest.raises(ErrorDeAcceso, match="no está en la carpeta del PC"):
        foto.leer_foto("../../etc/passwd")      # nunca sale de la carpeta de fotos
