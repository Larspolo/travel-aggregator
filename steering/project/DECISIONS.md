# Decisions: the project

The log of the owner's decisions: one line per decision, the newest at the end. `steering/project/PRINCIPLES.md` generalizes
them. Runs only add lines here (`merge=union` in `.gitattributes`).

Columns: date · ticket · decision · recommendation (`taken`, `changed`: the owner combined or changed it, `other`:
the owner chose another option, `-`: no recommendation) · principle (`P<n>`, or `new` when no principle predicts it).

- 2026-11-06 · setup · Continue after the terms check of Claude and GitHub; no request to a travel site from any agent, CI or cloud session · taken · P1
- 2026-11-06 · setup · Public repository; fixtures trimmed, with no personal data · taken · P5
- 2026-11-06 · setup · Ranking: simple first, the extras in "Advanced" · taken · P2
- 2026-11-06 · setup · Sources: robust first (bahn.de and the ranking before the next source) · taken · P3
- 2026-11-06 · setup · Owner decides only real ties · taken · -
- 2026-11-06 · setup · Try a feature: development server (`/try`), screenshots in each PR, a release image per epic · changed · -
- 2026-11-06 · setup · Phone and tablet tests only after a feature works on a computer · - · new
- 2026-11-06 · setup · Roadmap of 4 goals (capture, rank, trip, host), as drafted · taken · -
- 2026-11-06 · setup · A preview server at travel-preview.larspolo.nl follows each green main (`:preview`, scoped watchtower, own database); the real instance follows `:latest` per epic · taken · -
- 2026-11-06 · setup · The preview pages get Traefik basic auth until the login exists; `/api` keeps its token only · taken · P5
- 2026-11-06 · setup · Add a README; update it only at the end of each epic, in one PR, not in each ticket PR · changed · new
- 2026-11-06 · #145 · Limit the failed logins (#145); no Cloudflare Turnstile: a single-user app, and no third-party script on the login page · taken · P5
- 2026-11-06 · capture skill · Claude in Chrome on Jeroen's computer does the capture tickets in his own browser (only the searches of the ticket, the hook only records) and pushes the cleaned HAR · - · P1
- 2026-11-07 · #418 · Price-drop notifications: all three channels (A ntfy, B e-mail, C Web Push), and the user chooses the channel in the settings · changed · new
- 2026-11-07 · #535 · Visual theme of the web pages: A "Dense tool" (neutral grey surfaces, thin borders, one cool accent, many rows per screen; `DESIGN.md`) · taken · P2
- 2026-11-07 · #535, #619 · Correction (Larspolo): option A of #535 means only "dense"; its colours, borders, fonts and the limits that `DESIGN.md` took from P4 (system fonts only, no CSS framework, no own JavaScript) were not chosen. Common libraries and frameworks are allowed (#619). `DESIGN.md` version 3 · changed · new
- 2026-11-08 · #884 · The next sources: all four options (A ÖBB, B Eurostar, C SNCF Connect, D Trainline), in this order · changed · new
- 2026-11-08 · #996 · The preview pages lose the Traefik basic auth: only the app login protects them, as on the real instance (a browser forgets basic auth at each restart) · taken · P2
