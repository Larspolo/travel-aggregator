"""Give the next release version: one minor step after the newest tag v0.N.0 (#86).

    git tag --list 'v*' | python3 tools/release_version.py

Prints `v0.1.0` when no tag `v0.*` exists. One minor step per closed epic: an epic is one feature for the user, and
there is no 1.0 promise before the MVP. `.github/workflows/release.yml` uses it.
"""
import re
import sys

TAG = re.compile(r"^v0\.(\d+)\.(\d+)$")


def next_version(tags):
    minors = [int(m.group(1)) for m in (TAG.match(t.strip()) for t in tags) if m]
    return f"v0.{max(minors) + 1 if minors else 1}.0"


if __name__ == "__main__":
    print(next_version(sys.stdin.read().split()))
