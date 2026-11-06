"""The data of each run and each pacer cycle (2026-10-29): the `Run:` line of the run report (`tokens.py --run-line`),
the cycle records of `pacer.py --log` and their log on the branch `metrics` (`metrics_log.py --pacer --push`)."""
import datetime
import json
import subprocess

import metrics_log
import pacer
import pytest
import report
import tokens


def at(seconds):
    return f"2026-10-29T12:{seconds // 60:02d}:{seconds % 60:02d}.000Z"


def call(seconds, uid, name, model="claude-opus-5-5", usage=None, **inp):
    return {"type": "assistant", "timestamp": at(seconds), "effort": "low", "sessionId": "s-1", "gitBranch": "claude/x",
            "version": "2.1.312",
            "message": {"id": uid, "model": model, "usage": usage or {"input_tokens": 1000},
                        "content": [{"type": "tool_use", "id": uid, "name": name, "input": inp}]}}


def result(seconds, uid, text):
    return {"type": "user", "timestamp": at(seconds),
            "message": {"content": [{"type": "tool_result", "tool_use_id": uid, "content": text}]}}


def test_the_run_line_names_the_run_and_splits_the_eq_by_phase_and_ticket():
    think = {"input_tokens": 1000, "output_tokens": 200, "output_tokens_details": {"thinking_tokens": 150}}
    recs = [{"type": "user", "timestamp": at(0), "sessionId": "s-1"},
            call(10, "a", "Bash", command="python3 framework/tools/cycle_start.py"),
            call(60, "b", "Bash", command="python3 framework/tools/claim.py 7 2>&1 | tail -3"), result(61, "b", "claimed claim/7"),
            call(120, "c", "Edit", usage=think, file_path="x.py"),
            call(180, "d", "Bash", command="python3 framework/tools/claim.py 9 --takeover; echo rc=$?"),
            result(181, "d", "claimed claim/9-2"),
            call(240, "e", "Bash", model="claude-haiku-5-5", command="python3 -m pytest -n auto"),
            call(300, "f", "Bash", command="python3 framework/tools/claim.py 9 --guard"), result(301, "f", "claimed claim/9")]
    line = tokens.run_line(recs)
    assert line.startswith("Run: s-1 · branch claude/x · start 2026-10-29T12:00:00Z · wall 5 min · ")
    assert "· model opus-5-5 5, haiku-5-5 1 · effort low 6 · think 0.00M · cli 2.1.312 ·" in line
    eq = lambda n: f"{n * 1000 / 1e6:.2f}M"                         # 1000 input tokens per call, 2000 for "c"
    assert (f"· eq read {eq(0)}, claim {eq(3)}, code {eq(2)}, verify {eq(1)}, ci {eq(1)}, conflict {eq(0)}, "
            f"report {eq(0)} · tickets #7 {eq(4)}, #9 {eq(3)}") in line
    assert tokens.steps(recs)[2]["think"] == 150


def test_a_claim_with_a_redirect_or_a_takeover_counts_and_an_option_does_not():
    claim = lambda cmd: (m := tokens.CLAIMED.search(cmd + "\n")) and int(m[1])
    assert claim("python3 framework/tools/claim.py 7 2>&1 | tail -3") == 7
    assert claim("python3 framework/tools/claim.py 7 > out.txt") == 7
    assert claim("python3 framework/tools/claim.py 7; echo rc=$?") == 7
    assert claim("python3 framework/tools/claim.py 7 --takeover && echo ok") == 7
    assert not claim("python3 framework/tools/claim.py 7 --guard") and not claim("python3 framework/tools/claim.py 0 --review")


def test_the_report_ends_with_the_run_line_and_the_lane(monkeypatch):
    body = report.report("Did #1.", "Usage: now", ["Metrics: ticket #1"], release="", tokens="Tokens: x", calls="Calls: y",
                         run="Run: s-1", lane="haiku")
    assert body.split(report.FOOTER)[0].splitlines()[-2:] == ["Calls: y", "Run: s-1 · lane haiku"]
    monkeypatch.setattr(report, "git_lane", lambda: None)
    assert "Run: s-1 · lane opus" in report.report("t", "u", [], release="", tokens="T", calls="", run="Run: s-1")


LINE = ("five_hour 16% (resets Thu 02:50 UTC, 0.0 h, allowed) · max 40 runs · target 33 runs · claims 2 (3.89 Opus runs)"
        " · ready 32 · refill 0 (ready 32, target 33: no refill source) · paused False")


def test_the_pacer_record_holds_the_quota_the_plan_the_starts_and_the_numbers_of_the_line():
    now = datetime.datetime(2026, 10, 29, 3, 3, tzinfo=datetime.timezone.utc)
    rec = pacer.record(now, {"five_hour": (0.16, 1761706200, "allowed")}, 0.01, None, 2, {"haiku": 1}, {"haiku": 1, "main": 1},
                       LINE, ["hourly limit: deep"])
    assert rec["at"] == "2026-10-29T03:03:00Z" and rec["five_hour"] == [0.16, 1761706200, "allowed"]
    assert (rec["target"], rec["claims"], rec["claims_opus"], rec["ready"], rec["refill"]) == (33, 2, 3.89, 32, 0)
    assert rec["started"] == {"haiku": 1, "main": 1} and rec["problems"] == ["hourly limit: deep"] and rec["line"] == LINE
    assert pacer.record(now, {}, 0.01, None, 0, {}, {}, "x")["target"] is None


