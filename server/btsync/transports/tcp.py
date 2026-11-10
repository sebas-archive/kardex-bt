"""Transporte TCP: el mismo flujo que el Bluetooth, sin radio. Sirve para pruebas y para la demo
de respaldo con ``tools/fake_phone.py``."""

from __future__ import annotations

import socket
import sys
import threading
from typing import Callable

from ..protocol import frame
from .base import Connection

_READ_CAP = 65536  # tope de lectura por línea; el protocolo admite 4000 bytes


class TcpConnection:
    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._rfile = sock.makefile("rb")

    def readline(self) -> bytes | None:
        try:
            line = self._rfile.readline(_READ_CAP)
            if line and not line.endswith(b"\n") and len(line) >= _READ_CAP:
                # Línea desmesurada: se devuelve el primer tramo (la sesión responde LINEA_LARGA)
                # y se descarta el resto hasta el salto, sin acumularlo en memoria.
                while True:
                    rest = self._rfile.readline(_READ_CAP)
                    if not rest or rest.endswith(b"\n"):
                        break
        except (OSError, ValueError):
            return None
        return line or None

    def write(self, data: bytes) -> None:
        self._sock.sendall(data)

    def abort(self) -> None:
        """Corta la conexión desde otro hilo: desbloquea un ``readline`` en curso."""
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def close(self) -> None:
        for closer in (self._rfile.close, self._sock.close):
            try:
                closer()
            except OSError:
                pass


class TcpTransport:
    """Implementa ``Transport``. Con ``port=0`` el sistema elige un puerto libre (ver ``port``)."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._requested_port = port
        self._server: socket.socket | None = None
        self._stopping = threading.Event()
        self._lock = threading.Lock()
        self._active: TcpConnection | None = None
        self._accept_thread: threading.Thread | None = None
        self._handler_thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        """True mientras haya una sincronización en curso."""
        return self._active is not None

    def begin_pairing(self, on_passkey) -> None:
        """TCP no empareja: no hay código que confirmar."""

    def serve(self, on_connection: Callable[[Connection], None]) -> None:
        if self._server is not None:
            raise RuntimeError("el transporte ya está sirviendo")
        server = socket.create_server((self.host, self._requested_port))
        server.settimeout(0.2)  # para poder atender stop() sin quedar bloqueado en accept()
        self._server = server
        self.port = server.getsockname()[1]
        self._stopping = threading.Event()
        self._accept_thread = threading.Thread(
            target=self._accept_loop, args=(server, self._stopping, on_connection),
            name="tcp-accept", daemon=True,
        )
        self._accept_thread.start()

    def stop(self) -> None:
        self._stopping.set()
        server, self._server = self._server, None
        if server is not None:
            server.close()
        with self._lock:
            active = self._active
        if active is not None:
            active.abort()
        current = threading.current_thread()
        for thread in (self._accept_thread, self._handler_thread):
            if thread is not None and thread is not current:
                thread.join(timeout=5)
        self._accept_thread = self._handler_thread = None

    # ------------------------------------------------------------- internos
    def _accept_loop(self, server, stopping, on_connection) -> None:
        while not stopping.is_set():
            try:
                sock, _addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            sock.settimeout(None)
            with self._lock:
                busy = self._active is not None
                if not busy:
                    conn = TcpConnection(sock)
                    self._active = conn
            if busy:
                threading.Thread(target=_reject_busy, args=(sock,), daemon=True).start()
                continue
            self._handler_thread = threading.Thread(
                target=self._handle, args=(conn, on_connection), name="tcp-session", daemon=True
            )
            self._handler_thread.start()

    def _handle(self, conn: TcpConnection, on_connection) -> None:
        try:
            on_connection(conn)
        except Exception as exc:  # un fallo de una sesión no debe tumbar el transporte
            print(f"[tcp] la sesión terminó con error: {exc!r}", file=sys.stderr)
        finally:
            conn.close()
            with self._lock:
                self._active = None


def _reject_busy(sock: socket.socket) -> None:
    """D19: ya hay una sincronización; se avisa y se cierra con cortesía (sin RST)."""
    try:
        sock.sendall(frame(["NAK", "0", "OCUPADO"]))
        sock.shutdown(socket.SHUT_WR)
        sock.settimeout(1.0)
        while sock.recv(4096):
            pass
    except OSError:
        pass
    finally:
        sock.close()
