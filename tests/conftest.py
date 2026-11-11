"""Shared helpers and hand-written D&D Beyond fixtures for the tests."""

import copy
import os
import sys
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DDComp"),
)


def mod(
    mod_type: str, sub_type: str, value: Optional[int] = None, **extra: Any
) -> Dict:
    """A D&D Beyond modifier entry."""
    entry = {"type": mod_type, "subType": sub_type, "value": value, "fixedValue": value}
    entry.update(extra)
    return entry


def slot_table(rows: Dict[int, List[int]]) -> List[List[int]]:
    """A 21-row ``levelSpellSlots`` table with the given rows filled in."""
    table = [[0] * 9 for _ in range(21)]
    for level, row in rows.items():
        table[level] = row + [0] * (9 - len(row))
    return table


BARD_SLOTS = slot_table({5: [4, 3, 2], 6: [4, 3, 3]})


def item(
    definition_id: int,
    name: str,
    filter_type: str,
    equipped: bool = True,
    attuned: bool = False,
    quantity: int = 1,
    **definition: Any,
) -> Dict:
    """An inventory entry."""
    full = {"id": definition_id, "name": name, "filterType": filter_type}
    full.update(definition)
    return {
        "quantity": quantity,
        "equipped": equipped,
        "isAttuned": attuned,
        "definition": full,
    }


def spell(
    name: str,
    level: int,
    prepared: bool = False,
    always: bool = False,
    **definition: Any,
) -> Dict:
    """A spell entry as found in ``classSpells[].spells``."""
    full = {
        "name": name,
        "level": level,
        "school": "Evocation",
        "activation": {"activationTime": 1, "activationType": 1},
        "range": {"origin": "Ranged", "rangeValue": 60},
        "duration": {"durationType": "Instantaneous"},
        "components": [1, 2],
        "modifiers": [],
    }
    full.update(definition)
    return {
        "prepared": prepared,
        "alwaysPrepared": always,
        "countsAsKnownSpell": True,
        "spellCastingAbilityId": None,
        "definition": full,
    }


_BASE: Dict[str, Any] = {
    "id": 4242,
    "userId": 987654,
    "username": "SecretPlayer",
    "name": "Mira <Quickfoot> & Co",
    "stats": [
        {"id": 1, "value": 8},
        {"id": 2, "value": 14},
        {"id": 3, "value": 14},
        {"id": 4, "value": 10},
        {"id": 5, "value": 12},
        {"id": 6, "value": 15},
    ],
    "bonusStats": [{"id": i, "value": None} for i in range(1, 7)],
    "overrideStats": [{"id": i, "value": None} for i in range(1, 7)],
    "baseHitPoints": 28,
    "bonusHitPoints": None,
    "overrideHitPoints": None,
    "removedHitPoints": 5,
    "temporaryHitPoints": 3,
    "currentXp": 6500,
    "inspiration": True,
    "race": {
        "fullName": "Lightfoot Halfling",
        "weightSpeeds": {"normal": {"walk": 25, "fly": 0, "swim": 0}},
    },
    "background": {
        "hasCustomBackground": False,
        "definition": {"name": "Entertainer"},
    },
    "classes": [
        {
            "id": 77,
            "level": 5,
            "hitDiceUsed": 1,
            "definition": {
                "name": "Bard",
                "hitDice": 8,
                "canCastSpells": True,
                "spellCastingAbilityId": 6,
                "spellRules": {
                    "levelSpellSlots": BARD_SLOTS,
                    "multiClassSpellSlotDivisor": 1,
                    "multiClassSpellSlotRounding": 1,
                },
            },
            "subclassDefinition": {"name": "College of Lore"},
        }
    ],
    "modifiers": {
        "race": [mod("bonus", "dexterity-score", 2)],
        "class": [
            mod("bonus", "charisma-score", 2),
            mod("bonus", "choose-an-ability-score", 1),
            mod("proficiency", "dexterity-saving-throws"),
            mod("proficiency", "charisma-saving-throws"),
            mod("proficiency", "simple-weapons"),
            mod("proficiency", "rapier"),
            mod("proficiency", "stealth"),
            mod("proficiency", "persuasion"),
            mod("expertise", "persuasion"),
            mod("half-proficiency", "ability-checks"),
            mod("half-proficiency", "initiative"),
        ],
        "background": [],
        "item": [],
        "feat": [],
        "condition": [],
    },
    "inventory": [
        item(10, "Leather", "Armor", armorTypeId=1, armorClass=11),
        item(
            28,
            "Rapier",
            "Weapon",
            type="Rapier",
            categoryId=2,
            attackType=1,
            damage={"diceString": "1d8"},
            damageType="Piercing",
            range=5,
            longRange=5,
            properties=[{"name": "Finesse"}],
        ),
        item(
            37,
            "Longbow",
            "Weapon",
            equipped=False,
            type="Longbow",
            categoryId=2,
            attackType=2,
            damage={"diceString": "1d8"},
            damageType="Piercing",
            range=150,
            longRange=600,
            properties=[],
        ),
        item(90, "Torch", "Other Gear", equipped=False, quantity=10),
    ],
    "customItems": [],
    "currencies": {"cp": 1, "sp": 2, "ep": 0, "gp": 30, "pp": 0},
    "deathSaves": {"successCount": 1, "failCount": 0},
    "spellSlots": [
        {"level": i, "used": 1 if i == 1 else 0, "available": 0} for i in range(1, 10)
    ],
    "pactMagic": [{"level": i, "used": 0, "available": 0} for i in range(1, 6)],
    "classSpells": [
        {
            "characterClassId": 77,
            "spells": [
                spell(
                    "Vicious Mockery",
                    0,
                    requiresSavingThrow=True,
                    saveDcAbilityId=5,
                    scaleType="characterlevel",
                    modifiers=[
                        {
                            "type": "damage",
                            "subType": "psychic",
                            "die": {"diceCount": 1, "diceValue": 4},
                        }
                    ],
                ),
                spell("Healing Word", 1),
                spell("Shatter", 2),
            ],
        }
    ],
    "spells": {"race": [], "class": [], "background": [], "item": [], "feat": []},
    "actions": {
        "class": [
            {
                "name": "Bardic Inspiration",
                "limitedUse": {"maxUses": 0, "statModifierUsesId": 6, "resetType": 2},
            }
        ]
    },
    "feats": [],
    "traits": {"ideals": "Fairness & <truth>", "bonds": "My {lute}"},
    "notes": {"backstory": "Line one\nLine two"},
    "preferences": {"hitPointType": 1, "showUnarmedStrike": False},
}


@pytest.fixture
def character() -> Dict[str, Any]:
    """A fresh copy of a hand-written level 5 Bard character."""
    return copy.deepcopy(_BASE)
