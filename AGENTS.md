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


<claude-mem-context>
# Memory Context

# [OTP_Magic] recent context, 2026-06-30 5:47pm GMT+6

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 31 obs (10,129t read) | 558,522t work | 98% savings

### Jun 30, 2026
43 4:13p 🟣 OTP_Magic Telegram Bot — Project Spec Created
44 4:14p 🟣 OTP_Magic Project Scaffolded — Files Created
45 4:25p 🟣 handlers.py — /start and photo QR decode handlers implemented
46 4:26p 🔵 System Python is 3.14.4 — newer than spec minimum
47 " ✅ OTP_Magic venv created and all deps installed successfully
48 " 🟣 database.py — Full SQLite + Fernet storage layer implemented
49 4:28p ✅ VSCode launch config added for OTP_Magic bot
50 " 🔵 All OTP_Magic deps verified importable in venv
S27 Second SIGSEGV crash on regular photo — escalated fix: isolated pyzbar into subprocess via ProcessPoolExecutor (Jun 30 at 4:29 PM)
51 4:29p 🔵 pyzbar/zbar segfaults on non-QR library photos — SIGSEGV KERN_INVALID_ADDRESS
52 4:41p 🔵 handlers.py on disk is OLD version — missing database/totp_task integration
53 4:42p 🔴 pyzbar SIGSEGV crash fixed — image normalize to RGB + cap at 1920px before decode
54 4:44p 🔵 pyzbar SIGSEGV persists after RGB convert + thumbnail fix — crash not resolved
55 4:45p 🔴 libzbar SIGSEGV isolated to subprocess — ProcessPoolExecutor sandwich pattern
56 " 🔴 handlers.py adapted to qr.py API — decode_qr returns list[str] not list[pyzbar.Decoded]
S28 Session resumed — caveman mode confirmed active, awaiting next user instruction (Jun 30 at 4:45 PM)
S31 User requested CLAUDE.md update with project structure and tech stack changes — session still in setup/verification loop (Jun 30 at 4:49 PM)
57 4:50p 🔄 QR decoder switched from pyzbar (subprocess) to OpenCV QRCodeDetector
58 " 🔴 handlers.py: removed await from decode_qr() — cv2 version is synchronous
S34 Password-prefix feature implementation: add encrypted password prepended to TOTP display code (Jun 30 at 4:50 PM)
S29 Full handlers.py wiring completed + pyzbar removed from requirements — bot now fully functional end-to-end (Jun 30 at 4:50 PM)
59 4:56p 🔵 OTP_Magic Telegram Bot — Pre-Implementation State
61 " 🟣 Encrypted SQLite Storage Layer Implemented (database.py)
62 " 🟣 Live TOTP Code Generator Implemented (totp_task.py)
60 4:57p 🔵 qr.py QR Decoder Implementation Details
63 4:58p 🟣 handlers.py Wired to Storage and TOTP Task; Three New Commands Added
64 " 🟣 bot.py Updated: New Commands Registered and Task Respawn on Startup
65 " 🔵 All New Modules Import Cleanly in Project Venv
68 " ⚖️ Password Prefix Feature Planned for TOTP Display
S35 Password-prefix feature for OTP_Magic: encrypted password prepended to displayed TOTP code, two-step FSM onboarding (Jun 30 at 4:58 PM)
S30 Implement storage and TOTP generation logic for OTP_Magic Telegram bot (Jun 30 at 4:58 PM)
S32 Update CLAUDE.md to reflect actual implemented project structure and tech stack (pyzbar→cv2 switch, real DB schema, implementation decisions) (Jun 30 at 4:59 PM)
66 5:00p 🔵 database.py and totp_task.py on disk differ significantly from tracked versions
67 " ✅ CLAUDE.md rewritten with actual implementation docs — project structure, tech stack, schema
S33 Add password-prefix feature to TOTP flow: user sets password stored encrypted, displayed code becomes password+otp (Jun 30 at 5:02 PM)
69 5:34p 🟣 database.py Migrated to Support Encrypted Password Storage
70 " 🟣 totp_task.py Updated to Prepend Password to Displayed TOTP Code
71 " 🔵 database.py on Disk Shows Pre-Password Version Despite Two Write Attempts
72 5:35p 🟣 handlers.py: Two-Step FSM Onboarding Flow with Password Validation Implemented
73 " 🟣 bot.py Updated: /cancel and password_text_handler Registered; post_init Error Handling Added
S36 Password-prefix feature fully implemented: encrypted password stored per account, displayed as password+otp concatenation (Jun 30 at 5:37 PM)
**Investigated**: Re-read database.py and totp_task.py before modifying (found files had reverted to pre-password state despite prior write attempts). Confirmed file persistence issue — reads at 11:36:24 showed old content even after writes at 11:35. Applied all changes again in a fresh batch of writes.

**Learned**: File writes in this session can silently fail to persist — read-back verification is needed. The FSM approach uses context.user_data dict key presence (no explicit state machine library needed). TEXT & ~COMMAND filter in python-telegram-bot is the correct way to catch non-command text for password entry without conflicting with command handlers.

**Completed**: database.py: Account dataclass has password field (default ""), init_db adds encrypted_password BLOB column with idempotent ALTER TABLE migration, save_account accepts password param (Fernet-encrypted, NULL if empty), all CRUD queries updated, _decrypt_password helper returns "" on NULL or decrypt failure.
    totp_task.py: _totp_loop and start_task accept password param; display_code = f"{password}{otp}" if password else otp; dead last_code variable removed.
    handlers.py: photo_handler stores pending QR to context.user_data["pending_account"] and prompts for password instead of committing; password_text_handler validates (min 8, max 128 chars, no strip, Unicode) then saves+starts task; cancel_handler clears pending; delete_handler also clears pending.
    bot.py: /cancel registered, TEXT & ~COMMAND handler registered for password_text_handler, post_init passes account.password to start_task on restart, DB init failure now re-raises.
    Import smoke test passed: "all imports OK".

**Next Steps**: Implementation complete. All four files updated and verified importing cleanly. Bot is ready to run with BOT_TOKEN + ENCRYPTION_KEY in .env.


Access 559k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>