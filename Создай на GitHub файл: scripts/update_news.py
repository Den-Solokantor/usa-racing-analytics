#!/usr/bin/env python3
"""
Fetch US horse racing news from RSS, translate to Russian, write data/news.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"

FEEDS = [
    {"name": "TDN", "url": "https://www.thoroughbreddailynews.com/feed/"},
    {"name": "Paulick Report", "url": "https://paulickreport.com/feed/"},
    {"name": "BloodHorse", "url": "https://www.bloodhorse.com/rss/news"},
]

MAX_ITEMS = 10
UA = "USA-Racing-Analytics/1.0 (github-actions news bot)"


def fetch(url: str, timeout: int = 25) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def text_of(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def parse_rss(xml_bytes: bytes, source: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items

    for el in root.iter():
        if local_name(el.tag).lower() not in ("item", "entry"):
            continue
        title = link = summary = pub = ""
        for child in el:
            ln = local_name(child.tag).lower()
            if ln == "title" and not title:
                title = text_of(child)
            elif ln == "link" and not link:
                link = child.attrib.get("href") or text_of(child)
            elif ln in ("description", "summary", "content") and not summary:
                raw = re.sub(r"<[^>]+>", " ", text_of(child))
                summary = re.sub(r"\s+", " ", raw).strip()[:200]
            elif ln in ("pubdate", "published", "updated") and not pub:
                pub = text_of(child)
        if title and link:
            items.append(
                {
                    "title_en": title.strip(),
                    "source": source,
                    "url": link.strip(),
                    "summary_en": summary,
                    "pub": pub,
                }
            )
    return items


def relative_time(pub: str) -> str:
    if not pub:
        return ""
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        mins = int(
            (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
            // 60
        )
        if mins < 1:
            return "только что"
        if mins < 60:
            return f"{mins} мин. назад"
        hours = mins // 60
        if hours < 24:
            return f"{hours} ч. назад"
        days = hours // 24
        return "вчера" if days == 1 else f"{days} дн. назад"
    except Exception:
        return ""


def translate_one(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    # 1) MyMemory
    try:
        url = f"https://api.mymemory.translated.net/get?q={quote(text[:400])}&langpair=en|ru"
        data = json.loads(fetch(url, timeout=15).decode("utf-8", "replace"))
        tr = (data.get("responseData") or {}).get("translatedText") or ""
        if tr and "MYMEMORY WARNING" not in tr.upper() and tr.lower() != text.lower():
            return tr.strip()
    except Exception as e:
        print(f"  MyMemory: {e}", file=sys.stderr)

    # 2) LibreTranslate (best-effort)
    try:
        body = json.dumps(
            {"q": text[:400], "source": "en", "target": "ru", "format": "text"}
        ).encode()
        req = Request(
            "https://libretranslate.com/translate",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": UA},
            method="POST",
        )
        with urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
            tr = data.get("translatedText") or ""
            if tr:
                return tr.strip()
    except Exception as e:
        print(f"  LibreTranslate: {e}", file=sys.stderr)

    return text  # fallback: English


def main() -> int:
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for feed in FEEDS:
        try:
            print(f"Fetch {feed['name']}: {feed['url']}")
            items = parse_rss(fetch(feed["url"]), feed["name"])
            print(f"  -> {len(items)} items")
            for it in items:
                key = it["title_en"].lower().strip()
                if key in seen:
                    continue
                seen.add(key)
                collected.append(it)
        except Exception as e:
            print(f"  skip: {e}", file=sys.stderr)

    collected = collected[:MAX_ITEMS]
    if not collected:
        print("No items — leave existing file", file=sys.stderr)
        return 0

    print(f"Translating {len(collected)} items to Russian...")
    items_out = []
    for i, it in enumerate(collected):
        print(f"  [{i+1}/{len(collected)}] {it['title_en'][:60]}...")
        title_ru = translate_one(it["title_en"])
        time.sleep(0.8)
        summary_ru = (
            translate_one(it.get("summary_en") or "") if it.get("summary_en") else ""
        )
        time.sleep(0.8)
        items_out.append(
            {
                "title": title_ru,
                "title_en": it["title_en"],
                "source": it["source"],
                "url": it["url"],
                "time": relative_time(it.get("pub") or ""),
                "summary": summary_ru,
            }
        )

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "items": items_out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(items_out)} items -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
