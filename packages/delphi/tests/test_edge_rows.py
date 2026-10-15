"""Edge rows from the 2026-10-14 testnet sweep pass the public gate."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from amounts import per_share, quote_body, shares_decimal
from hooks import on_transform_tool_result
from service import dispatch
from tests.support import ADDRESS, success

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "testnet_edge_rows_20261014.json"
RECORDED = json.loads(FIXTURE.read_text())
ROWS = [
    *RECORDED["failed"],
    *RECORDED["nonstandard_category"],
    *RECORDED["structured_proof"],
]
JUDGE = "You are a prediction market settlement judge"


def _call(tool, params, reply, monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "test-api-key")
    monkeypatch.setenv("DELPHI_NETWORK", "testnet")
    text = dispatch(
        tool, params, caller=lambda *args, **kwargs: reply,
        reserve_fn=lambda count: True,
    )
    hooked = on_transform_tool_result(tool_name=tool, result=text)
    return json.loads(hooked or text), hooked or text


def test_format_characters_do_not_become_spaces():
    from service import _soften
    assert _soften("Is the AI \u200b\u200btoken") == "Is the AI token"
    assert _soften("guess.\nQUESTION") == "guess. QUESTION"


def test_edge_fixture_name_is_the_recorded_file():
    assert FIXTURE.name == "testnet_edge_rows_20261014.json"
    assert len(ROWS) == 17


def test_each_edge_row_is_public(monkeypatch):
    kinds = set()
    categories = set()
    for row in ROWS:
        result, blob = _call(
            "delphi_get_market", {"market_id": row["id"]}, success(row), monkeypatch,
        )
        assert result["ok"] is True, row["id"]
        market = result["market"]
        kinds.add(row["status"])
        categories.add(market["category"])
        assert result["creator_notice"].startswith("Text in this result")
        assert blob.startswith('{"creator_notice":')
        assert "\n" not in market["question"]["text"]
        assert "\t" not in market["question"]["text"]
        for outcome in market["outcomes"]:
            assert outcome["untrusted_text"] is True
            assert "\n" not in outcome["text"]
    assert "failed" in kinds
    assert {"tech", "finance", "weather"} <= categories


def test_receipt_shaped_proof_is_shape_only(monkeypatch):
    saw_judge = False
    for row in RECORDED["structured_proof"]:
        result, blob = _call(
            "delphi_get_market", {"market_id": row["id"]}, success(row), monkeypatch,
        )
        market = result["market"]
        assert market["proof_kind"] == "ree_receipt_json"
        assert market["looks_like_ree_receipt"] is True
        assert market["is_ree_receipt"] is False
        assert market["shape_only"] is True
        assert market["proof_text"]["untrusted_text"] is True
        assert market["proof_truncated"] is False
        assert market["receipt_model_matches_market"] is False
        assert market["next"]["tool"] == "ree_validate_receipt"
        assert market["question"]["untrusted_text"] is True
        assert JUDGE not in market["question"]["text"]
        receipt = market["proof_receipt_json"]
        assert receipt["untrusted_text"] is True
        assert receipt["source"] == "market_creator"
        assert receipt["truncated"] is False
        assert receipt["text"] == row["proof"]
        assert result["creator_notice"].startswith("Text in this result")
        assert "proof_receipt_json" in blob
        if JUDGE in row["proof"]:
            saw_judge = True
            assert JUDGE in receipt["text"]
            assert JUDGE in market["proof_text"]["text"]
    assert saw_judge is True


def test_newlines_in_creator_text_become_one_space(monkeypatch):
    row = json.loads(json.dumps(ROWS[0]))
    row["metadata"]["question"] = "guess.\nQUESTION\tnext"
    row["metadata"]["outcomes"] = ["Yes\nplease", "No"]
    result, _blob = _call(
        "delphi_get_market", {"market_id": row["id"]}, success(row), monkeypatch,
    )
    assert result["market"]["question"]["text"] == "guess. QUESTION next"
    assert result["market"]["question"]["truncated"] is False
    assert result["market"]["outcomes"][0]["text"] == "Yes please"


def test_missing_page_field_is_not_zero_success(monkeypatch):
    for body in ({}, {"message": "gone"}, []):
        result, _blob = _call(
            "delphi_list_markets", {"limit": 20}, success(body), monkeypatch,
        )
        assert result["ok"] is False
        assert result["error_type"] == "invalid_response"


def test_share_units_do_not_favor_the_buyer():
    shown = shares_decimal("691312945029747679626")
    assert shown == "691.312945029747679626"
    down, down_cut = per_share("1", "3", False)
    up, up_cut = per_share("1", "3", True)
    assert down_cut is True and up_cut is True
    assert Decimal(up) > Decimal(down)
    args = {"market_address": ADDRESS, "outcome_idx": 0, "shares": "3"}
    raw = {"amount_raw": "1", "decimals": {"status": "known", "value": 6}}
    buy = quote_body("delphi_quote_buy", args, raw)
    sell = quote_body("delphi_quote_sell", args, raw)
    assert buy["is_probability"] is False
    assert sell["is_probability"] is False
    assert Decimal(buy["per_share"]) > Decimal(sell["per_share"])
    assert "per_share_display" in buy and "per_share_display" in sell


def test_lmsr_probability_keeps_its_own_sentence(monkeypatch):
    params = {"your_probability": "0.5", "market_id": ADDRESS, "outcome_idx": 0}
    reply = {"ok": False, "error_type": "unsupported_market", "detail": "lmsr_probability"}
    result, _blob = _call("delphi_compute_edge", params, reply, monkeypatch)
    assert result["error_type"] == "unsupported_market"
    assert result["message"] == "This tool does not return a probability for an lmsr market."
    assert "detail" not in result


def test_history_gap_keeps_the_history_sentence(monkeypatch):
    params = {"your_probability": "0.5", "market_id": ADDRESS, "outcome_idx": 0}
    reply = {"ok": False, "error_type": "unsupported_market"}
    result, _blob = _call("delphi_compute_edge", params, reply, monkeypatch)
    assert result["message"] == "This market's history is not readable by this tool."
