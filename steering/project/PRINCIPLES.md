# Principles

The direction of travel-aggregator, made from the owner's decisions (`steering/project/DECISIONS.md`).
The `new-project` skill writes the first principles from the owner's answers. Then the runs add a principle when the
owner decides a question (the `ticket` skill, "Decision tickets"). Agents: before you recommend an option, compare it
with these principles and name the principle ("follows P1"). The full specification: `docs/SPEC.md`.

## P1. Passive capture only

The project reads only data that the owner's own browser shows. No code sends a request to a travel site: no
crawler, no replayed or changed request, no scheduled fetch, no request from CI or a cloud session (GitHub Actions
terms: only the build, test and release of this project). A userscript only observes the responses that the page
requested itself. Example: the search links of `trip:links` only open a page; they fetch nothing. The `capture`
skill in a local session on Jeroen's computer is his own browsing (owner, 2026-11-06): it clicks and types in his own
visible Chrome as a person does, only the searches of one capture ticket, and its hook only records the responses.
The same holds for a local session in the owner's (Larspolo's) own Chrome, for capture tickets and for owner checks
on the travel sites, for example #752 and #945 (owner, 2026-11-08): the evidence of such a check counts. The rules of
the `capture` skill stay: at most 3 searches per ticket (the owner can allow more in that session), no request from
code, stop at a block, a login or a CAPTCHA.

## P2. Simple first in the ranking

A few controls that work at once win over all controls at the same time. Price, hour and transfer weights are always
visible; each extra (night, door-to-door, risk, flexibility, staleness) has a working default and sits in an
"Advanced" panel. The breakdown always shows each part of the score. Example: a new extra adds one line to the
breakdown and one control in "Advanced", not a new column in the table.

## P3. Robust sources first

A source is done only with trimmed fixture tests, fail-soft parsing (one bad offer does not stop the batch), a log
line with the capture id for each failure, and "reparse capture". Finish bahn.de and the ranking before the next
source. Example: an NS International parser that passes only on a happy-path payload is not done.

## P4. Platform features first

Use the feature of PostgreSQL, SQLAlchemy, FastAPI, Pydantic, Jinja2, htmx or the browser before own code, and keep
the dependencies few (the specification). Write own code only when the platform has no such feature, and say why in
the PR. Example: validate the ingest body with a Pydantic model, not with own checks; use a PostgreSQL `UNIQUE`
constraint for the fingerprint per trip.

## P5. Untrusted and private data

Captured data is untrusted: validate it, limit its size, escape it in each page. Store no credentials, cookies,
passenger names or payment data. Fixtures in this public repository are trimmed to the fields that the parser
reads, with no personal data (a test checks their size). The agents cannot open the travel sites (P1): for a new
source, a `needs-human` ticket asks the owner to capture one real payload with the userscript.

## Owner involvement

The areas where the owner decides each choice, also when one option is clearly best (a decision ticket). In all
other areas the agents decide, and ask only when two options are equally good.

- Only real ties.

## Try a feature

How the owner tries a new feature. The agents make what this needs for each feature or epic.

- Preview server: each green merge to `main` becomes the image `:preview`, and `https://travel-preview.larspolo.nl`
  (the owner's server: Traefik, a scoped watchtower, its own database with test data) runs it within 5 minutes
  (`deploy/preview/`, the job `preview` of `.github/workflows/ci.yml`). The owner types `/try` in a local session: it lists what is
  new, with the steps to try it on the preview. `dev` in `[commands]` stays for a run on the owner's computer.
- Screenshots in each PR: each PR that changes a page has screenshots at desktop width (1280 px) and phone width
  (390 px), as an artifact of the CI job, with a description in the PR body (the REST API cannot upload images).
- A release image per epic: each closed epic makes a tagged Docker image on GHCR and moves `:latest`; the owner's
  real instance with the real data follows `:latest` (`host:deploy`). The preview never uses the real data.
- The agents check each page at phone width themselves (Playwright with a phone device, sideways scroll, control
  sizes, screenshots). The owner tests on a phone or a tablet only what only a person can tell (the feel under a
  finger), and only after a feature works on a computer (owner, 2026-11-07).
- The README at the end of each epic (owner): before the epic closes, one PR updates `README.md` for all that the
  epic added (setup, commands, settings, API, what a user can do), and `python3 -m pytest -m readme` passes. The epic
  waits for it. Ticket PRs do not change `README.md`.
- The deployed preview at the end of each epic: after the last merge of the epic, `scripts/preview_check.sh` passes
  (the preview runs the newest `main`, and the API works with a real database). The epic waits for it. A failure is
  a bug ticket. The agents never test the pages on the preview: the passwords are only the owner's.
