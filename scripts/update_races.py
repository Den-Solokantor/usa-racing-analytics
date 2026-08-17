#!/usr/bin/env python3
"""Update data/races.json for Сегодня на треках США."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "races.json"
UA = "USA-Racing-Analytics/1.0 (github-actions races bot)"
ET = ZoneInfo("America/New_York")
MAX_RACES = 6

TRACK_NAMES = {
    "SAR": "Saratoga", "BEL": "Belmont", "AQU": "Aqueduct", "CD": "Churchill Downs",
    "DMR": "Del Mar", "SA": "Santa Anita", "GP": "Gulfstream Park", "CNL": "Colonial Downs",
    "KEE": "Keeneland", "PRX": "Parx Racing", "LRL": "Laurel Park", "MTH": "Monmouth Park",
    "ELP": "Ellis Park", "IND": "Horseshoe Indianapolis", "WO": "Woodbine",
}


def fetch(url: str, auth: tuple[str, str] | None = None, timeout: int = 30) -> bytes:
    headers = {"User-Agent": UA, "Accept": "application/json"}
    req = Request(url, headers=headers)
    if auth:
        import base64
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def now_et() -> datetime:
    return datetime.now(ET)


def from_racing_api(user: str, password: str, day: datetime) -> list[dict[str, Any]]:
    date_s = day.strftime("%Y-%m-%d")
    url = f"https://api.theracingapi.com/v1/north-america/meets?{urlencode({'start_date': date_s, 'end_date': date_s})}"
    raw = json.loads(fetch(url, auth=(user, password)).decode("utf-8", "replace"))
    meets = raw.get("meets") or raw.get("data") or []
    races: list[dict[str, Any]] = []

    for meet in meets[:8]:
        meet_id = meet.get("meet_id") or meet.get("id")
        track = (
            meet.get("track_name") or meet.get("course") or meet.get("track")
            or TRACK_NAMES.get(str(meet.get("track_code", "")).upper(), "USA Track")
        )
        entries_url = f"https://api.theracingapi.com/v1/north-america/meets/{meet_id}/entries"
        try:
            ent = json.loads(fetch(entries_url, auth=(user, password)).decode("utf-8", "replace"))
        except Exception as e:
            print(f"entries skip {meet_id}: {e}", file=sys.stderr)
            continue

        race_list = ent.get("races") or ent.get("entries") or []
        if isinstance(ent, list):
            race_list = ent

        for race in race_list:
            if not isinstance(race, dict):
                continue
            num = race.get("race_number") or race.get("number") or race.get("race")
            rtype = race.get("race_type") or race.get("type") or race.get("name") or "Race"
            dist = race.get("distance") or race.get("distance_text") or ""
            surface = race.get("surface") or race.get("course_type") or ""
            purse = race.get("purse") or race.get("purse_text") or ""
            post = race.get("post_time") or race.get("off_time") or race.get("time") or ""
            runners = race.get("runners") or race.get("entries") or []
            n_run = len(runners) if isinstance(runners, list) else race.get("number_of_runners") or ""

            title = f"Race {num} · {rtype}" if num else str(rtype)
            meta_dist = " · ".join(x for x in [str(dist), str(surface)] if x)
            purse_s = f"Purse ${purse}" if purse and not str(purse).startswith("Purse") else str(purse)
            time_s = str(post)
            if time_s and "ET" not in time_s.upper():
                time_s = f"{time_s} ET"

            tags = []
            blob = f"{rtype} {surface}".lower()
            if "turf" in blob:
                tags.append("Turf")
            if "claim" in blob:
                tags.append("Claiming")
            if "allow" in blob or "stakes" in blob or "grade" in blob:
                tags.append("Watchlist")
            if not tags:
                tags.append("USA")

            preview = (
                f"Карточка дня · {track}. "
                f"{f'{n_run} участников. ' if n_run else ''}"
                "Данные The Racing API (North America)."
            )
            rid = re.sub(r"[^a-z0-9]+", "-", f"{track}-{num}".lower()).strip("-")
            races.append({
                "id": rid or f"usa-{len(races)+1}",
                "track": str(track),
                "time": time_s or "TBD ET",
                "title": title,
                "distance": meta_dist,
                "purse": purse_s,
                "preview": preview,
                "tags": tags,
            })
            if len(races) >= MAX_RACES:
                return races
    return races


def seasonal_fallback(day: datetime) -> list[dict[str, Any]]:
    month = day.month
    dow = day.weekday()
    if month in (7, 8, 9):
        pool = [
            ("Saratoga", "NYRA · лето", "Turf"),
            ("Del Mar", "Калифорния · лето", "Dirt"),
            ("Ellis Park", "Кентукки", "Dirt"),
            ("Colonial Downs", "Вирджиния", "Turf"),
            ("Monmouth Park", "Нью-Джерси", "Dirt"),
        ]
    elif month in (10, 11):
        pool = [
            ("Keeneland", "Кентукки · осень", "Dirt"),
            ("Belmont at Aqueduct", "NYRA", "Dirt"),
            ("Del Mar", "Breeders' Cup window", "Turf"),
            ("Santa Anita", "Калифорния", "Dirt"),
            ("Gulfstream Park", "Флорида", "Dirt"),
        ]
    elif month in (12, 1, 2, 3):
        pool = [
            ("Gulfstream Park", "Флорида · зима", "Dirt"),
            ("Santa Anita", "Калифорния", "Dirt"),
            ("Aqueduct", "NYRA · зима", "Dirt"),
            ("Fair Grounds", "Луизиана", "Dirt"),
            ("Tampa Bay Downs", "Флорида", "Turf"),
        ]
    else:
        pool = [
            ("Keeneland", "Кентукки · весна", "Dirt"),
            ("Churchill Downs", "Кентукки", "Dirt"),
            ("Belmont", "NYRA", "Turf"),
            ("Santa Anita", "Калифорния", "Dirt"),
            ("Gulfstream Park", "Флорида", "Dirt"),
        ]

    start = day.timetuple().tm_yday % len(pool)
    chosen = [pool[(start + i) % len(pool)] for i in range(3)]
    race_types = [
        ("Allowance Optional Claiming", "1 mile", "Purse $90,000"),
        ("Maiden Special Weight", "6.5f", "Purse $75,000"),
        ("Claiming $25,000", "1 1/16m", "Purse $32,000"),
        ("Allowance", "7f", "Purse $85,000"),
        ("Stakes", "1 1/8m", "Purse $150,000"),
    ]
    times = ["13:10 ET", "14:40 ET", "15:35 ET", "16:20 ET", "17:05 ET"]
    races = []
    for i, (track, region, surface) in enumerate(chosen):
        rt, dist, purse = race_types[(dow + i) % len(race_types)]
        rnum = 4 + i * 2
        tags = [surface, "USA"]
        if "Claim" in rt:
            tags.append("Claiming")
        if "Stakes" in rt or "Allowance" in rt:
            tags.append("Watchlist")
        races.append({
            "id": f"{track[:3].lower()}-{day.strftime('%m%d')}-{rnum}",
            "track": track,
            "time": times[(dow + i) % len(times)],
            "title": f"Race {rnum} · {rt}",
            "distance": f"{dist} · {surface}",
            "purse": purse,
            "preview": (
                f"{region}. Карточка на {day.strftime('%d.%m.%Y')} (автошаблон). "
                "Для официальных entries: секреты RACING_API_USER / RACING_API_PASSWORD."
            ),
            "tags": tags,
        })
    return races


def main() -> int:
    day = now_et()
    user = os.environ.get("RACING_API_USER", "").strip()
    password = os.environ.get("RACING_API_PASSWORD", "").strip()
    races: list[dict[str, Any]] = []
    source = "seasonal-fallback"

    if user and password:
        try:
            print("Trying The Racing API North America...")
            races = from_racing_api(user, password, day)
            if races:
                source = "theracingapi-na"
                print(f"API returned {len(races)} races")
            else:
                print("API returned 0 races — fallback", file=sys.stderr)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            print(f"API failed: {e} — fallback", file=sys.stderr)
    else:
        print("No API secrets — seasonal fallback")

    if not races:
        races = seasonal_fallback(day)

    payload = {
        "updated": datetime.now(ET).isoformat(),
        "source": source,
        "date": day.strftime("%Y-%m-%d"),
        "races": races[:MAX_RACES],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(payload['races'])} races -> {OUT} (source={source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
