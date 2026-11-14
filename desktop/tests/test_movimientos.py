"""Movimientos (entradas y salidas) y ajustes (Fase 3b)."""

import threading
from datetime import date, timedelta

import pytest

from app import db as dbq
from app.auth import INVENTARIO, ErrorDeAcceso
from conftest import staging

ARROZ, AZUCAR, JABON = "7701234000001", "7701234000002", "7701234000025"   # costo 2400, 3900, 2100
HOY = date.today()
T0 = 1731170400000
_seq = iter(range(200_000, 299_999))


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
    """Ana (ADMIN: consulta y aprueba ajustes), Luis (INVENTARIO). ARROZ = 100 en ALM-01."""
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    _sql("UPDATE existencias_tst SET cantidad = 100 WHERE sku = :s AND codigo_almacen = 'ALM-01'", s=ARROZ)
    return movimientos_db, ana, cuentas.iniciar_sesion("luis", "conteo2026")


# ------------------------------------------------------------------ es_critico (pura)
@pytest.mark.parametrize("antes, despues, costo, critico", [
    (100, 90, 1, True),          # 10 % exacto
    (100, 91, 1, False),         # 9 %
    (100, 110, 1, True),         # también hacia arriba
    (0, 1, 1, True),             # desde 0, cualquier cambio
    (0, 0, 1, False),
    (1000, 999, 200_000, True),  # 1 unidad de 200 000: el valor manda
    (1000, 999, 199_999, False),
])
def test_es_critico(movimientos_db, antes, despues, costo, critico):
    assert movimientos_db.es_critico(antes, despues, costo) is critico


# ------------------------------------------------------------------ entradas y salidas
def test_entrada_suma_y_queda_en_el_historial(gente):
    m, _ana, luis = gente
    m.registrar_entrada(luis, ARROZ, "ALM-01", 50, HOY, "Compra proveedor")
    assert _cantidad(ARROZ) == 150
    mov = m.listar()[0]
    assert (mov.tipo, mov.sku, mov.almacen, mov.cantidad, mov.antes, mov.despues, mov.observaciones, mov.responsable,
            mov.estado) == (m.ENTRADA, ARROZ, "ALM-01", 50.0, 100.0, 150.0, "Compra proveedor", "luis", m.APLICADO)
    assert mov.fecha.date() == HOY and mov.nombre_almacen == "Bodega Norte" and mov.producto == "Arroz 500 g"


def test_entrada_crea_la_fila_si_no_existia(gente):
    m, _ana, luis = gente
    assert _cantidad(ARROZ, "ALM-02") is None
    m.registrar_entrada(luis, ARROZ, "ALM-02", 5.5, HOY - timedelta(days=3), "")
    assert _cantidad(ARROZ, "ALM-02") == 5.5
    assert m.listar()[0].fecha.date() == HOY - timedelta(days=3)


def test_salida_resta_y_no_deja_negativo(gente):
    m, _ana, luis = gente
    m.registrar_salida(luis, ARROZ, "ALM-01", 30, HOY, "Venta", "Factura 12")
    assert _cantidad(ARROZ) == 70 and m.listar()[0].cantidad == -30.0 and m.listar()[0].motivo == "Venta"
    with pytest.raises(ErrorDeAcceso, match="Solo hay 70 en ese almacén"):
        m.registrar_salida(luis, ARROZ, "ALM-01", 71, HOY, "Venta", "")
    with pytest.raises(ErrorDeAcceso, match="Solo hay 0 en ese almacén"):
        m.registrar_salida(luis, ARROZ, "ALM-02", 1, HOY, "Venta", "")
    assert _cantidad(ARROZ) == 70


