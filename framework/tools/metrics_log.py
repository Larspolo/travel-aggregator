"""The log of the status issue comments on the orphan branch `metrics` (#1983): one file `status/YYYY-MM-DD.jsonl`
per day of `created_at`, one JSON line per comment (`id`, `created_at`, `updated_at`, `issue_url`, `body`).
`framework/tools/health.py` reads the files and only the newest comments from the API, not hundreds of API pages.
The folder `pacer/` holds one JSON line per cycle of the pacer (`pacer.py --log`, `pacer/YYYY-MM-DD.jsonl` by `at`).
The folder `runs/` holds the run reports (2026-10-29): `report.py --post` adds one file `runs/YYYY-MM-DD/<time>-<session>.json`
per report with `post()`, not a comment on the status issue (about 550 comments a day, each one a notification of the
owner). A record has the keys of a comment (`id`, `created_at`, `updated_at`, `body`) and `"run": true`, so `load()`
gives the readers of the comments (`health.status_comments`) both, and the fields of the run as named keys.

    python3 framework/tools/metrics_log.py DIR [--days N]     # DIR: a checkout of the branch `metrics` (metrics.yml)
    python3 framework/tools/metrics_log.py DIR --pacer F --push   # also the pacer records of F; commit and push (pacer.yml)

The pacer loop (`pacer.yml`) runs it in each cycle (10 minutes): the cron of `metrics.yml` ("every 15 minutes") ran
8 times in 38 hours (2026-10-27 to 10-29), and the branch was up to 6 hours old. `metrics.yml` stays as the fallback
and for a backfill. Two writers: `--push` takes the branch again and adds again when the other one pushed first.
An `issue_comment` trigger would start one Actions run for each comment of the repository (about 1100 a day).
"""
import argparse
import datetime
import glob
import json
import os
import subprocess
import sys
import tempfile
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dashboard import STATUS, api  # noqa: E402

BRANCH = "metrics"
RUNS = "runs"
KEEP = 14                   # days on the tip of the branch: each reader fetches the whole tip (about 2 MB a day)
KEYS = ("id", "created_at", "updated_at", "issue_url", "body")
UTC = datetime.timezone.utc
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def iso(t):
    return f"{t:%Y-%m-%dT%H:%M:%SZ}"


def day(c):
    return c["created_at"][:10]


def api_comments(since):
    """The status issue comments that changed since `since` (the API `since` is the `updated_at`)."""
    status = api(f"issues?state=open&labels={STATUS}")
    if not status:
        return []
    out = []
    for page in range(1, 1000):
        items = api(f"issues/{status[0]['number']}/comments?since={iso(since)}&per_page=100&page={page}")
        out += items
        if len(items) < 100:
            return out
    return out


def read_dir(root):
    """{id: comment} of the files in `root`."""
    out = {}
    for path in sorted(glob.glob(os.path.join(root, "status", "*.jsonl"))):
        with open(path) as f:
            for line in f:
                if line.strip():
                    c = json.loads(line)
                    out[c["id"]] = c
    return out


def newest(comments):
    """The newest `updated_at` of the comments (not of the run records: the API reads from it), or None."""
    return max((c["updated_at"] for c in comments if not c.get("run")), default=None)


def run_record(body, fields, now=None):
    """A run report as a record of `runs/`: the keys of a comment and the named fields of the run. The `id` is an
    integer like a comment ID (the readers sort by it): the time in milliseconds, and 3 digits of the session."""
    now = now or datetime.datetime.now(UTC)
    at = iso(now)
    key = zlib.crc32(str(fields.get("session") or fields.get("branch") or "").encode()) % 1000
    return {"id": int(now.timestamp() * 1e3) * 1000 + key, "created_at": at, "updated_at": at, "body": body,
            "run": True, **fields}


def run_path(rec):
    return f"{RUNS}/{rec['created_at'][:10]}/{rec['created_at'][11:19].replace(':', '')}-{rec['id'] % 10**9:09d}.json"


