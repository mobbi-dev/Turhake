<p align="center">
  <img src="https://turhake.org/assets/img/logo.png" alt="Turhake logo" width="300">
</p>

# Turhake Discord Bot

Turhake bot is a proudly useless Discord bot 🤖 It claims to do nothing... and yet mysteriously does quite a few things.

The project is still in its early stages of development. There are almost certainly bugs, rough edges, and questionable design decisions here and there. If you have ideas, find a bug, or notice something that could be improved, pull requests and issue reports are always welcome.

## Features

- HLTV match lookup and live match tracking
- CS Team watchlist (automatically tracks the next match and match schedule changes)
- Steam profile lookup
- FACEIT profile lookup
- Free game notifications
- CS2 news updates
- Weather forecasts

## Requirements

- Python 3.9+ (tested on 3.9 and 3.11)
- Chrome or Chromium for Selenium
- A `.env` file copied from `.env.example`

## Browser Setup

Turhake requires Chrome or Chromium for Selenium-based browser automation.

## Installation

Make sure you have Python installed, then install the required dependencies:

```bash
pip install -r requirements.txt
```

## Setup

Copy `.env.example` to `.env` in the project root

## Commands

### General

- `!commands` - Show public command help
- `!weather <city>` - Current weather
- `!weather tomorrow <city>` - Tomorrow's weather
- `!weather week <city>` - Weekly forecast
- `!weather hourly <city>` - Hourly forecast

### CS2 / Profiles

- `!cs <team> [count]` - Next CS match(es)
- `!live <team>` - Live match lookup
- `!steam <steamid/link>` - Steam profile info
- `!faceit <steamid/link>` - FACEIT profile info

### HLTV Team Watchlist

- `!team add <name>` - Add a team to watchlist
- `!team list` - Show tracked teams and aliases
- `!team remove <name>` - Remove a tracked team by name or alias
- `!hltvtop` - Hidden admin command to scrape and print the current HLTV top list

## Testing

- Run `pytest` from the project root to validate the formatter and scraper helpers.

## Notes

- HLTV/Steam CS2 updates features use Selenium
- The bot stores cache files in `cache/`
- Some commands post their results to dedicated channels instead of the command channel

## Logs Channel

You can disable Discord log channel output with:

```
LOGS_CHANNEL_ENABLED=false
```

When disabled, the bot still prints logs to console, but it will not post them to a Discord channel.

## License

MIT License
