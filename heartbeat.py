"""
Weekly "still alive" report for the cabin checker.

The checker's own alerts only fire when a run *fails*. They cannot tell you
about runs that never happened -- a disabled workflow, exhausted Actions
minutes, a renamed repo, GitHub dropping scheduled runs. In all of those the
Actions tab looks calm and your phone stays quiet, which is indistinguishable
from "checked, nothing available".

So this reports on the checker from the outside: how many times it actually
ran in the last 7 days, and how many of those failed. If a Sunday goes by
with no heartbeat at all, that silence is itself the signal.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import requests

REPO = os.environ.get("GITHUB_REPOSITORY", "mpm6821-ship-it/disney-cabin-checker")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY", "")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN", "")

WORKFLOW_FILE = "check.yml"
WINDOW_DAYS = 7

# Hourly checks -> ~168/week. Well under that means runs are being dropped.
EXPECTED_MIN_RUNS = 100


def fetch_runs():
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/runs"
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    runs, page = [], 1
    while page <= 4:  # 400 runs is plenty for a 7-day window
        r = requests.get(
            url, headers=headers, params={"per_page": 100, "page": page}, timeout=30
        )
        r.raise_for_status()
        batch = r.json().get("workflow_runs", [])
        if not batch:
            break
        for run in batch:
            started = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
            if started >= cutoff:
                runs.append(run)
        if len(batch) < 100 or all(
            datetime.fromisoformat(b["created_at"].replace("Z", "+00:00")) < cutoff
            for b in batch
        ):
            break
        page += 1
    return runs


def send_pushover(title, message, priority):
    if not (PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN):
        print("No Pushover credentials -- printing instead:")
        print(f"  {title}: {message}")
        return
    r = requests.post(
        "https://api.pushover.net/1/messages.json",
        data={
            "token": PUSHOVER_API_TOKEN,
            "user": PUSHOVER_USER_KEY,
            "title": title,
            "message": message,
            "priority": priority,
            "sound": "pushover" if priority <= 0 else "falling",
        },
        timeout=15,
    )
    print(f"Pushover -> {r.status_code} {r.text[:200]}")


def main():
    try:
        runs = fetch_runs()
    except Exception as exc:  # noqa: BLE001
        send_pushover(
            "Cabin checker heartbeat failed",
            f"Could not read workflow history from GitHub:\n\n{exc}\n\n"
            "The checker itself may still be fine -- but this report cannot "
            "confirm it. Check the Actions tab.",
            priority=0,
        )
        sys.exit(1)

    total = len(runs)
    failed = sum(1 for r in runs if r.get("conclusion") not in ("success", None))
    succeeded = sum(1 for r in runs if r.get("conclusion") == "success")
    last = runs[0]["created_at"] if runs else "never"

    print(f"window: last {WINDOW_DAYS} days")
    print(f"total={total} success={succeeded} failed={failed} last={last}")

    if total == 0:
        title, priority = "Cabin checker has STOPPED running", 1
        body = (
            f"No runs at all in the last {WINDOW_DAYS} days.\n\n"
            "The schedule is not firing. The workflow may be disabled, or "
            "Actions may be unavailable for this repo.\n\n"
            "You are NOT being watched for availability right now."
        )
    elif failed and succeeded == 0:
        title, priority = "Cabin checker is failing every run", 1
        body = (
            f"All {total} runs in the last {WINDOW_DAYS} days failed.\n\n"
            f"Most recent: {last}\n\n"
            "Disney likely changed the booking flow. Check the Actions tab "
            "for the failure screenshot."
        )
    elif failed:
        title, priority = "Cabin checker: some runs failing", 0
        body = (
            f"{succeeded} succeeded, {failed} failed in the last {WINDOW_DAYS} days.\n\n"
            "Intermittent -- often a slow page load. Worth a look if it keeps up."
        )
    elif total < EXPECTED_MIN_RUNS:
        title, priority = "Cabin checker: runs being skipped", 0
        body = (
            f"Only {total} runs in the last {WINDOW_DAYS} days "
            f"(hourly should be ~168).\n\n"
            "GitHub is dropping scheduled runs. Still working, just less often "
            "than you think."
        )
    else:
        title, priority = "Cabin checker is alive", -1  # -1 = quiet, no sound
        body = (
            f"{succeeded} checks in the last {WINDOW_DAYS} days, no failures.\n\n"
            f"Most recent: {last}\n\n"
            "Still watching. No availability found yet."
        )

    send_pushover(title, body, priority)


if __name__ == "__main__":
    main()
