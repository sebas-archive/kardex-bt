"""Categorías, almacenes y existencias (Fase 2): modelo, migración y permisos."""

import pytest

from app import db as dbq
from app.auth import INVENTARIO, ErrorDeAcceso


@pytest.fixture
def gente(cuentas, maestros_db):
    """Ana (ADMIN, solo consulta categorías) y Luis (INVENTARIO, las gestiona)."""
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    return maestros_db, ana, cuentas.iniciar_sesion("luis", "conteo2026")


def _sql(sql, **binds):
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute(sql, binds)
        filas = cur.fetchall() if cur.description else None
        conn.commit()
        return filas


def test_migrar_siembra_desde_los_datos_y_es_idempotente(maestros_db):
    categorias = {c.nombre for c in maestros_db.listar_categorias()}
    distintas = {f[0] for f in _sql("SELECT DISTINCT categoria FROM productos")}
    assert categorias == distintas and all(c.activa for c in maestros_db.listar_categorias())
    assert [(a.codigo, a.nombre) for a in maestros_db.listar_almacenes()] == [("ALM-01", "Bodega Norte"), ("ALM-02", "Bodega Sur")]
    total = _sql("SELECT COUNT(*) FROM productos")[0][0]
    existencias = maestros_db.listar_existencias()
    assert len(existencias) == total and {e.codigo_almacen for e in existencias} == {"ALM-01"}
    _sql("UPDATE almacenes_tst SET nombre = 'Editado' WHERE codigo = 'ALM-02'")
    maestros_db.migrar()                                   # no pisa lo editado ni duplica
    assert [(a.codigo, a.nombre) for a in maestros_db.listar_almacenes()] == [("ALM-01", "Bodega Norte"), ("ALM-02", "Editado")]
    assert len(maestros_db.listar_existencias()) == total


def test_categoria_cuenta_sus_productos(maestros_db):
    abarrotes = next(c for c in maestros_db.listar_categorias() if c.nombre == "Abarrotes")
    assert abarrotes.productos == _sql("SELECT COUNT(*) FROM productos WHERE categoria = 'Abarrotes'")[0][0]


def test_crear_renombrar_y_duplicar_categoria(gente):
    m, _ana, luis = gente
    m.crear_categoria(luis, "  Tst Congelados ")
    assert "Tst Congelados" in [c.nombre for c in m.listar_categorias()]
    with pytest.raises(ErrorDeAcceso, match="ya existe"):
        m.crear_categoria(luis, "tst congelados")             # sin distinguir mayúsculas
    with pytest.raises(ErrorDeAcceso, match="nombre"):
        m.crear_categoria(luis, "   ")
    m.renombrar_categoria(luis, "Tst Congelados", "Tst Helados")
    assert "Tst Helados" in [c.nombre for c in m.listar_categorias()]
    with pytest.raises(ErrorDeAcceso, match="ya existe"):
        m.renombrar_categoria(luis, "Tst Helados", "Abarrotes")


def test_renombrar_actualiza_los_productos(gente, monkeypatch):
    m, _ana, luis = gente
    sku = _sql("SELECT MIN(sku) FROM productos WHERE categoria = 'Abarrotes'")[0][0]
    try:
        m.renombrar_categoria(luis, "Abarrotes", "Tst Abarrotes")
        assert _sql("SELECT categoria FROM productos WHERE sku = :s", s=sku)[0][0] == "Tst Abarrotes"
        assert next(c for c in m.listar_categorias() if c.nombre == "Tst Abarrotes").productos > 0
    finally:
        _sql("UPDATE productos SET categoria = 'Abarrotes' WHERE categoria = 'Tst Abarrotes'")


def test_activar_y_desactivar(gente):
    m, _ana, luis = gente
    m.activar_categoria(luis, "Abarrotes", False)
    assert not next(c for c in m.listar_categorias() if c.nombre == "Abarrotes").activa
    m.activar_almacen(luis, "ALM-02", False)
    assert not next(a for a in m.listar_almacenes() if a.codigo == "ALM-02").activo
    m.activar_almacen(luis, "ALM-02", True)
    assert next(a for a in m.listar_almacenes() if a.codigo == "ALM-02").activo


def test_crear_editar_y_validar_almacen(gente):
    m, _ana, luis = gente
    m.crear_almacen(luis, " alm-09 ", "Tst Bodega", "Calle 1")
    assert ("ALM-09", "Tst Bodega", "Calle 1", True) in [(a.codigo, a.nombre, a.ubicacion, a.activo) for a in m.listar_almacenes()]
    with pytest.raises(ErrorDeAcceso, match="ya existe"):
        m.crear_almacen(luis, "ALM-09", "Otra", "")
    for codigo, nombre in (("", "X"), ("ALM-10", "  "), ("CODIGO-MUY-LARGO-DE-MAS-21", "X")):
        with pytest.raises(ErrorDeAcceso):
            m.crear_almacen(luis, codigo, nombre, "")
    m.editar_almacen(luis, "ALM-09", "Tst Bodega 2", "")
    assert ("ALM-09", "Tst Bodega 2", "") in [(a.codigo, a.nombre, a.ubicacion) for a in m.listar_almacenes()]


