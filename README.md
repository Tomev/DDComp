# DDComp

A simple telegram bot for taking care of D&D utilities.

## Usage
Just add it to your telegram group and you should be good to go. Use /help to see the
available commands.

## Setup
Install the dependencies with `pip install -r requirements.txt`, put the bot token in the
`telegram_ddcomp_token` environment variable and start the bot with
`python DDComp/ddcomp.py`. Run the tests with `pip install pytest` and `pytest`.

## /to_tableplop
`/to_tableplop <url>` takes the URL of a D&D Beyond character, for example
`https://www.dndbeyond.com/characters/12345678`, and replies with a `.json` file that can
be imported in Tableplop (Characters -> New Character -> Import). The sheet has
Character, Combat, Spells (for spellcasters) and Inventory tabs with Tableplop's native
ability, saving throw, skill and hit point widgets, plus clickable attack and spell
messages.

Limits:
- The character must be public on D&D Beyond (Character Privacy: Public).
- D&D Beyond does not publish final numbers, so the bot computes ability scores, HP, AC,
  initiative, saves, skills, attack bonuses, spell DCs and spell slots from 5e rules.
  Unusual class features, homebrew and some magic item effects are not covered; check
  the results against the D&D Beyond sheet.
- It uses D&D Beyond's undocumented character service, which may change without
  notice.
