# AGENTS.md: machine-flows

For Codex, ChatGPT, Cursor and any other agent. The long-form shared instructions are `ai-authored/claude/CLAUDE.md` in the owner's local copy. That file is personal (machines, projects, accounts) and is **not in this public repository**, so the generic rules are summarised here.

## Hard rules

- **No secrets.** Never write tokens, passwords, webhook URLs, keys or device IDs into any file or message. Name credential files and environment variables only. If you find something secret-looking, report the file and line, not the value.
- **Preview, then `--apply`.** Show what a script or command would change before it changes anything. Do not run an `--apply` the user has not seen the preview of.
- **Back up before overwriting or deleting.** Look at the target first. Say how to roll back.
- **Flag irreversible or outward-facing actions** (push, publish, delete, send, clone a repository) and wait for the user's go-ahead.
- No `sudo`, no symlinks inside `~/machine-flows`, and do not copy files into `/tmp`; stay under the home folder.

## Working conventions

- Run `git status` first. Stage only the files you mean to keep; check for untracked secrets.
- Commits: `type(scope): message`. Branches and pull requests follow the project tracker's ticket ID when there is one.
- Edit the real files in `ai-authored/`, not the small loader files in `~/.claude` or `~/.codex`.
- Plans in `plans/` are living documents (see `examples/plans/README.md`): update in place, tick boxes only when verified, never renumber.
- Tracking tables are sheet sets: edit the CSVs, regenerate the workbook with `mach sheets build <dir>`, never edit the workbook.
- Check runtime versions (`node -v`, `python3 -V`) instead of assuming them.

## Where things are

See `README.md` for the layout and `SETUP.md` for per-tool setup. `examples/` shows the files that live only on the owner's machines.
