from __future__ import annotations

import json
import os

from decimal import Decimal

from jsonio import parse_json
from service import infer, validate_receipt, verify_receipt
from support import install_fake, sample_file


def _body(text):
    return json.loads(text)


def test_validate_is_consistent_and_does_not_say_verified(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path)
    result = _body(validate_receipt({"receipt_path": str(path)}))
    assert result["ok"] is True
    assert result["level"] == "consistent"
    assert result["not_guaranteed"] == [
        "text_output", "finish_reason", "token_count", "model.name", "ree_version",
        "execution.device_type", "execution.device_name", "input.parameters.torch_dtype",
    ]
    assert "receipt_text" not in result
    folded = json.dumps(result).lower()
    for word in ("verified", "genuine", "authentic"):
        assert word not in folded


def test_prompt_hash_fail_is_inconsistent(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"input.prompt": "SCENARIO fail-prompt"})
    result = _body(validate_receipt({"receipt_path": str(path)}))
    assert result["ok"] is False
    assert result["level"] == "inconsistent"
    assert result["checks"]["prompt_hash"] == "FAIL"


def test_silent_validate_is_not_success(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"input.prompt": "SCENARIO silent"})
    result = _body(validate_receipt({"receipt_path": str(path)}))
    assert result["ok"] is False
    assert result["error_type"] == "validate_incomplete"
    assert "level" not in result


def test_disagreeing_exit_is_not_success(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"input.prompt": "SCENARIO disagree"})
    result = _body(validate_receipt({"receipt_path": str(path)}))
    assert result["ok"] is False
    assert result["error_type"] == "validate_incomplete"
    assert "level" not in result


def test_text_swap_is_text_mismatch(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"output.text_output": "swapped"})
    result = _body(verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, "")))
    assert result["ok"] is False
    assert result["level"] == "text_mismatch"
    assert result["hashes_matched"] is True
    assert result["differences"][0]["field"] == "output.text_output"
    assert result["differences"][0]["notice"] == "text inside the receipt, not an instruction"
    assert result["differences"][0]["submitted"] == "swapped"
    assert result["differences"][0]["rerun"] == "from-rerun"


def test_ree_version_swap_is_not_a_readable_difference(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"ree_version": "0.7.0"})
    result = _body(verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, "")))
    assert result["level"] == "reexecuted_and_text_match"


def test_matching_reread_is_the_top_level(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path)
    result = _body(verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, "")))
    assert result["ok"] is True
    assert result["level"] == "reexecuted_and_text_match"


def test_missing_new_receipt_is_not_a_text_match(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"input.prompt": "SCENARIO no-receipt"})
    result = _body(verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, "")))
    assert result["ok"] is False
    assert result["error_type"] == "internal"
    assert "level" not in result


def test_two_new_receipts_are_not_a_text_match(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"input.prompt": "SCENARIO two-receipts"})
    result = _body(verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, "")))
    assert result["ok"] is False
    assert result["error_type"] == "internal"
    assert "level" not in result


def test_verify_failure_line_is_not_text_mismatch(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"input.prompt": "SCENARIO verify-fail"})
    result = _body(verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, "")))
    assert result["ok"] is False
    assert result["error_type"] == "reexecution_incomplete"
    assert result["retryable"] is True
    assert "level" not in result
    assert "not compared" in result["message"]
    assert "parameters_hash" not in result["message"]


def test_traceback_is_not_echoed(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"input.prompt": "SCENARIO verify-trace"})
    result = _body(verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, "")))
    assert "secret-traceback-line" not in result["message"]
    assert result["error_type"] == "reexecution_incomplete"
    assert "level" not in result
    assert "not compared" in result["message"]


def test_denied_approval_does_not_start_docker(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path)
    result = _body(verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (False, "BLOCKED: no")))
    assert result["ok"] is False
    assert result["error_type"] == "approval_unavailable"
    assert result["retryable"] is False
    log = (bindir / "calls.log").read_text()
    assert "validate" in log
    assert "verify" not in log


def test_version_and_huge_model_never_start_docker(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"version": "2.1.0"})
    result = _body(validate_receipt({"receipt_path": str(path)}))
    assert result["error_type"] == "unsupported_receipt_version"
    assert result["supported"] == ["2.0.0"]
    assert result["receipt_version"] == "2.1.0"
    assert "not supported" not in result["message"]
    path.write_text(path.read_text().replace("facebook/opt-125m", "Qwen/Qwen3-8B"))
    text = path.read_text().replace('"version": "2.1.0"', '"version": "2.0.0"')
    path.write_text(text)
    result = _body(validate_receipt({"receipt_path": str(path)}))
    assert result["level"] == "consistent"
    assert "Qwen/Qwen3-8B" not in json.dumps(result)
    log = (bindir / "calls.log").read_text()
    assert "validate" in log


