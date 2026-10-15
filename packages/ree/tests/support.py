"""Shared fixtures. The fake docker is an executable, not a Python mock."""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal
from pathlib import Path

from contract import make_sample

FAKE = r'''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path

argv = sys.argv[1:]
log = Path(sys.argv[0]).resolve().parent / "calls.log"
with log.open("a") as handle:
    handle.write(json.dumps(argv) + "\n")
here = Path(sys.argv[0]).resolve().parent

def mounts():
    found = {}
    index = 0
    while index < len(argv):
        if argv[index] == "-v" and index + 1 < len(argv):
            host, _, rest = argv[index + 1].partition(":")
            found[rest.split(":")[0]] = host
            index += 2
            continue
        index += 1
    return found

def flag(name):
    if name in argv:
        slot = argv.index(name)
        if slot + 1 < len(argv):
            return argv[slot + 1]
    return ""

def skip_context(args):
    if args[:1] == ["--context"] and len(args) >= 3:
        return args[2:]
    return args

if skip_context(argv)[:1] == ["rm"]:
    raise SystemExit(0)
if skip_context(argv)[:1] == ["ps"]:
    marker = here / "leftover"
    if marker.exists():
        sys.stdout.write(marker.read_text())
    raise SystemExit(0)
if argv[:1] == ["kill"]:
    raise SystemExit(0)
if argv[:1] == ["sleep"]:
    time.sleep(30)
if argv[:1] == ["huge"]:
    sys.stdout.write("x" * 300000)
    raise SystemExit(0)
if argv[:1] == ["env"]:
    sys.stdout.write(json.dumps(sorted(os.environ)))
    raise SystemExit(0)
def probe_kind():
    path = here / "probe-kind"
    if path.exists():
        return path.read_text().strip()
    return ""

def rest_args():
    if argv[:1] == ["--context"] and len(argv) >= 3:
        return argv[2:]
    return argv

rest = rest_args()
ctx = argv[1] if argv[:1] == ["--context"] and len(argv) >= 3 else ""
if rest[:1] == ["info"]:
    if (here / "daemon-down").exists() or probe_kind() == "down":
        sys.stderr.write("failed to connect to the docker API\n")
        raise SystemExit(1)
    path = here / "memtotal"
    sys.stdout.write((path.read_text().strip() if path.exists() else "12514787328") + "\n")
    raise SystemExit(0)
if rest[:2] == ["context", "show"]:
    sys.stdout.write("colima\n")
    raise SystemExit(0)
if rest[:2] == ["context", "inspect"]:
    path = here / "context-host"
    sys.stdout.write((path.read_text().strip() if path.exists() else "unix:///tmp/missing.sock") + "\n")
    raise SystemExit(0)

if rest[:1] == ["version"]:
    down = (here / "daemon-down").exists() or probe_kind() == "down"
    if ctx and (here / ("daemon-down-" + ctx)).exists():
        down = True
    if down:
        sys.stderr.write("failed to connect to the docker API\n")
        raise SystemExit(1)
    sys.stdout.write("29.5.2\n")
    raise SystemExit(0)
if rest[:2] == ["image", "inspect"]:
    missing = (here / "missing-image").exists() or probe_kind() == "noimage"
    if ctx and (here / ("missing-image-" + ctx)).exists():
        missing = True
    if missing:
        sys.stderr.write("No such image\n")
        raise SystemExit(1)
    digest = "sha256:ad683947a8c3a0fcb2567280268c0b01f17652a38c3f76838a398bd79aaff0ec"
    sys.stdout.write(digest + " [\"gensynai/ree@" + digest + "\"]\n")
    raise SystemExit(0)

mounted = mounts()
data = {}
host = mounted.get("/mnt/receipt/receipt.json")
if host:
    data = json.loads(Path(host).read_text())
prompt = ""
if isinstance(data.get("input"), dict):
    prompt = data["input"].get("prompt") or ""
if not prompt:
    prompt = flag("--prompt-text")

def note_cid():
    path = flag("--cidfile")
    if path:
        Path(path).write_text("ab" * 32)

def mark(kind):
    (here / "probe-kind").write_text(kind)

def hash_lines(status="PASS"):
    summary = "ALL CHECKS PASSED" if status == "PASS" else "SOME CHECKS FAILED"
    sys.stdout.write(
        "I gensyn_sdk.cli:   prompt_hash: " + status + "\n"
        "  tools_hash: PASS\n"
        "  parameters_hash: PASS\n"
        "  receipt_hash: PASS\n"
        "receipt validation: " + summary + "\n"
    )

def write_one(body, name="receipt_20261011_120000.json"):
    tasks = mounted["/mnt/tasks"]
    folder = Path(tasks) / "model" / "metadata"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(body))

def template():
    body = json.loads((here / "template.json").read_text())
    asked = flag("--prompt-text")
    if asked:
        body["input"]["prompt"] = asked
    model = flag("--model-name")
    if model:
        body["model"]["name"] = model
    return body

PRESTART = {
    "SCENARIO daemon": ("down", 1),
    "SCENARIO cannot-connect": ("down", 1),
    "SCENARIO denied": ("down", 1),
    "SCENARIO no-image": ("noimage", 125),
    "SCENARIO other-image": ("", 125),
    "SCENARIO conflict": ("", 125),
}
command = ""
if "validate" in argv:
    command = "validate"
elif "verify" in argv:
    command = "verify"
elif "run-all" in argv:
    command = "run-all"

if command == "validate":
    if prompt in PRESTART:
        kind, code = PRESTART[prompt]
        if kind:
            mark(kind)
        raise SystemExit(code)
    note_cid()
    if prompt == "SCENARIO silent":
        raise SystemExit(0)
    if prompt == "SCENARIO disagree":
        hash_lines("PASS")
        raise SystemExit(1)
    if prompt == "SCENARIO fail-prompt":
        hash_lines("FAIL")
        raise SystemExit(1)
    hash_lines("PASS")
    raise SystemExit(0)

if command and prompt in PRESTART:
    kind, code = PRESTART[prompt]
    if kind:
        mark(kind)
    raise SystemExit(code)

if command == "verify" and prompt == "SCENARIO context-blind":
    raise SystemExit(125)
if command == "verify" and prompt == "SCENARIO killed":
    note_cid()
    sys.stderr.write("Killed\n")
    raise SystemExit(137)
if command == "verify" and prompt == "SCENARIO disk":
    note_cid()
    sys.stderr.write("No space left on device\n")
    raise SystemExit(1)
if command == "verify" and prompt == "SCENARIO revision":
    note_cid()
    sys.stderr.write("RevisionNotFoundError: 404 Client Error\n")
    raise SystemExit(1)
if command == "verify" and prompt == "SCENARIO verify-fail":
    note_cid()
    sys.stderr.write(
        "E gensyn_sdk.cli: verify failed: Receipt validation failed for: "
        "parameters_hash. Cannot verify an internally inconsistent receipt.\n"
    )
    raise SystemExit(1)
if command == "verify" and prompt == "SCENARIO verify-trace":
    note_cid()
    sys.stderr.write("Traceback (most recent call last):\nsecret-traceback-line\n")
    raise SystemExit(1)
if command == "verify" and prompt == "SCENARIO no-receipt":
    note_cid()
    sys.stderr.write("I gensyn_sdk.cli: VERIFICATION PASSED: receipt hashes match\n")
    raise SystemExit(0)
if command == "verify" and prompt == "SCENARIO two-receipts":
    note_cid()
    write_one(data, "receipt_20261011_120000.json")
    write_one(data, "receipt_20261011_120001.json")
    raise SystemExit(0)
if command == "verify" and prompt == "SCENARIO hashline":
    note_cid()
    sys.stdout.write("prompt_hash: PASS\n")
    sys.stdout.write("I gensyn_sdk.cli: VERIFICATION PASSED: receipt hashes match\n")
    write_one(data or template())
    raise SystemExit(0)
if command == "run-all" and prompt == "SCENARIO model-lie":
    note_cid()
    body = template()
    body["model"]["name"] = "Qwen/Qwen2.5-0.5B"
    write_one(body)
    raise SystemExit(0)
if command == "run-all" and prompt == "SCENARIO prompt-lie":
    note_cid()
    body = template()
    body["input"]["prompt"] = "not-the-request"
    write_one(body)
    raise SystemExit(0)
if command == "run-all" and prompt == "SCENARIO poison-infer":
    note_cid()
    write_one(template())
    sys.stdout.write("No such image: gensynai/ree@sha256:ad683947\n")
    raise SystemExit(0)
if command == "run-all" and prompt in ("SCENARIO killed", "SCENARIO disk", "SCENARIO revision"):
    note_cid()
    raise SystemExit(1)
if command == "verify":
    note_cid()
    write_one(template())
    raise SystemExit(0)
if command == "run-all":
    note_cid()
    write_one(template())
    sys.stdout.write("I gensyn_sdk.build_receipt: receipt saved\n")
    raise SystemExit(0)
sys.stderr.write("fake docker: unhandled\n")
raise SystemExit(99)
'''


def dumps_receipt(data):
    text = json.dumps(data, default=_decimal)
    return re.sub(r'"__D__([0-9.]+)__D__"', r"\1", text)


def _decimal(value):
    if not isinstance(value, Decimal):
        raise TypeError(type(value).__name__)
    rendered = format(value, "f")
    if "." not in rendered:
        rendered += ".0"
    return f"__D__{rendered}__D__"


def sample_file(directory, **changes):
    data = make_sample("receipt")
    for path, value in changes.items():
        cursor = data
        parts = path.split(".")
        for part in parts[:-1]:
            cursor = cursor[part]
        cursor[parts[-1]] = value
    path = Path(directory) / "receipt.json"
    path.write_text(dumps_receipt(data))
    return path


def install_fake(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "docker"
    script.write_text(FAKE.replace("#!/usr/bin/env python3", "#!" + sys.executable, 1))
    script.chmod(0o755)
    (bindir / "template.json").write_text(dumps_receipt(make_sample("receipt")))
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    return bindir
