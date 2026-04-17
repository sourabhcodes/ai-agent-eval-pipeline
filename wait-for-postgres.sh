#!/bin/bash
# Wait for PostgreSQL to be ready on localhost (Railway compatible)

host="localhost"
port="${DATABASE_PORT:-5432}"
user="${DATABASE_USER:-postgres}"
password="${POSTGRES_PASSWORD:-postgres}"
db="${DATABASE_NAME:-eval_pipeline}"

echo "Waiting for PostgreSQL at $host:$port..."

attempt=0
max_attempts=60

until [ $attempt -ge $max_attempts ]; do
  if PGPASSWORD="$password" psql -h "$host" -p "$port" -U "$user" -d "$db" -c "SELECT 1" 2>/dev/null; then
    echo "✓ Connected to PostgreSQL at $host:$port"
    exec "$@"
  fi
  attempt=$((attempt + 1))
  if [ $attempt -lt $max_attempts ]; then
    echo "PostgreSQL unavailable. Attempt $attempt/$max_attempts. Retrying in 1 second..."
    sleep 1
  fi
done

echo "ERROR: Could not connect to PostgreSQL after $max_attempts attempts"
echo "Continuing anyway and letting app retry..."
sleep 2
exec "$@"
