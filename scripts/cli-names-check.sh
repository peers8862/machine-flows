#!/bin/bash
# cli-names-check.sh: keep CLI agent command names explicit (machine-flows rule, 2026-10-08).
#   Cursor CLI = cursor-agent   (official installer: ~/.local/bin/cursor-agent)
#   Grok CLI   = grokcli-agent  (xAI installer: ~/.local/bin/grokcli-agent -> ~/.grok/bin/grok)
#   No bare `agent` command anywhere.
# Both vendor installers (re)create a bare `agent` on every install or update:
#   Cursor  https://cursor.com/install   : rm -f ~/.local/bin/agent; ln -s .../cursor-agent ~/.local/bin/agent
#   xAI     https://x.ai/cli/install.sh  : ln -sf ... ~/.grok/bin/agent; also ~/.local/bin/agent if ~/.grok/bin was not on PATH
# Run this after any Cursor CLI or grok install/update.
# Usage: bash cli-names-check.sh          # report only (exit 1 if a bare agent exists or a name is missing)
#        bash cli-names-check.sh --fix    # remove bare `agent` SYMLINKS in ~/.local/bin and ~/.grok/bin (targets recorded
#                                         # in ~/machine-flows-staging/backups/<ts>-cli-names/), create grokcli-agent if missing
# Never runs any CLI, never uses sudo, never touches /usr/local/bin, never creates anything inside ~/machine-flows.
# bash 3.2 compatible (macOS).
set -u
FIX=0; [ "${1:-}" = "--fix" ] && FIX=1
BIN="$HOME/.local/bin"; GROKBIN="$HOME/.grok/bin"
status=0; backup=""
say() { printf '%s\n' "$*"; }
target() { if [ -L "$1" ]; then printf '%s' "$(readlink "$1")"; elif [ -e "$1" ]; then printf '(regular file)'; else printf '(absent)'; fi; }
record() {
  if [ -z "$backup" ]; then
    backup="$HOME/machine-flows-staging/backups/$(date +%Y%m%d-%H%M%S)-cli-names"
    mkdir -p "$backup" || { say "cannot create $backup"; exit 2; }
  fi
  printf '%s\t%s\t%s\t%s\n' "$(date '+%F %T %Z')" "$(hostname -s)" "$1" "$(target "$1")" >> "$backup/removed-links.tsv"
}
say "host: $(hostname -s)   mode: $([ $FIX = 1 ] && echo fix || echo report)"
for p in "$BIN/agent" "$GROKBIN/agent" "/usr/local/bin/agent"; do
  [ -e "$p" ] || [ -L "$p" ] || continue
  say "bare agent: $p -> $(target "$p")"
  case "$p" in /usr/local/bin/*) say "  (not touched: outside the user's bin dirs; remove by hand if wanted)"; status=1; continue ;; esac
  if [ $FIX = 1 ] && [ -L "$p" ]; then record "$p"; rm -f "$p" && say "  removed (target recorded in $backup/removed-links.tsv)"
  else status=1; fi
done
if [ $FIX = 1 ] && [ ! -e "$BIN/grokcli-agent" ] && [ -e "$GROKBIN/grok" ]; then
  mkdir -p "$BIN" && ln -s "$GROKBIN/grok" "$BIN/grokcli-agent" && say "created $BIN/grokcli-agent -> $GROKBIN/grok"
fi
for n in cursor-agent grokcli-agent; do
  if [ -e "$BIN/$n" ]; then say "ok: $BIN/$n -> $(target "$BIN/$n")"
  else
    case "$n" in
      grokcli-agent) [ -d "$GROKBIN" ] && { say "missing: $BIN/$n (grok is installed)"; status=1; } || say "n/a: $n (xAI grok not installed here)";;
      *) say "missing: $BIN/$n"; status=1;;
    esac
  fi
done
hash -r 2>/dev/null
if command -v agent >/dev/null 2>&1; then say "WARNING: 'agent' still resolves to $(command -v agent)"; status=1; else say "ok: no 'agent' on PATH"; fi
exit $status
