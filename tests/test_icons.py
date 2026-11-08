"""The templates use the self-hosted SVG icons, not emoji (#624)."""
import re
from pathlib import Path

from app.web.pages import MODE_ICONS

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "web" / "templates"
SPRITE = (ROOT / "app" / "web" / "static" / "icons.svg").read_text()
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")
LIST = ["train", "bus", "plane", "walk", "pin", "eye", "eye-off", "check", "plus", "arrow-left",
        "arrow-right-left", "calendar-plus", "upload", "settings", "user", "map-pin", "key", "log-out", "menu",
        "trash", "chart", "git-compare"]


def symbols():
    return set(re.findall(r'<symbol id="([\w-]+)"', SPRITE))


def test_sprite_has_each_icon_with_stroke():
    for name in LIST:
        m = re.search(rf'<symbol id="{name}"[^>]*>', SPRITE)
        assert m, name
        assert 'fill="none"' in m.group(0) and 'stroke="currentColor"' in m.group(0), name
    assert "ISC" in SPRITE and "0.453.0" in SPRITE


def test_no_emoji_in_templates():
    for p in TEMPLATES.rglob("*.html"):
        for i, line in enumerate(p.read_text().splitlines(), 1):
            assert not EMOJI.search(line), f"{p.name}:{i}: {line.strip()}"


def test_each_icon_name_exists():
    names = set(MODE_ICONS.values())
    for p in TEMPLATES.rglob("*.html"):
        text = p.read_text()
        names |= set(re.findall(r"icons\.svg#([\w-]+)", text))
        names |= set(re.findall(r'icon\("([\w-]+)"', text))
        for m in re.finditer(r'\("(?:pin|hide|booked)",[^\]]*?\)', text):
            names |= set(re.findall(r'"([\w-]+)"\)', m.group(0)))
            names |= set(re.findall(r'"(eye(?:-off)?)"', m.group(0)))
    assert "pin" in names and "check" in names
    assert names <= symbols(), names - symbols()
