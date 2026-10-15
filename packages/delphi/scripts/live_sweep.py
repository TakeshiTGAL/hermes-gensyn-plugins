"""Read every current testnet market through the Hermes tool entry."""
from __future__ import annotations
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
STATUSES = ("open", "awaiting_settlement", "settled", "expired", "failed")
EMPTY_WALLET = "0x" + ("cd" * 20)
PLUGIN = Path(__file__).resolve().parents[1]
if str(PLUGIN) not in sys.path:
    sys.path.append(str(PLUGIN))
from json import JSONDecodeError
from jsonio import parse_json
def _home():
    root = Path(tempfile.mkdtemp(prefix="delphi-sweep-"))
    plug = root / "plugins" / "hermes-gensyn-delphi"
    plug.parent.mkdir(parents=True)
    plug.symlink_to(PLUGIN, target_is_directory=True)
    fd = os.open(
        root / "config.yaml", os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600,
    )
    try:
        os.write(fd, b"plugins:\n  enabled:\n    - hermes-gensyn-delphi\n")
    finally:
        os.close(fd)
    return root
def _call(handle, tool, args):
    last = {"ok": False, "error_type": "internal"}
    for attempt in range(48):
        raw = handle(tool, args, task_id="sweep", session_id="sweep")
        try:
            last = parse_json(raw)
        except (JSONDecodeError, TypeError):
            last = {"ok": False, "error_type": "invalid_response"}
        if last.get("ok") is True:
            return last
        kind = last.get("error_type")
        if kind == "rate_limited":
            time.sleep(2.1)
            continue
        if kind in {"timeout", "upstream"} and attempt < 3:
            time.sleep(1.0)
            continue
        return last
    return last
def _note(body):
    kind = body.get("error_type") or "invalid_response"
    message = body.get("message") if isinstance(body.get("message"), str) else ""
    print(f"sweep miss {kind} {message[:80]}", file=sys.stderr)
def main():
    from settings import read_setting
    network = read_setting("network", "")
    keyed = bool(read_setting("api_access_key", ""))
    if network != "testnet" or not keyed:
        print("SWEEP rows=0 failed=1 statuses=0")
        return 1
    logging.disable(logging.CRITICAL)
    import model_tools
    from hermes_cli.plugins import discover_plugins
    discover_plugins()
    handle = model_tools.handle_function_call
    rows = 0
    failed = 0
    seen = set()
    sample = {}
    def once(tool, args):
        nonlocal failed
        body = _call(handle, tool, args)
        if body.get("ok") is not True:
            failed += 1
            _note(body)
        return body
    for status in STATUSES:
        skip = 0
        while skip <= 10000:
            body = once(
                "delphi_list_markets",
                {"status": status, "limit": 50, "skip": skip},
            )
            page = body.get("markets") if body.get("ok") is True else None
            if not isinstance(page, list):
                break
            rows += len(page)
            for row in page:
                if isinstance(row, dict) and isinstance(row.get("status"), str):
                    seen.add(row["status"])
                if isinstance(row, dict) and status not in sample:
                    sample[status] = row.get("id")
            if len(page) < 50:
                break
            skip += 50
            if skip > 10000:
                failed += 1
                _note({"error_type": "invalid_argument"})
                break
    for market_id in sample.values():
        if not isinstance(market_id, str):
            failed += 1
            continue
        once("delphi_get_market", {"market_id": market_id})
    held = once("delphi_get_positions", {"wallet": EMPTY_WALLET, "limit": 50})
    if held.get("ok") is True and held.get("count") != 0:
        failed += 1
        _note({"error_type": "invalid_response"})
    open_id = sample.get("open")
    if isinstance(open_id, str):
        quote = {"market_address": open_id, "outcome_idx": 0, "shares": "1"}
        once("delphi_quote_buy", quote)
        once("delphi_quote_sell", quote)
        once("delphi_compute_edge", {
            "market_id": open_id, "outcome_idx": 0, "your_probability": "0.5",
        })
    else:
        failed += 1
        _note({"error_type": "not_found"})
    print(f"SWEEP rows={rows} failed={failed} statuses={len(seen)}")
    return 0 if failed == 0 and rows >= 200 else 1
if __name__ == "__main__":
    import shutil
    root = _home()
    os.environ["HERMES_HOME"] = str(root)
    try:
        code = main()
    except Exception as exc:
        print(type(exc).__name__, file=sys.stderr)
        print("SWEEP rows=0 failed=1 statuses=0")
        code = 1
    finally:
        shutil.rmtree(root, ignore_errors=True)
    raise SystemExit(code)
