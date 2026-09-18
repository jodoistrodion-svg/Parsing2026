from __future__ import annotations

from app.application import *

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    await load_user_data(user_id, force=True)

    await send_welcome_sticker(message.chat.id)
    await send_bot_message(message.chat.id, START_MSG_1, disable_web_page_preview=True)
    allowed = await db_is_allowed(user_id)

    if allowed:
        await send_bot_message(message.chat.id, START_MSG_2, reply_markup=kb_main(user_id), disable_web_page_preview=True, parse_mode="HTML")
    else:
        await send_bot_message(message.chat.id, START_MSG_2, disable_web_page_preview=True, parse_mode="HTML")
        await show_denied(user_id, message.chat.id)

    user_last_screen_msg_id[user_id] = None
    await safe_delete(message)


@dp.message(Command("health"))
async def health_cmd(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    await load_user_data(user_id)
    user_balance_cache[0] = {"text": "—", "ts": 0}
    await show_status(user_id, chat_id)
    await safe_delete(message)


@dp.message()
async def buttons_handler(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    await load_user_data(user_id)

    text = (message.text or "").strip()
    norm_cmd = _normalize_command_text(text)
    mode = user_modes[user_id]

    if norm_cmd == "start":
        await send_welcome_sticker(chat_id)
        await send_bot_message(chat_id, START_MSG_1, disable_web_page_preview=True)
        allowed = await db_is_allowed(user_id)
        if allowed:
            await send_screen(chat_id, user_id, START_MSG_2, reply_markup=kb_main(user_id), disable_web_page_preview=True, parse_mode="HTML")
        else:
            await send_bot_message(chat_id, START_MSG_2, disable_web_page_preview=True, parse_mode="HTML")
            await show_denied(user_id, chat_id)
        return await safe_delete(message)

    allowed = await db_is_allowed(user_id)
    if not allowed and user_id not in OWNER_IDS:
        if text == "🔓 Запрос на бота":
            now = int(time.time())
            last = await db_get_last_request_ts(user_id)
            if now - last < 60:
                await send_screen(chat_id, user_id, "⏳ Запрос уже отправлен. Подожди немного.", reply_markup=kb_request())
                return await safe_delete(message)

            await db_set_last_request_ts(user_id, now)
            try:
                await send_bot_message(
                    OWNER_ID,
                    f"🔔 <b>Запрос доступа</b>\nПользователь: <code>{user_id}</code>\n\nОткрой 👥 Пользователи и нажми на него, чтобы разрешить.",
                    parse_mode="HTML",
                )
            except Exception:
                pass

            await send_screen(chat_id, user_id, "✅ Запрос отправлен. Жди разрешения.", reply_markup=kb_request())
            return await safe_delete(message)

        await show_denied(user_id, chat_id)
        return await safe_delete(message)

    try:
        if text in ("◀️ Назад страница", "▶️ Далее") and user_page_state[user_id].get("ctx"):
            ctx = user_page_state[user_id]["ctx"]
            page = int(user_page_state[user_id]["page"])

            if ctx == "users_pick":
                total = await db_count_users()
                total_pages = (total + USER_PAGE_SIZE - 1) // USER_PAGE_SIZE if total else 1
                page = max(0, min(page + (-1 if text == "◀️ Назад страница" else 1), total_pages - 1))
                await show_users_screen(user_id, chat_id, page=page)
                return await safe_delete(message)

            sources = await get_all_sources(user_id, enabled_only=False)
            total_pages = (len(sources) + URL_PAGE_SIZE - 1) // URL_PAGE_SIZE if sources else 1
            page = max(0, min(page + (-1 if text == "◀️ Назад страница" else 1), total_pages - 1))
            user_page_state[user_id] = {"ctx": ctx, "page": page}

            if ctx == "pick_list":
                await show_urls_list_screen(user_id, chat_id, page=page)
                return await safe_delete(message)

            kb = build_urls_picker_kb(sources, page=page, back_text="⬅️ Назад")
            title = {
                "pick_autobuy": "🛒 Выбери URL для переключения автобая",
                "pick_toggle": "🔁 Выбери URL для ВКЛ/ВЫКЛ",
                "pick_delete": "🗑 Выбери URL для удаления",
                "pick_rename": "✏️ Выбери URL для переименования",
                "pick_test": "✅ Выбери URL для теста",
            }.get(ctx, "Выбери URL")
            user_modes[user_id] = ctx
            await send_screen(chat_id, user_id, title, reply_markup=kb)
            return await safe_delete(message)

        if mode == "users_pick" and user_id in OWNER_IDS:
            if text == "⬅️ Назад":
                user_modes[user_id] = None
                user_page_state[user_id] = {"ctx": None, "page": 0}
                await send_screen(chat_id, user_id, "🧭 <b>Главное меню</b>", reply_markup=kb_main(user_id), parse_mode="HTML")
                return await safe_delete(message)

            target_uid = parse_user_id_from_button(text)
            if target_uid is None:
                return await safe_delete(message)

            await db_ensure_user(target_uid)
            new_allowed = await db_toggle_allowed(target_uid)

            try:
                if new_allowed:
                    await send_bot_message(target_uid, "✅ Доступ к боту разрешён владельцем.\nНажми /start")
                else:
                    await send_bot_message(target_uid, "⛔️ Доступ к боту отключён владельцем.\nЧтобы запросить снова — нажми /start и кнопку запроса.")
            except Exception:
                pass

            page = int(user_page_state[user_id].get("page", 0))
            await show_users_screen(user_id, chat_id, page=page)
            return await safe_delete(message)

        if mode == "add_url_url":
            user_modes[user_id] = None
            url = normalize_url(text)
            ok, err = validate_market_url(url)
            if not ok:
                await send_screen(chat_id, user_id, err, reply_markup=kb_urls_menu())
                return await safe_delete(message)

            limit = await user_url_limit(user_id)
            if len(await get_all_sources(user_id, enabled_only=False)) >= limit:
                await send_screen(chat_id, user_id, f"❌ Достигнут лимит URL: {limit}", reply_markup=kb_urls_menu())
                return await safe_delete(message)

            _items, api_err = await fetch_with_retry(url, max_retries=4, request_timeout=max(FETCH_TIMEOUT, USER_ACTION_FETCH_TIMEOUT))
            if api_err:
                await send_screen(chat_id, user_id, f"❌ Не удалось проверить URL через API.\nПричина: {api_err}\n\nПопробуй ещё раз — теперь бот делает больше ретраев и ждёт ответ дольше.", reply_markup=kb_urls_menu())
                return await safe_delete(message)

            user_pending_url[user_id] = url
            user_modes[user_id] = "add_url_name"
            await send_screen(chat_id, user_id, "✏️ Введи название для этого URL:", reply_markup=kb_urls_menu())
            return await safe_delete(message)

        if mode == "add_url_name":
            name = sanitize_url_name(text)
            url = user_pending_url.get(user_id)
            user_pending_url[user_id] = None
            user_modes[user_id] = None

            if not url:
                await send_screen(chat_id, user_id, "⚠️ Не нашёл ожидаемый URL. Нажми ➕ Добавить URL ещё раз.", reply_markup=kb_urls_menu())
                return await safe_delete(message)

            await db_add_url(user_id, url, name)
            user_urls[user_id] = await db_get_urls(user_id)
            await send_screen(chat_id, user_id, f"✅ URL добавлен: <b>{html.escape(name)}</b>", reply_markup=kb_urls_menu(), parse_mode="HTML")
            return await safe_delete(message)

        if mode == "rename_url_name":
            new_name = sanitize_url_name(text)
            user_modes[user_id] = None
            url = user_pending_rename_url.get(user_id)
            user_pending_rename_url[user_id] = None

            if not url:
                await send_screen(chat_id, user_id, "⚠️ Не нашёл URL для переименования. Повтори ✏️ Переименовать URL.", reply_markup=kb_urls_menu())
                return await safe_delete(message)
            await db_set_url_name(user_id, url, new_name)
            user_urls[user_id] = await db_get_urls(user_id)
            await send_screen(chat_id, user_id, f"✅ Переименовано в: <b>{html.escape(new_name)}</b>", reply_markup=kb_urls_menu(), parse_mode="HTML")
            return await safe_delete(message)

        if mode and mode.startswith("pick_"):
            if text == "⬅️ Назад":
                user_modes[user_id] = None
                user_page_state[user_id] = {"ctx": None, "page": 0}
                await send_screen(chat_id, user_id, "📚 <b>Меню URL</b>\nВыбери действие кнопками ниже.", reply_markup=kb_urls_menu(), parse_mode="HTML")
                return await safe_delete(message)

            idx = parse_index_from_button(text)
            if idx is None:
                return await safe_delete(message)

            sources = await get_all_sources(user_id, enabled_only=False)
            src = next((s for s in sources if s["idx"] == idx), None)
            if not src:
                await send_screen(chat_id, user_id, "❌ Не нашёл этот URL. Открой список заново.", reply_markup=kb_urls_menu())
                return await safe_delete(message)

            name = src.get("name") or f"URL #{idx}"

            if mode == "pick_list":
                detail = (
                    f"<b>{html.escape(name)}</b>\n"
                    f"• Статус: {'🟢 ВКЛ' if src.get('enabled', True) else '🔴 ВЫКЛ'}\n"
                    f"• Автобай: {'🛒 ВКЛ' if src.get('autobuy', False) else '— ВЫКЛ'}\n"
                    f"• API URL:\n<code>{html.escape(src['url'])}</code>\n"
                    f"• Рекомендация: {'✅ Готов к охоте' if src.get('enabled', True) else '⚠️ Выключен, новые лоты не придут'}"
                )
                page = user_page_state[user_id].get("page", 0)
                kb = build_urls_picker_kb(sources, page=page, back_text="⬅️ Назад")
                await send_screen(chat_id, user_id, detail, reply_markup=kb, parse_mode="HTML")
                return await safe_delete(message)

            if mode == "pick_autobuy":
                new_ab = not src.get("autobuy", False)
                await db_set_url_autobuy(user_id, src["url"], new_ab)
                user_urls[user_id] = await db_get_urls(user_id)
                user_modes[user_id] = None
                user_page_state[user_id] = {"ctx": None, "page": 0}
                await send_screen(chat_id, user_id, f"🛒 <b>{html.escape(name)}</b>: {'ВКЛ' if new_ab else 'ВЫКЛ'}", reply_markup=kb_urls_menu(), parse_mode="HTML")
                return await safe_delete(message)

            if mode == "pick_toggle":
                new_enabled = not src.get("enabled", True)
                await db_set_url_enabled(user_id, src["url"], new_enabled)
                user_urls[user_id] = await db_get_urls(user_id)
                user_modes[user_id] = None
                user_page_state[user_id] = {"ctx": None, "page": 0}
                await send_screen(chat_id, user_id, f"🔁 <b>{html.escape(name)}</b>: {'ВКЛ' if new_enabled else 'ВЫКЛ'}", reply_markup=kb_urls_menu(), parse_mode="HTML")
                return await safe_delete(message)

            if mode == "pick_delete":
                await db_remove_url(user_id, src["url"])
                user_urls[user_id] = await db_get_urls(user_id)
                exists_after = any(x.get("url") == src["url"] for x in user_urls[user_id])
                user_modes[user_id] = None
                user_page_state[user_id] = {"ctx": None, "page": 0}
                if exists_after:
                    await send_screen(chat_id, user_id, f"❌ Не удалось удалить: <b>{html.escape(name)}</b>", reply_markup=kb_urls_menu(), parse_mode="HTML")
                else:
                    await send_screen(chat_id, user_id, f"🗑 Удалено: <b>{html.escape(name)}</b>\nОсталось URL: <b>{len(user_urls[user_id])}</b>", reply_markup=kb_urls_menu(), parse_mode="HTML")
                return await safe_delete(message)

            if mode == "pick_test":
                user_modes[user_id] = None
                user_page_state[user_id] = {"ctx": None, "page": 0}
                await send_test_for_single_url(user_id, chat_id, src)
                return await safe_delete(message)

            if mode == "pick_rename":
                user_pending_rename_url[user_id] = src["url"]
                user_modes[user_id] = "rename_url_name"
                user_page_state[user_id] = {"ctx": None, "page": 0}
                await send_screen(chat_id, user_id, f"✏️ Новое название для <b>{html.escape(name)}</b>:", reply_markup=kb_urls_menu(), parse_mode="HTML")
                return await safe_delete(message)

        if text == "👥 Пользователи" and user_id in OWNER_IDS:
            await show_users_screen(user_id, chat_id, page=0)
            return await safe_delete(message)

        if text == "ℹ️ Инфо":
            await send_screen(
                chat_id,
                user_id,
                "ℹ️ Управление только нижними кнопками.\n"
                "📚 Мои URL → управление источниками.\n"
                "🚀 Старт охотника → максимально быстрый классический режим.\n"
                "🛒 Обычный автобай включается по конкретному URL.\n\n"
                f"✏️ Названия URL автоматически очищаются и ограничены {MAX_URL_NAME_LEN} символами.\n"
                f"🧾 Лог автобая: {AUTOBUY_LOG_FILE}",
                reply_markup=kb_main(user_id),
                parse_mode="HTML",
            )
            return await safe_delete(message)

        if text == "📊 Статус" or norm_cmd == "status":
            await show_status(user_id, chat_id)
            return await safe_delete(message)

        if norm_cmd == "menu":
            await send_screen(chat_id, user_id, "🧭 <b>Главное меню</b>", reply_markup=kb_main(user_id), parse_mode="HTML")
            return await safe_delete(message)

        if text == "✨ Проверка лотов":
            await send_compact_10_for_user(user_id, chat_id)
            return await safe_delete(message)

        if text == "♻️ Сбросить историю":
            user_seen_items[user_id].clear()
            user_buy_attempted[user_id].clear()
            user_history_reset_pending[user_id] = True
            await db_clear_seen(user_id)
            await db_clear_buy_attempted(user_id)
            await send_screen(chat_id, user_id, "♻️ История сброшена. Следующий запуск охотника обработает все лоты как новые (включая автобай по URL, где он активен).", reply_markup=kb_main(user_id))
            return await safe_delete(message)

        if text == "🚀 Старт охотника" or norm_cmd == "hunter_start":
            requested_mode = "classic"
            lock = get_user_hunter_start_lock(user_id)
            async with lock:
                active_sources = await get_all_sources(user_id, enabled_only=True)
                if not active_sources:
                    await send_screen(chat_id, user_id, "❌ Нет активных URL. Зайди в 📚 Мои URL и добавь источник.", reply_markup=kb_main(user_id))
                    return await safe_delete(message)

                task = user_hunter_tasks.get(user_id)
                if task and not task.done():
                    await send_screen(chat_id, user_id, "⚠️ Охотник уже запущен. Сначала останови его.", reply_markup=kb_main(user_id))
                    return await safe_delete(message)

                user_search_active[user_id] = True
                user_hunter_mode[user_id] = requested_mode
                user_seen_items[user_id] = await db_load_seen(user_id)
                user_buy_attempted[user_id] = await db_load_buy_attempted(user_id)

                if not user_seen_items[user_id] and user_history_reset_pending[user_id]:
                    log_autobuy(f"HUNTER_RESET_MODE user_id={user_id} mode={requested_mode} treat_all_as_new=1")

                user_history_reset_pending[user_id] = False

                task = asyncio.create_task(hunter_loop_for_user(user_id, chat_id))
                user_hunter_tasks[user_id] = task

                log_autobuy(f"HUNTER_START user_id={user_id} active_urls={len(active_sources)} interval={HUNTER_INTERVAL_BASE}")
                await send_screen(chat_id, user_id, f"🚀 Охотник запущен! Активных URL: {len(active_sources)}\nИнтервал цикла: {HUNTER_INTERVAL_BASE:.2f} сек", reply_markup=kb_main(user_id))
                return await safe_delete(message)

        if text == "🛑 Стоп охотника" or norm_cmd == "hunter_stop":
            user_search_active[user_id] = False
            user_hunter_mode[user_id] = "off"
            task = user_hunter_tasks.get(user_id)
            if task:
                task.cancel()
                user_hunter_tasks.pop(user_id, None)
            log_autobuy(f"HUNTER_STOP user_id={user_id}")
            await send_screen(chat_id, user_id, "🛑 Охотник остановлен.", reply_markup=kb_main(user_id))
            return await safe_delete(message)

        if text == "📚 Мои URL":
            user_modes[user_id] = None
            user_page_state[user_id] = {"ctx": None, "page": 0}
            await send_screen(chat_id, user_id, "📚 <b>Меню URL</b>\nВыбери действие кнопками ниже.", reply_markup=kb_urls_menu(), parse_mode="HTML")
            return await safe_delete(message)

        if text == "⬅️ Назад":
            user_modes[user_id] = None
            user_page_state[user_id] = {"ctx": None, "page": 0}
            await send_screen(chat_id, user_id, "🧭 <b>Главное меню</b>", reply_markup=kb_main(user_id), parse_mode="HTML")
            return await safe_delete(message)

        if text == "📄 Список URL":
            await show_urls_list_screen(user_id, chat_id, page=0)
            return await safe_delete(message)

        if text == "➕ Добавить URL":
            user_modes[user_id] = "add_url_url"
            user_page_state[user_id] = {"ctx": None, "page": 0}
            await send_screen(chat_id, user_id, "➕ <b>Добавление источника</b>\nВставь API URL:\n<code>prod-api.lzt.market</code> / <code>api.lzt.market</code> / <code>api.lolz.live</code>", reply_markup=kb_urls_menu(), parse_mode="HTML")
            return await safe_delete(message)

        if text == "🛒 Автобай URL":
            sources = await get_all_sources(user_id, enabled_only=False)
            if not sources:
                await send_screen(chat_id, user_id, "URL пуст. Добавь источник.", reply_markup=kb_urls_menu())
                return await safe_delete(message)
            user_modes[user_id] = "pick_autobuy"
            user_page_state[user_id] = {"ctx": "pick_autobuy", "page": 0}
            await send_screen(chat_id, user_id, "🛒 Выбери URL для переключения автобая:", reply_markup=build_urls_picker_kb(sources, page=0, back_text="⬅️ Назад"))
            return await safe_delete(message)

        if text == "✏️ Переименовать URL":
            sources = await get_all_sources(user_id, enabled_only=False)
            if not sources:
                await send_screen(chat_id, user_id, "URL пуст. Добавь источник.", reply_markup=kb_urls_menu())
                return await safe_delete(message)
            user_modes[user_id] = "pick_rename"
            user_page_state[user_id] = {"ctx": "pick_rename", "page": 0}
            await send_screen(chat_id, user_id, "✏️ Выбери URL для переименования:", reply_markup=build_urls_picker_kb(sources, page=0, back_text="⬅️ Назад"))
            return await safe_delete(message)

        if text == "🗑 Удалить URL":
            sources = await get_all_sources(user_id, enabled_only=False)
            if not sources:
                await send_screen(chat_id, user_id, "URL пуст. Добавь источник.", reply_markup=kb_urls_menu())
                return await safe_delete(message)
            user_modes[user_id] = "pick_delete"
            user_page_state[user_id] = {"ctx": "pick_delete", "page": 0}
            await send_screen(chat_id, user_id, "🗑 Выбери URL для удаления:", reply_markup=build_urls_picker_kb(sources, page=0, back_text="⬅️ Назад"))
            return await safe_delete(message)

        if text == "🔁 Вкл/Выкл URL":
            sources = await get_all_sources(user_id, enabled_only=False)
            if not sources:
                await send_screen(chat_id, user_id, "URL пуст. Добавь источник.", reply_markup=kb_urls_menu())
                return await safe_delete(message)
            user_modes[user_id] = "pick_toggle"
            user_page_state[user_id] = {"ctx": "pick_toggle", "page": 0}
            await send_screen(chat_id, user_id, "🔁 Выбери URL для ВКЛ/ВЫКЛ:", reply_markup=build_urls_picker_kb(sources, page=0, back_text="⬅️ Назад"))
            return await safe_delete(message)

        if text == "✅ Тест URL":
            sources = await get_all_sources(user_id, enabled_only=False)
            if not sources:
                await send_screen(chat_id, user_id, "URL пуст. Добавь источник.", reply_markup=kb_urls_menu())
                return await safe_delete(message)
            user_modes[user_id] = "pick_test"
            user_page_state[user_id] = {"ctx": "pick_test", "page": 0}
            await send_screen(chat_id, user_id, "✅ Выбери URL для теста:", reply_markup=build_urls_picker_kb(sources, page=0, back_text="⬅️ Назад"))
            return await safe_delete(message)

        if text and not text.startswith("/"):
            await asyncio.sleep(0.01)
            await safe_delete(message)

    except Exception as e:
        try:
            await send_screen(
                chat_id,
                user_id,
                f"❌ Ошибка: {html.escape(str(e))}\n\nПанель восстановлена — попробуй ещё раз.",
                reply_markup=kb_main(user_id),
                parse_mode="HTML",
            )
        except Exception:
            pass
        await safe_delete(message)


# Application composition lives here; main.py is only the process entry point.
