from __future__ import annotations
import re
if __package__:
    from .contract import HASH_NAMES
else:
    from contract import HASH_NAMES
_LOG = re.compile(r"[IWE] [\w.]+:\s*(.*)\Z")
_HASH = re.compile(
    r"(?:[IWE] [\w.]+:\s*)?(prompt_hash|tools_hash|parameters_hash|receipt_hash): (PASS|FAIL)\Z"
)
_PASS = "VERIFICATION PASSED: receipt hashes match"
_FAIL = re.compile(r"verify failed: .+\Z")
def read_validate(text, code):
    hashes = {}
    for raw in text.splitlines():
        match = _HASH.fullmatch(raw.strip())
        if not match: continue
        name, status = match.group(1), match.group(2)
        if name in hashes: return _incomplete()
        hashes[name] = status
    if set(hashes) != set(HASH_NAMES): return _incomplete()
    passed = all(hashes[name] == "PASS" for name in HASH_NAMES)
    failed = any(hashes[name] == "FAIL" for name in HASH_NAMES)
    if passed and code == 0: return {"ok": True, "kind": "consistent", "checks": dict(hashes)}
    if failed and code == 1: return {"ok": False, "kind": "inconsistent", "checks": dict(hashes)}
    return _incomplete()
def _incomplete():
    text = "Official validate did not return four hash lines that match its exit code."
    return {"ok": False, "kind": "validate_incomplete", "message": text}
DISAGREE = {"same": (0, 1, 0, 1), "differ": (0, 0, 1, 1), "none": (0, 0, 1, 1)}
def log_disagrees(text, compared):
    passed = failed = False
    for raw in text.splitlines():
        match = _LOG.fullmatch(raw.strip())
        body = match.group(1).strip() if match else ""
        passed = passed or body == _PASS
        failed = failed or bool(body and _FAIL.fullmatch(body))
    bits = DISAGREE.get(compared)
    if bits is None: return True
    return bool(bits[int(failed) + 2 * int(passed)])
