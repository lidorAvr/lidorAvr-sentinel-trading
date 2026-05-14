#!/usr/bin/env python3
"""Pre-populate state-file timestamps before main → Pi deployment.

Mitigates the alert-burst risk identified in Mark's review (Finding 7).

Pi-backup state files do not contain `last_state_alert_ts` per position, so
on first cycle of the new main code, every state change since the snapshot
appears un-alerted (cooldown sees ts=0) and fires immediately. Pre-populating
to `now` gives the cooldown a real anchor.

Usage:
    python3 scripts/prepare_pi_state_for_deploy.py risk_monitor_state.json

The original file is backed up to <path>.pre-mitigation.<timestamp>.
"""
import json
import os
import shutil
import sys
import time


KEYS_TO_SEED_PER_POSITION = {
    "last_state_alert_ts": "now",
    "last_state_alert_type": "",
    "last_alert_ts": "now",
    "runner_decision": "",
    "runner_decision_ts": 0.0,
    "sizing_leak_alerted": False,
    "breakeven_alerted": False,
    "last_giveback_class": "na",
    "last_giveback_ts": 0.0,
}


def seed_value(spec, now_ts):
    return now_ts if spec == "now" else spec


def main(path):
    if not os.path.exists(path):
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        return 1

    with open(path, "r") as fh:
        state = json.load(fh)

    backup = f"{path}.pre-mitigation.{int(time.time())}"
    shutil.copy2(path, backup)
    print(f"Backed up original to {backup}")

    now_ts = time.time()
    positions = state.get("positions") or {}
    seeded_count = 0
    added_keys_total = 0

    for cid, entry in positions.items():
        if not isinstance(entry, dict):
            continue
        added_here = 0
        for key, default in KEYS_TO_SEED_PER_POSITION.items():
            if key not in entry:
                entry[key] = seed_value(default, now_ts)
                added_here += 1
        if added_here:
            seeded_count += 1
            added_keys_total += added_here

    today_str = time.strftime("%Y-%m-%d", time.gmtime(now_ts))
    if "last_digest_date" not in state:
        state["last_digest_date"] = today_str
        print(f"Seeded last_digest_date = {today_str}")

    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp_path, path)

    print(
        f"Seeded {seeded_count} positions with missing keys "
        f"({added_keys_total} keys total). Wrote {path}."
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
