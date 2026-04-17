#!/bin/bash
# Wait for PostgreSQL to be ready
# Tries both hostname and localhost for Railway compatibility

host="${DATABASE_HOST:-postgres}"
port="${DATABASE_PORT:-5432}"
user="${DATABASE_USER:-postgres}"
password="${POSTGRES_PASSWORD:-postgres}"
db="${DATABASE_NAME:-eval_pipeline}"

echo "Waiting for PostgreSQL at $host:$port..."
echo "User: $user, DB: $db"

max_attempts=60
attempt=0

# Function to test connection
test_connection() {
  local test_host=$1
  # Try TCP connection first
  if timeout 3 bash -c "echo > /dev/tcp/$test_host/$port" 2>/dev/null; then
    # TCP connection works, now try to connect with psql
    if PGPASSWORD="$password" psql -h "$test_host" -p "$port" -U "$user" -d "$db" -c "SELECT 1" 2>/dev/null; then
      echo "✓ PostgreSQL is up at $test_host - executing command"
      export DATABASE_HOST=$test_host
      exec "$@"
    fi
  fi
  return 1
}

# Try the configured host first
until [ $attempt -ge $max_attempts ]; do
  if test_connection "$host"; then
    exit 0
  fi
  
  # On Railway, also try localhost if primary host fails
  if [ "$host" != "localhost" ]; then
    if test_connection "localhost"; then
      exit 0
    fi
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
