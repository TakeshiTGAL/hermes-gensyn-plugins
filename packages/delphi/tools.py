"""Hermes handlers for the seven read-only Delphi tools."""
from __future__ import annotations
if __package__:
    from .service import dispatch
else:
    from service import dispatch
def _handler(name):
    def run(args, **_kwargs):
        return dispatch(name, args)
    return run
HANDLERS = {
    "delphi_list_markets": _handler("delphi_list_markets"),
    "delphi_get_market": _handler("delphi_get_market"),
    "delphi_get_positions": _handler("delphi_get_positions"),
    "delphi_query_subgraph": _handler("delphi_query_subgraph"),
    "delphi_compute_edge": _handler("delphi_compute_edge"),
    "delphi_quote_buy": _handler("delphi_quote_buy"),
    "delphi_quote_sell": _handler("delphi_quote_sell"),
}
