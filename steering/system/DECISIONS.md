# Decisions: the agent system

The log of the owner's decisions: one line per decision, the newest at the end. `steering/system/PRINCIPLES.md` generalizes
them. Runs only add lines here (`merge=union` in `.gitattributes`).

Columns: date · ticket · decision · recommendation (`taken`, `changed`: the owner combined or changed it, `other`:
the owner chose another option, `-`: no recommendation) · principle (`P<n>`, or `new` when no principle predicts it).

- 2026-11-06 · setup · Three lanes: main, haiku and deep (`weights` and `reserved` in `system.toml`) · - · -
- 2026-11-06 · setup · Budget for services: free only · taken · P7
- 2026-11-06 · session · Make an owner ticket (`needs-human`) as soon as the owner can do it: inputs when the epic is made (and 2 features ahead), a check when its last agent ticket closes; never a `needs-human` ticket that waits for agent work · changed · new
