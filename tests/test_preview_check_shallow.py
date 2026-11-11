"""scripts/preview_check.sh in a shallow clone: the health wait follows a newer commit of main (#1056).

The script runs against a local HTTP stub (PREVIEW_URL) and a local bare origin; no network is used.
"""

import http.server
import os
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "preview_check.sh"
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True,
                          text=True).stdout.strip()


def commit(work, msg):
    git(work, "commit", "-q", "--allow-empty", "-m", msg)
    return git(work, "rev-parse", "HEAD")


class Stub:
    """A health stub: poll n answers the commit that `plan(n)` returns; `plan` may push commits first."""

    def __init__(self, plan):
        self.plan = plan
        self.polls = 0
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/api/health":
                    self.send_response(401)
                    self.end_headers()
                    return
                stub.polls += 1
                sha = stub.plan(stub.polls)
                body = ('{"commit": "%s"}' % sha).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def repos(tmp_path):
    """A bare origin with c1 <- c2, and a shallow clone of it at depth 1 (its main is c2, c1 is missing)."""
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    clone = tmp_path / "clone"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    c1 = commit(work, "c1")
    c2 = commit(work, "c2")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "origin", "main")
    subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + str(origin), str(clone)],
                   check=True, env=GIT_ENV)
    return {"origin": origin, "work": work, "clone": clone, "c1": c1, "c2": c2}


def run_check(clone, url, want, tries=2):
    env = {k: v for k, v in GIT_ENV.items() if k.lower() not in ("http_proxy", "https_proxy")}
    env.update({"PREVIEW_URL": url, "PREVIEW_WAIT_TRIES": str(tries), "PREVIEW_WAIT_SECS": "0",
                "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
    return subprocess.run(["bash", str(SCRIPT), want], cwd=clone, env=env, capture_output=True, text=True,
                          timeout=120)


def test_clone_is_shallow(repos):
    assert git(repos["clone"], "rev-parse", "--is-shallow-repository") == "true"


def test_newer_commit_of_main_passes_in_shallow_clone(repos, tmp_path):
    c2, work = repos["c2"], repos["work"]
    c3 = commit(work, "c3")
    git(work, "push", "-q", "origin", "main")
    # A clone made now is shallow at c3: c2 is not local, so the new commit is a graft (the bug of #1056).
    clone = tmp_path / "clone3"
    subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + str(repos["origin"]), str(clone)],
                   check=True, env=GIT_ENV)
    assert git(clone, "rev-parse", "--is-shallow-repository") == "true"
    stub = Stub(lambda n: c3)   # the preview runs c3, which contains c2 (the commit of the check)
    try:
        res = run_check(clone, stub.url, c2)
    finally:
        stub.close()
    assert "ok   health: commit %s (contains %s)" % (c3, c2) in res.stdout, res.stdout + res.stderr


def test_commit_without_the_check_commit_still_fails(repos):
    c1, c2 = repos["c1"], repos["c2"]
    stub = Stub(lambda n: c1)   # c1 is older than the commit of the check: it does not contain c2
    try:
        res = run_check(repos["clone"], stub.url, c2)
    finally:
        stub.close()
    assert res.returncode == 1
    assert "FAIL health: the preview runs '%s', not %s" % (c1, c2) in res.stdout, res.stdout + res.stderr


def test_fetches_again_when_the_preview_moves_to_a_new_commit(repos):
    c1, c2, work = repos["c1"], repos["c2"], repos["work"]
    holder = {}

    def plan(n):
        if n == 1:
            return c1           # older commit first: the script fetches (origin main is still c2)
        if n == 2:
            holder["c3"] = commit(work, "c3")   # the preview moves on; main gets c3 only now
            git(work, "push", "-q", "origin", "main")
        return holder["c3"]     # the second fetch must bring c3 with its parent c2

    stub = Stub(plan)
    try:
        res = run_check(repos["clone"], stub.url, c2, tries=4)
    finally:
        stub.close()
    assert "ok   health: commit %s (contains %s)" % (holder["c3"], c2) in res.stdout, res.stdout + res.stderr
