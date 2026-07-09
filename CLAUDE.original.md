**App purpose**

Telegram bot replace Google Authenticator. User send QR photo (TOTP secret) once → set password prefix → bot store secret + password encrypted → bot continuously generate + display current TOTP code (prefixed, spoiler-hidden) in single message, auto-refresh every 5s via edit, show countdown timer until next 30s code refresh. Inline Stop/Delete buttons on message itself.

**Functional requirements**

- `/start` → bot prompt "send QR photo".
- User send photo → bot decode QR → extract `otpauth://totp/...` URI → parse secret + label/issuer.
- Bot asks for password prefix (8–128 chars, whitespace preserved) → next text message consumed as password, not QR.
- Bot save secret + password (both encrypted) keyed by `(user_id, label)`.
- Bot send one message w/ current 6-digit TOTP code (prefixed w/ password, spoiler-tagged) + seconds-remaining countdown + inline ⏹ Stop / 🗑 Delete buttons.
- Message auto-update (edit, not new send) every 5s.
- `/stop` or inline ⏹ → cancel auto-update task for that chat.
- `/delete` or inline 🗑 → remove all stored secrets for user, revoke access.
- `/list` → show all stored account labels for user.
- `/cancel` → abort pending QR-add flow (mid password-prompt).
- Survive bot restart: reload active subscriptions from DB, respawn update tasks, resume editing same message (`active_message_id`).
- Bot chat kept clean: prompts/errors sent via `_reply_tracked` and swept by `_cleanup_chat_messages` on next interaction; user's own messages (QR photo, password text, commands) deleted after processing.

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
| Encryption | `cryptography` (Fernet) | Key from `ENCRYPTION_KEY` env var, never hardcoded; encrypts secret AND password |
| Persistence | `sqlite3` (stdlib) | No ORM needed; in-place `ALTER TABLE` migration on startup |
| Config | `python-dotenv` | Loads `.env` at startup |

**Why `pyzbar` dropped**: `libzbar` C library segfaults (SIGSEGV) on macOS when processing certain images. `cv2.QRCodeDetector` is stable and already required for image processing.

**Python compat**: all modules start with `from __future__ import annotations` so `X | None` / `list[str]` type hints work back to Python 3.9 (PEP 604 syntax needs 3.10+ natively). `setup.sh`/`setup.ps1` still target 3.14+ for fresh installs, but code itself runs on older interpreters already present on a machine.

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

`encrypted_password` and `active_message_id` added via `ALTER TABLE ... ADD COLUMN` in `init_db()` (idempotent, swallows "duplicate column" error) — safe migration for existing DBs. Upsert on `(user_id, label)` conflict — re-scanning same QR overwrites secret/password/period.

---

**Implementation decisions**

- **Edit interval**: hardcoded `asyncio.sleep(5)` in `totp_task._totp_loop` — 6 edits per 30s cycle, safe under Telegram ~20 edits/min limit. (No longer env-configurable — `EDIT_INTERVAL` in `.env` is unused.)
- **Password prefix flow**: photo → QR parsed → stored in `context.user_data["pending_account"]` → next non-command text message treated as password (validated 8–128 chars, NOT stripped — exact whitespace preserved) → account saved. `/cancel` clears pending state.
- **Message format**: `🔐 <b>Label</b>\n<tg-spoiler>prefix123456</tg-spoiler>\n⏱ ██████░░░░ 18s`, HTML parse mode, code wrapped in spoiler tag, label/code HTML-escaped.
- **Inline keyboard**: every TOTP message carries ⏹ Stop / 🗑 Delete buttons (`totp:stop` / `totp:delete` callback_data). `callback_handler` in handlers.py dispatches; `reply_markup` must be passed on every `send_message`/`edit_message_text` call in the loop or buttons vanish.
- **Bot command menu**: `set_my_commands` called in `post_init` (start/list/stop/delete/cancel) — must run before `run_polling` starts.
- **Task respawn on restart**: `post_init` hook queries all DB accounts → calls `totp_task.start_task()` per account, passing stored `active_message_id` so it resumes editing the same message instead of sending a new one.
- **Duplicate label**: upsert — silently overwrites secret/password with new scan.
- **Delete scope**: `/delete` and inline 🗑 both delete ALL accounts for the user (`delete_all_accounts`), not per-label. Inline delete also stops the task and edits the message in place; does not currently clean up other tracked bot messages in the chat.
- **Chat cleanup**: bot tracks its own sent message IDs per chat (`chat_data["bot_message_ids"]`) via `_reply_tracked`, sweeps them via `_cleanup_chat_messages` before posting the next prompt; user-sent messages (photos, password text, commands) explicitly deleted after being consumed.
- **Rate limit**: `RetryAfter` caught in loop → sleeps `retry_after` seconds → continues.
- **Edit on deleted/broken message**: `BadRequest` (other than "not modified") or unexpected exception → `message_id = None` + `db.set_active_message_id(None)` → resends fresh message next tick.
- **`period` param**: parsed from `otpauth://` URI (`?period=60`), defaults to 30s if absent.

---

**Security**

- Secret AND password prefix encrypted with Fernet before DB insert; decrypted only in memory at TOTP generation time.
- Displayed code wrapped in Telegram `<tg-spoiler>` — hidden until tapped.
- Never log raw secret, password, or QR URI content.
- `ENCRYPTION_KEY` and `BOT_TOKEN` in `.env`, excluded from git via `.gitignore`.
- **Accepted risk**: bot account compromise → all 2FA secrets + password prefixes exposed. Single point of failure vs offline authenticator app. Mitigate: strong bot token rotation policy, restrict bot to private chats only.

---

**Error handling**

- Non-QR photo → "No QR code detected." (chat cleaned up first)
- QR not `otpauth://totp/` → reject with format explanation + raw preview.
- QR missing `secret` param → reject.
- Password fails validation (empty / <8 / >128 chars) → error message, pending QR retained, user can retry or `/cancel`.
- `save_account` DB failure → "Failed to save account", pending state cleared, chat cleaned.
- `RetryAfter` → backoff sleep in loop.
- `BadRequest` (not-modified) → silently ignored.
- `BadRequest` (other) / unexpected exception → resend message next tick.
- Fernet decrypt failure on restart (secret) → skip account, log warning. Password decrypt failure → falls back to empty string prefix, account still loads.

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
