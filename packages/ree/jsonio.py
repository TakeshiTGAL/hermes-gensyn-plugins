import json
from decimal import Decimal
def _reject_constant(name):
    raise ValueError(name)
def _pairs(items):
    value = {}
    for key, item in items:
        if key in value: raise ValueError("duplicate key")
        value[key] = item
    return value
def parse_json(value):
    return json.loads(value, parse_float=Decimal, parse_constant=_reject_constant, object_pairs_hook=_pairs)
