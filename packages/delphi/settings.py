"""The only reader for Delphi network, wallet, and key presence."""
from __future__ import annotations
_getter = None
def bind_config(getter):
    global _getter
    _getter = getter if callable(getter) else None
def read_setting(name, default=""):
    """Scope wins. A plugin setting applies only when the secret is unset."""
    from agent.secret_scope import UnscopedSecretError, get_secret
    try:
        value = get_secret("DELPHI_" + name.upper(), default=None)
    except UnscopedSecretError:
        raise
    if value not in (None, ""): return value
    if _getter is None: return default
    try:
        value = _getter(name)
    except Exception: return None
    return value if value not in (None, "") else default
