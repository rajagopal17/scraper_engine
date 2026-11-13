FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY scraper_engine/ scraper_engine/
COPY sql/ sql/

ENTRYPOINT ["python", "-m", "scraper_engine"]
CMD ["status"]
