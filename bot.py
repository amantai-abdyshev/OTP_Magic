import logging
import os

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters

import database as db
import totp_task
from handlers import (
    cancel_handler,
    delete_handler,
    list_handler,
    password_text_handler,
    photo_handler,
    start_handler,
    stop_handler,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app: Application) -> None:
    try:
        db.init_db()
    except Exception as e:
        logger.error("DB init failed: %s", e)
        raise

    accounts = db.get_all_active()
    logger.info("Respawning tasks for %d stored account(s)", len(accounts))
    for account in accounts:
        totp_task.start_task(
            app.bot,
            account.chat_id,
            account.label,
            account.secret,
            account.period,
            password=account.password,
        )


def main() -> None:
    token = os.environ["BOT_TOKEN"]

    app = Application.builder().token(token).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("stop", stop_handler))
    app.add_handler(CommandHandler("delete", delete_handler))
    app.add_handler(CommandHandler("list", list_handler))
    app.add_handler(CommandHandler("cancel", cancel_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, password_text_handler))

    logger.info("Bot starting…")
    app.run_polling()


if __name__ == "__main__":
    main()
