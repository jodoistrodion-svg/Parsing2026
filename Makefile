.PHONY: install dev test lint format audit check run

install:
	python -m pip install -r requirements.txt

dev:
	python -m pip install -r requirements.txt -r requirements-dev.txt

test:
	python -m pytest -q

lint:
	python -m pyflakes .
	python -m ruff check .

format:
	python -m ruff format .

audit:
	python -m pip_audit -r requirements.txt

check: lint test

run:
	python main.py
