"""The single vocabulary and field table for Delphi inputs and outputs."""
from __future__ import annotations
import re
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID
UINT256_MAX = 2**256 - 1
NETWORKS = ("testnet", "mainnet", "competition-testnet")
STATUSES = ("open", "awaiting_settlement", "settled", "expired", "failed")
ORDERS = ("liquidity", "created", "settles_at")
MODES = ("meta", "trades", "settlement")
ERROR_TYPES = (
    "auth", "rate_limited", "upstream", "timeout", "invalid_response",
    "invalid_argument", "config", "internal", "market_not_quotable", "not_found",
    "unsupported_market",
)
PROOF_KIND = ("empty", "creator_free_text", "ree_receipt_json")
PROBLEMS = (
    "missing", "unknown_field", "wrong_type", "out_of_range", "bad_format", "conflict",
)
ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}\Z")
CATEGORY_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}\Z")
TX_RE = re.compile(r"0x[0-9a-fA-F]{64}\Z")
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
UINT_RE = re.compile(r"(?:0|[1-9][0-9]*)\Z")
USER_PROB_RE = re.compile(r"(?:0(?:\.[0-9]{1,18})?|1(?:\.0{1,18})?)\Z")
SHARE_BODY = r"(?:[1-9][0-9]*(?:\.[0-9]{1,18})?|0\.[0-9]{1,18})"
SHARE_RE = re.compile(SHARE_BODY + r"\Z")
NONNEG_RE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,80})?\Z")
NUMBER_RE = re.compile(
    r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z"
)
SIGNED_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
UTC_RE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z\Z")
MARKET_URL_RE = re.compile(
    r"https://(?:testnet\.delphi\.fyi|app\.delphi\.fyi|"
    r"agent-competition\.gensyn\.ai)/market/"
    r"([0-9a-fA-F-]{36})\Z"
)
def _is_text(value): return isinstance(value, str) and 0 < len(value) <= 1_048_576
def _is_nullable_text(value): return value is None or _is_text(value)
def _is_bool(value): return type(value) is bool
def _is_address(value): return isinstance(value, str) and ADDRESS_RE.fullmatch(value) is not None
def _is_uuid(value):
    if not isinstance(value, str): return False
    try:
        return str(UUID(value)) == value.lower()
    except (ValueError, AttributeError): return False
def _is_event_id(value): return isinstance(value, str) and TOKEN_RE.fullmatch(value) is not None
def _is_tx_hash(value): return isinstance(value, str) and TX_RE.fullmatch(value) is not None
def _is_market_url(value):
    if not isinstance(value, str): return False
    match = MARKET_URL_RE.fullmatch(value)
    return match is not None and _is_uuid(match.group(1))
def _enum(values): return lambda value: isinstance(value, str) and value in values
def _int_range(low, high): return lambda value: type(value) is int and low <= value <= high
def _is_uint_string(value):
    return (
        isinstance(value, str)
        and UINT_RE.fullmatch(value) is not None
        and int(value) <= UINT256_MAX
    )
def _is_user_probability(value): return isinstance(value, str) and USER_PROB_RE.fullmatch(value) is not None
def _share_raw(value):
    if not isinstance(value, str) or SHARE_RE.fullmatch(value) is None: return None
    whole, _, frac = value.partition(".")
    if len(frac) > 18: return None
    raw = int(whole or "0") * 10**18 + int((frac or "0").ljust(18, "0"))
    if raw <= 0 or raw > UINT256_MAX: return None
    return raw
def _is_share_amount(value): return _share_raw(value) is not None
def _max_share():
    whole, frac = divmod(UINT256_MAX, 10**18)
    text = str(whole) if frac == 0 else f"{whole}.{frac:018d}".rstrip("0")
    return text
def _is_nonneg_decimal(value):
    return (
        isinstance(value, str)
        and len(value) <= 120
        and NONNEG_RE.fullmatch(value) is not None
    )
