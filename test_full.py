import sys, os
sys.path.insert(0, 'F:\\Locator\\MopedMap')
import mopedmap
from datetime import datetime, timezone

post_text = 'Смоленская область\nТверская область\nОпасность по БПЛА'
posts = [(post_text, 'vrv_radar', datetime.now(timezone.utc))]
all_markers = mopedmap.process_posts(posts)

os.chdir('F:\\Locator\\MopedMap')
geojson_lookup = mopedmap.load_region_geojson()
path = mopedmap.generate_html(all_markers, geojson_lookup=geojson_lookup)

# Check if no_marker was set
for m in all_markers:
    print('name=%s  radius_km=%s  no_marker=%s' % (m['name'], m.get('radius_km'), m.get('no_marker')))

# Check regionGeoJSON in output
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()
    
import re
m = re.search(r'const regionGeoJSON = (.+?]);', html, re.DOTALL)
if m:
    import json
    gj = json.loads(m.group(1))
    features = gj['features']
    print('\nRegion GeoJSON features: %d' % len(features))
    for f in features:
        print('  NAME=%s  alert_type=%s  popup_name=%s' % (
            f['properties'].get('NAME'),
            f['properties'].get('alert_type'),
            f['properties'].get('popup_name')))
else:
    print('regionGeoJSON not found!')
