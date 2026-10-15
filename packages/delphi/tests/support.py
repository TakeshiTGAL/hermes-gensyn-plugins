from __future__ import annotations

from copy import deepcopy

ADDRESS = "0x" + "ab" * 20
WALLET = "0x" + "cd" * 20
OTHER = "0x" + "ef" * 20
MARKET_UUID = "11111111-1111-4111-8111-111111111111"


def market(*, probabilities=None, **changes):
    row = {
        "id": ADDRESS,
        "appMarketId": MARKET_UUID,
        "marketUrl": f"https://testnet.delphi.fyi/market/{MARKET_UUID}",
        "status": "open",
        "category": "crypto",
        "deployer": "0x" + "11" * 20,
        "implementation": "0x" + "22" * 20,
        "metadataUri": "ipfs://metadata",
        "metadataUriContentHash": "abc123",
        "metadata": {"question": "Will it rain?", "outcomes": ["Yes", "No"]},
        "dataSources": [],
        "createdAt": "2026-01-01T00:00:00Z",
        "fetchedAt": None,
        "fetchResponseStatus": None,
        "resolvesAt": None,
        "settledAt": None,
        "settlesAt": "2026-12-01T00:00:00Z",
        "winningOutcomeIdx": None,
        "tradingFee": "20000000000000000",
        "proof": None,
        "error": None,
        "verifiable": True,
    }
    if probabilities is not None:
        row["spotPrices"] = list(probabilities)
        row["spotImpliedProbabilities"] = list(probabilities)
    row.update(changes)
    return row


def position(**changes):
    row = {
        "id": "position-1",
        "marketProxy": ADDRESS,
        "wallet": WALLET,
        "outcomeIdx": "0",
        "shares": "1000000000000000000",
        "redeemedOrLiquidated": False,
        "tokensRedeemed": "0",
        "marketStatus": "open",
    }
    row.update(changes)
    return row


def event(**changes):
    row = {
        "id": "event-1",
        "block_number": "10",
        "timestamp_": "20",
        "transactionHash_": "0x" + "12" * 32,
        "contractId_": "contract-1",
        "marketProxy": ADDRESS,
    }
    row.update(changes)
    return row


def meta(**changes):
    row = {
        "block": {"number": 7, "timestamp": 8, "hash": "0x" + "ab" * 32},
        "deployment": "deployment",
        "hasIndexingErrors": False,
    }
    row.update(changes)
    return row


class FakeBridge:
    def __init__(self, replies):
        self.replies = [deepcopy(item) for item in replies]
        self.calls = []

    def __call__(self, op, args, *, needs_key, budget, network):
        self.calls.append((op, deepcopy(args), needs_key, budget, network))
        if not self.replies:
            raise AssertionError(f"no reply for {op}")
        return self.replies.pop(0)


def success(result, outbound=1):
    return {"ok": True, "result": deepcopy(result), "outbound": outbound}


def failure(kind="upstream", message="failed", outbound=0):
    return {
        "ok": False,
        "error_type": kind,
        "message": message,
        "outbound": outbound,
    }
