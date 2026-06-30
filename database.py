import logging
import os
import sqlite3
from dataclasses import dataclass, field

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_DB_PATH = "otp_magic.db"
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = os.environ["ENCRYPTION_KEY"]
        _fernet = Fernet(key if isinstance(key, bytes) else key.encode())
    return _fernet


def init_db() -> None:
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                user_id           INTEGER NOT NULL,
                label             TEXT    NOT NULL,
                encrypted_secret  BLOB    NOT NULL,
                period            INTEGER NOT NULL DEFAULT 30,
                chat_id           INTEGER NOT NULL,
                encrypted_password BLOB,
                active_message_id INTEGER,
                created_at        TEXT    DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, label)
            )
            """
        )
        for column_sql, column_name in (
            ("ALTER TABLE accounts ADD COLUMN encrypted_password BLOB", "encrypted_password"),
            ("ALTER TABLE accounts ADD COLUMN active_message_id INTEGER", "active_message_id"),
        ):
            try:
                conn.execute(column_sql)
                logger.info("Migrated accounts table: added %s column", column_name)
            except sqlite3.OperationalError:
                pass
        conn.commit()


@dataclass
class Account:
    user_id: int
    label: str
    secret: str
    period: int
    chat_id: int
    password: str = field(default="")
    active_message_id: int | None = None


def _decrypt_password(fernet: Fernet, enc_pw: bytes | None) -> str:
    if not enc_pw:
        return ""
    try:
        return fernet.decrypt(enc_pw).decode()
    except Exception:
        logger.warning("Failed to decrypt password — returning empty string")
        return ""


def save_account(
    user_id: int,
    chat_id: int,
    label: str,
    secret: str,
    period: int = 30,
    password: str = "",
) -> None:
    fernet = _get_fernet()
    enc_secret = fernet.encrypt(secret.encode())
    enc_password = fernet.encrypt(password.encode()) if password else None

    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO accounts (user_id, label, encrypted_secret, period, chat_id, encrypted_password)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, label) DO UPDATE SET
                encrypted_secret   = excluded.encrypted_secret,
                period             = excluded.period,
                chat_id            = excluded.chat_id,
                encrypted_password = excluded.encrypted_password,
                created_at         = datetime('now')
            """,
            (user_id, label, enc_secret, period, chat_id, enc_password),
        )
        conn.commit()
    logger.info("Account saved: user_id=%s label=%s", user_id, label)


def get_account(user_id: int, label: str) -> Account | None:
    with sqlite3.connect(_DB_PATH) as conn:
        row = conn.execute(
            "SELECT user_id, label, encrypted_secret, period, chat_id, encrypted_password, active_message_id "
            "FROM accounts WHERE user_id=? AND label=?",
            (user_id, label),
        ).fetchone()
    if row is None:
        return None
    uid, lbl, enc_s, period, chat_id, enc_pw, active_message_id = row
    fernet = _get_fernet()
    secret = fernet.decrypt(enc_s).decode()
    password = _decrypt_password(fernet, enc_pw)
    return Account(
        user_id=uid,
        label=lbl,
        secret=secret,
        period=period,
        chat_id=chat_id,
        password=password,
        active_message_id=active_message_id,
    )


def get_all_accounts(user_id: int) -> list[Account]:
    with sqlite3.connect(_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT user_id, label, encrypted_secret, period, chat_id, encrypted_password, active_message_id "
            "FROM accounts WHERE user_id=?",
            (user_id,),
        ).fetchall()
    fernet = _get_fernet()
    result = []
    for uid, lbl, enc_s, period, chat_id, enc_pw, active_message_id in rows:
        secret = fernet.decrypt(enc_s).decode()
        password = _decrypt_password(fernet, enc_pw)
        result.append(
            Account(
                user_id=uid,
                label=lbl,
                secret=secret,
                period=period,
                chat_id=chat_id,
                password=password,
                active_message_id=active_message_id,
            )
        )
    return result


def get_all_active() -> list[Account]:
    """Return every stored account — used for task respawn on restart."""
    with sqlite3.connect(_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT user_id, label, encrypted_secret, period, chat_id, encrypted_password, active_message_id FROM accounts"
        ).fetchall()
    fernet = _get_fernet()
    result = []
    for uid, lbl, enc_s, period, chat_id, enc_pw, active_message_id in rows:
        try:
            secret = fernet.decrypt(enc_s).decode()
            password = _decrypt_password(fernet, enc_pw)
            result.append(
                Account(
                    user_id=uid,
                    label=lbl,
                    secret=secret,
                    period=period,
                    chat_id=chat_id,
                    password=password,
                    active_message_id=active_message_id,
                )
            )
        except Exception:
            logger.warning("Failed to decrypt account user_id=%s label=%s — skipping", uid, lbl)
    return result


def set_active_message_id(chat_id: int, label: str, message_id: int | None) -> None:
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute(
            "UPDATE accounts SET active_message_id=? WHERE chat_id=? AND label=?",
            (message_id, chat_id, label),
        )
        conn.commit()


def delete_account(user_id: int, label: str) -> bool:
    """Delete account. Returns True if row existed."""
    with sqlite3.connect(_DB_PATH) as conn:
        cur = conn.execute(
            "DELETE FROM accounts WHERE user_id=? AND label=?", (user_id, label)
        )
        conn.commit()
    return cur.rowcount > 0


def delete_all_accounts(user_id: int) -> int:
    """Delete all accounts for user. Returns count deleted."""
    with sqlite3.connect(_DB_PATH) as conn:
        cur = conn.execute("DELETE FROM accounts WHERE user_id=?", (user_id,))
        conn.commit()
    return cur.rowcount
