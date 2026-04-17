FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies with optimizations
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy wait-for-postgres script
COPY wait-for-postgres.sh /app/wait-for-postgres.sh
RUN chmod +x /app/wait-for-postgres.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONHASHSEED=random

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check (check if worker is responsive)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD celery -A app.celery inspect ping -d celery@$HOSTNAME > /dev/null 2>&1 || exit 1

# Celery worker - process evaluation and analysis tasks
CMD ["/bin/bash", "/app/wait-for-postgres.sh", "celery", "-A", "app.celery", "worker", \
     "--loglevel=info", \
     "--concurrency=4", \
     "-Q", "evaluation,analysis", \
     "--max-tasks-per-child=1000", \
     "--time-limit=1800", \
     "--soft-time-limit=1500"]