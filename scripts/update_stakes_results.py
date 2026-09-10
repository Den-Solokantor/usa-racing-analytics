#!/usr/bin/env python3
"""
Тянет RSS stakes с OffTrackBetting.com → data/results.json["stakes_results"].

НЕ затирает races[] / place / equibase-поля.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

RSS_URL = "https://www.offtrackbetting.com/rss-results-2.0.xml"
RESULTS_PATH = Path(__file__).resolve().parent.parent / "data" / "results.json"
SOURCE_NAME = "offtrackbetting.com"
CURRENT_YEAR = datetime.now(timezone.utc).year
RELEVANT_YEARS = {str(CURRENT_YEAR), str(CURRENT_YEAR - 1)}


def fetch_rss(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "usa-racing-analytics/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def track_from_link(link: str) -> str:
    m = re.search(r"/horse-racing-results/([^/]+)/", link)
    if not m:
        return ""
    return m.group(1).replace("-", " ").title()


def parse_title(title: str):
    title = title.strip()
    m = re.match(r"^(.*?)\s+Results?\s*&\s*Race Replay\s*-\s*(.+)$", title)
    if not m:
        return title, ""
    return m.group(1).strip(), m.group(2).strip()


def load_results() -> dict:
    if RESULTS_PATH.exists():
        with open(RESULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"updated": "", "results": [], "stakes_results": [], "races": []}


def save_results(data: dict) -> None:
    # Гарантия: races всегда ключ-список
    if data.get("races") is None:
        data["races"] = []
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> None:
    try:
        xml_text = fetch_rss(RSS_URL)
    except Exception as exc:
        print(f"Не удалось получить RSS: {exc}", file=sys.stderr)
        sys.exit(0)

    root = ET.fromstring(xml_text)
    items = root.findall("./channel/item")

    data = load_results()
    # не трогаем races
    races_backup = data.get("races")
    if races_backup is None:
        races_backup = []

    existing = {r["title"]: r for r in data.get("stakes_results", []) if r.get("title")}
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    added, updated = 0, 0

    for item in items:
        raw_title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not raw_title or not link:
            continue
        year_match = re.match(r"^(\d{4})", raw_title)
        if not year_match or year_match.group(1) not in RELEVANT_YEARS:
            continue
        race_title, winner = parse_title(raw_title)
        if not winner:
            continue
        record = {
            "title": race_title,
            "track": track_from_link(link),
            "winner": winner,
            "link": link,
            "source": SOURCE_NAME,
            "fetched": now_iso,
        }
        if race_title in existing:
            if existing[race_title].get("winner") != winner:
                existing[race_title] = record
                updated += 1
        else:
            existing[race_title] = record
            added += 1

    data["stakes_results"] = list(existing.values())
    data["stakes_updated"] = now_iso
    data["races"] = races_backup  # явно сохраняем
    save_results(data)
    print(
        f"Готово. Новых: {added}, обновлено: {updated}, stakes: {len(existing)}, "
        f"races[] сохранён: {len(races_backup)}"
    )


if __name__ == "__main__":
    main()
