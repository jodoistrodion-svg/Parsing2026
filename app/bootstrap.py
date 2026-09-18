from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.application import (
    API_TOKEN,
    LZT_BALANCE_ID,
    autobuy_queue_manager,
    close_session,
    db_close,
    dp,
    error_reporter_loop,
    has_valid_telegram_token,
    init_db,
    logger,
)

bot = None


async def main():
    global bot
    logger.info("BOT_START mode=classic balance_id=%s", LZT_BALANCE_ID)

    if not has_valid_telegram_token(API_TOKEN):
        raise RuntimeError("Некорректный API_TOKEN: бот не может быть запущен")

    bot = Bot(token=API_TOKEN)
    # Keep the application module's shared bot reference in sync.
    import app.application as application
    application.bot = bot

    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning("WEBHOOK_DELETE_ERR err=%s", application._safe_compact(str(e), 180))

    await init_db()
    error_task = asyncio.create_task(error_reporter_loop())
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        error_task.cancel()
        await asyncio.gather(error_task, return_exceptions=True)
        await autobuy_queue_manager.shutdown()
        await close_session()
        await db_close()
        if bot is not None and getattr(bot, "session", None) is not None:
            try:
                await bot.session.close()
            except Exception:
                pass
