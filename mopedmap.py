import requests
import json
import re
import os
import sys
import webbrowser
import time
import traceback
import html as html_module

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CITIES_FILE = os.path.join(BASE_DIR, "cities.json")
SETTLEMENTS_FILE = os.path.join(BASE_DIR, "settlements.json")
REGION_HISTORY_FILE = os.path.join(BASE_DIR, "region_history.json")

with open(CITIES_FILE, "r", encoding="utf-8") as f:
    cities_data = json.load(f)

CITY_DB = {}
CITY_BY_NAME_SUBJECT = {}
for c in cities_data:
    name = c["name"].strip()
    CITY_DB[name.lower()] = {
        "lat": float(c["coords"]["lat"]),
        "lon": float(c["coords"]["lon"]),
        "name": name,
        "subject": c["subject"],
    }
    subj = c["subject"].strip()
    key = (name.lower(), subj.lower())
    if key not in CITY_BY_NAME_SUBJECT:
            CITY_BY_NAME_SUBJECT[key] = {
                "lat": float(c["coords"]["lat"]),
                "lon": float(c["coords"]["lon"]),
                "name": name,
                "subject": subj,
            }

SETTLEMENT_DB = {}
SETTLEMENTS_BY_NAME_SUBJECT = {}
SETTLEMENTS_ALL_BY_KEY = {}
NON_UNIQUE_SETTLEMENT_NAMES = set()
if os.path.exists(SETTLEMENTS_FILE):
    with open(SETTLEMENTS_FILE, "r", encoding="utf-8") as f:
        settlements_data = json.load(f)
    for s in settlements_data:
        name = s["name"].strip()
        lk = name.lower()
        if lk not in CITY_DB:
            SETTLEMENT_DB[lk] = {
                "lat": float(s["lat"]),
                "lon": float(s["lon"]),
                "name": name,
                "subject": s["subject"],
            }
        subj = s["subject"].strip()
        key = (lk, subj.lower())
        if key not in CITY_BY_NAME_SUBJECT and key not in SETTLEMENTS_BY_NAME_SUBJECT:
            SETTLEMENTS_BY_NAME_SUBJECT[key] = {
                "lat": float(s["lat"]),
                "lon": float(s["lon"]),
                "name": name,
                "subject": subj,
            }
        SETTLEMENTS_ALL_BY_KEY.setdefault(key, []).append({
            "lat": float(s["lat"]),
            "lon": float(s["lon"]),
            "name": name,
            "subject": subj,
        })
# Build set of non-unique settlement names (appear in >1 subject)
_name_subj_counts = {}
for (lk, subj) in SETTLEMENTS_BY_NAME_SUBJECT:
    _name_subj_counts.setdefault(lk, set()).add(subj)
# Also check against CITY_BY_NAME_SUBJECT for same names in different sources
for (lk, subj) in CITY_BY_NAME_SUBJECT:
    _name_subj_counts.setdefault(lk, set()).add(subj)
for lk, subjects in _name_subj_counts.items():
    if len(subjects) > 1:
        NON_UNIQUE_SETTLEMENT_NAMES.add(lk)

# Hardcoded settlements for annexed regions not in Wikidata
_extra_settlements = [
    ("Красный Луч", 48.167, 38.933, "Луганская область"),
    ("Тамала", 52.54097, 43.25145, "Пензенская область"),
    ("Сосновка", 52.42125, 43.50979, "Пензенская область"),
]
for name, lat, lon, subj in _extra_settlements:
    lk = name.lower()
    subj_lower = subj.lower()
    key = (lk, subj_lower)
    if key not in SETTLEMENTS_BY_NAME_SUBJECT and key not in CITY_BY_NAME_SUBJECT:
        entry = {"name": name, "lat": lat, "lon": lon, "subject": subj}
        SETTLEMENTS_BY_NAME_SUBJECT[key] = entry
        SETTLEMENTS_ALL_BY_KEY.setdefault(key, []).append(entry)
        _name_subj_counts.setdefault(lk, set()).add(subj_lower)
        if len(_name_subj_counts[lk]) > 1:
            NON_UNIQUE_SETTLEMENT_NAMES.add(lk)

# Major cities (CITY_DB) that share a name with settlements in other regions.
# Without region context these should default to the major city — otherwise a
# post like "БПЛА над Белгородом" loses the marker entirely (the name is
# "non-unique" because e.g. a Белгород village exists in Брянская область).
NON_UNIQUE_MAJOR_CITIES = frozenset(
    lk for lk in NON_UNIQUE_SETTLEMENT_NAMES if lk in CITY_DB
)

def make_region_alias(alias, city_name, lat, lon, subject=None, use_city_db=True):
    if use_city_db:
        ck = city_name.lower()
        if ck in CITY_DB:
            lat = CITY_DB[ck]["lat"]
            lon = CITY_DB[ck]["lon"]
    if not subject:
        subject = alias.strip()
        # Capitalize first letter for common patterns
        if ' ' in subject:
            subject = subject.title()
        elif len(subject) <= 4 and subject.isalpha():
            subject = subject.upper()
    result = {
        "pattern": alias.lower(),
        "name": city_name,
        "lat": lat,
        "lon": lon,
        "type": "region",
        "is_region": True,
        "subject": subject,
    }
    return result


def make_region_alias_with_cases(alias, city_name, lat, lon, subject=None):
    """Generate region alias with common case variants and bare adjective form."""
    if subject is None:
        subject = alias.strip()
        if ' ' in subject:
            subject = subject.title()
    result = [make_region_alias(alias, city_name, lat, lon, subject)]
    a = alias.lower()
    # область -> области (genitive), областью (instrumental), ую область (accusative), bare adjective
    if a.endswith("ая область"):
        stem = a[:-10]
        result.append(make_region_alias(stem + "ой области", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ой областью", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ую область", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ой", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ая", city_name, lat, lon, subject))
    elif a.endswith("ая обл"):
        stem = a[:-6]
        result.append(make_region_alias(stem + "ой обл", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ую обл", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ой", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ая", city_name, lat, lon, subject))
    elif a.endswith("ская область"):
        stem = a[:-12]
        result.append(make_region_alias(stem + "ской области", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ской областью", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "скую область", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ской", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ская", city_name, lat, lon, subject))
    elif a.endswith("ская обл"):
        stem = a[:-8]
        result.append(make_region_alias(stem + "ской обл", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "скую обл", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ской", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ская", city_name, lat, lon, subject))
    # край -> края (genitive) — "ский край" must precede "ий край" to avoid
    # generating "краснодарскего края" (wrong) vs "краснодарского края" (correct)
    elif a.endswith("ский край"):
        stem = a[:-9]
        result.append(make_region_alias(stem + "ского края", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ском крае", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ским краем", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ский", city_name, lat, lon, subject))
    elif a.endswith("ий край"):
        stem = a[:-7]
        result.append(make_region_alias(stem + "его края", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ем крае", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "им краем", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ий", city_name, lat, lon, subject))
    # округ -> округа
    elif a.endswith("ский округ"):
        stem = a[:-10]
        result.append(make_region_alias(stem + "ского округа", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ском округе", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ским округом", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ский", city_name, lat, lon, subject))
    elif a.endswith("ий округ"):
        stem = a[:-8]
        result.append(make_region_alias(stem + "его округа", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ем округе", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "им округом", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ий", city_name, lat, lon, subject))
    # "... автономный округ" (Ханты-Мансийский/Ямало-Ненецкий/Чукотский/Ненецкий)
    # — простое окончание "ий округ" тут не срабатывает из-за "автономный"
    elif a.endswith(" автономный округ"):
        stem = a[:-len(" автономный округ")].rstrip("й")
        result.append(make_region_alias(stem + "ого автономного округа", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ом автономном округе", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "им автономным округом", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ий", city_name, lat, lon, subject))
    # республика -> республики (genitive), республику (accusative), республикой (instrumental)
    elif a.endswith("ская республика"):
        stem = a[:-15]
        result.append(make_region_alias(stem + "ской республики", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "скую республику", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ской республикой", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ской", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ская", city_name, lat, lon, subject))
    # республика X -> республики X (genitive), республику X (accusative), республикой X (instrumental)
    elif a.startswith("республика ") and len(a) > 12:
        rest = a[11:]
        result.append(make_region_alias("республики " + rest, city_name, lat, lon, subject))
        result.append(make_region_alias("республику " + rest, city_name, lat, lon, subject))
        result.append(make_region_alias("республикой " + rest, city_name, lat, lon, subject))
    return result

REGION_ALIASES = [
    make_region_alias("губкинский го", "Губкин", 51.28333, 37.55, "Белгородская область"),
    make_region_alias("губкинском го", "Губкин", 51.28333, 37.55, "Белгородская область"),
    make_region_alias("неклиновский район", "Ростов-на-Дону", 47.2357, 39.7015),
    make_region_alias("неклиновский р-н", "Ростов-на-Дону", 47.2357, 39.7015),
    make_region_alias("малоархангельский район", "Малоархангельск", 52.4, 36.5),
    make_region_alias("малоархангельский р-н", "Малоархангельск", 52.4, 36.5),
    make_region_alias("дмитровский район", "Дмитровск", 52.5055, 35.1415),
    make_region_alias("дмитровский р-н", "Дмитровск", 52.5055, 35.1415),
    make_region_alias("россошанский район", "Россошь", 50.2, 39.5833),
    make_region_alias("россошанский р-н", "Россошь", 50.2, 39.5833),
    make_region_alias("ейский район", "Ейск", 46.7106, 38.2778),
    make_region_alias("ейский р-н", "Ейск", 46.7106, 38.2778),
    make_region_alias("матвеев-курган", "Матвеев Курган", 47.564, 38.875),
    make_region_alias("матвеев курган", "Матвеев Курган", 47.564, 38.875),
    make_region_alias("матвеево-курганский район", "Матвеев Курган", 47.564, 38.875),
    make_region_alias("матвеево-курганский р-н", "Матвеев Курган", 47.564, 38.875),
    make_region_alias("азовский район", "Азов", 47.1, 39.4167),
    make_region_alias("азовский р-н", "Азов", 47.1, 39.4167),
    make_region_alias("орловский район", "Орёл", 52.9678, 36.0696),
    make_region_alias("орловский р-н", "Орёл", 52.9678, 36.0696),
    # Воронежская область — районные центры
    make_region_alias("кантемировский район", "Кантемировка", 49.70, 39.85),
    make_region_alias("кантемировский р-н", "Кантемировка", 49.70, 39.85),
    make_region_alias("терновский район", "Терновка", 51.678, 41.637),
    make_region_alias("терновский р-н", "Терновка", 51.678, 41.637),
    make_region_alias("аннинский район", "Анна", 51.484, 40.419),
    make_region_alias("аннинский р-н", "Анна", 51.484, 40.419),
    make_region_alias("новохоперский район", "Новохопёрск", 51.095, 41.617),
    make_region_alias("новохоперский р-н", "Новохопёрск", 51.095, 41.617),
    make_region_alias("бутурлиновский район", "Бутурлиновка", 50.825, 40.589),
    make_region_alias("бутурлиновский р-н", "Бутурлиновка", 50.825, 40.589),
    make_region_alias("верхнемамонский район", "Верхний Мамон", 50.164, 40.399),
    make_region_alias("верхнемамонский р-н", "Верхний Мамон", 50.164, 40.399),
    make_region_alias("лискинский район", "Лиски", 50.982, 39.499),
    make_region_alias("лискинский р-н", "Лиски", 50.982, 39.499),
    # Ростовская область — районные центры
    make_region_alias("верхнедонской район", "Казанская", 49.793, 41.136),
    make_region_alias("верхнедонской р-н", "Казанская", 49.793, 41.136),
    make_region_alias("миллеровский район", "Миллерово", 48.917, 40.4),
    make_region_alias("миллеровский р-н", "Миллерово", 48.917, 40.4),
    make_region_alias("тарасовский район", "Тарасовский", 48.727, 40.363),
    make_region_alias("тарасовский р-н", "Тарасовский", 48.727, 40.363),
    # Волгоградская область — районные центры
    make_region_alias("новониколаевский район", "Новониколаевский", 50.975, 42.364),
    make_region_alias("новониколаевский р-н", "Новониколаевский", 50.975, 42.364),
    make_region_alias("старощербиновская", "Старощербиновская", 46.6297, 38.6673),
    make_region_alias("новоминская", "Новоминская", 46.3193, 38.9579),
    make_region_alias("стародеревянковская", "Стародеревянковская", 46.1328, 38.9633),
    make_region_alias("тимашевск", "Тимашёвск", 45.6167, 38.9333),
    make_region_alias("кущёвская", "Кущёвская", 46.5656, 39.6289),
    make_region_alias("кущевская", "Кущёвская", 46.5656, 39.6289),
    make_region_alias("ленинградская", "Ленинградская", 46.3211, 39.3978),
    make_region_alias("павловск", "Павловская", 46.1374, 39.7919),
    make_region_alias("павловская", "Павловская", 46.1374, 39.7919),
    make_region_alias("степной курган", "Степной Курган", 47.72, 40.82),
    # каменка в Воронежской области (не путать с Каменка Пензенской или Брянской)
    {"pattern": "каменка", "name": "Каменка", "lat": 50.717, "lon": 39.417, "type": "city", "is_region": False, "subject": "Воронежская область"},
    {"pattern": "каменский район", "name": "Каменка", "lat": 50.717, "lon": 39.417, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "каменский р-н", "name": "Каменка", "lat": 50.717, "lon": 39.417, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "беловский район", "name": "Белая", "lat": 51.05, "lon": 35.72, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "беловский р-н", "name": "Белая", "lat": 51.05, "lon": 35.72, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "свердловский район", "name": "Змиёвка", "lat": 52.67, "lon": 36.37, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "свердловский р-н", "name": "Змиёвка", "lat": 52.67, "lon": 36.37, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "курба", "name": "Курба", "lat": 57.55, "lon": 39.56, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "курбу", "name": "Курба", "lat": 57.55, "lon": 39.56, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "курбы", "name": "Курба", "lat": 57.55, "lon": 39.56, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "угличский район", "name": "Углич", "lat": 57.53, "lon": 38.33, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "угличском районе", "name": "Углич", "lat": 57.53, "lon": 38.33, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "угличский р-н", "name": "Углич", "lat": 57.53, "lon": 38.33, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "угличском р-не", "name": "Углич", "lat": 57.53, "lon": 38.33, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "переславский район", "name": "Переславль-Залесский", "lat": 56.74, "lon": 38.86, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "переславском районе", "name": "Переславль-Залесский", "lat": 56.74, "lon": 38.86, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "переславский р-н", "name": "Переславль-Залесский", "lat": 56.74, "lon": 38.86, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "переславском р-не", "name": "Переславль-Залесский", "lat": 56.74, "lon": 38.86, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "ростовский район", "name": "Ростов", "lat": 57.18, "lon": 39.42, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "ростовском районе", "name": "Ростов", "lat": 57.18, "lon": 39.42, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "ростовский р-н", "name": "Ростов", "lat": 57.18, "lon": 39.42, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "ростовском р-не", "name": "Ростов", "lat": 57.18, "lon": 39.42, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "большесельский район", "name": "Большое Село", "lat": 57.717, "lon": 38.933, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "большесельском районе", "name": "Большое Село", "lat": 57.717, "lon": 38.933, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "большесельский р-н", "name": "Большое Село", "lat": 57.717, "lon": 38.933, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "большесельском р-не", "name": "Большое Село", "lat": 57.717, "lon": 38.933, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "борисоглебский район", "name": "Борисоглебский", "lat": 57.267, "lon": 39.150, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "борисоглебском районе", "name": "Борисоглебский", "lat": 57.267, "lon": 39.150, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "борисоглебский р-н", "name": "Борисоглебский", "lat": 57.267, "lon": 39.150, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "борисоглебском р-не", "name": "Борисоглебский", "lat": 57.267, "lon": 39.150, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "брейтовский район", "name": "Брейтово", "lat": 58.300, "lon": 37.867, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "брейтовском районе", "name": "Брейтово", "lat": 58.300, "lon": 37.867, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "брейтовский р-н", "name": "Брейтово", "lat": 58.300, "lon": 37.867, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "брейтовском р-не", "name": "Брейтово", "lat": 58.300, "lon": 37.867, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "даниловский район", "name": "Данилов", "lat": 58.183, "lon": 40.183, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "даниловском районе", "name": "Данилов", "lat": 58.183, "lon": 40.183, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "даниловский р-н", "name": "Данилов", "lat": 58.183, "lon": 40.183, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "даниловском р-не", "name": "Данилов", "lat": 58.183, "lon": 40.183, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "любимский район", "name": "Любим", "lat": 58.350, "lon": 40.683, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "любимском районе", "name": "Любим", "lat": 58.350, "lon": 40.683, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "любимский р-н", "name": "Любим", "lat": 58.350, "lon": 40.683, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "любимском р-не", "name": "Любим", "lat": 58.350, "lon": 40.683, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "мышкинский район", "name": "Мышкин", "lat": 57.783, "lon": 38.450, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "мышкинском районе", "name": "Мышкин", "lat": 57.783, "lon": 38.450, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "мышкинский р-н", "name": "Мышкин", "lat": 57.783, "lon": 38.450, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "мышкинском р-не", "name": "Мышкин", "lat": 57.783, "lon": 38.450, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "мышкино", "name": "Мышкин", "lat": 57.783, "lon": 38.450, "type": "city", "subject": "Ярославская область"},
    {"pattern": "некоузский район", "name": "Новый Некоуз", "lat": 57.917, "lon": 38.067, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "некоузском районе", "name": "Новый Некоуз", "lat": 57.917, "lon": 38.067, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "некоузский р-н", "name": "Новый Некоуз", "lat": 57.917, "lon": 38.067, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "некоузском р-не", "name": "Новый Некоуз", "lat": 57.917, "lon": 38.067, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "некрасовский район", "name": "Некрасовское", "lat": 57.667, "lon": 40.367, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "некрасовском районе", "name": "Некрасовское", "lat": 57.667, "lon": 40.367, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "некрасовский р-н", "name": "Некрасовское", "lat": 57.667, "lon": 40.367, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "некрасовском р-не", "name": "Некрасовское", "lat": 57.667, "lon": 40.367, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "первомайский район", "name": "Пречистое", "lat": 58.417, "lon": 40.333, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "первомайском районе", "name": "Пречистое", "lat": 58.417, "lon": 40.333, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "первомайский р-н", "name": "Пречистое", "lat": 58.417, "lon": 40.333, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "первомайском р-не", "name": "Пречистое", "lat": 58.417, "lon": 40.333, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "пошехонский район", "name": "Пошехонье", "lat": 58.500, "lon": 39.117, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "пошехонском районе", "name": "Пошехонье", "lat": 58.500, "lon": 39.117, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "пошехонский р-н", "name": "Пошехонье", "lat": 58.500, "lon": 39.117, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "пошехонском р-не", "name": "Пошехонье", "lat": 58.500, "lon": 39.117, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "рыбинский район", "name": "Рыбинск", "lat": 58.050, "lon": 38.833, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "рыбинском районе", "name": "Рыбинск", "lat": 58.050, "lon": 38.833, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "рыбинский р-н", "name": "Рыбинск", "lat": 58.050, "lon": 38.833, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "рыбинском р-не", "name": "Рыбинск", "lat": 58.050, "lon": 38.833, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "рыбинское водохранилище", "name": "Рыбинское водохранилище", "lat": 58.0653, "lon": 38.8208, "type": "city", "subject": "Ярославская область"},
    {"pattern": "рыбинского водохранилища", "name": "Рыбинское водохранилище", "lat": 58.0653, "lon": 38.8208, "type": "city", "subject": "Ярославская область"},
    {"pattern": "тутаевский район", "name": "Тутаев", "lat": 57.883, "lon": 39.533, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "тутаевском районе", "name": "Тутаев", "lat": 57.883, "lon": 39.533, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "тутаевский р-н", "name": "Тутаев", "lat": 57.883, "lon": 39.533, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "тутаевском р-не", "name": "Тутаев", "lat": 57.883, "lon": 39.533, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "ярославский район", "name": "Ярославль", "lat": 57.617, "lon": 39.867, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "ярославском районе", "name": "Ярославль", "lat": 57.617, "lon": 39.867, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "ярославский р-н", "name": "Ярославль", "lat": 57.617, "lon": 39.867, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "ярославском р-не", "name": "Ярославль", "lat": 57.617, "lon": 39.867, "type": "region", "is_region": True, "subject": "Ярославская область"},
    # Ярославская область — населённые пункты не из CITY_DB
    {"pattern": "большое село", "name": "Большое Село", "lat": 57.717, "lon": 38.933, "type": "city", "subject": "Ярославская область"},
    {"pattern": "большом селе", "name": "Большое Село", "lat": 57.717, "lon": 38.933, "type": "city", "subject": "Ярославская область"},
    {"pattern": "борисоглебский", "name": "Борисоглебский", "lat": 57.267, "lon": 39.150, "type": "city", "subject": "Ярославская область"},
    {"pattern": "борисоглебском", "name": "Борисоглебский", "lat": 57.267, "lon": 39.150, "type": "city", "subject": "Ярославская область"},
    {"pattern": "брейтово", "name": "Брейтово", "lat": 58.300, "lon": 37.867, "type": "city", "subject": "Ярославская область"},
    {"pattern": "брейтове", "name": "Брейтово", "lat": 58.300, "lon": 37.867, "type": "city", "subject": "Ярославская область"},
    {"pattern": "гаврилов ям", "name": "Гаврилов-Ям", "lat": 57.300, "lon": 39.867, "type": "city", "subject": "Ярославская область"},
    {"pattern": "гавриловом яме", "name": "Гаврилов-Ям", "lat": 57.300, "lon": 39.867, "type": "city", "subject": "Ярославская область"},
    {"pattern": "гаврилов-ямский район", "name": "Гаврилов-Ям", "lat": 57.300, "lon": 39.867, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "гаврилов-ямском районе", "name": "Гаврилов-Ям", "lat": 57.300, "lon": 39.867, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "гаврилов-ямский р-н", "name": "Гаврилов-Ям", "lat": 57.300, "lon": 39.867, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "гаврилов-ямском р-не", "name": "Гаврилов-Ям", "lat": 57.300, "lon": 39.867, "type": "region", "is_region": True, "subject": "Ярославская область"},
    {"pattern": "новый некоуз", "name": "Новый Некоуз", "lat": 57.917, "lon": 38.067, "type": "city", "subject": "Ярославская область"},
    {"pattern": "новом некоузе", "name": "Новый Некоуз", "lat": 57.917, "lon": 38.067, "type": "city", "subject": "Ярославская область"},
    {"pattern": "некрасовское", "name": "Некрасовское", "lat": 57.667, "lon": 40.367, "type": "city", "subject": "Ярославская область"},
    {"pattern": "некрасовском", "name": "Некрасовское", "lat": 57.667, "lon": 40.367, "type": "city", "subject": "Ярославская область"},
    {"pattern": "пречистое", "name": "Пречистое", "lat": 58.417, "lon": 40.333, "type": "city", "subject": "Ярославская область"},
    {"pattern": "пречистом", "name": "Пречистое", "lat": 58.417, "lon": 40.333, "type": "city", "subject": "Ярославская область"},
    # Ярославская область — дополнительные нп (добавлены 14.07)
    {"pattern": "телищев", "name": "Телищево", "lat": 57.52631, "lon": 39.98217, "type": "city", "subject": "Ярославская область"},
    {"pattern": "нижний пос", "name": "Нижний Поселок", "lat": 57.62089, "lon": 39.99506, "type": "city", "subject": "Ярославская область"},
    {"pattern": "ермолов", "name": "Ермолово", "lat": 57.63262, "lon": 39.99856, "type": "city", "subject": "Ярославская область"},
    {"pattern": "красный бор", "name": "Красный Бор", "lat": 57.64794, "lon": 40.01385, "type": "city", "subject": "Ярославская область"},
    {"pattern": "кобыляев", "name": "Кобыляево", "lat": 57.65165, "lon": 40.04280, "type": "city", "subject": "Ярославская область"},
    {"pattern": "козьмодемьянс", "name": "Козьмодемьянск", "lat": 57.49236, "lon": 39.69240, "type": "city", "subject": "Ярославская область"},
    {"pattern": "дубки", "name": "Дубки", "lat": 57.52836, "lon": 39.73805, "type": "city", "subject": "Ярославская область"},
    {"pattern": "гаврилков", "name": "Гаврилково", "lat": 57.42255, "lon": 39.61766, "type": "city", "subject": "Ярославская область"},
    {"pattern": "шалаев", "name": "Шалаево", "lat": 57.35987, "lon": 39.59351, "type": "city", "subject": "Ярославская область"},
    {"pattern": "грешнев", "name": "Грешнево", "lat": 57.70472, "lon": 40.21583, "type": "city", "subject": "Ярославская область"},
    {"pattern": "полесье", "name": "Полесье", "lat": 57.62917, "lon": 39.95760, "type": "city", "subject": "Ярославская область"},
    {"pattern": "любашин", "name": "Любашино", "lat": 57.49029, "lon": 39.94044, "type": "city", "subject": "Ярославская область"},
    {"pattern": "заволжье", "name": "Заволжье", "lat": 58.073, "lon": 38.858, "type": "city", "subject": "Ярославская область"},
    # Ярославская область — дополнительная партия (добавлены 29.07)
    {"pattern": "алексеевск", "name": "Алексеевское", "lat": 57.53912, "lon": 39.89271, "type": "city", "subject": "Ярославская область"},
    {"pattern": "климовск", "name": "Климовское", "lat": 57.51444, "lon": 39.88778, "type": "city", "subject": "Ярославская область"},
    {"pattern": "еремеевск", "name": "Еремеевское", "lat": 57.45836, "lon": 39.91689, "type": "city", "subject": "Ярославская область"},
    {"pattern": "заячий холм", "name": "Заячий Холм", "lat": 57.40639, "lon": 39.91333, "type": "city", "subject": "Ярославская область"},
    {"pattern": "станция рек", "name": "Станция Река", "lat": 57.51147, "lon": 39.70038, "type": "city", "subject": "Ярославская область"},
    {"pattern": "щедрин", "name": "Щедрино", "lat": 57.55498, "lon": 39.83340, "type": "city", "subject": "Ярославская область"},
    {"pattern": "нагорный", "name": "Нагорный", "lat": 57.56114, "lon": 39.83833, "type": "city", "subject": "Ярославская область"},
    {"pattern": "сергеев", "name": "Сергеево", "lat": 57.497, "lon": 39.932, "type": "city", "subject": "Ярославская область"},
    {"pattern": "брагин", "name": "Брагино", "lat": 57.68706, "lon": 39.78323, "type": "city", "subject": "Ярославская область"},
    {"pattern": "нефтестрой", "name": "Нефтестрой", "lat": 57.58604, "lon": 39.84162, "type": "city", "subject": "Ярославская область"},
    {"pattern": "новоселк", "name": "Новоселки", "lat": 57.626, "lon": 39.894, "type": "city", "subject": "Ярославская область"},
    {"pattern": "суздалк", "name": "Суздалка", "lat": 57.598, "lon": 39.872, "type": "city", "subject": "Ярославская область"},
    {"pattern": "пятерк", "name": "Пятерка", "lat": 57.630, "lon": 39.845, "type": "city", "subject": "Ярославская область"},
    {"pattern": "ананьин", "name": "Ананьино", "lat": 57.4889, "lon": 39.9647, "type": "city", "subject": "Ярославская область"},
    {"pattern": "карабих", "name": "Карабиха", "lat": 57.50889, "lon": 39.75222, "type": "city", "subject": "Ярославская область"},
    {"pattern": "красные ткач", "name": "Красные Ткачи", "lat": 57.48333, "lon": 39.75000, "type": "city", "subject": "Ярославская область"},
    {"pattern": "белкин", "name": "Белкино", "lat": 57.45533, "lon": 39.75748, "type": "city", "subject": "Ярославская область"},
    {"pattern": "кормилицин", "name": "Кормилицино", "lat": 57.47333, "lon": 39.72472, "type": "city", "subject": "Ярославская область"},
    {"pattern": "бурмакин", "name": "Бурмакино", "lat": 57.4342, "lon": 40.3095, "type": "city", "subject": "Ярославская область"},
    {"pattern": "туношн", "name": "Туношна", "lat": 57.54405, "lon": 40.12598, "type": "city", "subject": "Ярославская область"},
    {"pattern": "цеденев", "name": "Цеденево", "lat": 57.53273, "lon": 39.90674, "type": "city", "subject": "Ярославская область"},
    {"pattern": "ямищ", "name": "Ямищи", "lat": 57.529945, "lon": 39.898503, "type": "city", "subject": "Ярославская область"},
    # Вологодская область — районы
    {"pattern": "бабаевский район", "name": "Бабаево", "lat": 59.383, "lon": 35.95, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "бабаевском районе", "name": "Бабаево", "lat": 59.383, "lon": 35.95, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "бабаевский р-н", "name": "Бабаево", "lat": 59.383, "lon": 35.95, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "бабаевском р-не", "name": "Бабаево", "lat": 59.383, "lon": 35.95, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "бабушкинский район", "name": "им. Бабушкина", "lat": 59.757, "lon": 43.133, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "бабушкинском районе", "name": "им. Бабушкина", "lat": 59.757, "lon": 43.133, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "бабушкинский р-н", "name": "им. Бабушкина", "lat": 59.757, "lon": 43.133, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "бабушкинском р-не", "name": "им. Бабушкина", "lat": 59.757, "lon": 43.133, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "белозерский район", "name": "Белозерск", "lat": 60.033, "lon": 37.783, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "белозерском районе", "name": "Белозерск", "lat": 60.033, "lon": 37.783, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "белозерский р-н", "name": "Белозерск", "lat": 60.033, "lon": 37.783, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "белозерском р-не", "name": "Белозерск", "lat": 60.033, "lon": 37.783, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вашкинский район", "name": "Липин Бор", "lat": 60.267, "lon": 37.983, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вашкинском районе", "name": "Липин Бор", "lat": 60.267, "lon": 37.983, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вашкинский р-н", "name": "Липин Бор", "lat": 60.267, "lon": 37.983, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вашкинском р-не", "name": "Липин Бор", "lat": 60.267, "lon": 37.983, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "великоустюгский район", "name": "Великий Устюг", "lat": 60.76, "lon": 46.31, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "великоустюгском районе", "name": "Великий Устюг", "lat": 60.76, "lon": 46.31, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "великоустюгский р-н", "name": "Великий Устюг", "lat": 60.76, "lon": 46.31, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "великоустюгском р-не", "name": "Великий Устюг", "lat": 60.76, "lon": 46.31, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "верховажский район", "name": "Верховажье", "lat": 60.733, "lon": 42.05, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "верховажском районе", "name": "Верховажье", "lat": 60.733, "lon": 42.05, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "верховажский р-н", "name": "Верховажье", "lat": 60.733, "lon": 42.05, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "верховажском р-не", "name": "Верховажье", "lat": 60.733, "lon": 42.05, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вожегодский район", "name": "Вожега", "lat": 60.467, "lon": 39.483, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вожегодском районе", "name": "Вожега", "lat": 60.467, "lon": 39.483, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вожегодский р-н", "name": "Вожега", "lat": 60.467, "lon": 39.483, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вожегодском р-не", "name": "Вожега", "lat": 60.467, "lon": 39.483, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вологодский район", "name": "Вологда", "lat": 59.22, "lon": 39.89, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вологодском районе", "name": "Вологда", "lat": 59.22, "lon": 39.89, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вологодский р-н", "name": "Вологда", "lat": 59.22, "lon": 39.89, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вологодском р-не", "name": "Вологда", "lat": 59.22, "lon": 39.89, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вытегорский район", "name": "Вытегра", "lat": 61.0, "lon": 36.45, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вытегорском районе", "name": "Вытегра", "lat": 61.0, "lon": 36.45, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вытегорский р-н", "name": "Вытегра", "lat": 61.0, "lon": 36.45, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "вытегорском р-не", "name": "Вытегра", "lat": 61.0, "lon": 36.45, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "грязовецкий район", "name": "Грязовец", "lat": 58.883, "lon": 40.25, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "грязовецком районе", "name": "Грязовец", "lat": 58.883, "lon": 40.25, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "грязовецкий р-н", "name": "Грязовец", "lat": 58.883, "lon": 40.25, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "грязовецком р-не", "name": "Грязовец", "lat": 58.883, "lon": 40.25, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "кадуйский район", "name": "Кадуй", "lat": 59.2, "lon": 37.15, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "кадуйском районе", "name": "Кадуй", "lat": 59.2, "lon": 37.15, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "кадуйский р-н", "name": "Кадуй", "lat": 59.2, "lon": 37.15, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "кадуйском р-не", "name": "Кадуй", "lat": 59.2, "lon": 37.15, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "кирилловский район", "name": "Кириллов", "lat": 59.86, "lon": 38.38, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "кирилловском районе", "name": "Кириллов", "lat": 59.86, "lon": 38.38, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "кирилловский р-н", "name": "Кириллов", "lat": 59.86, "lon": 38.38, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "кирилловском р-не", "name": "Кириллов", "lat": 59.86, "lon": 38.38, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "кичменгско-городецкий район", "name": "Кичменгский Городок", "lat": 60.017, "lon": 45.783, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "кичменгско-городецком районе", "name": "Кичменгский Городок", "lat": 60.017, "lon": 45.783, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "кичменгско-городецкий р-н", "name": "Кичменгский Городок", "lat": 60.017, "lon": 45.783, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "кичменгско-городецком р-не", "name": "Кичменгский Городок", "lat": 60.017, "lon": 45.783, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "междуреченский район", "name": "Шуйское", "lat": 59.367, "lon": 41.033, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "междуреченском районе", "name": "Шуйское", "lat": 59.367, "lon": 41.033, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "междуреченский р-н", "name": "Шуйское", "lat": 59.367, "lon": 41.033, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "междуреченском р-не", "name": "Шуйское", "lat": 59.367, "lon": 41.033, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "никольский район", "name": "Никольск", "lat": 59.533, "lon": 45.45, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "никольском районе", "name": "Никольск", "lat": 59.533, "lon": 45.45, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "никольский р-н", "name": "Никольск", "lat": 59.533, "lon": 45.45, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "никольском р-не", "name": "Никольск", "lat": 59.533, "lon": 45.45, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "нюксенский район", "name": "Нюксеница", "lat": 60.417, "lon": 44.233, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "нюксенском районе", "name": "Нюксеница", "lat": 60.417, "lon": 44.233, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "нюксенский р-н", "name": "Нюксеница", "lat": 60.417, "lon": 44.233, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "нюксенском р-не", "name": "Нюксеница", "lat": 60.417, "lon": 44.233, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "сокольский район", "name": "Сокол", "lat": 59.467, "lon": 40.117, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "сокольском районе", "name": "Сокол", "lat": 59.467, "lon": 40.117, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "сокольский р-н", "name": "Сокол", "lat": 59.467, "lon": 40.117, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "сокольском р-не", "name": "Сокол", "lat": 59.467, "lon": 40.117, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "сямженский район", "name": "Сямжа", "lat": 60.017, "lon": 41.083, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "сямженском районе", "name": "Сямжа", "lat": 60.017, "lon": 41.083, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "сямженский р-н", "name": "Сямжа", "lat": 60.017, "lon": 41.083, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "сямженском р-не", "name": "Сямжа", "lat": 60.017, "lon": 41.083, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "тарногский район", "name": "Тарногский Городок", "lat": 60.5, "lon": 43.567, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "тарногском районе", "name": "Тарногский Городок", "lat": 60.5, "lon": 43.567, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "тарногский р-н", "name": "Тарногский Городок", "lat": 60.5, "lon": 43.567, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "тарногском р-не", "name": "Тарногский Городок", "lat": 60.5, "lon": 43.567, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "тотемский район", "name": "Тотьма", "lat": 59.97, "lon": 42.75, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "тотемском районе", "name": "Тотьма", "lat": 59.97, "lon": 42.75, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "тотемский р-н", "name": "Тотьма", "lat": 59.97, "lon": 42.75, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "тотемском р-не", "name": "Тотьма", "lat": 59.97, "lon": 42.75, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "усть-кубинский район", "name": "Устье", "lat": 59.633, "lon": 39.733, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "усть-кубинском районе", "name": "Устье", "lat": 59.633, "lon": 39.733, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "усть-кубинский р-н", "name": "Устье", "lat": 59.633, "lon": 39.733, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "усть-кубинском р-не", "name": "Устье", "lat": 59.633, "lon": 39.733, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "устюженский район", "name": "Устюжна", "lat": 58.833, "lon": 36.433, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "устюженском районе", "name": "Устюжна", "lat": 58.833, "lon": 36.433, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "устюженский р-н", "name": "Устюжна", "lat": 58.833, "lon": 36.433, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "устюженском р-не", "name": "Устюжна", "lat": 58.833, "lon": 36.433, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "харовский район", "name": "Харовск", "lat": 59.95, "lon": 40.2, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "харовском районе", "name": "Харовск", "lat": 59.95, "lon": 40.2, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "харовский р-н", "name": "Харовск", "lat": 59.95, "lon": 40.2, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "харовском р-не", "name": "Харовск", "lat": 59.95, "lon": 40.2, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "чагодощенский район", "name": "Чагода", "lat": 59.167, "lon": 35.333, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "чагодощенском районе", "name": "Чагода", "lat": 59.167, "lon": 35.333, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "чагодощенский р-н", "name": "Чагода", "lat": 59.167, "lon": 35.333, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "чагодощенском р-не", "name": "Чагода", "lat": 59.167, "lon": 35.333, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "череповецкий район", "name": "Череповец", "lat": 59.13, "lon": 37.92, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "череповецком районе", "name": "Череповец", "lat": 59.13, "lon": 37.92, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "череповецкий р-н", "name": "Череповец", "lat": 59.13, "lon": 37.92, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "череповецком р-не", "name": "Череповец", "lat": 59.13, "lon": 37.92, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "шекснинский район", "name": "Шексна", "lat": 59.217, "lon": 38.5, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "шекснинском районе", "name": "Шексна", "lat": 59.217, "lon": 38.5, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "шекснинский р-н", "name": "Шексна", "lat": 59.217, "lon": 38.5, "type": "region", "is_region": True, "subject": "Вологодская область"},
    {"pattern": "шекснинском р-не", "name": "Шексна", "lat": 59.217, "lon": 38.5, "type": "region", "is_region": True, "subject": "Вологодская область"},

    # Вологодская область — населённые пункты не из CITY_DB
    {"pattern": "верховажье", "name": "Верховажье", "lat": 60.733, "lon": 42.05, "type": "city", "subject": "Вологодская область"},
    {"pattern": "верховажьее", "name": "Верховажье", "lat": 60.733, "lon": 42.05, "type": "city", "subject": "Вологодская область"},
    {"pattern": "вожега", "name": "Вожега", "lat": 60.467, "lon": 39.483, "type": "city", "subject": "Вологодская область"},
    {"pattern": "вожеге", "name": "Вожега", "lat": 60.467, "lon": 39.483, "type": "city", "subject": "Вологодская область"},
    {"pattern": "кадуй", "name": "Кадуй", "lat": 59.2, "lon": 37.15, "type": "city", "subject": "Вологодская область"},
    {"pattern": "кадуе", "name": "Кадуй", "lat": 59.2, "lon": 37.15, "type": "city", "subject": "Вологодская область"},
    {"pattern": "кичменгский городок", "name": "Кичменгский Городок", "lat": 60.017, "lon": 45.783, "type": "city", "subject": "Вологодская область"},
    {"pattern": "кичменгский городоке", "name": "Кичменгский Городок", "lat": 60.017, "lon": 45.783, "type": "city", "subject": "Вологодская область"},
    {"pattern": "шуйское", "name": "Шуйское", "lat": 59.367, "lon": 41.033, "type": "city", "subject": "Вологодская область"},
    {"pattern": "шуйскоее", "name": "Шуйское", "lat": 59.367, "lon": 41.033, "type": "city", "subject": "Вологодская область"},
    {"pattern": "нюксеница", "name": "Нюксеница", "lat": 60.417, "lon": 44.233, "type": "city", "subject": "Вологодская область"},
    {"pattern": "нюксенице", "name": "Нюксеница", "lat": 60.417, "lon": 44.233, "type": "city", "subject": "Вологодская область"},
    {"pattern": "сямжа", "name": "Сямжа", "lat": 60.017, "lon": 41.083, "type": "city", "subject": "Вологодская область"},
    {"pattern": "сямже", "name": "Сямжа", "lat": 60.017, "lon": 41.083, "type": "city", "subject": "Вологодская область"},
    {"pattern": "тарногский городок", "name": "Тарногский Городок", "lat": 60.5, "lon": 43.567, "type": "city", "subject": "Вологодская область"},
    {"pattern": "тарногский городоке", "name": "Тарногский Городок", "lat": 60.5, "lon": 43.567, "type": "city", "subject": "Вологодская область"},
    {"pattern": "устье", "name": "Устье", "lat": 59.633, "lon": 39.733, "type": "city", "subject": "Вологодская область"},
    {"pattern": "устьее", "name": "Устье", "lat": 59.633, "lon": 39.733, "type": "city", "subject": "Вологодская область"},
    {"pattern": "чагода", "name": "Чагода", "lat": 59.167, "lon": 35.333, "type": "city", "subject": "Вологодская область"},
    {"pattern": "чагоде", "name": "Чагода", "lat": 59.167, "lon": 35.333, "type": "city", "subject": "Вологодская область"},
    {"pattern": "шексна", "name": "Шексна", "lat": 59.217, "lon": 38.5, "type": "city", "subject": "Вологодская область"},
    {"pattern": "шексне", "name": "Шексна", "lat": 59.217, "lon": 38.5, "type": "city", "subject": "Вологодская область"},
    {"pattern": "липин бор", "name": "Липин Бор", "lat": 60.267, "lon": 37.983, "type": "city", "subject": "Вологодская область"},
    {"pattern": "липин боре", "name": "Липин Бор", "lat": 60.267, "lon": 37.983, "type": "city", "subject": "Вологодская область"},

    # Костромская область — районы
    {"pattern": "антроповский район", "name": "Антропово", "lat": 58.4, "lon": 43.0, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "антроповском районе", "name": "Антропово", "lat": 58.4, "lon": 43.0, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "антроповский р-н", "name": "Антропово", "lat": 58.4, "lon": 43.0, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "антроповском р-не", "name": "Антропово", "lat": 58.4, "lon": 43.0, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "буйский район", "name": "Буй", "lat": 58.48, "lon": 41.53, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "буйском районе", "name": "Буй", "lat": 58.48, "lon": 41.53, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "буйский р-н", "name": "Буй", "lat": 58.48, "lon": 41.53, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "буйском р-не", "name": "Буй", "lat": 58.48, "lon": 41.53, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "вохомский район", "name": "Вохма", "lat": 58.933, "lon": 46.75, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "вохомском районе", "name": "Вохма", "lat": 58.933, "lon": 46.75, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "вохомский р-н", "name": "Вохма", "lat": 58.933, "lon": 46.75, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "вохомском р-не", "name": "Вохма", "lat": 58.933, "lon": 46.75, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "галичский район", "name": "Галич", "lat": 58.38, "lon": 42.35, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "галичском районе", "name": "Галич", "lat": 58.38, "lon": 42.35, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "галичский р-н", "name": "Галич", "lat": 58.38, "lon": 42.35, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "галичском р-не", "name": "Галич", "lat": 58.38, "lon": 42.35, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "кадыйский район", "name": "Кадый", "lat": 57.783, "lon": 43.183, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "кадыйском районе", "name": "Кадый", "lat": 57.783, "lon": 43.183, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "кадыйский р-н", "name": "Кадый", "lat": 57.783, "lon": 43.183, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "кадыйском р-не", "name": "Кадый", "lat": 57.783, "lon": 43.183, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "кологривский район", "name": "Кологрив", "lat": 58.83, "lon": 44.32, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "кологривском районе", "name": "Кологрив", "lat": 58.83, "lon": 44.32, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "кологривский р-н", "name": "Кологрив", "lat": 58.83, "lon": 44.32, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "кологривском р-не", "name": "Кологрив", "lat": 58.83, "lon": 44.32, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "костромской район", "name": "Кострома", "lat": 57.77, "lon": 40.93, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "костромской районе", "name": "Кострома", "lat": 57.77, "lon": 40.93, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "костромской р-н", "name": "Кострома", "lat": 57.77, "lon": 40.93, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "костромской р-не", "name": "Кострома", "lat": 57.77, "lon": 40.93, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "красносельский район", "name": "Красное-на-Волге", "lat": 57.517, "lon": 41.233, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "красносельском районе", "name": "Красное-на-Волге", "lat": 57.517, "lon": 41.233, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "красносельский р-н", "name": "Красное-на-Волге", "lat": 57.517, "lon": 41.233, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "красносельском р-не", "name": "Красное-на-Волге", "lat": 57.517, "lon": 41.233, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "макарьевский район", "name": "Макарьев", "lat": 57.88, "lon": 43.8, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "макарьевском районе", "name": "Макарьев", "lat": 57.88, "lon": 43.8, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "макарьевский р-н", "name": "Макарьев", "lat": 57.88, "lon": 43.8, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "макарьевском р-не", "name": "Макарьев", "lat": 57.88, "lon": 43.8, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "мантуровский район", "name": "Мантурово", "lat": 58.33, "lon": 44.76, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "мантуровском районе", "name": "Мантурово", "lat": 58.33, "lon": 44.76, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "мантуровский р-н", "name": "Мантурово", "lat": 58.33, "lon": 44.76, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "мантуровском р-не", "name": "Мантурово", "lat": 58.33, "lon": 44.76, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "межевской район", "name": "Георгиевское", "lat": 58.733, "lon": 45.017, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "межевской районе", "name": "Георгиевское", "lat": 58.733, "lon": 45.017, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "межевской р-н", "name": "Георгиевское", "lat": 58.733, "lon": 45.017, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "межевской р-не", "name": "Георгиевское", "lat": 58.733, "lon": 45.017, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "нейский район", "name": "Нея", "lat": 58.28, "lon": 43.87, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "нейском районе", "name": "Нея", "lat": 58.28, "lon": 43.87, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "нейский р-н", "name": "Нея", "lat": 58.28, "lon": 43.87, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "нейском р-не", "name": "Нея", "lat": 58.28, "lon": 43.87, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "нерехтский район", "name": "Нерехта", "lat": 57.46, "lon": 40.57, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "нерехтском районе", "name": "Нерехта", "lat": 57.46, "lon": 40.57, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "нерехтский р-н", "name": "Нерехта", "lat": 57.46, "lon": 40.57, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "нерехтском р-не", "name": "Нерехта", "lat": 57.46, "lon": 40.57, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "октябрьский район", "name": "Боговарово", "lat": 58.817, "lon": 41.467, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "октябрьском районе", "name": "Боговарово", "lat": 58.817, "lon": 41.467, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "октябрьский р-н", "name": "Боговарово", "lat": 58.817, "lon": 41.467, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "октябрьском р-не", "name": "Боговарово", "lat": 58.817, "lon": 41.467, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "островский район", "name": "Островское", "lat": 57.8, "lon": 42.233, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "островском районе", "name": "Островское", "lat": 57.8, "lon": 42.233, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "островский р-н", "name": "Островское", "lat": 57.8, "lon": 42.233, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "островском р-не", "name": "Островское", "lat": 57.8, "lon": 42.233, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "павинский район", "name": "Павино", "lat": 58.967, "lon": 46.2, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "павинском районе", "name": "Павино", "lat": 58.967, "lon": 46.2, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "павинский р-н", "name": "Павино", "lat": 58.967, "lon": 46.2, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "павинском р-не", "name": "Павино", "lat": 58.967, "lon": 46.2, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "парфеньевский район", "name": "Парфеньево", "lat": 58.483, "lon": 43.4, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "парфеньевском районе", "name": "Парфеньево", "lat": 58.483, "lon": 43.4, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "парфеньевский р-н", "name": "Парфеньево", "lat": 58.483, "lon": 43.4, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "парфеньевском р-не", "name": "Парфеньево", "lat": 58.483, "lon": 43.4, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "поназыревский район", "name": "Поназырево", "lat": 58.35, "lon": 46.3, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "поназыревском районе", "name": "Поназырево", "lat": 58.35, "lon": 46.3, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "поназыревский р-н", "name": "Поназырево", "lat": 58.35, "lon": 46.3, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "поназыревском р-не", "name": "Поназырево", "lat": 58.35, "lon": 46.3, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "пыщугский район", "name": "Пыщуг", "lat": 58.883, "lon": 45.633, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "пыщугском районе", "name": "Пыщуг", "lat": 58.883, "lon": 45.633, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "пыщугский р-н", "name": "Пыщуг", "lat": 58.883, "lon": 45.633, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "пыщугском р-не", "name": "Пыщуг", "lat": 58.883, "lon": 45.633, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "солигаличский район", "name": "Солигалич", "lat": 59.08, "lon": 42.29, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "солигаличском районе", "name": "Солигалич", "lat": 59.08, "lon": 42.29, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "солигаличский р-н", "name": "Солигалич", "lat": 59.08, "lon": 42.29, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "солигаличском р-не", "name": "Солигалич", "lat": 59.08, "lon": 42.29, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "судиславский район", "name": "Судиславль", "lat": 57.883, "lon": 41.7, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "судиславском районе", "name": "Судиславль", "lat": 57.883, "lon": 41.7, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "судиславский р-н", "name": "Судиславль", "lat": 57.883, "lon": 41.7, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "судиславском р-не", "name": "Судиславль", "lat": 57.883, "lon": 41.7, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "сусанинский район", "name": "Сусанино", "lat": 58.15, "lon": 41.6, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "сусанинском районе", "name": "Сусанино", "lat": 58.15, "lon": 41.6, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "сусанинский р-н", "name": "Сусанино", "lat": 58.15, "lon": 41.6, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "сусанинском р-не", "name": "Сусанино", "lat": 58.15, "lon": 41.6, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "чухломский район", "name": "Чухлома", "lat": 58.75, "lon": 42.68, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "чухломском районе", "name": "Чухлома", "lat": 58.75, "lon": 42.68, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "чухломский р-н", "name": "Чухлома", "lat": 58.75, "lon": 42.68, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "чухломском р-не", "name": "Чухлома", "lat": 58.75, "lon": 42.68, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "шарьинский район", "name": "Шарья", "lat": 58.37, "lon": 45.52, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "шарьинском районе", "name": "Шарья", "lat": 58.37, "lon": 45.52, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "шарьинский р-н", "name": "Шарья", "lat": 58.37, "lon": 45.52, "type": "region", "is_region": True, "subject": "Костромская область"},
    {"pattern": "шарьинском р-не", "name": "Шарья", "lat": 58.37, "lon": 45.52, "type": "region", "is_region": True, "subject": "Костромская область"},

    # Костромская область — населённые пункты не из CITY_DB
    {"pattern": "антропово", "name": "Антропово", "lat": 58.4, "lon": 43.0, "type": "city", "subject": "Костромская область"},
    {"pattern": "антропове", "name": "Антропово", "lat": 58.4, "lon": 43.0, "type": "city", "subject": "Костромская область"},
    {"pattern": "вохма", "name": "Вохма", "lat": 58.933, "lon": 46.75, "type": "city", "subject": "Костромская область"},
    {"pattern": "вохме", "name": "Вохма", "lat": 58.933, "lon": 46.75, "type": "city", "subject": "Костромская область"},
    {"pattern": "кадый", "name": "Кадый", "lat": 57.783, "lon": 43.183, "type": "city", "subject": "Костромская область"},
    {"pattern": "кадые", "name": "Кадый", "lat": 57.783, "lon": 43.183, "type": "city", "subject": "Костромская область"},
    {"pattern": "красное-на-волге", "name": "Красное-на-Волге", "lat": 57.517, "lon": 41.233, "type": "city", "subject": "Костромская область"},
    {"pattern": "красное-на-волгее", "name": "Красное-на-Волге", "lat": 57.517, "lon": 41.233, "type": "city", "subject": "Костромская область"},
    {"pattern": "георгиевское", "name": "Георгиевское", "lat": 58.733, "lon": 45.017, "type": "city", "subject": "Костромская область"},
    {"pattern": "георгиевскоее", "name": "Георгиевское", "lat": 58.733, "lon": 45.017, "type": "city", "subject": "Костромская область"},
    {"pattern": "боговарово", "name": "Боговарово", "lat": 58.817, "lon": 41.467, "type": "city", "subject": "Костромская область"},
    {"pattern": "боговарове", "name": "Боговарово", "lat": 58.817, "lon": 41.467, "type": "city", "subject": "Костромская область"},
    {"pattern": "островское", "name": "Островское", "lat": 57.8, "lon": 42.233, "type": "city", "subject": "Костромская область"},
    {"pattern": "островскоее", "name": "Островское", "lat": 57.8, "lon": 42.233, "type": "city", "subject": "Костромская область"},
    {"pattern": "павино", "name": "Павино", "lat": 58.967, "lon": 46.2, "type": "city", "subject": "Костромская область"},
    {"pattern": "павине", "name": "Павино", "lat": 58.967, "lon": 46.2, "type": "city", "subject": "Костромская область"},
    {"pattern": "парфеньево", "name": "Парфеньево", "lat": 58.483, "lon": 43.4, "type": "city", "subject": "Костромская область"},
    {"pattern": "парфеньеве", "name": "Парфеньево", "lat": 58.483, "lon": 43.4, "type": "city", "subject": "Костромская область"},
    {"pattern": "поназырево", "name": "Поназырево", "lat": 58.35, "lon": 46.3, "type": "city", "subject": "Костромская область"},
    {"pattern": "поназыреве", "name": "Поназырево", "lat": 58.35, "lon": 46.3, "type": "city", "subject": "Костромская область"},
    {"pattern": "пыщуг", "name": "Пыщуг", "lat": 58.883, "lon": 45.633, "type": "city", "subject": "Костромская область"},
    {"pattern": "пыщуге", "name": "Пыщуг", "lat": 58.883, "lon": 45.633, "type": "city", "subject": "Костромская область"},
    {"pattern": "судиславль", "name": "Судиславль", "lat": 57.883, "lon": 41.7, "type": "city", "subject": "Костромская область"},
    {"pattern": "судиславле", "name": "Судиславль", "lat": 57.883, "lon": 41.7, "type": "city", "subject": "Костромская область"},
    {"pattern": "сусанино", "name": "Сусанино", "lat": 58.15, "lon": 41.6, "type": "city", "subject": "Костромская область"},
    {"pattern": "сусанине", "name": "Сусанино", "lat": 58.15, "lon": 41.6, "type": "city", "subject": "Костромская область"},

    # Ивановская область — районы
    {"pattern": "верхнеландеховский район", "name": "Верхний Ландех", "lat": 56.833, "lon": 42.583, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "верхнеландеховском районе", "name": "Верхний Ландех", "lat": 56.833, "lon": 42.583, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "верхнеландеховский р-н", "name": "Верхний Ландех", "lat": 56.833, "lon": 42.583, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "верхнеландеховском р-не", "name": "Верхний Ландех", "lat": 56.833, "lon": 42.583, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "вичугский район", "name": "Вичуга", "lat": 57.21, "lon": 41.91, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "вичугском районе", "name": "Вичуга", "lat": 57.21, "lon": 41.91, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "вичугский р-н", "name": "Вичуга", "lat": 57.21, "lon": 41.91, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "вичугском р-не", "name": "Вичуга", "lat": 57.21, "lon": 41.91, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "гаврилово-посадский район", "name": "Гаврилов Посад", "lat": 56.567, "lon": 40.117, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "гаврилово-посадском районе", "name": "Гаврилов Посад", "lat": 56.567, "lon": 40.117, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "гаврилово-посадский р-н", "name": "Гаврилов Посад", "lat": 56.567, "lon": 40.117, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "гаврилово-посадском р-не", "name": "Гаврилов Посад", "lat": 56.567, "lon": 40.117, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "заволжский район", "name": "Заволжск", "lat": 57.483, "lon": 42.133, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "заволжском районе", "name": "Заволжск", "lat": 57.483, "lon": 42.133, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "заволжский р-н", "name": "Заволжск", "lat": 57.483, "lon": 42.133, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "заволжском р-не", "name": "Заволжск", "lat": 57.483, "lon": 42.133, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "ивановский район", "name": "Иваново", "lat": 57.0, "lon": 40.97, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "ивановском районе", "name": "Иваново", "lat": 57.0, "lon": 40.97, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "ивановский р-н", "name": "Иваново", "lat": 57.0, "lon": 40.97, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "ивановском р-не", "name": "Иваново", "lat": 57.0, "lon": 40.97, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "ильинский район", "name": "Ильинское-Хованское", "lat": 56.967, "lon": 39.767, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "ильинском районе", "name": "Ильинское-Хованское", "lat": 56.967, "lon": 39.767, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "ильинский р-н", "name": "Ильинское-Хованское", "lat": 56.967, "lon": 39.767, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "ильинском р-не", "name": "Ильинское-Хованское", "lat": 56.967, "lon": 39.767, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "кинешемский район", "name": "Кинешма", "lat": 57.45, "lon": 42.13, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "кинешемском районе", "name": "Кинешма", "lat": 57.45, "lon": 42.13, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "кинешемский р-н", "name": "Кинешма", "lat": 57.45, "lon": 42.13, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "кинешемском р-не", "name": "Кинешма", "lat": 57.45, "lon": 42.13, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "комсомольский район", "name": "Комсомольск", "lat": 57.017, "lon": 40.367, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "комсомольском районе", "name": "Комсомольск", "lat": 57.017, "lon": 40.367, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "комсомольский р-н", "name": "Комсомольск", "lat": 57.017, "lon": 40.367, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "комсомольском р-не", "name": "Комсомольск", "lat": 57.017, "lon": 40.367, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "лежневский район", "name": "Лежнево", "lat": 56.767, "lon": 40.883, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "лежневском районе", "name": "Лежнево", "lat": 56.767, "lon": 40.883, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "лежневский р-н", "name": "Лежнево", "lat": 56.767, "lon": 40.883, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "лежневском р-не", "name": "Лежнево", "lat": 56.767, "lon": 40.883, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "лухский район", "name": "Лух", "lat": 57.0, "lon": 42.25, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "лухском районе", "name": "Лух", "lat": 57.0, "lon": 42.25, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "лухский р-н", "name": "Лух", "lat": 57.0, "lon": 42.25, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "лухском р-не", "name": "Лух", "lat": 57.0, "lon": 42.25, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "палехский район", "name": "Палех", "lat": 56.8, "lon": 41.85, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "палехском районе", "name": "Палех", "lat": 56.8, "lon": 41.85, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "палехский р-н", "name": "Палех", "lat": 56.8, "lon": 41.85, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "палехском р-не", "name": "Палех", "lat": 56.8, "lon": 41.85, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "пестяковский район", "name": "Пестяки", "lat": 56.7, "lon": 42.667, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "пестяковском районе", "name": "Пестяки", "lat": 56.7, "lon": 42.667, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "пестяковский р-н", "name": "Пестяки", "lat": 56.7, "lon": 42.667, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "пестяковском р-не", "name": "Пестяки", "lat": 56.7, "lon": 42.667, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "приволжский район", "name": "Приволжск", "lat": 57.383, "lon": 41.283, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "приволжском районе", "name": "Приволжск", "lat": 57.383, "lon": 41.283, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "приволжский р-н", "name": "Приволжск", "lat": 57.383, "lon": 41.283, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "приволжском р-не", "name": "Приволжск", "lat": 57.383, "lon": 41.283, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "пучежский район", "name": "Пучеж", "lat": 56.983, "lon": 43.167, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "пучежском районе", "name": "Пучеж", "lat": 56.983, "lon": 43.167, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "пучежский р-н", "name": "Пучеж", "lat": 56.983, "lon": 43.167, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "пучежском р-не", "name": "Пучеж", "lat": 56.983, "lon": 43.167, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "родниковский район", "name": "Родники", "lat": 57.1, "lon": 41.73, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "родниковском районе", "name": "Родники", "lat": 57.1, "lon": 41.73, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "родниковский р-н", "name": "Родники", "lat": 57.1, "lon": 41.73, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "родниковском р-не", "name": "Родники", "lat": 57.1, "lon": 41.73, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "савинский район", "name": "Савино", "lat": 56.583, "lon": 41.217, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "савинском районе", "name": "Савино", "lat": 56.583, "lon": 41.217, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "савинский р-н", "name": "Савино", "lat": 56.583, "lon": 41.217, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "савинском р-не", "name": "Савино", "lat": 56.583, "lon": 41.217, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "тейковский район", "name": "Тейково", "lat": 56.85, "lon": 40.55, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "тейковском районе", "name": "Тейково", "lat": 56.85, "lon": 40.55, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "тейковский р-н", "name": "Тейково", "lat": 56.85, "lon": 40.55, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "тейковском р-не", "name": "Тейково", "lat": 56.85, "lon": 40.55, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "фурмановский район", "name": "Фурманов", "lat": 57.25, "lon": 41.1, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "фурмановском районе", "name": "Фурманов", "lat": 57.25, "lon": 41.1, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "фурмановский р-н", "name": "Фурманов", "lat": 57.25, "lon": 41.1, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "фурмановском р-не", "name": "Фурманов", "lat": 57.25, "lon": 41.1, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "шуйский район", "name": "Шуя", "lat": 56.85, "lon": 41.38, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "шуйском районе", "name": "Шуя", "lat": 56.85, "lon": 41.38, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "шуйский р-н", "name": "Шуя", "lat": 56.85, "lon": 41.38, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "шуйском р-не", "name": "Шуя", "lat": 56.85, "lon": 41.38, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "южский район", "name": "Южа", "lat": 56.583, "lon": 42.017, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "южском районе", "name": "Южа", "lat": 56.583, "lon": 42.017, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "южский р-н", "name": "Южа", "lat": 56.583, "lon": 42.017, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "южском р-не", "name": "Южа", "lat": 56.583, "lon": 42.017, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "юрьевецкий район", "name": "Юрьевец", "lat": 57.317, "lon": 43.1, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "юрьевецком районе", "name": "Юрьевец", "lat": 57.317, "lon": 43.1, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "юрьевецкий р-н", "name": "Юрьевец", "lat": 57.317, "lon": 43.1, "type": "region", "is_region": True, "subject": "Ивановская область"},
    {"pattern": "юрьевецком р-не", "name": "Юрьевец", "lat": 57.317, "lon": 43.1, "type": "region", "is_region": True, "subject": "Ивановская область"},

    # Ивановская область — населённые пункты не из CITY_DB
    {"pattern": "верхний ландех", "name": "Верхний Ландех", "lat": 56.833, "lon": 42.583, "type": "city", "subject": "Ивановская область"},
    {"pattern": "верхний ландехе", "name": "Верхний Ландех", "lat": 56.833, "lon": 42.583, "type": "city", "subject": "Ивановская область"},
    {"pattern": "ильинское-хованское", "name": "Ильинское-Хованское", "lat": 56.967, "lon": 39.767, "type": "city", "subject": "Ивановская область"},
    {"pattern": "ильинское-хованскоее", "name": "Ильинское-Хованское", "lat": 56.967, "lon": 39.767, "type": "city", "subject": "Ивановская область"},
    {"pattern": "лежнево", "name": "Лежнево", "lat": 56.767, "lon": 40.883, "type": "city", "subject": "Ивановская область"},
    {"pattern": "лежневе", "name": "Лежнево", "lat": 56.767, "lon": 40.883, "type": "city", "subject": "Ивановская область"},
    {"pattern": "лух", "name": "Лух", "lat": 57.0, "lon": 42.25, "type": "city", "subject": "Ивановская область"},
    {"pattern": "лухе", "name": "Лух", "lat": 57.0, "lon": 42.25, "type": "city", "subject": "Ивановская область"},
    {"pattern": "палех", "name": "Палех", "lat": 56.8, "lon": 41.85, "type": "city", "subject": "Ивановская область"},
    {"pattern": "палехе", "name": "Палех", "lat": 56.8, "lon": 41.85, "type": "city", "subject": "Ивановская область"},
    {"pattern": "пестяки", "name": "Пестяки", "lat": 56.7, "lon": 42.667, "type": "city", "subject": "Ивановская область"},
    {"pattern": "пестякие", "name": "Пестяки", "lat": 56.7, "lon": 42.667, "type": "city", "subject": "Ивановская область"},
    {"pattern": "пучеж", "name": "Пучеж", "lat": 56.983, "lon": 43.167, "type": "city", "subject": "Ивановская область"},
    {"pattern": "пучеже", "name": "Пучеж", "lat": 56.983, "lon": 43.167, "type": "city", "subject": "Ивановская область"},
    {"pattern": "родники", "name": "Родники", "lat": 57.1, "lon": 41.73, "type": "city", "subject": "Ивановская область"},
    {"pattern": "родникие", "name": "Родники", "lat": 57.1, "lon": 41.73, "type": "city", "subject": "Ивановская область"},
    {"pattern": "савино", "name": "Савино", "lat": 56.583, "lon": 41.217, "type": "city", "subject": "Ивановская область"},
    {"pattern": "савине", "name": "Савино", "lat": 56.583, "lon": 41.217, "type": "city", "subject": "Ивановская область"},
    {"pattern": "южа", "name": "Южа", "lat": 56.583, "lon": 42.017, "type": "city", "subject": "Ивановская область"},
    {"pattern": "юже", "name": "Южа", "lat": 56.583, "lon": 42.017, "type": "city", "subject": "Ивановская область"},

    # Владимирская область — районы
    {"pattern": "александровский район", "name": "Александров", "lat": 56.4, "lon": 38.73, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "александровском районе", "name": "Александров", "lat": 56.4, "lon": 38.73, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "александровский р-н", "name": "Александров", "lat": 56.4, "lon": 38.73, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "александровском р-не", "name": "Александров", "lat": 56.4, "lon": 38.73, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "вязниковский район", "name": "Вязники", "lat": 56.25, "lon": 42.15, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "вязниковском районе", "name": "Вязники", "lat": 56.25, "lon": 42.15, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "вязниковский р-н", "name": "Вязники", "lat": 56.25, "lon": 42.15, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "вязниковском р-не", "name": "Вязники", "lat": 56.25, "lon": 42.15, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "гороховецкий район", "name": "Гороховец", "lat": 56.2, "lon": 42.7, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "гороховецком районе", "name": "Гороховец", "lat": 56.2, "lon": 42.7, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "гороховецкий р-н", "name": "Гороховец", "lat": 56.2, "lon": 42.7, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "гороховецком р-не", "name": "Гороховец", "lat": 56.2, "lon": 42.7, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "гусь-хрустальный район", "name": "Гусь-Хрустальный", "lat": 55.62, "lon": 40.65, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "гусь-хрустальный районе", "name": "Гусь-Хрустальный", "lat": 55.62, "lon": 40.65, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "гусь-хрустальный р-н", "name": "Гусь-Хрустальный", "lat": 55.62, "lon": 40.65, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "гусь-хрустальный р-не", "name": "Гусь-Хрустальный", "lat": 55.62, "lon": 40.65, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "камешковский район", "name": "Камешково", "lat": 56.35, "lon": 40.983, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "камешковском районе", "name": "Камешково", "lat": 56.35, "lon": 40.983, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "камешковский р-н", "name": "Камешково", "lat": 56.35, "lon": 40.983, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "камешковском р-не", "name": "Камешково", "lat": 56.35, "lon": 40.983, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "киржачский район", "name": "Киржач", "lat": 56.15, "lon": 38.86, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "киржачском районе", "name": "Киржач", "lat": 56.15, "lon": 38.86, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "киржачский р-н", "name": "Киржач", "lat": 56.15, "lon": 38.86, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "киржачском р-не", "name": "Киржач", "lat": 56.15, "lon": 38.86, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "ковровский район", "name": "Ковров", "lat": 56.36, "lon": 41.32, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "ковровском районе", "name": "Ковров", "lat": 56.36, "lon": 41.32, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "ковровский р-н", "name": "Ковров", "lat": 56.36, "lon": 41.32, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "ковровском р-не", "name": "Ковров", "lat": 56.36, "lon": 41.32, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "кольчугинский район", "name": "Кольчугино", "lat": 56.3, "lon": 39.38, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "кольчугинском районе", "name": "Кольчугино", "lat": 56.3, "lon": 39.38, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "кольчугинский р-н", "name": "Кольчугино", "lat": 56.3, "lon": 39.38, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "кольчугинском р-не", "name": "Кольчугино", "lat": 56.3, "lon": 39.38, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "меленковский район", "name": "Меленки", "lat": 55.33, "lon": 41.63, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "меленковском районе", "name": "Меленки", "lat": 55.33, "lon": 41.63, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "меленковский р-н", "name": "Меленки", "lat": 55.33, "lon": 41.63, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "меленковском р-не", "name": "Меленки", "lat": 55.33, "lon": 41.63, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "муромский район", "name": "Муром", "lat": 55.57, "lon": 42.04, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "муромском районе", "name": "Муром", "lat": 55.57, "lon": 42.04, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "муромский р-н", "name": "Муром", "lat": 55.57, "lon": 42.04, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "муромском р-не", "name": "Муром", "lat": 55.57, "lon": 42.04, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "петушинский район", "name": "Петушки", "lat": 55.93, "lon": 39.46, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "петушинском районе", "name": "Петушки", "lat": 55.93, "lon": 39.46, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "петушинский р-н", "name": "Петушки", "lat": 55.93, "lon": 39.46, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "петушинском р-не", "name": "Петушки", "lat": 55.93, "lon": 39.46, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "селивановский район", "name": "Красная Горбатка", "lat": 55.867, "lon": 41.767, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "селивановском районе", "name": "Красная Горбатка", "lat": 55.867, "lon": 41.767, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "селивановский р-н", "name": "Красная Горбатка", "lat": 55.867, "lon": 41.767, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "селивановском р-не", "name": "Красная Горбатка", "lat": 55.867, "lon": 41.767, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "собинский район", "name": "Собинка", "lat": 55.98, "lon": 40.0, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "собинском районе", "name": "Собинка", "lat": 55.98, "lon": 40.0, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "собинский р-н", "name": "Собинка", "lat": 55.98, "lon": 40.0, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "собинском р-не", "name": "Собинка", "lat": 55.98, "lon": 40.0, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "судогодский район", "name": "Судогда", "lat": 55.95, "lon": 40.85, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "судогодском районе", "name": "Судогда", "lat": 55.95, "lon": 40.85, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "судогодский р-н", "name": "Судогда", "lat": 55.95, "lon": 40.85, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "судогодском р-не", "name": "Судогда", "lat": 55.95, "lon": 40.85, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "суздальский район", "name": "Суздаль", "lat": 56.42, "lon": 40.45, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "суздальском районе", "name": "Суздаль", "lat": 56.42, "lon": 40.45, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "суздальский р-н", "name": "Суздаль", "lat": 56.42, "lon": 40.45, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "суздальском р-не", "name": "Суздаль", "lat": 56.42, "lon": 40.45, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "юрьев-польский район", "name": "Юрьев-Польский", "lat": 56.5, "lon": 39.68, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "юрьев-польском районе", "name": "Юрьев-Польский", "lat": 56.5, "lon": 39.68, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "юрьев-польский р-н", "name": "Юрьев-Польский", "lat": 56.5, "lon": 39.68, "type": "region", "is_region": True, "subject": "Владимирская область"},
    {"pattern": "юрьев-польском р-не", "name": "Юрьев-Польский", "lat": 56.5, "lon": 39.68, "type": "region", "is_region": True, "subject": "Владимирская область"},

    # Владимирская область — населённые пункты не из CITY_DB
    {"pattern": "сима", "name": "Сима", "lat": 56.51, "lon": 39.58, "type": "city", "subject": "Владимирская область"},
    {"pattern": "симе", "name": "Сима", "lat": 56.51, "lon": 39.58, "type": "city", "subject": "Владимирская область"},
    {"pattern": "симу", "name": "Сима", "lat": 56.51, "lon": 39.58, "type": "city", "subject": "Владимирская область"},
    {"pattern": "симой", "name": "Сима", "lat": 56.51, "lon": 39.58, "type": "city", "subject": "Владимирская область"},
    {"pattern": "симы", "name": "Сима", "lat": 56.51, "lon": 39.58, "type": "city", "subject": "Владимирская область"},
    {"pattern": "красная горбатка", "name": "Красная Горбатка", "lat": 55.867, "lon": 41.767, "type": "city", "subject": "Владимирская область"},
    {"pattern": "красная горбатке", "name": "Красная Горбатка", "lat": 55.867, "lon": 41.767, "type": "city", "subject": "Владимирская область"},

    # Тверская область — районы
    {"pattern": "андреапольский район", "name": "Андреаполь", "lat": 56.65, "lon": 32.27, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "андреапольском районе", "name": "Андреаполь", "lat": 56.65, "lon": 32.27, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "андреапольский р-н", "name": "Андреаполь", "lat": 56.65, "lon": 32.27, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "андреапольском р-не", "name": "Андреаполь", "lat": 56.65, "lon": 32.27, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "бежецкий район", "name": "Бежецк", "lat": 57.78, "lon": 36.7, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "бежецком районе", "name": "Бежецк", "lat": 57.78, "lon": 36.7, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "бежецкий р-н", "name": "Бежецк", "lat": 57.78, "lon": 36.7, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "бежецком р-не", "name": "Бежецк", "lat": 57.78, "lon": 36.7, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "бельский район", "name": "Белый", "lat": 55.83, "lon": 32.93, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "бельском районе", "name": "Белый", "lat": 55.83, "lon": 32.93, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "бельский р-н", "name": "Белый", "lat": 55.83, "lon": 32.93, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "бельском р-не", "name": "Белый", "lat": 55.83, "lon": 32.93, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "бологовский район", "name": "Бологое", "lat": 57.88, "lon": 34.05, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "бологовском районе", "name": "Бологое", "lat": 57.88, "lon": 34.05, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "бологовский р-н", "name": "Бологое", "lat": 57.88, "lon": 34.05, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "бологовском р-не", "name": "Бологое", "lat": 57.88, "lon": 34.05, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "весьегонский район", "name": "Весьегонск", "lat": 58.65, "lon": 37.27, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "весьегонском районе", "name": "Весьегонск", "lat": 58.65, "lon": 37.27, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "весьегонский р-н", "name": "Весьегонск", "lat": 58.65, "lon": 37.27, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "весьегонском р-не", "name": "Весьегонск", "lat": 58.65, "lon": 37.27, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "вышневолоцкий район", "name": "Вышний Волочёк", "lat": 57.58, "lon": 34.57, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "вышневолоцком районе", "name": "Вышний Волочёк", "lat": 57.58, "lon": 34.57, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "вышневолоцкий р-н", "name": "Вышний Волочёк", "lat": 57.58, "lon": 34.57, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "вышневолоцком р-не", "name": "Вышний Волочёк", "lat": 57.58, "lon": 34.57, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "жарковский район", "name": "Жарковский", "lat": 55.85, "lon": 32.433, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "жарковском районе", "name": "Жарковский", "lat": 55.85, "lon": 32.433, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "жарковский р-н", "name": "Жарковский", "lat": 55.85, "lon": 32.433, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "жарковском р-не", "name": "Жарковский", "lat": 55.85, "lon": 32.433, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "западнодвинский район", "name": "Западная Двина", "lat": 56.27, "lon": 32.08, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "западнодвинском районе", "name": "Западная Двина", "lat": 56.27, "lon": 32.08, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "западнодвинский р-н", "name": "Западная Двина", "lat": 56.27, "lon": 32.08, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "западнодвинском р-не", "name": "Западная Двина", "lat": 56.27, "lon": 32.08, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "зубцовский район", "name": "Зубцов", "lat": 56.17, "lon": 34.58, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "зубцовском районе", "name": "Зубцов", "lat": 56.17, "lon": 34.58, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "зубцовский р-н", "name": "Зубцов", "lat": 56.17, "lon": 34.58, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "зубцовском р-не", "name": "Зубцов", "lat": 56.17, "lon": 34.58, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "калининский район", "name": "Тверь", "lat": 56.86, "lon": 35.92, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "калининском районе", "name": "Тверь", "lat": 56.86, "lon": 35.92, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "калининский р-н", "name": "Тверь", "lat": 56.86, "lon": 35.92, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "калининском р-не", "name": "Тверь", "lat": 56.86, "lon": 35.92, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "калязинский район", "name": "Калязин", "lat": 57.24, "lon": 37.85, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "калязинском районе", "name": "Калязин", "lat": 57.24, "lon": 37.85, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "калязинский р-н", "name": "Калязин", "lat": 57.24, "lon": 37.85, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "калязинском р-не", "name": "Калязин", "lat": 57.24, "lon": 37.85, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кашинский район", "name": "Кашин", "lat": 57.36, "lon": 37.61, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кашинском районе", "name": "Кашин", "lat": 57.36, "lon": 37.61, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кашинский р-н", "name": "Кашин", "lat": 57.36, "lon": 37.61, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кашинском р-не", "name": "Кашин", "lat": 57.36, "lon": 37.61, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кесовогорский район", "name": "Кесова Гора", "lat": 57.583, "lon": 37.283, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кесовогорском районе", "name": "Кесова Гора", "lat": 57.583, "lon": 37.283, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кесовогорский р-н", "name": "Кесова Гора", "lat": 57.583, "lon": 37.283, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кесовогорском р-не", "name": "Кесова Гора", "lat": 57.583, "lon": 37.283, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кимрский район", "name": "Кимры", "lat": 56.87, "lon": 37.35, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кимрском районе", "name": "Кимры", "lat": 56.87, "lon": 37.35, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кимрский р-н", "name": "Кимры", "lat": 56.87, "lon": 37.35, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кимрском р-не", "name": "Кимры", "lat": 56.87, "lon": 37.35, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "конаковский район", "name": "Конаково", "lat": 56.7, "lon": 36.78, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "конаковском районе", "name": "Конаково", "lat": 56.7, "lon": 36.78, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "конаковский р-н", "name": "Конаково", "lat": 56.7, "lon": 36.78, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "конаковском р-не", "name": "Конаково", "lat": 56.7, "lon": 36.78, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "краснохолмский район", "name": "Красный Холм", "lat": 58.06, "lon": 37.12, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "краснохолмском районе", "name": "Красный Холм", "lat": 58.06, "lon": 37.12, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "краснохолмский р-н", "name": "Красный Холм", "lat": 58.06, "lon": 37.12, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "краснохолмском р-не", "name": "Красный Холм", "lat": 58.06, "lon": 37.12, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кувшиновский район", "name": "Кувшиново", "lat": 57.03, "lon": 34.17, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кувшиновском районе", "name": "Кувшиново", "lat": 57.03, "lon": 34.17, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кувшиновский р-н", "name": "Кувшиново", "lat": 57.03, "lon": 34.17, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "кувшиновском р-не", "name": "Кувшиново", "lat": 57.03, "lon": 34.17, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "лесной район", "name": "Лесное", "lat": 58.283, "lon": 35.517, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "лесном районе", "name": "Лесное", "lat": 58.283, "lon": 35.517, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "лесной р-н", "name": "Лесное", "lat": 58.283, "lon": 35.517, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "лесном р-не", "name": "Лесное", "lat": 58.283, "lon": 35.517, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "лихославльский район", "name": "Лихославль", "lat": 57.12, "lon": 35.47, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "лихославльском районе", "name": "Лихославль", "lat": 57.12, "lon": 35.47, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "лихославльский р-н", "name": "Лихославль", "lat": 57.12, "lon": 35.47, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "лихославльском р-не", "name": "Лихославль", "lat": 57.12, "lon": 35.47, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "максатихинский район", "name": "Максатиха", "lat": 57.8, "lon": 35.883, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "максатихинском районе", "name": "Максатиха", "lat": 57.8, "lon": 35.883, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "максатихинский р-н", "name": "Максатиха", "lat": 57.8, "lon": 35.883, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "максатихинском р-не", "name": "Максатиха", "lat": 57.8, "lon": 35.883, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "молоковский район", "name": "Молоково", "lat": 58.167, "lon": 36.767, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "молоковском районе", "name": "Молоково", "lat": 58.167, "lon": 36.767, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "молоковский р-н", "name": "Молоково", "lat": 58.167, "lon": 36.767, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "молоковском р-не", "name": "Молоково", "lat": 58.167, "lon": 36.767, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "нелидовский район", "name": "Нелидово", "lat": 56.22, "lon": 32.78, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "нелидовском районе", "name": "Нелидово", "lat": 56.22, "lon": 32.78, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "нелидовский р-н", "name": "Нелидово", "lat": 56.22, "lon": 32.78, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "нелидовском р-не", "name": "Нелидово", "lat": 56.22, "lon": 32.78, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "оленинский район", "name": "Оленино", "lat": 56.2, "lon": 33.467, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "оленинском районе", "name": "Оленино", "lat": 56.2, "lon": 33.467, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "оленинский р-н", "name": "Оленино", "lat": 56.2, "lon": 33.467, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "оленинском р-не", "name": "Оленино", "lat": 56.2, "lon": 33.467, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "осташковский район", "name": "Осташков", "lat": 57.15, "lon": 33.1, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "осташковском районе", "name": "Осташков", "lat": 57.15, "lon": 33.1, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "осташковский р-н", "name": "Осташков", "lat": 57.15, "lon": 33.1, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "осташковском р-не", "name": "Осташков", "lat": 57.15, "lon": 33.1, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "пеновский район", "name": "Пено", "lat": 56.917, "lon": 32.733, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "пеновском районе", "name": "Пено", "lat": 56.917, "lon": 32.733, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "пеновский р-н", "name": "Пено", "lat": 56.917, "lon": 32.733, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "пеновском р-не", "name": "Пено", "lat": 56.917, "lon": 32.733, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "рамешковский район", "name": "Рамешки", "lat": 57.35, "lon": 36.033, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "рамешковском районе", "name": "Рамешки", "lat": 57.35, "lon": 36.033, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "рамешковский р-н", "name": "Рамешки", "lat": 57.35, "lon": 36.033, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "рамешковском р-не", "name": "Рамешки", "lat": 57.35, "lon": 36.033, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "ржевский район", "name": "Ржев", "lat": 56.26, "lon": 34.33, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "ржевском районе", "name": "Ржев", "lat": 56.26, "lon": 34.33, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "ржевский р-н", "name": "Ржев", "lat": 56.26, "lon": 34.33, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "ржевском р-не", "name": "Ржев", "lat": 56.26, "lon": 34.33, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "сандовский район", "name": "Сандово", "lat": 58.45, "lon": 36.417, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "сандовском районе", "name": "Сандово", "lat": 58.45, "lon": 36.417, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "сандовский р-н", "name": "Сандово", "lat": 58.45, "lon": 36.417, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "сандовском р-не", "name": "Сандово", "lat": 58.45, "lon": 36.417, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "селижаровский район", "name": "Селижарово", "lat": 56.85, "lon": 33.45, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "селижаровском районе", "name": "Селижарово", "lat": 56.85, "lon": 33.45, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "селижаровский р-н", "name": "Селижарово", "lat": 56.85, "lon": 33.45, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "селижаровском р-не", "name": "Селижарово", "lat": 56.85, "lon": 33.45, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "сонковский район", "name": "Сонково", "lat": 57.783, "lon": 37.15, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "сонковском районе", "name": "Сонково", "lat": 57.783, "lon": 37.15, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "сонковский р-н", "name": "Сонково", "lat": 57.783, "lon": 37.15, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "сонковском р-не", "name": "Сонково", "lat": 57.783, "lon": 37.15, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "спировский район", "name": "Спирово", "lat": 57.417, "lon": 34.983, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "спировском районе", "name": "Спирово", "lat": 57.417, "lon": 34.983, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "спировский р-н", "name": "Спирово", "lat": 57.417, "lon": 34.983, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "спировском р-не", "name": "Спирово", "lat": 57.417, "lon": 34.983, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "старицкий район", "name": "Старица", "lat": 56.52, "lon": 34.94, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "старицком районе", "name": "Старица", "lat": 56.52, "lon": 34.94, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "старицкий р-н", "name": "Старица", "lat": 56.52, "lon": 34.94, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "старицком р-не", "name": "Старица", "lat": 56.52, "lon": 34.94, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "торжокский район", "name": "Торжок", "lat": 57.04, "lon": 34.96, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "торжокском районе", "name": "Торжок", "lat": 57.04, "lon": 34.96, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "торжокский р-н", "name": "Торжок", "lat": 57.04, "lon": 34.96, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "торжокском р-не", "name": "Торжок", "lat": 57.04, "lon": 34.96, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "торопецкий район", "name": "Торопец", "lat": 56.5, "lon": 31.63, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "торопецком районе", "name": "Торопец", "lat": 56.5, "lon": 31.63, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "торопецкий р-н", "name": "Торопец", "lat": 56.5, "lon": 31.63, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "торопецком р-не", "name": "Торопец", "lat": 56.5, "lon": 31.63, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "удомельский район", "name": "Удомля", "lat": 57.88, "lon": 35.01, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "удомельском районе", "name": "Удомля", "lat": 57.88, "lon": 35.01, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "удомельский р-н", "name": "Удомля", "lat": 57.88, "lon": 35.01, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "удомельском р-не", "name": "Удомля", "lat": 57.88, "lon": 35.01, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "фировский район", "name": "Фирово", "lat": 57.483, "lon": 33.7, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "фировском районе", "name": "Фирово", "lat": 57.483, "lon": 33.7, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "фировский р-н", "name": "Фирово", "lat": 57.483, "lon": 33.7, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "фировском р-не", "name": "Фирово", "lat": 57.483, "lon": 33.7, "type": "region", "is_region": True, "subject": "Тверская область"},

    # Тверская область — населённые пункты не из CITY_DB
    {"pattern": "кесова гора", "name": "Кесова Гора", "lat": 57.583, "lon": 37.283, "type": "city", "subject": "Тверская область"},
    {"pattern": "кесова горе", "name": "Кесова Гора", "lat": 57.583, "lon": 37.283, "type": "city", "subject": "Тверская область"},
    {"pattern": "лесное", "name": "Лесное", "lat": 58.283, "lon": 35.517, "type": "city", "subject": "Тверская область"},
    {"pattern": "лесноее", "name": "Лесное", "lat": 58.283, "lon": 35.517, "type": "city", "subject": "Тверская область"},
    {"pattern": "максатиха", "name": "Максатиха", "lat": 57.8, "lon": 35.883, "type": "city", "subject": "Тверская область"},
    {"pattern": "максатихе", "name": "Максатиха", "lat": 57.8, "lon": 35.883, "type": "city", "subject": "Тверская область"},
    {"pattern": "молоково", "name": "Молоково", "lat": 58.167, "lon": 36.767, "type": "city", "subject": "Тверская область"},
    {"pattern": "молокове", "name": "Молоково", "lat": 58.167, "lon": 36.767, "type": "city", "subject": "Тверская область"},
    {"pattern": "оленино", "name": "Оленино", "lat": 56.2, "lon": 33.467, "type": "city", "subject": "Тверская область"},
    {"pattern": "оленине", "name": "Оленино", "lat": 56.2, "lon": 33.467, "type": "city", "subject": "Тверская область"},
    {"pattern": "пено", "name": "Пено", "lat": 56.917, "lon": 32.733, "type": "city", "subject": "Тверская область"},
    {"pattern": "пене", "name": "Пено", "lat": 56.917, "lon": 32.733, "type": "city", "subject": "Тверская область"},
    {"pattern": "рамешки", "name": "Рамешки", "lat": 57.35, "lon": 36.033, "type": "city", "subject": "Тверская область"},
    {"pattern": "рамешкие", "name": "Рамешки", "lat": 57.35, "lon": 36.033, "type": "city", "subject": "Тверская область"},
    {"pattern": "сандово", "name": "Сандово", "lat": 58.45, "lon": 36.417, "type": "city", "subject": "Тверская область"},
    {"pattern": "сандове", "name": "Сандово", "lat": 58.45, "lon": 36.417, "type": "city", "subject": "Тверская область"},
    {"pattern": "селижарово", "name": "Селижарово", "lat": 56.85, "lon": 33.45, "type": "city", "subject": "Тверская область"},
    {"pattern": "селижарове", "name": "Селижарово", "lat": 56.85, "lon": 33.45, "type": "city", "subject": "Тверская область"},
    {"pattern": "сонково", "name": "Сонково", "lat": 57.783, "lon": 37.15, "type": "city", "subject": "Тверская область"},
    {"pattern": "сонкове", "name": "Сонково", "lat": 57.783, "lon": 37.15, "type": "city", "subject": "Тверская область"},
    {"pattern": "спирово", "name": "Спирово", "lat": 57.417, "lon": 34.983, "type": "city", "subject": "Тверская область"},
    {"pattern": "спирове", "name": "Спирово", "lat": 57.417, "lon": 34.983, "type": "city", "subject": "Тверская область"},
    {"pattern": "фирово", "name": "Фирово", "lat": 57.483, "lon": 33.7, "type": "city", "subject": "Тверская область"},
    {"pattern": "фирове", "name": "Фирово", "lat": 57.483, "lon": 33.7, "type": "city", "subject": "Тверская область"},
    {"pattern": "жарковский", "name": "Жарковский", "lat": 55.85, "lon": 32.433, "type": "city", "subject": "Тверская область"},
    {"pattern": "жарковские", "name": "Жарковский", "lat": 55.85, "lon": 32.433, "type": "city", "subject": "Тверская область"},
    {"pattern": "новоселки", "name": "Новоселки", "lat": 56.18, "lon": 32.85, "type": "city", "subject": "Тверская область"},
    {"pattern": "нилидово", "name": "Нелидово", "lat": 56.22, "lon": 32.78, "type": "city", "subject": "Тверская область"},
    # Нелидовский район, Тверская область
    {"pattern": "ниливский район", "name": "Нелидово", "lat": 56.22, "lon": 32.78, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "ниливском районе", "name": "Нелидово", "lat": 56.22, "lon": 32.78, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "ниливский р-н", "name": "Нелидово", "lat": 56.22, "lon": 32.78, "type": "region", "is_region": True, "subject": "Тверская область"},
    {"pattern": "ниливском р-не", "name": "Нелидово", "lat": 56.22, "lon": 32.78, "type": "region", "is_region": True, "subject": "Тверская область"},

    # Кировская область — районы
    {"pattern": "кильмезский район", "name": "Кильмезь", "lat": 56.94459, "lon": 51.06363, "type": "region", "is_region": True, "subject": "Кировская область"},
    {"pattern": "кильмезском районе", "name": "Кильмезь", "lat": 56.94459, "lon": 51.06363, "type": "region", "is_region": True, "subject": "Кировская область"},
    {"pattern": "кильмезский р-н", "name": "Кильмезь", "lat": 56.94459, "lon": 51.06363, "type": "region", "is_region": True, "subject": "Кировская область"},
    {"pattern": "кильмезском р-не", "name": "Кильмезь", "lat": 56.94459, "lon": 51.06363, "type": "region", "is_region": True, "subject": "Кировская область"},
    # Кировская область — населённые пункты не из CITY_DB
    {"pattern": "вихарево", "name": "Вихарево", "lat": 56.91486, "lon": 51.34248, "type": "city", "subject": "Кировская область"},
    {"pattern": "вихареве", "name": "Вихарево", "lat": 56.91486, "lon": 51.34248, "type": "city", "subject": "Кировская область"},

    # Удмуртская Республика — районы
    {"pattern": "сюмсинский район", "name": "Сюмси", "lat": 57.11108, "lon": 51.61494, "type": "region", "is_region": True, "subject": "Удмуртская Республика"},
    {"pattern": "сюмсинском районе", "name": "Сюмси", "lat": 57.11108, "lon": 51.61494, "type": "region", "is_region": True, "subject": "Удмуртская Республика"},
    {"pattern": "сюмсинского района", "name": "Сюмси", "lat": 57.11108, "lon": 51.61494, "type": "region", "is_region": True, "subject": "Удмуртская Республика"},
    {"pattern": "сюмсинский р-н", "name": "Сюмси", "lat": 57.11108, "lon": 51.61494, "type": "region", "is_region": True, "subject": "Удмуртская Республика"},
    {"pattern": "сюмсинском р-не", "name": "Сюмси", "lat": 57.11108, "lon": 51.61494, "type": "region", "is_region": True, "subject": "Удмуртская Республика"},

    # Московская область — районы
    {"pattern": "волоколамский район", "name": "Волоколамск", "lat": 56.03, "lon": 35.95, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "волоколамском районе", "name": "Волоколамск", "lat": 56.03, "lon": 35.95, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "волоколамского района", "name": "Волоколамск", "lat": 56.03, "lon": 35.95, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "волоколамский р-н", "name": "Волоколамск", "lat": 56.03, "lon": 35.95, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "волоколамском р-не", "name": "Волоколамск", "lat": 56.03, "lon": 35.95, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "волоколамского р-на", "name": "Волоколамск", "lat": 56.03, "lon": 35.95, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "воскресенский район", "name": "Воскресенск", "lat": 55.33, "lon": 38.65, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "воскресенском районе", "name": "Воскресенск", "lat": 55.33, "lon": 38.65, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "воскресенский р-н", "name": "Воскресенск", "lat": 55.33, "lon": 38.65, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "воскресенском р-не", "name": "Воскресенск", "lat": 55.33, "lon": 38.65, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "дмитровский район", "name": "Дмитров", "lat": 56.35, "lon": 37.52, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "дмитровском районе", "name": "Дмитров", "lat": 56.35, "lon": 37.52, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "дмитровский р-н", "name": "Дмитров", "lat": 56.35, "lon": 37.52, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "дмитровском р-не", "name": "Дмитров", "lat": 56.35, "lon": 37.52, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "егорьевский район", "name": "Егорьевск", "lat": 55.38, "lon": 39.03, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "егорьевском районе", "name": "Егорьевск", "lat": 55.38, "lon": 39.03, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "егорьевский р-н", "name": "Егорьевск", "lat": 55.38, "lon": 39.03, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "егорьевском р-не", "name": "Егорьевск", "lat": 55.38, "lon": 39.03, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "зарайский район", "name": "Зарайск", "lat": 54.77, "lon": 38.88, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "зарайском районе", "name": "Зарайск", "lat": 54.77, "lon": 38.88, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "зарайский р-н", "name": "Зарайск", "lat": 54.77, "lon": 38.88, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "зарайском р-не", "name": "Зарайск", "lat": 54.77, "lon": 38.88, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "истринский район", "name": "Истра", "lat": 55.92, "lon": 36.87, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "истринском районе", "name": "Истра", "lat": 55.92, "lon": 36.87, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "истринский р-н", "name": "Истра", "lat": 55.92, "lon": 36.87, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "истринском р-не", "name": "Истра", "lat": 55.92, "lon": 36.87, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "каширский район", "name": "Кашира", "lat": 54.84, "lon": 38.15, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "каширском районе", "name": "Кашира", "lat": 54.84, "lon": 38.15, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "каширский р-н", "name": "Кашира", "lat": 54.84, "lon": 38.15, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "каширском р-не", "name": "Кашира", "lat": 54.84, "lon": 38.15, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "клинский район", "name": "Клин", "lat": 56.33, "lon": 36.73, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "клинском районе", "name": "Клин", "lat": 56.33, "lon": 36.73, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "клинского района", "name": "Клин", "lat": 56.33, "lon": 36.73, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "клинский р-н", "name": "Клин", "lat": 56.33, "lon": 36.73, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "клинском р-не", "name": "Клин", "lat": 56.33, "lon": 36.73, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "клинского р-на", "name": "Клин", "lat": 56.33, "lon": 36.73, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "коломенский район", "name": "Коломна", "lat": 55.08, "lon": 38.78, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "коломенском районе", "name": "Коломна", "lat": 55.08, "lon": 38.78, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "коломенский р-н", "name": "Коломна", "lat": 55.08, "lon": 38.78, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "коломенском р-не", "name": "Коломна", "lat": 55.08, "lon": 38.78, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "красногорский район", "name": "Красногорск", "lat": 55.82, "lon": 37.33, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "красногорском районе", "name": "Красногорск", "lat": 55.82, "lon": 37.33, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "красногорский р-н", "name": "Красногорск", "lat": 55.82, "lon": 37.33, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "красногорском р-не", "name": "Красногорск", "lat": 55.82, "lon": 37.33, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "ленинский район", "name": "Видное", "lat": 55.55, "lon": 37.7, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "ленинском районе", "name": "Видное", "lat": 55.55, "lon": 37.7, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "ленинский р-н", "name": "Видное", "lat": 55.55, "lon": 37.7, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "ленинском р-не", "name": "Видное", "lat": 55.55, "lon": 37.7, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "лотошинский район", "name": "Лотошино", "lat": 56.233, "lon": 35.633, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "лотошинском районе", "name": "Лотошино", "lat": 56.233, "lon": 35.633, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "лотошинский р-н", "name": "Лотошино", "lat": 56.233, "lon": 35.633, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "лотошинском р-не", "name": "Лотошино", "lat": 56.233, "lon": 35.633, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "луховицкий район", "name": "Луховицы", "lat": 54.97, "lon": 39.02, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "луховицком районе", "name": "Луховицы", "lat": 54.97, "lon": 39.02, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "луховицкий р-н", "name": "Луховицы", "lat": 54.97, "lon": 39.02, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "луховицком р-не", "name": "Луховицы", "lat": 54.97, "lon": 39.02, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "люберецкий район", "name": "Люберцы", "lat": 55.68, "lon": 37.89, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "люберецком районе", "name": "Люберцы", "lat": 55.68, "lon": 37.89, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "люберецкий р-н", "name": "Люберцы", "lat": 55.68, "lon": 37.89, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "люберецком р-не", "name": "Люберцы", "lat": 55.68, "lon": 37.89, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "можайский район", "name": "Можайск", "lat": 55.5, "lon": 36.03, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "можайском районе", "name": "Можайск", "lat": 55.5, "lon": 36.03, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "можайский р-н", "name": "Можайск", "lat": 55.5, "lon": 36.03, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "можайском р-не", "name": "Можайск", "lat": 55.5, "lon": 36.03, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "наро-фоминский район", "name": "Наро-Фоминск", "lat": 55.38, "lon": 36.73, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "наро-фоминском районе", "name": "Наро-Фоминск", "lat": 55.38, "lon": 36.73, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "наро-фоминский р-н", "name": "Наро-Фоминск", "lat": 55.38, "lon": 36.73, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "наро-фоминском р-не", "name": "Наро-Фоминск", "lat": 55.38, "lon": 36.73, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "ногинский район", "name": "Ногинск", "lat": 55.85, "lon": 38.45, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "ногинском районе", "name": "Ногинск", "lat": 55.85, "lon": 38.45, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "ногинский р-н", "name": "Ногинск", "lat": 55.85, "lon": 38.45, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "ногинском р-не", "name": "Ногинск", "lat": 55.85, "lon": 38.45, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "одинцовский район", "name": "Одинцово", "lat": 55.68, "lon": 37.28, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "одинцовском районе", "name": "Одинцово", "lat": 55.68, "lon": 37.28, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "одинцовский р-н", "name": "Одинцово", "lat": 55.68, "lon": 37.28, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "одинцовском р-не", "name": "Одинцово", "lat": 55.68, "lon": 37.28, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "озёрский район", "name": "Озёры", "lat": 54.85, "lon": 38.55, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "озёрском районе", "name": "Озёры", "lat": 54.85, "lon": 38.55, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "озёрский р-н", "name": "Озёры", "lat": 54.85, "lon": 38.55, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "озёрском р-не", "name": "Озёры", "lat": 54.85, "lon": 38.55, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "орехово-зуевский район", "name": "Орехово-Зуево", "lat": 55.8, "lon": 38.97, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "орехово-зуевском районе", "name": "Орехово-Зуево", "lat": 55.8, "lon": 38.97, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "орехово-зуевский р-н", "name": "Орехово-Зуево", "lat": 55.8, "lon": 38.97, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "орехово-зуевском р-не", "name": "Орехово-Зуево", "lat": 55.8, "lon": 38.97, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "орехово-зуевский го", "name": "Орехово-Зуево", "lat": 55.8, "lon": 38.96667, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "орехово-зуевского го", "name": "Орехово-Зуево", "lat": 55.8, "lon": 38.96667, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "орехово-зуевском го", "name": "Орехово-Зуево", "lat": 55.8, "lon": 38.96667, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "орехово - зуевский го", "name": "Орехово-Зуево", "lat": 55.8, "lon": 38.96667, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "орехово - зуевского го", "name": "Орехово-Зуево", "lat": 55.8, "lon": 38.96667, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "орехово - зуевском го", "name": "Орехово-Зуево", "lat": 55.8, "lon": 38.96667, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "орехово-зуевский городской округ", "name": "Орехово-Зуево", "lat": 55.8, "lon": 38.96667, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "орехово-зуевского городского округа", "name": "Орехово-Зуево", "lat": 55.8, "lon": 38.96667, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "павлово-посадский район", "name": "Павловский Посад", "lat": 55.783, "lon": 38.65, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "павлово-посадском районе", "name": "Павловский Посад", "lat": 55.783, "lon": 38.65, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "павлово-посадский р-н", "name": "Павловский Посад", "lat": 55.783, "lon": 38.65, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "павлово-посадском р-не", "name": "Павловский Посад", "lat": 55.783, "lon": 38.65, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "павлово-посадский", "name": "Павловский Посад", "lat": 55.783, "lon": 38.65, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "павловском посадском", "name": "Павловский Посад", "lat": 55.783, "lon": 38.65, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "подольский район", "name": "Подольск", "lat": 55.43, "lon": 37.54, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "подольском районе", "name": "Подольск", "lat": 55.43, "lon": 37.54, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "подольского района", "name": "Подольск", "lat": 55.43, "lon": 37.54, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "подольский р-н", "name": "Подольск", "lat": 55.43, "lon": 37.54, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "подольском р-не", "name": "Подольск", "lat": 55.43, "lon": 37.54, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "подольского р-на", "name": "Подольск", "lat": 55.43, "lon": 37.54, "type": "region", "is_region": True, "subject": "Московская область"},
    # Троицкий АО (Новая Москва) — иначе rayon-фолбэк берёт Троицк/Челябинскую из CITY_DB
    {"pattern": "троицкий ао", "name": "Троицк", "lat": 55.467, "lon": 37.3, "type": "region", "is_region": True, "subject": "Москва"},
    {"pattern": "троицком ао", "name": "Троицк", "lat": 55.467, "lon": 37.3, "type": "region", "is_region": True, "subject": "Москва"},
    {"pattern": "троицкого ао", "name": "Троицк", "lat": 55.467, "lon": 37.3, "type": "region", "is_region": True, "subject": "Москва"},
    {"pattern": "го троицк", "name": "Троицк", "lat": 55.467, "lon": 37.3, "type": "region", "is_region": True, "subject": "Москва"},
    {"pattern": "ао троицк", "name": "Троицк", "lat": 55.467, "lon": 37.3, "type": "region", "is_region": True, "subject": "Москва"},
    # г.Москва — явный маркер столицы; CITY_DB entry не-юник (GeoNames-тёзки), нужен is_region для контекста
    {"pattern": "г.москва", "name": "Москва", "lat": 55.7558, "lon": 37.6178, "type": "region", "is_region": True, "subject": "Москва"},
    # Богородский округ (Московская) — иначе «Богородском» → Нижегородская
    {"pattern": "богородский округ", "name": "Ногинск", "lat": 55.85, "lon": 38.43333, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "богородском округе", "name": "Ногинск", "lat": 55.85, "lon": 38.43333, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "богородского округа", "name": "Ногинск", "lat": 55.85, "lon": 38.43333, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "пушкинский район", "name": "Пушкино", "lat": 56.02, "lon": 37.85, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "пушкинском районе", "name": "Пушкино", "lat": 56.02, "lon": 37.85, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "пушкинский р-н", "name": "Пушкино", "lat": 56.02, "lon": 37.85, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "пушкинском р-не", "name": "Пушкино", "lat": 56.02, "lon": 37.85, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "раменский район", "name": "Раменское", "lat": 55.57, "lon": 38.23, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "раменском районе", "name": "Раменское", "lat": 55.57, "lon": 38.23, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "раменский р-н", "name": "Раменское", "lat": 55.57, "lon": 38.23, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "раменском р-не", "name": "Раменское", "lat": 55.57, "lon": 38.23, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "рузский район", "name": "Руза", "lat": 55.7, "lon": 36.2, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "рузском районе", "name": "Руза", "lat": 55.7, "lon": 36.2, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "рузский р-н", "name": "Руза", "lat": 55.7, "lon": 36.2, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "рузском р-не", "name": "Руза", "lat": 55.7, "lon": 36.2, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "сергиево-посадский район", "name": "Сергиев Посад", "lat": 56.3, "lon": 38.13, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "сергиево-посадском районе", "name": "Сергиев Посад", "lat": 56.3, "lon": 38.13, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "сергиево-посадский р-н", "name": "Сергиев Посад", "lat": 56.3, "lon": 38.13, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "сергиево-посадском р-не", "name": "Сергиев Посад", "lat": 56.3, "lon": 38.13, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "серебряно-прудский район", "name": "Серебряные Пруды", "lat": 54.467, "lon": 38.733, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "серебряно-прудском районе", "name": "Серебряные Пруды", "lat": 54.467, "lon": 38.733, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "серебряно-прудский р-н", "name": "Серебряные Пруды", "lat": 54.467, "lon": 38.733, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "серебряно-прудском р-не", "name": "Серебряные Пруды", "lat": 54.467, "lon": 38.733, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "серпуховский район", "name": "Серпухов", "lat": 54.92, "lon": 37.41, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "серпуховском районе", "name": "Серпухов", "lat": 54.92, "lon": 37.41, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "серпуховский р-н", "name": "Серпухов", "lat": 54.92, "lon": 37.41, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "серпуховском р-не", "name": "Серпухов", "lat": 54.92, "lon": 37.41, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "солнечногорский район", "name": "Солнечногорск", "lat": 56.18, "lon": 36.98, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "солнечногорском районе", "name": "Солнечногорск", "lat": 56.18, "lon": 36.98, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "солнечногорский р-н", "name": "Солнечногорск", "lat": 56.18, "lon": 36.98, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "солнечногорском р-не", "name": "Солнечногорск", "lat": 56.18, "lon": 36.98, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "ступинский район", "name": "Ступино", "lat": 54.9, "lon": 38.07, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "ступинском районе", "name": "Ступино", "lat": 54.9, "lon": 38.07, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "ступинский р-н", "name": "Ступино", "lat": 54.9, "lon": 38.07, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "ступинском р-не", "name": "Ступино", "lat": 54.9, "lon": 38.07, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "талдомский район", "name": "Талдом", "lat": 56.73, "lon": 37.53, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "талдомском районе", "name": "Талдом", "lat": 56.73, "lon": 37.53, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "талдомский р-н", "name": "Талдом", "lat": 56.73, "lon": 37.53, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "талдомском р-не", "name": "Талдом", "lat": 56.73, "lon": 37.53, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "чеховский район", "name": "Чехов", "lat": 55.15, "lon": 37.48, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "чеховском районе", "name": "Чехов", "lat": 55.15, "lon": 37.48, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "чеховский р-н", "name": "Чехов", "lat": 55.15, "lon": 37.48, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "чеховском р-не", "name": "Чехов", "lat": 55.15, "lon": 37.48, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "шатурский район", "name": "Шатура", "lat": 55.58, "lon": 39.54, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "шатурском районе", "name": "Шатура", "lat": 55.58, "lon": 39.54, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "шатурский р-н", "name": "Шатура", "lat": 55.58, "lon": 39.54, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "шатурском р-не", "name": "Шатура", "lat": 55.58, "lon": 39.54, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "шаховской район", "name": "Шаховская", "lat": 56.033, "lon": 35.517, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "шаховской районе", "name": "Шаховская", "lat": 56.033, "lon": 35.517, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "шаховской р-н", "name": "Шаховская", "lat": 56.033, "lon": 35.517, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "шаховской р-не", "name": "Шаховская", "lat": 56.033, "lon": 35.517, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "щёлковский район", "name": "Щёлково", "lat": 55.92, "lon": 37.99, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "щёлковском районе", "name": "Щёлково", "lat": 55.92, "lon": 37.99, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "щёлковский р-н", "name": "Щёлково", "lat": 55.92, "lon": 37.99, "type": "region", "is_region": True, "subject": "Московская область"},
    {"pattern": "щёлковском р-не", "name": "Щёлково", "lat": 55.92, "lon": 37.99, "type": "region", "is_region": True, "subject": "Московская область"},

    # Московская область — населённые пункты не из CITY_DB
    {"pattern": "лотошино", "name": "Лотошино", "lat": 56.233, "lon": 35.633, "type": "city", "subject": "Московская область"},
    {"pattern": "лотошине", "name": "Лотошино", "lat": 56.233, "lon": 35.633, "type": "city", "subject": "Московская область"},
    {"pattern": "серебряные пруды", "name": "Серебряные Пруды", "lat": 54.467, "lon": 38.733, "type": "city", "subject": "Московская область"},
    {"pattern": "серебряные прудые", "name": "Серебряные Пруды", "lat": 54.467, "lon": 38.733, "type": "city", "subject": "Московская область"},
    {"pattern": "шаховская", "name": "Шаховская", "lat": 56.033, "lon": 35.517, "type": "city", "subject": "Московская область"},
    {"pattern": "шаховскае", "name": "Шаховская", "lat": 56.033, "lon": 35.517, "type": "city", "subject": "Московская область"},

    # Рязанская область — районы
    {"pattern": "ермишинский район", "name": "Ермишь", "lat": 54.767, "lon": 42.267, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "ермишинском районе", "name": "Ермишь", "lat": 54.767, "lon": 42.267, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "ермишинский р-н", "name": "Ермишь", "lat": 54.767, "lon": 42.267, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "ермишинском р-не", "name": "Ермишь", "lat": 54.767, "lon": 42.267, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "захаровский район", "name": "Захарово", "lat": 54.367, "lon": 39.283, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "захаровском районе", "name": "Захарово", "lat": 54.367, "lon": 39.283, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "захаровский р-н", "name": "Захарово", "lat": 54.367, "lon": 39.283, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "захаровском р-не", "name": "Захарово", "lat": 54.367, "lon": 39.283, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "кадомский район", "name": "Кадом", "lat": 54.567, "lon": 42.467, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "кадомском районе", "name": "Кадом", "lat": 54.567, "lon": 42.467, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "кадомский р-н", "name": "Кадом", "lat": 54.567, "lon": 42.467, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "кадомском р-не", "name": "Кадом", "lat": 54.567, "lon": 42.467, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "касимовский район", "name": "Касимов", "lat": 54.93, "lon": 41.39, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "касимовском районе", "name": "Касимов", "lat": 54.93, "lon": 41.39, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "касимовский р-н", "name": "Касимов", "lat": 54.93, "lon": 41.39, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "касимовском р-не", "name": "Касимов", "lat": 54.93, "lon": 41.39, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "клепиковский район", "name": "Спас-Клепики", "lat": 55.133, "lon": 40.167, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "клепиковском районе", "name": "Спас-Клепики", "lat": 55.133, "lon": 40.167, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "клепиковский р-н", "name": "Спас-Клепики", "lat": 55.133, "lon": 40.167, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "клепиковском р-не", "name": "Спас-Клепики", "lat": 55.133, "lon": 40.167, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "кораблинский район", "name": "Кораблино", "lat": 53.92, "lon": 40.02, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "кораблинском районе", "name": "Кораблино", "lat": 53.92, "lon": 40.02, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "кораблинский р-н", "name": "Кораблино", "lat": 53.92, "lon": 40.02, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "кораблинском р-не", "name": "Кораблино", "lat": 53.92, "lon": 40.02, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "милославский район", "name": "Милославское", "lat": 53.567, "lon": 39.433, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "милославском районе", "name": "Милославское", "lat": 53.567, "lon": 39.433, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "милославский р-н", "name": "Милославское", "lat": 53.567, "lon": 39.433, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "милославском р-не", "name": "Милославское", "lat": 53.567, "lon": 39.433, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "михайловский район", "name": "Михайлов", "lat": 54.23, "lon": 39.03, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "михайловском районе", "name": "Михайлов", "lat": 54.23, "lon": 39.03, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "михайловский р-н", "name": "Михайлов", "lat": 54.23, "lon": 39.03, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "михайловском р-не", "name": "Михайлов", "lat": 54.23, "lon": 39.03, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "пителинский район", "name": "Пителино", "lat": 54.583, "lon": 41.817, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "пителинском районе", "name": "Пителино", "lat": 54.583, "lon": 41.817, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "пителинский р-н", "name": "Пителино", "lat": 54.583, "lon": 41.817, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "пителинском р-не", "name": "Пителино", "lat": 54.583, "lon": 41.817, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "пронский район", "name": "Пронск", "lat": 54.117, "lon": 39.6, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "пронском районе", "name": "Пронск", "lat": 54.117, "lon": 39.6, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "пронский р-н", "name": "Пронск", "lat": 54.117, "lon": 39.6, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "пронском р-не", "name": "Пронск", "lat": 54.117, "lon": 39.6, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "путятинский район", "name": "Путятино", "lat": 54.167, "lon": 41.117, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "путятинском районе", "name": "Путятино", "lat": 54.167, "lon": 41.117, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "путятинский р-н", "name": "Путятино", "lat": 54.167, "lon": 41.117, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "путятинском р-не", "name": "Путятино", "lat": 54.167, "lon": 41.117, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "рыбновский район", "name": "Рыбное", "lat": 54.73, "lon": 39.52, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "рыбновском районе", "name": "Рыбное", "lat": 54.73, "lon": 39.52, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "рыбновский р-н", "name": "Рыбное", "lat": 54.73, "lon": 39.52, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "рыбновском р-не", "name": "Рыбное", "lat": 54.73, "lon": 39.52, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "ряжский район", "name": "Ряжск", "lat": 53.7, "lon": 40.07, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "ряжском районе", "name": "Ряжск", "lat": 53.7, "lon": 40.07, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "ряжский р-н", "name": "Ряжск", "lat": 53.7, "lon": 40.07, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "ряжском р-не", "name": "Ряжск", "lat": 53.7, "lon": 40.07, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "рязанский район", "name": "Рязань", "lat": 54.6, "lon": 39.71, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "рязанском районе", "name": "Рязань", "lat": 54.6, "lon": 39.71, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "рязанский р-н", "name": "Рязань", "lat": 54.6, "lon": 39.71, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "рязанском р-не", "name": "Рязань", "lat": 54.6, "lon": 39.71, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "сапожковский район", "name": "Сапожок", "lat": 53.95, "lon": 40.683, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "сапожковском районе", "name": "Сапожок", "lat": 53.95, "lon": 40.683, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "сапожковский р-н", "name": "Сапожок", "lat": 53.95, "lon": 40.683, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "сапожковском р-не", "name": "Сапожок", "lat": 53.95, "lon": 40.683, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "сараевский район", "name": "Сары", "lat": 53.717, "lon": 40.983, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "сараевском районе", "name": "Сары", "lat": 53.717, "lon": 40.983, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "сараевский р-н", "name": "Сары", "lat": 53.717, "lon": 40.983, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "сараевском р-не", "name": "Сары", "lat": 53.717, "lon": 40.983, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "сасовский район", "name": "Сасово", "lat": 54.35, "lon": 41.92, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "сасовском районе", "name": "Сасово", "lat": 54.35, "lon": 41.92, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "сасовский р-н", "name": "Сасово", "lat": 54.35, "lon": 41.92, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "сасовском р-не", "name": "Сасово", "lat": 54.35, "lon": 41.92, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "скопинский район", "name": "Скопин", "lat": 53.82, "lon": 39.55, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "скопинском районе", "name": "Скопин", "lat": 53.82, "lon": 39.55, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "скопинский р-н", "name": "Скопин", "lat": 53.82, "lon": 39.55, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "скопинском р-не", "name": "Скопин", "lat": 53.82, "lon": 39.55, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "спасский район", "name": "Спасск-Рязанский", "lat": 54.4, "lon": 40.38, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "спасском районе", "name": "Спасск-Рязанский", "lat": 54.4, "lon": 40.38, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "спасский р-н", "name": "Спасск-Рязанский", "lat": 54.4, "lon": 40.38, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "спасском р-не", "name": "Спасск-Рязанский", "lat": 54.4, "lon": 40.38, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "алькеевский район", "name": "Базарные Матаки", "lat": 54.90528, "lon": 49.92583, "type": "region", "is_region": True, "subject": "Республика Татарстан"},
    {"pattern": "алькеевском районе", "name": "Базарные Матаки", "lat": 54.90528, "lon": 49.92583, "type": "region", "is_region": True, "subject": "Республика Татарстан"},
    {"pattern": "алькеевский р-н", "name": "Базарные Матаки", "lat": 54.90528, "lon": 49.92583, "type": "region", "is_region": True, "subject": "Республика Татарстан"},
    {"pattern": "алькеевском р-не", "name": "Базарные Матаки", "lat": 54.90528, "lon": 49.92583, "type": "region", "is_region": True, "subject": "Республика Татарстан"},
    {"pattern": "старожиловский район", "name": "Старожилово", "lat": 54.233, "lon": 39.9, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "старожиловском районе", "name": "Старожилово", "lat": 54.233, "lon": 39.9, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "старожиловский р-н", "name": "Старожилово", "lat": 54.233, "lon": 39.9, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "старожиловском р-не", "name": "Старожилово", "lat": 54.233, "lon": 39.9, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "ухоловский район", "name": "Ухолово", "lat": 53.783, "lon": 40.483, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "ухоловском районе", "name": "Ухолово", "lat": 53.783, "lon": 40.483, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "ухоловский р-н", "name": "Ухолово", "lat": 53.783, "lon": 40.483, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "ухоловском р-не", "name": "Ухолово", "lat": 53.783, "lon": 40.483, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "чучковский район", "name": "Чучково", "lat": 54.267, "lon": 41.45, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "чучковском районе", "name": "Чучково", "lat": 54.267, "lon": 41.45, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "чучковский р-н", "name": "Чучково", "lat": 54.267, "lon": 41.45, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "чучковском р-не", "name": "Чучково", "lat": 54.267, "lon": 41.45, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "шацкий район", "name": "Шацк", "lat": 54.02, "lon": 41.72, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "шацком районе", "name": "Шацк", "lat": 54.02, "lon": 41.72, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "шацкий р-н", "name": "Шацк", "lat": 54.02, "lon": 41.72, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "шацком р-не", "name": "Шацк", "lat": 54.02, "lon": 41.72, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "шиловский район", "name": "Шилово", "lat": 54.317, "lon": 40.867, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "шиловском районе", "name": "Шилово", "lat": 54.317, "lon": 40.867, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "шиловский р-н", "name": "Шилово", "lat": 54.317, "lon": 40.867, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "шиловском р-не", "name": "Шилово", "lat": 54.317, "lon": 40.867, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "александро-невский район", "name": "Александро-Невский", "lat": 53.467, "lon": 40.2, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "александро-невском районе", "name": "Александро-Невский", "lat": 53.467, "lon": 40.2, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "александро-невский р-н", "name": "Александро-Невский", "lat": 53.467, "lon": 40.2, "type": "region", "is_region": True, "subject": "Рязанская область"},
    {"pattern": "александро-невском р-не", "name": "Александро-Невский", "lat": 53.467, "lon": 40.2, "type": "region", "is_region": True, "subject": "Рязанская область"},

    # Рязанская область — населённые пункты не из CITY_DB
    {"pattern": "ермишь", "name": "Ермишь", "lat": 54.767, "lon": 42.267, "type": "city", "subject": "Рязанская область"},
    {"pattern": "ермише", "name": "Ермишь", "lat": 54.767, "lon": 42.267, "type": "city", "subject": "Рязанская область"},
    {"pattern": "захарово", "name": "Захарово", "lat": 54.367, "lon": 39.283, "type": "city", "subject": "Рязанская область"},
    {"pattern": "кадом", "name": "Кадом", "lat": 54.567, "lon": 42.467, "type": "city", "subject": "Рязанская область"},
    {"pattern": "кадоме", "name": "Кадом", "lat": 54.567, "lon": 42.467, "type": "city", "subject": "Рязанская область"},
    {"pattern": "спас-клепики", "name": "Спас-Клепики", "lat": 55.133, "lon": 40.167, "type": "city", "subject": "Рязанская область"},
    {"pattern": "милославское", "name": "Милославское", "lat": 53.567, "lon": 39.433, "type": "city", "subject": "Рязанская область"},
    {"pattern": "пителино", "name": "Пителино", "lat": 54.583, "lon": 41.817, "type": "city", "subject": "Рязанская область"},
    {"pattern": "пронск", "name": "Пронск", "lat": 54.117, "lon": 39.6, "type": "city", "subject": "Рязанская область"},
    {"pattern": "пронске", "name": "Пронск", "lat": 54.117, "lon": 39.6, "type": "city", "subject": "Рязанская область"},
    {"pattern": "путятино", "name": "Путятино", "lat": 54.167, "lon": 41.117, "type": "city", "subject": "Рязанская область"},
    {"pattern": "сапожок", "name": "Сапожок", "lat": 53.95, "lon": 40.683, "type": "city", "subject": "Рязанская область"},
    {"pattern": "сапожоке", "name": "Сапожок", "lat": 53.95, "lon": 40.683, "type": "city", "subject": "Рязанская область"},
    {"pattern": "старожилово", "name": "Старожилово", "lat": 54.233, "lon": 39.9, "type": "city", "subject": "Рязанская область"},
    {"pattern": "ухолово", "name": "Ухолово", "lat": 53.783, "lon": 40.483, "type": "city", "subject": "Рязанская область"},
    {"pattern": "чучково", "name": "Чучково", "lat": 54.267, "lon": 41.45, "type": "city", "subject": "Рязанская область"},
    {"pattern": "шилово", "name": "Шилово", "lat": 54.317, "lon": 40.867, "type": "city", "subject": "Рязанская область"},
    {"pattern": "александро-невский", "name": "Александро-Невский", "lat": 53.467, "lon": 40.2, "type": "city", "subject": "Рязанская область"},
    {"pattern": "александро-невские", "name": "Александро-Невский", "lat": 53.467, "lon": 40.2, "type": "city", "subject": "Рязанская область"},

    # Тамбовская область — районы
    {"pattern": "бондарский район", "name": "Бондари", "lat": 52.95, "lon": 42.083, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "бондарском районе", "name": "Бондари", "lat": 52.95, "lon": 42.083, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "бондарский р-н", "name": "Бондари", "lat": 52.95, "lon": 42.083, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "бондарском р-не", "name": "Бондари", "lat": 52.95, "lon": 42.083, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "гавриловский район", "name": "Гавриловка 2-я", "lat": 52.867, "lon": 42.767, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "гавриловском районе", "name": "Гавриловка 2-я", "lat": 52.867, "lon": 42.767, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "гавриловский р-н", "name": "Гавриловка 2-я", "lat": 52.867, "lon": 42.767, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "гавриловском р-не", "name": "Гавриловка 2-я", "lat": 52.867, "lon": 42.767, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "жердевский район", "name": "Жердевка", "lat": 51.85, "lon": 41.47, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "жердевском районе", "name": "Жердевка", "lat": 51.85, "lon": 41.47, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "жердевский р-н", "name": "Жердевка", "lat": 51.85, "lon": 41.47, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "жердевском р-не", "name": "Жердевка", "lat": 51.85, "lon": 41.47, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "знаменский район", "name": "Знаменка", "lat": 52.417, "lon": 41.433, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "знаменском районе", "name": "Знаменка", "lat": 52.417, "lon": 41.433, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "знаменский р-н", "name": "Знаменка", "lat": 52.417, "lon": 41.433, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "знаменском р-не", "name": "Знаменка", "lat": 52.417, "lon": 41.433, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "инжавинский район", "name": "Инжавино", "lat": 52.317, "lon": 42.483, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "инжавинском районе", "name": "Инжавино", "lat": 52.317, "lon": 42.483, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "инжавинский р-н", "name": "Инжавино", "lat": 52.317, "lon": 42.483, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "инжавинском р-не", "name": "Инжавино", "lat": 52.317, "lon": 42.483, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "кирсановский район", "name": "Кирсанов", "lat": 52.65, "lon": 42.72, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "кирсановском районе", "name": "Кирсанов", "lat": 52.65, "lon": 42.72, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "кирсановский р-н", "name": "Кирсанов", "lat": 52.65, "lon": 42.72, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "кирсановском р-не", "name": "Кирсанов", "lat": 52.65, "lon": 42.72, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "мичуринский район", "name": "Мичуринск", "lat": 52.9, "lon": 40.48, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "мичуринском районе", "name": "Мичуринск", "lat": 52.9, "lon": 40.48, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "мичуринский р-н", "name": "Мичуринск", "lat": 52.9, "lon": 40.48, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "мичуринском р-не", "name": "Мичуринск", "lat": 52.9, "lon": 40.48, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "мордовский район", "name": "Мордово", "lat": 52.083, "lon": 40.783, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "мордовском районе", "name": "Мордово", "lat": 52.083, "lon": 40.783, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "мордовский р-н", "name": "Мордово", "lat": 52.083, "lon": 40.783, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "мордовском р-не", "name": "Мордово", "lat": 52.083, "lon": 40.783, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "моршанский район", "name": "Моршанск", "lat": 53.45, "lon": 41.8, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "моршанском районе", "name": "Моршанск", "lat": 53.45, "lon": 41.8, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "моршанский р-н", "name": "Моршанск", "lat": 53.45, "lon": 41.8, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "моршанском р-не", "name": "Моршанск", "lat": 53.45, "lon": 41.8, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "мучкапский район", "name": "Мучкапский", "lat": 51.85, "lon": 42.467, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "мучкапском районе", "name": "Мучкапский", "lat": 51.85, "lon": 42.467, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "мучкапский р-н", "name": "Мучкапский", "lat": 51.85, "lon": 42.467, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "мучкапском р-не", "name": "Мучкапский", "lat": 51.85, "lon": 42.467, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "никифоровский район", "name": "Дмитриевка", "lat": 52.883, "lon": 40.783, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "никифоровском районе", "name": "Дмитриевка", "lat": 52.883, "lon": 40.783, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "никифоровский р-н", "name": "Дмитриевка", "lat": 52.883, "lon": 40.783, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "никифоровском р-не", "name": "Дмитриевка", "lat": 52.883, "lon": 40.783, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "первомайский район", "name": "Первомайский", "lat": 53.25, "lon": 40.283, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "первомайском районе", "name": "Первомайский", "lat": 53.25, "lon": 40.283, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "первомайский р-н", "name": "Первомайский", "lat": 53.25, "lon": 40.283, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "первомайском р-не", "name": "Первомайский", "lat": 53.25, "lon": 40.283, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "петровский район", "name": "Петровское", "lat": 52.633, "lon": 40.267, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "петровском районе", "name": "Петровское", "lat": 52.633, "lon": 40.267, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "петровский р-н", "name": "Петровское", "lat": 52.633, "lon": 40.267, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "петровском р-не", "name": "Петровское", "lat": 52.633, "lon": 40.267, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "пичаевский район", "name": "Пичаево", "lat": 53.233, "lon": 42.2, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "пичаевском районе", "name": "Пичаево", "lat": 53.233, "lon": 42.2, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "пичаевский р-н", "name": "Пичаево", "lat": 53.233, "lon": 42.2, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "пичаевском р-не", "name": "Пичаево", "lat": 53.233, "lon": 42.2, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "рассказовский район", "name": "Рассказово", "lat": 52.65, "lon": 41.88, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "рассказовском районе", "name": "Рассказово", "lat": 52.65, "lon": 41.88, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "рассказовский р-н", "name": "Рассказово", "lat": 52.65, "lon": 41.88, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "рассказовском р-не", "name": "Рассказово", "lat": 52.65, "lon": 41.88, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "ржаксинский район", "name": "Ржакса", "lat": 52.133, "lon": 42.183, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "ржаксинском районе", "name": "Ржакса", "lat": 52.133, "lon": 42.183, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "ржаксинский р-н", "name": "Ржакса", "lat": 52.133, "lon": 42.183, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "ржаксинском р-не", "name": "Ржакса", "lat": 52.133, "lon": 42.183, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "сампурский район", "name": "Сатинка", "lat": 52.367, "lon": 41.667, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "сампурском районе", "name": "Сатинка", "lat": 52.367, "lon": 41.667, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "сампурский р-н", "name": "Сатинка", "lat": 52.367, "lon": 41.667, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "сампурском р-не", "name": "Сатинка", "lat": 52.367, "lon": 41.667, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "сосновский район", "name": "Сосновка", "lat": 53.233, "lon": 41.367, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "сосновском районе", "name": "Сосновка", "lat": 53.233, "lon": 41.367, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "сосновский р-н", "name": "Сосновка", "lat": 53.233, "lon": 41.367, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "сосновском р-не", "name": "Сосновка", "lat": 53.233, "lon": 41.367, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "староюрьевский район", "name": "Староюрьево", "lat": 53.317, "lon": 40.55, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "староюрьевском районе", "name": "Староюрьево", "lat": 53.317, "lon": 40.55, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "староюрьевский р-н", "name": "Староюрьево", "lat": 53.317, "lon": 40.55, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "староюрьевском р-не", "name": "Староюрьево", "lat": 53.317, "lon": 40.55, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "тамбовский район", "name": "Тамбов", "lat": 52.7, "lon": 41.45, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "тамбовском районе", "name": "Тамбов", "lat": 52.7, "lon": 41.45, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "тамбовский р-н", "name": "Тамбов", "lat": 52.7, "lon": 41.45, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "тамбовском р-не", "name": "Тамбов", "lat": 52.7, "lon": 41.45, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "токарёвский район", "name": "Токарёвка", "lat": 51.983, "lon": 41.15, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "токарёвском районе", "name": "Токарёвка", "lat": 51.983, "lon": 41.15, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "токарёвский р-н", "name": "Токарёвка", "lat": 51.983, "lon": 41.15, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "токарёвском р-не", "name": "Токарёвка", "lat": 51.983, "lon": 41.15, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "уваровский район", "name": "Уварово", "lat": 51.98, "lon": 42.27, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "уваровском районе", "name": "Уварово", "lat": 51.98, "lon": 42.27, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "уваровский р-н", "name": "Уварово", "lat": 51.98, "lon": 42.27, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "уваровском р-не", "name": "Уварово", "lat": 51.98, "lon": 42.27, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "умётский район", "name": "Умёт", "lat": 52.55, "lon": 42.967, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "умётском районе", "name": "Умёт", "lat": 52.55, "lon": 42.967, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "умётский р-н", "name": "Умёт", "lat": 52.55, "lon": 42.967, "type": "region", "is_region": True, "subject": "Тамбовская область"},
    {"pattern": "умётском р-не", "name": "Умёт", "lat": 52.55, "lon": 42.967, "type": "region", "is_region": True, "subject": "Тамбовская область"},

    # Тамбовская область — населённые пункты не из CITY_DB
    {"pattern": "бондари", "name": "Бондари", "lat": 52.95, "lon": 42.083, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "гавриловка 2-я", "name": "Гавриловка 2-я", "lat": 52.867, "lon": 42.767, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "гавриловка 2-е", "name": "Гавриловка 2-я", "lat": 52.867, "lon": 42.767, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "знаменка", "name": "Знаменка", "lat": 52.417, "lon": 41.433, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "знаменке", "name": "Знаменка", "lat": 52.417, "lon": 41.433, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "инжавино", "name": "Инжавино", "lat": 52.317, "lon": 42.483, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "мордово", "name": "Мордово", "lat": 52.083, "lon": 40.783, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "мучкапский", "name": "Мучкапский", "lat": 51.85, "lon": 42.467, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "мучкапские", "name": "Мучкапский", "lat": 51.85, "lon": 42.467, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "дмитриевка", "name": "Дмитриевка", "lat": 52.883, "lon": 40.783, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "дмитриевке", "name": "Дмитриевка", "lat": 52.883, "lon": 40.783, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "первомайский", "name": "Первомайский", "lat": 53.25, "lon": 40.283, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "первомайские", "name": "Первомайский", "lat": 53.25, "lon": 40.283, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "петровское", "name": "Петровское", "lat": 52.633, "lon": 40.267, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "пичаево", "name": "Пичаево", "lat": 53.233, "lon": 42.2, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "ржакса", "name": "Ржакса", "lat": 52.133, "lon": 42.183, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "ржаксе", "name": "Ржакса", "lat": 52.133, "lon": 42.183, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "сатинка", "name": "Сатинка", "lat": 52.367, "lon": 41.667, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "сатинке", "name": "Сатинка", "lat": 52.367, "lon": 41.667, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "сосновка", "name": "Сосновка", "lat": 53.233, "lon": 41.367, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "сосновке", "name": "Сосновка", "lat": 53.233, "lon": 41.367, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "староюрьево", "name": "Староюрьево", "lat": 53.317, "lon": 40.55, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "токарёвка", "name": "Токарёвка", "lat": 51.983, "lon": 41.15, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "токарёвке", "name": "Токарёвка", "lat": 51.983, "lon": 41.15, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "умёт", "name": "Умёт", "lat": 52.55, "lon": 42.967, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "умёте", "name": "Умёт", "lat": 52.55, "lon": 42.967, "type": "city", "subject": "Тамбовская область"},
    {"pattern": "зубова поляна", "name": "Зубова Поляна", "lat": 54.0833, "lon": 42.8167, "type": "city", "subject": "Республика Мордовия"},
    {"pattern": "зубовой поляны", "name": "Зубова Поляна", "lat": 54.0833, "lon": 42.8167, "type": "city", "subject": "Республика Мордовия"},
    {"pattern": "зубову поляну", "name": "Зубова Поляна", "lat": 54.0833, "lon": 42.8167, "type": "city", "subject": "Республика Мордовия"},

    # Воронежская область — районы
    {"pattern": "аннинский район", "name": "Анна", "lat": 51.48, "lon": 40.42, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "аннинском районе", "name": "Анна", "lat": 51.48, "lon": 40.42, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "аннинский р-н", "name": "Анна", "lat": 51.48, "lon": 40.42, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "аннинском р-не", "name": "Анна", "lat": 51.48, "lon": 40.42, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "бобровский район", "name": "Бобров", "lat": 51.1, "lon": 40.03, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "бобровском районе", "name": "Бобров", "lat": 51.1, "lon": 40.03, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "бобровский р-н", "name": "Бобров", "lat": 51.1, "lon": 40.03, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "бобровском р-не", "name": "Бобров", "lat": 51.1, "lon": 40.03, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "борисоглебский район", "name": "Борисоглебск", "lat": 51.367, "lon": 42.083, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "борисоглебском районе", "name": "Борисоглебск", "lat": 51.367, "lon": 42.083, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "борисоглебский р-н", "name": "Борисоглебск", "lat": 51.367, "lon": 42.083, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "борисоглебском р-не", "name": "Борисоглебск", "lat": 51.367, "lon": 42.083, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "борисоглебский", "name": "Борисоглебск", "lat": 51.367, "lon": 42.083, "type": "city", "subject": "Воронежская область"},
    {"pattern": "борисоглебском", "name": "Борисоглебск", "lat": 51.367, "lon": 42.083, "type": "city", "subject": "Воронежская область"},
    {"pattern": "богучарский район", "name": "Богучар", "lat": 49.93, "lon": 40.55, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "богучарском районе", "name": "Богучар", "lat": 49.93, "lon": 40.55, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "богучарский р-н", "name": "Богучар", "lat": 49.93, "lon": 40.55, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "богучарском р-не", "name": "Богучар", "lat": 49.93, "lon": 40.55, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "бутурлиновский район", "name": "Бутурлиновка", "lat": 50.83, "lon": 40.6, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "бутурлиновском районе", "name": "Бутурлиновка", "lat": 50.83, "lon": 40.6, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "бутурлиновский р-н", "name": "Бутурлиновка", "lat": 50.83, "lon": 40.6, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "бутурлиновском р-не", "name": "Бутурлиновка", "lat": 50.83, "lon": 40.6, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "верхнемамонский район", "name": "Верхний Мамон", "lat": 50.167, "lon": 40.383, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "верхнемамонском районе", "name": "Верхний Мамон", "lat": 50.167, "lon": 40.383, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "верхнемамонский р-н", "name": "Верхний Мамон", "lat": 50.167, "lon": 40.383, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "верхнемамонском р-не", "name": "Верхний Мамон", "lat": 50.167, "lon": 40.383, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "верхнехавский район", "name": "Верхняя Хава", "lat": 51.833, "lon": 39.933, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "верхнехавском районе", "name": "Верхняя Хава", "lat": 51.833, "lon": 39.933, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "верхнехавский р-н", "name": "Верхняя Хава", "lat": 51.833, "lon": 39.933, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "верхнехавском р-не", "name": "Верхняя Хава", "lat": 51.833, "lon": 39.933, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "воробьёвский район", "name": "Воробьёвка", "lat": 50.65, "lon": 40.933, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "воробьёвском районе", "name": "Воробьёвка", "lat": 50.65, "lon": 40.933, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "воробьёвский р-н", "name": "Воробьёвка", "lat": 50.65, "lon": 40.933, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "воробьёвском р-не", "name": "Воробьёвка", "lat": 50.65, "lon": 40.933, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "грибановский район", "name": "Грибановский", "lat": 51.45, "lon": 41.967, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "грибановском районе", "name": "Грибановский", "lat": 51.45, "lon": 41.967, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "грибановский р-н", "name": "Грибановский", "lat": 51.45, "lon": 41.967, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "грибановском р-не", "name": "Грибановский", "lat": 51.45, "lon": 41.967, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "калачеевский район", "name": "Калач", "lat": 50.43, "lon": 41.02, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "калачеевском районе", "name": "Калач", "lat": 50.43, "lon": 41.02, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "калачеевский р-н", "name": "Калач", "lat": 50.43, "lon": 41.02, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "калачеевском р-не", "name": "Калач", "lat": 50.43, "lon": 41.02, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "каменский район", "name": "Каменка", "lat": 50.717, "lon": 39.417, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "каменском районе", "name": "Каменка", "lat": 50.717, "lon": 39.417, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "каменский р-н", "name": "Каменка", "lat": 50.717, "lon": 39.417, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "каменском р-не", "name": "Каменка", "lat": 50.717, "lon": 39.417, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "кантемировский район", "name": "Кантемировка", "lat": 49.667, "lon": 39.85, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "кантемировском районе", "name": "Кантемировка", "lat": 49.667, "lon": 39.85, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "кантемировский р-н", "name": "Кантемировка", "lat": 49.667, "lon": 39.85, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "кантемировском р-не", "name": "Кантемировка", "lat": 49.667, "lon": 39.85, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "каширский район", "name": "Каширское", "lat": 51.4, "lon": 39.583, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "каширском районе", "name": "Каширское", "lat": 51.4, "lon": 39.583, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "каширский р-н", "name": "Каширское", "lat": 51.4, "lon": 39.583, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "каширском р-не", "name": "Каширское", "lat": 51.4, "lon": 39.583, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "лискинский район", "name": "Лиски", "lat": 50.98, "lon": 39.5, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "лискинском районе", "name": "Лиски", "lat": 50.98, "lon": 39.5, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "лискинский р-н", "name": "Лиски", "lat": 50.98, "lon": 39.5, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "лискинском р-не", "name": "Лиски", "lat": 50.98, "lon": 39.5, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "монастырщина", "name": "Монастырщина", "lat": 49.832, "lon": 40.921, "type": "city", "subject": "Воронежская область"},
    {"pattern": "монастырщине", "name": "Монастырщина", "lat": 49.832, "lon": 40.921, "type": "city", "subject": "Воронежская область"},
    {"pattern": "нижнедевицкий район", "name": "Нижнедевицк", "lat": 51.55, "lon": 38.367, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "нижнедевицком районе", "name": "Нижнедевицк", "lat": 51.55, "lon": 38.367, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "нижнедевицкий р-н", "name": "Нижнедевицк", "lat": 51.55, "lon": 38.367, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "нижнедевицком р-не", "name": "Нижнедевицк", "lat": 51.55, "lon": 38.367, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "новоусманский район", "name": "Новая Усмань", "lat": 51.65, "lon": 39.4, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "новоусманском районе", "name": "Новая Усмань", "lat": 51.65, "lon": 39.4, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "новоусманский р-н", "name": "Новая Усмань", "lat": 51.65, "lon": 39.4, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "новоусманском р-не", "name": "Новая Усмань", "lat": 51.65, "lon": 39.4, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "новохопёрский район", "name": "Новохопёрск", "lat": 51.1, "lon": 41.62, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "новохопёрском районе", "name": "Новохопёрск", "lat": 51.1, "lon": 41.62, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "новохопёрский р-н", "name": "Новохопёрск", "lat": 51.1, "lon": 41.62, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "новохопёрском р-не", "name": "Новохопёрск", "lat": 51.1, "lon": 41.62, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "ольховатский район", "name": "Ольховатка", "lat": 50.283, "lon": 39.3, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "ольховатском районе", "name": "Ольховатка", "lat": 50.283, "lon": 39.3, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "ольховатский р-н", "name": "Ольховатка", "lat": 50.283, "lon": 39.3, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "ольховатском р-не", "name": "Ольховатка", "lat": 50.283, "lon": 39.3, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "острогожский район", "name": "Острогожск", "lat": 50.87, "lon": 39.07, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "острогожском районе", "name": "Острогожск", "lat": 50.87, "lon": 39.07, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "острогожский р-н", "name": "Острогожск", "lat": 50.87, "lon": 39.07, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "острогожском р-не", "name": "Острогожск", "lat": 50.87, "lon": 39.07, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "павловский район", "name": "Павловск", "lat": 50.45, "lon": 40.13, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "павловском районе", "name": "Павловск", "lat": 50.45, "lon": 40.13, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "павловский р-н", "name": "Павловск", "lat": 50.45, "lon": 40.13, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "павловском р-не", "name": "Павловск", "lat": 50.45, "lon": 40.13, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "панинский район", "name": "Панино", "lat": 51.65, "lon": 40.133, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "панинском районе", "name": "Панино", "lat": 51.65, "lon": 40.133, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "панинский р-н", "name": "Панино", "lat": 51.65, "lon": 40.133, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "панинском р-не", "name": "Панино", "lat": 51.65, "lon": 40.133, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "петропавловский район", "name": "Петропавловка", "lat": 50.1, "lon": 40.883, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "петропавловском районе", "name": "Петропавловка", "lat": 50.1, "lon": 40.883, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "петропавловский р-н", "name": "Петропавловка", "lat": 50.1, "lon": 40.883, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "петропавловском р-не", "name": "Петропавловка", "lat": 50.1, "lon": 40.883, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "поворинский район", "name": "Поворино", "lat": 51.2, "lon": 42.25, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "поворинском районе", "name": "Поворино", "lat": 51.2, "lon": 42.25, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "поворинский р-н", "name": "Поворино", "lat": 51.2, "lon": 42.25, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "поворинском р-не", "name": "Поворино", "lat": 51.2, "lon": 42.25, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "подгоренский район", "name": "Подгоренский", "lat": 50.4, "lon": 39.65, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "подгоренском районе", "name": "Подгоренский", "lat": 50.4, "lon": 39.65, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "подгоренский р-н", "name": "Подгоренский", "lat": 50.4, "lon": 39.65, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "подгоренском р-не", "name": "Подгоренский", "lat": 50.4, "lon": 39.65, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "рамонский район", "name": "Рамонь", "lat": 51.917, "lon": 39.333, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "рамонском районе", "name": "Рамонь", "lat": 51.917, "lon": 39.333, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "рамонский р-н", "name": "Рамонь", "lat": 51.917, "lon": 39.333, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "рамонском р-не", "name": "Рамонь", "lat": 51.917, "lon": 39.333, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "репьёвский район", "name": "Репьёвка", "lat": 51.083, "lon": 38.633, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "репьёвском районе", "name": "Репьёвка", "lat": 51.083, "lon": 38.633, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "репьёвский р-н", "name": "Репьёвка", "lat": 51.083, "lon": 38.633, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "репьёвском р-не", "name": "Репьёвка", "lat": 51.083, "lon": 38.633, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "россошанский район", "name": "Россошь", "lat": 50.2, "lon": 39.57, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "россошанском районе", "name": "Россошь", "lat": 50.2, "lon": 39.57, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "россошанский р-н", "name": "Россошь", "lat": 50.2, "lon": 39.57, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "россошанском р-не", "name": "Россошь", "lat": 50.2, "lon": 39.57, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "семилукский район", "name": "Семилуки", "lat": 51.68, "lon": 39.03, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "семилукском районе", "name": "Семилуки", "lat": 51.68, "lon": 39.03, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "семилукский р-н", "name": "Семилуки", "lat": 51.68, "lon": 39.03, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "семилукском р-не", "name": "Семилуки", "lat": 51.68, "lon": 39.03, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "таловский район", "name": "Таловая", "lat": 51.117, "lon": 40.717, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "таловском районе", "name": "Таловая", "lat": 51.117, "lon": 40.717, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "таловский р-н", "name": "Таловая", "lat": 51.117, "lon": 40.717, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "таловском р-не", "name": "Таловая", "lat": 51.117, "lon": 40.717, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "терновский район", "name": "Терновка", "lat": 51.683, "lon": 41.633, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "терновском районе", "name": "Терновка", "lat": 51.683, "lon": 41.633, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "терновский р-н", "name": "Терновка", "lat": 51.683, "lon": 41.633, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "терновском р-не", "name": "Терновка", "lat": 51.683, "lon": 41.633, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "хохольский район", "name": "Хохольский", "lat": 51.567, "lon": 38.8, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "хохольском районе", "name": "Хохольский", "lat": 51.567, "lon": 38.8, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "хохольский р-н", "name": "Хохольский", "lat": 51.567, "lon": 38.8, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "хохольском р-не", "name": "Хохольский", "lat": 51.567, "lon": 38.8, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "эртильский район", "name": "Эртиль", "lat": 51.83, "lon": 40.8, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "эртильском районе", "name": "Эртиль", "lat": 51.83, "lon": 40.8, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "эртильский р-н", "name": "Эртиль", "lat": 51.83, "lon": 40.8, "type": "region", "is_region": True, "subject": "Воронежская область"},
    {"pattern": "эртильском р-не", "name": "Эртиль", "lat": 51.83, "lon": 40.8, "type": "region", "is_region": True, "subject": "Воронежская область"},

    # Воронежская область — населённые пункты не из CITY_DB
    {"pattern": "нижнедевицк", "name": "Нижнедевицк", "lat": 51.55, "lon": 38.367, "type": "city", "subject": "Воронежская область"},
    {"pattern": "нижнедевицке", "name": "Нижнедевицк", "lat": 51.55, "lon": 38.367, "type": "city", "subject": "Воронежская область"},
    {"pattern": "репьёвка", "name": "Репьёвка", "lat": 51.083, "lon": 38.633, "type": "city", "subject": "Воронежская область"},
    {"pattern": "репьёвке", "name": "Репьёвка", "lat": 51.083, "lon": 38.633, "type": "city", "subject": "Воронежская область"},
    {"pattern": "таловая", "name": "Таловая", "lat": 51.117, "lon": 40.717, "type": "city", "subject": "Воронежская область"},
    {"pattern": "таловае", "name": "Таловая", "lat": 51.117, "lon": 40.717, "type": "city", "subject": "Воронежская область"},

    # Липецкая область — районы
    {"pattern": "воловский район", "name": "Волово", "lat": 52.017, "lon": 37.883, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "воловском районе", "name": "Волово", "lat": 52.017, "lon": 37.883, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "воловский р-н", "name": "Волово", "lat": 52.017, "lon": 37.883, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "воловском р-не", "name": "Волово", "lat": 52.017, "lon": 37.883, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "грязинский район", "name": "Грязи", "lat": 52.5, "lon": 39.93, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "грязинском районе", "name": "Грязи", "lat": 52.5, "lon": 39.93, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "грязинский р-н", "name": "Грязи", "lat": 52.5, "lon": 39.93, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "грязинском р-не", "name": "Грязи", "lat": 52.5, "lon": 39.93, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "данковский район", "name": "Данков", "lat": 53.25, "lon": 39.15, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "данковском районе", "name": "Данков", "lat": 53.25, "lon": 39.15, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "данковский р-н", "name": "Данков", "lat": 53.25, "lon": 39.15, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "данковском р-не", "name": "Данков", "lat": 53.25, "lon": 39.15, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "добринский район", "name": "Добринка", "lat": 52.167, "lon": 40.467, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "добринском районе", "name": "Добринка", "lat": 52.167, "lon": 40.467, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "добринский р-н", "name": "Добринка", "lat": 52.167, "lon": 40.467, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "добринском р-не", "name": "Добринка", "lat": 52.167, "lon": 40.467, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "добровский район", "name": "Доброе", "lat": 52.867, "lon": 39.8, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "добровском районе", "name": "Доброе", "lat": 52.867, "lon": 39.8, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "добровский р-н", "name": "Доброе", "lat": 52.867, "lon": 39.8, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "добровском р-не", "name": "Доброе", "lat": 52.867, "lon": 39.8, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "долгоруковский район", "name": "Долгоруково", "lat": 52.317, "lon": 38.35, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "долгоруковском районе", "name": "Долгоруково", "lat": 52.317, "lon": 38.35, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "долгоруковский р-н", "name": "Долгоруково", "lat": 52.317, "lon": 38.35, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "долгоруковском р-не", "name": "Долгоруково", "lat": 52.317, "lon": 38.35, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "елецкий район", "name": "Елец", "lat": 52.62, "lon": 38.5, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "елецком районе", "name": "Елец", "lat": 52.62, "lon": 38.5, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "елецкий р-н", "name": "Елец", "lat": 52.62, "lon": 38.5, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "елецком р-не", "name": "Елец", "lat": 52.62, "lon": 38.5, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "задонский район", "name": "Задонск", "lat": 52.38, "lon": 38.92, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "задонском районе", "name": "Задонск", "lat": 52.38, "lon": 38.92, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "задонский р-н", "name": "Задонск", "lat": 52.38, "lon": 38.92, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "задонском р-не", "name": "Задонск", "lat": 52.38, "lon": 38.92, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "измалковский район", "name": "Измалково", "lat": 52.683, "lon": 37.983, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "измалковском районе", "name": "Измалково", "lat": 52.683, "lon": 37.983, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "измалковский р-н", "name": "Измалково", "lat": 52.683, "lon": 37.983, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "измалковском р-не", "name": "Измалково", "lat": 52.683, "lon": 37.983, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "краснинский район", "name": "Красное", "lat": 52.85, "lon": 38.783, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "краснинском районе", "name": "Красное", "lat": 52.85, "lon": 38.783, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "краснинский р-н", "name": "Красное", "lat": 52.85, "lon": 38.783, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "краснинском р-не", "name": "Красное", "lat": 52.85, "lon": 38.783, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "лебедянский район", "name": "Лебедянь", "lat": 53.0, "lon": 39.15, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "лебедянском районе", "name": "Лебедянь", "lat": 53.0, "lon": 39.15, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "лебедянский р-н", "name": "Лебедянь", "lat": 53.0, "lon": 39.15, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "лебедянском р-не", "name": "Лебедянь", "lat": 53.0, "lon": 39.15, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "лев-толстовский район", "name": "Лев Толстой", "lat": 53.2, "lon": 39.45, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "лев-толстовском районе", "name": "Лев Толстой", "lat": 53.2, "lon": 39.45, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "лев-толстовский р-н", "name": "Лев Толстой", "lat": 53.2, "lon": 39.45, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "лев-толстовском р-не", "name": "Лев Толстой", "lat": 53.2, "lon": 39.45, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "липецкий район", "name": "Липецк", "lat": 52.6, "lon": 39.6, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "липецком районе", "name": "Липецк", "lat": 52.6, "lon": 39.6, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "липецкий р-н", "name": "Липецк", "lat": 52.6, "lon": 39.6, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "липецком р-не", "name": "Липецк", "lat": 52.6, "lon": 39.6, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "становлянский район", "name": "Становое", "lat": 52.767, "lon": 38.35, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "становлянском районе", "name": "Становое", "lat": 52.767, "lon": 38.35, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "становлянский р-н", "name": "Становое", "lat": 52.767, "lon": 38.35, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "становлянском р-не", "name": "Становое", "lat": 52.767, "lon": 38.35, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "тербунский район", "name": "Тербуны", "lat": 52.133, "lon": 38.283, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "тербунском районе", "name": "Тербуны", "lat": 52.133, "lon": 38.283, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "тербунский р-н", "name": "Тербуны", "lat": 52.133, "lon": 38.283, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "тербунском р-не", "name": "Тербуны", "lat": 52.133, "lon": 38.283, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "усманский район", "name": "Усмань", "lat": 52.05, "lon": 39.73, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "усманском районе", "name": "Усмань", "lat": 52.05, "lon": 39.73, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "усманский р-н", "name": "Усмань", "lat": 52.05, "lon": 39.73, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "усманском р-не", "name": "Усмань", "lat": 52.05, "lon": 39.73, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "хлевенский район", "name": "Хлевное", "lat": 52.2, "lon": 39.083, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "хлевенском районе", "name": "Хлевное", "lat": 52.2, "lon": 39.083, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "хлевенский р-н", "name": "Хлевное", "lat": 52.2, "lon": 39.083, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "хлевенском р-не", "name": "Хлевное", "lat": 52.2, "lon": 39.083, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "чаплыгинский район", "name": "Чаплыгин", "lat": 53.25, "lon": 39.95, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "чаплыгинском районе", "name": "Чаплыгин", "lat": 53.25, "lon": 39.95, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "чаплыгинский р-н", "name": "Чаплыгин", "lat": 53.25, "lon": 39.95, "type": "region", "is_region": True, "subject": "Липецкая область"},
    {"pattern": "чаплыгинском р-не", "name": "Чаплыгин", "lat": 53.25, "lon": 39.95, "type": "region", "is_region": True, "subject": "Липецкая область"},

    # Липецкая область — населённые пункты не из CITY_DB
    {"pattern": "волово", "name": "Волово", "lat": 52.017, "lon": 37.883, "type": "city", "subject": "Липецкая область"},
    {"pattern": "добринка", "name": "Добринка", "lat": 52.167, "lon": 40.467, "type": "city", "subject": "Липецкая область"},
    {"pattern": "добринке", "name": "Добринка", "lat": 52.167, "lon": 40.467, "type": "city", "subject": "Липецкая область"},
    {"pattern": "доброе", "name": "Доброе", "lat": 52.867, "lon": 39.8, "type": "city", "subject": "Липецкая область"},
    {"pattern": "долгоруково", "name": "Долгоруково", "lat": 52.317, "lon": 38.35, "type": "city", "subject": "Липецкая область"},
    {"pattern": "измалково", "name": "Измалково", "lat": 52.683, "lon": 37.983, "type": "city", "subject": "Липецкая область"},
    {"pattern": "красное", "name": "Красное", "lat": 52.85, "lon": 38.783, "type": "city", "subject": "Липецкая область"},
    {"pattern": "лев толстой", "name": "Лев Толстой", "lat": 53.2, "lon": 39.45, "type": "city", "subject": "Липецкая область"},
    {"pattern": "лев толстое", "name": "Лев Толстой", "lat": 53.2, "lon": 39.45, "type": "city", "subject": "Липецкая область"},
    {"pattern": "становое", "name": "Становое", "lat": 52.767, "lon": 38.35, "type": "city", "subject": "Липецкая область"},
    {"pattern": "тербуны", "name": "Тербуны", "lat": 52.133, "lon": 38.283, "type": "city", "subject": "Липецкая область"},
    {"pattern": "хлевное", "name": "Хлевное", "lat": 52.2, "lon": 39.083, "type": "city", "subject": "Липецкая область"},

    # Тульская область — районы
    {"pattern": "арсеньевский район", "name": "Арсеньево", "lat": 53.733, "lon": 36.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "арсеньевском районе", "name": "Арсеньево", "lat": 53.733, "lon": 36.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "арсеньевский р-н", "name": "Арсеньево", "lat": 53.733, "lon": 36.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "арсеньевском р-не", "name": "Арсеньево", "lat": 53.733, "lon": 36.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "белёвский район", "name": "Белёв", "lat": 53.8, "lon": 36.13, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "белёвском районе", "name": "Белёв", "lat": 53.8, "lon": 36.13, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "белёвский р-н", "name": "Белёв", "lat": 53.8, "lon": 36.13, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "белёвском р-не", "name": "Белёв", "lat": 53.8, "lon": 36.13, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "богородицкий район", "name": "Богородицк", "lat": 53.77, "lon": 38.12, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "богородицком районе", "name": "Богородицк", "lat": 53.77, "lon": 38.12, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "богородицкий р-н", "name": "Богородицк", "lat": 53.77, "lon": 38.12, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "богородицком р-не", "name": "Богородицк", "lat": 53.77, "lon": 38.12, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "венёвский район", "name": "Венёв", "lat": 54.35, "lon": 38.27, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "венёвском районе", "name": "Венёв", "lat": 54.35, "lon": 38.27, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "венёвский р-н", "name": "Венёв", "lat": 54.35, "lon": 38.27, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "венёвском р-не", "name": "Венёв", "lat": 54.35, "lon": 38.27, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "воловский район", "name": "Волово", "lat": 53.95, "lon": 38.0, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "воловском районе", "name": "Волово", "lat": 53.95, "lon": 38.0, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "воловский р-н", "name": "Волово", "lat": 53.95, "lon": 38.0, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "воловском р-не", "name": "Волово", "lat": 53.95, "lon": 38.0, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "дубенский район", "name": "Дубна", "lat": 54.15, "lon": 36.95, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "дубенском районе", "name": "Дубна", "lat": 54.15, "lon": 36.95, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "дубенский р-н", "name": "Дубна", "lat": 54.15, "lon": 36.95, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "дубенском р-не", "name": "Дубна", "lat": 54.15, "lon": 36.95, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "ефремовский район", "name": "Ефремов", "lat": 53.15, "lon": 38.12, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "ефремовском районе", "name": "Ефремов", "lat": 53.15, "lon": 38.12, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "ефремовский р-н", "name": "Ефремов", "lat": 53.15, "lon": 38.12, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "ефремовском р-не", "name": "Ефремов", "lat": 53.15, "lon": 38.12, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "заокский район", "name": "Заокский", "lat": 54.733, "lon": 37.4, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "заокском районе", "name": "Заокский", "lat": 54.733, "lon": 37.4, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "заокский р-н", "name": "Заокский", "lat": 54.733, "lon": 37.4, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "заокском р-не", "name": "Заокский", "lat": 54.733, "lon": 37.4, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "каменский район", "name": "Архангельское", "lat": 53.35, "lon": 37.667, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "каменском районе", "name": "Архангельское", "lat": 53.35, "lon": 37.667, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "каменский р-н", "name": "Архангельское", "lat": 53.35, "lon": 37.667, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "каменском р-не", "name": "Архангельское", "lat": 53.35, "lon": 37.667, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "кимовский район", "name": "Кимовск", "lat": 53.97, "lon": 38.53, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "кимовском районе", "name": "Кимовск", "lat": 53.97, "lon": 38.53, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "кимовский р-н", "name": "Кимовск", "lat": 53.97, "lon": 38.53, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "кимовском р-не", "name": "Кимовск", "lat": 53.97, "lon": 38.53, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "киреевский район", "name": "Киреевск", "lat": 53.93, "lon": 37.93, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "киреевском районе", "name": "Киреевск", "lat": 53.93, "lon": 37.93, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "киреевский р-н", "name": "Киреевск", "lat": 53.93, "lon": 37.93, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "киреевском р-не", "name": "Киреевск", "lat": 53.93, "lon": 37.93, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "куркинский район", "name": "Куркино", "lat": 53.483, "lon": 38.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "куркинском районе", "name": "Куркино", "lat": 53.483, "lon": 38.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "куркинский р-н", "name": "Куркино", "lat": 53.483, "lon": 38.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "куркинском р-не", "name": "Куркино", "lat": 53.483, "lon": 38.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "ленинский район", "name": "Ленинский", "lat": 54.1, "lon": 37.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "ленинском районе", "name": "Ленинский", "lat": 54.1, "lon": 37.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "ленинский р-н", "name": "Ленинский", "lat": 54.1, "lon": 37.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "ленинском р-не", "name": "Ленинский", "lat": 54.1, "lon": 37.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "новомосковский район", "name": "Новомосковск", "lat": 54.03, "lon": 38.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "новомосковском районе", "name": "Новомосковск", "lat": 54.03, "lon": 38.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "новомосковский р-н", "name": "Новомосковск", "lat": 54.03, "lon": 38.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "новомосковском р-не", "name": "Новомосковск", "lat": 54.03, "lon": 38.65, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "одоевский район", "name": "Одоев", "lat": 53.93, "lon": 36.68, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "одоевском районе", "name": "Одоев", "lat": 53.93, "lon": 36.68, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "одоевский р-н", "name": "Одоев", "lat": 53.93, "lon": 36.68, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "одоевском р-не", "name": "Одоев", "lat": 53.93, "lon": 36.68, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "плавский район", "name": "Плавск", "lat": 53.7, "lon": 37.3, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "плавском районе", "name": "Плавск", "lat": 53.7, "lon": 37.3, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "плавский р-н", "name": "Плавск", "lat": 53.7, "lon": 37.3, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "плавском р-не", "name": "Плавск", "lat": 53.7, "lon": 37.3, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "суворовский район", "name": "Суворов", "lat": 54.12, "lon": 36.5, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "суворовском районе", "name": "Суворов", "lat": 54.12, "lon": 36.5, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "суворовский р-н", "name": "Суворов", "lat": 54.12, "lon": 36.5, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "суворовском р-не", "name": "Суворов", "lat": 54.12, "lon": 36.5, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "тёпло-огарёвский район", "name": "Тёплое", "lat": 53.617, "lon": 37.583, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "тёпло-огарёвском районе", "name": "Тёплое", "lat": 53.617, "lon": 37.583, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "тёпло-огарёвский р-н", "name": "Тёплое", "lat": 53.617, "lon": 37.583, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "тёпло-огарёвском р-не", "name": "Тёплое", "lat": 53.617, "lon": 37.583, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "узловский район", "name": "Узловая", "lat": 53.98, "lon": 38.18, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "узловском районе", "name": "Узловая", "lat": 53.98, "lon": 38.18, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "узловский р-н", "name": "Узловая", "lat": 53.98, "lon": 38.18, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "узловском р-не", "name": "Узловая", "lat": 53.98, "lon": 38.18, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "чернский район", "name": "Чернь", "lat": 53.45, "lon": 36.9, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "чернском районе", "name": "Чернь", "lat": 53.45, "lon": 36.9, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "чернский р-н", "name": "Чернь", "lat": 53.45, "lon": 36.9, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "чернском р-не", "name": "Чернь", "lat": 53.45, "lon": 36.9, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "щёкинский район", "name": "Щёкино", "lat": 53.97, "lon": 37.52, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "щёкинском районе", "name": "Щёкино", "lat": 53.97, "lon": 37.52, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "щёкинский р-н", "name": "Щёкино", "lat": 53.97, "lon": 37.52, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "щёкинском р-не", "name": "Щёкино", "lat": 53.97, "lon": 37.52, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "ясногорский район", "name": "Ясногорск", "lat": 54.48, "lon": 37.7, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "ясногорском районе", "name": "Ясногорск", "lat": 54.48, "lon": 37.7, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "ясногорский р-н", "name": "Ясногорск", "lat": 54.48, "lon": 37.7, "type": "region", "is_region": True, "subject": "Тульская область"},
    {"pattern": "ясногорском р-не", "name": "Ясногорск", "lat": 54.48, "lon": 37.7, "type": "region", "is_region": True, "subject": "Тульская область"},

    # Тульская область — населённые пункты не из CITY_DB
    {"pattern": "арсеньево", "name": "Арсеньево", "lat": 53.733, "lon": 36.65, "type": "city", "subject": "Тульская область"},
    {"pattern": "волово", "name": "Волово", "lat": 53.95, "lon": 38.0, "type": "city", "subject": "Тульская область"},
    {"pattern": "дубна", "name": "Дубна", "lat": 54.15, "lon": 36.95, "type": "city", "subject": "Тульская область"},
    {"pattern": "дубне", "name": "Дубна", "lat": 54.15, "lon": 36.95, "type": "city", "subject": "Тульская область"},
    {"pattern": "заокский", "name": "Заокский", "lat": 54.733, "lon": 37.4, "type": "city", "subject": "Тульская область"},
    {"pattern": "заокские", "name": "Заокский", "lat": 54.733, "lon": 37.4, "type": "city", "subject": "Тульская область"},
    {"pattern": "архангельское", "name": "Архангельское", "lat": 53.35, "lon": 37.667, "type": "city", "subject": "Тульская область"},
    {"pattern": "куркино", "name": "Куркино", "lat": 53.483, "lon": 38.65, "type": "city", "subject": "Тульская область"},
    {"pattern": "ленинский", "name": "Ленинский", "lat": 54.1, "lon": 37.65, "type": "city", "subject": "Тульская область"},
    {"pattern": "ленинские", "name": "Ленинский", "lat": 54.1, "lon": 37.65, "type": "city", "subject": "Тульская область"},
    {"pattern": "одоев", "name": "Одоев", "lat": 53.93, "lon": 36.68, "type": "city", "subject": "Тульская область"},
    {"pattern": "одоеве", "name": "Одоев", "lat": 53.93, "lon": 36.68, "type": "city", "subject": "Тульская область"},
    {"pattern": "тёплое", "name": "Тёплое", "lat": 53.617, "lon": 37.583, "type": "city", "subject": "Тульская область"},
    {"pattern": "чернь", "name": "Чернь", "lat": 53.45, "lon": 36.9, "type": "city", "subject": "Тульская область"},
    {"pattern": "черне", "name": "Чернь", "lat": 53.45, "lon": 36.9, "type": "city", "subject": "Тульская область"},

    # Калужская область — районы
    {"pattern": "бабынинский район", "name": "Бабынино", "lat": 54.4, "lon": 35.717, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "бабынинском районе", "name": "Бабынино", "lat": 54.4, "lon": 35.717, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "бабынинский р-н", "name": "Бабынино", "lat": 54.4, "lon": 35.717, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "бабынинском р-не", "name": "Бабынино", "lat": 54.4, "lon": 35.717, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "барятинский район", "name": "Барятино", "lat": 54.3, "lon": 34.517, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "барятинском районе", "name": "Барятино", "lat": 54.3, "lon": 34.517, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "барятинский р-н", "name": "Барятино", "lat": 54.3, "lon": 34.517, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "барятинском р-не", "name": "Барятино", "lat": 54.3, "lon": 34.517, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "боровский район", "name": "Боровск", "lat": 55.2, "lon": 36.48, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "боровском районе", "name": "Боровск", "lat": 55.2, "lon": 36.48, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "боровский р-н", "name": "Боровск", "lat": 55.2, "lon": 36.48, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "боровском р-не", "name": "Боровск", "lat": 55.2, "lon": 36.48, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "дзержинский район", "name": "Кондрово", "lat": 54.8, "lon": 35.93, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "дзержинском районе", "name": "Кондрово", "lat": 54.8, "lon": 35.93, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "дзержинский р-н", "name": "Кондрово", "lat": 54.8, "lon": 35.93, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "дзержинском р-не", "name": "Кондрово", "lat": 54.8, "lon": 35.93, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "думиничский район", "name": "Думиничи", "lat": 54.0, "lon": 35.1, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "думиничском районе", "name": "Думиничи", "lat": 54.0, "lon": 35.1, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "думиничский р-н", "name": "Думиничи", "lat": 54.0, "lon": 35.1, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "думиничском р-не", "name": "Думиничи", "lat": 54.0, "lon": 35.1, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "жиздринский район", "name": "Жиздра", "lat": 53.75, "lon": 34.733, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "жиздринском районе", "name": "Жиздра", "lat": 53.75, "lon": 34.733, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "жиздринский р-н", "name": "Жиздра", "lat": 53.75, "lon": 34.733, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "жиздринском р-не", "name": "Жиздра", "lat": 53.75, "lon": 34.733, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "жуковский район", "name": "Жуков", "lat": 55.03, "lon": 36.75, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "жуковском районе", "name": "Жуков", "lat": 55.03, "lon": 36.75, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "жуковский р-н", "name": "Жуков", "lat": 55.03, "lon": 36.75, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "жуковском р-не", "name": "Жуков", "lat": 55.03, "lon": 36.75, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "износковский район", "name": "Износки", "lat": 54.983, "lon": 35.317, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "износковском районе", "name": "Износки", "lat": 54.983, "lon": 35.317, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "износковский р-н", "name": "Износки", "lat": 54.983, "lon": 35.317, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "износковском р-не", "name": "Износки", "lat": 54.983, "lon": 35.317, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "кировский район", "name": "Киров", "lat": 54.08, "lon": 34.3, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "кировском районе", "name": "Киров", "lat": 54.08, "lon": 34.3, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "кировский р-н", "name": "Киров", "lat": 54.08, "lon": 34.3, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "кировском р-не", "name": "Киров", "lat": 54.08, "lon": 34.3, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "козельский район", "name": "Козельск", "lat": 54.03, "lon": 35.78, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "козельском районе", "name": "Козельск", "lat": 54.03, "lon": 35.78, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "козельский р-н", "name": "Козельск", "lat": 54.03, "lon": 35.78, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "козельском р-не", "name": "Козельск", "lat": 54.03, "lon": 35.78, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "куйбышевский район", "name": "Бетлица", "lat": 54.017, "lon": 33.95, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "куйбышевском районе", "name": "Бетлица", "lat": 54.017, "lon": 33.95, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "куйбышевский р-н", "name": "Бетлица", "lat": 54.017, "lon": 33.95, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "куйбышевском р-не", "name": "Бетлица", "lat": 54.017, "lon": 33.95, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "куйбышевский район", "name": "Куйбышево", "lat": 47.817, "lon": 38.908, "type": "region", "is_region": True, "subject": "Ростовская область"},
    {"pattern": "куйбышевском районе", "name": "Куйбышево", "lat": 47.817, "lon": 38.908, "type": "region", "is_region": True, "subject": "Ростовская область"},
    {"pattern": "куйбышевский р-н", "name": "Куйбышево", "lat": 47.817, "lon": 38.908, "type": "region", "is_region": True, "subject": "Ростовская область"},
    {"pattern": "куйбышевском р-не", "name": "Куйбышево", "lat": 47.817, "lon": 38.908, "type": "region", "is_region": True, "subject": "Ростовская область"},
    {"pattern": "людиновский район", "name": "Людиново", "lat": 53.87, "lon": 34.45, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "людиновском районе", "name": "Людиново", "lat": 53.87, "lon": 34.45, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "людиновский р-н", "name": "Людиново", "lat": 53.87, "lon": 34.45, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "людиновском р-не", "name": "Людиново", "lat": 53.87, "lon": 34.45, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "малоярославецкий район", "name": "Малоярославец", "lat": 55.02, "lon": 36.47, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "малоярославецком районе", "name": "Малоярославец", "lat": 55.02, "lon": 36.47, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "малоярославецкий р-н", "name": "Малоярославец", "lat": 55.02, "lon": 36.47, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "малоярославецком р-не", "name": "Малоярославец", "lat": 55.02, "lon": 36.47, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "медынский район", "name": "Медынь", "lat": 54.97, "lon": 35.86, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "медынском районе", "name": "Медынь", "lat": 54.97, "lon": 35.86, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "медынский р-н", "name": "Медынь", "lat": 54.97, "lon": 35.86, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "медынском р-не", "name": "Медынь", "lat": 54.97, "lon": 35.86, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "мещовский район", "name": "Мещовск", "lat": 54.32, "lon": 35.28, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "мещовском районе", "name": "Мещовск", "lat": 54.32, "lon": 35.28, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "мещовский р-н", "name": "Мещовск", "lat": 54.32, "lon": 35.28, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "мещовском р-не", "name": "Мещовск", "lat": 54.32, "lon": 35.28, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "мосальский район", "name": "Мосальск", "lat": 54.48, "lon": 34.98, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "мосальском районе", "name": "Мосальск", "lat": 54.48, "lon": 34.98, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "мосальский р-н", "name": "Мосальск", "lat": 54.48, "lon": 34.98, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "мосальском р-не", "name": "Мосальск", "lat": 54.48, "lon": 34.98, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "перемышльский район", "name": "Перемышль", "lat": 54.267, "lon": 36.167, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "перемышльском районе", "name": "Перемышль", "lat": 54.267, "lon": 36.167, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "перемышльский р-н", "name": "Перемышль", "lat": 54.267, "lon": 36.167, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "перемышльском р-не", "name": "Перемышль", "lat": 54.267, "lon": 36.167, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "спас-деменский район", "name": "Спас-Деменск", "lat": 54.42, "lon": 34.02, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "спас-деменском районе", "name": "Спас-Деменск", "lat": 54.42, "lon": 34.02, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "спас-деменский р-н", "name": "Спас-Деменск", "lat": 54.42, "lon": 34.02, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "спас-деменском р-не", "name": "Спас-Деменск", "lat": 54.42, "lon": 34.02, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "сухиничский район", "name": "Сухиничи", "lat": 54.1, "lon": 35.35, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "сухиничском районе", "name": "Сухиничи", "lat": 54.1, "lon": 35.35, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "сухиничский р-н", "name": "Сухиничи", "lat": 54.1, "lon": 35.35, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "сухиничском р-не", "name": "Сухиничи", "lat": 54.1, "lon": 35.35, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "тарусский район", "name": "Таруса", "lat": 54.72, "lon": 37.18, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "тарусском районе", "name": "Таруса", "lat": 54.72, "lon": 37.18, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "тарусский р-н", "name": "Таруса", "lat": 54.72, "lon": 37.18, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "тарусском р-не", "name": "Таруса", "lat": 54.72, "lon": 37.18, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "ульяновский район", "name": "Ульяново", "lat": 53.717, "lon": 35.533, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "ульяновском районе", "name": "Ульяново", "lat": 53.717, "lon": 35.533, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "ульяновский р-н", "name": "Ульяново", "lat": 53.717, "lon": 35.533, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "ульяновском р-не", "name": "Ульяново", "lat": 53.717, "lon": 35.533, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "ферзиковский район", "name": "Ферзиково", "lat": 54.5, "lon": 36.75, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "ферзиковском районе", "name": "Ферзиково", "lat": 54.5, "lon": 36.75, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "ферзиковский р-н", "name": "Ферзиково", "lat": 54.5, "lon": 36.75, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "ферзиковском р-не", "name": "Ферзиково", "lat": 54.5, "lon": 36.75, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "хвастовичский район", "name": "Хвастовичи", "lat": 53.467, "lon": 35.1, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "хвастовичском районе", "name": "Хвастовичи", "lat": 53.467, "lon": 35.1, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "хвастовичский р-н", "name": "Хвастовичи", "lat": 53.467, "lon": 35.1, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "хвастовичском р-не", "name": "Хвастовичи", "lat": 53.467, "lon": 35.1, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "юхновский район", "name": "Юхнов", "lat": 54.75, "lon": 35.23, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "юхновском районе", "name": "Юхнов", "lat": 54.75, "lon": 35.23, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "юхновский р-н", "name": "Юхнов", "lat": 54.75, "lon": 35.23, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "юхновском р-не", "name": "Юхнов", "lat": 54.75, "lon": 35.23, "type": "region", "is_region": True, "subject": "Калужская область"},

    # Калужская область — населённые пункты не из CITY_DB
    {"pattern": "бабынино", "name": "Бабынино", "lat": 54.4, "lon": 35.717, "type": "city", "subject": "Калужская область"},
    {"pattern": "барятино", "name": "Барятино", "lat": 54.3, "lon": 34.517, "type": "city", "subject": "Калужская область"},
    {"pattern": "думиничи", "name": "Думиничи", "lat": 54.0, "lon": 35.1, "type": "city", "subject": "Калужская область"},
    {"pattern": "износки", "name": "Износки", "lat": 54.983, "lon": 35.317, "type": "city", "subject": "Калужская область"},
    {"pattern": "бетлица", "name": "Бетлица", "lat": 54.017, "lon": 33.95, "type": "city", "subject": "Калужская область"},
    {"pattern": "бетлице", "name": "Бетлица", "lat": 54.017, "lon": 33.95, "type": "city", "subject": "Калужская область"},
    {"pattern": "перемышль", "name": "Перемышль", "lat": 54.267, "lon": 36.167, "type": "city", "subject": "Калужская область"},
    {"pattern": "перемышле", "name": "Перемышль", "lat": 54.267, "lon": 36.167, "type": "city", "subject": "Калужская область"},
    {"pattern": "ульяново", "name": "Ульяново", "lat": 53.717, "lon": 35.533, "type": "city", "subject": "Калужская область"},
    {"pattern": "ферзиково", "name": "Ферзиково", "lat": 54.5, "lon": 36.75, "type": "city", "subject": "Калужская область"},
    {"pattern": "хвастовичи", "name": "Хвастовичи", "lat": 53.467, "lon": 35.1, "type": "city", "subject": "Калужская область"},
    # Дзержинский район, Калужская область (адм. центр — Кондрово)
    {"pattern": "дзержинский район", "name": "Кондрово", "lat": 54.8, "lon": 35.93333, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "дзержинском районе", "name": "Кондрово", "lat": 54.8, "lon": 35.93333, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "дзержинский р-н", "name": "Кондрово", "lat": 54.8, "lon": 35.93333, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "дзержинском р-не", "name": "Кондрово", "lat": 54.8, "lon": 35.93333, "type": "region", "is_region": True, "subject": "Калужская область"},
    {"pattern": "острожное", "name": "Острожное", "lat": 54.79, "lon": 35.96, "type": "city", "subject": "Калужская область"},
    {"pattern": "кудиново", "name": "Кудиново", "lat": 54.83, "lon": 35.98, "type": "city", "subject": "Калужская область"},

    # Орловская область — районы
    {"pattern": "болховский район", "name": "Болхов", "lat": 53.45, "lon": 36.0, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "болховском районе", "name": "Болхов", "lat": 53.45, "lon": 36.0, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "болховский р-н", "name": "Болхов", "lat": 53.45, "lon": 36.0, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "болховском р-не", "name": "Болхов", "lat": 53.45, "lon": 36.0, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "верховский район", "name": "Верховье", "lat": 52.817, "lon": 37.233, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "верховском районе", "name": "Верховье", "lat": 52.817, "lon": 37.233, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "верховский р-н", "name": "Верховье", "lat": 52.817, "lon": 37.233, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "верховском р-не", "name": "Верховье", "lat": 52.817, "lon": 37.233, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "глазуновский район", "name": "Глазуновка", "lat": 52.5, "lon": 36.317, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "глазуновском районе", "name": "Глазуновка", "lat": 52.5, "lon": 36.317, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "глазуновский р-н", "name": "Глазуновка", "lat": 52.5, "lon": 36.317, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "глазуновском р-не", "name": "Глазуновка", "lat": 52.5, "lon": 36.317, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "дмитровский район", "name": "Дмитровск", "lat": 52.5, "lon": 35.15, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "дмитровском районе", "name": "Дмитровск", "lat": 52.5, "lon": 35.15, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "дмитровский р-н", "name": "Дмитровск", "lat": 52.5, "lon": 35.15, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "дмитровском р-не", "name": "Дмитровск", "lat": 52.5, "lon": 35.15, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "должанский район", "name": "Долгое", "lat": 52.05, "lon": 37.5, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "должанском районе", "name": "Долгое", "lat": 52.05, "lon": 37.5, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "должанский р-н", "name": "Долгое", "lat": 52.05, "lon": 37.5, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "должанском р-не", "name": "Долгое", "lat": 52.05, "lon": 37.5, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "залегощенский район", "name": "Залегощь", "lat": 52.9, "lon": 36.883, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "залегощенском районе", "name": "Залегощь", "lat": 52.9, "lon": 36.883, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "залегощенский р-н", "name": "Залегощь", "lat": 52.9, "lon": 36.883, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "залегощенском р-не", "name": "Залегощь", "lat": 52.9, "lon": 36.883, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "знаменский район", "name": "Знаменское", "lat": 53.283, "lon": 35.683, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "знаменском районе", "name": "Знаменское", "lat": 53.283, "lon": 35.683, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "знаменский р-н", "name": "Знаменское", "lat": 53.283, "lon": 35.683, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "знаменском р-не", "name": "Знаменское", "lat": 53.283, "lon": 35.683, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "колпнянский район", "name": "Колпны", "lat": 52.217, "lon": 37.033, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "колпнянском районе", "name": "Колпны", "lat": 52.217, "lon": 37.033, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "колпнянский р-н", "name": "Колпны", "lat": 52.217, "lon": 37.033, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "колпнянском р-не", "name": "Колпны", "lat": 52.217, "lon": 37.033, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "корсаковский район", "name": "Корсаково", "lat": 53.267, "lon": 37.35, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "корсаковском районе", "name": "Корсаково", "lat": 53.267, "lon": 37.35, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "корсаковский р-н", "name": "Корсаково", "lat": 53.267, "lon": 37.35, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "корсаковском р-не", "name": "Корсаково", "lat": 53.267, "lon": 37.35, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "краснозоренский район", "name": "Красная Заря", "lat": 52.783, "lon": 37.683, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "краснозоренском районе", "name": "Красная Заря", "lat": 52.783, "lon": 37.683, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "краснозоренский р-н", "name": "Красная Заря", "lat": 52.783, "lon": 37.683, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "краснозоренском р-не", "name": "Красная Заря", "lat": 52.783, "lon": 37.683, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "кромской район", "name": "Кромы", "lat": 52.683, "lon": 35.767, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "кромской районе", "name": "Кромы", "lat": 52.683, "lon": 35.767, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "кромской р-н", "name": "Кромы", "lat": 52.683, "lon": 35.767, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "кромской р-не", "name": "Кромы", "lat": 52.683, "lon": 35.767, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "ливенский район", "name": "Ливны", "lat": 52.43, "lon": 37.6, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "ливенском районе", "name": "Ливны", "lat": 52.43, "lon": 37.6, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "ливенский р-н", "name": "Ливны", "lat": 52.43, "lon": 37.6, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "ливенском р-не", "name": "Ливны", "lat": 52.43, "lon": 37.6, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "малоархангельский район", "name": "Малоархангельск", "lat": 52.4, "lon": 36.5, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "малоархангельском районе", "name": "Малоархангельск", "lat": 52.4, "lon": 36.5, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "малоархангельский р-н", "name": "Малоархангельск", "lat": 52.4, "lon": 36.5, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "малоархангельском р-не", "name": "Малоархангельск", "lat": 52.4, "lon": 36.5, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "мценский район", "name": "Мценск", "lat": 53.28, "lon": 36.58, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "мценском районе", "name": "Мценск", "lat": 53.28, "lon": 36.58, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "мценский р-н", "name": "Мценск", "lat": 53.28, "lon": 36.58, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "мценском р-не", "name": "Мценск", "lat": 53.28, "lon": 36.58, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "новодеревеньковский район", "name": "Хомутово", "lat": 52.85, "lon": 37.433, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "новодеревеньковском районе", "name": "Хомутово", "lat": 52.85, "lon": 37.433, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "новодеревеньковский р-н", "name": "Хомутово", "lat": 52.85, "lon": 37.433, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "новодеревеньковском р-не", "name": "Хомутово", "lat": 52.85, "lon": 37.433, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "новосильский район", "name": "Новосиль", "lat": 52.967, "lon": 37.05, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "новосильском районе", "name": "Новосиль", "lat": 52.967, "lon": 37.05, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "новосильский р-н", "name": "Новосиль", "lat": 52.967, "lon": 37.05, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "новосильском р-не", "name": "Новосиль", "lat": 52.967, "lon": 37.05, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "орловский район", "name": "Орёл", "lat": 52.97, "lon": 36.07, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "орловском районе", "name": "Орёл", "lat": 52.97, "lon": 36.07, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "орловский р-н", "name": "Орёл", "lat": 52.97, "lon": 36.07, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "орловском р-не", "name": "Орёл", "lat": 52.97, "lon": 36.07, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "покровский район", "name": "Покровское", "lat": 52.617, "lon": 36.867, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "покровском районе", "name": "Покровское", "lat": 52.617, "lon": 36.867, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "покровский р-н", "name": "Покровское", "lat": 52.617, "lon": 36.867, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "покровском р-не", "name": "Покровское", "lat": 52.617, "lon": 36.867, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "свердловский район", "name": "Змиёвка", "lat": 52.667, "lon": 36.367, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "свердловском районе", "name": "Змиёвка", "lat": 52.667, "lon": 36.367, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "свердловский р-н", "name": "Змиёвка", "lat": 52.667, "lon": 36.367, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "свердловском р-не", "name": "Змиёвка", "lat": 52.667, "lon": 36.367, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "сосковский район", "name": "Сосково", "lat": 52.75, "lon": 35.383, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "сосковском районе", "name": "Сосково", "lat": 52.75, "lon": 35.383, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "сосковский р-н", "name": "Сосково", "lat": 52.75, "lon": 35.383, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "сосковском р-не", "name": "Сосково", "lat": 52.75, "lon": 35.383, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "троснянский район", "name": "Тросна", "lat": 52.45, "lon": 35.783, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "троснянском районе", "name": "Тросна", "lat": 52.45, "lon": 35.783, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "троснянский р-н", "name": "Тросна", "lat": 52.45, "lon": 35.783, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "троснянском р-не", "name": "Тросна", "lat": 52.45, "lon": 35.783, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "урицкий район", "name": "Нарышкино", "lat": 52.967, "lon": 35.733, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "урицком районе", "name": "Нарышкино", "lat": 52.967, "lon": 35.733, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "урицкий р-н", "name": "Нарышкино", "lat": 52.967, "lon": 35.733, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "урицком р-не", "name": "Нарышкино", "lat": 52.967, "lon": 35.733, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "хотынецкий район", "name": "Хотынец", "lat": 53.117, "lon": 35.4, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "хотынецком районе", "name": "Хотынец", "lat": 53.117, "lon": 35.4, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "хотынецкий р-н", "name": "Хотынец", "lat": 53.117, "lon": 35.4, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "хотынецком р-не", "name": "Хотынец", "lat": 53.117, "lon": 35.4, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "шаблыкинский район", "name": "Шаблыкино", "lat": 52.85, "lon": 35.183, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "шаблыкинском районе", "name": "Шаблыкино", "lat": 52.85, "lon": 35.183, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "шаблыкинский р-н", "name": "Шаблыкино", "lat": 52.85, "lon": 35.183, "type": "region", "is_region": True, "subject": "Орловская область"},
    {"pattern": "шаблыкинском р-не", "name": "Шаблыкино", "lat": 52.85, "lon": 35.183, "type": "region", "is_region": True, "subject": "Орловская область"},

    # Орловская область — населённые пункты не из CITY_DB
    {"pattern": "верховье", "name": "Верховье", "lat": 52.817, "lon": 37.233, "type": "city", "subject": "Орловская область"},
    {"pattern": "глазуновка", "name": "Глазуновка", "lat": 52.5, "lon": 36.317, "type": "city", "subject": "Орловская область"},
    {"pattern": "глазуновке", "name": "Глазуновка", "lat": 52.5, "lon": 36.317, "type": "city", "subject": "Орловская область"},
    {"pattern": "долгое", "name": "Долгое", "lat": 52.05, "lon": 37.5, "type": "city", "subject": "Орловская область"},
    {"pattern": "знаменское", "name": "Знаменское", "lat": 53.283, "lon": 35.683, "type": "city", "subject": "Орловская область"},
    {"pattern": "колпны", "name": "Колпны", "lat": 52.217, "lon": 37.033, "type": "city", "subject": "Орловская область"},
    {"pattern": "корсаково", "name": "Корсаково", "lat": 53.267, "lon": 37.35, "type": "city", "subject": "Орловская область"},
    {"pattern": "красная заря", "name": "Красная Заря", "lat": 52.783, "lon": 37.683, "type": "city", "subject": "Орловская область"},
    {"pattern": "красная заре", "name": "Красная Заря", "lat": 52.783, "lon": 37.683, "type": "city", "subject": "Орловская область"},
    {"pattern": "хомутово", "name": "Хомутово", "lat": 52.85, "lon": 37.433, "type": "city", "subject": "Орловская область"},
    {"pattern": "покровское", "name": "Покровское", "lat": 52.617, "lon": 36.867, "type": "city", "subject": "Орловская область"},
    {"pattern": "змиёвка", "name": "Змиёвка", "lat": 52.667, "lon": 36.367, "type": "city", "subject": "Орловская область"},
    {"pattern": "змиёвке", "name": "Змиёвка", "lat": 52.667, "lon": 36.367, "type": "city", "subject": "Орловская область"},
    {"pattern": "сосково", "name": "Сосково", "lat": 52.75, "lon": 35.383, "type": "city", "subject": "Орловская область"},
    {"pattern": "тросна", "name": "Тросна", "lat": 52.45, "lon": 35.783, "type": "city", "subject": "Орловская область"},
    {"pattern": "тросне", "name": "Тросна", "lat": 52.45, "lon": 35.783, "type": "city", "subject": "Орловская область"},
    {"pattern": "нарышкино", "name": "Нарышкино", "lat": 52.967, "lon": 35.733, "type": "city", "subject": "Орловская область"},
    {"pattern": "хотынец", "name": "Хотынец", "lat": 53.117, "lon": 35.4, "type": "city", "subject": "Орловская область"},
    {"pattern": "хотынеце", "name": "Хотынец", "lat": 53.117, "lon": 35.4, "type": "city", "subject": "Орловская область"},
    {"pattern": "шаблыкино", "name": "Шаблыкино", "lat": 52.85, "lon": 35.183, "type": "city", "subject": "Орловская область"},

    # Курская область — районы
    {"pattern": "беловский район", "name": "Белая", "lat": 51.05, "lon": 35.717, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "беловском районе", "name": "Белая", "lat": 51.05, "lon": 35.717, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "беловский р-н", "name": "Белая", "lat": 51.05, "lon": 35.717, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "беловском р-не", "name": "Белая", "lat": 51.05, "lon": 35.717, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "большесолдатский район", "name": "Большое Солдатское", "lat": 51.333, "lon": 35.5, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "большесолдатском районе", "name": "Большое Солдатское", "lat": 51.333, "lon": 35.5, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "большесолдатский р-н", "name": "Большое Солдатское", "lat": 51.333, "lon": 35.5, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "большесолдатском р-не", "name": "Большое Солдатское", "lat": 51.333, "lon": 35.5, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "глушковский район", "name": "Глушково", "lat": 51.333, "lon": 34.617, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "глушковском районе", "name": "Глушково", "lat": 51.333, "lon": 34.617, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "глушковский р-н", "name": "Глушково", "lat": 51.333, "lon": 34.617, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "глушковском р-не", "name": "Глушково", "lat": 51.333, "lon": 34.617, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "горшеченский район", "name": "Горшечное", "lat": 51.517, "lon": 38.033, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "горшеченском районе", "name": "Горшечное", "lat": 51.517, "lon": 38.033, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "горшеченский р-н", "name": "Горшечное", "lat": 51.517, "lon": 38.033, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "горшеченском р-не", "name": "Горшечное", "lat": 51.517, "lon": 38.033, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "дмитриевский район", "name": "Дмитриев", "lat": 52.12, "lon": 35.08, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "дмитриевском районе", "name": "Дмитриев", "lat": 52.12, "lon": 35.08, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "дмитриевский р-н", "name": "Дмитриев", "lat": 52.12, "lon": 35.08, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "дмитриевском р-не", "name": "Дмитриев", "lat": 52.12, "lon": 35.08, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "железногорский район", "name": "Железногорск", "lat": 52.33, "lon": 35.35, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "железногорском районе", "name": "Железногорск", "lat": 52.33, "lon": 35.35, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "железногорский р-н", "name": "Железногорск", "lat": 52.33, "lon": 35.35, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "железногорском р-не", "name": "Железногорск", "lat": 52.33, "lon": 35.35, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "золотухинский район", "name": "Золотухино", "lat": 52.0, "lon": 36.383, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "золотухинском районе", "name": "Золотухино", "lat": 52.0, "lon": 36.383, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "золотухинский р-н", "name": "Золотухино", "lat": 52.0, "lon": 36.383, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "золотухинском р-не", "name": "Золотухино", "lat": 52.0, "lon": 36.383, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "касторенский район", "name": "Касторное", "lat": 51.817, "lon": 38.117, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "касторенском районе", "name": "Касторное", "lat": 51.817, "lon": 38.117, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "касторенский р-н", "name": "Касторное", "lat": 51.817, "lon": 38.117, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "касторенском р-не", "name": "Касторное", "lat": 51.817, "lon": 38.117, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "конышёвский район", "name": "Конышёвка", "lat": 51.833, "lon": 35.283, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "конышёвском районе", "name": "Конышёвка", "lat": 51.833, "lon": 35.283, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "конышёвский р-н", "name": "Конышёвка", "lat": 51.833, "lon": 35.283, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "конышёвском р-не", "name": "Конышёвка", "lat": 51.833, "lon": 35.283, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "кореневский район", "name": "Коренево", "lat": 51.4, "lon": 34.9, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "кореневском районе", "name": "Коренево", "lat": 51.4, "lon": 34.9, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "кореневский р-н", "name": "Коренево", "lat": 51.4, "lon": 34.9, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "кореневском р-не", "name": "Коренево", "lat": 51.4, "lon": 34.9, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "курский район", "name": "Курск", "lat": 51.73, "lon": 36.18, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "курском районе", "name": "Курск", "lat": 51.73, "lon": 36.18, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "курский р-н", "name": "Курск", "lat": 51.73, "lon": 36.18, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "курском р-не", "name": "Курск", "lat": 51.73, "lon": 36.18, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "курчатовский район", "name": "Курчатов", "lat": 51.67, "lon": 35.65, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "курчатовском районе", "name": "Курчатов", "lat": 51.67, "lon": 35.65, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "курчатовский р-н", "name": "Курчатов", "lat": 51.67, "lon": 35.65, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "курчатовском р-не", "name": "Курчатов", "lat": 51.67, "lon": 35.65, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "льговский район", "name": "Льгов", "lat": 51.68, "lon": 35.27, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "льговском районе", "name": "Льгов", "lat": 51.68, "lon": 35.27, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "льговский р-н", "name": "Льгов", "lat": 51.68, "lon": 35.27, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "льговском р-не", "name": "Льгов", "lat": 51.68, "lon": 35.27, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "мантуровский район", "name": "Мантурово", "lat": 51.483, "lon": 37.117, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "мантуровском районе", "name": "Мантурово", "lat": 51.483, "lon": 37.117, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "мантуровский р-н", "name": "Мантурово", "lat": 51.483, "lon": 37.117, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "мантуровском р-не", "name": "Мантурово", "lat": 51.483, "lon": 37.117, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "медвенский район", "name": "Медвенка", "lat": 51.417, "lon": 36.1, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "медвенском районе", "name": "Медвенка", "lat": 51.417, "lon": 36.1, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "медвенский р-н", "name": "Медвенка", "lat": 51.417, "lon": 36.1, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "медвенском р-не", "name": "Медвенка", "lat": 51.417, "lon": 36.1, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "обоянский район", "name": "Обоянь", "lat": 51.22, "lon": 36.27, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "обоянском районе", "name": "Обоянь", "lat": 51.22, "lon": 36.27, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "обоянский р-н", "name": "Обоянь", "lat": 51.22, "lon": 36.27, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "обоянском р-не", "name": "Обоянь", "lat": 51.22, "lon": 36.27, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "октябрьский район", "name": "Прямицыно", "lat": 51.65, "lon": 35.933, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "октябрьском районе", "name": "Прямицыно", "lat": 51.65, "lon": 35.933, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "октябрьский р-н", "name": "Прямицыно", "lat": 51.65, "lon": 35.933, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "октябрьском р-не", "name": "Прямицыно", "lat": 51.65, "lon": 35.933, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "поныровский район", "name": "Поныри", "lat": 52.317, "lon": 36.3, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "поныровском районе", "name": "Поныри", "lat": 52.317, "lon": 36.3, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "поныровский р-н", "name": "Поныри", "lat": 52.317, "lon": 36.3, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "поныровском р-не", "name": "Поныри", "lat": 52.317, "lon": 36.3, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "пристенский район", "name": "Пристень", "lat": 51.233, "lon": 36.7, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "пристенском районе", "name": "Пристень", "lat": 51.233, "lon": 36.7, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "пристенский р-н", "name": "Пристень", "lat": 51.233, "lon": 36.7, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "пристенском р-не", "name": "Пристень", "lat": 51.233, "lon": 36.7, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "рыльский район", "name": "Рыльск", "lat": 51.57, "lon": 34.68, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "рыльском районе", "name": "Рыльск", "lat": 51.57, "lon": 34.68, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "рыльский р-н", "name": "Рыльск", "lat": 51.57, "lon": 34.68, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "рыльском р-не", "name": "Рыльск", "lat": 51.57, "lon": 34.68, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "советский район", "name": "Кшенский", "lat": 51.85, "lon": 37.717, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "советском районе", "name": "Кшенский", "lat": 51.85, "lon": 37.717, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "советский р-н", "name": "Кшенский", "lat": 51.85, "lon": 37.717, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "советском р-не", "name": "Кшенский", "lat": 51.85, "lon": 37.717, "type": "region", "is_region": True, "subject": "Курская область"},
    # Внутригородские районы Брянска: «Фокинский район»/«Бежицкий район» не являются
    # самостоятельными муниципальными районами нигде (это районы г.Брянска).
    # Без алиасов rayon-fallback давал «фокинский район»→Фокино/Приморский край
    # (CITY_DB['фокино'] — единственный город с таким префиксом).
    {"pattern": "фокинский район", "name": "Фокино", "lat": 53.45472, "lon": 34.41345, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "фокинском районе", "name": "Фокино", "lat": 53.45472, "lon": 34.41345, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "фокинский р-н", "name": "Фокино", "lat": 53.45472, "lon": 34.41345, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "фокинском р-не", "name": "Фокино", "lat": 53.45472, "lon": 34.41345, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "бежицкий район", "name": "Брянск", "lat": 53.2433, "lon": 34.3634, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "бежицком районе", "name": "Брянск", "lat": 53.2433, "lon": 34.3634, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "бежицкий р-н", "name": "Брянск", "lat": 53.2433, "lon": 34.3634, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "бежицком р-не", "name": "Брянск", "lat": 53.2433, "lon": 34.3634, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "солнцевский район", "name": "Солнцево", "lat": 51.417, "lon": 36.75, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "солнцевском районе", "name": "Солнцево", "lat": 51.417, "lon": 36.75, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "солнцевский р-н", "name": "Солнцево", "lat": 51.417, "lon": 36.75, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "солнцевском р-не", "name": "Солнцево", "lat": 51.417, "lon": 36.75, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "суджанский район", "name": "Суджа", "lat": 51.2, "lon": 35.27, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "суджанском районе", "name": "Суджа", "lat": 51.2, "lon": 35.27, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "суджанский р-н", "name": "Суджа", "lat": 51.2, "lon": 35.27, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "суджанском р-не", "name": "Суджа", "lat": 51.2, "lon": 35.27, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "тимский район", "name": "Тим", "lat": 51.617, "lon": 37.117, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "тимском районе", "name": "Тим", "lat": 51.617, "lon": 37.117, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "тимский р-н", "name": "Тим", "lat": 51.617, "lon": 37.117, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "тимском р-не", "name": "Тим", "lat": 51.617, "lon": 37.117, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "фатежский район", "name": "Фатеж", "lat": 52.08, "lon": 35.85, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "фатежском районе", "name": "Фатеж", "lat": 52.08, "lon": 35.85, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "фатежский р-н", "name": "Фатеж", "lat": 52.08, "lon": 35.85, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "фатежском р-не", "name": "Фатеж", "lat": 52.08, "lon": 35.85, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "хомутовский район", "name": "Хомутовка", "lat": 51.917, "lon": 34.55, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "хомутовском районе", "name": "Хомутовка", "lat": 51.917, "lon": 34.55, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "хомутовский р-н", "name": "Хомутовка", "lat": 51.917, "lon": 34.55, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "хомутовском р-не", "name": "Хомутовка", "lat": 51.917, "lon": 34.55, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "черемисиновский район", "name": "Черемисиново", "lat": 51.883, "lon": 37.267, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "черемисиновском районе", "name": "Черемисиново", "lat": 51.883, "lon": 37.267, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "черемисиновский р-н", "name": "Черемисиново", "lat": 51.883, "lon": 37.267, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "черемисиновском р-не", "name": "Черемисиново", "lat": 51.883, "lon": 37.267, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "щигровский район", "name": "Щигры", "lat": 51.88, "lon": 36.9, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "щигровском районе", "name": "Щигры", "lat": 51.88, "lon": 36.9, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "щигровский р-н", "name": "Щигры", "lat": 51.88, "lon": 36.9, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "щигровском р-не", "name": "Щигры", "lat": 51.88, "lon": 36.9, "type": "region", "is_region": True, "subject": "Курская область"},

    # Курская область — населённые пункты не из CITY_DB
    {"pattern": "большое солдатское", "name": "Большое Солдатское", "lat": 51.333, "lon": 35.5, "type": "city", "subject": "Курская область"},
    {"pattern": "глушково", "name": "Глушково", "lat": 51.333, "lon": 34.617, "type": "city", "subject": "Курская область"},
    {"pattern": "горшечное", "name": "Горшечное", "lat": 51.517, "lon": 38.033, "type": "city", "subject": "Курская область"},
    {"pattern": "золотухино", "name": "Золотухино", "lat": 52.0, "lon": 36.383, "type": "city", "subject": "Курская область"},
    {"pattern": "касторное", "name": "Касторное", "lat": 51.817, "lon": 38.117, "type": "city", "subject": "Курская область"},
    {"pattern": "конышёвка", "name": "Конышёвка", "lat": 51.833, "lon": 35.283, "type": "city", "subject": "Курская область"},
    {"pattern": "конышёвке", "name": "Конышёвка", "lat": 51.833, "lon": 35.283, "type": "city", "subject": "Курская область"},
    {"pattern": "коренево", "name": "Коренево", "lat": 51.4, "lon": 34.9, "type": "city", "subject": "Курская область"},
    {"pattern": "мантурово", "name": "Мантурово", "lat": 51.483, "lon": 37.117, "type": "city", "subject": "Курская область"},
    {"pattern": "медвенка", "name": "Медвенка", "lat": 51.417, "lon": 36.1, "type": "city", "subject": "Курская область"},
    {"pattern": "медвенке", "name": "Медвенка", "lat": 51.417, "lon": 36.1, "type": "city", "subject": "Курская область"},
    {"pattern": "прямицыно", "name": "Прямицыно", "lat": 51.65, "lon": 35.933, "type": "city", "subject": "Курская область"},
    {"pattern": "поныри", "name": "Поныри", "lat": 52.317, "lon": 36.3, "type": "city", "subject": "Курская область"},
    {"pattern": "пристень", "name": "Пристень", "lat": 51.233, "lon": 36.7, "type": "city", "subject": "Курская область"},
    {"pattern": "пристене", "name": "Пристень", "lat": 51.233, "lon": 36.7, "type": "city", "subject": "Курская область"},
    {"pattern": "кшенский", "name": "Кшенский", "lat": 51.85, "lon": 37.717, "type": "city", "subject": "Курская область"},
    {"pattern": "кшенские", "name": "Кшенский", "lat": 51.85, "lon": 37.717, "type": "city", "subject": "Курская область"},
    {"pattern": "солнцево", "name": "Солнцево", "lat": 51.417, "lon": 36.75, "type": "city", "subject": "Курская область"},
    {"pattern": "тим", "name": "Тим", "lat": 51.617, "lon": 37.117, "type": "city", "subject": "Курская область"},
    {"pattern": "тиме", "name": "Тим", "lat": 51.617, "lon": 37.117, "type": "city", "subject": "Курская область"},
    {"pattern": "хомутовка", "name": "Хомутовка", "lat": 51.917, "lon": 34.55, "type": "city", "subject": "Курская область"},
    {"pattern": "хомутовке", "name": "Хомутовка", "lat": 51.917, "lon": 34.55, "type": "city", "subject": "Курская область"},
    {"pattern": "черемисиново", "name": "Черемисиново", "lat": 51.883, "lon": 37.267, "type": "city", "subject": "Курская область"},

    # Белгородская область — районы
    {"pattern": "алексеевский район", "name": "Алексеевка", "lat": 50.63, "lon": 38.68, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "алексеевском районе", "name": "Алексеевка", "lat": 50.63, "lon": 38.68, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "алексеевский р-н", "name": "Алексеевка", "lat": 50.63, "lon": 38.68, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "алексеевском р-не", "name": "Алексеевка", "lat": 50.63, "lon": 38.68, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "белгородский район", "name": "Белгород", "lat": 50.6, "lon": 36.58, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "белгородском районе", "name": "Белгород", "lat": 50.6, "lon": 36.58, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "белгородский р-н", "name": "Белгород", "lat": 50.6, "lon": 36.58, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "белгородском р-не", "name": "Белгород", "lat": 50.6, "lon": 36.58, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "борисовский район", "name": "Борисовка", "lat": 50.6, "lon": 36.017, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "борисовском районе", "name": "Борисовка", "lat": 50.6, "lon": 36.017, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "борисовский р-н", "name": "Борисовка", "lat": 50.6, "lon": 36.017, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "борисовском р-не", "name": "Борисовка", "lat": 50.6, "lon": 36.017, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "валуйский район", "name": "Валуйки", "lat": 50.22, "lon": 38.12, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "валуйском районе", "name": "Валуйки", "lat": 50.22, "lon": 38.12, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "валуйский р-н", "name": "Валуйки", "lat": 50.22, "lon": 38.12, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "валуйском р-не", "name": "Валуйки", "lat": 50.22, "lon": 38.12, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "вейделевский район", "name": "Вейделевка", "lat": 50.15, "lon": 38.45, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "вейделевском районе", "name": "Вейделевка", "lat": 50.15, "lon": 38.45, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "вейделевский р-н", "name": "Вейделевка", "lat": 50.15, "lon": 38.45, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "вейделевском р-не", "name": "Вейделевка", "lat": 50.15, "lon": 38.45, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "волоконовский район", "name": "Волоконовка", "lat": 50.483, "lon": 37.867, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "волоконовском районе", "name": "Волоконовка", "lat": 50.483, "lon": 37.867, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "волоконовский р-н", "name": "Волоконовка", "lat": 50.483, "lon": 37.867, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "волоконовском р-не", "name": "Волоконовка", "lat": 50.483, "lon": 37.867, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "грайворонский район", "name": "Грайворон", "lat": 50.48, "lon": 35.67, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "грайворонском районе", "name": "Грайворон", "lat": 50.48, "lon": 35.67, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "грайворонский р-н", "name": "Грайворон", "lat": 50.48, "lon": 35.67, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "грайворонском р-не", "name": "Грайворон", "lat": 50.48, "lon": 35.67, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "губкинский район", "name": "Губкин", "lat": 51.28, "lon": 37.55, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "губкинском районе", "name": "Губкин", "lat": 51.28, "lon": 37.55, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "губкинский р-н", "name": "Губкин", "lat": 51.28, "lon": 37.55, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "губкинском р-не", "name": "Губкин", "lat": 51.28, "lon": 37.55, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "ивнянский район", "name": "Ивня", "lat": 51.067, "lon": 36.133, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "ивнянском районе", "name": "Ивня", "lat": 51.067, "lon": 36.133, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "ивнянский р-н", "name": "Ивня", "lat": 51.067, "lon": 36.133, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "ивнянском р-не", "name": "Ивня", "lat": 51.067, "lon": 36.133, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "корочанский район", "name": "Короча", "lat": 50.82, "lon": 37.18, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "корочанском районе", "name": "Короча", "lat": 50.82, "lon": 37.18, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "корочанский р-н", "name": "Короча", "lat": 50.82, "lon": 37.18, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "корочанском р-не", "name": "Короча", "lat": 50.82, "lon": 37.18, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "красненский район", "name": "Красное", "lat": 50.933, "lon": 38.683, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "красненском районе", "name": "Красное", "lat": 50.933, "lon": 38.683, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "красненский р-н", "name": "Красное", "lat": 50.933, "lon": 38.683, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "красненском р-не", "name": "Красное", "lat": 50.933, "lon": 38.683, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "красногвардейский район", "name": "Бирюч", "lat": 50.65, "lon": 38.4, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "красногвардейском районе", "name": "Бирюч", "lat": 50.65, "lon": 38.4, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "красногвардейский р-н", "name": "Бирюч", "lat": 50.65, "lon": 38.4, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "красногвардейском р-не", "name": "Бирюч", "lat": 50.65, "lon": 38.4, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "краснояружский район", "name": "Красная Яруга", "lat": 50.8, "lon": 35.65, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "краснояружском районе", "name": "Красная Яруга", "lat": 50.8, "lon": 35.65, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "краснояружский р-н", "name": "Красная Яруга", "lat": 50.8, "lon": 35.65, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "краснояружском р-не", "name": "Красная Яруга", "lat": 50.8, "lon": 35.65, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "новооскольский район", "name": "Новый Оскол", "lat": 50.77, "lon": 37.87, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "новооскольском районе", "name": "Новый Оскол", "lat": 50.77, "lon": 37.87, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "новооскольский р-н", "name": "Новый Оскол", "lat": 50.77, "lon": 37.87, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "новооскольском р-не", "name": "Новый Оскол", "lat": 50.77, "lon": 37.87, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "прохоровский район", "name": "Прохоровка", "lat": 51.03, "lon": 36.73, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "прохоровском районе", "name": "Прохоровка", "lat": 51.03, "lon": 36.73, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "прохоровский р-н", "name": "Прохоровка", "lat": 51.03, "lon": 36.73, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "прохоровском р-не", "name": "Прохоровка", "lat": 51.03, "lon": 36.73, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "ракитянский район", "name": "Ракитное", "lat": 50.833, "lon": 35.833, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "ракитянском районе", "name": "Ракитное", "lat": 50.833, "lon": 35.833, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "ракитянский р-н", "name": "Ракитное", "lat": 50.833, "lon": 35.833, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "ракитянском р-не", "name": "Ракитное", "lat": 50.833, "lon": 35.833, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "ровеньский район", "name": "Ровеньки", "lat": 49.9, "lon": 38.9, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "ровеньском районе", "name": "Ровеньки", "lat": 49.9, "lon": 38.9, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "ровеньский р-н", "name": "Ровеньки", "lat": 49.9, "lon": 38.9, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "ровеньском р-не", "name": "Ровеньки", "lat": 49.9, "lon": 38.9, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "старооскольский район", "name": "Старый Оскол", "lat": 51.3, "lon": 37.85, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "старооскольском районе", "name": "Старый Оскол", "lat": 51.3, "lon": 37.85, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "старооскольский р-н", "name": "Старый Оскол", "lat": 51.3, "lon": 37.85, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "старооскольском р-не", "name": "Старый Оскол", "lat": 51.3, "lon": 37.85, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "чернянский район", "name": "Чернянка", "lat": 50.933, "lon": 37.8, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "чернянском районе", "name": "Чернянка", "lat": 50.933, "lon": 37.8, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "чернянский р-н", "name": "Чернянка", "lat": 50.933, "lon": 37.8, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "чернянском р-не", "name": "Чернянка", "lat": 50.933, "lon": 37.8, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "шебекинский район", "name": "Шебекино", "lat": 50.4, "lon": 36.9, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "шебекинском районе", "name": "Шебекино", "lat": 50.4, "lon": 36.9, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "шебекинский р-н", "name": "Шебекино", "lat": 50.4, "lon": 36.9, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "шебекинском р-не", "name": "Шебекино", "lat": 50.4, "lon": 36.9, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "яковлевский район", "name": "Строитель", "lat": 50.78, "lon": 36.47, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "яковлевском районе", "name": "Строитель", "lat": 50.78, "lon": 36.47, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "яковлевский р-н", "name": "Строитель", "lat": 50.78, "lon": 36.47, "type": "region", "is_region": True, "subject": "Белгородская область"},
    {"pattern": "яковлевском р-не", "name": "Строитель", "lat": 50.78, "lon": 36.47, "type": "region", "is_region": True, "subject": "Белгородская область"},

    # Белгородская область — населённые пункты не из CITY_DB
    {"pattern": "вейделевка", "name": "Вейделевка", "lat": 50.15, "lon": 38.45, "type": "city", "subject": "Белгородская область"},
    {"pattern": "вейделевке", "name": "Вейделевка", "lat": 50.15, "lon": 38.45, "type": "city", "subject": "Белгородская область"},
    {"pattern": "волоконовка", "name": "Волоконовка", "lat": 50.483, "lon": 37.867, "type": "city", "subject": "Белгородская область"},
    {"pattern": "волоконовке", "name": "Волоконовка", "lat": 50.483, "lon": 37.867, "type": "city", "subject": "Белгородская область"},
    {"pattern": "ивня", "name": "Ивня", "lat": 51.067, "lon": 36.133, "type": "city", "subject": "Белгородская область"},
    {"pattern": "ивне", "name": "Ивня", "lat": 51.067, "lon": 36.133, "type": "city", "subject": "Белгородская область"},
    {"pattern": "красное", "name": "Красное", "lat": 50.933, "lon": 38.683, "type": "city", "subject": "Белгородская область"},
    {"pattern": "бирюч", "name": "Бирюч", "lat": 50.65, "lon": 38.4, "type": "city", "subject": "Белгородская область"},
    {"pattern": "бирюче", "name": "Бирюч", "lat": 50.65, "lon": 38.4, "type": "city", "subject": "Белгородская область"},
    {"pattern": "красная яруга", "name": "Красная Яруга", "lat": 50.8, "lon": 35.65, "type": "city", "subject": "Белгородская область"},
    {"pattern": "красная яруге", "name": "Красная Яруга", "lat": 50.8, "lon": 35.65, "type": "city", "subject": "Белгородская область"},
    {"pattern": "ракитное", "name": "Ракитное", "lat": 50.833, "lon": 35.833, "type": "city", "subject": "Белгородская область"},
    {"pattern": "ровеньки", "name": "Ровеньки", "lat": 49.9, "lon": 38.9, "type": "city", "subject": "Белгородская область"},
    {"pattern": "чернянка", "name": "Чернянка", "lat": 50.933, "lon": 37.8, "type": "city", "subject": "Белгородская область"},
    {"pattern": "чернянке", "name": "Чернянка", "lat": 50.933, "lon": 37.8, "type": "city", "subject": "Белгородская область"},

    # Брянская область — районы
    {"pattern": "брасовский район", "name": "Локоть", "lat": 52.567, "lon": 34.567, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "брасовском районе", "name": "Локоть", "lat": 52.567, "lon": 34.567, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "брасовский р-н", "name": "Локоть", "lat": 52.567, "lon": 34.567, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "брасовском р-не", "name": "Локоть", "lat": 52.567, "lon": 34.567, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "брянский район", "name": "Брянск", "lat": 53.25, "lon": 34.37, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "брянском районе", "name": "Брянск", "lat": 53.25, "lon": 34.37, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "брянский р-н", "name": "Брянск", "lat": 53.25, "lon": 34.37, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "брянском р-не", "name": "Брянск", "lat": 53.25, "lon": 34.37, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "выгоничский район", "name": "Выгоничи", "lat": 53.1, "lon": 34.067, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "выгоничском районе", "name": "Выгоничи", "lat": 53.1, "lon": 34.067, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "выгоничский р-н", "name": "Выгоничи", "lat": 53.1, "lon": 34.067, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "выгоничском р-не", "name": "Выгоничи", "lat": 53.1, "lon": 34.067, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "гордеевский район", "name": "Гордеевка", "lat": 52.95, "lon": 31.983, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "гордеевском районе", "name": "Гордеевка", "lat": 52.95, "lon": 31.983, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "гордеевский р-н", "name": "Гордеевка", "lat": 52.95, "lon": 31.983, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "гордеевском р-не", "name": "Гордеевка", "lat": 52.95, "lon": 31.983, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "дубровский район", "name": "Дубровка", "lat": 53.683, "lon": 33.517, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "дубровском районе", "name": "Дубровка", "lat": 53.683, "lon": 33.517, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "дубровский р-н", "name": "Дубровка", "lat": 53.683, "lon": 33.517, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "дубровском р-не", "name": "Дубровка", "lat": 53.683, "lon": 33.517, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "дятьковский район", "name": "Дятьково", "lat": 53.6, "lon": 34.33, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "дятьковском районе", "name": "Дятьково", "lat": 53.6, "lon": 34.33, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "дятьковский р-н", "name": "Дятьково", "lat": 53.6, "lon": 34.33, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "дятьковском р-не", "name": "Дятьково", "lat": 53.6, "lon": 34.33, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "жирятинский район", "name": "Жирятино", "lat": 53.217, "lon": 33.733, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "жирятинском районе", "name": "Жирятино", "lat": 53.217, "lon": 33.733, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "жирятинский р-н", "name": "Жирятино", "lat": 53.217, "lon": 33.733, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "жирятинском р-не", "name": "Жирятино", "lat": 53.217, "lon": 33.733, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "жуковский район", "name": "Жуковка", "lat": 53.53, "lon": 33.72, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "жуковском районе", "name": "Жуковка", "lat": 53.53, "lon": 33.72, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "жуковский р-н", "name": "Жуковка", "lat": 53.53, "lon": 33.72, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "жуковском р-не", "name": "Жуковка", "lat": 53.53, "lon": 33.72, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "злынковский район", "name": "Злынка", "lat": 52.433, "lon": 31.733, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "злынковском районе", "name": "Злынка", "lat": 52.433, "lon": 31.733, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "злынковский р-н", "name": "Злынка", "lat": 52.433, "lon": 31.733, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "злынковском р-не", "name": "Злынка", "lat": 52.433, "lon": 31.733, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "карачевский район", "name": "Карачев", "lat": 53.12, "lon": 34.98, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "карачевском районе", "name": "Карачев", "lat": 53.12, "lon": 34.98, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "карачевский р-н", "name": "Карачев", "lat": 53.12, "lon": 34.98, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "карачевском р-не", "name": "Карачев", "lat": 53.12, "lon": 34.98, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "клетнянский район", "name": "Клетня", "lat": 53.383, "lon": 33.217, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "клетнянском районе", "name": "Клетня", "lat": 53.383, "lon": 33.217, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "клетнянский р-н", "name": "Клетня", "lat": 53.383, "lon": 33.217, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "клетнянском р-не", "name": "Клетня", "lat": 53.383, "lon": 33.217, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "климовский район", "name": "Климово", "lat": 52.367, "lon": 32.183, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "климовском районе", "name": "Климово", "lat": 52.367, "lon": 32.183, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "климовский р-н", "name": "Климово", "lat": 52.367, "lon": 32.183, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "климовском р-не", "name": "Климово", "lat": 52.367, "lon": 32.183, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "клинцовский район", "name": "Клинцы", "lat": 52.75, "lon": 32.23, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "клинцовском районе", "name": "Клинцы", "lat": 52.75, "lon": 32.23, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "клинцовский р-н", "name": "Клинцы", "lat": 52.75, "lon": 32.23, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "клинцовском р-не", "name": "Клинцы", "lat": 52.75, "lon": 32.23, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "комаричский район", "name": "Комаричи", "lat": 52.417, "lon": 34.8, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "комаричском районе", "name": "Комаричи", "lat": 52.417, "lon": 34.8, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "комаричский р-н", "name": "Комаричи", "lat": 52.417, "lon": 34.8, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "комаричском р-не", "name": "Комаричи", "lat": 52.417, "lon": 34.8, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "красногорский район", "name": "Красная Гора", "lat": 53.0, "lon": 31.6, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "красногорском районе", "name": "Красная Гора", "lat": 53.0, "lon": 31.6, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "красногорский р-н", "name": "Красная Гора", "lat": 53.0, "lon": 31.6, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "красногорском р-не", "name": "Красная Гора", "lat": 53.0, "lon": 31.6, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "мглинский район", "name": "Мглин", "lat": 53.067, "lon": 32.85, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "мглинском районе", "name": "Мглин", "lat": 53.067, "lon": 32.85, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "мглинский р-н", "name": "Мглин", "lat": 53.067, "lon": 32.85, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "мглинском р-не", "name": "Мглин", "lat": 53.067, "lon": 32.85, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "навлинский район", "name": "Навля", "lat": 52.833, "lon": 34.5, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "навлинском районе", "name": "Навля", "lat": 52.833, "lon": 34.5, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "навлинский р-н", "name": "Навля", "lat": 52.833, "lon": 34.5, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "навлинском р-не", "name": "Навля", "lat": 52.833, "lon": 34.5, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "новозыбковский район", "name": "Новозыбков", "lat": 52.53, "lon": 31.93, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "новозыбковском районе", "name": "Новозыбков", "lat": 52.53, "lon": 31.93, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "новозыбковский р-н", "name": "Новозыбков", "lat": 52.53, "lon": 31.93, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "новозыбковском р-не", "name": "Новозыбков", "lat": 52.53, "lon": 31.93, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "погарский район", "name": "Погар", "lat": 52.55, "lon": 33.25, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "погарском районе", "name": "Погар", "lat": 52.55, "lon": 33.25, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "погарский р-н", "name": "Погар", "lat": 52.55, "lon": 33.25, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "погарском р-не", "name": "Погар", "lat": 52.55, "lon": 33.25, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "почепский район", "name": "Почеп", "lat": 52.93, "lon": 33.45, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "почепском районе", "name": "Почеп", "lat": 52.93, "lon": 33.45, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "почепский р-н", "name": "Почеп", "lat": 52.93, "lon": 33.45, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "почепском р-не", "name": "Почеп", "lat": 52.93, "lon": 33.45, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "рогнединский район", "name": "Рогнедино", "lat": 53.8, "lon": 33.55, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "рогнединском районе", "name": "Рогнедино", "lat": 53.8, "lon": 33.55, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "рогнединский р-н", "name": "Рогнедино", "lat": 53.8, "lon": 33.55, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "рогнединском р-не", "name": "Рогнедино", "lat": 53.8, "lon": 33.55, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "севский район", "name": "Севск", "lat": 52.15, "lon": 34.5, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "севском районе", "name": "Севск", "lat": 52.15, "lon": 34.5, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "севский р-н", "name": "Севск", "lat": 52.15, "lon": 34.5, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "севском р-не", "name": "Севск", "lat": 52.15, "lon": 34.5, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "стародубский район", "name": "Стародуб", "lat": 52.58, "lon": 32.77, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "стародубском районе", "name": "Стародуб", "lat": 52.58, "lon": 32.77, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "стародубский р-н", "name": "Стародуб", "lat": 52.58, "lon": 32.77, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "стародубском р-не", "name": "Стародуб", "lat": 52.58, "lon": 32.77, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "суземский район", "name": "Суземка", "lat": 52.317, "lon": 34.083, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "суземском районе", "name": "Суземка", "lat": 52.317, "lon": 34.083, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "суземский р-н", "name": "Суземка", "lat": 52.317, "lon": 34.083, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "суземском р-не", "name": "Суземка", "lat": 52.317, "lon": 34.083, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "суражский район", "name": "Сураж", "lat": 53.017, "lon": 32.383, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "суражском районе", "name": "Сураж", "lat": 53.017, "lon": 32.383, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "суражский р-н", "name": "Сураж", "lat": 53.017, "lon": 32.383, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "суражском р-не", "name": "Сураж", "lat": 53.017, "lon": 32.383, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "трубчевский район", "name": "Трубчевск", "lat": 52.58, "lon": 33.77, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "трубчевском районе", "name": "Трубчевск", "lat": 52.58, "lon": 33.77, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "трубчевский р-н", "name": "Трубчевск", "lat": 52.58, "lon": 33.77, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "трубчевском р-не", "name": "Трубчевск", "lat": 52.58, "lon": 33.77, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "унечский район", "name": "Унеча", "lat": 52.85, "lon": 32.68, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "унечском районе", "name": "Унеча", "lat": 52.85, "lon": 32.68, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "унечский р-н", "name": "Унеча", "lat": 52.85, "lon": 32.68, "type": "region", "is_region": True, "subject": "Брянская область"},
    {"pattern": "унечском р-не", "name": "Унеча", "lat": 52.85, "lon": 32.68, "type": "region", "is_region": True, "subject": "Брянская область"},

    # Брянская область — населённые пункты не из CITY_DB
    {"pattern": "локоть", "name": "Локоть", "lat": 52.567, "lon": 34.567, "type": "city", "subject": "Брянская область"},
    {"pattern": "локоте", "name": "Локоть", "lat": 52.567, "lon": 34.567, "type": "city", "subject": "Брянская область"},
    {"pattern": "выгоничи", "name": "Выгоничи", "lat": 53.1, "lon": 34.067, "type": "city", "subject": "Брянская область"},
    {"pattern": "гордеевка", "name": "Гордеевка", "lat": 52.95, "lon": 31.983, "type": "city", "subject": "Брянская область"},
    {"pattern": "гордеевке", "name": "Гордеевка", "lat": 52.95, "lon": 31.983, "type": "city", "subject": "Брянская область"},
    {"pattern": "дубровка", "name": "Дубровка", "lat": 53.683, "lon": 33.517, "type": "city", "subject": "Брянская область"},
    {"pattern": "дубровке", "name": "Дубровка", "lat": 53.683, "lon": 33.517, "type": "city", "subject": "Брянская область"},
    {"pattern": "жирятино", "name": "Жирятино", "lat": 53.217, "lon": 33.733, "type": "city", "subject": "Брянская область"},
    {"pattern": "злынка", "name": "Злынка", "lat": 52.433, "lon": 31.733, "type": "city", "subject": "Брянская область"},
    {"pattern": "злынке", "name": "Злынка", "lat": 52.433, "lon": 31.733, "type": "city", "subject": "Брянская область"},
    {"pattern": "клетня", "name": "Клетня", "lat": 53.383, "lon": 33.217, "type": "city", "subject": "Брянская область"},
    {"pattern": "клетне", "name": "Клетня", "lat": 53.383, "lon": 33.217, "type": "city", "subject": "Брянская область"},
    {"pattern": "климово", "name": "Климово", "lat": 52.367, "lon": 32.183, "type": "city", "subject": "Брянская область"},
    {"pattern": "комаричи", "name": "Комаричи", "lat": 52.417, "lon": 34.8, "type": "city", "subject": "Брянская область"},
    {"pattern": "красная гора", "name": "Красная Гора", "lat": 53.0, "lon": 31.6, "type": "city", "subject": "Брянская область"},
    {"pattern": "красная горе", "name": "Красная Гора", "lat": 53.0, "lon": 31.6, "type": "city", "subject": "Брянская область"},
    {"pattern": "мглин", "name": "Мглин", "lat": 53.067, "lon": 32.85, "type": "city", "subject": "Брянская область"},
    {"pattern": "мглине", "name": "Мглин", "lat": 53.067, "lon": 32.85, "type": "city", "subject": "Брянская область"},
    {"pattern": "навля", "name": "Навля", "lat": 52.833, "lon": 34.5, "type": "city", "subject": "Брянская область"},
    {"pattern": "навле", "name": "Навля", "lat": 52.833, "lon": 34.5, "type": "city", "subject": "Брянская область"},
    {"pattern": "погар", "name": "Погар", "lat": 52.55, "lon": 33.25, "type": "city", "subject": "Брянская область"},
    {"pattern": "погаре", "name": "Погар", "lat": 52.55, "lon": 33.25, "type": "city", "subject": "Брянская область"},
    {"pattern": "рогнедино", "name": "Рогнедино", "lat": 53.8, "lon": 33.55, "type": "city", "subject": "Брянская область"},
    {"pattern": "суземка", "name": "Суземка", "lat": 52.317, "lon": 34.083, "type": "city", "subject": "Брянская область"},
    {"pattern": "суземке", "name": "Суземка", "lat": 52.317, "lon": 34.083, "type": "city", "subject": "Брянская область"},
    {"pattern": "красный колодец", "name": "Красный Колодец", "lat": 52.597, "lon": 34.497, "type": "city", "subject": "Брянская область"},
    {"pattern": "красном колодце", "name": "Красный Колодец", "lat": 52.597, "lon": 34.497, "type": "city", "subject": "Брянская область"},

    # Смоленская область — районы
    {"pattern": "велижский район", "name": "Велиж", "lat": 55.6, "lon": 31.2, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "велижском районе", "name": "Велиж", "lat": 55.6, "lon": 31.2, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "велижский р-н", "name": "Велиж", "lat": 55.6, "lon": 31.2, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "велижском р-не", "name": "Велиж", "lat": 55.6, "lon": 31.2, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "вяземский район", "name": "Вязьма", "lat": 55.2, "lon": 34.3, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "вяземском районе", "name": "Вязьма", "lat": 55.2, "lon": 34.3, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "вяземский р-н", "name": "Вязьма", "lat": 55.2, "lon": 34.3, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "вяземском р-не", "name": "Вязьма", "lat": 55.2, "lon": 34.3, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "гагаринский район", "name": "Гагарин", "lat": 55.55, "lon": 34.98, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "гагаринском районе", "name": "Гагарин", "lat": 55.55, "lon": 34.98, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "гагаринский р-н", "name": "Гагарин", "lat": 55.55, "lon": 34.98, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "гагаринском р-не", "name": "Гагарин", "lat": 55.55, "lon": 34.98, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "глинковский район", "name": "Глинка", "lat": 54.633, "lon": 32.867, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "глинковском районе", "name": "Глинка", "lat": 54.633, "lon": 32.867, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "глинковский р-н", "name": "Глинка", "lat": 54.633, "lon": 32.867, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "глинковском р-не", "name": "Глинка", "lat": 54.633, "lon": 32.867, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "демидовский район", "name": "Демидов", "lat": 55.27, "lon": 31.52, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "демидовском районе", "name": "Демидов", "lat": 55.27, "lon": 31.52, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "демидовский р-н", "name": "Демидов", "lat": 55.27, "lon": 31.52, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "демидовском р-не", "name": "Демидов", "lat": 55.27, "lon": 31.52, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "дорогобужский район", "name": "Дорогобуж", "lat": 54.92, "lon": 33.3, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "дорогобужском районе", "name": "Дорогобуж", "lat": 54.92, "lon": 33.3, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "дорогобужский р-н", "name": "Дорогобуж", "lat": 54.92, "lon": 33.3, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "дорогобужском р-не", "name": "Дорогобуж", "lat": 54.92, "lon": 33.3, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "духовщинский район", "name": "Духовщина", "lat": 55.2, "lon": 32.4, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "духовщинском районе", "name": "Духовщина", "lat": 55.2, "lon": 32.4, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "духовщинский р-н", "name": "Духовщина", "lat": 55.2, "lon": 32.4, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "духовщинском р-не", "name": "Духовщина", "lat": 55.2, "lon": 32.4, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "ельнинский район", "name": "Ельня", "lat": 54.57, "lon": 33.18, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "ельнинском районе", "name": "Ельня", "lat": 54.57, "lon": 33.18, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "ельнинский р-н", "name": "Ельня", "lat": 54.57, "lon": 33.18, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "ельнинском р-не", "name": "Ельня", "lat": 54.57, "lon": 33.18, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "ершичский район", "name": "Ершичи", "lat": 53.667, "lon": 32.75, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "ершичском районе", "name": "Ершичи", "lat": 53.667, "lon": 32.75, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "ершичский р-н", "name": "Ершичи", "lat": 53.667, "lon": 32.75, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "ершичском р-не", "name": "Ершичи", "lat": 53.667, "lon": 32.75, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "кардымовский район", "name": "Кардымово", "lat": 54.883, "lon": 32.433, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "кардымовском районе", "name": "Кардымово", "lat": 54.883, "lon": 32.433, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "кардымовский р-н", "name": "Кардымово", "lat": 54.883, "lon": 32.433, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "кардымовском р-не", "name": "Кардымово", "lat": 54.883, "lon": 32.433, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "краснинский район", "name": "Красный", "lat": 54.55, "lon": 31.433, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "краснинском районе", "name": "Красный", "lat": 54.55, "lon": 31.433, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "краснинский р-н", "name": "Красный", "lat": 54.55, "lon": 31.433, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "краснинском р-не", "name": "Красный", "lat": 54.55, "lon": 31.433, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "монастырщинский район", "name": "Монастырщина", "lat": 54.35, "lon": 31.833, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "монастырщинском районе", "name": "Монастырщина", "lat": 54.35, "lon": 31.833, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "монастырщинский р-н", "name": "Монастырщина", "lat": 54.35, "lon": 31.833, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "монастырщинском р-не", "name": "Монастырщина", "lat": 54.35, "lon": 31.833, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "новодугинский район", "name": "Новодугино", "lat": 55.633, "lon": 34.3, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "новодугинском районе", "name": "Новодугино", "lat": 55.633, "lon": 34.3, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "новодугинский р-н", "name": "Новодугино", "lat": 55.633, "lon": 34.3, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "новодугинском р-не", "name": "Новодугино", "lat": 55.633, "lon": 34.3, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "починковский район", "name": "Починок", "lat": 54.4, "lon": 32.45, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "починковском районе", "name": "Починок", "lat": 54.4, "lon": 32.45, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "починковский р-н", "name": "Починок", "lat": 54.4, "lon": 32.45, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "починковском р-не", "name": "Починок", "lat": 54.4, "lon": 32.45, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "рославльский район", "name": "Рославль", "lat": 53.95, "lon": 32.87, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "рославльском районе", "name": "Рославль", "lat": 53.95, "lon": 32.87, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "рославльский р-н", "name": "Рославль", "lat": 53.95, "lon": 32.87, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "рославльском р-не", "name": "Рославль", "lat": 53.95, "lon": 32.87, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "руднянский район", "name": "Рудня", "lat": 54.95, "lon": 31.08, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "руднянском районе", "name": "Рудня", "lat": 54.95, "lon": 31.08, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "руднянский р-н", "name": "Рудня", "lat": 54.95, "lon": 31.08, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "руднянском р-не", "name": "Рудня", "lat": 54.95, "lon": 31.08, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "сафоновский район", "name": "Сафоново", "lat": 55.1, "lon": 33.23, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "сафоновском районе", "name": "Сафоново", "lat": 55.1, "lon": 33.23, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "сафоновский р-н", "name": "Сафоново", "lat": 55.1, "lon": 33.23, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "сафоновском р-не", "name": "Сафоново", "lat": 55.1, "lon": 33.23, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "смоленский район", "name": "Смоленск", "lat": 54.78, "lon": 32.04, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "смоленском районе", "name": "Смоленск", "lat": 54.78, "lon": 32.04, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "смоленский р-н", "name": "Смоленск", "lat": 54.78, "lon": 32.04, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "смоленском р-не", "name": "Смоленск", "lat": 54.78, "lon": 32.04, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "сычёвский район", "name": "Сычёвка", "lat": 55.83, "lon": 34.28, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "сычёвском районе", "name": "Сычёвка", "lat": 55.83, "lon": 34.28, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "сычёвский р-н", "name": "Сычёвка", "lat": 55.83, "lon": 34.28, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "сычёвском р-не", "name": "Сычёвка", "lat": 55.83, "lon": 34.28, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "тёмкинский район", "name": "Тёмкино", "lat": 55.083, "lon": 35.0, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "тёмкинском районе", "name": "Тёмкино", "lat": 55.083, "lon": 35.0, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "тёмкинский р-н", "name": "Тёмкино", "lat": 55.083, "lon": 35.0, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "тёмкинском р-не", "name": "Тёмкино", "lat": 55.083, "lon": 35.0, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "угранский район", "name": "Угра", "lat": 54.767, "lon": 34.317, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "угранском районе", "name": "Угра", "lat": 54.767, "lon": 34.317, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "угранский р-н", "name": "Угра", "lat": 54.767, "lon": 34.317, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "угранском р-не", "name": "Угра", "lat": 54.767, "lon": 34.317, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "хиславичский район", "name": "Хиславичи", "lat": 54.183, "lon": 32.167, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "хиславичском районе", "name": "Хиславичи", "lat": 54.183, "lon": 32.167, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "хиславичский р-н", "name": "Хиславичи", "lat": 54.183, "lon": 32.167, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "хиславичском р-не", "name": "Хиславичи", "lat": 54.183, "lon": 32.167, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "холм-жирковский район", "name": "Холм-Жирковский", "lat": 55.517, "lon": 33.467, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "холм-жирковском районе", "name": "Холм-Жирковский", "lat": 55.517, "lon": 33.467, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "холм-жирковский р-н", "name": "Холм-Жирковский", "lat": 55.517, "lon": 33.467, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "холм-жирковском р-не", "name": "Холм-Жирковский", "lat": 55.517, "lon": 33.467, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "шумячский район", "name": "Шумячи", "lat": 53.85, "lon": 32.417, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "шумячском районе", "name": "Шумячи", "lat": 53.85, "lon": 32.417, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "шумячский р-н", "name": "Шумячи", "lat": 53.85, "lon": 32.417, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "шумячском р-не", "name": "Шумячи", "lat": 53.85, "lon": 32.417, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "ярцевский район", "name": "Ярцево", "lat": 55.07, "lon": 32.7, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "ярцевском районе", "name": "Ярцево", "lat": 55.07, "lon": 32.7, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "ярцевский р-н", "name": "Ярцево", "lat": 55.07, "lon": 32.7, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "ярцевском р-не", "name": "Ярцево", "lat": 55.07, "lon": 32.7, "type": "region", "is_region": True, "subject": "Смоленская область"},

    # Смоленская область — населённые пункты не из CITY_DB
    {"pattern": "глинка", "name": "Глинка", "lat": 54.633, "lon": 32.867, "type": "city", "subject": "Смоленская область"},
    {"pattern": "глинке", "name": "Глинка", "lat": 54.633, "lon": 32.867, "type": "city", "subject": "Смоленская область"},
    {"pattern": "ершичи", "name": "Ершичи", "lat": 53.667, "lon": 32.75, "type": "city", "subject": "Смоленская область"},
    {"pattern": "кардымово", "name": "Кардымово", "lat": 54.883, "lon": 32.433, "type": "city", "subject": "Смоленская область"},
    {"pattern": "красный", "name": "Красный", "lat": 54.55, "lon": 31.433, "type": "city", "subject": "Смоленская область"},
    {"pattern": "красные", "name": "Красный", "lat": 54.55, "lon": 31.433, "type": "city", "subject": "Смоленская область"},
    {"pattern": "монастырщина", "name": "Монастырщина", "lat": 54.35, "lon": 31.833, "type": "city", "subject": "Смоленская область"},
    {"pattern": "монастырщине", "name": "Монастырщина", "lat": 54.35, "lon": 31.833, "type": "city", "subject": "Смоленская область"},
    {"pattern": "новодугино", "name": "Новодугино", "lat": 55.633, "lon": 34.3, "type": "city", "subject": "Смоленская область"},
    {"pattern": "тёмкино", "name": "Тёмкино", "lat": 55.083, "lon": 35.0, "type": "city", "subject": "Смоленская область"},
    {"pattern": "угра", "name": "Угра", "lat": 54.767, "lon": 34.317, "type": "city", "subject": "Смоленская область"},
    {"pattern": "угре", "name": "Угра", "lat": 54.767, "lon": 34.317, "type": "city", "subject": "Смоленская область"},
    {"pattern": "хиславичи", "name": "Хиславичи", "lat": 54.183, "lon": 32.167, "type": "city", "subject": "Смоленская область"},
    {"pattern": "холм-жирковский", "name": "Холм-Жирковский", "lat": 55.517, "lon": 33.467, "type": "city", "subject": "Смоленская область"},
    {"pattern": "холм-жирковские", "name": "Холм-Жирковский", "lat": 55.517, "lon": 33.467, "type": "city", "subject": "Смоленская область"},
    {"pattern": "шумячи", "name": "Шумячи", "lat": 53.85, "lon": 32.417, "type": "city", "subject": "Смоленская область"},
    make_region_alias("медынский район", "Медынь", 54.97, 35.86),
    make_region_alias("медынский р-н", "Медынь", 54.97, 35.86),
    make_region_alias("кромской район", "Кромы", 52.687, 35.768),
    make_region_alias("кромской р-н", "Кромы", 52.687, 35.768),
    make_region_alias("залегощенский район", "Залегощь", 52.902, 36.884),
    make_region_alias("залегощенский р-н", "Залегощь", 52.902, 36.884),
    make_region_alias("заокский район", "Страхово", 54.75, 37.34, subject="Тульская область"),
    make_region_alias("заокский р-н", "Страхово", 54.75, 37.34, subject="Тульская область"),
    make_region_alias("ростов на дону", "Ростов-на-Дону", 47.2357, 39.7015),
    make_region_alias_with_cases("ростовская область", "Ростов-на-Дону", 47.2357, 39.7015),
    make_region_alias_with_cases("ростовская обл", "Ростов-на-Дону", 47.2357, 39.7015),
    make_region_alias_with_cases("московская область", "Москва", 55.7558, 37.6173, subject="Московская область"),
    make_region_alias_with_cases("московская обл", "Москва", 55.7558, 37.6173, subject="Московская область"),
    make_region_alias("мо", "Москва", 55.7558, 37.6173, subject="Московская область"),
    make_region_alias_with_cases("ленинградская область", "Санкт-Петербург", 59.9343, 30.3351, subject="Ленинградская область"),
    make_region_alias_with_cases("ленинградская обл", "Санкт-Петербург", 59.9343, 30.3351, subject="Ленинградская область"),
    {"pattern": "тосненский район", "name": "Тосно", "lat": 59.541179, "lon": 30.875006, "type": "region", "is_region": True, "subject": "Ленинградская область"},
    {"pattern": "тосненском районе", "name": "Тосно", "lat": 59.541179, "lon": 30.875006, "type": "region", "is_region": True, "subject": "Ленинградская область"},
    {"pattern": "тосненского района", "name": "Тосно", "lat": 59.541179, "lon": 30.875006, "type": "region", "is_region": True, "subject": "Ленинградская область"},
    {"pattern": "тосненский р-н", "name": "Тосно", "lat": 59.541179, "lon": 30.875006, "type": "region", "is_region": True, "subject": "Ленинградская область"},
    {"pattern": "тосненском р-не", "name": "Тосно", "lat": 59.541179, "lon": 30.875006, "type": "region", "is_region": True, "subject": "Ленинградская область"},
    {"pattern": "тосненского р-на", "name": "Тосно", "lat": 59.541179, "lon": 30.875006, "type": "region", "is_region": True, "subject": "Ленинградская область"},
    make_region_alias_with_cases("краснодарский край", "Краснодар", 45.0355, 38.9753),
    make_region_alias_with_cases("ставропольский край", "Ставрополь", 45.0448, 41.9692),
    make_region_alias_with_cases("приморский край", "Владивосток", 43.1056, 131.8735),
    make_region_alias_with_cases("хабаровский край", "Хабаровск", 48.4802, 135.0719),
    make_region_alias_with_cases("алтайский край", "Барнаул", 53.3474, 83.7783),
    make_region_alias_with_cases("забайкальский край", "Чита", 52.0333, 113.5),
    make_region_alias_with_cases("камчатский край", "Петропавловск-Камчатский", 53.0167, 158.65),
    make_region_alias_with_cases("пермский край", "Пермь", 58.0105, 56.2502),
    make_region_alias("крым", "Симферополь", 44.9521, 34.1024, subject="Республика Крым"),
    make_region_alias_with_cases("республика крым", "Симферополь", 44.9521, 34.1024, subject="Республика Крым"),
    make_region_alias("керченский полуостров", "Керчь", 45.33861, 36.46806, subject="Республика Крым"),
    make_region_alias("керченский", "Керчь", 45.33861, 36.46806, subject="Республика Крым"),
    make_region_alias("адыгея", "Майкоп", 44.6833, 40.1167),
    make_region_alias_with_cases("республика адыгея", "Майкоп", 44.6833, 40.1167),
    make_region_alias("башкортостан", "Уфа", 54.7355, 55.9587),
    make_region_alias_with_cases("республика башкортостан", "Уфа", 54.7355, 55.9587),
    make_region_alias("бурятия", "Улан-Удэ", 51.8333, 107.6),
    make_region_alias_with_cases("республика бурятия", "Улан-Удэ", 51.8333, 107.6),
    make_region_alias("дагестан", "Махачкала", 42.9849, 47.5047),
    make_region_alias_with_cases("республика дагестан", "Махачкала", 42.9849, 47.5047),
    make_region_alias("ингушетия", "Магас", 43.1688, 44.8168),
    make_region_alias_with_cases("республика ингушетия", "Магас", 43.1688, 44.8168),
    make_region_alias("кабардино-балкария", "Нальчик", 43.4982, 43.6059),
    make_region_alias_with_cases("кабардино-балкарская республика", "Нальчик", 43.4982, 43.6059),
    make_region_alias("калмыкия", "Элиста", 46.3082, 44.2558),
    make_region_alias_with_cases("республика калмыкия", "Элиста", 46.3082, 44.2558),
    make_region_alias_with_cases("карачаево-черкесская республика", "Черкесск", 44.2263, 42.0418),
    make_region_alias("карачаево-черкессия", "Черкесск", 44.2263, 42.0418),
    make_region_alias("карелия", "Петрозаводск", 61.7849, 34.3469),
    make_region_alias_with_cases("республика карелия", "Петрозаводск", 61.7849, 34.3469),
    make_region_alias("коми", "Сыктывкар", 61.6688, 50.8361),
    make_region_alias_with_cases("республика коми", "Сыктывкар", 61.6688, 50.8361),
    make_region_alias("марий эл", "Йошкар-Ола", 56.6344, 47.8999),
    make_region_alias_with_cases("республика марий эл", "Йошкар-Ола", 56.6344, 47.8999),
    make_region_alias("мордовия", "Саранск", 54.1838, 45.1749),
    make_region_alias_with_cases("республика мордовия", "Саранск", 54.1838, 45.1749),
    make_region_alias("якутия", "Якутск", 62.0355, 129.6755),
    make_region_alias_with_cases("республика саха", "Якутск", 62.0355, 129.6755),
    make_region_alias("саха (якутия)", "Якутск", 62.0355, 129.6755),
    make_region_alias("северная осетия", "Владикавказ", 43.0205, 44.6819),
    make_region_alias_with_cases("республика северная осетия", "Владикавказ", 43.0205, 44.6819),
    make_region_alias("татарстан", "Казань", 55.7961, 49.1064),
    make_region_alias_with_cases("республика татарстан", "Казань", 55.7961, 49.1064),
    make_region_alias("тыва", "Кызыл", 51.7194, 94.4372),
    make_region_alias("удмуртия", "Ижевск", 56.8498, 53.2045),
    make_region_alias_with_cases("удмуртская республика", "Ижевск", 56.8498, 53.2045),
    make_region_alias("хакасия", "Абакан", 53.7167, 91.4167),
    make_region_alias_with_cases("республика хакасия", "Абакан", 53.7167, 91.4167),
    make_region_alias("чувашия", "Чебоксары", 56.1322, 47.2442),
    make_region_alias_with_cases("чувашская республика", "Чебоксары", 56.1322, 47.2442),
    make_region_alias("чечня", "Грозный", 43.3125, 45.6947),
    make_region_alias_with_cases("чеченская республика", "Грозный", 43.3125, 45.6947),
    make_region_alias_with_cases("белгородская область", "Белгород", 50.5997, 36.5986),
    make_region_alias_with_cases("белгородская обл", "Белгород", 50.5997, 36.5986),
    make_region_alias_with_cases("брянская область", "Брянск", 53.2521, 34.3717),
    make_region_alias_with_cases("брянская обл", "Брянск", 53.2521, 34.3717),
    make_region_alias_with_cases("владимирская область", "Владимир", 56.1333, 40.4167),
    make_region_alias_with_cases("владимирская обл", "Владимир", 56.1333, 40.4167),
    make_region_alias_with_cases("волгоградская область", "Волгоград", 48.7071, 44.5169),
    make_region_alias_with_cases("вологодская область", "Вологда", 59.2167, 39.9),
    make_region_alias_with_cases("воронежская область", "Воронеж", 51.6717, 39.2106),
    make_region_alias_with_cases("воронежская обл", "Воронеж", 51.6717, 39.2106),
    make_region_alias_with_cases("ивановская область", "Иваново", 56.9997, 40.9726),
    # Аэропорты
    {"pattern": "аэропорт иваново", "name": "Аэропорт Иваново (Южный)", "lat": 56.9417, "lon": 40.9408, "type": "city", "is_region": False, "subject": "Ивановская область"},
    {"pattern": "аэропорт ярославль", "name": "Аэропорт Ярославль (Туношна)", "lat": 57.5608, "lon": 40.1544, "type": "city", "is_region": False, "subject": "Ярославская область"},
    # Аэропорты Московской области
    {"pattern": "аэропорт жуковский", "name": "Аэропорт Жуковский", "lat": 55.5533, "lon": 38.15, "type": "city", "is_region": False, "subject": "Московская область"},
    {"pattern": "аэропорт домодедово", "name": "Аэропорт Домодедово", "lat": 55.4088, "lon": 37.9063, "type": "city", "is_region": False, "subject": "Московская область"},
    {"pattern": "аэропорт внуково", "name": "Аэропорт Внуково", "lat": 55.5916, "lon": 37.2615, "type": "city", "is_region": False, "subject": "Московская область"},
    {"pattern": "аэропорт шереметьево", "name": "Аэропорт Шереметьево", "lat": 55.9726, "lon": 37.4146, "type": "city", "is_region": False, "subject": "Московская область"},
    make_region_alias_with_cases("иркутская область", "Иркутск", 52.2864, 104.2807),
    make_region_alias_with_cases("калининградская область", "Калининград", 54.7104, 20.4522),
    make_region_alias_with_cases("калужская область", "Калуга", 54.5293, 36.2754),
    make_region_alias_with_cases("кемеровская область", "Кемерово", 55.3548, 86.0887),
    make_region_alias_with_cases("кировская область", "Киров", 58.6036, 49.6680),
    make_region_alias_with_cases("костромская область", "Кострома", 57.7678, 40.9269),
    make_region_alias_with_cases("курганская область", "Курган", 55.4544, 65.3219),
    make_region_alias_with_cases("курская область", "Курск", 51.7304, 36.1927),
    make_region_alias_with_cases("липецкая область", "Липецк", 52.6032, 39.5938),
    make_region_alias_with_cases("нижегородская область", "Нижний Новгород", 56.3269, 44.0059),
    make_region_alias_with_cases("нижегородская обл", "Нижний Новгород", 56.3269, 44.0059),
    make_region_alias_with_cases("новгородская область", "Великий Новгород", 58.5250, 31.2750),
    make_region_alias_with_cases("новосибирская область", "Новосибирск", 55.0302, 82.9204),
    make_region_alias_with_cases("омская область", "Омск", 54.9893, 73.3682),
    make_region_alias_with_cases("оренбургская область", "Оренбург", 51.7682, 55.0970),
    make_region_alias_with_cases("орловская область", "Орёл", 52.9678, 36.0696),
    make_region_alias_with_cases("пензенская область", "Пенза", 53.2001, 45.0175),
    make_region_alias_with_cases("псковская область", "Псков", 57.8167, 28.3333),
    make_region_alias_with_cases("рязанская область", "Рязань", 54.61667, 39.71667),
    make_region_alias_with_cases("самарская область", "Самара", 53.2415, 50.2212),
    make_region_alias_with_cases("саратовская область", "Саратов", 51.5336, 46.0343),
    make_region_alias_with_cases("сахалинская область", "Южно-Сахалинск", 46.9592, 142.7388),
    make_region_alias_with_cases("свердловская область", "Екатеринбург", 56.8389, 60.6057),
    make_region_alias_with_cases("смоленская область", "Смоленск", 54.7826, 32.0453),
    make_region_alias_with_cases("тамбовская область", "Тамбов", 52.7313, 41.4433),
    make_region_alias_with_cases("тверская область", "Тверь", 56.8587, 35.9176),
    make_region_alias_with_cases("томская область", "Томск", 56.4887, 84.9523),
    make_region_alias_with_cases("тульская область", "Тула", 54.1924, 37.6154),
    make_region_alias_with_cases("ульяновская область", "Ульяновск", 54.3178, 48.4027),
    make_region_alias_with_cases("челябинская область", "Челябинск", 55.1599, 61.4026),
    make_region_alias_with_cases("ярославская область", "Ярославль", 57.6261, 39.8845),
    make_region_alias_with_cases("амурская область", "Благовещенск", 50.2578, 127.5364),
    make_region_alias_with_cases("архангельская область", "Архангельск", 64.5395, 40.5173),
    make_region_alias_with_cases("астраханская область", "Астрахань", 46.3333, 48.0333),
    make_region_alias_with_cases("мурманская область", "Мурманск", 68.9792, 33.0925),
    make_region_alias_with_cases("тюменская область", "Тюмень", 57.1535, 65.5423),
    make_region_alias_with_cases("херсонская область", "Херсон", 46.6354, 32.6169),
    # Херсонская область — районы
    {"pattern": "чаплынский район", "name": "Чаплынка", "lat": 46.365, "lon": 33.533, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "чаплынском районе", "name": "Чаплынка", "lat": 46.365, "lon": 33.533, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "чаплынский р-н", "name": "Чаплынка", "lat": 46.365, "lon": 33.533, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "чаплынском р-не", "name": "Чаплынка", "lat": 46.365, "lon": 33.533, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "новотроицкий район", "name": "Новотроицк", "lat": 46.348, "lon": 34.325, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "новотроицком районе", "name": "Новотроицк", "lat": 46.348, "lon": 34.325, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "новотроицкий р-н", "name": "Новотроицк", "lat": 46.348, "lon": 34.325, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "новотроицком р-не", "name": "Новотроицк", "lat": 46.348, "lon": 34.325, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "генический район", "name": "Геническ", "lat": 46.175, "lon": 34.803, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "геническом районе", "name": "Геническ", "lat": 46.175, "lon": 34.803, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "генический р-н", "name": "Геническ", "lat": 46.175, "lon": 34.803, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "геническом р-не", "name": "Геническ", "lat": 46.175, "lon": 34.803, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "геническ", "name": "Геническ", "lat": 46.78, "lon": 34.80, "type": "city", "subject": "Херсонская область"},
    {"pattern": "геническа", "name": "Геническ", "lat": 46.78, "lon": 34.80, "type": "city", "subject": "Херсонская область"},
    {"pattern": "геническе", "name": "Геническ", "lat": 46.78, "lon": 34.80, "type": "city", "subject": "Херсонская область"},
    {"pattern": "новоалексеевка", "name": "Новоалексеевка", "lat": 46.63, "lon": 34.38, "type": "city", "subject": "Херсонская область"},
    {"pattern": "новоалексеевки", "name": "Новоалексеевка", "lat": 46.63, "lon": 34.38, "type": "city", "subject": "Херсонская область"},
    {"pattern": "новоалексеевке", "name": "Новоалексеевка", "lat": 46.63, "lon": 34.38, "type": "city", "subject": "Херсонская область"},
    {"pattern": "новоалексеевку", "name": "Новоалексеевка", "lat": 46.63, "lon": 34.38, "type": "city", "subject": "Херсонская область"},
    make_region_alias_with_cases("запорожская область", "Запорожье", 47.8388, 35.1396),
    make_region_alias("днр", "Донецк", 48.0159, 37.8028, subject="Донецкая область", use_city_db=False),
    {"pattern": "лднр", "name": "Донецк", "lat": 48.0159, "lon": 37.8028, "type": "region", "is_region": True, "subject": "Донецкая область"},
    {"pattern": "горловка", "name": "Горловка", "lat": 48.3342, "lon": 37.8919, "type": "city", "subject": "ДНР"},
    {"pattern": "енакиево", "name": "Енакиево", "lat": 48.2300, "lon": 38.2042, "type": "city", "subject": "ДНР"},
    make_region_alias("лнр", "Луганск", 48.574, 39.3078, subject="Луганская область"),
    {"pattern": "красный луч", "name": "Красный Луч", "lat": 48.33, "lon": 38.97, "type": "city", "subject": "Луганская область"},
    make_region_alias("артёмовск", "Артёмовск", 48.594, 38.002, "ДНР", use_city_db=False),
    make_region_alias("бахмут", "Бахмут", 48.594, 38.002, "ДНР", use_city_db=False),
    make_region_alias_with_cases("ямало-ненецкий автономный округ", "Салехард", 66.5300, 66.6019),
    make_region_alias_with_cases("ханты-мансийский автономный округ", "Ханты-Мансийск", 61.0024, 69.0099),
    # опечатка «Мантийский» (без «с») — встречается в реальных постах
    {"pattern": "ханты-мантийский автономный округ", "name": "Ханты-Мансийск", "lat": 61.0024, "lon": 69.0099, "type": "region", "is_region": True, "subject": "Ханты-Мансийский Автономный Округ"},
    {"pattern": "ханты-мантийского автономного округа", "name": "Ханты-Мансийск", "lat": 61.0024, "lon": 69.0099, "type": "region", "is_region": True, "subject": "Ханты-Мансийский Автономный Округ"},
    {"pattern": "ханты-мантийском автономном округе", "name": "Ханты-Мансийск", "lat": 61.0024, "lon": 69.0099, "type": "region", "is_region": True, "subject": "Ханты-Мансийский Автономный Округ"},
    make_region_alias_with_cases("чукотский автономный округ", "Анадырь", 64.7333, 177.5167),
    make_region_alias_with_cases("еврейская автономная область", "Биробиджан", 48.7833, 132.9333),
    make_region_alias_with_cases("ненецкий автономный округ", "Нарьян-Мар", 67.6385, 53.0067),

    # Октябрьский район, Ростовская область
    {"pattern": "октябрьский район ростовская", "name": "Каменоломни", "lat": 47.6667, "lon": 40.2000, "type": "region", "is_region": True, "subject": "Ростовская область"},
    {"pattern": "октябрьском районе ростовской", "name": "Каменоломни", "lat": 47.6667, "lon": 40.2000, "type": "region", "is_region": True, "subject": "Ростовская область"},
    {"pattern": "октябрьский р-н ростовская", "name": "Каменоломни", "lat": 47.6667, "lon": 40.2000, "type": "region", "is_region": True, "subject": "Ростовская область"},
    {"pattern": "октябрьском р-не ростовской", "name": "Каменоломни", "lat": 47.6667, "lon": 40.2000, "type": "region", "is_region": True, "subject": "Ростовская область"},
    # Октябрьский, Рыбинский район (Ярославская область)
    {"pattern": "октябрьский, рыбинский", "name": "Октябрьский", "lat": 57.985, "lon": 39.11, "type": "city", "subject": "Ярославская область"},
    {"pattern": "октябрьский (рыбинский", "name": "Октябрьский", "lat": 57.985, "lon": 39.11, "type": "city", "subject": "Ярославская область"},
    # Октябрьский, Белгородский район (Белгородская область)
    {"pattern": "октябрьский, белгородская", "name": "Октябрьский", "lat": 50.44, "lon": 36.35, "type": "city", "subject": "Белгородская область"},
    {"pattern": "октябрьский, белгородский", "name": "Октябрьский", "lat": 50.44, "lon": 36.35, "type": "city", "subject": "Белгородская область"},
    # Отрадный/Отрадное, Белгородская область
    {"pattern": "отрадный, белгородская", "name": "Отрадное", "lat": 50.415, "lon": 36.334, "type": "city", "subject": "Белгородская область"},
    {"pattern": "отрадный, белгородский", "name": "Отрадное", "lat": 50.415, "lon": 36.334, "type": "city", "subject": "Белгородская область"},
    # Первомайский, Шумячский район (Смоленская область)
    {"pattern": "первомайский шумячский", "name": "Первомайский", "lat": 53.85, "lon": 32.42, "type": "city", "subject": "Смоленская область"},
    {"pattern": "первомайский смоленская", "name": "Первомайский", "lat": 53.85, "lon": 32.42, "type": "city", "subject": "Смоленская область"},
    # Шумячский район (Смоленская область)
    {"pattern": "шумячский район", "name": "Шумячи", "lat": 53.85, "lon": 32.42, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "шумячском районе", "name": "Шумячи", "lat": 53.85, "lon": 32.42, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "шумячский р-н", "name": "Шумячи", "lat": 53.85, "lon": 32.42, "type": "region", "is_region": True, "subject": "Смоленская область"},
    {"pattern": "шумячском р-не", "name": "Шумячи", "lat": 53.85, "lon": 32.42, "type": "region", "is_region": True, "subject": "Смоленская область"},
    # Красногвардейский район, Крым (адм. центр — Красногвардейское/Курман)
    {"pattern": "красногвардейский район крым", "name": "Красногвардейское", "lat": 45.497, "lon": 34.297, "type": "region", "is_region": True, "subject": "Республика Крым"},
    {"pattern": "красногвардейский р-н крым", "name": "Красногвардейское", "lat": 45.497, "lon": 34.297, "type": "region", "is_region": True, "subject": "Республика Крым"},
    {"pattern": "крым красногвардейский район", "name": "Красногвардейское", "lat": 45.497, "lon": 34.297, "type": "region", "is_region": True, "subject": "Республика Крым"},
    {"pattern": "крым красногвардейский р-н", "name": "Красногвардейское", "lat": 45.497, "lon": 34.297, "type": "region", "is_region": True, "subject": "Республика Крым"},
    # Петровское, Красногвардейский район, Крым
    {"pattern": "петровское крым", "name": "Петровское", "lat": 45.495, "lon": 34.275, "type": "city", "subject": "Республика Крым"},
    {"pattern": "крым петровское", "name": "Петровское", "lat": 45.495, "lon": 34.275, "type": "city", "subject": "Республика Крым"},
    {"pattern": "петровское красногвардейский", "name": "Петровское", "lat": 45.495, "lon": 34.275, "type": "city", "subject": "Республика Крым"},
    # Кольчугино, Симферопольский район, Крым
    {"pattern": "кольчугино республика крым", "name": "Кольчугино", "lat": 44.94, "lon": 34.23, "type": "city", "subject": "Республика Крым"},
    {"pattern": "кольчугино симферополь", "name": "Кольчугино", "lat": 44.94, "lon": 34.23, "type": "city", "subject": "Республика Крым"},
    {"pattern": "крым кольчугино", "name": "Кольчугино", "lat": 44.94, "lon": 34.23, "type": "city", "subject": "Республика Крым"},
    # Табачное, Бахчисарайский район, Крым
    {"pattern": "табачное", "name": "Табачное", "lat": 44.902, "lon": 33.676, "type": "city", "subject": "Республика Крым"},
    {"pattern": "бахчисарай", "name": "Бахчисарай", "lat": 44.753, "lon": 33.861, "type": "city", "subject": "Республика Крым"},
    # Первомайский район, Крым (адм. центр — Первомайское)
    {"pattern": "первомайский район крым", "name": "Первомайское", "lat": 45.717, "lon": 33.856, "type": "region", "is_region": True, "subject": "Республика Крым"},
    {"pattern": "первомайском районе крым", "name": "Первомайское", "lat": 45.717, "lon": 33.856, "type": "region", "is_region": True, "subject": "Республика Крым"},
    {"pattern": "первомайский р-н крым", "name": "Первомайское", "lat": 45.717, "lon": 33.856, "type": "region", "is_region": True, "subject": "Республика Крым"},
    {"pattern": "первомайском р-не крым", "name": "Первомайское", "lat": 45.717, "lon": 33.856, "type": "region", "is_region": True, "subject": "Республика Крым"},
    {"pattern": "крым первомайский район", "name": "Первомайское", "lat": 45.717, "lon": 33.856, "type": "region", "is_region": True, "subject": "Республика Крым"},
    {"pattern": "крым первомайский р-н", "name": "Первомайское", "lat": 45.717, "lon": 33.856, "type": "region", "is_region": True, "subject": "Республика Крым"},
    # Зеленый Гай, Запорожская область
    {"pattern": "зеленый гай", "name": "Зеленый Гай", "lat": 46.85, "lon": 35.37, "type": "city", "subject": "Запорожская область"},
    {"pattern": "зеленого гая", "name": "Зеленый Гай", "lat": 46.85, "lon": 35.37, "type": "city", "subject": "Запорожская область"},
    # Акимовка, Запорожская область
    {"pattern": "акимовка", "name": "Акимовка", "lat": 46.733, "lon": 36.350, "type": "city", "subject": "Запорожская область"},
    # Приморск, Запорожская область (контекстные паттерны)
    {"pattern": "приморск запорожская", "name": "Приморск", "lat": 46.735, "lon": 36.345, "type": "city", "subject": "Запорожская область"},
    {"pattern": "приморск бердянск", "name": "Приморск", "lat": 46.735, "lon": 36.345, "type": "city", "subject": "Запорожская область"},
    {"pattern": "бердянск приморск", "name": "Приморск", "lat": 46.735, "lon": 36.345, "type": "city", "subject": "Запорожская область"},
    # Тамань, Краснодарский край
    {"pattern": "тамань", "name": "Тамань", "lat": 45.22, "lon": 36.72, "type": "city", "subject": "Краснодарский край"},
    # Каменка-Днепровская, Запорожская область
    {"pattern": "каменка днепровская", "name": "Каменка-Днепровская", "lat": 47.48, "lon": 34.41, "type": "city", "subject": "Запорожская область"},
    {"pattern": "каменки днепровской", "name": "Каменка-Днепровская", "lat": 47.48, "lon": 34.41, "type": "city", "subject": "Запорожская область"},
    # Великая Знаменка, Запорожская область
    {"pattern": "великая знаменка", "name": "Великая Знаменка", "lat": 47.44, "lon": 34.02, "type": "city", "subject": "Запорожская область"},
    {"pattern": "великой знаменки", "name": "Великая Знаменка", "lat": 47.44, "lon": 34.02, "type": "city", "subject": "Запорожская область"},
    # Великая Белозерка, Запорожская область
    {"pattern": "великая белозерка", "name": "Великая Белозерка", "lat": 47.21, "lon": 34.93, "type": "city", "subject": "Запорожская область"},
    {"pattern": "великой белозерки", "name": "Великая Белозерка", "lat": 47.21, "lon": 34.93, "type": "city", "subject": "Запорожская область"},
    # Бердянск, Запорожская область
    {"pattern": "бердянск", "name": "Бердянск", "lat": 46.755, "lon": 36.790, "type": "city", "subject": "Запорожская область"},
    {"pattern": "бердянска", "name": "Бердянск", "lat": 46.755, "lon": 36.790, "type": "city", "subject": "Запорожская область"},
    {"pattern": "бердянске", "name": "Бердянск", "lat": 46.755, "lon": 36.790, "type": "city", "subject": "Запорожская область"},
    # Мелитополь, Запорожская область
    {"pattern": "мелитополь", "name": "Мелитополь", "lat": 46.842, "lon": 35.365, "type": "city", "subject": "Запорожская область"},
    {"pattern": "мелитополя", "name": "Мелитополь", "lat": 46.842, "lon": 35.365, "type": "city", "subject": "Запорожская область"},
    {"pattern": "мелитополе", "name": "Мелитополь", "lat": 46.842, "lon": 35.365, "type": "city", "subject": "Запорожская область"},
    # Феодосия, Республика Крым
    {"pattern": "феодосия", "name": "Феодосия", "lat": 45.035, "lon": 35.378, "type": "city", "subject": "Республика Крым"},
    {"pattern": "феодосии", "name": "Феодосия", "lat": 45.035, "lon": 35.378, "type": "city", "subject": "Республика Крым"},
    # Горностаевка, Ленинский район, Крым
    {"pattern": "горностаевка", "name": "Горностаевка", "lat": 45.35, "lon": 36.48, "type": "city", "subject": "Республика Крым"},
    # Мелкие сёла Крыма (не в settlement_db)
    {"pattern": "сенокосное", "name": "Сенокосное", "lat": 45.827, "lon": 33.770, "type": "city", "subject": "Республика Крым"},
    # Ивановский район, Херсонская область
    {"pattern": "ивановский район херсонская", "name": "Ивановка", "lat": 46.717, "lon": 34.55, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "ивановском районе херсонской", "name": "Ивановка", "lat": 46.717, "lon": 34.55, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "ивановский р-н херсонская", "name": "Ивановка", "lat": 46.717, "lon": 34.55, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "херсонская ивановский район", "name": "Ивановка", "lat": 46.717, "lon": 34.55, "type": "region", "is_region": True, "subject": "Херсонская область"},
    {"pattern": "херсонская ивановский р-н", "name": "Ивановка", "lat": 46.717, "lon": 34.55, "type": "region", "is_region": True, "subject": "Херсонская область"},
    # Володарский район, ДНР/Донецкая область
    {"pattern": "володарский район днр", "name": "Володарское", "lat": 47.167, "lon": 37.317, "type": "region", "is_region": True, "subject": "ДНР"},
    {"pattern": "володарском районе днр", "name": "Володарское", "lat": 47.167, "lon": 37.317, "type": "region", "is_region": True, "subject": "ДНР"},
    {"pattern": "володарский р-н днр", "name": "Володарское", "lat": 47.167, "lon": 37.317, "type": "region", "is_region": True, "subject": "ДНР"},
    {"pattern": "днр володарский район", "name": "Володарское", "lat": 47.167, "lon": 37.317, "type": "region", "is_region": True, "subject": "ДНР"},
    {"pattern": "днр володарский р-н", "name": "Володарское", "lat": 47.167, "lon": 37.317, "type": "region", "is_region": True, "subject": "ДНР"},
    # Херсонская область — Новый Гай, Аскания Нова
    {"pattern": "новый гай", "name": "Новый Гай", "lat": 46.45, "lon": 33.87, "type": "city", "subject": "Херсонская область"},
    {"pattern": "новом гаю", "name": "Новый Гай", "lat": 46.45, "lon": 33.87, "type": "city", "subject": "Херсонская область"},
    {"pattern": "аскания нова", "name": "Аскания-Нова", "lat": 46.45, "lon": 33.87, "type": "city", "subject": "Херсонская область"},
    {"pattern": "аскании новой", "name": "Аскания-Нова", "lat": 46.45, "lon": 33.87, "type": "city", "subject": "Херсонская область"},
    # Северский район, Краснодарский край
    {"pattern": "северский район", "name": "Северская", "lat": 44.85, "lon": 38.67, "type": "region", "is_region": True, "subject": "Краснодарский край"},
    {"pattern": "северском районе", "name": "Северская", "lat": 44.85, "lon": 38.67, "type": "region", "is_region": True, "subject": "Краснодарский край"},
    {"pattern": "северский р-н", "name": "Северская", "lat": 44.85, "lon": 38.67, "type": "region", "is_region": True, "subject": "Краснодарский край"},
    {"pattern": "северском р-не", "name": "Северская", "lat": 44.85, "lon": 38.67, "type": "region", "is_region": True, "subject": "Краснодарский край"},
    {"pattern": "северская", "name": "Северская", "lat": 44.85, "lon": 38.67, "type": "city", "subject": "Краснодарский край"},
    # Красноармейский район, Краснодарский край
    {"pattern": "красноармейский район", "name": "Красноармейская", "lat": 45.36, "lon": 38.21, "type": "region", "is_region": True, "subject": "Краснодарский край"},
    {"pattern": "красноармейском районе", "name": "Красноармейская", "lat": 45.36, "lon": 38.21, "type": "region", "is_region": True, "subject": "Краснодарский край"},
    {"pattern": "красноармейский р-н", "name": "Красноармейская", "lat": 45.36, "lon": 38.21, "type": "region", "is_region": True, "subject": "Краснодарский край"},
    {"pattern": "красноармейском р-не", "name": "Красноармейская", "lat": 45.36, "lon": 38.21, "type": "region", "is_region": True, "subject": "Краснодарский край"},
    # Красносельский район, Краснодарский край
    {"pattern": "красносельский район", "name": "Красносельская", "lat": 46.35, "lon": 39.0, "type": "region", "is_region": True, "subject": "Краснодарский край"},
    {"pattern": "красносельском районе", "name": "Красносельская", "lat": 46.35, "lon": 39.0, "type": "region", "is_region": True, "subject": "Краснодарский край"},
    {"pattern": "красносельский р-н", "name": "Красносельская", "lat": 46.35, "lon": 39.0, "type": "region", "is_region": True, "subject": "Краснодарский край"},
    {"pattern": "красносельском р-не", "name": "Красносельская", "lat": 46.35, "lon": 39.0, "type": "region", "is_region": True, "subject": "Краснодарский край"},
    {"pattern": "красносельская", "name": "Красносельская", "lat": 46.35, "lon": 39.0, "type": "city", "subject": "Краснодарский край"},
    {"pattern": "староджерелиевская", "name": "Староджерелиевская", "lat": 45.35, "lon": 38.28, "type": "city", "subject": "Краснодарский край"},
    {"pattern": "старовеличковская", "name": "Старовеличковская", "lat": 45.42, "lon": 38.22, "type": "city", "subject": "Краснодарский край"},
    # гг — государственная граница (стык Брянской/Курской/Украина)
    {"pattern": "гг", "name": "гос. граница", "lat": 51.229707, "lon": 35.116505, "type": "region", "is_region": False, "subject": "Курская область"},
]

# Disambiguation rules: when a name matches multiple subjects, reassign
# if another result in the same post provides context.
# Key: name_lower → {wrong_subject_lower: replacement_with_context_subject}
DISAMBIGUATION_MAP = {
    "первомайский": {
        "тамбовская область": [
            {"context_subject": "смоленская область", "lat": 53.85, "lon": 32.42, "name": "Первомайский", "subject": "Смоленская область"},
            {"context_subject": "республика крым", "lat": 45.717, "lon": 33.856, "name": "Первомайское", "subject": "Республика Крым"},
        ],
        "ярославская область": [
            {"context_subject": "тамбовская область", "lat": 53.25, "lon": 40.283, "name": "Первомайский", "subject": "Тамбовская область"},
            {"context_subject": "республика крым", "lat": 45.717, "lon": 33.856, "name": "Первомайское", "subject": "Республика Крым"},
        ],
    },
    "петровское": {
        "тамбовская область": {
            "context_subject": "республика крым",
            "lat": 45.495,
            "lon": 34.275,
            "name": "Петровское",
            "subject": "Республика Крым",
        },
    },
    "красногвардейский": {
        "белгородская область": {
            "context_subject": "республика крым",
            "lat": 45.497,
            "lon": 34.297,
            "name": "Красногвардейское",
            "subject": "Республика Крым",
        },
    },
    "советский": {
        "ханты-мансийский ао": {
            "context_subject": "республика крым",
            "lat": 45.340,
            "lon": 34.930,
            "name": "Советский",
            "subject": "Республика Крым",
        },
        "курская область": [
            {
                "context_subject": "брянская область",
                "lat": 53.2433,
                "lon": 34.3634,
                "name": "Брянск",
                "subject": "Брянская область",
            },
            {
                # «Советский район Орска» — внутригородской район г.Орска
                "context_subject": "оренбургская область",
                "lat": 51.2,
                "lon": 58.61667,
                "name": "Орск",
                "subject": "Оренбургская область",
            },
        ],
    },
    "советском": {
        "ханты-мансийский ао": {
            "context_subject": "республика крым",
            "lat": 45.340,
            "lon": 34.930,
            "name": "Советский",
            "subject": "Республика Крым",
        },
        "курская область": [
            {
                "context_subject": "брянская область",
                "lat": 53.2433,
                "lon": 34.3634,
                "name": "Брянск",
                "subject": "Брянская область",
            },
            {
                "context_subject": "оренбургская область",
                "lat": 51.2,
                "lon": 58.61667,
                "name": "Орск",
                "subject": "Оренбургская область",
            },
        ],
    },
    "кольчугино": {
        "владимирская область": {
            "context_subject": "республика крым",
            "lat": 44.94,
            "lon": 34.23,
            "name": "Кольчугино",
            "subject": "Республика Крым",
        },
    },
    "приморск": {
        "ленинградская область": {
            "context_subject": "запорожская область",
            "lat": 46.735,
            "lon": 36.345,
            "name": "Приморск",
            "subject": "Запорожская область",
        },
    },
    "гай": {
        "оренбургская область": [
            {
                "context_subject": "запорожская область",
                "lat": 46.85,
                "lon": 35.37,
                "name": "Гай",
                "subject": "Запорожская область",
            },
            {
                "context_subject": "херсонская область",
                "lat": 46.45,
                "lon": 33.87,
                "name": "Новый Гай",
                "subject": "Херсонская область",
            },
        ],
    },
    "иваново": {
        "ивановская область": {
            "context_subject": "херсонская область",
            "lat": 46.717,
            "lon": 34.55,
            "name": "Ивановка",
            "subject": "Херсонская область",
        },
    },
    "ивановский": {
        "ивановская область": {
            "context_subject": "херсонская область",
            "lat": 46.717,
            "lon": 34.55,
            "name": "Ивановка",
            "subject": "Херсонская область",
        },
    },
    "володарск": {
        "нижегородская область": {
            "context_subject": "донецкая область",
            "lat": 47.167,
            "lon": 37.317,
            "name": "Володарское",
            "subject": "ДНР",
        },
    },
    "володарский": {
        "нижегородская область": [
            {
                "context_subject": "донецкая область",
                "lat": 47.167,
                "lon": 37.317,
                "name": "Володарское",
                "subject": "ДНР",
            },
            {
                "context_subject": "брянская область",
                "lat": 53.2433,
                "lon": 34.3634,
                "name": "Брянск",
                "subject": "Брянская область",
            },
        ],
    },
    "калининский": {
        "тверская область": {
            "context_subject": "краснодарский край",
            "lat": 45.48,
            "lon": 38.67,
            "name": "Калининская",
            "subject": "Краснодарский край",
        },
    },
    "мирный": {
        "архангельская область": [
            {"context_subject": "брянская область", "lat": 53.38037, "lon": 33.00014, "name": "Мирный", "subject": "Брянская область"},
        ],
        "якутия": [
            {"context_subject": "брянская область", "lat": 53.38037, "lon": 33.00014, "name": "Мирный", "subject": "Брянская область"},
        ],
    },
    "отрадное": {
        "ленинградская область": [
            {"context_subject": "республика крым", "lat": 44.860, "lon": 33.733, "name": "Отрадное", "subject": "Республика Крым"},
            {"context_subject": "севастополь", "lat": 44.860, "lon": 33.733, "name": "Отрадное", "subject": "Республика Крым"},
            {"context_subject": "ростовская область", "lat": 47.396, "lon": 38.744, "name": "Отрадное", "subject": "Ростовская область"},
        ],
    },
    "данилов": {
        "ярославская область": [
            {
                "context_subject": "волгоградская область",
                "lat": 50.582,
                "lon": 45.512,
                "name": "Даниловка",
                "subject": "Волгоградская область",
            },
        ],
    },
    "киров": {
        "кировская область": {
            "context_subject": "калужская область",
            "lat": 54.08333,
            "lon": 34.3,
            "name": "Киров",
            "subject": "Калужская область",
        },
    },
    "березники": {
        "пермский край": {
            "context_subject": "курская область",
            "lat": 51.614,
            "lon": 34.787,
            "name": "Березники",
            "subject": "Курская область",
        },
    },
    "алексеевский": {
        "белгородская область": [
            {"context_subject": "татарстан", "lat": 55.306, "lon": 50.119, "name": "Алексеевское", "subject": "Республика Татарстан"},
            {"context_subject": "республика татарстан", "lat": 55.306, "lon": 50.119, "name": "Алексеевское", "subject": "Республика Татарстан"},
        ],
    },
    "спасский": {
        "рязанская область": [
            {"context_subject": "татарстан", "lat": 54.96667, "lon": 49.03333, "name": "Болгар", "subject": "Республика Татарстан"},
            {"context_subject": "республика татарстан", "lat": 54.96667, "lon": 49.03333, "name": "Болгар", "subject": "Республика Татарстан"},
            {"context_subject": "нижегородская область", "lat": 55.85778, "lon": 45.7, "name": "Спасское", "subject": "Нижегородская область"},
            {"context_subject": "пензенская область", "lat": 53.93333, "lon": 43.18333, "name": "Спасск", "subject": "Пензенская область"},
            {"context_subject": "приморский край", "lat": 44.6, "lon": 132.81667, "name": "Спасск-Дальний", "subject": "Приморский край"},
        ],
    },
    "спасском": {
        "рязанская область": [
            {"context_subject": "татарстан", "lat": 54.96667, "lon": 49.03333, "name": "Болгар", "subject": "Республика Татарстан"},
            {"context_subject": "республика татарстан", "lat": 54.96667, "lon": 49.03333, "name": "Болгар", "subject": "Республика Татарстан"},
            {"context_subject": "нижегородская область", "lat": 55.85778, "lon": 45.7, "name": "Спасское", "subject": "Нижегородская область"},
            {"context_subject": "пензенская область", "lat": 53.93333, "lon": 43.18333, "name": "Спасск", "subject": "Пензенская область"},
            {"context_subject": "приморский край", "lat": 44.6, "lon": 132.81667, "name": "Спасск-Дальний", "subject": "Приморский край"},
        ],
    },
    "борисоглебский": {
        "ярославская область": [
            {"context_subject": "воронежская область", "lat": 51.367, "lon": 42.083, "name": "Борисоглебск", "subject": "Воронежская область"},
        ],
    },
    "красногорск": {
        "__any__": [
            {"context_subject": "удмуртия", "lat": 57.70694, "lon": 52.49694, "name": "Красногорское", "subject": "Удмуртия"},
        ],
    },
    "красногорский": {
        "__any__": [
            {"context_subject": "удмуртия", "lat": 57.70694, "lon": 52.49694, "name": "Красногорское", "subject": "Удмуртия"},
        ],
    },
    "монастырщинский": {
        "смоленская область": [
            {"context_subject": "воронежская область", "lat": 49.832, "lon": 40.921, "name": "Монастырщина", "subject": "Воронежская область"},
        ],
    },
    "красносельский": {
        "костромская область": [
            {"context_subject": "краснодарский край", "lat": 46.35, "lon": 39.0, "name": "Красносельская", "subject": "Краснодарский край"},
        ],
    },
    "красное-на-волге": {
        "костромская область": [
            {"context_subject": "краснодарский край", "lat": 46.35, "lon": 39.0, "name": "Красносельская", "subject": "Краснодарский край"},
        ],
    },
    "белозерский": {
        "вологодская область": [
            {"context_subject": "московская область", "lat": 55.46, "lon": 37.47, "name": "Белоозёрский", "subject": "Московская область"},
        ],
    },
    "белозерск": {
        "вологодская область": [
            {"context_subject": "московская область", "lat": 55.46, "lon": 37.47, "name": "Белоозёрский", "subject": "Московская область"},
        ],
    },
    "архангельская": {
        "архангельская область": {
            "context_subject": "краснодарский край",
            "lat": 45.707,
            "lon": 40.350,
            "name": "Архангельская",
            "subject": "Краснодарский край",
        },
    },
    "куйбышевский": {
        "калужская область": [
            {
                "context_subject": "ростовская область",
                "lat": 47.817,
                "lon": 38.908,
                "name": "Куйбышево",
                "subject": "Ростовская область",
            },
            {
                "context_subject": "запорожская область",
                "lat": 47.35,
                "lon": 36.65,
                "name": "Куйбышево",
                "subject": "Запорожская область",
            },
        ],
    },
    "видное": {
        "московская область": {
            "context_subject": "республика крым",
            "lat": 45.092875,
            "lon": 35.243711,
            "name": "Видное",
            "subject": "Республика Крым",
        },
    },
    "кировский": {
        "калужская область": {
            "context_subject": "республика крым",
            "lat": 45.223,
            "lon": 35.205,
            "name": "Кировское",
            "subject": "Республика Крым",
        },
    },
    "ленинский": {
        "московская область": [
            {
                "context_subject": "республика крым",
                "lat": 45.294,
                "lon": 35.769,
                "name": "Ленино",
                "subject": "Республика Крым",
            },
            {
                # «Ленинский район, г.Орск» — внутригородской район г.Орска
                "context_subject": "оренбургская область",
                "lat": 51.2,
                "lon": 58.61667,
                "name": "Орск",
                "subject": "Оренбургская область",
            },
        ],
        "тульская область": {
            "context_subject": "республика крым",
            "lat": 45.294,
            "lon": 35.769,
            "name": "Ленино",
            "subject": "Республика Крым",
        },
    },
    "ленинском": {
        "московская область": [
            {
                "context_subject": "республика крым",
                "lat": 45.294,
                "lon": 35.769,
                "name": "Ленино",
                "subject": "Республика Крым",
            },
            {
                "context_subject": "оренбургская область",
                "lat": 51.2,
                "lon": 58.61667,
                "name": "Орск",
                "subject": "Оренбургская область",
            },
        ],
        "тульская область": {
            "context_subject": "республика крым",
            "lat": 45.294,
            "lon": 35.769,
            "name": "Ленино",
            "subject": "Республика Крым",
        },
    },
    "муром": {
        "владимирская область": {
            "context_subject": "белгородская область",
            "lat": 50.367,
            "lon": 36.833,
            "name": "Муром",
            "subject": "Белгородская область",
        },
    },
    "дмитриевка": {
        "тамбовская область": {
            "context_subject": "белгородская область",
            "lat": 50.433,
            "lon": 36.900,
            "name": "Дмитриевка",
            "subject": "Белгородская область",
        },
    },
    "доброе": {
        "липецкая область": {
            "context_subject": "белгородская область",
            "lat": 50.450,
            "lon": 36.867,
            "name": "Доброе",
            "subject": "Белгородская область",
        },
    },
    "никольское": {
        "орловская область": {
            "context_subject": "калужская область",
            "lat": 54.76,
            "lon": 35.92,
            "name": "Никольское",
            "subject": "Калужская область",
        },
    },
    # --- Crimea/Donbass villages: redirect from any region when context matches ---
    "первомайское": {
        "__any__": {"context_subject": "республика крым", "lat": 45.717, "lon": 33.856, "name": "Первомайское", "subject": "Республика Крым"},
    },
    "калинино": {
        "__any__": [
            {"context_subject": "республика крым", "lat": 45.48, "lon": 33.70, "name": "Калинино", "subject": "Республика Крым"},
            {"context_subject": "донецкая область", "lat": 48.28, "lon": 38.20, "name": "Калинино", "subject": "ДНР"},
        ],
    },
    "братское": {
        "__any__": [
            {"context_subject": "республика крым", "lat": 46.685, "lon": 40.002, "name": "Братское", "subject": "Республика Крым"},
            {"context_subject": "донецкая область", "lat": 48.52, "lon": 38.58, "name": "Братское", "subject": "ДНР"},
        ],
    },
    "новопавловка": {
        "__any__": [
            {"context_subject": "республика крым", "lat": 45.981, "lon": 40.967, "name": "Новопавловка", "subject": "Республика Крым"},
            {"context_subject": "донецкая область", "lat": 48.13, "lon": 37.90, "name": "Новопавловка", "subject": "ДНР"},
        ],
    },
    "высокая": {
        "__any__": {"context_subject": "донецкая область", "text_keyword": "днр", "lat": 48.30, "lon": 38.25, "name": "Высокое", "subject": "ДНР"},
    },
    "пантелеймоновка": {
        "__any__": {"context_subject": "донецкая область", "text_keyword": "пантелеймоновка", "lat": 48.20, "lon": 38.00, "name": "Пантелеймоновка", "subject": "ДНР"},
    },
    "макеевка": {
        "__any__": {"context_subject": "донецкая область", "text_keyword": "макеевка", "lat": 48.05, "lon": 37.97, "name": "Макеевка", "subject": "ДНР"},
    },
    "бобровское": {
        "__any__": {"context_subject": "воронежская область", "text_keyword": "бобровск", "lat": 51.0946, "lon": 40.0333, "name": "Бобров", "subject": "Воронежская область"},
    },
    "терновка": {
        "__any__": {"context_subject": "воронежская область", "text_keyword": "воронежск", "lat": 51.6833, "lon": 41.6333, "name": "Терновка", "subject": "Воронежская область"},
    },
    "панинское": {
        "__any__": {"context_subject": "воронежская область", "text_keyword": "воронежск", "lat": 51.6333, "lon": 40.1333, "name": "Панино", "subject": "Воронежская область"},
    },
    "аркадьевка": {
        "__any__": {"context_subject": "республика крым", "text_keyword": "крым", "lat": 44.85, "lon": 33.55, "name": "Аркадьевка", "subject": "Республика Крым"},
    },
    "родниковое": {
        "__any__": {"context_subject": "республика крым", "text_keyword": "крым", "lat": 45.03, "lon": 33.87, "name": "Родниковое", "subject": "Республика Крым"},
    },
    "заозёрное": {
        "__any__": {"context_subject": "республика крым", "text_keyword": "крым", "lat": 45.19, "lon": 33.65, "name": "Заозёрное", "subject": "Республика Крым"},
    },
    "углегорск": {
        "__any__": {"context_subject": "донецкая область", "text_keyword": "днр", "lat": 48.3178, "lon": 38.2703, "name": "Углегорск", "subject": "ДНР"},
    },
    "сусанино": {
        "__any__": {"context_subject": "республика крым", "text_keyword": "крым", "lat": 45.35, "lon": 34.14, "name": "Сусанино", "subject": "Республика Крым"},
    },
    "виноградово": {
        "__any__": {"context_subject": "республика крым", "text_keyword": "крым", "lat": 45.28, "lon": 34.07, "name": "Виноградово", "subject": "Республика Крым"},
    },
    "чернышево": {
        "__any__": {"context_subject": "республика крым", "lat": 45.776, "lon": 33.524, "name": "Чернышево", "subject": "Республика Крым"},
    },
    "кропоткино": {
        "__any__": {"context_subject": "республика крым", "lat": 45.783, "lon": 33.550, "name": "Кропоткино", "subject": "Республика Крым"},
    },
    "раздольное": {
        "__any__": [
            {"context_subject": "республика крым", "lat": 45.806, "lon": 33.479, "name": "Раздольное", "subject": "Республика Крым"},
            {"context_subject": "донецкая область", "lat": 48.35, "lon": 38.40, "name": "Раздольное", "subject": "ДНР"},
        ],
    },
    "червоное": {
        "__any__": {"context_subject": "республика крым", "lat": 45.663, "lon": 33.880, "name": "Червоное", "subject": "Республика Крым"},
    },
    "ботаническое": {
        "__any__": {"context_subject": "республика крым", "lat": 44.956, "lon": 34.132, "name": "Ботаническое", "subject": "Республика Крым"},
    },
    "сенокосное": {
        "__any__": {"context_subject": "республика крым", "lat": 45.827, "lon": 33.770, "name": "Сенокосное", "subject": "Республика Крым"},
    },
    # Октябрьский — Белгородская (не Уфа)
    "октябрьский": {
        "костромская область": [
            {
                # «Октябрьский район Орска» — внутригородской район г.Орска
                "context_subject": "оренбургская область",
                "lat": 51.2,
                "lon": 58.61667,
                "name": "Орск",
                "subject": "Оренбургская область",
            },
            {"context_subject": "белгородская область", "lat": 50.44, "lon": 36.35, "name": "Октябрьский", "subject": "Белгородская область"},
            {"context_subject": "республика крым", "lat": 45.35, "lon": 36.48, "name": "Октябрьский", "subject": "Республика Крым"},
        ],
        "__any__": [
            {"context_subject": "белгородская область", "lat": 50.44, "lon": 36.35, "name": "Октябрьский", "subject": "Белгородская область"},
            {"context_subject": "республика крым", "lat": 45.35, "lon": 36.48, "name": "Октябрьский", "subject": "Республика Крым"},
        ],
    },
    "октябрьском": {
        "костромская область": [
            {
                "context_subject": "оренбургская область",
                "lat": 51.2,
                "lon": 58.61667,
                "name": "Орск",
                "subject": "Оренбургская область",
            },
            {"context_subject": "белгородская область", "lat": 50.44, "lon": 36.35, "name": "Октябрьский", "subject": "Белгородская область"},
            {"context_subject": "республика крым", "lat": 45.35, "lon": 36.48, "name": "Октябрьский", "subject": "Республика Крым"},
        ],
        "__any__": [
            {"context_subject": "белгородская область", "lat": 50.44, "lon": 36.35, "name": "Октябрьский", "subject": "Белгородская область"},
            {"context_subject": "республика крым", "lat": 45.35, "lon": 36.48, "name": "Октябрьский", "subject": "Республика Крым"},
        ],
    },
    "ждановка": {
        "__any__": [
            {"context_subject": "донецкая область", "lat": 48.25, "lon": 38.40, "name": "Ждановка", "subject": "ДНР"},
            {"context_subject": "республика крым", "lat": 45.35, "lon": 33.80, "name": "Ждановка", "subject": "Республика Крым"},
        ],
    },
    "авдеевка": {
        "__any__": [
            {"context_subject": "донецкая область", "lat": 48.22, "lon": 37.75, "name": "Авдеевка", "subject": "ДНР"},
            {"context_subject": "республика крым", "lat": 45.20, "lon": 33.50, "name": "Авдеевка", "subject": "Республика Крым"},
        ],
    },
    "скопино": {
        "курганская область": {
            "context_subject": "рязанская область",
            "lat": 53.85,
            "lon": 39.55,
            "name": "Скопино",
            "subject": "Рязанская область",
        },
    },
    "луганск": {
        "новосибирская область": {
            "context_subject": "луганская область",
            "text_keyword": "луганск",
            "lat": 48.574,
            "lon": 39.3078,
            "name": "Луганск",
            "subject": "Луганская область",
        },
    },
    "каховка": {
        "амурская область": {
            "context_subject": "херсонская область",
            "lat": 46.80,
            "lon": 33.47,
            "name": "Каховка",
            "subject": "Херсонская область",
        },
    },
    "алешки": {
        "воронежская область": {
            "context_subject": "херсонская область",
            "lat": 46.62,
            "lon": 32.72,
            "name": "Алешки",
            "subject": "Херсонская область",
        },
    },
    "дзержинск": {
        "нижегородская область": {
            "context_subject": "днр",
            "lat": 48.3964,
            "lon": 37.858,
            "name": "Дзержинск",
            "subject": "ДНР",
        },
    },
    "новотроицк": {
        "оренбургская область": {
            "context_subject": "херсонская область",
            "text_keyword": "чаплын",
            "lat": 46.348,
            "lon": 34.325,
            "name": "Новотроицк",
            "subject": "Херсонская область",
        },
        "__any__": {
            "context_subject": "херсонская область",
            "text_keyword": "чаплын",
            "lat": 46.348,
            "lon": 34.325,
            "name": "Новотроицк",
            "subject": "Херсонская область",
        },
    },
    "волово": {
        "липецкая область": {
            "context_subject": "тульская область",
            "text_keyword": "тульская",
            "lat": 53.95,
            "lon": 38.0,
            "name": "Волово",
            "subject": "Тульская область",
        },
    },
    "мантуровский": {
        "костромская область": [
            {
                "context_subject": "курская область",
                "lat": 51.483, "lon": 37.117,
                "name": "Мантурово",
                "subject": "Курская область",
            },
            {
                "context_subject": "воронежская область",
                "lat": 50.494, "lon": 39.733,
                "name": "Мантурово",
                "subject": "Воронежская область",
            },
        ],
    },
    "козловка": {
        "чувашия": {
            "context_subject": "воронежская область",
            "text_keyword": "воронежская",
            "lat": 50.8643,
            "lon": 40.4497,
            "name": "Козловка",
            "subject": "Воронежская область",
        },
    },
    "уразово": {
        "республика башкортостан": {
            "context_subject": "белгородская область",
            "text_keyword": "белгородская",
            "lat": 50.0832,
            "lon": 38.039,
            "name": "Уразово",
            "subject": "Белгородская область",
        },
    },
    "знаменка": {
        "тамбовская область": {
            "context_subject": "орловская область",
            "text_keyword": "орловская",
            "lat": 52.8961,
            "lon": 35.9867,
            "name": "Знаменка",
            "subject": "Орловская область",
        },
    },
    "рыково": {
        "ивановская область": {
            "context_subject": "херсонская область",
            "lat": 46.3318,
            "lon": 34.749,
            "name": "Рыково",
            "subject": "Херсонская область",
        },
    },
    "новоселка": {
        "ярославская область": {
            "context_subject": "донецкая область",
            "text_keyword": "великая",
            "lat": 47.8437,
            "lon": 36.8396,
            "name": "Великая Новоселка",
            "subject": "Донецкая область",
        },
    },
    "михайловка": {
        "волгоградская область": [
            {
                "context_subject": "херсонская область",
                "text_keyword": "херсонская",
                "lat": 47.3133,
                "lon": 33.958,
                "name": "Михайловка",
                "subject": "Херсонская область",
            },
            {
                "context_subject": "воронежская область",
                "lat": 49.891,
                "lon": 39.634,
                "name": "Михайловка",
                "subject": "Воронежская область",
            },
        ],
    },
    "хотьково": {
        "московская область": {
            "context_subject": "орловская область",
            "text_keyword": "орловская",
            "lat": 52.9089,
            "lon": 35.3804,
            "name": "Хотьково",
            "subject": "Орловская область",
        },
    },
    "щегловка": {
        "тамбовская область": {
            "context_subject": "брянская область",
            "text_keyword": "брянская",
            "lat": 52.7955,
            "lon": 34.686,
            "name": "Щегловка",
            "subject": "Брянская область",
        },
    },
    "красное": {
        "липецкая область": {
            "context_subject": "орловская область",
            "text_keyword": "орловская",
            "lat": 52.6205,
            "lon": 35.2717,
            "name": "Красное Знамя",
            "subject": "Орловская область",
        },
    },
    "приморское": {
        "ульяновская область": {
            "context_subject": "запорожская область",
            "text_keyword": "запорожская",
            "lat": 46.73,
            "lon": 36.35,
            "name": "Приморское",
            "subject": "Запорожская область",
        },
    },
    "родники": {
        "ивановская область": {
            "context_subject": "донецкая область",
            "text_keyword": "днр",
            "lat": 48.05,
            "lon": 37.55,
            "name": "Родники",
            "subject": "Донецкая область",
        },
    },
    "чертково": {
        "__any__": {
            "context_subject": "луганская область",
            "text_keyword": "чертково",
            "lat": 49.3833,
            "lon": 40.1500,
            "name": "Чертково",
            "subject": "Ростовская область",
        },
    },
    "сим": {
        "челябинская область": {
            "context_subject": "владимирская область",
            "lat": 56.51,
            "lon": 39.58,
            "name": "Сима",
            "subject": "Владимирская область",
        },
    },
    "малоархангельское": {
        "самарская область": {
            "context_subject": "орловская область",
            "lat": 52.4,
            "lon": 36.5,
            "name": "Малоархангельское",
            "subject": "Орловская область",
        },
    },
    "ростов": {
        "__any__": [
            {
                "context_subject": "ростовская область",
                "lat": 47.24,
                "lon": 39.71,
                "name": "Ростов-на-Дону",
                "subject": "Ростовская область",
            },
            {
                "context_subject": "запорожская область",
                "lat": 47.24,
                "lon": 39.71,
                "name": "Ростов-на-Дону",
                "subject": "Ростовская область",
            },
            {
                "context_subject": "донецкая область",
                "lat": 47.24,
                "lon": 39.71,
                "name": "Ростов-на-Дону",
                "subject": "Ростовская область",
            },
        ],
    },
    "жуков": {
        "калужская область": {
            "context_subject": "брянская область",
            "lat": 53.53,
            "lon": 33.72,
            "name": "Жуков",
            "subject": "Брянская область",
        },
    },
    "жуковский": {
        "калужская область": {
            "context_subject": "брянская область",
            "lat": 53.53,
            "lon": 33.72,
            "name": "Жуков",
            "subject": "Брянская область",
        },
    },
    "кашира": {
        "московская область": {
            "context_subject": "воронежская область",
            "lat": 51.4,
            "lon": 39.583,
            "name": "Кашира",
            "subject": "Воронежская область",
        },
    },
    "каширский": {
        "московская область": {
            "context_subject": "воронежская область",
            "lat": 51.4,
            "lon": 39.583,
            "name": "Каширский район",
            "subject": "Воронежская область",
        },
    },
    "боговарово": {
        "костромская область": {
            "context_subject": "ростовская область",
            "lat": 49.0,
            "lon": 40.5,
            "name": "Боговарово",
            "subject": "Ростовская область",
        },
    },
    "пречистое": {
        "ярославская область": {
            "context_subject": "республика крым",
            "lat": 45.61,
            "lon": 33.82,
            "name": "Пречистое",
            "subject": "Республика Крым",
        },
    },
    "брянское": {
        "__any__": {
            "context_subject": "брянская область",
            "lat": 53.3,
            "lon": 34.3,
            "name": "Брянское",
            "subject": "Брянская область",
        },
    },
    "бетлица": {
        "калужская область": {
            "context_subject": "запорожская область",
            "lat": 47.35,
            "lon": 36.65,
            "name": "Бетлица",
            "subject": "Запорожская область",
        },
    },
    "горожанка": {
        "воронежская область": {
            "context_subject": "брянская область",
            "lat": 52.450,
            "lon": 34.183,
            "name": "Горожанка",
            "subject": "Брянская область",
        },
    },
    "запорожье": {
        "камчатский край": {
            "context_subject": "запорожская область",
            "lat": 47.84,
            "lon": 35.14,
            "name": "Запорожье",
            "subject": "Запорожская область",
        },
    },
    "новороссия": {
        "приморский край": {
            "context_subject": "запорожская область",
            "lat": 47.40,
            "lon": 36.50,
            "name": "Новороссия",
            "subject": "Запорожская область",
        },
    },
    "луч": {
        "воронежская область": {
            "context_subject": "луганская область",
            "lat": 48.33,
            "lon": 38.97,
            "name": "Красный Луч",
            "subject": "Луганская область",
        },
    },
    "аэропорт": {
        "еврейская автономная область": [
            {
                "context_subject": "омская область",
                "lat": 55.0,
                "lon": 73.3,
                "name": "Аэропорт Омск",
                "subject": "Омская область",
            },
        ],
    },
    "николаевск-на-амуре": {
        "хабаровский край": {
            "context_subject": "херсонская область",
            "lat": 46.975,
            "lon": 31.99,
            "name": "Николаев",
            "subject": "Николаевская область",
        },
    },
    "белозерка": {
        "__any__": [
            {
                "context_subject": "запорожская область",
                "text_keyword": "белозерк",
                "lat": 47.21,
                "lon": 34.93,
                "name": "Великая Белозерка",
                "subject": "Запорожская область",
            },
        ],
    },
    "моста": {
        "ивановская область": [
            {
                "context_subject": "республика крым",
                "text_keyword": "крым",
                "lat": 45.33,
                "lon": 36.43,
                "name": "Крымский мост",
                "subject": "Республика Крым",
            },
            {
                "context_subject": "севастополь",
                "lat": 45.33,
                "lon": 36.43,
                "name": "Крымский мост",
                "subject": "Республика Крым",
            },
        ],
    },
    "каменка": {
        "пензенская область": {
            "context_subject": "запорожская область",
            "lat": 47.48,
            "lon": 34.41,
            "name": "Каменка-Днепровская",
            "subject": "Запорожская область",
        },
    },
    "родники": {
        "ивановская область": {
            "context_subject": "ростовская область",
            "lat": 46.66,
            "lon": 40.58,
            "name": "Родники",
            "subject": "Ростовская область",
        },
    },
    "луначарское": {
        "пензенская область": {
            "context_subject": "запорожская область",
            "lat": 47.2,
            "lon": 36.2,
            "name": "Луначарское",
            "subject": "Запорожская область",
        },
    },
    "малая": {
        "вологодская область": {
            "context_subject": "запорожская область",
            "lat": 47.27,
            "lon": 34.97,
            "name": "Малая Белозерка",
            "subject": "Запорожская область",
        },
    },
    "киево": {
        "__any__": {
            "context_subject": "__never__",
            "text_keyword": "киев",
            "lat": 50.45,
            "lon": 30.52,
            "name": "Киев",
            "subject": "Киевская область",
        },
    },
    "волна": {
        "__any__": {
            "context_subject": "краснодарский край",
            "lat": 45.20,
            "lon": 36.70,
            "name": "Волна",
            "subject": "Краснодарский край",
        },
    },
    "волчанск": {
        "свердловская область": {
            "context_subject": "запорожская область",
            "lat": 46.72,
            "lon": 36.35,
            "name": "Волчанск",
            "subject": "Запорожская область",
        },
    },
    "марковка": {
        "оренбургская область": {
            "context_subject": "луганская область",
            "lat": 49.52389,
            "lon": 39.56833,
            "name": "Марковка",
            "subject": "Луганская область",
        },
    },
    "красный": {
        "смоленская область": [
            {
                "context_subject": "луганская область",
                "lat": 48.33,
                "lon": 38.97,
                "name": "Красный",
                "subject": "Луганская область",
            },
            {
                "context_subject": "омская область",
                "lat": 55.05,
                "lon": 73.78,
                "name": "Красный Яр",
                "subject": "Омская область",
            },
        ],
    },
    "красная": {
        "__any__": [
            {
                "context_subject": "республика крым",
                "text_keyword": "крым",
                "lat": 45.47389,
                "lon": 34.12583,
                "name": "Красная Поляна",
                "subject": "Республика Крым",
            },
            {
                "context_subject": "республика крым",
                "text_keyword": "крым",
                "lat": 45.4825,
                "lon": 32.93778,
                "name": "Красная Поляна",
                "subject": "Республика Крым",
            },
        ],
    },
    # гг — госграница: перенаправление на границу указанной области
    "гг": {
        "__any__": [
            {
                "context_subject": "курская область",
                "lat": 51.229707, "lon": 35.116505,
                "name": "гос. граница",
                "subject": "Курская область",
            },
            {
                "context_subject": "белгородская область",
                "lat": 50.4, "lon": 36.6,
                "name": "гос. граница",
                "subject": "Белгородская область",
            },
        ],
    },
    "куйбышевский": {
        "калужская область": [
            {
                "context_subject": "ростовская область",
                "lat": 47.818, "lon": 38.912,
                "name": "Куйбышево",
                "subject": "Ростовская область",
            },
        ],
    },
    "комсомольский": {
        "__any__": {
            "context_subject": "чувашия",
            "lat": 56.75, "lon": 47.42,
            "name": "Комсомольск",
            "subject": "Чувашия",
        },
    },
    "комсомольском": {
        "__any__": {
            "context_subject": "чувашия",
            "lat": 56.75, "lon": 47.42,
            "name": "Комсомольск",
            "subject": "Чувашия",
        },
    },
}

ALL_PATTERNS = []
for entry in REGION_ALIASES:
    items = entry if isinstance(entry, list) else [entry]
    for r in items:
        pat = r["pattern"].replace("ё", "е")
        ALL_PATTERNS.append((len(pat), pat, r))

def get_case_forms(name, is_region=False):
    """Generate common Russian case forms for a place name."""
    forms = [name]
    if is_region:
        return forms
    n = name
    # Feminine names ending in -ка: Петровка → Петровки, Петровке, Петровку
    # Also feminine names ending in -а (not -ка): Москва → Москвы, Москве, Москву
    if n.endswith("ка") and len(n) > 3:
        stem = n[:-1]  # петровк
        forms.append(stem + "и")  # genitive
        forms.append(stem + "е")  # dative/prepositional
        forms.append(stem + "у")  # accusative
    elif n.endswith("а") and len(n) > 2 and not n.endswith("ая"):
        stem = n[:-1]
        # Russian orthography: after г/к/х/ж/ш/ч/щ/ц use "и" instead of "ы"
        if stem and stem[-1] in "гкхжшчщц":
            forms.append(stem + "и")  # genitive
        else:
            forms.append(stem + "ы")  # genitive
        forms.append(stem + "е")  # dative/prepositional
        forms.append(stem + "у")  # accusative
    # Neuter names ending in -но, -во, -ло, -то: Кузьмино → Кузьмина
    for suffix in ("но", "во", "ло", "то", "до", "ко", "со", "зо", "ро", "мо", "по"):
        if n.endswith(suffix) and len(n) > 3:
            stem = n[:-1]
            forms.append(stem + "а")  # genitive
            forms.append(stem + "у")  # dative
            forms.append(stem + "е")  # prepositional
            break
    # Neuter names ending in -ое, -ее: Троицкое → Троицкого. Skip -ом (clashes with rayon names like Яковлевском)
    for suffix in ("ое", "ее"):
        if n.endswith(suffix) and len(n) > 3:
            stem = n[:-2]
            forms.append(stem + "ого")  # genitive
            forms.append(stem + "ому")  # dative
            break
    # Feminine names ending in -ая: Грушевская → Грушевской
    if n.endswith("ая") and len(n) > 3:
        stem = n[:-2]
        forms.append(stem + "ой")  # genitive/dative/instrumental/prepositional
        forms.append(stem + "ую")  # accusative
    # Masculine names ending in consonant: Курск → Курска, Курску, Курске
    if n and n[-1] not in "аеёиоуыэюя":
        if n[-1] == "й":
            stem = n[:-1]
            forms.append(stem + "я")
            forms.append(stem + "ю")
            forms.append(stem + "е")
            forms.append(stem + "ем")
        else:
            forms.append(n + "а")
            forms.append(n + "у")
            forms.append(n + "е")
            forms.append(n + "ом")
            # Also try with fleeting vowel removed (Орёл→Орла, not Орела)
            # Find the last vowel before final consonant cluster
            for _vi in range(len(n) - 2, 0, -1):
                if n[_vi] in "ео":
                    _stem = n[:_vi] + n[_vi+1:]
                    if len(_stem) >= 3:
                        forms.append(_stem + "а")
                        forms.append(_stem + "у")
                        forms.append(_stem + "е")
                        forms.append(_stem + "ом")
                        break
    # Remove duplicates while preserving order
    seen = set()
    result = []
    for f in forms:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result

for name_lower, c in CITY_DB.items():
    pat = name_lower.replace("ё", "е")
    for case_form in get_case_forms(pat, is_region=False):
        ALL_PATTERNS.append((len(case_form), case_form, c))

for name_lower, c in SETTLEMENT_DB.items():
    if name_lower in NON_UNIQUE_SETTLEMENT_NAMES:
        continue
    # Skip common words that match settlement names but aren't location references
    if name_lower in ('восток', 'запад', 'север', 'юг',
                       'северо-восток', 'северо-запад', 'юго-восток', 'юго-запад',
                       'мера', 'меры', 'мере', 'меру',
                       'богатырь', 'богатырьа', 'богатырьу', 'богатырье', 'богатырьом',
                       'крымский', 'крымския', 'крымскию', 'крымские', 'крымскием',
                       'центральный', 'центральныя', 'центральныю', 'центральные', 'центральныем',
                        'суда', 'черное', 'чёрное',
                        'или',
                        'дай', 'дайте', 'даю', 'дают'):
        continue
    pat = name_lower.replace("ё", "е")
    for case_form in get_case_forms(pat):
        ALL_PATTERNS.append((len(case_form), case_form, c))

ALL_PATTERNS.sort(key=lambda x: -x[0])

# Префиксы паттернов (до 3 символов) для быстрого предфильтра в extract_locations:
# паттерн может совпасть, только если его первые символы присутствуют в тексте
# как n-грамма (1-3 символа). Порядок итерации ALL_PATTERNS не меняется.
ALL_PATTERNS_PREFIX = [p[:3] if len(p) >= 3 else p for _, p, _ in ALL_PATTERNS]

# Build reverse lookup: rayon adjective form → correct city data
# Maps "борисовском" → {"name": "Борисовка", "lat": 50.6, "lon": 36.017, "subject": "Белгородская область"}
RAYON_ADJ_TO_CITY = {}
_rayon_suffixes = [' район', ' районе', ' р-н', ' р-не']
for _, pattern, entry in ALL_PATTERNS:
    for rs in _rayon_suffixes:
        if pattern.endswith(rs):
            adj_form = pattern[:-len(rs)]
            RAYON_ADJ_TO_CITY[adj_form] = {
                "name": entry["name"],
                "lat": entry["lat"],
                "lon": entry["lon"],
                "subject": entry["subject"],
            }
            break

# Pre-filtered list of oblast/krai/republic/okrug-level is_region patterns
# for get_mentioned_region_subjects — avoids scanning all 173k patterns per post.
REGION_MENTION_PATTERNS = []
for _, _, entry in ALL_PATTERNS:
    if not entry.get("is_region"):
        continue
    p = entry["pattern"].lower()
    if not any(kw in p for kw in ('область', 'области', 'областью', 'областей',
                                   'край', 'края', 'краем', 'краю',
                                   'республик', 'республика', 'республику',
                                   'округ', 'округе',
                                   'автономный', 'автономная')):
        continue
    REGION_MENTION_PATTERNS.append((p, entry["subject"].strip().lower()))

# Combined regex for non-unique settlement names (matched only when region context resolves them)
if NON_UNIQUE_SETTLEMENT_NAMES:
    _non_unique_patterns = []
    _non_unique_to_lk = {}
    for lk in sorted(NON_UNIQUE_SETTLEMENT_NAMES, key=len, reverse=True):
        for case_form in get_case_forms(lk):
            _non_unique_patterns.append(re.escape(case_form))
            _non_unique_to_lk[case_form] = lk
    NON_UNIQUE_SETTLEMENT_RE = re.compile(r'(?<!\w)(' + '|'.join(_non_unique_patterns) + r')(?!\w)')
    _NON_UNIQUE_TO_LK = _non_unique_to_lk
else:
    NON_UNIQUE_SETTLEMENT_RE = None
    _NON_UNIQUE_TO_LK = {}

from datetime import datetime, timezone, timedelta


HOURS_FILTER = 4
HISTORY_HOURS = 24
HISTORY_FETCH_HOURS = 24
DISPLAY_HOURS = {'rocket': 1, 'danger': 4, 'aviation': 2, 'attention': 4, 'sighting': 3, 'interception': 3, 'clear': 4, 'info': 4}

RADARMAP_API_URL = "https://radar-map.ru/api/state"

CHANNELS = [
    {"url": "https://t.me/s/locatorru", "name": "locatorru", "priority": 1},
    {"url": "https://t.me/s/vrv_radar", "name": "vrv_radar", "priority": 1},

    {"url": "https://t.me/s/radarrussiia", "name": "radarrussiia", "priority": 2},
    {"url": "https://t.me/s/radarYR", "name": "radarYR", "priority": 2},
    # {"url": "https://t.me/s/russiamonitoring_radar_bpla", "name": "russiamonitoring_radar_bpla"},
    {"url": "https://t.me/s/radar_rossia_bpla", "name": "radar_rossia_bpla", "priority": 2},
    {"url": "https://t.me/s/radar_yaroslavl", "name": "radar_yaroslavl", "priority": 2},
    {"url": "https://t.me/s/radar_yar76", "name": "radar_yar76", "priority": 2},
    {"url": "https://t.me/s/radarr_yar", "name": "radarr_yar", "priority": 2},
    {"url": "https://t.me/s/radar_rossii_rossii", "name": "radar_rossii_rossii", "priority": 2},
    # {"url": "https://t.me/s/ivanovo_radar", "name": "ivanovo_radar", "priority": 2},
    {"url": "https://t.me/s/RDFradar", "name": "RDFradar", "priority": 2},
    # {"url": "https://t.me/s/LPRalarm", "name": "LPRalarm", "priority": 2},
    # {"url": "https://t.me/s/lpr1_treugolnik", "name": "lpr1_treugolnik", "priority": 2},

    # {"url": "https://t.me/s/radar_russia_monitor", "name": "radar_russia_monitor", "priority": 2},
]

CHANNEL_PRIORITY = {ch["name"]: ch.get("priority", 2) for ch in CHANNELS}


def clean_message_text(raw, channel=""):
    clean = raw.replace('<br>', '\n').replace('<br/>', '\n')
    clean = re.sub(r'<[^>]+>', ' ', clean).strip()
    clean = html_module.unescape(clean)
    clean = re.sub(r'\s+', ' ', clean)
    clean = re.split(r'📡', clean)[0].strip()
    clean = re.sub(r'@locatorru.*$', '', clean).strip()
    clean = re.sub(r'@locator_ru.*$', '', clean).strip()
    clean = re.sub(r'@vrv_radar.*$', '', clean).strip()
    clean = re.sub(r'@vrv_support.*$', '', clean).strip()
    clean = re.sub(r'@radarrussia.*$', '', clean).strip()
    clean = re.sub(r'@radarrussiia.*$', '', clean).strip()
    clean = re.sub(r'@radarYR.*$', '', clean).strip()
    clean = re.sub(r'@russiamonitoring_radar_bpla.*$', '', clean).strip()
    clean = re.sub(r'@radar_rossia_bpla.*$', '', clean).strip()
    clean = re.sub(r'@radar_yaroslavl.*$', '', clean).strip()
    clean = re.sub(r'@radar_yar76.*$', '', clean).strip()
    clean = re.sub(r'@radarr_yar.*$', '', clean).strip()
    clean = re.sub(r'@radar_rossii_rossii.*$', '', clean).strip()
    clean = re.sub(r'@migalka_alerts_bot.*$', '', clean).strip()
    clean = re.sub(r'@radar_russia_monitor.*$', '', clean).strip()
    clean = re.sub(r'Радар по всей России[^\n]*', '', clean).strip()
    clean = re.sub(r'🔎[^\n]*Радар[^\n]*Россия[^\n]*', '', clean).strip()
    clean = re.sub(r'мониторинг\.ру.*', '', clean).strip()
    clean = re.sub(r'Мониторинг\.РФ.*', '', clean).strip()
    clean = re.sub(r'мониторинг\.рф.*', '', clean).strip()
    clean = re.sub(r'Радар\.РФ\s*[-–—]\s*radar\.RF', '', clean).strip()
    clean = re.sub(r'Радар Ярославль\s*[-–—]\s*', '', clean).strip()
    clean = re.sub(r'Радар Чувашия\s*[-–—]\s*', '', clean).strip()
    clean = re.sub(r'Радар Ярославская область\s*[-–—]\s*', '', clean).strip()
    clean = re.sub(r'Подписаться', '', clean).strip()
    clean = re.sub(r'[^\x20-\x7E\u0400-\u04FF\u0500-\u052F.,!?\-:;()ё№«»]+', ' ', clean)
    clean = re.sub(r'Мы в MAX.*', '', clean).strip()
    # Insert space between lowercase-uppercase Cyrillic transitions (no-space formatting)
    clean = re.sub(r'([а-яё])([А-ЯЁ])', r'\1 \2', clean)
    return clean.strip()


def fetch_channel(url, name, hours_filter=None):
    hours = hours_filter if hours_filter is not None else HOURS_FILTER
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    posts = []
    seen_ids = set()
    before = None

    for page in range(20):
        page_url = url + (f"?before={before}" if before else "")
        try:
            r = requests.get(page_url, timeout=20, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            })
            r.raise_for_status()
            html = r.text
        except Exception:
            break

        if "tgme_widget_message_text" not in html:
            break

        # Extract message wraps with data-post and time
        wraps = re.findall(
            r'<div class="tgme_widget_message[^"]*"[^>]*data-post="([^"]*)"[^>]*>.*?'
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>.*?'
            r'<time datetime="([^"]+)"',
            html, re.DOTALL
        )

        page_posts = 0
        oldest_id = None
        for post_id, msg_html, time_str in wraps:
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            oldest_id = post_id
            try:
                dt = datetime.fromisoformat(time_str)
            except ValueError:
                continue
            if dt < cutoff:
                continue
            clean = clean_message_text(msg_html, name)
            # Create display version: preserve <br> as newlines, strip other HTML, remove noise
            display = msg_html.replace('<br>', '\n').replace('<br/>', '\n')
            display = re.sub(r'<[^>]+>', ' ', display)
            display = html_module.unescape(display)
            display = re.sub(r'\s*\n\s*', '\n', display).strip()
            display = re.sub(r'@\w+\s*', '', display).strip()
            display = re.sub(r'@ \w+\s*', '', display).strip()
            display = re.sub(r'Подписаться', '', display).strip()
            # Remove known footer text (inline-safe: no leading .*, matches from keyword to end of line)
            display = re.sub(r'Локатор России[^\n]*', '', display).strip()
            display = re.sub(r'Радар Ярославль[^\n]*', '', display).strip()
            display = re.sub(r'Радар Ярославск[^\n]*', '', display).strip()
            display = re.sub(r'Радар Чувашия[^\n]*', '', display).strip()
            display = re.sub(r'Обход белых списков[^\n]*', '', display).strip()
            display = re.sub(r'Радар по всей России[^\n]*', '', display).strip()
            display = re.sub(r'Мониторинг\.РФ[^\n]*', '', display).strip()
            display = re.sub(r'мониторинг\.ру[^\n]*', '', display).strip()
            display = re.sub(r'мониторинг\.рф[^\n]*', '', display).strip()
            display = re.sub(r'Мы в MAX[^\n]*', '', display).strip()
            display = re.sub(r'Радар\.РФ[^\n]*', '', display).strip()
            display = re.sub(r'radar\.RF[^\n]*', '', display).strip()
            display = re.sub(r'🔎[^\n]*Радар[^\n]*Россия[^\n]*', '', display).strip()
            display = re.sub(r'&#x[0-9a-fA-F]+;', '', display)
            display = re.sub(r'&#\d+;', '', display)
            display = display.replace('📡', '').replace('🛰', '').replace('⚡', '').replace('🔔', '')
            display = re.sub(r'[\U0001F300-\U0001F9FF\u2600-\u27BF\uFE00-\uFE0F\u200D]+', '', display).strip()
            if clean and len(clean) > 10:
                posts.append((clean, display, name, dt))
                page_posts += 1

        if page_posts == 0 or oldest_id is None:
            break

        # Prepare next page from the oldest post on this page
        parts = oldest_id.split("/")
        if len(parts) == 2:
            before = int(parts[1])
        else:
            break

    if posts:
        print(f"  {name}: {len(posts)} постов")
    return posts


def fetch_radarmap_api(hours_filter=None):
    """Fetch recent messages from radar-map.ru API."""
    hours = hours_filter if hours_filter is not None else HOURS_FILTER
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        r = requests.get(RADARMAP_API_URL, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        r.raise_for_status()
        data = r.json()
    except Exception:
        print("  radar-map.ru API: ошибка загрузки")
        return []

    # Build source_id -> label map
    source_labels = {}
    for s in data.get("sources", []):
        source_labels[s["id"]] = s.get("label", s["id"])

    recent = data.get("recent_by_source", {})
    posts = []
    for src_id, msgs in recent.items():
        label = source_labels.get(src_id, src_id)
        for msg in msgs:
            ts = msg.get("ts")
            if not ts:
                continue
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            if dt < cutoff:
                continue
            text = msg.get("text", "").strip()
            if not text or len(text) < 5:
                continue
            posts.append((text, label, dt))
    if posts:
        print(f"  radar-map.ru ({len(recent)} источников): {len(posts)} постов")
    return posts


def fetch_all(hours_filter=None):
    window = hours_filter if hours_filter is not None else HOURS_FILTER
    print(f"Загрузка постов из Telegram (окно {window}ч)...")
    all_posts = []
    for ch in CHANNELS:
        posts = fetch_channel(ch["url"], ch["name"], hours_filter)
        all_posts.extend(posts)
    api_posts = fetch_radarmap_api(hours_filter)
    all_posts.extend(api_posts)
    print(f"Всего загружено: {len(all_posts)} постов")
    return all_posts

WORD_CHARS = set("abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz0123456789абвгдеёжзийклмнопрстуфхцчшщъыьэюя")


def is_word_boundary(text, idx):
    if idx <= 0:
        return True
    return text[idx - 1] not in WORD_CHARS


# ── Контекстный гейтинг топонимов ─────────────────────────────────────
# Частотные русские слова, которые в постах про БПЛА никогда не являются
# топонимами. Если базовое имя села/города или совпавшая форма входит в
# этот набор — матч подавляется независимо от контекста (кроме is_region).
# См. docs/superpowers/specs/2026-08-01-context-gating-design.md.
COMMON_RUSSIAN_WORDS = frozenset({
    # союзы / частицы / вводные
    "и", "а", "но", "или", "либо", "то", "не", "ни", "же", "ли", "бы", "да",
    "ну", "вот", "только", "просто", "тоже", "также", "еще", "ещё", "даже",
    "уже", "сразу", "вместе", "опять", "снова", "тут", "там", "здесь", "тогда",
    "потом", "сейчас", "теперь", "когда", "если", "чтобы", "потому", "поэтому",
    "зато", "хотя", "как", "так", "словно", "будто", "пусть", "вообще", "впрочем",
    "именно", "лишь", "вовсе", "разве", "неужели", "вряд", "почти", "очень",
    "совсем", "более", "менее", "наиболее", "наименее",
    # предлоги
    "в", "во", "на", "за", "из", "со", "с", "к", "у", "от", "до", "по", "под",
    "над", "о", "об", "при", "без", "для", "через", "сквозь", "между", "около",
    "вокруг", "возле", "мимо", "против", "кроме", "вместо", "после", "перед",
    "среди", "насчет", "вроде", "напротив", "внутри", "снаружи", "из-за",
    "из-под", "благодаря", "относительно", "включая", "исключая", "вплоть",
    "впереди", "позади", "рядом", "вблизи", "вдоль",
    # местоимения
    "я", "ты", "он", "она", "оно", "мы", "вы", "они", "меня", "тебя", "него",
    "неё", "нее", "нас", "вас", "ним", "ними", "мой", "моя", "моё", "мое",
    "мои", "твой", "твоя", "твоё", "твое", "твои", "наш", "наша", "наше",
    "наши", "ваш", "ваша", "ваше", "ваши", "вашу", "вашему", "вашим", "их",
    "свой", "своя", "своё", "свое", "свои", "себя", "сам", "сама", "само",
    "сами", "самый", "самая", "самые", "кто", "что", "кого", "кому", "чего",
    "чему", "чей", "чья", "чьё", "чье", "чьи", "этот", "эта", "это", "эти",
    "этого", "этому", "этой", "этих", "этим", "тот", "та", "те", "того", "тому",
    "весь", "вся", "всё", "все", "всего", "всей", "всех", "всем", "каждый",
    "каждая", "каждое", "каждые", "любой", "любая", "любое", "любые", "такое",
    "такая", "такой", "такие", "таких", "другой", "другие", "другого", "других",
    "иной", "иные", "иных", "никакой", "никакие", "ничто", "ничего", "никто",
    "что-то", "кто-то", "какой-то", "кое-что", "некий", "некие", "некоторые",
    # числительные / количество
    "один", "одна", "одно", "одни", "два", "две", "три", "четыре", "пять",
    "шесть", "семь", "восемь", "девять", "десять", "двадцать", "тридцать",
    "сорок", "пятьдесят", "сто", "тысяча", "тысячи", "несколько", "много",
    "мало", "немного", "немало", "больше", "меньше", "пара", "пары", "раз",
    "раза", "разы", "разов",
    # порядковые числительные: села «Второй» (Воронежская), «Девятое»
    # (Смоленская), «Десятое» (Тверская) матчатся как обычные слова
    # («один и второй», «первый этаж»). Составные имена («Второе Никольское»)
    # матчатся полным спаном и остаются.
    "первый", "первая", "первое", "первые", "первого", "первой", "первых",
    "первым", "первом", "второй", "вторая", "второе", "вторые", "второго",
    "второй", "вторых", "вторым", "втором", "третий", "третья", "третье",
    "третьи", "третьего", "третьей", "третьих", "третьим", "третьем",
    "четвертый", "четвёртый", "четвертая", "четвёртая", "четвертое",
    "четвёртое", "четвертые", "четвёртые", "четвертого", "четвёртого",
    "четвертой", "четвёртой", "четвертых", "четвёртых", "четвертым",
    "четвёртым", "четвертом", "четвёртом", "пятый", "пятая", "пятое",
    "пятые", "пятого", "пятой", "пятых", "пятым", "пятом", "шестой",
    "шестая", "шестое", "шестые", "шестого", "шестой", "шестых", "шестым",
    "шестом", "седьмой", "седьмая", "седьмое", "седьмые", "седьмого",
    "седьмой", "седьмых", "седьмым", "седьмом", "восьмой", "восьмая",
    "восьмое", "восьмые", "восьмого", "восьмой", "восьмых", "восьмым",
    "восьмом", "девятый", "девятая", "девятое", "девятые", "девятого",
    "девятой", "девятых", "девятым", "девятом", "десятый", "десятая",
    "десятое", "десятые", "десятого", "десятой", "десятых", "десятым",
    "десятом",
    # время
    "час", "часа", "часов", "сутка", "сутки", "суток", "сутке", "сутку",
    "минута", "минуты", "минут", "секунда", "секунды", "секунд", "день", "дня",
    "дней", "неделя", "недели", "недель", "месяц", "месяца", "месяцев", "год",
    "года", "лет", "время", "времена", "момент", "пора", "сегодня", "вчера",
    "завтра", "ночью", "утром", "вечером", "днём", "днем", "утро", "вечер",
    "ночь", "ночи",
    # известные ложные совпадения из постов
    "кой", "мирный", "мирная", "мирное", "республика", "республики", "рай",
    "рае", "голубой", "голубое", "голубого", "голубую", "мост", "моста",
    "мосту", "мостом", "мосты", "мостов", "суш", "суша", "суши", "суше", "сушу",
    # "рядом"/"зоне" → села Ряд (Тверская) и Зон (Удмуртия): частотные слова
    "ряд", "ряда", "ряду", "ряде", "рядом", "зон", "зона", "зоны", "зоне",
    "зону",
    # "смена" → село Смена (МО/Ярославская/Рязанская): «смена курса» частотно
    "смена", "смены", "смене", "смену", "сменой",
    # "были" → село Были (Кировская): «были фиксации» — глагол «быть»
    "был", "была", "было", "были", "буду", "будешь", "будет", "будем",
    "будете", "будут", "будь", "будьте", "быть",
    # родовые слова / объекты инфраструктуры
    "село", "села", "селу", "селом", "деревня", "деревни", "деревню", "улица",
    "улицы", "улицу", "площадь", "площади", "площадью", "аэропорт", "аэропорта",
    "шоссе", "трасса", "трассы", "дорога", "дороги", "дорогу", "дорогой",
    "станция", "станции", "вокзал", "вокзала", "центр", "центра", "центре",
    "поселок", "поселка", "поселке", "город", "города", "городе", "городок",
    "район", "района", "районе", "районы", "району", "районом", "область",
    "области", "областей", "областью", "край", "края", "краем", "краю",
    # "округ"/"округа" → село Округа (Кировская): «в городском округе Домодедово»,
    # «округ/округа» — административная единица, не топоним (is_region не затрагивается)
    "округ", "округа", "округу", "округом", "округе", "округи", "округов",
    "округам", "округами", "округах", "округой", "округою",
    # природа (в текстах чаще бытовое слово, чем топоним)
    "лес", "леса", "лесу", "поле", "поля", "полю", "берег", "берега", "остров",
    "острова", "гора", "горы", "луг", "луга", "болото", "болота", "ручей",
    "ручья", "речка", "речки", "река", "реки", "реку", "бор", "бора", "вяз",
    "яма", "ям", "дол", "долина", "долины", "гай", "верх", "низ", "низко",
    "низкий", "низкая", "низкое", "низкие", "нижний", "нижняя", "нижнее",
    "нижние", "озеро",
    "озера", "пруд", "пруда", "море", "моря", "залив", "залива", "пролив",
    "пролива", "бухта", "бухты", "мыс", "мыса",
    # "побережье" → село Побережье (Брянская): «на Черноморское побережье» — берег моря
    "побережье", "побережья", "побережью", "побережьем", "побережий",
    "побережьям", "побережьями", "побережьях",
    # лексика постов про БПЛА
    "бпла", "беспилотник", "беспилотника", "беспилотники", "беспилотников",
    "фиксация", "фиксации", "фиксацию", "опасность", "внимание", "отбой",
    "пролет", "пролёт", "пролеты", "пролёты", "сводка", "сводки", "радар",
    "радары", "мониторинг", "обстановка", "данные", "информация", "работа",
    "движение", "направление", "направления", "направлении", "сторона",
    "стороны", "сторону", "стороне", "тревога", "ракетная", "атака", "атаки",
    "удара", "удар", "удары", "пуск", "пуски", "запуск", "запуски", "перехват",
    "перехвата", "падение", "падения", "поиск", "поиска", "воздушная",
    "воздушный", "воздушного", "летит", "летят", "летела", "летели", "движется",
    "движутся", "направляется", "направляются", "следует", "следуют", "замечен",
    "замечены", "зафиксирован", "зафиксирована", "зафиксированы", "обнаружен",
    "обнаружены", "уничтожен", "уничтожены", "сбит", "сбиты", "перехвачен",
    "перехвачены", "наблюдается", "наблюдаются", "отмечается", "отмечаются",
})
# Авто-стоп-лист из БД: все сёла/города, чьё базовое имя — частотное русское
# слово (например "моста", "голубое", "сутка", "ваша", "рай", "суш", "бор").
# Заменяет ручной COMMON_WORD_MATCHES.
STOPLIST_SETTLEMENTS = frozenset(
    n for n in set(CITY_DB) | set(SETTLEMENT_DB) if n in COMMON_RUSSIAN_WORDS
)

# Слово «море» в падежах: если топоним непосредственно предшествует ему,
# это название моря («Азовское море», «Азовского моря»), а не село
# (Азовское, Республика Крым).
SEA_WORDS = frozenset({'море', 'моря', 'морю', 'морем', 'морях'})

# Пространственные маркеры: матч в теле принимается, если непосредственно
# перед ним стоит такой предлог (или такая пара слов).
_MARKER_SINGLE = frozenset({
    'от', 'из', 'в', 'на', 'к', 'у', 'через', 'до', 'под', 'над', 'с', 'со',
    'за', 'возле', 'около', 'мимо', 'вблизи', 'вокруг', 'при', 'из-за', 'из-под',
})
_MARKER_MULTI = frozenset({
    'в сторону', 'в стороу', 'со стороны', 'в направлении', 'в направление',
    'в районе', 'недалеко от', 'близко к', 'рядом с',
})

# Граница блока локаций (header): первый " - " или статусное слово.
# Всё до неё — список локаций, всё после — тело поста.
_HEADER_END_RE = re.compile(
    r'\s+[-—]\s+|\b(опасность|фиксаци|пролет|пролёт|внимание|отбой|тревога|ракетн)'
)


def _header_end(text_lower):
    m = _HEADER_END_RE.search(text_lower)
    return m.start() if m else len(text_lower)


def _is_common_word_name(r):
    """Общее слово, выступившее как село/город (не регион) — подавляем всегда."""
    if r.get("is_region"):
        return False
    return (r.get("name", "").lower().strip() in STOPLIST_SETTLEMENTS
            or r.get("matched", "").lower().strip() in COMMON_RUSSIAN_WORDS)


def _add_span(spans, r):
    s = r.get("_match_start")
    e = r.get("_match_end")
    if s is not None and e is not None:
        spans.add((s, e))


def _body_spatial_ok(text_lower, start, accepted_spans):
    """Принимаем матч в теле, если перед ним пространственный маркер
    или уже принятый топоним (продолжение списка локаций)."""
    segment = text_lower[max(0, start - 60):start]
    seg_start = start - len(segment)
    toks = [(m.group(), seg_start + m.start(), seg_start + m.end())
            for m in re.finditer(r'\S+', segment)]
    if not toks:
        return False
    prev_tok, ps, pe = toks[-1]
    prev_clean = prev_tok.strip('.,;:!?()[]-«»„“”"\'')
    if prev_clean in _MARKER_SINGLE:
        return True
    if len(toks) >= 2:
        prev2_clean = toks[-2][0].strip('.,;:!?()[]-«»„“”"\'')
        if (prev2_clean + ' ' + prev_clean) in _MARKER_MULTI:
            return True
    # продолжение списка: предыдущий токен — уже принятый топоним
    # (союз "и"/"или" между элементами списка тоже считаем продолжением)
    _span_tokens = [(ps, pe)] + ([(toks[-2][1], toks[-2][2])] if prev_clean in ('и', 'или') and len(toks) >= 2 else [])
    for s, e in accepted_spans:
        if s is None or e is None:
            continue
        for tps, tpe in _span_tokens:
            if s <= tpe and tps <= e:
                return True
    return False


def extract_locations(text, extra_context=None, include_cross_region_nonunique=False):
    text_lower = text.lower().replace("ё", "е")
    # Filter false-positive "суш" (Республика Тыва) from "по суше" / "в суше" phrases
    text_lower = re.sub(r'\b[впо]\s+суше\b', ' СУХОПУТНО ', text_lower)
    WORD_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789абвгдежзийклмнопрстуфхцчшщъыьэюя-")
    matched_spans = set()
    results = []

    # Предфильтр паттернов: паттерн может совпасть, только если его первые
    # символы (1-3) присутствуют в тексте как n-грамма. Пропускаем только
    # заведомо невозможные паттерны — порядок итерации сохраняется.
    _pool = set()
    for _i in range(len(text_lower)):
        _pool.add(text_lower[_i])
        if _i + 1 < len(text_lower):
            _pool.add(text_lower[_i:_i + 2])
        if _i + 2 < len(text_lower):
            _pool.add(text_lower[_i:_i + 3])

    # Pre-compute non-unique compound spans — these MUST override individual
    # word matches to prevent the compound from being blocked in the second pass
    _non_unique_spans = set()
    if NON_UNIQUE_SETTLEMENT_RE:
        for _nu_m in NON_UNIQUE_SETTLEMENT_RE.finditer(text_lower):
            _non_unique_spans.add((_nu_m.start(), _nu_m.end()))

    for _pfx, (_, pattern, entry) in zip(ALL_PATTERNS_PREFIX, ALL_PATTERNS):
        if _pfx not in _pool:
            continue
        if isinstance(entry, dict) and "type" in entry:
            name = entry["name"]
            lat = entry["lat"]
            lon = entry["lon"]
            ftype = entry["type"]
            is_region = entry.get("is_region", False)
        else:
            name = entry["name"]
            lat = entry["lat"]
            lon = entry["lon"]
            ftype = "city"
            is_region = False

        start = 0
        while True:
            idx = text_lower.find(pattern, start)
            if idx == -1:
                break
            end = idx + len(pattern)

            # Require word boundaries
            if idx > 0 and text_lower[idx - 1] in WORD_CHARS:
                start = idx + 1
                continue
            if end < len(text_lower) and text_lower[end] in WORD_CHARS:
                start = idx + 1
                continue
            # Skip if this match is a rayon suffix preceded by a rayon adjective
            # (RAYON_RE handles these better, e.g. "Рузский МО" → RAYON_RE finds Руза)
            if len(pattern) <= 4 and pattern in ('мо', 'го', 'ао'):
                _pre = text_lower[max(0, idx-40):idx].strip()
                if _pre:
                    _prev_word = _pre.split()[-1].strip(",(;")
                    if re.search(r'(ский|ской|цкий|цкой|ском|цком)$', _prev_word):
                        start = idx + 1
                        continue
                # Also skip if followed by a rayon adjective ("МО Спасский" = МО Спасского района)
                _post = text_lower[end:end+20].strip()
                if _post:
                    _next_word = _post.split()[0].strip(",(;")
                    if re.search(r'(ский|ской|цкий|цкой|ском|цком)$', _next_word):
                        start = idx + 1
                        continue
            # Skip if followed by район/ГО/МО/АО (RAYON_RE handles these better)
            # Skip if followed by район/ГО/МО/АО (RAYON_RE handles these better).
            # Compare the FULL following word: "startswith(' мо')" would wrongly
            # match "москва" as the abbreviation "МО" (e.g. "в Троицком АО Москвы").
            # Don't skip if the pattern itself IS a full rayon compound (e.g. "троицкий ао",
            # "войновский го") — the skip is only for standalone adjectives.
            _nx = text_lower[end:end+15]
            _nx_words = _nx.strip().split()
            if _nx_words and _nx_words[0] in ('район', 'районе', 'р-н', 'р-не', 'мо', 'го', 'ао'):
                _pat_last = pattern.strip().split()[-1] if pattern.strip() else ''
                if _pat_last not in ('район', 'районе', 'р-н', 'р-не', 'мо', 'го', 'ао'):
                    start = idx + 1
                    continue
            # Skip if followed by a sea word — "Азовское море"/"Азовского моря"
            # is the sea, not the settlement Азовское (Республика Крым).
            if not is_region and _nx_words and _nx_words[0] in SEA_WORDS:
                start = idx + 1
                continue

            is_overlap = any(
                not (end <= s_start or s_end <= idx)
                for s_start, s_end in matched_spans
            )
            if not is_overlap:
                # Also reject if this span overlaps with a non-unique compound —
                # the compound will be resolved in the second pass with region context
                _nu_overlap = any(
                    not (end <= nu_start or nu_end <= idx)
                    for nu_start, nu_end in _non_unique_spans
                )
                entry_name_lower = name.strip().lower()
                # Also skip when the entry's name is a case form of a non-unique name:
                # e.g. settlement "Кирова" (Ярославская) is a genitive form of the city
                # "Киров" — it must not steal the span from the second-pass resolution
                # (else "от Кирова" wrongly resolves to Ярославская instead of Киров).
                _nu_lk = _NON_UNIQUE_TO_LK.get(entry_name_lower) or entry_name_lower
                if _nu_overlap and _nu_lk in NON_UNIQUE_SETTLEMENT_NAMES and not is_region:
                    start = idx + 1
                    continue
                matched_spans.add((idx, end))
                r = {"name": name, "lat": lat, "lon": lon,
                     "type": ftype, "matched": text[idx:end],
                     "_match_start": idx, "_match_end": end}

                if is_region:
                    r["is_region"] = True
                if isinstance(entry, dict) and "subject" in entry:
                    r["subject"] = entry["subject"]
                elif not is_region and not (isinstance(entry, dict) and "type" in entry):
                    ck = name.lower()
                    if ck in CITY_DB:
                        r["subject"] = CITY_DB[ck]["subject"]
                results.append(r)
                break
            start = idx + 1

    # Dynamic rayon matching: any "Xский/ской/цкой/цкий" + район/МО/ГО forms
    # Handles both nominative and prepositional adjective forms
    RAYON_RE = re.compile(
        r'(?<!\w)([\w-]+?)(ский|ской|цкой|цкий|ском|цком)\s+(район|районе|рае|ре|р-н|р-не|МО|ГО|мо|го|АО|ао)(?!\w)',
        re.IGNORECASE
    )
    # Also match bare adjective forms in district lists (e.g. "Белгородском, Валуйском, ... Чернянском МО")
    # Pattern: adjective in prepositional/nominative followed by comma, "и", or at end
    BARE_RAYON_RE = re.compile(
        r'(?<!\w)([\w-]+?)(ский|ской|цкой|цкий|ском|цком)(?=\s*[,;)\]]|\s+и\s+|$)',
        re.IGNORECASE
    )
    # Collect all rayon matches (both explicit and bare) for cross-region deduction
    rayon_matches = []  # list of (idx, end, stem, suffix, matched_text, is_bare)
    for m in RAYON_RE.finditer(text_lower):
        rayon_matches.append((m.start(), m.end(), m.group(1), m.group(2).lower(), m.group(), False))
    for m in BARE_RAYON_RE.finditer(text_lower):
        # Skip if this span overlaps with an explicit rayon match
        overlap = any(
            not (m.end() <= s_start or s_end <= m.start())
            for s_start, s_end, _, _, _, _ in rayon_matches
        )
        if not overlap:
            rayon_matches.append((m.start(), m.end(), m.group(1), m.group(2).lower(), m.group(), True))

    # Match "ГО/МО + Город" (e.g. "ГО Одинцово", "МО Чехов") — before standalone МО
    MO_GO_PREFIX_RE = re.compile(r'\b(ГО|МО)\s+([А-Я][а-яё\-]+)\b')
    for m in MO_GO_PREFIX_RE.finditer(text):
        _is_overlap = any(
            not (m.end() <= s_start or s_end <= m.start())
            for s_start, s_end in matched_spans
        )
        if _is_overlap:
            continue
        city_name = m.group(2).lower()
        if city_name in CITY_DB:
            matched_spans.add((m.start(), m.end()))
            c = CITY_DB[city_name]
            results.append({
                "name": c["name"], "lat": c["lat"], "lon": c["lon"],
                "type": "region", "matched": text[m.start():m.end()],
                "is_region": True, "subject": c["subject"],
                "_match_start": m.start(), "_match_end": m.end(),
            })

    # Match standalone "МО" (Московская область) — "в МО", "БПЛА в МО"
    # Skip if preceded by a rayon adjective (e.g. "Рузский МО" — handled by RAYON_RE)
    MO_STANDALONE_RE = re.compile(r'\bМО\b')
    for m in MO_STANDALONE_RE.finditer(text_lower):
        _is_overlap = any(
            not (m.end() <= s_start or s_end <= m.start())
            for s_start, s_end in matched_spans
        )
        if _is_overlap:
            continue
        # Skip if "МО" is preceded by a rayon adjective (Рузский/Чернянский/etc)
        _pre = text_lower[max(0, m.start()-40):m.start()].strip()
        if _pre:
            _prev_word = _pre.split()[-1].strip(",(;")
            if re.search(r'(ский|ской|цкий|цкой|ском|цком)$', _prev_word):
                continue
        # Skip if "МО" is followed by a word in CITY_DB (MO_GO_PREFIX_RE should handle it)
        _post = text_lower[m.end():m.end()+40].strip()
        if _post:
            _next_word = _post.split()[0].strip(",(;")
            if _next_word in CITY_DB:
                continue
            # Also skip if followed by a rayon adjective ("МО Спасский" = МО Спасского района)
            if re.search(r'(ский|ской|цкий|цкой|ском|цком)$', _next_word):
                continue
        matched_spans.add((m.start(), m.end()))
        results.append({
            "name": "Москва", "lat": 55.7558, "lon": 37.6173,
            "type": "region", "matched": text[m.start():m.end()],
            "is_region": True, "subject": "Московская область",
            "_match_start": m.start(), "_match_end": m.end(),
        })

    # Process bare adjectives first (they often find a city in CITY_DB),
    # then explicit (МО/ГО) which can use region deduction from earlier matches
    explicit_matches = [m for m in rayon_matches if not m[5]]
    bare_matches = [m for m in rayon_matches if m[5]]
    # Collect region subjects from successful rayon matches for deduction
    rayon_region_subjects = {}  # stem_lower -> subject_lower
    for idx, end, stem, adj_suffix, matched_text, is_bare in bare_matches + explicit_matches:
        # If a rayon match covers a LONGER span starting at same position as an existing
        # ALL_PATTERNS match, the rayon match is more specific — replace the shorter one.
        # But if the rayon span equals an existing span exactly, keep the ALL_PATTERNS
        # result: it is already a precise match (e.g. bare adjective "Курской" already
        # resolves to Курск via "курской" pattern; replacing it would fall back to a
        # CITY_DB prefix guess like "кур" → Курган).
        _remove = set()
        for s_start, s_end in matched_spans:
            if s_start >= idx and s_end <= end and not (s_start == idx and s_end == end):
                _remove.add((s_start, s_end))
        if _remove:
            matched_spans -= _remove
            # Also remove associated results (they'll be replaced by the rayon match)
            results = [r for r in results if (r.get("_match_start"), r.get("_match_end")) not in {(s, e) for s, e in _remove}]
        is_overlap = any(
            not (end <= s_start or s_end <= idx)
            for s_start, s_end in matched_spans
        )
        if is_overlap:
            continue
        adj_suffix = adj_suffix
        # First try RAYON_ADJ_TO_CITY (most accurate — from REGION_ALIASES)
        adj_form = stem + adj_suffix
        adj_city = RAYON_ADJ_TO_CITY.get(adj_form)
        if adj_city:
            # Check consistency with other successful rayon matches
            if rayon_region_subjects:
                majority_subj = max(set(rayon_region_subjects.values()), key=list(rayon_region_subjects.values()).count)
                if adj_city["subject"].lower() != majority_subj:
                    adj_city = None
        if adj_city:
            matched_spans.add((idx, end))
            r = {
                "name": adj_city["name"], "lat": adj_city["lat"], "lon": adj_city["lon"],
                "type": "region", "matched": text[idx:end],
                "is_region": True, "subject": adj_city["subject"],
                "_match_start": idx, "_match_end": end,
            }
            results.append(r)
            rayon_region_subjects[stem] = adj_city["subject"].lower()
            continue
        # Fall back to prefix search in CITY_DB
        city_prefixes = [stem]
        # Try adding back common adjectival suffixes
        if not any(cand.startswith(stem) for cand in CITY_DB):
            city_prefixes.append(stem + "ск")
            city_prefixes.append(stem + "к")
            city_prefixes.append(stem + "ов")
            city_prefixes.append(stem + "ин")
        # For -ском/цком stems, also try stem minus last char (prepositional removes the final consonant)
        if adj_suffix in ('ском', 'цком') and len(stem) > 3:
            city_prefixes.append(stem[:-1])
            city_prefixes.append(stem[:-1] + "ск")
            city_prefixes.append(stem[:-1] + "к")
        # Collect existing region subjects from results to prefer matching region
        _existing_region_subjs = set()
        for r in results:
            if r.get("is_region") and r.get("subject"):
                _existing_region_subjs.add(r["subject"].lower().strip())
        city_key = None
        for prefix in city_prefixes:
            for ck in CITY_DB:
                if ck.startswith(prefix):
                    if _existing_region_subjs:
                        # Prefer city from a region already mentioned in results
                        if CITY_DB[ck]["subject"].lower().strip() in _existing_region_subjs:
                            city_key = ck
                            break
                    else:
                        city_key = ck
                        break
            if city_key:
                break
        # If no match in existing regions, pick the first match anyway
        if city_key is None:
            for prefix in city_prefixes:
                for ck in CITY_DB:
                    if ck.startswith(prefix):
                        city_key = ck
                        break
                if city_key:
                    break
        if city_key is not None:
            # Verify city subject is consistent with other successful rayon matches
            c = CITY_DB[city_key]
            if rayon_region_subjects:
                majority_subj = max(set(rayon_region_subjects.values()), key=list(rayon_region_subjects.values()).count)
                if c["subject"].lower() != majority_subj:
                    # Inconsistent with other rayons — treat as not found
                    city_key = None
        if city_key is None:
            # Fallback: deduce region from other matched rayons + existing region results
            # City-only matches (is_region=False) are excluded to prevent wrong
            # CITY_DB cities (e.g. Новотроицк→Оренбург) from cascading to all rayons
            subj_freq = {}
            for existing in results:
                if not existing.get("is_region"):
                    continue
                esubj = existing.get("subject", "")
                if esubj:
                    subj_lower = esubj.lower()
                    subj_freq[subj_lower] = subj_freq.get(subj_lower, 0) + 1
            # Also count subjects from extra_context (which is already disambiguated)
            # to break ties in favor of the broader context
            if extra_context:
                for existing in extra_context:
                    if existing.get("is_region") and existing.get("subject"):
                        subj_freq[existing["subject"].lower()] = subj_freq.get(existing["subject"].lower(), 0) + 1
            for rstem, rsubj in rayon_region_subjects.items():
                subj_freq[rsubj] = subj_freq.get(rsubj, 0) + 2
            best_subj = max(subj_freq, key=subj_freq.get) if subj_freq else None
            if best_subj:
                matched_spans.add((idx, end))
                fallback_lat, fallback_lon, fallback_name = None, None, None
                for existing in results:
                    if existing.get("subject", "").lower() == best_subj:
                        fallback_lat = existing["lat"]
                        fallback_lon = existing["lon"]
                        fallback_name = existing["name"]
                        break
                if fallback_name is None:
                    for cname, centry in CITY_DB.items():
                        if centry["subject"].lower() == best_subj:
                            fallback_name = centry["name"]
                            fallback_lat = centry["lat"]
                            fallback_lon = centry["lon"]
                            break
                if fallback_name:
                    # Look up proper subject casing from CITY_DB
                    proper_subj = best_subj
                    for centry in CITY_DB.values():
                        if centry["subject"].lower() == best_subj:
                            proper_subj = centry["subject"]
                            break
                    r = {
                        "name": fallback_name, "lat": fallback_lat, "lon": fallback_lon,
                        "type": "region", "matched": text[idx:end],
                        "is_region": True, "subject": proper_subj,
                        "_match_start": idx, "_match_end": end,
                    }
                    results.append(r)
            continue
        c = CITY_DB[city_key]
        matched_spans.add((idx, end))
        r = {
            "name": c["name"], "lat": c["lat"], "lon": c["lon"],
            "type": "region", "matched": text[idx:end],
            "is_region": True, "subject": c["subject"],
            "_match_start": idx, "_match_end": end,
        }
        results.append(r)
        # Record this rayon's subject for deduction of subsequent bare rayons
        rayon_region_subjects[stem] = c["subject"].lower()

    # --- Disambiguation: if a name matched a wrong subject but context
    #     from another result points elsewhere, reassign ---
    for r in results:
        nl = r["name"].lower()
        # Also check by matched text (e.g., "красногвардейский" for rayon patterns)
        matched_key = r.get("matched", "").lower().strip()
        # Strip "район"/"р-н" from matched for key lookup
        for suffix in (" район", " р-н", " районе", " р-не"):
            if matched_key.endswith(suffix):
                matched_key = matched_key[:-len(suffix)]
                break
        for key in (nl, matched_key):
            if key in DISAMBIGUATION_MAP:
                cur_subj = r.get("subject", "").lower()
                candidates = None
                if cur_subj in DISAMBIGUATION_MAP[key]:
                    candidates = DISAMBIGUATION_MAP[key][cur_subj]
                elif "__any__" in DISAMBIGUATION_MAP[key]:
                    candidates = DISAMBIGUATION_MAP[key]["__any__"]
                if candidates is not None:
                    if not isinstance(candidates, list):
                        candidates = [candidates]
                    all_results = results
                    if extra_context:
                        all_results = results + extra_context
                    _found = False
                    for entry in candidates:
                        target = entry["context_subject"]
                        matched = any(r2.get("subject", "").lower() == target for r2 in all_results)
                        if not matched and "text_keyword" in entry:
                            matched = entry["text_keyword"] in text_lower
                        if matched:
                            r["lat"] = entry["lat"]
                            r["lon"] = entry["lon"]
                            r["name"] = entry["name"]
                            r["subject"] = entry["subject"]
                            _found = True
                            break
                    if _found:
                        break

    # --- Automatic context-based subject matching: if a result has fewer
    #     context mentions in its subject than another subject, try to
    #     re-resolve it in the more common subject ---
    all_ctx = results
    if extra_context:
        all_ctx = results + extra_context
    _ctx_subj_counts = {}
    for ctx in all_ctx:
        subj = ctx.get("subject", "").lower().strip()
        if subj:
            _ctx_subj_counts[subj] = _ctx_subj_counts.get(subj, 0) + 1
    if _ctx_subj_counts:
        _max_count = max(_ctx_subj_counts.values())
        _dominant_subjs = {s for s, c in _ctx_subj_counts.items() if c == _max_count}
        for r in results:
            if r.get("is_region"):
                continue
            cur_subj = r.get("subject", "").lower().strip()
            if not cur_subj or cur_subj in _dominant_subjs:
                continue
            if _ctx_subj_counts.get(cur_subj, 0) >= _max_count:
                continue
            for target_subj in _dominant_subjs:
                key = (r["name"].lower(), target_subj)
                if key in CITY_BY_NAME_SUBJECT:
                    correct = CITY_BY_NAME_SUBJECT[key]
                    r["lat"] = correct["lat"]
                    r["lon"] = correct["lon"]
                    r["name"] = correct["name"]
                    r["subject"] = correct["subject"]
                    break
                elif key in SETTLEMENTS_BY_NAME_SUBJECT:
                    correct = SETTLEMENTS_BY_NAME_SUBJECT[key]
                    r["lat"] = correct["lat"]
                    r["lon"] = correct["lon"]
                    r["name"] = correct["name"]
                    r["subject"] = correct["subject"]
                    break

    # --- Region context filtering ---
    # ДНР/ЛНР/Крым context filter
        _ctx_regions = [
            (('донецкая область', 'днр'), ('днр', 'лнр', 'донецк', 'луганск')),
            (('луганская область', 'лнр'), ('лнр', 'луганск')),
            (('республика крым', 'крым'), ('крым',)),
        ]
        for _ctx_subjs, _ctx_kws in _ctx_regions:
            _has_ctx = any(
                r.get('subject', '').lower().strip() in _ctx_subjs
                for r in results
            )
            if _has_ctx and any(kw in text_lower for kw in _ctx_kws):
                _main_subj = _ctx_subjs[0]
                _filtered = []
                for r in results:
                    if r.get('is_region'):
                        _filtered.append(r)
                        continue
                    _rs = r.get('subject', '').lower().strip()
                    if _rs in _ctx_subjs:
                        _filtered.append(r)
                        continue
                    _key = (r['name'].lower(), _main_subj)
                    if _key in CITY_BY_NAME_SUBJECT or _key in SETTLEMENTS_BY_NAME_SUBJECT:
                        _filtered.append(r)
                        continue
                results = _filtered
                break

        # Auto-remove settlement/city results whose region conflicts with
        # region-type mentions (rayon, область/край)
        _region_subjs = set()
        for r in results:
            if r.get("is_region") and r.get("subject"):
                _region_subjs.add(r["subject"].lower().strip())
        if extra_context:
            for r in extra_context:
                if r.get("is_region") and r.get("subject"):
                    _region_subjs.add(r["subject"].lower().strip())
        if _region_subjs:
            _any_region_match = any(
                r.get("subject", "").lower().strip() in _region_subjs
                for r in results
            ) or any(
                not r.get("is_region")
                and r.get("subject", "").lower().strip() in _region_subjs
                for r in (extra_context or [])
            )
            if _any_region_match:
                results = [
                    r for r in results
                    if r.get("is_region")
                    or not r.get("subject")
                    or r["subject"].lower().strip() in _region_subjs
                    or any(
                        rs.endswith(" " + r["subject"].lower().strip())
                        for rs in _region_subjs
                    )
                ]



    # --- Match non-unique settlement names only when region context resolves them ---
    if NON_UNIQUE_SETTLEMENT_RE:
        all_ctx = results
        if extra_context:
            all_ctx = results + extra_context
        # Ordered list: local results first (their region mentions are more
        # authoritative for a settlement in this fragment), then extra_context.
        # A plain set would iterate in arbitrary order and could pick a
        # secondary region ("возможно далее на Воронежскую область") over the
        # rayon-derived one ("Советский район, Курская область").
        ctx_subjects = []
        _seen_subj = set()
        for ctx in all_ctx:
            subj = ctx.get("subject", "").lower().strip()
            if subj and subj not in _seen_subj:
                _seen_subj.add(subj)
                ctx_subjects.append(subj)
        # Normalize short-form subjects (e.g. "лнр" → "луганская область")
        for subj in list(ctx_subjects):
            if subj in REGION_GEOJSON_MAP:
                mapped = REGION_GEOJSON_MAP[subj]
                if mapped not in _seen_subj:
                    _seen_subj.add(mapped)
                    ctx_subjects.append(mapped)
        # If ДНР or ЛНР is in context, ignore all other regions
        dnr_lnr = {'донецкая область', 'луганская область', 'днр', 'лнр'}
        if _seen_subj & dnr_lnr:
            ctx_subjects = [s for s in ctx_subjects if s in dnr_lnr]
        # Even without context subjects, process non-unique names when include_cross_region_nonunique
        # is set (direction extraction needs cross-region matches), or when the name is a major
        # city (CITY_DB) — a namesake village in another region must not drop the city marker.
        if ctx_subjects or include_cross_region_nonunique or NON_UNIQUE_MAJOR_CITIES:
            for m in NON_UNIQUE_SETTLEMENT_RE.finditer(text_lower):
                matched_form = m.group(1)
                lk = _NON_UNIQUE_TO_LK.get(matched_form) or matched_form
                if lk not in NON_UNIQUE_SETTLEMENT_NAMES:
                    continue
                idx, end = m.start(), m.end()
                is_overlap = any(
                    not (end <= s_start or s_end <= idx)
                    for s_start, s_end in matched_spans
                )
                if is_overlap:
                    continue
                # Find the variant matching one of the context subjects
                # Reference coords: rayon-level matches already found in context
                # (e.g. Кшенский from "Советский район") or specific settlements
                # (is_region=False). Oblast capital region matches are NOT used —
                # the capital is usually far from the settlement, e.g. "Петропавловка,
                # Советский район" must pick the Петропавловка near Кшенский, not
                # the one near Курск (which is closer to the oblast capital).
                _refs = []
                for ctx in all_ctx:
                    if ctx.get("lat") is None:
                        continue
                    if ctx.get("is_region"):
                        _mm = str(ctx.get("matched", "")).lower()
                        if not re.search(r'(район|района|районе|районы|р-н|р-не|р-ны|мо|го|ао)$', _mm):
                            continue
                    _refs.append((ctx["lat"], ctx["lon"]))
                entry = None
                for cs in ctx_subjects:
                    key = (lk, cs)
                    _cands = SETTLEMENTS_ALL_BY_KEY.get(key)
                    if _cands:
                        if _refs and len(_cands) > 1:
                            _best = _cands[0]
                            _best_d = None
                            for _cand in _cands:
                                _d = min(
                                    (_cand["lat"] - _rf[0]) ** 2 + (_cand["lon"] - _rf[1]) ** 2
                                    for _rf in _refs
                                )
                                if _best_d is None or _d < _best_d:
                                    _best_d = _d
                                    _best = _cand
                            entry = _best
                        else:
                            entry = _cands[0]
                        break
                    if key in CITY_BY_NAME_SUBJECT:
                        entry = CITY_BY_NAME_SUBJECT[key]
                        break
                if entry is None:
                    if ctx_subjects:
                        if not include_cross_region_nonunique:
                            continue
                        # With known context, only allow CITY_DB cross-region entries
                        if lk in CITY_DB:
                            entry = CITY_DB[lk]
                        if entry is None:
                            continue
                    else:
                        # No context: prefer the major city (CITY_DB) — it is far more
                        # likely than an obscure namesake settlement. Only fall back to a
                        # settlement when cross-region matches are explicitly allowed.
                        if lk in CITY_DB:
                            entry = CITY_DB[lk]
                        elif not include_cross_region_nonunique:
                            continue
                        else:
                            for key, e in SETTLEMENTS_BY_NAME_SUBJECT.items():
                                if key[0] == lk:
                                    entry = e
                                    break
                if entry is None:
                    continue
                matched_spans.add((idx, end))
                r = {
                    "name": entry["name"],
                    "lat": entry["lat"],
                    "lon": entry["lon"],
                    "type": "city",
                    "matched": text[idx:end],
                    "subject": entry["subject"],
                    "_match_start": idx, "_match_end": end,
                }
                results.append(r)

    # --- Контекстный гейтинг (см. docs/superpowers/specs/2026-08-01-context-gating-design.md) ---
    # Порядок приёма матча:
    #   1) is_region / район → всегда (уже отфильтрованы по регионам выше)
    #   2) в блоке локаций (header) → всегда
    #   3) в теле → только рядом пространственный маркер или продолжение списка
    # Общие слова (стоп-лист) подавляются везде, кроме явных регионов.
    header_end = _header_end(text_lower)
    accepted_spans = set()
    gated_ids = set()
    # Решение о приёме матчей принимаем слева направо (для цепочек-списков),
    # но финальный порядок results сохраняем прежним (важно для дедупликации).
    for r in sorted(results, key=lambda _r: _r.get("_match_start") if _r.get("_match_start") is not None else -1):
        if _is_common_word_name(r):
            continue
        if r.get("is_region"):
            gated_ids.add(id(r))
            _add_span(accepted_spans, r)
            continue
        start = r.get("_match_start")
        if start is None:
            gated_ids.add(id(r))
            continue
        if start < header_end:
            gated_ids.add(id(r))
            _add_span(accepted_spans, r)
            continue
        if _body_spatial_ok(text_lower, start, accepted_spans):
            gated_ids.add(id(r))
            _add_span(accepted_spans, r)
    results = [r for r in results if id(r) in gated_ids]

    unique = {}
    found_keys = set()
    for r in results:
        name_key = r["name"].lower()
        has_radius = bool(r.get("is_region"))
        item_key = (name_key, has_radius)
        coord_key = round(r["lat"], 1), round(r["lon"], 1)
        if item_key in found_keys:
            continue
        found_keys.add(item_key)
        unique[(coord_key, has_radius)] = r
    return list(unique.values())


DIRECTION_SEPS = [
    r'\bв сторону\b',
    r'\bв стороу\b',  # typo (missing н): "в стороу Касторное"
    r'\bв вашу сторону\b',
    r'\bв нашу сторону\b',
    r'\bв направлении\b',
    r'\bнаправлении\b',
    r'\bв направление\b',
    r'\bнаправление\b',
    '→', '➡️',
    r'\bот\b',
    r'\bсо стороны\b',
    r'\bс стороны\b',  # typo (missing о)
]


def _alert_region_markers(post_text):
    """Регионы из шапки поста (до ' - ' или статусного слова) — ими указывается
    направление «в вашу/нашу сторону» (регионы оповещения о налёте)."""
    m = re.search(r'\s*[-—]\s*', post_text)
    hdr = post_text[:m.start()] if m else post_text
    return [r for r in extract_locations(hdr) if r.get('is_region')]


# «стык X и Y областей» — фраза, обозначающая точку на границе двух регионов
_STYK_RE = re.compile(
    r'(?:на\s+)?стык[аеи]?\s+(.+?)\s+и\s+(.+?)\s+'
    r'(?:област\w*|кра\w*|республик\w*|округов?\w*|районов?\w*|ао|мо|го)\b',
    re.IGNORECASE
)


def _polygon_vertices(feat):
    """Все вершины границы региона (lat, lon) из GeoJSON-фичи."""
    geom = feat.get('geometry') if feat else None
    if not geom:
        return []
    coords = geom.get('coordinates', [])
    verts = []
    def _walk(c):
        if c and isinstance(c[0], list):
            for sub in c:
                _walk(sub)
        elif len(c) >= 2 and isinstance(c[0], (int, float)):
            verts.append((c[1], c[0]))  # [lon, lat] → (lat, lon)
    _walk(coords)
    return verts


def _make_styk_junction(region_locs, dst_locs, geojson_lookup=None):
    """Точка на границе между регионами из фразы «стык X и Y областей».
    При наличии цели (в сторону Z) берём вершину общей границы, ближайшую
    к цели; без геометрии — середина между координатами маркеров регионов."""
    verts = []
    for l in region_locs:
        v = []
        if geojson_lookup and l.get("subject"):
            feat = find_geojson_feature(l["subject"].lower(), geojson_lookup)
            if feat:
                v = _polygon_vertices(feat)
        verts.append(v)
    if all(v for v in verts):
        shared = [p for p in verts[0]
                  if any(abs(p[0] - q[0]) <= 0.011 and abs(p[1] - q[1]) <= 0.011
                         for q in verts[1])]
        if shared:
            if dst_locs:
                dl = dst_locs[0]
                return min(shared, key=lambda p: (p[0] - dl["lat"]) ** 2 + (p[1] - dl["lon"]) ** 2)
            return (sum(p[0] for p in shared) / len(shared),
                    sum(p[1] for p in shared) / len(shared))
    lats = [l["lat"] for l in region_locs]
    lons = [l["lon"] for l in region_locs]
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def extract_directions(text, geojson_lookup=None):
    """Extract source→destination pairs from posts containing direction phrases.
    Returns list of (source_loc, dest_loc) tuples.
    """
    # Split into sentences. Period must be followed by whitespace AND a capital
    # letter to be a sentence boundary — otherwise "р.Волга"/"г.Москва"
    # abbreviations (period directly followed by a letter) break sentences apart.
    # A period before a single-letter abbreviation ("г.", "р.", "п.") ending the
    # previous sentence is ALSO a boundary: "...областей. г.Ярославль" must not
    # merge with the first sentence (else "г.Ярославль" becomes a drone source).
    sentences = re.split(r'[.!](?=\s+[А-ЯЁA-Z0-9])|[.!](?=\s+[а-яё]\.\s*[А-ЯЁA-Z0-9])|\n+', text)
    pairs = []
    cardinal = {"восток", "запад", "север", "юг", "юго-восток", "юго-запад",
                "северо-восток", "северо-запад"}

    # Pre-check full text for "от X области" — used to suppress false directions
    # when a separator like "→" creates a reversed arrow.
    # "от X области/края/республики" = source of danger, not a direction
    region_words = {'область', 'области', 'областью', 'областей',
                    'край', 'края', 'краем', 'краю',
                    'республик', 'республики', 'республика', 'республику',
                    'район', 'районе', 'района', 'районов', 'районом',
                    'р-н', 'р-не', 'мо', 'го'}
    text_has_ot_region = bool(re.search(
        r'\bот\b\s+\S+\s+(' + '|'.join(region_words) + r')\b',
        text.lower()
    ))

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        text_lower = sentence.lower()
        # Find the first direction separator in this sentence
        split_idx = None
        sep_len = 0
        for pat in DIRECTION_SEPS:
            m = re.search(pat, text_lower)
            if m:
                split_idx = m.start()
                sep_len = len(m.group())
                break

        if split_idx is None:
            continue

        before = sentence[:split_idx].strip()
        after = sentence[split_idx + sep_len:].strip()

        # Skip if after is cardinal direction
        after_lower = after.lower().strip().rstrip(".,!?:;")
        if after_lower in cardinal:
            continue

        from_sep = (text_lower[split_idx:split_idx + sep_len].strip() in ('от', 'со стороны', 'с стороны'))

        if from_sep:
            # "от [число]" = quantifier ("от 7 БПЛА"), not a direction
            first_word = after_lower.split()[0] if after_lower.split() else ''
            if any(c.isdigit() for c in first_word):
                continue
            after_words = after_lower.split()
            if any(w in region_words for w in after_words[:3]):
                continue
            # "со стороны Азовского моря" / "от моря" — источником является море,
            # а не населённый пункт; стрелку не строим (моря нет в БД).
            if any(w in SEA_WORDS for w in after_words[:3]):
                continue
        elif after_lower.startswith('от'):
            # "от X области" after a non-"от" separator (e.g. "→ от Курской области")
            # → real source is after "от", the arrow is misleading.
            rest = after_lower[len('от'):].strip()
            rest_words = rest.split()
            if any(w in region_words for w in rest_words[:3]):
                continue
        elif re.search(r'\bв (вашу|нашу) сторону\b', text_lower):
            # "от X ... в вашу/нашу сторону" — источник после "от",
            # направление указано оборотом «в вашу/нашу сторону», не отсекаем.
            pass
        elif text_has_ot_region:
            # Full post contains "от X области" — this indicates real source.
            # Skip arrow directions from non-"от" separators (e.g. "Липецк → Курская").
            continue

        # Extract locations from full sentence for disambiguation context
        # (so Первомайский район in "before" can see Крым in "after")
        full_context = extract_locations(sentence)
        from_sep = (text_lower[split_idx:split_idx + sep_len].strip() in ('от', 'со стороны', 'с стороны'))
        vashu = bool(re.search(r'\bв (вашу|нашу) сторону\b', text_lower))
        if vashu and not from_sep:
            # "от X ... в вашу/нашу сторону": источник — после "от" (или до
            # разделителя, если «от» нет), цель — регионы оповещения из шапки
            # поста (регионы, куда летят БПЛА).
            ot_m = re.search(r'\bот\b', sentence.lower())
            if ot_m:
                src_text = sentence[ot_m.end():split_idx].strip()
                srcs = extract_locations(src_text, extra_context=full_context, include_cross_region_nonunique=True)
            else:
                srcs = extract_locations(before, extra_context=full_context, include_cross_region_nonunique=True)
            dsts = _alert_region_markers(text)
        elif from_sep:
            # "от X" → source is after "от" (origin), dest is before (target)
            srcs = extract_locations(after, extra_context=full_context, include_cross_region_nonunique=True)
            dsts = extract_locations(before, extra_context=full_context, include_cross_region_nonunique=True)
        else:
            srcs = extract_locations(before, extra_context=full_context, include_cross_region_nonunique=True)
            dsts = extract_locations(after, extra_context=full_context, include_cross_region_nonunique=True)

        # «стык X и Y областей» — единая точка на границе регионов:
        # одна стрелка от стыка к цели вместо стрелок из столиц регионов
        styk_m = _STYK_RE.search(sentence)
        if styk_m:
            styk_text = sentence[styk_m.start():styk_m.end()]
            styk_locs = [l for l in extract_locations(styk_text, extra_context=full_context) if l.get("is_region")]
            if len(styk_locs) >= 2:
                jlat, jlon = _make_styk_junction(styk_locs, dsts, geojson_lookup)
                junction = {
                    "lat": jlat, "lon": jlon,
                    "name": styk_text, "matched": styk_text,
                    "is_region": True, "type": "region",
                    "_match_start": styk_m.start(), "_match_end": styk_m.end(),
                }
                # Регионы стыка остаются как fill-only маркеры (заливка регионов),
                # а стрелку рисуем только от точки стыка
                srcs = [junction] + [{**l, "_fill_only": True} for l in styk_locs]

        for s in srcs:
            for d in dsts:
                if round(s["lat"], 1) == round(d["lat"], 1) and round(s["lon"], 1) == round(d["lon"], 1):
                    continue
                pairs.append((s, d))

    # --- Handle "тыл"/"тыловые" (rear/hinterland) markers ---
    # When a post mentions UAVs flying into rear regions, draw a short arrow
    # from each found location towards Moscow Oblast.
    if not pairs and re.search(r'(?<!без )тыл', text.lower()):
        MOSCOW_LAT, MOSCOW_LON = 55.7558, 37.6173
        ARROW_DEG = 0.5  # ~55 km at 55°N
        for loc in extract_locations(text):
            # Skip only explicitly named regions ("Брянская область", "Курск" etc.)
            # but keep rayon-derived locations ("Хомутовский район" → Хомутовка)
            if loc.get("is_region") and not loc.get("matched", "").lower().endswith((" район", " р-н")):
                continue
            dx = MOSCOW_LON - loc["lon"]
            dy = MOSCOW_LAT - loc["lat"]
            dist_sq = dx*dx + dy*dy
            if dist_sq < 0.0001:
                continue
            scale = ARROW_DEG / (dist_sq ** 0.5)
            dest = {
                "lat": loc["lat"] + dy * scale,
                "lon": loc["lon"] + dx * scale,
                "name": "тыловые регионы",
                "subject": "Московская область",
            }
            pairs.append((loc, dest))

    return pairs


def classify_post(text):
    text_lower = text.lower()
    if "cloudtips" in text_lower or "обращение к жителям следующих регионов" in text_lower:
        return "info"
    elif "отбой" in text_lower or "по обстановке тихо" in text_lower:
        return "clear"
    elif "ракетн" in text_lower:
        return "rocket"
    elif "уничтожен" in text_lower or "сбит" in text_lower or "перехват" in text_lower or "пво" in text_lower:
        return "interception"
    elif "отражени" in text_lower:
        return "interception"
    elif "авиацион" in text_lower and "бпла" not in text_lower and "беспилот" not in text_lower:
        return "aviation"
    elif "аэропорт" in text_lower and ("временные ограничения" in text_lower or "ограничения на прием" in text_lower):
        return "info"
    elif "лепестк" in text_lower or "на заметку" in text_lower:
        return "info"
    elif "меры безопасности" in text_lower or "пуск" in text_lower or "опасность" in text_lower or "тревога" in text_lower or ("угроз" in text_lower and "в случае" not in text_lower):
        return "danger"
    elif "фиксаци" in text_lower and "не наблюда" in text_lower:
        return "clear"
    elif ("на карте" in text_lower or "в прямом эфире" in text_lower) and ("сайт" in text_lower or "присылай" in text_lower or "показывающ" in text_lower):
        return "info"
    elif "фиксаци" in text_lower or "пролёт" in text_lower or "пролет" in text_lower or "группа" in text_lower:
        return "sighting"
    elif "внимание" in text_lower:
        return "attention"
    elif "бпла" in text_lower or "беспилотн" in text_lower:
        return "sighting"
    return "info"


# ── GeoJSON region boundaries ──────────────────────────────────────────
GEOJSON_URL = 'https://raw.githubusercontent.com/Hubbitus/RussiaRegions.geojson/master/RussiaRegions.geojson'


def simplify_coords(coords, precision=2):
    if isinstance(coords[0], list):
        if isinstance(coords[0][0], list):
            return [simplify_coords(c, precision) for c in coords]
        else:
            return [[round(x, precision), round(y, precision)] for x, y in coords]
    return coords


def load_region_geojson():
    """Download and simplify GeoJSON, return dict name_lower→feature."""
    lookup = {}
    try:
        r = requests.get(GEOJSON_URL, timeout=60)
        data = r.json()
    except Exception:
        print("  Не удалось загрузить GeoJSON регионов — используем статические полигоны")
    else:
        for f in data['features']:
            name = f['properties'].get('NAME', '').strip()
            if not name:
                continue
            geom = f['geometry']
            if geom['type'] == 'MultiPolygon':
                geom['coordinates'] = simplify_coords(geom['coordinates'], 2)
            elif geom['type'] == 'Polygon':
                geom['coordinates'] = simplify_coords(geom['coordinates'], 2)
            else:
                continue
            lookup[name.lower()] = {
                'type': 'Feature',
                'properties': {'NAME': name},
                'geometry': {'type': geom['type'], 'coordinates': geom['coordinates']}
            }
        print(f"  Загружено {len(lookup)} регионов из GeoJSON")
    # Always add static polygons — fills gaps (disputed territories) and covers upstream failure
    for name_lower, feat in STATIC_GEOJSON_FEATURES.items():
        if name_lower not in lookup:
            lookup[name_lower] = feat
    if STATIC_GEOJSON_FEATURES:
        print(f"  Всего регионов: {len(lookup)} (включая статические)")
    return lookup


# Simplified polygons for regions not in the standard Russia GeoJSON
STATIC_GEOJSON_FEATURES = {
    'республика крым': {
        'type': 'Feature',
        'properties': {'NAME': 'Республика Крым'},
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[
                [33.5, 46.2], [34.5, 46.2], [35.0, 45.8],
                [35.5, 45.5], [36.5, 45.3], [36.5, 45.0],
                [36.0, 44.8], [35.5, 44.5], [34.0, 44.4],
                [33.5, 44.5], [33.0, 44.8], [32.5, 45.3],
                [32.5, 45.8], [33.0, 46.0], [33.5, 46.2],
            ]]
        }
    },
    'севастополь': {
        'type': 'Feature',
        'properties': {'NAME': 'Севастополь'},
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[
                [33.3, 44.5], [33.7, 44.5], [33.7, 44.6],
                [33.3, 44.6], [33.3, 44.5],
            ]]
        }
    },
    'донецкая область': {
        'type': 'Feature',
        'properties': {'NAME': 'Донецкая область'},
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[
                [36.5, 48.5], [38.5, 48.5], [39.0, 48.0],
                [39.0, 47.5], [38.5, 47.0], [37.5, 46.8],
                [37.0, 47.0], [36.5, 47.2], [36.5, 48.5],
            ]]
        }
    },
    'луганская область': {
        'type': 'Feature',
        'properties': {'NAME': 'Луганская область'},
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[
                [37.5, 49.5], [40.0, 49.5], [40.0, 49.0],
                [40.0, 48.5], [39.0, 48.0], [38.5, 48.0],
                [37.5, 48.0], [37.5, 49.5],
            ]]
        }
    },
    'херсонская область': {
        'type': 'Feature',
        'properties': {'NAME': 'Херсонская область'},
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[
                [31.5, 47.0], [34.0, 47.0], [34.5, 46.5],
                [34.5, 46.0], [33.5, 46.0], [33.0, 46.2],
                [32.5, 46.8], [31.5, 47.0],
            ]]
        }
    },
    'запорожская область': {
        'type': 'Feature',
        'properties': {'NAME': 'Запорожская область'},
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[
                [34.0, 47.5], [36.5, 47.5], [37.0, 47.0],
                [37.0, 46.5], [36.5, 46.5], [35.0, 46.8],
                [34.5, 47.0], [34.0, 47.0], [34.0, 47.5],
            ]]
        }
    },
}


REGION_GEOJSON_MAP = {
    'адыгея': 'республика адыгея',
    'башкортостан': 'республика башкортостан',
    'бурятия': 'республика бурятия',
    'дагестан': 'республика дагестан',
    'ингушетия': 'республика ингушетия',
    'кабардино-балкария': 'кабардино-балкарская республика',
    'калмыкия': 'республика калмыкия',
    'карачаево-черкессия': 'карачаево-черкесская республика',
    'карелия': 'республика карелия',
    'коми': 'республика коми',
    'марий эл': 'республика марий эл',
    'мордовия': 'республика мордовия',
    'якутия': 'республика саха (якутия)',
    'северная осетия': 'республика северная осетия-алания',
    'татарстан': 'республика татарстан (татарстан)',
    'тыва': 'республика тыва',
    'удмуртия': 'удмуртская республика',
    'хакасия': 'республика хакасия',
    'чувашская республика': 'чувашская республика - чувашия',
    'чувашия': 'чувашская республика - чувашия',
    'чечня': 'чеченская республика',
    'ханты-мансийский автономный округ': 'ханты-мансийский автономный округ - югра',
    'днр': 'донецкая область',
    'лнр': 'луганская область',
}


def find_geojson_feature(region_name_lower, geojson_lookup):
    """Match a region alias to GeoJSON feature by name."""
    nl = region_name_lower.strip()
    # Direct match
    if nl in geojson_lookup:
        return geojson_lookup[nl]
    # With республика prefix
    if not nl.startswith('республика '):
        test = 'республика ' + nl
        if test in geojson_lookup:
            return geojson_lookup[test]
    # Without республика prefix
    if nl.startswith('республика '):
        test = nl[len('республика '):]
        if test in geojson_lookup:
            return geojson_lookup[test]
    # Special map
    if nl in REGION_GEOJSON_MAP:
        key = REGION_GEOJSON_MAP[nl]
        if key in geojson_lookup:
            return geojson_lookup[key]
    # Try stripped name in special map (e.g. "республика северная осетия" -> "северная осетия")
    if nl.startswith('республика '):
        test = nl[len('республика '):]
        if test in REGION_GEOJSON_MAP:
            key = REGION_GEOJSON_MAP[test]
            if key in geojson_lookup:
                return geojson_lookup[key]
    return None


def get_mentioned_region_subjects(post_text):
    """Collect subjects of explicit oblast/krai/republic/okrug mentions in post text.

    Rayon-level patterns ("Xский район") are deliberately ignored: their presence
    does not mean the oblast is explicitly named, and they pollute the context
    (e.g. "Каменский район" exists in Тульской, Воронежской и Свердловской
    областях — matching the rayon must not add all three subjects).
    """
    text_lower = post_text.lower()
    subjects = set()
    for p, subject in REGION_MENTION_PATTERNS:
        # Word-boundary match, not substring: "омская область" must not match
        # inside "костр[омская область]" (suffix of "костромская").
        if re.search(r'(?<!\w)' + re.escape(p) + r'(?!\w)', text_lower):
            subjects.add(subject)
    return subjects


def filter_locations_by_post_region(locations, post_text):
    """Filter locations to only those matching a region mentioned in the post text.
    
    If the post explicitly names an oblast/krai/republic, discard locations 
    from other regions (avoids false matches like "моста" → Ивановская область).
    Only considers oblast/krai/republic level entries, NOT rayon-level ones
    (to avoid "Калининский район → Тверская область" creating false region matches).
    """
    if not locations:
        return locations
    mentioned_subjects = get_mentioned_region_subjects(post_text)
    if not mentioned_subjects:
        return locations
    filtered = [loc for loc in locations if loc.get("subject", "").strip().lower() in mentioned_subjects]
    return filtered if filtered else locations


def parse_post_time(time_str):
    if not time_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.strptime(time_str, '%d.%m.%Y %H:%M').replace(tzinfo=timezone(timedelta(hours=3)))
    except:
        return datetime.min.replace(tzinfo=timezone.utc)


def dedup_markers(markers):
    seen = {}
    for m in markers:
        dest = m.get('dest_name', '').lower().strip() if m.get('direction') else ''
        key = (m['name'].lower().strip(), round(m['lat'], 1), round(m['lon'], 1), m.get('type', ''), m.get('is_region', False), dest)
        existing = seen.get(key)
        if existing:
            existing_time = parse_post_time(existing.get('time', ''))
            new_time = parse_post_time(m.get('time', ''))
            if new_time > existing_time:
                seen[key] = m
            elif new_time == existing_time:
                existing_pri = CHANNEL_PRIORITY.get(existing.get('source', ''), 99)
                new_pri = CHANNEL_PRIORITY.get(m.get('source', ''), 99)
                if new_pri < existing_pri:
                    seen[key] = m
                elif new_pri == existing_pri and len(m.get('text', '')) > len(existing.get('text', '')):
                    seen[key] = m
        else:
            seen[key] = m
    return list(seen.values())


def sanitize_popup_text(text):
    if not text:
        return text
    t = text
    t = html_module.unescape(t)
    t = re.sub(r'&#x[0-9a-fA-F]+;', '', t)
    t = re.sub(r'&#\d+;', '', t)
    t = t.replace('\U0001f4e1', '').replace('\U0001f6f0', '').replace('\u26a1', '').replace('\U0001f514', '')
    t = re.sub(r'[\U0001F300-\U0001F9FF\u2600-\u27BF\uFE00-\uFE0F\u200D]', '', t)
    t = re.sub(r'Локатор России[^\n]*', '', t).strip()
    t = re.sub(r'Радар Ярославль[^\n]*', '', t).strip()
    t = re.sub(r'Радар Чувашия[^\n]*', '', t).strip()
    t = re.sub(r'Радар по всей России[^\n]*', '', t).strip()
    t = re.sub(r'Мониторинг\.РФ[^\n]*', '', t).strip()
    t = re.sub(r'Мы в MAX[^\n]*', '', t).strip()
    t = re.sub(r'Радар\.РФ[^\n]*', '', t).strip()
    t = re.sub(r'radar\.RF[^\n]*', '', t).strip()
    t = re.sub(r'[^·\n]{1,40}\s*·\s*\w+\s*·\s*\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}', '', t).strip()
    t = re.sub(r'@\w+\s*', '', t).strip()
    t = re.sub(r'Подписаться', '', t).strip()
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def generate_html(posts_data, filename=None, geojson_lookup=None, history=None):
    if filename is None:
        filename = os.environ.get("OUTPUT_FILE", "mopedmap.html")
    # Keep only the latest post per city
    posts_data = dedup_markers(posts_data)
    # Suppress non-interception markers at locations with interception
    int_keys = set()
    for m in posts_data:
        if m.get('type') == 'interception':
            int_keys.add((m['name'].lower().strip(), round(m['lat'], 1), round(m['lon'], 1)))
    if int_keys:
        posts_data = [m for m in posts_data if not (
            (m['name'].lower().strip(), round(m['lat'], 1), round(m['lon'], 1)) in int_keys
            and m.get('type') != 'interception'
        )]
    # Extract region geometries for active fill types
    region_map = {}  # region_name_lower -> feature
    type_priority = {'rocket': 0, 'danger': 1, 'aviation': 2, 'interception': 3, 'attention': 4, 'sighting': 5, 'info': 6, 'clear': 7}
    # Collect all region entries per region
    from collections import defaultdict
    region_entries = defaultdict(list)
    for item in posts_data:
        if item.get('no_marker'):
            continue
        item_type = item.get('type')
        if item_type not in type_priority:
            continue
        city_name = item.get('name', '').lower().strip()
        region_name = item.get('subject', '').lower().strip() if item.get('subject') else None
        if not region_name and city_name in CITY_DB:
            region_name = CITY_DB[city_name].get('subject', '').lower().strip()
        if region_name:
            region_entries[region_name].append((type_priority[item_type], item, item_type, city_name))
    # Select best entry per region: most severe non-clear threat wins
    # Clear entries don't affect region fill (they appear as individual markers)
    for region_name, entries in region_entries.items():
        non_clear = [(p, item, t, cn) for p, item, t, cn in entries if t != 'clear']
        if non_clear:
            best_prio = min(p for p, _, _, _ in non_clear)
            candidates = [(item, t, cn) for p, item, t, cn in non_clear if p == best_prio]
            def candidate_sort_key(x):
                t = parse_post_time(x[0].get('time', ''))
                pri = CHANNEL_PRIORITY.get(x[0].get('source', ''), 99)
                return (t, -pri, len(x[0].get('text', '')))
            best_item, best_type, best_city = max(candidates, key=candidate_sort_key)
        else:
            # Only clear entries: still show popup with latest clear event
            clear_entries = [(item, t, cn) for p, item, t, cn in entries if t == 'clear']
            best_item, best_type, best_city = max(clear_entries, key=lambda x: parse_post_time(x[0].get('time', '')))
        feat = find_geojson_feature(region_name, geojson_lookup)
        if feat:
            feat_copy = json.loads(json.dumps(feat))
            feat_copy['properties']['alert_type'] = best_type
            feat_copy['properties']['popup_name'] = best_item.get('name', '')
            feat_copy['properties']['popup_text'] = sanitize_popup_text(best_item.get('text', ''))
            feat_copy['properties']['popup_source'] = best_item.get('source', '')
            feat_copy['properties']['popup_time'] = best_item.get('time', '')
            region_map[region_name] = feat_copy
            if best_city != region_name:
                city_feat = find_geojson_feature(best_city, geojson_lookup)
                if city_feat and best_city not in region_map:
                    city_copy = json.loads(json.dumps(city_feat))
                    city_copy['properties']['alert_type'] = best_type
                    city_copy['properties']['popup_name'] = best_item.get('name', '')
                    city_copy['properties']['popup_text'] = sanitize_popup_text(best_item.get('text', ''))
                    city_copy['properties']['popup_source'] = best_item.get('source', '')
                    city_copy['properties']['popup_time'] = best_item.get('time', '')
                    region_map[best_city] = city_copy
    # Fallback: create region fills from city-level items whose subject maps to a GeoJSON region
    # Skip if the same post has a real region entry (область/край/республика in matched text)
    # with a DIFFERENT subject and no entry matches this city's subject — the city is likely
    # a false homonym (e.g. "Архангельск" in a list of Krasnodar Krai locations)
    for item in posts_data:
        if not item.get('is_region') and item.get('type') in type_priority:
            cn = item.get('name', '').lower().strip()
            rn = item.get('subject', '').lower().strip() if item.get('subject') else None
            if not rn and cn in CITY_DB:
                rn = CITY_DB[cn].get('subject', '').lower().strip()
            if rn and rn not in region_map and rn != cn:
                # Check if same post has a real region entry with a different subject
                same_text = item.get('text', '')
                has_own_region = False
                has_other_region = False
                for other in posts_data:
                    if other is item or other.get('text') != same_text:
                        continue
                    if other.get('is_region'):
                        other_rn = other.get('subject', '').lower().strip() if other.get('subject') else None
                        if not other_rn:
                            other_cn = other.get('name', '').lower().strip()
                            if other_cn in CITY_DB:
                                other_rn = CITY_DB[other_cn].get('subject', '').lower().strip()
                        if other_rn:
                            mt = other.get('matched', '').lower()
                            is_real_region = any(t in mt for t in ('область', 'край', 'республика', 'район', 'р-н'))
                            if is_real_region:
                                if other_rn == rn:
                                    has_own_region = True
                                else:
                                    has_other_region = True
                if has_other_region and not has_own_region:
                    continue  # city is likely a false homonym, skip fallback
                feat = find_geojson_feature(rn, geojson_lookup)
                if feat:
                    feat_copy = json.loads(json.dumps(feat))
                    feat_copy['properties']['alert_type'] = item['type']
                    feat_copy['properties']['popup_name'] = item.get('name', '')
                    feat_copy['properties']['popup_text'] = sanitize_popup_text(item.get('text', ''))
                    feat_copy['properties']['popup_source'] = item.get('source', '')
                    feat_copy['properties']['popup_time'] = item.get('time', '')
                    region_map[rn] = feat_copy
    # Mark items that should not render a point marker
    always_show = {'sighting', 'clear', 'interception'}
    for item in posts_data:
        if item.get('is_region') and item.get('type') not in always_show:
            mt = item.get('matched', '').lower()
            if any(t in mt for t in ('область', 'край', 'республика', 'район', 'р-н')):
                continue  # explicit region reference — keep marker
            if re.search(r'\s(мо|го|ао)$', mt):
                continue  # rayon-level ГО/МО/АО reference — specific location, keep marker
            rn = item.get('subject', '').lower().strip() if item.get('subject') else None
            if not rn:
                city_name = item.get('name', '').lower().strip()
                if city_name in CITY_DB:
                    rn = CITY_DB[city_name].get('subject', '').lower().strip()
            if rn and rn in region_map:
                item['no_marker'] = True
    # Suppress region markers from bare adjective forms (e.g. "архангельская" matching as
    # Архангельская область) when the same post has a real region entry with a different subject
    for item in posts_data:
        if not item.get('is_region') or item.get('no_marker'):
            continue
        mt = item.get('matched', '').lower()
        if any(t in mt for t in ('область', 'край', 'республика', 'район', 'р-н')):
            continue  # real region or rayon reference, keep marker
        item_text = item.get('text', '')
        item_rn = item.get('subject', '').lower().strip() if item.get('subject') else None
        if not item_rn:
            item_cn = item.get('name', '').lower().strip()
            if item_cn in CITY_DB:
                item_rn = CITY_DB[item_cn].get('subject', '').lower().strip()
        if not item_rn:
            continue
        has_own_real = False
        has_other_real = False
        for other in posts_data:
            if other is item or other.get('text') != item_text:
                continue
            if other.get('is_region'):
                other_mt = other.get('matched', '').lower()
                if not any(t in other_mt for t in ('область', 'край', 'республика', 'район', 'р-н')):
                    continue
                other_rn = other.get('subject', '').lower().strip() if other.get('subject') else None
                if not other_rn:
                    other_cn = other.get('name', '').lower().strip()
                    if other_cn in CITY_DB:
                        other_rn = CITY_DB[other_cn].get('subject', '').lower().strip()
                if other_rn == item_rn:
                    has_own_real = True
                else:
                    has_other_real = True
        if has_other_real and not has_own_real:
            item['no_marker'] = True
    # Suppress city-level markers (from CITY_DB) when the same post has a real region entry
    # with a different subject and no entry matches this city's subject — false homonym
    for item in posts_data:
        if item.get('is_region') or item.get('no_marker'):
            continue
        cn = item.get('name', '').lower().strip()
        rn = item.get('subject', '').lower().strip() if item.get('subject') else None
        if not rn and cn in CITY_DB:
            rn = CITY_DB[cn].get('subject', '').lower().strip()
        if not rn:
            continue
        item_text = item.get('text', '')
        has_own_real = False
        has_other_real = False
        for other in posts_data:
            if other is item or other.get('text') != item_text:
                continue
            if other.get('is_region'):
                other_mt = other.get('matched', '').lower()
                if not any(t in other_mt for t in ('область', 'край', 'республика', 'район', 'р-н')):
                    continue
                other_rn = other.get('subject', '').lower().strip() if other.get('subject') else None
                if not other_rn:
                    other_cn = other.get('name', '').lower().strip()
                    if other_cn in CITY_DB:
                        other_rn = CITY_DB[other_cn].get('subject', '').lower().strip()
                if other_rn == rn:
                    has_own_real = True
                else:
                    has_other_real = True
        if has_other_real and not has_own_real:
            item['no_marker'] = True
    # Suppress region-level marker if the same post (source+time) has a CITY_DB city marker in the same subject
    for item in posts_data:
        if not (item.get('is_region') and not item.get('no_marker')):
            continue
        item_subj = item.get('subject', '').lower().strip()
        if not item_subj:
            cn = item.get('name', '').lower().strip()
            if cn in CITY_DB:
                item_subj = CITY_DB[cn].get('subject', '').lower().strip()
        if not item_subj:
            continue
        for other in posts_data:
            if other is item or other.get('no_marker') or other.get('is_region'):
                continue
            if other.get('source') != item.get('source') or other.get('time') != item.get('time'):
                continue
            other_cn = other.get('name', '').lower().strip()
            if other_cn not in CITY_DB:
                continue  # only major cities suppress region markers, not settlements/rayons
            other_subj = other.get('subject', '').lower().strip()
            if not other_subj:
                if other_cn in CITY_DB:
                    other_subj = CITY_DB[other_cn].get('subject', '').lower().strip()
            if other_subj == item_subj:
                item['no_marker'] = True
                break
    # Suppress settlement markers (not in CITY_DB) when an explicit region reference
    # for the same subject exists — the region fill + capital marker is sufficient
    for item in posts_data:
        if item.get('is_region') or item.get('no_marker'):
            continue
        cn = item.get('name', '').lower().strip()
        if cn in CITY_DB:
            continue
        rn = item.get('subject', '').lower().strip() if item.get('subject') else None
        if not rn:
            continue
        for other in posts_data:
            if other is item or other.get('no_marker'):
                continue
            if other.get('is_region') and other.get('subject', '').lower().strip() == rn:
                mt = other.get('matched', '').lower()
                if any(t in mt for t in ('область', 'край', 'республика', 'район', 'р-н')):
                    item['no_marker'] = True
                    break

    # Priority at same coordinates
    coord_items = {}
    for item in posts_data:
        key = (round(item.get('lat', 0), 1), round(item.get('lon', 0), 1))
        coord_items.setdefault(key, []).append(item)
    for key, items in coord_items.items():
        types = {it.get('type') for it in items}
        # clear vs any threat: only clear threats matching the clear text type
        threat_types = {'danger', 'rocket', 'aviation', 'interception', 'sighting', 'attention'}
        if 'clear' in types and types & threat_types:
            clear_items = [it for it in items if it.get('type') == 'clear']
            threat_items = [it for it in items if it.get('type') in threat_types]
            latest_clear = max(parse_post_time(it.get('time', '')) for it in clear_items)
            latest_threat = max(parse_post_time(it.get('time', '')) for it in threat_items)
            if latest_clear >= latest_threat:
                for it in threat_items:
                    should_clear = False
                    for c in clear_items:
                        ct = c.get('text', '').lower()
                        if 'ракетн' in ct:
                            ct_set = {'rocket'}
                        elif 'бпла' in ct:
                            ct_set = {'danger', 'attention', 'aviation'}
                        else:
                            ct_set = threat_types
                        if it.get('type') in ct_set:
                            should_clear = True
                            break
                    if should_clear:
                        it['no_marker'] = True
            else:
                for it in clear_items:
                    it['no_marker'] = True
        # interception hides sighting
        if 'interception' in types and 'sighting' in types:
            for it in items:
                if it.get('type') == 'sighting':
                    it['no_marker'] = True
        # sighting hides danger/attention
        if 'sighting' in types:
            for it in items:
                if it.get('type') in ('danger', 'attention'):
                    it['no_marker'] = True
        # danger vs interception: within 1h → interception wins; 1h+ older → danger wins
        if 'danger' in types and 'interception' in types:
            danger_items = [it for it in items if it.get('type') == 'danger']
            int_items = [it for it in items if it.get('type') == 'interception']
            latest_danger = max(parse_post_time(it.get('time', '')) for it in danger_items)
            latest_int = max(parse_post_time(it.get('time', '')) for it in int_items)
            diff = (latest_danger - latest_int).total_seconds()
            if diff >= 3600:
                for it in int_items:
                    it['no_marker'] = True  # interception 1h+ older → danger wins
            else:
                for it in danger_items:
                    it['no_marker'] = True  # within 1h → interception wins

    # Clear region fills where clear is newer than the fill → keep polygon but show clear popup
    # Only clear fills matching the threat type mentioned in the clear text
    for item in posts_data:
        if item.get('type') == 'clear' and not item.get('no_marker'):
            clear_text = item.get('text', '').lower()
            if 'ракетн' in clear_text:
                clear_types = {'rocket'}
            elif 'бпла' in clear_text:
                clear_types = {'danger', 'attention', 'aviation', 'interception'}
            else:
                clear_types = {'rocket', 'danger', 'aviation', 'attention', 'interception'}
            rn = item.get('subject', '').lower().strip() if item.get('subject') else None
            if not rn:
                cn = item.get('name', '').lower().strip()
                if cn in CITY_DB:
                    rn = CITY_DB[cn].get('subject', '').lower().strip()
            if rn and rn in region_map:
                at = region_map[rn]['properties'].get('alert_type', '')
                if at in clear_types:
                    fill_time = region_map[rn]['properties'].get('popup_time', '')
                    if parse_post_time(item.get('time', '')) >= parse_post_time(fill_time):
                        # Check if other active (non-cleared) threats remain for this region
                        other_type = None
                        for other in posts_data:
                            if other.get('type') not in type_priority or other.get('cleared'):
                                continue
                            if other.get('type') == 'clear':
                                continue
                            if other.get('no_marker'):
                                continue  # скрытые/ложные маркеры не держат заливку
                            if other.get('is_region') or other.get('subject'):
                                other_rn = other.get('subject', '').lower().strip() if other.get('subject') else None
                                if not other_rn:
                                    other_cn = other.get('name', '').lower().strip()
                                    if other_cn in CITY_DB:
                                        other_rn = CITY_DB[other_cn].get('subject', '').lower().strip()
                                if other_rn == rn and other.get('type') not in clear_types:
                                    if other_type is None or type_priority.get(other.get('type'), 99) < type_priority.get(other_type, 99):
                                        other_type = other.get('type')
                        if other_type:
                            new_type = other_type
                        else:
                            new_type = 'clear'
                        # Update all region_map entries for this GeoJSON polygon
                        this_name = region_map[rn]['properties'].get('NAME', '').lower()
                        for rm_key in list(region_map):
                            rm_name = region_map[rm_key]['properties'].get('NAME', '').lower()
                            if rm_name == this_name:
                                region_map[rm_key]['properties']['alert_type'] = new_type
                                region_map[rm_key]['properties']['popup_name'] = item.get('name', '')
                                region_map[rm_key]['properties']['popup_text'] = sanitize_popup_text(item.get('text', ''))
                                region_map[rm_key]['properties']['popup_source'] = item.get('source', '')
                                region_map[rm_key]['properties']['popup_time'] = item.get('time', '')
            # Also clear city-level polygon fill
            cn = item.get('name', '').lower().strip()
            if cn in region_map:
                at = region_map[cn]['properties'].get('alert_type', '')
                if at in clear_types:
                    fill_time = region_map[cn]['properties'].get('popup_time', '')
                    if parse_post_time(item.get('time', '')) >= parse_post_time(fill_time):
                        region_map[cn]['properties']['alert_type'] = 'clear'
                        region_map[cn]['properties']['popup_name'] = item.get('name', '')
                        region_map[cn]['properties']['popup_text'] = sanitize_popup_text(item.get('text', ''))
                        region_map[cn]['properties']['popup_source'] = item.get('source', '')
                    region_map[cn]['properties']['popup_time'] = item.get('time', '')

    # Fill regions with sightings but no active threat as attention (БПЛА)
    # Collect regions with active threat fills
    active_threat_regions = set()
    threat_types_map = {'danger', 'rocket', 'aviation', 'attention'}
    for rn, feat in region_map.items():
        at = feat['properties'].get('alert_type', '')
        if at in threat_types_map:
            active_threat_regions.add(rn)
    # Collect regions with active (non-cleared) sightings
    sighting_items_by_region = {}
    for item in posts_data:
        if item.get('type') == 'sighting' and not item.get('cleared'):
            rn = item.get('subject', '').lower().strip() if item.get('subject') else None
            if not rn:
                cn = item.get('name', '').lower().strip()
                if cn in CITY_DB:
                    rn = CITY_DB[cn].get('subject', '').lower().strip()
            if rn:
                existing = sighting_items_by_region.get(rn)
                if existing is None:
                    sighting_items_by_region[rn] = item
                else:
                    existing_time = parse_post_time(existing.get('time', ''))
                    new_time = parse_post_time(item.get('time', ''))
                    if new_time > existing_time:
                        sighting_items_by_region[rn] = item
                    elif new_time == existing_time:
                        existing_pri = CHANNEL_PRIORITY.get(existing.get('source', ''), 99)
                        new_pri = CHANNEL_PRIORITY.get(item.get('source', ''), 99)
                        if new_pri < existing_pri:
                            sighting_items_by_region[rn] = item
    for rn, sighting_item in sighting_items_by_region.items():
        if rn in active_threat_regions:
            continue
        if rn in region_map:
            at = region_map[rn]['properties'].get('alert_type', '')
            if at == 'sighting':
                region_map[rn]['properties']['alert_type'] = 'attention'
                region_map[rn]['properties']['popup_name'] = sighting_item.get('name', '')
                region_map[rn]['properties']['popup_text'] = sanitize_popup_text(f"Фиксации БПЛА в районе\n{sighting_item.get('text', '')}")
                region_map[rn]['properties']['popup_source'] = sighting_item.get('source', '')
                region_map[rn]['properties']['popup_time'] = sighting_item.get('time', '')
            continue
        feat = find_geojson_feature(rn, geojson_lookup)
        if feat:
            feat_copy = json.loads(json.dumps(feat))
            feat_copy['properties']['alert_type'] = 'attention'
            feat_copy['properties']['popup_name'] = sighting_item.get('name', '')
            feat_copy['properties']['popup_text'] = sanitize_popup_text(f"Фиксации БПЛА в районе\n{sighting_item.get('text', '')}")
            feat_copy['properties']['popup_source'] = sighting_item.get('source', '')
            feat_copy['properties']['popup_time'] = sighting_item.get('time', '')
            region_map[rn] = feat_copy
            # Also add synthetic item to posts_data so closest-danger detects it
            coords = feat_copy['geometry']['coordinates']
            if feat_copy['geometry']['type'] == 'Polygon':
                center_lat = coords[0][0][1]
                center_lon = coords[0][0][0]
            else:
                center_lat = coords[0][0][0][1]
                center_lon = coords[0][0][0][0]
            syn = {
                "lat": center_lat, "lon": center_lon,
                "name": sighting_item.get('name', ''),
                "type": "attention",
                "text": f"Фиксации БПЛА в районе\n{sighting_item.get('text', '')}",
                "source": sighting_item.get('source', ''),
                "time": sighting_item.get('time', ''),
                "is_region": True,
                "no_marker": True,
                "subject": rn,
            }
            posts_data.append(syn)

    # Fallback: show history popups for regions without current events (max HISTORY_HOURS old)
    if history:
        history_cutoff = datetime.now(timezone(timedelta(hours=3))) - timedelta(hours=HISTORY_HOURS)
        for rn, h_entry in history.items():
            if rn in region_map:
                continue
            h_time = h_entry.get('time', '')
            if not h_time or parse_post_time(h_time) < history_cutoff:
                continue
            feat = find_geojson_feature(rn, geojson_lookup)
            if feat:
                feat_copy = json.loads(json.dumps(feat))
                h_name = h_entry.get('name', '')
                h_type = h_entry.get('type', '')
                h_text = h_entry.get('text', '')[:500]
                h_time = h_entry.get('time', '')
                h_source = h_entry.get('source', '')
                # All history entries get transparent fill with [История] popup
                alert_type = 'history'
                feat_copy['properties']['alert_type'] = alert_type
                feat_copy['properties']['popup_name'] = f"[История] {h_name}"
                feat_copy['properties']['popup_text'] = f"Последнее ({h_time}):\n{h_text}"
                feat_copy['properties']['popup_source'] = h_source
                feat_copy['properties']['popup_time'] = h_time
                region_map[rn] = feat_copy

    markers_json = json.dumps(posts_data, ensure_ascii=False)

    region_features = list(region_map.values())
    region_geojson = json.dumps({'type': 'FeatureCollection', 'features': region_features}, ensure_ascii=False)

    districts_geojson = ""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dp = os.path.join(script_dir, "yaroslavl_districts.geojson")
    if os.path.exists(dp):
        with open(dp, encoding="utf-8") as df:
            dg = json.load(df)
        for feat in dg.get("features", []):
            feat["properties"]["region"] = feat["properties"].get("region", "Ярославская область")
        districts_geojson = json.dumps(dg, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>YarLocator — Карта угроз</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #222; display: flex; flex-direction: column; height: 100vh; }}
#map {{ flex: 1; width: 100%; min-height: 0; }}
.footer {{ display: flex; align-items: center; padding: 6px 12px; background: #fff; border-top: 1px solid #ddd; font-size: 11px; color: #555; gap: 6px; flex-wrap: wrap; }}
.footer span {{ white-space: nowrap; }}
.footer .dot {{ font-size: 16px; line-height: 1; }}
.header {{ min-height: 60px; display: flex; align-items: center; padding: 8px 12px; background: #fff; border-bottom: 1px solid #ddd; gap: 6px; flex-wrap: wrap; overflow: hidden; }}

.header h1 {{ font-size: 15px; color: #d32f2f; white-space: nowrap; }}
.header .info {{ font-size: 11px; color: #777; margin-left: auto; }}
.legend {{ background: rgba(255, 255, 255, 0.95); padding: 12px 16px; border-radius: 10px; color: #333; font-size: 13px; border: 1px solid #ccc; }}
.legend i {{ width: 12px; height: 12px; display: inline-block; border-radius: 50%; margin-right: 6px; }}
.popup-text {{ font-size: 12px; max-height: 500px; overflow-y: auto; line-height: 1.4; word-break: break-word; white-space: pre-wrap; }}
.leaflet-popup-content {{ max-width: 600px !important; }}
.leaflet-tile-pane {{ filter: saturate(0.77); }}
.popup-name {{ font-size: 15px; font-weight: bold; color: #d32f2f; margin-bottom: 4px; }}
.popup-source {{ color: #666; font-size: 11px; margin-top: 4px; }}
.dest-tooltip {{ background: #fff; border: 1px solid #ccc; color: #333; font-size: 11px; padding: 2px 6px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.district-tooltip.leaflet-tooltip {{ background: rgba(255,255,255,0.85); border: none; color: #555; font-size: 11px; padding: 1px 5px; border-radius: 3px; box-shadow: 0 0 3px rgba(0,0,0,0.1); }}
.leaflet-popup-content-wrapper {{ max-height: 80vh; overflow-y: auto; }}
.leaflet-popup-content {{ max-height: 75vh; overflow-y: auto; }}
@media (max-width:600px) {{ .header {{ font-size: 12px; }} .info {{ font-size: 10px; }} .header h1 {{ font-size: 13px; }} #dist-info {{ font-size: 11px !important; }} .legend {{ display: none !important; }} }}

</style>
</head>
<body>
<div class="header">
  <h1>YarLocator <span id="dist-info" style="font-size:12px;color:#d32f2f;font-weight:normal"></span></h1>
  <span class="info">Угрозы БПЛА | {len(posts_data)} точек | {(datetime.now(timezone.utc) + timedelta(hours=3)).strftime('%d.%m.%Y %H:%M')} МСК</span>
</div>
<div id="map"></div>
<div class="footer">
  <span class="dot" style="color:#e94560">●</span> Опасность БПЛА
  <span class="dot" style="color:#06b6d4">●</span> Авиационная опасность
  <span style="color:#000000;font-size:14px">◆</span> Фиксация
  <span class="dot" style="color:#eab308">●</span> Внимание
  <span style="color:#000000;font-size:14px;font-weight:bold">✕</span> Перехват
  <span class="dot" style="color:#a855f7">●</span> Ракетная опасность
  <span class="dot" style="color:#6a7a5a">●</span> Отбой
  <span class="dot" style="color:#60a5fa">●</span> Инфо
  <span style="color:#22c55e;font-size:14px">✚</span> Молнии (30 мин)
  <span style="margin-left:auto;color:#999">Обновление каждые 5 мин · данные за 4 часа</span>
</div>
<script>
const PC = window.innerWidth >= 1024;
const map = L.map('map', {{ center: PC ? [54.63, 39.73] : [56.74, 38.86], zoom: 6, zoomControl: true, attributionControl: false }});

map.createPane('lightning-0');
map.getPane('lightning-0').style.filter = 'invert(0.15) brightness(0.7) sepia(1) hue-rotate(90deg) saturate(4)';
map.createPane('lightning-1');
map.getPane('lightning-1').style.filter = 'invert(0.15) brightness(0.5) sepia(1) hue-rotate(90deg) saturate(3)';

L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  maxZoom: 19
}}).addTo(map);

const lightningTileUrl = 'https://images.lightningmaps.org/blitzortung/europe/index.php?tile&zoom={{z}}&x={{x}}&y={{y}}&type=';
const lightningLayer0 = L.tileLayer(lightningTileUrl + '0', {{ opacity: 0.9, maxZoom: 19, pane: 'lightning-0', attribution: 'Молнии: <a href=\"https://www.blitzortung.org\">Blitzortung.org</a>' }});
const lightningLayer1 = L.tileLayer(lightningTileUrl + '1', {{ opacity: 0.9, maxZoom: 19, pane: 'lightning-1' }});
const lightningGroup = L.layerGroup([lightningLayer0, lightningLayer1]).addTo(map);

setInterval(function() {{
  const ts = '&_t=' + Date.now();
  lightningLayer0.setUrl(lightningTileUrl + '0' + ts);
  lightningLayer1.setUrl(lightningTileUrl + '1' + ts);
}}, 120000);

L.control.attribution({{ prefix: false }}).addTo(map);

const data = {markers_json};

const styleMap = {{
  danger: {{ color: '#a83232', size: 12, glow: null }},
  aviation: {{ color: '#2a6a90', size: 12, glow: null }},
  sighting: {{ color: '#555555', size: 14, glow: null }},
  clear: {{ color: '#22c55e', size: 10, glow: null }},
  attention: {{ color: '#8a6830', size: 10, glow: null }},
  interception: {{ color: '#333333', size: 10, glow: null }},
  rocket: {{ color: '#6d4a9e', size: 14, glow: null }},
  info: {{ color: '#4a6ebb', size: 8, glow: null }},
  history: {{ color: '#999999', size: 0, glow: null }}
}};

const bounds = [];

const typeLabel = {{ danger: 'Опасность БПЛА', aviation: 'Авиационная опасность', sighting: 'Фиксация', clear: 'Отбой', attention: 'Внимание', interception: 'Перехват', rocket: 'Ракетная опасность', history: 'Архив' }};

const regionGeoJSON = {region_geojson};
const districtsGeoJSON = {districts_geojson if districts_geojson else 'null'};

// Draw region polygon fills
L.geoJSON(regionGeoJSON, {{
  style: function(feature) {{
    const alertType = feature.properties.alert_type || 'danger';
    if (alertType === 'history') {{
      return {{
        color: '#999999', fillColor: 'transparent',
        fillOpacity: 0, weight: 1, opacity: 0.4,
        interactive: true
      }};
    }}
    const s = styleMap[alertType] || styleMap.danger;
    const fillColor = (alertType === 'sighting') ? styleMap.danger.color : s.color;
    return {{
      color: fillColor, fillColor: fillColor,
      fillOpacity: alertType === 'clear' ? 0 : 0.1,
      weight: 1.5, opacity: 0.35
    }};
  }},
  onEachFeature: function(feature, layer) {{
    const p = feature.properties;
    if (p.popup_text) {{
      const label = typeLabel[p.alert_type] || p.alert_type || '';
      let html = `<div class="popup-name">${{p.popup_name || ''}}</div><div class="popup-text">${{p.popup_text}}</div><div class="popup-source">${{label}}${{p.popup_source ? ' · ' + p.popup_source : ''}}${{p.popup_time ? ' · ' + p.popup_time : ''}}</div>`;
      layer.bindPopup(html);
    }}
  }}
}}).addTo(map);

// District boundaries overlay (визуальные линии, тултип через mousemove map)
if (districtsGeoJSON) {{
  L.geoJSON(districtsGeoJSON, {{
    interactive: false,
    style: {{
      color: '#777', weight: 0.8, opacity: 0.4,
      fill: false
    }}
  }}).addTo(map);
  // Pre-process district polygons for point-in-polygon check
  const dPolys = [];
  districtsGeoJSON.features.forEach(function(f) {{
    const dn = f.properties.district;
    if (!dn) return;
    const coords = f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates[0][0] : f.geometry.coordinates[0];
    dPolys.push({{ name: dn, coords: coords.map(function(c) {{ return [c[1], c[0]]; }}) }});
  }});
  let tip = null;
  map.on('mousemove', function(e) {{
    const ll = [e.latlng.lat, e.latlng.lng];
    let found = null;
    for (let i = 0; i < dPolys.length; i++) {{
      const pts = dPolys[i].coords;
      let inside = false;
      for (let j = 0, k = pts.length - 1; j < pts.length; k = j++) {{
        const xi = pts[j][0], yi = pts[j][1];
        const xk = pts[k][0], yk = pts[k][1];
        if (((yi > ll[1]) !== (yk > ll[1])) && (ll[0] < (xk - xi) * (ll[1] - yi) / (yk - yi) + xi)) {{
          inside = !inside;
        }}
      }}
      if (inside) {{ found = dPolys[i]; break; }}
    }}
    if (found) {{
      if (!tip) {{
        tip = L.tooltip({{ permanent: true, direction: 'center', className: 'district-tooltip' }})
          .setLatLng(e.latlng).addTo(map);
      }}
      tip.setLatLng(e.latlng).setContent(found.name);
    }} else {{
      if (tip) {{ tip.remove(); tip = null; }}
    }}
  }});
}}

const lightningCtrl = L.control({{ position: 'topleft' }});
lightningCtrl.onAdd = function() {{
  const div = L.DomUtil.create('div', '');
  div.style.cssText = 'background:rgba(255,255,255,.9);padding:4px 8px;border-radius:6px;font-size:13px;border:1px solid #ccc;cursor:pointer;white-space:nowrap';
  div.innerHTML = '<label style="cursor:pointer"><input type="checkbox" id="lightning-cb" checked> <span style="font-size:16px">⛈</span></label>';
  L.DomEvent.disableClickPropagation(div);
  const cb = div.querySelector('#lightning-cb');
  cb.addEventListener('change', function() {{
    if (this.checked) lightningGroup.addTo(map);
    else map.removeLayer(lightningGroup);
  }});
  return div;
}};
lightningCtrl.addTo(map);

data.forEach(item => {{
  const s = styleMap[item.type] || styleMap.info;

  if (item.no_marker) return;

  const size = s.size;
  const glow = s.glow ? `box-shadow:0 0 ${{s.size > 12 ? 10 : 6}}px ${{s.glow}};` : '';
  const border = '2px solid #333';
  const extraGlow = glow;
  const shape = item.type === 'sighting'
    ? 'clip-path:polygon(50% 0%,100% 50%,50% 100%,0% 50%);border-radius:0;'
    : 'border-radius:50%;';
  const html = item.type === 'interception'
    ? `<div style="background:${{s.color}};width:${{size}}px;height:${{size}}px;border:${{border}};border-radius:2px;${{extraGlow}};display:flex;align-items:center;justify-content:center"><span style="color:#fff;font-size:${{size-4}}px;font-weight:bold;line-height:1">✕</span></div>`
    : `<div style="background:${{s.color}};width:${{size}}px;height:${{size}}px;border:${{border}};${{shape}}${{extraGlow}}"></div>`;

  const zOffset = (item.type === 'sighting' || item.type === 'interception') ? 2000 : 0;
  const marker = L.marker([item.lat, item.lon], {{
    icon: L.divIcon({{ html, className: '', iconSize: [size + 8, size + 8] }}),
    zIndexOffset: zOffset
  }}).addTo(map);

  let popupHtml = `<div class="popup-name">${{item.name}}</div><div class="popup-text">${{item.text}}</div><div class="popup-source">${{typeLabel[item.type] || item.type}}${{item.source ? ' · ' + item.source : ''}}${{item.time ? ' · ' + item.time : ''}}</div>`;
  if (item.direction) {{
    popupHtml += `<div class="popup-source">→ ${{item.dest_name || '?'}}</div>`;
  }}
  marker.bindPopup(popupHtml);

  bounds.push([item.lat, item.lon]);
}});

// Draw direction arrows
data.filter(item => item.direction).forEach(item => {{
  const from = [item.lat, item.lon];
  const to = item.direction;
  const s = styleMap[item.type] || styleMap.info;
  const color = s.color;

  L.polyline([from, to], {{
    color, weight: 3, opacity: 0.75, dashArray: '6, 5'
  }}).addTo(map);

  // Arrow at midpoint
  const midLat = (from[0] + to[0]) / 2;
  const midLon = (from[1] + to[1]) / 2;
  const angle = Math.atan2(to[1] - from[1], to[0] - from[0]) * 180 / Math.PI;
  const arrowSvg = '<svg width="14" height="14" viewBox="0 0 14 14" style="transform:rotate(' + (angle - 90) + 'deg)"><polygon points="0,0 14,7 0,14" fill="' + color + '" opacity="0.9"/></svg>';
  L.marker([midLat, midLon], {{
    icon: L.divIcon({{ html: arrowSvg, className: '', iconSize: [14, 14], iconAnchor: [7, 7] }}),
    interactive: true
  }}).addTo(map).bindPopup('<div class="popup-name">' + item.name + ' → ' + (item.dest_name || '?') + '</div><div class="popup-text">' + (item.text || '') + '</div><div class="popup-source">' + (typeLabel[item.type] || item.type || '') + (item.source ? ' · ' + item.source : '') + (item.time ? ' · ' + item.time : '') + '</div>');

  L.circleMarker(to, {{
    radius: 6, color: '#333', weight: 2, fill: true, fillColor: color,
    fillOpacity: 0.25, dashArray: '3, 4', opacity: 0.8
  }}).addTo(map).bindTooltip(item.dest_name || '?', {{
    permanent: false, direction: 'top', offset: [0, -4],
    className: 'dest-tooltip'
  }}).bindPopup('<div class="popup-name">' + (item.dest_name || '?') + '</div><div class="popup-text">' + (item.text || '') + '</div><div class="popup-source">→ ' + item.name + ' (' + (typeLabel[item.type] || item.type || '') + (item.source ? ' · ' + item.source : '') + (item.time ? ' · ' + item.time : '') + ')</div>');
}});

if (bounds.length > 0) {{
  map.setView(PC ? [54.63, 39.73] : [56.74, 38.86], 6);
}}

const YAROSLAVL_COORDS = [57.553026, 39.850545];
// Permanent blue star marker at Yaroslavl
const starIcon = L.divIcon({{
  html: '<div style="width:14px;height:14px;clip-path:polygon(50% 0%,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%);background:#2196f3;border:1px solid #1565c0"></div>',
  className: '', iconSize: [14, 14], iconAnchor: [7, 7]
}});
L.marker(YAROSLAVL_COORDS, {{ icon: starIcon, zIndexOffset: 1000 }}).addTo(map).bindPopup('Ярославль - постоянный маркер');
// Closest threat to Yaroslavl
const yarLatLng = L.latLng(YAROSLAVL_COORDS);
let minDist = Infinity;
let minDistCity = Infinity;
let closestItem = null;
let closestCity = null;
data.forEach(item => {{
  if (item.type === 'danger' || item.type === 'rocket' || item.type === 'aviation' || item.type === 'attention' || item.type === 'sighting' || item.type === 'interception') {{
    if (!item.cleared) {{
      const d = map.distance(yarLatLng, [item.lat, item.lon]);
      if (d < minDist) {{ minDist = d; closestItem = item; }}
      if (!item.is_region && d < minDistCity) {{ minDistCity = d; closestCity = item; }}
    }}
  }}
}});
// Prefer city-level marker (distance from actual location), fall back to region
const useItem = closestCity || closestItem;
if (useItem) {{
  const distKm = ((closestCity ? minDistCity : minDist) / 1000).toFixed(0);
  let ago = '';
  const closestTime = useItem.time || '';
  if (closestTime) {{
    const [dd, mm, yyyy, hh, mi] = closestTime.match(/(\\d+)/g);
    const postDate = new Date(+yyyy, +mm - 1, +dd, +hh, +mi);
    const mins = Math.round((Date.now() - postDate) / 60000);
    if (mins > 0) ago = `, ${{mins}} мин назад`;
  }}
  const subjText = useItem.subject ? `, ${{useItem.subject}}` : '';
  document.getElementById('dist-info').textContent = `ближайшая опасность: ${{distKm}} км (${{useItem.name}}${{subjText}}${{ago}})`;
}}

const legendCtrl = L.control({{ position: 'bottomright' }});
legendCtrl.onAdd = function() {{
  const div = L.DomUtil.create('div', 'legend');
  div.style.cursor = 'pointer';
  div.innerHTML = '<span id="legend-toggle"><b>▶ Легенда</b></span><div id="legend-body" style="display:none;margin-top:4px"><b>Легенда</b><br>' +
    '<i style="background:#e94560"></i> Опасность БПЛА<br>' +
    '<i style="background:#06b6d4"></i> Авиационная опасность<br>' +
    '<i style="background:#f5a623"></i> Фиксация<br>' +
    '<i style="background:#4ade80"></i> Отбой<br>' +
    '<i style="background:#eab308"></i> Внимание<br>' +
    '<i style="background:#f97316"></i> Перехват<br>' +
    '<i style="background:#a855f7"></i> Ракетная опасность<br>' +
    '<hr style="border-color:#333;margin:6px 0">' +
    '<span style="display:inline-block;width:12px;height:12px;clip-path:polygon(50% 0%,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%);background:#333;border:2px solid #00f5ff;vertical-align:middle;margin-right:6px"></span> Ярославль и область' +
    '<br><span style="font-size:11px;color:#888">Заливка = область в опасности</span></div>';
  div.onclick = function() {{
    const body = div.querySelector('#legend-body');
    const toggle = div.querySelector('#legend-toggle');
    if (body.style.display === 'none') {{
      body.style.display = '';
      toggle.textContent = '▼ Легенда';
    }} else {{
      body.style.display = 'none';
      toggle.textContent = '▶ Легенда';
    }}
  }};
  return div;
}};
legendCtrl.addTo(map);
</script>
</body>
</html>"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    return os.path.abspath(filename)


def load_region_history():
    try:
        with open(REGION_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_region_history(history):
    try:
        with open(REGION_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  Ошибка сохранения истории регионов: {e}")


def update_region_history(markers, history):
    for m in markers:
        rn = m.get('subject', '').lower().strip() if m.get('subject') else None
        if not rn:
            cn = m.get('name', '').lower().strip()
            if cn in CITY_DB:
                rn = CITY_DB[cn].get('subject', '').lower().strip()
        if not rn:
            continue
        m_time = m.get('time', '')
        if not m_time:
            continue
        existing = history.get(rn, {})
        existing_time = existing.get('time', '')
        if not existing_time or parse_post_time(m_time) > parse_post_time(existing_time):
            history[rn] = {
                'name': m.get('name', ''),
                'type': m.get('type', ''),
                'text': m.get('text', '')[:500],
                'source': m.get('source', ''),
                'time': m_time,
            }
    return history


SUMMARY_PATTERNS = [
    r'за полгода сбили более',
    r'в течение прошедш\w+ ноч',
    r'в период с.*дежурными средствами пво',
    r'средствами пво перехвачены и уничтожен',
    r'за прошедш\w+ ноч',
    r'за прошедш\w+ сутк',
    r'за последние сутк',
    r'за сутки.*силами пво',
    r'за сутки.*уничтожен\w* \d+\s*(бпла|беспилотн\w*)',
    r'за сутки.*сбит\w* \d+\s*(бпла|беспилотн\w*)',
    r'силами противовоздушной обороны',
    r'по всем вышеперечисленн',
    r'по ранее объявленн',
    r'ракетн\w+ опасность по всем',
    r'сохраняется\.? меры безопасности',
    r'^отбой\s*$',
    r'^🟢отбой\s*$',
    r'падение дрон',
    r'результатом воздействия пво',
    r'министерство обороны',
    r'ночью средствами пво',
    r'впервые регионы.*подверглись массовым ракетным атакам',
    r'создать специальные каналы для информирования',
    r'каналы будут работать даже без мобильной связи',
    r'найти свой город и подписаться',
    r'по всей территории рф может быть объявлен режим',
    r'чрезвычайного положения',
    r'многие регионы.*подверглись массовым ракетным атакам',
    r'создать телеграм каналы для оповещения',
    r'крымская оборонительная операция',
    r'ключевые принципы, которых мы придерживаемся',
    r'видео ночного киев\w*',
    r'· лпр ·',
]


def is_summary_post(text):
    text_lower = text.lower().strip()
    for pat in SUMMARY_PATTERNS:
        if re.search(pat, text_lower):
            return True
    return False


# Канал radar_rossia_bpla публикует сводки последствий ночных атак
# («в результате атаки пострадал… погибли… экстренные службы») без текущих
# координат/направления БПЛА — такие посты не нужны на карте.
NEWS_RECAP_CHANNEL = "radar_rossia_bpla"
NEWS_RECAP_PATTERNS = [
    r'в результате атаки',
    r'пострадал\w*',
    r'погибл\w*',
    r'поврежден\w*',
    r'обломк\w*',
    r'экстренные службы',
    r'ранен\w*',
    r'ущерб\w*',
    r'прилет\w*',
    r'жилой дом',
    r'после атаки',
    r'из-за атаки',
    # официальные сводки последствий («[История] Сети / Последнее (...)»):
    # глава региона/служба отчитывается о последствиях, активных направлений нет
    r'на (моём|моем) личном контроле',
    r'призываю не распространять',
    r'следите за дальнейшими оповещениями',
    r'приближаться к обломкам',
    r'на месте происшествия',
]
_DIRECTION_KW_RE = re.compile(r'в сторону|в вашу сторону|в нашу сторону|в направлен|→|➡️')


VRV_RADAR_CHANNEL = "vrv_radar"
VRV_RADAR_FILTER_PATTERNS = [
    r'запрещено снимать',
    r'запрещено выкладывать',
    r'запрещено публиковать',
    r'информационная тишина',
]


def is_vrv_radar_reminder(text):
    """Напоминание о запрете съёмки/публикации с vrv_radar (без локаций)."""
    text_lower = text.lower()
    return any(re.search(pat, text_lower) for pat in VRV_RADAR_FILTER_PATTERNS)


def is_news_recap_post(text):
    """Сводка последствий атаки / официальное сообщение (без активного
    направления БПЛА). Применяется ко ВСЕМ каналам; посты с направлением
    («в сторону/в направлении/→») не фильтруются — активные пролёты остаются."""
    text_lower = text.lower()
    if _DIRECTION_KW_RE.search(text_lower):
        return False
    return any(re.search(pat, text_lower) for pat in NEWS_RECAP_PATTERNS)


# Рекламные/паникёрские посты, раскручивающие сторонние Telegram-каналы
# (например «Закрытая повестка») — без актуальных координат БПЛА, на карту не нужны.
PROMO_SPAM_PATTERNS = [
    r'закрытая повестка',
    r'в telegram стремительно набирает популярность',
    r'пора читать правду',
    r'официальные сми об этом молчат',
    r'последний шанс на быстрое окончание войны',
    r'почему нужно снять вклады',
    r'остаётся за рамками официальной пропаганды',
    r'настоящая кульминация начнётся',
]


def is_promo_spam_post(text):
    """Рекламный пост-накрутка канала (без локаций/направлений БПЛА)."""
    text_lower = text.lower()
    return any(re.search(pat, text_lower) for pat in PROMO_SPAM_PATTERNS)


# Посты-памятки («Памятка при атаке БПЛА», «Что делать при обнаружении БПЛА»,
# «#ВРВОбразовательный») — образовательный материал без текущих координат и
# направлений БПЛА, на карту не нужен.
MEMO_PATTERNS = [
    r'памятка при атаке',
    r'что делать при обнаружении бпла',
    r'собрали в памятке',
    r'информация была под рукой',
    r'куда укрыться',
    r'#\w*образовательн\w*',
]


def is_memo_post(text):
    """Памятка/инструкция по поведению при атаке (без локаций БПЛА)."""
    text_lower = text.lower()
    if _DIRECTION_KW_RE.search(text_lower):
        return False
    return any(re.search(pat, text_lower) for pat in MEMO_PATTERNS)


def closest_point_on_polygon(lat, lon, polygon_coords):
    """Find closest point on polygon boundary from (lat, lon)."""
    best_lat, best_lon = lat, lon
    best_dist = float('inf')
    if polygon_coords and isinstance(polygon_coords[0], list) and polygon_coords[0] and isinstance(polygon_coords[0][0], list) and isinstance(polygon_coords[0][0][0], list):
        rings = []
        for poly in polygon_coords:
            rings.extend(poly)
    else:
        rings = polygon_coords
    for ring in rings:
        for i in range(len(ring) - 1):
            x1, y1 = ring[i]
            x2, y2 = ring[i + 1]
            dx = x2 - x1
            dy = y2 - y1
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq == 0:
                continue
            px = lon - x1
            py = lat - y1
            t = max(0.0, min(1.0, (px * dx + py * dy) / seg_len_sq))
            cx = x1 + t * dx
            cy = y1 + t * dy
            d = (cx - lon) ** 2 + (cy - lat) ** 2
            if d < best_dist:
                best_dist = d
                best_lat = cy
                best_lon = cx
    return (best_lat, best_lon)


# Fixed state border points for regions where polygon's closest point
# falls on internal (oblast-to-oblast) boundary instead of international border.
# Key = region subject lowercase, value = (lat, lon)
STATE_BORDER_POINTS = {
    "курская область": (51.229707, 35.116505),
    "брянская область": (51.229707, 35.116505),
}


def find_border_point(region_name, src_lat, src_lon, geojson_lookup):
    """Find closest border point of region from source coordinates.
    Returns (lat, lon) or None."""
    rn = region_name.strip().lower()
    if rn in STATE_BORDER_POINTS:
        return STATE_BORDER_POINTS[rn]
    feat = find_geojson_feature(region_name, geojson_lookup)
    if not feat:
        return None
    geom = feat.get('geometry')
    if not geom:
        return None
    coords = geom.get('coordinates')
    if not coords:
        return None
    return closest_point_on_polygon(src_lat, src_lon, coords)


_REGION_DEST_KW = re.compile(r'\b(область|области|областью|областей|обл|'
                             r'край|края|'
                             r'республика|республики|республике|республику|республикой|'
                             r'округ|округе|ао)\b')


def process_posts(posts, geojson_lookup=None):
    all_markers = []
    filtered = 0
    msk = timezone(timedelta(hours=3))
    for post_item in posts:
        if isinstance(post_item, tuple):
            if len(post_item) == 4:
                post, display_text, source, dt = post_item
                post_time = dt.astimezone(msk).strftime('%d.%m.%Y %H:%M')
            elif len(post_item) == 3:
                post, source, dt = post_item
                display_text = post
                post_time = dt.astimezone(msk).strftime('%d.%m.%Y %H:%M')
            else:
                post, source = post_item
                display_text = post
                post_time = ""
        else:
            post, source = post_item, ""
            display_text = post
            post_time = ""
        # Normalize spacing: insert space before uppercase Cyrillic after lowercase (fixes concatenated text like "районТульская")
        post = re.sub(r'([а-яё])([А-ЯЁ])', r'\1 \2', post)
        display_text = re.sub(r'([а-яё])([А-ЯЁ])', r'\1 \2', display_text)
        original_post = sanitize_popup_text(display_text)
        # Replace newlines with spaces so multi-word patterns can match across lines
        post = re.sub(r'\n+', ' ', post)
        post = re.sub(r'\s+', ' ', post).strip()
        if "max.ru/join/" in post:
            filtered += 1
            continue
        if is_summary_post(post):
            filtered += 1
            continue
        if is_news_recap_post(post):
            filtered += 1
            continue
        if source == VRV_RADAR_CHANNEL and is_vrv_radar_reminder(post):
            filtered += 1
            continue
        if is_promo_spam_post(post):
            filtered += 1
            continue
        if is_memo_post(post):
            filtered += 1
            continue
        if "лпр" in source.lower() or "лпр" in post.lower():
            filtered += 1
            continue
        if "#сводка" in post.lower():
            filtered += 1
            continue
        if "радару требуется ваша поддержка" in post.lower():
            filtered += 1
            continue
        if re.search(r'ищем админ', post.lower()):
            filtered += 1
            continue
        post_type = classify_post(post)

        # Skip info-only posts with no threat description (just names without context)
        if post_type == "info":
            filtered += 1
            continue

        # Try direction parsing first
        dir_pairs = extract_directions(post, geojson_lookup=geojson_lookup)
        if dir_pairs:
            # Filter source locations by post region (avoids false rayon matches like Красногорский→Брянская when post mentions Марий Эл).
            # Uses explicit oblast/krai/republic mentions only — rayon patterns ("Каменский район"→Тульская/Воронежская) would
            # pollute the set and let wrong-region pairs through.
            _mentioned = get_mentioned_region_subjects(post)
            if _mentioned:
                # Fill-only источники (регионы из фразы «стык X и Y областей»)
                # упомянуты явно — не отсекаем их фильтром ложно-региональных пар
                _fp = [(s, d) for s, d in dir_pairs if s.get("_fill_only") or not s.get("subject") or s["subject"].strip().lower() in _mentioned]
                if _fp:
                    dir_pairs = _fp
            # Suppress region markers when a specific settlement exists in same subject+destination
            specific_srcs = set()
            for src, dst in dir_pairs:
                if not src.get("is_region"):
                    specific_srcs.add((src.get("subject", "").lower(), round(dst["lat"], 1), round(dst["lon"], 1)))
                # Rayon-level region sources suppress oblast-level for same subject+dst
                elif src.get("is_region") and "район" in src.get("matched", "").lower():
                    specific_srcs.add((src.get("subject", "").lower(), round(dst["lat"], 1), round(dst["lon"], 1)))
            seen_pairs = set()
            for src, dst in dir_pairs:
                # Skip region src if a specific settlement exists for same subject+destination
                # But do NOT skip rayon-level sources themselves (they are the more specific one)
                if src.get("is_region") and "район" not in src.get("matched", "").lower():
                    subj = src.get("subject", "").lower()
                    dst_key = (round(dst["lat"], 1), round(dst["lon"], 1))
                    if any(s_subj == subj and (s_lat, s_lon) == dst_key for s_subj, s_lat, s_lon in specific_srcs):
                        continue
                key = (round(src["lat"], 1), round(src["lon"], 1), round(dst["lat"], 1), round(dst["lon"], 1))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                # Region-only destination: point to border instead of capital
                # — only for oblast/krai/republic level, NOT rayon-level.
                # Skip when source is INSIDE the same region: the drones are moving
                # within the region (e.g. "от Погар, Почеп" → "Брянск, Брянская
                # область"), so the arrow must go to the city, not to the border.
                region_check_text = (dst.get("matched", "") + " " + dst.get("name", "") + " " + dst.get("subject", "")).lower()
                region_check_subject = dst.get("subject", "").lower().strip()
                _src_subj = (src.get("subject") or "").lower().strip()
                if dst.get("is_region") and "район" not in dst.get("matched", "").lower() and _src_subj != region_check_subject and (_REGION_DEST_KW.search(region_check_text) or region_check_subject in REGION_GEOJSON_MAP):
                    if geojson_lookup:
                        bp = find_border_point(region_check_subject, src["lat"], src["lon"], geojson_lookup)
                        if bp:
                            dst = {**dst, "lat": bp[0], "lon": bp[1], "name": dst.get("subject", dst["name"])}
                m = {
                    "lat": src["lat"], "lon": src["lon"],
                    "name": src["name"], "type": post_type,
                    "text": original_post[:5000] + ("..." if len(original_post) > 5000 else ""),
                    "source": source, "time": post_time,
                }
                # Fill-only источники (регионы из фразы «стык X и Y областей»)
                # остаются как заливка регионов, без стрелки
                if not src.get("_fill_only"):
                    m["direction"] = [dst["lat"], dst["lon"]]
                    m["dest_name"] = dst["name"]
                if src.get("is_region"):
                    m["is_region"] = True
                if src.get("subject"):
                    m["subject"] = src["subject"]
                if src.get("matched"):
                    m["matched"] = src["matched"]
                all_markers.append(m)
        else:
            # Split into sentences for per-sentence type classification
            # (posts often list multiple regions with different threat types)
            sentences = [s.strip() for s in re.split(r'[.!?]+(?=\s+[А-ЯЁA-Z0-9])(?!\s*[;,])\s*|[.!?]+(?=\s+[а-яё]\.\s*[А-ЯЁA-Z0-9])(?!\s*[;,])\s*', post) if len(s.strip()) > 3]
            # Pre-extract from full post for disambiguation context across sentences
            # (e.g. "Видное" as first line needs to see Crimea locations mentioned later)
            full_context = extract_locations(post)
            full_context = filter_locations_by_post_region(full_context, post)
            # Use post-level type as fallback for info sentences (e.g. "Рыбинск, Ярославская область. Фиксации БПЛА")
            for sentence in sentences:
                sent_type = classify_post(sentence)
                if sent_type == "info" and post_type != "info":
                    sent_type = post_type
                locations = extract_locations(sentence, extra_context=full_context)
                # Filter by oblast explicitly mentioned in the post to avoid false matches
                locations = filter_locations_by_post_region(locations, post)
                # Dedup locations in same sentence by proximity (< 5 km), keep longest name
                survivors = []
                for loc in locations:
                    dup = False
                    for i, existing in enumerate(survivors):
                        dlat = loc["lat"] - existing["lat"]
                        dlon = loc["lon"] - existing["lon"]
                        if (dlat * dlat + dlon * dlon) < 0.002:  # ~5 km at 58°N
                            existing_len = len(existing.get("matched", existing["name"]))
                            new_len = len(loc.get("matched", loc["name"]))
                            if new_len > existing_len:
                                survivors[i] = loc
                            dup = True
                            break
                    if not dup:
                        survivors.append(loc)
                # Suppress generic city markers when a more specific location exists in same subject
                _subj_groups = {}
                for s in survivors:
                    _ss = s.get("subject", "").lower().strip()
                    if not _ss:
                        continue
                    _subj_groups.setdefault(_ss, []).append(s)
                _drop_indices = set()
                for _ss, _group in _subj_groups.items():
                    _region_coords = set()
                    for s in _group:
                        if s.get("is_region"):
                            _region_coords.add((round(s["lat"], 4), round(s["lon"], 4)))
                    if not _region_coords:
                        continue
                    _all_coords = set()
                    for s in _group:
                        _all_coords.add((round(s["lat"], 4), round(s["lon"], 4)))
                    if len(_all_coords) < 2:
                        continue
                    for idx, s in enumerate(survivors):
                        if s.get("is_region") or s.get("subject", "").lower().strip() != _ss:
                            continue
                        if (round(s["lat"], 4), round(s["lon"], 4)) in _region_coords:
                            _drop_indices.add(idx)
                    # Also suppress capital region markers when a more specific location exists
                    for idx, s in enumerate(survivors):
                        if not s.get("is_region") or s.get("subject", "").lower().strip() != _ss:
                            continue
                        # Rayon-level markers ("Спасском районе"→Спасск-Дальний) are the
                        # specific location — never suppress them in favor of the capital
                        # (otherwise both Владивосток and Спасск-Дальний get dropped).
                        _mm = s.get("matched", "").lower()
                        if re.search(r'(район|районе|районы|р-н|р-не|р-ны)$', _mm) or re.search(r'\s(мо|го|ао)$', _mm):
                            continue
                        sc = (round(s["lat"], 4), round(s["lon"], 4))
                        for ck, cv in CITY_DB.items():
                            if cv.get("subject", "").lower().strip() == _ss:
                                if (round(cv["lat"], 4), round(cv["lon"], 4)) == sc:
                                    if any(oc != sc for oc in _all_coords):
                                        _drop_indices.add(idx)
                                    break
                survivors = [s for i, s in enumerate(survivors) if i not in _drop_indices]

                for loc in survivors:
                    marker = {
                        "lat": loc["lat"], "lon": loc["lon"],
                        "name": loc["name"], "type": sent_type,
                        "text": original_post[:5000] + ("..." if len(original_post) > 5000 else ""),
                        "source": source, "time": post_time,
                    }
                    if loc.get("is_region"):
                        marker["is_region"] = True
                    if loc.get("subject"):
                        marker["subject"] = loc["subject"]
                    if loc.get("matched"):
                        marker["matched"] = loc["matched"]
                    all_markers.append(marker)

    if filtered:
        print(f"  Отфильтровано {filtered} сводок/объявлений")
    return all_markers


def main():
    posts = []

    if len(sys.argv) > 1:
        input_text = " ".join(sys.argv[1:])
        print("Обработка текста из аргументов командной строки...")
        posts = [input_text]
    else:
        posts = fetch_all(hours_filter=HISTORY_FETCH_HOURS)
        if not posts:
            print("\nНе удалось загрузить посты, генерирую пустую карту...")
            posts = []

    print("Загрузка границ регионов...")
    geojson_lookup = load_region_geojson()

    all_markers = process_posts(posts, geojson_lookup=geojson_lookup)
    if not all_markers:
        print("Не найдено локаций, генерирую пустую карту...")
        all_markers = []

    history = load_region_history()
    history = update_region_history(all_markers, history)
    save_region_history(history)

    # Keep markers within per-type display windows
    now_msk = datetime.now(timezone(timedelta(hours=3)))
    display_markers = []
    for m in all_markers:
        m_type = m.get('type', 'info')
        hours = DISPLAY_HOURS.get(m_type, HOURS_FILTER)
        if parse_post_time(m.get('time', '')) >= now_msk - timedelta(hours=hours):
            display_markers.append(m)

    filename = generate_html(display_markers, geojson_lookup=geojson_lookup, history=history)
    abs_path = os.path.abspath(filename)
    print(f"\nСгенерирована карта: file://{abs_path}")
    print(f"Локаций на карте: {len(display_markers)}")
    # Открыть браузер только если есть дисплей (не в CI)
    import platform
    if platform.system() != 'Linux' or os.environ.get('DISPLAY'):
        webbrowser.open(f"file://{abs_path}")


if __name__ == "__main__":
    main()
