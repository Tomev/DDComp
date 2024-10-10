#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Application and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""

import logging
import random
import os

from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from typing import List, Callable, Dict

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


commands: Dict[str, Callable] = { }

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    global commands

    message = "The following commands are available:\n"
    for command in commands:
        message += f"/{command}\n"

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
        message += f'Rolling stats {i + 1}:\n'
        rolls = [random.randint(1, 6) for _ in range(4)]
        rolls.sort()
        message += f'    Rolls: {rolls}\n'
        rolls.pop(0)
        message += f'    Best 3: {rolls}\n'
        stats.append(sum(rolls))
        message += f'    Stat total: {stats[-1]}\n\n'       

    stats.sort(reverse=True)
    message += f'\nStats: {stats}'

    await update.message.reply_text(message)





commands = {
    "help": help_command,
    "character": character
}


def main() -> None:
    """Start the bot."""
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
