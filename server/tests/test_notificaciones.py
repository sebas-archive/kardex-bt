"""Notificaciones (avisos de que algo pasó; no son solicitudes): modelo y eventos del lado del servidor."""

import pytest

from btsync import notificaciones, respaldo
from conftest import OPERADOR_ACTIVO, connect, staging
from test_controller import FakeStore, FakeTransport, ctl, started, wait_for  # noqa: F401
from test_session import UUID, acct, end, hello, inicio, rec, run


def filas():
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT tipo, texto, seccion, rol, usuario FROM notificaciones_tst ORDER BY id")
        return cur.fetchall()
    finally:
        conn.close()


def test_crear_con_rol_y_con_usuario_y_clave_unica():
    conn = connect()
    cur = conn.cursor()
    assert notificaciones.crear(cur, "PRUEBA", "Para todos los admin", "Ajustes", rol="ADMIN")
    assert notificaciones.crear(cur, "PRUEBA", "Solo para luis", "", usuario="luis", clave="k1")
    assert not notificaciones.crear(cur, "PRUEBA", "Repetida", "", usuario="luis", clave="k1")
    conn.commit()
    conn.close()
    assert filas() == [("PRUEBA", "Para todos los admin", "Ajustes", "ADMIN", None),
                       ("PRUEBA", "Solo para luis", None, None, "luis")]


def test_una_sincronizacion_completa_notifica_a_admin_e_inventario(store, db):
    from btsync.controller import LISTO, SyncController

    c = SyncController(FakeTransport(), store, lambda s: None)
    c.start()
    try:
        conn = c.transport.connect()
        conn.feed(hello(UUID), acct(), rec(1), rec(2), end(2))
        wait_for(lambda: c.status()["estado"] == LISTO, timeout=15, what="LISTO")
    finally:
        c.cancel()
    sync = [f for f in filas() if f[0] == "SINCRONIZACION"]
    assert sorted(f[3] for f in sync) == ["ADMIN", "INVENTARIO"]
    # El conteo es continuo: las dos lecturas válidas se procesan y el aviso no reporta errores.
    assert all(f[1] == "Sincronización recibida: Bodega Test, 2 lecturas" and f[2] == "Sincronización"
               for f in sync)


def test_si_notificar_falla_la_sincronizacion_termina_igual():
    from btsync.controller import LISTO, SyncController

    class Rota(FakeStore):
        def notificar_sincronizacion(self, errores):
            raise RuntimeError("ORA-00942: la tabla no existe")

    c = SyncController(FakeTransport(), Rota(), lambda s: None)
    c.start()
    try:
        conn = c.transport.connect()
        conn.feed(hello(), acct(), rec(1), end(1))
        wait_for(lambda: c.status()["estado"] == LISTO, what="LISTO pese al fallo")
    finally:
        c.cancel()


def test_una_cuenta_nueva_del_movil_notifica_la_solicitud(store):
    store.sincronizar_cuenta("tst-nuevo-op", "Pedro Ruiz", "tst-tel-nuevo")
    store.rollback()
    conn = connect()
    conn.cursor().execute("DELETE FROM usuarios WHERE usuario = 'tst-nuevo-op'")
    conn.commit()
    conn.close()
    assert ("SOLICITUD", "Nueva solicitud de cuenta: Pedro Ruiz", "Solicitudes", "ADMIN", None) in filas()


def test_el_respaldo_automatico_notifica_lo_creado_y_el_fallo(tmp_path, monkeypatch):
    from datetime import datetime

    monkeypatch.setenv("RESPALDOS_DIR", str(tmp_path / "r"))
    monkeypatch.setenv("FOTOS_DIR", str(tmp_path / "f"))
    monkeypatch.setattr(respaldo, "tablas_de_la_app", lambda cur: [])
    monkeypatch.setattr(respaldo, "AUDITORIA", "auditoria_sin_tabla_tst")
    respaldo.Automatico(connect, reloj=lambda: datetime(2026, 11, 14, 23, 30))()
    creado = [f for f in filas() if f[0] == "RESPALDO"]
    assert len(creado) == 1 and creado[0][1].startswith("Respaldo automático creado: respaldo-20261114-233000-auto")
    monkeypatch.setattr(respaldo, "crear", lambda *a, **k: (_ for _ in ()).throw(OSError(28, "No space left on device")))
    with pytest.raises(OSError):
        respaldo.Automatico(connect, reloj=lambda: datetime(2026, 11, 15, 23, 30))()
    fallo = [f for f in filas() if f[0] == "RESPALDO_FALLO"]
    assert len(fallo) == 1 and fallo[0][1].startswith("Falló el respaldo automático:") and fallo[0][3] == "ADMIN"


# --------------------------------------------------- SKU nuevo: aviso en la campana
def test_avisar_nuevos_sku_crea_una_por_lectura_y_no_duplica():
    conn = connect()
    try:
        cur = conn.cursor()
        assert notificaciones.avisar_nuevos_sku(cur, [(41, "khs"), (42, "ZZ9")]) == 2
        conn.commit()
        assert notificaciones.avisar_nuevos_sku(cur, [(41, "khs"), (42, "ZZ9")]) == 0   # clave repetida
        conn.commit()
    finally:
        conn.close()
    avisos = [f for f in filas() if f[0] == "NUEVO_SKU"]
    assert len(avisos) == 2
    assert avisos == [
        ("NUEVO_SKU", "Nuevo SKU khs: decide «Crear y procesar» o «No crear» en Sincronización.",
         "Sincronización", "ADMIN", None),
        ("NUEVO_SKU", "Nuevo SKU ZZ9: decide «Crear y procesar» o «No crear» en Sincronización.",
         "Sincronización", "ADMIN", None),
    ]


def test_avisar_nuevos_sku_acepta_las_filas_del_escritorio():
    from types import SimpleNamespace

    conn = connect()
    try:
        cur = conn.cursor()
        assert notificaciones.avisar_nuevos_sku(cur, [SimpleNamespace(id_transito=7, sku="KHS")]) == 1
        conn.commit()
    finally:
        conn.close()
    assert [f[1] for f in filas() if f[0] == "NUEVO_SKU"] == [
        "Nuevo SKU KHS: decide «Crear y procesar» o «No crear» en Sincronización."]


def test_run_batch_deja_en_la_campana_los_sku_nuevos_pendientes(escenario, store, db):
    """Cubre «el móvil sincronizó con la app cerrada»: el batch deja el aviso sin depender del escritorio."""
    staging(db, "tst-notif", 1, 1731170400000, "ACTUAL", "zz9", 4)
    store.run_batch("SYNC")
    avisos = [f for f in filas() if f[0] == "NUEVO_SKU"]
    assert len(avisos) == 1
    assert avisos[0][1] == "Nuevo SKU zz9: decide «Crear y procesar» o «No crear» en Sincronización."
    assert avisos[0][2:] == ("Sincronización", "ADMIN", None)
    store.run_batch("SYNC")                    # el SKU sigue pendiente: la clave evita el duplicado
    assert len([f for f in filas() if f[0] == "NUEVO_SKU"]) == 1

