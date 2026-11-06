# The image of travel-aggregator: deploy/preview/ runs it as :preview (the job preview of .github/workflows/ci.yml).
# Stage 1 installs the Python packages into a virtual environment; stage 2 copies only that and the app.
FROM python:3.12-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install -r /tmp/requirements.txt

FROM python:3.12-slim
ARG GIT_SHA=dev
# PYTHONPATH: the alembic program (docker-entrypoint.sh) imports app/ from /app
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GIT_SHA=$GIT_SHA PORT=8000
# pg_dump 16 for the backup before a data migration (app/backup.py). The Debian client is older than the postgres:16
# server, and pg_dump cannot read a newer server: so install the client from the PGDG apt repository.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $VERSION_CODENAME-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-16 \
    && apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin app \
    && install -d -o app -g app /backups
ENV BACKUP_DIR=/backups
VOLUME ["/backups"]
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --chown=root:root . /app
USER app
EXPOSE 8000
# No curl in the slim image: the healthcheck uses Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4)"]
ENTRYPOINT ["/app/docker-entrypoint.sh"]
