#!/usr/bin/env python3
"""
GitHub Actions: карды Equibase (TVG) → data/races.json + data/results.json.

Без браузера, только httpx.
Не делает git push — это делает workflow.

Запуск локально:
  pip install httpx
  python scripts/update_cards_from_equibase.py
  python scripts/update_cards_from_equibase.py --date 2026-08-22
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import httpx
except ImportError:
    sys.exit("Нужен httpx: pip install httpx")

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:
    _ET = None

ROOT = Path(__file__).resolve().parents[1]
RACES_PATH = ROOT / "data" / "races.json"
RESULTS_PATH = ROOT / "data" / "results.json"

TRACK_NAMES: dict[str, str] = {
    "SAR": "Saratoga", "BEL": "Belmont", "AQU": "Aqueduct", "BAQ": "Belmont at Aqueduct",
    "CD": "Churchill Downs", "DMR": "Del Mar", "SA": "Santa Anita", "GP": "Gulfstream Park",
    "GPW": "Gulfstream Park West", "OP": "Oaklawn Park", "KEE": "Keeneland",
    "CT": "Colonial Downs", "CNL": "Colonial Downs", "MTH": "Monmouth Park",
    "WO": "Woodbine", "PRX": "Parx Racing", "TAM": "Tampa Bay Downs", "FG": "Fair Grounds",
    "LRL": "Laurel Park", "PIM": "Pimlico", "TUP": "Turf Paradise", "GG": "Golden Gate Fields",
    "EMD": "Emerald Downs", "CBY": "Canterbury Park", "DEL": "Delaware Park",
    "ELP": "Ellis Park", "FL": "Finger Lakes", "HAW": "Hawthorne", "IND": "Indiana Grand",
    "LS": "Lone Star Park", "MVR": "Mahoning Valley", "PEN": "Penn National",
    "TDN": "Thistledown", "TP": "Turfway Park", "ZIA": "Zia Park",
    "BTP": "Belterra Park", "ALB": "Albuquerque",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
BASE = "https://tvg.equibase.com/static/entry"

_POST_TIME_RE = re.compile(
    r"POST\s*Time\s*-\s*(\d{1,2}):(\d{2})\s*([AP])\.?M\.?\s*ET", re.I
)
_PURSE_DIST_RE = re.compile(r"Purse\s*\$([\d,]+)\.\s*([^.]+?)\.")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def track_display_name(code: str) -> str:
    return TRACK_NAMES.get((code or "").upper(), code)


def frac_to_decimal(s: Any) -> Optional[float]:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return round(float(s), 2)
    s = str(s).strip()
    if not s or s in {"-", "--", "N/A", "SCR", "Scr"}:
        return None
    low = s.lower()
    if low in {"evs", "evens", "even", "even money"}:
        return 2.0
    m = re.match(r"^(\d+)/(\d+)$", s)
    if m:
        n, d = int(m.group(1)), int(m.group(2))
        return round(1 + n / d, 2) if d else None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def parse_post_time(section_text: str, race_date: str):
    m = _POST_TIME_RE.search(section_text)
    if not m:
        return None, None
    hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if ampm == "P" and hour != 12:
        hour += 12
    if ampm == "A" and hour == 12:
        hour = 0
    label = f"{m.group(1)}:{m.group(2)} {ampm}M ET"
    dt = None
    if _ET is not None:
        try:
            y, mo, d = (int(p) for p in race_date.split("-"))
            dt = datetime(y, mo, d, hour, minute, tzinfo=_ET)
        except Exception:
            dt = None
    return label, dt


def parse_purse_distance(section_text: str):
    m = _PURSE_DIST_RE.search(section_text)
    if not m:
        return None, None
    return f"Purse ${m.group(1)}", m.group(2).strip()


def tracks_for_date(client: httpx.Client, race_date: str) -> list[str]:
    y, m, d = race_date.split("-")
    mdy = f"{m}{d}{y[2:]}"
    try:
        r = client.get(f"{BASE}/")
    except Exception as e:
        log(f"Индекс: ошибка {e}")
        return []
    if r.status_code != 200:
        log(f"Индекс -> HTTP {r.status_code}")
        return []
    found = re.findall(
        rf"(?:entry/|Index)([A-Z]{{2,4}}){mdy}(?:USA|CAN|PR)?-?EQB\.html",
        r.text,
        flags=re.I,
    )
    tracks = sorted({t.upper() for t in found})
    log(f"Индекс: {len(tracks)} треков {tracks[:15]}{'...' if len(tracks) > 15 else ''}")
    return tracks


def parse_entry_page(html: str, track: str, race_date: str) -> list[dict]:
    out: list[dict] = []
    now_et = datetime.now(_ET) if _ET is not None else None
    parts = re.split(r'(?i)id=["\']Race(\d+)["\']', html)
    i = 1
    while i + 1 < len(parts):
        try:
            race_no = int(parts[i])
        except ValueError:
            i += 2
            continue
        section = parts[i + 1]
        section_plain = re.sub(r"<[^>]+>", " ", section)
        post_time_label, post_time_dt = parse_post_time(section_plain, race_date)
        purse, distance = parse_purse_distance(section_plain)
        finished = None
        if post_time_dt is not None and now_et is not None:
            finished = now_et > post_time_dt

        for row in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", section):
            tds = re.findall(r"(?is)<td[^>]*>(.*?)</td>", row)
            texts = [" ".join(re.sub(r"<[^>]+>", " ", t).split()) for t in tds]
            if not texts:
                continue
            joined = " ".join(texts).upper()
            if "SCRATCH" in joined or texts[0].upper().replace("&NBSP;", "").strip() in {
                "SCR", "SCRATCHED"
            }:
                continue
            post_s = texts[0].strip()
            if not re.match(r"^\d{1,2}$", post_s):
                continue
            horse = texts[2] if len(texts) > 2 else texts[1]
            horse = re.sub(r"\s*\([A-Z]{2,3}\)\s*$", "", horse).strip()
            if not horse or re.search(
                r"(?i)^(horse|program|jockey|trainer|pp|p#)$", horse
            ):
                continue
            ml_raw = None
            for cand in (
                texts[10] if len(texts) > 10 else None,
                texts[-2] if len(texts) >= 2 else None,
                texts[5] if len(texts) > 5 else None,
            ):
                if cand and re.match(r"^\d+/\d+$|^\d+\.\d+$|evens?", cand, re.I):
                    ml_raw = cand
                    break
            ml_value = frac_to_decimal(ml_raw)
            out.append({
                "track": track,
                "race": race_no,
                "post": int(post_s),
                "horse": horse,
                "morning_line": ml_value,
                "post_time": post_time_label,
                "finished": finished,
                "purse": purse,
                "distance": distance,
            })
        i += 2
    return out


def fetch_odds(race_date: str, track: str = "") -> list[dict]:
    y, m, d = race_date.split("-")
    mdy = f"{m}{d}{y[2:]}"
    client = httpx.Client(
        headers={
            "User-Agent": UA,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        follow_redirects=True,
        timeout=30,
    )
    try:
        tracks = [track.upper()] if track else tracks_for_date(client, race_date)
        all_rows: list[dict] = []
        for tr in tracks:
            url = f"{BASE}/{tr}{mdy}USA-EQB.html"
            try:
                r = client.get(url)
            except Exception as e:
                log(f"{tr}: {e}")
                continue
            if r.status_code != 200 or len(r.text) < 5000:
                log(f"{tr}: HTTP {r.status_code} len={len(r.text)}")
                continue
            rows = parse_entry_page(r.text, tr, race_date)
            log(f"{tr}: {len(rows)} лошадей")
            all_rows.extend(rows)
        return all_rows
    finally:
        client.close()


def odds_to_races_json(odds: list[dict], race_date: str) -> dict:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in odds:
        tr = (r.get("track") or "").upper()
        try:
            rn = int(r.get("race") or 0)
        except (TypeError, ValueError):
            rn = 0
        if not tr or not rn:
            continue
        groups[(tr, rn)].append(r)

    races = []
    date_compact = race_date.replace("-", "")
    for (tr, rn), horses_raw in sorted(groups.items()):
        horses_sorted = sorted(
            horses_raw, key=lambda h: int(h.get("post") or 0)
        )
        first = horses_sorted[0] if horses_sorted else {}
        horses = []
        for h in horses_sorted:
            name = (h.get("horse") or "").strip()
            if not name:
                continue
            horses.append({
                "post": int(h.get("post") or 0),
                "name": name,
                "ml": h.get("morning_line"),
                "win": None,
            })
        finished = first.get("finished")
        tags = ["USA", "Equibase", "ML", "ML estimate"]
        if finished:
            tags.append("Finished")
        races.append({
            "id": f"{tr.lower()}-{date_compact[4:]}-{rn}",
            "track": track_display_name(tr),
            "time": first.get("post_time") or "",
            "title": f"Race {rn}",
            "distance": first.get("distance") or "",
            "purse": first.get("purse") or "",
            "horses": horses,
            "preview": "",
            "tags": tags,
        })

    return {
        "updated": datetime.now(timezone.utc).astimezone().isoformat(),
        "source": "equibase-parser-gha",
        "date": race_date,
        "races": races[:40],
    }


def races_to_results_json(
    races_payload: dict, existing: Optional[dict] = None
) -> dict:
    existing = existing or {}
    old_by_id: dict[str, dict] = {}
    for r in existing.get("races") or []:
        if r.get("id"):
            old_by_id[r["id"]] = r
    for t in existing.get("tracks") or []:
        for r in t.get("races") or []:
            rid = r.get("id") or (
                f"{(t.get('code') or t.get('track') or '').lower()}-r{r.get('race')}"
            )
            old_by_id[rid] = r

    out_races = []
    for race in races_payload.get("races") or []:
        old = old_by_id.get(race.get("id") or "") or {}
        old_by_post = {
            h.get("post"): h
            for h in (old.get("horses") or [])
            if h.get("post") is not None
        }
        old_by_name = {
            (h.get("name") or "").lower(): h
            for h in (old.get("horses") or [])
            if h.get("name")
        }
        new_horses = []
        for h in race.get("horses") or []:
            prev = (
                old_by_post.get(h.get("post"))
                or old_by_name.get((h.get("name") or "").lower())
                or {}
            )
            new_horses.append({
                "post": h.get("post"),
                "name": h.get("name"),
                "ml": h.get("ml"),
                "place": prev.get("place"),
            })
        has_places = any(h.get("place") is not None for h in new_horses)
        finished = "Finished" in (race.get("tags") or [])
        out_races.append({
            "id": race.get("id"),
            "track": race.get("track"),
            "time": race.get("time") or "",
            "title": race.get("title") or "",
            "distance": race.get("distance") or "",
            "purse": race.get("purse") or "",
            "status": "official" if has_places else "pending",
            "tags": ["USA", "Result"] + (["Finished"] if finished else []),
            "horses": new_horses,
        })

    return {
        "updated": datetime.now(timezone.utc).astimezone().isoformat(),
        "date": races_payload.get("date"),
        "source": "manual+cards",
        "note": (
            "Состав как в «Сегодня». После финиша: "
            "python set_places.py --race ID --winner ..."
        ),
        "results": [],
        "stakes_results": existing.get("stakes_results") or [],
        "races": out_races,
    }


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--track", default="")
    args = ap.parse_args()

    log(f"Дата: {args.date}")
    odds = fetch_odds(args.date, args.track)
    if not odds:
        log("Пусто — карды ещё не вышли или Equibase недоступен")
        sys.exit(0)

    races_payload = odds_to_races_json(odds, args.date)
    RACES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RACES_PATH.write_text(
        json.dumps(races_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    log(f"Записан {RACES_PATH} ({len(races_payload['races'])} гонок)")

    existing: dict = {}
    if RESULTS_PATH.exists():
        try:
            existing = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log("WARN: results.json битый — пересоздаём")
            existing = {}

    results_payload = races_to_results_json(races_payload, existing)
    RESULTS_PATH.write_text(
        json.dumps(results_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    log(f"Записан {RESULTS_PATH} ({len(results_payload['races'])} гонок)")


if __name__ == "__main__":
    main()
