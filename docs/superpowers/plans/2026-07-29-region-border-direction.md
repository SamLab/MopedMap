# Region Border Direction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make arrows point to the region's border instead of its capital when the destination is only a region (no city mentioned).

**Architecture:** Add geometry helpers that find the closest point on a GeoJSON polygon boundary from a source point. In `process_posts`, detect region-only destinations (is_region=True + matched text contains region keywords) and replace their coordinates with the border point.

**Tech Stack:** Python 3, GeoJSON (already loaded), mopedmap.py

## Global Constraints

- All changes go into `mopedmap.py`
- GeoJSON coordinates are in [lon, lat] order
- Fallback to capital when GeoJSON unavailable or region not found

---

### Task 1: Add geometry helper functions

**Files:**
- Modify: `F:\Locator\mopedmap.py` — add new functions before `process_posts` (~line 4980)

**Interfaces:**
- Consumes: `geojson_lookup` dict (name_lower → GeoJSON feature), `find_geojson_feature` function (already defined)
- Produces:
  - `closest_point_on_polygon(lat, lon, polygon_coords)` → (lat, lon)
  - `find_border_point(region_name, src_lat, src_lon, geojson_lookup)` → (lat, lon) | None

- [ ] **Step 1: Add `closest_point_on_polygon` before `process_posts` (or after `generate_html`). Place it right before `process_posts` (before line ~4980).**

```python
def closest_point_on_polygon(lat, lon, polygon_coords):
    """Find closest point on polygon boundary from (lat, lon).
    polygon_coords: GeoJSON coordinates — list of rings for Polygon,
                    or list of polygon-coords for MultiPolygon.
    Returns (lat, lon) of closest point on boundary."""
    best_lat, best_lon = lat, lon
    best_dist = float('inf')

    # Flatten: extract all rings
    if polygon_coords and isinstance(polygon_coords[0], list) and polygon_coords[0] and isinstance(polygon_coords[0][0], list) and isinstance(polygon_coords[0][0][0], list):
        # MultiPolygon: [[[lon,lat], ...], [[lon,lat], ...]] 
        rings = []
        for poly in polygon_coords:
            rings.extend(poly)
    else:
        # Polygon: [[lon,lat], ...]
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
```

- [ ] **Step 2: Add `find_border_point` right after `closest_point_on_polygon`**

```python
def find_border_point(region_name, src_lat, src_lon, geojson_lookup):
    """Find closest border point of region from source coordinates.
    region_name: lowercased region name (e.g. 'рязанская область')
    Returns (lat, lon) or None if region not found."""
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
```

- [ ] **Step 3: Verify no syntax errors**

Run: `python -c "import py_compile; py_compile.compile(r'F:\Locator\mopedmap.py', doraise=True)"`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add mopedmap.py
git commit -m "feat: add closest_point_on_polygon and find_border_point helpers"
```

---

### Task 2: Integrate border point in process_posts

**Files:**
- Modify: `F:\Locator\mopedmap.py` — lines ~5896-5930 (direction marker creation)

**Interfaces:**
- Consumes: `find_border_point`, `geojson_lookup` parameter of `process_posts`
- Modifies: destination coordinates and name for region-only destinations

- [ ] **Step 1: Add `_IS_REGION_DEST` pattern constant before process_posts**

Add this right before `process_posts`:
```python
_REGION_DEST_KW = re.compile(r'\b(область|области|областью|обл|'
                             r'край|края|'
                             r'республик|'
                             r'округ|округе|ао)\b')
```

- [ ] **Step 2: Modify direction marker creation loop**

In `process_posts`, around line ~5916, replace the marker creation with:

```python
                # Compute border point for region-only destinations
                if dst.get("is_region") and _REGION_DEST_KW.search(dst.get("matched", "").lower()):
                    if geojson_lookup:
                        bp = find_border_point(dst.get("subject", "").lower(), src["lat"], src["lon"], geojson_lookup)
                        if bp:
                            dst = {**dst, "lat": bp[0], "lon": bp[1], "name": dst.get("subject", dst["name"])}
                m = {
                    "lat": src["lat"], "lon": src["lon"],
                    "name": src["name"], "type": post_type,
                    "text": original_post[:5000] + ("..." if len(original_post) > 5000 else ""),
                    "direction": [dst["lat"], dst["lon"]],
                    "dest_name": dst["name"],
                    "source": source, "time": post_time,
                }
```

The exact insertion point is right before `m = {` (around line 5916). The existing `m = {` block should remain unchanged.

- [ ] **Step 3: Add `geojson_lookup` parameter to `process_posts`**

```python
def process_posts(posts, channel_ids, hours_filter=DEFAULT_HOURS, geojson_lookup=None):
```

- [ ] **Step 4: Wire `geojson_lookup` at call site**

In main (around line ~6035):
```python
    display_markers = process_posts(post_data, CHANNEL_IDS, hours_filter=HOURS_FILTER, geojson_lookup=geojson_lookup)
```

- [ ] **Step 5: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile(r'F:\Locator\mopedmap.py', doraise=True)"`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add mopedmap.py
git commit -m "feat: integrate border point computation for region-only destinations"
```

---

### Task 3: Test with real post

**Files:**
- Create: `F:\Locator\test_border.py` (temp, will be deleted)

- [ ] **Step 1: Write test script**

```python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\Locator')
sys.stdout.reconfigure(encoding='utf-8')

from mopedmap import extract_directions, process_posts, load_region_geojson

# Mock a post like the user's example
post = u'Дмитриевка, Гавриловский район, Тамбовская область - пролёт 2 БПЛА в направлении Рязанской области.'
mock_entry = {
    'messages': [
        {
            'text': post,
            'date': '2026-07-29T02:41:00',
            'channel': 'locatorru',
        }
    ],
    'channel_id': 'locatorru',
}

# Test with geojson
geojson_lookup = load_region_geojson()
if not geojson_lookup:
    print('GeoJSON not loaded')
    sys.exit(0)

pairs = extract_directions(post)
print('Direction pairs:')
for src, dst in pairs:
    print('  FROM: %s (%.4f, %.4f) matched="%s"' % (src['name'], src['lat'], src['lon'], src.get('matched','')))
    print('  TO:   %s (%.4f, %.4f) type=%s is_region=%s matched="%s"' % (
        dst['name'], dst['lat'], dst['lon'],
        dst.get('type',''), dst.get('is_region',False), dst.get('matched','')))

# Check border point
from mopedmap import find_border_point
for src, dst in pairs:
    if dst.get('is_region'):
        bp = find_border_point(dst.get('subject','').lower(), src['lat'], src['lon'], geojson_lookup)
        if bp:
            print('  Border pt for "%s" from (%.2f, %.2f): (%.4f, %.4f)' % (
                dst.get('subject',''), src['lat'], src['lon'], bp[0], bp[1]))
```

- [ ] **Step 2: Run test**

Run: `python F:\Locator\test_border.py`
Expected: 
- Direction pairs show Рязанская область destination with is_region=True
- Border point computed as ~(53.5, 40.5) or similar — closer to the source than Рязань (54.61, 39.71)

- [ ] **Step 3: Clean up**

Run: `Remove-Item -LiteralPath "F:\Locator\test_border.py" -ErrorAction SilentlyContinue`

- [ ] **Step 4: Commit and push**

```bash
git add -A
git commit -m "feat: region border direction — full implementation"
git push
```
