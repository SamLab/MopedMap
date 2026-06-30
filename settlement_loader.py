#!/usr/bin/env python3
"""
Load all settlements from 18 target regions via Wikidata SPARQL.
Outputs settlements.json — list of {name, lat, lon, subject}.
Deduplicates against cities.json and REGION_ALIASES.
"""
import json
import os
import sys
import time
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CITIES_FILE = os.path.join(BASE_DIR, "cities.json")
SETTLEMENTS_FILE = os.path.join(BASE_DIR, "settlements.json")

REGIONS = {
    "Калужская область": "Q2842",
    "Тверская область": "Q2292",
    "Московская область": "Q1697",
    "Тульская область": "Q2792",
    "Рязанская область": "Q2753",
    "Брянская область": "Q2810",
    "Смоленская область": "Q2347",
    "Курская область": "Q3178",
    "Белгородская область": "Q3329",
    "Воронежская область": "Q3447",
    "Орловская область": "Q3129",
    "Липецкая область": "Q3510",
    "Тамбовская область": "Q3550",
    "Краснодарский край": "Q3680",
    "Ярославская область": "Q2448",
    "Ивановская область": "Q2654",
    "Костромская область": "Q2596",
    "Вологодская область": "Q2015",
}

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"


def query_wikidata(sparql, retries=3, timeout=180):
    headers = {"User-Agent": "MopedMapLoader/1.0 (https://github.com/SamLab/MopedMap; settlement data for UAV tracking)"}
    for attempt in range(retries):
        try:
            resp = requests.get(
                SPARQL_ENDPOINT,
                params={"query": sparql, "format": "json"},
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(10 * (attempt + 1))
    return None


def load_existing_names():
    """Load city names from cities.json for dedup."""
    existing = set()
    if os.path.exists(CITIES_FILE):
        with open(CITIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for c in data:
            existing.add(c["name"].strip().lower())
    return existing


def load_region_alias_patterns():
    """Load pattern names from REGION_ALIASES in mopedmap.py for dedup."""
    existing = set()
    try:
        src = open(os.path.join(BASE_DIR, "mopedmap.py"), "r", encoding="utf-8").read()
        import re
        for m in re.finditer(r'"pattern":\s*"([^"]+)"', src):
            existing.add(m.group(1).lower())
    except Exception:
        pass
    return existing


SETTLEMENT_TYPES = (
    "wd:Q515"   # город
    " wd:Q3957" # пгт
    " wd:Q204686" # городской посёлок
    " wd:Q532"  # деревня
    " wd:Q3257575" # село
    " wd:Q15281072" # сельский населённый пункт
    " wd:Q13223623" # посёлок
)


def fetch_region_settlements(region_label, region_qid):
    """Fetch all settlements for one region using direct type matching."""
    sparql = f"""
    SELECT ?settlementLabel ?lat ?lon WHERE {{
      VALUES ?type {{ wd:Q515 wd:Q3957 wd:Q204686 wd:Q532 wd:Q3257575 wd:Q15281072 wd:Q13223623 }}
      ?settlement wdt:P31 ?type .
      ?settlement wdt:P131+ wd:{region_qid} .
      ?settlement wdt:P625 ?coords .
      BIND(geof:latitude(?coords) AS ?lat)
      BIND(geof:longitude(?coords) AS ?lon)
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ru" . }}
    }}
    """
    data = query_wikidata(sparql)
    if not data:
        print(f"  FAILED: {region_label}")
        return []

    results = []
    bindings = data.get("results", {}).get("bindings", [])
    for b in bindings:
        name = b.get("settlementLabel", {}).get("value", "").strip()
        lat = b.get("lat", {}).get("value")
        lon = b.get("lon", {}).get("value")
        if not name or not lat or not lon:
            continue
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except ValueError:
            continue
        results.append({
            "name": name,
            "lat": round(lat_f, 5),
            "lon": round(lon_f, 5),
            "subject": region_label,
        })
    return results


def main():
    existing_cities = load_existing_names()
    existing_patterns = load_region_alias_patterns()
    print(f"Existing cities: {len(existing_cities)}, region aliases: {len(existing_patterns)}")

    all_settlements = []
    for label, qid in REGIONS.items():
        print(f"Fetching {label} ({qid})...")
        items = fetch_region_settlements(label, qid)
        print(f"  Got {len(items)} settlements")
        all_settlements.extend(items)
        time.sleep(5)

    print(f"\nTotal raw: {len(all_settlements)}")

    deduped = []
    seen = set()
    skipped_existing = 0
    skipped_dup = 0
    for s in all_settlements:
        key = s["name"].lower()
        if key in existing_cities or key in existing_patterns:
            skipped_existing += 1
            continue
        coord_key = (round(s["lat"], 2), round(s["lon"], 2), key)
        if coord_key in seen:
            skipped_dup += 1
            continue
        seen.add(coord_key)
        deduped.append(s)

    print(f"Skipped {skipped_existing} already in cities/aliases, {skipped_dup} coordinate dups")
    print(f"Final: {len(deduped)} settlements")

    with open(SETTLEMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=1)
    print(f"Saved to {SETTLEMENTS_FILE}")


if __name__ == "__main__":
    main()
