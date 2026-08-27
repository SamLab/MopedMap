# Лента постов регионов (панель в правом верхнем углу) — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в генерируемый HTML-файл карты сворачиваемую панель в правом верхнем углу с лентой постов по Ярославской области и 6 соседям (Тверская, Вологодская, Костромская, Ивановская, Владимирская, Московская).

**Architecture:** Python-функция `build_region_feed(posts_data)` отбирает и группирует итоговые маркеры карты в ленту, `generate_html` сериализует её в `feed_json` и инжектит в HTML. Рендеринг — CSS-панель + лёгкий JS (свёрнута по умолчанию как легенда). Существующие маркеры/заливка не трогаются.

**Tech Stack:** Python 3, встроенный `json`, Jinja-подобный f-строковый HTML-шаблон в `mopedmap.py`, Leaflet.js + vanilla JS на клиенте.

## Global Constraints

- Код и комментарии в репозитории — на русском.
- Не дублировать rayon-паттерны в нескольких subject — здесь не применимо (задача не про disambiguation), но сохранять стиль существующего кода.
- `mopedmap.py` — огромный файл (~7000 строк). Не перестраивать его структуру; добавлять код рядом с существующим.
- Поля маркеров, используемые далее: `text`, `source`, `time`, `name`, `subject`, `is_region`. `subject` может отсутствовать — тогда регион берётся из `CITY_DB[name_lower]['subject']`.
- Каналы не трогать — лента строится из уже отфильтрованных итоговых маркеров.
- После каждого выполненного теста — коммит. Push — по завершении всей фичи (пользователь просит commit+push).
- Тесты запускаются как скрипты: `python -B script.py` (у проекта нет pytest-инфраструктуры). Создавать тест-скрипты во временной директории не нужно — кладём в `F:\Locator\test_*.py` и удаляем после прогона (или оставляем, если пользователь не против; по умолчанию удаляем).

---

### Task 1: Функция сборки ленты `build_region_feed`

**Files:**
- Modify: `F:\Locator\mopedmap.py` (добавить константу `TRACKED_REGIONS` и функцию `build_region_feed` перед `def generate_html`, строка ~5770)
- Test: `F:\Locator\test_feed.py` (временный, удалить после)

**Interfaces:**
- Produces: `TRACKED_REGIONS: frozenset[str]`, `build_region_feed(posts_data, max_items=20) -> list[dict]`
  - Возвращает список dict: `{"time", "sources" (list[str]), "regions" (list[str]), "text" (str), "pinned" (bool)}`.
  - `time` — самый свежий `time`-строки среди маркеров поста (исходный формат из process_posts, напр. `'23.08.2026 05:14'`), сортировка по нему (строка сравнивается лексикографически, т.к. формат `ДД.ММ.ГГГГ ЧЧ:ММ` — годится).
  - `text` — первая строка текста поста (после нормализации), обрезанная до 180 символов.
  - `regions` — упорядоченные уникальные subject-ы маркеров поста.
  - `pinned` — `True`, если `'ярославская область' in regions`.
  - Порядок результата: pinned сверху, затем по `time` desc.

  **Примечание о 4-часовом окне:** `generate_html` получает `posts_data` уже
  отфильтрованными по временным окнам типов (в `main()` через `display_markers`,
  дефолт 4 часа). Поэтому `build_region_feed` НЕ должен дополнительно фильтровать
  по времени — оно уже применено к входящим данным.

- [ ] **Step 1: Write the failing test**

Создать `F:\Locator\test_feed.py`:

