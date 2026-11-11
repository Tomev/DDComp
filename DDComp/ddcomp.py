#!/usr/bin/env python
# pylint: disable=unused-argument
"""
DDComp -- A simple telegram bot for taking care of D&D utilities. Use /help to see the
available commands.
"""

import json
import logging
import os
import random
import sys
from inspect import getdoc
from typing import Callable, Dict, List

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Make the sibling module importable both when started as `python DDComp/ddcomp.py`
# and when this file is imported from elsewhere (e.g. the tests).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tableplop  # noqa: E402  pylint: disable=wrong-import-position

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


commands: Dict[str, Callable] = {}


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends this message when the command /help is issued."""
    global commands

    message = "The following commands are available:\n"
    for command in sorted(commands):
        doc: str = getdoc(commands[command]).replace("\n", " ")
        message += f"/{command} -- {doc}\n"

    await update.message.reply_text(message)


async def character(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    This function handles the /character command. It rolls stats for a new character
    using standard D&D rules.
    """
    n_stats: int = 6
    message: str = ""
    stats: List[int] = []

    for i in range(n_stats):
        message += f"Rolling stats {i + 1}:\n"
        rolls = [random.randint(1, 6) for _ in range(4)]
        rolls.sort()
        message += f"    Rolls: {rolls}\n"
        rolls.pop(0)
        message += f"    Best 3: {rolls}\n"
        stats.append(sum(rolls))
        message += f"    Stat total: {stats[-1]}\n\n"

    stats.sort(reverse=True)
    message += f"\nStats: {stats}"

    await update.message.reply_text(message)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Provides basic information about the bot.
    """
    message: str = "Repository: https://github.com/Tomev/DDComp"
    await update.message.reply_text(message)


TO_TABLEPLOP_USAGE: str = (
    "Usage: /to_tableplop <url>\n"
    "Example: /to_tableplop https://www.dndbeyond.com/characters/12345678"
)
TO_TABLEPLOP_CAPTION: str = (
    "In Tableplop: Characters -> New Character -> Import, then pick this file.\n"
    "Computed values (AC, HP, attack bonuses, spell slots) may differ from "
    "D&D Beyond; please check them against your D&D Beyond sheet."
)


async def to_tableplop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Converts a public D&D Beyond character into a Tableplop character file. Usage:
    /to_tableplop <D&D Beyond character URL>.
    """
    url: str = context.args[0] if context.args else ""
    character_id = tableplop.parse_character_url(url)
    if character_id is None:
        await update.message.reply_text(TO_TABLEPLOP_USAGE)
        return

    try:
        data = await tableplop.fetch_character(character_id)
    except tableplop.CharacterPrivateError:
        await update.message.reply_text(
            "This character is private. Open the character's settings on D&D "
            "Beyond, set Character Privacy to Public, and try again."
        )
        return
    except tableplop.CharacterNotFoundError:
        await update.message.reply_text(
            "D&D Beyond has no character with this id. Please check the URL."
        )
        return
    except tableplop.DDBError as error:
        logger.warning("Fetching character %s failed: %s", character_id, error)
        await update.message.reply_text(
            "Could not reach D&D Beyond right now. Please try again later."
        )
        return

    try:
        sheet = tableplop.convert(data)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Converting character %s failed", character_id)
        await update.message.reply_text("Sorry, this character could not be converted.")
        return

    name: str = tableplop.character_name(data)
    await update.message.reply_document(
        document=json.dumps(sheet, ensure_ascii=False, indent=1).encode("utf-8"),
        filename=tableplop.output_filename(name),
        caption=TO_TABLEPLOP_CAPTION,
    )


# This will be used to add handlers for respective commands. It's also used in the
# help command to list available commands.
commands = {
    "help": help_command,
    "character": character,
    "about": about,
    "to_tableplop": to_tableplop,
}


def main() -> None:
    token: str = os.getenv("telegram_ddcomp_token")

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(token).build()

    # on different commands - answer in Telegram
    for command, handler in commands.items():
        application.add_handler(CommandHandler(command, handler))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
