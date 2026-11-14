"""Configuración general (Fase 5): valores en Oracle con sus iniciales; el receptor lee el límite de foto de ahí."""

import pytest

from btsync import config
from btsync.protocol import foto_lineas, frame
from conftest import connect
from test_session import UUID, end, inicio, rec, run, sent  # noqa: F401


@pytest.fixture
def config_tst():
    conn = connect()
    conn.cursor().execute("DELETE FROM configuracion_tst")
    conn.commit()
    yield conn
    conn.cursor().execute("DELETE FROM configuracion_tst")
    conn.commit()
    conn.close()


def test_sin_filas_lee_los_iniciales(config_tst):
    assert config.leer(config_tst.cursor()) == config.DEFAULTS
    assert config.DEFAULTS == {
        "lote.intervalo_min": "1", "fotos.max_mb": "2", "fotos.dir": "/work/fotos",
        "respaldos.auto": "S", "respaldos.hora": "23:00", "respaldos.conservar": "7"}


def test_escribir_y_leer(config_tst):
    cur = config_tst.cursor()
    config.escribir(cur, {"fotos.max_mb": "5"})
    config.escribir(cur, {"fotos.max_mb": "3", "lote.intervalo_min": "30"})
    config_tst.commit()
    valores = config.leer(cur)
    assert valores["fotos.max_mb"] == "3" and valores["lote.intervalo_min"] == "30"
    assert valores["respaldos.auto"] == "S"


def test_migrar_dos_veces(config_tst):
    config.migrar(config_tst)
    config.migrar(config_tst)


def test_clave_desconocida_no_se_escribe(config_tst):
    with pytest.raises(KeyError):
        config.escribir(config_tst.cursor(), {"no.existe": "1"})


def test_el_limite_de_foto_sale_de_la_configuracion(store, config_tst, tmp_path, monkeypatch):
    monkeypatch.setenv("FOTOS_DIR", str(tmp_path))
    config.escribir(config_tst.cursor(), {"fotos.max_mb": "1"})
    config_tst.commit()
    grande = b"\xff\xd8" + bytes(range(256)) * 6000 + b"\xff\xd9"     # ~1,5 MB
    conn, _ = run(store, [*inicio(), rec(1), *[frame(x) for x in foto_lineas(1, grande)], end(1)])
    out = [(m.kind, m.fields) for m in sent(conn)]
    assert out.count(("FOTOERR", ["1", "GRANDE"])) == 1 and out[-1][0] == "BYE"


@pytest.mark.parametrize("clave, valor", [
    ("fotos.max_mb", "abc"), ("fotos.max_mb", "0"), ("respaldos.conservar", "0"), ("respaldos.hora", "9:00"),
    ("respaldos.hora", "24:00"), ("respaldos.auto", "talvez"), ("lote.intervalo_min", "0")
])
def test_un_valor_invalido_guardado_vale_el_inicial(config_tst, clave, valor):
    """El servicio usa estos valores sin pantalla de por medio (p. ej. tras restaurar un respaldo): uno inválido
    no debe tumbar cada sincronización ni borrar todos los respaldos automáticos."""
    config.escribir(config_tst.cursor(), {clave: valor})
    config_tst.commit()
    assert config.leer(config_tst.cursor())[clave] == config.DEFAULTS[clave]
