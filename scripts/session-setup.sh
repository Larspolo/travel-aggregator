#!/bin/bash
# The project-specific steps of the SessionStart hook in a cloud session: it runs this file before the install command
# of agent.toml (.claude/hooks/session-start.sh).
# pywebpush (#514) needs cryptography>=47 and builds http-ece from source. The system Python of the cloud has the
# Debian package cryptography 41, which pip cannot uninstall ("RECORD file not found"), and an old setuptools that
# cannot build http-ece without PEP 517. Install both next to the Debian packages first: then the install command
# finds them. CI and the Dockerfile do not need this (their Python has no Debian packages).
pip=(python3 -m pip install --quiet --disable-pip-version-check --root-user-action=ignore --use-pep517)
"${pip[@]}" --ignore-installed "cryptography>=47" || echo "session-setup: cryptography>=47 not installed" >&2
"${pip[@]}" "http-ece>=1.1.0" || echo "session-setup: http-ece not installed" >&2
