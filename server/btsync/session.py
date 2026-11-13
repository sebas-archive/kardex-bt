"""Una sincronización con un teléfono: HELLO → ACCT → ACCTST + READY + catálogo → REC* → END → BYE.

Solo una cuenta ACTIVO entrega lecturas: con otro estado cada hueco recibe ``NAK|seq|CUENTA_NO_ACTIVA`` y el
móvil conserva lo que tenía en su búfer. El estado se lee al empezar y vale para toda la sesión.

La sesión NO ejecuta el batch (D9): termina en BYE y quien la creó decide qué hacer después.
Las reglas de ACK, NAK y retroceso están en docs/protocolo.md.
"""

from __future__ import annotations

import re
import time
from typing import Callable

import oracledb

from .protocol import PROTOCOL_VERSION, FrameError, Message, Rec, encode_text, frame, parse
from .store import Store
from .transports.base import Connection

COMMIT_EVERY = 25
USUARIO = re.compile(r"[a-z0-9._-]{3,30}")   # como desktop/app/auth.py (el móvil admite hasta 20)
MAX_NOMBRE = 60


def time_ms() -> int:
    return int(time.time() * 1000)


class Session:
    def __init__(
        self,
        conn: Connection,
        store: Store,
        on_event: Callable[[str, dict], None],
        now_ms: Callable[[], int] = time_ms,
    ) -> None:
        self.conn = conn
        self.store = store
        self.on_event = on_event
        self.now_ms = now_ms
        self.uuid: str | None = None
        self.sync_id: int | None = None
        self.expected = 1            # próximo seq que se acepta
        self.last_acked = 0
        self.pending = 0             # insertados sin COMMIT
        self.received = 0            # REC bien formados vistos
        self.inserted = 0            # filas nuevas en esta sesión
        self.rejected = 0            # NAK enviados
        self.nak_active = False      # go-back-N: se ignora todo hasta el seq esperado
        self.cuenta_activa = False   # según ACCTST: sin cuenta ACTIVO no se aceptan REC

    # ------------------------------------------------------------------ API
    def run(self) -> None:
        try:
            self._run()
        except oracledb.Error:
            self._db_unavailable()
        except OSError:
            # El canal murió al escribir: es un corte. Lo que no tuvo COMMIT se descarta,
            # para que la siguiente sesión no lo confirme por accidente.
            self._rollback_quietly()
        finally:
            self._close_sync()
            try:
                self.conn.close()
            except OSError:
                pass

    # ------------------------------------------------------------- internos
    def _send(self, fields: list[str]) -> None:
        self.conn.write(frame(fields))

    def _run(self) -> None:
        if not self._handshake():
            return
        while True:
            line = self.conn.readline()
            if line is None:  # corte: lo que no tuvo COMMIT se descarta
                self.store.rollback()
                return
            try:
                msg = parse(line)
            except FrameError as exc:
                self._reject(exc.reason)
                continue
            if msg.kind == "REC":
                self._on_rec(msg, line)
            elif msg.kind == "END":
                self._on_end()
                return
            else:
                self._reject("FORMAT")

    def _handshake(self) -> bool:
        line = self.conn.readline()
        if line is None:
            return False
        try:
            msg = parse(line)
        except FrameError as exc:
            self._send(["NAK", "0", exc.reason])
            return False
        if msg.kind != "HELLO" or msg.fields[0] != PROTOCOL_VERSION:
            self._send(["NAK", "0", "FORMAT"])
            return False
        self.uuid, name = msg.fields[1], msg.fields[2]
        cuenta = self._read_acct()
        if cuenta is None:
            self._send(["NAK", "0", "FORMAT"])
            return False
        usuario, nombre_operador = cuenta
        estado = self.store.sincronizar_cuenta(usuario, nombre_operador, self.uuid)
        self.cuenta_activa = estado.estado == "ACTIVO"
        self._send(["ACCTST", *map(encode_text, (usuario, estado.estado, estado.rol or "", estado.motivo or ""))])
        self.on_event("hello", {"uuid": self.uuid, "nombre": name, "operador": usuario, "cuenta": estado.estado})
        self.store.register_device(self.uuid, name)
        self.sync_id = self.store.open_sync(self.uuid)
        last = self.store.last_seq(self.uuid)
        self.expected, self.last_acked = last + 1, last
        self._send(["READY", str(last), str(self.now_ms())])
        catalog = self.store.catalog()
        for fields in catalog.conteos:
            self._send(["CATCONTEO", *map(encode_text, fields)])
        for fields in catalog.productos:
            self._send(["CATPROD", *map(encode_text, fields)])
        self._send(["CAT_END"])
        return True

    def _read_acct(self) -> tuple[str, str] | None:
        """La línea que sigue a HELLO debe ser ``ACCT|usuario|nombre``."""
        line = self.conn.readline()
        if line is None:
            return None
        try:
            msg = parse(line)
        except FrameError:
            return None
        if msg.kind != "ACCT":
            return None
        usuario, nombre = msg.fields[0], msg.fields[1].strip()
        # Las mismas reglas que los clientes: así no llegan a Oracle cuentas que nadie podría crear (ni ORA-12899).
        if not USUARIO.fullmatch(usuario) or not nombre or len(nombre) > MAX_NOMBRE:
            return None
        return usuario, nombre

    def _reject(self, reason: str) -> None:
        """Un único NAK por hueco; hasta que llegue el seq esperado lo demás se ignora."""
        if self.nak_active:
            return
        self._send(["NAK", str(self.expected), reason])
        self.rejected += 1
        self.nak_active = True

    def _on_rec(self, msg: Message, line: bytes) -> None:
        try:
            rec = Rec.from_message(msg)
        except FrameError as exc:
            self._reject(exc.reason)
            return
        self.received += 1
        if rec.seq < self.expected:  # duplicado: ya está persistido
            return
        if not self.cuenta_activa:
            self._reject("CUENTA_NO_ACTIVA")
            return
        if rec.seq > self.expected:
            self._reject("SECUENCIA")
            return
        raw = line.rstrip(b"\n")[: line.rstrip(b"\n").rfind(b"*")].decode("utf-8")
        if self.store.insert_staging(self.uuid, rec.seq, raw):
            self.inserted += 1
            self.on_event("progress", {"recibidos": self.inserted})
        self.expected += 1
        self.pending += 1
        self.nak_active = False
        if self.pending >= COMMIT_EVERY:
            self._commit_and_ack()

    def _commit_and_ack(self) -> None:
        self.store.commit()
        self.pending = 0
        last = self.expected - 1
        if last > self.last_acked:
            self._send(["ACK", str(last)])
            self.last_acked = last

    def _on_end(self) -> None:
        self._commit_and_ack()
        self._send(["BYE", str(self.inserted), str(self.rejected)])
        self.on_event("done", {"aceptados": self.inserted, "rechazados": self.rejected})

    def _rollback_quietly(self) -> None:
        try:
            self.store.rollback()
        except oracledb.Error:
            pass

    def _db_unavailable(self) -> None:
        self._rollback_quietly()
        try:
            self._send(["NAK", str(self.expected), "DB_NO_DISPONIBLE"])
        except OSError:
            pass

    def _close_sync(self) -> None:
        if self.sync_id is None:
            return
        try:
            self.store.close_sync(self.sync_id, self.received, self.inserted)
        except oracledb.Error:
            pass
