# Parsing2026

Асинхронный Telegram-бот для мониторинга источников LZT Market и обработки автобая.

## Запуск

1. Python 3.12.
2. `python -m pip install -r requirements.txt`
3. Скопируй `.env.example` в `.env`.
4. Заполни `API_TOKEN`, `LZT_API_KEY` и `OWNER_ID`.
5. По умолчанию `ACCESS_MODE=closed`.
6. `python main.py`

## Структура

`main.py` — compatibility shell; hot-path компоненты находятся в пакетах `bot/`, `buyer/`, `domain/`, `filters/`, `market/`, `purchase/`, `services/`.

## Проверки

`python -m compileall -q .`

`python -m pytest -q`

GitHub Actions выполняет compile + pytest на Python 3.12.

## Безопасность

Секреты не хранятся в Git. Используй только placeholders в `.env.example`.

В старом `env.example` были опубликованы реальные Telegram/LZT credentials. Удаление значения из текущей ветки не отзывает и не удаляет его из истории Git. Эти credentials необходимо отозвать и перевыпустить у провайдеров.
