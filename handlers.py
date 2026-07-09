from __future__ import annotations

import io
import logging
from urllib.parse import urlparse, parse_qs

from telegram import Update
from telegram.ext import ContextTypes

import database as db
import totp_task
from qr import decode_qr

logger = logging.getLogger(__name__)

TOTP_PREFIX = "otpauth://totp/"
_BOT_MESSAGE_IDS_KEY = "bot_message_ids"


async def _delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int | None) -> None:
    if message_id is None:
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def _reply_tracked(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    msg = await context.bot.send_message(update.effective_chat.id, text, **kwargs)
    context.chat_data.setdefault(_BOT_MESSAGE_IDS_KEY, []).append(msg.message_id)
    return msg


async def _cleanup_chat_messages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *extra_message_ids: int | None,
) -> None:
    chat_id = update.effective_chat.id
    message_ids = context.chat_data.pop(_BOT_MESSAGE_IDS_KEY, [])
    message_ids.extend(extra_message_ids)
    for message_id in message_ids:
        await _delete_message(context, chat_id, message_id)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply_tracked(update, context, "Send QR code photo to add account.")


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    photo = update.message.photo[-1]
    tg_file = await photo.get_file()

    buf = io.BytesIO()
    await tg_file.download_to_memory(buf)

    decoded = decode_qr(buf.getvalue())

    if not decoded:
        await _cleanup_chat_messages(update, context, update.message.message_id)
        await _reply_tracked(
            update,
            context,
            "No QR code detected. Make sure the code is clearly visible and try again."
        )
        return

    raw = decoded[0]

    if not raw.startswith(TOTP_PREFIX):
        preview = raw[:60] + ("..." if len(raw) > 60 else "")
        await _cleanup_chat_messages(update, context, update.message.message_id)
        await _reply_tracked(
            update,
            context,
            "QR code is not a TOTP URI.\n"
            f"Expected: otpauth://totp/...\n"
            f"Got: {preview}\n\n"
            "Scan a QR code from Google Authenticator or similar 2FA setup."
        )
        return

    logger.info("Valid TOTP URI from user_id=%s", update.effective_user.id)

    parsed = urlparse(raw)
    params = parse_qs(parsed.query)
    secret = params.get("secret", [None])[0]
    issuer = params.get("issuer", [None])[0]
    label = parsed.path.lstrip("/") or "Unknown"
    period = int(params.get("period", ["30"])[0])

    if not secret:
        await _cleanup_chat_messages(update, context, update.message.message_id)
        await _reply_tracked(update, context, "TOTP URI missing 'secret' parameter. Invalid QR code.")
        return

    display_label = f"{issuer}:{label}" if issuer and issuer not in label else label
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        existing = db.get_account(user_id, display_label)
        db.save_account(user_id, chat_id, display_label, secret, period)
    except Exception as e:
        logger.error("save_account failed: %s", e)
        await _cleanup_chat_messages(update, context, update.message.message_id)
        await _reply_tracked(update, context, "Failed to save account. Please try again.")
        return

    await _cleanup_chat_messages(update, context, update.message.message_id)

    totp_task.start_task(
        context.bot,
        chat_id,
        display_label,
        secret,
        period,
        active_message_id=existing.active_message_id if existing else None,
    )


async def text_hint_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Send a QR photo to add an account.")


async def stop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    stopped = totp_task.stop_task(chat_id)
    if stopped:
        await update.message.reply_text("⏹ Stopped. Send /start to resume.")
    else:
        await update.message.reply_text("No active task running.")


async def delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    accounts = db.get_all_accounts(user_id)
    totp_task.stop_task(chat_id)
    await _cleanup_chat_messages(update, context, update.message.message_id)
    for account in accounts:
        if account.chat_id == chat_id:
            await _delete_message(context, chat_id, account.active_message_id)

    count = db.delete_all_accounts(user_id)

    if count:
        await _reply_tracked(update, context, f"🗑 Deleted {count} account(s). All secrets removed.")
    else:
        await _reply_tracked(update, context, "No accounts stored.")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    action = query.data

    if action == "totp:stop":
        totp_task.stop_task(chat_id)
        await query.answer("Stopped")
        await query.edit_message_text("⏹ Stopped. Send /start to resume.")

    elif action == "totp:delete":
        totp_task.stop_task(chat_id)
        count = db.delete_all_accounts(user_id)
        await query.answer("Deleted" if count else "Nothing to delete")
        text = f"🗑 Deleted {count} account(s). All secrets removed." if count else "No accounts stored."
        await query.edit_message_text(text)

    else:
        await query.answer()


async def list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    accounts = db.get_all_accounts(user_id)

    if not accounts:
        await update.message.reply_text("No accounts stored. Send a QR photo to add one.")
        return

    lines = [f"• {a.label}" for a in accounts]
    await update.message.reply_text("*Stored accounts:*\n" + "\n".join(lines), parse_mode="Markdown")
