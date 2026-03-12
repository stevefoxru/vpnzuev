# VPN Telegram Bot

Telegram bot for selling and managing VPN keys via wg-easy API.

## Features
- buy VPN key for 7/30/90 days
- multiple keys per user
- per-key renewal
- admin panel in Telegram
- key revoke via wg-easy API
- expired key cleanup

## Setup

1. Install Python 3.12+, PostgreSQL, Docker
2. Clone repo
3. Create `.env` from `.env.example`
4. Create virtualenv
5. Install dependencies:
   pip install -r requirements.txt
6. Run bot:
   python bot.py

## Production
Use systemd service.
