"""Weight estimate and Docker context. Bytes only; no invented RAM margin."""
from __future__ import annotations
import os
import re
from pathlib import Path
if __package__:
    from .contract import NEXT_LOCAL
    from .docker import docker_text, option_problem
else:
    from contract import NEXT_LOCAL
    from docker import docker_text, option_problem
_NAME = re.compile(r"(\d+(?:\.\d+)?)([BbMm])(?![A-Za-z0-9])")
_CTX = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_GB, _SCALE = 1_000_000_000, {"b": 1_000_000_000, "m": 1_000_000}
_HELD, _WEIGHTS = {"ctx": None}, {".safetensors", ".bin"}
_MOUNT = "This Docker context cannot mount the receipt and work files."
_MEM = "The weights are larger than Docker memory. Hash validation still runs on this machine."
def remember(ctx):
    _HELD["ctx"] = ctx
def context_problem(name):
    if name in (None, ""): return None
    if not isinstance(name, str): return "wrong_type"
    if name.startswith("-") or _CTX.fullmatch(name) is None: return "bad_format"
    return None
def _scaled(text, scale):
    whole, _dot, frac = text.partition(".")
    if not whole.isdigit() or (frac and not frac.isdigit()): return None
    return int(whole) * scale if not frac else int(whole + frac) * scale // (10 ** len(frac))
def name_bytes(model):
    if not isinstance(model, str): return None
    found = list(_NAME.finditer(model))
    if not found: return None
    params = _scaled(found[-1].group(1), _SCALE[found[-1].group(2).lower()])
    return None if params is None else params * 2
def weight_bytes(model, root):
    if not isinstance(model, str) or model.count("/") != 1: return None
    org, name = model.split("/", 1)
    folder = Path(root) / "hub" / ("models--" + org + "--" + name) / "snapshots"
    if not folder.is_dir(): return None
    best = 0
    for snap in folder.iterdir():
        if not snap.is_dir(): continue
        base, total = snap.resolve(), 0
        for item in snap.iterdir():
            if not item.is_file() or item.suffix not in _WEIGHTS: continue
            try: target = item.resolve()
            except OSError: continue
            if base != target and base not in target.parents: continue
            total += item.stat().st_size
        best = max(best, total)
    return best or None
def estimate(model, available, root):
    weights = weight_bytes(model, root) if root else None
    if weights: return {"source": "weights", "needed": weights, "available": available}
    named = name_bytes(model)
    if named: return {"source": "name", "needed": named, "available": available}
    return {"source": "unknown", "needed": None, "available": available}
def _gb(n, up): return (n + _GB - 1) // _GB if up else n // _GB
def note_for(est):
    if est["source"] == "unknown" or est["needed"] is None: return "Size is unknown."
    if est["available"] is None: return "Docker memory was not read."
    needed, avail = _gb(est["needed"], True), _gb(est["available"], False)
    if est["source"] == "name": return f"Name estimate {needed}GB, Docker {avail}GB."
    return f"Weight files {needed}GB, Docker {avail}GB."
def _settings():
    ctx = _HELD["ctx"]
    if ctx is None or not hasattr(ctx, "get_config"): return ""
    try: raw = ctx.get_config("docker_context", "")
    except Exception: return {"bad": "wrong_type"}
    if raw in (None, ""): return ""
    problem = context_problem(raw)
    return {"bad": problem} if problem else raw
def context_setting():
    found = _settings()
    return "" if isinstance(found, dict) else found
def mount_reason(host):
    if not host: return "inspect_failed"
    if host.startswith("unix://"):
        path = host[7:]
        return None if path.startswith("/") and Path(path).exists() else "socket_missing"
    if host.startswith(("tcp://", "ssh://", "npipe://", "fd://")): return "remote_daemon"
    return "unknown_host"
def _machine(context):
    if context: return context
    host = os.environ.get("DOCKER_HOST", "")
    if isinstance(host, str) and host and option_problem(host) is None: return host
    shown = docker_text(["docker", "context", "show"])
    if shown and context_problem(shown) is None: return shown
    return "current"
def _stop(kind, message, **fields):
    fields.update({"retryable": False, "next": dict(NEXT_LOCAL)})
    return {"error": kind, "error_type": kind, "message": message, "fields": fields}
def context_rejected():
    found = _settings()
    return found["bad"] if isinstance(found, dict) else None
def prepare(model, root=None):
    found = _settings()
    if isinstance(found, dict): return {"error": "context", "problem": found["bad"]}
    context = found
    if context:
        host = docker_text([
            "docker", "--context", context, "context", "inspect", context,
            "--format", "{{.Endpoints.docker.Host}}",
        ])
        reason = mount_reason(host)
        if reason: return _stop("context_mount_unavailable", _MOUNT, reason=reason)
    info = ["info", "--format", "{{.MemTotal}}"]
    argv = ["docker", "--context", context, *info] if context else ["docker", *info]
    raw = docker_text(argv)
    available = int(raw) if raw and raw.isdigit() else None
    cache = Path.home() / ".cache" / "huggingface" if root is None else Path(root)
    est = estimate(model, available, cache)
    plan = {
        "context": context, "cpu_only": True, "machine": _machine(context),
        "note": note_for(est), "source": est["source"],
    }
    if est["needed"] is not None and available is not None and est["needed"] > available:
        plan.update(_stop(
            "insufficient_memory", _MEM, needed_gb=_gb(est["needed"], True),
            available_gb=_gb(available, False), size_source=est["source"],
        ))
    return plan
