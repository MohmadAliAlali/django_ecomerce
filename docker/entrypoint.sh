#!/bin/sh

set -e

echo "Waiting for PostgreSQL..."
until pg_isready \
    -h "$POSTGRES_HOST" \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER"
do
    echo "PostgreSQL is not ready yet. Retrying in 1s..."
    sleep 1
done
echo "PostgreSQL is ready!"

exec "$@"