def _is_probability_list(value):
    return (
        isinstance(value, list)
        and 0 < len(value) <= 16
        and all(_is_sdk_probability(item) for item in value)
    )
def _is_sdk_probability(value):
    if not isinstance(value, str) or len(value) > 32 or NUMBER_RE.fullmatch(value) is None: return False
    try:
        number = Decimal(value)
    except InvalidOperation: return False
    return number.is_finite() and Decimal(0) <= number <= Decimal(1) and (
        number == 0 or number.adjusted() >= -324
    )
def _is_signed_decimal(value):
    if not isinstance(value, str) or SIGNED_RE.fullmatch(value) is None: return False
    try:
        return Decimal(value).is_finite()
    except InvalidOperation: return False
def _is_text_list(value): return isinstance(value, list) and all(_is_text(item) for item in value)
def _is_utc(value):
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None: return False
    head, _, frac = value[:-1].partition(".")
    body = head if not frac else f"{head}.{frac[:6].ljust(6, '0')}"
    try:
        datetime.fromisoformat(body + "+00:00")
        return True
    except ValueError: return False
def _is_json_value(value, depth=0):
    if depth > 8: return False
    if value is None or type(value) in (bool, int, str, Decimal):
        return not isinstance(value, str) or len(value) <= 4096
    if isinstance(value, list):
        return len(value) <= 100 and all(_is_json_value(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return len(value) <= 100 and all(
            _is_text(key) and _is_json_value(item, depth + 1)
            for key, item in value.items()
        )
    return False
def _is_only_null(value): return value is None
def _is_false(value): return value is False
def _is_true(value): return value is True
def _is_category(value): return isinstance(value, str) and CATEGORY_RE.fullmatch(value) is not None
def _is_creator(value): return value == "market_creator"
def _is_clip(value):
    return (
        isinstance(value, str) and 1 <= len(value) <= 240
        and "\n" not in value and "\r" not in value and "\t" not in value and "\x00" not in value
    )
def _is_receipt_json(value):
    return isinstance(value, str) and value[:1] == "{" and "\x00" not in value and 1 <= len(value) <= 65536
def _is_phrase(value):
    return (
        isinstance(value, str) and 1 <= len(value) <= 120
        and "\n" not in value and "\x00" not in value
    )
def _is_name_list(value):
    return (
        isinstance(value, list) and 1 <= len(value) <= 16
        and all(isinstance(item, str) and TOKEN_RE.fullmatch(item) is not None for item in value)
    )
def _phrase(values): return ", ".join(values[:-1]) + ", or " + values[-1]
def _type(check, valid, boundary, wrong_type, invalid):
    return {
        "check": check, "valid": valid, "boundary": boundary,
        "wrong_type": wrong_type, "invalid": invalid, "expected": "the documented shape",
    }
TYPES = {
    "text": _type(_is_text, "value", "x" * 4096, 1, ""),
    "nullable_text": _type(_is_nullable_text, "value", None, 1, ""),
    "bool": _type(_is_bool, True, False, 1, "true"),
    "address": _type(_is_address, "0x" + "ab" * 20, "0x" + "00" * 20, 1, "0x12"),
    "uuid": _type(_is_uuid, "11111111-1111-4111-8111-111111111111",
                  "00000000-0000-4000-8000-000000000000", 1, "no"),
    "event_id": _type(_is_event_id, "event-1", "x" * 256, 1, "a b"),
    "token": _type(_is_event_id, "event-1", "x" * 256, 1, "a b"),
    "tx_hash": _type(_is_tx_hash, "0x" + "12" * 32, "0x" + "00" * 32, 1, "0x12"),
    "market_url": _type(
        _is_market_url,
        "https://testnet.delphi.fyi/market/11111111-1111-4111-8111-111111111111",
        "https://app.delphi.fyi/market/00000000-0000-4000-8000-000000000000",
        1,
        "https://evil.example/market/11111111-1111-4111-8111-111111111111",
    ),
    "network": _type(_enum(NETWORKS), "testnet", "mainnet", 1, "devnet"),
    "market_status": _type(_enum(STATUSES), "open", "failed", 1, "unknown"),
    "category": _type(_is_category, "crypto", "tech", 1, "Crypto"),
    "order_by": _type(_enum(ORDERS), "liquidity", "settles_at", 1, "new"),
    "subgraph_mode": _type(_enum(MODES), "meta", "settlement", 1, "query"),
    "relation": _type(_enum(("above", "below", "equal")), "above", "equal", 1, "near"),
    "error_type": _type(_enum(ERROR_TYPES), "upstream", "internal", 1, "unknown"),
    "limit": _type(_int_range(1, 50), 20, 50, "20", 0),
    "first": _type(_int_range(1, 20), 10, 20, "10", 0),
    "skip": _type(_int_range(0, 10000), 0, 10000, "0", -1),
    "count": _type(_int_range(0, 50), 1, 50, "1", -1),
    "uint_string": _type(_is_uint_string, "1", str(UINT256_MAX), 1, str(2**256)),
    "user_probability": _type(_is_user_probability, "0.5", "1.000", 0.5, "1e-7"),
    "sdk_probability": _type(_is_sdk_probability, "0.1", "5e-324", 0.1, "1.1"),
    "share_amount": _type(
        _is_share_amount, "1", _max_share(), 1, "0.1000000000000000000",
    ),
    "nonneg_decimal": _type(_is_nonneg_decimal, "1.5", "0", 1, "1e-7"),
    "outcome_index": _type(_int_range(0, 2**31 - 1), 0, 2**31 - 1, "0", -1),
    "probability_source": _type(_enum(("argument", "sdk_live")), "argument", "sdk_live", 1, "live"),
    "quote_side": _type(_enum(("buy", "sell")), "buy", "sell", 1, "redeem"),
    "decimals_status": _type(_enum(("known", "unavailable")), "known", "unavailable", 1, "null"),
    "byte_size": _type(_int_range(0, 255), 6, 255, "6", -1),
    "probability_list": _type(_is_probability_list, ["0.4", "0.6"], ["5e-324"], "x", []),
    "signed_decimal": _type(_is_signed_decimal, "0.1", "-0.1", 0.1, "1e-7"),
    "text_list": _type(_is_text_list, ["Yes", "No"], [], "x", [""]),
    "utc": _type(_is_utc, "2026-01-01T00:00:00Z", "9999-12-31T23:59:59Z", 1, "soon"),
    "json_value": _type(_is_json_value, [], {"source": "sdk"}, object(), {1: "bad"}),
    "only_null": _type(_is_only_null, None, None, "null", "error"),
    "block_number": _type(_int_range(0, 2**53 - 1), 1, 2**53 - 1, "1", -1),
    "phrase": _type(_is_phrase, "0x and 40 hex characters", "0", 1, ""),
    "name_list": _type(_is_name_list, ["delphi_quote_buy"], ["x"], "x", []),
    "proof_kind": _type(_enum(PROOF_KIND), "creator_free_text", "ree_receipt_json", 1, "hash"),
    "false_only": _type(_is_false, False, False, True, "false"),
    "true_only": _type(_is_true, True, True, False, "true"),
    "creator_source": _type(_is_creator, "market_creator", "market_creator", 1, "user"),
    "clip_text": _type(_is_clip, "Yes", "x" * 240, 1, ""),
    "receipt_json": _type(_is_receipt_json, '{"version":"1"}', "{" + "v" * 65535, 1, "[]"),
    "argument_problem": _type(_enum(PROBLEMS), "missing", "conflict", 1, "nope"),
}
TYPES["market_status"]["expected"] = _phrase(STATUSES)
TYPES["category"]["expected"] = "lowercase slug of up to 32 characters"
TYPES["order_by"]["expected"] = _phrase(ORDERS)
TYPES["subgraph_mode"]["expected"] = _phrase(MODES)
TYPES["address"]["expected"] = "0x and 40 hex characters"
TYPES["bool"]["expected"] = "true or false"
TYPES["limit"]["expected"] = "integer from 1 to 50"
TYPES["first"]["expected"] = "integer from 1 to 20"
TYPES["skip"]["expected"] = "integer from 0 to 10000"
TYPES["outcome_index"]["expected"] = "integer from 0 to 2147483647"
TYPES["user_probability"]["expected"] = (
    "decimal string, up to 18 fraction digits, from 0 to 1"
)
TYPES["share_amount"]["expected"] = (
    "decimal string, up to 18 fraction digits, greater than 0"
)
def F(type_name, *, required=True, nullable=False):
    return {"type": type_name, "required": required, "nullable": nullable}
def N(table, *, required=True, nullable=False):
    return {"table": table, "required": required, "nullable": nullable}
def L(table, *, required=True): return {"list": table, "required": required}
MARKET_FIELDS = {
    "id": F("address"), "appMarketId": F("uuid"), "marketUrl": F("market_url"),
    "status": F("market_status"), "category": F("category"), "deployer": F("address"),
    "implementation": F("address"), "metadataUri": F("text"),
    "metadataUriContentHash": F("text"), "metadata": N("sdk.metadata", nullable=True),
    "dataSources": F("json_value"), "createdAt": F("utc"),
    "fetchedAt": F("utc", nullable=True), "fetchResponseStatus": F("text", nullable=True),
    "resolvesAt": F("utc", nullable=True), "settledAt": F("utc", nullable=True),
    "settlesAt": F("utc", nullable=True), "winningOutcomeIdx": F("uint_string", nullable=True),
    "tradingFee": F("uint_string", nullable=True), "proof": F("text", nullable=True),
    "error": F("text", nullable=True), "verifiable": F("bool"),
}
EVENT_BASE = {
    "id": F("event_id"), "block_number": F("uint_string"),
    "timestamp_": F("uint_string"), "transactionHash_": F("tx_hash"),
    "contractId_": F("event_id"), "marketProxy": F("address", nullable=True),
}
PUBLIC_MARKET = {
    "id": F("address"), "app_market_id": F("uuid"), "market_url": F("market_url"),
    "status": F("market_status"), "category": F("category"), "question": N("out.untrusted"),
    "outcomes": L("out.untrusted"), "created_at": F("utc"),
    "settles_at": F("utc", nullable=True), "resolves_at": F("utc", nullable=True),
    "settled_at": F("utc", nullable=True),
    "winning_outcome_idx": F("uint_string", nullable=True),
    "trading_fee": F("uint_string", nullable=True),
    "trading_fee_percent": F("nonneg_decimal", nullable=True),
    "verifiable": F("bool"), "model_identifier": N("out.untrusted", nullable=True),
    "metadata_version": N("out.untrusted", nullable=True),
    "proof_text": N("out.proof_box", nullable=True), "proof_kind": F("proof_kind"),
    "looks_like_ree_receipt": F("bool"),
    "is_ree_receipt": F("bool"), "sdk_error": F("bool"),
    "error": N("out.untrusted", nullable=True),
    "proof_truncated": F("bool"),
    "proof_receipt_json": N("out.proof_box", required=False),
    "proof_too_large": F("bool", required=False),
    "receipt_version": N("out.untrusted", required=False),
    "receipt_model": N("out.untrusted", required=False),
    "market_model": N("out.untrusted", required=False),
    "receipt_model_matches_market": F("bool", required=False),
    "shape_only": F("true_only", required=False),
    "next": N("out.next_receipt", required=False),
}
PUBLIC_EVENT = {
    "id": F("event_id"), "block_number": F("uint_string"),
    "timestamp": F("uint_string"), "transaction_hash": F("tx_hash"),
    "contract_id": F("event_id"), "market_proxy": F("address", nullable=True),
}
OUTPUT_COMMON = {"ok": F("bool"), "tool": F("token"), "as_of": F("utc")}
