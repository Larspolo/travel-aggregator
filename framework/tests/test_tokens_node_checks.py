"""framework/tools/tokens.py: the Node checks in the verify field (#810). A command gets its slowest check kind, so the
lint and fast tests of a Node project count as Vitest, not as `ruff`."""
import tokens


def test_the_lint_and_fast_tests_of_one_file_are_vitest_files():
    cmd = "ruff check . && npx @biomejs/biome check . && npx vitest run tests/booking_move_link_email.test.ts"
    assert tokens.check(cmd) == "vitest files"


def test_the_whole_vitest_suite_and_biome():
    assert tokens.check("npx vitest run") == "vitest"
    assert tokens.check("npx @biomejs/biome check --write .") == "biome"
    assert tokens.check("ruff check . && npx @biomejs/biome check .") == "ruff"


def test_browser_build_and_speed_checks():
    assert tokens.check("npx playwright test e2e/booking-move.spec.ts --project=phone") == "playwright"
    assert tokens.check("npm run build 2>&1 | tail -20") == "build"
    assert tokens.check("npx next build") == "build"
    assert tokens.check("npm run build && node scripts/lighthouse.mjs --cls 0.1") == "lighthouse"
    assert tokens.check("npm run build && npx playwright test") == "playwright"


def test_the_python_kinds_stay():
    assert tokens.check("python3 -m pytest -q && npx vitest run") == "pytest"
    assert tokens.check("python3 -m pytest tests/test_a.py") == "pytest files"
    assert tokens.check("ruff check .") == "ruff"
    assert tokens.check("npm ci") is None
