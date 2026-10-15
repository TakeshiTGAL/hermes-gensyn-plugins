from __future__ import annotations
import re
from copy import deepcopy
from decimal import Decimal
IMAGE_DIGEST = "sha256:ad683947a8c3a0fcb2567280268c0b01f17652a38c3f76838a398bd79aaff0ec"
IMAGE_REF = "gensynai/ree@" + IMAGE_DIGEST
IMAGE_TAG = "gensynai/ree:v0.8.0"
RECEIPT_VERSION = "2.0.0"
MODELS = ("facebook/opt-125m", "Qwen/Qwen2.5-0.5B", "Qwen/Qwen3-0.6B")
LEVELS = (
    "consistent", "inconsistent", "reexecuted", "reexecuted_and_text_match",
    "text_mismatch", "reexecution_mismatch", "inferred",
)
NOT_GUARANTEED = ("text_output", "finish_reason", "token_count", "model.name", "ree_version",
    "execution.device_type", "execution.device_name", "input.parameters.torch_dtype")
INFER_REQUEST = (("model", "name"), ("input", "prompt"))
HASH_NAMES = ("prompt_hash", "tools_hash", "parameters_hash", "receipt_hash")
HASH_FIELDS = (
    ("output", "tokens_hash"), ("input", "prompt_hash"), ("input", "tools_hash"),
    ("input", "parameters_hash"), ("hashes", "receipt_hash"),
    ("model", "config_hash"), ("model", "commit_hash"),
)
COMPARE = (
    ("output", "text_output"), ("output", "finish_reason"), ("output", "token_count"),
    ("model", "name"), ("input", "prompt"),
)
TOOLS = ("ree_validate_receipt", "ree_verify_receipt", "ree_infer")
ERROR_TYPES = (
    "invalid_argument", "unsupported", "timeout", "upstream", "invalid_response", "config",
    "internal", "text_mismatch", "docker_unavailable", "image_missing", "container_not_started",
    "validate_incomplete", "reexecution_incomplete", "reexecution_mismatch", "approval_denied",
    "approval_unavailable", "unsupported_receipt_version", "insufficient_memory",
    "context_mount_unavailable", "killed",
)
NOT_COMPARED = ("ree_version", "execution.*")
TEXT_SKIP = ("absent_submitted", "absent_rerun", "absent_both")
BINDING = ("not_checked",)
VERDICT = (
    (True, 1, "same", "same", "reexecuted_and_text_match"), (True, 1, "same", "differ", "text_mismatch"),
    (True, 1, "differ", "-", "reexecution_mismatch"), (False, 1, "differ", "-", "reexecution_mismatch"),
    (False, 0, "-", "-", "reexecution_incomplete"), (True, 0, "-", "-", "internal"),
    (True, 2, "-", "-", "internal"),
)
def _has_text(data):
    output = data.get("output") if isinstance(data, dict) else None
    return isinstance(output, dict) and "text_output" in output
def text_skip_reason(submitted, fresh):
    left = _has_text(submitted)
    right = _has_text(fresh)
    if left and right:
        return None
    if not left and not right:
        return "absent_both"
    if left:
        return "absent_rerun"
    return "absent_submitted"
def judge(code, count, hashes, text):
    exit_zero = code == 0
    number = 1 if count == 1 else 0 if count == 0 else 2
    kind = hashes if number == 1 else "-"
    readable = text if number == 1 and kind == "same" and exit_zero else "-"
    if kind == "differ": readable = "-"
    for row in VERDICT:
        if (row[0], row[1], row[2], row[3]) == (exit_zero, number, kind, readable): return row[4]
    return "internal"
def request_mismatch(data, wanted):
    for path in INFER_REQUEST:
        if data[path[0]][path[1]] != wanted[path]: return ".".join(path)
    return None
def image_absent_message():
    tag = IMAGE_TAG
    return ("Image " + tag + " is not local. Run `docker pull " + tag + "` yourself. "
            "That pull is consent to the REE-Binary-License. This plugin does not pull it.")
