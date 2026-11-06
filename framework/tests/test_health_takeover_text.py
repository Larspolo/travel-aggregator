"""health.takeovers() reads a "Taken over by" comment in free text, and skips one with no branch name (#4751 crashed
`health.py` on 2026-10-31)."""
import health


def c(n, t, body):
    return {"issue_url": f"https://api.github.com/repos/o/r/issues/{n}", "created_at": f"2026-10-27T{t}:00Z",
            "body": body}


def test_free_text_takeover_names_its_claim():
    comments = [c(10, "01:00", "Started by `b/a`."),
                c(10, "02:00", "Taken over by the pacer run for #10 (claim `b/x`). The quick CI was red.")]
    rows = health.takeovers(comments, [])
    assert [(i, old) for _, i, old, _, _ in rows] == [(10, "b/a")]


def test_takeover_without_a_branch_is_skipped():
    comments = [c(10, "01:00", "Started by `b/a`."), c(10, "02:00", "Taken over by another run.")]
    assert health.takeovers(comments, []) == []
