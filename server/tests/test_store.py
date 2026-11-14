from conftest import connect

UUID = "tst-store-1"


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


def test_catalog_is_a_single_pseudo_catalogo(store):
    catalog = store.catalog(None)
    assert [c[0] for c in catalog.tareas] == ["CATALOGO"]
    tarea = catalog.tareas[0]
    assert tarea[1] == "Catálogo" and tarea[2] == "" and tarea[3] == "" and tarea[4] == "ABIERTO"
    assert len(catalog.productos) == 60
    assert len(catalog.items) == 60
    assert all(item[0] == "CATALOGO" and item[2] == "N" for item in catalog.items)
    # Conteo ciego: ninguna tupla del catálogo lleva cantidades de stock.
    assert all(len(p) == 4 for p in catalog.productos)
    assert "987654" not in repr(catalog)
