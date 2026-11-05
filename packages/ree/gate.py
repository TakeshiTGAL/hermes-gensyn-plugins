from __future__ import annotations
import contextvars
import os
import threading
import time
import uuid
from pathlib import Path
if __package__:
    from .contract import MODELS
else:
    from contract import MODELS
REASON_BUDGET = 300
_TTL = 600
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_UNATTENDED = frozenset({"webhook", "msgraph_webhook", "api_server"})
_OFF = frozenset({"off", "false", "no", "0"})
_LOCK = threading.Lock()
_PERMITS = {}
_PENDING = {}
_GRANTS = frozenset({"once", "session", "always"})
_RULE_PREFIX = "plugin_rule:"
_CRON_READER = None
def reason_fits(text):
    if "\n" in text or "`" in text or len(text) > REASON_BUDGET: return False
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return len(escaped) <= REASON_BUDGET
def bind_cron_reader(reader):
    global _CRON_READER
    _CRON_READER = reader if callable(reader) else None
def _context_values(name):
    try:
        current = contextvars.copy_context()
    except Exception:
        return []
    found = []
    for var, value in current.items():
        if getattr(var, "name", None) == name:
            found.append(value)
    return found
def session_flag(name):
    explicit_empty = False
    for value in _context_values(name):
        if isinstance(value, bool):
            if value:
                return "1"
            explicit_empty = True
            continue
        if not isinstance(value, str):
            continue
        if value == "":
            explicit_empty = True
            continue
        return value
    if explicit_empty:
        return ""
    return str(os.environ.get(name) or "")
def _flag_on(name):
    return session_flag(name).strip().lower() in _TRUTHY
def _cron_reader():
    reader = _CRON_READER
    if reader is not None:
        return reader
    try:
        from cron.execution_identity import current_cron_execution as reader
    except Exception:
        return None
    return reader
def _config_path():
    home = os.environ.get("HERMES_HOME", "").strip()
    if home:
        return Path(home).expanduser() / "config.yaml"
    return Path.home() / ".hermes" / "config.yaml"
def _mode_value(text):
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if not in_block:
            if indent == 0 and stripped == "approvals:":
                in_block = True
            continue
        if indent == 0:
            break
        if stripped.startswith("mode:"):
            raw = stripped.split(":", 1)[1].split("#", 1)[0].strip().strip("'\"")
            return raw.lower()
    return ""
def _approvals_off():
    path = _config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    except Exception:
        return None
    try:
        return _mode_value(text) in _OFF
    except Exception:
        return None
def _interactive_cli():
    decided = False
    on = False
    for value in _context_values("hermes_interactive"):
        if value is None:
            continue
        decided = True
        if isinstance(value, str):
            if value.strip().lower() in _TRUTHY:
                on = True
        elif bool(value):
            on = True
    if decided:
        return on
    return _flag_on("HERMES_INTERACTIVE")
def _person_present():
    if _interactive_cli():
        return True
    if _flag_on("HERMES_GATEWAY_SESSION") or _flag_on("HERMES_EXEC_ASK"):
        return True
    platform = session_flag("HERMES_SESSION_PLATFORM").strip().lower()
    return bool(platform) and platform not in _UNATTENDED
def _later(label):
    return f"BLOCKED: {label} cannot start REE, even after always, so the call was refused."
def command_block_reason():
    if os.environ.get("HERMES_PLUGIN_HOST_PROCESS") == "1":
        return _later("host isolation")
    if _flag_on("HERMES_CRON_SESSION"):
        return _later("a cron job")
    reader = _cron_reader()
    if reader is not None:
        try:
            mark = reader()
        except Exception:
            return _later("a turn whose cron mark could not be read")
        if mark is not None:
            return _later("a cron job")
    if _flag_on("HERMES_YOLO_MODE"):
        return "BLOCKED: Hermes yolo cannot start REE, so the call was refused."
    off = _approvals_off()
    if off is None:
        return "BLOCKED: approvals mode could not be read, so the call was refused."
    if off:
        return "BLOCKED: Hermes approvals are off, so the call was refused."
    if _flag_on("HERMES_SINGLE_QUERY_SESSION"):
        return _later("a single-query session")
    platform = session_flag("HERMES_SESSION_PLATFORM").strip().lower()
    if platform in _UNATTENDED:
        return _later("an unattended session")
    if not _person_present():
        return "BLOCKED: no interactive user or gateway is present, so the call was refused."
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
def _token(kind, model, max_new_tokens, machine, note, cpu_only, session_id, task_id, receipt_hash):
    count = None if max_new_tokens is None else int(max_new_tokens)
    return (
        str(session_id or ""), str(task_id or ""), str(kind), str(model), count,
        str(machine), str(note), bool(cpu_only), str(receipt_hash or ""),
    )
