"""Cuentas de operadores que llegan del móvil (mensaje ACCT): Store.sincronizar_cuenta."""

from btsync.store import EstadoCuenta
from conftest import OPERADOR_ACTIVO, connect


def _fila(usuario):
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT nombre, rol, estado, origen, clave_hash FROM usuarios WHERE usuario = :u", u=usuario)
        return cur.fetchone()
    finally:
        conn.close()


def test_sincronizar_cuenta_crea_pendiente(store):
    assert store.sincronizar_cuenta("tst-op-nuevo", "Nuevo Operador", "tst-dev-1") == EstadoCuenta("PENDIENTE", None, None)
    assert _fila("tst-op-nuevo") == ("Nuevo Operador", None, "PENDIENTE", "MOVIL", "-")


def test_sincronizar_cuenta_idempotente(store):
    store.sincronizar_cuenta("tst-op-nuevo", "Nuevo Operador", "tst-dev-1")
    assert store.sincronizar_cuenta("tst-op-nuevo", "Nuevo Operador", "tst-dev-1") == EstadoCuenta("PENDIENTE", None, None)
    assert store.sincronizar_cuenta(OPERADOR_ACTIVO, "x", "tst-dev-1") == EstadoCuenta("ACTIVO", "OPERADOR", None)


def test_devuelve_el_motivo_de_una_cuenta_suspendida(store):
    conn = connect()
    conn.cursor().execute("UPDATE usuarios SET estado = 'SUSPENDIDO', motivo = 'Vacaciones' WHERE usuario = :u", u=OPERADOR_ACTIVO)
    conn.commit()
    conn.close()
    assert store.sincronizar_cuenta(OPERADOR_ACTIVO, "x", "tst-dev-1") == EstadoCuenta("SUSPENDIDO", "OPERADOR", "Vacaciones")


def test_usuario_igual_a_cuenta_de_escritorio_se_rechaza(store):
    conn = connect()
    conn.cursor().execute("INSERT INTO usuarios (usuario, nombre, rol, clave_hash, estado) "
                          "VALUES ('tst-escritorio', 'Ana PC', 'ADMIN', 'hash', 'ACTIVO')")
    conn.commit()
    conn.close()
    assert store.sincronizar_cuenta("tst-escritorio", "Impostor", "tst-dev-1") == EstadoCuenta(
        "RECHAZADO", None, "Ese usuario ya existe en el PC")
    assert _fila("tst-escritorio") == ("Ana PC", "ADMIN", "ACTIVO", "ESCRITORIO", "hash")   # no se tocó


def test_cuenta_queda_vinculada_al_primer_telefono(store):
    assert store.sincronizar_cuenta("tst-op-nuevo", "Nuevo", "tst-dev-1").estado == "PENDIENTE"
    otro = store.sincronizar_cuenta("tst-op-nuevo", "Impostor", "tst-dev-2")
    assert otro.estado == "SUSPENDIDO" and "otro teléfono" in otro.motivo
    assert store.sincronizar_cuenta("tst-op-nuevo", "Nuevo", "tst-dev-1").estado == "PENDIENTE"   # el suyo sigue igual
    assert _fila("tst-op-nuevo")[0] == "Nuevo"


def test_operador_sin_permiso_de_bluetooth_no_sincroniza(store):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT nivel FROM permisos WHERE rol = 'OPERADOR' AND modulo = 'bluetooth'")
    antes = cur.fetchone()
    try:
        cur.execute("UPDATE permisos SET nivel = 'NINGUNO' WHERE rol = 'OPERADOR' AND modulo = 'bluetooth'")
        conn.commit()
        estado = store.sincronizar_cuenta(OPERADOR_ACTIVO, "x", "tst-dev-1")
        assert estado.estado == "SUSPENDIDO" and "permiso" in estado.motivo
    finally:
        if antes:
            cur.execute("UPDATE permisos SET nivel = :n WHERE rol = 'OPERADOR' AND modulo = 'bluetooth'", n=antes[0])
            conn.commit()
        conn.close()


def test_store_close_libera_la_conexion(store):
    store.sincronizar_cuenta(OPERADOR_ACTIVO, "x", "tst-dev-1")
    conexion = store._conn
    store.close()
    assert store._conn is None and not conexion.is_healthy()
    store.close()   # dos veces no falla
