#!/bin/bash
# The setup script of the cloud environment: the owner pastes it into the environment settings (framework/docs/SYSTEM.md).
# It runs before the clone: install tools by name only (system packages, runtimes), with no file of the repository.
# The SessionStart hook installs the packages of the repository (the install command of agent.toml).
set -euo pipefail
SETUP_VERSION=1   # raise it with each change: the SessionStart hook compares it with /etc/travel-aggregator-setup-version
SETUP_NEEDS="python3.12 /usr/lib/postgresql/16/bin/pg_ctl"   # the hook checks them with the setup script of another project

# PostgreSQL 16 for the tests: tests/conftest.py starts a temporary cluster with initdb and pg_ctl (no service).
if [ ! -x /usr/lib/postgresql/16/bin/pg_ctl ]; then
  apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql-16 postgresql-client-16
fi
command -v python3.12 >/dev/null || { apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12; }

echo "$SETUP_VERSION" > /etc/travel-aggregator-setup-version || true
