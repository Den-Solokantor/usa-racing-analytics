#!/usr/bin/env python3
"""
Equibase (USA) парсер — cards / live / results + автозалив на сайт.

Режимы:
  cards   — статические карды + ML через httpx (без браузера).
  live    — tote через Playwright.
  results — place 1/2/3 из ESPN Equibase quick-results (httpx).

Примеры:
  python equibase_live_odds.py --mode cards --push --site-repo ~/usa-racing-analytics
  python equibase_live_odds.py --mode results --date 2026-09-03 --track BTP \\
      --races-json ~/usa-racing-analytics/data/results.json
  python equibase_live_odds.py --mode results --date 2026-09-03 --auto \\
      --races-json ~/usa-racing-analytics/data/results.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    from zoneinfo import ZoneInfo

    _ET = ZoneInfo("America/New_York")
except Exception:
    _ET = None

OUT_COLS = (
    "track",
    "race",
    "post",
    "horse",
    "morning_line",
    "win_odds",
    "place_odds",
    "show_odds",
    "post_time",
    "finished",
    "source",
    "timestamp",
)

TRACK_NAMES: dict[str, str] = {
    "SAR": "Saratoga",
    "BEL": "Belmont",
    "AQU": "Aqueduct",
    "BAQ": "Belmont at Aqueduct",
    "CD": "Churchill Downs",
    "DMR": "Del Mar",
    "SA": "Santa Anita",
    "GP": "Gulfstream Park",
    "GPW": "Gulfstream Park West",
    "OP": "Oaklawn Park",
    "KEE": "Keeneland",
    "CT": "Charles Town",
    "CNL": "Colonial Downs",
    "MTH": "Monmouth Park",
    "WO": "Woodbine",
    "PRX": "Parx Racing",
    "TAM": "Tampa Bay Downs",
    "FG": "Fair Grounds",
    "LRL": "Laurel Park",
    "PIM": "Pimlico",
    "TUP": "Turf Paradise",
    "GG": "Golden Gate Fields",
    "EMD": "Emerald Downs",
    "CBY": "Canterbury Park",
    "DEL": "Delaware Park",
    "ELP": "Ellis Park",
    "FL": "Finger Lakes",
    "HAW": "Hawthorne",
    "IND": "Horseshoe Indianapolis",
    "LS": "Lone Star Park",
    "MVR": "Mahoning Valley",
    "PEN": "Penn National",
    "PHA": "Parx (Philadelphia Park)",
    "RUI": "Ruidoso Downs",
    "SUF": "Suffolk Downs",
    "TDN": "Thistledown",
    "TP": "Turfway Park",
    "ZIA": "Zia Park",
    "BTP": "Belterra Park",
    "ALB": "Albuquerque",
    "CAS": "Casino at the Downs",
    "ATO": "Atokad Downs",
}

TRACK_NAME_TO_CODE: dict[str, str] = {v: k for k, v in TRACK_NAMES.items()}
TRACK_NAME_TO_CODE.update(
    {
        "Belterra Park": "BTP",
        "Saratoga": "SAR",
        "Del Mar": "DMR",
        "Belmont": "BEL",
        "Belmont at Aqueduct": "BAQ",
        "Churchill Downs": "CD",
        "Gulfstream Park": "GP",
        "Santa Anita": "SA",
        "Charles Town": "CT",
        "Laurel Park": "LRL",
        "Monmouth Park": "MTH",
        "Colonial Downs": "CNL",
        "Ellis Park": "ELP",
        "Canterbury Park": "CBY",
        "Albuquerque": "ALB",
        "Parx Racing": "PRX",
        "Thistledown": "TDN",
        "Finger Lakes": "FL",
        "Horseshoe Indianapolis": "IND",
        "Penn National": "PEN",
        "Indiana Grand": "IND",
        "Atokad Downs": "ATO",
        "ATO": "ATO",
    }
)


def check_hardware() -> None:
    ram_mb = 0
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    ram_mb = int(line.split()[1]) // 1024
                    break
    except OSError:
        pass
    cpu_flags = ""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("flags"):
                    cpu_flags = line.split(":", 1)[1].lower()
                    break
    except OSError:
        pass
    print(
        f"RAM: {ram_mb} МБ | CPU flags: ssse3={'ssse3' in cpu_flags} "
        f"sse4_2={'sse4_2' in cpu_flags}"
    )
    if ram_mb and ram_mb < 3000:
        print("⚠ Мало ОЗУ (<3 ГБ): для live закрой браузеры. cards/results — ок.")


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


def pick_value(obj: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        v = obj.get(k, default)
        if v not in (None, "", "-"):
            return v
    return default


def track_display_name(code: str) -> str:
    return TRACK_NAMES.get((code or "").upper(), code)


def resolve_track_code(name_or_code: str) -> str:
    s = (name_or_code or "").strip()
    if not s:
        return ""
    if s.upper() in TRACK_NAMES:
        return s.upper()
    if s in TRACK_NAME_TO_CODE:
        return TRACK_NAME_TO_CODE[s]
    # partial match
    low = s.lower()
    for name, code in TRACK_NAME_TO_CODE.items():
        if low == name.lower() or low in name.lower():
            return code
    return s.upper()


_POST_TIME_RE = re.compile(
    r"POST\s*Time\s*-\s*(\d{1,2}):(\d{2})\s*([AP])\.?M\.?\s*ET", re.I
)
_PURSE_DIST_RE = re.compile(r"Purse\s*\$([\d,]+)\.\s*([^.]+?)\.")


def parse_post_time(
    section_text: str, race_date: str
) -> tuple[Optional[str], Optional[datetime]]:
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


def parse_purse_distance(section_text: str) -> tuple[Optional[str], Optional[str]]:
    m = _PURSE_DIST_RE.search(section_text)
    if not m:
        return None, None
    return f"Purse ${m.group(1)}", m.group(2).strip()


def _cell(v: Any, width: int = 12) -> str:
    if v is None:
        return "".rjust(width)
    if isinstance(v, float):
        s = f"{v:.2f}"
    else:
        s = str(v)
    if len(s) > width:
        s = s[: width - 1] + "~"
    return s.ljust(width)


def print_odds(odds: list[dict]) -> None:
    if not odds:
        print("(пусто — данные не получены)")
        return
    header = (
        "track",
        "race",
        "post",
        "horse",
        "ML",
        "win",
        "place",
        "show",
        "timestamp",
    )
    widths = {
        "track": 10,
        "race": 4,
        "post": 4,
        "horse": 22,
        "ML": 8,
        "win": 8,
        "place": 8,
        "show": 8,
        "timestamp": 24,
    }
    print(" ".join(_cell(h, widths[h]) for h in header))
    for r in odds:
        row = {
            "track": r.get("track", ""),
            "race": r.get("race", 0),
            "post": r.get("post", r.get("program", 0)),
            "horse": r.get("horse", ""),
            "ML": r.get("morning_line"),
            "win": r.get("win_odds"),
            "place": r.get("place_odds"),
            "show": r.get("show_odds"),
            "timestamp": (r.get("timestamp") or "")[:19],
        }
        print(" ".join(_cell(row[h], widths[h]) for h in header))


def write_csv(path: str, odds: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS, extrasaction="ignore")
        w.writeheader()
        for r in odds:
            w.writerow(r)
    print(f"CSV: {path} ({len(odds)} строк)")


# ---------------------------------------------------------------------------
# JSON для сайта
# ---------------------------------------------------------------------------
def odds_to_races_json(
    odds: list[dict], race_date: str, hide_finished: bool = False
) -> dict:
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
            horses_raw,
            key=lambda h: int(h.get("post") or h.get("program") or 0),
        )
        first = horses_sorted[0] if horses_sorted else {}
        post_time = first.get("post_time") or ""
        finished = first.get("finished")
        purse = first.get("purse") or ""
        distance = first.get("distance") or ""
        if finished and hide_finished:
            continue

        horses = []
        for h in horses_sorted:
            name = (h.get("horse") or "").strip()
            if not name:
                continue
            ml = h.get("morning_line")
            wo = h.get("win_odds")
            src = h.get("source") or ""
            is_live = bool(wo is not None and not str(src).startswith("static"))
            horses.append(
                {
                    "post": int(h.get("post") or h.get("program") or 0),
                    "name": name,
                    "ml": ml,
                    "win": wo if is_live else None,
                }
            )

        has_live = any(x.get("win") is not None for x in horses)
        tags = ["USA", "Equibase", "ML"]
        tags.append("Live odds" if has_live else "ML estimate")
        if finished:
            tags.append("Finished")

        races.append(
            {
                "id": f"{tr.lower()}-{date_compact[4:]}-{rn}",
                "track": track_display_name(tr),
                "time": post_time,
                "title": f"Race {rn}",
                "distance": distance,
                "purse": purse,
                "horses": horses,
                "preview": "",
                "tags": tags,
            }
        )

    return {
        "updated": datetime.now(timezone.utc).astimezone().isoformat(),
        "source": "equibase-parser",
        "date": race_date,
        "races": races[:40],
    }


def races_to_results_json(
    races_payload: dict,
    existing_results: Optional[dict] = None,
) -> dict:
    existing = existing_results or {}
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
        rid = race.get("id")
        old = old_by_id.get(rid) or {}
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
            place = h.get("place")
            if place is None:
                place = prev.get("place")
            new_horses.append(
                {
                    "post": h.get("post"),
                    "name": h.get("name"),
                    "ml": h.get("ml"),
                    "place": place,
                    **(
                        {"mutuel_win": h["mutuel_win"]}
                        if h.get("mutuel_win") is not None
                        else (
                            {"mutuel_win": prev["mutuel_win"]}
                            if prev.get("mutuel_win") is not None
                            else {}
                        )
                    ),
                }
            )

        has_places = any(h.get("place") is not None for h in new_horses)
        status = "official" if has_places else "pending"
        finished = "Finished" in (race.get("tags") or [])

        out_races.append(
            {
                "id": race.get("id"),
                "track": race.get("track"),
                "time": race.get("time") or "",
                "title": race.get("title") or "",
                "distance": race.get("distance") or "",
                "purse": race.get("purse") or "",
                "status": status,
                "tags": ["USA", "Result"] + (["Finished"] if finished else []),
                "horses": new_horses,
            }
        )

    return {
        "updated": datetime.now(timezone.utc).astimezone().isoformat(),
        "date": races_payload.get("date"),
        "source": existing.get("source") or "manual+cards",
        "note": (
            "Состав как в «Сегодня». place — из Equibase quick-results "
            "или set_places / --mode results."
        ),
        "results": [],
        "stakes_results": existing.get("stakes_results") or [],
        "races": out_races,
    }


def push_to_site_repo(repo: Path, races_payload: dict) -> None:
    repo = repo.expanduser().resolve()
    if not repo.is_dir():
        raise SystemExit(f"Нет каталога репо: {repo}")

    data_dir = repo / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    races_path = data_dir / "races.json"
    races_path.write_text(
        json.dumps(races_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Сайт: {races_path} ({len(races_payload.get('races') or [])} гонок)")

    results_path = data_dir / "results.json"
    existing_results: dict = {}
    if results_path.exists():
        try:
            existing_results = json.loads(results_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("WARN: results.json битый — пересоздаём", file=sys.stderr)
            existing_results = {}

    results_payload = races_to_results_json(races_payload, existing_results)
    results_path.write_text(
        json.dumps(results_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Сайт: {results_path} "
        f"({len(results_payload.get('races') or [])} гонок в results)"
    )

    def run(cmd: list[str]) -> None:
        print("+", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=str(repo), check=True)

    run(["git", "add", "data/races.json", "data/results.json"])
    st = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=str(repo))
    if st.returncode == 0:
        print("Сайт: нет изменений для commit")
        return

    msg = f"chore: equibase cards+results {races_payload.get('date', '')}".strip()
    run(["git", "commit", "-m", msg])
    run(["git", "pull", "--rebase", "origin", "main"])
    run(["git", "push", "origin", "main"])
    print("Сайт: push OK — Netlify обновит через 1–2 мин")


def maybe_push(args: argparse.Namespace, odds: list[dict]) -> None:
    if not args.push:
        return
    if not odds:
        print("Push: нет данных — пропуск")
        return
    if not args.site_repo:
        sys.exit("Укажи --site-repo /path/to/usa-racing-analytics")
    payload = odds_to_races_json(
        odds, args.date, hide_finished=getattr(args, "hide_finished", False)
    )
    Path("races_for_site.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Локально: races_for_site.json")
    push_to_site_repo(Path(args.site_repo), races_payload=payload)


# ---------------------------------------------------------------------------
# Режим cards
# ---------------------------------------------------------------------------
class EquibaseStaticCards:
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
    BASE = "https://tvg.equibase.com/static/entry"

    def __init__(self, verbose: bool = True):
        try:
            import httpx
        except ImportError:
            sys.exit("Нужен httpx: pip install httpx")
        self._client = httpx.Client(
            headers={
                "User-Agent": self.UA,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                ),
            },
            follow_redirects=True,
            timeout=30,
        )
        self._verbose = verbose

    def _log(self, msg: str) -> None:
        if self._verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

    def tracks_for_date(self, race_date: str) -> list[str]:
        y, m, d = race_date.split("-")
        mdy = f"{m}{d}{y[2:]}"
        try:
            r = self._client.get(f"{self.BASE}/")
        except Exception as e:
            self._log(f"Индекс: ошибка {e}")
            return []
        if r.status_code != 200:
            self._log(f"Индекс -> HTTP {r.status_code}")
            return []
        found = re.findall(
            rf"(?:entry/|Index)([A-Z]{{2,4}}){mdy}(?:USA|CAN|PR)?-?EQB\.html",
            r.text,
            flags=re.I,
        )
        tracks = sorted({t.upper() for t in found})
        self._log(
            f"Индекс: треков на {race_date}: {len(tracks)} "
            f"{tracks[:12]}{'...' if len(tracks) > 12 else ''}"
        )
        return tracks

    def parse_entry_page(
        self,
        html: str,
        track: str,
        race_date: str,
        ml_as_win_fallback: bool = True,
    ) -> list[dict]:
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
            rows = re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", section)
            for row in rows:
                tds = re.findall(r"(?is)<td[^>]*>(.*?)</td>", row)
                texts = [" ".join(re.sub(r"<[^>]+>", " ", t).split()) for t in tds]
                if not texts:
                    continue
                joined = " ".join(texts).upper()
                if "SCRATCH" in joined or texts[0].upper().replace(
                    "&NBSP;", ""
                ).strip() in {"SCR", "SCRATCHED"}:
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
                    if cand and re.match(
                        r"^\d+/\d+$|^\d+\.\d+$|evens?", cand, re.I
                    ):
                        ml_raw = cand
                        break
                ml_value = frac_to_decimal(ml_raw)
                use_fallback = ml_as_win_fallback and ml_value is not None
                out.append(
                    {
                        "track": track,
                        "race": race_no,
                        "post": int(post_s),
                        "horse": horse,
                        "morning_line": ml_value,
                        "win_odds": ml_value if use_fallback else None,
                        "place_odds": None,
                        "show_odds": None,
                        "post_time": post_time_label,
                        "finished": finished,
                        "purse": purse,
                        "distance": distance,
                        "source": "static_ml_estimate" if use_fallback else "static",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
            i += 2
        return out

    def racecards(
        self, race_date: str, track: str = "", ml_as_win_fallback: bool = True
    ) -> list[dict]:
        y, m, d = race_date.split("-")
        mdy = f"{m}{d}{y[2:]}"
        tracks = [track.upper()] if track else self.tracks_for_date(race_date)
        all_rows: list[dict] = []
        for tr in tracks:
            url = f"{self.BASE}/{tr}{mdy}USA-EQB.html"
            try:
                r = self._client.get(url)
            except Exception as e:
                self._log(f"{url}: ошибка {e}")
                continue
            if r.status_code != 200:
                self._log(f"{tr}: HTTP {r.status_code}")
                continue
            if len(r.text) < 5000:
                self._log(
                    f"{tr}: слишком короткий ответ ({len(r.text)} B) — challenge?"
                )
                continue
            rows = self.parse_entry_page(
                r.text, tr, race_date, ml_as_win_fallback=ml_as_win_fallback
            )
            self._log(f"{tr}: {len(rows)} лошадей")
            all_rows.extend(rows)
        return all_rows

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# Live odds (Playwright)
# ---------------------------------------------------------------------------
class EquibaseLiveOdds:
    HORSE_KEYS = ("horseName", "horse_name", "name", "Name", "horse", "runnerName")
    ODDS_KEYS = (
        "currentOdds",
        "winOdds",
        "win_odds",
        "odds",
        "Odds",
        "winPayoff",
        "currentPrice",
        "morningLineOdds",
    )
    POST_KEYS = ("program", "postPosition", "post", "programNumber", "number", "pp")
    RACE_KEYS = ("raceNumber", "race_number", "raceNum", "race", "number")
    TRACK_KEYS = ("trackName", "track_name", "track", "trackCode", "raceTrack")
    BLOCK_RESOURCE_TYPES = {"image", "media", "font"}
    BLOCK_URL_PATTERNS = (
        ".css",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".woff",
        ".woff2",
        ".ttf",
        ".mp4",
        ".svg",
    )

    def __init__(
        self,
        headless: bool = True,
        stealth: bool = True,
        verbose: bool = True,
        debug: bool = False,
        browser_name: str = "chromium",
    ):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            sys.exit(
                "Нужен playwright: pip install playwright && playwright install chromium"
            )
        self._pw = sync_playwright().start()
        self._headless = headless
        self._stealth = stealth
        self._verbose = verbose
        self._debug = debug
        self._browser_name = browser_name
        self._browser = None
        self._context = None
        self._captured: list[dict] = []
        self._json_count = 0

    def _log(self, msg: str) -> None:
        if self._verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

    def _apply_stealth(self) -> None:
        if not self._stealth:
            return
        try:
            from playwright_stealth import Stealth

            Stealth().apply_stealth_sync(self._context)
            self._log("stealth применён")
            return
        except Exception:
            pass
        try:
            from playwright_stealth import stealth_sync

            stealth_sync(self._context)
            self._log("stealth 1.x применён")
        except Exception:
            self._log("stealth недоступен (не критично)")

    def _looks_like_odds_payload(self, data: Any) -> bool:
        if isinstance(data, dict):
            keys = set(data.keys())
            if any(k in keys for k in self.HORSE_KEYS) and any(
                k in keys for k in self.ODDS_KEYS
            ):
                return True
            if any(k in keys for k in ("runners", "entries", "starters", "horses")):
                for v in data.values():
                    if self._looks_like_odds_payload(v):
                        return True
            return any(self._looks_like_odds_payload(v) for v in data.values())
        if isinstance(data, list):
            return any(self._looks_like_odds_payload(v) for v in data)
        return False

    def _extract_runners(
        self, data: Any, race_no: Optional[int] = None, track: str = ""
    ) -> Iterable[dict]:
        if isinstance(data, dict):
            rn = pick_value(data, *self.RACE_KEYS)
            if isinstance(rn, (int, float)) and not isinstance(rn, bool):
                race_no = int(rn)
            tk = pick_value(data, *self.TRACK_KEYS)
            if tk:
                track = str(tk)
            horse = pick_value(data, *self.HORSE_KEYS)
            odds = pick_value(data, *self.ODDS_KEYS)
            if horse and odds is not None:
                yield {
                    "track": track,
                    "race": race_no or 0,
                    "post": pick_value(data, *self.POST_KEYS, default=0),
                    "horse": str(horse),
                    "morning_line": frac_to_decimal(
                        pick_value(data, "morningLine", "morning_line", "ml")
                    ),
                    "win_odds": frac_to_decimal(odds),
                    "place_odds": frac_to_decimal(
                        pick_value(data, "placeOdds", "place_odds", "place")
                    ),
                    "show_odds": frac_to_decimal(
                        pick_value(data, "showOdds", "show_odds", "show")
                    ),
                }
            for v in data.values():
                yield from self._extract_runners(v, race_no, track)
        elif isinstance(data, list):
            for v in data:
                yield from self._extract_runners(v, race_no, track)

    def _on_response(self, response) -> None:
        url = response.url
        ctype = response.headers.get("content-type", "")
        try:
            body = response.body()
        except Exception:
            body = b""
        if "json" not in ctype and not re.search(
            r"\.json|/api/|odds|program|entries", url
        ):
            return
        if not body:
            return
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except Exception:
            return
        if self._looks_like_odds_payload(data):
            runners = list(self._extract_runners(data))
            if runners:
                self._captured.append(
                    {
                        "url": url,
                        "time": datetime.now(timezone.utc).isoformat(),
                        "runners": runners,
                    }
                )
                self._log(f"Кэфы пойманы: {url} ({len(runners)} лошадей)")

    def _ensure_browser(self) -> None:
        if self._browser:
            return
        launcher = getattr(self._pw, self._browser_name)
        self._browser = launcher.launch(
            headless=self._headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-extensions",
            ],
        )
        self._context = self._browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            viewport={"width": 1024, "height": 768},
        )
        self._apply_stealth()

    def _block_heavy(self, route) -> None:
        try:
            rtype = route.request.resource_type
            if rtype in self.BLOCK_RESOURCE_TYPES:
                route.abort()
                return
            url = route.request.url.lower()
            if any(p in url for p in self.BLOCK_URL_PATTERNS):
                route.abort()
                return
        except Exception:
            pass
        route.continue_()

    def _page(self, url: str, settle_seconds: float = 10.0):
        self._ensure_browser()
        page = self._context.new_page()
        page.on("response", self._on_response)
        page.route("**/*", self._block_heavy)
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self._log(f"Открываю: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        except Exception as e:
            self._log(f"goto: {e}")
        page.wait_for_timeout(int(settle_seconds * 1000))
        return page

    def live_odds(
        self, race_date: Optional[str] = None, track: str = ""
    ) -> list[dict]:
        self._captured.clear()
        if race_date is None:
            race_date = date.today().isoformat()
        url = f"https://www.equibase.com/entries/{race_date}"
        if track:
            url += f"/{track.upper()}"
        page = self._page(url)
        if not self._captured:
            self._log("XHR пуст — DOM fallback")
            self._captured.extend(self._parse_odds_tables(page))
        page.close()
        odds = self._merge_captured()
        if track:
            f = track.upper()
            odds = [o for o in odds if f in (o["track"] or "").upper()]
        return odds

    def _parse_odds_tables(self, page) -> list[dict]:
        found: list[dict] = []
        rows = page.query_selector_all("table tr, [class*=runner], [class*=horse]")
        for row in rows:
            tds = row.query_selector_all("td")
            texts = [td.inner_text().strip() for td in tds]
            if len(texts) < 4:
                continue
            win = frac_to_decimal(texts[3]) if len(texts) > 3 else None
            if win is None:
                continue
            found.append(
                {
                    "url": page.url,
                    "time": datetime.now(timezone.utc).isoformat(),
                    "runners": [
                        {
                            "track": "",
                            "race": 0,
                            "post": texts[0],
                            "horse": texts[1],
                            "win_odds": win,
                        }
                    ],
                }
            )
        return found

    def _merge_captured(self) -> list[dict]:
        merged: dict[tuple, dict] = {}
        for blob in self._captured:
            ts = blob["time"]
            for r in blob["runners"]:
                if not r.get("horse"):
                    continue
                key = (
                    r.get("track") or "",
                    r.get("race") or 0,
                    r.get("post") or 0,
                    r["horse"],
                )
                rec = merged.get(key)
                if rec is None:
                    rec = dict(r)
                    rec["source"] = blob["url"]
                    rec["timestamp"] = ts
                    merged[key] = rec
                else:
                    if r.get("win_odds") is not None:
                        rec["win_odds"] = r["win_odds"]
                        rec["source"] = blob["url"]
                        rec["timestamp"] = ts
        return list(merged.values())

    def close(self) -> None:
        if self._browser:
            self._browser.close()
        self._pw.stop()


# ---------------------------------------------------------------------------
# Режим results — place 1/2/3 из ESPN Equibase quick-results
# ---------------------------------------------------------------------------
def mdy_slash(race_date: str) -> str:
    """2026-09-03 -> 09/03/2026"""
    y, m, d = race_date.split("-")
    return f"{m}/{d}/{y}"


def _norm_horse(name: str) -> str:
    """Нормализация имени для сопоставления."""
    s = (name or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _html_to_lines(html: str) -> list[str]:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</tr>", "\n", text, flags=re.I)
    text = re.sub(r"</(p|div|h[1-6]|li|td|th)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]


def _parse_order_of_finish(lines: list[str]) -> list[str]:
    """Имена в порядке финиша (1-й, 2-й, 3-й…)."""
    stop = re.compile(
        r"^(Copyright|Wager|Payoff|Winning Numbers|Race\s+\d|Pgm|"
        r"Horse|Win|Place|Show|Track Condition|Purse|Distance|Video|"
        r"\$\d|Exacta|Trifecta|Superfecta|Daily Double)",
        re.I,
    )
    order: list[str] = []
    for n, ln in enumerate(lines):
        if re.search(r"Order\s+of\s+Finish", ln, re.I):
            for ln2 in lines[n + 1 :]:
                if stop.match(ln2) or re.search(r"Copyright", ln2, re.I):
                    break
                # имя лошади: буквы, без голых чисел/заголовков
                if re.match(r"^[A-Za-z0-9][A-Za-z0-9' .\-]{1,45}$", ln2):
                    if ln2.lower() in {"horse", "win", "place", "show", "pgm"}:
                        continue
                    if re.fullmatch(r"\d+(\.\d+)?", ln2):
                        continue
                    order.append(ln2.strip())
            break
    # уникальные, с сохранением порядка
    seen = set()
    out = []
    for nm in order:
        k = _norm_horse(nm)
        if k and k not in seen:
            seen.add(k)
            out.append(nm)
    return out


def _parse_pgm_rows(lines: list[str]) -> list[dict]:
    """
    Строки Pgm / Horse / optional mutuel.
    Не присваивает place — только post, horse, mutuel_win.
    """
    rows: list[dict] = []
    i = 0
    while i < len(lines):
        if lines[i] in ("Pgm", "Pgm # - Horse") or (
            lines[i].startswith("Pgm") and len(lines[i]) < 20
        ):
            j = i + 1
            while j < len(lines) and lines[j] in (
                "Horse",
                "Win",
                "Place",
                "Show",
                "Pgm # - Horse",
                "Pgm",
            ):
                j += 1
            while j < len(lines):
                if lines[j] in (
                    "Wager Type",
                    "Winning Numbers",
                    "Payoff",
                    "Order of Finish",
                ) or re.search(r"Order\s+of\s+Finish", lines[j], re.I):
                    break
                if re.match(r"^\d{1,2}$", lines[j]):
                    post = int(lines[j])
                    name = lines[j + 1] if j + 1 < len(lines) else ""
                    mutuel = None
                    k = j + 2
                    # до 3 чисел win/place/show
                    if k < len(lines) and re.match(r"^\d+\.\d{2}$", lines[k]):
                        mutuel = float(lines[k])
                        k += 1
                        while k < len(lines) and re.match(r"^\d+\.\d{2}$", lines[k]):
                            k += 1
                    if name and re.match(r"^[A-Za-z]", name):
                        rows.append(
                            {
                                "post": post,
                                "horse": name.strip(),
                                "mutuel_win": mutuel,
                            }
                        )
                    j = k
                    continue
                j += 1
            break
        i += 1
    return rows


def _match_row(name: str, rows: list[dict]) -> Optional[dict]:
    """Точное, затем частичное совпадение имени."""
    want = _norm_horse(name)
    if not want:
        return None
    by = {_norm_horse(r.get("horse") or ""): r for r in rows}
    if want in by:
        return by[want]
    # частичное: одно имя содержит другое
    for k, r in by.items():
        if not k:
            continue
        if want in k or k in want:
            return r
    return None


def fetch_quick_result_race(
    client, track_code: str, race_date: str, race_no: int
) -> list[dict]:
    """
    Финиш по порядку (надёжно через Order of Finish):
      [{"post": 4, "horse": "...", "mutuel_win": 10.8, "place": 1}, ...]
    place = позиция (1 = победитель). mutuel_win = выплата Win, не место.
    """
    url = (
        "http://espn.equibase.com/eqbQuickResultsDisplay.cfm"
        f"?TRK={track_code}&CY=USA&DATE={mdy_slash(race_date)}"
        f"&RN={race_no}&STYLE=espn"
    )
    r = client.get(url)
    html = r.text
    lines = _html_to_lines(html)

    order_names = _parse_order_of_finish(lines)
    rows = _parse_pgm_rows(lines)

    out: list[dict] = []

    # 1) Главный источник места — Order of Finish
    if order_names:
        for place, nm in enumerate(order_names, start=1):
            matched = _match_row(nm, rows)
            if matched:
                out.append(
                    {
                        "post": matched.get("post"),
                        "horse": matched.get("horse") or nm,
                        "mutuel_win": matched.get("mutuel_win"),
                        "place": place,
                    }
                )
            else:
                # имени нет в pgm-таблице — всё равно фиксируем place
                out.append(
                    {
                        "post": None,
                        "horse": nm,
                        "mutuel_win": None,
                        "place": place,
                    }
                )
        return out

    # 2) Fallback: порядок строк Pgm (хуже, только если Order of Finish пуст)
    for place, row in enumerate(rows, start=1):
        out.append({**row, "place": place})
    return out



def race_number_from_obj(race: dict) -> Optional[int]:
    title = race.get("title") or ""
    m = re.search(r"(\d+)", title)
    if m:
        return int(m.group(1))
    rid = race.get("id") or ""
    m2 = re.search(r"-(\d+)$", rid)
    if m2:
        return int(m2.group(1))
    if race.get("race") is not None:
        try:
            return int(race["race"])
        except (TypeError, ValueError):
            pass
    return None


def apply_places_to_data(
    data: dict, track_code: str, track_name: str, race_no: int, finish: list[dict]
) -> int:
    filled = 0
    by_post = {h["post"]: h for h in finish if h.get("post") is not None}
    by_name = {(h.get("horse") or "").lower(): h for h in finish if h.get("horse")}

    for race in data.get("races") or []:
        rn = race_number_from_obj(race)
        if rn != race_no:
            continue

        tr = race.get("track") or ""
        code = resolve_track_code(tr)
        if (
            code != track_code
            and tr != track_name
            and tr.upper() != track_code
            and track_display_name(track_code) != tr
        ):
            continue

        for h in race.get("horses") or []:
            prev = by_post.get(h.get("post"))
            if not prev:
                nm = (h.get("name") or h.get("horse") or "").lower().strip()
                prev = by_name.get(nm)
            if not prev:
                # частичное совпадение имени (Atokad и др.)
                nm = _norm_horse(h.get("name") or h.get("horse") or "")
                for k, fin in by_name.items():
                    kk = _norm_horse(k)
                    if nm and kk and (nm in kk or kk in nm):
                        prev = fin
                        break
            if not prev:
                continue
            if h.get("place") is None:
                h["place"] = prev["place"]
                filled += 1
            if prev.get("mutuel_win") is not None and h.get("mutuel_win") is None:
                h["mutuel_win"] = prev["mutuel_win"]

        if any(x.get("place") is not None for x in race.get("horses") or []):
            tags = race.setdefault("tags", [])
            if "Finished" not in tags:
                tags.append("Finished")
            race["status"] = "official"
    return filled


def cmd_results(
    race_date: str,
    track: str = "",
    races_json: str = "data/results.json",
    auto: bool = False,
    max_race: int = 14,
    push: bool = False,
    site_repo: str = "",
) -> None:
    try:
        import httpx
    except ImportError:
        sys.exit("Нужен httpx: pip install httpx")

    path = Path(races_json).expanduser()
    if not path.exists():
        alt = path.parent / "races.json"
        if alt.exists():
            path = alt
        else:
            raise SystemExit(f"Нет файла: {races_json}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("date"):
        data["date"] = race_date

    track_names = list(
        dict.fromkeys(r.get("track", "") for r in data.get("races") or [])
    )

    targets: list[tuple[str, str]] = []
    if track:
        code = resolve_track_code(track)
        label = track_display_name(code) if code in TRACK_NAMES else track
        targets = [(label, code)]
    elif auto:
        for tn in track_names:
            code = resolve_track_code(tn)
            if not code or code not in TRACK_NAMES and len(code) > 4:
                print(f"  (пропуск) нет кода Equibase: {tn}")
                continue
            need = False
            for race in data.get("races") or []:
                if race.get("track") != tn:
                    continue
                horses = race.get("horses") or []
                if horses and any(h.get("place") is None for h in horses):
                    need = True
                    break
            if need:
                targets.append((tn, code))
        if not targets:
            print("Нечего заполнять: все place уже стоят или нет треков.")
            return
    else:
        print("Треки в JSON:")
        for tn in track_names:
            print(f"  {tn:28s} -> {resolve_track_code(tn) or '?'}")
        print("\nУкажи --track ИМЯ|КОД или --auto")
        return

    client = httpx.Client(
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
            )
        },
        follow_redirects=True,
        timeout=30,
    )
    total = 0
    try:
        for tn, code in targets:
            print(f"\n=== {tn} ({code}) ===")
            empty_streak = 0
            for rn in range(1, max_race + 1):
                try:
                    finish = fetch_quick_result_race(client, code, race_date, rn)
                except Exception as e:
                    print(f"  R{rn}: ошибка {e}")
                    empty_streak += 1
                    if empty_streak >= 3:
                        break
                    continue
                if not finish:
                    print(f"  R{rn}: пусто")
                    empty_streak += 1
                    if empty_streak >= 3:
                        break
                    continue
                empty_streak = 0
                n = apply_places_to_data(data, code, tn, rn, finish)
                total += n
                top = ", ".join(f"{h['place']}.{h.get('horse')}" for h in finish[:3])
                print(f"  R{rn}: {top}  (+{n} place)")
    finally:
        client.close()

    data["updated"] = datetime.now(timezone.utc).astimezone().isoformat()
    data["source"] = "equibase-quick-results"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nСохранено: {path} (place проставлено: {total})")

    if push and site_repo:
        repo = Path(site_repo).expanduser().resolve()
        # если правили results.json в репо — commit
        if path.resolve().is_relative_to(repo):
            def run(cmd: list[str]) -> None:
                print("+", " ".join(cmd), flush=True)
                subprocess.run(cmd, cwd=str(repo), check=True)

            rel = str(path.resolve().relative_to(repo))
            run(["git", "add", rel])
            st = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=str(repo))
            if st.returncode != 0:
                run(["git", "commit", "-m", f"chore: equibase results places {race_date}"])
                run(["git", "pull", "--rebase", "origin", "main"])
                run(["git", "push", "origin", "main"])
                print("Push OK")
            else:
                print("Нет изменений для commit")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Equibase (USA): cards / live / results + push"
    )
    ap.add_argument(
        "--mode",
        choices=("cards", "live", "results"),
        default="cards",
        help="cards=ML, live=tote, results=place 1/2/3",
    )
    ap.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Дата YYYY-MM-DD (America/New_York)",
    )
    ap.add_argument(
        "--track", default="", help="Код или имя трека (CD, SAR, Belterra Park…)"
    )
    ap.add_argument(
        "--hide-finished",
        action="store_true",
        help="Убирать из JSON гонки с прошедшим post_time",
    )
    ap.add_argument(
        "--no-ml-fallback",
        action="store_true",
        help="Не подставлять win_odds из ML в cards",
    )
    ap.add_argument("--poll", type=int, default=60, help="Интервал live, сек")
    ap.add_argument("--runs", type=int, default=1, help="Число опросов live")
    ap.add_argument("--out", default="equibase_odds", help="Префикс CSV")
    ap.add_argument(
        "--browser",
        choices=("chromium", "firefox"),
        default="chromium",
        help="Движок live",
    )
    ap.add_argument("--headful", action="store_true", help="Видимый браузер")
    ap.add_argument("--debug", action="store_true", help="Диагностика")
    ap.add_argument(
        "--site-repo",
        default=os.environ.get("SITE_REPO", ""),
        help="Клон репо сайта (usa-racing-analytics)",
    )
    ap.add_argument(
        "--push",
        action="store_true",
        help="Записать JSON в репо и git push",
    )
    ap.add_argument(
        "--auto",
        action="store_true",
        help="results: все треки, где place ещё пустой",
    )
    ap.add_argument(
        "--races-json",
        default="",
        help="Путь к results.json или races.json (для --mode results)",
    )
    ap.add_argument(
        "--max-race",
        type=int,
        default=14,
        help="results: макс. номер заезда на треке",
    )
    args = ap.parse_args()

    if args.mode == "results":
        rj = args.races_json
        if not rj:
            if args.site_repo:
                rj = str(
                    Path(args.site_repo).expanduser() / "data" / "results.json"
                )
            else:
                rj = "data/results.json"
        cmd_results(
            race_date=args.date,
            track=args.track,
            races_json=rj,
            auto=args.auto,
            max_race=args.max_race,
            push=args.push,
            site_repo=args.site_repo,
        )
        return

    if args.mode == "live":
        check_hardware()

    if args.mode == "cards":
        sc = EquibaseStaticCards()
        try:
            track = args.track
            if track and track.upper() not in TRACK_NAMES:
                track = resolve_track_code(track)
            odds = sc.racecards(
                args.date,
                track,
                ml_as_win_fallback=not args.no_ml_fallback,
            )
        finally:
            sc.close()
        print_odds(odds)
        finished_races = {
            (r.get("track"), r.get("race")) for r in odds if r.get("finished")
        }
        if finished_races:
            print(f"⚠ Уже стартовало: {len(finished_races)} гонок")
        if odds:
            write_csv(f"{args.out}_cards.csv", odds)
        maybe_push(args, odds)
        return

    # live
    scraper = EquibaseLiveOdds(
        headless=not args.headful,
        debug=args.debug,
        browser_name=args.browser,
    )
    all_rows: list[dict] = []
    last_odds: list[dict] = []
    try:
        for i in range(args.runs):
            print(f"\n=== Опрос {i + 1}/{args.runs} ===", flush=True)
            track = args.track
            if track and track.upper() not in TRACK_NAMES:
                track = resolve_track_code(track)
            odds = scraper.live_odds(args.date, track)
            last_odds = odds
            print_odds(odds)
            if odds:
                write_csv(f"{args.out}_{i + 1:02d}.csv", odds)
                for r in odds:
                    row = dict(r)
                    row["run"] = i + 1
                    all_rows.append(row)
            if i + 1 < args.runs:
                time.sleep(args.poll)
    finally:
        scraper.close()
    if all_rows:
        write_csv(f"{args.out}_all.csv", all_rows)
    maybe_push(args, last_odds)


if __name__ == "__main__":
    main()