def post(rec, remote="origin", tries=5, root=None):
    """Add the record `rec` as its own file to the branch `metrics` of `remote`, with no checkout: a commit on the
    newest tip, and again on the new tip when another run pushed first (a new file: no conflict). An absent branch
    starts. Returns the path in the branch, or None when no push went through."""
    root, path = root or ROOT, run_path(rec)
    ref = f"refs/remotes/{remote}/{BRANCH}"
    sh = lambda *a, env=None, data=None: subprocess.run(["git", "-C", root, *a], capture_output=True, text=True,
                                                         timeout=60, input=data, env=env)
    try:
        blob = sh("hash-object", "-w", "--stdin", data=json.dumps(rec, ensure_ascii=False) + "\n").stdout.strip()
        for _ in range(tries):
            tip = sh("fetch", "-q", "--depth", "1", remote, f"+refs/heads/{BRANCH}:{ref}").returncode == 0
            with tempfile.TemporaryDirectory() as d:
                env = {**os.environ, "GIT_INDEX_FILE": os.path.join(d, "index")}
                if tip:
                    sh("read-tree", ref, env=env)
                sh("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
                tree = sh("write-tree", env=env).stdout.strip()
            commit = sh("commit-tree", tree, *(["-p", ref] if tip else []), "-m", f"Add the run report {path}").stdout.strip()
            if commit and sh("push", "-q", remote, f"{commit}:refs/heads/{BRANCH}").returncode == 0:
                return path
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def read_runs(ref, days, root=None):
    """The run records of the day folders `days` (YYYY-MM-DD) in the tree of `ref`, with two git calls."""
    root = root or ROOT
    names = subprocess.run(["git", "-C", root, "ls-tree", "-r", "--name-only", ref, "--", *[f"{RUNS}/{d}/" for d in days]],
                           capture_output=True, text=True, timeout=60).stdout.split()
    if not names:
        return []
    out = subprocess.run(["git", "-C", root, "cat-file", "--batch"], capture_output=True, timeout=60,
                         input="".join(f"{ref}:{n}\n" for n in names).encode()).stdout
    recs, i = [], 0
    while i < len(out):                     # b"<sha> blob <size>\n<content>\n" per name, b"<name> missing\n" else
        end = out.index(b"\n", i)
        head = out[i:end].split()
        if len(head) != 3 or not head[2].isdigit():
            i = end + 1
            continue
        size = int(head[2])
        try:
            recs.append(json.loads(out[end + 1:end + 1 + size]))
        except ValueError:
            pass
        i = end + 1 + size + 1
    return recs


def add(root, comments):
    """Add or replace the comments by `id` in the day files of `root`. Returns the paths of the changed files."""
    old = read_dir(root)
    days = {}
    for c in comments:
        c = {k: c.get(k) for k in KEYS}
        if old.get(c["id"]) != c:
            old[c["id"]] = c
            days[day(c)] = True
    changed = []
    for d in sorted(days):
        path = os.path.join(root, "status", f"{d}.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        rows = sorted((c for c in old.values() if day(c) == d), key=lambda c: (c["created_at"], c["id"]))
        with open(path, "w") as f:
            f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in rows)
        changed.append(path)
    return changed


def update(root, days=None, now=None):
    """Read the comments since the newest stored `updated_at` and add them. `days`, or an empty branch: read the
    comments of the last `days` (default 7) again (a backfill, a repair)."""
    now = now or datetime.datetime.now(UTC)
    last = newest(read_dir(root).values())
    since = parse(last) if last and days is None else now - datetime.timedelta(days=days or 7)
    return add(root, api_comments(since))


def add_pacer(root, path):
    """Add the cycle records of the file `path` (`pacer.py --log`: one JSON line per cycle) to the day files
    `pacer/YYYY-MM-DD.jsonl` of `root`, one line per `at`. A line that does not parse is left out. Returns the paths of
    the changed files."""
    try:
        with open(path) as f:
            text = f.read().splitlines()
    except OSError:
        return []
    days = {}
    for x in text:
        try:
            r = json.loads(x)
            days.setdefault(r["at"][:10], {})[r["at"]] = r
        except (ValueError, KeyError, TypeError):
            continue
    changed = []
    for d, rows in sorted(days.items()):
        path = os.path.join(root, "pacer", f"{d}.jsonl")
        old = {}
        if os.path.exists(path):
            with open(path) as f:
                old = {r["at"]: r for r in map(json.loads, filter(str.strip, f))}
        new = {**old, **rows}
        if new != old:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.writelines(json.dumps(new[k], ensure_ascii=False) + "\n" for k in sorted(new))
            changed.append(path)
    return changed


def prune(root, now=None, keep=KEEP):
    """Remove the day files and day folders older than `keep` days from the checkout `root` (`status/`, `pacer/`,
    `runs/`): the readers need at most 7 days, and the git history of the branch keeps them. Returns the removed paths."""
    import shutil
    cut = f"{(now or datetime.datetime.now(UTC)) - datetime.timedelta(days=keep):%Y-%m-%d}"
    gone = []
    for folder in ("status", "pacer", RUNS):
        for name in sorted(os.listdir(os.path.join(root, folder))) if os.path.isdir(os.path.join(root, folder)) else []:
            if name[:10] < cut and name[:4].isdigit():
                path = os.path.join(root, folder, name)
                shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
                gone.append(path)
    return gone


def push(root, pacer=None, days=None, tries=5, remote="origin", now=None):
    """Take the newest tip of the branch `metrics` into the checkout `root`, add the new status comments and the pacer
    records of the file `pacer`, remove the days before `KEEP` (`prune`), commit and push. The runs push their reports
    too (`post`): when one pushed first, take the tip again and add again (`update` reads from the newest stored
    comment, `add_pacer` by `at`: nothing comes twice). Returns 0, or 1 when no push went through."""
    sh = lambda *a: subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, timeout=60)
    for _ in range(tries):
        if sh("fetch", "-q", "--depth", "1", remote, BRANCH).returncode == 0:   # no branch yet: start it
            sh("reset", "-q", "--hard", "FETCH_HEAD")
        changed = update(root, days, now) + (add_pacer(root, pacer) if pacer else []) + prune(root, now)
        if not changed:
            print("no change")
            return 0
        sh("add", "-A", ".")
        sh("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
           "commit", "-q", "-m", "Log the status comments and the pacer cycles")
        if sh("push", "-q", remote, f"HEAD:refs/heads/{BRANCH}").returncode == 0:
            print(f"pushed {len(changed)} files")
            return 0
    print("no push", file=sys.stderr)
    return 1


