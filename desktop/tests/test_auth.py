"""Cuentas del escritorio: registro, inicio de sesión, recuperación, roles y preferencias."""

from datetime import datetime

import pytest

from app import db as dbq
from app.auth import (ACTIVO, ADMIN, INVENTARIO, OPERADOR, PENDIENTE, RECHAZADO, SUSPENDIDO, CuentaSinAcceso,
                      ErrorDeAcceso, PREGUNTAS, Sesion)

CORREO_ADMIN = "ana@example.com"
PREGUNTA = PREGUNTAS[0]
RESPUESTA = "Firulais"


def _columna(usuario, columna):
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT {columna} FROM usuarios_tst WHERE usuario = :u", u=usuario)
        fila = cur.fetchone()
        return None if fila is None else fila[0]


def _ejecutar(sql, **binds):
    with dbq._conexion() as conn:
        conn.cursor().execute(sql, binds)
        conn.commit()


def _admin(cuentas, usuario="ana.gomez", nombre="Ana Gómez", correo=CORREO_ADMIN):
    return cuentas.registrar(usuario, nombre, "conteo2026", "conteo2026", correo, PREGUNTA, RESPUESTA)


@pytest.fixture
def dos(cuentas):
    """Ana (primera cuenta → ADMIN con pregunta) y Luis (INVENTARIO aprobado)."""
    ana = _admin(cuentas)
    assert cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026", "luis@example.com") is None
    cuentas.aprobar(ana, "luis", INVENTARIO)
    return cuentas, ana, Sesion("luis", "Luis Ortiz", INVENTARIO)


@pytest.fixture
def operador(dos):
    """Una cuenta del celular, aprobada como Operador (reutiliza el Administrador de ``dos``)."""
    cuentas, ana, _ = dos
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO usuarios_tst (usuario, nombre, correo, rol, clave_hash, estado, origen) "
                    "VALUES ('op1', 'Operaria Uno', NULL, NULL, :h, 'PENDIENTE', 'MOVIL')", h=cuentas.crear_hash("conteo2026"))
        conn.commit()
    cuentas.aprobar(ana, "op1", OPERADOR)
    return cuentas, ana


def test_first_account_is_the_only_admin_and_the_rest_wait(cuentas):
    ana = _admin(cuentas, "  Ana.Gomez ", " Ana Gómez ")
    assert ana == Sesion("ana.gomez", "Ana Gómez", ADMIN)
    assert ana.correo == CORREO_ADMIN
    assert _columna("ana.gomez", "pregunta") == PREGUNTA
    assert cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026", "luis@example.com") is None
    with pytest.raises(CuentaSinAcceso):
        cuentas.iniciar_sesion("luis", "conteo2026")
    assert [(u.usuario, u.rol) for u in cuentas.listar()] == [("ana.gomez", ADMIN), ("luis", None)]
    cuentas.aprobar(ana, "luis", INVENTARIO)
    assert cuentas.iniciar_sesion("luis", "conteo2026").rol == INVENTARIO


@pytest.mark.parametrize("usuario, nombre, correo, clave, confirmacion, mensaje", [
    ("lu", "Luis", "l@example.com", "conteo2026", "conteo2026", "usuario"),
    ("luis pérez", "Luis", "l@example.com", "conteo2026", "conteo2026", "usuario"),
    ("luis", "  ", "l@example.com", "conteo2026", "conteo2026", "nombre"),
    ("luis", "n" * 61, "l@example.com", "conteo2026", "conteo2026", "nombre"),
    ("luis", "Luis", "sin-arroba", "conteo2026", "conteo2026", "correo"),
    ("luis", "Luis", "", "conteo2026", "conteo2026", "correo"),
    ("luis", "Luis", "l@example.com", "abc123", "abc123", "8 caracteres"),
    ("luis", "Luis", "l@example.com", "solamenteletras", "solamenteletras", "letras y números"),
    ("luis", "Luis", "l@example.com", "conteo2026", "conteo2027", "no coinciden"),
])
def test_register_validates_every_field(cuentas, usuario, nombre, correo, clave, confirmacion, mensaje):
    with pytest.raises(ErrorDeAcceso, match=mensaje):
        cuentas.registrar(usuario, nombre, clave, confirmacion, correo)
    assert cuentas.listar() == []


