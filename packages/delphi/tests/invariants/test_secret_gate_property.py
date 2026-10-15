"""Finite secret check: one percent-decode, one \\uXXXX decode, and both orders."""
from __future__ import annotations

import json
import random
import re
import string
import subprocess
from pathlib import Path

from service import egress

ROOT = Path(__file__).resolve().parents[4]
BRIDGE = ROOT / "packages" / "delphi" / "scripts" / "bridge.mjs"
OUTSIDE = (
    "A second decode, HTML entities, and marks that are not controls "
    "or format characters are outside this check."
)


def _percent(text):
    return re.sub(r"%([0-9A-Fa-f]{2})", lambda match: chr(int(match.group(1), 16)), text)


def _unicode(text):
    return re.sub(r"\\u([0-9A-Fa-f]{4})", lambda match: chr(int(match.group(1), 16)), text)


def exposed(text, secret):
    folded = secret.casefold()
    if not folded:
        return False
    parts = [folded, *(folded[index:index + 12] for index in range(max(0, len(folded) - 11)))]
    percent, uni = _percent(text), _unicode(text)
    forms = (text, percent, uni, _unicode(percent), _percent(uni))
    return any(part in form.casefold() for form in forms for part in parts)


def _encode_percent(text):
    return "".join(f"%{ord(char):02X}" for char in text)


def _encode_unicode(text):
    return "".join(f"\\u{ord(char):04x}" for char in text)


def cases():
    rng = random.Random(15)
    alphabet = string.ascii_letters + string.digits + "%\\-_"
    built = []
    for index in range(520):
        secret = "Sg" + "".join(rng.choice(alphabet) for _ in range(rng.randint(14, 62)))
        mode = index % 6
        if mode == 5:
            built.append({"secret": secret, "text": "ordinary market question", "hit": False})
            continue
        text = secret
        if mode == 1:
            text = _encode_percent(secret)
        elif mode == 2:
            text = _encode_unicode(secret)
        elif mode == 3:
            text = _encode_percent(_encode_unicode(secret))
        elif mode == 4:
            text = _encode_unicode(_encode_percent(secret))
        built.append({"secret": secret, "text": text, "hit": True})
    return built


def ask_bridge(rows):
    script = (
        "import { readFileSync } from 'node:fs';\n"
        f"import {{ holdsSecret }} from {json.dumps(BRIDGE.as_uri())};\n"
        "const cases = JSON.parse(readFileSync(0, 'utf8'));\n"
        "const out = cases.map((item) => holdsSecret(item.text, item.secret));\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    done = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps(rows).encode(),
        capture_output=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()[-500:]
    return json.loads(done.stdout)


def test_secret_gate_matches_one_decode_on_random_text(monkeypatch):
    rows = cases()
    assert len(rows) >= 500
    assert sum(row["hit"] for row in rows) >= 400
    bridge = ask_bridge(rows)
    assert len(bridge) == len(rows)
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "placeholder-not-used")
    for row, held in zip(rows, bridge):
        assert exposed(row["text"], row["secret"]) is row["hit"]
        assert held is row["hit"]
        monkeypatch.setenv("DELPHI_API_ACCESS_KEY", row["secret"])
        text = egress(
            "delphi_get_market",
            {
                "ok": False,
                "tool": "delphi_get_market",
                "error_type": "upstream",
                "message": row["text"],
                "retryable": True,
            },
        )
        if row["hit"]:
            assert json.loads(text)["error_type"] == "internal"
            assert not exposed(text, row["secret"])
        else:
            assert json.loads(text)["error_type"] == "upstream"
            assert row["text"] in text


def test_html_second_decode_and_other_marks_are_out_of_scope():
    sentence = " ".join(OUTSIDE.split())
    docs = [
        ROOT / "SECURITY.md",
        ROOT / "README.md",
        ROOT / "packages" / "delphi" / "README.md",
    ]
    for path in docs:
        assert sentence in " ".join(path.read_text().split())
    plugin = " ".join((ROOT / "packages" / "delphi" / "plugin.yaml").read_text().split())
    assert "fixed sentence" in plugin
    assert "outside this check" in plugin
