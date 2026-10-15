from __future__ import annotations

from copy import deepcopy

import pytest

from decimal import Decimal

from contract import CANON, ONE_OF, TABLES, TYPES, make_sample, validate


def all_fields():
    for table_name, fields in TABLES.items():
        for field_name, spec in fields.items():
            yield table_name, field_name, spec


@pytest.mark.parametrize("type_name", sorted(TYPES))
def test_every_type_has_complete_representatives(type_name):
    spec = TYPES[type_name]
    assert {"valid", "boundary", "wrong_type", "invalid", "check"} <= set(spec)
    assert spec["check"](deepcopy(spec["valid"]))
    assert spec["check"](deepcopy(spec["boundary"]))
    assert not spec["check"](deepcopy(spec["wrong_type"]))
    assert not spec["check"](deepcopy(spec["invalid"]))


@pytest.mark.parametrize("table_name", sorted(TABLES))
def test_complete_sample_passes(table_name):
    assert validate(table_name, make_sample(table_name)) is None


@pytest.mark.parametrize(
    "table_name,field_name,spec",
    list(all_fields()),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_every_required_field_rejects_missing(table_name, field_name, spec):
    value = make_sample(table_name)
    if field_name not in value:
        pytest.skip("field belongs to an unselected one-of form")
    value.pop(field_name)
    problem = validate(table_name, value)
    in_group = any(field_name in group for group in ONE_OF.get(table_name, ()))
    if spec.get("required", True) or in_group:
        assert problem
    else:
        assert problem is None


@pytest.mark.parametrize(
    "table_name,field_name,spec",
    list(all_fields()),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_every_field_rejects_unlisted_null(table_name, field_name, spec):
    value = make_sample(table_name)
    value[field_name] = None
    problem = validate(table_name, value)
    if spec.get("nullable") or spec.get("type") == "only_null":
        assert problem is None
    else:
        assert problem and field_name in problem


@pytest.mark.parametrize(
    "table_name,field_name,spec",
    list(all_fields()),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_every_field_rejects_wrong_type(table_name, field_name, spec):
    value = make_sample(table_name)
    if "type" in spec:
        value[field_name] = deepcopy(TYPES[spec["type"]]["wrong_type"])
    else:
        value[field_name] = "wrong"
    assert validate(table_name, value)


@pytest.mark.parametrize(
    "table_name,field_name,spec",
    list(all_fields()),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_every_scalar_field_rejects_its_invalid_representative(table_name, field_name, spec):
    if "type" not in spec:
        pytest.skip("nested table is covered recursively")
    value = make_sample(table_name)
    value[field_name] = deepcopy(TYPES[spec["type"]]["invalid"])
    assert validate(table_name, value)


def test_unknown_input_is_rejected_but_unknown_upstream_is_discardable():
    args = make_sample("args.get_market")
    args["unknown"] = True
    assert validate("args.get_market", args)
    row = make_sample("sdk.market")
    row["futureSdkField"] = "ignored"
    assert validate("sdk.market", row) is None


@pytest.mark.parametrize("table_name", sorted(ONE_OF))
def test_each_one_of_form_passes_and_the_mix_fails(table_name):
    groups = ONE_OF[table_name]
    for group in groups:
        value = make_sample(table_name)
        for other in groups:
            for name in other:
                value.pop(name, None)
        for name in group:
            kind = TABLES[table_name][name]["type"]
            value[name] = deepcopy(TYPES[kind]["valid"])
        assert validate(table_name, value) is None
    mixed = make_sample(table_name)
    for name in groups[1]:
        kind = TABLES[table_name][name]["type"]
        mixed[name] = deepcopy(TYPES[kind]["valid"])
    assert validate(table_name, mixed)


def test_non_object_is_rejected():
    assert validate("args.list_markets", []) == "args.list_markets must be an object"


def canon_fields():
    for table_name, fields in TABLES.items():
        for field_name, spec in fields.items():
            if spec.get("type") in CANON:
                yield table_name, field_name, spec["type"]


def mixed_form(kind):
    if kind == "uuid":
        return "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"
    if kind == "address":
        return "0x" + "Ab" * 20
    if kind == "tx_hash":
        return "0x" + "Ab" * 32
    return "https://testnet.delphi.fyi/market/AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"


@pytest.mark.parametrize(
    "table_name,field_name,kind",
    list(canon_fields()),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_every_address_and_id_field_has_one_form(table_name, field_name, kind):
    value = make_sample(table_name)
    mixed = mixed_form(kind)
    assert mixed != CANON[kind](mixed)
    for group in ONE_OF.get(table_name, ()):
        if field_name not in group:
            continue
        for other in ONE_OF[table_name]:
            if other == group:
                continue
            for name in other:
                value.pop(name, None)
    if field_name not in value:
        for group in ONE_OF.get(table_name, ()):
            if field_name not in group:
                continue
            for other in ONE_OF[table_name]:
                for name in other:
                    value.pop(name, None)
            for name in group:
                kind_name = TABLES[table_name][name]["type"]
                value.setdefault(name, deepcopy(TYPES[kind_name]["valid"]))
    value[field_name] = mixed
    assert validate(table_name, value) is None
    assert value[field_name] == CANON[kind](mixed)


def placed_sample(table_name, field_name):
    value = make_sample(table_name)
    if field_name == "market_address" and table_name == "args.compute_edge":
        value.pop("implied_probability", None)
        value["outcome_idx"] = 0
        value["market_address"] = deepcopy(TYPES["address"]["valid"])
        return value
    if field_name in value:
        return value
    for group in ONE_OF.get(table_name, ()):
        if field_name not in group:
            continue
        for other in ONE_OF[table_name]:
            for name in other:
                value.pop(name, None)
        for name in group:
            kind_name = TABLES[table_name][name]["type"]
            value[name] = deepcopy(TYPES[kind_name]["valid"])
        return value
    return value


FREE_TEXT = {
    ("sdk.metadata", "question"),
    ("sdk.metadata", "outcomes"),
    ("sdk.market", "metadataUri"),
    ("sdk.market", "metadataUriContentHash"),
    ("sdk.market", "fetchResponseStatus"),
    ("sdk.market", "proof"),
    ("sdk.market", "error"),
    ("out.proof_box", "text"),
    ("out.error", "message"),
}
SKIP_TYPES = {
    "text", "nullable_text", "text_list", "json_value", "only_null", "phrase",
    "clip_text", "receipt_json",
}
BAD_CHARS = [
    ("space", " "),
    ("cf", "\u2061"),
    ("percent", "%"),
    ("backslash", "\\"),
    ("amp", "&"),
]


def strict_columns():
    found = []
    for table_name, field_name, spec in all_fields():
        kind = spec.get("type")
        if kind in SKIP_TYPES or kind is None:
            continue
        found.append((table_name, field_name, kind))
    return found


def test_free_text_columns_are_only_the_listed_set():
    found = set()
    for table_name, field_name, spec in all_fields():
        if spec.get("type") in {"text", "text_list", "nullable_text"}:
            found.add((table_name, field_name))
    assert found == FREE_TEXT


@pytest.mark.parametrize(
    "table_name,field_name,kind,label,bad",
    [
        (*column, label, bad)
        for column in strict_columns()
        for label, bad in BAD_CHARS
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_strict_column_rejects_markup(table_name, field_name, kind, label, bad):
    del kind, label
    value = placed_sample(table_name, field_name)
    current = value[field_name]
    if isinstance(current, str):
        value[field_name] = f"{current}{bad}"
    elif isinstance(current, list) and current and isinstance(current[0], str):
        current[0] = f"{current[0]}{bad}"
    else:
        value[field_name] = f"{current}{bad}"
    problem = validate(table_name, value)
    assert problem and field_name in problem


def test_decimal_json_numbers_stay_inside_upstream_objects():
    row = make_sample("sdk.market")
    row["dataSources"] = {"weight": Decimal("1.5"), "tags": [Decimal("0")]}
    assert validate("sdk.market", row) is None
