import requests
import json
import re
import os
import sys
import webbrowser
import time
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CITIES_FILE = os.path.join(BASE_DIR, "cities.json")

with open(CITIES_FILE, "r", encoding="utf-8") as f:
    cities_data = json.load(f)

CITY_DB = {}
for c in cities_data:
    name = c["name"].strip()
    CITY_DB[name.lower()] = {
        "lat": float(c["coords"]["lat"]),
        "lon": float(c["coords"]["lon"]),
        "name": name,
        "subject": c["subject"],
    }

def make_region_alias(alias, city_name, lat, lon, radius_km=60):
    ck = city_name.lower()
    if ck in CITY_DB:
        lat = CITY_DB[ck]["lat"]
        lon = CITY_DB[ck]["lon"]
    return {
        "pattern": alias.lower(),
        "name": city_name,
        "lat": lat,
        "lon": lon,
        "type": "region",
        "radius_km": radius_km,
    }


def make_region_alias_with_cases(alias, city_name, lat, lon, radius_km=60):
    """Generate region alias with common case variants."""
    result = [make_region_alias(alias, city_name, lat, lon, radius_km)]
    a = alias.lower()
    # область -> области (genitive)
    if a.endswith("ая область"):
        stem = a[:-10]
        result.append(make_region_alias(stem + "ой области", city_name, lat, lon, radius_km))
    elif a.endswith("ая обл"):
        stem = a[:-6]
        result.append(make_region_alias(stem + "ой обл", city_name, lat, lon, radius_km))
    elif a.endswith("ская область"):
        stem = a[:-12]
        result.append(make_region_alias(stem + "ской области", city_name, lat, lon, radius_km))
    elif a.endswith("ская обл"):
        stem = a[:-8]
        result.append(make_region_alias(stem + "ской обл", city_name, lat, lon, radius_km))
    # край -> края (genitive)
    elif a.endswith("ий край"):
        stem = a[:-7]
        result.append(make_region_alias(stem + "его края", city_name, lat, lon, radius_km))
    elif a.endswith("ский край"):
        stem = a[:-9]
        result.append(make_region_alias(stem + "ского края", city_name, lat, lon, radius_km))
    # округ -> округа
    elif a.endswith("ий округ"):
        stem = a[:-8]
        result.append(make_region_alias(stem + "его округа", city_name, lat, lon, radius_km))
    elif a.endswith("ский округ"):
        stem = a[:-10]
        result.append(make_region_alias(stem + "ского округа", city_name, lat, lon, radius_km))
    return result

