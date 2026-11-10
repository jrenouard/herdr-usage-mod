#!/usr/bin/env python3
"""Claude Code status line that saves the account's rate limits for the `usage` mod.

Claude Code hands every status line run a JSON blob on stdin; on a subscription it
carries `rate_limits` (5-hour and 7-day windows). This saves that part to
~/.claude/usage-limits.json, where collect.py reads it.

On its own it prints nothing, so no status line appears:

    "statusLine": { "type": "command",
                    "command": "python3 ~/.config/herdr-app/mods/usage/statusline.py" }

Already have a status line? Pass its command as the one argument; it gets the same
stdin and its output is shown unchanged:

    "command": "python3 ~/.config/herdr-app/mods/usage/statusline.py 'your-command --here'"
"""
import json
import os
import subprocess
import sys
import time

OUT = os.path.expanduser("~/.claude/usage-limits.json")

raw = sys.stdin.buffer.read()

try:
    limits = json.loads(raw).get("rate_limits")
    if limits:
        tmp = f"{OUT}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump({"ts": int(time.time()), "rate_limits": limits}, f)
        os.replace(tmp, OUT)  # atomic: several sessions write this at once
except Exception:
    pass  # a status line must never break the session it runs in

if len(sys.argv) > 1:
    sys.exit(subprocess.run(sys.argv[1], shell=True, input=raw).returncode)
