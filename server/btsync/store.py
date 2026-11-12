"""Acceso a Oracle: staging, catálogo y bitácora de sincronizaciones."""

from __future__ import annotations

from dataclasses import dataclass, field

import threading

import oracledb

_client_ready = False
_connect_lock = threading.Lock()


def connect_oracle(dsn: str, user: str, password: str) -> oracledb.Connection:
    """Abre una conexión thick. **Toda** conexión a Oracle debe pasar por aquí.

    Las llamadas se serializan: con el Instant Client 19 (modo thick, Oracle XE 11g) varios hilos
    llamando a ``oracledb.connect()`` a la vez abortan el proceso ("double free or corruption",
    ORA-24550). Se reprodujo en 3 de 3 corridas de 40 rondas de 4 hilos; con el candado, en 0 de 3.
    Ejecutar consultas desde varios hilos, cada uno con su conexión, no tiene este problema.
    """
    with _connect_lock:
        _init_client()
        return oracledb.connect(user=user, password=password, dsn=dsn)


def _init_client() -> None:
    """Oracle 11g exige modo thick (Instant Client)."""
    global _client_ready
    if not _client_ready:
        oracledb.init_oracle_client()
        _client_ready = True


@dataclass(frozen=True)
class Catalog:
    """Lo que el móvil necesita para contar. Nunca incluye el stock del sistema (conteo ciego)."""

    conteos: list[tuple[str, str]] = field(default_factory=list)
    ubicaciones: list[tuple[str, str, str]] = field(default_factory=list)
    productos: list[tuple[str, str, str, str]] = field(default_factory=list)


class Store:
    def __init__(self, dsn: str, user: str, password: str) -> None:
        self._dsn, self._user, self._password = dsn, user, password
        self._conn: oracledb.Connection | None = None

    def _connection(self) -> oracledb.Connection:
        """Conexión viva; si se cayó, abre otra (lo no confirmado se pierde, como en un corte)."""
        if self._conn is not None and not self._conn.is_healthy():
            self._conn = None
        if self._conn is None:
            self._conn = connect_oracle(self._dsn, self._user, self._password)
        return self._conn

    def register_device(self, uuid: str, name: str) -> None:
        conn = self._connection()
        conn.cursor().execute(
            "MERGE INTO dispositivos d USING dual ON (d.uuid = :u) "
            "WHEN MATCHED THEN UPDATE SET d.nombre = :n, d.ultima_sync = SYSTIMESTAMP "
            "WHEN NOT MATCHED THEN INSERT (uuid, nombre, ultima_sync) VALUES (:u, :n, SYSTIMESTAMP)",
            u=uuid,
            n=name,
        )
        conn.commit()

    def last_seq(self, uuid: str) -> int:
        cur = self._connection().cursor()
        cur.execute(
            "SELECT NVL(MAX(seq), 0) FROM captura_transito WHERE uuid_dispositivo = :u", u=uuid
        )
        return int(cur.fetchone()[0])

    def insert_staging(self, uuid: str, seq: int, raw: str) -> bool:
        """Inserta una línea REC. False si ya existía ``(uuid, seq)``. No hace commit."""
        cur = self._connection().cursor()
        try:
            cur.execute(
                "INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw) VALUES (:u, :s, :r)",
                u=uuid,
                s=seq,
                r=raw,
            )
        except oracledb.IntegrityError as exc:
            if "ORA-00001" in str(exc):
                return False
            raise
        return True

    def commit(self) -> None:
        if self._conn is not None:
            self._conn.commit()

    def rollback(self) -> None:
        if self._conn is not None:
            self._conn.rollback()

    def catalog(self) -> Catalog:
        cur = self._connection().cursor()
        cur.execute("SELECT id_conteo, nombre FROM conteos WHERE estado = 'ABIERTO' ORDER BY id_conteo")
        conteos = [(r[0], r[1]) for r in cur]
        cur.execute(
            "SELECT cod_ubicacion, zona, NVL(descripcion, '') FROM ubicaciones ORDER BY cod_ubicacion"
        )
        ubicaciones = [(r[0], r[1], r[2] or "") for r in cur]
        cur.execute("SELECT sku, nombre, categoria, unidad FROM productos ORDER BY sku")
        productos = [(r[0], r[1], r[2], r[3]) for r in cur]
        return Catalog(conteos, ubicaciones, productos)

    def run_batch(self, origen: str) -> tuple[int, int]:
        """Ejecuta PKG_BATCH.PROCESAR_PENDIENTES y devuelve ``(procesados, errores)`` de esa corrida.

        Llamar solo con la sesión ya cerrada: el procedimiento hace COMMIT.
        """
        conn = self._connection()
        cur = conn.cursor()
        cur.execute("SELECT NVL(MAX(id), 0) FROM log_batch")
        before = cur.fetchone()[0]
        cur.callproc("pkg_batch.procesar_pendientes", [origen])
        # La bitácora de ESTA corrida: posterior a la marca y con nuestro origen (el job usa 'JOB').
        cur.execute(
            "SELECT procesados, errores FROM ("
            "  SELECT procesados, errores FROM log_batch WHERE id > :b AND origen = :o ORDER BY id DESC"
            ") WHERE ROWNUM = 1",
            b=before,
            o=origen,
        )
        row = cur.fetchone()
        return (int(row[0]), int(row[1])) if row else (0, 0)

    def open_sync(self, uuid: str) -> int:
        conn = self._connection()
        cur = conn.cursor()
        out = cur.var(int)
        cur.execute(
            "INSERT INTO sync_sesiones (uuid_dispositivo) VALUES (:u) RETURNING id INTO :id",
            u=uuid,
            id=out,
        )
        conn.commit()
        return int(out.getvalue()[0])

    def close_sync(self, id: int, recibidos: int, aceptados: int) -> None:
        conn = self._connection()
        conn.cursor().execute(
            "UPDATE sync_sesiones SET fin = SYSTIMESTAMP, recibidos = :r, aceptados = :a WHERE id = :i",
            r=recibidos,
            a=aceptados,
            i=id,
        )
        conn.commit()
