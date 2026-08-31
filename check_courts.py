#!/usr/bin/env python3
"""Poll LTA court availability against user-defined alert rules and notify via
Telegram when a new slot matching a rule opens up.

Rules (which courts, which days of week, which time window) live in a
Supabase table managed by the site/ frontend -- see supabase_schema.sql and
site/index.html. This script only reads them.

No LLM calls: pure HTTP polling + rule matching. Run on a schedule
(GitHub Actions / cron).
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

STATE_PATH = Path(__file__).parent / "state.json"

LTA_AVAILABILITY_URL = "https://www.lta.org.uk/api/courtdetail/availability?venueid={venue_id}&date={date}"

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

DAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def http_get_json(url: str, headers: dict) -> object:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def fetch_rules() -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/alert_rules?select=*"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    }
    return http_get_json(url, headers)


def fetch_availability(venue_id: str, day: str) -> dict:
    url = LTA_AVAILABILITY_URL.format(venue_id=venue_id, date=day)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def slot_set(data: dict) -> set[str]:
    """'CourtName|startTimeISO' for every non-mini-court available slot."""
    result = set()
    for court in data.get("venueDetails", []):
        if court["name"].lower().startswith("mini"):
            continue
        for slot in court.get("availableSlots", []):
            result.add(f"{court['name']}|{slot['startTime']}")
    return result


def rule_matches(rule: dict, slot_date: date, start_clock: str) -> bool:
    weekday = DAY_CODES[slot_date.weekday()]
    if weekday not in rule["days"]:
        return False
    return rule["start_time"] <= start_clock < rule["end_time"]


def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[warn] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set, printing instead:")
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=15)


def main() -> int:
    rules = fetch_rules()
    if not rules:
        print("No alert rules configured - nothing to check.")
        return 0

    rules_by_venue: dict[str, list[dict]] = {}
    venue_names: dict[str, str] = {}
    for rule in rules:
        rules_by_venue.setdefault(rule["venue_id"], []).append(rule)
        venue_names[rule["venue_id"]] = rule["venue_name"]

    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    new_state = {}
    alerts = []

    for venue_id, venue_rules in rules_by_venue.items():
        vname = venue_names[venue_id]

        # First call (today) also tells us how many days ahead LTA allows booking.
        today = date.today()
        try:
            first = fetch_availability(venue_id, today.isoformat())
        except Exception as exc:
            print(f"[error] {vname} {today}: {exc}", file=sys.stderr)
            continue
        available_dates = first.get("rules", {}).get("availableDates", [today.isoformat()])

        for day_str in available_dates:
            key = f"{venue_id}|{day_str}"
            if day_str == today.isoformat():
                data = first
            else:
                try:
                    data = fetch_availability(venue_id, day_str)
                except Exception as exc:
                    print(f"[error] {vname} {day_str}: {exc}", file=sys.stderr)
                    new_state[key] = state.get(key, [])
                    continue

            current = slot_set(data)
            previous = set(state.get(key, []))
            new_state[key] = sorted(current)

            newly_available = current - previous
            if not newly_available:
                continue

            slot_date = datetime.strptime(day_str, "%Y-%m-%d").date()
            for entry in sorted(newly_available):
                court, start_iso = entry.split("|", 1)
                start_clock = start_iso[11:16]
                for rule in venue_rules:
                    if rule_matches(rule, slot_date, start_clock):
                        alerts.append(f"{vname} — {court}: {day_str} {start_clock}")
                        break

    STATE_PATH.write_text(json.dumps(new_state, indent=2))

    if alerts:
        message = "New tennis court availability:\n" + "\n".join(alerts)
        send_telegram(message)
        print(message)
    else:
        print("No new matching availability.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
