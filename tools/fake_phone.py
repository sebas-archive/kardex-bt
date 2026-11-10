#!/usr/bin/env python3
"""Teléfono simulado: hace el conteo físico de tools/truth.json y lo sincroniza por TCP.

Se comporta como la app Android: guarda primero en su "outbox" (un archivo JSON), reanuda desde
el ``READY|seq`` del servidor, envía en ventanas de 50, retrocede ante un ``NAK`` (go-back-N) y
corrige las marcas de tiempo con la hora del servidor sin tocar la hora original (D15).

Ejemplo:
    python tools/fake_phone.py --host localhost --port 9000 --seed 42 --dirty
Códigos de salida: 0 todo confirmado, 1 quedó algo pendiente, 2 sin conexión, 3 PC ocupado.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    from btsync.protocol import encode_text, frame, parse
except ImportError:  # ejecutado fuera del contenedor
    sys.path.insert(0, str(ROOT / "server"))
    from btsync.protocol import encode_text, frame, parse

WINDOW = 50           # REC sin confirmar que se permiten en vuelo
MAX_SESSIONS = 5      # reconexiones antes de rendirse
ERROR_RATE = 0.03     # ~3 % de las lecturas tienen un error de conteo


def generar_lecturas(seed: int, operador: str, dirty: bool, reloj_ms: int) -> list[dict]:
    truth = json.loads((ROOT / "tools" / "truth.json").read_text(encoding="utf-8"))
    rng = random.Random(seed)
    conteo = truth["conteo"]
    lecturas: list[dict] = []

    def add(ubicacion: str, sku: str, cantidad: int, nota: str = "") -> None:
        lecturas.append({
            "seq": len(lecturas) + 1,
            "ts_original_ms": reloj_ms + len(lecturas),  # reloj del teléfono al capturar
            "id_conteo": conteo,
            "ubicacion": ubicacion,
            "sku": sku,
            "cantidad": str(cantidad),
            "operador": operador,
            "nota": nota,
        })

    for fila in truth["fisico"]:
        cantidad = fila["cantidad"]
        if rng.random() < ERROR_RATE:
            cantidad = max(0, cantidad + rng.choice([-2, -1, 1, 2]))
        add(fila["ubicacion"], fila["sku"], cantidad)

    if dirty:
        base = truth["fisico"]
        # Tres lecturas que el batch debe marcar como ERROR...
        add(base[0]["ubicacion"], "SKU-NO-EXISTE", 5, "producto sin alta")
        add("Z-99", base[0]["sku"], 3, "ubicación inexistente")
        add("Z-99", base[0]["sku"], 4, "recuento en ubicación inexistente")
        # ...y tres recuentos válidos, que reemplazan a la lectura anterior.
        for fila in rng.sample(base, 3):
            add(fila["ubicacion"], fila["sku"], fila["cantidad"], "recuento")
    return lecturas


def guardar(path: Path, estado: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)  # atómico: un corte nunca deja el archivo a medias


def leer(rfile):
    line = rfile.readline()
    if not line:
        raise ConnectionError("el servidor cerró la conexión")
    return parse(line)


def una_sesion(args, estado: dict, reloj) -> str:
    """Una conexión completa. Devuelve 'BYE' u 'OCUPADO'; lanza OSError si se corta."""
    lecturas = estado["lecturas"]
    total = len(lecturas)
    with socket.create_connection((args.host, args.port), timeout=15) as sock:
        rfile = sock.makefile("rb")
        sock.sendall(frame(["HELLO", "1", encode_text(args.uuid), encode_text(args.name)]))
        msg = leer(rfile)
        if msg.kind == "NAK":
            if msg.fields[1] == "OCUPADO":
                return "OCUPADO"
            raise ConnectionError(f"el servidor rechazó el saludo: {msg.fields}")
        ultimo = int(msg.fields[0])
        # D15: un único desfase por sincronización, calculado contra el reloj del teléfono AHORA.
        offset = int(msg.fields[1]) - reloj()
        estado["confirmado_hasta"] = ultimo
        guardar(args.state_file, estado)
        while leer(rfile).kind != "CAT_END":  # el catálogo (sin stock) no se usa aquí
            pass

        confirmado = ultimo
        siguiente = ultimo + 1
        fin_enviado = False
        while True:
            while siguiente <= total and (siguiente - 1 - confirmado) < WINDOW:
                l = lecturas[siguiente - 1]
                sock.sendall(frame([
                    "REC", str(l["seq"]), str(l["ts_original_ms"] + offset),
                    *(encode_text(l[k]) for k in ("id_conteo", "ubicacion", "sku", "cantidad", "operador", "nota")),
                ]))
                siguiente += 1
                if args.delay_ms:
                    time.sleep(args.delay_ms / 1000)
            if siguiente > total and not fin_enviado:
                sock.sendall(frame(["END", str(max(0, total - ultimo))]))
                fin_enviado = True

            msg = leer(rfile)
            if msg.kind == "ACK":
                confirmado = int(msg.fields[0])
                estado["confirmado_hasta"] = confirmado
                guardar(args.state_file, estado)
            elif msg.kind == "NAK":
                print(f"NAK {msg.fields}", file=sys.stderr)
                if not fin_enviado:  # go-back-N: se reenvía desde lo que el servidor espera
                    siguiente = int(msg.fields[0])
            elif msg.kind == "BYE":
                print(f"BYE|{msg.fields[0]}|{msg.fields[1]}")
                return "BYE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--dirty", action="store_true", help="agrega 3 lecturas con error y 3 recuentos")
    parser.add_argument("--skew-ms", type=int, default=0, help="adelanto (+) o atraso (-) del reloj del teléfono")
    parser.add_argument("--operator", default="Ana")
    parser.add_argument("--uuid", default="fake-phone-0001")
    parser.add_argument("--name", default="Teléfono simulado")
    parser.add_argument("--state-file", type=Path, default=None, help="outbox persistente (JSON)")
    parser.add_argument("--delay-ms", type=int, default=0, help="pausa entre REC (para ensayar cortes)")
    args = parser.parse_args()
    if args.state_file is None:
        args.state_file = Path(tempfile.gettempdir()) / f"fake_phone_{args.uuid}.json"

    def reloj() -> int:
        return int(time.time() * 1000) + args.skew_ms

    if args.state_file.exists():
        estado = json.loads(args.state_file.read_text(encoding="utf-8"))
    else:
        estado = {
            "uuid": args.uuid,
            "confirmado_hasta": 0,
            "lecturas": generar_lecturas(args.seed, args.operator, args.dirty, reloj()),
        }
        guardar(args.state_file, estado)
    total = len(estado["lecturas"])

    for intento in range(1, MAX_SESSIONS + 1):
        try:
            resultado = una_sesion(args, estado, reloj)
        except ConnectionRefusedError as exc:
            print(f"sin conexión con {args.host}:{args.port}: {exc}", file=sys.stderr)
            return 2
        except (OSError, ValueError) as exc:
            print(f"corte en el intento {intento}: {exc}", file=sys.stderr)
            time.sleep(0.3)
            continue
        if resultado == "OCUPADO":
            print("OCUPADO: el PC ya está sincronizando otro teléfono", file=sys.stderr)
            return 3
        if estado["confirmado_hasta"] >= total:
            print(f"confirmadas {total} lecturas", file=sys.stderr)
            return 0
    print(f"quedaron pendientes {total - estado['confirmado_hasta']} lecturas", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
