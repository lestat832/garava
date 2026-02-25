FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY garava/ garava/

# Create non-root user and data directory
RUN groupadd -r garava && useradd -r -g garava garava \
    && mkdir -p /data && chown garava:garava /data

# Environment defaults
ENV GARAVA_DB_PATH=/data/garava.db
ENV GARTH_HOME=/data/.garth
ENV GARAVA_LOG_LEVEL=INFO
ENV GARAVA_POLL_INTERVAL=10

USER garava

# Run the sync service
CMD ["python", "-m", "garava", "run"]
