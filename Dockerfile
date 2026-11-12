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
# APT_RETRY: a timeout of apt.postgresql.org gave "Unable to locate package" and a red CI job (#2488): try longer,
# and fail at the fetch with its own error.
ARG APT_RETRY="-o Acquire::Retries=6"
RUN apt-get $APT_RETRY --error-on=any update && apt-get $APT_RETRY install -y --no-install-recommends ca-certificates curl gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $VERSION_CODENAME-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get $APT_RETRY --error-on=any update && apt-get $APT_RETRY install -y --no-install-recommends postgresql-client-16 \
    && apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin app \
    && install -d -o app -g app /backups
ENV BACKUP_DIR=/backups
VOLUME ["/backups"]
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --chown=root:root . /app
# The build time of the image: /api/health gives it, so the owner sees when the running image was built (#1736).
RUN date -u +%Y-%m-%dT%H:%M:%SZ > /app/BUILD_TIME
USER app
EXPOSE 8000
# No curl in the slim image: the healthcheck uses Python. Traefik sends no request to a container that is not
# healthy yet: --start-interval checks each 2 s in the start period, so a new image is healthy a few seconds after
# the start, not after the first 30 s interval (the 503 of the pages after a deploy, #996). The start period
# of 60 s covers the backup and the migrations. --start-interval needs Docker Engine 25 or later.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --start-interval=2s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4)"]
ENTRYPOINT ["/app/docker-entrypoint.sh"]
