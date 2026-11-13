"""Cuentas de la aplicación de escritorio: registro, inicio de sesión y roles ADMIN / INVENTARIO."""

from datetime import datetime

import pytest

from app import db as dbq
from app.auth import (ACTIVO, ADMIN, INVENTARIO, OPERADOR, PENDIENTE, RECHAZADO, SUSPENDIDO, CuentaSinAcceso,
                      ErrorDeAcceso, Sesion)


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


@pytest.fixture
def dos(cuentas):
    """Ana (primera cuenta → ADMIN) y Luis (INVENTARIO)."""
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    assert cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026") is None   # queda pendiente
    cuentas.aprobar(ana, "luis", INVENTARIO)
    return cuentas, ana, Sesion("luis", "Luis Ortiz", INVENTARIO)


def test_first_account_is_admin_and_the_rest_wait_for_a_role(cuentas):
    ana = cuentas.registrar("  Ana.Gomez ", " Ana Gómez ", "conteo2026", "conteo2026")
    assert ana == Sesion("ana.gomez", "Ana Gómez", ADMIN)          # usuario en minúsculas, sin espacios
    assert cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026") is None   # nadie elige su rol
    with pytest.raises(CuentaSinAcceso):
        cuentas.iniciar_sesion("luis", "conteo2026")
    assert [(u.usuario, u.rol) for u in cuentas.listar()] == [("ana.gomez", ADMIN), ("luis", None)]
    cuentas.aprobar(ana, "luis", INVENTARIO)
    assert cuentas.iniciar_sesion("luis", "conteo2026").rol == INVENTARIO


@pytest.mark.parametrize("usuario, nombre, clave, confirmacion, mensaje", [
    ("lu", "Luis", "conteo2026", "conteo2026", "usuario"),
    ("luis pérez", "Luis", "conteo2026", "conteo2026", "usuario"),
    ("luis", "  ", "conteo2026", "conteo2026", "nombre"),
    ("luis", "n" * 61, "conteo2026", "conteo2026", "nombre"),
    ("luis", "Luis", "abc123", "abc123", "8 caracteres"),
    ("luis", "Luis", "solamenteletras", "solamenteletras", "letras y números"),
    ("luis", "Luis", "conteo2026", "conteo2027", "no coinciden"),
])
def test_register_validates_every_field(cuentas, usuario, nombre, clave, confirmacion, mensaje):
    with pytest.raises(ErrorDeAcceso, match=mensaje):
        cuentas.registrar(usuario, nombre, clave, confirmacion)
    assert cuentas.listar() == []


def test_register_rejects_a_duplicate_user(dos):
    cuentas, _, _ = dos
    with pytest.raises(ErrorDeAcceso, match="ya existe"):
        cuentas.registrar("LUIS", "Otro Luis", "conteo2026", "conteo2026")
    assert [u.usuario for u in cuentas.listar()] == ["ana.gomez", "luis"]


def test_password_is_never_stored_in_plain_text(dos):
    hash_ana, hash_luis = _columna("ana.gomez", "clave_hash"), _columna("luis", "clave_hash")
    assert "conteo2026" not in hash_ana and hash_ana.startswith("pbkdf2-sha256$1000$")
    assert hash_ana != hash_luis                                    # misma clave, sal distinta


def test_login_accepts_only_the_right_password(dos):
    cuentas, ana, _ = dos
    assert cuentas.iniciar_sesion(" ANA.gomez ", "conteo2026") == ana
    for usuario, clave in (("ana.gomez", "Conteo2026"), ("nadie", "conteo2026")):
        with pytest.raises(ErrorDeAcceso, match="Usuario o contraseña incorrectos"):   # mismo mensaje: no revela si existe
            cuentas.iniciar_sesion(usuario, clave)


def test_login_locks_after_five_failures_and_unlocks_with_time(dos):
    cuentas, ana, _ = dos
    for _ in range(4):
        with pytest.raises(ErrorDeAcceso, match="incorrectos"):
            cuentas.iniciar_sesion("ana.gomez", "malaclave1")
    with pytest.raises(ErrorDeAcceso, match="Demasiados intentos"):
        cuentas.iniciar_sesion("ana.gomez", "malaclave1")           # el quinto fallo bloquea
    with pytest.raises(ErrorDeAcceso, match="Demasiados intentos"):
        cuentas.iniciar_sesion("ana.gomez", "conteo2026")           # ni con la clave buena
    _ejecutar("UPDATE usuarios_tst SET bloqueado_hasta = SYSTIMESTAMP - INTERVAL '1' SECOND WHERE usuario = 'ana.gomez'")
    assert cuentas.iniciar_sesion("ana.gomez", "conteo2026") == ana
    assert _columna("ana.gomez", "intentos") == 0


