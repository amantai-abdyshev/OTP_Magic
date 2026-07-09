**App purpose**

Telegram bot replace Google Authenticator. User send QR photo (TOTP secret) once → bot store secret encrypted, save + start immediately → bot continuously generate + display current TOTP code (spoiler-hidden) in single message, auto-refresh every 5s via edit, show countdown timer until next 30s code refresh. Inline Stop/Delete buttons on message itself.

**Functional requirements**

- `/start` → bot prompt "send QR photo".
- User send photo → bot decode QR → extract `otpauth://totp/...` URI → parse secret + label/issuer → save + start live code immediately (single step, no prompt).
- Bot save secret (encrypted) keyed by `(user_id, label)`.
- Bot send one message w/ current 6-digit TOTP code (spoiler-tagged) + seconds-remaining countdown + inline ⏹ Stop / 🗑 Delete buttons.
- Message auto-update (edit, not new send) every 5s.
- `/stop` or inline ⏹ → cancel auto-update task for that chat.
- `/delete` or inline 🗑 → remove all stored secrets for user, revoke access.
- `/list` → show all stored account labels for user.
- Random text message (not a command, not a photo) → hint reply "Send a QR photo to add an account."
- Survive bot restart: reload active subscriptions from DB, respawn update tasks, resume editing same message (`active_message_id`).
- Bot chat kept clean: prompts/errors sent via `_reply_tracked`, swept by `_cleanup_chat_messages` next interaction; user's own messages (QR photo, commands) deleted after processing.

---

**Project structure**

```
OTP_Magic/
├── bot.py          — entry point; registers handlers; post_init sets command menu + respawns tasks on restart
├── handlers.py     — Telegram command + message + callback-query handlers
├── database.py     — SQLite persistence + Fernet encryption/decryption (secret + password)
├── totp_task.py    — async TOTP loop; manages chat_id → asyncio.Task dict; builds inline keyboard
├── qr.py           — QR decode via cv2.QRCodeDetector
├── requirements.txt
├── setup.sh        — macOS/Linux zero-to-running setup (auto-installs/upgrades Python)
├── setup.ps1       — Windows PowerShell equivalent (auto-upgrades Python via winget)
├── .env            — BOT_TOKEN, ENCRYPTION_KEY (git-ignored)
├── .env.example
├── .gitignore
└── .vscode/
    ├── launch.json — F5 debug config pointing to .venv
    └── settings.json
```

---

**Tech stack (actual)**

| Concern | Library | Notes |
|---|---|---|
| Bot framework | `python-telegram-bot` v22+ (async) | `Application.post_init` sets bot command menu + respawns tasks |
| TOTP generation | `pyotp` | `TOTP(secret, interval=period).now()` |
| QR decode | `opencv-python-headless` (`cv2.QRCodeDetector`) | Replaced `pyzbar` — libzbar caused SIGSEGV on macOS |
| Image load | `Pillow` | Convert to RGB + cap at 1920px before cv2 |
| Encryption | `cryptography` (Fernet) | Key from `ENCRYPTION_KEY` env var, never hardcoded; encrypts secret |
| Persistence | `sqlite3` (stdlib) | No ORM needed; in-place `ALTER TABLE` migration on startup |
| Config | `python-dotenv` | Loads `.env` at startup |

**Why `pyzbar` dropped**: `libzbar` C library segfaults (SIGSEGV) on macOS on certain images. `cv2.QRCodeDetector` stable, already required for image processing.

**Python compat**: all modules start w/ `from __future__ import annotations` so `X | None` / `list[str]` type hints work back to Python 3.9 (PEP 604 syntax needs 3.10+ natively). `setup.sh`/`setup.ps1` still target 3.14+ for fresh installs, but code itself runs on older interpreters already present on machine.

---

**Database schema**

```sql
CREATE TABLE accounts (
    user_id            INTEGER NOT NULL,
    label              TEXT    NOT NULL,
    encrypted_secret   BLOB    NOT NULL,
    period             INTEGER NOT NULL DEFAULT 30,
    chat_id            INTEGER NOT NULL,
    encrypted_password BLOB,
    active_message_id  INTEGER,
    created_at         TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, label)
)
```

