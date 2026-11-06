# Start a new project

A new project starts from the template `framework/template/` (#4196). You fill a short list of files, run the
bootstrap, do the settings, and the runs then build the project from its roadmap with no other step.

**The easy way:** start a Claude Code session in a clone of this repository and type `/new-project <your idea>`. The
skill `.claude/skills/new-project/SKILL.md` suggests the stack and the roadmap, fills the files, and makes and sets up
the repository (`framework/tools/new_repo.py`). It asks you only what it cannot decide (the idea, the direction,
your resources), and guides you one step at a time through the steps that need your accounts (`new_repo.py --check`
shows which are done). A local session with `gh auth login` does the most work. The steps below are the manual way.

## 1. Fill the template

`python3 framework/tools/bootstrap.py DIR --repo OWNER/NAME` writes the files of `framework/template/` into DIR, with the
repository, the owner login and the project name in place. Fill these files in DIR (the comments and the `TODO` lines
say what to write):

1. `steering/project/ROADMAP.md`: the goals of the project and their features, each as `- [ ] \`goal:feature\` text`.
   The runs make the epics and the tickets from this list.
2. `CLAUDE.md`: the commands (install, lint, tests) and the code map.
3. `agent.toml`: the commands in `[commands]`. Keep the other values: they are the defaults of the system.
4. `.claude/skills/verify/SKILL.md`: the check levels of the project, from cheap to expensive.
5. `.github/workflows/ci.yml`: the quick checks (job `quick`). Keep the job name: Automerge waits for it.
6. `scripts/cloud-setup.sh` and `scripts/allowed-domains.txt`: the tools and the hosts that the project needs.
7. `docs/ENVIRONMENT.md`: the network and the setup script, in words.
8. `steering/project/PRINCIPLES.md`: keep it empty. The runs add a principle with each decision of the owner.

## 2. Push the first commit

Commit DIR to the new repository and push it to the default branch. Merge the first PR by hand, when you use one:
Automerge cannot merge it, because the workflows are not on the default branch yet.
`python3 framework/tools/bootstrap.py DIR --repo OWNER/NAME --github` also makes the labels and the status issue.

## 3. Do the settings

Do the steps of `framework/docs/SYSTEM.md`, section "Setup steps of the owner", in order: the GitHub settings, the cloud
environment, the scheduled tasks (the prompt is `/scheduled max`), and the secrets of `pacer.yml`
(`CLAUDE_CODE_OAUTH_TOKEN`, `PACER_URL_MAIN`, `PACER_TOKEN_MAIN`, and the URL and token of each lane).

## 4. The first run

The pacer starts the first run. The queue is empty, so the run refills it: each feature of the roadmap with no epic
is a source of the refill (`autopilot` skill, `queue.md`), and the `roadmap` skill makes its epic and tickets. You need
no ticket in the repository. After that, steer through issues (`framework/docs/STEERING.md`).
