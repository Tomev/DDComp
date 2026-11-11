"""
Conversion of public D&D Beyond characters into Tableplop character sheets.

The module has no Telegram dependencies. It provides:

* :func:`parse_character_url` -- extract the character id from a D&D Beyond URL,
* :func:`fetch_character` -- download the character JSON from D&D Beyond,
* :func:`convert` -- turn the character ``data`` object into a Tableplop
  ``tableplop-character-v2`` dictionary.

The computations follow 5e rules and the field layout of the D&D Beyond
``character/v5`` endpoint. They do not cover every feature, item or homebrew rule,
so computed values (AC, HP, attack bonuses...) may differ from the D&D Beyond sheet.
"""

import asyncio
import html
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from math import ceil, floor
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

import httpx

DDB_CHARACTER_ENDPOINT = (
    "https://character-service.dndbeyond.com/character/v5/character/{character_id}"
)
REQUEST_TIMEOUT_SECONDS = 20.0
TABLEPLOP_TYPE = "tableplop-character-v2"

# (D&D Beyond stat id, Tableplop property name, short label)
ABILITIES: List[Tuple[int, str, str]] = [
    (1, "strength", "str"),
    (2, "dexterity", "dex"),
    (3, "constitution", "con"),
    (4, "intelligence", "int"),
    (5, "wisdom", "wis"),
    (6, "charisma", "cha"),
]
ABILITY_BY_ID: Dict[int, str] = {stat_id: name for stat_id, name, _ in ABILITIES}

# Skill slug (used by both D&D Beyond and Tableplop) -> ability property name.
SKILLS: Dict[str, str] = {
    "acrobatics": "dexterity",
    "animal-handling": "wisdom",
    "arcana": "intelligence",
    "athletics": "strength",
    "deception": "charisma",
    "history": "intelligence",
    "insight": "wisdom",
    "intimidation": "charisma",
    "investigation": "intelligence",
    "medicine": "wisdom",
    "nature": "intelligence",
    "perception": "wisdom",
    "performance": "charisma",
    "persuasion": "charisma",
    "religion": "intelligence",
    "sleight-of-hand": "dexterity",
    "stealth": "dexterity",
    "survival": "wisdom",
}

# 5e multiclass spellcaster table: caster level -> slots for spell levels 1..9.
FULL_CASTER_SLOTS: List[List[int]] = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [2, 0, 0, 0, 0, 0, 0, 0, 0],
    [3, 0, 0, 0, 0, 0, 0, 0, 0],
    [4, 2, 0, 0, 0, 0, 0, 0, 0],
    [4, 3, 0, 0, 0, 0, 0, 0, 0],
    [4, 3, 2, 0, 0, 0, 0, 0, 0],
    [4, 3, 3, 0, 0, 0, 0, 0, 0],
    [4, 3, 3, 1, 0, 0, 0, 0, 0],
    [4, 3, 3, 2, 0, 0, 0, 0, 0],
    [4, 3, 3, 3, 1, 0, 0, 0, 0],
    [4, 3, 3, 3, 2, 0, 0, 0, 0],
    [4, 3, 3, 3, 2, 1, 0, 0, 0],
    [4, 3, 3, 3, 2, 1, 0, 0, 0],
    [4, 3, 3, 3, 2, 1, 1, 0, 0],
    [4, 3, 3, 3, 2, 1, 1, 0, 0],
    [4, 3, 3, 3, 2, 1, 1, 1, 0],
    [4, 3, 3, 3, 2, 1, 1, 1, 0],
    [4, 3, 3, 3, 2, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 2, 1, 1],
]

# Classes that cast every spell they know; other casters must prepare spells.
KNOWN_SPELL_CASTERS: Set[str] = {"Bard", "Sorcerer", "Warlock", "Ranger"}
PACT_MAGIC_CLASSES: Set[str] = {"Warlock"}

PROFICIENCY_FORMULA = (
    "level <= 4 ? 2 : level <= 8 ? 3 : level <= 12 ? 4 : level <= 16 ? 5 : 6"
)
MESSAGE_ICON = "/images/message.png"
ACTIVATION_TYPES: Dict[int, str] = {1: "action", 3: "bonus action", 4: "reaction"}
RESET_TYPES: Dict[int, str] = {1: "short rest", 2: "long rest"}
ARMOR_LIGHT, ARMOR_MEDIUM, ARMOR_HEAVY, ARMOR_SHIELD = 1, 2, 3, 4
FIREARM_PROPERTIES: Set[str] = {"Ammunition (Firearms)", "Reload", "Misfire"}


# --------------------------------------------------------------------------------------
# URL parsing and fetching
# --------------------------------------------------------------------------------------


class DDBError(Exception):
    """Base class for errors while getting a character from D&D Beyond."""


class CharacterPrivateError(DDBError):
    """D&D Beyond refused access (HTTP 403): the character is not public."""


class CharacterNotFoundError(DDBError):
    """D&D Beyond has no character with this id (HTTP 404)."""


class DDBUnavailableError(DDBError):
    """Network failure, timeout, or an unexpected response from D&D Beyond."""


_CHARACTER_PATH = re.compile(r"^/(?:profile/[^/]+/)?characters/(\d+)(?:/.*)?$")


def parse_character_url(url: str) -> Optional[int]:
    """
    Returns the character id from a D&D Beyond character URL, or ``None`` when the
    text is not such a URL. Accepts ``https://www.dndbeyond.com/characters/<id>``
    with or without ``www``, scheme, trailing slug, query string or fragment.
    """
    text = url.strip().strip("<>")
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    if (parsed.hostname or "").lower() not in ("dndbeyond.com", "www.dndbeyond.com"):
        return None
    match = _CHARACTER_PATH.match(parsed.path)
    if not match:
        return None
    character_id = int(match.group(1))
    return character_id if character_id > 0 else None


