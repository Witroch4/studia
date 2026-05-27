# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Dependências de sistema mínimas para chromium + build
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget gnupg \
        libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdbus-1-3 \
        libdrm2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libxkbcommon0 libx11-6 libxcomposite1 libxdamage1 libxext6 \
        libxfixes3 libxrandr2 libxss1 libxtst6 fonts-liberation \
        libappindicator3-1 libu2f-udev libvulkan1 xdg-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==1.8.5"

COPY pyproject.toml /app/
RUN poetry install --no-root --without dev 2>/dev/null || poetry install --no-root

# Instala Chromium para o Playwright (somente chromium, sem firefox/webkit)
RUN playwright install --with-deps chromium

COPY app /app/app

EXPOSE 8090

CMD ["python", "-m", "app.main", "api-serve", "--host", "0.0.0.0", "--port", "8090"]
