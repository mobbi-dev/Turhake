# Turhake Discord Bot

Turhake is a proudly useless Discord bot that somehow manages to provide a few useful features.

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

## License

MIT License