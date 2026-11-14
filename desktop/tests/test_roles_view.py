"""Vista «Roles y permisos»: doce filas, Administrador bloqueado entero."""

from app.auth import ADMIN, INVENTARIO, OPERADOR, Sesion
from app.permisos import CONSULTA, GESTION, NINGUNO
from app.views.roles import RolesView

ANA = Sesion("ana.gomez", "Ana Gómez", ADMIN)


def _vista(qtbot, permisos_db):
    vista = RolesView()
    qtbot.addWidget(vista)
    vista.set_sesion(ANA)
    from app import auth
    from app import db
    with db._conexion() as conn:   # Ana existe y está ACTIVO: guardar lo comprueba en vivo
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {auth.TABLA} WHERE usuario = 'ana.gomez'")
        cur.execute(f"INSERT INTO {auth.TABLA} (usuario, nombre, rol, clave_hash, estado) "
                    "VALUES ('ana.gomez', 'Ana', 'ADMIN', 'x', 'ACTIVO')")
        conn.commit()
    qtbot.waitUntil(lambda: vista.combo(OPERADOR, "sync") is not None, timeout=5000)
    return vista


def test_roles_muestra_los_doce_modulos(qtbot, cuentas, permisos_db):
    vista = _vista(qtbot, permisos_db)
    assert vista.tabla.rowCount() == 12
    assert vista.combo(OPERADOR, "sync").currentData() == GESTION
    assert vista.combo(OPERADOR, "notificaciones").currentData() == CONSULTA
    assert vista.combo(INVENTARIO, "usuarios").currentData() == NINGUNO
    assert not any("próximamente" in vista.tabla.item(f, 0).text() for f in range(vista.tabla.rowCount()))


def test_la_fila_del_administrador_esta_deshabilitada_entera(qtbot, cuentas, permisos_db):
    vista = _vista(qtbot, permisos_db)
    for clave, _ in permisos_db.MODULOS:
        assert not vista.combo(ADMIN, clave).isEnabled()
    assert vista.combo(INVENTARIO, "dashboard").isEnabled()


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
