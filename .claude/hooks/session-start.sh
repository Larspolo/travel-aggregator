#!/bin/bash
# Install the packages of the project (the install command of agent.toml) in a Claude Code cloud session, so that tests and lint work.
set -euo pipefail

# The merge driver of game/data/*.jsonl (.gitattributes, #2004): merge the lines by "name", not by union. Also local.
# A copy in the git directory: an older branch that merges main does not have framework/tools/merge_jsonl.py in its tree.
( cd "${CLAUDE_PROJECT_DIR:-.}" && gd=$(git rev-parse --path-format=absolute --git-common-dir) &&
  cp framework/tools/merge_jsonl.py "$gd/" && git config merge.jsonl.driver "python3 $gd/merge_jsonl.py %O %A %B" ) || true

# The Bash tool of a cloud session has no TMPDIR: "$TMPDIR/x.py" was "/x.py" (#2032).
if [ -n "${CLAUDE_ENV_FILE:-}" ] && [ -z "${TMPDIR:-}" ]; then
  echo "export TMPDIR=/tmp" >> "$CLAUDE_ENV_FILE"
fi

# The Claude account of the run (#4236, docs/COLLABORATORS.md): the variable AGENT_ACCOUNT of the cloud environment
# of each collaborator. framework/tools/claim.py, framework/tools/report.py and framework/tools/usage.py write it into their lines.
if [ -n "${AGENT_ACCOUNT:-}" ]; then
  ( cd "${CLAUDE_PROJECT_DIR:-.}" && git config travel-aggregator.account "$AGENT_ACCOUNT" ) || true
fi

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"
# The project-specific steps (framework/docs/SYSTEM.md, "Generic and specific files"), then the install command of
# agent.toml (#4801): the setup script runs before the clone and cannot install the packages of the repository.
if [ -f scripts/session-setup.sh ]; then bash scripts/session-setup.sh; fi
install=$(python3 -c 'import tomllib; print(tomllib.load(open("agent.toml", "rb")).get("commands", {}).get("install", ""))' \
  2>/dev/null || true)
if [ -n "$install" ]; then bash -c "$install"; fi

# The environment runs the setup script that the owner pasted. Tell the agent when it is older than the repository.
# One environment can serve more projects (#1964): it then has the version file of another project. With no version
# file of this project, tell the agent only when a need of SETUP_NEEDS (a command, a path or a path pattern) is missing.
want=$(sed -n 's/^SETUP_VERSION=\([0-9]*\).*/\1/p' scripts/cloud-setup.sh)
have=$(cat /etc/travel-aggregator-setup-version 2>/dev/null || echo none)
read -ra needs <<< "$(sed -n 's/^SETUP_NEEDS="\([^"]*\)".*/\1/p' scripts/cloud-setup.sh)"
missing=""
for n in "${needs[@]}"; do
  compgen -G "$n" >/dev/null || command -v "$n" >/dev/null || missing="$missing $n"
done
if [ "$have" != "$want" ] && { [ "$have" != none ] || [ -n "$missing" ]; }; then
  echo "travel-aggregator: the cloud environment runs setup script version $have, scripts/cloud-setup.sh is version $want" \
       "(missing:${missing:- none})." \
       "If no open ticket asks the owner to paste it, make one (needs-human, P1, size:S) with the steps" \
       "of framework/docs/STEERING.md, section 'Setup script (faster start)'."
fi
