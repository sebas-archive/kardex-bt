import pytest

from conftest import connect

UUID = "tst-store-1"


@pytest.fixture
def conteos_de_prueba():
    """Un conteo ABIERTO y uno CERRADO, con un stock del sistema distintivo, ya con COMMIT."""
    conn = connect()
    cur = conn.cursor()

    def limpiar():
        cur.execute("DELETE FROM stock_sistema WHERE id_conteo LIKE 'TST-%'")
        cur.execute("DELETE FROM conteos WHERE id_conteo LIKE 'TST-%'")
        conn.commit()

    limpiar()
    cur.execute(
        "INSERT INTO conteos (id_conteo, nombre, estado) VALUES ('TST-OPEN', 'Abierto de prueba', 'ABIERTO')"
    )
    cur.execute(
        "INSERT INTO conteos (id_conteo, nombre, estado) VALUES ('TST-CLOSED', 'Cerrado de prueba', 'CERRADO')"
    )
    cur.execute(
        "INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) "
        "VALUES ('TST-OPEN', (SELECT MIN(sku) FROM productos), 987654.321)"
    )
    conn.commit()
    try:
        yield
    finally:
        limpiar()
        conn.close()


def test_last_seq_zero_for_unknown_device(store):
    assert store.last_seq("tst-nunca-visto") == 0


def test_insert_staging_returns_false_on_duplicate(store):
    assert store.insert_staging(UUID, 1, "REC|1") is True
    store.commit()
    assert store.insert_staging(UUID, 1, "REC|1") is False
    assert store.last_seq(UUID) == 1


def test_register_device_is_idempotent(store, db):
    store.register_device(UUID, "Bodega 1")
    store.register_device(UUID, "Bodega 1 renombrada")
    cur = db.cursor()
    cur.execute("SELECT nombre FROM dispositivos WHERE uuid = :u", u=UUID)
    assert cur.fetchall() == [("Bodega 1 renombrada",)]


def test_catalog_has_only_open_conteos(store, conteos_de_prueba):
    catalog = store.catalog()
    ids = [c[0] for c in catalog.conteos]
    assert "CONT-2026-11" in ids
    assert "TST-OPEN" in ids
    assert "TST-CLOSED" not in ids
    assert len(catalog.productos) == 60
    # Conteo ciego: ninguna tupla del catálogo lleva cantidades de stock.
    assert all(len(p) == 4 for p in catalog.productos)
    assert "987654" not in repr(catalog)
