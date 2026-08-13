FROM python:3.11-slim

WORKDIR /app

# Install dependencies first — this layer is cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run as a non-root user. The data directory is writable because the app
# creates history.db there and the bootstrap step may download into it.
RUN useradd --create-home --uid 1001 app \
    && mkdir -p /app/data \
    && chown -R app:app /app
USER app

ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\",8000)}/health')"

# Bootstrap ensures a dataset exists before the API binds; on a machine that
# already has the Parquet files mounted it is a no-op. $PORT is honoured so the
# same image runs on Fly.io and Render without changes.
CMD ["sh", "-c", "python -m data.bootstrap && exec uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
