from __future__ import annotations

import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))


def _scope_stub():
    """Python 3.9 cannot import the Hermes tree. Tests still call get_secret."""
    import os
    import types
    from contextvars import ContextVar
    try:
        import agent.secret_scope  # noqa: F401
        return
    except (ImportError, TypeError):
        pass
    scope = ContextVar("delphi_test_scope", default=None)
    state = {"multi": False}

    class UnscopedSecretError(RuntimeError):
        def __init__(self, secret_name="", developer_detail=""):
            super().__init__(secret_name)
            self.secret_name = secret_name

    def set_multiplex_active(active):
        state["multi"] = bool(active)

    def set_secret_scope(secrets, profile_home=None):
        return scope.set(None if secrets is None else dict(secrets))

    def reset_secret_scope(token):
        scope.reset(token)

    def get_secret(name, default=None):
        bound = scope.get()
        if bound is not None:
            if name in bound and bound[name] is not None:
                return bound[name]
            return default if state["multi"] else os.environ.get(name, default)
        if state["multi"]:
            raise UnscopedSecretError(name)
        value = os.environ.get(name)
        return default if value is None else value

    module = types.ModuleType("agent.secret_scope")
    module.UnscopedSecretError = UnscopedSecretError
    module.set_multiplex_active = set_multiplex_active
    module.set_secret_scope = set_secret_scope
    module.reset_secret_scope = reset_secret_scope
    module.get_secret = get_secret
    agent = sys.modules.get("agent") or types.ModuleType("agent")
    agent.secret_scope = module
    sys.modules["agent"] = agent
    sys.modules["agent.secret_scope"] = module


_scope_stub()
