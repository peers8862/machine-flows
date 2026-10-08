# plans/: how planning docs work (example)

The real `plans/` folder stays local because plans name people, machines and organisations. This is its convention in generic form. Agents read it before they create, update or archive a plan. Plan `00` is the master plan; every other plan covers one topic and points back to it.

## 1. The convention

- **One topic, one living file.** Update the plan in place; don't start a "v2" file. When a decision changes, edit the text and add a dated note.
- **Shape:** `# NN: Title`, then a `Status:` line (what's done, what's waiting, with date), then 1–3 short paragraphs saying what the plan is for and why. After that come checklists (`- [ ]` / `- [x]`) and tables that agents keep current.
- **Tick boxes only when verified.** Add when and where: `- [x] … (done 2026-01-05 10:40 host)`. If an item is dropped or moved, say so and where it went: `- [x] ~~…~~ dropped 2026-01-09: replaced by plan 09 §5`.
- **Facts carry a date and a source** (command, file, doc URL). Times carry a zone label.
- **Lead with the result.** Put the current state and the next decision near the top. Put history in a Change log section at the end, or in plan 00's Change log when the change affects more than one plan.
- **No secrets.** Name credential files only, and show config files by key names only.
- **Not plans:** standing rules go in plan 00's operational rules and the shared instruction files. Lessons go in `service-memories/lessons/`. Machine facts go in `inventory/<host>/`.
- **Tracking tables are sheet sets:** an `index.csv` plus the CSVs it lists are the source of truth and the workbook is generated (`mach sheets build <dir>`); never edit a workbook by hand.

## 2. Numbering

- File name: `NN-short-kebab-name.md`, with a two-digit number.
- New plan = the highest number used in `plans/` **or** `plans/archived/`, plus one. Never reuse a number and never renumber a plan, even after it is archived: other documents cite plans as "plan 06 §10", so a number must always mean the same plan.
- `00` is the master plan and is never archived.
- When you add or archive a plan, update the register in the same task.

| # | File | Topic | State |
| --- | --- | --- | --- |
| 00 | `00-master-plan.md` | Master plan: stages, operational rules, change log | active (never archived) |
| 02 | `02-example-topic.md` | One topic | active |

## 3. When a plan is done

A plan is done when **both** are true:

1. Every checklist item is ticked, or explicitly marked as dropped or moved to another plan (with where it went).
2. The owner agrees it is done. Agents may propose archiving ("plan 04 has no open items; archive it?"), but never archive on their own judgment.

## 4. How to archive a plan

Finished plans move to `plans/archived/` and keep their file name and number.

- [ ] Get the owner's OK (section 3).
- [ ] Set the status line to `Status: **done YYYY-MM-DD, archived**`, plus one line naming where any follow-ups went.
- [ ] Move any still-open items to the plan that now owns them.
- [ ] Move the file with `mv`. Don't leave a stub, copy or symlink behind.
- [ ] Fix references: search the folder for the file name and repoint each link to `plans/archived/NN-name.md`.
- [ ] Add a dated line to plan 00's Change log saying what was archived and why it is done.
- [ ] Update the documents index for the machine, and the register in section 2.
