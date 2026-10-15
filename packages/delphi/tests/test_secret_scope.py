"""Profile scope wins. Production code does not read these names from os.environ."""
from __future__ import annotations
import ast
from pathlib import Path
import pytest
from agent.secret_scope import (
    UnscopedSecretError, reset_secret_scope, set_multiplex_active, set_secret_scope,
)
from bridge import _environment
from settings import read_setting
ROOT = Path(__file__).resolve().parents[1]
NAMES = frozenset((
    "DELPHI_API_ACCESS_KEY", "DELPHI_NETWORK", "DELPHI_WALLET_ADDRESS",
))
_SAMPLES = (
    (
        'def look(env_name):\n    return os.environ.get(env_name)\nlook("DELPHI_NETWORK")\n',
        True,
    ),
    ('import os\nos.environ.pop("DELPHI_API_ACCESS_KEY", None)\n', True),
    ('import os\nos.environ.get("PATH")\n', False),
    ('import os\nenv = {"DELPHI_API_ACCESS_KEY": ""}\n', False),
)


def _reset(token):
    reset_secret_scope(token)
    set_multiplex_active(False)


def test_scope_wins_over_environ(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "from-env")
    token = set_secret_scope({"DELPHI_API_ACCESS_KEY": "from-scope"})
    try:
        assert read_setting("api_access_key") == "from-scope"
        assert _environment(True)["DELPHI_API_ACCESS_KEY"] == "from-scope"
    finally:
        _reset(token)


def test_multiplex_miss_does_not_read_environ(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "other-profile")
    set_multiplex_active(True)
    token = set_secret_scope({})
    try:
        assert read_setting("api_access_key", "") == ""
        assert "DELPHI_API_ACCESS_KEY" not in _environment(True)
    finally:
        _reset(token)


def test_unscoped_error_is_not_swallowed(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "other-profile")
    set_multiplex_active(True)
    try:
        with pytest.raises(UnscopedSecretError):
            read_setting("api_access_key")
    finally:
        set_multiplex_active(False)


def _string(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _slice(node):
    index = getattr(ast, "Index", None)
    if index is not None and isinstance(node, index):
        return node.value
    return node


def _environ_owner(node):
    if not isinstance(node, ast.Attribute) or node.attr != "environ":
        return False
    return isinstance(node.value, ast.Name) and node.value.id == "os"


def _environ_call(node):
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "getenv":
        return isinstance(func.value, ast.Name) and func.value.id == "os"
    if isinstance(func, ast.Attribute) and func.attr in {"get", "pop"}:
        return _environ_owner(func.value)
    return False


def _assigned(owner, name):
    found = []
    for node in ast.walk(owner):
        if isinstance(node, ast.Assign):
            values = node.targets
            text = _string(node.value)
        elif isinstance(node, ast.AnnAssign):
            values = [node.target]
            text = _string(node.value) if node.value is not None else None
        else:
            continue
        if text in NAMES and any(isinstance(item, ast.Name) and item.id == name for item in values):
            found.append(text)
    return found


def _passed(tree, fn_name, index):
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != fn_name or len(node.args) <= index:
            continue
        text = _string(node.args[index])
        if text in NAMES:
            found.append(text)
    return found


class _Scan(ast.NodeVisitor):
    def __init__(self, tree):
        self.tree = tree
        self.fn = None
        self.hits = []

    def visit_FunctionDef(self, node):
        previous = self.fn
        self.fn = node
        self.generic_visit(node)
        self.fn = previous

    visit_AsyncFunctionDef = visit_FunctionDef

    def _note(self, arg):
        text = _string(arg)
        if text in NAMES:
            self.hits.append(text)
            return
        if not isinstance(arg, ast.Name):
            return
        owner = self.fn or self.tree
        if _assigned(owner, arg.id):
            self.hits.append(arg.id)
        if self.fn is None:
            return
        names = [item.arg for item in self.fn.args.args]
        if arg.id not in names:
            return
        if _passed(self.tree, self.fn.name, names.index(arg.id)):
            self.hits.append(arg.id)

    def visit_Call(self, node):
        if _environ_call(node) and node.args:
            self._note(node.args[0])
        self.generic_visit(node)

    def visit_Subscript(self, node):
        if _environ_owner(node.value):
            self._note(_slice(node.slice))
        self.generic_visit(node)


def credential_environ_hits(source):
    tree = ast.parse(source)
    scan = _Scan(tree)
    scan.visit(tree)
    return scan.hits


def test_getter_exception_does_not_become_testnet(monkeypatch):
    import json
    from service import dispatch
    from settings import bind_config
    monkeypatch.delenv("DELPHI_NETWORK", raising=False)
    set_multiplex_active(False)
    token = set_secret_scope({})

    def broken(_name):
        raise RuntimeError("broken")

    bind_config(broken)
    try:
        assert read_setting("network", "testnet") is None
        body = json.loads(dispatch("delphi_query_subgraph", {"mode": "meta"}))
    finally:
        bind_config(None)
        reset_secret_scope(token)
    assert body["ok"] is False
    assert body["error_type"] == "config"
    assert body["missing"] == ["DELPHI_NETWORK"]


def test_name_and_pop_forms_are_caught():
    for source, bad in _SAMPLES:
        assert bool(credential_environ_hits(source)) is bad


def test_production_does_not_read_these_names_from_environ():
    hits = []
    for package in (ROOT, ROOT.parent / "ree"):
        for path in package.rglob("*.py"):
            if "tests" in path.parts or "node_modules" in path.parts:
                continue
            found = credential_environ_hits(path.read_text())
            if found:
                hits.append(path.name + ":" + ",".join(found))
    assert hits == []