REGION_ALIASES = [
    make_region_alias_with_cases("ростовская область", "Ростов-на-Дону", 47.2357, 39.7015),
    make_region_alias_with_cases("ростовская обл", "Ростов-на-Дону", 47.2357, 39.7015),
    make_region_alias_with_cases("московская область", "Москва", 55.7558, 37.6173, 30),
    make_region_alias_with_cases("московская обл", "Москва", 55.7558, 37.6173, 30),
    make_region_alias_with_cases("ленинградская область", "Санкт-Петербург", 59.9343, 30.3351, 35),
    make_region_alias_with_cases("ленинградская обл", "Санкт-Петербург", 59.9343, 30.3351, 35),
    make_region_alias_with_cases("краснодарский край", "Краснодар", 45.0355, 38.9753, 80),
    make_region_alias_with_cases("ставропольский край", "Ставрополь", 45.0448, 41.9692, 70),
    make_region_alias_with_cases("приморский край", "Владивосток", 43.1056, 131.8735, 100),
    make_region_alias_with_cases("хабаровский край", "Хабаровск", 48.4802, 135.0719, 120),
    make_region_alias_with_cases("алтайский край", "Барнаул", 53.3474, 83.7783, 80),
    make_region_alias_with_cases("забайкальский край", "Чита", 52.0333, 113.5, 100),
    make_region_alias_with_cases("камчатский край", "Петропавловск-Камчатский", 53.0167, 158.65, 150),
    make_region_alias_with_cases("пермский край", "Пермь", 58.0105, 56.2502, 80),
    make_region_alias("крым", "Симферополь", 44.9521, 34.1024),
    make_region_alias("республика крым", "Симферополь", 44.9521, 34.1024),
    make_region_alias("адыгея", "Майкоп", 44.6833, 40.1167),
    make_region_alias("республика адыгея", "Майкоп", 44.6833, 40.1167),
    make_region_alias("башкортостан", "Уфа", 54.7355, 55.9587),
    make_region_alias("республика башкортостан", "Уфа", 54.7355, 55.9587),
    make_region_alias("бурятия", "Улан-Удэ", 51.8333, 107.6),
    make_region_alias("республика бурятия", "Улан-Удэ", 51.8333, 107.6),
    make_region_alias("дагестан", "Махачкала", 42.9849, 47.5047),
    make_region_alias("республика дагестан", "Махачкала", 42.9849, 47.5047),
    make_region_alias("ингушетия", "Магас", 43.1688, 44.8168),
    make_region_alias("республика ингушетия", "Магас", 43.1688, 44.8168),
    make_region_alias("кабардино-балкария", "Нальчик", 43.4982, 43.6059),
    make_region_alias("кабардино-балкарская республика", "Нальчик", 43.4982, 43.6059),
    make_region_alias("калмыкия", "Элиста", 46.3082, 44.2558),
    make_region_alias("республика калмыкия", "Элиста", 46.3082, 44.2558),
    make_region_alias("карачаево-черкесская республика", "Черкесск", 44.2263, 42.0418),
    make_region_alias("карачаево-черкессия", "Черкесск", 44.2263, 42.0418),
    make_region_alias("карелия", "Петрозаводск", 61.7849, 34.3469),
    make_region_alias("республика карелия", "Петрозаводск", 61.7849, 34.3469),
    make_region_alias("коми", "Сыктывкар", 61.6688, 50.8361),
    make_region_alias("республика коми", "Сыктывкар", 61.6688, 50.8361),
    make_region_alias("марий эл", "Йошкар-Ола", 56.6344, 47.8999),
    make_region_alias("республика марий эл", "Йошкар-Ола", 56.6344, 47.8999),
    make_region_alias("мордовия", "Саранск", 54.1838, 45.1749),
    make_region_alias("республика мордовия", "Саранск", 54.1838, 45.1749),
    make_region_alias("якутия", "Якутск", 62.0355, 129.6755),
    make_region_alias("республика саха", "Якутск", 62.0355, 129.6755),
    make_region_alias("саха (якутия)", "Якутск", 62.0355, 129.6755),
    make_region_alias("северная осетия", "Владикавказ", 43.0205, 44.6819),
    make_region_alias("республика северная осетия", "Владикавказ", 43.0205, 44.6819),
    make_region_alias("татарстан", "Казань", 55.7961, 49.1064),
    make_region_alias("республика татарстан", "Казань", 55.7961, 49.1064),
    make_region_alias("тыва", "Кызыл", 51.7194, 94.4372),
    make_region_alias("удмуртия", "Ижевск", 56.8498, 53.2045),
    make_region_alias("удмуртская республика", "Ижевск", 56.8498, 53.2045),
    make_region_alias("хакасия", "Абакан", 53.7167, 91.4167),
    make_region_alias("республика хакасия", "Абакан", 53.7167, 91.4167),
    make_region_alias("чувашия", "Чебоксары", 56.1322, 47.2442),
    make_region_alias("чувашская республика", "Чебоксары", 56.1322, 47.2442),
    make_region_alias("чечня", "Грозный", 43.3125, 45.6947),
    make_region_alias("чеченская республика", "Грозный", 43.3125, 45.6947),
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
    make_region_alias_with_cases("рязанская область", "Рязань", 54.6095, 39.7126),
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
    make_region_alias_with_cases("тюменская область", "Тюмень", 57.1535, 65.5423, 100),
    make_region_alias_with_cases("херсонская область", "Херсон", 46.6354, 32.6169, 50),
    make_region_alias_with_cases("запорожская область", "Запорожье", 47.8388, 35.1396, 50),
    make_region_alias("днр", "Донецк", 48.0159, 37.8028),
    make_region_alias("лнр", "Луганск", 48.574, 39.3078),
    make_region_alias_with_cases("ямало-ненецкий автономный округ", "Салехард", 66.5300, 66.6019, 150),
    make_region_alias_with_cases("ханты-мансийский автономный округ", "Ханты-Мансийск", 61.0024, 69.0099, 120),
    make_region_alias_with_cases("чукотский автономный округ", "Анадырь", 64.7333, 177.5167, 150),
    make_region_alias_with_cases("еврейская автономная область", "Биробиджан", 48.7833, 132.9333, 40),
    make_region_alias_with_cases("ненецкий автономный округ", "Нарьян-Мар", 67.6385, 53.0067, 100),
]

