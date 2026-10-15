"""Wrap creator text and attach the edge learning summary."""
from __future__ import annotations
import json
if __package__:
    from .jsonio import parse_json
    from .service import NOTICE, egress
else:
    from jsonio import parse_json
    from service import NOTICE, egress
_NOTICE_TOOLS = {"delphi_list_markets", "delphi_get_market", "delphi_query_subgraph"}
def on_transform_tool_result(tool_name=None, result=None, **_kwargs):
    if not isinstance(result, str): return None
    try:
        data = parse_json(result)
    except (ValueError, RecursionError, TypeError): return None
    if not isinstance(data, dict) or data.get("ok") is not True: return None
    if tool_name == "delphi_compute_edge":
        if "learning_summary" in data:
            return None
        data["learning_summary"] = {
            "action": "compute_edge", "edge": data.get("edge"),
            "relation": data.get("relation"), "timestamp": data.get("as_of"), }
        return egress(tool_name, data)
    if tool_name not in _NOTICE_TOOLS:
        return None
    data.pop("creator_notice", None)
    ordered = {"creator_notice": NOTICE, **data}
    return json.dumps(ordered, separators=(",", ":"))
