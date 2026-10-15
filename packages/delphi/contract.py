"""Field tables. The vocabulary is in spec.py. Validation stays in this file."""
from __future__ import annotations
from copy import deepcopy
if __package__:
    from .spec import ( ERROR_TYPES, EVENT_BASE, F, L, MARKET_FIELDS, MODES, N,
        NETWORKS, ORDERS, OUTPUT_COMMON, PROBLEMS, PUBLIC_EVENT, PUBLIC_MARKET,
        SHARE_BODY, STATUSES, TYPES, _max_share, _share_raw, )
else:
    from spec import ( ERROR_TYPES, EVENT_BASE, F, L, MARKET_FIELDS, MODES, N,
        NETWORKS, ORDERS, OUTPUT_COMMON, PROBLEMS, PUBLIC_EVENT, PUBLIC_MARKET,
        SHARE_BODY, STATUSES, TYPES, _max_share, _share_raw, )
def failure_note(kind, detail):
    if kind == "unsupported_market" and detail == "lmsr_probability":
        return "This tool does not return a probability for an lmsr market."
    return None
TABLES = { "args.list_markets": {
        "status": F("market_status", required=False), "category": F("category", required=False),
        "verifiable": F("bool", required=False), "orderBy": F("order_by", required=False),
        "limit": F("limit", required=False), "skip": F("skip", required=False), }, "args.get_market": {
        "market_id": F("address", required=False), "market_address": F("address", required=False), },
    "args.get_positions": { "wallet": F("address", required=False), "limit": F("limit", required=False),
        "skip": F("skip", required=False), "redeemedOrLiquidated": F("bool", required=False), },
    "args.query_subgraph": { "mode": F("subgraph_mode"), "market_address": F("address", required=False),
        "first": F("first", required=False), "skip": F("skip", required=False), }, "args.compute_edge": {
        "implied_probability": F("user_probability", required=False),
        "your_probability": F("user_probability"), "market_id": F("address", required=False),
        "market_address": F("address", required=False), "outcome_idx": F("outcome_index", required=False), },
    "args.quote_buy": {
        "market_address": F("address", required=False), "market_id": F("address", required=False),
        "outcome_idx": F("outcome_index"), "shares": F("share_amount"), }, "args.quote_sell": {
        "market_address": F("address", required=False), "market_id": F("address", required=False),
        "outcome_idx": F("outcome_index"), "shares": F("share_amount"), },
    "sdk.metadata": {"question": F("text"), "outcomes": F("text_list")}, "sdk.decimals": {
        "status": F("decimals_status"), "value": F("byte_size", required=False), },
    "sdk.quote": {"amount_raw": F("uint_string"), "decimals": N("sdk.decimals")}, "sdk.live_probability": {
        "id": F("address"), "spotImpliedProbabilities": F("probability_list"), }, "sdk.market": MARKET_FIELDS,
    "sdk.position": { "id": F("event_id"), "marketProxy": F("address"), "wallet": F("address"),
        "outcomeIdx": F("uint_string"), "shares": F("uint_string"),
        "redeemedOrLiquidated": F("bool"), "tokensRedeemed": F("uint_string"),
        "marketStatus": F("market_status"), }, "sdk.block": {
        "number": F("block_number"), "timestamp": F("block_number", nullable=True),
        "hash": F("tx_hash", nullable=True), }, "sdk.meta": {
        "block": N("sdk.block"), "deployment": F("token"), "hasIndexingErrors": F("bool"), }, "sdk.buy": {
        **EVENT_BASE, "buyer": F("address", nullable=True), "outcomeIdx": F("uint_string", nullable=True),
        "tokensIn": F("uint_string", nullable=True), "sharesOut": F("uint_string", nullable=True), },
    "sdk.sell": { **EVENT_BASE, "seller": F("address", nullable=True),
        "outcomeIdx": F("uint_string", nullable=True), "sharesIn": F("uint_string", nullable=True),
        "tokensOut": F("uint_string", nullable=True), }, "sdk.settled": {
        **EVENT_BASE, "winningOutcomeIdx": F("uint_string", nullable=True),
        "marketCreatorReward": F("uint_string", nullable=True), "refund": F("uint_string", nullable=True),
        "marketCreatorTradingFeesCut": F("uint_string", nullable=True), }, "sdk.failed": EVENT_BASE,
    "sdk.request": {**EVENT_BASE, "keeper": F("address", nullable=True)}, "out.market": PUBLIC_MARKET,
    "out.untrusted": { "untrusted_text": F("true_only"), "source": F("creator_source"),
        "text": F("clip_text"), "truncated": F("bool"), },
    "out.proof_box": { "untrusted_text": F("true_only"), "source": F("creator_source"),
        "text": F("text"), "truncated": F("bool"), },
    "out.next_receipt": {"tool": F("token"), "note": F("phrase")}, "out.position": {
        "id": F("event_id"), "market_proxy": F("address"), "wallet": F("address"),
        "outcome_idx": F("uint_string"), "shares": F("uint_string"), "shares_decimal": F("nonneg_decimal"),
        "redeemed_or_liquidated": F("bool"), "tokens_redeemed": F("uint_string"),
        "market_status": F("market_status"), }, "out.meta": { "block_number": F("block_number"),
        "block_timestamp": F("block_number", nullable=True),
        "block_hash": F("tx_hash", nullable=True), "deployment": F("token"), "has_indexing_errors": F("bool"),
    }, "out.buy": { **PUBLIC_EVENT, "buyer": F("address", nullable=True),
        "outcome_idx": F("uint_string", nullable=True), "tokens_in": F("uint_string", nullable=True),
        "shares_out": F("uint_string", nullable=True), }, "out.sell": {
        **PUBLIC_EVENT, "seller": F("address", nullable=True), "outcome_idx": F("uint_string", nullable=True),
        "shares_in": F("uint_string", nullable=True), "tokens_out": F("uint_string", nullable=True), },
    "out.settled": { **PUBLIC_EVENT, "winning_outcome_idx": F("uint_string", nullable=True),
        "market_creator_reward": F("uint_string", nullable=True), "refund": F("uint_string", nullable=True),
        "market_creator_trading_fees_cut": F("uint_string", nullable=True), }, "out.failed": PUBLIC_EVENT,
    "out.request": {**PUBLIC_EVENT, "keeper": F("address", nullable=True)}, "out.list_markets": {
        **OUTPUT_COMMON, "creator_notice": F("phrase"), "count": F("count"),
        "markets": L("out.market"), "upstream_null": F("bool"), },
    "out.get_market": {**OUTPUT_COMMON, "creator_notice": F("phrase"), "market": N("out.market")},
    "out.get_positions": { **OUTPUT_COMMON, "wallet": F("address"), "count": F("count"),
        "positions": L("out.position"), "upstream_null": F("bool"), }, "out.subgraph_meta": {
        **OUTPUT_COMMON, "creator_notice": F("phrase"), "mode": F("subgraph_mode"), "meta": N("out.meta"), },
    "out.subgraph_trades": { **OUTPUT_COMMON, "creator_notice": F("phrase"), "mode": F("subgraph_mode"),
        "market_address": F("address"), "buys": L("out.buy"), "sells": L("out.sell"), },
    "out.subgraph_settlement": { **OUTPUT_COMMON, "creator_notice": F("phrase"), "mode": F("subgraph_mode"),
        "market_address": F("address"), "settled": L("out.settled"), "failed": L("out.failed"),
        "resolution_requests": L("out.request"), }, "out.summary": {
        "action": F("token"), "edge": F("signed_decimal"), "relation": F("relation"), "timestamp": F("utc"),
    }, "out.compute_edge": { **OUTPUT_COMMON, "implied_probability": F("sdk_probability"),
        "your_probability": F("user_probability"), "edge": F("signed_decimal"),
        "relation": F("relation"), "probability_source": F("probability_source"),
        "learning_summary": N("out.summary", required=False), }, "out.quote": {
        **OUTPUT_COMMON, "market_address": F("address"), "outcome_idx": F("outcome_index"),
        "shares": F("share_amount"), "side": F("quote_side"), "amount_raw": F("uint_string"),
        "decimals": N("sdk.decimals"), "amount": F("nonneg_decimal", required=False),
        "per_share": F("nonneg_decimal"), "per_share_truncated": F("bool"),
        "per_share_display": F("nonneg_decimal", required=False), "is_probability": F("false_only"), },
    "out.error": { "ok": F("bool"), "tool": F("token"), "error_type": F("error_type"),
        "message": F("text"), "retryable": F("bool"), "field": F("token", required=False),
        "problem": F("argument_problem", required=False), "expected": F("phrase", required=False),
        "allowed_fields": F("name_list", required=False), "missing": F("name_list", required=False),
        "needed_for": F("token", required=False), "works_without_key": F("name_list", required=False), }, }
