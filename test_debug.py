import sys
sys.path.insert(0, 'F:\\Locator\\MopedMap')
import mopedmap
import json
from datetime import datetime, timezone

post_text = 'Смоленская область\nТверская область\nОпасность по БПЛА'
print('Input text:')
print(repr(post_text))

# Simulate the full pipeline
posts = [(post_text, 'vrv_radar', datetime.now(timezone.utc))]
print('\nRaw posts:', len(posts))

all_markers = mopedmap.process_posts(posts)
print('\nMarkers:')
for m in all_markers:
    print('  name=%s  lat=%s  lon=%s  type=%s  radius_km=%s' % (
        m['name'], m['lat'], m['lon'], m.get('type'), m.get('radius_km')))

print('\nChecking if summary post:', mopedmap.is_summary_post(post_text))
print('Post type:', mopedmap.classify_post(post_text))

locations = mopedmap.extract_locations(post_text)
print('\nLocations extracted:')
for loc in locations:
    print('  name=%s  lat=%s  lon=%s  radius_km=%s  matched=%s' % (
        loc['name'], loc['lat'], loc['lon'], loc.get('radius_km'), loc.get('matched')))
