"""Contratos de transporte: la sesión solo conoce ``Connection``; quien acepta es ``Transport``."""

from __future__ import annotations

from typing import Callable, Protocol


class Connection(Protocol):
    """Un canal de bytes orientado a líneas con un teléfono."""

    def readline(self) -> bytes | None:
        """Siguiente línea (con su ``\\n``) o ``None`` si el otro lado cerró."""

    def write(self, data: bytes) -> None: ...

    def close(self) -> None: ...


class Transport(Protocol):
    """Acepta conexiones y se las entrega a ``on_connection``.

    ``serve`` no bloquea: empieza a aceptar y vuelve. ``on_connection`` se llama en un hilo
    del transporte, una vez por conexión aceptada, y la conexión se cierra cuando retorna.
    ``stop`` deja de aceptar y corta la conexión activa; después se puede volver a ``serve``.

    Contrato (D19): como máximo una conexión activa. Mientras haya una, las demás reciben
    ``frame(["NAK", "0", "OCUPADO"])`` y se cierran.
    """

    def serve(self, on_connection: Callable[[Connection], None]) -> None: ...

    def stop(self) -> None: ...
