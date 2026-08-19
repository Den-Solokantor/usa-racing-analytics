#!/usr/bin/env python3
"""
Обновление data/results.json:
  - tracks[]          — НЕ трогаем (ручной ввод обычных заездов)
  - stakes_results[]  — из RSS OffTrackBetting.com (крупные stakes)
  - results[]         — оставляем как есть (опциональный плоский список)

Без FormFav / Rapid / Equibase.
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
UA = "USA-Racing-Analytics/1.0 (results; +https://solokantorracing.netlify.app)"

# Официальные RSS с https://www.offtrackbetting.com/rss.html
OTB_FEEDS = [
    "https://www.offtrackbetting.com/rss-results-2.0.xml",
    "https://www.offtrackbetting.com/rss-results-1.0.xml",
]


def now_et() -> datetime:
    return datetime.now(ETZ)


def fetch(url: str, timeout: int = 40) -> bytes:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_otb_item(title: str, description: str, link: str) -> dict | None:
    """
    Типичные заголовки OTB:
      "2025 Whitney Stakes Results & Race Replay - Sierra Leone"
      "Alabama Stakes Results - Horse Name"
    """
    t = strip_html(title)
    d = strip_html(description)
    if not t:
        return None

    winner = ""
    # «... Results ... - WinnerName»
    m = re.search(r"(?:Results?|Replay)\s*[-–—:]\s*(.+)$", t, re.I)
    if m:
        winner = m.group(1).strip()
        # убрать хвосты вроде "& Race Replay"
        winner = re.sub(r"\s*&\s*Race\s*Replay.*$", "", winner, flags=re.I).strip()

    race_title = t
    race_title = re.sub(r"\s*Results?.*$", "", race_title, flags=re.I).strip(" -–—")

    track = ""
    # иногда трек в description
    tm = re.search(
        r"\bat\s+([A-Z][A-Za-z0-9 .'\-]+?(?:Park|Course|Downs|Meadows|Field|Coliseum)?)\b",
        d,
    )
    if tm:
        track = tm.group(1).strip()

    if not winner and not race_title:
        return None

    return {
        "track": track,
        "title": race_title or t,
        "winner": winner or "—",
        "link": link or "",
        "status": "official" if winner else "pending",
        "source": "offtrackbetting",
    }


def fetch_stakes_from_otb() -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()

    for feed in OTB_FEEDS:
        try:
            raw = fetch(feed)
            root = ET.fromstring(raw)
        except (HTTPError, URLError, TimeoutError, ET.ParseError) as e:
            print(f"OTB feed skip {feed}: {e}", file=sys.stderr)
            continue

        # RSS 2.0: channel/item
        channel = root.find("channel")
        entries = channel.findall("item") if channel is not None else root.findall("item")
        # Atom fallback
        if not entries:
            ns = {"a": "http://www.w3.org/2005/Atom"}
            entries = root.findall("a:entry", ns)

        for el in entries:
            title = (el.findtext("title") or "").strip()
            link = (el.findtext("link") or "").strip()
            if not link:
                link_el = el.find("link")
                if link_el is not None:
                    link = (link_el.get("href") or "").strip()
            desc = (el.findtext("description") or el.findtext("{http://www.w3.org/2005/Atom}summary") or "").strip()

            parsed = parse_otb_item(title, desc, link)
            if not parsed:
                continue
            key = (parsed.get("title") or "") + "|" + (parsed.get("winner") or "")
            if key in seen:
                continue
            seen.add(key)
            items.append(parsed)

        if items:
            print(f"OTB: {len(items)} stakes from {feed}")
            break

    return items[:40]


def seasonal_tracks(day: datetime) -> list[dict]:
    """Только если tracks пустой — шаблон сезона (pending)."""
    month = day.month
    if month in (7, 8, 9):
        names = [("Saratoga", "SAR"), ("Del Mar", "DMR"), ("Monmouth Park", "MTH")]
    elif month in (10, 11):
        names = [("Keeneland", "KEE"), ("Santa Anita", "SA"), ("Belmont at Aqueduct", "BAQ")]
    elif month in (12, 1, 2, 3):
        names = [("Gulfstream Park", "GP"), ("Santa Anita", "SA"), ("Aqueduct", "AQU")]
    else:
        names = [("Keeneland", "KEE"), ("Churchill Downs", "CD"), ("Santa Anita", "SA")]

    out = []
    for name, code in names:
        out.append({
            "track": name,
            "code": code,
            "races": [
                {
                    "race": n,
                    "title": "",
                    "winner": "— ожидание —",
                    "jockey": "",
                    "trainer": "",
                    "odds": "",
                    "margin": "",
                    "status": "pending",
                }
                for n in range(1, 10)
            ],
        })
    return out


def main() -> int:
    day = now_et()
    existing: dict = {}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("WARN: results.json broken — rebuild", file=sys.stderr)
            existing = {}

    # Ручные данные сохраняем
    tracks = existing.get("tracks") or []
    flat_results = existing.get("results") or []
    if not tracks:
        tracks = seasonal_tracks(day)
        print("tracks empty → seasonal template")

    stakes: list[dict] = []
    source = "manual"
    note = "Обычные заезды — вручную в tracks. Stakes — OTB RSS (если доступен)."

    try:
        stakes = fetch_stakes_from_otb()
        if stakes:
            source = "manual+otb-rss"
            note = "Обычные заезды — вручную. Крупные stakes — RSS OffTrackBetting.com."
        else:
            # не затираем старые stakes, если RSS пустой/403
            stakes = existing.get("stakes_results") or []
            print("OTB empty — keep previous stakes_results", file=sys.stderr)
    except Exception as e:
        print(f"OTB failed: {e}", file=sys.stderr)
        stakes = existing.get("stakes_results") or []

    payload = {
        "updated": now_et().isoformat(),
        "date": day.strftime("%Y-%m-%d"),
        "source": source,
        "note": note,
        "results": flat_results,
        "stakes_results": stakes,
        "tracks": tracks,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} source={source} tracks={len(tracks)} stakes={len(stakes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
