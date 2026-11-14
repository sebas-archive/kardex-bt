"""Protocolo de líneas entre el móvil y el PC (ver docs/protocolo.md).

Una línea por mensaje: ``KIND|campo|campo...*CRC32`` terminada en ``\\n``. Los campos de texto
libre se codifican con ``encode_text``. El CRC32 (8 hex mayúsculas) cubre los bytes UTF-8 que
preceden al último ``*``. Máximo 4000 bytes por línea (sin el ``\\n``, incluido el CRC).
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
import zlib
from dataclasses import dataclass

MAX_LINE_BYTES = 4000

# Cantidad mínima de partes (incluido el KIND) que exige cada tipo de mensaje.
_MIN_PARTS = {
    "HELLO": 4,
    "ACCT": 3,
    "ACCTST": 5,
    "REC": 9,
    "FOTO": 6,
    "FOTOOK": 2,
    "FOTOERR": 3,
    "END": 2,
    "READY": 3,
    "CATTAREA": 8,
    "CATITEM": 4,
    "INICIO": 2,
    "CATPROD": 5,
    "CAT_END": 1,
    "ACK": 2,
    "NAK": 3,
    "BYE": 3,
}

# Versión del protocolo que viaja en HELLO. La 2 quitó la ubicación del REC y el mensaje CATUBIC.
# La 3 añadió ACCT/ACCTST: el móvil identifica la cuenta del operador y el PC responde su estado.
# La 4 cambió CATCONTEO por CATTAREA + CATITEM (las tareas del operador) y añadió INICIO (el móvil empezó una tarea).
# La 5 añadió los dañados al final del REC y las fotos (FOTO / FOTOOK / FOTOERR), que van tras las lecturas.
PROTOCOL_VERSION = "5"

_CRC_HEX = re.compile(rb"[0-9A-F]{8}")
_ESCAPES = {"%25": "%", "%7C": "|", "%0D": "\r", "%0A": "\n"}
_ESCAPE_RE = re.compile(r"%(?:25|7C|0D|0A)")


class FrameError(Exception):
    """Línea inválida. ``reason`` es ``CRC``, ``FORMAT`` o ``LINEA_LARGA``."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class Message:
    kind: str
    fields: list[str]


@dataclass(frozen=True)
class Rec:
    seq: int
    ts_ms: int
    id_conteo: str
    sku: str
    cantidad: str
    operador: str
    nota: str
    danados: str = ""   # protocolo 5: cuántas de las unidades contadas están dañadas («» si no se indicó)

    @classmethod
    def from_message(cls, m: Message) -> Rec:
        f = m.fields
        if m.kind != "REC" or len(f) != 8:
            raise FrameError("FORMAT", "REC exige exactamente 8 campos")
        try:
            seq, ts_ms = int(f[0]), int(f[1])
        except ValueError:
            raise FrameError("FORMAT", "seq y epoch_ms deben ser enteros") from None
        return cls(seq, ts_ms, f[2], f[3], f[4], f[5], f[6], f[7])

    def to_raw(self) -> str:
        """La línea REC tal como viaja por el cable, sin el CRC."""
        parts = [
            "REC",
            str(self.seq),
            str(self.ts_ms),
            *(
                encode_text(x)
                for x in (
                    self.id_conteo,
                    self.sku,
                    self.cantidad,
                    self.operador,
                    self.nota,
                    self.danados,
                )
            ),
        ]
        return "|".join(parts)


FOTO_PARTE = 2700   # caracteres de base64 por línea FOTO: con la cabecera queda lejos de los 4000 bytes


def foto_lineas(seq: int, datos: bytes, tam: int = FOTO_PARTE) -> list[list[str]]:
    """Las líneas FOTO (sin CRC de línea) de una foto: ``FOTO|seq|parte|total|crc32 del archivo|base64``."""
    b64 = base64.b64encode(datos).decode("ascii")
    trozos = [b64[i:i + tam] for i in range(0, len(b64), tam)] or [""]
    crc = f"{zlib.crc32(datos) & 0xFFFFFFFF:08X}"
    return [["FOTO", str(seq), str(n), str(len(trozos)), crc, t] for n, t in enumerate(trozos, start=1)]


def encode_text(s: str) -> str:
    return (
        s.replace("%", "%25")
        .replace("|", "%7C")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )


def decode_text(s: str) -> str:
    return _ESCAPE_RE.sub(lambda m: _ESCAPES[m.group(0)], s)


def frame(fields: list[str]) -> bytes:
    """Arma la línea. ``fields[0]`` es el KIND; el resto ya viene codificado."""
    body = "|".join(fields).encode("utf-8")
    return body + b"*" + b"%08X" % (zlib.crc32(body) & 0xFFFFFFFF) + b"\n"


def parse(line: bytes) -> Message:
    if line.endswith(b"\n"):
        line = line[:-1]
    if len(line) > MAX_LINE_BYTES:
        raise FrameError("LINEA_LARGA", f"{len(line)} bytes")
    star = line.rfind(b"*")
    if star < 0 or not _CRC_HEX.fullmatch(line[star + 1 :]):
        raise FrameError("FORMAT", "falta el CRC")
    body, crc_hex = line[:star], line[star + 1 :]
    if zlib.crc32(body) & 0xFFFFFFFF != int(crc_hex, 16):
        raise FrameError("CRC")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise FrameError("FORMAT", "UTF-8 inválido") from None
    parts = text.split("|")
    minimum = _MIN_PARTS.get(parts[0])
    if minimum is None:
        raise FrameError("FORMAT", f"tipo desconocido {parts[0]!r}")
    if len(parts) < minimum:
        raise FrameError("FORMAT", f"{parts[0]} exige {minimum} partes, llegaron {len(parts)}")
    return Message(kind=parts[0], fields=[decode_text(p) for p in parts[1:]])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m btsync.protocol",
        description="Arma o lee líneas del protocolo (útil para pruebas manuales por Bluetooth).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--frame",
        nargs="+",
        metavar="CAMPO",
        help="KIND seguido de sus campos en TEXTO PLANO (se codifican solos); imprime la línea con CRC",
    )
    group.add_argument("--parse", metavar="LINEA", help="valida una línea e imprime su tipo y campos")
    args = parser.parse_args(argv)

    if args.frame:
        kind, *rest = args.frame
        sys.stdout.buffer.write(frame([kind, *(encode_text(x) for x in rest)]))
        sys.stdout.buffer.flush()
        return 0
    try:
        msg = parse(args.parse.encode("utf-8"))
    except FrameError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(msg.kind, msg.fields)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
