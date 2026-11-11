"""`png_ok` of `[git]` in `agent.toml` names the folders where a .png belongs in git (#853)."""
import health

FILES = [("app/web/static/icon-192.png", 4096), ("app/logo.png", 10), ("docs/a.png", 10),
         ("app/web/static/big.png", 2 << 20), ("logs/latest.log", 10)]


def test_png_ok_allows_its_folders():
    ok = ["docs/", "samples/", "app/web/static/"]
    assert health.bad_files(FILES, png_ok=ok) == [("app/logo.png", 10), ("app/web/static/big.png", 2 << 20),
                                                  ("logs/latest.log", 10)]


def test_default_is_docs_and_samples():
    assert health.bad_files(FILES, png_ok=("docs/", "samples/")) == [
        ("app/web/static/icon-192.png", 4096), ("app/logo.png", 10), ("app/web/static/big.png", 2 << 20),
        ("logs/latest.log", 10)]

