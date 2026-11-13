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
    productos: list[tuple[str, str, str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class EstadoCuenta:
    """Lo que el PC responde en ACCTST: estado de la cuenta del operador, su rol y el motivo (si la rechazaron o suspendieron)."""

    estado: str
    rol: str | None
    motivo: str | None


CONFLICTO_ESCRITORIO = "Ese usuario ya existe en el PC"
OTRO_TELEFONO = "Esta cuenta está vinculada a otro teléfono. Pide al administrador que la desvincule."
SIN_PERMISO = "Tu rol no tiene permiso para sincronizar. Habla con el administrador."


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

    def sincronizar_cuenta(self, usuario: str, nombre: str, uuid: str) -> EstadoCuenta:
        """La cuenta del operador que sincroniza desde el teléfono ``uuid``.

        - Si no existe se crea PENDIENTE (origen MOVIL, sin clave del PC) y queda **vinculada a ese teléfono**.
        - Un usuario que ya existe como cuenta del PC no se toca: RECHAZADO con el motivo.
        - Desde otro teléfono la cuenta no entrega lecturas (SUSPENDIDO con el motivo) hasta que el administrador
          la desvincule: sin esto, cualquiera podría registrar en su teléfono el usuario de un operador aprobado.
        - Si la matriz quita al rol Operador el permiso de Bluetooth, tampoco (SUSPENDIDO con el motivo).
        """
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO usuarios (usuario, nombre, clave_hash, estado, origen, uuid_dispositivo) "
                        "VALUES (:u, :n, '-', 'PENDIENTE', 'MOVIL', :d)", u=usuario, n=nombre, d=uuid)
            conn.commit()
        except oracledb.IntegrityError as exc:
            conn.rollback()
            if "ORA-00001" not in str(exc):   # ya existía (o la creó otra conexión a la vez): se lee abajo
                raise
        cur.execute("SELECT estado, rol, motivo, origen, uuid_dispositivo FROM usuarios WHERE usuario = :u", u=usuario)
        estado, rol, motivo, origen, vinculado = cur.fetchone()
        if origen != "MOVIL":
            return EstadoCuenta("RECHAZADO", None, CONFLICTO_ESCRITORIO)
        if vinculado is None:   # el administrador la desvinculó: la toma este teléfono
            cur.execute("UPDATE usuarios SET uuid_dispositivo = :d WHERE usuario = :u AND uuid_dispositivo IS NULL",
                        d=uuid, u=usuario)
            conn.commit()
        elif vinculado != uuid:
            return EstadoCuenta("SUSPENDIDO", rol, OTRO_TELEFONO)
        if estado == "ACTIVO" and not self._operador_puede_sincronizar(cur):
            return EstadoCuenta("SUSPENDIDO", rol, SIN_PERMISO)
        return EstadoCuenta(estado, rol, motivo)

    @staticmethod
    def _operador_puede_sincronizar(cur) -> bool:
        """Nivel de GESTION en el módulo Bluetooth para el rol Operador (matriz de permisos). Sin fila: el inicial (sí)."""
        try:
            cur.execute("SELECT nivel FROM permisos WHERE rol = 'OPERADOR' AND modulo = 'bluetooth'")
        except oracledb.DatabaseError:   # base anterior a la tabla de permisos
            return True
        fila = cur.fetchone()
        return fila is None or fila[0] == "GESTION"

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

    def close(self) -> None:
        """Cierra la conexión (la XE tiene pocos procesos: no hay que esperar al recolector de basura)."""
        if self._conn is not None:
            try:
                self._conn.close()
            except oracledb.Error:
                pass
            self._conn = None

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
        cur.execute("SELECT sku, nombre, categoria, unidad FROM productos ORDER BY sku")
        productos = [(r[0], r[1], r[2], r[3]) for r in cur]
        return Catalog(conteos, productos)

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
