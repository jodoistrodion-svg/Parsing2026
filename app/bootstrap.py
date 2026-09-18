from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramConflictError, TelegramUnauthorizedError

import app.application as application
import app.runtime.core as runtime
from app.services.market_api import close_session
from app.storage.sqlite import db_close, init_db

API_TOKEN = application.API_TOKEN
LZT_BALANCE_ID = application.LZT_BALANCE_ID
autobuy_queue_manager = application.autobuy_queue_manager
dp = application.dp
has_valid_telegram_token = application.has_valid_telegram_token
logger = application.logger

bot: Bot | None = None


async def main():
    global bot
    logger.info("BOT_START mode=classic balance_id=%s", LZT_BALANCE_ID)

    if not has_valid_telegram_token(API_TOKEN):
        raise RuntimeError("Некорректный API_TOKEN: бот не может быть запущен")

    bot = Bot(token=API_TOKEN)
    runtime.bot = bot

    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning("WEBHOOK_DELETE_ERR err=%s", application._safe_compact(str(e), 180))

    await init_db()
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except TelegramUnauthorizedError:
        logger.exception("POLLING_UNAUTHORIZED invalid telegram token")
        raise
    except TelegramConflictError:
        logger.exception("POLLING_CONFLICT another polling/webhook instance is running")
        raise
    finally:
        await autobuy_queue_manager.shutdown()
        await close_session()
        await db_close()
        if bot is not None and getattr(bot, "session", None) is not None:
            try:
                await bot.session.close()
            except Exception:
                pass