async def fetch_character(
    character_id: int, client: Optional[httpx.AsyncClient] = None
) -> Dict[str, Any]:
    """
    Downloads a public character from D&D Beyond and returns its ``data`` object.

    Raises :class:`CharacterPrivateError` (HTTP 403), :class:`CharacterNotFoundError`
    (HTTP 404) or :class:`DDBUnavailableError` (anything else that went wrong).
    """
    url = DDB_CHARACTER_ENDPOINT.format(character_id=character_id)
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "DDComp-bot", "Accept": "application/json"},
        )
    try:
        response = await client.get(url)
    except httpx.HTTPError as error:
        raise DDBUnavailableError(f"Request failed: {type(error).__name__}") from error
    finally:
        if own_client:
            await client.aclose()

    if response.status_code == 403:
        raise CharacterPrivateError(character_id)
    if response.status_code == 404:
        raise CharacterNotFoundError(character_id)
    if response.status_code != 200:
        raise DDBUnavailableError(f"HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as error:
        raise DDBUnavailableError("Response is not JSON") from error
    if not isinstance(payload, dict) or not payload.get("success"):
        raise DDBUnavailableError("D&D Beyond reported a failure")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DDBUnavailableError("Response has no character data")
    return data


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------


def modifier(score: int) -> int:
    """Returns the 5e ability modifier of a score."""
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    """Returns the proficiency bonus for a total character level."""
    return 2 + (max(level, 1) - 1) // 4


def slugify(text: str) -> str:
    """Lowercase, hyphen separated ASCII slug (``"Crossbow, Hand"`` -> ``crossbow-hand``)."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def roll(dice: str, bonus: int = 0) -> str:
    """Tableplop roll expression, e.g. ``{1d8 + 3}``."""
    if bonus > 0:
        return f"{{{dice} + {bonus}}}"
    if bonus < 0:
        return f"{{{dice} - {-bonus}}}"
    return f"{{{dice}}}"


def _plus_constant(formula: str, bonus: int) -> str:
    if bonus > 0:
        return f"{formula} + {bonus}"
    if bonus < 0:
        return f"{formula} - {-bonus}"
    return formula


def message_text(text: Any) -> str:
    """
    Makes user-provided text safe inside a Tableplop chat message: braces would be
    read as rolls, ``@:`` as substitutions and a leading ``!`` as a command.
    """
    cleaned = re.sub(r"[{}]", "", str(text or "")).replace("@:", "@ :")
    return cleaned.lstrip("!").strip()


def html_paragraphs(sections: Iterable[Tuple[str, Any]]) -> str:
    """Builds the HTML ``value`` of a paragraph from (label, text) pairs, escaped."""
    parts: List[str] = []
    for label, text in sections:
        if text is None or str(text).strip() == "":
            continue
        body = html.escape(str(text).strip(), quote=False)
        body = body.replace("\r\n", "\n").replace("\n", "<br>")
        if label:
            parts.append(
                f"<p><strong>{html.escape(label, quote=False)}:</strong> {body}</p>"
            )
        else:
            parts.append(f"<p>{body}</p>")
    return "".join(parts) or "<p>&nbsp;</p>"


def _num(value: Any) -> int:
    """Returns ``value`` as int, treating ``None`` and junk as 0."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _mod_value(mod: Dict[str, Any]) -> int:
    value = mod.get("value")
    if value is None:
        value = mod.get("fixedValue")
    return _num(value)


# --------------------------------------------------------------------------------------
# Character computations
# --------------------------------------------------------------------------------------


def character_name(data: Dict[str, Any]) -> str:
    """
    Character name, falling back to ``"Character"``. D&D Beyond's default name is
    ``"<username>'s Character"``; that is replaced so the username never leaks.
    """
    name = str(data.get("name") or "").strip()
    username = str(data.get("username") or "").strip()
    if not name or (
        username and re.search(rf"\b{re.escape(username)}\b", name, re.IGNORECASE)
    ):
        return "Character"
    return name


def total_level(data: Dict[str, Any]) -> int:
    """Sum of all class levels (at least 1)."""
    return max(1, sum(_num(c.get("level")) for c in data.get("classes") or []))


def _equipped_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        item
        for item in data.get("inventory") or []
        if item.get("equipped") and isinstance(item.get("definition"), dict)
    ]


