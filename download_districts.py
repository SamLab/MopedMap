import json, os, urllib.request, sys
from collections import OrderedDict

REGIONS = OrderedDict([
    ("Ярославская область", ("CFO", "Ярославская область_Yaroslavl region.geojson")),
    ("Московская область", ("CFO", "Московская область_Moscow Region.geojson")),
    ("Белгородская область", ("CFO", "Белгородская область_Belgorod region.geojson")),
    ("Курская область", ("CFO", "Курская область_Kursk region.geojson")),
    ("Воронежская область", ("CFO", "Воронежская область_Voronezh region.geojson")),
    ("Брянская область", ("CFO", "Брянская область_Bryansk region.geojson")),
    ("Смоленская область", ("CFO", "Смоленская область_Smolensk region.geojson")),
    ("Калужская область", ("CFO", "Калужская область_Kaluga region.geojson")),
    ("Тульская область", ("CFO", "Тульская область_Tula region.geojson")),
    ("Липецкая область", ("CFO", "Липецкая область_Lipetsk region.geojson")),
    ("Тамбовская область", ("CFO", "Тамбовская область_Tambov region.geojson")),
    ("Орловская область", ("CFO", "Орловская область_Orel region.geojson")),
    ("Рязанская область", ("CFO", "Рязанская область_Ryazan region.geojson")),
    ("Владимирская область", ("CFO", "Владимирская область_Vladimir region.geojson")),
    ("Ивановская область", ("CFO", "Ивановская область_Ivanovo region.geojson")),
    ("Костромская область", ("CFO", "Костромская область_Kostroma region.geojson")),
    ("Тверская область", ("CFO", "Тверская область_Tver region.geojson")),
    ("Ленинградская область", ("SZFO", "Ленинградская область_Leningrad region.geojson")),
    ("Псковская область", ("SZFO", "Псковская область_Pskov region.geojson")),
    ("Новгородская область", ("SZFO", "Новгородская область_Novgorod region.geojson")),
    ("Вологодская область", ("SZFO", "Вологодская область_Vologda region.geojson")),
    ("Нижегородская область", ("PFO", "Нижегородская область_Nizhny Novgorod Region.geojson")),
    ("Краснодарский край", ("YUFO", "Краснодарский край_Krasnodar region.geojson")),
    ("Ростовская область", ("YUFO", "Ростовская область_Rostov region.geojson")),
    ("Республика Крым", ("Crimea", "Республика Крым_Crimea Republic.geojson")),
])

def simplify_coords(coords, precision=4):
    if isinstance(coords, list):
        if len(coords) > 0 and isinstance(coords[0], (int, float)):
            return [round(coords[0], precision), round(coords[1], precision)]
        return [simplify_coords(c, precision) for c in coords]
    return coords

base_url = "https://raw.githubusercontent.com/timurkanaz/Russia_geojson_OSM/master/GeoJson's/Regions"

combined = {"type": "FeatureCollection", "features": []}
script_dir = os.path.dirname(os.path.abspath(__file__))

for region_name, (subdir, filename) in REGIONS.items():
    url = f"{base_url}/{subdir}/{urllib.parse.quote(filename)}"
    sys.stdout.write(f"Downloading {region_name}... ")
    sys.stdout.flush()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        sys.stdout.write(f"FAIL: {e}\n")
        continue

    for feat in data.get("features", []):
        orig_name = feat["properties"].get("district") or feat["properties"].get("name", "")
        feat["properties"] = {"district": orig_name, "region": region_name}
        if feat["geometry"]["type"] == "MultiPolygon":
            feat["geometry"]["coordinates"] = simplify_coords(feat["geometry"]["coordinates"])
        elif feat["geometry"]["type"] == "Polygon":
            feat["geometry"]["coordinates"] = simplify_coords(feat["geometry"]["coordinates"])
    combined["features"].extend(data["features"])
    sys.stdout.write(f"OK ({len(data['features'])} features)\n")

out_path = os.path.join(script_dir, "districts_europe.geojson")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(combined, f, ensure_ascii=False)

size_mb = os.path.getsize(out_path) / 1024 / 1024
print(f"\nDone! Combined file: {out_path} ({size_mb:.1f} MB, {len(combined['features'])} features)")
