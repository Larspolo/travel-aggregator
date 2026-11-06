# Steering files

The owner steers travel-aggregator with the files in this directory. `system/` holds the preferences for the agent
system (how the runs work). `project/` holds the preferences for the project (what travel-aggregator becomes). The
numbers of the principles are unique over both `PRINCIPLES.md` files: P1 to P5 are project principles, P6 and up
are system principles.

| File | Who writes it | Kind |
|---|---|---|
| `system/PRINCIPLES.md` | The agent, from the owner's decisions. The owner edits it at any time. | system |
| `system/DECISIONS.md` | The agent, one line for each answer of the owner. | system |
| `project/PRINCIPLES.md` | The agent, from the owner's decisions. The owner edits it at any time. | project |
| `project/DECISIONS.md` | The agent, one line for each answer of the owner. | project |
| `project/ROADMAP.md` | The owner (a new feature line), and the agent (done features, `roadmap` skill). | project |

This project has no release focus and no `project/RELEASE.md`: skip the release rules of the skills.
