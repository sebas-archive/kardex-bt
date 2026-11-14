"""Matriz de permisos editable: doce módulos, fila del Administrador bloqueada."""

import pytest

from app.auth import ADMIN, INVENTARIO, OPERADOR, PREGUNTAS, ErrorDeAcceso, Sesion
from app.permisos import CONSULTA, GESTION, NINGUNO


@pytest.fixture
def gente(cuentas):
    """Ana (ADMIN) y Luis (INVENTARIO) existen en la tabla: exigir comprueba su cuenta en vivo."""
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026", "ana@example.com",
                            PREGUNTAS[0], "Firulais")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026", "luis@example.com")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    return ana, cuentas.iniciar_sesion("luis", "conteo2026")


def test_matriz_inicial_coincide_con_la_especificacion(permisos_db):
    p = permisos_db
    assert len(p.MODULOS) == 12
    assert {clave for clave, _ in p.MODULOS} == {
        "dashboard", "inventario", "graficas", "sync", "notificaciones", "perfil",
        "solicitudes", "usuarios", "permisos", "auditoria", "configuracion", "respaldos"}
    for clave, _ in p.MODULOS:
        assert p.nivel(ADMIN, clave) == GESTION
    for clave in ("dashboard", "inventario", "graficas", "sync", "notificaciones", "perfil"):
        assert p.nivel(INVENTARIO, clave) == GESTION
    for clave in ("solicitudes", "usuarios", "permisos", "auditoria", "configuracion", "respaldos"):
        assert p.nivel(INVENTARIO, clave) == NINGUNO
    assert p.nivel(OPERADOR, "sync") == GESTION
    assert p.nivel(OPERADOR, "notificaciones") == CONSULTA
    for clave in ("dashboard", "inventario", "graficas", "perfil", "solicitudes", "usuarios", "permisos",
                  "auditoria", "configuracion", "respaldos"):
        assert p.nivel(OPERADOR, clave) == NINGUNO
    assert len(p.matriz()) == 12 * 3


def test_guardar_cambia_nivel_y_se_lee_de_nuevo(permisos_db, gente):
    ANA, LUIS = gente
    permisos_db.guardar(ANA, INVENTARIO, "configuracion", CONSULTA)
    assert permisos_db.nivel(INVENTARIO, "configuracion") == CONSULTA
    assert permisos_db.puede(INVENTARIO, "configuracion")
    assert not permisos_db.puede(INVENTARIO, "configuracion", GESTION)


@pytest.mark.parametrize("modulo", ["dashboard", "usuarios", "solicitudes", "permisos", "sync", "respaldos"])
def test_la_fila_del_administrador_esta_bloqueada(permisos_db, gente, modulo):
    ANA, _ = gente
    with pytest.raises(ErrorDeAcceso, match="bloqueada"):
        permisos_db.guardar(ANA, ADMIN, modulo, CONSULTA)
    assert permisos_db.nivel(ADMIN, modulo) == GESTION


def test_solo_con_permiso_de_permisos_se_guarda(permisos_db, gente):
    ANA, LUIS = gente
    with pytest.raises(ErrorDeAcceso, match="permiso"):
        permisos_db.guardar(LUIS, INVENTARIO, "usuarios", GESTION)
    permisos_db.guardar(ANA, INVENTARIO, "permisos", GESTION)       # se le da el permiso: ya puede
    permisos_db.guardar(LUIS, OPERADOR, "sync", NINGUNO)
    assert permisos_db.nivel(OPERADOR, "sync") == NINGUNO


@pytest.mark.parametrize("rol, modulo, nivel", [("JEFE", "usuarios", GESTION), (INVENTARIO, "nada", GESTION),
                                                (INVENTARIO, "usuarios", "TODO")])
def test_guardar_valida_rol_modulo_y_nivel(permisos_db, gente, rol, modulo, nivel):
    ANA, _ = gente
    with pytest.raises(ErrorDeAcceso):
        permisos_db.guardar(ANA, rol, modulo, nivel)


def test_exigir_niega_a_inventario_gestionar_usuarios(permisos_db, gente):
    ANA, LUIS = gente
    with pytest.raises(ErrorDeAcceso, match="No tienes permiso para esto."):
        permisos_db.exigir(LUIS, "usuarios")
    permisos_db.exigir(ANA, "usuarios")
    permisos_db.exigir(LUIS, "sync")          # Inventario sí gestiona Sincronización


def test_nivel_de_modulo_inexistente_es_ninguno(permisos_db):
    assert permisos_db.nivel(ADMIN, "no-existe") == NINGUNO
    assert not permisos_db.puede(ADMIN, "no-existe")


def test_el_permiso_se_lee_de_oracle_en_auth(cuentas, permisos_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026", "ana@example.com",
                            PREGUNTAS[0], "Firulais")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026", "luis@example.com")
    cuentas.registrar("marta", "Marta Ruiz", "conteo2026", "conteo2026", "marta@example.com")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    luis = cuentas.iniciar_sesion("luis", "conteo2026")
    with pytest.raises(ErrorDeAcceso, match="permiso"):
        cuentas.aprobar(luis, "marta", INVENTARIO)
    permisos_db.guardar(ana, INVENTARIO, "solicitudes", GESTION)    # ahora Inventario puede resolver solicitudes
    cuentas.aprobar(luis, "marta", INVENTARIO)


def test_exigir_con_cuenta_inexistente_niega(permisos_db):
    with pytest.raises(ErrorDeAcceso, match="permiso"):
        permisos_db.exigir(Sesion("fantasma", "Nadie", ADMIN), "usuarios")


def test_migrar_borra_los_modulos_retirados(permisos_db):
    from app import db
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO permisos_tst (rol, modulo, nivel) VALUES ('OPERADOR', 'tareas', 'GESTION')")
        conn.commit()
    permisos_db.migrar()
    assert permisos_db.nivel(OPERADOR, "tareas") == NINGUNO
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM permisos_tst WHERE modulo = 'tareas'")
        assert cur.fetchone()[0] == 0


def test_permisos_migrar_aguanta_otro_escritorio(permisos_db, monkeypatch):
    antes = permisos_db.matriz()
    monkeypatch.setattr(permisos_db, "_existe_tabla", lambda *a: False)
    monkeypatch.setattr(permisos_db, "_filas_existentes", lambda *a: set())   # cree que faltan todas
    permisos_db.migrar()
    assert permisos_db.matriz() == antes