def parse(t):
    return datetime.datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=60)


def load(since, remote="origin"):
    """The stored comments and run records created since `since`, from `remote`/metrics, or None when git cannot read
    the branch."""
    try:  # a hung git call (#3290) reads as a failed one; only the tip: the pacer adds a commit each cycle
        # a second try: a parallel fetch in the same clone holds the lock of the ref or of `shallow`, and the reader
        # then counted 0 run reports in 100 merged PRs with no warning (process review 2026-11-02)
        for wait in (2, None):
            if not git("fetch", "-q", "--depth", "1", remote, f"+refs/heads/{BRANCH}:refs/remotes/{remote}/{BRANCH}").returncode:
                break
            if wait is None:
                return None
            time.sleep(wait)
        out, d, days = [], since.date(), []
        while d <= datetime.datetime.now(UTC).date():
            r = git("show", f"{remote}/{BRANCH}:status/{d:%Y-%m-%d}.jsonl")
            out += [json.loads(line) for line in r.stdout.splitlines() if line.strip()] if r.returncode == 0 else []
            days.append(f"{d:%Y-%m-%d}")
            d += datetime.timedelta(days=1)
        out += read_runs(f"{remote}/{BRANCH}", days)
    except subprocess.TimeoutExpired:
        return None
    return [c for c in out if c["created_at"] >= iso(since)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dir", help="a checkout of the branch metrics")
    ap.add_argument("--days", type=int, help="read the comments of the last N days again (an empty branch: 7)")
    ap.add_argument("--pacer", metavar="FILE", help="also add the pacer records of FILE (pacer.py --log)")
    ap.add_argument("--push", action="store_true", help="commit and push the branch (again after a push of another writer)")
    a = ap.parse_args(argv)
    if a.push:
        return push(a.dir, a.pacer, a.days)
    for path in update(a.dir, a.days) + (add_pacer(a.dir, a.pacer) if a.pacer else []):
        print(os.path.relpath(path, a.dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
