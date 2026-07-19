"""
Disney Fort Wilderness DVC Cabin Availability Checker
v2 - hits multiple endpoints to maximize coverage
"""

import requests
import json
import os
import sys
from datetime import datetime

CHECK_IN_DATE  = os.environ.get("CHECK_IN_DATE",  "2026-12-01")
CHECK_OUT_DATE = os.environ.get("CHECK_OUT_DATE", "2026-12-05")

PUSHOVER_USER_KEY  = os.environ.get("PUSHOVER_USER_KEY",  "")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN", "")

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


def check_calendar_api():
    """Hit Disney's availability calendar API - segment=resort"""
    url = "https://disneyworld.disney.go.com/availability-calendar/api/calendar"
    params = {
        "segment": "resort",
        "startDate": CHECK_IN_DATE,
        "endDate": CHECK_OUT_DATE,
    }
    print(f"\n[{now()}] Trying calendar API (segment=resort)...")
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        print(f"  Status: {r.status_code}")
        print(f"  Raw response: {r.text[:2000]}")
        r.raise_for_status()
        data = r.json()
        available = []
        for item in data:
            date = item.get("date", "")
            avail = item.get("availability", "none")
            if date and avail != "none" and CHECK_IN_DATE <= date <= CHECK_OUT_DATE:
                available.append(date)
        return available
    except Exception as e:
        print(f"  Error: {e}")
        return []


def check_rates_api():
    """Hit Disney's rates/rooms endpoint directly for Fort Wilderness DVC Cabins"""
    url = (
        "https://disneyworld.disney.go.com/finder/api/v1/explorer-service/list-ancestor-entities-of/"
        "wdw/80010189;entityType=resort/room-types"
    )
    print(f"\n[{now()}] Trying rates/rooms API...")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  Status: {r.status_code}")
        print(f"  Raw response: {r.text[:2000]}")
        return []
    except Exception as e:
        print(f"  Error: {e}")
        return []


def check_offer_api():
    """Try Disney's offer/availability endpoint"""
    url = "https://disneyworld.disney.go.com/availability-calendar/api/calendar"
    params = {
        "segment": "room",
        "startDate": CHECK_IN_DATE,
        "endDate": CHECK_OUT_DATE,
        "resort": "80010189",
    }
    print(f"\n[{now()}] Trying calendar API (segment=room, resort ID)...")
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        print(f"  Status: {r.status_code}")
        print(f"  Raw response: {r.text[:2000]}")
        r.raise_for_status()
        data = r.json()
        available = []
        for item in data:
            date = item.get("date", "")
            avail = item.get("availability", "none")
            if date and avail != "none" and CHECK_IN_DATE <= date <= CHECK_OUT_DATE:
                available.append(date)
        return available
    except Exception as e:
        print(f"  Error: {e}")
        return []


def send_pushover_alert(available_dates):
    date_list = ", ".join(available_dates)
    message = (
        f"Fort Wilderness DVC Cabins are available!\n\n"
        f"Open dates: {date_list}\n"
        f"Window: {CHECK_IN_DATE} to {CHECK_OUT_DATE}\n\n"
        f"Tap the link to book before it's gone."
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
        r = requests.post("https://api.pushover.net/1/messages.json", data=payload, timeout=10)
        if r.status_code == 200:
            print(f"[{now()}] Pushover alert sent.")
        else:
            print(f"[{now()}] Pushover error: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"[{now()}] Failed to send alert: {e}")


def main():
    print("=" * 55)
    print("Disney Fort Wilderness Cabin Checker v2")
    print(f"Window: {CHECK_IN_DATE} to {CHECK_OUT_DATE}")
    print("=" * 55)

    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        print("ERROR: Pushover credentials missing.")
        sys.exit(1)

    # Try all endpoints and collect results
    available = []
    available += check_calendar_api()
    available += check_offer_api()
    check_rates_api()  # diagnostic only for now

    available = list(set(available))  # deduplicate

    if available:
        print(f"\n[{now()}] AVAILABILITY FOUND: {', '.join(available)}")
        send_pushover_alert(available)
    else:
        print(f"\n[{now()}] No availability found across all endpoints.")


if __name__ == "__main__":
    main()
