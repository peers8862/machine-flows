"""Preview or run one routed completion.

Usage:
  python3 -m model_router --class triage --channel cli --subsystem demo --dry-run
  python3 -m model_router --class extraction --channel cli --subsystem demo --non-urgent --prompt "..."
"""

import argparse
import json
import os
import sys

from model_router.router import ConfigError, State, invoke, load_config, plan
from model_router.transport import post_chat


def default_root():
    env = os.environ.get("MACH_MF_ROOT")
    if env:
        return env
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isfile(os.path.join(here, "models.toml")):
        return here
    return os.getcwd()


def main(argv):
    parser = argparse.ArgumentParser(prog="model_router", add_help=True)
    parser.add_argument("--class", dest="task_class", required=True)
    parser.add_argument("--channel", default="cli", choices=("cli", "imessage"))
    parser.add_argument("--subsystem", required=True)
    parser.add_argument("--conversation", default="")
    parser.add_argument("--non-urgent", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--root", default="")
    parser.add_argument("--state-dir", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run and not args.prompt:
        print("pass --prompt to call a provider, or --dry-run to preview the ladder", file=sys.stderr)
        return 2
    root = args.root or default_root()
    state_dir = args.state_dir or os.path.join(root, "files", "model-router")
    request = {
        "task_class": args.task_class,
        "channel": args.channel,
        "subsystem": args.subsystem,
        "conversation_id": args.conversation,
        "urgent": not args.non_urgent,
        "prompt": args.prompt,
    }
    try:
        config = load_config(os.path.join(root, "models.toml"))
        state = State(state_dir)
        if args.dry_run:
            result = plan(config, request, state, check_keys=True)
        else:
            result = invoke(config, request, state, post_chat)
    except ConfigError as err:
        print("model_router: %s" % err, file=sys.stderr)
        return 2
    if args.json:
        json.dump(result, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    if result["status"] == "plan":
        _print_plan(result, sys.stdout)
        return 0
    _print_outcome(result, sys.stderr)
    if result.get("text"):
        sys.stdout.write(result["text"])
        if not result["text"].endswith("\n"):
            sys.stdout.write("\n")
    return 0


def _print_plan(result, out):
    out.write("plan %s channel=%s subsystem=%s\n" % (result["task_class"], result["channel"], result["subsystem"]))
    for cand in result["candidates"]:
        out.write("  candidate %s/%s %s\n" % (cand["tier"], cand["provider"], cand["model"]))
    for skipped in result["skipped"]:
        out.write("  skipped %s/%s %s\n" % (skipped["tier"], skipped["provider"], skipped["reason"]))


def _print_outcome(result, out):
    task = result["task_class"]
    if result["status"] == "degraded":
        out.write("%s: %s\n" % (task, result["message"]))
        return
    if result["status"] == "queued":
        out.write("%s: queued %s\n" % (task, result["queue_id"]))
        return
    if result.get("notice"):
        out.write("%s: %s via %s/%s (%s)\n" % (task, result["notice"], result["tier"], result["provider"], result["model"]))
        return
    out.write("%s: %s/%s (%s)\n" % (task, result["tier"], result["provider"], result["model"]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
