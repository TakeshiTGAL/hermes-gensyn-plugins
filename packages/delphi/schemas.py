"""Hermes schemas generated from the central argument tables."""
from __future__ import annotations
if __package__:
    from .contract import MODES, NETWORKS, ORDERS, SHARE_BODY, STATUSES, TABLES
else:
    from contract import MODES, NETWORKS, ORDERS, SHARE_BODY, STATUSES, TABLES
DESCRIPTIONS = { "delphi_list_markets": "Returns static market pages. Key required. Read-only.",
    "delphi_get_market": ( "Returns one static market. Key required. Read-only. "
        "Pass market_id or market_address, not both." ),
    "delphi_get_positions": "Returns positions for one public wallet. Key required. Read-only.",
    "delphi_query_subgraph": "Returns subgraph rows. No key. Read-only.", "delphi_compute_edge": (
        "Returns an edge. your_probability is required. No key for implied_probability. "
        "Key required for market_id or market_address. Read-only." ), "delphi_quote_buy": (
        "Returns a buy quote. No key. Read-only. outcome_idx starts at 0. "
        "The amount includes fees and price move. It is not a probability. "
        "Do not put it in implied_probability. "
        "With a key, delphi_get_market names it; without a key, the name is unknown." ),
    "delphi_quote_sell": ( "Returns a sell quote. No key. Read-only. outcome_idx starts at 0. "
        "The amount includes fees and price move. It is not a probability. "
        "Do not put it in implied_probability. "
        "With a key, delphi_get_market names it; without a key, the name is unknown." ), }
def _property(type_name):
    if type_name in ("limit", "first", "skip", "outcome_index", "byte_size"):
        bounds = { "limit": (1, 50), "first": (1, 20), "skip": (0, 10000),
            "outcome_index": (0, 2**31 - 1), "byte_size": (0, 255), }[type_name]
        return {"anyOf": [{"type": "integer", "minimum": bounds[0], "maximum": bounds[1]}]}
    if type_name == "bool":
        return {"anyOf": [{"type": "boolean"}]}
    enums = { "market_status": STATUSES, "order_by": ORDERS, "subgraph_mode": MODES,
        "network": NETWORKS, "probability_source": ("argument", "sdk_live"),
        "quote_side": ("buy", "sell"), "decimals_status": ("known", "unavailable"), }
    if type_name in enums:
        return {"type": "string", "enum": list(enums[type_name])}
    patterns = {
        "address": r"^0x[0-9a-fA-F]{40}$", "category": r"^[a-z0-9][a-z0-9_-]{0,31}$", "uuid": (
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-" r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
        ), "user_probability": r"^(?:0(?:\.[0-9]{1,18})?|1(?:\.0{1,18})?)$",
        "share_amount": f"^{SHARE_BODY}$", }
    result = {"type": "string"}
    if type_name in patterns:
        result["pattern"] = patterns[type_name]
    return result
def _schema(name):
    table = TABLES[f"args.{name.removeprefix('delphi_')}"]
    properties = {field: _property(spec["type"]) for field, spec in table.items()}
    required = [field for field, spec in table.items() if spec.get("required", True)]
    return { "name": name,
        "description": DESCRIPTIONS[name], "parameters": { "type": "object", "additionalProperties": False,
            "properties": properties, "required": required, }, }
SCHEMAS = {name: _schema(name) for name in DESCRIPTIONS}
