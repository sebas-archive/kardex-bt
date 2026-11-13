import json
import subprocess
import sys
from pathlib import Path

import pytest

from btsync.protocol import (
    FrameError,
    Message,
    Rec,
    decode_text,
    encode_text,
    frame,
    parse,
)

ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads(
    (ROOT / "docs" / "protocol-vectors.json").read_text(encoding="utf-8")
)["vectors"]
BY_NAME = {v["name"]: v for v in VECTORS}


def test_frame_matches_all_vectors():
    assert len(VECTORS) == 11
    for v in VECTORS:
        assert frame(v["frame_fields"]) == v["line"].encode("utf-8") + b"\n", v["name"]


def test_parse_matches_all_vectors():
    for v in VECTORS:
        msg = parse(v["line"].encode("utf-8") + b"\n")
        assert msg == Message(kind=v["kind"], fields=v["fields"]), v["name"]


def test_text_roundtrip_special_chars():
    original = "a|b\nc%ñ😀"
    encoded = encode_text(original)
    assert "|" not in encoded
    assert "\n" not in encoded
    assert decode_text(encoded) == original


def test_crc_mismatch_raises_crc():
    good = BY_NAME["ack"]["line"]
    assert good.endswith("6A8544FA")
    bad = good[:-1] + "B"
    with pytest.raises(FrameError) as exc:
        parse(bad.encode("utf-8") + b"\n")
    assert exc.value.reason == "CRC"


def test_too_few_fields_raises_format():
    line = frame(["REC", "1", "2"])  # CRC correcto, pero un REC necesita 9 campos
    with pytest.raises(FrameError) as exc:
        parse(line)
    assert exc.value.reason == "FORMAT"


def test_line_over_4000_bytes_raises_linea_larga():
    base = frame(["REC", "1", "2", "C", "S", "1", "Ana", ""])
    pad = 4000 - (len(base) - 1)  # el limite cuenta la linea sin el salto final
    exactly_4000 = frame(["REC", "1", "2", "C", "S", "1", "Ana", "x" * pad])
    assert len(exactly_4000) - 1 == 4000
    assert parse(exactly_4000).kind == "REC"  # 4000 bytes: todavia valido
    too_long = frame(["REC", "1", "2", "C", "S", "1", "Ana", "x" * (pad + 1)])
    with pytest.raises(FrameError) as exc:
        parse(too_long)
    assert exc.value.reason == "LINEA_LARGA"


def test_rec_to_raw_excludes_crc():
    simple = Rec.from_message(parse(BY_NAME["rec_simple"]["line"].encode("utf-8")))
    assert simple == Rec(
        seq=1,
        ts_ms=1731170400000,
        id_conteo="CONT-2026-11",
        sku="7701234000011",
        cantidad="12.5",
        operador="Ana",
        nota="ok",
    )
    assert (
        simple.to_raw()
        == "REC|1|1731170400000|CONT-2026-11|7701234000011|12.5|Ana|ok"
    )
    # Con texto raro: to_raw vuelve a producir la forma de cable (sin el CRC).
    special = Rec.from_message(parse(BY_NAME["rec_special_text"]["line"].encode("utf-8")))
    assert special.operador == "Ñandú|%"
    assert special.nota == "a|b\nc%😀"
    assert special.to_raw() == BY_NAME["rec_special_text"]["line"].split("*")[0]


def test_cli_frame_prints_vector():
    result = subprocess.run(
        [sys.executable, "-m", "btsync.protocol", "--frame", "HELLO", "3", "dev-0001", "Bodega Norte"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == BY_NAME["hello"]["line"] + "\n"


def test_acct_acctst_round_trip_con_crc():
    from btsync.protocol import PROTOCOL_VERSION
    assert PROTOCOL_VERSION == "3"
    suspendido = BY_NAME["acctst_suspendido"]
    msg = parse(suspendido["line"].encode("utf-8") + b"\n")
    assert msg.kind == "ACCTST" and msg.fields[3] == "Revisar | inventario al 100%\nhabla con el jefe"
    assert parse(BY_NAME["acctst_pendiente"]["line"].encode() + b"\n").fields == ["luis.ortiz", "PENDIENTE", "", ""]
    with pytest.raises(FrameError):
        parse(frame(["ACCT", "solo-usuario"]))          # ACCT exige usuario y nombre
    with pytest.raises(FrameError):
        parse(frame(["ACCTST", "luis", "ACTIVO"]))      # ACCTST exige 4 campos