def test_first_admin_needs_a_security_question(cuentas):
    with pytest.raises(ErrorDeAcceso, match="pregunta"):
        cuentas.registrar("ana", "Ana", "conteo2026", "conteo2026", CORREO_ADMIN)
    with pytest.raises(ErrorDeAcceso, match="respuesta"):
        cuentas.registrar("ana", "Ana", "conteo2026", "conteo2026", CORREO_ADMIN, PREGUNTA, "")
    assert cuentas.listar() == []


def test_duplicate_user_or_email_is_rejected(dos):
    cuentas, _, _ = dos
    with pytest.raises(ErrorDeAcceso, match="ya existe"):
        cuentas.registrar("LUIS", "Otro Luis", "conteo2026", "conteo2026", "otro@example.com")
    with pytest.raises(ErrorDeAcceso, match="correo"):
        cuentas.registrar("nuevo", "Nuevo", "conteo2026", "conteo2026", "LUIS@example.com")


def test_password_is_never_stored_in_plain_text(dos):
    hash_ana, hash_luis = _columna("ana.gomez", "clave_hash"), _columna("luis", "clave_hash")
    assert "conteo2026" not in hash_ana and hash_ana.startswith("pbkdf2-sha256$1000$")
    assert hash_ana != hash_luis


def test_login_is_generic_and_operators_are_rejected(dos, operador):
    cuentas, ana, _ = dos
    assert cuentas.iniciar_sesion(" ANA.gomez ", "conteo2026") == ana
    for usuario, clave in (("ana.gomez", "Conteo2026"), ("nadie", "conteo2026")):
        with pytest.raises(ErrorDeAcceso, match="Usuario o contraseña incorrectos"):
            cuentas.iniciar_sesion(usuario, clave)
    with pytest.raises(ErrorDeAcceso, match="app móvil"):
        operador[0].iniciar_sesion("op1", "conteo2026")


def test_login_locks_after_five_failures_with_the_same_message(dos):
    cuentas, ana, _ = dos
    for _ in range(5):
        with pytest.raises(ErrorDeAcceso, match="Usuario o contraseña incorrectos"):
            cuentas.iniciar_sesion("ana.gomez", "malaclave1")
    with pytest.raises(ErrorDeAcceso, match="Usuario o contraseña incorrectos"):
        cuentas.iniciar_sesion("ana.gomez", "conteo2026")           # bloqueada: ni con la buena
    _ejecutar("UPDATE usuarios_tst SET bloqueado_hasta = SYSTIMESTAMP - INTERVAL '1' SECOND WHERE usuario = 'ana.gomez'")
    assert cuentas.iniciar_sesion("ana.gomez", "conteo2026") == ana
    assert _columna("ana.gomez", "intentos") == 0


def test_admin_changes_its_password_directly(dos):
    cuentas, ana, _ = dos
    with pytest.raises(ErrorDeAcceso, match="actual"):
        cuentas.cambiar_clave("ana.gomez", "otra12345", "nueva2027", "nueva2027")
    assert cuentas.cambiar_clave("ana.gomez", "conteo2026", "nueva2027", "nueva2027") == "Contraseña cambiada."
    assert cuentas.iniciar_sesion("ana.gomez", "nueva2027") == ana


def test_inventory_password_change_waits_for_approval(dos):
    cuentas, ana, _ = dos
    assert "Solicitud" in cuentas.cambiar_clave("luis", "conteo2026", "nueva2027", "nueva2027")
    assert _columna("luis", "clave_pendiente") is not None
    assert cuentas.iniciar_sesion("luis", "conteo2026").rol == INVENTARIO      # la vieja sigue valiendo
    cuentas.resolver_clave(ana, "luis", True)
    assert cuentas.iniciar_sesion("luis", "nueva2027").rol == INVENTARIO


def test_rejecting_a_password_request_keeps_the_old_one_and_shows_the_reason(dos):
    cuentas, ana, _ = dos
    cuentas.cambiar_clave("luis", "conteo2026", "nueva2027", "nueva2027")
    cuentas.resolver_clave(ana, "luis", False, "No cumplía la política")
    assert _columna("luis", "clave_pendiente") is None
    assert _columna("luis", "clave_motivo") == "No cumplía la política"
    assert cuentas.iniciar_sesion("luis", "conteo2026").aviso_clave == "No cumplía la política"
    cuentas.consumir_aviso_clave("luis")
    assert _columna("luis", "clave_motivo") is None
    with pytest.raises(ErrorDeAcceso, match="ya fue resuelta"):
        cuentas.resolver_clave(ana, "luis", True)
    with pytest.raises(ErrorDeAcceso):
        cuentas.iniciar_sesion("luis", "nueva2027")


