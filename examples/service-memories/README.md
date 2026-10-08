# service-memories/ and files/ (example layout)

Lessons and per-service memory. The content is the owner's working knowledge, so it stays local.

```
service-memories/
  lessons/
    INDEX.md               # generated index: one line per lesson (do not edit by hand)
    README.md              # lesson file format
    <topic>/<slug>.md      # one lesson per file, with frontmatter
    archived/INDEX.md      # retired lessons
    reviews/YYYY-MM.md     # monthly review proposals from `mach memory review --save`
files/
  inbox/                   # notes, prompts and replies waiting to be handled
    notes/  prompts/  replies/  subsystems/
```

A lesson is a short note about something non-obvious that was learned (a bug fix, a trade-off, a reusable pattern). Frontmatter carries at least a title, tags, the machines it applies to and a `source` (the session, plan or log it came from; never pasted text). Reviews are proposals: nothing changes until the owner approves numbered items.

`mach memory init` creates the skeleton; `mach memory review` proposes changes; `--apply` backs up first and prints a rollback line.