def test_change_password_requires_the_current_one(dos):
    cuentas, ana, _ = dos
    with pytest.raises(ErrorDeAcceso, match="actual"):
        cuentas.cambiar_clave("ana.gomez", "otra12345", "nueva2027", "nueva2027")
    with pytest.raises(ErrorDeAcceso, match="8 caracteres"):
        cuentas.cambiar_clave("ana.gomez", "conteo2026", "corta1", "corta1")
    cuentas.cambiar_clave("ana.gomez", "conteo2026", "nueva2027", "nueva2027")
    assert cuentas.iniciar_sesion("ana.gomez", "nueva2027") == ana
    with pytest.raises(ErrorDeAcceso):
        cuentas.iniciar_sesion("ana.gomez", "conteo2026")


def test_only_an_admin_manages_accounts(dos):
    cuentas, ana, luis = dos
    for accion in (lambda: cuentas.cambiar_rol(luis, "ana.gomez", INVENTARIO),
                   lambda: cuentas.suspender(luis, "ana.gomez", "porque sí"),
                   lambda: cuentas.restablecer_clave(luis, "ana.gomez", "nueva2027")):
        with pytest.raises(ErrorDeAcceso, match="permiso"):
            accion()
    cuentas.cambiar_rol(ana, "luis", ADMIN)
    assert [(u.usuario, u.rol, u.estado) for u in cuentas.listar()] == [("ana.gomez", ADMIN, ACTIVO), ("luis", ADMIN, ACTIVO)]
    cuentas.restablecer_clave(ana, "luis", "nueva2027")
    assert cuentas.iniciar_sesion("luis", "nueva2027").rol == ADMIN
    with pytest.raises(ErrorDeAcceso, match="rol"):
        cuentas.cambiar_rol(ana, "luis", "JEFE")


def test_the_last_active_admin_cannot_be_removed(dos):
    cuentas, ana, _ = dos
    with pytest.raises(ErrorDeAcceso, match="único administrador"):
        cuentas.cambiar_rol(ana, "ana.gomez", INVENTARIO)
    with pytest.raises(ErrorDeAcceso, match="único administrador"):
        cuentas.suspender(ana, "ana.gomez", "prueba")
    cuentas.cambiar_rol(ana, "luis", ADMIN)                          # con otro administrador ya se puede
    cuentas.cambiar_rol(ana, "ana.gomez", INVENTARIO)
    assert [(u.usuario, u.rol) for u in cuentas.listar()] == [("ana.gomez", INVENTARIO), ("luis", ADMIN)]


def test_a_forgotten_password_goes_through_an_admin_request(dos):
    cuentas, ana, luis = dos
    mensaje = cuentas.solicitar_clave("luis", "nueva2027", "nueva2027")
    assert cuentas.solicitar_clave("nadie", "nueva2027", "nueva2027") == mensaje   # mismo texto exista o no
    assert [u.usuario for u in cuentas.listar() if u.clave_solicitada] == ["luis"]
    assert "nueva2027" not in _columna("luis", "clave_pendiente")
    assert cuentas.iniciar_sesion("luis", "conteo2026") == luis    # mientras no se apruebe, sirve la anterior
    with pytest.raises(ErrorDeAcceso, match="permiso"):
        cuentas.resolver_clave(luis, "luis", True)
    cuentas.resolver_clave(ana, "luis", True)
    assert cuentas.iniciar_sesion("luis", "nueva2027") == luis
    assert not any(u.clave_solicitada for u in cuentas.listar())
    cuentas.solicitar_clave("luis", "otra2028x", "otra2028x")
    cuentas.resolver_clave(ana, "luis", False)                      # rechazada: la contraseña no cambia
    assert cuentas.iniciar_sesion("luis", "nueva2027") == luis and not any(u.clave_solicitada for u in cuentas.listar())
    with pytest.raises(ErrorDeAcceso, match="no coinciden"):
        cuentas.solicitar_clave("luis", "nueva2027", "distinta1")


