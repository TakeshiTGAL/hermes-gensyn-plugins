"""Thin Python adapter for the local SDK bridge."""
from __future__ import annotations
import json
import os
import shutil
import tempfile
from pathlib import Path
if __package__:
    from .jsonio import parse_json
    from .process import ChildError, run_child
    from .settings import read_setting
else:
    from jsonio import parse_json
    from process import ChildError, run_child
    from settings import read_setting
BRIDGE_TIMEOUT_SECONDS = 25.0
BRIDGE_PATH = Path(__file__).resolve().parent / "scripts" / "bridge.mjs"
ENV_ALLOWLIST = ( "PATH", "HOME", "TMPDIR", "LANG", "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", )
def _environment(needs_key):
    env = {name: os.environ[name] for name in ENV_ALLOWLIST if os.environ.get(name)}
    env["NODE_OPTIONS"] = "--max-old-space-size=256"
    key = read_setting("api_access_key") if needs_key else ""
    if key:
        env["DELPHI_API_ACCESS_KEY"] = key
    return env
def call_bridge(op, args, *, needs_key, budget, network):
    node = shutil.which("node")
    if node is None: return {"ok": False, "error_type": "config", "message": "Node.js is not available."}
    request = json.dumps( {"op": op, "args": args, "network": network, "max_outbound": budget},
        separators=(",", ":"), ).encode()
    work = tempfile.mkdtemp(prefix="delphi-cwd-")
    try:
        child = run_child( [node, str(BRIDGE_PATH)], request, _environment(needs_key), BRIDGE_TIMEOUT_SECONDS,
            cwd=work, )
    except ChildError as exc: return {"ok": False, "error_type": exc.kind, "message": str(exc), "outbound": 0}
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if child.returncode != 0:
        return { "ok": False, "error_type": "upstream", "message": "The local SDK bridge failed.",
            "outbound": 0, }
    try:
        value = parse_json(child.stdout)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return { "ok": False, "error_type": "invalid_response",
            "message": "The local SDK bridge returned invalid JSON.", "outbound": 0, }
    if not isinstance(value, dict):
        return { "ok": False, "error_type": "invalid_response",
            "message": "The local SDK bridge returned the wrong shape.", "outbound": 0, }
    return value