```python
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'F:\Locator')
import mopedmap as m

def mk(name, lat, lon, subject=None, text=("Z", "y"), source="s", time="23.08.2026 05:14"):
    d = {"name": name, "lat": lat, "lon": lon, "text": text, "source": source, "time": time}
    if subject:
        d["subject"] = subject
    return d

marks = [
    mk("Рыбинск", 58.05, 38.84, "Ярославская область", text="Фиксации БПЛА", time="23.08.2026 06:00"),
    mk("Углич", 57.53, 38.33, "Ярославская область", text="Фиксации БПЛА", time="23.08.2026 06:01"),
    mk("Тверь", 56.86, 35.91, "Тверская область", text="Опасность БПЛА", time="23.08.2026 05:30"),
    mk("Иваново", 56.99, 40.97, "Ивановская область", text="Опасность БПЛА", time="23.08.2026 05:40"),
    mk("Казань", 55.78, 49.12, "Татарстан", text="Опасность БПЛА", time="23.08.2026 05:00"),
]

feed = m.build_region_feed(marks, max_items=20)
assert len(feed) == 3, f"ожидал 3 поста, получил {len(feed)}: {feed}"

# pinned: Ярославская сверху
assert feed[0]["pinned"] is True, feed
assert feed[1]["pinned"] is False and feed[2]["pinned"] is False, feed
# внутри группы — по времени desc (Тверь 05:30 < Иваново 05:40 → Иваново первым среди неппн)
# regions хранятся строчными (lowercase) — см. _region_of
assert [f["regions"][0] for f in feed] == ["ярославская область", "ивановская область", "тверская область"], feed
# Дедуп каналов: Рыбинск и Углич — один и тот же текст → один пост, источник первый
assert len(feed[0]["sources"]) == 1
assert feed[0]["text"] == "Фиксации БПЛА"
print("TEST_PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONIOENCODING='utf-8'; python -B F:\Locator\test_feed.py`
Expected: FAIL — `AttributeError: module 'mopedmap' has no attribute 'build_region_feed'`

- [ ] **Step 3: Write minimal implementation**

В `mopedmap.py`, непосредственно перед `def generate_html(posts_data, ...)` (строка 5771), вставить:

```python
TRACKED_REGIONS = frozenset({
    "ярославская область", "тверская область", "вологодская область",
    "костромская область", "ивановская область",
    "владимирская область", "московская область",
})


def build_region_feed(posts_data, max_items=20):
    """Собирает ленту постов по Ярославской области и 6 соседним регионам.

    Берёт итоговые маркеры карты (posts_data), оставляет те, чей регион —
    один из TRACKED_REGIONS, группирует по тексту поста (дедуп каналов),
    объединяет источники, сортирует: Ярославская область (pinned) сверху,
    затем по времени desc. Возвращает до max_items записей.
    """
    def _region_of(item):
        rn = (item.get("subject") or "").strip().lower()
        if not rn:
            cn = item.get("name", "").strip().lower()
            if cn in CITY_DB:
                rn = (CITY_DB[cn].get("subject") or "").strip().lower()
        return rn

    posts = {}  # norm-text -> {"time","sources","regions","text","pinned"}
    for item in posts_data:
        rn = _region_of(item)
        if rn not in TRACKED_REGIONS:
            continue
        raw_text = item.get("text") or ""
        norm = " ".join(sanitize_popup_text(raw_text).split()).strip().lower()
        key = norm or id(item)
        p = posts.get(key)
        if p is None:
            p = {"time": item.get("time", ""), "sources": [], "regions": [],
                 "text": norm, "pinned": False}
            posts[key] = p
        if item.get("time", "") and item["time"] > p["time"]:
            p["time"] = item["time"]
        src = (item.get("source") or "").strip()
        if src and src not in p["sources"]:
            p["sources"].append(src)
        if rn and rn not in p["regions"]:
            p["regions"].append(rn)
        if rn == "ярославская область":
            p["pinned"] = True

    items = list(posts.values())
    items.sort(key=lambda p: (0 if p["pinned"] else 1,),
               reverse=False)
    # стабильная сортировка: pinned уже отделены; внутри — по времени desc
    pinned = [p for p in items if p["pinned"]]
    others = [p for p in items if not p["pinned"]]
    pinned.sort(key=lambda p: p["time"], reverse=True)
    others.sort(key=lambda p: p["time"], reverse=True)
    ordered = pinned + others

    result = []
    for p in ordered[:max_items]:
        result.append({
            "time": p["time"],
            "sources": p["sources"],
            "regions": p["regions"],
            "text": (p["text"][:180] + ("…" if len(p["text"]) > 180 else "")),
            "pinned": p["pinned"],
        })
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONIOENCODING='utf-8'; python -B F:\Locator\test_feed.py`
Expected: `TEST_PASS`

- [ ] **Step 5: Commit**

