from __future__ import annotations

import json
import re
from pathlib import Path

from contract import TABLES
from schemas import DESCRIPTIONS

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "packages" / "delphi"


def text(path):
    return path.read_text()


def test_manifest_registers_only_five_tools_and_transform():
    manifest = text(PACKAGE / "plugin.yaml")
    block = re.search(r"^provides_tools:\n((?:  - .+\n)+)", manifest, re.M)
    assert block
    assert sorted(re.findall(r"- (delphi_[a-z_]+)", block.group(1))) == [
        "delphi_compute_edge",
        "delphi_get_market",
        "delphi_get_positions",
        "delphi_list_markets",
        "delphi_query_subgraph",
        "delphi_quote_buy",
        "delphi_quote_sell",
    ]
    assert "provides_hooks:\n  - transform_tool_result" in manifest
    assert "post_tool_call" not in manifest
    assert "platforms:\n  - linux\n  - macos" in manifest
    assert 'requires_hermes: ">=0.21.4"' in manifest


def test_public_facts_match_constants_and_scope():
    public = "\n".join(
        text(path)
        for path in (
            ROOT / "README.md",
            ROOT / "SECURITY.md",
            ROOT / "DECISIONS.md",
            PACKAGE / "README.md",
            PACKAGE / "plugin.yaml",
            PACKAGE / "skills" / "delphi" / "SKILL.md",
        )
    )
    for phrase in (
        "seven read-only tools",
        "30",
        "60 seconds",
        "Linux",
        "macOS",
        "testnet",
        "mainnet",
        "competition-testnet",
        "signer",
        "not investment advice",
        "hermes tools",
        "Not made by Gensyn",
        "0.2",
    ):
        assert phrase.lower() in public.lower()
    assert "<HERMES_HOME>" in public
    assert "DELPHI_API_ACCESS_KEY" in public
    assert "delphi-api.gensyn.ai" in public
    assert "api.delphi.fyi" in public


def test_no_forbidden_implementation_surface():
    sources = "\n".join(
        text(path)
        for path in PACKAGE.rglob("*")
        if path.suffix in (".py", ".mjs")
        and "tests" not in path.parts
        and "node_modules" not in path.parts
    )
    for token in (
        "buyShares(",
        "sellShares(",
        "redeemMarket(",
        "writeContract",
        "readContract",
        "eth_chainId",
        "urllib",
        "post_tool_call",
    ):
        assert token not in sources
    assert sources.count("import subprocess") == 1


def test_required_edge_fields_are_named_in_public_text():
    required = [
        name for name, spec in TABLES["args.compute_edge"].items() if spec["required"]
    ]
    assert "your_probability" in required
    skill = text(PACKAGE / "skills" / "delphi" / "SKILL.md")
    readme = text(PACKAGE / "README.md")
    desc = DESCRIPTIONS["delphi_compute_edge"]
    for name in required:
        assert name in skill
        assert name in readme
        assert name in desc


def test_bridge_imports_only_sdk_and_node_modules():
    bridge = text(PACKAGE / "scripts" / "bridge.mjs")
    imports = re.findall(r'from "([^"]+)"', bridge)
    assert imports
    assert all(item == "@gensyn-ai/gensyn-delphi-sdk" or item.startswith("node:") for item in imports)
    assert "fixedMessage" in bridge
    assert "publicMessage" not in bridge


def test_dependency_is_exactly_sdk_210():
    package = text(PACKAGE / "package.json")
    lock = text(PACKAGE / "package-lock.json")
    assert '"@gensyn-ai/gensyn-delphi-sdk": "2.1.0"' in package
    assert '"version": "2.1.0"' in lock


def test_ci_is_fresh_runner_safe_and_keyed_missing_key_fails():
    workflow = text(ROOT / ".github" / "workflows" / "smoke-test.yml")
    assert "takeshi" + "tgal" not in workflow
    assert "DELPHI_API_ACCESS_KEY" in workflow
    assert "fork" in workflow
    assert "exit 1" in workflow
    assert "python -m pytest" in workflow
    assert workflow.count("repository: NousResearch/hermes-agent") == 2
    assert workflow.count("PYTHONPATH:") == 2


def _folded_description(text):
    match = re.search(r"^description: >-\n((?:  .*\n)+)", text, re.M)
    assert match
    parts = []
    for line in match.group(1).splitlines():
        parts.append(line[2:] if line.startswith("  ") else line)
    return " ".join(part.strip() for part in parts).strip()


def test_catalog_gate_reads_every_draft(tmp_path):
    import importlib.util
    path = ROOT / "catalog" / "gate.py"
    spec = importlib.util.spec_from_file_location("catalog_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    verdict = module.draft_verdict(ROOT, tmp_path)
    assert verdict in module.DRAFT_RESULTS
    assert module.npm_ci_verdict(ROOT) in module.NPM_CI_RESULTS
    for sample, want in module.REQUIRES_SAMPLES:
        assert module.requires_form(sample) == want
    for sample, want in module.NPM_CI_SAMPLES:
        assert module.npm_ci_forms(sample) == (want,)


def test_catalog_draft_matches_the_manifest():
    plugin = text(PACKAGE / "plugin.yaml")
    draft = text(ROOT / "catalog" / "hermes-gensyn-delphi.yaml")
    match = re.search(r'^description: (".*")\s*$', draft, re.M)
    assert match
    assert json.loads(match.group(1)) == _folded_description(plugin)
    assert re.search(r"^repo: https://github.com/TakeshiTGAL/hermes-gensyn-plugins$", draft, re.M)
    assert re.search(r"^subdir: packages/delphi$", draft, re.M)
    assert re.search(r"^# sha is set in the catalog pull request\.$", draft, re.M)
    assert re.search(r'^sha: "0{40}"$', draft, re.M)
    assert re.search(r"(?m)^image:", draft) is None
    assert "Disclosure —" in draft


def test_package_readme_names_public_inputs_and_static_row_columns():
    readme = text(PACKAGE / "README.md")
    for table in (
        "args.list_markets",
        "args.get_market",
        "args.get_positions",
        "args.query_subgraph",
        "args.compute_edge",
        "out.market",
        "out.position",
    ):
        for field in TABLES[table]:
            assert f"`{field}`" in readme


def test_receipt_docs_keep_the_full_text_inside_the_box():
    phrase = (
        "The full receipt stays inside `proof_receipt_json`, an untrusted box "
        "(`untrusted_text: true`) whose `text` is the original JSON, not clipped, "
        "and is not left as a bare string outside that box."
    )
    paths = (
        PACKAGE / "README.md",
        PACKAGE / "skills" / "delphi" / "SKILL.md",
        PACKAGE / "CHANGELOG.md",
    )
    for path in paths:
        assert phrase in " ".join(text(path).split())
    source = text(PACKAGE / "service.py")
    assert '"proof_receipt_json": _box(raw, False)' in source
