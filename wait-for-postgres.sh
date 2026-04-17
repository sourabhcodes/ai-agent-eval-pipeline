#!/bin/bash
# Wait for PostgreSQL to be ready

host="${DATABASE_HOST:-postgres}"
port="${DATABASE_PORT:-5432}"
user="${DATABASE_USER:-postgres}"
password="${POSTGRES_PASSWORD:-postgres}"
db="${DATABASE_NAME:-eval_pipeline}"

echo "Waiting for PostgreSQL at $host:$port..."
echo "User: $user, DB: $db"

max_attempts=60
attempt=0

until [ $attempt -ge $max_attempts ]; do
  if timeout 3 bash -c "echo > /dev/tcp/$host/$port" 2>/dev/null; then
    # TCP connection works, now try to connect with psql
    if PGPASSWORD="$password" psql -h "$host" -p "$port" -U "$user" -d "$db" -c "SELECT 1" 2>/dev/null; then
      echo "✓ PostgreSQL is up - executing command"
      exec "$@"
    else
      echo "TCP connection ok but psql failed. Retrying..."
    fi
  else
    echo "Cannot reach $host:$port"
  fi
  
  attempt=$((attempt + 1))
  if [ $attempt -lt $max_attempts ]; then
    echo "PostgreSQL unavailable. Attempt $attempt/$max_attempts. Retrying in 1 second..."
    sleep 1
  fi
done

echo "ERROR: Could not connect to PostgreSQL after $max_attempts attempts"
echo "Trying to continue anyway..."
exec "$@"
