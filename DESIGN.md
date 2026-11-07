# DESIGN.md – the look of the travel-aggregator pages

Status: **chosen**, version 2. The visual theme is A2, "Modern dense tool" (#621, 2026-11-07): theme A of #535 with a
modern finish on all pages. Agents: read this file before you change a page in `app/web/templates/` or the CSS.

The form of this file follows the DESIGN.md files of the Awesome Design MD Gallery (https://design.hagicode.com/).
This file takes only style principles from it: no brand names, logos, fonts or exact brand colours.

## 1. Visual theme: A2, Modern dense tool

Calm and neutral, with one cool accent colour. The ranking and its breakdown stay the main content (P2), and the
table rows stay dense. Version 2 adds what version 1 did not give (owners on #619 and #621: "we want the entire UI to
be better and modern"):

- **One frame on each page.** The same app bar, then a page header with the title, a short subtitle and the actions
  of the page. The content is in cards. A user knows at once where they are and what they can do.
- **Air between groups, density inside them.** Space between the cards and the sections; compact rows in a table.
- **Clear controls.** Real buttons with one primary action per page, labels above the fields, icons from one set.
- **Soft depth.** Rounded cards with a light shadow in light mode, a border in dark mode.
- **Every page, not only the trip page.** A page that is not done in the new style is a bug of the look.

History: #535 compared four themes (A Dense tool, B Light dashboard, C Warm editorial, D System look); the owner chose
A. Its tickets #589 to #593 made the tokens, the cost cell, the row actions, the weights panel and the phone cards. #620
(for #619) made the top bar. #621 changed this file to version 2; its sub-issues apply it to each page.

The pages follow the colour scheme of the device (light or dark, `prefers-color-scheme`). There is no own switch.

## 2. Tokens

All colours, radii, shadows and text sizes are CSS variables in `:root`. A rule uses only the variables, never a
colour value.

| Token | Role |
|---|---|
| `--bg` | The page background |
| `--surface` | Cards, panels, the table head, an expanded row, the inputs |
| `--text` | Body text and numbers |
| `--muted` | Secondary text: source, "2h ago", the breakdown legend, help text |
| `--line` | Borders and the lines between rows |
| `--accent` | Links, the focus ring, the primary button, the slider |
| `--accent-text` | Text and icons on an `--accent` background |
| `--accent-soft` | The background of the active app bar link and of a selected row |
| `--good` | "Best value", "price dropped", a capture that is ok, a recent backup |
| `--info` | "Cheapest" and "fastest" |
| `--warn` | "Stale, price may have changed", no backup or an old backup |
| `--danger` | Delete actions, a failed capture, an error text |
| `--shadow` | The depth of a card and of the app bar |

Colour values (light / dark):

| Token | Light | Dark |
|---|---|---|
| `--bg` | `#f6f6f8` | `#0b0b0d` |
| `--surface` | `#ffffff` | `#16161a` |
| `--text` | `#18181b` | `#ededef` |
| `--muted` | `#5f5f69` | `#9a9aa3` |
| `--line` | `#e4e4e7` | `#2a2a30` |
| `--accent` | `#5b5bd6` | `#8b8bf5` |
| `--accent-text` | `#ffffff` | `#0b0b0d` |
| `--accent-soft` | `#ededfc` | `#1f1f3a` |
| `--good` | `#1a7f37` | `#3fb950` |
| `--info` | `#0969da` | `#58a6ff` |
| `--warn` | `#9a4f00` | `#e3a03f` |
| `--danger` | `#c4302b` | `#f47067` |
| `--shadow` | `0 1px 2px rgb(0 0 0 / .05), 0 2px 8px rgb(0 0 0 / .06)` | `none` |

Version 2 changes `--bg` and `--surface` in light mode: the page is light grey and the cards are white, so that the
cards stand out. In dark mode the cards are lighter than the page, as before.

Other tokens:

| Token | Value |
|---|---|
| `--space-1` to `--space-6` | 4, 8, 12, 16, 24 and 32 px |
| `--radius` | 8 px: inputs, buttons, chips with text |
| `--radius-lg` | 12 px: cards and panels |
| `--text-sm` | 13 px: help text, table head, chips, the breakdown |
| `--text-lg` | 18 px: the title of a card (`<h2>`) |
| `--text-xl` | 24 px: the page title (`<h1>`) |

## 3. Typography

- Font: the system font stack (`system-ui, sans-serif`). No web font: it is one more download and one more dependency (P4).
- Size: 15 px body text on a computer, 16 px on a phone (no zoom on input focus in iOS).
- Scale: page title `--text-xl` weight 650, card title `--text-lg` weight 600, body 15 px, small `--text-sm`. Labels
  are `--text-sm` weight 500 in `--text`. Table heads are `--text-sm` weight 600 in `--muted`.
- All prices, costs, times and durations use `font-variant-numeric: tabular-nums`, so that the columns align.
- The effective cost is the largest number in a row (1.15 em, weight 600). The ticket price is normal text.
- **One money format.** All amounts on a page use the same filter: the symbol before the number and two decimals
  (`€80.90`; the code only when the currency has no symbol). A page never shows `EUR 80.90` next to `€208.90`.
- Times: `07:34`, with "+1 day" after an arrival on a later day. Dates: `Sun 20 Dec`.

## 4. Components

The Jinja2 macros of the components are in `app/web/templates/ui.html` (P4: Jinja2 macros, no own JavaScript).

- **App bar.** One bar at the top of each page except the login page: the brand (icon and name) at the left, the main
  links with an icon (Trips, Captures, Profiles, Places, Settings), Log out at the right. The current page has
  `--accent-soft` and `aria-current="page"`. Sticky, with `--shadow`. At 40 rem or less: the brand and a "Menu"
  button (`<details class="menu">`, no JavaScript) that opens the links as a list with 44 px rows.
- **Page header.** Directly under the app bar. A back link above the title when the page has a parent page ("← Trip"),
  then the `<h1>`, a muted subtitle (for example the route and the dates), and a toolbar with the actions of the page
  at the right (under the title on a phone). Each page has exactly one `<h1>`, in the page header.
- **No second navigation.** A page never repeats the app bar as a link line. A link to a sub-page (API tokens,
  Exchange rates) is an action in the page header of its parent page (Settings).
- **Card.** The container of each group of content: `--surface`, a `--line` border, `--radius-lg`, `--shadow`,
  `--space-5` padding (`--space-4` on a phone). An optional card header has an `<h2>` and the actions of the card.
- **Buttons.** `.btn` classes: primary (`--accent` background, `--accent-text`) for the one main action of a page or
  a form; secondary (outlined, `--line` border, `--surface` fill) for the other actions; ghost (no border) for
  "Cancel" and small actions; danger (`--danger` text and border, filled only in the confirm step) for delete. Height
  36 px on a computer, at least 44 px on a phone. A button can have an icon before its text.
- **Icon buttons.** Pin, Hide, Booked, Edit and Delete in a row are square icon buttons (32 px, 44 px on a phone)
  with an `aria-label` and a `title`. They stay `<form method="post">` with the CSRF field, so they work without
  JavaScript.
- **Inputs and fields.** Each input is in a `.field`: the `<label for>` above the input, the help text under it in
  `--muted` `--text-sm`, and an error text in `--danger` with `role="alert"`. Inputs have the full width of their
  column, `--surface` background, a `--line` border, `--radius` and the `--accent` focus ring (2 px `outline`, 2 px
  offset). Use `accent-color: var(--accent)` for range, checkbox and radio inputs (P4: no own slider code). Each
  slider has an `<output>` with its value next to its label.
- **Forms.** A form is in a card. The fields are in a `.form-grid`: two columns from 40 rem (for example From and To
  next to each other), one column on a phone. The `.form-actions` row is at the end: the primary button first, then
  "Cancel" as a ghost button.
- **Tables.** In a card, with no outer border. A sticky head, the numbers at the right, a `--line` between rows and
  `--surface` on hover. A wide table scrolls inside its card (`.scroll`), never the page.
- **Cost cell.** The effective cost on top. Under it, a thin bar (6 px) with one segment per part of the breakdown,
  and the text breakdown ("€90 price + €62 time + €30 transfers") in `--muted`. The text stays: the bar alone does
  not tell the values (P2: the breakdown always shows each part).
- **Badges and chips.** A small pill (`--text-sm`) with a text label and a status colour: best value (`--good`),
  cheapest and fastest (`--info`), booked (`--accent`), stale (`--warn`), price dropped (`--good`); the status of a
  trip, the result of a capture, the state of a backup. Never colour only: each badge has text. A long explanation
  goes into `title`, not into the row.
- **Icons.** One icon set: the SVG sprite `app/web/static/icons.svg` (a subset of a common open set, with its licence
  in the file), used as `<svg class="icon" aria-hidden="true"><use href="/static/icons.svg#name"></use></svg>` through
  the `icon` macro. 16 px in text, 20 px in buttons, in `currentColor`. No emoji as an icon: they look different on
  each device.
- **Empty state.** A list with no items shows one short sentence, a muted icon and the primary action ("No trips yet."
  and "New trip"), not an empty table.
- **Panels.** `<details>` and `<fieldset>` for the groups of the weights form. No own JavaScript for open and close.
- **Motion.** Only short transitions (120 ms) of colour and shadow on hover and focus. `prefers-reduced-motion:
  reduce` turns them off.

## 5. Layout

- The page is at most 80 rem wide, centred. A page with only a form is at most 48 rem wide.
- Order of each page: app bar, page header, content. `--space-5` between the cards and the sections.
- Trip page on a computer (wider than 64 rem): the weights panel at the left (18 rem, a card), the ranked table at the
  right (a card). The price, hour and transfer controls are always open at the top of the panel (P2). The filters and
  "Advanced" are `<details>` groups below them.
- "Advanced" has fieldsets: Airport, Time windows, Night, Modes, Fares, Staleness, Profile.
- The table of the trip page: one row per itinerary, at most 4 text lines high; the route cell has the times, the mode
  icons, the duration and the transfers; the cost column at the right; the detail row opens below the row.
- Trips list (`/`): one card per trip in a grid (`repeat(auto-fill, minmax(18rem, 1fr))`) with the title, the route,
  the dates, the number of offers, the best offer and the status chip.
- Login: no app bar; one card of at most 24 rem in the middle of the page, with the brand above it.

## 6. Depth and elevation

- Two levels: the page (`--bg`) and the cards (`--surface` with `--shadow` and a `--line` border). The app bar has
  `--shadow` too. In dark mode `--shadow` is `none`, and the border and `--surface` show the level.
- No third level on a page, except the open phone menu.
- Radius: `--radius` (8 px) on inputs, buttons and chips with text; `--radius-lg` (12 px) on cards and panels.

## 7. Responsive behaviour

- Phone width (40 rem or less, test at 390 px): the app bar has the brand and the "Menu" button; the toolbar of the
  page header goes under the title and wraps.
- Each itinerary is a card, not a table row. The card shows the route, the times with "+1 day", the mode icons, the
  effective cost and the badges first; the selection check box and the row actions are in one row at the end. A tap
  opens the details.
- The weights panel is one `<details>` above the list ("Weights and filters"), closed by default, with the price,
  hour and transfer controls in the summary area.
- Hit areas of at least 44 × 44 px for each control.
- No horizontal scroll on any page at 390 px (`trip:mobile`, #310).

## 8. Do and do not

- Do use only the tokens of section 2. Do keep all CSS in `app/web/static/app.css` (no build step, `docs/SPEC.md`), in
  its sections (`/* == Base == */`, `/* == App bar == */`, `/* == Page header == */`, `/* == Cards == */`,
  `/* == Forms == */`, `/* == Tables == */`, `/* == Trip page == */`, `/* == Trips list == */`, `/* == Login == */`,
  `/* == Phone == */`): parallel tickets then change different lines.
- Do use the components and macros of section 4; do not make a second style of the same thing on one page.
- Do keep the contrast of text on its background at 4.5:1 or more, also for `--muted`, in light and dark mode.
- Do escape all captured text (P5). A design change never uses `| safe` on captured data.
- Do keep each form working without JavaScript (htmx only adds to it).
- Do not load a file from a CDN or another host (P5: the pages show private data and must work offline from the
  server). A common library (icons, a small CSS or JavaScript library) is allowed when it replaces much own code: put
  it in `app/web/static/` with its licence and version, and say in the PR why (P4).
- Do not add a full CSS framework (for example Bootstrap or Material) on top of the tokens: it brings a second set of
  tokens, sizes and class names into each template, and its look replaces theme A. Own CSS on the tokens is about
  as short (version 2 needs some hundred lines) and stays one system. The owners allowed a framework on #619 but did
  not ask for one.
- Do not add an inline `style=` attribute. Do not use emoji as icons.
- Do not show a new extra of the ranking as a new column: it is one more part of the breakdown (P2).

## 9. Agent prompt guide

- "Change the trip page: follow `DESIGN.md`, use only its tokens and components, keep the forms working without
  JavaScript, and add screenshots at 1280 px and 390 px, light and dark, to the PR."
- Check a page change with Playwright at 1280 px and with a phone device, in light and dark colour scheme.

## 10. Page checklist

Each page meets all these points at 1280 px and 390 px, in light and dark mode. `tests/test_page_checklist.py`
checks the points that the HTML can show (the `<h1>`, one primary button, labels, icons, no emoji, no `style=`):

1. The app bar of section 4, and no second link line that repeats it.
2. A page header with exactly one `<h1>`; the actions of the page in its toolbar.
3. The content in cards; tables in a card; no sideways scroll of the page.
4. At most one primary button; "Cancel" is a ghost button; delete is a danger button.
5. Each field has a `<label>` above it; help and error texts under the field.
6. Icons only from `icons.svg`; no emoji; no colour without a text.
7. An empty list shows the empty state with its action.
8. All amounts in one money format; numbers in `tabular-nums`.
9. A visible focus ring on each control; hit areas of 44 px on a phone.
10. Only tokens in the CSS; no `style=` attribute.
