"""Una sincronización con un teléfono: HELLO → READY + catálogo → REC* → END → BYE.

La sesión NO ejecuta el batch (D9): termina en BYE y quien la creó decide qué hacer después.
Las reglas de ACK, NAK y retroceso están en docs/protocolo.md.
"""

from __future__ import annotations

import time
from typing import Callable

import oracledb

from .protocol import FrameError, Message, Rec, encode_text, frame, parse
from .store import Store
from .transports.base import Connection

COMMIT_EVERY = 25


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

    # ------------------------------------------------------------------ API
    def run(self) -> None:
        try:
            self._run()
        except oracledb.Error:
            self._db_unavailable()
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
        if msg.kind != "HELLO" or msg.fields[0] != "1":
            self._send(["NAK", "0", "FORMAT"])
            return False
        self.uuid, name = msg.fields[1], msg.fields[2]
        self.on_event("hello", {"uuid": self.uuid, "nombre": name})
        self.store.register_device(self.uuid, name)
        self.sync_id = self.store.open_sync(self.uuid)
        last = self.store.last_seq(self.uuid)
        self.expected, self.last_acked = last + 1, last
        self._send(["READY", str(last), str(self.now_ms())])
        catalog = self.store.catalog()
        for fields in catalog.conteos:
            self._send(["CATCONTEO", *map(encode_text, fields)])
        for fields in catalog.ubicaciones:
            self._send(["CATUBIC", *map(encode_text, fields)])
        for fields in catalog.productos:
            self._send(["CATPROD", *map(encode_text, fields)])
        self._send(["CAT_END"])
        return True

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

    def _db_unavailable(self) -> None:
        try:
            self.store.rollback()
        except oracledb.Error:
            pass
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
