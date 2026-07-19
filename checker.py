"""
Disney Fort Wilderness DVC Cabin Availability Checker.

Drives the real booking flow with Playwright:
    resort rates-rooms page
      -> "Check Availability" modal
      -> fill check-in / check-out (wdpr-datepicker, shadow DOM)
      -> "Find a Room"
      -> read the room cards

The room cards land in exactly one of two states:

    AVAILABLE    a price block and a "Select" button are rendered
    UNAVAILABLE  "This room type is unavailable for the dates, party size or offer selected."

Anything else is treated as BROKEN and exits non-zero. That is deliberate: a
silent "no availability" from a checker that has actually stopped working is
indistinguishable from a real answer, which is the one failure mode that makes
this whole thing useless.
"""

import os
import sys
from datetime import datetime

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

import requests

RESORT_URL = (
    "https://disneyworld.disney.go.com/resorts/"
    "dvc-cabins-at-fort-wilderness-resort/rates-rooms/"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Dates are plain config, not secrets -- set them in the workflow's env: block.
CHECK_IN_DATE = os.environ.get("CHECK_IN_DATE", "2026-12-01")
CHECK_OUT_DATE = os.environ.get("CHECK_OUT_DATE", "2026-12-05")
ADULTS = os.environ.get("ADULTS", "2")

PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY", "")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN", "")

# Marker text Disney renders when the room type has nothing open.
UNAVAILABLE_MARKER = "This room type is unavailable"

BOOKING_URL = f"{RESORT_URL}?checkIn={CHECK_IN_DATE}&checkOut={CHECK_OUT_DATE}&adults={ADULTS}"


class CheckerBroken(Exception):
    """The page no longer looks the way we expect -- never treat this as 'no availability'."""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    print(f"[{now()}] {msg}", flush=True)


def to_form_date(iso_date):
    """2026-12-01 -> 12/01/2026 (the format the datepicker input expects)."""
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%m/%d/%Y")
    except ValueError as exc:
        raise CheckerBroken(f"Bad date {iso_date!r}, expected YYYY-MM-DD") from exc


def fill_date(page, selector, value, label):
    """wdpr-datepicker keeps its <input> in shadow DOM; Playwright pierces it."""
    field = page.locator(f"{selector} input").first
    try:
        field.click(timeout=15000)
        field.fill("")
        field.type(value, delay=90)
        page.keyboard.press("Tab")
        page.wait_for_timeout(2500)
    except PWTimeout as exc:
        raise CheckerBroken(f"Could not reach the {label} field ({selector})") from exc

    got = field.input_value().strip()
    if got != value:
        raise CheckerBroken(f"{label} did not take: wanted {value!r}, field shows {got!r}")
    log(f"  {label}: {got}")


def read_availability(page):
    """Return (state, detail). state is 'available' | 'unavailable'."""
    body = page.evaluate("() => document.body.innerText")

    # Price + Select button are what Disney renders for a bookable room.
    offer = page.evaluate(
        """() => {
            const card = document.querySelector('.wdw-resort-list-cards');
            const select = document.querySelector('.card-select-button');
            return {
                priceText: card ? card.innerText.replace(/\\n/g, ' ').trim().slice(0, 200) : null,
                hasSelect: !!select,
            };
        }"""
    )

    has_price = bool(offer["priceText"])
    has_select = bool(offer["hasSelect"])
    says_unavailable = UNAVAILABLE_MARKER in body

    if (has_price or has_select) and not says_unavailable:
        return "available", offer["priceText"] or "room offered (no price text parsed)"

    if says_unavailable and not (has_price or has_select):
        return "unavailable", None

    # Both markers, or neither -> the page changed. Do not guess.
    raise CheckerBroken(
        "Could not classify the result page. "
        f"price={has_price} select={has_select} unavailable_text={says_unavailable}. "
        "Disney likely changed the booking flow -- the selectors need updating."
    )


def check(page):
    log(f"Loading {RESORT_URL}")
    page.goto(RESORT_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(10000)

    try:
        page.get_by_role("button", name="Check Availability").first.click(
            force=True, timeout=20000
        )
    except PWTimeout as exc:
        raise CheckerBroken("No 'Check Availability' button on the resort page") from exc
    page.wait_for_timeout(5000)

    if not page.locator(".modalContainer").count():
        raise CheckerBroken("'Check Availability' did not open the booking modal")

    fill_date(page, "#checkInDate", to_form_date(CHECK_IN_DATE), "Check in")
    fill_date(page, "#checkOutDate", to_form_date(CHECK_OUT_DATE), "Check out")

    try:
        page.locator(".modalContainer wdpr-button", has_text="Find a Room").first.click(
            force=True, timeout=15000
        )
    except PWTimeout as exc:
        raise CheckerBroken("No 'Find a Room' button in the modal") from exc
    page.wait_for_timeout(12000)

    return read_availability(page)


def send_pushover(title, message, priority=1, sound="siren", url=None):
    if not (PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN):
        log("  (no Pushover credentials -- skipping alert)")
        return
    payload = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": title,
        "message": message,
        "priority": priority,
        "sound": sound,
    }
    if url:
        payload["url"] = url
        payload["url_title"] = "Open Disney Booking Page"
    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json", data=payload, timeout=10
        )
        if r.status_code == 200:
            log("  Pushover alert sent.")
        else:
            log(f"  Pushover error {r.status_code}: {r.text[:200]}")
    except Exception as exc:  # noqa: BLE001 - never let the alert kill the run
        log(f"  Pushover failed: {exc}")


def main():
    print("=" * 60)
    print("Disney Fort Wilderness Cabin Checker")
    print(f"Window: {CHECK_IN_DATE} to {CHECK_OUT_DATE}  ({ADULTS} adults)")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chromium")
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1400, "height": 1100},
            locale="en-US",
        )
        page = context.new_page()
        try:
            state, detail = check(page)
        except (CheckerBroken, PWTimeout, Exception) as exc:  # noqa: BLE001
            page.screenshot(path="failure.png", full_page=True)
            log(f"CHECKER BROKEN: {exc}")
            send_pushover(
                "Disney cabin checker is broken",
                f"The checker could not read availability:\n\n{exc}\n\n"
                "It is NOT reporting 'no availability' -- it stopped working. "
                "Check the GitHub Actions log.",
                priority=0,
                sound="falling",
            )
            browser.close()
            sys.exit(1)
        browser.close()

    if state == "available":
        log(f"AVAILABILITY FOUND: {detail}")
        send_pushover(
            "Disney Cabin Alert - Book Now!",
            f"Fort Wilderness DVC Cabins are available!\n\n"
            f"{CHECK_IN_DATE} to {CHECK_OUT_DATE} ({ADULTS} adults)\n"
            f"{detail}\n\n"
            f"Tap to book before it's gone.",
            url=BOOKING_URL,
        )
    else:
        log(f"No availability for {CHECK_IN_DATE} to {CHECK_OUT_DATE}.")


if __name__ == "__main__":
    main()