def test_the_pacer_adds_one_line_per_cycle_to_its_log(monkeypatch, tmp_path):
    monkeypatch.setattr(pacer.usage, "read_usage", lambda: {"five_hour": (0.2, 0, "allowed")})
    monkeypatch.setattr(pacer.usage, "fire", lambda *a, skip=(), status=None, **kw: (1, {"haiku": 0}, LINE))
    monkeypatch.setattr(pacer.usage, "read_status", lambda: ([], ""))
    monkeypatch.setattr(pacer.usage, "burns", lambda comments: (0.01, None))
    log = tmp_path / "pacer.jsonl"
    for _ in range(2):
        with pytest.raises(SystemExit) as e:
            pacer.main(["--log", str(log)], env={})                 # no URL: no call
        assert e.value.code == 0
    rows = [json.loads(x) for x in log.read_text().splitlines()]
    assert len(rows) == 2 and rows[0]["k"] == 1 and rows[0]["problems"] == ["no URL: main"]


def cycle(t, k=1):
    return {"at": t, "k": k}


def test_the_pacer_records_go_to_one_file_per_day_once_per_cycle(tmp_path):
    src = tmp_path / "pacer.jsonl"
    src.write_text("\n".join([json.dumps(cycle("2026-10-28T23:55:00Z")), json.dumps(cycle("2026-10-29T00:05:00Z")),
                              '{"at": "2026-10-29T00:1']) + "\n")  # a cut line is left out
    root = tmp_path / "log"
    assert metrics_log.add_pacer(root, src) == [str(root / "pacer" / f"2026-10-2{d}.jsonl") for d in (8, 9)]
    assert metrics_log.add_pacer(root, src) == []
    src.write_text(json.dumps(cycle("2026-10-29T00:05:00Z", k=3)) + "\n" + json.dumps(cycle("2026-10-29T00:01:00Z")) + "\n")
    assert metrics_log.add_pacer(root, src) == [str(root / "pacer" / "2026-10-29.jsonl")]
    rows = [json.loads(x) for x in (root / "pacer" / "2026-10-29.jsonl").read_text().splitlines()]
    assert [(r["at"][11:16], r["k"]) for r in rows] == [("00:01", 1), ("00:05", 3)]
    assert metrics_log.add_pacer(root, tmp_path / "none.jsonl") == []


def test_push_adds_again_when_another_writer_pushed_first(tmp_path, monkeypatch):
    git = lambda cwd, *a: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout
    remote = tmp_path / "remote"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    seed = tmp_path / "seed"
    git(tmp_path, "init", "-q", str(seed))
    git(seed, "checkout", "-q", "--orphan", "metrics")
    (seed / "status").mkdir()
    (seed / "status" / "2026-10-28.jsonl").write_text("")
    git(seed, "add", "-A")
    git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "start")
    git(seed, "push", "-q", str(remote), "metrics")
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        git(tmp_path, "clone", "-q", "--branch", "metrics", str(remote), str(d))
    comments = [{"id": 1, "created_at": "2026-10-29T10:00:00Z", "updated_at": "2026-10-29T10:00:00Z", "body": "x"}]
    monkeypatch.setattr(metrics_log, "api", lambda path: [{"number": 1}] if path.startswith("issues?") else comments)
    src = tmp_path / "pacer.jsonl"
    src.write_text(json.dumps(cycle("2026-10-29T10:05:00Z")) + "\n")
    now = datetime.datetime(2026, 10, 29, 11, tzinfo=datetime.timezone.utc)
    assert metrics_log.push(a, days=1, now=now) == 0                 # writer A: the comment
    assert metrics_log.push(b, pacer=src, days=1, now=now) == 0      # writer B: on the tip of A
    files = git(remote, "ls-tree", "-r", "--name-only", "metrics").split()
    assert {"status/2026-10-29.jsonl", "pacer/2026-10-29.jsonl"} <= set(files)
    assert len(git(remote, "log", "--format=%H", "metrics").split()) == 3
    assert metrics_log.push(b, pacer=src, now=now) == 0              # nothing new: no commit
    assert len(git(remote, "log", "--format=%H", "metrics").split()) == 3


def test_prune_keeps_the_last_days_on_the_tip(tmp_path):
    for path in ("status/2026-10-01.jsonl", "status/2026-10-20.jsonl", "pacer/2026-10-01.jsonl",
                 "runs/2026-10-01/120000-1.json", "runs/2026-10-29/120000-2.json"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("{}")
    now = datetime.datetime(2026, 10, 29, 11, tzinfo=datetime.timezone.utc)
    gone = metrics_log.prune(tmp_path, now)
    assert sorted(p.split(str(tmp_path) + "/")[1] for p in gone) == ["pacer/2026-10-01.jsonl", "runs/2026-10-01",
                                                                     "status/2026-10-01.jsonl"]
    assert (tmp_path / "status/2026-10-20.jsonl").exists() and (tmp_path / "runs/2026-10-29/120000-2.json").exists()
    assert metrics_log.prune(tmp_path, now) == [] and metrics_log.prune(tmp_path / "none", now) == []