def test_estado_de_las_existencias(maestros_db):
    sku_cero, sku_bajo, sku_ok = [f[0] for f in _sql("SELECT sku FROM (SELECT sku FROM productos ORDER BY sku) WHERE ROWNUM <= 3")]
    _sql("UPDATE existencias_tst SET cantidad = 0 WHERE sku = :s", s=sku_cero)
    _sql("UPDATE existencias_tst SET cantidad = 9 WHERE sku = :s", s=sku_bajo)     # mínimo 10
    _sql("UPDATE existencias_tst SET cantidad = 10 WHERE sku = :s", s=sku_ok)
    estados = {e.sku: e.estado for e in maestros_db.listar_existencias()}
    assert (estados[sku_cero], estados[sku_bajo], estados[sku_ok]) == ("AGOTADO", "STOCK_BAJO", "DISPONIBLE")


def test_sin_fila_no_aparece_en_ese_almacen(maestros_db):
    assert not [e for e in maestros_db.listar_existencias() if e.codigo_almacen == "ALM-02"]


def test_admin_solo_consulta_categorias(gente):
    m, ana, _luis = gente
    for accion in (lambda: m.crear_categoria(ana, "Tst X"), lambda: m.activar_almacen(ana, "ALM-01", False),
                   lambda: m.crear_almacen(ana, "ALM-77", "X", "")):
        with pytest.raises(ErrorDeAcceso, match="permiso"):
            accion()


# ------------------------------------------------------------------ correcciones de la revisión final
def test_carrera_al_crear_categoria_da_ya_existe(gente, monkeypatch):
    m, _ana, luis = gente
    monkeypatch.setattr(m, "_categoria_existe", lambda *a, **k: False)   # el otro usuario ganó entre el SELECT y el INSERT
    for nombre in ("Abarrotes", "ABARROTES"):                             # mismo nombre y solo cambio de mayúsculas
        with pytest.raises(ErrorDeAcceso, match="ya existe"):
            m.crear_categoria(luis, nombre)
    with pytest.raises(ErrorDeAcceso, match="ya existe"):
        m.renombrar_categoria(luis, "Aseo", "abarrotes")


def test_carrera_al_crear_almacen_da_ya_existe(gente, monkeypatch):
    m, _ana, luis = gente
    monkeypatch.setattr(m, "_almacen_existe", lambda *a, **k: False)
    with pytest.raises(ErrorDeAcceso, match="ya existe"):
        m.crear_almacen(luis, "ALM-01", "Repetido", "")


@pytest.mark.parametrize("accion", ["activar_categoria", "editar_almacen", "activar_almacen"])
def test_accion_sobre_fila_que_ya_no_existe_avisa(gente, accion):
    m, _ana, luis = gente
    llamada = {"activar_categoria": lambda: m.activar_categoria(luis, "No Existe", False),
               "editar_almacen": lambda: m.editar_almacen(luis, "ALM-99", "X", ""),
               "activar_almacen": lambda: m.activar_almacen(luis, "ALM-99", False)}[accion]
    with pytest.raises(ErrorDeAcceso, match="ya no existe"):
        llamada()


def test_admin_no_escribe_con_ninguna_funcion(gente):
    m, ana, _luis = gente
    for accion in (lambda: m.renombrar_categoria(ana, "Aseo", "Tst Y"), lambda: m.activar_categoria(ana, "Aseo", False),
                   lambda: m.editar_almacen(ana, "ALM-01", "X", "")):
        with pytest.raises(ErrorDeAcceso, match="permiso"):
            accion()


# ------------------------------------------------------------------ pendientes de la Fase 2
def test_listar_solo_activos(gente):
    m, _ana, luis = gente
    m.activar_almacen(luis, "ALM-02", False)
    m.activar_categoria(luis, "Aseo", False)
    assert [a.codigo for a in m.listar_almacenes(solo_activos=True)] == ["ALM-01"]
    assert "Aseo" not in [c.nombre for c in m.listar_categorias(solo_activas=True)]
    assert "Aseo" in [c.nombre for c in m.listar_categorias()]


def test_existencia_sabe_si_su_almacen_y_categoria_estan_activos(gente):
    m, _ana, luis = gente
    m.activar_categoria(luis, "Aseo", False)
    m.activar_almacen(luis, "ALM-01", False)
    e = next(x for x in m.listar_existencias() if x.categoria == "Aseo")
    assert (e.almacen_activo, e.categoria_activa) == (False, False)


def test_migrar_aguanta_otro_escritorio_que_ya_creo_todo(maestros_db, monkeypatch):
    """Dos escritorios arrancan a la vez: el segundo ve «no existe» y al crear ya existe. No debe caerse ni duplicar."""
    antes = len(maestros_db.listar_existencias())
    monkeypatch.setattr(maestros_db, "_existe", lambda *a: False)
    monkeypatch.setattr(maestros_db, "_hay_columna", lambda *a: False)
    monkeypatch.setattr(maestros_db, "_hay_indice", lambda *a: False)
    maestros_db.migrar()
    assert len(maestros_db.listar_existencias()) == antes


def test_ddl_tolerante_ignora_lo_que_ya_existe_y_no_lo_demas():
    with dbq._conexion() as conn:
        cur = conn.cursor()
        dbq.ddl_tolerante(cur, "CREATE TABLE productos (x NUMBER)")           # ORA-00955: ya existe
        dbq.ddl_tolerante(cur, "ALTER TABLE productos ADD (nombre VARCHAR2(5))")   # ORA-01430: columna ya existe
        with pytest.raises(Exception, match="ORA-00942"):
            dbq.ddl_tolerante(cur, "ALTER TABLE no_existe_tabla ADD (x NUMBER)")
