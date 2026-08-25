#!/usr/bin/env python3
"""
Парсер tips → data/tips.json

Источники:
  - Tipmeerkat (основные top picks по трекам USA)
  - GetYourTipsOut (ссылки на дневные American tips)

Не путать с официальными results (place 1/2/3).

Запуск:
  pip install httpx
  python scripts/update_tips.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

try:
    import httpx
except ImportError:
    sys.exit("pip install httpx")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "tips.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

TIPMEERKAT_INDEX = "https://tipmeerkat.com/latest-tips-picks"
GYTO_US = "https://www.getyourtipsout.co.uk/american-horse-racing-tips/"

# только США (по addressCountry / url slug)
US_SLUG_HINTS = (
    "louisiana-downs", "parx", "thistledown", "finger-lakes", "indianapolis",
    "fairmount", "gulfstream", "saratoga", "del-mar", "monmouth", "colonial",
    "ellis", "laurel", "penn-national", "mountaineer", "prairie", "canterbury",
    "albuquerque", "remington", "horseshoe", "belterra", "charles-town",
    "presque-isle", "meadowlands", "tampa", "santa-anita", "churchill",
)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
        follow_redirects=True,
        timeout=35,
    )


def extract_jsonld(html: str) -> list[Any]:
    out = []
    for block in re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    ):
        try:
            out.append(json.loads(block))
        except json.JSONDecodeError:
            continue
    return out


def tipmeerkat_meetings(c: httpx.Client, day: str) -> list[dict]:
    """Список USA meetings на дату из index JSON-LD."""
    try:
        r = c.get(TIPMEERKAT_INDEX)
        r.raise_for_status()
    except Exception as e:
        log(f"Tipmeerkat index: {e}")
        return []

    meetings = []
    for data in extract_jsonld(r.text):
        if not isinstance(data, dict) or data.get("@type") != "ItemList":
            continue
        for el in data.get("itemListElement") or []:
            item = el.get("item") if isinstance(el, dict) else None
            if not isinstance(item, dict):
                continue
            loc = item.get("location") or {}
            addr = loc.get("address") or {}
            country = (addr.get("addressCountry") or "").upper()
            url = item.get("url") or ""
            name = (loc.get("name") or item.get("name") or "").strip()
            start = (item.get("startDate") or "")[:10]
            if start and start != day:
                continue
            is_us = country in {"US", "USA", "UNITED STATES"} or any(
                h in url.lower() for h in US_SLUG_HINTS
            )
            if not is_us:
                continue
            meetings.append({"track": name, "url": url, "date": start or day})
    # unique by url
    seen = set()
    uniq = []
    for m in meetings:
        if m["url"] in seen:
            continue
        seen.add(m["url"])
        uniq.append(m)
    log(f"Tipmeerkat: {len(uniq)} USA meetings on {day}")
    return uniq


_TOP_PICK_RE = re.compile(
    r"Top pick:\s*#?\s*(\d+)\s+([A-Za-z0-9][A-Za-z0-9'\.\- ]{1,50})",
    re.I,
)
_RACE_SPLIT_RE = re.compile(r"(?i)(?:^|>|\n)\s*Race\s+(\d+)\b")


def parse_tipmeerkat_track(html: str, track: str, url: str, day: str) -> list[dict]:
    """Достаёт top picks с страницы трека."""
    tips = []
    # убираем scripts
    clean = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    clean = re.sub(r"<style[^>]*>.*?</style>", " ", clean, flags=re.I | re.S)

    # пробуем привязать к Race N по близости в тексте
    # упрощённо: ищем все Top pick, race_no = порядковый / из соседнего Race N
    text = re.sub(r"<[^>]+>", "\n", clean)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    current_race: Optional[int] = None
    seen_picks = set()
    for ln in lines:
        rm = re.match(r"(?i)^Race\s+(\d+)\b", ln)
        if rm:
            current_race = int(rm.group(1))
            continue
        m = _TOP_PICK_RE.search(ln)
        if not m:
            continue
        post = int(m.group(1))
        horse = m.group(2).strip(" .-")
        key = (current_race, post, horse.lower())
        if key in seen_picks:
            continue
        seen_picks.add(key)
        tips.append(
            {
                "source": "tipmeerkat",
                "track": track,
                "date": day,
                "race": current_race,
                "post": post,
                "horse": horse,
                "role": "top_pick",
                "url": url,
            }
        )
    return tips


def fetch_tipmeerkat(c: httpx.Client, day: str, max_tracks: int = 12) -> list[dict]:
    meetings = tipmeerkat_meetings(c, day)
    all_tips: list[dict] = []
    for i, m in enumerate(meetings[:max_tracks]):
        url = m["url"]
        try:
            r = c.get(url)
            if r.status_code != 200 or len(r.text) < 2000:
                log(f"  skip {m['track']}: HTTP {r.status_code}")
                continue
            tips = parse_tipmeerkat_track(r.text, m["track"], url, day)
            log(f"  {m['track']}: {len(tips)} top picks")
            all_tips.extend(tips)
        except Exception as e:
            log(f"  {m['track']}: {e}")
    return all_tips


def fetch_gyto_links(c: httpx.Client) -> list[dict]:
    """Ссылки на дневные American tips (без разбора платного текста)."""
    try:
        r = c.get(GYTO_US)
        r.raise_for_status()
    except Exception as e:
        log(f"GYTO: {e}")
        return []

    items = []
    for href, title in re.findall(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', r.text, flags=re.I | re.S
    ):
        title = re.sub(r"<[^>]+>", "", title)
        title = re.sub(r"\s+", " ", title).strip()
        if not title or len(title) < 12:
            continue
        if not re.search(r"american|stateside|gulfstream|tampa|usa", title, re.I):
            continue
        if not re.search(r"tip", title, re.I):
            continue
        full = urljoin(GYTO_US, href)
        items.append(
            {
                "source": "getyourtipsout",
                "title": title,
                "url": full,
                "role": "article",
            }
        )
    # unique
    seen = set()
    out = []
    for it in items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        out.append(it)
    log(f"GYTO: {len(out)} article links")
    return out[:15]


def main() -> None:
    day = date.today().isoformat()
    log(f"Tips for {day}")

    with client() as c:
        tips = fetch_tipmeerkat(c, day)
        articles = fetch_gyto_links(c)

    payload = {
        "updated": datetime.now(timezone.utc).astimezone().isoformat(),
        "date": day,
        "source": "tipmeerkat+gyto",
        "note": (
            "Это прогнозы (tips), не официальные results. "
            "Сверка с place — после set_places / chart."
        ),
        "tips": tips,
        "articles": articles,
        "stats": {
            "tips": len(tips),
            "articles": len(articles),
            "tracks": len({t.get("track") for t in tips if t.get("track")}),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"Wrote {OUT} ({len(tips)} tips, {len(articles)} articles)")


if __name__ == "__main__":
    main()
