"""mismatch() (#555): the offers of a capture match the places and the date of the trip."""

from datetime import date

from app.models import Trip
from app.schemas import OfferIn
from app.tripmatch import mismatch


def leg(from_name, to_name, depart="2026-12-20T07:34:00+01:00", from_code=None, to_code=None):
    return {"mode": "train", "from_name": from_name, "to_name": to_name, "from_code": from_code, "to_code": to_code,
            "depart_at": depart, "arrive_at": "2026-12-20T14:02:00+01:00"}


def offer(from_name="Amsterdam Centraal", to_name="Zürich HB", **kw):
    return OfferIn.model_validate({"price_amount": "89.90", "price_currency": "EUR", "legs": [leg(from_name, to_name,
                                                                                                  **kw)]})


def trip(origin="Amsterdam", destination="Zurich", date_from=date(2026, 12, 20), date_to=None):
    return Trip(title="T", origin_text=origin, destination_text=destination, date_from=date_from, date_to=date_to)


def test_the_correct_places_and_date_match():
    assert mismatch(trip(), [offer()]) is None


def test_another_destination_is_a_places_mismatch():
    assert mismatch(trip(), [offer(to_name="Lisboa Oriente")]) == "places"


def test_a_date_one_day_after_the_end_is_a_date_mismatch():
    t = trip(date_from=date(2026, 12, 18), date_to=date(2026, 12, 19))
    assert mismatch(t, [offer(depart="2026-12-20T07:34:00+01:00")]) == "date"


def test_the_last_day_of_the_range_matches():
    t = trip(date_from=date(2026, 12, 18), date_to=date(2026, 12, 20))
    assert mismatch(t, [offer()]) is None


def test_the_local_date_of_the_offer_counts_not_utc():
    # 00:30 on 20 December in +01:00 is 19 December in UTC: the local date is the one that counts
    assert mismatch(trip(), [offer(depart="2026-12-20T00:30:00+01:00")]) is None


def test_empty_texts_and_no_dates_match_each_offer():
    assert mismatch(trip(origin="", destination=None, date_from=None), [offer(to_name="Lisboa Oriente")]) is None


def test_one_matching_offer_of_three_gives_none():
    offers = [offer(to_name="Lisboa Oriente"), offer(), offer(from_name="Brussel Zuid")]
    assert mismatch(trip(), offers) is None


def test_the_code_of_a_station_matches_the_text():
    t = trip(origin="AMS", destination="ZRH")
    assert mismatch(t, [offer(from_name="Schiphol", to_name="Flughafen", from_code="ams", to_code="zrh")]) is None


def test_a_word_of_two_letters_does_not_match():
    assert mismatch(trip(origin="NL"), [offer(from_name="NL Den Haag")]) == "places"


def test_no_offers_gives_none():
    assert mismatch(trip(), []) is None
