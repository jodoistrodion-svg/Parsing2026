FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

COPY requirements.txt .
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY . .

RUN mkdir -p /data /app/logs && chown -R appuser:appuser /app /data

USER appuser

ENV DB_FILE=/data/bot_data.sqlite     HEALTH_HOST=0.0.0.0     HEALTH_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3   CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)" || exit 1

CMD ["python", "main.py"]
