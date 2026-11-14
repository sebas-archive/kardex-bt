"""Matriz de permisos editable: qué módulos ve y gestiona cada rol."""

import pytest

from app.auth import ADMIN, INVENTARIO, OPERADOR, ErrorDeAcceso, Sesion
from app.permisos import CONSULTA, GESTION, NINGUNO



@pytest.fixture
def gente(cuentas):
    """Ana (ADMIN) y Luis (INVENTARIO) existen en la tabla: exigir comprueba su cuenta en vivo."""
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    return ana, cuentas.iniciar_sesion("luis", "conteo2026")


def test_matriz_inicial_coincide_con_la_especificacion(permisos_db):
    p = permisos_db
    assert p.nivel(ADMIN, "usuarios") == GESTION
    assert p.nivel(INVENTARIO, "usuarios") == NINGUNO
    assert p.nivel(OPERADOR, "tareas") == GESTION
    assert p.nivel(OPERADOR, "usuarios") == NINGUNO
    assert p.nivel(ADMIN, "ajustes") == GESTION
    assert p.nivel(ADMIN, "existencias") == CONSULTA
    assert p.nivel(INVENTARIO, "configuracion") == NINGUNO
    matriz = p.matriz()
    assert len(matriz) == len(p.MODULOS) * 3
    assert {clave for clave, _ in p.MODULOS} >= {"dashboard", "usuarios", "roles", "permisos", "solicitudes",
                                                  "existencias", "bluetooth", "historial", "perfil"}


def test_guardar_cambia_nivel_y_se_lee_de_nuevo(permisos_db, gente):
    ANA, LUIS = gente
    permisos_db.guardar(ANA, INVENTARIO, "configuracion", CONSULTA)
    assert permisos_db.nivel(INVENTARIO, "configuracion") == CONSULTA
    assert permisos_db.puede(INVENTARIO, "configuracion")
    assert not permisos_db.puede(INVENTARIO, "configuracion", GESTION)


@pytest.mark.parametrize("modulo", ["usuarios", "solicitudes", "permisos"])
def test_no_se_puede_quitar_acceso_intocable(permisos_db, gente, modulo):
    ANA, LUIS = gente
    with pytest.raises(ErrorDeAcceso, match="administrador"):
        permisos_db.guardar(ANA, ADMIN, modulo, CONSULTA)
    assert permisos_db.nivel(ADMIN, modulo) == GESTION


def test_solo_con_permiso_de_permisos_se_guarda(permisos_db, gente):
    ANA, LUIS = gente
    with pytest.raises(ErrorDeAcceso, match="permiso"):
        permisos_db.guardar(LUIS, INVENTARIO, "usuarios", GESTION)
    permisos_db.guardar(ANA, INVENTARIO, "permisos", GESTION)       # se le da el permiso: ya puede
    permisos_db.guardar(LUIS, OPERADOR, "historial", NINGUNO)
    assert permisos_db.nivel(OPERADOR, "historial") == NINGUNO


@pytest.mark.parametrize("rol, modulo, nivel", [("JEFE", "usuarios", GESTION), (INVENTARIO, "nada", GESTION),
                                                (INVENTARIO, "usuarios", "TODO")])
def test_guardar_valida_rol_modulo_y_nivel(permisos_db, gente, rol, modulo, nivel):
    ANA, LUIS = gente
    with pytest.raises(ErrorDeAcceso):
        permisos_db.guardar(ANA, rol, modulo, nivel)


def test_exigir_niega_a_inventario_gestionar_usuarios(permisos_db, gente):
    ANA, LUIS = gente
    with pytest.raises(ErrorDeAcceso, match="No tienes permiso para esto."):
        permisos_db.exigir(LUIS, "usuarios")
    permisos_db.exigir(ANA, "usuarios")
    permisos_db.exigir(LUIS, "existencias")


def test_nivel_de_modulo_inexistente_es_ninguno(permisos_db):
    assert permisos_db.nivel(ADMIN, "no-existe") == NINGUNO
    assert not permisos_db.puede(ADMIN, "no-existe")


def test_el_permiso_se_lee_de_oracle_en_auth(cuentas, permisos_db):
    ana = cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.registrar("marta", "Marta Ruiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    luis = cuentas.iniciar_sesion("luis", "conteo2026")
    with pytest.raises(ErrorDeAcceso, match="permiso"):
        cuentas.aprobar(luis, "marta", INVENTARIO)
    permisos_db.guardar(ana, INVENTARIO, "solicitudes", GESTION)    # ahora Inventario puede resolver solicitudes
    cuentas.aprobar(luis, "marta", INVENTARIO)


def test_exigir_con_cuenta_inexistente_niega(permisos_db, cuentas):
    with pytest.raises(ErrorDeAcceso, match="permiso"):
        permisos_db.exigir(Sesion("fantasma", "Nadie", ADMIN), "usuarios")


def test_modulos_en_uso(permisos_db):
    assert {"usuarios", "solicitudes", "permisos", "roles", "dashboard", "existencias", "bluetooth", "reportes",
            "perfil", "categorias", "conteos", "tareas", "diferencias",
            "entradas_salidas", "movimientos", "ajustes", "historial", "configuracion", "respaldos"} == set(permisos_db.EN_USO)


def test_permisos_migrar_aguanta_otro_escritorio(permisos_db, monkeypatch):
    antes = permisos_db.matriz()
    monkeypatch.setattr(permisos_db, "_existe_tabla", lambda *a: False)
    monkeypatch.setattr(permisos_db, "_filas_existentes", lambda *a: set())   # cree que faltan todas
    permisos_db.migrar()
    assert permisos_db.matriz() == antes
