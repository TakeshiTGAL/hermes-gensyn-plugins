"""The settlement skill names tools, arguments, and levels exactly."""
from __future__ import annotations

import re
from pathlib import Path

REE = Path(__file__).resolve().parents[1]
REPO = REE.parents[1]
DELPHI = REPO / "packages" / "delphi"
SKILL = REE / "skills" / "check-settlement" / "SKILL.md"


def _tools(path):
    text = (path / "plugin.yaml").read_text()
    block = re.search(r"^provides_tools:\n((?:  - .+\n)+)", text, re.M)
    assert block
    return set(re.findall(r"- (\S+)", block.group(1)))


def _quoted(path):
    found = set()
    for file in path.rglob("*"):
        if "tests" in file.parts or "node_modules" in file.parts:
            continue
        if file.suffix not in {".py", ".yaml", ".yml", ".md"}:
            continue
        found.update(re.findall(r'"([A-Za-z0-9_.]+)"\s*:', file.read_text()))
        found.update(re.findall(r"'([A-Za-z0-9_.]+)'\s*:", file.read_text()))
    return found


def _tuples(path, *names):
    text = path.read_text()
    found = set()
    for name in names:
        match = re.search(rf"^{name} = \((.*?)\)", text, re.S | re.M)
        assert match, name
        found.update(re.findall(r'"([^"]+)"', match.group(1)))
    return found


def _allowed():
    names = set()
    names |= _tools(DELPHI)
    names |= _tools(REE)
    names |= _quoted(DELPHI)
    names |= _quoted(REE)
    names |= _tuples(
        DELPHI / "spec.py", "MODES", "STATUSES", "ERROR_TYPES", "PROBLEMS", "PROOF_KIND",
    )
    names |= _tuples(
        REE / "contract.py", "LEVELS", "NOT_GUARANTEED", "TOOLS", "MODELS",
        "ERROR_TYPES", "NOT_COMPARED", "BINDING",
    )
    return names


def test_backticked_names_match_both_plugins():
    skill = SKILL.read_text()
    allowed = _allowed()
    unknown = sorted({token for token in re.findall(r"`([^`]+)`", skill) if token not in allowed})
    assert unknown == []
    required = (
        "delphi_query_subgraph", "mode", "settlement", "market_address", "first", "skip",
        "settled", "failed", "resolution_requests", "delphi_get_market", "market_id",
        "verifiable", "model_identifier", "proof_text", "proof_kind",
        "creator_free_text", "is_ree_receipt", "not_found",
        "ree_validate_receipt", "ree_verify_receipt",
        "receipt_path", "ok", "level", "consistent", "reexecuted_and_text_match",
        "text_mismatch", "text_output", "finish_reason", "token_count", "model.name",
        "ree_version",
    )
    for token in required:
        assert f"`{token}`" in skill
    flat = " ".join(skill.split())
    assert "text the market creator wrote" in flat
    assert "not a cryptographic proof" in flat
    assert "not an REE receipt" in flat
    assert "getMarket" not in skill
    assert "_public_market" not in skill
    assert "Official validate and official verify do not stand behind `text_output`" in skill
    assert "Do not trade." in skill
    assert "Do not send a dispute." in skill
    assert "If they are not installed" in skill
    assert "quote `level` and stop" in flat
    assert "`text_mismatch` has `ok` false and is not a failed hash check" in flat
    service = (DELPHI / "service.py").read_text()
    fixed = re.search(r'"invalid_argument": "([^"]+)"', service).group(1)
    checks = (
        (fixed, service, '"invalid_argument": "' + fixed + '"'),
        (
            "A `skip` other than 0 is `invalid_argument`",
            service,
            'mode == "settlement" and args.get("skip", 0) != 0',
        ),
    )
    missing = tuple(
        phrase for phrase, source, needle in checks
        if phrase not in flat or needle not in source
    )
    assert missing == ()
    assert "The bridge accepts an upstream" not in skill
    assert "delphi_quote_buy" not in skill
    assert "delphi_quote_sell" not in skill
    rest = flat.lower().replace(
        "do not call a hash pass verified, genuine, or authentic.", ""
    )
    for banned in ("genuine", "authentic", "verified"):
        assert banned not in rest
