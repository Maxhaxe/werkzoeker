FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=10000 \
    MAX_PAGES_PER_SCRAPER=3 \
    MAX_CONCURRENT_SCRAPERS=2 \
    REQUEST_TIMEOUT=15

# Install system dependencies needed for lxml and c-extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose health port for cloud hosts (Render, Railway, Koyeb, Fly)
EXPOSE 10000

CMD ["python", "main.py", "--listen"]
