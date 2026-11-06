"""Automerge adds the label `conflict` only for a real merge conflict (#3063): "Base branch was modified" and "Merge
already in progress" come when two merges land in the same second, and the next sweep merges the PR."""
import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

WORKFLOW = os.path.join(os.path.dirname(__file__), "..", "..", ".github", "workflows", "automerge.yml")
CONFLICT = "Pull Request has merge conflicts"
MODIFIED = "Base branch was modified. Review and try the merge again."
BUSY = "Merge already in progress"
FAKE_GH = """#!{python}
import json, os, subprocess, sys
args = sys.argv[1:]
with open(os.environ["GH_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
method = args[args.index("-X") + 1] if "-X" in args else "POST" if {{"-f", "-F"}} & set(args) else "GET"
out, rc = json.load(open(os.environ["GH_TABLE"])).get(method + " " + args[1], [{{}}, 0])
text = json.dumps(out)
if "--jq" in args and rc == 0:
    text = subprocess.run(["jq", "-r", args[args.index("--jq") + 1]], input=text, capture_output=True, text=True).stdout
print(text.rstrip("\\n"))
sys.exit(rc)
"""


def merge_function():
    """The bash function merge of the step "Merge the green agent PRs", as the runner sees it."""
    lines = open(WORKFLOW).read().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith("merge() {"))
    indent = lines[start][:len(lines[start]) - len(lines[start].lstrip())]
    end = next(i for i in range(start, len(lines)) if lines[i] == indent + "}")
    return textwrap.dedent("\n".join(lines[start:end + 1]))


def gate(tmp_path, config=None):
    """The owner gate as the setup step copies it (#4241): main's owner_gate.py, agent_config.py and agent.toml."""
    tools = os.path.join(os.path.dirname(__file__), "..", "tools")
    (tmp_path / "gate").mkdir()
    for f in ("owner_gate.py", "agent_config.py"):
        shutil.copy(os.path.join(tools, f), tmp_path / "gate" / f)
    (tmp_path / "gate" / "agent.toml").write_text(config or 'owner = "o"\n')


def run(tmp_path, message, state="clean"):
    """Run merge() for a green PR whose merge fails with `message`; land() fails too. Gives (calls, $conflict)."""
    (tmp_path / "bin").mkdir()
    gh = tmp_path / "bin" / "gh"
    gh.write_text(FAKE_GH.format(python=sys.executable))
    gh.chmod(0o755)
    (tmp_path / "table.json").write_text(json.dumps({
        "PUT repos/o/r/pulls/7/merge": [{"message": message}, 1],
        "GET repos/o/r/pulls/7": [{"merged": False, "head": {"sha": "abc"}, "mergeable_state": state}, 0]}))
    pr = json.dumps({"number": 7, "head": {"ref": "agent/7-x", "sha": "abc"}, "labels": [], "body": "A change."})
    script = "\n".join(["R=o/r merged=0 conflict=0 AGENT=true", "land() { return 1; }", "squash() { return 1; }",
                        merge_function(), f"merge '{pr}' abc", 'echo "conflict=$conflict"'])
    gate(tmp_path)
    env = dict(os.environ, PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}", GH_LOG=str(tmp_path / "log"),
               GH_TABLE=str(tmp_path / "table.json"), RUNNER_TEMP=str(tmp_path))
    p = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    calls = [json.loads(line) for line in (tmp_path / "log").read_text().splitlines()]
    return calls, p.stdout.split("conflict=")[-1].strip()


def marked(calls):
    """The label and comment calls of the PR."""
    return [c[1] for c in calls if c[1] in ("repos/o/r/issues/7/labels", "repos/o/r/issues/7/comments")]


pytestmark = pytest.mark.skipif(subprocess.run(["which", "jq"], capture_output=True).returncode != 0,
                                reason="the fake gh needs jq")


def test_a_real_conflict_gets_the_label_and_the_comment(tmp_path):
    calls, conflict = run(tmp_path, CONFLICT)
    assert marked(calls) == ["repos/o/r/issues/7/labels", "repos/o/r/issues/7/comments"]
    assert ["-f", "labels[]=conflict"] == calls[-2][2:]
    assert CONFLICT in (tmp_path / "body.md").read_text()
    assert conflict == "1"


@pytest.mark.parametrize("message", [MODIFIED, BUSY])
def test_a_short_lived_failure_waits_for_the_next_sweep(tmp_path, message):
    calls, conflict = run(tmp_path, message)
    assert marked(calls) == []
    assert conflict == "0"


def test_a_dirty_pr_gets_the_label_also_with_another_message(tmp_path):
    calls, conflict = run(tmp_path, MODIFIED, state="dirty")
    assert marked(calls) == ["repos/o/r/issues/7/labels", "repos/o/r/issues/7/comments"]
    assert conflict == "1"
