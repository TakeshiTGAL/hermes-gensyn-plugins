from __future__ import annotations
import importlib
import os
import uuid
if __package__:
    from .contract import MODELS
else:
    from contract import MODELS
REASON_BUDGET = 300
_CHECKS = (
    ("tools.approval_context", "_is_cron_approval_context", "a cron job"),
    ("tools.approval", "_yolo_active", "Hermes yolo"),
    ("tools.approval_context", "_get_approval_mode", "approvals.mode"),
    ("tools.approval_context", "_is_single_query_approval_context", "a single-query session"),
    ("tools.approval_context", "_is_unattended_platform_approval_context", "an unattended session"),
)
def reason_fits(text):
    if "\n" in text or "`" in text or len(text) > REASON_BUDGET: return False
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return len(escaped) <= REASON_BUDGET
def _load(module, name):
    try: loaded = importlib.import_module(module)
    except Exception: return "failed", None
    if not hasattr(loaded, name): return "missing", None
    try:
        return "ok", getattr(loaded, name)
    except Exception: return "failed", None
def _blocked(label):
    return f"BLOCKED: could not check {label}, so the call was refused."
def command_block_reason():
    if os.environ.get("HERMES_PLUGIN_HOST_PROCESS") == "1":
        return "BLOCKED: host isolation cannot start REE, so the call was refused."
    for module, name, label in _CHECKS:
        status, fn = _load(module, name)
        if status != "ok": return _blocked(label)
        try:
            value = fn()
        except Exception: return _blocked(label)
        if name == "_get_approval_mode":
            if value == "off": return "BLOCKED: Hermes approvals are off, so the call was refused."
        elif value: return f"BLOCKED: {label} cannot start REE, so the call was refused."
    status, _fn = _load("tools.approval", "request_tool_approval")
    if status != "ok": return "BLOCKED: Hermes approval could not be loaded, so the call was refused."
    return None
_WEIGHTS = "Takes minutes. not limited to Hugging Face. "
_TOKEN = "cache token file visible in container. "
_CLEAN = "Timeout removes it."
_TAIL = "Choosing always stops here."
def question(kind, model, max_new_tokens=None, machine="current", note="", cpu_only=True):
    where = f"On {machine}. "
    sized = (note + " ") if note else ""
    if kind == "verify" and model not in MODELS:
        extra = (note + " ") if note else "Size is unknown. "
        return (
            f"{where}Re-execute {model}. {extra}"
            "gigabytes; may not fit memory. CPU-only. "
            "Not limited to Hugging Face. " + _TOKEN + _CLEAN
        )
    if kind == "verify":
        head = f"Re-execute {model} on CPU. "
        mount = "One read-only receipt file. "
    else:
        head = f"Infer {model} on CPU, {max_new_tokens} tokens. "
        mount = "no receipt file. "
    return where + head + _WEIGHTS + mount + _TOKEN + sized + _CLEAN + " " + _TAIL
def denial_kind(result):
    if isinstance(result, dict) and result.get("outcome") == "denied": return "approval_denied"
    return "approval_unavailable"
DENIAL = {
    "approval_denied": "Approval was not granted. Do not retry.",
    "approval_unavailable": (
        "Approval was not obtained (could not ask, or there was no answer). Do not retry."
    ),
}
def approve(kind, model, max_new_tokens=None, machine="current", note="", cpu_only=True):
    try:
        return _approve(kind, model, max_new_tokens, machine, note, cpu_only)
    except Exception: return False, "BLOCKED: approval failed closed, so the call was refused."
def _approve(kind, model, max_new_tokens, machine, note, cpu_only):
    reason = command_block_reason()
    if reason: return False, reason
    text = question(kind, model, max_new_tokens, machine, note, cpu_only)
    if not reason_fits(text):
        return False, "BLOCKED: the approval question would be cut off, so it was not sent."
    status, fn = _load("tools.approval", "request_tool_approval")
    if status != "ok": return False, "BLOCKED: Hermes approval could not be loaded, so the call was refused."
    rule_key = f"ree_{kind}:{model}:{uuid.uuid4().hex}"
    try:
        result = fn(f"ree_{kind}", text, rule_key=rule_key)
    except Exception: return False, "BLOCKED: the Hermes approval request failed, so the call was refused."
    if not isinstance(result, dict) or result.get("approved") is not True: return False, result
    return True, result