`encrypted_password` + `active_message_id` added via `ALTER TABLE ... ADD COLUMN` in `init_db()` (idempotent, swallows "duplicate column" error) — safe migration for existing DBs. `encrypted_password` column kept but unused (always NULL) — `save_account`/`Account` still default `password=""`, no schema change needed to drop the feature. Upsert on `(user_id, label)` conflict — re-scanning same QR overwrites secret/period.

---

**Implementation decisions**

- **Edit interval**: hardcoded `asyncio.sleep(5)` in `totp_task._totp_loop` — 6 edits per 30s cycle, safe under Telegram ~20 edits/min limit. (No longer env-configurable — `EDIT_INTERVAL` in `.env` unused.)
- **Onboarding flow**: single step. photo → QR parsed → `save_account` → `totp_task.start_task` immediately. No password prompt, no pending-state, no `/cancel`.
- **Message format**: `🔐 <b>Label</b>\n<tg-spoiler>123456</tg-spoiler>\n⏱ ██████░░░░ 18s`, HTML parse mode, code wrapped in spoiler tag, label/code HTML-escaped.
- **Inline keyboard**: every TOTP message carries ⏹ Stop / 🗑 Delete buttons (`totp:stop` / `totp:delete` callback_data). `callback_handler` in handlers.py dispatches; `reply_markup` must be passed on every `send_message`/`edit_message_text` call in loop or buttons vanish.
- **Bot command menu**: `set_my_commands` called in `post_init` (start/list/stop/delete) — must run before `run_polling` starts.
- **Task respawn on restart**: `post_init` hook queries all DB accounts → calls `totp_task.start_task()` per account, passing stored `active_message_id` so it resumes editing same message instead of sending new one.
- **Duplicate label**: upsert — silently overwrites secret w/ new scan.
- **Delete scope**: `/delete` and inline 🗑 both delete ALL accounts for user (`delete_all_accounts`), not per-label. Inline delete also stops task and edits message in place; does not currently clean up other tracked bot messages in chat.
- **Chat cleanup**: bot tracks own sent message IDs per chat (`chat_data["bot_message_ids"]`) via `_reply_tracked`, sweeps via `_cleanup_chat_messages` before posting next prompt; user-sent messages (photos, commands) explicitly deleted after consumed. Random text messages get a hint reply via `text_hint_handler`.
- **Rate limit**: `RetryAfter` caught in loop → sleeps `retry_after` seconds → continues.
- **Edit on deleted/broken message**: `BadRequest` (other than "not modified") or unexpected exception → `message_id = None` + `db.set_active_message_id(None)` → resends fresh message next tick.
- **`period` param**: parsed from `otpauth://` URI (`?period=60`), defaults to 30s if absent.

---

**Security**

- Secret encrypted w/ Fernet before DB insert; decrypted only in memory at TOTP generation time.
- Displayed code wrapped in Telegram `<tg-spoiler>` — hidden until tapped.
- Never log raw secret or QR URI content.
- `ENCRYPTION_KEY` and `BOT_TOKEN` in `.env`, excluded from git via `.gitignore`.
- **Accepted risk**: bot account compromise → all 2FA secrets exposed. Single point of failure vs offline authenticator app. Mitigate: strong bot token rotation policy, restrict bot to private chats only.

---

**Error handling**

- Non-QR photo → "No QR code detected." (chat cleaned up first)
- QR not `otpauth://totp/` → reject w/ format explanation + raw preview.
- QR missing `secret` param → reject.
- `save_account` DB failure → "Failed to save account", chat cleaned.
- `RetryAfter` → backoff sleep in loop.
- `BadRequest` (not-modified) → silently ignored.
- `BadRequest` (other) / unexpected exception → resend message next tick.
- Fernet decrypt failure on restart (secret) → skip account, log warning.

---

**Run / debug**

```bash
# One-command setup + run (macOS/Linux)
./setup.sh          # auto-installs/upgrades Python, creates venv, installs deps, prompts BOT_TOKEN, generates ENCRYPTION_KEY, runs bot

# Windows
./setup.ps1

# Manual
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # set BOT_TOKEN
python bot.py

# Debug in VSCode: F5
```