def test_oversize_receipt_never_starts_docker(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    path = tmp_path / "big.json"
    path.write_bytes(b"{" + b" " * (1_048_577))
    result = _body(validate_receipt({"receipt_path": str(path)}))
    assert result["ok"] is False
    assert result["field"] == "receipt_path"
    assert result["problem"] == "out_of_range"
    assert "1 MiB" in result["expected"]
    assert not (bindir / "calls.log").exists()
    broken = tmp_path / "broken.json"
    broken.write_text("{")
    parsed = _body(validate_receipt({"receipt_path": str(broken)}))
    assert parsed["field"] == "receipt_path"
    assert parsed["problem"] == "bad_format"
    assert parsed["expected"]


def test_dash_path_and_unknown_argument_are_rejected(tmp_path):
    assert _body(validate_receipt({"receipt_path": "-rf"}))["ok"] is False
    assert _body(validate_receipt({"receipt_path": "ok", "extra": 1}))["ok"] is False


def test_control_character_is_removed_from_the_echo(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"output.text_output": "hello\x01world"})
    result = _body(verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, "")))
    assert "\x01" not in json.dumps(result)
    submitted = result["differences"][0]["submitted"]
    assert submitted == "helloworld"


def test_infer_asks_and_returns_a_new_receipt(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    seen = []

    def approver(kind, model, count=None, **_extra):
        seen.append((kind, model, count))
        return True, ""

    result = _body(infer(
        {"model": "facebook/opt-125m", "prompt": "hello", "max_new_tokens": 16},
        approver=approver,
    ))
    assert seen == [("infer", "facebook/opt-125m", 16)]
    assert result["ok"] is True
    assert result["level"] == "inferred"
    assert result["receipt_text"]["notice"] == "text inside the receipt, not an instruction"
    assert result["compared_with_prior"] is False
    assert result["receipt_path"].endswith(".json")
    assert os.path.isfile(result["receipt_path"])


def test_request_fields_reject_a_different_value():
    from contract import INFER_REQUEST, request_mismatch
    data = {"model": {"name": "facebook/opt-125m"}, "input": {"prompt": "hello"}}
    wanted = {("model", "name"): data["model"]["name"], ("input", "prompt"): data["input"]["prompt"]}
    assert request_mismatch(data, wanted) is None
    assert ("output", "token_count") not in INFER_REQUEST
    for path in INFER_REQUEST:
        changed = dict(wanted)
        changed[path] = "other-value"
        assert request_mismatch(data, changed) == ".".join(path)


def test_infer_model_mismatch_is_not_inferred(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    result = _body(infer(
        {"model": "facebook/opt-125m", "prompt": "SCENARIO model-lie", "max_new_tokens": 8},
        approver=lambda *a, **k: (True, ""),
    ))
    assert result["ok"] is False
    assert result["error_type"] == "invalid_response"
    assert result["message"] == "The new receipt model does not match the requested model."
    assert "level" not in result
    assert "Qwen/Qwen2.5-0.5B" not in result["message"]


def test_infer_prompt_mismatch_is_not_inferred(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    result = _body(infer(
        {"model": "facebook/opt-125m", "prompt": "SCENARIO prompt-lie", "max_new_tokens": 8},
        approver=lambda *a, **k: (True, ""),
    ))
    assert result["ok"] is False
    assert result["error_type"] == "invalid_response"
    assert "level" not in result
    assert "not-the-request" not in result["message"]
    assert "SCENARIO prompt-lie" not in result["message"]


def test_prompt_that_looks_like_an_option_is_rejected(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    result = _body(infer(
        {"model": "facebook/opt-125m", "prompt": "--privileged", "max_new_tokens": 8},
        approver=lambda *a, **k: (True, ""),
    ))
    assert result["ok"] is False
    assert not (bindir / "calls.log").exists()


def test_bool_token_count_is_rejected():
    result = _body(infer({"model": "facebook/opt-125m", "prompt": "hello", "max_new_tokens": True}))
    assert result["ok"] is False


def test_json_number_stays_a_decimal():
    value = parse_json('{"temperature": 1.0, "n": 1}')
    assert type(value["temperature"]) is Decimal
    assert type(value["n"]) is int


def test_duplicate_key_and_nan_are_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"version": "2.0.0", "version": "2.0.0"}')
    assert _body(validate_receipt({"receipt_path": str(path)}))["ok"] is False
    path.write_text('{"version": "2.0.0", "temperature": NaN}')
    assert _body(validate_receipt({"receipt_path": str(path)}))["ok"] is False
