# Format research: Tableplop character JSON and D&D Beyond character JSON

Research date: 2026-11-11. Purpose: let a later session write the `/to_tableplop <url>` converter without redoing research.

## Headline status (read first)

- **Tableplop schema: VERIFIED from real Tableplop exports, but not from an official spec and not from a file the owner exported themself.** Tableplop has no public schema documentation that I could find. The evidence is three real `"type": "tableplop-character-v2"` files published by community members (saved in `docs/samples/`). Every field and type listed in Part 1 appears in those files. Whether Tableplop's *current* import still accepts exactly this shape was **not tested** (no Tableplop account was used). **Recommended gap-filler: the owner exports one character from Tableplop and diffs it against these samples** (Part 4 lists what to look for).
- **D&D Beyond endpoint: VERIFIED live on 2026-11-11** with real public characters. The version in the URL matters: `v5` works, `v3` and `v4` now return `UnsupportedApiVersion`.
- A well-known community converter (Apollonaut13/ddb-to-tableplop-character) emits an **older v1 shape** (`stats`/`info`/`sections`) and calls DDB `v3`. It is **outdated on both ends** and must not be used as a format reference, only as a source of ideas for the DDB maths.

Legend used below: **[V: source]** = verified from that source; **[A]** = assumed / inferred / from memory, not confirmed.

Sources (all fetched 2026-11-11):
- S1 `docs/samples/tableplop_5e_corym_v2.json` = https://github.com/rso2021/TableplopCharacterSheets/blob/main/CharacterSheets/DND5e_Generic_V02_001.json (GPL-3.0 repo; 284 properties, a full 5e sheet)
- S2 `docs/samples/tableplop_spygame_5e_v2.json` = https://github.com/Kickball/tableplop-templates/blob/main/The%20Spy%20Game.json (5e, "Tableplop Version Tested 14.4.0" per README; smaller and cleaner; no licence file in repo, so treat as reference only)
- S3 https://github.com/Kickball/tableplop-templates/blob/main/Index%20Card%20RPG%20v3%20-%20Player.json (ICRPG; README: tested on Tableplop 17.1.0; NOT saved in samples, used only to cross-check types, e.g. `table`, `heading`)
- S4 https://github.com/rso2021/TableplopCharacterSheets README: "V01 files ... no longer used. V02 files are for the new JSON specification."
- S5 https://github.com/Apollonaut13/ddb-to-tableplop-character/blob/main/ddbCharacter_to_tableplop.py (v1-format output, DDB v3, outdated)
- S6 https://github.com/Apollonaut13/tableplopMonsterJSONConverter README (import UI steps)
- D1 `docs/samples/ddb_character_41000137_bard6_trimmed.json` (live fetch of public character 41000137, Bard 6, spells, manual HP)
- D2 `docs/samples/ddb_character_20600137_fighter12_trimmed.json` (live fetch of public character 20600137, Fighter 12, fixed HP, magic items, 3 feats)
- D3 live fetch of public character 50000000 (a near-empty level-1 character; not saved; used for the minimal-shape check)

The DDB samples are third-party public characters; `userId`, `username`, and avatar/decoration URLs were removed and long description strings and source/art fields were trimmed. Structure and all numeric/rules fields are untouched.

---

## Part 1. Tableplop character import format

### 1.1 How the user imports (UI)

