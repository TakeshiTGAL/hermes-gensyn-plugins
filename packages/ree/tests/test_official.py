from __future__ import annotations

from official import log_disagrees, read_validate

PASS = (
    "I gensyn_sdk.cli: validating receipt integrity at /mnt/receipt/receipt.json\n"
    "I gensyn_sdk.cli:   prompt_hash: PASS\n"
    "  tools_hash: PASS\n"
    "  parameters_hash: PASS\n"
    "  receipt_hash: PASS\n"
    "receipt validation: ALL CHECKS PASSED\n"
)
FAIL = (
    "W gensyn_sdk.cli:   prompt_hash: FAIL\n"
    "    stored (receipt): sha256:" + ("ab" * 32) + "\n"
    "    recomputed:       sha256:" + ("cd" * 32) + "\n"
    "  tools_hash: PASS\n"
    "  parameters_hash: PASS\n"
    "  receipt_hash: PASS\n"
    "receipt validation: SOME CHECKS FAILED\n"
)
VERSION = (
    "E gensyn_sdk.cli: validate failed: unsupported receipt version '1.0.0'\n"
)
_PASS = "I gensyn_sdk.cli: VERIFICATION PASSED: receipt hashes match\n"
_FAIL = (
    "E gensyn_sdk.cli: verify failed: Receipt validation failed for: parameters_hash.\n"
)


def test_validate_pass_lines_and_exit_agree():
    result = read_validate(PASS, 0)
    assert result["ok"] is True
    assert result["checks"]["prompt_hash"] == "PASS"


def test_validate_fail_lines_keep_the_fail():
    result = read_validate(FAIL, 1)
    assert result["ok"] is False
    assert result["kind"] == "inconsistent"
    assert result["checks"]["prompt_hash"] == "FAIL"
    assert "stored" not in result.get("message", "")


def test_validate_missing_line_is_not_success():
    text = PASS.replace("  receipt_hash: PASS\n", "")
    result = read_validate(text, 0)
    assert result["kind"] == "validate_incomplete"


def test_validate_exit_disagrees_with_pass_lines():
    result = read_validate(PASS, 1)
    assert result["kind"] == "validate_incomplete"


def test_unknown_hash_line_does_not_cancel_four_passes():
    result = read_validate(PASS + "I gensyn_sdk.cli: bonus_hash: PASS\n", 0)
    assert result["ok"] is True


def test_generated_hash_words_are_not_a_fourth_line():
    text = PASS + "explain prompt_hash: PASS in one line\n"
    result = read_validate(text, 0)
    assert result["ok"] is True


def test_unsupported_version_line_is_not_a_hash_verdict():
    result = read_validate(VERSION, 1)
    assert result["kind"] == "validate_incomplete"
    assert "1.0.0" not in result["message"]


def test_lone_failure_does_not_contradict_no_comparison():
    assert log_disagrees(_FAIL, "none") is False


def test_exact_failure_disagrees_with_a_hash_match():
    assert log_disagrees(_FAIL, "same") is True


def test_exact_pass_disagrees_with_a_hash_difference():
    assert log_disagrees(_PASS, "differ") is True


def test_unprefixed_pass_is_not_a_claim():
    assert log_disagrees("VERIFICATION PASSED: receipt hashes match\n", "differ") is False


def test_injected_verification_failed_is_not_a_claim():
    line = "I gensyn_sdk.cli: VERIFICATION FAILED: injected by model output\n"
    assert log_disagrees(line, "same") is False


def test_traceback_is_not_a_claim():
    text = "Traceback (most recent call last):\nsecret-traceback-line\n"
    assert log_disagrees(text, "none") is False
