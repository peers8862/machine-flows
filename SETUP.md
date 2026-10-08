# Setup

How to use machine-flows from each AI tool, and how git fits with a Syncthing-synced folder.

## The folder and git

`~/machine-flows/` is a Syncthing folder. Its ignore file (`.stglobalignore`, synced) lists `.git`, so **`.git` is never synced**: each machine has its own clone and history. Only the working files travel through Syncthing.

- Treat Syncthing as the way files reach other machines and git as the way a change is reviewed and published. Commit on the machine where you edited.
- `.gitignore` is a whitelist (first line `/*`). A new file stays untracked until you add an un-ignore line for it. Check `git status` before committing and never use a blind `git add -A`.
- Personal areas (`inventory/`, `files/`, `service-settings/`, `service-memories/`, `drafts/`, `plans/`, `ai-tools/`) are not in the repo. See `examples/` for what they hold.
- Do not make symlinks inside the folder; Syncthing syncs them as links, which differ per machine.

## Install mach (optional)

`mach` is a separate repository, [peers8862/mach](https://github.com/peers8862/mach), expected at `~/machine-flows/mach/`. Cloning a repository is an outward network action, so **an agent may clone it only when the user explicitly says so**:

```bash
git clone https://github.com/peers8862/mach ~/machine-flows/mach
```

Then follow mach's install steps: `mach/README.md` ("Install") and `mach/docs/GUIDE.md` (section 11, "Install and test"):

```bash
bash ~/machine-flows/mach/install.sh            # preview only
bash ~/machine-flows/mach/install.sh --apply    # links ~/.local/bin/mach
```

The link lives outside the synced folder. Everything else in this repo works without mach.

## Claude Code

Claude reads `~/.claude/CLAUDE.md`. Make that file a two-line import of the shared instructions so one edit reaches every machine:

```
@~/machine-flows/ai-authored/claude/CLAUDE.md
@~/.claude/CLAUDE.machine.md
```

Put machine-specific facts (OS, runtimes, storage rules) in `ai-authored/claude/machines/<hostname>.md` and import that from `~/.claude/CLAUDE.machine.md`. Back up an existing `~/.claude/CLAUDE.md` before replacing it. Edit the real files in `ai-authored/`, not the loader files.

## Codex CLI

Codex reads `AGENTS.md` (the global one in `~/.codex/`, then one per repository). Point it at the shared rules by keeping a short `AGENTS.md` in each repo, like the one at the root of this repository, and reference `ai-authored/claude/CLAUDE.md` as the long form. MCP servers go in `~/.codex/config.toml`; define them once in `mcp/servers.yaml` (format in `examples/mcp/`) and apply per machine with preview first.

## Cursor

Open `~/machine-flows` (or a project) as the workspace. Cursor reads `AGENTS.md` at the workspace root and rules under `.cursor/rules/`. Keep rules short and make them point at `AGENTS.md` instead of repeating it. For terminal use call `cursor-agent`; there is no bare `agent` command (`scripts/cli-names-check.sh --fix` removes one the installers create).

## ChatGPT (web or desktop)

ChatGPT cannot read your disk. For each ChatGPT project, paste the contents of the shared instruction block (the generic rules in `AGENTS.md`, plus any project-specific block) into the project's instructions, and upload only files that are safe to share. Never paste secrets, tokens or inventories into a chat or a project. Keep each instruction block short; if it grows past a screen, move detail into a file in the project.

## Any other agent

Tell it to read `AGENTS.md` first. It should not read or write anything outside `~/machine-flows` and the project it was given, and it should show a preview before every change.
