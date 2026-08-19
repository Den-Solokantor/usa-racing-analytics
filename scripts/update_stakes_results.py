#!/usr/bin/env python3
"""
update_stakes_results.py

Тянет RSS-фид результатов крупных (stakes) скачек с OffTrackBetting.com
и обновляет блок "stakes_results" в data/results.json.

ВАЖНО:
- Этот фид покрывает ТОЛЬКО именные stakes-заезды (Kentucky Derby,
  Preakness, Belmont, Breeders' Cup, Pacific Classic и т.п.), а не
  каждую гонку каждого дня на каждом треке.
- Обычные заезды (races.json / results.json -> "results") по-прежнему
  заполняются вручную, см. README.
- Используется в соответствии с Terms of Use OffTrackBetting.com:
  некоммерческое использование, ссылка на источник обязательна и
  сохраняется в каждой записи (поле "link").

Запуск:
    python scripts/update_stakes_results.py
"""

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

# Берём только записи текущего (или прошлого, на случай начала года) сезона,
# чтобы не тащить весь архив с 2014 года.
CURRENT_YEAR = datetime.now(timezone.utc).year
RELEVANT_YEARS = {str(CURRENT_YEAR), str(CURRENT_YEAR - 1)}


def fetch_rss(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "usa-racing-analytics/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def track_from_link(link: str) -> str:
    # .../horse-racing-results/<track-slug>/<race-slug>.html
    m = re.search(r"/horse-racing-results/([^/]+)/", link)
    if not m:
        return ""
    return m.group(1).replace("-", " ").title()


def parse_title(title: str):
    """
    Пример: '2026 Kentucky Derby Results & Race Replay - Golden Tempo'
    -> race_title='2026 Kentucky Derby', winner='Golden Tempo'
    """
    title = title.strip()
    m = re.match(r"^(.*?)\s+Results?\s*&\s*Race Replay\s*-\s*(.+)$", title)
    if not m:
        return title, ""
    race_title, winner = m.group(1).strip(), m.group(2).strip()
    return race_title, winner


def load_results():
    if RESULTS_PATH.exists():
        with open(RESULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"updated": "", "results": [], "stakes_results": []}


def save_results(data):
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    try:
        xml_text = fetch_rss(RSS_URL)
    except Exception as exc:  # сеть недоступна, фид лёг и т.п.
        print(f"Не удалось получить RSS: {exc}", file=sys.stderr)
        sys.exit(0)  # не роняем workflow из-за временной недоступности источника

    root = ET.fromstring(xml_text)
    items = root.findall("./channel/item")

    data = load_results()
    existing = {r["title"]: r for r in data.get("stakes_results", [])}

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
    data["updated"] = now_iso
    save_results(data)

    print(f"Готово. Новых записей: {added}, обновлено: {updated}, всего stakes: {len(existing)}")


if __name__ == "__main__":
    main()
