# OTP Magic

A Telegram bot that replaces Google Authenticator. Send it a QR code from any
service's 2FA setup, and it keeps a live, auto-refreshing TOTP code in your
chat — hidden behind a spoiler tag, prefixed with a password of your choice,
with a countdown until the next code.

## How it works

1. `/start` — the bot asks for a QR photo.
2. Send a photo of the 2FA QR code (`otpauth://totp/...`). The bot decodes it
   and extracts the secret.
3. Set a password prefix (8–128 characters). It is displayed in front of every
   code, so only you know where the prefix ends and the code begins.
4. The bot stores the secret and password encrypted (Fernet) in a local SQLite
   database, then posts a single message with the current 6-digit code,
   auto-updated every 5 seconds with a countdown bar. Inline ⏹ Stop / 🗑 Delete
   buttons live on the message itself.

Active codes survive bot restarts — the bot resumes editing the same message.

### Commands

| Command | Action |
|---|---|
| `/start` | Begin — prompts for a QR photo |
| `/list` | Show all stored account labels |
| `/stop` | Stop the live code updates in this chat |
| `/delete` | Delete **all** stored secrets for your user |
| `/cancel` | Abort a pending QR-add flow |

## Running locally

### One-command setup

```bash
./setup.sh    # macOS / Linux
./setup.ps1   # Windows (PowerShell)
```

The script installs Python if needed, creates a venv, installs dependencies,
prompts for your bot token, generates an encryption key, and starts the bot.

### Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env
python bot.py
```

### Environment variables (`.env`)

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `ENCRYPTION_KEY` | Fernet key — generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

## Security notes

- TOTP secrets and password prefixes are encrypted at rest (Fernet) and
  decrypted only in memory at code-generation time.
- Codes are wrapped in Telegram spoiler tags — hidden until tapped.
- **Accepted trade-off**: if the bot account or host is compromised, all
  stored 2FA secrets are exposed. This is a single point of failure compared
  to an offline authenticator app. Use a strong, rotated bot token and keep
  the bot in private chats only.

## License

[MIT](LICENSE)