@pytest.mark.parametrize("cantidad, fecha, motivo, mensaje", [
    (0, HOY, "Venta", "mayor que 0"),
    (-2, HOY, "Venta", "mayor que 0"),
    (1.2345, HOY, "Venta", "3 decimales"),
    (1, HOY + timedelta(days=1), "Venta", "futura"),
    (1, HOY, "", "motivo"),
    (1, HOY, "Regalo", "motivo"),
])
def test_salida_rechaza_datos_invalidos(gente, cantidad, fecha, motivo, mensaje):
    m, _ana, luis = gente
    with pytest.raises(ErrorDeAcceso, match=mensaje):
        m.registrar_salida(luis, ARROZ, "ALM-01", cantidad, fecha, motivo, "")
    assert _cantidad(ARROZ) == 100 and m.listar() == []


def test_no_registra_en_almacen_inactivo_ni_producto_de_categoria_inactiva(gente):
    m, _ana, luis = gente
    _sql("UPDATE almacenes_tst SET activo = 'N' WHERE codigo = 'ALM-02'")
    with pytest.raises(ErrorDeAcceso, match="almacén ya no está activo"):
        m.registrar_entrada(luis, ARROZ, "ALM-02", 1, HOY, "")
    _sql("UPDATE categorias_tst SET activa = 'N' WHERE nombre = 'Aseo'")
    with pytest.raises(ErrorDeAcceso, match="categoría inactiva"):
        m.registrar_entrada(luis, JABON, "ALM-01", 1, HOY, "")


def test_admin_no_registra_entradas_ni_salidas(gente):
    m, ana, _luis = gente
    with pytest.raises(ErrorDeAcceso, match="permiso"):
        m.registrar_entrada(ana, ARROZ, "ALM-01", 1, HOY, "")
    with pytest.raises(ErrorDeAcceso, match="permiso"):
        m.registrar_salida(ana, ARROZ, "ALM-01", 1, HOY, "Venta", "")


