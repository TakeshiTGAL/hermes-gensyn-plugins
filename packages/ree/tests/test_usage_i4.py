"""Typed refusals from the argument table, plus the recorded sessions."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from contract import (
    ARG_FIELDS, MODELS, NEXT_VERIFY, entry_refusal, make_sample, receipt_refusal, validate,
)
from gate import question, reason_fits
from schemas import DESCRIPTIONS
from service import infer, validate_receipt, verify_receipt
from support import install_fake

PLANTED = "PLANTED_VALUE_i4"
LIVE = Path(__file__).resolve().parents[3].parent / ".gensyn-test" / "ree-live"
ADDED = ("field", "problem", "expected", "allowed_fields")
PROBLEMS = ("missing", "unknown_field", "wrong_type", "out_of_range", "bad_format", "conflict")


def _body(text):
    return json.loads(text)


def _base(tool):
    if tool == "ree_infer":
        return {"model": MODELS[0], "prompt": "hello", "max_new_tokens": 4}
    return {"receipt_path": "/tmp/receipt.json"}


def _applicable(tool, arg, problem):
    if problem == "conflict":
        return False
    if problem == "unknown_field":
        return True
    if problem == "missing":
        return True
    if arg == "max_new_tokens":
        return problem in ("wrong_type", "out_of_range")
    if arg == "model":
        return problem in ("wrong_type", "bad_format")
    if arg == "prompt":
        return problem in ("wrong_type", "bad_format", "out_of_range")
    if arg == "receipt_path":
        return problem in ("wrong_type", "bad_format", "out_of_range")
    return False


def _payload(tool, arg, problem):
    params = _base(tool)
    if problem == "missing":
        params.pop(arg)
        return params, None
    if problem == "unknown_field":
        params["not_a_field"] = PLANTED
        return params, PLANTED
    if arg == "max_new_tokens" and problem == "wrong_type":
        params[arg] = 16.0
        return params, "16.0"
    if arg == "max_new_tokens" and problem == "out_of_range":
        params[arg] = 257
        return params, "257"
    if arg == "model" and problem == "wrong_type":
        params[arg] = 1
        return params, None
    if arg == "model" and problem == "bad_format":
        params[arg] = "org/" + PLANTED
        return params, PLANTED
    if arg == "prompt" and problem == "wrong_type":
        params[arg] = 1
        return params, None
    if arg == "prompt" and problem == "bad_format":
        params[arg] = "hello\n" + PLANTED
        return params, PLANTED
    if arg == "prompt" and problem == "out_of_range":
        params[arg] = "x" * 4001
        return params, None
    if arg == "receipt_path" and problem == "wrong_type":
        params[arg] = 1
        return params, None
    if arg == "receipt_path" and problem == "bad_format":
        params[arg] = "-" + PLANTED
        return params, PLANTED
    params[arg] = "p" * 4097
    return params, None


def _cases():
    rows = []
    for tool, fields in ARG_FIELDS.items():
        for arg in fields:
            for problem in PROBLEMS:
                rows.append((tool, arg, problem))
    return rows


@pytest.mark.parametrize("tool,arg,problem", _cases())
def test_every_tool_argument_and_problem(tool, arg, problem):
    if not _applicable(tool, arg, problem):
        found = entry_refusal(tool, _base(tool))
        assert found is None or found[1] != problem
        return
    params, planted = _payload(tool, arg, problem)
    found = entry_refusal(tool, params)
    assert found is not None
    assert found[1] == problem
    blob = json.dumps({"field": found[0], "problem": found[1], "expected": found[2],
                       "allowed_fields": list(found[3])})
    if planted:
        assert planted not in blob
    assert set(found[3]) == set(ARG_FIELDS[tool])


def test_stop_and_other_model_names_pass_the_shape():
    sample = make_sample("receipt")
    sample["output"]["finish_reason"] = "stop"
    assert validate("receipt", sample) is None
    assert receipt_refusal(sample) is None
    sample["output"]["finish_reason"] = "eos_token"
    assert validate("receipt", sample) is None
    sample["model"]["name"] = "Qwen/Qwen3-8B"
    assert validate("receipt", sample) is None
    sample["output"]["finish_reason"] = "bad value"
    found = receipt_refusal(sample)
    assert found[0] == "output.finish_reason" and found[1] == "bad_format"
    assert "bad value" not in json.dumps(found[:3])
    sample["input"]["tools"] = [{"name": "lookup"}]
    sample["output"]["finish_reason"] = "stop"
    assert validate("receipt", sample) is None
    sample["input"]["tools"] = [{
        "type": "function",
        "function": {
            "name": "lookup",
            "description": "Look up a fact",
            "parameters": {"type": "object", "properties": {}},
        },
    }]
    assert validate("receipt", sample) is None
    sample["input"]["tools"] = [{"name": "bad value"}]
    assert validate("receipt", sample) is not None


def test_large_model_question_fits_and_warns():
    name = "a/" + ("b" * 126)
    text = question("verify", name)
    assert reason_fits(text)
    assert "gigabytes" in text
    assert "memory" in text
    assert "CPU-only" in text
    assert "Not limited to Hugging Face" in text
    assert "cache token file visible in container." in text
    assert "Takes minutes" in question("verify", MODELS[0])


def test_consistent_points_at_verify(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    from support import sample_file
    path = sample_file(tmp_path)
    body = _body(validate_receipt({"receipt_path": str(path)}))
    assert body["level"] == "consistent"
    assert body["next"]["tool"] == NEXT_VERIFY["tool"]
    assert body["next"]["needs_approval"] is True
    assert body["next"]["checks"] == ["re-execution", "text fields"]


def test_infer_float_and_denied_approval_do_not_echo(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    prompt = "Is Tokyo the capital of Japan? Answer yes or no."
    floated = _body(infer({
        "model": "Qwen/Qwen2.5-0.5B", "prompt": prompt, "max_new_tokens": 16.0,
    }))
    assert floated["problem"] == "wrong_type"
    assert "16.0" not in json.dumps(floated)
    assert prompt not in json.dumps(floated)
    denied = _body(infer(
        {"model": "facebook/opt-125m", "prompt": "東京は日本の首都？ yes か no", "max_new_tokens": 16},
        approver=lambda *args, **kwargs: (False, {"approved": False, "outcome": "denied"}),
    ))
    assert denied["error_type"] == "approval_denied"
    assert denied["retryable"] is False
    assert "Do not retry." in denied["message"]
    assert "東京" not in json.dumps(denied)


def test_recorded_receipts_validate(tmp_path, monkeypatch):
    if not LIVE.exists():
        pytest.skip("recorded receipts are not on this machine")
    install_fake(tmp_path, monkeypatch)
    for name in ("t_meta.json", "t_model.json", "t_text.json"):
        src = LIVE / name
        dest = tmp_path / name
        shutil.copy(src, dest)
        body = _body(validate_receipt({"receipt_path": str(dest)}))
        assert body["level"] == "consistent", name
        assert body["next"]["tool"] == "ree_verify_receipt"
    denied = _body(verify_receipt(
        {"receipt_path": str(tmp_path / "t_text.json")},
        approver=lambda *args, **kwargs: (False, {"approved": False, "outcome": "denied"}),
    ))
    assert denied["error_type"] == "approval_denied"
    assert denied["retryable"] is False


def test_descriptions_match_the_tool_names():
    assert DESCRIPTIONS["ree_validate_receipt"].startswith("Returns hash checks.")
    assert "does not re-execute" in DESCRIPTIONS["ree_validate_receipt"]
    assert "Needs approval." in DESCRIPTIONS["ree_verify_receipt"]
    for name in MODELS:
        assert name in DESCRIPTIONS["ree_infer"]
