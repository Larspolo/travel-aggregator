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
