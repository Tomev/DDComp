"""Tests for the D&D Beyond -> 5e number computations."""

from typing import Any, Dict

import pytest
import tableplop
from conftest import item, mod, slot_table, spell


def by_name(sheet: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {p["name"]: p for p in sheet["properties"] if "name" in p}


# ---- ability scores ----------------------------------------------------------------


def test_ability_scores_add_bonuses_and_ignore_unresolved_choices(character) -> None:
    scores = tableplop.ability_scores(character)
    assert scores == {
        "strength": 8,
        "dexterity": 16,
        "constitution": 14,
        "intelligence": 10,
        "wisdom": 12,
        "charisma": 17,
    }


def test_ability_scores_manual_bonus_override_and_set(character) -> None:
    character["bonusStats"][3]["value"] = 2  # INT
    character["overrideStats"][0]["value"] = 19  # STR
    character["modifiers"]["item"] = [
        mod("set", "constitution-score", 19, componentId=500, requiresAttunement=True)
    ]
    character["inventory"].append(
        item(500, "Amulet of Health", "Wondrous item", attuned=True)
    )
    scores = tableplop.ability_scores(character)
    assert scores["intelligence"] == 12
    assert scores["strength"] == 19
    assert scores["constitution"] == 19


def test_set_score_never_lowers_and_needs_attunement(character) -> None:
    character["modifiers"]["item"] = [
        mod("set", "charisma-score", 12, componentId=501),
        mod("set", "constitution-score", 19, componentId=500, requiresAttunement=True),
    ]
    character["inventory"].append(item(501, "Odd Hat", "Wondrous item"))
    character["inventory"].append(item(500, "Amulet of Health", "Wondrous item"))
    scores = tableplop.ability_scores(character)
    assert scores["charisma"] == 17
    assert scores["constitution"] == 14  # not attuned


def test_modifier_rounds_down() -> None:
    assert [tableplop.modifier(s) for s in (1, 8, 9, 10, 11, 17, 20)] == [
        -5,
        -1,
        -1,
        0,
        0,
        3,
        5,
    ]


@pytest.mark.parametrize(
    "level,bonus",
    [(1, 2), (4, 2), (5, 3), (8, 3), (9, 4), (12, 4), (13, 5), (17, 6), (20, 6)],
)
def test_proficiency_bonus(level: int, bonus: int) -> None:
    assert tableplop.proficiency_bonus(level) == bonus


# ---- saves, skills, initiative -----------------------------------------------------


def test_saving_throws(character) -> None:
    props = by_name(tableplop.convert(character))
    assert props["dexterity-save"]["value"] == 6
    assert props["dexterity-save-proficiency"]["value"] is True
    assert props["charisma-save"]["value"] == 6
    assert props["strength-save"]["value"] == -1
    assert props["strength-save-proficiency"]["value"] is False


def test_save_bonus_from_attuned_item_is_folded_in(character) -> None:
    character["modifiers"]["item"] = [
        mod("bonus", "saving-throws", 1, componentId=600, requiresAttunement=True)
    ]
    character["inventory"].append(item(600, "Cloak", "Wondrous item", attuned=True))
    props = by_name(tableplop.convert(character))
    assert props["strength-save"]["value"] == 0
    assert props["strength-save"]["formula"].endswith("+ 1")


def test_skills_proficiency_expertise_and_half_proficiency(character) -> None:
    props = by_name(tableplop.convert(character))
    assert props["stealth"]["value"] == 6  # DEX 3 + prof 3
    assert props["persuasion"]["value"] == 9  # CHA 3 + prof 3 + expertise 3
    assert props["persuasion-expertise"]["value"] is True
    assert props["athletics"]["value"] == 0  # STR -1 + half prof 1
    assert props["insight"]["value"] == 2  # WIS 1 + half prof 1
    assert props["jack-of-all-trades"]["value"] is True
    assert props["stealth"]["data"] == {"subtitle": "dex"}


def test_skills_without_half_proficiency(character) -> None:
    character["modifiers"]["class"] = [
        m for m in character["modifiers"]["class"] if m["type"] != "half-proficiency"
    ]
    props = by_name(tableplop.convert(character))
    assert props["athletics"]["value"] == -1
    assert props["jack-of-all-trades"]["value"] is False
    assert props["initiative"]["value"] == 3


def test_expertise_implies_proficiency(character) -> None:
    character["modifiers"]["class"].append(mod("expertise", "arcana"))
    props = by_name(tableplop.convert(character))
    assert props["arcana-proficiency"]["value"] is True
    assert props["arcana"]["value"] == 6


def test_initiative_with_half_proficiency_and_alert(character) -> None:
    character["modifiers"]["feat"] = [mod("bonus", "initiative", 5)]
    props = by_name(tableplop.convert(character))
    assert props["initiative"]["value"] == 3 + 1 + 5
    assert props["initiative"]["formula"] == "dexterity + 6"


# ---- hit points ----------------------------------------------------------------------


def test_hit_points_fixed(character) -> None:
    props = by_name(tableplop.convert(character))
    assert props["hit-points-maximum"]["value"] == 28 + 2 * 5
    assert props["hit-points"]["value"] == 38 - 5
    assert props["hit-points-temporary"]["value"] == 3


def test_hit_points_per_level_bonus_and_manual_bonus(character) -> None:
    character["modifiers"]["feat"] = [mod("bonus", "hit-points-per-level", 2)]
    character["bonusHitPoints"] = 4
    character["temporaryHitPoints"] = 0
    props = by_name(tableplop.convert(character))
    assert props["hit-points-maximum"]["value"] == 28 + 4 + (2 + 2) * 5
    assert props["hit-points-temporary"]["value"] == ""


def test_hit_points_override_and_floor_at_zero(character) -> None:
    character["overrideHitPoints"] = 20
    character["removedHitPoints"] = 25
    props = by_name(tableplop.convert(character))
    assert props["hit-points-maximum"]["value"] == 20
    assert props["hit-points"]["value"] == 0


# ---- armor class and speed -----------------------------------------------------------


def test_ac_light_armor(character) -> None:
    mods = tableplop.active_modifiers(character)
    scores = tableplop.ability_scores(character, mods)
    assert tableplop.armor_class(character, scores, mods) == 11 + 3


def test_ac_medium_armor_caps_dex_and_shield_adds(character) -> None:
    character["inventory"][0] = item(
        11, "Scale Mail", "Armor", armorTypeId=2, armorClass=14
    )
    character["inventory"].append(
        item(8, "Shield", "Armor", armorTypeId=4, armorClass=2)
    )
    mods = tableplop.active_modifiers(character)
    scores = tableplop.ability_scores(character, mods)
    assert tableplop.armor_class(character, scores, mods) == 14 + 2 + 2


def test_ac_heavy_armor_and_item_bonus_only_when_equipped(character) -> None:
    character["inventory"][0] = item(
        4619, "Demon Armor", "Armor", armorTypeId=3, armorClass=18
    )
    character["inventory"].append(
        item(
            5120,
            "Studded Leather, +3",
            "Armor",
            equipped=False,
            armorTypeId=1,
            armorClass=12,
        )
    )
    character["modifiers"]["item"] = [
        mod("bonus", "armor-class", 1, componentId=4619),
        mod("bonus", "armor-class", 3, componentId=5120),
    ]
    mods = tableplop.active_modifiers(character)
    scores = tableplop.ability_scores(character, mods)
    assert tableplop.armor_class(character, scores, mods) == 19


def test_ac_unarmored_barbarian(character) -> None:
    character["inventory"] = []
    character["classes"][0]["definition"]["name"] = "Barbarian"
    mods = tableplop.active_modifiers(character)
    scores = tableplop.ability_scores(character, mods)
    assert tableplop.armor_class(character, scores, mods) == 10 + 3 + 2


def test_speed_with_set_fly_and_heavy_armor_penalty(character) -> None:
    character["inventory"][0] = item(
        12, "Plate", "Armor", armorTypeId=3, armorClass=18, strengthRequirement=15
    )
    character["modifiers"]["item"] = [mod("set", "speed-flying", 90, componentId=12)]
    mods = tableplop.active_modifiers(character)
    scores = tableplop.ability_scores(character, mods)
    assert tableplop.speeds(character, scores, mods) == {"walk": 15, "fly": 90}
    character["modifiers"]["race"].append(mod("ignore", "heavy-armor-speed-reduction"))
    mods = tableplop.active_modifiers(character)
    assert tableplop.speeds(character, scores, mods)["walk"] == 25


# ---- attacks -----------------------------------------------------------------------


def test_weapon_attacks_finesse_and_skip_unequipped(character) -> None:
    mods = tableplop.active_modifiers(character)
    scores = tableplop.ability_scores(character, mods)
    attacks = tableplop.weapon_attacks(character, scores, 3, mods)
    assert [a.name for a in attacks] == ["Rapier"]
    assert attacks[0].to_hit == 3 + 3
    assert (attacks[0].damage_dice, attacks[0].damage_bonus) == ("1d8", 3)


def test_ranged_magic_weapon_with_archery_and_no_proficiency(character) -> None:
    character["inventory"][2]["equipped"] = True
    character["inventory"][2]["definition"]["grantedModifiers"] = [
        mod("bonus", "magic", 1)
    ]
    character["modifiers"]["class"].append(mod("bonus", "ranged-weapon-attacks", 2))
    character["preferences"]["showUnarmedStrike"] = True
    mods = tableplop.active_modifiers(character)
    scores = tableplop.ability_scores(character, mods)
    attacks = {a.name: a for a in tableplop.weapon_attacks(character, scores, 3, mods)}
    bow = attacks["Longbow"]
    assert bow.to_hit == 3 + 0 + 1 + 2  # DEX, not proficient, +1 magic, archery
    assert bow.damage_bonus == 3 + 1
    unarmed = attacks["Unarmed Strike"]
    assert (unarmed.to_hit, unarmed.damage_bonus) == (-1 + 3, 0)


def test_attack_message_text(character) -> None:
    sheet = tableplop.convert(character)
    messages = [p for p in sheet["properties"] if p["type"] == "message"]
    rapier = next(p for p in messages if p["name"] == "attack-rapier")
    assert rapier["message"].startswith(
        "Rapier: {1d20 + 6} to hit, {1d8 + 3} piercing."
    )


# ---- spells --------------------------------------------------------------------------


def test_spell_dc_attack_and_known_caster_list(character) -> None:
    props = by_name(tableplop.convert(character))
    assert props["spell-save-dc"]["value"] == 8 + 3 + 3
    assert props["spell-attack-bonus"]["value"] == 3 + 3
    assert props["spellcasting-ability"]["value"] == "Charisma"
    mockery = props["spell-vicious-mockery"]["message"]
    assert "WIS save DC 14" in mockery
    assert "{2d4} psychic" in mockery  # cantrip damage scales at level 5
    assert "spell-healing-word" in props and "spell-shatter" in props


def test_prepared_caster_keeps_only_prepared_spells(character) -> None:
    character["classes"][0]["definition"]["name"] = "Cleric"
    character["classes"][0]["definition"]["spellCastingAbilityId"] = 5
    character["classSpells"][0]["spells"] = [
        spell("Sacred Flame", 0),
        spell("Bless", 1, prepared=True),
        spell("Cure Wounds", 1, always=True),
        spell("Guiding Bolt", 1, requiresAttackRoll=True),
    ]
    mods = tableplop.active_modifiers(character)
    scores = tableplop.ability_scores(character, mods)
    spells = tableplop.spell_list(character, scores, 3, mods)
    assert [s.name for s in spells] == ["Sacred Flame", "Bless", "Cure Wounds"]
    assert spells[0].save_dc == 8 + 3 + 1


def test_spell_attack_roll_in_message(character) -> None:
    character["classSpells"][0]["spells"] = [
        spell("Fire Bolt", 0, requiresAttackRoll=True)
    ]
    props = by_name(tableplop.convert(character))
    assert "{1d20 + 6} to hit" in props["spell-fire-bolt"]["message"]


def test_spell_slots_single_class_from_table_not_available(character) -> None:
    slots = tableplop.spell_slots(character)
    assert [(s.level, s.maximum, s.used) for s in slots.regular] == [
        (1, 4, 1),
        (2, 3, 0),
        (3, 2, 0),
    ]
    props = by_name(tableplop.convert(character))
    assert props["spell-slots-level-3"]["value"] == 2
    assert props["spell-slots-used-1"]["value"] == 1
    assert props["spell-slots-used-1-max"]["formula"] == "spell-slots-level-1"


def test_spell_slots_multiclass_rule(character) -> None:
    character["classes"][0]["level"] = 3
    character["classes"].append(
        {
            "id": 78,
            "level": 5,
            "definition": {
                "name": "Paladin",
                "hitDice": 10,
                "canCastSpells": True,
                "spellCastingAbilityId": 6,
                "spellRules": {
                    "levelSpellSlots": slot_table({5: [4, 2]}),
                    "multiClassSpellSlotDivisor": 2,
                    "multiClassSpellSlotRounding": 1,
                },
            },
        }
    )
    # caster level 3 + floor(5 / 2) = 5 -> 4/3/2
    assert [s.maximum for s in tableplop.spell_slots(character).regular] == [4, 3, 2]
    character["classes"][1]["definition"]["spellRules"][
        "multiClassSpellSlotRounding"
    ] = 2
    # 3 + ceil(5 / 2) = 6 -> 4/3/3
    assert [s.maximum for s in tableplop.spell_slots(character).regular] == [4, 3, 3]


def test_non_caster_class_table_is_ignored(character) -> None:
    character["classes"][0]["definition"]["canCastSpells"] = False
    character["classSpells"] = []
    assert tableplop.spell_slots(character).regular == []
    sheet = tableplop.convert(character)
    tabs = [p["value"] for p in sheet["properties"] if p["type"] == "tab-section"]
    assert tabs == ["Character", "Combat", "Inventory"]


def test_warlock_pact_slots_are_separate(character) -> None:
    character["classes"][0]["definition"]["name"] = "Warlock"
    character["classes"][0]["definition"]["spellRules"]["levelSpellSlots"] = slot_table(
        {5: [0, 0, 2]}
    )
    slots = tableplop.spell_slots(character)
    assert slots.regular == []
    assert [(s.level, s.maximum) for s in slots.pact] == [(3, 2)]


# ---- features, text, privacy ---------------------------------------------------------


def test_limited_use_from_stat(character) -> None:
    props = by_name(tableplop.convert(character))
    assert (
        "Bardic Inspiration:</strong> 3 uses per long rest"
        in props["features"]["value"]
    )


def test_paragraph_text_is_html_escaped(character) -> None:
    props = by_name(tableplop.convert(character))
    details = props["details"]["value"]
    assert "Fairness &amp; &lt;truth&gt;" in details
    assert "Line one<br>Line two" in details
    assert "<truth>" not in details


def test_user_text_cannot_inject_rolls(character) -> None:
    character["inventory"][1]["definition"]["name"] = "!Evil {1d100} Blade @:x:"
    sheet = tableplop.convert(character)
    message = next(p for p in sheet["properties"] if p["type"] == "message")["message"]
    assert "{1d100}" not in message and not message.startswith("!")
    assert "@:" not in message


def test_username_never_in_output(character) -> None:
    character["name"] = "SecretPlayer's Character"
    sheet = tableplop.convert(character)
    text = str(sheet)
    assert "SecretPlayer" not in text
    assert "987654" not in text
    assert by_name(sheet)["character-name"]["value"] == "Character"


def test_output_filename() -> None:
    assert (
        tableplop.output_filename("Mira <Quickfoot> & Co")
        == "mira_quickfoot_co_tableplop.json"
    )
    assert tableplop.output_filename("???") == "character_tableplop.json"
