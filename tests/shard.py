"""Split the selected tests over N CI jobs: `pytest -m slow -n auto --shard K/N` runs only part K (#1062).

The job `browser` of ci.yml runs as a matrix of N jobs, and each job runs one part of the slow tests. A part is a set of
whole test files, so that the module fixtures (a server, a browser) start in one job only. The split gives each file
to the part with the fewest tests yet (the largest files first). Each job selects the same tests, so the parts do not
overlap and together they are all the selected tests.
"""

from collections import Counter


def parse(value):
    """(K, N) of "K/N", with 1 <= K <= N."""
    try:
        k, n = (int(x) for x in value.split("/"))
    except ValueError:
        raise ValueError(f"--shard needs K/N, for example 1/2, not {value!r}") from None
    if not 1 <= k <= n:
        raise ValueError(f"--shard {value}: K must be from 1 to N")
    return k, n


def parts(counts, n):
    """{file: part 1..N}: each file (largest count first, then by name) goes to the part with the fewest tests yet."""
    load = [0] * n
    out = {}
    for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        k = min(range(n), key=lambda i: (load[i], i))
        load[k] += count
        out[name] = k + 1
    return out


def select(items, k, n, key=lambda item: item.nodeid.split("::")[0]):
    """(kept, deselected) items of part K of N."""
    part = parts(Counter(key(item) for item in items), n)
    kept = [item for item in items if part[key(item)] == k]
    return kept, [item for item in items if part[key(item)] != k]