def _con_pendiente(cuentas):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    assert cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026") is None
    return ana


def test_login_pendiente_lanza_cuenta_sin_acceso(cuentas):
    _con_pendiente(cuentas)
    with pytest.raises(CuentaSinAcceso) as info:
        cuentas.iniciar_sesion("luis", "conteo2026")
    e = info.value
    assert (e.usuario, e.nombre, e.estado, e.motivo) == ("luis", "Luis Ortiz", PENDIENTE, None)
    assert isinstance(e.registrado, datetime)
    with pytest.raises(ErrorDeAcceso, match="incorrectos") as info:     # con clave mala no revela el estado
        cuentas.iniciar_sesion("luis", "otra2026x")
    assert not isinstance(info.value, CuentaSinAcceso)
    assert cuentas.consultar_cuenta("luis").estado == PENDIENTE
    assert cuentas.consultar_cuenta("nadie") is None


def test_aprobar_asigna_rol_y_activa(cuentas):
    ana = _con_pendiente(cuentas)
    cuentas.aprobar(ana, "luis", INVENTARIO)
    assert cuentas.iniciar_sesion("luis", "conteo2026") == Sesion("luis", "Luis Ortiz", INVENTARIO)
    assert (_columna("luis", "estado"), _columna("luis", "resuelto_por")) == (ACTIVO, "ana.gomez")
    with pytest.raises(ErrorDeAcceso, match="rol"):
        cuentas.aprobar(ana, "luis", "JEFE")


def test_rechazar_guarda_motivo_y_bloquea_el_login(cuentas):
    ana = _con_pendiente(cuentas)
    cuentas.rechazar(ana, "luis", "  No trabaja en la bodega  ")
    with pytest.raises(CuentaSinAcceso) as info:
        cuentas.iniciar_sesion("luis", "conteo2026")
    assert (info.value.estado, info.value.motivo) == (RECHAZADO, "No trabaja en la bodega")


@pytest.mark.parametrize("motivo", ["", "   ", "x" * 301])
def test_motivo_obligatorio_y_maximo_300(cuentas, motivo):
    ana = _con_pendiente(cuentas)
    with pytest.raises(ErrorDeAcceso, match="motivo"):
        cuentas.rechazar(ana, "luis", motivo)
    cuentas.aprobar(ana, "luis", INVENTARIO)
    with pytest.raises(ErrorDeAcceso, match="motivo"):
        cuentas.suspender(ana, "luis", motivo)
    assert _columna("luis", "estado") == ACTIVO


def test_suspender_y_reactivar(cuentas):
    ana = _con_pendiente(cuentas)
    cuentas.aprobar(ana, "luis", INVENTARIO)
    cuentas.suspender(ana, "luis", "Vacaciones")
    with pytest.raises(CuentaSinAcceso) as info:
        cuentas.iniciar_sesion("luis", "conteo2026")
    assert (info.value.estado, info.value.motivo) == (SUSPENDIDO, "Vacaciones")
    cuentas.reactivar(ana, "luis")
    assert cuentas.iniciar_sesion("luis", "conteo2026").rol == INVENTARIO
    assert _columna("luis", "motivo") is None


def test_segunda_resolucion_falla(cuentas):
    ana = _con_pendiente(cuentas)
    cuentas.aprobar(ana, "luis", INVENTARIO)
    for accion in (lambda: cuentas.aprobar(ana, "luis", ADMIN), lambda: cuentas.rechazar(ana, "luis", "tarde")):
        with pytest.raises(ErrorDeAcceso, match="ya fue resuelta"):
            accion()
    assert _columna("luis", "rol") == INVENTARIO


def test_unico_admin_no_se_suspende(cuentas):
    ana = _con_pendiente(cuentas)
    with pytest.raises(ErrorDeAcceso, match="único administrador"):
        cuentas.suspender(ana, "ana.gomez", "prueba")


def test_operador_no_entra_al_escritorio(cuentas):
    ana = _con_pendiente(cuentas)
    cuentas.aprobar(ana, "luis", INVENTARIO)
    _ejecutar("UPDATE usuarios_tst SET rol = 'OPERADOR' WHERE usuario = 'luis'")   # no se puede por la app; si pasa, no entra
    with pytest.raises(ErrorDeAcceso, match="app móvil"):
        cuentas.iniciar_sesion("luis", "conteo2026")


