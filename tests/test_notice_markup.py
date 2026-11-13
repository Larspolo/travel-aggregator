"""The markup of a high notice of the operator (epic #2694): one part "notice: <start>" for the first high notice."""

from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.risk import notice_extras


def _it(notices):
    return SimpleNamespace(legs=[], notices=notices)


def _w(markup=Decimal("15")):
    return Weights(notice_markup=markup)


def test_a_long_high_notice_is_cut_at_a_word_and_marked_with_an_ellipsis():
    it = _it([{"text": "Bauarbeiten: Ersatzverkehr mit Bussen", "level": "high", "leg": 0}])
    assert notice_extras(it, _w()) == (("notice: Bauarbeiten: Ersatzverkehr …", Decimal("15")),)


def test_a_short_high_notice_is_shown_whole():
    it = _it([{"text": "Track repairs", "level": "high", "leg": 0}])
    assert notice_extras(it, _w()) == (("notice: Track repairs", Decimal("15")),)


def test_the_first_high_notice_is_used_and_low_notices_are_skipped():
    it = _it([
        {"text": "Low remark", "level": "low", "leg": 0},
        {"text": "First high notice", "level": "high", "leg": 0},
        {"text": "Second high notice", "level": "high", "leg": 1},
    ])
    assert notice_extras(it, _w()) == (("notice: First high notice", Decimal("15")),)


def test_a_text_with_no_space_in_the_first_28_characters_is_cut_at_28():
    text = "Abcdefghijklmnopqrstuvwxyz0123456789"
    it = _it([{"text": text, "level": "high", "leg": 0}])
    assert notice_extras(it, _w()) == (("notice: " + text[:28] + " …", Decimal("15")),)


def test_no_notices_or_only_low_notices_give_no_part():
    assert notice_extras(_it(None), _w()) == ()
    assert notice_extras(_it([]), _w()) == ()
    assert notice_extras(_it([{"text": "Low remark", "level": "low", "leg": 0}]), _w()) == ()


def test_a_markup_of_zero_gives_no_part():
    it = _it([{"text": "Track repairs", "level": "high", "leg": 0}])
    assert notice_extras(it, _w(Decimal("0"))) == ()