def test_admin_recovers_with_the_security_question(dos):
    cuentas, _, _ = dos
    clave_pregunta = cuentas.pregunta_de("ana.gomez")
    assert clave_pregunta == PREGUNTA
    with pytest.raises(ErrorDeAcceso, match="respuesta"):
        cuentas.recuperar("ana.gomez", "nueva2027", "nueva2027", "otra")
    assert "Contraseña cambiada" in cuentas.recuperar("ana.gomez", "nueva2027", "nueva2027", RESPUESTA)
    assert cuentas.iniciar_sesion("ana.gomez", "nueva2027").rol == ADMIN
    assert cuentas.pregunta_de("luis") is None


def test_inventory_recovery_creates_a_request(dos):
    cuentas, ana, _ = dos
    assert "Solicitud" in cuentas.recuperar("luis", "nueva2027", "nueva2027")
    assert _columna("luis", "clave_pendiente") is not None
    cuentas.resolver_clave(ana, "luis", True)
    assert cuentas.iniciar_sesion("luis", "nueva2027").rol == INVENTARIO


def test_only_an_admin_manages_accounts(dos):
    cuentas, ana, luis = dos
    for accion in (lambda: cuentas.cambiar_rol(luis, "ana.gomez", INVENTARIO),
                   lambda: cuentas.suspender(luis, "ana.gomez", "porque sí"),
                   lambda: cuentas.restablecer_clave(luis, "ana.gomez", "nueva2027")):
        with pytest.raises(ErrorDeAcceso, match="permiso"):
            accion()
    cuentas.restablecer_clave(ana, "luis", "nueva2027")
    assert cuentas.iniciar_sesion("luis", "nueva2027").rol == INVENTARIO


def test_there_is_never_a_second_admin(dos):
    cuentas, ana, luis = dos
    with pytest.raises(ErrorDeAcceso, match="Administrador"):
        cuentas.cambiar_rol(ana, "luis", ADMIN)
    with pytest.raises(ErrorDeAcceso, match="Administrador"):
        cuentas.suspender(ana, "ana.gomez", "no")
    assert [(u.usuario, u.rol) for u in cuentas.listar()] == [("ana.gomez", ADMIN), ("luis", INVENTARIO)]


def test_operator_can_only_be_operator_and_never_reset_from_desktop(operador):
    cuentas, ana = operador
    with pytest.raises(ErrorDeAcceso, match="celular"):
        cuentas.cambiar_rol(ana, "op1", INVENTARIO)
    with pytest.raises(ErrorDeAcceso, match="teléfono"):
        cuentas.restablecer_clave(ana, "op1", "nueva2027")
    cuentas.desvincular_telefono(ana, "op1")


def test_approval_roles_are_limited_by_origin(cuentas):
    ana = _admin(cuentas)
    cuentas.registrar("luis", "Luis", "conteo2026", "conteo2026", "luis@example.com")
    with pytest.raises(ErrorDeAcceso, match="Administrador"):
        cuentas.aprobar(ana, "luis", ADMIN)
    cuentas.aprobar(ana, "luis", INVENTARIO)
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO usuarios_tst (usuario, nombre, correo, rol, clave_hash, estado, origen) "
                    "VALUES ('op1', 'Operaria', NULL, NULL, :h, 'PENDIENTE', 'MOVIL')", h=cuentas.crear_hash("conteo2026"))
        conn.commit()
    with pytest.raises(ErrorDeAcceso, match="celular"):
        cuentas.aprobar(ana, "op1", INVENTARIO)
    cuentas.aprobar(ana, "op1", OPERADOR)


def test_preferences_and_photo_are_per_user(dos):
    cuentas, _, _ = dos
    assert cuentas.guardar_preferencias("luis", tema="claro", idioma="en") == ("claro", "en")
    assert cuentas.iniciar_sesion("luis", "conteo2026").idioma == "en"
    cuentas.guardar_foto("luis", "perfiles/luis.jpg")
    assert cuentas.foto_de("luis") == "perfiles/luis.jpg"
    with pytest.raises(ErrorDeAcceso, match="ruta"):
        cuentas.guardar_foto("luis", "../fuera.jpg")
    cuentas.guardar_foto("luis", None)
    assert cuentas.foto_de("luis") is None
