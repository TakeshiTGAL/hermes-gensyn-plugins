from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]


def _text(*names):
    return "\n".join((ROOT / name).read_text() for name in names)


def test_public_text_states_the_required_facts():
    plugin = (ROOT / "plugin.yaml").read_text()
    docs = _text("plugin.yaml", "README.md", "SECURITY.md", "skills/ree/SKILL.md")
    assert "Disclosure —" in plugin
    assert "Choosing always" in plugin
    assert "not limited to Hugging Face" in plugin
    assert "hermes-ree" in docs
    assert "does not pull" in plugin
    assert "REE-Binary-License" in docs
    assert "text_mismatch" in docs
    assert "hermes tools" in docs
    assert "plugin-data/hermes-gensyn-ree" in docs
    assert "does not start Docker" not in plugin
    assert "network none" in plugin or "--network none" in plugin
    readme = (ROOT / "README.md").read_text()
    skill = (ROOT / "skills/ree/SKILL.md").read_text()
    head = " ".join(readme.split("## Quick Start", 1)[0].split())
    assert "compares those fields" not in head
    assert "A `ree_version` difference alone is `reexecuted_and_text_match`." in head
    assert "Verification is the token hash." in head
    assert "`text_output` is reference text and is being removed." in head
    assert "If a compared readable field differs and the hashes match, the result is" not in head
    assert "do not repeat the notice" not in docs
    start = "| `level` | Meaning |"
    end = "Compared hashes:"
    assert readme[readme.index(start):readme.index(end)] == skill[skill.index(start):skill.index(end)]


def test_statements_are_not_joined_with_semicolons():
    names = ("service.py", "docker.py", "process.py")
    text = "\n".join((ROOT / name).read_text() for name in names)
    assert "deadline; body" not in text
    assert "append(cursor); cursor" not in text
    assert "write_bytes(payload); path.chmod" not in text
    assert "__init__(message); self.kind" not in text


def test_prompt_phrase_matches_the_gate():
    from contract import _prompt_problem
    from schemas import DESCRIPTIONS
    samples = ("\n", "\r", "\x00", "-prompt")
    phrase = "text from 1 to 4000 characters without newline, CR, NUL, or a leading hyphen"
    assert {_prompt_problem(item) for item in samples} == {("bad_format", phrase)}
    docs = " ".join(_text("README.md", "skills/ree/SKILL.md").split())
    assert phrase in docs
    for word in ("newline", "CR", "NUL", "leading hyphen"):
        assert word in DESCRIPTIONS["ree_infer"]


def test_catalog_gate_reads_every_draft(tmp_path):
    import importlib.util
    path = REPO / "catalog" / "gate.py"
    spec = importlib.util.spec_from_file_location("catalog_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    verdict = module.draft_verdict(REPO, tmp_path)
    assert verdict in module.DRAFT_RESULTS
    assert module.npm_ci_verdict(REPO) in module.NPM_CI_RESULTS
    for sample, want in module.REQUIRES_SAMPLES:
        assert module.requires_form(sample) == want
    for sample, want in module.NPM_CI_SAMPLES:
        assert module.npm_ci_forms(sample) == (want,)


def test_catalog_draft_matches_the_manifest():
    plugin = (ROOT / "plugin.yaml").read_text()
    match = re.search(r"^description: >-\n((?:  .*\n)+)", plugin, re.M)
    assert match
    parts = []
    for line in match.group(1).splitlines():
        parts.append(line[2:] if line.startswith("  ") else line)
    folded = " ".join(part.strip() for part in parts).strip()
    draft = (REPO / "catalog" / "hermes-gensyn-ree.yaml").read_text()
    found = re.search(r'^description: (".*")\s*$', draft, re.M)
    assert found
    description = json.loads(found.group(1))
    assert description != folded
    assert 900 <= len(description) <= 1100
    assert "Publish only" not in description
    for phrase in (
        "ree_validate_receipt",
        "text_output",
        "does not re-execute",
        "gensynai/ree:v0.8.0",
        "REE-Binary-License",
        "not limited to Hugging Face",
        "cron, yolo",
        "network none",
        "hermes tools",
        "plugin-data/hermes-gensyn-ree",
        "hostile-code sandbox",
        "Docker daemon",
    ):
        assert phrase in description
    assert re.search(r"^repo: https://github.com/TakeshiTGAL/hermes-gensyn-plugins$", draft, re.M)
    assert re.search(r"^subdir: packages/ree$", draft, re.M)
    assert re.search(r"^# sha is set in the catalog pull request\.$", draft, re.M)
    assert re.search(r'^sha: "0{40}"$', draft, re.M)
    assert re.search(r"(?m)^image:", draft) is None
    assert "Disclosure —" in draft
