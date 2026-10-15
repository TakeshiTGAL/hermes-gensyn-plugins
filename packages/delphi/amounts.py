"""Exact decimal arithmetic for edge and quotes."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from fractions import Fraction
if __package__:
    from .contract import validate
    from .spec import _is_nonneg_decimal
else:
    from contract import validate
    from spec import _is_nonneg_decimal
def fee_percent(raw):
    if raw is None: return None
    whole, frac = divmod(int(raw) * 100, 10**18)
    return str(whole) if frac == 0 else f"{whole}.{frac:018d}".rstrip("0")
def _fail(message):
    raise ValueError(message)
def _fraction(text):
    try:
        return Fraction(Decimal(text))
    except (InvalidOperation, ValueError, ZeroDivisionError):
        _fail("probability is not an exact decimal")
def _plain(value):
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    numerator = abs(value.numerator)
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        _fail("probability difference is not a finite decimal")
    scale = max(twos, fives)
    numerator *= (2 ** (scale - twos)) * (5 ** (scale - fives))
    digits = str(numerator).rjust(scale + 1, "0")
    if scale == 0: return sign + digits
    text = f"{sign}{digits[:-scale]}.{digits[-scale:]}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text
def _places(text): return len(text.partition(".")[2])
def _share_fraction(text):
    whole, _, frac = text.partition(".")
    return Fraction(int(f"{int(whole or '0')}{frac}" or "0"), 10 ** len(frac))
def _cut(value, scale, ceil=False):
    scaled = value * (10 ** scale)
    whole = int(scaled)
    if ceil and scaled != whole:
        whole += 1
    digits = str(whole).rjust(scale + 1, "0")
    text = f"{digits[:-scale]}.{digits[-scale:]}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text
def shares_decimal(raw_text):
    return _plain(Fraction(int(raw_text), 10 ** 18))
def per_share(raw_text, shares_text, ceil=False):
    ratio = Fraction(int(raw_text)) / _share_fraction(shares_text)
    try:
        text = _plain(ratio)
    except ValueError: return _cut(ratio, 18, ceil), True
    if _places(text) <= 18 and not ceil: return text, False
    if _places(text) <= 18 and ceil and Fraction(text) == ratio: return text, False
    return _cut(ratio, 18, ceil), True
def _human(raw_text, decimals): return _plain(Fraction(int(raw_text), 10 ** decimals))
def local_edge(yours, implied, source):
    difference = _fraction(yours) - _fraction(implied)
    relation = "above" if difference > 0 else "below" if difference < 0 else "equal"
    return {
        "implied_probability": implied, "your_probability": yours, "edge": _plain(difference),
        "relation": relation, "probability_source": source, }
def _shown(raw_text, shares_text, decimals, ceil):
    ratio = Fraction(int(raw_text), 10 ** decimals) / _share_fraction(shares_text)
    try:
        text = _plain(ratio)
    except ValueError:
        return _cut(ratio, 18, ceil)
    if _places(text) <= 18 and (not ceil or Fraction(text) == ratio): return text
    return _cut(ratio, 18, ceil)
def quote_body(tool, args, result):
    problem = validate("sdk.quote", result)
    if problem:
        _fail(problem)
    decimals = result["decimals"]
    if decimals["status"] == "known" and "value" not in decimals:
        _fail("collateral decimals are incomplete")
    side = "buy" if tool.endswith("_buy") else "sell"
    ceil = side == "buy"
    share, truncated = per_share(result["amount_raw"], args["shares"], ceil)
    body = {
        "market_address": args["market_address"], "outcome_idx": args["outcome_idx"],
        "shares": args["shares"], "side": side, "amount_raw": result["amount_raw"],
        "decimals": decimals, "per_share": share, "per_share_truncated": truncated, "is_probability": False, }
    if decimals["status"] == "known":
        rendered = _human(result["amount_raw"], decimals["value"])
        if _is_nonneg_decimal(rendered):
            body["amount"] = rendered
            display = _shown(result["amount_raw"], args["shares"], decimals["value"], ceil)
            if _is_nonneg_decimal(display): body["per_share_display"] = display
        else:
            body["decimals"] = {"status": "unavailable"}
    return body
