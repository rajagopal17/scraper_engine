FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
# Split into separate RUN layers so a transient stall in one (common on Docker
# Desktop/WSL2's network path to pythonhosted.org on large wheels) doesn't
# force redownloading everything on retry. Timeout/retries raised because the
# playwright wheel (~53MB) has been observed stalling to ~10 kB/s mid-download.
RUN pip install --no-cache-dir --retries 15 --default-timeout 300 -r requirements.txt
# python:3.11-slim-bookworm doesn't ship libatomic1, which playwright's bundled
# Node driver needs to even start ("libatomic.so.1: cannot open shared object
# file") — install it before playwright's own --with-deps (that flag covers
# Chromium's deps, not the driver's).
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/*
RUN playwright install --with-deps chromium

COPY scraper_engine/ scraper_engine/
COPY sql/ sql/

ENTRYPOINT ["python", "-m", "scraper_engine"]
CMD ["status"]
