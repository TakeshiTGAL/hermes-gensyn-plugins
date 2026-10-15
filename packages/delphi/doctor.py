"""Offline doctor for local runtime and configuration only."""
from __future__ import annotations
import json
import os
import re
import shutil
from pathlib import Path
if __package__:
    from .contract import NETWORKS, TYPES
    from .settings import read_setting
    from .jsonio import parse_json
    from .process import ChildError, run_child
else:
    from contract import NETWORKS, TYPES
    from settings import read_setting
    from jsonio import parse_json
    from process import ChildError, run_child
SDK_VERSION = "2.1.0"
MIN_NODE = (20, 18, 0)
NODE_DEADLINE_SECONDS = 5.0
PACKAGE_JSON = Path(__file__).resolve().parent / "node_modules" / (
    "@gensyn-ai/gensyn-delphi-sdk/package.json" )
def _check(status, message, **details): return {"status": status, "message": message, **details}
def _installed_sdk_version():
    try:
        data = parse_json(PACKAGE_JSON.read_text())
    except (OSError, ValueError, RecursionError):
        return None
    version = data.get("version")
    return version if isinstance(version, str) else None
def _node_check(runner, node_path):
    if not node_path:
        return _check("error", "Node.js was not found.")
    env = { name: os.environ[name]
        for name in ("PATH", "HOME", "TMPDIR", "LANG") if os.environ.get(name) }
    try:
        result = runner([node_path, "--version"], b"", env, NODE_DEADLINE_SECONDS)
    except ChildError as exc: return _check("error", f"Node.js check failed: {exc.kind}.")
    if result.returncode != 0: return _check("error", "node --version failed.")
    match = re.fullmatch(rb"v(\d+)\.(\d+)\.(\d+)\s*", result.stdout)
    if match is None: return _check("error", "Node.js returned an invalid version.")
    version = tuple(int(part) for part in match.groups())
    if version < MIN_NODE: return _check("error", "Node.js 20.18.0 or later is required.")
    return _check("ok", "Node.js is compatible.", version=".".join(map(str, version)))
_INVALID = { "network": ("DELPHI_NETWORK", "The configured network is invalid."),
    "wallet": ("DELPHI_WALLET_ADDRESS", "The configured wallet address is invalid."), }
def _invalid(check):
    setting, message = _INVALID[check]
    return _check("error", message, setting=setting, problem="invalid")
def run_doctor(*, runner=run_child, node_path=None, sdk_version=None):
    """Check local files and settings without sending any network request."""
    node_path = shutil.which("node") if node_path is None else node_path
    installed = _installed_sdk_version() if sdk_version is None else sdk_version
    checks = {
        "node": _node_check(runner, node_path), "sdk": (
            _check("ok", "Pinned SDK is installed.", version=installed) if installed == SDK_VERSION
            else _check( "error", "SDK version mismatch. Run npm ci --ignore-scripts in packages/delphi.",
                expected=SDK_VERSION, installed=installed, ) ), }
    key_present = bool(read_setting("api_access_key"))
    checks["api_key"] = (
        _check("ok", "DELPHI_API_ACCESS_KEY is configured; value not shown.") if key_present
        else _check("error", "DELPHI_API_ACCESS_KEY is not configured.") )
    network = read_setting("network", "testnet")
    checks["network"] = (
        _check("ok", "Network is supported.", value=network) if network in NETWORKS
        else _invalid("network") )
    wallet = read_setting("wallet_address", "")
    if not wallet:
        checks["wallet"] = _check( "ok", "No wallet is configured; pass wallet to delphi_get_positions.", )
    elif TYPES["address"]["check"](wallet):
        checks["wallet"] = _check("ok", "Public wallet address has the expected shape.")
    else:
        checks["wallet"] = _invalid("wallet")
    checks["overall"] = ( "healthy" if all(value["status"] == "ok" for value in checks.values())
        else "error" )
    return checks
def doctor_main(_args=None):
    result = run_doctor()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["overall"] == "healthy" else 1
