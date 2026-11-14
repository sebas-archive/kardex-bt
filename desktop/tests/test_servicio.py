"""El escritorio ve el servicio Bluetooth (Fase 5): estado por su latido, pausa y respuesta al código."""

import pytest

from app import servicio
from app.auth import INVENTARIO, ErrorDeAcceso


@pytest.fixture
def ana(cuentas):
    return cuentas.registrar("ana.gomez", "Ana Gómez", "conteo2026", "conteo2026")


def test_con_latido_reciente_se_ve_el_estado_escrito(servicio_db):
    poner, _ = servicio_db
    poner(hace_s=3, estado="RECIBIENDO", recibidos=4)
    e = servicio.estado()
    assert (e.estado, e.recibidos) == ("RECIBIENDO", 4)


@pytest.mark.parametrize("hace", [11, 600])
def test_con_latido_viejo_esta_detenido(servicio_db, hace):
    poner, _ = servicio_db
    poner(hace_s=hace, estado="RECIBIENDO")
    assert servicio.estado().estado == "DETENIDO"


def test_sin_fila_esta_detenido(servicio_db):
    assert servicio.estado().estado == "DETENIDO"


def test_pausar_y_reanudar_quedan_en_la_auditoria(servicio_db, ana, auditoria_db):
    poner, leer = servicio_db
    poner()
    servicio.pausar(ana)
    assert leer("pausado") == "S"
    servicio.reanudar(ana)
    assert leer("pausado") == "N"
    acciones = [e.accion for e in auditoria_db.listar(ana) if e.modulo == "bluetooth"]
    assert acciones == ["Reanudó servicio", "Pausó servicio"]


def test_responder_el_codigo(servicio_db, ana):
    poner, leer = servicio_db
    poner(estado="CONFIRMAR_CODIGO", codigo="123456")
    servicio.responder_codigo(ana, True)
    assert leer("respuesta") == "S"


def test_sin_gestion_en_bluetooth_no_pausa(servicio_db, cuentas, ana):
    poner, leer = servicio_db
    poner()
    cuentas.registrar("luis", "Luis Ortiz", "conteo2026", "conteo2026")
    cuentas.aprobar(ana, "luis", INVENTARIO)
    from app import permisos

    permisos.guardar(ana, INVENTARIO, "bluetooth", permisos.CONSULTA)
    with pytest.raises(ErrorDeAcceso):
        servicio.pausar(cuentas.iniciar_sesion("luis", "conteo2026"))
    assert leer("pausado") == "N"


def test_el_remoto_publica_el_estado_y_avisa_cada_sincronizacion(qtbot, servicio_db):
    from app.servicio_remoto import ServicioRemoto

    poner, _ = servicio_db
    poner(estado="RECIBIENDO", recibidos=2, listos=4)
    remoto = ServicioRemoto(intervalo_ms=0)
    listos = []
    remoto.listo.connect(lambda: listos.append(1))
    remoto.sondear()
    qtbot.waitUntil(lambda: remoto.status()["estado"] == "RECIBIENDO", timeout=5000)
    assert listos == []                                   # el primer estado leído no es «llegaron datos»
    poner(estado="ESPERANDO_EMPAREJAMIENTO", listos=5)
    remoto.sondear()
    qtbot.waitUntil(lambda: listos == [1], timeout=5000)
    poner(hace_s=30, estado="ESPERANDO_EMPAREJAMIENTO", listos=5)
    remoto.sondear()
    qtbot.waitUntil(lambda: remoto.status()["estado"] == "DETENIDO", timeout=5000)
