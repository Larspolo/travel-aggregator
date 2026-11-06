"""The project values of the agent system from `agent.toml` at the root (#905), and the owner's settings of the system
(`[pacing]`, `[review]`) from `steering/system/system.toml` (#4194).

`AGENT_CONFIG` names another first file (the tests use a fake config); then the second file is `AGENT_SYSTEM`, or none.
The tools read `CONFIG` once at import."""
import os
import subprocess

import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


SYSTEM = os.path.join(ROOT, "steering", "system", "system.toml")


def load(path=None, system=None):
    """The dict of the first file, joined with the sections of the second file when it exists (a section in both:
    ValueError)."""
    with open(path or os.environ.get("AGENT_CONFIG") or os.path.join(ROOT, "agent.toml"), "rb") as f:
        config = tomllib.load(f)
    system = system or os.environ.get("AGENT_SYSTEM") or (None if path or os.environ.get("AGENT_CONFIG") else SYSTEM)
    if system and os.path.exists(system):
        with open(system, "rb") as f:
            extra = tomllib.load(f)
        if both := sorted(set(config) & set(extra)):
            raise ValueError(f"{system} and the project file both have {both}")
        config.update(extra)
    return config



def owners(config=None):
    """The GitHub logins that steer the agents (decision #4229): `owners`, default [`owner`]. `owner` is the
    tie-breaker of opposite asks."""
    config = CONFIG if config is None else config
    return list(config.get("owners") or [config["owner"]])


def account():
    """The Claude account of this run (#4236): `git config travel-aggregator.account` (the SessionStart hook copies the variable
    AGENT_ACCOUNT of the cloud environment), else None: then the lines get no account word."""
    r = subprocess.run(["git", "config", "--get", "travel-aggregator.account"], capture_output=True, text=True)
    return r.stdout.strip() or None


def first_account(config=None):
    """The name of the first table of `[accounts]`: a line with no account word belongs to it. None with no table."""
    return next(iter((CONFIG if config is None else config).get("accounts", {})), None)


def login(account, config=None):
    """The GitHub login of a Claude account (`login` of its table in `[accounts]`), else the owner (#4243)."""
    config = CONFIG if config is None else config
    return config.get("accounts", {}).get(account, {}).get("login", config["owner"])


CONFIG = load()
