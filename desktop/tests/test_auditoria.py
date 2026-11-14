"""Auditoría (Fase 4): toda acción que cambia datos, y todo inicio de sesión, deja una fila con quién, qué y cuándo."""

from datetime import date

import pytest

from app import db as dbq
from app.auth import ADMIN, INVENTARIO, ErrorDeAcceso

ARROZ = "7701234000001"


def _sql(sql, **binds):
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute(sql, binds)
        filas = cur.fetchall() if cur.description else None
        conn.commit()
        return filas


def _ultima(auditoria_db, quien):
    return [(e.usuario, e.modulo, e.accion, e.detalle) for e in auditoria_db.listar(quien)][0]


@pytest.fixture
def gente(cuentas, movimientos_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    _sql("INSERT INTO usuarios_tst (usuario, nombre, rol, clave_hash, estado, origen) "
         "VALUES ('pedro', 'Pedro Ruiz', 'OPERADOR', '-', 'ACTIVO', 'MOVIL')")
    return cuentas, ana, cuentas.iniciar_sesion("luis", "conteo2026")


def test_inicio_de_sesion_correcto_y_fallido(gente, auditoria_db):
    cuentas, ana, _luis = gente
    with pytest.raises(ErrorDeAcceso):
        cuentas.iniciar_sesion("luis", "mala-clave")
    with pytest.raises(ErrorDeAcceso):
        cuentas.iniciar_sesion("nadie", "x")
    acciones = [(e.usuario, e.accion, e.detalle) for e in auditoria_db.listar(ana)]
    assert ("nadie", "Inicio de sesión fallido", "usuario inexistente") in acciones
    assert ("luis", "Inicio de sesión fallido", "contraseña incorrecta") in acciones
    assert ("luis", "Inicio de sesión", "") in acciones


def test_cuentas_y_permisos(gente, auditoria_db, permisos_db):
    cuentas, ana, _luis = gente
    cuentas.registrar("marta", "Marta Paz", "conteo2026", "conteo2026")
    cuentas.rechazar(ana, "marta", "No trabaja aquí")
    assert _ultima(auditoria_db, ana) == ("ana.gomez", "usuarios", "Rechazó cuenta", "marta — «No trabaja aquí»")
    cuentas.suspender(ana, "luis", "Vacaciones")
    assert _ultima(auditoria_db, ana) == ("ana.gomez", "usuarios", "Suspendió cuenta", "luis — «Vacaciones»")
    cuentas.reactivar(ana, "luis")
    assert _ultima(auditoria_db, ana)[2:] == ("Reactivó cuenta", "luis")
    permisos_db.guardar(ana, INVENTARIO, "movimientos", "CONSULTA")
    assert _ultima(auditoria_db, ana) == ("ana.gomez", "permisos", "Cambió permiso",
                                          "Inventario · Movimientos: Gestión → Consulta")


def test_maestros_tareas_y_diferencias(gente, auditoria_db, maestros_db):
    from app import tareas
    _c, ana, luis = gente
    maestros_db.crear_categoria(luis, "Tst Congelados")
    assert _ultima(auditoria_db, ana) == ("luis", "categorias", "Creó categoría", "Tst Congelados")
    maestros_db.activar_almacen(luis, "ALM-02", False)
    assert _ultima(auditoria_db, ana)[2:] == ("Desactivó almacén", "ALM-02")
    id_tarea = tareas.crear_tarea(luis, "Bodega", "ALM-01", "pedro", [ARROZ], "")
    assert _ultima(auditoria_db, ana) == ("luis", "tareas", "Creó tarea", f"{id_tarea} · Bodega → pedro (1 productos)")
    tareas.cerrar(luis, id_tarea)
    assert _ultima(auditoria_db, ana)[2:] == ("Cerró tarea", id_tarea)


def test_movimientos_y_ajustes(gente, auditoria_db, movimientos_db):
    _c, ana, luis = gente
    m = movimientos_db
    _sql("UPDATE existencias_tst SET cantidad = 100 WHERE sku = :s AND codigo_almacen = 'ALM-01'", s=ARROZ)
    m.registrar_salida(luis, ARROZ, "ALM-01", 3, date.today(), "Venta", "")
    assert _ultima(auditoria_db, ana) == ("luis", "movimientos", "Registró salida",
                                          "Arroz 500 g (7701234000001) · ALM-01: −3 (Venta)")
    m.solicitar_ajuste(luis, ARROZ, "ALM-01", 40, "Conteo")
    assert _ultima(auditoria_db, ana)[1:] == ("ajustes", "Solicitó ajuste",
                                              "Arroz 500 g (7701234000001) · ALM-01: 97 → 40 (pendiente)")
    m.aprobar(ana, m.listar()[0].id)
    assert _ultima(auditoria_db, ana)[:3] == ("ana.gomez", "ajustes", "Aprobó ajuste")


def test_accion_rechazada_no_deja_fila(gente, auditoria_db, movimientos_db):
    _c, ana, luis = gente
    antes = len(auditoria_db.listar(ana))
    with pytest.raises(ErrorDeAcceso):
        movimientos_db.registrar_salida(luis, ARROZ, "ALM-01", 10_000, date.today(), "Venta", "")
    with pytest.raises(ErrorDeAcceso):
        movimientos_db.registrar_entrada(ana, ARROZ, "ALM-01", 1, date.today(), "")   # el Administrador no registra
    assert len(auditoria_db.listar(ana)) == antes


def test_inventario_solo_ve_la_operacion(gente, auditoria_db, maestros_db):
    cuentas, ana, luis = gente
    cuentas.suspender(ana, "pedro", "Prueba")
    maestros_db.crear_categoria(luis, "Tst Congelados")
    modulos = {e.modulo for e in auditoria_db.listar(luis)}
    assert "categorias" in modulos and not modulos & {"usuarios", "permisos", "acceso"}
    assert {"usuarios", "categorias"} <= {e.modulo for e in auditoria_db.listar(ana)}
    e = auditoria_db.listar(ana)[0]
    assert e.nombre == "Luis Ortiz" and e.fecha is not None