ALL_PATTERNS = []
for entry in REGION_ALIASES:
    items = entry if isinstance(entry, list) else [entry]
    for r in items:
        ALL_PATTERNS.append((len(r["pattern"]), r["pattern"], r))

for name_lower, c in CITY_DB.items():
    ALL_PATTERNS.append((len(name_lower), name_lower, c))

ALL_PATTERNS.sort(key=lambda x: -x[0])

from datetime import datetime, timezone, timedelta


HOURS_FILTER = 8


CHANNELS = [
    {"url": "https://t.me/s/locatorru", "name": "locatorru"},
    {"url": "https://t.me/s/vrv_radar", "name": "vrv_radar"},
    {"url": "https://t.me/s/radarrussia", "name": "radarrussia"},
    {"url": "https://t.me/s/radarYR", "name": "radarYR"},
]


def clean_message_text(raw, channel=""):
    clean = re.sub(r'<[^>]+>', '', raw)
    clean = clean.replace('<br>', '\n').replace('<br/>', '\n').strip()
    clean = re.sub(r'\s+', ' ', clean)
    clean = re.split(r'📡', clean)[0].strip()
    clean = re.sub(r'@locatorru.*$', '', clean).strip()
    clean = re.sub(r'@locator_ru.*$', '', clean).strip()
    clean = re.sub(r'@vrv_radar.*$', '', clean).strip()
    clean = re.sub(r'@vrv_support.*$', '', clean).strip()
    clean = re.sub(r'@radarrussia.*$', '', clean).strip()
    clean = re.sub(r'@radarYR.*$', '', clean).strip()
    clean = re.sub(r'Радар по всей России.*$', '', clean).strip()
    clean = re.sub(r'Подписаться', '', clean).strip()
    clean = re.sub(r'[^\x20-\x7E\u0400-\u04FF\u0500-\u052F.,!?\-:;()ё№«»]+', ' ', clean)
    return clean.strip()


def fetch_channel(url, name):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_FILTER)
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
            if clean and len(clean) > 10:
                posts.append(clean)
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


def fetch_all():
    print("Загрузка постов из Telegram...")
    all_posts = []
    for ch in CHANNELS:
        posts = fetch_channel(ch["url"], ch["name"])
        all_posts.extend(posts)
    print(f"Всего загружено: {len(all_posts)} постов")
    return all_posts

WORD_CHARS = set("abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz0123456789абвгдеёжзийклмнопрстуфхцчшщъыьэюя")


def is_word_boundary(text, idx):
    if idx <= 0:
        return True
    return text[idx - 1] not in WORD_CHARS


