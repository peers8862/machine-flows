# mach subsystems

A subsystem names a company or project and its units (pillars, services, products, publications, pipelines, events). Its keyed TOML manifest lives at `<id>/subsystem.toml`. It records repo and folder pointers, routines and agent files, roles, service profiles, and delivery defaults. The manifest routes prompts; repo rules still govern work inside each repo.

## Schema

Top level: `schema = 1`, `id` (lowercase kebab, matches folder, no built-in command collision), `name`, `working_root`, optional `linear_team`, `note_dest`. `[delivery]` has `max_fires_per_day` (positive integer) and `reply = "chat" | "inbox"`. `[repos.<id>]` has `path`, `remote`, `verified` (bool), `source`. `[units.<id>]` has `name`, `kind` (`pillar|service|product|publication|pipeline|event`), optional `parent`, `special`, `repo`, `folder`, arrays `types`, `routines`, `agent_files`, `recipes`, plus `verified`, `notes`, `todo`. `[units.<id>.roles]` has `lead` and other role-to-destination entries, `since`, `changed` (dated strings), `notes`, `assignments`. `[services."<dest>"]` has arrays `strengths`, `limits`, `workloads` and `notes`. Table keys are unique; unit IDs are unique per subsystem. Directories starting `_` are templates.

A destination is `grokbot:<Name>` (name may contain spaces), `claude`, `codex`, `cursor-agent`, `grokcli-agent`, `kiro`, `note:<dest>`, or `user`. Every Grok Bot destination needs a service profile. `user` captures a note to `note_dest` or inbox. `mach subsystem lint` reports INFO for unassigned lead and `todo`; FAIL makes dispatch refuse that manifest.

## Commands

- `mach subsystem list`, `show demo`, `lint [demo]` inspect manifests.
- `mach demo` lists units as a tree; `mach demo alpha --roles` shows role history and profiles.
- `mach demo alpha "prompt"` sends immediately to its lead and records a run. `--to codex` or `--role drafting` selects a destination; `--dry-run` previews; `--write` permits CLI writes; `--reply inbox` requests a reply file; `--force` bypasses the Grok Bot daily cap.
- `mach subsystem new <id> [--from subsystem-setup.md] [--apply] [--replace]` scaffolds or ingests a draft. `mach subsystem unit|role <id> --from <draft.md> [--apply]` previews a diff, then updates with a rollback backup.
- `mach queue` lists unprocessed subsystem drafts in `files/inbox/subsystems/` with their ingest commands. `mach run` accepts `subsystem-prompt`, and directs setup documents to `--from`.

## Grok Bot router

Put this in **unsynced** `~/.config/mach/secrets.toml` and run `chmod 600 ~/.config/mach/secrets.toml`:

```toml
[grokbot_router]
url = "https://your-router-webhook"
key = "your-sender-key"
key_header = "Authorization: Bearer"
```

Copy URL and key from the routine panel of **mach router: forward prompts to pillar bots**. `key_header = "X-Webhook-Key"` sends `X-Webhook-Key: <key>`; `Authorization: Bearer` sends `Authorization: Bearer <key>`. An unsafe or missing file queues a paste-ready prompt and exits 1. Successful HTTP 2xx delivery records `done`; errors exit 2. The cap counts router run records on this machine per local day. Secrets and full URLs never belong in manifests or run records.
