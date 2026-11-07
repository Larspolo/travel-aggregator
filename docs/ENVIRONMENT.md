# Environment

The project part of the cloud environment of travel-aggregator (`framework/docs/STEERING.md`).

## Network

"Allow package managers" is on (PyPI for the Python packages, the Ubuntu mirrors for `apt-get`). Beyond them, only
`github.com` and the owner's preview server `travel-preview.larspolo.nl` (`scripts/allowed-domains.txt`). Never add a
travel site (bahn.de, NS International, Flixbus, a flight site): the agents do not send requests to them (P1). Fixtures
come from the owner.

The environment has one network secret: an API token of the preview (`python -m app.tokens create agents` on the
server), for the host `travel-preview.larspolo.nl`, header `Authorization`, value `Bearer <token>`. The proxy adds it to
each request to the host; no run sees it. With it, `/api` works and the pages get 401 from Traefik basic auth (they
need `Basic`): test the pages locally. The owner revokes it with `python -m app.tokens revoke ID`.

## Setup script

`scripts/cloud-setup.sh` installs PostgreSQL 16 (`postgresql-16`, for the temporary test cluster of
`tests/conftest.py`) and Python 3.12, when the image does not have them. The SessionStart hook then installs
`requirements-dev.txt`. Playwright and Chromium come with the cloud image (`/opt/pw-browsers/chromium`). The cloud has no
Docker daemon: CI builds and checks the image.

## Resources of the owner

What the owner has for the project: the computer, the devices, the accounts and licenses, the budget and the Claude
plan (the `new-project` skill writes it). Do not plan work that needs a resource that is not here: make a decision
ticket for it.

- Computers: macOS, Windows and Linux, each with Docker. The development server (`/try`) must work on all three.
- A server with Docker and Traefik (external network `proxy`, HTTPS). It runs the preview at
  `https://travel-preview.larspolo.nl` (`deploy/preview/`): Traefik basic auth on the pages until the login exists,
  none on `/api`. The agents reach `/api` with the network secret (`scripts/preview_check.sh`), not the pages.
- A browser with Tampermonkey: the owner installs the userscripts and captures real payloads for the fixtures.
- A phone for the mobile layout: the owner tests on it only the feel under a finger, after the agents checked the layout.
- Budget: free only. A service with a cost (mail, push, hosting) gets a decision ticket.
- Claude plan: three scheduled tasks (main, haiku lane, deep lane).
- GitHub: a public repository (free Actions minutes, free GHCR images for public packages).
