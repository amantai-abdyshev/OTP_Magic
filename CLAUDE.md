**App purpose**

Telegram bot replace Google Authenticator. User send QR photo (TOTP secret) once → bot store secret encrypted → bot continuously generate + display current TOTP code in single message, auto-refresh every 30s via edit (no spam new messages), show countdown timer until next refresh.

**Functional requirements**

- `/start` → bot prompt "send QR photo".
- User send photo → bot decode QR → extract `otpauth://totp/...` URI → parse secret + label/issuer.
- Bot save secret (encrypted) keyed by `user_id`.
- Bot send one message w/ current 6-digit TOTP code + seconds-remaining countdown.
- Message auto-update (edit, not new send) on countdown tick + on code refresh (every 30s boundary).
- `/stop` → cancel auto-update task for that chat.
- `/delete` → remove stored secret, revoke access.
- `/list` → show all stored account labels for user.
- Survive bot restart: reload active subscriptions from DB, respawn update tasks.

---

**Project structure**

```
OTP_Magic/
├── bot.py          — entry point; registers handlers; post_init respawns tasks on restart
├── handlers.py     — Telegram command + message handlers (start, stop, delete, list, photo)
├── database.py     — SQLite persistence + Fernet encryption/decryption
├── totp_task.py    — async TOTP loop; manages chat_id → asyncio.Task dict
├── qr.py           — QR decode via cv2.QRCodeDetector
├── requirements.txt
├── .env            — BOT_TOKEN, ENCRYPTION_KEY, EDIT_INTERVAL (git-ignored)
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
| Bot framework | `python-telegram-bot` v22+ (async) | `Application.post_init` for restart-safe task respawn |
| TOTP generation | `pyotp` | `TOTP(secret, interval=period).now()` |
| QR decode | `opencv-python-headless` (`cv2.QRCodeDetector`) | Replaced `pyzbar` — libzbar caused SIGSEGV on macOS |
| Image load | `Pillow` | Convert to RGB + cap at 1920px before cv2 |
| Encryption | `cryptography` (Fernet) | Key from `ENCRYPTION_KEY` env var, never hardcoded |
| Persistence | `sqlite3` (stdlib) | No ORM needed |
| Config | `python-dotenv` | Loads `.env` at startup |

**Why `pyzbar` dropped**: `libzbar` C library segfaults (SIGSEGV) on macOS when processing certain images. `cv2.QRCodeDetector` is stable and already required for image processing.

---

**Database schema**

```sql
CREATE TABLE accounts (
    user_id          INTEGER NOT NULL,
    label            TEXT    NOT NULL,
    encrypted_secret BLOB    NOT NULL,
    period           INTEGER NOT NULL DEFAULT 30,
    chat_id          INTEGER NOT NULL,
    created_at       TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, label)
)
```

Upsert on `(user_id, label)` conflict — re-scanning same QR overwrites.

---

**Implementation decisions**

- **Edit interval**: 5s (`EDIT_INTERVAL=5` in `.env`) → 6 edits per 30s cycle, safe under Telegram ~20 edits/min limit.
- **Message format**: `🔐 Label\n\`code\`\n⏱ ██████░░░░ 18s` — progress bar + seconds.
- **Task respawn on restart**: `post_init` hook queries all DB accounts → calls `totp_task.start_task()` per account. Auto-resume, no user action needed.
- **Duplicate label**: upsert — silently overwrites with new secret.
- **Rate limit**: `RetryAfter` caught in loop → sleeps `retry_after` seconds → continues.
- **Edit on deleted message**: `BadRequest` caught → `message_id = None` → resends fresh message next tick.
- **`period` param**: parsed from `otpauth://` URI (`?period=60`), defaults to 30s if absent.

---

**Security**

- Secrets encrypted with Fernet before DB insert; decrypted only in memory at TOTP generation time.
- Never log raw secret or QR URI content.
- `ENCRYPTION_KEY` and `BOT_TOKEN` in `.env`, excluded from git via `.gitignore`.
- **Accepted risk**: bot account compromise → all 2FA secrets exposed. Single point of failure vs offline authenticator app. Mitigate: strong bot token rotation policy, restrict bot to private chats only.

---

**Error handling**

- Non-QR photo → "No QR code detected."
- QR not `otpauth://totp/` → reject with format explanation.
- QR missing `secret` param → reject.
- `RetryAfter` → backoff sleep in loop.
- `BadRequest` (not-modified) → silently ignored.
- `BadRequest` (other) → resend message next tick.
- Fernet decrypt failure on restart → skip account, log warning.

---

**Run / debug**

```bash
# Install deps (one-time)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
brew install zbar  # not needed anymore but kept for reference

# Fill .env
cp .env.example .env  # set BOT_TOKEN

# Run
python bot.py

# Debug in VSCode: F5
```
