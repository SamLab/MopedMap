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

def make_region_alias(alias, city_name, lat, lon, subject=None):
    ck = city_name.lower()
    if ck in CITY_DB:
        lat = CITY_DB[ck]["lat"]
        lon = CITY_DB[ck]["lon"]
    result = {
        "pattern": alias.lower(),
        "name": city_name,
        "lat": lat,
        "lon": lon,
        "type": "region",
        "is_region": True,
    }
    if subject:
        result["subject"] = subject
    return result


def make_region_alias_with_cases(alias, city_name, lat, lon, subject=None):
    """Generate region alias with common case variants and bare adjective form."""
    result = [make_region_alias(alias, city_name, lat, lon, subject)]
    a = alias.lower()
    # область -> области (genitive)
    if a.endswith("ая область"):
        stem = a[:-10]
        result.append(make_region_alias(stem + "ой области", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ая", city_name, lat, lon, subject))
    elif a.endswith("ая обл"):
        stem = a[:-6]
        result.append(make_region_alias(stem + "ой обл", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ая", city_name, lat, lon, subject))
    elif a.endswith("ская область"):
        stem = a[:-12]
        result.append(make_region_alias(stem + "ской области", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ская", city_name, lat, lon, subject))
    elif a.endswith("ская обл"):
        stem = a[:-8]
        result.append(make_region_alias(stem + "ской обл", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ская", city_name, lat, lon, subject))
    # край -> края (genitive)
    elif a.endswith("ий край"):
        stem = a[:-7]
        result.append(make_region_alias(stem + "его края", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ий", city_name, lat, lon, subject))
    elif a.endswith("ский край"):
        stem = a[:-9]
        result.append(make_region_alias(stem + "ского края", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ский", city_name, lat, lon, subject))
    # округ -> округа
    elif a.endswith("ий округ"):
        stem = a[:-8]
        result.append(make_region_alias(stem + "его округа", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ий", city_name, lat, lon, subject))
    elif a.endswith("ский округ"):
        stem = a[:-10]
        result.append(make_region_alias(stem + "ского округа", city_name, lat, lon, subject))
        result.append(make_region_alias(stem + "ский", city_name, lat, lon, subject))
    return result

REGION_ALIASES = [
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
    {"pattern": "коммунар", "name": "Коммунар", "lat": 51.13, "lon": 35.72, "type": "region", "is_region": True, "subject": "Курская область"},
    {"pattern": "никольское", "name": "Никольское", "lat": 52.88, "lon": 36.38, "type": "region", "is_region": True, "subject": "Орловская область"},
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
    make_region_alias_with_cases("ленинградская область", "Санкт-Петербург", 59.9343, 30.3351, subject="Ленинградская область"),
    make_region_alias_with_cases("ленинградская обл", "Санкт-Петербург", 59.9343, 30.3351, subject="Ленинградская область"),
    make_region_alias_with_cases("краснодарский край", "Краснодар", 45.0355, 38.9753),
    make_region_alias_with_cases("ставропольский край", "Ставрополь", 45.0448, 41.9692),
    make_region_alias_with_cases("приморский край", "Владивосток", 43.1056, 131.8735),
    make_region_alias_with_cases("хабаровский край", "Хабаровск", 48.4802, 135.0719),
    make_region_alias_with_cases("алтайский край", "Барнаул", 53.3474, 83.7783),
    make_region_alias_with_cases("забайкальский край", "Чита", 52.0333, 113.5),
    make_region_alias_with_cases("камчатский край", "Петропавловск-Камчатский", 53.0167, 158.65),
    make_region_alias_with_cases("пермский край", "Пермь", 58.0105, 56.2502),
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
    make_region_alias_with_cases("тюменская область", "Тюмень", 57.1535, 65.5423),
    make_region_alias_with_cases("херсонская область", "Херсон", 46.6354, 32.6169),
    make_region_alias_with_cases("запорожская область", "Запорожье", 47.8388, 35.1396),
    make_region_alias("днр", "Донецк", 48.0159, 37.8028),
    make_region_alias("лнр", "Луганск", 48.574, 39.3078),
    make_region_alias_with_cases("ямало-ненецкий автономный округ", "Салехард", 66.5300, 66.6019),
    make_region_alias_with_cases("ханты-мансийский автономный округ", "Ханты-Мансийск", 61.0024, 69.0099),
    make_region_alias_with_cases("чукотский автономный округ", "Анадырь", 64.7333, 177.5167),
    make_region_alias_with_cases("еврейская автономная область", "Биробиджан", 48.7833, 132.9333),
    make_region_alias_with_cases("ненецкий автономный округ", "Нарьян-Мар", 67.6385, 53.0067),
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


HOURS_FILTER = 4


CHANNELS = [
    {"url": "https://t.me/s/locatorru", "name": "locatorru"},
    {"url": "https://t.me/s/vrv_radar", "name": "vrv_radar"},

    {"url": "https://t.me/s/radarrussiia", "name": "radarrussiia"},
    {"url": "https://t.me/s/radarYR", "name": "radarYR"},
    {"url": "https://t.me/s/russiamonitoring_radar_bpla", "name": "russiamonitoring_radar_bpla"},
    {"url": "https://t.me/s/radar_rossia_bpla", "name": "radar_rossia_bpla"},
    {"url": "https://t.me/s/radar_yaroslavl", "name": "radar_yaroslavl"},
    {"url": "https://t.me/s/radar_yar76", "name": "radar_yar76"},
    {"url": "https://t.me/s/radarr_yar", "name": "radarr_yar"},
]


def clean_message_text(raw, channel=""):
    clean = raw.replace('<br>', '\n').replace('<br/>', '\n')
    clean = re.sub(r'<[^>]+>', ' ', clean).strip()
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
    clean = re.sub(r'Радар по всей России.*$', '', clean).strip()
    clean = re.sub(r'мониторинг\.ру\s*$', '', clean).strip()
    clean = re.sub(r'Подписаться', '', clean).strip()
    clean = re.sub(r'[^\x20-\x7E\u0400-\u04FF\u0500-\u052F.,!?\-:;()ё№«»]+', ' ', clean)
    clean = re.sub(r'Мониторинг\.РФ\s*\|\s*Мы в MAX', '', clean).strip()
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
                posts.append((clean, name, dt))
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

            is_overlap = any(
                not (end <= s_start or s_end <= idx)
                for s_start, s_end in matched_spans
            )
            if not is_overlap:
                matched_spans.add((idx, end))
                r = {"name": name, "lat": lat, "lon": lon,
                     "type": ftype, "matched": text[idx:end]}
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
    if "отбой" in text_lower or "по обстановке тихо" in text_lower:
        return "clear"
    elif "ракетн" in text_lower:
        return "rocket"
    elif "уничтожен" in text_lower or "сбит" in text_lower or "перехват" in text_lower or "пво" in text_lower:
        return "interception"
    elif "отражени" in text_lower:
        return "interception"
    elif "авиацион" in text_lower and "бпла" not in text_lower and "беспилот" not in text_lower:
        return "aviation"
    elif "меры безопасности" in text_lower or "пуск" in text_lower or "опасность" in text_lower or ("угроз" in text_lower and "в случае" not in text_lower):
        return "danger"
    elif "фиксаци" in text_lower and "не наблюда" in text_lower:
        return "clear"
    elif "фиксаци" in text_lower or "пролёт" in text_lower or "группа" in text_lower:
        return "sighting"
    elif "внимание" in text_lower:
        return "attention"
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
    try:
        r = requests.get(GEOJSON_URL, timeout=60)
        data = r.json()
    except Exception:
        print("  Не удалось загрузить GeoJSON регионов")
        return {}
    lookup = {}
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
    return lookup


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
    'чувашия': 'чувашская республика - чувашия',
    'чечня': 'чеченская республика',
    'ханты-мансийский автономный округ': 'ханты-мансийский автономный округ - югра',
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
    return None


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
        key = (m['name'].lower().strip(), round(m['lat'], 1), round(m['lon'], 1), m.get('is_region', False), m.get('type', 'info'))
        existing = seen.get(key)
        if existing:
            if parse_post_time(m.get('time', '')) > parse_post_time(existing.get('time', '')):
                seen[key] = m
        else:
            seen[key] = m
    return list(seen.values())


def generate_html(posts_data, filename=None, geojson_lookup=None):
    if filename is None:
        filename = os.environ.get("OUTPUT_FILE", "mopedmap.html")
    # Keep only the latest post per city
    posts_data = dedup_markers(posts_data)
    # Extract region geometries for active fill types
    # Map city name -> region name via CITY_DB subject field
    region_map = {}  # region_name_lower -> feature
    type_priority = {'rocket': 0, 'danger': 1, 'aviation': 2, 'attention': 4}
    for item in posts_data:
        is_region = item.get('is_region', False)
        item_type = item.get('type')
        if is_region and item_type in type_priority:
            city_name = item.get('name', '').lower().strip()
            region_name = item.get('subject', '').lower().strip() if item.get('subject') else None
            if not region_name and city_name in CITY_DB:
                region_name = CITY_DB[city_name].get('subject', '').lower().strip()
            if region_name and geojson_lookup:
                existing = region_map.get(region_name)
                if existing:
                    existing_time = existing['properties'].get('popup_time', '')
                    if parse_post_time(item.get('time', '')) <= parse_post_time(existing_time):
                        continue
                feat = find_geojson_feature(region_name, geojson_lookup)
                if feat:
                    feat_copy = json.loads(json.dumps(feat))
                    feat_copy['properties']['alert_type'] = item_type
                    feat_copy['properties']['popup_name'] = item.get('name', '')
                    feat_copy['properties']['popup_text'] = item.get('text', '')
                    feat_copy['properties']['popup_source'] = item.get('source', '')
                    feat_copy['properties']['popup_time'] = item.get('time', '')
                    region_map[region_name] = feat_copy
                # Also fill city-level polygon if different from region (e.g. Москва & Московская область)
                if city_name != region_name:
                    city_feat = find_geojson_feature(city_name, geojson_lookup)
                    if city_feat and city_name not in region_map:
                        city_copy = json.loads(json.dumps(city_feat))
                        city_copy['properties']['alert_type'] = item_type
                        city_copy['properties']['popup_name'] = item.get('name', '')
                        city_copy['properties']['popup_text'] = item.get('text', '')
                        city_copy['properties']['popup_source'] = item.get('source', '')
                        city_copy['properties']['popup_time'] = item.get('time', '')
                        region_map[city_name] = city_copy
    # Mark items that should not render a point marker
    always_show = {'sighting', 'clear', 'interception'}
    for item in posts_data:
        if item.get('is_region') and item.get('type') not in always_show:
            rn = item.get('subject', '').lower().strip() if item.get('subject') else None
            if not rn:
                city_name = item.get('name', '').lower().strip()
                if city_name in CITY_DB:
                    rn = CITY_DB[city_name].get('subject', '').lower().strip()
            if rn and rn in region_map:
                item['no_marker'] = True

    # Priority at same coordinates
    coord_items = {}
    for item in posts_data:
        key = (round(item.get('lat', 0), 1), round(item.get('lon', 0), 1))
        coord_items.setdefault(key, []).append(item)
    for key, items in coord_items.items():
        types = {it.get('type') for it in items}
        # clear vs any threat: keep only the newer one
        threat_types = {'danger', 'rocket', 'aviation', 'interception', 'sighting', 'attention'}
        if 'clear' in types and types & threat_types:
            clear_items = [it for it in items if it.get('type') == 'clear']
            threat_items = [it for it in items if it.get('type') in threat_types]
            latest_clear = max(parse_post_time(it.get('time', '')) for it in clear_items)
            latest_threat = max(parse_post_time(it.get('time', '')) for it in threat_items)
            if latest_clear >= latest_threat:
                for it in threat_items:
                    it['no_marker'] = True; it['cleared'] = True  # clear newer → clear wins
            else:
                for it in clear_items:
                    it['no_marker'] = True  # threat newer → threat wins
        # interception hides sighting
        if 'interception' in types and 'sighting' in types:
            for it in items:
                if it.get('type') == 'sighting':
                    it['no_marker'] = True; it['cleared'] = True
        # sighting hides danger/attention
        if 'sighting' in types:
            for it in items:
                if it.get('type') in ('danger', 'attention'):
                    it['no_marker'] = True; it['cleared'] = True
        # danger vs interception: within 1h → interception wins; 1h+ older → danger wins
        if 'danger' in types and 'interception' in types:
            danger_items = [it for it in items if it.get('type') == 'danger']
            int_items = [it for it in items if it.get('type') == 'interception']
            latest_danger = max(parse_post_time(it.get('time', '')) for it in danger_items)
            latest_int = max(parse_post_time(it.get('time', '')) for it in int_items)
            diff = (latest_danger - latest_int).total_seconds()
            if diff >= 3600:
                for it in int_items:
                    it['no_marker'] = True; it['cleared'] = True  # interception 1h+ older → danger wins
            else:
                for it in danger_items:
                    it['no_marker'] = True; it['cleared'] = True  # within 1h → interception wins

    # Clear region fills where clear is newer than the fill → keep polygon but show clear popup
    # Only clear fills matching the threat type mentioned in the clear text
    for item in posts_data:
        if item.get('type') == 'clear' and not item.get('no_marker'):
            clear_text = item.get('text', '').lower()
            if 'ракетн' in clear_text:
                clear_types = {'rocket'}
            elif 'бпла' in clear_text:
                clear_types = {'danger', 'attention', 'aviation'}
            else:
                clear_types = {'rocket', 'danger', 'aviation', 'attention'}
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
                        region_map[rn]['properties']['alert_type'] = 'clear'
                        region_map[rn]['properties']['popup_name'] = item.get('name', '')
                        region_map[rn]['properties']['popup_text'] = item.get('text', '')
                        region_map[rn]['properties']['popup_source'] = item.get('source', '')
                        region_map[rn]['properties']['popup_time'] = item.get('time', '')
            # Also clear city-level polygon fill
            cn = item.get('name', '').lower().strip()
            if cn in region_map:
                at = region_map[cn]['properties'].get('alert_type', '')
                if at in clear_types:
                    fill_time = region_map[cn]['properties'].get('popup_time', '')
                    if parse_post_time(item.get('time', '')) >= parse_post_time(fill_time):
                        region_map[cn]['properties']['alert_type'] = 'clear'
                        region_map[cn]['properties']['popup_name'] = item.get('name', '')
                        region_map[cn]['properties']['popup_text'] = item.get('text', '')
                        region_map[cn]['properties']['popup_source'] = item.get('source', '')
                    region_map[cn]['properties']['popup_time'] = item.get('time', '')

    markers_json = json.dumps(posts_data, ensure_ascii=False)

    region_features = list(region_map.values())
    region_geojson = json.dumps({'type': 'FeatureCollection', 'features': region_features}, ensure_ascii=False)

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
@keyframes pulse-ring {{
  0% {{ transform: scale(1); opacity: 0.4; }}
  50% {{ transform: scale(2.5); opacity: 0.1; }}
  100% {{ transform: scale(1); opacity: 0.4; }}
}}
.pulse-ring {{
  width: 30px; height: 30px; border-radius: 50%;
  border: 3px solid var(--pulse-color, #00f5ff);
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  animation: pulse-ring 2s ease-in-out infinite;
  pointer-events: none;
}}
.header {{ min-height: 60px; display: flex; align-items: center; padding: 8px 12px; background: #fff; border-bottom: 1px solid #ddd; gap: 6px; flex-wrap: wrap; overflow: hidden; }}
.header h1 {{ font-size: 15px; color: #d32f2f; white-space: nowrap; }}
.header .info {{ font-size: 11px; color: #777; margin-left: auto; }}
.legend {{ background: rgba(255, 255, 255, 0.95); padding: 12px 16px; border-radius: 10px; color: #333; font-size: 13px; border: 1px solid #ccc; }}
.legend i {{ width: 12px; height: 12px; display: inline-block; border-radius: 50%; margin-right: 6px; }}
.popup-text {{ font-size: 12px; max-height: 250px; overflow-y: auto; line-height: 1.4; word-break: break-word; }}
.leaflet-popup-content {{ max-width: 380px !important; }}
.popup-name {{ font-size: 15px; font-weight: bold; color: #d32f2f; margin-bottom: 4px; }}
.popup-source {{ color: #666; font-size: 11px; margin-top: 4px; }}
.dest-tooltip {{ background: #fff; border: 1px solid #ccc; color: #333; font-size: 11px; padding: 2px 6px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
@media (max-width:600px) {{ .header {{ font-size: 12px; }} .info {{ font-size: 10px; }} .header h1 {{ font-size: 13px; }} #dist-info {{ font-size: 11px !important; }} }}

</style>
</head>
<body>
<div class="header">
  <h1>&#x1F4E1; YarLocator <span id="dist-info" style="font-size:12px;color:#d32f2f;font-weight:normal"></span></h1>
  <span class="info">Угрозы БПЛА | {len(posts_data)} точек | {(datetime.now(timezone.utc) + timedelta(hours=3)).strftime('%d.%m.%Y %H:%M')} МСК</span>
</div>
<div id="map"></div>
<div class="footer">
  <span class="dot" style="color:#e94560">●</span> Опасность БПЛА
  <span class="dot" style="color:#06b6d4">●</span> Авиационная опасность
  <span style="color:#000000;font-size:13px">▲</span> Фиксация
  <span class="dot" style="color:#eab308">●</span> Внимание
  <span style="color:#000000;font-size:14px;font-weight:bold">✕</span> Перехват
  <span class="dot" style="color:#a855f7">●</span> Ракетная опасность
  <span class="dot" style="color:#4ade80">●</span> Отбой
  <span class="dot" style="color:#60a5fa">●</span> Инфо
  <span style="margin-left:auto;color:#999">Обновление каждые 5 мин · данные за 4 часа</span>
</div>
<script>
const map = L.map('map', {{ center: [54.6095, 39.7126], zoom: 6, zoomControl: true, attributionControl: false }});

L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
  subdomains: 'abcd',
  maxZoom: 19
}}).addTo(map);

L.control.attribution({{ prefix: false }}).addTo(map);

const data = {markers_json};

// Always show Yaroslavl as a star marker at Luchinskoye
const YAROSLAVL_COORDS = [57.552927, 39.850605];
data.push({{
  lat: YAROSLAVL_COORDS[0], lon: YAROSLAVL_COORDS[1],
  name: 'Ярославль', type: 'info',
  text: 'Постоянный маркер', source: '', time: ''
}});

const specialNames = ['Ярославль', 'Ярославская область'];
const isSpecial = (name) => specialNames.some(s => name.includes(s));

const styleMap = {{
  danger: {{ color: '#e94560', size: 14, glow: '#e94560' }},
  aviation: {{ color: '#06b6d4', size: 14, glow: '#06b6d4' }},
  sighting: {{ color: '#000000', size: 12, glow: null }},
  clear: {{ color: '#4ade80', size: 12, glow: null }},
  attention: {{ color: '#eab308', size: 12, glow: null }},
  interception: {{ color: '#000000', size: 12, glow: null }},
  rocket: {{ color: '#a855f7', size: 16, glow: '#a855f7' }},
  info: {{ color: '#60a5fa', size: 10, glow: null }}
}};

const bounds = [];

const typeLabel = {{ danger: 'Опасность БПЛА', aviation: 'Авиационная опасность', sighting: 'Фиксация', clear: 'Отбой', attention: 'Внимание', interception: 'Перехват', rocket: 'Ракетная опасность' }};

const regionGeoJSON = {region_geojson};

// Draw region polygon fills
L.geoJSON(regionGeoJSON, {{
  style: function(feature) {{
    const alertType = feature.properties.alert_type || 'danger';
    const s = styleMap[alertType] || styleMap.danger;
    return {{
      color: s.color, fillColor: s.color,
      fillOpacity: alertType === 'clear' ? 0 : 0.15,
      weight: 1, opacity: alertType === 'clear' ? 0.5 : 0.3
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

// Check if Yaroslavl has active threats (for star pulse animation)
const yaroslavlHasThreat = data.some(d =>
  isSpecial(d.name) && d.text !== 'Постоянный маркер' && !d.cleared &&
  ['danger', 'rocket', 'aviation', 'attention'].includes(d.type)
);

data.forEach(item => {{
  if (item.type === 'info' && !isSpecial(item.name)) return;
  const special = isSpecial(item.name);
  const s = styleMap[item.type] || styleMap.info;

  if (item.no_marker) return;
  // For Yaroslavl: skip plain circle marker for danger/attention/clear/info; keep distinctive ones
  if (special && item.text !== 'Постоянный маркер' && !['sighting','interception','rocket','aviation'].includes(item.type)) return;

  const size = special ? s.size + 6 : s.size;
  const glow = s.glow ? `box-shadow:0 0 ${{s.size > 12 ? 10 : 6}}px ${{s.glow}};` : '';
  const border = special ? '3px solid #00f5ff' : '2px solid #333';
  const extraGlow = special ? 'box-shadow:0 0 16px #00f5ff;' : glow;
  const starPulse = (special && item.text === 'Постоянный маркер' && yaroslavlHasThreat) ? 'animation:pulse-ring 2s ease-in-out infinite;' : '';
  const shape = special
    ? 'clip-path:polygon(50% 0%,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%);border-radius:0;'
    : item.type === 'sighting'
      ? 'clip-path:polygon(50% 0%,100% 100%,0% 100%);border-radius:0;'
      : 'border-radius:50%;';
  const html = item.type === 'interception'
    ? `<div style="background:${{s.color}};width:${{size}}px;height:${{size}}px;border:${{border}};border-radius:2px;${{extraGlow}};display:flex;align-items:center;justify-content:center"><span style="color:#fff;font-size:${{size-4}}px;font-weight:bold;line-height:1">✕</span></div>`
    : `<div style="background:${{s.color}};width:${{size}}px;height:${{size}}px;border:${{border}};${{shape}}${{extraGlow}}${{starPulse}}"></div>`;

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
    color, weight: 1.5, opacity: 0.35, dashArray: '4, 6'
  }}).addTo(map);

  L.circleMarker(to, {{
    radius: 6, color, weight: 1.5, fill: false, dashArray: '2, 3', opacity: 0.5
  }}).addTo(map).bindTooltip(item.dest_name || '?', {{
    permanent: false, direction: 'top', offset: [0, -4],
    className: 'dest-tooltip'
  }}).bindPopup('<div class="popup-name">' + (item.dest_name || '?') + '</div><div class="popup-text">' + (item.text || '') + '</div><div class="popup-source">' + (typeLabel[item.type] || item.type || '') + (item.source ? ' · ' + item.source : '') + (item.time ? ' · ' + item.time : '') + ' → ' + item.name + '</div>');
}});

if (bounds.length > 0) {{
  map.setView([54.6095, 39.7126], 6);
}}

// Closest threat to Yaroslavl
const yarLatLng = L.latLng(YAROSLAVL_COORDS);
let minDist = Infinity;
let closestName = '';
let closestTime = '';
data.forEach(item => {{
  if (item.type === 'danger' || item.type === 'rocket' || item.type === 'aviation' || item.type === 'attention') {{
    if (!item.cleared) {{
      const d = map.distance(yarLatLng, [item.lat, item.lon]);
      if (d < minDist) {{ minDist = d; closestName = item.name; closestTime = item.time; }}
    }}
  }}
}});
if (minDist < Infinity) {{
  const distKm = (minDist / 1000).toFixed(0);
  let ago = '';
  if (closestTime) {{
    const [dd, mm, yyyy, hh, mi] = closestTime.match(/(\\d+)/g);
    const postDate = new Date(+yyyy, +mm - 1, +dd, +hh, +mi);
    const mins = Math.round((Date.now() - postDate) / 60000);
    if (mins > 0) ago = `, ${{mins}} мин назад`;
  }}
  document.getElementById('dist-info').textContent = `ближайшая опасность: ${{distKm}} км (${{closestName}}${{ago}})`;
}}

L.control({{ position: 'bottomright' }}).onAdd = function() {{
  const div = L.DomUtil.create('div', 'legend');
  div.innerHTML = '<b>Легенда</b><br>' +
    '<i style="background:#e94560"></i> Опасность БПЛА<br>' +
    '<i style="background:#06b6d4"></i> Авиационная опасность<br>' +
    '<i style="background:#f5a623"></i> Фиксация<br>' +
    '<i style="background:#4ade80"></i> Отбой<br>' +
    '<i style="background:#eab308"></i> Внимание<br>' +
    '<i style="background:#f97316"></i> Перехват<br>' +
    '<i style="background:#a855f7"></i> Ракетная опасность<br>' +
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
    r'впервые регионы.*подверглись массовым ракетным атакам',
    r'создать специальные каналы для информирования',
    r'каналы будут работать даже без мобильной связи',
    r'найти свой город и подписаться',
    r'по всей территории рф может быть объявлен режим',
    r'чрезвычайного положения',
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
    msk = timezone(timedelta(hours=3))
    for post_item in posts:
        if isinstance(post_item, tuple):
            if len(post_item) == 3:
                post, source, dt = post_item
                post_time = dt.astimezone(msk).strftime('%d.%m.%Y %H:%M')
            else:
                post, source = post_item
                post_time = ""
        else:
            post, source = post_item, ""
            post_time = ""
        # Normalize spacing: insert space before uppercase Cyrillic after lowercase (fixes concatenated text like "районТульская")
        post = re.sub(r'([а-яё])([А-ЯЁ])', r'\1 \2', post)
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
                    "text": post[:300] + ("..." if len(post) > 300 else ""),
                    "direction": [dst["lat"], dst["lon"]],
                    "dest_name": dst["name"],
                    "source": source, "time": post_time,
                }
                if src.get("is_region"):
                    m["is_region"] = True
                if src.get("subject"):
                    m["subject"] = src["subject"]
                all_markers.append(m)
        else:
            locations = extract_locations(post)
            for loc in locations:
                marker = {
                    "lat": loc["lat"], "lon": loc["lon"],
                    "name": loc["name"], "type": post_type,
                    "text": post[:300] + ("..." if len(post) > 300 else ""),
                    "source": source, "time": post_time,
                }
                if loc.get("is_region"):
                    marker["is_region"] = True
                if loc.get("subject"):
                    marker["subject"] = loc["subject"]
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
            print("\nНе удалось загрузить посты, генерирую пустую карту...")
            posts = []
    all_markers = process_posts(posts)
    if not all_markers:
        print("Не найдено локаций, генерирую пустую карту...")
        all_markers = []

    print("Загрузка границ регионов...")
    geojson_lookup = load_region_geojson()

    filename = generate_html(all_markers, geojson_lookup=geojson_lookup)
    abs_path = os.path.abspath(filename)
    print(f"\nСгенерирована карта: file://{abs_path}")
    print(f"Локаций на карте: {len(all_markers)}")
    # Открыть браузер только если есть дисплей (не в CI)
    import platform
    if platform.system() != 'Linux' or os.environ.get('DISPLAY'):
        webbrowser.open(f"file://{abs_path}")


if __name__ == "__main__":
    main()
