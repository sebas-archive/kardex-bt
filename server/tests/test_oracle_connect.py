def test_server_version_is_11_2(db):
    cur = db.cursor()
    cur.execute("SELECT banner FROM v$version")
    banners = [row[0] for row in cur.fetchall()]
    assert any("11.2" in b for b in banners), banners


def test_database_charset_is_al32utf8(db):
    cur = db.cursor()
    cur.execute(
        "SELECT value FROM nls_database_parameters WHERE parameter = 'NLS_CHARACTERSET'"
    )
    assert cur.fetchone()[0] == "AL32UTF8"


def test_btsync_package_importable():
    import btsync

    assert btsync.__version__ == "0.1.0"
