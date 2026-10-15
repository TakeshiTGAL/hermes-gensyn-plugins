from __future__ import annotations

from copy import deepcopy

import pytest

from contract import TABLES, TYPES, make_sample, validate


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
    value.pop(field_name)
    problem = validate(table_name, value)
    if spec.get("required", True):
        assert problem and field_name in problem
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
        value[field_name] = "not-an-object"
    assert validate(table_name, value)


@pytest.mark.parametrize(
    "table_name,field_name,spec",
    list(all_fields()),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_every_scalar_field_rejects_its_invalid_representative(table_name, field_name, spec):
    if "type" not in spec:
        return
    value = make_sample(table_name)
    value[field_name] = deepcopy(TYPES[spec["type"]]["invalid"])
    assert validate(table_name, value)


def test_unknown_field_is_rejected_at_every_object():
    receipt = make_sample("receipt")
    receipt["extra"] = True
    assert validate("receipt", receipt)
    params = make_sample("receipt.parameters")
    params["extra"] = True
    assert validate("receipt.parameters", params)


def test_non_object_is_rejected():
    assert validate("receipt", []) == "receipt must be an object"
