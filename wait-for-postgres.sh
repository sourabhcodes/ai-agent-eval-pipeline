#!/bin/bash
# Wait for PostgreSQL to be ready

host="${DATABASE_HOST:-postgres}"
port="${DATABASE_PORT:-5432}"
user="${DATABASE_USER:-postgres}"
password="${POSTGRES_PASSWORD:-postgres}"
db="${DATABASE_NAME:-eval_pipeline}"

echo "Waiting for PostgreSQL at $host:$port..."

max_attempts=30
attempt=0

until [ $attempt -ge $max_attempts ]; do
  if PGPASSWORD="$password" psql -h "$host" -p "$port" -U "$user" -d "$db" -c "SELECT 1" 2>/dev/null; then
    echo "PostgreSQL is up - executing command"
    exec "$@"
  fi
  
  attempt=$((attempt + 1))
  if [ $attempt -lt $max_attempts ]; then
    echo "PostgreSQL unavailable. Attempt $attempt/$max_attempts. Retrying in 2 seconds..."
    sleep 2
  fi
done

echo "ERROR: Could not connect to PostgreSQL after $max_attempts attempts"
exit 1
