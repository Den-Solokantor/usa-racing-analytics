#!/usr/bin/env python3
"""Update data/results.json — winners by track (ET day)."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "results.json"
UA = "USA-Racing-Analytics/1.0 (results bot)"
ET = ZoneInfo("America/New_York")
BASE = "https://api.formfav.com/v1"


def now_et() -> datetime:
    return datetime.now(ET)


def fetch(url: str, headers: dict[str, str] | None = None, timeout: int = 40) -> bytes:
    h = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        h.update(headers)
    req = Request(url, headers=h)
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def from_formfav(api_key: str, day: datetime) -> list[dict[str, Any]]:
    date_s = day.strftime("%Y-%m-%d")
    headers = {"X-API-Key": api_key}
    q = urlencode({"date": date_s, "race_code": "gallops", "timezone": "America/New_York"})
    data = json.loads(fetch(f"{BASE}/form/meetings?{q}", headers=headers).decode("utf-8", "replace"))
    meetings: list[Any] = []
    if isinstance(data, list):
        meetings = data
    elif isinstance(data, dict):
        meetings = data.get("meetings") or data.get("data") or data.get("tracks") or []

    tracks_out: list[dict[str, Any]] = []
    for meet in meetings:
        if not isinstance(meet, dict):
            continue
        track = str(meet.get("track") or meet.get("venue") or meet.get("name") or meet.get("course") or "").strip()
        slug = str(meet.get("slug") or meet.get("track_slug") or slugify(track))
        country = str(meet.get("country") or meet.get("countryCode") or "").lower()
        if country and country not in ("us", "usa", "ca", ""):
            if len(country) == 2 and country != "us":
                continue
        if not slug:
            continue

        rq = urlencode({
            "date": date_s, "track": slug, "race_code": "gallops",
            "country": "us", "timezone": "America/New_York",
        })
        try:
            time.sleep(0.4)
            res = json.loads(fetch(f"{BASE}/results/meeting?{rq}", headers=headers).decode("utf-8", "replace"))
        except Exception as e:
            print(f"results skip {slug}: {e}", file=sys.stderr)
            continue

        races_data = res.get("races") or res.get("results") or res.get("data") or [] if isinstance(res, dict) else (res if isinstance(res, list) else [])
        race_rows: list[dict[str, Any]] = []
        for r in races_data:
            if not isinstance(r, dict):
                continue
            num = r.get("race") or r.get("raceNumber") or r.get("number") or r.get("race_number")
            title = str(r.get("raceName") or r.get("title") or r.get("name") or "").strip()
            winner = jockey = trainer = odds = margin = ""
            w = r.get("winner") or r.get("first") or {}
            if isinstance(w, dict):
                winner = str(w.get("name") or w.get("horse") or "").strip()
                jockey = str(w.get("jockey") or "").strip()
                trainer = str(w.get("trainer") or "").strip()
                odds = str(w.get("odds") or w.get("sp") or "").strip()
                margin = str(w.get("margin") or w.get("distance") or "").strip()
            elif isinstance(w, str):
                winner = w
            runners = r.get("runners") or r.get("horses") or r.get("finishers") or []
            if not winner and isinstance(runners, list):
                for h in runners:
                    if not isinstance(h, dict):
                        continue
                    pos = str(h.get("position") or h.get("pos") or h.get("finish") or "")
                    if pos in ("1", "1st", "first"):
                        winner = str(h.get("name") or h.get("horse") or "").strip()
                        jockey = str(h.get("jockey") or "").strip()
                        trainer = str(h.get("trainer") or "").strip()
                        odds = str(h.get("odds") or h.get("sp") or "").strip()
                        margin = str(h.get("margin") or h.get("distance_beaten") or "").strip()
                        break
            race_rows.append({
                "race": int(num) if num is not None and str(num).isdigit() else num,
                "title": title,
                "winner": winner or "— ожидание —",
                "jockey": jockey, "trainer": trainer, "odds": odds, "margin": margin,
                "status": "official" if winner else "pending",
            })
        if race_rows:
            tracks_out.append({"track": track or slug, "code": slug.upper()[:4], "races": race_rows})
    return tracks_out


def placeholder_tracks(day: datetime) -> list[dict[str, Any]]:
    month = day.month
    if month in (7, 8, 9):
        names = ["Saratoga", "Del Mar", "Monmouth Park", "Colonial Downs", "Ellis Park"]
    elif month in (10, 11):
        names = ["Keeneland", "Santa Anita", "Belmont at Aqueduct", "Gulfstream Park"]
    elif month in (12, 1, 2, 3):
        names = ["Gulfstream Park", "Santa Anita", "Aqueduct", "Fair Grounds"]
    else:
        names = ["Keeneland", "Churchill Downs", "Belmont", "Santa Anita"]
    out = []
    for name in names[:5]:
        out.append({
            "track": name, "code": slugify(name)[:4].upper(),
            "races": [{
                "race": n, "title": "", "winner": "— ожидание —",
                "jockey": "", "trainer": "", "odds": "", "margin": "", "status": "pending",
            } for n in range(1, 4)],
        })
    return out


def main() -> int:
    day = now_et()
    key = os.environ.get("FORMFAV_API_KEY", "").strip()
    tracks: list[dict[str, Any]] = []
    source = "placeholder"
    note = "Реальные победители появятся после подключения FORMFAV_API_KEY или ручного обновления JSON."
    if key:
        try:
            print("Trying FormFav results...")
            tracks = from_formfav(key, day)
            if not tracks:
                yday = day - timedelta(days=1)
                print("No results for today — try yesterday...")
                tracks = from_formfav(key, yday)
                if tracks:
                    day = yday
            if tracks:
                source = "formfav"
                note = "Данные FormFav (результаты встреч)."
                print(f"FormFav: {len(tracks)} tracks")
            else:
                print("FormFav empty — placeholder", file=sys.stderr)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            print(f"FormFav failed: {e}", file=sys.stderr)
    if not tracks:
        tracks = placeholder_tracks(day)
    payload = {
        "updated": datetime.now(ET).isoformat(),
        "date": day.strftime("%Y-%m-%d"),
        "source": source, "note": note, "tracks": tracks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote results -> {OUT} source={source} tracks={len(tracks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
