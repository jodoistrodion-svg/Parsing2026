from __future__ import annotations

import asyncio
import logging
import signal

from aiogram import Bot

from aiogram.exceptions import TelegramConflictError, TelegramUnauthorizedError

import app.application as application
import app.runtime.core as runtime
from app.config.settings import (
    AUTOBUY_LOG_FILE,
    DB_CLEANUP_INTERVAL_SECONDS,
    DB_FILE,
    LOG_FORMAT,
    LOG_LEVEL,
    LZT_API_KEY,
    API_TOKEN,
    SEEN_RETENTION_DAYS,
    BUY_ATTEMPT_RETENTION_DAYS,
    HEALTH_HOST,
    HEALTH_PORT,
    TG_STARTUP_PROBE,
    describe_runtime_config,
    validate_runtime_config,
)
from app.runtime.health import HealthServer
from app.runtime.tasks import TaskSupervisor
from app.services.market_api import close_session
from app.storage.sqlite import db_close, db_cleanup, init_db
from metrics.events import METRICS
from services.logging_setup import setup_logging

logger = setup_logging(
    AUTOBUY_LOG_FILE,
    15 * 1024 * 1024,
    2,
    level=LOG_LEVEL,
    log_format=LOG_FORMAT,
    secrets=(API_TOKEN, LZT_API_KEY),
)

bot: Bot | None = None


async def _maintenance_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=max(60, DB_CLEANUP_INTERVAL_SECONDS),
            )
        except asyncio.TimeoutError:
            try:
                await db_cleanup(
                    seen_retention_days=SEEN_RETENTION_DAYS,
                    buy_attempt_retention_days=BUY_ATTEMPT_RETENTION_DAYS,
                )
                METRICS.inc("database_maintenance_total")
            except Exception:
                METRICS.inc("database_maintenance_failures_total")
                logger.exception("DATABASE_MAINTENANCE_FAILED")
        except asyncio.CancelledError:
            raise


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        signal_value = getattr(signal, name, None)
        if signal_value is None:
            continue
        try:
            loop.add_signal_handler(signal_value, stop_event.set)
        except (NotImplementedError, RuntimeError):
            # Windows event loops may not expose add_signal_handler.
            continue


async def main() -> None:
    global bot

    validate_runtime_config()
    logger.info(
        "BOT_START mode=production balance_id=%s db=%s config=%s",
        application.LZT_BALANCE_ID,
        DB_FILE,
        describe_runtime_config(),
    )

    if not application.has_valid_telegram_token(API_TOKEN):
        raise RuntimeError("Некорректный API_TOKEN: бот не может быть запущен")

    health = HealthServer(HEALTH_HOST, HEALTH_PORT)
    supervisor = TaskSupervisor()
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    bot = Bot(token=API_TOKEN)
    runtime.bot = bot

    try:
        await init_db()
        await health.start()
        maintenance_task = await supervisor.spawn(
            "database-maintenance",
            _maintenance_loop(stop_event),
        )

        if TG_STARTUP_PROBE:
            await bot.get_me()

        await health.set_ready(True)
        METRICS.inc("application_starts_total")

        polling_task = asyncio.create_task(
            application.dp.start_polling(
                bot,
                allowed_updates=application.dp.resolve_used_update_types(),
            ),
            name="telegram-polling",
        )
        stop_waiter = asyncio.create_task(stop_event.wait(), name="shutdown-signal")
        done, _ = await asyncio.wait(
            {polling_task, stop_waiter},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if stop_waiter in done and not polling_task.done():
            logger.info("SHUTDOWN_SIGNAL_RECEIVED")
            try:
                await application.dp.stop_polling()
            except Exception:
                logger.exception("STOP_POLLING_FAILED")

        await polling_task
        if maintenance_task.done() and not maintenance_task.cancelled():
            error = maintenance_task.exception()
            if error is not None:
                logger.error("DATABASE_MAINTENANCE_STOPPED error=%s", error)
    except TelegramUnauthorizedError:
        health.set_error("telegram_unauthorized")
        logger.exception("POLLING_UNAUTHORIZED invalid telegram token")
        raise
    except TelegramConflictError:
        health.set_error("telegram_conflict")
        logger.exception("POLLING_CONFLICT another polling/webhook instance is running")
        raise
    except asyncio.CancelledError:
        logger.info("BOT_CANCELLED")
        raise
    except Exception as exc:
        health.set_error(type(exc).__name__)
        logger.exception("BOT_FATAL_ERROR")
        raise
    finally:
        stop_event.set()
        await health.stop()
        await supervisor.shutdown()
        await application.autobuy_queue_manager.shutdown(drain=False)
        await runtime.purchase_idempotency.clear()
        await close_session()
        await db_close()
        if bot is not None and getattr(bot, "session", None) is not None:
            try:
                await bot.session.close()
            except Exception:
                logger.exception("TELEGRAM_SESSION_CLOSE_FAILED")
        bot = None
        runtime.bot = None
        logger.info("BOT_STOP")
