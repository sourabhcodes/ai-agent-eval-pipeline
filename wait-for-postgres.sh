#!/bin/bash
# Wait for PostgreSQL to be ready
# Tries both service hostname and localhost

host="${DATABASE_HOST:-postgres}"
port="${DATABASE_PORT:-5432}"
user="${DATABASE_USER:-postgres}"
password="${POSTGRES_PASSWORD:-postgres}"
db="${DATABASE_NAME:-eval_pipeline}"

echo "Waiting for PostgreSQL at $host:$port..."

# Try 10 attempts with service name, then switch to localhost
attempt=0
max_attempts=10

echo "=== Attempt 1: Trying $host:$port ==="
until [ $attempt -ge $max_attempts ]; do
  if PGPASSWORD="$password" psql -h "$host" -p "$port" -U "$user" -d "$db" -c "SELECT 1" 2>/dev/null; then
    echo "✓ Connected to PostgreSQL at $host:$port"
    exec "$@"
  fi
  attempt=$((attempt + 1))
  if [ $attempt -lt $max_attempts ]; then
    sleep 1
  fi
done

# If service name didn't work, try localhost
echo "=== Service hostname failed, trying localhost ==="
attempt=0
max_attempts=30

until [ $attempt -ge $max_attempts ]; do
  if PGPASSWORD="$password" psql -h "localhost" -p "$port" -U "$user" -d "$db" -c "SELECT 1" 2>/dev/null; then
    echo "✓ Connected to PostgreSQL at localhost:$port"
    exec "$@"
  fi
  attempt=$((attempt + 1))
  if [ $attempt -lt $max_attempts ]; then
    echo "PostgreSQL unavailable at localhost. Attempt $attempt/$max_attempts. Retrying in 1 second..."
    sleep 1
  fi
done

echo "ERROR: Could not connect to PostgreSQL"
echo "Continuing anyway and letting app retry..."
sleep 2
exec "$@"
