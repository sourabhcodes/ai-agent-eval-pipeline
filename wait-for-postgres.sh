#!/bin/bash
# Wait for PostgreSQL (quick check only)
# If postgres isn't available, app will handle it gracefully on first request

echo "Checking if PostgreSQL is available..."

# Quick check - only try for 5 seconds
attempt=0
max_attempts=5

until [ $attempt -ge $max_attempts ]; do
  if [ -n "$DATABASE_URL" ] && [[ "$DATABASE_URL" != \$\{* ]]; then
    if psql "$DATABASE_URL" -c "SELECT 1" >/dev/null 2>&1; then
      echo "✓ PostgreSQL is ready!"
      exec "$@"
    fi
  else
    host="localhost"
    port="${DATABASE_PORT:-5432}"
    user="${DATABASE_USER:-postgres}"
    password="${POSTGRES_PASSWORD:-postgres}"
    db="${DATABASE_NAME:-eval_pipeline}"
    if PGPASSWORD="$password" psql -h "$host" -p "$port" -U "$user" -d "$db" -c "SELECT 1" >/dev/null 2>&1; then
      echo "✓ PostgreSQL is ready!"
      exec "$@"
    fi
  fi
  attempt=$((attempt + 1))
  [ $attempt -lt $max_attempts ] && sleep 1
done

echo "⚠ PostgreSQL not ready yet - app will retry on first request"
exec "$@"
