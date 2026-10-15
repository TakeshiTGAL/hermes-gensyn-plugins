"""One JSON decoder that never creates a binary float."""
import json
from decimal import Decimal
def parse_json(value):
    return json.loads(value, parse_float=Decimal)
