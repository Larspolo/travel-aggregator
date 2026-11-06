#!/bin/sh
# The start of the container: the migrations first (when the project has them), then the app.
set -eu
if [ -f alembic.ini ]; then
  alembic upgrade head
fi
# The reverse proxy (Traefik, Caddy, nginx) sets X-Forwarded-*: trust it for the scheme and the client address.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
