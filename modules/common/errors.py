from typing import Optional

from discord.ext import commands


def format_command_error(error) -> Optional[str]:
    if isinstance(error, commands.MissingRequiredArgument):
        return "⚠️ The command is missing a required argument. Use `!commands` for help."
    if isinstance(error, commands.CommandNotFound):
        return "❌ Unknown command. Use `!commands` for help."
    if isinstance(error, commands.BadArgument):
        return "⚠️ The argument type or format is invalid. Use `!commands` for help."
    return None