```bash
git add F:\Locator\mopedmap.py
git commit -m "feat: build_region_feed — лента постов Ярославская + соседи (дедуп каналов, pinned)"
```

---

### Task 2: Встраивание панели в `generate_html` (CSS + HTML + JS)

**Files:**
- Modify: `F:\Locator\mopedmap.py`
  - строка ~6234 (`markers_json = json.dumps(...)`): рядом добавить `feed_json`
  - CSS-блок внутри `<style>` (после `.legend i`)
  - тело HTML: после `<div id="map"></div>` добавить панель
  - JS-блок: после `const data = {markers_json};` добавить рендер ленты
- Test: задача проверяется визуально + скриптом, что `generate_html` не падает и в выводе есть `feed_json`/панель.

**Interfaces:**
- Consumes: `build_region_feed(posts_data)` из Task 1.
- Produces: изменённая `generate_html`, которая вставляет сворачиваемую панель.

- [ ] **Step 1: Write the failing test (smoke)**

Создать `F:\Locator\test_html_smoke.py`:

```python
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'F:\Locator')
import mopedmap as m
from datetime import datetime, timezone, timedelta

dt = datetime(2026, 8, 23, 5, 14, tzinfo=timezone(timedelta(hours=3)))
post = "Ярославская область - опасность по БПЛА со стороны Костромы."
src = "locatorru"
markers = m.process_posts([(post, post, src, dt)], geojson_lookup=None)
assert markers, "ожидал маркеры"
html = m.generate_html(markers, filename=None, geojson_lookup=None, history=None)
assert "feed_json" in html and "feed-panel" in html, "в HTML нет ленты"
assert "feed-data" in html, "нет данных ленты"
# панель по умолчанию свёрнута (тело display:none)
assert "feed-body" in html and "none" in html, "панель не свёрнута по умолчанию"
print("SMOKE_PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONIOENCODING='utf-8'; python -B F:\Locator\test_html_smoke.py`
Expected: FAIL — assertion "в HTML нет ленты"

- [ ] **Step 3: Implement**

**(3a)** После строки `markers_json = json.dumps(posts_data, ensure_ascii=False)` (строка 6234) добавить:

```python
    feed_data = build_region_feed(posts_data)
    feed_json = json.dumps(feed_data, ensure_ascii=False)
```

**(3b)** В CSS-блоке после `.legend i {{ ... }}` (строка 6269) добавить:

```css
.region-feed {{ position: absolute; top: 56px; right: 12px; z-index: 1000; width: 320px; max-height: 42vh; background: rgba(255,255,255,0.97); border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.2); border: 1px solid #ccc; font-size: 12px; color: #333; display: flex; flex-direction: column; overflow: hidden; }}
.region-feed-toggle {{ padding: 8px 12px; cursor: pointer; background: #fff; border-bottom: 1px solid #eee; font-weight: bold; color: #d32f2f; user-select: none; }}
.region-feed-body {{ overflow-y: auto; max-height: calc(42vh - 34px); }}
.region-feed-item {{ padding: 8px 12px; border-bottom: 1px solid #f0f0f0; }}
.region-feed-item.pinned {{ background: #fff7e6; border-left: 3px solid #d32f2f; }}
.region-feed-item-meta {{ font-size: 11px; color: #666; margin-bottom: 2px; }}
.region-feed-item-meta b.yar {{ color: #d32f2f; }}
.region-feed-item-text {{ font-size: 12px; color: #222; line-height: 1.35; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
```

**(3c)** В теле HTML после `<div id="map"></div>` (строка 6288) добавить:

```html
<div class="region-feed" id="region-feed" style="display:none">
  <div class="region-feed-toggle" id="region-feed-toggle">▶ Посты: Яр. область + соседи</div>
  <div class="region-feed-body" id="region-feed-body" style="display:none"></div>
</div>
```

**(3d)** В JS-блоке после `const data = {markers_json};` (строка 6328) добавить:

