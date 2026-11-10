#!/usr/bin/python3
"""Subscription usage for the `usage` mod, as one JSON object on stdout.

Reads only what the three CLIs already leave on disk; no login is touched and
nothing goes over the network. Each number is therefore as fresh as that CLI's
last run:

  claude  ~/.claude/usage-limits.json   written by statusline.py, next to this file
  codex   ~/.codex/sessions/**/rollout-*.jsonl   `rate_limits` in token_count events
  grok    ~/.grok/logs/unified.jsonl    "billing: fetched credits config" lines

Output: { "<provider>": { "windows": [{label, used, resets}], "seen": epoch, "note"? } | null }
`used` is a percent, `resets` and `seen` are epoch seconds (or null).

`--demo` prints made-up numbers instead (every window, one past the warning mark);
`--demo=edge` prints the awkward cases (a window past its reset, a provider with
nothing on disk). Both are for screenshots and for checking the mod draws them.
"""
import glob
import json
import os
import re
import sys
import time
from datetime import datetime

HOME = os.path.expanduser("~")
TAIL = 2_000_000  # bytes read from the end of a log before giving up on it


def tail_lines(path, size=TAIL):
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - size))
        return f.read().decode("utf-8", "replace").splitlines()


def label(minutes):
    if not minutes:
        return "limit"
    if minutes < 1440:
        return f"{round(minutes / 60)}h"
    return "week" if minutes == 10080 else f"{round(minutes / 1440)}d"


def epoch(iso):
    try:
        # Python 3.9 wants at most 6 fractional digits and no "Z".
        iso = re.sub(r"(\.\d{6})\d+", r"\1", iso.replace("Z", "+00:00"))
        return int(datetime.fromisoformat(iso).timestamp())
    except Exception:
        return None


def claude():
    path = f"{HOME}/.claude/usage-limits.json"
    data = json.load(open(path))
    limits = data.get("rate_limits") or {}
    windows = []
    for key, name in (("five_hour", "5h"), ("seven_day", "week")):
        w = limits.get(key)
        if w and w.get("used_percentage") is not None:
            windows.append({"label": name, "used": w["used_percentage"], "resets": w.get("resets_at")})
    return {"windows": windows, "seen": data.get("ts")} if windows else None


def codex():
    days = sorted(glob.glob(f"{HOME}/.codex/sessions/*/*/*"), reverse=True)[:14]
    for day in days:
        files = sorted(glob.glob(f"{day}/rollout-*.jsonl"), key=os.path.getmtime, reverse=True)
        for path in files:
            for line in reversed(tail_lines(path)):
                if '"rate_limits"' not in line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                limits = (event.get("payload") or {}).get("rate_limits") or event.get("rate_limits")
                if not limits:
                    continue
                windows = [
                    {"label": label(w.get("window_minutes")), "used": w["used_percent"], "resets": w.get("resets_at")}
                    for w in (limits.get("primary"), limits.get("secondary"))
                    if w and w.get("used_percent") is not None
                ]
                if not windows:
                    continue
                out = {"windows": windows, "seen": epoch(event.get("timestamp", "")) or int(os.path.getmtime(path))}
                credits = limits.get("credits") or {}
                if credits.get("balance") and not credits.get("unlimited"):
                    try:
                        out["note"] = f"{float(credits['balance']):,.0f} credits"
                    except ValueError:
                        pass
                return out
    return None


def grok():
    path = f"{HOME}/.grok/logs/unified.jsonl"
    for size in (TAIL, os.path.getsize(path)):
        for line in reversed(tail_lines(path, size)):
            if "fetched credits config" not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            config = (event.get("ctx") or {}).get("config") or {}
            period = config.get("currentPeriod") or {}
            if not period:
                continue
            # The field is left out when it is zero.
            used = config.get("creditUsagePercent", 0)
            kind = {"USAGE_PERIOD_TYPE_WEEKLY": "week", "USAGE_PERIOD_TYPE_MONTHLY": "month", "USAGE_PERIOD_TYPE_DAILY": "day"}
            return {
                "windows": [{
                    "label": kind.get(period.get("type"), "limit"),
                    "used": used,
                    "resets": epoch(period.get("end") or config.get("billingPeriodEnd") or ""),
                }],
                "seen": epoch(event.get("ts", "")),
                "note": f"{(event.get('ctx') or {}).get('subscriptionTier') or 'Unknown'} plan",
            }
    return None


def demo(kind):
    now = int(time.time())
    hour, day = 3600, 86400
    if kind == "edge":
        return {
            "claude": {"windows": [{"label": "5h", "used": 100, "resets": now + 50 * 60}, {"label": "week", "used": 79.6, "resets": now + 6 * day}], "seen": now - 30},
            "codex": {"windows": [{"label": "week", "used": 23, "resets": now - 2 * day}], "seen": now - 9 * day},
            "grok": None,
        }
    return {
        "claude": {"windows": [{"label": "5h", "used": 42, "resets": now + 2 * hour + 600}, {"label": "week", "used": 15, "resets": now + 4 * day + 8 * hour}], "seen": now - 40},
        "codex": {"windows": [{"label": "5h", "used": 8, "resets": now + 4 * hour}, {"label": "week", "used": 84, "resets": now + 23 * hour}], "seen": now - 3 * hour, "note": "12,000 credits"},
        "grok": {"windows": [{"label": "week", "used": 31, "resets": now + 2 * day + 5 * hour}], "seen": now - 20 * 60, "note": "SuperGrok plan"},
    }


for arg in sys.argv[1:]:
    if arg.startswith("--demo"):
        print(json.dumps(demo(arg.partition("=")[2])))
        sys.exit(0)

out = {}
for name, read in (("claude", claude), ("codex", codex), ("grok", grok)):
    try:
        out[name] = read()
    except Exception:
        out[name] = None
print(json.dumps(out))
