# Disney Fort Wilderness Cabin Checker

Checks whether the DVC Cabins at Disney's Fort Wilderness Resort have availability
for a given date window, and sends a Pushover alert when they do.

## How it works

There is no public availability API. An earlier version of this project called
`disneyworld.disney.go.com/availability-calendar/api/calendar`; that route returns
`[{}]` to unauthenticated callers and **404s from the real page origin** — it does
not exist. Availability only comes out of the booking flow itself.

So `checker.py` drives that flow with Playwright:

1. Load the resort's *Room Rates* page.
2. Click **Check Availability** to open the booking modal.
3. Fill check-in / check-out (`wdpr-datepicker` keeps its `<input>` in shadow DOM;
   Playwright pierces it automatically).
4. Click **Find a Room**.
5. Read the room cards.

The result page lands in exactly one of two states:

| State | What Disney renders |
|---|---|
| Available | a price block (`.wdw-resort-list-cards`) and a `Select` button |
| Unavailable | "This room type is unavailable for the dates, party size or offer selected." |

## Failing loudly

If the page matches **neither** state — or both — the checker raises, exits `1`,
and sends a Pushover notice saying it is broken.

This is the whole point. A scraper that silently reports "no availability" after
Disney changes their markup looks identical to a real negative, and you would
never know you had stopped being alerted. A red workflow run is recoverable;
a quiet false negative is not. A screenshot (`failure.png`) is uploaded as a
workflow artifact to make the diagnosis quick.

## Configuration

Dates are plain config — edit them in `.github/workflows/check.yml` under `env:`:

```yaml
CHECK_IN_DATE: '2026-12-01'   # YYYY-MM-DD
CHECK_OUT_DATE: '2026-12-05'
ADULTS: '2'
```

Two repo **secrets** are required for alerts:

- `PUSHOVER_USER_KEY`
- `PUSHOVER_API_TOKEN`

Without them the checker still runs and logs its result; it just cannot notify.

## Schedule

Hourly (`0 * * * *`). Disney's inventory does not turn over fast enough to justify
a 10-minute cron, and a lighter footprint is less likely to get the runner blocked.
Note that automated querying is in tension with Disney's terms of service; keep the
interval conservative.

## Running locally

```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium

CHECK_IN_DATE=2026-09-15 CHECK_OUT_DATE=2026-09-17 python checker.py
```

Chromium must be the **full** build, not `headless-shell` — Disney's edge rejects
headless-shell with `ERR_HTTP2_PROTOCOL_ERROR`.

## Known limitations

- **Brittle by nature.** It depends on Disney's markup. It is built to fail loudly
  rather than silently, but it *will* need occasional selector maintenance.
- **Geo-dependent pricing.** GitHub's runners are US-based, and Disney showed
  Florida-resident offers during testing. This affects prices shown, not whether
  a room is available.
- **One room type.** It watches the DVC Cabins only.

## Keeping the schedule alive

GitHub disables scheduled workflows after **60 days without commit activity**, and
only commits reset that timer — not issues, releases, or workflow runs. A checker
that just sits there watching a date months out will therefore switch itself off
before the date arrives, with a single easily-missed email as warning.

`.github/workflows/keepalive.yml` makes a trivial monthly commit to prevent this.
