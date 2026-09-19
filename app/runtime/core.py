
from __future__ import annotations

import asyncio
import html
import re
import time
from collections import defaultdict

from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from bot.ui import render_status_card
from buyer.queue import UserAutobuyQueueManager
from purchase.idempotency import PurchaseIdempotency
from services.logging_setup import setup_logging

from app.config.settings import (
    API_TOKEN,
    AUTOBUY_LOG_FILE,
    BUY_SEMAPHORE,
    HUNTER_INTERVAL_BASE,
    LOG_FORMAT,
    LOG_LEVEL,
    LOG_MAX_BYTES,
    LOG_ROTATE_KEEP,
    LIMITED_EXTRA_DELAY,
    LZT_API_KEY,
    MAX_URLS_PER_USER_DEFAULT,
    MAX_URLS_PER_USER_LIMITED,
    MAX_URL_NAME_LEN,
    OWNER_IDS,
    SHORT_CARD_MAX,
    TG_SEND_DELAY,
    URL_PAGE_SIZE,
    USER_PAGE_SIZE,
)
from market.discovery import _run_bounded

logger = setup_logging(
    AUTOBUY_LOG_FILE,
    LOG_MAX_BYTES,
    LOG_ROTATE_KEEP,
    level=LOG_LEVEL,
    log_format=LOG_FORMAT,
    secrets=(API_TOKEN, LZT_API_KEY),
)


def _safe_compact(s: str, n: int = 400) -> str:
    s = (s or "").replace("\n", "\\n").replace("\r", "\\r")
    if len(s) <= n:
        return s
    return s[: n - 20] + f"...(len={len(s)})"


def log_autobuy(line: str):
    logger.info(line)


bot: Bot | None = None
dp = Dispatcher()

# ====================== START MESSAGES ======================
START_MSG_1 = (
    "🤖 Parsing Bot 🤖\n"
    "😶‍🌫️Отслеживание новых лотов по вашим URL в один клик😶‍🌫️\n\n"
    "🔗 Полезные ссылки, обязательно подписаться 🔗\n"
    "• Канал поддержки: https://t.me/+wHlSL7Ij2rpjYmFi\n"
    "• Создатель: https://t.me/StaliNusshhAaaaaa😶‍🌫️"
)

START_MSG_2 = (
    "🧭 <b>Главное меню</b>\n"
    "╭────────────────────╮\n"
    "│ ✨ Проверка лотов — до 10 свежих карточек\n"
    "│ 📚 Мои URL — источники, тест, автобай\n"
    "│ 📊 Статус — охотник, баланс, API-ошибки\n"
    "│ 🚀 Старт охотника — непрерывный мониторинг\n"
    "│ ♻️ Сбросить историю — считать все лоты новыми\n"
    "╰────────────────────╯"
)

WELCOME_STICKERS = [
    "CAACAgIAAxkBAAIBQmYkJ4hB5lL0QwABJvY5S4UuTxR1xAACZQADwDZPE9xKkS4L5N5eNgQ",
    "CAACAgIAAxkBAAIBQ2YkJ5ILV0M5mD9Vpq3nP8a3m2qvAALgAAPANk8Tq5Y-X_7h3xQ2BA",
    "CAACAgIAAxkBAAIBRGYkJ53xVv9wNR8d3lNn2s9y4C9fAALiAAPANk8TG8rJkYdM3MM2BA",
]

DENIED_TEXT = (
    "⛔️ Доступ к боту закрыт.\n\n"
    "Если ты приобрёл доступ, введи выданный код.\n"
    "Если кода нет — можно отправить запрос владельцу."
)


# ====================== UI: KEYBOARDS ======================
def kb_button(text: str, style: str | None = None) -> KeyboardButton:
    if style:
        try:
            return KeyboardButton(text=text, style=style)
        except Exception:
            pass
    return KeyboardButton(text=text)


def kb_request() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [kb_button("🔑 Ввести код доступа", "success")],
            [kb_button("🔓 Запрос на бота", "primary")],
        ],
        resize_keyboard=True,
    )