CANON = {"address": str.lower, "tx_hash": str.lower, "uuid": str.lower, "market_url": str.lower}
ONE_OF = {
    "args.get_market": (("market_id",), ("market_address",)),
    "args.compute_edge": (("implied_probability",), ("market_id", "outcome_idx")),
    "args.quote_buy": (("market_address",), ("market_id",)),
    "args.quote_sell": (("market_address",), ("market_id",)), }
_ALIAS = { "args.get_market": ("market_id", "market_address"),
    "args.compute_edge": ("market_id", "market_address"), "args.quote_buy": ("market_address", "market_id"),
    "args.quote_sell": ("market_address", "market_id"), }
NETWORK_APP_HOST = { "testnet": "testnet.delphi.fyi", "mainnet": "app.delphi.fyi",
    "competition-testnet": "agent-competition.gensyn.ai", }
SUBGRAPH_FIELDS = { "meta": ("mode",), "trades": ("mode", "market_address", "first", "skip"),
    "settlement": ("mode", "market_address", "first", "skip"), }
def make_sample(table_name):
    skipped = set()
    groups = ONE_OF.get(table_name, ())
    for group in groups[1:]:
        skipped.update(group)
    value = {}
    for name, spec in TABLES[table_name].items():
        if name in skipped or (
            name == "market_address" and table_name in ("args.get_market", "args.compute_edge") ):
            continue
        if "type" in spec:
            value[name] = deepcopy(TYPES[spec["type"]]["valid"])
        elif "table" in spec:
            value[name] = make_sample(spec["table"])
        else:
            value[name] = [make_sample(spec["list"])]
    return value