def extract_locations(text):
    text_lower = text.lower()
    WORD_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
    matched_spans = set()
    results = []

    for _, pattern, entry in ALL_PATTERNS:
        if isinstance(entry, dict) and "type" in entry:
            name = entry["name"]
            lat = entry["lat"]
            lon = entry["lon"]
            ftype = entry["type"]
            radius_km = entry.get("radius_km")
        else:
            name = entry["name"]
            lat = entry["lat"]
            lon = entry["lon"]
            ftype = "city"
            radius_km = None

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

            is_overlap = any(
                not (end <= s_start or s_end <= idx)
                for s_start, s_end in matched_spans
            )
            if not is_overlap:
                matched_spans.add((idx, end))
                r = {"name": name, "lat": lat, "lon": lon,
                     "type": ftype, "matched": text[idx:end]}
                if radius_km is not None:
                    r["radius_km"] = radius_km
                results.append(r)
                break
            start = idx + 1

    unique = {}
    found_names = set()
    for r in results:
        name_key = r["name"].lower()
        coord_key = round(r["lat"], 1), round(r["lon"], 1)
        if name_key in found_names:
            continue
        found_names.add(name_key)
        unique[coord_key] = r
    return list(unique.values())


DIRECTION_SEPS = [
    r'\bв сторону\b',
    r'\bв направлении\b',
    r'\bнаправлении\b',
    '→', '➡️',
]


def extract_directions(text):
    """Extract source→destination pairs from posts containing direction phrases.
    Returns list of (source_loc, dest_loc) tuples.
    """
    # Split into sentences if multiple
    sentences = re.split(r'[.!\n]+', text)
    pairs = []
    cardinal = {"восток", "запад", "север", "юг", "юго-восток", "юго-запад",
                "северо-восток", "северо-запад"}

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

        sources = extract_locations(before)
        dests = extract_locations(after)

        for s in sources:
            for d in dests:
                if round(s["lat"], 1) == round(d["lat"], 1) and round(s["lon"], 1) == round(d["lon"], 1):
                    continue
                pairs.append((s, d))

    return pairs


def classify_post(text):
    text_lower = text.lower()
    if "отбой" in text_lower:
        return "clear"
    elif "ракетн" in text_lower:
        return "rocket"
    elif "уничтожен" in text_lower or "сбит" in text_lower or "перехват" in text_lower:
        return "interception"
    elif "отражени" in text_lower:
        return "interception"
    elif "опасность" in text_lower or "угроз" in text_lower:
        return "danger"
    elif "фиксаци" in text_lower:
        return "sighting"
    elif "внимание" in text_lower:
        return "attention"
    return "info"


