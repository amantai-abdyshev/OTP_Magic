import asyncio
import html
import logging
import time

import pyotp
from telegram import Bot
from telegram.error import RetryAfter, BadRequest

import database as db

logger = logging.getLogger(__name__)

# chat_id → asyncio.Task
_tasks: dict[int, asyncio.Task] = {}
PARSE_MODE = "HTML"


def _format_message(label: str, display_code: str, remaining: int) -> str:
    bar_total = 30
    filled = round((remaining / bar_total) * 10)
    bar = "█" * filled + "░" * (10 - filled)
    safe_label = html.escape(label)
    safe_display_code = html.escape(display_code)
    return (
        f"🔐 <b>{safe_label}</b>\n"
        f"<tg-spoiler>{safe_display_code}</tg-spoiler>\n"
        f"⏱ {bar} {remaining}s"
    )


async def _totp_loop(
    bot: Bot,
    chat_id: int,
    label: str,
    secret: str,
    period: int,
    password: str,
    active_message_id: int | None,
) -> None:
    totp = pyotp.TOTP(secret, interval=period)
    message_id = active_message_id

    try:
        while True:
            now = time.time()
            remaining = period - (int(now) % period)
            otp = totp.now()
            display_code = f"{password}{otp}" if password else otp
            text = _format_message(label, display_code, remaining)

            if message_id is None:
                msg = await bot.send_message(chat_id, text, parse_mode=PARSE_MODE)
                message_id = msg.message_id
                db.set_active_message_id(chat_id, label, message_id)
            else:
                try:
                    await bot.edit_message_text(
                        text,
                        chat_id=chat_id,
                        message_id=message_id,
                        parse_mode=PARSE_MODE,
                    )
                except RetryAfter as e:
                    logger.warning("Rate limited chat_id=%s, retry in %ss", chat_id, e.retry_after)
                    await asyncio.sleep(e.retry_after)
                    continue
                except BadRequest as e:
                    if "message is not modified" in str(e).lower():
                        pass
                    else:
                        logger.warning("edit_message_text failed: %s", e)
                        message_id = None
                        db.set_active_message_id(chat_id, label, None)
                except Exception as e:
                    logger.error("Unexpected error in totp_loop: %s", e)
                    message_id = None
                    db.set_active_message_id(chat_id, label, None)

            await asyncio.sleep(5)

    except asyncio.CancelledError:
        logger.info("TOTP task cancelled for chat_id=%s", chat_id)


def start_task(
    bot: Bot,
    chat_id: int,
    label: str,
    secret: str,
    period: int = 30,
    password: str = "",
    active_message_id: int | None = None,
) -> None:
    stop_task(chat_id)
    task = asyncio.create_task(
        _totp_loop(bot, chat_id, label, secret, period, password, active_message_id),
        name=f"totp_{chat_id}",
    )
    _tasks[chat_id] = task
    logger.info("TOTP task started chat_id=%s label=%s", chat_id, label)


def stop_task(chat_id: int) -> bool:
    """Cancel TOTP task. Returns True if one was running."""
    task = _tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False


def active_chat_ids() -> list[int]:
    return list(_tasks.keys())
