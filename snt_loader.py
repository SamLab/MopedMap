#!/usr/bin/env python3
"""
Импорт СНТ/СТ/ДНТ/ДНП и прочих садоводческих товариществ Ярославской области из OSM.

Источник — Overpass API (landuse=allotments + объекты с именем-маркером СНТ/СТ/...).
Записи дописываются в settlements.json (не перезаписывают файл целиком) с полями:
{name, lat, lon, subject: "Ярославская область", snt: true, [snt_ctx: true]}.

`snt_ctx` ставится для «родовых» имён (одно слово, без цифры) — такие матчатся
в постах только при наличии слова-маркера (СНТ/СТ/...) рядом с именем.

Использование:
    python snt_loader.py                 # fetch из Overpass и дописать
    python snt_loader.py cache.json      # взять объекты из локального JSON (оффлайн)
"""
import json
import os
import re
import sys
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTLEMENTS_FILE = os.path.join(BASE_DIR, "settlements.json")
CITIES_FILE = os.path.join(BASE_DIR, "cities.json")
SUBJECT = "Ярославская область"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

OVERPASS_QUERY = """
[out:json][timeout:280];
area["ISO3166-2"="RU-YAR"]->.a;
(
  nwr(area.a)["name"~"^(СНТ|СТ|СНОТ|СНП|ДНТ|ДНП|ДСК|СДТ|ТСН|СОТ|КП|К/П)\\b",i];
  nwr(area.a)["landuse"="allotments"]["name"];
);
out tags center;
"""

# Маркеры-префиксы (сортируются по длине убыв. — порядок важен).
_MARKERS = [
    "садоводческое некоммерческое товарищество",
    "садоводческое товарищество",
    "садовое некоммерческое товарищество",
    "садовое товарищество",
    "некоммерческое товарищество",
    "коллективный сад",
    "дачный посёлок",
    "садовые участки",
    "садоводство",
    "снт", "снот", "снп", "сдт", "сот",
    "днт", "днп", "дск", "тсн", "кп", "ст", "к/п",
]
_MARKERS.sort(key=len, reverse=True)
_MARKER_RE = re.compile(
    r"^\s*(?:" + "|".join(re.escape(m) for m in _MARKERS) + r")\b[\s.:№-]*",
    re.IGNORECASE,
)
_NUM_RE = re.compile(r"^\s*(?:№\s*\d+|\d+[.)]?)\s*")
_PAREN_RE = re.compile(r"\([^)]*\)")
_TRAIL_NUM_RE = re.compile(r"\s*№\s*\d*\s*$")
_QUOTES = '"\'«»“”'
_SKIP_NAMES = {"оздоровитель"}


def clean_snt_name(raw):
    """Очистить имя СНТ. Вернуть очищенное имя или None, если запись битая."""
    if not raw:
        return None
    t = raw.strip()
    # непарные кавычки — обрубленная запись
    if t.count('"') % 2 != 0 or t.count("«") != t.count("»") or t.count("“") != t.count("”"):
        return None
    t = _PAREN_RE.sub(" ", t)
    # многократно срезаем ведущие маркеры/нумерацию
    for _ in range(8):
        new = _MARKER_RE.sub("", t)
        new = _NUM_RE.sub("", new)
        if new == t:
            break
        t = new
    t = _TRAIL_NUM_RE.sub("", t)
    # снять обрамляющие кавычки/пробелы
    prev = None
    while prev != t:
        prev = t
        t = t.strip().strip(_QUOTES).strip()
    t = t.rstrip(" \t.,;:!?")
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) < 2:
        return None
    if re.search(r"[A-Za-z]", t):
        return None
    if any(ch in t for ch in ("№", "?", "(", ")", '"', "«", "»", "“", "”")):
        return None
    if t.lower() in _SKIP_NAMES:
        return None
    if not re.search(r"[А-Яа-яЁё]", t):
        return None
    return t[0].upper() + t[1:]


def is_generic_snt(name):
    """Родовое имя: одно слово и без цифры → требует слова-маркера в тексте поста."""
    if not name:
        return False
    return (" " not in name) and not re.search(r"\d", name)


def load_existing_keys():
    """Множество (name.lower(), subject.lower()) из settlements.json и cities.json."""
    keys = set()
    for path in (SETTLEMENTS_FILE, CITIES_FILE):
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for x in data:
            n = (x.get("name") or "").strip().lower()
            s = (x.get("subject") or "").strip().lower()
            keys.add((n, s))
            keys.add((n, "__any__"))
    return keys


def fetch_overpass():
    """Получить объекты allotments/СНТ Ярославской области из Overpass."""
    headers = {"User-Agent": "MopedMapSNT/1.0 (https://github.com/SamLab/MopedMap)"}
    last_err = None
    for attempt in range(3):
        for url in OVERPASS_ENDPOINTS:
            try:
                resp = requests.post(url, data={"data": OVERPASS_QUERY}, headers=headers, timeout=300)
                resp.raise_for_status()
                return resp.json().get("elements", [])
            except Exception as e:  # noqa: BLE001
                last_err = e
                print(f"  Overpass {url} failed: {e}")
        time.sleep(10 * (attempt + 1))
    print(f"  Overpass FAILED: {last_err}")
    return []


def osm_items_to_records(elements):
    """Нормализовать элементы Overpass в список {osm_name, lat, lon}."""
    out = []
    for el in elements:
        tags = el.get("tags", {})
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            center = el.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")
        if lat is None or lon is None:
            continue
        out.append({"osm_name": name, "lat": lat, "lon": lon})
    return out


def build_new_entries(raw_items, existing_keys):
    """Вернуть список новых записей для дописывания + статистику."""
    seen = set()
    new = []
    stats = {"raw": len(raw_items), "cleaned": 0, "rejected": 0, "existing": 0, "dup": 0}
    for it in raw_items:
        name = clean_snt_name(it.get("osm_name", ""))
        if not name:
            stats["rejected"] += 1
            continue
        stats["cleaned"] += 1
        key = (name.lower(), SUBJECT.lower())
        if (name.lower(), "__any__") in existing_keys:
            stats["existing"] += 1
            continue
        if key in seen:
            stats["dup"] += 1
            continue
        seen.add(key)
        entry = {
            "name": name,
            "lat": round(float(it["lat"]), 7),
            "lon": round(float(it["lon"]), 7),
            "subject": SUBJECT,
            "snt": True,
        }
        if is_generic_snt(name):
            entry["snt_ctx"] = True
        new.append(entry)
    return new, stats


def append_entries(new_entries):
    with open(SETTLEMENTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.extend(new_entries)
    with open(SETTLEMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return len(data)


def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else None
    if cache:
        with open(cache, "r", encoding="utf-8") as f:
            raw_items = json.load(f)
        print(f"Loaded {len(raw_items)} raw items from {cache}")
    else:
        print("Fetching from Overpass...")
        raw_items = osm_items_to_records(fetch_overpass())
        print(f"Got {len(raw_items)} named objects")

    existing_keys = load_existing_keys()
    new_entries, stats = build_new_entries(raw_items, existing_keys)
    print("Stats:", stats)
    print(f"New entries: {len(new_entries)}")
    for e in new_entries[:20]:
        print("  +", e["name"], "snt_ctx" if e.get("snt_ctx") else "")
    if len(new_entries) > 20:
        print(f"  ... (+{len(new_entries) - 20} more)")

    total = append_entries(new_entries)
    print(f"settlements.json now has {total} entries")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