def test_dos_salidas_a_la_vez_no_dejan_negativo(gente):
    m, _ana, luis = gente
    _sql("UPDATE existencias_tst SET cantidad = 10 WHERE sku = :s AND codigo_almacen = 'ALM-01'", s=ARROZ)
    barrera, resultados = threading.Barrier(2), []

    def salir():
        barrera.wait()
        try:
            m.registrar_salida(luis, ARROZ, "ALM-01", 7, HOY, "Venta", "")
            resultados.append("ok")
        except ErrorDeAcceso as exc:
            resultados.append(str(exc))
        finally:
            dbq.liberar_conexion()

    hilos = [threading.Thread(target=salir) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(30)
    assert sorted(resultados) == ["Solo hay 3 en ese almacén.", "ok"]
    assert _cantidad(ARROZ) == 3


# ------------------------------------------------------------------ ajustes
def test_ajuste_no_critico_se_aplica(gente):
    m, _ana, luis = gente
    assert m.solicitar_ajuste(luis, ARROZ, "ALM-01", 95, "Merma") == m.APLICADO   # 5 %, 12 000
    assert _cantidad(ARROZ) == 95
    a = m.listar()[0]
    assert (a.tipo, a.antes, a.despues, a.cantidad, a.motivo, a.estado) == (m.AJUSTE, 100.0, 95.0, -5.0, "Merma", m.APLICADO)


def test_ajuste_critico_espera_y_al_aprobar_aplica_el_delta(gente):
    m, ana, luis = gente
    assert m.solicitar_ajuste(luis, ARROZ, "ALM-01", 40, "Conteo") == m.PENDIENTE   # -60: 60 %
    assert _cantidad(ARROZ) == 100
    m.registrar_entrada(luis, ARROZ, "ALM-01", 10, HOY, "")                         # mientras tanto: 110
    pendiente = next(x for x in m.listar() if x.tipo == m.AJUSTE)
    m.aprobar(ana, pendiente.id)
    assert _cantidad(ARROZ) == 50                                                   # 110 - 60
    hecho = next(x for x in m.listar() if x.id == pendiente.id)
    # El historial conserva lo que se pidió (100 → 40, −60); la existencia recibió el delta.
    assert (hecho.estado, hecho.resuelto_por, hecho.antes, hecho.despues, hecho.cantidad) == \
        (m.APLICADO, "ana.gomez", 100.0, 40.0, -60.0)
    with pytest.raises(ErrorDeAcceso, match="ya fue resuelto"):
        m.aprobar(ana, pendiente.id)
    assert _cantidad(ARROZ) == 50


def test_aprobar_no_deja_negativo(gente):
    m, ana, luis = gente
    m.solicitar_ajuste(luis, ARROZ, "ALM-01", 0, "Robo")                            # -100: pendiente
    m.registrar_salida(luis, ARROZ, "ALM-01", 50, HOY, "Venta", "")
    pendiente = next(x for x in m.listar() if x.tipo == m.AJUSTE)
    with pytest.raises(ErrorDeAcceso, match="quedaría en"):
        m.aprobar(ana, pendiente.id)
    assert _cantidad(ARROZ) == 50


def test_rechazar_exige_motivo_y_no_toca_existencia(gente):
    m, ana, luis = gente
    m.solicitar_ajuste(luis, ARROZ, "ALM-01", 10, "Conteo")
    pendiente = m.listar()[0]
    with pytest.raises(ErrorDeAcceso, match="motivo"):
        m.rechazar(ana, pendiente.id, "  ")
    m.rechazar(ana, pendiente.id, "Recontar antes")
    r = m.listar()[0]
    assert (r.estado, r.motivo_rechazo, r.resuelto_por) == (m.RECHAZADO, "Recontar antes", "ana.gomez")
    assert _cantidad(ARROZ) == 100
    with pytest.raises(ErrorDeAcceso, match="ya fue resuelto"):
        m.rechazar(ana, pendiente.id, "otra vez")


def test_quien_solicita_y_quien_aprueba(gente):
    m, ana, luis = gente
    with pytest.raises(ErrorDeAcceso, match="Administrador no"):
        m.solicitar_ajuste(ana, ARROZ, "ALM-01", 10, "Conteo")
    m.solicitar_ajuste(luis, ARROZ, "ALM-01", 10, "Conteo")
    pendiente = m.listar()[0]
    with pytest.raises(ErrorDeAcceso, match="Administrador"):
        m.aprobar(luis, pendiente.id)
    _sql("UPDATE usuarios_tst SET rol = 'INVENTARIO' WHERE usuario = 'ana.gomez'")   # degradada a mitad de sesión
    with pytest.raises(ErrorDeAcceso):
        m.aprobar(ana, pendiente.id)
    with pytest.raises(ErrorDeAcceso, match="ya no existe"):
        _sql("UPDATE usuarios_tst SET rol = 'ADMIN' WHERE usuario = 'ana.gomez'")
        m.aprobar(ana, 987654321)


def test_ajuste_exige_motivo_y_cantidad_valida(gente):
    m, _ana, luis = gente
    with pytest.raises(ErrorDeAcceso, match="motivo"):
        m.solicitar_ajuste(luis, ARROZ, "ALM-01", 95, "")
    with pytest.raises(ErrorDeAcceso, match="0 o más"):
        m.solicitar_ajuste(luis, ARROZ, "ALM-01", -1, "Merma")
    with pytest.raises(ErrorDeAcceso, match="no cambia"):
        m.solicitar_ajuste(luis, ARROZ, "ALM-01", 100, "Merma")


# ------------------------------------------------------------------ desde una diferencia
def _tarea_con_diferencia(luis):
    from app import tareas
    _sql("INSERT INTO usuarios_tst (usuario, nombre, rol, clave_hash, estado, origen) "
         "VALUES ('pedro', 'Pedro Ruiz', 'OPERADOR', '-', 'ACTIVO', 'MOVIL')")
    id_tarea = tareas.crear_tarea(luis, "Tarea", "ALM-01", "pedro", [ARROZ], "")   # sistema 100
    with dbq._conexion() as conn:
        n = next(_seq)
        staging(conn, "tst-tareas-esc", n, T0 + n * 1000, id_tarea, ARROZ, 97)
        conn.cursor().callproc("pkg_batch.procesar_pendientes")
    return tareas, id_tarea


def test_propuesta_y_ajuste_desde_una_diferencia(gente):
    m, ana, luis = gente
    tareas, id_tarea = _tarea_con_diferencia(luis)
    m.registrar_salida(luis, ARROZ, "ALM-01", 10, HOY, "Venta", "")                 # ahora hay 90
    assert m.propuesta_desde_diferencia(id_tarea, ARROZ) == ("ALM-01", 90.0, 87.0)  # 90 + (97 - 100)
    assert m.solicitar_ajuste(luis, ARROZ, "ALM-01", 87, f"Conteo {id_tarea}", id_conteo=id_tarea) == m.APLICADO
    d = next(x for x in tareas.listar_diferencias() if x.id_conteo == id_tarea)
    assert d.estado == tareas.AJUSTADA and tareas.NOMBRE_REVISION[d.estado] == "Ajustada"


def test_diferencia_con_ajuste_pendiente(gente):
    m, ana, luis = gente
    tareas, id_tarea = _tarea_con_diferencia(luis)
    m.solicitar_ajuste(luis, ARROZ, "ALM-01", 50, f"Conteo {id_tarea}", id_conteo=id_tarea)   # crítico
    d = next(x for x in tareas.listar_diferencias() if x.id_conteo == id_tarea)
    assert d.estado == tareas.AJUSTE_PENDIENTE
    m.rechazar(ana, m.listar()[0].id, "No")
    d = next(x for x in tareas.listar_diferencias() if x.id_conteo == id_tarea)
    assert d.estado == tareas.PENDIENTE                                              # rechazado: vuelve a pendiente


# ------------------------------------------------------------------ correcciones de la revisión final
def test_no_hay_dos_ajustes_pendientes_del_mismo_producto(gente):
    m, _ana, luis = gente
    m.solicitar_ajuste(luis, ARROZ, "ALM-01", 50, "Conteo")                       # pendiente
    with pytest.raises(ErrorDeAcceso, match="Ya hay un ajuste pendiente"):
        m.solicitar_ajuste(luis, ARROZ, "ALM-01", 50, "Otra vez")
    _sql("UPDATE existencias_tst SET cantidad = 100 WHERE sku = :s AND codigo_almacen = 'ALM-01'", s=AZUCAR)
    assert m.solicitar_ajuste(luis, AZUCAR, "ALM-01", 99, "Merma") == m.APLICADO    # otro producto: sí


def test_una_diferencia_no_se_ajusta_dos_veces(gente):
    m, ana, luis = gente
    _tareas, id_tarea = _tarea_con_diferencia(luis)
    m.solicitar_ajuste(luis, ARROZ, "ALM-01", 97, "Conteo", id_conteo=id_tarea)   # aplicado
    with pytest.raises(ErrorDeAcceso, match="ya tiene un ajuste"):
        m.solicitar_ajuste(luis, ARROZ, "ALM-01", 94, "Conteo", id_conteo=id_tarea)


def test_diferencia_con_ajuste_rechazado_se_puede_volver_a_ajustar(gente):
    m, ana, luis = gente
    _tareas, id_tarea = _tarea_con_diferencia(luis)
    m.solicitar_ajuste(luis, ARROZ, "ALM-01", 40, "Conteo", id_conteo=id_tarea)   # crítico
    m.rechazar(ana, m.listar()[0].id, "No")
    assert m.solicitar_ajuste(luis, ARROZ, "ALM-01", 97, "Conteo", id_conteo=id_tarea) == m.APLICADO


def test_ajuste_pendiente_no_crea_existencia(gente):
    m, ana, luis = gente
    assert m.solicitar_ajuste(luis, ARROZ, "ALM-02", 5, "Encontrado") == m.PENDIENTE   # desde 0: crítico
    assert _cantidad(ARROZ, "ALM-02") is None
    m.aprobar(ana, m.listar()[0].id)
    assert _cantidad(ARROZ, "ALM-02") == 5


def test_existencia_y_costo_para_el_dialogo(gente):
    m, _ana, _luis = gente
    assert m.existencia_y_costo(ARROZ, "ALM-01") == (100.0, 2400.0)
    assert m.existencia_y_costo(ARROZ, "ALM-02") == (0.0, 2400.0)
