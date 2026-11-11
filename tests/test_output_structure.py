"""Structural checks of the Tableplop output, including a small formula evaluator."""

import json
import re
from collections import defaultdict
from typing import Any, Dict, List

import pytest
import tableplop

ALLOWED_TYPES = {
    "tab-section",
    "title-section",
    "horizontal-section",
    "section",
    "paragraph",
    "text",
    "number",
    "checkbox",
    "checkboxes",
    "health",
    "ability",
    "saving-throw",
    "skill",
    "message",
    "filter-list",
}
FUNCTIONS = {"floor", "ceil", "min", "max"}
TOKEN = re.compile(
    r"\s*(?:(\d+)|([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)|(<=|>=|[-+*/()?:<>,]))"
)


def tokenize(formula: str) -> List[str]:
    tokens, pos = [], 0
    formula = formula.rstrip()
    while pos < len(formula):
        match = TOKEN.match(formula, pos)
        assert match, f"cannot tokenize {formula!r} at {pos}"
        tokens.append(next(g for g in match.groups() if g is not None))
        pos = match.end()
    return tokens


def evaluate(formula: str, values: Dict[str, Any]) -> float:
    """Evaluates the subset of the Tableplop formula language the converter emits."""
    tokens = tokenize(formula)
    pos = 0

    def peek() -> str:
        return tokens[pos] if pos < len(tokens) else ""

    def take(expected: str = "") -> str:
        nonlocal pos
        token = tokens[pos]
        assert not expected or token == expected, (formula, expected, token)
        pos += 1
        return token

    def ternary() -> Any:
        condition = comparison()
        if peek() == "?":
            take("?")
            yes = ternary()
            take(":")
            no = ternary()
            return yes if condition else no
        return condition

    def comparison() -> Any:
        left = additive()
        if peek() in ("<", "<=", ">", ">="):
            op = take()
            right = additive()
            return {
                "<": left < right,
                "<=": left <= right,
                ">": left > right,
                ">=": left >= right,
            }[op]
        return left

    def additive() -> Any:
        value = term()
        while peek() in ("+", "-"):
            op = take()
            right = term()
            value = value + right if op == "+" else value - right
        return value

    def term() -> Any:
        value = factor()
        while peek() in ("*", "/"):
            op = take()
            right = factor()
            value = value * right if op == "*" else value / right
        return value

    def factor() -> Any:
        token = take()
        if token == "-":
            return -factor()
        if token == "(":
            value = ternary()
            take(")")
            return value
        if token.isdigit():
            return int(token)
        if token in FUNCTIONS:
            take("(")
            args = [ternary()]
            while peek() == ",":
                take(",")
                args.append(ternary())
            take(")")
            import math

            return {"floor": math.floor, "ceil": math.ceil, "min": min, "max": max}[
                token
            ](*args)
        value = values[token]
        if value == "":
            return 0
        return value

    result = ternary()
    assert pos == len(tokens), f"trailing tokens in {formula!r}"
    return result


@pytest.fixture
def sheet(character) -> Dict[str, Any]:
    character["preferences"]["showUnarmedStrike"] = True
    result = tableplop.convert(character)
    json.dumps(result)  # must be serialisable
    return result


def test_top_level(sheet) -> None:
    assert set(sheet) == {"properties", "private", "type"}
    assert sheet["type"] == "tableplop-character-v2"
    assert sheet["private"] is False


def test_tabs(sheet) -> None:
    tabs = [p for p in sheet["properties"] if p["parentId"] is None]
    assert all(p["type"] == "tab-section" for p in tabs)
    assert [p["value"] for p in sorted(tabs, key=lambda p: p["rank"])] == [
        "Character",
        "Combat",
        "Spells",
        "Inventory",
    ]


def test_ids_parents_ranks_and_fields(sheet) -> None:
    props = sheet["properties"]
    ids = [p["id"] for p in props]
    assert all(isinstance(i, int) for i in ids)
    assert len(ids) == len(set(ids))
    known = set(ids)
    ranks = defaultdict(list)
    for prop in props:
        assert prop["parentId"] is None or prop["parentId"] in known
        assert prop["type"] in ALLOWED_TYPES
        assert isinstance(prop["data"], dict)
        assert isinstance(prop["rank"], int)
        assert prop["characterId"] == props[0]["characterId"]
        assert "value" in prop
        ranks[prop["parentId"]].append(prop["rank"])
        if prop["type"] == "tab-section":
            assert prop["parentId"] is None
    for parent_ranks in ranks.values():
        assert len(parent_ranks) == len(set(parent_ranks))


def test_names_unique_and_formula_safe(sheet) -> None:
    names = [p["name"] for p in sheet["properties"] if "name" in p]
    assert len(names) == len(set(names))
    for name in names:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name), name


def test_formula_references_exist(sheet) -> None:
    names = {p["name"] for p in sheet["properties"] if "name" in p}
    for prop in sheet["properties"]:
        if "formula" not in prop:
            continue
        for token in tokenize(prop["formula"]):
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", token) and token not in FUNCTIONS:
                assert token in names, (prop["name"], token)


def test_formula_values_agree(sheet) -> None:
    values = {p["name"]: p["value"] for p in sheet["properties"] if "name" in p}
    checked = 0
    for prop in sheet["properties"]:
        if "formula" in prop:
            assert evaluate(prop["formula"], values) == prop["value"], prop["name"]
            checked += 1
    kinds = {p["type"] for p in sheet["properties"] if "formula" in p}
    assert {"ability", "saving-throw", "skill"} <= kinds
    assert checked >= 6 + 6 + 18


def test_widget_children(sheet) -> None:
    props = sheet["properties"]
    by_id = {p["id"]: p for p in props}
    children = defaultdict(list)
    for prop in props:
        children[prop["parentId"]].append(prop)

    health = next(p for p in props if p["type"] == "health")
    assert {c["name"] for c in children[health["id"]]} == {
        "hit-points-maximum",
        "hit-points-temporary",
    }
    for prop in props:
        if prop["type"] == "checkboxes":
            assert [c["name"] for c in children[prop["id"]]] == [prop["name"] + "-max"]
        if prop["type"] == "ability":
            assert [c["name"] for c in children[prop["id"]]] == [
                prop["name"] + "-score"
            ]
        if prop["type"] == "message":
            assert by_id[prop["parentId"]]["type"] == "filter-list"
            assert prop["message"]
    counts = defaultdict(int)
    for prop in props:
        counts[prop["type"]] += 1
    assert counts["ability"] == 6
    assert counts["saving-throw"] == 6
    assert counts["skill"] == 18


def test_evaluator_sanity() -> None:
    assert evaluate("floor ((x - 10) / 2)", {"x": 9}) == -1
    assert evaluate(tableplop.PROFICIENCY_FORMULA, {"level": 9}) == 4
    assert evaluate("a ? 1 : b ? (floor (3 / 2)) : 0", {"a": "", "b": True}) == 1