def clear_room(session_id="", task_id=""):
    room = (str(session_id or ""), str(task_id or ""))
    now = time.monotonic()
    with _LOCK:
        _expire(now)
        for key in list(_PERMITS):
            if key[:2] == room:
                _PERMITS.pop(key, None)
        for key, (token, _made) in list(_PENDING.items()):
            if token[:2] == room:
                _PENDING.pop(key, None)
def _expire(now):
    for key, made in list(_PERMITS.items()):
        if now - made > _TTL:
            _PERMITS.pop(key, None)
    for key, (_token_value, made) in list(_PENDING.items()):
        if now - made > _TTL:
            _PENDING.pop(key, None)
def _drop(token):
    with _LOCK:
        _PERMITS.pop(token, None)
        for key, (pending, _made) in list(_PENDING.items()):
            if pending == token:
                _PENDING.pop(key, None)
def _pend(rule_key, token):
    now = time.monotonic()
    with _LOCK:
        _expire(now)
        _PENDING[rule_key] = (token, now)
def _rule_names(pattern_key, pattern_keys):
    raw = []
    if isinstance(pattern_key, str):
        raw.append(pattern_key)
    if isinstance(pattern_keys, (list, tuple)):
        raw.extend(item for item in pattern_keys if isinstance(item, str))
    names = []
    for item in raw:
        name = item[len(_RULE_PREFIX):] if item.startswith(_RULE_PREFIX) else ""
        if name and name not in names:
            names.append(name)
    return names
def note_response(pattern_key="", pattern_keys=None, choice="", decided_by=None):
    # Once, session, or always from post_approval_response is the public mark that a person
    # answered. Session /yolo and a room approval_mode of off never fire that hook.
    grant = decided_by in (None, "") and isinstance(choice, str) and choice in _GRANTS
    now = time.monotonic()
    for name in _rule_names(pattern_key, pattern_keys):
        with _LOCK:
            item = _PENDING.pop(name, None)
            if item is None:
                continue
            token, made = item
            if grant and now - made <= _TTL:
                _PERMITS[token] = made
            return
def asked(
    kind, model, max_new_tokens=None, machine="current", note="", cpu_only=True,
    session_id="", task_id="", receipt_hash="",
):
    token = _token(
        kind, model, max_new_tokens, machine, note, cpu_only, session_id, task_id, receipt_hash,
    )
    now = time.monotonic()
    with _LOCK:
        made = _PERMITS.get(token)
        if made is not None and now - made <= _TTL:
            return True
        for pending, made in _PENDING.values():
            if pending == token and now - made <= _TTL:
                return True
    return False
def _take(token):
    now = time.monotonic()
    with _LOCK:
        made = _PERMITS.pop(token, None)
    return made is not None and now - made <= _TTL
def issue(
    kind, model, max_new_tokens=None, machine="current", note="", cpu_only=True,
    session_id="", task_id="", receipt_hash="",
):
    reason = command_block_reason()
    if reason:
        return {"action": "block", "message": reason}
    text = question(kind, model, max_new_tokens, machine, note, cpu_only)
    if not reason_fits(text):
        return {"action": "block", "message": "BLOCKED: the approval question would be cut off, so it was not sent."}
    rule_key = f"ree_{kind}:{model}:{uuid.uuid4().hex}"
    _pend(rule_key, _token(
        kind, model, max_new_tokens, machine, note, cpu_only, session_id, task_id, receipt_hash,
    ))
    return {
        "action": "approve",
        "message": text,
        "rule_key": rule_key,
    }
def approve(
    kind, model, max_new_tokens=None, machine="current", note="", cpu_only=True,
    session_id="", task_id="", receipt_hash="",
):
    try:
        return _approve(
            kind, model, max_new_tokens, machine, note, cpu_only, session_id, task_id, receipt_hash,
        )
    except Exception:
        return False, "BLOCKED: approval failed closed, so the call was refused."
def _approve(kind, model, max_new_tokens, machine, note, cpu_only, session_id, task_id, receipt_hash):
    token = _token(
        kind, model, max_new_tokens, machine, note, cpu_only, session_id, task_id, receipt_hash,
    )
    reason = command_block_reason()
    if reason:
        _drop(token)
        return False, reason
    text = question(kind, model, max_new_tokens, machine, note, cpu_only)
    if not reason_fits(text):
        _drop(token)
        return False, "BLOCKED: the approval question would be cut off, so it was not sent."
    if not _take(token):
        _drop(token)
        return False, "BLOCKED: approval was not obtained, so the call was refused."
    return True, {"approved": True}
