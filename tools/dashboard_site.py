"""Build the owner's dashboard (travel-aggregator Autopilot) as a static site for GitHub Pages (from the dashboard of aoe2mc).

    python3 tools/dashboard_site.py OUT_DIR             # OUT_DIR/index.html and OUT_DIR/data/*.json
    python3 tools/dashboard_site.py OUT_DIR --no-data   # only the page (a test, no GitHub calls)

The page is `tools/dashboard_artifact/index.html`, the same file that the claude.ai artifact showed. It calls the
runtime of the artifact type (`dash.calc`, `dash.data`, `dash.params`, `dash.setParams`, `dash.onData`,
`dash.setLink`, `dash.colors`), its CSS tokens (`--cds-*`, `--color-*`) and `d3`. RUNTIME and TOKENS below give the
same names, so one page serves both. The data files are those of `tools/dashboard_data.py`. The workflow
`dashboard-site.yml` builds and publishes the site: no Claude session and no quota.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard_data  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "tools", "dashboard_artifact", "index.html")
D3 = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"

# The CSS tokens that the page reads, light and dark (`prefers-color-scheme`).
TOKENS = """
:root { color-scheme: light dark;
  --font-anthropic-sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-anthropic-serif: Georgia, "Times New Roman", serif;
  --color-bg: #faf9f5; --color-panel: #ffffff; --color-fg: #1f1e1d; --color-fg-muted: #6b6a66;
  --color-border-line: #e5e3dc; --color-bad: #c0392b;
  --cds-text-secondary: #6b6a66; --cds-surface-popover: #ffffff; --cds-shadow-popover: 0 4px 16px rgb(0 0 0 / 0.12);
  --cds-border: 1px solid #e5e3dc; --cds-radius: 8px; --cds-dur-slow: 400ms;
  --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 16px; --cds-gap-lg: 24px;
  --cds-pad-xs: 4px; --cds-pad-sm: 8px; --cds-pad-md: 16px; --cds-pad-lg: 24px;
  --cds-font-size-caption: 12px; --cds-font-size-body: 15px; --cds-font-size-heading: 17px; --cds-font-size-title: 28px;
  --cds-font-weight-medium: 600;
  --cds-chart-grid: #ecebe6; --cds-chart-axis: #c9c7bf; --cds-chart-muted: #c9c7bf; --cds-chart-reference: #8a8984;
  --cds-chart-status-critical: #c0392b;
  --c0: #2f6fdb; --c1: #d9822b; --c2: #2e9d6a; --c3: #8c5fd1; --c4: #c94f7c; --c5: #6b8e23; }
@media (prefers-color-scheme: dark) { :root {
  --color-bg: #1c1b19; --color-panel: #262523; --color-fg: #ecebe6; --color-fg-muted: #a3a29c;
  --color-border-line: #3a3936; --color-bad: #ef6b5b;
  --cds-text-secondary: #a3a29c; --cds-surface-popover: #2f2e2b; --cds-border: 1px solid #3a3936;
  --cds-chart-grid: #33322f; --cds-chart-axis: #55534e; --cds-chart-muted: #55534e; --cds-chart-reference: #8f8d87;
  --cds-chart-status-critical: #ef6b5b;
  --c0: #6b9cf0; --c1: #eba15a; --c2: #5cc496; --c3: #ae8ae6; --c4: #e07ba0; --c5: #9cbc4a; } }
body { margin: 0; padding: 16px; background: var(--color-bg); color: var(--color-fg); }
body > .ax { max-width: 1200px; margin: 0 auto; }
.dash-skeleton { opacity: 0.4; }
[hidden] { display: none !important; }   /* the page sets display on .ax-page */
"""

# The runtime of the artifact type, as small as the page needs: calcs over the data files, parameters in the
# browser storage (a per-viewer convenience), a redraw on data, parameters and a resize.
RUNTIME = """
window.dash = (() => {
  const FILES = %s;
  const calcs = {}, raw = {}, subs = [];
  let cache = {}, loading = true, params = {};
  try { params = JSON.parse(localStorage.getItem('travel-aggregator-dash')) || {}; } catch (e) {}
  function data(name) {
    if (loading) return { status: 'loading', data: [] };
    if (name in cache) return cache[name];
    let out = { status: 'error', data: [] };
    try {
      if (name in raw) out = raw[name] ? { status: 'ok', data: raw[name] } : out;
      else if (calcs[name]) {
        const ins = calcs[name].inputs.map(data);
        if (ins.every((d) => d.status === 'ok')) out = { status: 'ok', data: calcs[name].fn(...ins.map((d) => d.data)) };
      }
    } catch (e) { console.error(name, e); }
    return (cache[name] = out);
  }
  const fire = () => subs.forEach((f) => f());
  let t;
  addEventListener('resize', () => { clearTimeout(t); t = setTimeout(fire, 150); });
  Promise.all(Object.entries(FILES).map(([n, f]) => fetch('data/' + f, { cache: 'no-cache' })
    .then((r) => (r.ok ? r.json() : null)).catch(() => null).then((j) => { raw[n] = j; })))
    .then(() => { loading = false; cache = {}; fire(); });
  return {
    calc: (name, spec) => { calcs[name] = spec; },
    data,
    params: () => params,
    setParams: (p) => { params = Object.assign({}, params, p); try { localStorage.setItem('travel-aggregator-dash', JSON.stringify(params)); } catch (e) {} fire(); },
    onData: (f) => { subs.push(f); f(); },
    setLink: (id) => history.replaceState(null, '', '#' + id),
    colors: ['var(--c0)', 'var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)'],
  };
})();
"""


def page(body):
    """The full HTML of the site: the tokens, d3, the runtime, then the page of the artifact."""
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>travel-aggregator Autopilot</title>\n'
            f'<style>{TOKENS}</style>\n<script src="{D3}"></script>\n'
            f'<script>{RUNTIME % json.dumps(dashboard_data.DATASETS)}</script>\n</head>\n<body>\n{body}\n</body>\n</html>\n')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir")
    ap.add_argument("--no-data", action="store_true", help="write only the page")
    a = ap.parse_args(argv)
    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "index.html"), "w") as f:
        f.write(page(open(PAGE).read()))
    return 0 if a.no_data else dashboard_data.main(os.path.join(a.out_dir, "data"))


if __name__ == "__main__":
    sys.exit(main())