RECEIPT_LIMIT = 1_048_576
PROMPT_LIMIT = 4000
TEXT_ECHO_LIMIT = 400
VALIDATE_DEADLINE = 60
VERIFY_DEADLINE = 600
INFER_DEADLINE = 600
LARGE_DEADLINE = 1800
HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
SEMVER_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
DEVICE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,31}\Z")
MODEL_RE = re.compile(r"[A-Za-z0-9_./-]{1,128}\Z")
WORD_RE = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")
DTYPES = ("torch.float16", "torch.bfloat16", "torch.float32")
OPERATIONS = ("default", "deterministic", "reproducible")
def _is_text(value, limit): return isinstance(value, str) and "\x00" not in value and 0 < len(value) <= limit
def _is_receipt_text(value): return isinstance(value, str) and "\x00" not in value
def _is_bool(value): return type(value) is bool
def _int_range(low, high): return lambda value: type(value) is int and low <= value <= high
def _is_hash(value): return isinstance(value, str) and HASH_RE.fullmatch(value) is not None
def _is_commit(value): return isinstance(value, str) and COMMIT_RE.fullmatch(value) is not None
def _is_semver(value): return isinstance(value, str) and SEMVER_RE.fullmatch(value) is not None
def _is_version(value): return value == RECEIPT_VERSION
def _is_model(value): return isinstance(value, str) and value in MODELS
def _is_model_shape(value):
    return isinstance(value, str) and MODEL_RE.fullmatch(value) is not None and value.count("/") == 1
def _is_word(value): return isinstance(value, str) and WORD_RE.fullmatch(value) is not None
def _is_tools(value):
    if value is None: return True
    if type(value) is not list or not 1 <= len(value) <= 16: return False
    for item in value:
        if type(item) is not dict or not 1 <= len(item) <= 8: return False
        for key, val in item.items():
            if not _is_word(key) or not (type(val) is dict or _is_word(val)): return False
    return True
def _enum(values): return lambda value: isinstance(value, str) and value in values
def _is_decimal(value):
    return type(value) is Decimal and value.is_finite() and Decimal(0) <= value <= Decimal(2)