def active_modifiers(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    All modifiers that currently apply. D&D Beyond lists the modifiers of every
    inventory item in ``modifiers.item``, equipped or not, so item modifiers are kept
    only when an item with that definition id is equipped, and attuned when the
    modifier requires attunement.
    """
    modifiers = data.get("modifiers") or {}
    result: List[Dict[str, Any]] = []
    for source, mods in modifiers.items():
        if source != "item":
            result.extend(m for m in mods or [] if isinstance(m, dict))

    equipped: Set[int] = set()
    attuned: Set[int] = set()
    for item in _equipped_items(data):
        definition_id = item["definition"].get("id")
        equipped.add(definition_id)
        if item.get("isAttuned"):
            attuned.add(definition_id)
    for mod in modifiers.get("item") or []:
        component = mod.get("componentId")
        if component not in equipped:
            continue
        if mod.get("requiresAttunement") and component not in attuned:
            continue
        result.append(mod)
    return result


def _sum(mods: List[Dict[str, Any]], mod_type: str, sub_type: str) -> int:
    return sum(
        _mod_value(m)
        for m in mods
        if m.get("type") == mod_type and m.get("subType") == sub_type
    )


def _has(mods: List[Dict[str, Any]], mod_type: str, sub_type: str) -> bool:
    return any(m.get("type") == mod_type and m.get("subType") == sub_type for m in mods)


def _max_set(mods: List[Dict[str, Any]], mod_type: str, sub_type: str) -> Optional[int]:
    values = [
        _mod_value(m)
        for m in mods
        if m.get("type") == mod_type and m.get("subType") == sub_type
    ]
    return max(values) if values else None


def ability_scores(
    data: Dict[str, Any], mods: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, int]:
    """
    Final ability scores: override if set, else base + manual bonus + ``bonus``
    modifiers, raised to any ``set`` modifier (e.g. an item that sets CHA to 20).
    """
    if mods is None:
        mods = active_modifiers(data)

    def by_id(key: str) -> Dict[int, Any]:
        return {s.get("id"): s.get("value") for s in data.get(key) or []}

    base, bonus, override = by_id("stats"), by_id("bonusStats"), by_id("overrideStats")
    scores: Dict[str, int] = {}
    for stat_id, name, _ in ABILITIES:
        if override.get(stat_id) is not None:
            scores[name] = _num(override[stat_id])
            continue
        score = base.get(stat_id)
        score = 10 if score is None else _num(score)
        score += _num(bonus.get(stat_id)) + _sum(mods, "bonus", f"{name}-score")
        set_to = _max_set(mods, "set", f"{name}-score")
        if set_to is not None:
            score = max(score, set_to)
        scores[name] = score
    return scores


def max_hit_points(
    data: Dict[str, Any], con_mod: int, mods: List[Dict[str, Any]]
) -> int:
    """
    Maximum HP: ``overrideHitPoints`` if set, else base (hit dice) + manual bonus +
    CON modifier per level + ``hit-points-per-level`` bonuses per level.
    """
    if data.get("overrideHitPoints") is not None:
        return _num(data["overrideHitPoints"])
    level = total_level(data)
    per_level = _sum(mods, "bonus", "hit-points-per-level")
    return max(
        1,
        _num(data.get("baseHitPoints"))
        + _num(data.get("bonusHitPoints"))
        + (con_mod + per_level) * level,
    )


def _class_names(data: Dict[str, Any]) -> Set[str]:
    return {
        (c.get("definition") or {}).get("name", "") for c in data.get("classes") or []
    }


def _subclass_names(data: Dict[str, Any]) -> List[str]:
    return [
        (c.get("subclassDefinition") or {}).get("name") or ""
        for c in data.get("classes") or []
    ]


def _worn_armor(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Returns the (armor, shield) definitions that are equipped, if any."""
    armor = shield = None
    for item in _equipped_items(data):
        definition = item["definition"]
        if definition.get("filterType") != "Armor":
            continue
        armor_type = definition.get("armorTypeId")
        if armor_type == ARMOR_SHIELD:
            if shield is None or _num(definition.get("armorClass")) > _num(
                shield.get("armorClass")
            ):
                shield = definition
        elif armor_type in (ARMOR_LIGHT, ARMOR_MEDIUM, ARMOR_HEAVY):
            if armor is None or _num(definition.get("armorClass")) > _num(
                armor.get("armorClass")
            ):
                armor = definition
    return armor, shield


def armor_class(
    data: Dict[str, Any], scores: Dict[str, int], mods: List[Dict[str, Any]]
) -> int:
    """
    Armor class from worn armor (light: + DEX, medium: + DEX up to 2, heavy: flat),
    or unarmored (10 + DEX, Barbarian + CON, Monk + WIS without shield, Draconic
    sorcerer 13 + DEX), plus shield and active ``armor-class`` bonuses.
    """
    dex = modifier(scores["dexterity"])
    armor, shield = _worn_armor(data)
    if armor is not None:
        base = _num(armor.get("armorClass"))
        armor_type = armor.get("armorTypeId")
        if armor_type == ARMOR_LIGHT:
            base += dex
        elif armor_type == ARMOR_MEDIUM:
            base += min(dex, 2)
        bonus = _sum(mods, "bonus", "armored-armor-class")
    else:
        options = [10 + dex]
        classes = _class_names(data)
        if "Barbarian" in classes:
            options.append(10 + dex + modifier(scores["constitution"]))
        if "Monk" in classes and shield is None:
            options.append(10 + dex + modifier(scores["wisdom"]))
        if any("Draconic" in name for name in _subclass_names(data)):
            options.append(13 + dex)
        base = max(options)
        bonus = _sum(mods, "bonus", "unarmored-armor-class")
    if shield is not None:
        base += _num(shield.get("armorClass"))
    return base + bonus + _sum(mods, "bonus", "armor-class")


def speeds(
    data: Dict[str, Any], scores: Dict[str, int], mods: List[Dict[str, Any]]
) -> Dict[str, int]:
    """
    Movement speeds in feet. Walking speed comes from the race plus ``bonus`` speed
    modifiers, raised to ``set`` modifiers, minus 10 for heavy armor worn without the
    required Strength. Other speeds (fly, swim, climb, burrow) only when non-zero.
    """
    race_speeds = ((data.get("race") or {}).get("weightSpeeds") or {}).get(
        "normal"
    ) or {}
    armor, _ = _worn_armor(data)
    result: Dict[str, int] = {}
    for key, sub in (
        ("walk", "walking"),
        ("fly", "flying"),
        ("swim", "swimming"),
        ("climb", "climbing"),
        ("burrow", "burrowing"),
    ):
        speed = _num(race_speeds.get(key))
        if key == "walk":
            speed = speed or 30
            speed += _sum(mods, "bonus", "speed") + _sum(mods, "bonus", "speed-walking")
            if armor is None:
                speed += _sum(mods, "bonus", "unarmored-movement")
        for mod_type in ("set", "set-base"):
            for sub_type in (f"speed-{sub}", f"innate-speed-{sub}"):
                set_to = _max_set(mods, mod_type, sub_type)
                if set_to is not None:
                    speed = max(speed, set_to)
        if (
            key == "walk"
            and armor is not None
            and armor.get("armorTypeId") == ARMOR_HEAVY
            and scores["strength"] < _num(armor.get("strengthRequirement"))
            and not _has(mods, "ignore", "heavy-armor-speed-reduction")
        ):
            speed -= 10
        if key == "walk" or speed > 0:
            result[key] = max(speed, 0)
    return result


def initiative_bonus(
    dex_mod: int, prof: int, mods: List[Dict[str, Any]]
) -> Tuple[int, int]:
    """Returns (total initiative, part of it that is not the DEX modifier)."""
    extra = _sum(mods, "bonus", "initiative")
    if _has(mods, "half-proficiency", "initiative") or _has(
        mods, "half-proficiency", "ability-checks"
    ):
        extra += prof // 2
    return dex_mod + extra, extra


@dataclass
class SpellSlotLevel:
    """Spell slots of one spell level."""

    level: int
    maximum: int
    used: int


@dataclass
class SpellSlots:
    """Regular spell slots and Warlock pact-magic slots."""

    regular: List[SpellSlotLevel] = field(default_factory=list)
    pact: List[SpellSlotLevel] = field(default_factory=list)


def _spell_rules(class_entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Spell rules of a class entry if it casts spells (through class or subclass)."""
    definition = class_entry.get("definition") or {}
    subclass = class_entry.get("subclassDefinition") or {}
    if definition.get("canCastSpells") and definition.get("spellRules"):
        return definition["spellRules"]
    if subclass.get("canCastSpells") and subclass.get("spellRules"):
        return subclass["spellRules"]
    return None


def _table_row(rules: Dict[str, Any], level: int) -> List[int]:
    table = rules.get("levelSpellSlots") or []
    if 0 <= level < len(table) and table[level]:
        return [_num(n) for n in table[level]][:9] + [0] * max(0, 9 - len(table[level]))
    return [0] * 9


def spell_slots(data: Dict[str, Any]) -> SpellSlots:
    """
    Spell-slot maxima from ``spellRules.levelSpellSlots`` (``spellSlots[].available``
    is always 0 in the API). With two or more spellcasting classes the 5e multiclass
    rule applies: each class adds ``level / multiClassSpellSlotDivisor`` (rounded down,
    or up when ``multiClassSpellSlotRounding`` is 2) to a caster level looked up in the
    full-caster table. Warlock pact magic is kept separate.
    """
    regular_casters: List[Tuple[Dict[str, Any], int]] = []
    pact_row = [0] * 9
    for class_entry in data.get("classes") or []:
        rules = _spell_rules(class_entry)
        if rules is None:
            continue
        level = _num(class_entry.get("level"))
        name = (class_entry.get("definition") or {}).get("name")
        if name in PACT_MAGIC_CLASSES:
            pact_row = _table_row(rules, level)
        else:
            regular_casters.append((rules, level))

    if len(regular_casters) == 1:
        rules, level = regular_casters[0]
        row = _table_row(rules, level)
    elif regular_casters:
        caster_level = 0
        for rules, level in regular_casters:
            divisor = _num(rules.get("multiClassSpellSlotDivisor")) or 1
            rounding = ceil if rules.get("multiClassSpellSlotRounding") == 2 else floor
            caster_level += rounding(level / divisor)
        row = FULL_CASTER_SLOTS[min(caster_level, 20)]
    else:
        row = [0] * 9

    def used(key: str, index: int) -> int:
        entries = data.get(key) or []
        for entry in entries:
            if _num(entry.get("level")) == index + 1:
                return _num(entry.get("used"))
        return 0

    slots = SpellSlots()
    for index, maximum in enumerate(row):
        if maximum > 0:
            slots.regular.append(
                SpellSlotLevel(
                    index + 1, maximum, min(used("spellSlots", index), maximum)
                )
            )
    for index, maximum in enumerate(pact_row):
        if maximum > 0:
            slots.pact.append(
                SpellSlotLevel(
                    index + 1, maximum, min(used("pactMagic", index), maximum)
                )
            )
    return slots


@dataclass
class Attack:
    """A weapon attack with precomputed numbers."""

    name: str
    to_hit: int
    damage_dice: str
    damage_bonus: int
    damage_type: str
    versatile_dice: Optional[str] = None
    notes: str = ""


def _weapon_proficient(definition: Dict[str, Any], mods: List[Dict[str, Any]]) -> bool:
    proficiencies = {m.get("subType") for m in mods if m.get("type") == "proficiency"}
    candidates = {
        slugify(definition.get("type") or ""),
        slugify(definition.get("name") or ""),
    }
    category = definition.get("categoryId")
    if category == 1:
        candidates.add("simple-weapons")
    elif category == 2:
        candidates.add("martial-weapons")
    properties = {p.get("name") for p in definition.get("properties") or []}
    if properties & FIREARM_PROPERTIES:
        candidates.add("firearms")
    return bool(candidates & proficiencies)


def weapon_attacks(
    data: Dict[str, Any], scores: Dict[str, int], prof: int, mods: List[Dict[str, Any]]
) -> List[Attack]:
    """
    Attacks for equipped weapons (and the unarmed strike when D&D Beyond shows it).
    To hit = ability modifier (STR melee, DEX ranged, the better one for Finesse) +
    proficiency if proficient + the weapon's magic bonus + attack bonus modifiers.
    Damage = weapon dice + the same ability modifier + magic bonus.
    """
    str_mod = modifier(scores["strength"])
    dex_mod = modifier(scores["dexterity"])
    generic_bonus = _sum(mods, "bonus", "weapon-attacks")
    attacks: List[Attack] = []
    seen: Set[str] = set()
    for item in _equipped_items(data):
        definition = item["definition"]
        damage = definition.get("damage") or {}
        if definition.get("filterType") != "Weapon" or not damage.get("diceString"):
            continue
        name = str(definition.get("name") or "Weapon")
        if name in seen:
            continue
        seen.add(name)
        properties = {
            p.get("name"): p.get("notes") for p in definition.get("properties") or []
        }
        ranged = definition.get("attackType") == 2
        ability_mod = dex_mod if ranged else str_mod
        if "Finesse" in properties:
            ability_mod = max(str_mod, dex_mod)
        magic = sum(
            _mod_value(m)
            for m in definition.get("grantedModifiers") or []
            if m.get("type") == "bonus"
            and m.get("subType") == "magic"
            and (not m.get("requiresAttunement") or item.get("isAttuned"))
        )
        kind_bonus = _sum(
            mods, "bonus", "ranged-weapon-attacks" if ranged else "melee-weapon-attacks"
        )
        to_hit = (
            ability_mod
            + (prof if _weapon_proficient(definition, mods) else 0)
            + magic
            + generic_bonus
            + kind_bonus
        )
        if ranged:
            notes = f"Ranged {_num(definition.get('range'))}/{_num(definition.get('longRange'))} ft."
        else:
            reach = 10 if "Reach" in properties else 5
            notes = f"Melee {reach} ft."
            if "Thrown" in properties:
                notes += f" Thrown {_num(definition.get('range'))}/{_num(definition.get('longRange'))} ft."
        if properties:
            notes += " " + ", ".join(sorted(properties)) + "."
        versatile = properties.get("Versatile")
        attacks.append(
            Attack(
                name=name,
                to_hit=to_hit,
                damage_dice=str(damage["diceString"]),
                damage_bonus=ability_mod + magic,
                damage_type=str(definition.get("damageType") or "").lower(),
                versatile_dice=str(versatile) if versatile else None,
                notes=notes,
            )
        )
    if (data.get("preferences") or {}).get("showUnarmedStrike"):
        attacks.append(
            Attack(
                name="Unarmed Strike",
                to_hit=str_mod
                + prof
                + generic_bonus
                + _sum(mods, "bonus", "melee-weapon-attacks"),
                damage_dice="",
                damage_bonus=max(1 + str_mod, 0),
                damage_type="bludgeoning",
                notes="Melee 5 ft.",
            )
        )
    return attacks


@dataclass
class Spell:
    """A spell the character can cast, with its casting numbers."""

    name: str
    level: int
    description: str
    save_dc: int
    attack_bonus: int


def _spell_ability(
    spell: Dict[str, Any], class_ability: Optional[int], scores: Dict[str, int]
) -> str:
    ability_id = spell.get("spellCastingAbilityId") or class_ability
    if ability_id in ABILITY_BY_ID:
        return ABILITY_BY_ID[ability_id]
    # No casting ability given (e.g. a cantrip from a feature): use the best mental stat.
    return max(("intelligence", "wisdom", "charisma"), key=lambda a: scores[a])


def spellcasting_ability(data: Dict[str, Any]) -> Optional[str]:
    """Casting ability of the highest-level spellcasting class, if any."""
    casters = [c for c in data.get("classes") or [] if _spell_rules(c) is not None]
    if not casters:
        return None
    best = max(casters, key=lambda c: _num(c.get("level")))
    ability_id = (best.get("definition") or {}).get("spellCastingAbilityId") or (
        best.get("subclassDefinition") or {}
    ).get("spellCastingAbilityId")
    return ABILITY_BY_ID.get(ability_id)


def _describe_spell(
    definition: Dict[str, Any],
    ability_mod: int,
    save_dc: int,
    attack_bonus: int,
    level: int,
) -> str:
    spell_level = _num(definition.get("level"))
    school = str(definition.get("school") or "").lower()
    head = "cantrip" if spell_level == 0 else f"level {spell_level}"
    parts = [f"{head} {school}".strip()]

    activation = definition.get("activation") or {}
    activation_name = ACTIVATION_TYPES.get(activation.get("activationType"))
    if activation_name:
        count = _num(activation.get("activationTime")) or 1
        parts.append(
            f"{count} {activation_name}" if count > 1 else f"1 {activation_name}"
        )

    spell_range = definition.get("range") or {}
    origin = spell_range.get("origin")
    if origin == "Ranged":
        parts.append(f"range {_num(spell_range.get('rangeValue'))} ft")
    elif origin:
        parts.append(f"range {str(origin).lower()}")

    duration = definition.get("duration") or {}
    if duration.get("durationType") == "Instantaneous":
        parts.append("instantaneous")
    elif duration.get("durationUnit"):
        prefix = "concentration, " if definition.get("concentration") else ""
        interval = _num(duration.get("durationInterval"))
        unit = str(duration["durationUnit"]).lower() + ("s" if interval > 1 else "")
        parts.append(f"{prefix}{interval} {unit}")
    components = "".join(
        {1: "V", 2: "S", 3: "M"}.get(c, "") for c in definition.get("components") or []
    )
    if components:
        parts.append(components)
    if definition.get("ritual"):
        parts.append("ritual")
    text = ", ".join(parts) + "."

    if definition.get("requiresAttackRoll"):
        text += f" {roll('1d20', attack_bonus)} to hit."
    save_ability = ABILITY_BY_ID.get(definition.get("saveDcAbilityId"))
    if definition.get("requiresSavingThrow") and save_ability:
        text += f" {save_ability[:3].upper()} save DC {save_dc}."

    # Damage dice, scaled for cantrips at character levels 5, 11 and 17.
    scale = 1
    if spell_level == 0 and definition.get("scaleType") == "characterlevel":
        scale = 1 + (level >= 5) + (level >= 11) + (level >= 17)
    for mod in definition.get("modifiers") or []:
        die = mod.get("die") or {}
        count, value = die.get("diceCount"), die.get("diceValue")
        if not count or not value:
            continue
        dice = f"{_num(count) * scale}d{_num(value)}"
        bonus = _num(die.get("fixedValue")) + (
            ability_mod if mod.get("usePrimaryStat") else 0
        )
        if mod.get("type") == "damage":
            text += f" Damage {roll(dice, bonus)} {message_text(mod.get('subType'))}."
        elif mod.get("type") == "bonus" and mod.get("subType") == "hit-points":
            text += f" Healing {roll(dice, bonus)}."
    return text


def spell_list(
    data: Dict[str, Any], scores: Dict[str, int], prof: int, mods: List[Dict[str, Any]]
) -> List[Spell]:
    """
    Castable spells: every cantrip, prepared and always-prepared spells, all known
    spells of known-spell casters (Bard, Sorcerer, Warlock, Ranger), and every spell
    granted by race, background, items or feats. Sorted by level then name.
    """
    level = total_level(data)
    classes_by_id = {c.get("id"): c for c in data.get("classes") or []}
    dc_bonus = _sum(mods, "bonus", "spell-save-dc")
    attack_extra = _sum(mods, "bonus", "spell-attacks")
    entries: List[Tuple[Dict[str, Any], Optional[int], bool]] = []
    for class_spells in data.get("classSpells") or []:
        class_entry = classes_by_id.get(class_spells.get("characterClassId")) or {}
        class_def = class_entry.get("definition") or {}
        ability_id = class_def.get("spellCastingAbilityId") or (
            class_entry.get("subclassDefinition") or {}
        ).get("spellCastingAbilityId")
        knows_all = class_def.get("name") in KNOWN_SPELL_CASTERS
        for spell in class_spells.get("spells") or []:
            entries.append((spell, ability_id, knows_all))
    for spells in (data.get("spells") or {}).values():
        for spell in spells or []:
            entries.append((spell, None, True))

    result: List[Spell] = []
    seen: Set[str] = set()
    for spell, ability_id, knows_all in entries:
        definition = spell.get("definition") or {}
        name = str(definition.get("name") or "").strip()
        spell_level = _num(definition.get("level"))
        if not name or name in seen:
            continue
        available = (
            spell_level == 0
            or knows_all
            or spell.get("prepared")
            or spell.get("alwaysPrepared")
        )
        if not available:
            continue
        seen.add(name)
        ability = _spell_ability(spell, ability_id, scores)
        ability_mod = modifier(scores[ability])
        save_dc = 8 + prof + ability_mod + dc_bonus
        if spell.get("overrideSaveDc"):
            save_dc = _num(spell["overrideSaveDc"])
        attack_bonus = prof + ability_mod + attack_extra
        result.append(
            Spell(
                name=name,
                level=spell_level,
                description=_describe_spell(
                    definition, ability_mod, save_dc, attack_bonus, level
                ),
                save_dc=save_dc,
                attack_bonus=attack_bonus,
            )
        )
    result.sort(key=lambda s: (s.level, s.name))
    return result


def class_summary(data: Dict[str, Any]) -> str:
    """``"Bard (College of Eloquence) 6"``, multiclass joined with ``" / "``."""
    parts = []
    for class_entry in data.get("classes") or []:
        name = (class_entry.get("definition") or {}).get("name") or "Class"
        subclass = (class_entry.get("subclassDefinition") or {}).get("name")
        label = f"{name} ({subclass})" if subclass else name
        parts.append(f"{label} {_num(class_entry.get('level'))}")
    return " / ".join(parts)


def background_name(data: Dict[str, Any]) -> str:
    """Background name, standard or custom."""
    background = data.get("background") or {}
    if background.get("hasCustomBackground"):
        return str((background.get("customBackground") or {}).get("name") or "")
    return str((background.get("definition") or {}).get("name") or "")


def _feature_lines(
    data: Dict[str, Any], scores: Dict[str, int], prof: int
) -> List[Tuple[str, str]]:
    lines: List[Tuple[str, str]] = []
    seen: Set[str] = set()
    for actions in (data.get("actions") or {}).values():
        for action in actions or []:
            name = str(action.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            detail = ""
            limited = action.get("limitedUse") or {}
            uses = _num(limited.get("maxUses"))
            stat = ABILITY_BY_ID.get(limited.get("statModifierUsesId"))
            if stat:
                uses += max(modifier(scores[stat]), 1)
            if limited.get("useProficiencyBonus"):
                uses += prof
            if uses > 0:
                reset = RESET_TYPES.get(limited.get("resetType"))
                detail = f"{uses} use{'s' if uses != 1 else ''}"
                detail += f" per {reset}" if reset else ""
            lines.append((name, detail))
    feats = [
        str((f.get("definition") or {}).get("name") or "")
        for f in data.get("feats") or []
    ]
    feats = [f for f in feats if f]
    if feats:
        lines.append(("Feats", ", ".join(feats)))
    return lines


# --------------------------------------------------------------------------------------
# Tableplop output
# --------------------------------------------------------------------------------------


class SheetBuilder:
    """Collects Tableplop properties with unique ids and per-parent ranks."""

    def __init__(self, character_id: int = 1) -> None:
        self.character_id = character_id
        self.properties: List[Dict[str, Any]] = []
        self._next_id = 1
        self._ranks: Dict[Optional[int], int] = defaultdict(int)
        self._names: Set[str] = set()

    def unique_name(self, base: str) -> str:
        """Returns ``base`` or ``base-2``, ``base-3``... so names stay unique."""
        name, counter = base, 2
        while name in self._names:
            name = f"{base}-{counter}"
            counter += 1
        return name

    def add(
        self,
        parent: Optional[int],
        prop_type: str,
        value: Any = "",
        name: Optional[str] = None,
        formula: Optional[str] = None,
        message: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        **extra: Any,
    ) -> int:
        """Adds a property and returns its id."""
        prop_id = self._next_id
        self._next_id += 1
        prop: Dict[str, Any] = {
            "id": prop_id,
            "parentId": parent,
            "type": prop_type,
            "data": data if data is not None else {},
        }
        if name is not None:
            if name in self._names:
                raise ValueError(f"Duplicate property name: {name}")
            self._names.add(name)
            prop["name"] = name
        prop["value"] = value
        prop["rank"] = self._ranks[parent]
        self._ranks[parent] += 1
        if formula is not None:
            prop["formula"] = formula
        if message is not None:
            prop["message"] = message
        prop.update(extra)
        prop["characterId"] = self.character_id
        self.properties.append(prop)
        return prop_id

    def result(self) -> Dict[str, Any]:
        """The complete Tableplop file as a dict."""
        return {"properties": self.properties, "private": False, "type": TABLEPLOP_TYPE}


def _add_slots(
    sheet: SheetBuilder,
    parent: int,
    prefix: str,
    label: str,
    slots: List[SpellSlotLevel],
) -> None:
    for slot in slots:
        level_name = f"{prefix}-slots-level-{slot.level}"
        sheet.add(parent, "text", f"{label} level {slot.level}")
        sheet.add(parent, "number", slot.maximum, name=level_name)
        used_id = sheet.add(
            parent,
            "checkboxes",
            slot.used or "",
            name=f"{prefix}-slots-used-{slot.level}",
        )
        sheet.add(
            used_id,
            "number",
            slot.maximum,
            name=f"{prefix}-slots-used-{slot.level}-max",
            formula=level_name,
        )


def convert(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a D&D Beyond character (the ``data`` object of the v5 response) into a
    Tableplop ``tableplop-character-v2`` dictionary, ready for ``json.dumps``.
    """
    mods = active_modifiers(data)
    scores = ability_scores(data, mods)
    ability_mods = {name: modifier(score) for name, score in scores.items()}
    level = total_level(data)
    prof = proficiency_bonus(level)
    sheet = SheetBuilder()

    # ---- Character tab ---------------------------------------------------------------
    tab = sheet.add(None, "tab-section", "Character")
    row = sheet.add(tab, "horizontal-section")
    left = sheet.add(row, "section", size=65)
    right = sheet.add(row, "section", size=35)

    abilities = sheet.add(left, "title-section", "Abilities")
    for _, name, _ in ABILITIES:
        ability_id = sheet.add(
            abilities,
            "ability",
            ability_mods[name],
            name=name,
            formula=f"floor (({name}-score - 10) / 2)",
            message=f"{name} check: {{1d20 + {name}}}",
        )
        sheet.add(ability_id, "number", scores[name], name=f"{name}-score")

    con_mod = ability_mods["constitution"]
    hp_max = max_hit_points(data, con_mod, mods)
    hp_current = max(hp_max - _num(data.get("removedHitPoints")), 0)
    temp_hp = _num(data.get("temporaryHitPoints"))
    health = sheet.add(left, "health", hp_current, name="hit-points")
    sheet.add(health, "number", hp_max, name="hit-points-maximum")
    sheet.add(health, "number", temp_hp or "", name="hit-points-temporary")

    info = sheet.add(left, "title-section", "Info")
    sheet.add(info, "text", character_name(data), name="character-name")
    sheet.add(info, "text", class_summary(data), name="class")
    sheet.add(
        info, "text", str((data.get("race") or {}).get("fullName") or ""), name="race"
    )
    sheet.add(info, "text", background_name(data), name="background")
    sheet.add(info, "number", level, name="level")
    sheet.add(info, "number", _num(data.get("currentXp")), name="experience")
    sheet.add(info, "number", prof, name="proficiency", formula=PROFICIENCY_FORMULA)
    sheet.add(info, "number", armor_class(data, scores, mods), name="armor-class")
    initiative, initiative_extra = initiative_bonus(
        ability_mods["dexterity"], prof, mods
    )
    sheet.add(
        info,
        "number",
        initiative,
        name="initiative",
        formula=_plus_constant("dexterity", initiative_extra),
        message="!r initiative = 1d20 + initiative",
    )
    speed = speeds(data, scores, mods)
    sheet.add(info, "number", speed["walk"], name="speed")
    other = [f"{kind} {feet} ft" for kind, feet in speed.items() if kind != "walk"]
    if other:
        sheet.add(info, "text", ", ".join(other), name="other-speeds")
    sheet.add(info, "checkbox", bool(data.get("inspiration")), name="inspiration")

    details = sheet.add(left, "title-section", "Details")
    traits = data.get("traits") or {}
    notes = data.get("notes") or {}
    sheet.add(
        details,
        "paragraph",
        name="details",
        value=html_paragraphs(
            [
                ("Personality traits", traits.get("personalityTraits")),
                ("Ideals", traits.get("ideals")),
                ("Bonds", traits.get("bonds")),
                ("Flaws", traits.get("flaws")),
                ("Appearance", traits.get("appearance")),
                ("Backstory", notes.get("backstory")),
                ("Allies", notes.get("allies")),
                ("Enemies", notes.get("enemies")),
                ("Organizations", notes.get("organizations")),
                ("Personal possessions", notes.get("personalPossessions")),
                ("Other holdings", notes.get("otherHoldings")),
                ("Other notes", notes.get("otherNotes")),
            ]
        ),
    )

    saves = sheet.add(right, "title-section", "Saving Throws")
    save_bonus = _sum(mods, "bonus", "saving-throws")
    for _, name, short in ABILITIES:
        proficient = _has(mods, "proficiency", f"{name}-saving-throws")
        bonus = save_bonus + _sum(mods, "bonus", f"{name}-saving-throws")
        save_id = sheet.add(
            saves,
            "saving-throw",
            ability_mods[name] + (prof if proficient else 0) + bonus,
            name=f"{name}-save",
            formula=_plus_constant(
                f"{name} + ({name}-save-proficiency ? proficiency : 0)", bonus
            ),
            message=f"{short.upper()} save: {{1d20 + {name}-save}}",
        )
        sheet.add(save_id, "checkbox", proficient, name=f"{name}-save-proficiency")

    senses = sheet.add(right, "title-section", "Senses")
    darkvision = _max_set(mods, "set-base", "darkvision")
    sheet.add(senses, "number", darkvision or "", name="dark-vision")

    skills = sheet.add(right, "title-section", "Skills")
    jack = _has(mods, "half-proficiency", "ability-checks")
    check_bonus = _sum(mods, "bonus", "ability-checks")
    skill_values: Dict[str, int] = {}
    for skill, ability in SKILLS.items():
        expertise = _has(mods, "expertise", skill)
        proficient = expertise or _has(mods, "proficiency", skill)
        bonus = check_bonus + _sum(mods, "bonus", skill)
        if proficient:
            prof_part = prof
        else:
            prof_part = prof // 2 if jack else 0
        value = ability_mods[ability] + prof_part + (prof if expertise else 0) + bonus
        skill_values[skill] = value
        formula = (
            f"{ability} + ({skill}-proficiency ? proficiency : jack-of-all-trades ? "
            f"(floor (proficiency / 2)) : 0) + ({skill}-expertise ? proficiency : 0)"
        )
        label = skill.replace("-", " ").capitalize()
        skill_id = sheet.add(
            skills,
            "skill",
            value,
            name=skill,
            formula=_plus_constant(formula, bonus),
            message=f"{label} check: {{1d20 + {skill}}}",
            data={"subtitle": ability[:3]},
        )
        sheet.add(skill_id, "checkbox", proficient, name=f"{skill}-proficiency")
        sheet.add(skill_id, "checkbox", expertise, name=f"{skill}-expertise")
    sheet.add(skills, "checkbox", jack, name="jack-of-all-trades")
    sheet.add(
        senses,
        "number",
        10 + skill_values["perception"],
        name="passive-perception",
        formula="10 + perception",
    )
    sheet.add(
        senses,
        "number",
        10 + skill_values["insight"],
        name="passive-insight",
        formula="10 + insight",
    )

    # ---- Combat tab ------------------------------------------------------------------
    combat = sheet.add(None, "tab-section", "Combat")
    attacks_section = sheet.add(combat, "title-section", "Attacks")
    attack_list = sheet.add(attacks_section, "filter-list")
    for attack in weapon_attacks(data, scores, prof, mods):
        label = message_text(attack.name)
        if attack.damage_dice:
            damage = roll(attack.damage_dice, attack.damage_bonus)
        else:
            damage = str(attack.damage_bonus)
        text = f"{label}: {roll('1d20', attack.to_hit)} to hit, {damage} {attack.damage_type}"
        if attack.versatile_dice:
            text += f" (two-handed {roll(attack.versatile_dice, attack.damage_bonus)})"
        text += f". {message_text(attack.notes)}"
        sheet.add(
            attack_list,
            "message",
            name=sheet.unique_name("attack-" + (slugify(attack.name) or "weapon")),
            message=text,
            icon=MESSAGE_ICON,
        )

    death = sheet.add(combat, "title-section", "Death Saves")
    death_saves = data.get("deathSaves") or {}
    for prop_name, key in (
        ("death-saves-made", "successCount"),
        ("death-saves-failed", "failCount"),
    ):
        count = _num(death_saves.get(key))
        boxes = sheet.add(death, "checkboxes", count or "", name=prop_name)
        sheet.add(boxes, "number", 3, name=f"{prop_name}-max")

    hit_dice = ", ".join(
        f"{_num(c.get('level'))}d{_num((c.get('definition') or {}).get('hitDice'))}"
        f" ({_num(c.get('hitDiceUsed'))} used)"
        for c in data.get("classes") or []
    )
    resources = sheet.add(combat, "title-section", "Resources")
    sheet.add(resources, "text", hit_dice, name="hit-dice")
    features = _feature_lines(data, scores, prof)
    if features:
        sheet.add(resources, "paragraph", html_paragraphs(features), name="features")

    # ---- Spells tab --------------------------------------------------------------------
    spells = spell_list(data, scores, prof, mods)
    slots = spell_slots(data)
    if spells or slots.regular or slots.pact:
        spell_tab = sheet.add(None, "tab-section", "Spells")
        casting = sheet.add(spell_tab, "title-section", "Spellcasting")
        ability = spellcasting_ability(data) or max(
            ("intelligence", "wisdom", "charisma"), key=lambda a: scores[a]
        )
        sheet.add(casting, "text", ability.capitalize(), name="spellcasting-ability")
        dc_bonus = _sum(mods, "bonus", "spell-save-dc")
        attack_extra = _sum(mods, "bonus", "spell-attacks")
        sheet.add(
            casting,
            "number",
            8 + prof + ability_mods[ability] + dc_bonus,
            name="spell-save-dc",
            formula=_plus_constant(f"8 + proficiency + {ability}", dc_bonus),
        )
        sheet.add(
            casting,
            "number",
            prof + ability_mods[ability] + attack_extra,
            name="spell-attack-bonus",
            formula=_plus_constant(f"proficiency + {ability}", attack_extra),
            message="Spell attack: {1d20 + spell-attack-bonus}",
        )
        if slots.regular:
            slot_section = sheet.add(spell_tab, "title-section", "Spell Slots")
            _add_slots(sheet, slot_section, "spell", "Spell slots", slots.regular)
        if slots.pact:
            pact_section = sheet.add(spell_tab, "title-section", "Pact Magic")
            _add_slots(sheet, pact_section, "pact", "Pact slots", slots.pact)
        if spells:
            spell_section = sheet.add(spell_tab, "title-section", "Spells")
            spell_filter = sheet.add(spell_section, "filter-list")
            for spell in spells:
                sheet.add(
                    spell_filter,
                    "message",
                    name=sheet.unique_name("spell-" + (slugify(spell.name) or "spell")),
                    message=f"{message_text(spell.name)}: {spell.description}",
                    icon=MESSAGE_ICON,
                )

    # ---- Inventory tab -----------------------------------------------------------------
    inventory_tab = sheet.add(None, "tab-section", "Inventory")
    currency = sheet.add(inventory_tab, "title-section", "Currency")
    coins = data.get("currencies") or {}
    for key, name in (
        ("pp", "platinum"),
        ("gp", "gold"),
        ("ep", "electrum"),
        ("sp", "silver"),
        ("cp", "copper"),
    ):
        sheet.add(currency, "number", _num(coins.get(key)), name=name)
    equipment = sheet.add(inventory_tab, "title-section", "Equipment")
    items: List[Tuple[str, str]] = []
    for item in data.get("inventory") or []:
        definition = item.get("definition") or {}
        flags = []
        if item.get("equipped"):
            flags.append("equipped")
        if item.get("isAttuned"):
            flags.append("attuned")
        line = f"{definition.get('name') or 'Item'} x{_num(item.get('quantity'))}"
        if flags:
            line += f" ({', '.join(flags)})"
        items.append(("", line))
    for item in data.get("customItems") or []:
        items.append(
            ("", f"{item.get('name') or 'Item'} x{_num(item.get('quantity')) or 1}")
        )
    sheet.add(equipment, "paragraph", html_paragraphs(items), name="equipment")

    return sheet.result()


def output_filename(name: str) -> str:
    """File name for the converted sheet, e.g. ``leslie_device_tableplop.json``."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:50].strip("_")
    return f"{slug or 'character'}_tableplop.json"


def main(argv: Optional[List[str]] = None) -> int:
    """
    Command-line use without the bot: ``python DDComp/tableplop.py <url>`` writes
    ``<character-name>_tableplop.json`` to the current directory. Returns the exit code.
    """
    args = sys.argv[1:] if argv is None else argv
    character_id = parse_character_url(args[0]) if len(args) == 1 else None
    if character_id is None:
        print("Usage: python DDComp/tableplop.py <D&D Beyond character URL>")
        return 2
    try:
        data = asyncio.run(fetch_character(character_id))
    except CharacterPrivateError:
        print("This character is private. Set its privacy to Public on D&D Beyond.")
        return 1
    except CharacterNotFoundError:
        print("D&D Beyond has no character with this id.")
        return 1
    except DDBError as error:
        print(f"Could not get the character from D&D Beyond: {error}")
        return 1
    filename = output_filename(character_name(data))
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(convert(data), file, ensure_ascii=False, indent=1)
    print(f"Wrote {filename}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
