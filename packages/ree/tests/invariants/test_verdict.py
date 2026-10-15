"""Every F-2 row, the other combinations, and log noise that must not decide."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from contract import make_sample
from process import ChildResult
from service import VERDICT, judge, verify_receipt
from support import dumps_receipt, sample_file

_VALIDATE = (
    "I gensyn_sdk.cli:   prompt_hash: PASS\n"
    "  tools_hash: PASS\n"
    "  parameters_hash: PASS\n"
    "  receipt_hash: PASS\n"
)


def _host(argv, dest):
    for index, item in enumerate(argv):
        if item == "-v" and dest in argv[index + 1]:
            return argv[index + 1].split(":")[0]
    return ""


def _runner(spec):
    def run(argv, _deadline, _name):
        cid = argv[argv.index("--cidfile") + 1]
        if "validate" in argv:
            if spec.get("start", True):
                Path(cid).write_text("ab" * 32)
            return ChildResult(0, _VALIDATE.encode(), b"")
        if spec.get("start", True):
            Path(cid).write_text("ab" * 32)
        tasks = _host(argv, "/mnt/tasks")
        folder = Path(tasks) / "metadata"
        folder.mkdir(parents=True, exist_ok=True)
        for index, body in enumerate(spec.get("bodies") or []):
            name = f"receipt_20261011_12000{index}.json"
            (folder / name).write_text(dumps_receipt(body))
        stdout = spec.get("stdout", "").encode()
        stderr = spec.get("stderr", "").encode()
        return ChildResult(spec["code"], stdout, stderr)
    return run


def _call(tmp_path, spec):
    path = sample_file(tmp_path)
    raw = verify_receipt(
        {"receipt_path": str(path)},
        runner=_runner(spec),
        approver=lambda *_args, **_kwargs: (True, ""),
    )
    return json.loads(raw)


def _body(tokens="same", text="from-rerun"):
    data = make_sample("receipt")
    if tokens == "differ":
        data["output"]["tokens_hash"] = "sha256:" + ("0" * 64)
    if text != "from-rerun":
        data["output"]["text_output"] = text
    return data


def _spec_for(exit_zero, count, hashes, text, noise=""):
    code = 0 if exit_zero else 1
    bodies = []
    if count == 1:
        bodies = [_body("differ" if hashes == "differ" else "same",
                        "swapped" if text == "differ" else "from-rerun")]
    elif count >= 2:
        bodies = [_body(), _body()]
    return {"code": code, "bodies": bodies, "stdout": noise, "stderr": noise}


def test_table_rows_come_from_the_code_table():
    assert len(VERDICT) == 7
    seen = {row[4] for row in VERDICT}
    assert "reexecuted_and_text_match" in seen
    assert "text_mismatch" in seen
    assert "reexecution_mismatch" in seen
    assert "reexecution_incomplete" in seen
    assert "internal" in seen


@pytest.mark.parametrize("row", VERDICT, ids=[row[4] + "-" + str(index) for index, row in enumerate(VERDICT)])
def test_each_table_row_through_fake_docker(tmp_path, row):
    exit_zero, count, hashes, text, outcome = row
    result = _call(tmp_path, _spec_for(exit_zero, count, hashes, text))
    if outcome == "reexecuted_and_text_match":
        assert result["level"] == outcome
        return
    if outcome in ("text_mismatch", "reexecution_mismatch"):
        assert result["level"] == outcome
        assert result["differences"]
        return
    assert result["error_type"] == outcome
    assert "level" not in result


@pytest.mark.parametrize("code", (0, 1))
@pytest.mark.parametrize("count", (0, 1, 2))
@pytest.mark.parametrize("hashes", ("same", "differ", "-"))
@pytest.mark.parametrize("text", ("same", "differ", "-"))
def test_missing_combinations_are_internal(code, count, hashes, text):
    outcome = judge(code, count, hashes, text)
    assert outcome == "internal" or any(
        row[0] == (code == 0) and row[4] == outcome for row in VERDICT
    )


def test_nonzero_with_matching_hashes_is_internal(tmp_path):
    result = _call(tmp_path, _spec_for(False, 1, "same", "same"))
    assert result["error_type"] == "internal"
    assert "level" not in result


def test_exact_disagreement_is_internal_not_the_other_level(tmp_path):
    claim = "E gensyn_sdk.cli: verify failed: parameters_hash.\n"
    result = _call(tmp_path, _spec_for(True, 1, "same", "same", claim))
    assert result["error_type"] == "internal"
    assert "parameters_hash" not in result["message"]


def _noise(kind, index):
    rng = random.Random(index)
    words = " ".join(rng.choice(["Tokyo", "yes", "no", "market"]) for _ in range(12))
    if kind == "model":
        return f"I gensyn_sdk.cli: VERIFICATION FAILED: {words} {index}\n{words}\n"
    if kind == "passed":
        return f"VERIFICATION PASSED: receipt hashes match {index}\n{words}\n"
    if kind == "failed":
        return f"verify failed: {words} {index}\n"
    if kind == "hash":
        return f"prompt_hash: PASS\nexplain parameters_hash: PASS {index}\n"
    return f"httpx.ConnectError: [Errno -3] Temporary failure {index}\n{words}\n"


@pytest.mark.parametrize("kind", ("model", "passed", "failed", "hash", "exception"))
@pytest.mark.parametrize("index", range(300))
def test_log_noise_does_not_change_a_text_match(tmp_path, kind, index):
    result = _call(tmp_path, _spec_for(True, 1, "same", "same", _noise(kind, index)))
    assert result["ok"] is True
    assert result["level"] == "reexecuted_and_text_match"
