#!/usr/bin/env python3
"""
Обновление data/results.json — ТОЛЬКО stakes_results (OTB RSS).

НЕ трогает:
  - races[]   — состав дня + place из Equibase (cards / results GHA)
  - date/source, связанные с equibase

Раньше скрипт пересобирал JSON только с tracks[] и затирал races[] —
из‑за этого блок «Результаты» на сайте становился пустым.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "results.json"
ETZ = ZoneInfo("America/New_York")
UA = "USA-Racing-Analytics/1.0 (stakes-only; +https://solokantorracing.netlify.app)"

OTB_FEEDS = [
    "https://www.offtrackbetting.com/rss-results-2.0.xml",
    "https://www.offtrackbetting.com/rss-results-1.0.xml",
]


def now_et() -> datetime:
    return datetime.now(ETZ)


def fetch(url: str, timeout: int = 40) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def parse_otb_item(title: str, description: str, link: str) -> dict | None:
    t = strip_html(title)
    d = strip_html(description)
    if not t:
        return None

    winner = ""
    m = re.search(r"(?:Results?|Replay)\s*[-–—:]\s*(.+)$", t, re.I)
    if m:
        winner = m.group(1).strip()
        winner = re.sub(r"\s*&\s*Race\s*Replay.*$", "", winner, flags=re.I).strip()

    race_title = re.sub(r"\s*Results?.*$", "", t, flags=re.I).strip(" -–—")
    if not winner:
        return None

    track = ""
    tm = re.search(
        r"\bat\s+([A-Z][A-Za-z0-9 .'\\-]+?(?:Park|Course|Downs|Meadows|Field)?)\b",
        d,
    )
    if tm:
        track = tm.group(1).strip()
    if not track:
        m2 = re.search(r"/horse-racing-results/([^/]+)/", link or "")
        if m2:
            track = m2.group(1).replace("-", " ").title()

    return {
        "title": race_title,
        "track": track,
        "winner": winner,
        "link": link or "",
        "source": "offtrackbetting",
        "fetched": now_et().isoformat(),
    }


def fetch_stakes_from_otb() -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    year = str(now_et().year)
    prev = str(now_et().year - 1)

    for feed in OTB_FEEDS:
        try:
            raw = fetch(feed)
        except (HTTPError, URLError, TimeoutError) as e:
            print(f"OTB feed fail {feed}: {e}", file=sys.stderr)
            continue
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            print(f"OTB XML fail {feed}: {e}", file=sys.stderr)
            continue

        for item in root.findall("./channel/item"):
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            desc = item.findtext("description") or ""
            if year not in title and prev not in title:
                continue
            rec = parse_otb_item(title, desc, link)
            if not rec:
                continue
            key = rec["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(rec)

    return items


def main() -> int:
    existing: dict = {}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("WARN: results.json broken — keep minimal shell", file=sys.stderr)
            existing = {}

    # Критично: сохраняем races[] (Equibase cards/results)
    races = existing.get("races")
    if races is None:
        races = []

    tracks = existing.get("tracks")  # legacy, не обязателен
    flat_results = existing.get("results") or []

    try:
        stakes = fetch_stakes_from_otb()
        if not stakes:
            stakes = existing.get("stakes_results") or []
            print("OTB empty — keep previous stakes_results", file=sys.stderr)
    except Exception as e:
        print(f"OTB failed: {e}", file=sys.stderr)
        stakes = existing.get("stakes_results") or []

    # Не затираем date/source от equibase, если races уже есть
    payload = dict(existing)  # все прежние ключи
    payload["stakes_results"] = stakes
    payload["results"] = flat_results
    payload["races"] = races
    if tracks is not None:
        payload["tracks"] = tracks

    # updated для stakes-слоя — отдельная метка, не ломаем equibase date
    payload["stakes_updated"] = now_et().isoformat()
    if not payload.get("updated"):
        payload["updated"] = payload["stakes_updated"]
    if not payload.get("date"):
        payload["date"] = now_et().strftime("%Y-%m-%d")
    if not payload.get("note"):
        payload["note"] = (
            "races[] — Equibase (cards/results GHA). "
            "stakes_results — OTB RSS. update_results.py не затирает races[]."
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {OUT}: races={len(races)} stakes={len(stakes)} "
        f"(races[] preserved)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
