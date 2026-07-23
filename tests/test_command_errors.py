from types import SimpleNamespace

from discord.ext import commands

from modules.common.errors import format_command_error


def test_format_command_error_for_missing_argument():
    param = SimpleNamespace(displayed_name="team", name="team")
    error = commands.MissingRequiredArgument(param)

    assert format_command_error(error) == "⚠️ The command is missing a required argument. Use `!commands` for help."


def test_format_command_error_for_unknown_command():
    error = commands.CommandNotFound("!nope")

    assert format_command_error(error) == "❌ Unknown command. Use `!commands` for help."


def test_format_command_error_for_bad_argument():
    error = commands.BadArgument()

    assert format_command_error(error) == "⚠️ The argument type or format is invalid. Use `!commands` for help."


def test_format_command_error_for_unhandled_error():
    assert format_command_error(RuntimeError("boom")) is None