- **[V: S6]** Campaign "Characters" tab -> "New Character" -> "Import" -> pick the `.json` file -> confirm the pop-up -> rename the character if wanted. Alternative path: in a scene, right-click the map -> New Token -> Character -> New Character -> name it -> Create; then in the character menu at the bottom left, scroll past "5e SRD" and "Custom" to "Import", pick the file, confirm.
- **[A]** Importing replaces the content of the newly created character (the DDB-PDF converter at https://github.com/sonofwau/dndbeyond_to_json says an import overwrites an existing character; that was a search-result summary, not opened).
- **[A]** The browser file picker accepts a plain `.json` file. File name is irrelevant. UTF-8 encoding, which is what all samples use. The exact accepted MIME type/size limit are unknown.

### 1.2 Top-level shape

**[V: S1, S2, S3]** The file is one JSON object with exactly three keys:

```json
{
  "properties": [ /* flat list of property objects */ ],
  "private": false,
  "type": "tableplop-character-v2"
}
```

(S2 additionally has a fourth key `"appearance": null`; S1 and S3 have only the three keys above **[V]**. Treat `appearance` as optional; **[A]** omit it.)

- `type` is a fixed marker string `"tableplop-character-v2"` **[V: S1,S2,S3]**. This is how v2 is told apart from the old v1 shape (`{"stats":{...},"info":{...},"appearances":{},"savedMessages":[]}`, seen in https://github.com/Kickball/tableplop-templates/blob/main/Cyberpunk%20Red.json **[V]**, "no longer used" per S4).
- `private` (bool) = whether the sheet is hidden from players **[A: name only; always `false` in the samples]**.
- The sheet is a **flat array of properties forming a tree via `parentId`**. There is no nesting in the JSON itself.

### 1.3 Property (widget) entry

Every element of `properties`. **[V: S1, S2, S3]** key sets observed (the union below; no other keys appear in any of the 570+ entries):

| key | type | present on | meaning |
|---|---|---|---|
| `id` | integer | all | Unique within the file. Samples use large sequential-ish ints (e.g. 602960..603239, 685768..686566). Ids are unique **[V]**. Whether Tableplop remaps ids on import is **not confirmed [A: it does, since each export carries the source `characterId`]**; to be safe generate unique ints and keep references consistent. |
| `parentId` | integer or `null` | all | `null` for the top-level nodes (tabs); else the `id` of the container. Parent must be in the same file **[V]**. |
| `type` | string | all | Widget type, see 1.4. |
| `data` | object | all | Per-type extras, `{}` when none (see 1.5). Present on every entry in every sample **[V]**. |
| `value` | string, number, bool | all | Current value. Containers use `""` (sections) or their title text (tabs/titles). Checkboxes use `true/false` or `""` for unchecked (both occur **[V]**; emit `false`). Number properties with a `formula` still carry a cached `value`; **[A]** Tableplop recomputes formulas on load, but emit the correct computed value anyway so the file is right even if it does not. |
| `rank` | integer | all | Sort order **among siblings** (same `parentId`), ascending. Negative values are allowed and common (e.g. -4, -19); gaps and duplicates occur **[V]**. The converter can use 0,1,2,... per parent. |
| `characterId` | integer | all | Id of the originating character; identical across the whole file (S1: 213341, S2: 214080) **[V]**. **[A]** ignored/rewritten on import; emit any constant int. |
| `name` | string | most leaf properties | Variable name used in formulas, e.g. `"strength"`, `"hit-points"`. Absent on pure layout nodes and some paragraphs **[V]**. Case-sensitive; hyphens are allowed in names (formulas write `strength-save-proficiency` and rely on this) **[V]**. Spaces were not seen in names of referenced properties (message names such as `"Recover 🩹"` exist but are not formula variables) **[V: S3]**; keep formula-referenced names `[A-Za-z0-9-]`. |
| `formula` | string | number/text/ability/skill/saving-throw/... | Expression (see 1.6). Optional. |
| `message` | string | message, ability, skill, saving-throw, some number/text/checkbox/checkboxes | Chat/roll template sent when the user clicks the property's send icon / double-clicks it (see 1.7). Optional. |
| `icon` | string | message | Image URL or path, e.g. `"/images/message.png"` **[V: S1]** or an uploaded CDN URL **[V: S3]**. |
| `size` | number | `section` only | Column width as a percentage of the horizontal section; sections in one `horizontal-section` sum to ~100 (59.08+40.92, 50+50, 65+35) **[V]**. |
| `local` | bool | `health`, `number` (death/hp parts) | `true` on hit-points, hit-points-maximum, hit-points-temporary, other-roll in S1 **[V]**. **[A]** "local" means the value is not shared with a copied/linked sheet; harmless to copy. |
| `private` | bool | `title-section` | `true` on a section titled "Notes (private)" **[V: S1]**; **[A]** hides that section from other players. |

### 1.4 Property types

All types seen in the real files (counts from S1 / S2 / S3):

| `type` | seen | role | children / notes |
|---|---|---|---|
| `tab-section` | S1:5 S2:2 S3:4 | A tab of the sheet. `parentId: null`, `value` = tab title. Ordered by `rank`. | Only top-level nodes are tabs **[V]**. Children: `title-section`, `horizontal-section`, etc. |
| `title-section` | 18 / 6 / - | A titled group (heading + body). `value` = title. May nest in other title-sections. | `private: true` allowed. |
| `horizontal-section` | 9 / 1 / - | Row container with columns. `value: ""`. | Children are `section`s. |
| `section` | 18 / 2 / - | A column in a `horizontal-section`. `value: ""`, has `size` (percent). | Children: any widgets. |
| `heading` | - / - / 1 | Heading text **[V: S3]**; field detail not examined. | |
| `paragraph` | 15 / 1 / - | Rich text block. `value` is an **HTML string** (`"<p>text</p>"`; `&nbsp;`, `<strong>` seen) **[V]**. `name` optional. | |
| `text` | 25 / 1 / - | Single-line text field. `value` string. Can have `formula` producing a string (`"\"Norm: \" + armor-class"`) **[V: S1]**. | |
| `number` | 98 / 17 / - | Numeric field. `value` number or `""`. Optional `formula`, `message`. | Used also for sub-values like `strength-score`, `hit-points-maximum`. |
| `checkbox` | 52 / 39 / - | Single checkbox. `value` bool (or `""`). Optional `message` (S1: the "used" checkboxes send a message when ticked). | In formulas it behaves as a boolean/0-1 (`x-proficiency ? proficiency : 0`) **[V]**. |
| `checkboxes` | 9 / - / - | Row of N checkboxes (pips) (death saves, spell slots used, ammo). The **count is given by a child number named `<name>-max`** (e.g. `death-saves-made` + child `death-saves-made-max` = 3; `spell-slots-used-one` + child `spell-slots-used-one-max` with `formula: "spell-slots-level-one"`) **[V: S1]**. `value` = how many are ticked (`""` = 0). | child `number` with `parentId` = the checkboxes id. |
| `health` | 1 / 1 / 2 | Hit-point bar. `name: "hit-points"`, `value` = **current** HP. | Children **[V: S1,S2]**: `number` named `hit-points-maximum` (max HP) and `number` named `hit-points-temporary` (temp HP; `""` if none). Both have `parentId` = the health property id. S1 marks all three `local: true`. |
| `ability` | - / 6 / 11 | Ability-score tile in the Tableplop-native layout. `name` e.g. `strength`, `value` = **modifier**, `formula: "floor ((strength-score - 10) / 2)"`, `message: "strength check: {1d20 + strength}"`. Child `number` named `strength-score` holds the **score** **[V: S2]**. | S1 instead builds the abilities as a `table` of `text`/`number` props (a custom layout); S2 shows the native `ability` pattern, preferable. |
| `saving-throw` | 6 / 6 / - | Save row. `name` e.g. `strength-save`, `value` = save bonus, `formula: "strength + (strength-save-proficiency ? proficiency : 0)"`, `message: "STR save: {1d20 + strength-save}"`. Child `checkbox` named `strength-save-proficiency`. | **[V: S1,S2]**. |
| `skill` | 19 / 16 / - | Skill row. `name` e.g. `sleight-of-hand`, `data: {"subtitle": "dex"}` (the small ability label), `value` = bonus, formula and message as in 1.7. Children: checkbox `<skill>-proficiency`, (S1 only) checkbox `<skill>-expertise`. | **[V]**. |
| `message` | 5 / 3 / 3 | A saved chat message / macro button (attacks, spells). `name` = label, `icon`, `message` = template text (1.7). `value: ""`. Usually inside a `filter-list`. | **[V]**. |
| `filter-list` | 2 / 1 / 1 | A searchable list container for `message`s (the "Actions" and "Spells" lists). `value: ""`. | **[V]**. |
| `table` | 1 / - / 2 | Table container. `data.headers` = array of column header strings, e.g. `["Name","Mod","Total","Base","Gear","Temp"]`. Children (`text`/`number`) fill cells row-wise by `rank` order **[V: S1,S3; exact row-wrap rule not confirmed [A]: one row = `headers.length` consecutive children]**. | |
| `appearance` | 1 / 1 / 1 | Token/appearance picker. `data: {"appearances": []}`, `value: ""`. | **[V]**; emit one inside the first tab (as S2 does) or omit; **[A]** omitting is safe. |

Types that exist in Tableplop but were **not observed** in any sample (do not emit): anything like image, dice, counter, notes, initiative. **[A: unknown]**.

### 1.5 `data` object contents (per type)

**[V]** Observed non-empty `data`: `skill.data.subtitle` (string, 3-letter lowercase ability), `table.data.headers` (string array), `appearance.data.appearances` (array, empty in all samples). Everything else is `{}`. Always include `data` (use `{}`).

### 1.6 Formulas

**[V: S1, S2, S3]** `formula` is a free-form expression string. Evidence:

- Operators: `+ - * /`, comparison `< <= > >=`, ternary `a ? b : c` (nestable), parentheses; bool/checkbox values are usable directly in `?:` conditions or arithmetic (`(use-thief-tools-proficiency ? 1 : 0) * proficiency`).
- Functions seen: `floor(...)`, `ceil(...)`, `min(...)`, string concatenation with `+` and `"..."` literals. (`floor ((x - 10) / 2)` with a space before the paren also occurs.)
- References: a **property's `name`**, bare (no brackets). Hyphens are part of the name token: `strength-save-proficiency`. Name lookup is **global by `name`** on the sheet, not path based: `proficiency`, `level`, `dex` etc. are used from anywhere **[V]**. Some formulas use short names `dex`, `str` etc. (`"dex"`, `"dexterity + ..."`, `"10 + perception"`): in S2 initiative is `formula: "dex"`; in S1 initiative is `"dex"` while the ability property is named `dexterity`, **so `dex` is presumably a built-in alias**, but this is **[A]** and S1's `armor-class` formula `ac-base-armor + ac-shield-bonus + min(dex, armor-dex-max)` also uses it. Safe approach: reference the full property `name` you create (`dexterity`), never rely on aliases.
- `@:name:` inline substitution inside *text/message* contexts (e.g. `"proficiency + @:spell-primary-stat:"`), where the referenced property holds a *name*; avoid in generated files.
- Formula `value` caching: every formula property also stores a `value`. **[A]** Tableplop recomputes.

Proficiency bonus formula used in both samples **[V]**:
`level <= 4 ? 2 : level <= 8 ? 3 : level <= 12 ? 4 : level <= 16 ? 5 : 6` (S1 text truncated at `: 5 :`; the final `6` is the obvious completion **[A]**).

Skill formula (S2, includes Jack-of-all-trades and expertise) **[V]**:
`wisdom + (insight-proficiency ? proficiency : jack-of-all-trades ? (floor (proficiency / 2)) : 0) + (insight-expertise ? proficiency : 0)`.
This requires a `jack-of-all-trades` checkbox somewhere; for a generated file drop that clause: `wisdom + (insight-proficiency ? proficiency : 0) + (insight-expertise ? proficiency : 0)` **[A: valid by construction; S1 uses `(x-expertise ? proficiency*2 : x-proficiency ? proficiency : 0)` in the v1 converter S5]**.

### 1.7 Messages (`message` field)

**[V]** Mini-language embedded in the string:
- `{1d20 + strength}` = a dice roll with property references, evaluated on send.
- `{1d20 + strength-save}`; `{1d8 + dex}`; `1d20@:csi-attack-suffix:` (advantage suffix substitution).
- Leading `!r name = expr` or `!h text` = special commands (`"!r initiative = 1d20 + initiative"` makes the click roll initiative into the tracker; `!h` = hidden/whisper? **[A]**).
- Plain text before the braces is the label: `"Light Pistol: {1d20 + prof + dex} to hit, {1d8 + dex} piercing. Range 40/160 ft."` (S2 message prop) **[V]**.
- Multiple lines use `\n`.
Messages are optional everywhere; a converter can safely emit the simple `"Label: {1d20 + x}"` forms copied from S2.

### 1.8 How a 5e sheet is laid out (what to generate)

Two real layouts: S1 (4-5 custom tabs, ~280 props, heavy custom macros) and S2 (clean, uses native `ability`/`health`/`saving-throw`/`skill`). **Recommended target = S2's structure** (all **[V: S2]**):

```
tab-section "Character"            (parentId null)
  horizontal-section
    section size 65
      title-section "Abilities"
        ability strength  (formula floor ((strength-score - 10) / 2); message "strength check: {1d20 + strength}")
          number strength-score (value = score)
        ... dexterity, constitution, intelligence, wisdom, charisma (same pattern)
      health hit-points  (value current)
        number hit-points-maximum
        number hit-points-temporary
      title-section "Info"
        number initiative (formula "dex"; message "!r initiative = 1d20 + initiative")
        number armor-class
        number speed
        number proficiency (formula = level ladder)
        text class
        number level
        number experience
      appearance (optional)
      title-section "Details"
        paragraph
    section size 35
      title-section "Saving Throws"
        saving-throw strength-save ... (child checkbox strength-save-proficiency)
      title-section "Skills"
        skill athletics ... persuasion (data.subtitle; children -proficiency, -expertise checkboxes)
tab-section "Combat"/"Spells" ... (filter-list of message items)
```

The 18 skills and their abilities (identical in S1, S2, S5): athletics str; acrobatics, sleight-of-hand, stealth dex; arcana, history, investigation, nature, religion int; animal-handling, insight, medicine, perception, survival wis; deception, intimidation, performance, persuasion cha. Property names are the lowercase hyphenated skill names.

Pitfalls from the samples to avoid: S2 `initiative` formula `dex` must resolve (the sheet has no property named `dex`!), which implies Tableplop **built-in ability aliases `str dex con int wis cha`** **[A, inferred from S2 + S1]**. Emit `formula: "dexterity"` to be safe unless you can confirm aliases.

### 1.9 Minimal valid file (derived from S2; not itself tested against Tableplop)

```json
{
  "properties": [
    {"id": 1, "parentId": null, "type": "tab-section", "data": {}, "value": "Character", "rank": 0, "characterId": 1},
    {"id": 2, "parentId": 1, "type": "ability", "data": {}, "name": "strength", "value": 2, "rank": 0,
     "formula": "floor ((strength-score - 10) / 2)", "message": "strength check: {1d20 + strength}", "characterId": 1},
    {"id": 3, "parentId": 2, "type": "number", "data": {}, "name": "strength-score", "value": 14, "rank": 0, "characterId": 1}
  ],
  "private": false,
  "type": "tableplop-character-v2"
}
```

---

## Part 2. D&D Beyond public character data

### 2.1 Endpoint

- **[V: live curl 2026-11-11]** `GET https://character-service.dndbeyond.com/character/v5/character/<id>` returns the full character JSON for a publicly shared character, no cookies, no auth, no special headers. Works with curl's default User-Agent and with `python-requests/2.31`; both returned 200. (`Set-Cookie` AWSALB* load-balancer cookies are returned and can be ignored.)
- **[V]** `v3` and `v4` now return `{"error":{"code":"UnsupportedApiVersion",...}}`. The old community converters (S5) that call `/v3/` are broken. Use `v5`.
- **[V]** `Content-Type: application/json; charset=utf-8`. Responses are 80 KB to 800 KB+ (public sample sizes: 77 KB minimal, 365 KB druid 13, 777 KB paladin/warlock with 70 items), so allow a timeout and don't log the body.
- **[V]** Id extraction: `https://www.dndbeyond.com/characters/<id>` and `.../characters/<id>/<slug>`. `<id>` is a plain integer; extract with `r"dndbeyond\.com/characters/(\d+)"`. (Share links like `https://ddb.ac/characters/<id>/<code>` appear in S5; `[A]` they also contain `/characters/<id>/`, not tested.) The `readonlyUrl` field in the response is `https://dndbeyond.com/characters/<id>`.
- Envelope **[V]**:
  ```json
  {"id":0,"success":true,"message":"Character successfully received.","data":{ ...character... },"pagination":null}
  ```
  Always check `success` and use `data`.

### 2.2 Errors (live results)

| case | HTTP | body |
|---|---|---|
| Public character | 200 | `success: true`, `data` = character |
| **Private** character (e.g. id 1) | **403** | `{"id":0,"success":false,"message":"An unexpected error has occurred","data":{"serverMessage":"Unauthorized Access Attempt.","errorCode":"2c0e0ac"},"pagination":null}` |
| **Nonexistent** id (e.g. 1000, 100000, 1234567) | **404** | `{"success":false,"message":"The resource requested was not found.","data":{"serverMessage":"The resource requested was not found.",...}}` |
| Non-numeric id (`abc`) | 400-style | `"The parameters provided are invalid."` (HTTP status not captured) |
| Id far above any real one (999999999999) | not 404 | `"No adequate concurrency handler."` (status not captured) |

**[A]** A 403 is returned for private characters but a character that was *deleted* might also be 404; they can be distinguished: 403 -> "character is private, ask the owner to set sharing to Public", 404 -> "not found". Characters shared "Anyone with link" vs "Public" **[A]**: both appear to be readable by id (all fetched characters had `preferences.privacyType = 3` and `sharingType = 2`), but this was not isolated.

### 2.3 Top-level `data` keys (v5) [V: D1, D2, D3]

`id, userId, username, isAssignedToPlayer, readonlyUrl, decorations, name, socialName, gender, faith, age, hair, eyes, skin, height, weight, inspiration, baseHitPoints, bonusHitPoints, overrideHitPoints, removedHitPoints, temporaryHitPoints, currentXp, alignmentId, lifestyleId, stats[6], bonusStats[6], overrideStats[6], background, race, raceDefinitionId, raceDefinitionTypeId, notes, traits, preferences, configuration, lifestyle, inventory[], currencies, classes[], feats[], features, customDefenseAdjustments[], customSenses[], customSpeeds[], customProficiencies[], customActions[], characterValues[], conditions[], deathSaves, adjustmentXp, spellSlots[9], pactMagic[5], activeSourceCategories, spells{race,class,background,item,feat}, options{...}, choices{...}, actions{race,class,background,item,feat}, modifiers{race,class,background,item,feat,condition}, classSpells[], customItems[], campaign, creatures, optionalOrigins, optionalClassFeatures, dateModified, providedFrom, canEdit, status, statusSlug, campaignSetting`.

Never output `userId`/`username` to Telegram.

### 2.4 Where each thing lives and how to compute it

All paths are relative to `data`. "Computation" items marked **[A]** follow D&D 5e rules/community converter practice and were **not cross-checked against D&D Beyond's rendered sheet**; items marked **[V]** were checked against the sample JSON.

**Name** - `data.name` **[V]**. (D3's default is "<username>'s Character"; may be empty/null **[A]**; fall back to "Character".)

**Race** - `data.race.fullName` (e.g. "Variant Human", "Mountain Dwarf") and `data.race.baseRaceName` ("Human"), `data.race.size` (name or null), `data.race.weightSpeeds.normal.walk` = base walking speed **[V: D1 30, D2 25]**. `background`: `data.background.definition.name` ("Entertainer") when `hasCustomBackground` is false; else `data.background.customBackground.name` **[V for definition; A for custom]**.

**Classes and levels** - `data.classes[]`; each: `level` (int), `definition.name`, `definition.hitDice` (die size, 8 = d8), `hitDiceUsed`, `isStartingClass`, `subclassDefinition.name` (or `null`), `definition.spellCastingAbilityId` (1-6; 6=CHA) and `definition.canCastSpells`, `definition.spellRules` **[V]**. Total level = sum of `classes[].level` **[V]**. Display e.g. `"Bard 6"`, `"Fighter (Arcane Archer) 12"`.

**Ability scores** - stat ids: `1 STR, 2 DEX, 3 CON, 4 INT, 5 WIS, 6 CHA` **[V: D1 `stats[].id` 1..6, order is fixed]**.
- Base: `data.stats[i].value` (D1 `[8,12,13,10,15,17]`, D2 `[13,18,15,13,13,11]`) **[V]**.
- Manual bonus: `data.bonusStats[i].value` (null or int) **[V shape]**.
- Override: `data.overrideStats[i].value` (null, else replaces the *final* score) **[V shape; all samples null]**.
- Modifier bonuses: in every list of `data.modifiers.<race|class|background|item|feat|condition>[]`, entries with `type == "bonus"` and `subType` in `strength-score, dexterity-score, constitution-score, intelligence-score, wisdom-score, charisma-score` add `value`. **[V: D1 race gave charisma-score +1 and intelligence-score +1; D2 race +2 CON/+2 STR]**. Ignore `choose-an-ability-score` entries (not resolved to a stat, D2 has six of them with `isGranted: true`, those are the unchosen feat/ASI placeholders; the resolved choice appears as a normal `dexterity-score` entry flagged `isGranted: false`, D2 `class: bonus/dexterity-score=1 [choice]` twice, i.e. a +2 total from ASIs **[V]**). **Use `value` (falls back to `fixedValue`)**, both were equal in all samples.
- Item sets: `type == "set"` with `subType` like `charisma-score` and `value` N (D2: Sword of Zariel sets CHA to 20) **[V present; A: applies as `max(final, N)`, only when the item is equipped and (if `definition.canAttune`) `isAttuned`]**. Note that item modifiers are listed in `modifiers.item` even for unequipped items **[A: unverified]** so filter by the owning inventory item's `equipped`/`isAttuned` using `componentId == item.definition.id` **[A]**.
- Final score: `override if set else base + bonusStats + sum(bonus modifiers)`, then apply `set` modifiers (`max`) **[A]**. Cap at 20 is not enforced by DDB's JSON; leave uncapped **[A]**.
- Modifier: `floor((score - 10) / 2)`.

**Proficiency bonus** - not stored; `2 + (total_level - 1) // 4` **[A; same formula used in S1/S2/S5]**.

**Saving throws** - proficient if some modifier (any list) has `type == "proficiency"` and `subType == "<ability>-saving-throws"`, e.g. `dexterity-saving-throws`, `charisma-saving-throws` **[V: D1 class modifiers]**. Bonus = ability mod + (prof ? proficiency : 0) + sum of `bonus/saving-throws` modifiers (D1 has a +1 item bonus on all saves **[V]**; the Tableplop mapping can ignore it or fold it in).

**Skills** - proficiency: `type == "proficiency"` and `subType == "<skill-slug>"` using hyphenated slugs `acrobatics, animal-handling, arcana, athletics, deception, history, insight, intimidation, investigation, medicine, nature, perception, performance, persuasion, religion, sleight-of-hand, stealth, survival` **[V: D1 has deception, investigation, arcana, acrobatics, persuasion, performance, plus expertise/deception and expertise/performance]**. Expertise: `type == "expertise"`, same subType **[V]**. Half proficiency (Jack of all trades / Bard): `type == "half-proficiency"` with `subType` `ability-checks` and `initiative` **[V: D1]**. Skill bonus = ability mod + proficiency*(2 if expertise else 1 if prof else (0.5 floored if half-prof else 0)). `customProficiencies[]` (D1: "Singing", "Piano") are tool/other proficiencies (type 2), not skills **[V]**. `characterValues[]` holds per-field manual overrides keyed by numeric `typeId` (D2: typeId 1 value 21, typeId 9 text); the typeId meaning table is **not** known **[A]**, ignore.

**Hit points** (formula follows the S5 community script and DDB conventions; **max HP was NOT verified against DDB's displayed value** because the rendered sheet is login-gated; hence flagged **[A]**):
- `baseHitPoints` (D1 23, D2 76), `bonusHitPoints` (null or int), `overrideHitPoints` (null or int; D1 = 39), `removedHitPoints` (damage taken; D1 32), `temporaryHitPoints` **[V fields]**.
- `preferences.hitPointType`: `1` = fixed average, `2` = manual/rolled **[A meaning; V values: D2 = 1, D1 = 2]**. D2 check: Fighter 12 (d10 average 6) = 10 + 11*6 = **76 == baseHitPoints** [V arithmetic], so in fixed mode `baseHitPoints` already includes the hit dice but **not** the Constitution contribution.
- Max HP = `overrideHitPoints` if not null, else `baseHitPoints + (bonusHitPoints or 0) + CON_modifier * total_level + per-level bonuses`, where per-level bonus is the sum of `modifiers` entries with `subType == "hit-points-per-level"` times total level (D2: feat Tough has `bonus/hit-points-per-level = 2` **[V entry]**; so D2 max = 76 + 3*12 + 2*12 = 136 **[A]**). Hill Dwarf's +1/level similarly appears as a `hit-points-per-level` modifier in `modifiers.race` **[A]**.
- Current HP = `max - removedHitPoints` (floor 0). Temp HP = `temporaryHitPoints`. Hit dice: `classes[].hitDice` with `hitDiceUsed` **[V]**.
- `deathSaves.successCount/failCount/isStabilized` **[V]**.

**Armor class** (not stored; compute; **[A]** rules, not cross-checked with DDB output):
- Equipped inventory item where `definition.filterType == "Armor"` and `definition.armorTypeId` is 1 light, 2 medium, 3 heavy, 4 shield **[V ids: D1 Studded Leather = 1, D2 Demon Armor = 3 ac 18; shield id 4 = A]**; `definition.armorClass` = base AC (studded 12, demon armor 18) **[V]**; `definition.baseArmorName` names the base armor **[V]**.
- Light: base + DEX mod. Medium: base + min(DEX mod, 2). Heavy: base. Shield (armorTypeId 4): +`armorClass` (normally 2). Unarmored: 10 + DEX mod (Barbarian +CON, Monk +WIS, Draconic Sorcerer 13+DEX) **[A, S5 logic]**.
- Plus `bonus` modifiers with `subType == "armor-class"` (D1 item +1, D2 items +1,+1,+2,+3 **[V entries]**), only from equipped/attuned items; `item.definition.grantedModifiers[]` also carries them **[V: D2 Demon Armor has 2]**. Fighting-style / Defense etc. appear as class/feat modifiers with `subType` `armor-class`-ish names **[A]**.

**Speed** - `race.weightSpeeds.normal.walk` (also fly/burrow/swim/climb) **[V]**; `modifiers` of `type == "set"` with `subType` `speed-flying`, `speed-walking`... override (D2 item `set/speed-flying = 90`) **[V entry]**; `customSpeeds[]` **[V field, empty in samples]**; Monk/Barbarian unarmored-movement bonuses come as `bonus/unarmored-movement` **[A]**; `ignore/heavy-armor-speed-reduction` present on dwarves **[V]**.

**Initiative** - DEX mod + `bonus/initiative` modifiers (D2 feat Alert `bonus/initiative = 5` **[V entry]**) + half-proficiency if `half-proficiency/initiative` (D1 **[V entry]**, floor(proficiency/2)) **[A computation]**.

**Passive Perception** - `10 + perception skill bonus` **[A]** (Tableplop sheet S2 has this as a formula, so you can skip it).

**Inventory** - `data.inventory[]` **[V]**: `quantity`, `equipped` (bool), `isAttuned`, `definition.name`, `definition.filterType` ("Weapon", "Armor", "Other Gear", "Wondrous item"...), `definition.type` ("Dagger"...), `definition.weight`, `definition.cost`, `definition.magic`, `definition.canAttune`, `definition.rarity`, `definition.armorClass`, `definition.armorTypeId`, `definition.baseArmorName`, `definition.damage` = `{diceCount, diceValue, fixedValue, diceString:"1d4"}`, `definition.damageType` ("Piercing"), `definition.range` and `longRange`, `definition.properties[].name` ("Finesse","Light","Thrown","Versatile"... **[V]**), `definition.attackType` (1 melee, 2 ranged) **[A]**, `definition.grantedModifiers[]`, `containerEntityId` (the bag it's in). `customItems[]` are user-made items **[V empty in samples]**. Currencies: `data.currencies` = `{cp, sp, gp, ep, pp}` **[V]**.

**Attacks** - there is no single "attacks" list. Derive from: (a) equipped `Weapon` inventory items (or those with `displayAsAttack`), plus `showUnarmedStrike` in preferences **[V field]**; (b) `actions.class/race/feat[]` entries with `activation`, `dice`, `snippet`, `limitedUse` (D1: "Bardic Inspiration" with `limitedUse`) **[V]**; (c) spells with `definition.requiresAttackRoll` (+ `attackType`). Attack bonus = ability mod (STR, or DEX if `Finesse`/ranged; max of both for Finesse) + proficiency (if proficient: modifiers with `type == "proficiency"` and `subType` equal to the weapon name slug e.g. `rapier`, `shortsword`, `longsword`, `crossbow-hand`, or the categories `simple-weapons` / `martial-weapons`) + `bonus/weapon-attacks` / `magic bonus` **[V proficiency subtypes in D1; A the rest]**. Damage = `damage.diceString` + same ability mod + magical bonuses; type = `damageType`.

**Spells** - `data.classSpells[]`: `{characterClassId, spells[]}` (one per class that casts) **[V]**; `data.spells.race/class/background/item/feat` for non-class-granted spells (empty arrays in D1) **[V keys]**. Spell object: `prepared`, `alwaysPrepared`, `countsAsKnownSpell`, `usesSpellSlot`, `definition.name`, `definition.level` (0 = cantrip), `definition.school`, `definition.range` = `{origin, rangeValue, aoeType, aoeValue}`, `definition.activation` = `{activationTime, activationType}`, `definition.duration`, `definition.concentration`, `definition.ritual`, `definition.components` (array of ints, 1 V, 2 S, 3 M), `definition.requiresSavingThrow` + `definition.saveDcAbilityId`, `definition.requiresAttackRoll`, `definition.attackType`, `definition.damageEffect`, `definition.healing`, `definition.description` (HTML) **[V]**. Whether a spell is "available": cantrips always; others prepared if `prepared` or `alwaysPrepared`, or for "known"-casters (Bard/Sorcerer/Warlock/Ranger) all with `countsAsKnownSpell` **[A]**.
- Spellcasting ability = `classes[i].definition.spellCastingAbilityId` (6 = CHA in D1) **[V]**. Spell save DC = `8 + proficiency + casting mod`; spell attack = `proficiency + casting mod` **[A]**; (D1's Bard could differ by item bonuses, ignored).

**Spell slots** - **IMPORTANT [V]**: `data.spellSlots[]` (9 entries, `{level, used, available}`) has `available` **= 0 for every sample** (D1 Bard 6 shows `used` 1,1,2 and `available` 0,0,0), so **maximum slots are NOT in this field**; only `used` is. Compute max from the class table: `data.classes[i].definition.spellRules.levelSpellSlots[class_level]` is a 9-element array for that class level, indexed by level (D1 Bard 6 -> `[4,3,3,0,0,0,0,0,0]` **[V]**). Remaining = max - `spellSlots[n-1].used`. **Multiclass**: slot tables for multiple casters need combined caster level: sum over classes of `level / spellRules.multiClassSpellSlotDivisor` rounded per `multiClassSpellSlotRounding`, then look up the *full-caster* table **[A: standard 5e; the field names exist [V]; the full-caster table is not shipped separately in the JSON so hardcode the 5e PHB table]**. `data.pactMagic[]` (5 entries) is the Warlock equivalent `{level, used, available}` **[V shape; D1 all zero since not a warlock; A semantics]**.

**Other useful fields** - `traits.{personalityTraits,ideals,bonds,flaws,appearance}` and `notes.{backstory,allies,...}` (strings or null) for Tableplop paragraphs **[V keys]**; `currentXp`; `inspiration`; `faith`; `alignmentId` (1..9 numeric, mapping not captured **[A]**); `conditions[]`; `feats[].definition.name` **[V]**; `race.racialTraits` omitted in the trimmed samples (full in raw response).

### 2.5 Things the JSON does not directly give you

Final ability scores, proficiency bonus, AC, max HP, initiative, spell slot maxima, attack bonuses, spell DC: all must be computed (above). D&D Beyond's website shows the authoritative values and there may be small mismatches for homebrew, unusual class features or some item effects. Document that limitation in the bot's reply.

---

## Part 3. Mapping D&D Beyond -> Tableplop (type names per section 1.4)

Let `lvl = sum(classes[].level)`, `mod(x) = floor((x-10)/2)`, `FS[i]` = final score for stat id i (section 2.4). Tableplop property = (`type`, `name`).

| Tableplop (`type`, `name`) | Parent in sheet | Value from D&D Beyond | Note |
|---|---|---|---|
| file `type` | top | constant `"tableplop-character-v2"` | |
| file `private` | top | `false` | |
| `tab-section` "Character" / "Combat" / "Spells" / "Inventory" | `null` | constants | `rank` 0..n |
| `text` `character-name` (or the file name) | Info | `data.name` | Tableplop shows a character name in its own UI; the import may not carry one **[A]**. User renames after import. Use the name for the downloaded file (`<slug>_tableplop.json`). |
| `text` `race` | Info | `race.fullName` | |
| `text` `class` | Info | `"Bard 6"`, multiclass `"Rogue 1 / Warlock 4"` | `classes[].definition.name` + `.level` + subclass |
| `text` `background` | Info | `background.definition.name` | |
| `number` `level` | Info | `lvl` | |
| `number` `experience` | Info | `currentXp` | |
| `number` `proficiency` | Info | `2 + (lvl-1)//4` | also set `formula` = ladder in 1.6 |
| `ability` `strength` (value=mod) + child `number` `strength-score` (value=FS[1]) | Abilities | scores per 2.4 | formula `floor ((strength-score - 10) / 2)`; same for dexterity(2), constitution(3), intelligence(4), wisdom(5), charisma(6) |
| `saving-throw` `<ability>-save` + `checkbox` `<ability>-save-proficiency` | Saving Throws | checkbox = a `proficiency/<ability>-saving-throws` modifier exists; value = mod + prof | formula as 1.4 |
| `skill` `<skill>` (+ `data.subtitle`) + `checkbox` `<skill>-proficiency` + `checkbox` `<skill>-expertise` | Skills | proficiency / expertise modifiers 2.4 | 18 skills; compute `value` |
| `health` `hit-points` | Info | current HP = max - `removedHitPoints` | children below |
| `number` `hit-points-maximum` | child of health | max HP per 2.4 | |
| `number` `hit-points-temporary` | child of health | `temporaryHitPoints` (or `""`) | |
| `number` `armor-class` | Info | computed AC (2.4) | |
| `number` `speed` | Info | `race.weightSpeeds.normal.walk` + modifiers | |
| `number` `initiative` | Info | DEX mod + bonuses | message `!r initiative = 1d20 + initiative` |
| `checkboxes` `death-saves-made` / `death-saves-failed` (+ child `-max` = 3) | Combat | `deathSaves.successCount` / `failCount` | |
| `checkbox` `inspiration` | Info | `inspiration` | |
| `paragraph` | Details | HTML-escaped `traits.*`, `notes.*` joined as `<p><strong>Ideals:</strong> ...</p>` | escape `&<>` since `value` is HTML **[V: samples use `&amp;`]** |
| `paragraph` `equipment` | Inventory | list of `inventory[].definition.name` x `quantity`, plus `currencies` | simplest representation; or one `text` per item |
| `filter-list` + `message` per weapon | Combat | one per attack: `name` = weapon; `message` = `"Rapier: {1d20 + <atk>} to hit, {1d8 + <dmg>} piercing"` | numbers pre-computed (more robust than formula refs) |
| `filter-list` + `message` per spell | Spells | `definition.name` + level/school/range/duration; roll text for attack (`{1d20 + <spellatk>}`) or DC | |
| `number` `spell-save-dc`, `number` `spell-attack-bonus` | Spells | `8+prof+castmod`, `prof+castmod` | |
| `number` `spell-slots-level-<n>` + `checkboxes` `spell-slots-used-<n>` with child `-max` | Spells | max from `spellRules.levelSpellSlots[classLevel][n-1]` (2.4); `used` from `spellSlots[n-1].used` | S1 pattern; **do not** read `spellSlots[].available` |
| `number` `passive-perception` | Combat | `10 + perception` | optional |

## Part 4. Could not confirm

1. **No Tableplop export made by the owner and no official schema.** Schema is from three community files (S1, S2, S3). Tableplop's current import acceptance was not tested. Ask the owner to export one character and compare: top-level keys, whether `appearance` appears, id/characterId values, and whether a `name`/title for the character is included in the export.
2. Whether Tableplop remaps `id`/`characterId`/`parentId` on import (assumed yes), and whether formulas are recalculated on load (assumed yes).
3. Built-in aliases (`dex`, `str`, ...), the full formula grammar and function list, the `!h`/`!r` message commands, and the `@:name:` syntax; only usage patterns seen in samples were recorded.
4. Row-wrapping rule of `table` children, the exact meaning of `local`, `private` on `title-section`, and the `heading` type's fields.
5. Max HP, AC, initiative, and spell-slot maxima computations were **not cross-checked against D&D Beyond's rendered sheet** (login-gated); formulas follow 5e rules and community practice. Check with the owner's own character: compare computed values to what the DDB sheet shows.
6. Whether DDB lists modifiers from unequipped/unattuned items in `modifiers.item` (so filtering needed), exact `armorTypeId` for shields (assumed 4), the semantics of `hitPointType` values 1/2 (assumed fixed/manual), `characterValues[].typeId` table, `alignmentId` table, and the `attackType` ids.
7. The HTTP status of 400-class responses and any rate limiting by DDB: not probed. A burst of ~150 requests during discovery caused no throttling. Behaviour of "Anyone with a link" vs "Public" sharing not isolated.
8. DDB can change `v5` or tighten access at any time: it is an undocumented internal service endpoint (its predecessor `v3` already disappeared).
9. Licensing: the sample Tableplop files belong to their authors (S1 under GPL-3.0; S2/S3 no licence file). Don't ship them in the bot; they are research references only. The DDB samples are third-party public characters with personal fields removed.
