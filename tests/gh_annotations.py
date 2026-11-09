"""The failed tests of a CI step as GitHub annotations (#1443).

`failures()` of framework/tools/ship_pr.py reads the failure annotations of a red check run: the cloud cannot read the
job logs well, and the end of a log is the PostgreSQL service, not the failed test. `pytest_terminal_summary` of
tests/conftest.py writes these lines when `GITHUB_ACTIONS` is `true`; GitHub turns each `::error` line into an
annotation. GitHub keeps at most 10 error annotations of a step, so the 10th line gives the count of the rest.
"""

LIMIT = 10


def escape(text, prop=False):
    """The text of a workflow command: `%`, CR and LF escaped, and also `:` and `,` in a property."""
    text = str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return text.replace(":", "%3A").replace(",", "%2C") if prop else text


def message(report):
    """The first line of the crash message of a report, else the last line of its text."""
    crash = getattr(report.longrepr, "reprcrash", None)
    text = crash.message if crash is not None else str(report.longrepr or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "no message"
    return (lines[0] if crash is not None else lines[-1])[:300]


def lines(reports):
    """One `::error` line per failed or error report, at the `def` line of the test (at most LIMIT lines)."""
    out = []
    for report in reports:
        path, lineno = report.location[0], report.location[1]
        where = f"file={escape(path, True)}" + (f",line={lineno + 1}" if lineno is not None else "")
        out.append(f"::error {where},title={escape('failed test', True)}::"
                   f"{escape(report.nodeid)} - {escape(message(report))}")
    if len(out) > LIMIT:
        rest = len(out) - (LIMIT - 1)
        out = out[:LIMIT - 1] + [f"::error title=more failed tests::{rest} more failed tests: see the job log"]
    return out
