"""The weights are a side panel; "Advanced" has one fieldset per group of DESIGN.md section 5 (#592)."""

import re

from tests.test_trip_hide import trip  # noqa: F401

GUARDS = ("app/web/templates/trip*.html", "app/web/pages.py")   # ship_pr runs this file for these changes: no import leads to it (#730)

GROUPS = ["Hour tiers", "Airport", "Time windows", "Night", "Modes", "Carriers", "Transfer places", "CO₂", "Fares", "Staleness", "Profile"]
NAMES = {"hour_markup", "transfer_markup", "show_hidden", "show_departed", "hide_stale", "sort", "dir", "mode", "earliest_depart",
         "latest_arrive", "day", "source", "max_transfers", "max_duration_min", "airport_before_min", "airport_after_min",
         "baggage_fee", "early_limit", "late_limit", "time_window_penalty", "night_start", "night_end", "night_min",
         "night_adjust", "overnight_min", "overnight_cost", "wait_hour_markup", "night_hour_markup", "short_transfer_min", "short_transfer_penalty", "station_change_min", "station_change_penalty", "no_fallback_penalty", "stale_hours",
         "stale_penalty", "hour_tier1_after_min", "hour_tier1_markup", "hour_tier2_after_min", "hour_tier2_markup",
         "train_markup", "bus_markup", "flight_markup", "ferry_markup", "co2_price_kg", "co2_train_kg_h",
         "co2_bus_kg_h", "co2_flight_kg_h", "co2_ferry_kg_h", "flex_non_refundable",
         "flex_partly_refundable", "flex_flexible", "first_class_hour", "self_transfer_penalty", "reservation_fee", "exclude_mode", "exclude_carrier",
         "carrier1_name", "carrier1_markup", "carrier2_name", "carrier2_markup", "carrier3_name", "carrier3_markup",
         "transfer_place1_name", "transfer_place1_markup", "transfer_place2_name", "transfer_place2_markup",
         "transfer_place3_name", "transfer_place3_markup",
         "train_hour_markup", "bus_hour_markup", "flight_hour_markup", "ferry_hour_markup",
         "night_seat_adjust", "night_couchette_adjust", "night_sleeper_adjust"}


def _form(html):
    return html[html.index('<form class="weights"'):html.index("</form>", html.index('<form class="weights"'))]


def test_the_panel_has_the_main_controls_first_and_a_fieldset_per_group(trip):  # noqa: F811
    client, trip_id = trip
    html = client.get(f"/trips/{trip_id}").text
    assert html.index('<aside class="panel card"') < html.index('<form class="weights"') < html.index('id="table"')
    form = _form(html)
    assert form.index('name="hour_markup"') < form.index("<details")
    assert form.index('name="transfer_markup"') < form.index("<details")
    advanced = form[form.index('<details class="advanced">'):]
    assert re.findall(r"<fieldset><legend>([^<]+)</legend>", advanced) == GROUPS
    fieldsets = re.findall(r"<fieldset>.*?</fieldset>", advanced, flags=re.S)
    outside = re.sub(r"<fieldset>.*?</fieldset>", "", advanced, flags=re.S)
    assert "<input" not in outside and sum(f.count("<input") for f in fieldsets) == 60  # 6 transfer place inputs (#1851)


def test_each_input_name_of_the_form_is_still_sent(trip):  # noqa: F811
    client, trip_id = trip
    form = _form(client.get(f"/trips/{trip_id}").text)
    names = set(re.findall(r'<(?:input|select)[^>]*name="([^"]+)"', form)) - {"name"}
    assert NAMES <= names | {"exclude_mode", "exclude_carrier"}
    assert names - {"exclude_mode", "exclude_carrier", "profile"} <= NAMES