```js
const feed = {feed_json};
(function() {{
  const panel = document.getElementById('region-feed');
  if (!feed || feed.length === 0) {{ return; }}
  panel.style.display = '';
  const body = document.getElementById('region-feed-body');
  const toggle = document.getElementById('region-feed-toggle');
  const html = feed.map(f => {{
    const yar = f.pinned ? '<b class="yar">Яр</b> ' : '';
    const regions = (f.regions || []).join(', ');
    const sources = (f.sources || []).join(' / ');
    return '<div class="region-feed-item' + (f.pinned ? ' pinned' : '') + '">' +
      '<div class="region-feed-item-meta">' + yar + '<b>' + (f.time||'') + '</b> · ' + sources +
      (regions ? ' · ' + regions : '') + '</div>' +
      '<div class="region-feed-item-text"></div></div>';
  }}).join('');
  body.innerHTML = html;
  // заполнить text безопасно
  const items = body.querySelectorAll('.region-feed-item-text');
  feed.forEach((f, i) => {{ if (items[i]) items[i].textContent = f.text; }});
  toggle.addEventListener('click', function() {{
    if (body.style.display === 'none') {{
      body.style.display = '';
      toggle.textContent = '▼ Посты: Яр. область + соседи';
    }} else {{
      body.style.display = 'none';
      toggle.textContent = '▶ Посты: Яр. область + соседи';
    }}
  }});
}})();
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONIOENCODING='utf-8'; python -B F:\Locator\test_html_smoke.py`
Expected: `SMOKE_PASS`

- [ ] **Step 5: Manual visual check**

Запустить полный прогон, чтобы сгенерировать реальный `mopedmap.html`:

```bash
$env:PYTHONIOENCODING='utf-8'; python -B F:\Locator\mopedmap.py
```

Открыть `F:\Locator\mopedmap.html` (или путь из OUTPUT_FILE). Проверить:
- в правом верхнем углу под шапкой — заголовок «▶ Посты: Яр. область + соседи»
- клик разворачивает список постов (если есть данные за 4 часа по этим регионам)
- Ярославские посты — сверху и подсвечены; дубли каналов — одним постом
- панель не мешает карте

- [ ] **Step 6: Commit**

```bash
git add F:\Locator\mopedmap.py
git commit -m "feat: панель ленты постов Ярославская+соседи в правом верхнем углу (свёрнута как легенда)"
```

---

### Task 3: Регрессия и очистка

**Files:**
- Delete: `F:\Locator\test_feed.py`, `F:\Locator\test_html_smoke.py` (после успешного прогона)
- Modify: `F:\Locator\CONTEXT.md` (добавить запись о фиче)

- [ ] **Step 1: Прогнать существующую регрессию**

Воспроизвести регрессионный прогон документированных кейсов (24/29) — убедиться, что добавление панели не сломало маркеры/заливку. Использовать любой ранее применявшийся скрипт регрессии или быстрый прогон `process_posts` + `generate_html` по корпусу тестовых постов, сравнив количество маркеров с ожидаемым. Панель ничего не должна менять в `posts_data`.

- [ ] **Step 2: Удалить временные тест-файлы**

```bash
Remove-Item -LiteralPath F:\Locator\test_feed.py, F:\Locator\test_html_smoke.py
```

- [ ] **Step 3: Обновить CONTEXT.md**

Добавить в «Done (continued)» запись (стиль как у остальных):

```
- **Панель ленты постов регионов (27.08.2026)**: В правом верхнем углу карты добавлена
  сворачиваемая панель с лентой постов по Ярославской области и 6 соседям (Тверская,
  Вологодская, Костромская, Ивановская, Владимирская, Московская). `TRACKED_REGIONS` +
  `build_region_feed(posts_data)` собирают ленту из итоговых маркеров карты: фильтр по
  региону (subject, или CITY_DB[name] при отсутствии), группировка по нормализованному
  тексту (дедуп каналов), объединение источников, сортировка — Ярославская (pinned)
  сверху, затем по времени desc, лимит ~20 строк. Рендер — CSS-панель + JS, свёрнута
  по умолчанию как легенда («▶ Посты: Яр. область + соседи»). Spec:
  `docs/superpowers/specs/2026-08-27-region-feed-panel-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add F:\Locator\CONTEXT.md
git commit -m "docs: панель ленты постов регионов"
```

---

### Task 4: Push

- [ ] **Step 1: Push**

```bash
git push origin main
```

Expected: `main` обновлён на remote.