def validate(table_name, value):
    if not isinstance(value, dict):
        return f"{table_name} must be an object"
    fields = TABLES[table_name]
    if table_name.startswith(("args.", "out.")):
        unknown = sorted(set(value) - set(fields))
        if unknown: return f"{table_name}.{unknown[0]} is not allowed"
    for name, spec in fields.items():
        if name not in value:
            if spec.get("required", True):
                return f"{table_name}.{name} is missing"
            continue
        item = value[name]
        if item is None and spec.get("nullable"): continue
        if item is None and spec.get("type") != "only_null": return f"{table_name}.{name} has invalid null"
        if "type" in spec:
            kind = spec["type"]
            if kind in CANON and isinstance(item, str):
                item = value[name] = CANON[kind](item)
            if not TYPES[kind]["check"](item): return f"{table_name}.{name} has invalid {kind}"
        elif "table" in spec:
            problem = validate(spec["table"], item)
            if problem: return f"{table_name}.{name}: {problem}"
        else:
            if not isinstance(item, list): return f"{table_name}.{name} must be an array"
            for index, row in enumerate(item):
                problem = validate(spec["list"], row)
                if problem: return f"{table_name}.{name}[{index}]: {problem}"
    groups = ONE_OF.get(table_name)
    if groups:
        selected = [group for group in groups if all(name in value for name in group)]
        if len(selected) != 1: return f"{table_name} needs exactly one input form"
        for group in groups:
            if group is selected[0]: continue
            for name in group:
                if name in value: return f"{table_name}.{name} is not used in this form"
    return None
_INTS = {"limit", "first", "skip", "outcome_index", "count"}
def _typed(kind, item):
    expected = TYPES[kind]["expected"]
    if kind in _INTS:
        if type(item) is not int: return ("wrong_type", expected)
        if not TYPES[kind]["check"](item):
            return ("out_of_range", expected)
        return None
    if kind == "bool":
        if type(item) is not bool:
            return ("wrong_type", expected)
        return None
    if TYPES[kind]["check"](item): return None
    if not isinstance(item, str):
        return ("wrong_type", expected)
    return ("bad_format", expected)
def argument_refusal(table_name, value):
    """Typed refusal for one argument table. Does not include the submitted value."""
    fields = TABLES[table_name]
    allowed = tuple(fields)
    if type(value) is not dict: return ("input", "wrong_type", "an object", allowed)
    alias = _ALIAS.get(table_name)
    if alias:
        primary, other = alias
        if primary in value and other in value:
            return ("input", "conflict", "exactly one input form", allowed)
        if other in value and primary not in value:
            value = dict(value)
            value[primary] = value.pop(other)
    unknown = sorted(set(value) - set(fields))
    if unknown:
        return ("input", "unknown_field", "an allowed field", allowed)
    groups = ONE_OF.get(table_name, ())
    picked = [group for group in groups if all(name in value for name in group)]
    if groups and len(picked) == 0:
        if table_name == "args.compute_edge" and ("market_id" in value or "outcome_idx" in value):
            name = "outcome_idx" if "outcome_idx" not in value else "market_id"
            kind = "outcome_index" if name == "outcome_idx" else "address"
            return (name, "missing", TYPES[kind]["expected"], allowed)
        return (groups[0][0], "missing", "one input form", allowed)
    if groups and len(picked) != 1: return ("input", "conflict", "exactly one input form", allowed)
    chosen = set(picked[0]) if picked else None
    grouped = {name for group in groups for name in group}
    mode = value.get("mode")
    if table_name == "args.query_subgraph" and mode in SUBGRAPH_FIELDS:
        extra = sorted(set(value) - set(SUBGRAPH_FIELDS[mode]))
        if extra:
            return ("input", "unknown_field", "an allowed field", allowed)
        if mode != "meta" and "market_address" not in value:
            return ("market_address", "missing", TYPES["address"]["expected"], allowed)
    for name, spec in fields.items():
        if chosen is not None and name in grouped and name not in chosen:
            if name in value:
                return (name, "conflict", "exactly one input form", allowed)
            continue
        if name not in value:
            if spec.get("required", True): return (name, "missing", TYPES[spec["type"]]["expected"], allowed)
            continue
        found = _typed(spec["type"], value[name])
        if found and found[0] not in PROBLEMS: return None
        if found: return (name, found[0], found[1], allowed)
    if table_name == "args.query_subgraph" and mode == "settlement" and value.get("skip", 0) != 0:
        return ("skip", "out_of_range", "0", allowed)
    return None