def kb_license_admin() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [kb_button("➕ Создать код", "success"), kb_button("📊 Статистика кодов")],
            [kb_button("📋 Последние коды"), kb_button("🚫 Отозвать по ID", "danger")],
            [kb_button("⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def kb_main(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [kb_button("🚀 Старт охотника", "success"), kb_button("🛑 Стоп охотника")],
        [kb_button("✨ Проверка лотов", "primary"), kb_button("📊 Статус")],
        [kb_button("📚 Мои URL", "primary"), kb_button("♻️ Сбросить историю")],
        [kb_button("🔑 LZT API", "primary")],
        [kb_button("ℹ️ Инфо")],
    ]
    if user_id in OWNER_IDS:
        rows.insert(4, [kb_button("👥 Пользователи", "primary"), kb_button("🔑 Коды доступа", "success")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def kb_lzt_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [kb_button("🔗 Подключить / заменить"), kb_button("🔄 Проверить")],
            [kb_button("🗑 Удалить подключение"), kb_button("⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def kb_urls_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [kb_button("➕ Добавить URL", "success"), kb_button("📄 Список URL")],
            [kb_button("🔁 Вкл/Выкл URL"), kb_button("🛒 Автобай URL", "primary")],
            [kb_button("✏️ Переименовать URL"), kb_button("🗑 Удалить URL", "danger")],
            [kb_button("✅ Тест URL"), kb_button("⬅️ Назад")],
        ],
        resize_keyboard=True,
    )




def _to_bool_label(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    low = str(value).strip().lower()
    if low in {"1", "true", "yes", "on", "enabled", "да"}:
        return "Да"
    if low in {"0", "false", "no", "off", "disabled", "нет"}:
        return "Нет"
    return None


def _format_value(v, limit: int = 140) -> str:
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not v.is_integer():
            return f"{v:.2f}".rstrip("0").rstrip(".")
        return f"{int(v):,}".replace(",", " ")
    s = str(v).strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def sanitize_url_name(raw_name: str | None, fallback: str | None = None) -> str:
    name = (raw_name or "").strip()
    name = re.sub(r"[\x00-\x1f\x7f]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    if not name:
        name = (fallback or "").strip()
    if not name:
        name = f"URL {int(time.time())}"

    if len(name) > MAX_URL_NAME_LEN:
        name = name[:MAX_URL_NAME_LEN].rstrip()

    return name


def _pick_first(item: dict, keys: list[str]):
    for k in keys:
        if k in item and item.get(k) not in (None, ""):
            return item.get(k)
    return None


def _collect_item_specs(item: dict) -> list[str]:
    known_specs = [
        ("🏆 Трофеи", ["trophies", "cups", "brawl_cup", "clash_cup", "rating"]),
        ("🔼 Уровень", ["level", "lvl", "user_level", "genshin_level"]),
        ("🏰 TownHall", ["townhall", "th"]),
        ("🧩 Ранг", ["rank", "elo", "mmr"]),
        ("🎖 Прайм", ["prime", "premium", "vip"]),
        ("📱 Привязка телефона", ["phone_bound", "phone"]),
        ("📧 Привязка почты", ["email_bound", "email"]),
        ("📨 Доступ к почте", ["mail_access", "email_access"]),
        ("🔐 2FA", ["twofa", "2fa", "ga", "guard"]),
        ("🌍 Регион", ["region", "country", "locale", "server"]),
        ("🧭 Платформа", ["platform", "device", "os"]),
        ("🧱 Инвентарь", ["inventory", "inv_value", "skin_count", "items_count"]),
    ]

    specs: list[str] = []
    used: set[str] = set()
    for label, keys in known_specs:
        raw = _pick_first(item, keys)
        if raw is None:
            continue
        for k in keys:
            if k in item:
                used.add(k)

        bool_label = _to_bool_label(raw)
        value = bool_label if bool_label is not None else _format_value(raw)
        specs.append(f"• {label}: <b>{html.escape(value)}</b>")

    ignored = {
        "title", "price", "old_price", "discount", "item_id", "id", "url", "link", "description", "desc",
        "category", "category_name", "game", "type", "seller_id", "owner_id", "user_id", "views", "view_count",
        "likes", "favorites", "fav_count", "published_at", "created_at", "date", "time", "updated_at", "edited_at",
    }
    extras_added = 0
    for k, v in item.items():
        if extras_added >= 8:
            break
        if k in ignored or k in used:
            continue
        if v in (None, "", [], {}):
            continue
        if isinstance(v, (dict, list, tuple, set)):
            continue
        human_key = k.replace("_", " ").strip().title()
        specs.append(f"• {html.escape(human_key)}: <b>{html.escape(_format_value(v, limit=90))}</b>")
        extras_added += 1
    return specs


# ====================== HELPERS ======================
def has_valid_telegram_token(token: str) -> bool:
    if not token:
        return False
    return bool(re.match(r"^\d{6,12}:[A-Za-z0-9_-]{20,}$", token))


async def send_welcome_sticker(chat_id: int):
    if bot is None:
        return
    for st in WELCOME_STICKERS:
        try:
            await bot.send_sticker(chat_id, st)
            return
        except Exception:
            continue


async def safe_delete(message: types.Message):
    try:
        await message.delete()
    except Exception:
        pass


send_locks: dict[int, asyncio.Lock] = {}


def get_send_lock(chat_id: int) -> asyncio.Lock:
    lock = send_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        send_locks[chat_id] = lock
    return lock


async def send_bot_message(chat_id: int, text: str, **kwargs):
    if bot is None:
        raise RuntimeError("Bot не инициализирован")

    lock = get_send_lock(chat_id)
    async with lock:
        for attempt in range(3):
            try:
                msg = await bot.send_message(chat_id, text, **kwargs)
                if TG_SEND_DELAY > 0:
                    await asyncio.sleep(TG_SEND_DELAY)
                return msg
            except TelegramRetryAfter as e:
                await asyncio.sleep(float(getattr(e, "retry_after", 1.5)) + 0.2)
            except (TelegramBadRequest, TelegramForbiddenError):
                raise
            except Exception:
                if attempt >= 2:
                    raise
                await asyncio.sleep(0.01)


def _get_notify_queue(user_id: int) -> asyncio.Queue:
    q = user_notify_queues.get(user_id)
    if q is None:
        q = asyncio.Queue(maxsize=1500)
        user_notify_queues[user_id] = q
    return q


async def _notify_worker_loop(user_id: int):
    q = _get_notify_queue(user_id)
    while user_search_active[user_id] or not q.empty():
        try:
            chat_id, text, kwargs = await asyncio.wait_for(q.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        try:
            await send_bot_message(chat_id, text, **kwargs)
        except Exception as e:
            log_autobuy(f"NOTIFY_SEND_ERR user_id={user_id} err='{_safe_compact(str(e),240)}'")
        finally:
            q.task_done()


def ensure_notify_worker(user_id: int):
    task = user_notify_workers.get(user_id)
    if task and not task.done():
        return
    user_notify_workers[user_id] = asyncio.create_task(_notify_worker_loop(user_id))


def enqueue_hunter_notification(user_id: int, chat_id: int, text: str, **kwargs):
    q = _get_notify_queue(user_id)
    payload = (chat_id, text, kwargs)
    try:
        q.put_nowait(payload)
        return
    except asyncio.QueueFull:
        pass

    dropped = 0
    while q.full() and not q.empty() and dropped < 200:
        try:
            q.get_nowait()
            q.task_done()
            dropped += 1
        except Exception:
            break
    try:
        q.put_nowait(payload)
    except Exception:
        pass
    if dropped:
        log_autobuy(f"NOTIFY_QUEUE_DROP user_id={user_id} dropped={dropped}")


def make_item_key(item: dict) -> str:
    iid = item.get("item_id") or item.get("id")
    if iid is not None:
        return f"id::{str(iid).strip()}"
    title = str(item.get("title") or "").strip()
    price = str(item.get("price") or "")
    return f"noid::{title}::{price}"


def parse_index_from_button(text: str) -> int | None:
    m = re.match(r"^\s*(\d+)\)", text or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


from app.storage.sqlite import (
    db_count_users, db_ensure_user, db_get_role, db_get_urls,
    db_list_users, db_load_buy_attempted, db_load_seen, db_seed_urls_if_empty,
)
from app.services.market_api import fetch_with_retry, get_account_buy_balance_text
# ====================== STATE ======================
user_search_active = defaultdict(lambda: False)
user_hunter_mode = defaultdict(lambda: "off")  # off/classic
user_seen_items = defaultdict(set)
user_buy_attempted = defaultdict(set)
user_buy_inflight = defaultdict(set)
autobuy_queue_manager = UserAutobuyQueueManager(maxsize=2500, workers_per_user=8)
purchase_idempotency = PurchaseIdempotency()
user_hunter_tasks: dict[int, asyncio.Task] = {}
user_hunter_start_locks: dict[int, asyncio.Lock] = {}
user_history_reset_pending = defaultdict(lambda: False)

user_notify_queues: dict[int, asyncio.Queue] = {}
user_notify_workers: dict[int, asyncio.Task] = {}

user_modes = defaultdict(lambda: None)
user_started = set()
user_urls = defaultdict(list)
user_api_errors = defaultdict(int)
user_roles = defaultdict(lambda: "unknown")

user_last_screen_msg_id = defaultdict(lambda: None)
user_no_lots_msg_id = defaultdict(lambda: None)
user_pending_url = defaultdict(lambda: None)
user_pending_rename_url = defaultdict(lambda: None)
user_page_state = defaultdict(lambda: {"ctx": None, "page": 0})

autobuy_endpoint_cache: dict[str, list[str]] = {}
buy_locks: dict[str, asyncio.Lock] = {}
buy_semaphore = asyncio.Semaphore(BUY_SEMAPHORE)


def get_buy_lock(item_key: str) -> asyncio.Lock:
    lock = buy_locks.get(item_key)
    if lock is None:
        lock = asyncio.Lock()
        buy_locks[item_key] = lock
    return lock


def get_user_hunter_start_lock(user_id: int) -> asyncio.Lock:
    lock = user_hunter_start_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        user_hunter_start_locks[user_id] = lock
    return lock


async def delete_last_screen(chat_id: int, user_id: int):
    mid = user_last_screen_msg_id.get(user_id)
    if not mid or bot is None:
        return
    try:
        await bot.delete_message(chat_id, mid)
    except Exception:
        pass
    user_last_screen_msg_id[user_id] = None


async def send_screen(chat_id: int, user_id: int, text: str, reply_markup: ReplyKeyboardMarkup | None = None, parse_mode: str | None = None):
    await delete_last_screen(chat_id, user_id)
    msg = await send_bot_message(
        chat_id,
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )
    user_last_screen_msg_id[user_id] = msg.message_id
    return msg


async def show_denied(user_id: int, chat_id: int):
    await send_screen(chat_id, user_id, DENIED_TEXT, reply_markup=kb_request())


async def upsert_no_lots_message(chat_id: int, user_id: int, text: str):
    if bot is None:
        return

    mid = user_no_lots_msg_id.get(user_id)
    if mid:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=mid,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return
        except TelegramBadRequest:
            pass
        except Exception:
            pass

    try:
        msg = await send_bot_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
        user_no_lots_msg_id[user_id] = msg.message_id
    except Exception:
        pass


def reset_no_lots_message(user_id: int):
    user_no_lots_msg_id[user_id] = None


def build_urls_picker_kb(sources: list[dict], page: int, back_text: str = "⬅️ Назад") -> ReplyKeyboardMarkup:
    total = len(sources)
    if total <= 0:
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=back_text)]], resize_keyboard=True)

    total_pages = (total + URL_PAGE_SIZE - 1) // URL_PAGE_SIZE
    page = max(0, min(page, total_pages - 1))

    start = page * URL_PAGE_SIZE
    end = min(total, start + URL_PAGE_SIZE)
    chunk = sources[start:end]

    rows: list[list[KeyboardButton]] = []
    row: list[KeyboardButton] = []
    for src in chunk:
        idx = src["idx"]
        name = src.get("name") or f"URL #{idx}"
        row.append(KeyboardButton(text=f"{idx}) {name}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if total_pages > 1:
        rows.append([
            KeyboardButton(text="◀️ Назад страница"),
            KeyboardButton(text=f"📄 {page+1}/{total_pages}"),
            KeyboardButton(text="▶️ Далее"),
        ])

    rows.append([KeyboardButton(text=back_text)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def build_users_picker_kb(users: list[tuple[int, int, str]], page: int) -> ReplyKeyboardMarkup:
    total = len(users)
    if total <= 0:
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)

    total_pages = (total + USER_PAGE_SIZE - 1) // USER_PAGE_SIZE
    page = max(0, min(page, total_pages - 1))

    start = page * USER_PAGE_SIZE
    end = min(total, start + USER_PAGE_SIZE)
    chunk = users[start:end]

    rows: list[list[KeyboardButton]] = []
    for uid, allowed, _role in chunk:
        icon = "✅" if allowed else "⛔️"
        rows.append([KeyboardButton(text=f"{icon} {uid}")])

    if total_pages > 1:
        rows.append([
            KeyboardButton(text="◀️ Назад страница"),
            KeyboardButton(text=f"📄 {page+1}/{total_pages}"),
            KeyboardButton(text="▶️ Далее"),
        ])

    rows.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


async def show_urls_list_screen(user_id: int, chat_id: int, page: int = 0):
    sources = await get_all_sources(user_id, enabled_only=False)
    if not sources:
        user_modes[user_id] = None
        user_page_state[user_id] = {"ctx": None, "page": 0}
        await send_screen(chat_id, user_id, "URL пуст. Добавь источник.", reply_markup=kb_urls_menu())
        return

    total_pages = (len(sources) + URL_PAGE_SIZE - 1) // URL_PAGE_SIZE
    page = max(0, min(page, total_pages - 1))

    user_modes[user_id] = "pick_list"
    user_page_state[user_id] = {"ctx": "pick_list", "page": page}

    enabled_count = sum(1 for s in sources if s.get("enabled", True))
    autobuy_count = sum(1 for s in sources if s.get("autobuy", False))
    title = (
        f"📄 <b>Список URL</b> · всего: <b>{len(sources)}</b>\n"
        f"├ 🟢 Активных: <b>{enabled_count}</b>\n"
        f"├ 🛒 С автобаем: <b>{autobuy_count}</b>\n"
        f"└ 📑 Страница: <b>{page + 1}/{total_pages}</b>\n\n"
        "Нажми на нужный URL, чтобы открыть детали."
    )
    await send_screen(chat_id, user_id, title, reply_markup=build_urls_picker_kb(sources, page=page, back_text="⬅️ Назад"), parse_mode="HTML")


async def show_users_screen(user_id: int, chat_id: int, page: int = 0):
    users = await db_list_users(USER_PAGE_SIZE, max(page, 0) * USER_PAGE_SIZE)
    total = await db_count_users()

    if total <= 0:
        user_modes[user_id] = None
        user_page_state[user_id] = {"ctx": None, "page": 0}
        await send_screen(chat_id, user_id, "👥 Пользователей пока нет.", reply_markup=kb_main(user_id))
        return

    total_pages = (total + USER_PAGE_SIZE - 1) // USER_PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    users = await db_list_users(USER_PAGE_SIZE, page * USER_PAGE_SIZE)

    user_modes[user_id] = "users_pick"
    user_page_state[user_id] = {"ctx": "users_pick", "page": page}

    allowed_count = sum(1 for _uid, allowed, _role in users if allowed)
    text = (
        f"👥 Пользователи: {total}\n"
        f"• На странице: {len(users)}\n"
        f"• Разрешено на странице: {allowed_count}\n"
        "Нажми на пользователя, чтобы переключить доступ."
    )
    await send_screen(chat_id, user_id, text, reply_markup=build_users_picker_kb(users, page=page))


async def show_status(user_id: int, chat_id: int):
    sources = await get_all_sources(user_id, enabled_only=False)
    active_sources = sum(1 for s in sources if s.get("enabled", True))
    autobuy_sources = sum(1 for s in sources if s.get("autobuy", False))
    hunter_state = "🟢 Запущен" if user_hunter_mode.get(user_id) == "classic" and user_search_active.get(user_id) else "🔴 Остановлен"
    balance_text = await get_account_buy_balance_text(user_id=user_id)

    text = render_status_card(
        total_sources=len(sources),
        active_sources=active_sources,
        autobuy_sources=autobuy_sources,
        hunter_state=hunter_state,
        api_errors=user_api_errors.get(user_id, 0),
        balance_text=balance_text,
    )
    await send_screen(chat_id, user_id, text, reply_markup=kb_main(user_id), parse_mode="HTML")


def parse_user_id_from_button(text: str) -> int | None:
    m = re.search(r"(\d{5,})", text or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


# ====================== LOAD USER DATA ======================
async def load_user_data(user_id: int, force: bool = False):
    if user_id in user_started and not force:
        return
    await db_ensure_user(user_id)
    await db_seed_urls_if_empty(user_id)
    user_urls[user_id] = await db_get_urls(user_id)
    user_seen_items[user_id] = await db_load_seen(user_id)
    user_buy_attempted[user_id] = await db_load_buy_attempted(user_id)
    user_roles[user_id] = await db_get_role(user_id)
    user_started.add(user_id)


async def get_user_role(user_id: int) -> str | None:
    await load_user_data(user_id)
    role = user_roles.get(user_id, "unknown")
    return None if role == "unknown" else role


async def user_url_limit(user_id: int) -> int:
    role = await get_user_role(user_id)
    return MAX_URLS_PER_USER_LIMITED if role == "limited" else MAX_URLS_PER_USER_DEFAULT


async def user_hunter_interval(user_id: int) -> float:
    role = await get_user_role(user_id)
    extra = LIMITED_EXTRA_DELAY if role == "limited" else 0.0
    return HUNTER_INTERVAL_BASE + extra


# ====================== SOURCES ======================
async def get_all_sources(user_id: int, enabled_only: bool = False):
    await load_user_data(user_id)

    deduped = []
    seen = set()
    for src in user_urls[user_id]:
        u = src.get("url")
        if not u or u in seen:
            continue
        seen.add(u)
        deduped.append(src)
    user_urls[user_id] = deduped

    out = []
    for i, s in enumerate(user_urls[user_id], start=1):
        if enabled_only and not s.get("enabled", True):
            continue
        out.append({**s, "idx": i})
    return out


def _build_source_info(src: dict) -> dict:
    url = src["url"]
    return {
        "idx": src["idx"],
        "url": url,
        "name": src.get("name") or f"URL #{src['idx']}",
        "enabled": src.get("enabled", True),
        "autobuy": src.get("autobuy", False),
    }


async def _fetch_source_items(src: dict, user_id: int):
    source_info = _build_source_info(src)
    items, err = await fetch_with_retry(source_info["url"], user_id=user_id)
    return source_info, items, err


async def fetch_all_sources(user_id: int):
    sources = await get_all_sources(user_id, enabled_only=True)
    if not sources:
        return [], []

    sources.sort(key=lambda s: (not bool(s.get("autobuy", False)), s.get("idx", 0)))
    items_with_sources = []
    errors = []
    async for res in _run_bounded(sources, lambda src: _fetch_source_items(src, user_id)):
        if isinstance(res, Exception):
            errors.append(("UNKNOWN", "UNKNOWN", str(res)))
            continue
        source_info, items, err = res
        if err:
            errors.append((source_info["name"], source_info["url"], err))
            continue
        items_with_sources.extend((it, source_info) for it in items)
    return items_with_sources, errors


async def iter_sources_results(user_id: int):
    sources = await get_all_sources(user_id, enabled_only=True)
    if not sources:
        return
    sources.sort(key=lambda s: (not bool(s.get("autobuy", False)), s.get("idx", 0)))
    async for result in _run_bounded(sources, _fetch_source_items):
        yield result


async def iter_sources_results_split(user_id: int, include_non_autobuy: bool):
    sources = await get_all_sources(user_id, enabled_only=True)
    if not sources:
        return
    autobuy_sources = [s for s in sources if s.get("autobuy", False)]
    plain_sources = [s for s in sources if not s.get("autobuy", False)]

    async for result in _run_bounded(autobuy_sources, lambda src: _fetch_source_items(src, user_id)):
        yield result
    if include_non_autobuy:
        async for result in _run_bounded(plain_sources, lambda src: _fetch_source_items(src, user_id)):
            yield result


async def send_compact_10_for_user(user_id: int, chat_id: int):
    sources = await get_all_sources(user_id, enabled_only=True)
    if not sources:
        await send_screen(chat_id, user_id, "❌ Нет активных URL.", reply_markup=kb_main(user_id))
        return
    items_with_sources, errors = await fetch_all_sources(user_id)
    if not items_with_sources:
        detail = "❌ Свежих лотов не найдено."
        if errors:
            detail += f"\nОшибок источников: {len(errors)}"
        await send_screen(chat_id, user_id, detail, reply_markup=kb_main(user_id))
        return
    for item, source in items_with_sources[:10]:
        try:
            await send_bot_message(chat_id, make_card(item, source.get("name") or "Источник"), parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            log_autobuy(f"LOT_CHECK_SEND_ERR user_id={user_id} err='{_safe_compact(str(e),240)}'")


async def send_test_for_single_url(user_id: int, chat_id: int, source: dict):
    source_info = _build_source_info(source)
    items, err = await fetch_with_retry(source_info["url"], max_retries=2, user_id=user_id)
    if err:
        await send_screen(chat_id, user_id, f"❌ Ошибка проверки URL:\n{html.escape(str(err))}", reply_markup=kb_urls_menu())
        return
    if not items:
        await send_screen(chat_id, user_id, f"✅ URL отвечает, но лотов сейчас нет.\n<code>{html.escape(source_info['url'])}</code>", reply_markup=kb_urls_menu(), parse_mode="HTML")
        return
    await send_screen(chat_id, user_id, f"✅ URL отвечает. Найдено лотов: <b>{len(items)}</b>\nПоказываю первый.", reply_markup=kb_urls_menu(), parse_mode="HTML")
    await send_bot_message(chat_id, make_card(items[0], source_info["name"]), parse_mode="HTML", disable_web_page_preview=True)


# ====================== DISPLAY ======================
def make_card(item: dict, source_name: str) -> str:
    title = str(item.get("title", "Без названия"))
    price = item.get("price", None)
    old_price = item.get("old_price") or item.get("original_price")
    discount = item.get("discount")
    item_id = item.get("item_id") or item.get("id")

    seller_id = item.get("seller_id") or item.get("owner_id") or item.get("user_id")
    category = item.get("category") or item.get("category_name") or item.get("game") or item.get("type")
    published_at = item.get("published_at") or item.get("created_at") or item.get("date") or item.get("time")
    updated_at = item.get("updated_at") or item.get("edited_at")
    views = item.get("views") or item.get("view_count")
    likes = item.get("likes") or item.get("favorites") or item.get("fav_count")

    desc = item.get("description") or item.get("desc") or ""
    if isinstance(desc, str):
        desc = html.unescape(desc).strip()
    else:
        desc = ""

    direct_url = item.get("url") or item.get("link") or None

    def _fmt_time(x):
        try:
            if isinstance(x, (int, float)) and x > 0:
                return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(x)))
        except Exception:
            pass
        return str(x) if x is not None else None

    link = direct_url or (f"https://lzt.market/{item_id}" if item_id is not None else None)

    lines = []
    lines.append("╔══════ 🎐 Карточка лота 🎐 ══════╗")
    lines.append(f"🎯 <b>{html.escape(title)}</b>")
    lines.append(f"📦 Источник: <b>{html.escape(str(source_name or 'Источник'))}</b>")

    pricing = []
    if price is not None and price != "—":
        pricing.append(f"💰 Цена: <b>{html.escape(_format_value(price))} ₽</b>")
    if old_price not in (None, ""):
        pricing.append(f"🏷 Старая цена: <b>{html.escape(_format_value(old_price))} ₽</b>")
    if discount not in (None, ""):
        pricing.append(f"📉 Скидка: <b>{html.escape(_format_value(discount))}</b>")
    if pricing:
        lines.extend(pricing)

    main_meta = []
    if category:
        main_meta.append(f"🎮 Категория: <b>{html.escape(str(category))}</b>")
    if item_id is not None:
        main_meta.append(f"🆔 Лот: <code>{html.escape(str(item_id))}</code>")
    if seller_id is not None:
        main_meta.append(f"👤 Продавец: <code>{html.escape(str(seller_id))}</code>")
    if views is not None:
        main_meta.append(f"👁 Просмотры: <b>{html.escape(_format_value(views))}</b>")
    if likes is not None:
        main_meta.append(f"⭐ Избранное: <b>{html.escape(_format_value(likes))}</b>")
    lines.extend(main_meta)

    timing = []
    if published_at is not None:
        timing.append(f"🕒 Опубликован: <b>{html.escape(_fmt_time(published_at))}</b>")
    if updated_at is not None:
        timing.append(f"♻️ Обновлён: <b>{html.escape(_fmt_time(updated_at))}</b>")
    if timing:
        lines.extend(timing)

    specs = _collect_item_specs(item)
    if specs:
        lines.append("")
        lines.append("🧾 <b>Подробности:</b>")
        lines.extend(specs)

    if link:
        lines.append("")
        lines.append(f"🔗 Ссылка: {html.escape(link)}")

    if desc:
        clean = re.sub(r"\s{3,}", "  ", desc).strip()
        if len(clean) > 1200:
            clean = clean[:1200] + "…"
        lines.append("")
        lines.append("📝 <b>Описание:</b>")
        lines.append(html.escape(clean))
    lines.append("╚══════════════════════════════════╝")

    card = "\n".join(lines)
    if len(card) > SHORT_CARD_MAX:
        return card[: SHORT_CARD_MAX - 120] + "\n… <i>(часть текста скрыта из-за лимита Telegram)</i>\n╚══════════════════════════════════╝"
    return card



