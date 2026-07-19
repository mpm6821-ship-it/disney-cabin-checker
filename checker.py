"""
Disney Fort Wilderness DVC Cabin Availability Checker
Runs on GitHub Actions on a schedule. Sends a Pushover alert when cabins open.
"""

import requests
import json
import os
import sys
from datetime import datetime

# ============================================================
# DATES - set these as GitHub Secrets or edit directly here
# ============================================================
CHECK_IN_DATE  = os.environ.get("CHECK_IN_DATE",  "2026-12-01")
CHECK_OUT_DATE = os.environ.get("CHECK_OUT_DATE", "2026-12-05")

# ============================================================
# PUSHOVER - pulled from GitHub Secrets (never hardcode these)
# ============================================================
PUSHOVER_USER_KEY  = os.environ.get("PUSHOVER_USER_KEY",  "")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN", "")

# ============================================================
# DISNEY API - don't change these
# ============================================================
AVAILABILITY_URL = "https://disneyworld.disney.go.com/availability-calendar/api/calendar"

BOOKING_URL = (
    "https://disneyworld.disney.go.com/resorts/dvc-cabins-at-fort-wilderness-resort/rates-rooms/"
    f"?checkIn={CHECK_IN_DATE}&checkOut={CHECK_OUT_DATE}&adults=2"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://disneyworld.disney.go.com/",
}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def check_availability():
    params = {
        "segment": "resort",
        "startDate": CHECK_IN_DATE,
        "endDate": CHECK_OUT_DATE,
    }

    print(f"[{now()}] Checking availability for {CHECK_IN_DATE} to {CHECK_OUT_DATE}...")

    try:
        response = requests.get(
            AVAILABILITY_URL,
            headers=HEADERS,
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        print(f"[{now()}] API response received. Scanning {len(data)} date entries.")

        available_dates = []
        for item in data:
            item_date   = item.get("date", "")
            availability = item.get("availability", "none")
            print(f"  {item_date}: {availability}")

            if availability != "none" and CHECK_IN_DATE <= item_date <= CHECK_OUT_DATE:
                available_dates.append(item_date)

        return available_dates

    except requests.exceptions.RequestException as e:
        print(f"[{now()}] Request error: {e}")
        sys.exit(1)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[{now()}] Response parsing error: {e}")
        sys.exit(1)


def send_pushover_alert(available_dates):
    date_list = ", ".join(available_dates)
    message = (
        f"Fort Wilderness DVC Cabins are available!\n\n"
        f"Open dates: {date_list}\n"
        f"Window: {CHECK_IN_DATE} to {CHECK_OUT_DATE}\n\n"
        f"Tap the link below to book before it's gone."
    )

    payload = {
        "token":     PUSHOVER_API_TOKEN,
        "user":      PUSHOVER_USER_KEY,
        "title":     "Disney Cabin Alert - Book Now!",
        "message":   message,
        "url":       BOOKING_URL,
        "url_title": "Open Disney Booking Page",
        "priority":  1,
        "sound":     "siren",
    }

    try:
        response = requests.post(
            "https://api.pushover.net/1/messages.json",
            data=payload,
            timeout=10,
        )
        if response.status_code == 200:
            print(f"[{now()}] Pushover alert sent.")
        else:
            print(f"[{now()}] Pushover error: {response.status_code} - {response.text}")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"[{now()}] Failed to send alert: {e}")
        sys.exit(1)


def main():
    print("=" * 55)
    print("Disney Fort Wilderness Cabin Checker")
    print(f"Window: {CHECK_IN_DATE} to {CHECK_OUT_DATE}")
    print("=" * 55)

    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        print("ERROR: Pushover credentials missing. Add them as GitHub Secrets.")
        sys.exit(1)

    available_dates = check_availability()

    if available_dates:
        print(f"[{now()}] AVAILABILITY FOUND: {', '.join(available_dates)}")
        send_pushover_alert(available_dates)
    else:
        print(f"[{now()}] No availability found. Will check again on next scheduled run.")


if __name__ == "__main__":
    main()
