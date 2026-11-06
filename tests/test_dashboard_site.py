"""The dashboard as a GitHub Pages site (from the dashboard of aoe2mc): `tools/dashboard_site.py` gives the page the
runtime and the CSS tokens that it reads."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import dashboard_data  # noqa: E402
import dashboard_site  # noqa: E402


def test_the_site_page_holds_the_runtime_d3_and_the_artifact_page(tmp_path):
    assert dashboard_site.main([str(tmp_path), "--no-data"]) == 0
    html = (tmp_path / "index.html").read_text()
    assert html.startswith("<!doctype html>") and dashboard_site.D3 in html
    assert "window.dash" in html and open(dashboard_site.PAGE).read() in html
    for name, file in dashboard_data.DATASETS.items():
        assert f'"{name}": "{file}"' in html                 # the runtime fetches each data file


def test_the_runtime_gives_each_dash_call_and_css_token_of_the_page():
    page = open(dashboard_site.PAGE).read()
    calls = set(re.findall(r"dash\.(\w+)", page))
    assert calls <= set(re.findall(r"^    (\w+)[:,]", dashboard_site.RUNTIME, re.M))
    tokens = set(re.findall(r"var\((--(?:cds|color|font)-[\w-]+)", page))
    assert tokens <= set(re.findall(r"(--[\w-]+):", dashboard_site.TOKENS))
