import asyncio
import logging
import time

import pyotp
from telegram import Bot
from telegram.error import RetryAfter, BadRequest

logger = logging.getLogger(__name__)

# chat_id → asyncio.Task
_tasks: dict[int, asyncio.Task] = {}


def _format_message(label: str, display_code: str, remaining: int) -> str:
    bar_total = 30
    filled = round((remaining / bar_total) * 10)
    bar = "█" * filled + "░" * (10 - filled)
    return (
        f"🔐 *{label}*\n"
        f"`{display_code}`\n"
        f"⏱ {bar} {remaining}s"
    )


async def _totp_loop(bot: Bot, chat_id: int, label: str, secret: str, period: int, password: str) -> None:
    totp = pyotp.TOTP(secret, interval=period)
    message_id: int | None = None

    try:
        while True:
            now = time.time()
            remaining = period - (int(now) % period)
            otp = totp.now()
            display_code = f"{password}{otp}" if password else otp
            text = _format_message(label, display_code, remaining)

            if message_id is None:
                msg = await bot.send_message(chat_id, text, parse_mode="Markdown")
                message_id = msg.message_id
            else:
                try:
                    await bot.edit_message_text(
                        text,
                        chat_id=chat_id,
                        message_id=message_id,
                        parse_mode="Markdown",
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
                except Exception as e:
                    logger.error("Unexpected error in totp_loop: %s", e)
                    message_id = None

            await asyncio.sleep(5)

    except asyncio.CancelledError:
        logger.info("TOTP task cancelled for chat_id=%s", chat_id)


def start_task(bot: Bot, chat_id: int, label: str, secret: str, period: int = 30, password: str = "") -> None:
    stop_task(chat_id)
    task = asyncio.create_task(
        _totp_loop(bot, chat_id, label, secret, period, password),
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
