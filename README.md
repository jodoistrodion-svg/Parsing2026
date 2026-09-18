# Parsing2026

Асинхронный Telegram-бот для мониторинга источников LZT Market и обработки автобая.

## Запуск

1. Python 3.12.
2. `python -m pip install -r requirements.txt`
3. Для разработки и тестов: `python -m pip install -r requirements-dev.txt`
4. Скопируй `env.example` в `.env`.
5. Заполни `API_TOKEN` и `OWNER_ID`. `LZT_API_KEY` нужен только для функций, которые обращаются к защищённому API LZT.
6. По умолчанию `ACCESS_MODE=closed`.
7. `python main.py`

## Структура

`main.py` — process entry point. `app/application.py` — composition root. `app/runtime/core.py` — application runtime/state and orchestration helpers. `app/handlers.py` — Telegram handlers. `app/purchase/autobuy.py` — autobuy lifecycle/hot path. Infrastructure is isolated in `app/services/`, `app/storage/`, `market/`, `buyer/`, `purchase/`, `domain/`, `filters/`.

## Проверки

`python -m compileall -q .`

`python -m pytest -q`

GitHub Actions выполняет compile + pytest на Python 3.12.
Для локальной проверки используй:
`python -m compileall -q .`
`python -m pytest -q`

## Безопасность

Секреты не хранятся в Git. Используй только placeholders в `env.example`.

В старом `env.example` были опубликованы реальные Telegram/LZT credentials. Удаление значения из текущей ветки не отзывает и не удаляет его из истории Git. Эти credentials необходимо отозвать и перевыпустить у провайдеров.