def test_historial_lista_resueltas_con_responsable(cuentas):
    ana = _con_pendiente(cuentas)
    cuentas.registrar("marta", "Marta Ruiz", "conteo2026", "conteo2026")
    cuentas.registrar("pablo", "Pablo Díaz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    cuentas.rechazar(ana, "marta", "Duplicada")
    historial = cuentas.historial_solicitudes()
    assert sorted((h.usuario, h.estado, h.rol, h.motivo, h.resuelto_por) for h in historial) == [
        ("luis", ACTIVO, INVENTARIO, None, "ana.gomez"), ("marta", RECHAZADO, None, "Duplicada", "ana.gomez")]
    assert all(isinstance(h.resuelto, datetime) for h in historial)


def test_registrar_usuario_rechazado_dice_ya_existe(cuentas):
    ana = _con_pendiente(cuentas)
    cuentas.rechazar(ana, "luis", "No")
    with pytest.raises(ErrorDeAcceso, match="ya existe"):
        cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")


# ------------------------------------------------------------------ Fase 1: estados de cuenta
_DDL_VIEJO = """
CREATE TABLE usuarios_mig (
    usuario          VARCHAR2(30 CHAR)  NOT NULL,
    nombre           VARCHAR2(60 CHAR)  NOT NULL,
    rol              VARCHAR2(12 CHAR),
    clave_hash       VARCHAR2(200 CHAR) NOT NULL,
    clave_pendiente  VARCHAR2(200 CHAR),
    activo           CHAR(1)            DEFAULT 'S' NOT NULL,
    intentos         NUMBER             DEFAULT 0 NOT NULL,
    bloqueado_hasta  TIMESTAMP,
    creado           TIMESTAMP          DEFAULT SYSTIMESTAMP,
    CONSTRAINT pk_usuarios_mig PRIMARY KEY (usuario),
    CONSTRAINT ck_usuarios_mig_rol CHECK (rol IS NULL OR rol IN ('ADMIN', 'INVENTARIO'))
)"""


def test_migrar_convierte_activo_en_estado(cuentas, monkeypatch):
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'USUARIOS_MIG'")
        if cur.fetchone()[0]:
            cur.execute("DROP TABLE usuarios_mig")
        cur.execute(_DDL_VIEJO)
        for usuario, rol, activo in (("nuevo", None, "S"), ("activa", "INVENTARIO", "S"), ("apagada", "INVENTARIO", "N")):
            cur.execute("INSERT INTO usuarios_mig (usuario, nombre, rol, clave_hash, activo) VALUES (:u, :u, :r, 'x', :a)",
                        u=usuario, r=rol, a=activo)
        conn.commit()
    monkeypatch.setattr(cuentas, "TABLA", "usuarios_mig")
    for _ in range(2):                                   # idempotente: la segunda vez no cambia nada
        cuentas.migrar()
        with dbq._conexion() as conn:
            cur = conn.cursor()
            cur.execute("SELECT usuario, estado, origen FROM usuarios_mig ORDER BY usuario")
            assert cur.fetchall() == [("activa", "ACTIVO", "ESCRITORIO"), ("apagada", "SUSPENDIDO", "ESCRITORIO"),
                                      ("nuevo", "PENDIENTE", "ESCRITORIO")]
            cur.execute("SELECT COUNT(*) FROM user_tab_columns WHERE table_name = 'USUARIOS_MIG' AND column_name = 'ACTIVO'")
            assert cur.fetchone()[0] == 0
    _ejecutar("UPDATE usuarios_mig SET rol = 'OPERADOR' WHERE usuario = 'activa'")   # el CHECK ya admite OPERADOR
    _ejecutar("DROP TABLE usuarios_mig")


# ------------------------------------------------------------------ correcciones de la revisión final
def _cuenta_movil(usuario="op.movil", estado="PENDIENTE", rol=None):
    _ejecutar("INSERT INTO usuarios_tst (usuario, nombre, rol, clave_hash, estado, origen) "
              "VALUES (:u, 'Operador Móvil', :r, '-', :e, 'MOVIL')", u=usuario, r=rol, e=estado)


def test_cuenta_del_movil_solo_se_aprueba_como_operador(cuentas):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    _cuenta_movil()
    for rol in (ADMIN, INVENTARIO):
        with pytest.raises(ErrorDeAcceso, match="celular"):
            cuentas.aprobar(ana, "op.movil", rol)
    cuentas.aprobar(ana, "op.movil", OPERADOR)
    with pytest.raises(ErrorDeAcceso, match="celular"):
        cuentas.cambiar_rol(ana, "op.movil", ADMIN)
    assert _columna("op.movil", "rol") == OPERADOR


def test_cuenta_del_pc_no_se_aprueba_como_operador(cuentas):
    ana = _con_pendiente(cuentas)
    with pytest.raises(ErrorDeAcceso, match="PC"):
        cuentas.aprobar(ana, "luis", OPERADOR)
    assert _columna("luis", "estado") == PENDIENTE


def test_admin_suspendido_pierde_sus_poderes_al_momento(cuentas):
    ana = _con_pendiente(cuentas)
    cuentas.aprobar(ana, "luis", ADMIN)
    luis = cuentas.iniciar_sesion("luis", "conteo2026")
    cuentas.suspender(ana, "luis", "Revisión")
    for accion in (lambda: cuentas.reactivar(luis, "luis"), lambda: cuentas.suspender(luis, "ana.gomez", "venganza")):
        with pytest.raises(ErrorDeAcceso, match="permiso"):
            accion()
    assert (_columna("luis", "estado"), _columna("ana.gomez", "estado")) == (SUSPENDIDO, ACTIVO)


def test_admin_degradado_pierde_sus_poderes_al_momento(cuentas):
    ana = _con_pendiente(cuentas)
    cuentas.aprobar(ana, "luis", ADMIN)
    luis = cuentas.iniciar_sesion("luis", "conteo2026")
    cuentas.cambiar_rol(ana, "luis", INVENTARIO)
    with pytest.raises(ErrorDeAcceso, match="permiso"):
        cuentas.cambiar_rol(luis, "luis", ADMIN)


def test_primera_cuenta_del_pc_es_admin_aunque_haya_cuentas_del_movil(cuentas):
    _cuenta_movil()                                       # un teléfono sincronizó antes que nadie se registrara en el PC
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    assert ana is not None and ana.rol == ADMIN


def test_un_admin_activo_del_movil_no_cuenta_como_administrador(cuentas):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    _cuenta_movil(estado="ACTIVO", rol="ADMIN")           # dato heredado o manipulado
    with pytest.raises(ErrorDeAcceso, match="único administrador"):
        cuentas.suspender(ana, "ana.gomez", "prueba")


def test_desvincular_telefono(cuentas):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    _cuenta_movil(estado="ACTIVO", rol="OPERADOR")
    _ejecutar("UPDATE usuarios_tst SET uuid_dispositivo = 'tel-viejo' WHERE usuario = 'op.movil'")
    cuentas.desvincular_telefono(ana, "op.movil")
    assert _columna("op.movil", "uuid_dispositivo") is None
    assert [u.telefono for u in cuentas.listar() if u.usuario == "op.movil"] == [False]


def test_migrar_convierte_aunque_estado_ya_exista(cuentas, monkeypatch):
    """Un arranque anterior alcanzó a crear ESTADO y falló: el siguiente igual convierte ACTIVO antes de borrarla."""
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'USUARIOS_MIG'")
        if cur.fetchone()[0]:
            cur.execute("DROP TABLE usuarios_mig")
        cur.execute(_DDL_VIEJO)
        cur.execute("INSERT INTO usuarios_mig (usuario, nombre, rol, clave_hash, activo) VALUES ('admin', 'A', 'ADMIN', 'x', 'S')")
        cur.execute("ALTER TABLE usuarios_mig ADD (estado VARCHAR2(10 CHAR) DEFAULT 'PENDIENTE' NOT NULL)")
        conn.commit()
    monkeypatch.setattr(cuentas, "TABLA", "usuarios_mig")
    cuentas.migrar()
    with dbq._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT estado FROM usuarios_mig")
        assert cur.fetchone()[0] == "ACTIVO"
    _ejecutar("DROP TABLE usuarios_mig")
