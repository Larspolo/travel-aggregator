# DESIGN.md – the look of the travel-aggregator pages

Status: version 3 (2026-11-07). Agents: read this file before you change a page in `app/web/templates/` or the CSS.

## 0. What the owners said, and what the agents chose

Only section 1 has the requirements of the owners. All other sections are the choices of the agents to meet them.
When a better look needs a change of sections 2 to 10, change them. Do not write a choice of the agents as an owner
rule, and do not make a rule from the reasons of a recommendation.

Version 2 had limits that no owner asked for: "system fonts only, no web font", "no CSS framework", "no own
JavaScript" and plain browser controls. They came from a wide reading of P4 ("keep the dependencies few"). The owners
removed them (Larspolo, 2026-11-07: option A of #535 means only "dense").

## 1. Requirements of the owners

- **Dense** (#535, option A). Many offers on one screen. This is the only part of option A that the owners chose.
  The colours, the borders and the fonts of option A were not part of the choice.
- **Better and modern, on all pages** (#619, #621). "We want the entire UI to be better and modern."
- **Intuitive to navigate** (#619).
- **Common libraries and frameworks are allowed** (Jeroenvb3, #619): "Feel free to use very common frameworks like
  bootstrap, jquery, alpine, materialdesign, bootstrap logos or others. not needed but you can use common libraries
  and frameworks if it helps to organise this."
- **The stack** (`docs/SPEC.md`, "Stack"): server-rendered pages (Jinja2) with htmx, Alpine.js or plain JavaScript.
  No SPA build chain, and no Node to build the image.
- **Escape all captured text** (P5). A design change never uses `| safe` on captured data.
- **Phone width** (`steering/project/PRINCIPLES.md`, "Try a feature"): the agents check each page at 390 px
  (sideways scroll, control sizes, screenshots) and at 1280 px. Each PR that changes a page has these screenshots.
- **The ranking stays clear** (P2): the price, hour and transfer weights are visible; the breakdown shows each part.

## 2. Tokens (agent choice)

All colours, radii, shadows and text sizes are CSS variables in `:root` of `app/web/static/app.css`. The rules use
the variables, so that light and dark mode stay in one place (`tests/test_pages_theme.py` checks it).

| Token | Role | Light | Dark |
|---|---|---|---|
| `--bg` | The page background | `#f5f5f7` | `#0c0c0f` |
| `--surface` | Cards, panels, the app bar, the inputs | `#ffffff` | `#15151a` |
| `--surface-2` | The table head, a row on hover, code | `#f8f8fa` | `#1b1b21` |
| `--text` | Body text and numbers | `#17171c` | `#ececf0` |
| `--muted` | Secondary text: source, "2h ago", the breakdown, help text | `#5d5d68` | `#9b9ba6` |
| `--line` | Borders and the lines between rows | `#e3e3e8` | `#2a2a31` |
| `--accent` | Links, the focus ring, the primary button, the slider, the check boxes | `#5145d6` | `#8f87ff` |
| `--accent-text` | Text on `--accent` | `#ffffff` | `#0c0c0f` |
| `--accent-soft` | The active app bar link, the slider values, "booked" | `#eeedfd` | `#23214a` |
| `--good` | "Best value", "price dropped", a capture that is ok | `#187a35` | `#43c164` |
| `--info` | "Cheapest" and "fastest" | `#0a64c9` | `#5eaaff` |
| `--warn` | "Stale", no backup or an old backup | `#9a4f00` | `#e3a03f` |
| `--danger` | Delete actions, a failed capture, an error text | `#c4302b` | `#f47067` |
| `--shadow`, `--shadow-sm` | The depth of a card and of a control | soft shadows | `none` |
| `--ring` | The focus ring of an input | accent, 22 % | accent, 30 % |

Other tokens: `--space-1` to `--space-6` (4, 8, 12, 16, 24, 32 px), `--radius` 8 px (inputs, buttons),
`--radius-lg` 12 px (cards, menus), `--text-sm` 12.5 px, `--text-lg` 16 px, `--text-xl` 22 px, `--font`.

Badges and chips are tinted: the status colour as text on a light mix of it (`color-mix()`), not a full fill.

## 3. Typography (agent choice)

- Font: Inter 4.0, self-hosted in `app/web/static/fonts/` (Latin subsets in WOFF2, about 60 kB per weight, OFL
  licence in the folder), with the system fonts as the fallback. Inter is made for dense screens and has tabular
  numbers. The files are in the repository, so the pages make no request to another host.
- Size: 14 px body text on a computer (dense), 16 px on a phone (no zoom on input focus in iOS).
- Page title `--text-xl` weight 650, card title `--text-lg` weight 600, labels `--text-sm` weight 500, table heads
  `--text-sm` weight 600 in `--muted`.
- All prices, costs, times and durations use `font-variant-numeric: tabular-nums`.
- The effective cost is the largest number in a row. The ticket price is normal text.
- One money format: the symbol before the number and two decimals (`€80.90`; the code only when the currency has no
  symbol).
- Times: `07:34`, with "+1 day" after an arrival on a later day. Dates: `Sun 20 Dec`.

## 4. Components (agent choice)

The Jinja2 macros of the components are in `app/web/templates/ui.html`.

- **App bar.** A white bar over the full width, sticky: the brand at the left, the main links with an icon (Trips,
  Upcoming, Captures, Settings), Log out at the right. The current page has `--accent-soft`. On a phone: the
  brand and a "Menu" button.
- **Page header.** A back link above the title when the page has a parent page, the `<h1>`, a muted subtitle, and
  a toolbar with the actions of the page at the right. At most three or four buttons: put the actions that people
  use less often in a "More" menu (`details.more`, as on the trip page).
- **Card.** The container of each group of content: `--surface`, a `--line` border, `--radius-lg`, `--shadow`.
- **Buttons.** `.btn` (secondary), `.btn-primary` (the one main action of a page), `.btn-ghost` (Cancel, small
  actions), `.btn-danger` (delete), `.btn-icon` (a square icon button). 34 px high on a computer, 44 px on a phone.
- **Inputs and fields.** A `.field` has the label above the input and the help or error text under it. Inputs have a
  soft shadow and the `--ring` on focus. Check boxes, radios and sliders are drawn in the accent colour. On a phone,
  each check box has a hit area of 40 px around a box of 20 px.
- **Tables.** In a card. The head is `--surface-2` in `--muted`; the sort links are not underlined. On the trip page,
  the row of an itinerary and its "Legs and fares" row read as one item (no line between them).
- **Cost cell.** The effective cost, a thin bar with one segment per part of the breakdown, and the text breakdown.
- **Badges and chips.** Small tinted pills with a text label. Never colour only.
- **Icons.** The Lucide subset in `app/web/static/icons.svg`, through the `icon` macro. No emoji as an icon.
- **Empty state.** One short sentence (and an action when the page has no action for it yet) in a card.
- **Disclosure.** `<details>` with a chevron that turns when it opens.
- **Motion.** Short transitions (120 ms). `prefers-reduced-motion: reduce` turns them off.

## 5. Layout (agent choice)

- The page is at most 80 rem wide, centred. A page with only a form has a form card of at most 48 rem.
- Trip page on a computer (wider than 64 rem): the weights panel at the left (17 rem, a sticky card), the ranked table
  at the right (a card). The price, hour and transfer controls are always open at the top of the panel (P2). The
  filters and "Advanced" (fieldsets: Airport, Time windows, Night, Modes, Fares, Staleness, Profile) are below them.
- A row of the ranked table is at most 4 text lines high at 1280 px (`tests/test_trip_rows_look.py`).
- Settings (#925): all settings pages are in one area with one link "Settings" in the app bar.
  - Each settings page extends `settings_base.html`: the page header at the top, the settings navigation at the left
    (14 rem, sticky), the cards at the right (at most 48 rem). On a phone the navigation is two columns of links under
    the header. The navigation replaces the back links and the links to sub-pages in a toolbar.
  - The groups and their pages are one list, `SETTINGS_NAV` in `app/web/pages.py`: App (General, Messages),
    Ranking (Profiles, Places, Exchange rates), Capture (Userscripts, Add a website). A new setting goes on the page
    of its topic; a new topic is one more page of `SETTINGS_NAV`, in the group that it changes.
  - Each card with fields is one form with its own Save button, and the Save saves only the fields of that card.
    A list (profiles, places, rates, tokens) saves each change at once with the button of its row or of its "Add"
    card. A button that acts only on this device (Web Push) acts at once and says so.
- Trips list: one card per trip in a grid. Login: one card of at most 24 rem in the middle of the page.

## 6. Responsive behaviour (agent choice)

- At 40 rem or less (test at 390 px): the app bar has the brand and "Menu"; the toolbar goes under the title.
- Each itinerary is a card: route, times, mode icons, the effective cost and the badges first; the check box and the
  row actions in one row at the end; "Legs and fares" at the bottom.
- The weights panel is one closed `<details>` above the list ("Weights and filters").
- No sideways scroll on any page at 390 px.

## 7. Libraries

- Allowed: common libraries and frameworks (section 1), for example Alpine.js, Bootstrap or an icon set.
- Put a library in `app/web/static/` with its licence and version (no build step). This is an agent choice: the pages
  then work without a request to another host.
- Now the app uses htmx, Inter and the Lucide icon subset. There is no CSS framework: the own CSS on the tokens is
  short and already has all components. Add one when it makes the pages better or the CSS much shorter.

## 8. Practices (agent choice)

- Keep the CSS in `app/web/static/app.css`, in its sections (`/* == Base == */`, `/* == App bar == */`,
  `/* == Page header == */`, `/* == Cards == */`, `/* == Forms == */`, `/* == Tables == */`, `/* == Trip page == */`,
  `/* == Trips list == */`, `/* == Login == */`, `/* == Phone == */`): parallel tickets then change different lines.
- Use the components of section 4; do not make a second style of the same thing.
- Keep the contrast of text on its background at 4.5:1 or more, in light and dark mode.
- No inline `style=` attribute (`tests/test_page_checklist.py`).
- A new extra of the ranking is one more part of the breakdown, not a new column (P2).

## 9. Agent prompt guide

- "Change the trip page: follow `DESIGN.md`, and add screenshots at 1280 px and 390 px, light and dark, to the PR.
  Look at the screenshots with realistic data before the PR: a page that meets the checklist but looks plain is not
  done."
- Check a page change with Playwright at 1280 px and with a phone device, in light and dark colour scheme.

## 10. Page checklist (agent choice)

Each page meets these points at 1280 px and 390 px, in light and dark mode. `tests/test_page_checklist.py` checks the
points that the HTML can show (the `<h1>`, one primary button, labels, icons, no emoji, no `style=`):

1. The app bar of section 4, and no second link line that repeats it.
2. A page header with exactly one `<h1>`; the actions of the page in its toolbar.
3. The content in cards; tables in a card; no sideways scroll of the page.
4. At most one primary button; "Cancel" is a ghost button; delete is a danger button.
5. Each field has a `<label>` above it; help and error texts under the field.
6. Icons only from `icons.svg`; no emoji; no colour without a text.
7. An empty list shows the empty state.
8. All amounts in one money format; numbers in `tabular-nums`.
9. A visible focus ring on each control; hit areas of 40 px or more on a phone.
10. Colours only from the tokens; no `style=` attribute.
