"""CI smoke through the same public dispatch and validation gates."""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from jsonio import parse_json  # noqa: E402
from service import dispatch  # noqa: E402
from settings import read_setting  # noqa: E402
def call(tool, params):
    result = parse_json(dispatch(tool, params))
    print(json.dumps(result, sort_keys=True))
    if result.get("ok") is not True:
        raise SystemExit(1)
    return result
if sys.argv[1:] == ["keyless"]:
    from agent.secret_scope import set_secret_scope
    set_secret_scope({"DELPHI_API_ACCESS_KEY": ""})
    call("delphi_query_subgraph", {"mode": "meta"})
elif sys.argv[1:] == ["keyed"]:
    if not read_setting("api_access_key"):
        raise SystemExit("DELPHI_API_ACCESS_KEY is required for keyed smoke")
    page = call("delphi_list_markets", {"status": "open", "limit": 1})
    if len(page["markets"]) != 1:
        raise SystemExit("keyed smoke requires one market")
    call( "delphi_compute_edge", {"implied_probability": "0.4", "your_probability": "0.5"}, )
else:
    raise SystemExit("usage: smoke.py keyless|keyed")
