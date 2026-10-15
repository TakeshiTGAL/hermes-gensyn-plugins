"""Always-true statements for entry, upstream, the child, and the rate limit."""
from __future__ import annotations

import json
import os
import random

from bridge import ENV_ALLOWLIST, _environment
from rate import RateLimiter
from service import dispatch
from spec import _share_raw
from tests.support import ADDRESS, FakeBridge, market, success

QUOTE = {"market_address": ADDRESS, "outcome_idx": 0, "shares": "1"}
_CHILD_NAMES = set(ENV_ALLOWLIST) | {
    "NODE_OPTIONS",
    "DELPHI_API_ACCESS_KEY",
}


def test_random_invalid_shares_never_reach_the_bridge(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "configured-key-value")
    monkeypatch.setenv("DELPHI_NETWORK", "testnet")
    rng = random.Random(14)
    bridge = FakeBridge([])
    seen = 0
    while seen < 200:
        shares = rng.choice([
            "0",
            "-1",
            "1e-7",
            "0." + "1" * rng.randint(19, 40),
            " " + "1",
            "+1",
            "01",
            "".join(rng.choice("abc.e+- ") for _ in range(rng.randint(1, 24))),
        ])
        if _share_raw(shares) is not None:
            continue
        text = dispatch(
            "delphi_quote_buy",
            {**QUOTE, "shares": shares},
            caller=bridge,
            reserve_fn=lambda _count: True,
        )
        data = json.loads(text)
        if data["ok"]:
            continue
        seen += 1
        assert data["error_type"] == "invalid_argument"
    assert bridge.calls == []
    assert seen >= 200


def test_random_broken_markets_are_never_a_partial_success(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "configured-key-value")
    monkeypatch.setenv("DELPHI_NETWORK", "testnet")
    rng = random.Random(15)
    replies = []
    for _ in range(200):
        row = market()
        row["id"] = "0x" + "".join(rng.choice("ghijklmnopqrstuvwxyz") for _ in range(40))
        replies.append(success({"markets": [row]}))
    bridge = FakeBridge(replies)
    for _ in range(200):
        data = json.loads(dispatch(
            "delphi_list_markets",
            {},
            caller=bridge,
            reserve_fn=lambda _count: True,
        ))
        assert data["ok"] is False
        assert "markets" not in data


def test_random_parent_names_stay_out_of_the_child_environment(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "configured-key-value")
    rng = random.Random(16)
    for _ in range(200):
        name = "EXTRA_" + "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(12))
        monkeypatch.setenv(name, "marker")
    for needs_key in (False, True):
        env = _environment(needs_key)
        assert set(env) <= _CHILD_NAMES
        assert not any(name.startswith("EXTRA_") for name in env)
        assert "PRIVATE" not in "".join(env)
    assert "DELPHI_API_ACCESS_KEY" not in _environment(False)
    assert os.environ["DELPHI_API_ACCESS_KEY"] == "configured-key-value"


def test_random_reservations_never_pass_thirty():
    limiter = RateLimiter(limit=30, window=60.0, clock=lambda: 0.0)
    rng = random.Random(17)
    held = 0
    for _ in range(500):
        count = rng.randint(0, 10)
        if limiter.reserve(count):
            held += count
        else:
            assert held + count > 30 or count > 30
        assert held <= 30
    assert held == 30
