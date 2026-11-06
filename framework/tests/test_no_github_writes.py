"""No test writes to the real repository (conftest.no_github_writes): a claim test posted "Started by `run-0`." on the
real issue #8 at each full run."""
import subprocess
import urllib.request

import claim
import pytest
from conftest import github_write


def test_github_write_tells_reads_from_writes():
    assert not github_write(["gh", "api", "repos/o/r/issues/8"])
    assert not github_write(["gh", "api", "repos/o/r/issues", "-X", "GET"])
    assert not github_write(["git", "push", "origin", "x"])
    assert github_write(["gh", "api", "repos/o/r/issues/8/comments", "-X", "POST", "--input", "-"])
    assert github_write(["gh", "api", "repos/o/r/labels", "-f", "name=x"])
    assert github_write(["gh", "issue", "comment", "8", "--body", "x"])
    assert github_write((), "POST") and not github_write((), "GET")


def test_a_write_fails_in_a_test():
    with pytest.raises(RuntimeError, match="must not write"):
        subprocess.run(["gh", "api", "repos/o/r/issues/8/comments", "-X", "POST"])
    req = urllib.request.Request("https://api.github.com/repos/o/r/issues/8/comments", method="POST", data=b"{}")
    with pytest.raises(RuntimeError, match="must not write"):
        urllib.request.urlopen(req)


def test_start_after_a_claim_writes_nothing(capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)        # the gh path, as in a cloud session
    claim.start(8, by="run-0")
    assert "the label or the comment failed" in capsys.readouterr().out