def generate_html(posts_data, filename=None):
    if filename is None:
        filename = os.environ.get("OUTPUT_FILE", "mopedmap.html")
    markers_json = json.dumps(posts_data, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LocatorRU — Карта угроз</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #222; }}
#map {{ height: calc(100vh - 50px); width: 100%; }}
.header {{ height: 50px; display: flex; align-items: center; padding: 0 20px; background: #fff; border-bottom: 1px solid #ddd; gap: 10px; }}
.header h1 {{ font-size: 18px; color: #d32f2f; }}
.header .info {{ font-size: 13px; color: #777; margin-left: auto; }}
.legend {{ background: rgba(255, 255, 255, 0.95); padding: 12px 16px; border-radius: 10px; color: #333; font-size: 13px; border: 1px solid #ccc; }}
.legend i {{ width: 12px; height: 12px; display: inline-block; border-radius: 50%; margin-right: 6px; }}
.popup-text {{ font-size: 12px; max-height: 150px; overflow-y: auto; line-height: 1.4; }}
.popup-name {{ font-size: 15px; font-weight: bold; color: #d32f2f; margin-bottom: 4px; }}
.popup-source {{ color: #666; font-size: 11px; margin-top: 4px; }}
.dest-tooltip {{ background: #fff; border: 1px solid #ccc; color: #333; font-size: 11px; padding: 2px 6px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
</style>
</head>
<body>
<div class="header">
  <h1>&#x1F4E1; LocatorRU</h1>
  <span class="info">Угрозы БПЛА | {len(posts_data)} точек | {time.strftime('%d.%m.%Y %H:%M')}</span>
</div>
<div id="map"></div>
<script>
const map = L.map('map', {{ center: [55.0, 50.0], zoom: 4, zoomControl: true }});

L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
  subdomains: 'abcd',
  maxZoom: 19
}}).addTo(map);

const data = {markers_json};

// Always show Yaroslavl as a star marker
const YAROSLAVL_COORDS = [57.6261, 39.8845];
const defaultData = data.find(d => d.name === 'Ярославль');
if (!defaultData) {{
  data.push({{
    lat: YAROSLAVL_COORDS[0], lon: YAROSLAVL_COORDS[1],
    name: 'Ярославль', type: 'info',
    text: 'Постоянный маркер'
  }});
}}

const specialNames = ['Ярославль', 'Ярославская область'];
const isSpecial = (name) => specialNames.some(s => name.includes(s));

const styleMap = {{
  danger: {{ color: '#e94560', size: 14, glow: '#e94560' }},
  sighting: {{ color: '#f5a623', size: 12, glow: null }},
  clear: {{ color: '#4ade80', size: 12, glow: null }},
  attention: {{ color: '#a855f7', size: 12, glow: null }},
  interception: {{ color: '#f97316', size: 12, glow: '#f97316' }},
  rocket: {{ color: '#ef4444', size: 16, glow: '#ef4444' }},
  info: {{ color: '#60a5fa', size: 10, glow: null }}
}};

const bounds = [];
const seen = new Set();

const typeLabel = {{ danger: 'Опасность', sighting: 'Фиксация', clear: 'Отбой', attention: 'Внимание', interception: 'Перехват', rocket: 'Ракетная опасность' }};

const fillTypes = {{ danger: true, rocket: true, sighting: true, attention: true }};

data.forEach(item => {{
  if (item.type === 'info' && !isSpecial(item.name)) return;
  const key = item.lat.toFixed(1) + ',' + item.lon.toFixed(1);
  if (seen.has(key)) return;
  seen.add(key);

  // Draw fill circle for regions with active alerts
  if (item.radius_km && fillTypes[item.type]) {{
    L.circle([item.lat, item.lon], {{
      radius: item.radius_km * 1000,
      color: styleMap[item.type].color,
      fillColor: styleMap[item.type].color,
      fillOpacity: 0.15,
      weight: 1,
      opacity: 0.3
    }}).addTo(map);
  }}

  const special = isSpecial(item.name);
  const s = styleMap[item.type] || styleMap.info;
  const size = special ? s.size + 6 : s.size;
  const glow = s.glow ? `box-shadow:0 0 ${{s.size > 12 ? 10 : 6}}px ${{s.glow}};` : '';
  const border = special ? '3px solid #00f5ff' : '2px solid #333';
  const extraGlow = special ? 'box-shadow:0 0 16px #00f5ff;' : glow;
  const shape = special
    ? 'clip-path:polygon(50% 0%,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%);border-radius:0;'
    : 'border-radius:50%;';
  const html = `<div style="background:${{s.color}};width:${{size}}px;height:${{size}}px;border:${{border}};${{shape}}${{extraGlow}}"></div>`;

  const marker = L.marker([item.lat, item.lon], {{
    icon: L.divIcon({{ html, className: '', iconSize: [size + 8, size + 8] }})
  }}).addTo(map);

  let popupHtml = `<div class="popup-name">${{item.name}}</div><div class="popup-text">${{item.text}}</div><div class="popup-source">${{typeLabel[item.type] || item.type}}</div>`;
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
    color, weight: 1.5, opacity: 0.35, dashArray: '4, 6'
  }}).addTo(map);

  L.circleMarker(to, {{
    radius: 6, color, weight: 1.5, fill: false, dashArray: '2, 3', opacity: 0.5
  }}).addTo(map).bindTooltip(item.dest_name || '?', {{
    permanent: false, direction: 'top', offset: [0, -4],
    className: 'dest-tooltip'
  }});
}});

if (bounds.length > 0) {{
  map.fitBounds(bounds, {{ padding: [40, 40], maxZoom: 6 }});
}}

L.control({{ position: 'bottomright' }}).onAdd = function() {{
  const div = L.DomUtil.create('div', 'legend');
  div.innerHTML = '<b>Легенда</b><br>' +
    '<i style="background:#e94560"></i> Опасность<br>' +
    '<i style="background:#f5a623"></i> Фиксация<br>' +
    '<i style="background:#4ade80"></i> Отбой<br>' +
    '<i style="background:#a855f7"></i> Внимание<br>' +
    '<i style="background:#f97316"></i> Перехват<br>' +
    '<i style="background:#ef4444"></i> Ракетная опасность<br>' +
    '<hr style="border-color:#333;margin:6px 0">' +
    '<span style="display:inline-block;width:12px;height:12px;clip-path:polygon(50% 0%,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%);background:#333;border:2px solid #00f5ff;vertical-align:middle;margin-right:6px"></span> Ярославль и область' +
    '<br><span style="font-size:11px;color:#888">Заливка = область в опасности</span>';
  return div;
}}.addTo(map);
</script>
</body>
</html>"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    return os.path.abspath(filename)


SUMMARY_PATTERNS = [
    r'в период с.*дежурными средствами пво',
    r'средствами пво перехвачены и уничтожен',
    r'за прошедш\w+ ноч',
    r'за прошедш\w+ сутк',
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
]


def is_summary_post(text):
    text_lower = text.lower().strip()
    for pat in SUMMARY_PATTERNS:
        if re.search(pat, text_lower):
            return True
    return False


def process_posts(posts):
    all_markers = []
    filtered = 0
    for post in posts:
        if is_summary_post(post):
            filtered += 1
            continue
        post_type = classify_post(post)

        # Try direction parsing first
        dir_pairs = extract_directions(post)
        if dir_pairs:
            seen_pairs = set()
            for src, dst in dir_pairs:
                key = (round(src["lat"], 1), round(src["lon"], 1), round(dst["lat"], 1), round(dst["lon"], 1))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                m = {
                    "lat": src["lat"], "lon": src["lon"],
                    "name": src["name"], "type": post_type,
                    "text": post[:120] + ("..." if len(post) > 120 else ""),
                    "direction": [dst["lat"], dst["lon"]],
                    "dest_name": dst["name"],
                }
                if src.get("radius_km"):
                    m["radius_km"] = src["radius_km"]
                all_markers.append(m)
    else:
        locations = extract_locations(post)
        for loc in locations:
            marker = {
                "lat": loc["lat"], "lon": loc["lon"],
                "name": loc["name"], "type": post_type,
                "text": post[:120] + ("..." if len(post) > 120 else ""),
            }
            if loc.get("radius_km"):
                marker["radius_km"] = loc["radius_km"]
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
        posts = fetch_all()
        if not posts:
            print("\nНе удалось загрузить посты автоматически.")
            print("Возможные причины:")
            print("  - Telegram заблокирован в вашей сети")
            print("  - Нет доступа к t.me")
            print("\nВы можете:")
            print("  1. Ввести текст вручную (просто добавьте текст в аргументы)")
            print("  2. Запустить с параметром: python locator_map.py \"ваш текст здесь\"")
            print("\nПример: python locator_map.py \"Курская область - опасность по БПЛА. Брянская область - фиксации.\"")
            return

    all_markers = process_posts(posts)

    if not all_markers:
        print("Не найдено локаций в тексте")
        return

    filename = generate_html(all_markers)
    abs_path = os.path.abspath(filename)
    print(f"\nСгенерирована карта: file://{abs_path}")
    print(f"Локаций на карте: {len(all_markers)}")
    # Открыть браузер только если есть дисплей (не в CI)
    import platform
    if platform.system() != 'Linux' or os.environ.get('DISPLAY'):
        webbrowser.open(f"file://{abs_path}")


if __name__ == "__main__":
    main()
