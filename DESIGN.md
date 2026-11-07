# DESIGN.md – the look of the travel-aggregator pages

Status: **draft**. Jeroen chooses the visual theme (section 1) in the decision ticket. The sections 2 to 9 are the
same for all options. Agents: read this file before you change a page in `app/web/templates/` or the CSS.

The form of this file follows the DESIGN.md files of the Awesome Design MD Gallery (https://design.hagicode.com/).
This file takes only style principles from it: no brand names, logos, fonts or exact brand colours.

## 1. Visual theme (decision open)

| Option | Name | Mood |
|---|---|---|
| A | Dense tool | Calm and neutral. Grey surfaces, thin borders, one cool accent colour. Many rows on one screen. |
| B | Light dashboard | Friendly and clear. White cards with a soft shadow on a light grey page, more space. |
| C | Warm editorial | Personal. Cream surfaces, a warm terracotta accent, serif headings. |
| D | System look | The browser's own colours (`Canvas`, `AccentColor`). Only sections 2 to 9 change. |

All options follow the colour scheme of the device (light or dark, `prefers-color-scheme`). There is no own switch.

## 2. Colour tokens and roles

All colours are CSS variables in `:root`. A page uses only the variables, never a colour value.

| Token | Role |
|---|---|
| `--bg` | The page background |
| `--surface` | Panels, cards, the table head, an expanded row |
| `--text` | Body text and numbers |
| `--muted` | Secondary text: source, "2h ago", the breakdown legend |
| `--line` | Borders and the lines between rows |
| `--accent` | Links, the focus ring, the primary button, the slider |
| `--good` | "Best value" and "price dropped" |
| `--info` | "Cheapest" and "fastest" |
| `--warn` | "Stale, price may have changed" |

Values (light / dark):

| Token | A | B | C |
|---|---|---|---|
| `--bg` | `#ffffff` / `#0b0b0d` | `#f6f8fa` / `#0f1420` | `#faf7f2` / `#1c1917` |
| `--surface` | `#f7f7f8` / `#16161a` | `#ffffff` / `#182030` | `#ffffff` / `#262220` |
| `--text` | `#18181b` / `#ededef` | `#1a1f36` / `#e6e9ef` | `#2b2622` / `#ede6dd` |
| `--muted` | `#71717a` / `#8b8b93` | `#5f6b7d` / `#8a94a6` | `#736a61` / `#a39a90` |
| `--line` | `#e4e4e7` / `#26262b` | `#e3e8ee` / `#2a3446` | `#e8e0d6` / `#3a3431` |
| `--accent` | `#5b5bd6` / `#8b8bf5` | `#4f5bd5` / `#8b93f0` | `#b5532f` / `#e08a66` |

Option D uses the CSS system colours: `Canvas`, `CanvasText`, `GrayText`, `AccentColor`.
The status colours are the same for all options: `--good` `#1a7f37` / `#3fb950`, `--info` `#0969da` / `#58a6ff`,
`--warn` `#9a4f00` / `#e3a03f`.

## 3. Typography

- Font: the system font stack (`system-ui, sans-serif`). No web font: it is one more download and one more dependency (P4).
  Option C uses `ui-serif, Georgia, serif` for `h1` and `h2` only.
- Size: 15 px body text on a computer, 16 px on a phone (no zoom on input focus in iOS).
- All prices, costs, times and durations use `font-variant-numeric: tabular-nums`, so that the columns align.
- The effective cost is the largest number in a row (1.15 em, weight 600). The ticket price is normal text.

## 4. Components

- **Cost cell.** The effective cost on top. Under it, a thin bar (6 px) with one segment per part of the breakdown,
  and the text breakdown ("€90 price + €62 time + €30 transfers") in `--muted`. The text stays: the bar alone does
  not tell the values (P2: the breakdown always shows each part).
- **Badges.** A small pill with a text label and a status colour: best value (`--good`), cheapest and fastest
  (`--info`), booked (`--accent`), stale (`--warn`), price dropped (`--good`). Never colour only: each badge has text.
- **Row actions.** Pin, Hide and Booked are small icon buttons with an `aria-label` and a `title`, at the end of the
  row. They stay `<form method="post">` with the CSRF field, so they work without JavaScript.
- **Buttons.** One primary style (`--accent` background) for the main action of a page. All other buttons are
  outlined (`--line` border, no fill). Hit area at least 40 × 40 px on a phone.
- **Inputs.** `--surface` background, `--line` border, 6 px radius, the `--accent` focus ring (2 px `outline`).
  Use `accent-color: var(--accent)` for range, checkbox and radio inputs (P4: no own slider code).
- **Panels.** `<details>` and `<fieldset>` for the groups of the weights form. No own JavaScript for open and close.
- **Navigation.** One top bar on each page: Trips, Captures, Settings and Log out. No second link list on a page.

## 5. Layout

- The page is at most 80 rem wide. Spacing steps: 4, 8, 12, 16, 24 and 32 px (`--space-1` to `--space-6`).
- Trip page on a computer (wider than 64 rem): the weights panel at the left (18 rem), the ranked table at the right.
  The price, hour and transfer controls are always open at the top of the panel (P2). The filters and "Advanced" are
  `<details>` groups below them.
- "Advanced" has fieldsets: Airport, Time windows, Night, Modes, Fares, Staleness, Profile.
- The table: one line per itinerary, the cost column at the right, the detail row opens below the row.

## 6. Depth and elevation

- Options A and D: no shadows. Borders and `--surface` show the levels.
- Option B: one soft shadow for cards and panels (`0 1px 3px rgb(0 0 0 / .08)`), none in dark mode.
- Option C: no shadows, 8 px radius on cards.

## 7. Responsive behaviour

- Phone width (40 rem or less, test at 390 px): each itinerary is a card, not a table row. The card shows the route,
  the times with "+1 day", the mode icons, the effective cost and the badges. A tap opens the details.
- The weights panel is one `<details>` above the list ("Weights and filters"), closed by default, with the price,
  hour and transfer controls in the summary area.
- No horizontal scroll on any page at 390 px (`trip:mobile`, #310).

## 8. Do and do not

- Do use only the tokens of section 2. Do keep all CSS in `app/web/static/app.css` (no build step, `docs/SPEC.md`).
- Do keep the contrast of text on its background at 4.5:1 or more, also for `--muted`, in light and dark mode.
- Do escape all captured text (P5). A design change never uses `| safe` on captured data.
- Do not add a CSS framework or a JavaScript framework. Do not add an inline `style=` attribute.
- Do not show a new extra of the ranking as a new column: it is one more part of the breakdown (P2).

## 9. Agent prompt guide

- "Change the trip page: follow `DESIGN.md`, use only its tokens, keep the forms working without JavaScript, and add
  screenshots at 1280 px and 390 px, light and dark, to the PR."
- Check a page change with Playwright at 1280 px and with a phone device, in light and dark colour scheme.