def _is_device(value): return isinstance(value, str) and DEVICE_RE.fullmatch(value) is not None
def _is_device_name(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128: return False
    return all(" " <= ch != "\x7f" for ch in value)
def shown_version(value):
    if isinstance(value, str) and SEMVER_RE.fullmatch(value) is not None: return value
    return None
def deadline_for(model):
    return VERIFY_DEADLINE if model in MODELS else LARGE_DEADLINE
def _is_only_null(value): return value is None
def _type(check, valid, boundary, wrong_type, invalid, expected="the documented shape"):
    return {
        "check": check, "valid": valid, "boundary": boundary,
        "wrong_type": wrong_type, "invalid": invalid, "expected": expected,
    }
def _span(low, high, valid, boundary):
    invalid = low - 1 if low > 0 else high + 1
    phrase = f"integer from {low} to {high}"
    return _type(_int_range(low, high), valid, boundary, "1", invalid, phrase)
_HASH = "sha256:" + ("ab" * 32)
_COMMIT = "cd" * 20
TYPES = {
    "receipt_version": _type(_is_version, "2.0.0", "2.0.0", 1, "2.1.0", "2.0.0"),
    "semver": _type(_is_semver, "0.8.0", "0.0.0", 1, "0.7"),
    "model_name": _type(
        _is_model_shape, MODELS[0], "a/" + ("b" * 126), 1, "noslash",
        "letters, digits, and ._/- with one slash",
    ),
    "commit": _type(_is_commit, _COMMIT, "0" * 40, 1, "abcd"),
    "sha256": _type(_is_hash, _HASH, "sha256:" + ("0" * 64), 1, "sha256:abcd"),
    "prompt": _type(_is_receipt_text, "from-rerun", "x" * 8000, 1, "\x00"),
    "body": _type(_is_receipt_text, "from-rerun", "", 1, "\x00"),
    "only_null": _type(_is_only_null, None, None, "null", "[]", "null"),
    "tools": _type(
        _is_tools, None, [{"name": "lookup"}], 1, [{"name": "bad value"}], "null or a list of objects",
    ),
    "bool": _type(_is_bool, True, False, 1, "true"),
    "decimal": _type(_is_decimal, Decimal("1.0"), Decimal(0), 1, Decimal(-1)),
    "tokens": _span(1, 4096, 16, 4096),
    "seed": _span(0, 2**63 - 1, 12345, 2**63 - 1),
    "topk": _span(0, 100_000, 50, 100_000),
    "token_id": _span(0, 1_000_000, 2, 1_000_000),
    "vocab": _span(1, 1_000_000, 50272, 1_000_000),
    "degen": _span(0, 10_000, 4, 10_000),
    "count": _span(0, 100_000, 16, 100_000),
    "operation_set": _type(
        _enum(OPERATIONS), "reproducible", "default", 1, "other",
        "default, deterministic, or reproducible",
    ),
    "rand_algorithm": _type(_is_word, "default", "x" * 64, 1, "bad value", "a short ASCII word"),
    "dtype": _type(
        _enum(DTYPES), "torch.float16", "torch.bfloat16", 1, "float16",
        "torch.float16, torch.bfloat16, or torch.float32",
    ),
    "finish": _type(_is_word, "stop", "max_length", 1, "bad value", "a short ASCII word"),
    "device": _type(_is_device, "cpu", "cuda", 1, "bad name"),
    "device_name": _type(_is_device_name, "NVIDIA A100", "N" * 128, 1, "x" * 129),
    "tool_name": _type(_enum(TOOLS), TOOLS[0], TOOLS[2], 1, "other"),
    "error_type": _type(_enum(ERROR_TYPES), "upstream", "internal", 1, "unknown"),
    "level": _type(_enum(LEVELS), "consistent", "text_mismatch", 1, "verified"),
    "message": _type(lambda v: _is_text(v, 500), "failed", "x" * 500, 1, ""),
}
def F(type_name, *, required=True, nullable=False):
    return {"type": type_name, "required": required, "nullable": nullable}
def N(table, *, required=True): return {"table": table, "required": required}
PARAMETERS = {
    "max_new_tokens": F("tokens"), "temperature": F("decimal"), "top_k": F("topk"),
    "top_p": F("decimal"), "min_p": F("decimal", nullable=True), "repetition_penalty": F("decimal"),
    "seed": F("seed"), "operation_set": F("operation_set"), "rand_algorithm": F("rand_algorithm"),
    "do_sample": F("bool"), "eos_token": F("token_id"), "short_circuit_length": F("token_id", nullable=True),
    "short_circuit_token": F("token_id", nullable=True), "use_kv_cache": F("bool"),
    "pad_token": F("token_id"), "vocab_size": F("vocab"), "degenerate_min_tokens": F("degen"),
    "torch_dtype": F("dtype"),
    "enable_thinking": F("bool", required=False),
}
TABLES = {
    "receipt.parameters": PARAMETERS,
    "receipt.model": {"name": F("model_name"), "commit_hash": F("commit"), "config_hash": F("sha256")},
    "receipt.input": {
        "prompt": F("prompt"), "prompt_hash": F("sha256"), "tools": F("tools", nullable=True),
        "tools_hash": F("sha256"), "parameters": N("receipt.parameters"), "parameters_hash": F("sha256"),
    },
    "receipt.output": {
        "tokens_hash": F("sha256"), "token_count": F("count"),
        "finish_reason": F("finish"), "text_output": F("body", required=False),
    },
    "receipt.execution": {"device_type": F("device"), "device_name": F("device_name")},
    "receipt.hashes": {"receipt_hash": F("sha256")},
    "receipt": {
        "version": F("receipt_version"), "ree_version": F("semver"), "model": N("receipt.model"),
        "input": N("receipt.input"), "output": N("receipt.output"), "execution": N("receipt.execution"),
        "hashes": N("receipt.hashes"),
    },
}
def make_sample(table_name):
    value = {}
    for name, spec in TABLES[table_name].items():
        if "type" in spec:
            value[name] = deepcopy(TYPES[spec["type"]]["valid"])
        else:
            value[name] = make_sample(spec["table"])
    return value
def validate(table_name, value):
    if not isinstance(value, dict): return f"{table_name} must be an object"
    fields = TABLES[table_name]
    unknown = sorted(set(value) - set(fields))
    if unknown: return f"{table_name}.{unknown[0]} is not allowed"
    for name, spec in fields.items():
        if name not in value:
            if spec.get("required", True): return f"{table_name}.{name} is missing"
            continue
        item = value[name]
        if item is None and spec.get("nullable"): continue
        if item is None and spec.get("type") != "only_null": return f"{table_name}.{name} has invalid null"
        if "type" in spec:
            if not TYPES[spec["type"]]["check"](item):
                return f"{table_name}.{name} has invalid {spec['type']}"
        else:
            problem = validate(spec["table"], item)
            if problem: return f"{table_name}.{name}: {problem}"
    return None
_INT_TYPES = {"tokens", "seed", "topk", "token_id", "vocab", "degen", "count"}
def _scalar(kind, item):
    expected = TYPES[kind]["expected"]
    if kind in _INT_TYPES or kind == "decimal":
        want = int if kind in _INT_TYPES else Decimal
        if type(item) is not want: return ("wrong_type", expected)
        if not TYPES[kind]["check"](item): return ("out_of_range", expected)
        return None
    if kind == "bool": return None if type(item) is bool else ("wrong_type", expected)
    if TYPES[kind]["check"](item): return None
    return ("wrong_type", expected) if not isinstance(item, str) else ("bad_format", expected)
def _object(table, value, path):
    fields = TABLES[table]
    allowed = tuple(fields)
    label = path or "receipt"
    if type(value) is not dict: return (label, "wrong_type", "object", allowed)
    unknown = sorted(set(value) - set(fields))
    if unknown:
        key = unknown[0]
        parent = path or "receipt"
        child = (f"{path}.{key}" if path else key) if _is_word(key) else parent + ".unknown"
        return (child, "unknown_field", "an allowed field", allowed)
    for name, spec in fields.items():
        child = f"{path}.{name}" if path else name
        if name not in value:
            if spec.get("required", True):
                kind = spec.get("type")
                expected = TYPES[kind]["expected"] if kind else "object"
                return (child, "missing", expected, allowed)
            continue
        item = value[name]
        if item is None and (spec.get("nullable") or spec.get("type") == "only_null"): continue
        if "table" in spec:
            found = _object(spec["table"], item, child)
            if found: return found
            continue
        if item is None: return (child, "wrong_type", TYPES[spec["type"]]["expected"], allowed)
        found = _scalar(spec["type"], item)
        if found: return (child, found[0], found[1], allowed)
    return None
def receipt_refusal(value):
    return _object("receipt", value, "")
def _path_problem(item):
    if not isinstance(item, str): return ("wrong_type", "a receipt path")
    if not item or item.startswith("-") or "\n" in item or "\r" in item or "\x00" in item:
        return ("bad_format", "a receipt path")
    if len(item) > 4096: return ("out_of_range", "a receipt path up to 4096 characters")
    return None
def _infer_model(item):
    expected = "facebook/opt-125m, Qwen/Qwen2.5-0.5B, or Qwen/Qwen3-0.6B"
    if not isinstance(item, str): return ("wrong_type", expected)
    if item not in MODELS: return ("bad_format", expected)
    return None
def _prompt_problem(item):
    if not isinstance(item, str): return ("wrong_type", "text from 1 to 4000 characters")
    if "\n" in item or "\r" in item or "\x00" in item or item.startswith("-"):
        return ("bad_format", "text from 1 to 4000 characters without newline, CR, NUL, or a leading hyphen")
    if not 1 <= len(item) <= PROMPT_LIMIT: return ("out_of_range", "text from 1 to 4000 characters")
    return None
def _tokens_problem(item):
    expected = "integer from 1 to 256"
    if type(item) is not int: return ("wrong_type", expected)
    if not 1 <= item <= 256: return ("out_of_range", expected)
    return None
ARG_FIELDS = {
    "ree_validate_receipt": {"receipt_path": _path_problem},
    "ree_verify_receipt": {"receipt_path": _path_problem},
    "ree_infer": {
        "model": _infer_model, "prompt": _prompt_problem, "max_new_tokens": _tokens_problem,
    },
}
NEXT_VERIFY = {
    "tool": "ree_verify_receipt", "needs_approval": True,
    "checks": ["re-execution", "text fields"], "hash_check_any_size": True,
}
NEXT_LOCAL = {
    "tool": "ree_validate_receipt", "runs_here": True, "any_size": True,
    "reexecute_here": False, "settings": ["docker_context"],
}
def entry_refusal(tool, value):
    """Typed refusal for one tool call. Does not include the submitted value."""
    fields = ARG_FIELDS[tool]
    allowed = tuple(fields)
    if type(value) is not dict: return ("input", "wrong_type", "object", allowed)
    unknown = sorted(set(value) - set(fields))
    if unknown:
        field = unknown[0] if _is_word(unknown[0]) else "arguments"
        return (field, "unknown_field", "an allowed field", allowed)
    for name, check in fields.items():
        if name not in value:
            sample = check("")
            return (name, "missing", sample[1], allowed)
        found = check(value[name])
        if found: return (name, found[0], found[1], allowed)
    return None