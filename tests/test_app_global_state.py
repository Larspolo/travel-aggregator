"""Global state of the app has a `reset()` method, so the autouse fixture `_reset_limiters` of `tests/conftest.py`
resets it before each test (#521: a limiter of one test locked the API for the next tests on the same xdist worker)."""
import collections
import sys


def test_each_module_level_state_of_the_app_has_reset():
    import app.main  # noqa: F401 (loads all modules of the app)

    bad = []
    for name, module in sorted(sys.modules.items()):
        if name != "app" and not name.startswith("app."):
            continue
        for attr, obj in vars(module).items():
            if attr.startswith("__") or isinstance(obj, type):
                continue
            mutable = isinstance(obj, (dict, list, set, collections.deque)) and not attr.isupper()
            own = type(obj).__module__.startswith("app.") and vars(obj) if hasattr(obj, "__dict__") else False
            if (mutable or own) and not callable(getattr(obj, "reset", None)):
                bad.append(f"{name}.{attr}")
    assert not bad, (f"module-level state with no reset(): {bad}. Put it in a class with a reset() method: the "
                     "fixture _reset_limiters of tests/conftest.py then resets it before each test (#521)")


def test_the_fixture_finds_the_limiters(app_state_objects):
    from app.auth import api_limiter, login_limiter, token_limiter

    found = app_state_objects
    assert all(any(x is obj for x in found) for obj in (api_limiter, login_limiter, token_limiter))
