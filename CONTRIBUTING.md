# Contributing

## Local setup

Python 3.12+ is recommended.

PowerShell:

    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt

Copy env.example to .env and keep secrets local.

## Required checks

    python -m compileall -q .
    python -m pytest -q
    python -m pyflakes .
    python -m ruff check .

For formatting:

    python -m ruff format .

Do not commit .env, SQLite databases, logs or virtual environments.
