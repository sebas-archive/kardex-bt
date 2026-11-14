"""Empleados: las cuentas del móvil también se suspenden (con motivo) y se reactivan; el Administrador no."""

from app import auth, db
from app.auth import ADMIN, OPERADOR, PREGUNTAS
from app.views import usuarios as vista_usuarios
from app.views.usuarios import UsuariosView


def _admin(cuentas):
    return cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026", "ana@example.com",
                             PREGUNTAS[0], "Firulais")


def _movil(cuentas, ana, usuario="op1"):
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"INSERT INTO {auth.TABLA} (usuario, nombre, correo, rol, clave_hash, estado, origen) "
                    "VALUES (:u, 'Operaria Uno', NULL, NULL, :h, 'PENDIENTE', 'MOVIL')",
                    u=usuario, h=cuentas.crear_hash("conteo2026"))
        conn.commit()
    cuentas.aprobar(ana, usuario, OPERADOR)


def _estado(usuario: str) -> str:
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT estado FROM {auth.TABLA} WHERE usuario = :u", u=usuario)
        return cur.fetchone()[0]


def _vista(qtbot, sesion):
    vista = UsuariosView()
    qtbot.addWidget(vista)
    vista.show()
    vista.set_sesion(sesion)
    qtbot.waitUntil(lambda: vista.tabla.rowCount() > 0, timeout=5000)
    return vista


def test_movil_se_suspende_con_motivo_y_se_reactiva(qtbot, cuentas, monkeypatch):
    ana = _admin(cuentas)
    _movil(cuentas, ana)
    vista = _vista(qtbot, ana)
    vista.seleccionar("op1")
    assert not vista.btn_estado.isHidden() and vista.btn_estado.isEnabled()
    assert vista.btn_estado.text() == "Suspender"
    monkeypatch.setattr(vista_usuarios, "pedir_motivo", lambda *_a, **_k: "Vacaciones")
    vista.btn_estado.click()
    qtbot.waitUntil(lambda: _estado("op1") == auth.SUSPENDIDO, timeout=5000)
    vista.seleccionar("op1")
    assert vista.btn_estado.text() == "Reactivar" and vista.btn_estado.isEnabled()
    vista.btn_estado.click()
    qtbot.waitUntil(lambda: _estado("op1") == auth.ACTIVO, timeout=5000)


def test_administrador_no_se_puede_suspender(qtbot, cuentas):
    ana = _admin(cuentas)
    vista = _vista(qtbot, ana)
    vista.seleccionar("ana.gomez")
    assert not vista.btn_estado.isEnabled()
    assert "Administrador no se puede suspender" in vista.btn_estado.toolTip()
    assert vista.btn_estado.text() == "Suspender"
