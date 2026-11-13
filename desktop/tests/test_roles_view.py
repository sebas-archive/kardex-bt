"""Vista «Roles y permisos»: la matriz editable."""

from app.auth import ADMIN, INVENTARIO, OPERADOR, Sesion
from app.permisos import CONSULTA, GESTION
from app.views.roles import RolesView

ANA = Sesion("ana.gomez", "Ana Gómez", ADMIN)


def _vista(qtbot, permisos_db):
    vista = RolesView()
    qtbot.addWidget(vista)
    vista.set_sesion(ANA)
    from app import auth
    with __import__("app.db", fromlist=["db"])._conexion() as conn:   # Ana existe y está ACTIVO: guardar lo comprueba en vivo
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {auth.TABLA} WHERE usuario = 'ana.gomez'")
        cur.execute(f"INSERT INTO {auth.TABLA} (usuario, nombre, rol, clave_hash, estado) VALUES ('ana.gomez', 'Ana', 'ADMIN', 'x', 'ACTIVO')")
        conn.commit()
    qtbot.waitUntil(lambda: vista.combo(OPERADOR, "tareas") is not None, timeout=5000)
    return vista


def test_roles_muestra_la_matriz(qtbot, cuentas, permisos_db):
    vista = _vista(qtbot, permisos_db)
    assert vista.combo(OPERADOR, "tareas").currentData() == GESTION
    assert vista.combo(INVENTARIO, "usuarios").currentData() == "NINGUNO"
    assert vista.tabla.rowCount() == len(permisos_db.MODULOS)


def test_roles_celda_intocable_deshabilitada(qtbot, cuentas, permisos_db):
    vista = _vista(qtbot, permisos_db)
    for modulo in ("usuarios", "solicitudes", "permisos"):
        assert not vista.combo(ADMIN, modulo).isEnabled()
    assert vista.combo(ADMIN, "dashboard").isEnabled()


def test_roles_cambiar_un_combo_guarda_en_oracle(qtbot, cuentas, permisos_db):
    vista = _vista(qtbot, permisos_db)
    combo = vista.combo(INVENTARIO, "configuracion")
    combo.setCurrentIndex(combo.findData(CONSULTA))
    qtbot.waitUntil(lambda: permisos_db.nivel(INVENTARIO, "configuracion") == CONSULTA, timeout=5000)


def test_roles_sin_permiso_no_consulta(qtbot, permisos_db):
    vista = RolesView()
    qtbot.addWidget(vista)
    vista.set_sesion(Sesion("luis", "Luis Ortiz", INVENTARIO))
    qtbot.wait(300)
    assert vista.tabla.rowCount() == 0


def test_roles_modulos_aun_no_disponibles_deshabilitados(qtbot, cuentas, permisos_db):
    vista = _vista(qtbot, permisos_db)
    fila = [clave for clave, _ in permisos_db.MODULOS].index("respaldos")
    assert "próximamente" in vista.tabla.item(fila, 0).text()
    assert not vista.combo(INVENTARIO, "respaldos").isEnabled()
    assert vista.combo(INVENTARIO, "dashboard").isEnabled()
