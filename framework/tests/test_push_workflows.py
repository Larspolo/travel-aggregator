"""Automerge starts the push workflows of main after its merges (#4839): a push of GITHUB_TOKEN starts none."""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import push_workflows  # noqa: E402
from test_automerge_failure import FAKE_GH, WORKFLOW, gate, merge_function  # noqa: E402

FILES = {
    "image.yml": "name: Image\non:\n  push:\n    branches: [main]\n    paths-ignore:\n      - 'docs/**'\n"
                 "      - '*.md'\n  workflow_dispatch:\njobs: {}\n",
    "site.yml": "on:\n  push:\n    branches:\n      - main\n    paths: [site/**]\n  workflow_dispatch:\n",
    "release.yml": "on:\n  push:\n    tags: ['v*']\n  workflow_dispatch:\n",
    "ci.yml": "on:\n  push:\n    branches: [main]\n  workflow_dispatch:\n",
    "nodispatch.yml": "on:\n  push:\n    branches: [main]\n",
}


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "workflows"
    d.mkdir()
    for name, text in FILES.items():
        (d / name).write_text(text)
    return str(d)


def test_a_matching_file_selects_the_workflow(folder):
    assert push_workflows.workflows(folder, ["app/main.py"]) == ["image.yml"]
    assert push_workflows.workflows(folder, ["site/a/index.html", "README.md"]) == ["image.yml", "site.yml"]


def test_ignored_files_select_none(folder):
    assert push_workflows.workflows(folder, ["docs/a/b.md", "README.md"]) == []


def test_never_a_tag_workflow_or_ci(folder):
    got = push_workflows.workflows(folder, ["x.py", "site/i.html", "docs/a.md"])
    assert "release.yml" not in got and "ci.yml" not in got and "nodispatch.yml" not in got


pytestmark = pytest.mark.skipif(subprocess.run(["which", "jq"], capture_output=True).returncode != 0,
                                reason="the fake gh needs jq")


def dispatch_block():
    """The bash lines of automerge.yml that start the printed push workflows."""
    lines = open(WORKFLOW).read().splitlines()
    i = next(k for k, ln in enumerate(lines) if "merged_files.txt\" ]; then" in ln)
    j = next(k for k in range(i, len(lines)) if lines[k].strip() == "fi")
    return "\n".join(ln.strip() for ln in lines[i:j + 1])


def test_automerge_starts_each_printed_workflow_once(tmp_path, folder):
    (tmp_path / "bin").mkdir()
    gh = tmp_path / "bin" / "gh"
    gh.write_text(FAKE_GH.format(python=sys.executable))
    gh.chmod(0o755)
    files = [{"filename": "app/main.py"}]
    (tmp_path / "table.json").write_text(json.dumps({
        "GET repos/o/r/pulls/7/files?per_page=100": [files, 0], "GET repos/o/r/pulls/8/files?per_page=100": [files, 0]}))
    tools = os.path.join(os.path.dirname(__file__), "..", "tools")
    (tmp_path / "push_workflows.py").write_text(open(os.path.join(tools, "push_workflows.py")).read())
    gate(tmp_path)
    script = ["R=o/r merged=0 conflict=0 AGENT=true", merge_function()]
    for n in (7, 8):
        pr = json.dumps({"number": n, "head": {"ref": f"agent/{n}-x", "sha": "abc"}, "labels": [], "body": "A."})
        script.append(f"merge '{pr}' abc")
    script.append(dispatch_block())
    env = dict(os.environ, PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}", GH_LOG=str(tmp_path / "log"),
               GH_TABLE=str(tmp_path / "table.json"), RUNNER_TEMP=str(tmp_path))
    p = subprocess.run(["bash", "-c", "\n".join(script)], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    calls = [json.loads(ln) for ln in (tmp_path / "log").read_text().splitlines()]
    assert [c for c in calls if c[:2] == ["workflow", "run"]] == [["workflow", "run", "image.yml", "--repo", "o/r",
                                                                   "--ref", "main"]]
