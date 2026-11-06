import json, re, sys
from playwright.sync_api import sync_playwright
S = sys.argv[1]; B = "http://127.0.0.1:8077"; TOK = open(f"{S}/tok").read().strip()
def leg(dep, arr, carrier):
    return {"mode": "train", "carrier": carrier, "from_name": "Amsterdam", "to_name": "Berlin",
            "depart_at": f"2026-12-10T{dep}:00+01:00", "arrive_at": f"2026-12-10T{arr}:00+01:00"}
def offers():
    return [{"external_id": "slow", "price_amount": "40.00", "price_currency": "EUR", "legs": [leg("08", "14", "SlowRail")]},
            {"external_id": "fast", "price_amount": "80.00", "price_currency": "EUR", "legs": [leg("09", "11", "FastRail")]}]
out = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    shot = lambda n: pg.screenshot(path=f"{S}/shots/{n}.png", full_page=True)
    pg.goto(B + "/login"); pg.fill("input[name=password]", "pw"); pg.click("button[type=submit]")
    ids = []
    for t in ("Check C", "Check D"):
        pg.goto(B + "/trips/new"); pg.fill("input[name=title]", t); pg.click("form button[type=submit]")
        pg.wait_for_load_state()
        ids.append(int(re.search(r"/trips/(\d+)", pg.locator("tr", has_text=t).last.locator("a", has_text="Edit").get_attribute("href")).group(1)))
    for i in ids:
        r = pg.request.post(B + "/api/ingest", headers={"Authorization": f"Bearer {TOK}"}, data=({
            "trip_id": i, "source": "manual", "captured_at": "2026-11-06T18:00:00+00:00", "offers": offers()}),
            )
        out[f"ingest{i}"] = (r.status, r.text()[:200])
    pg.goto(f"{B}/trips/{ids[0]}"); shot("1_trip1")
    first = lambda: pg.locator("#table tbody tr").first.inner_text()[:120].replace("\n", " ")
    out["step1_first"] = first()
    def save(v, name):
        pg.goto(f"{B}/trips/{ids[0]}?hour_markup={v}")
        pg.click("summary:has-text(\"Advanced\")")
        pg.fill("input[name=name][form=save-profile]", name); pg.click("button[form=save-profile]")
        pg.wait_for_load_state(); out[f"save_{name}"] = pg.url
    save(50, "Fast"); shot("2_saved_fast"); save(0, "Cheap"); shot("2_saved_cheap")
    pg.goto(B + "/profiles"); out["profiles_before"] = pg.locator("table").inner_text()
    pg.locator("tr", has_text="Fast").locator("button", has_text="Set default").click(); pg.wait_for_load_state()
    pg.goto(B + "/profiles"); out["profiles_after"] = pg.locator("table").inner_text(); shot("3_profiles")
    pg.goto(f"{B}/trips/{ids[1]}/edit"); pg.select_option("select[name=profile_id]", label="Cheap"); shot("3_edit_trip2")
    pg.click("form button[type=submit]"); pg.wait_for_load_state()
    for k, i in enumerate(ids):
        pg.goto(f"{B}/trips/{i}"); shot(f"4_trip{k+1}")
        out[f"step4_trip{k+1}"] = {"first": first(), "profile": pg.locator("select[name=profile] option:checked").inner_text(),
                                   "hour": pg.locator("input[type=range][name=hour_markup]").input_value()}
    pg.goto(f"{B}/trips/{ids[1]}")
    pg.select_option("select[name=profile]", label="Fast"); pg.click("text=Use profile"); pg.wait_for_load_state()
    out["switch_url"] = pg.url; out["switch_hour"] = pg.locator("input[type=range][name=hour_markup]").input_value()
    out["switch_first"] = first()
    pg.locator("input[type=range][name=hour_markup]").fill("20"); pg.wait_for_timeout(1500)
    out["slider_url"] = pg.url
    out["slider"] = {"profile": pg.locator("select[name=profile] option:checked").inner_text(),
                     "hour": pg.locator("input[type=range][name=hour_markup]").input_value(),
                     "output": pg.locator("output[name=hour_value]").inner_text(), "first": first()}
    shot("4_switch_slider")
    pg.reload(); out["after_reload"] = {"profile": pg.locator("select[name=profile] option:checked").inner_text(),
                                         "hour": pg.locator("input[type=range][name=hour_markup]").input_value()}
    b.close()
print(json.dumps(out, indent=1))
