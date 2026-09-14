# Звуковое оповещение о событиях в Ярославской области — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Звуковой сигнал в браузерной карте при **новых** событиях в Ярославской области (маркеры внутри области или стрелки «в её сторону»), без перезагрузки страницы (polling `state.json`).

**Architecture:** `generate_html` дополнительно пишет `state.json` (генерируется рядом с `index.html`); клиентский JS опрашивает его каждые 60–120 с, диффает маркеры, при новых событиях по области играет Web Audio сигнал. Мета-refresh 300 с заменяется аварийным сторожем 1800 с.

**Tech Stack:** Python (mopedmap.py, f-string HTML), Vanilla JS, Web Audio API, localStorage, gh-pages.

## Global Constraints

- Всё в `F:\Locator\mopedmap.py`, один файл; JS-код внутри f-string → все литеральные `{`/`}` в JS удваиваются до `{{`/`}}`.
- Комментарии в коде и коммитах — на русском.
- Звучат типы: danger, rocket, aviation, attention, sighting, interception. Молчат: info, clear.
- Триггер события: subject содержит «ярослав» ИЛИ (есть `direction` И dest внутри bbox Ярославской области).
- Мета-refresh: `content="300"` → `content="1800"`.
- Состояние «звук вкл/выкл» и `seen`-отпечатки — в `localStorage` (переживают 30-мин аварийный reload).
- После правок обязательны: AST-прогон, `check_braces.py` PASS, полные регрессии (перечислены в Task 4).
- Репозиторий: коммиты + push на main; деплой `deploy.yml` триггерится push'ем; при transient-флаке GitHub — ручной `gh workflow run "Deploy map to Pages" --ref main`.

---

### Task 1: Сервер: `state.json`, мета-refresh 1800, кнопка 🔔, якорь шапки

**Files:**
- Modify: `F:\Locator\mopedmap.py` (блок 6459–6476, мета 6499, шапка 6558, JS-константы 6613–6616, footer 6575–6576, запись файла 7046–7048)
- Test: `C:\Users\SamLab\AppData\Local\Temp\opencode\test_state_json.py` (создать в Task 4, первая часть — здесь: заглушка на отсутствие state.json)

**Interfaces:**
- Produces: переменная `state_obj` (dict: `generated_at`, `night_kills`, `day_kills`, `markers`, `feed`, `channels`), `now_msk_str` (строка `%d.%m.%Y %H:%M`), файл `state.json` рядом с выходным HTML, HTML-якоря `#hdr-tail`, `#sound-toggle`, JS-константа `GENERATED_AT`.

- [ ] **Step 1: Написать падающий тест** (первая часть `test_state_json.py`)

В `C:\Users\SamLab\AppData\Local\Temp\opencode\test_state_json.py`:

```python
# -*- coding: utf-8 -*-
import json, os, re, sys, io, contextlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"F:\Locator")
import mopedmap

posts = [
    {"lat": 57.77, "lon": 40.93, "name": "Кострома", "type": "danger",
     "text": "Опасность БПЛА со стороны Костромы в сторону Ярославля",
     "source": "locatorru", "time": "09.09.2026 10:00", "is_region": True,
     "subject": "костромская область", "matched": "костромская область"},
    {"lat": 57.55, "lon": 39.85, "name": "Ярославль", "type": "sighting",
     "text": "Фиксация БПЛА в районе Ярославля",
     "source": "vrv_radar", "time": "09.09.2026 09:40", "subject": "ярославская область"},
]
outdir = r"C:\Users\SamLab\AppData\Local\Temp\opencode"
html_path = os.path.join(outdir, "state_test.html")
state_path = os.path.join(outdir, "state.json")
for p in (html_path, state_path):
    if os.path.exists(p):
        os.remove(p)

fails = []
def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (" " + extra if extra else ""))
    if not cond:
        fails.append(name)

with contextlib.redirect_stdout(io.StringIO()):
    mopedmap.generate_html(posts, filename=html_path, geojson_lookup=None, history={})

ok("state_json_exists", os.path.exists(state_path))
if os.path.exists(state_path):
    with open(state_path, encoding="utf-8") as f:
        st = json.load(f)
    ok("state_keys", {"generated_at", "night_kills", "day_kills", "markers", "feed", "channels"} <= set(st), str(sorted(st.keys())))
    ok("markers_roundtrip", st["markers"] == posts, "n=" + str(len(st.get("markers") or [])))
    ok("generated_at_fmt", bool(re.match(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2} МСК$", st["generated_at"])), st.get("generated_at", ""))
    ok("night_kills_none", st["night_kills"] is None)
    ok("day_kills_none", st["day_kills"] is None)

with open(html_path, encoding="utf-8") as f:
    html = f.read()
ok("meta_refresh_1800", 'content="1800">' in html)
ok("meta_refresh_300_absent", 'content="300">' not in html)
ok("sound_toggle", 'id="sound-toggle"' in html)
ok("hdr_tail", 'id="hdr-tail"' in html)
ok("generated_at_const", 'GENERATED_AT' in html)

print()
if fails:
    print(f"RESULT: {len(fails)} FAIL")
    sys.exit(1)
print("RESULT: ALL PASS")
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `python "C:\Users\SamLab\AppData\Local\Temp\opencode\test_state_json.py"`
Expected: `FAIL state_json_exists` и др.

- [ ] **Step 3: Реализация — серверная часть**

В `mopedmap.py`:

(3a) После блока `channel_json = json.dumps(channel_counts, ensure_ascii=False)` (строка 6476) добавить:

```python
    now_msk_str = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime('%d.%m.%Y %H:%M')
    state_obj = {
        "generated_at": now_msk_str + " МСК",
        "night_kills": night_kills,
        "day_kills": day_kills,
        "markers": posts_data,
        "feed": feed_data,
        "channels": channel_counts,
    }
```

(3b) Строка 6499: `<meta http-equiv="refresh" content="300">` → `<meta http-equiv="refresh" content="1800">`

(3c) Строка 6558 — шапка, подставить `now_msk_str` и добавить якорь `#hdr-tail`:

```python
  <span class="info">На карте <span id="pt-count">{len(posts_data)}</span> точек<span id="hdr-tail">{f" | За ночь {night_kills} бпла" if night_kills else ""}{f" | За день {day_kills} бпла" if day_kills else ""} | {now_msk_str} МСК</span></span>
```

(3d) Блок 6613–6616 → (перед `const data`, чтобы `lastGeneratedAt`/`pollFailCount` были видны в polling):

```python
const GENERATED_AT = "{now_msk_str}";
let lastGeneratedAt = GENERATED_AT;
let pollFailCount = 0;

const data = {markers_json};
let channelStats = {channel_json};

let feed = {feed_json};
```

(3e) Footer, строки 6575–6576:

```python
  <span id="chStats-toggle" title="Показать каналы" style="cursor:pointer">☰ Каналы</span>
  <span id="sound-toggle" title="Звук выключен — клик включить" style="cursor:pointer;opacity:0.55">🔔</span>
  <span style="margin-left:auto;color:#999">Обновление каждые ~1 мин · данные за 4 часа</span>
```

(3f) Запись файла, строки 7046–7048:

```python
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    state_path = os.path.join(os.path.dirname(os.path.abspath(filename)), "state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state_obj, f, ensure_ascii=False)
    return os.path.abspath(filename)
```

- [ ] **Step 4: Запустить тест — теперь зелёный**

Run: `python "C:\Users\SamLab\AppData\Local\Temp\opencode\test_state_json.py"`
Expected: `RESULT: ALL PASS`

- [ ] **Step 5: AST + фикстура**

Run: `python -W error::SyntaxWarning -c "import ast; ast.parse(open(r'F:\Locator\mopedmap.py', encoding='utf-8').read())"`
Expected: без вывода, код завершения 0.

- [ ] **Step 6: Commit**

```bash
git -C F:\Locator add mopedmap.py
git -C F:\Locator commit -m "feat: генерация state.json рядом с index.html, мета-refresh 1800 (аварийный), кнопка звука, якорь шапки"
```

---

### Task 2: JS: рефакторинг ленты (`refreshFeedUI`) и функция шапки (`renderHeaderTail`)

**Files:**
- Modify: `F:\Locator\mopedmap.py` (IIFE ленты 6617–6655)

**Interfaces:**
- Produces: `function refreshFeedUI()` (перерисовка `#region-feed` из `feed`), `function renderHeaderTail(s)` (обновление `#hdr-tail` из state-объекта). Консумируется Task 3 (pollState).

- [ ] **Step 1: Заменить IIFE ленты (строки 6617–6655) на `refreshFeedUI` + обработчик**

Точно заменить блок от `const feed = {feed_json};` до `}})();` включительно (он уже изменён в Task 1 на `let feed = ...`) — фактически заменяются строки IIFE после `let feed = {feed_json};`:

```python
function refreshFeedUI() {{
  const panel = document.getElementById('region-feed');
  if (!feed || feed.length === 0) {{ panel.style.display = 'none'; return; }}
  panel.style.display = '';
  const body = document.getElementById('region-feed-body');
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
  const items = body.querySelectorAll('.region-feed-item-text');
  feed.forEach((f, i) => {{ if (items[i]) items[i].textContent = f.text; }});
}}

(function() {{
  const defaultOpen = window.matchMedia && (window.matchMedia('(pointer: fine)').matches || window.matchMedia('(min-width: 768px)').matches);
  const body = document.getElementById('region-feed-body');
  const toggle = document.getElementById('region-feed-toggle');
  const wantOpen = st.panelOpen !== undefined ? st.panelOpen : defaultOpen;
  if (wantOpen) {{
    body.style.display = '';
    toggle.textContent = '▼ Посты: Яр. область + соседи';
  }}
  toggle.addEventListener('click', function() {{
    if (body.style.display === 'none') {{
      body.style.display = '';
      toggle.textContent = '▼ Посты: Яр. область + соседи';
      st.panelOpen = true;
    }} else {{
      body.style.display = 'none';
      toggle.textContent = '▶ Посты: Яр. область + соседи';
      st.panelOpen = false;
    }}
    lsSave(st);
  }});
  refreshFeedUI();
}})();

function renderHeaderTail(s) {{
  const el = document.getElementById('hdr-tail');
  if (!el) return;
  let t = '';
  if (s.night_kills) t += ' | За ночь ' + s.night_kills + ' бпла';
  if (s.day_kills) t += ' | За день ' + s.day_kills + ' бпла';
  t += ' | ' + (s.generated_at || lastGeneratedAt || '');
  el.textContent = t;
}}
```

- [ ] **Step 2: AST + статическая проверка**

Run: `python -W error::SyntaxWarning -c "import ast; ast.parse(open(r'F:\Locator\mopedmap.py', encoding='utf-8').read())"`
Expected: без вывода.
Run: `python "C:\Users\SamLab\AppData\Local\Temp\opencode\check_braces.py"`
Expected: `PASS`

- [ ] **Step 3: Commit**

```bash
git -C F:\Locator add mopedmap.py
git -C F:\Locator commit -m "feat: refreshFeedUI/renderHeaderTail — обновление ленты и шапки без перезагрузки"
```

---

### Task 3: JS: звуковой движок + детекция Ярославля + polling `state.json`

**Files:**
- Modify: `F:\Locator\mopedmap.py` (вставить блок перед `syncLegendUI();` строка 7041; добавить `startPolling();` после `renderAll();` строка 7042)

**Interfaces:**
- Consumes: `visibleItems()`, `tEpoch()`, `data`/`feed`/`channelStats` (let), `refreshFeedUI()`, `renderHeaderTail(s)`, `lastGeneratedAt`, `pollFailCount`.
- Produces: `SOUND_TYPES`, `SOUND_PRIORITY`, `YAR_BBOX`, `isYarSubject(s)`, `inYarBBox(lat,lon)`, `yarEvents()`, `yarFp(it)`, `loadSoundSeen()`, `saveSoundSeen(v)`, `audioCtx`, `soundEnabled`, `ensureAudio()`, `playTone(...)`, `siren()`, `beep()`, `playForType(t)`, `bestNewSound(items)`, `checkSound()`, `pollState()`, `schedulePoll()`, `startPolling()`, обработчики кнопки `#sound-toggle` и первого жеста.

- [ ] **Step 1: Вставить JS-блок перед `syncLegendUI();` (строка 7041)**

```python
// ── Звуковое оповещение о событиях в Ярославской области ────────────
const SOUND_TYPES = {{ danger: true, rocket: true, aviation: true, attention: true, sighting: true, interception: true }};
const SOUND_PRIORITY = {{ rocket: 0, danger: 1, aviation: 2, interception: 3, attention: 4, sighting: 5 }};
const YAR_BBOX = {{ n: 58.9, s: 56.05, e: 40.95, w: 37.4 }};
function isYarSubject(s) {{ return String(s || '').toLowerCase().indexOf('ярослав') !== -1; }}
function inYarBBox(lat, lon) {{ return YAR_BBOX.s <= lat && lat <= YAR_BBOX.n && YAR_BBOX.w <= lon && lon <= YAR_BBOX.e; }}
function yarEvents() {{
  return visibleItems().filter(function(it) {{
    if (!SOUND_TYPES[it.type]) return false;
    if (it.cleared || it.no_marker || it._fill_only) return false;
    if (isYarSubject(it.subject)) return true;
    if (it.direction && Array.isArray(it.direction) && it.direction.length >= 2 &&
        inYarBBox(it.direction[0], it.direction[1])) return true;
    return false;
  }});
}}
function yarFp(it) {{ return it.type + '|' + (it.name || '') + '|' + (it.time || ''); }}
function loadSoundSeen() {{ try {{ const v = JSON.parse(localStorage.getItem('yar_sound_seen') || '{{}}'); return (v && typeof v === 'object') ? v : {{}}; }} catch (e) {{ return {{}}; }} }}
function saveSoundSeen(v) {{ try {{ localStorage.setItem('yar_sound_seen', JSON.stringify(v)); }} catch (e) {{}} }}
let audioCtx = null;
let soundEnabled = !!st.soundEnabled;
function ensureAudio() {{
  if (audioCtx) {{ if (audioCtx.state === 'suspended') audioCtx.resume().catch(function() {{}}); return; }}
  try {{ const AC = window.AudioContext || window.webkitAudioContext; if (AC) audioCtx = new AC(); }} catch (e) {{ audioCtx = null; }}
}}
function playTone(freqFrom, freqTo, dur, gainMax, type) {{
  if (!audioCtx || audioCtx.state !== 'running') return;
  try {{
    const t0 = audioCtx.currentTime;
    const osc = audioCtx.createOscillator(), g = audioCtx.createGain();
    osc.type = type || 'sawtooth';
    osc.frequency.setValueAtTime(freqFrom, t0);
    if (freqTo) osc.frequency.exponentialRampToValueAtTime(Math.max(1, freqTo), t0 + dur);
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(gainMax, t0 + 0.05);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(g); g.connect(audioCtx.destination);
    osc.start(t0); osc.stop(t0 + dur + 0.05);
  }} catch (e) {{}}
}}
function siren() {{
  playTone(520, 740, 0.8, 0.18, 'sawtooth');
  playTone(740, 520, 0.8, 0.18, 'sawtooth');
}}
function beep() {{
  playTone(880, 880, 0.12, 0.15, 'square');
  setTimeout(function() {{ playTone(880, 880, 0.12, 0.15, 'square'); }}, 180);
}}
function playForType(t) {{ if (t === 'rocket' || t === 'danger' || t === 'aviation') siren(); else beep(); }}
function bestNewSound(items) {{
  let best = null;
  items.forEach(function(it) {{ if (!best || SOUND_PRIORITY[it.type] < SOUND_PRIORITY[best.type]) best = it; }});
  return best;
}}
function checkSound() {{
  if (!soundEnabled) return;
  const seen = loadSoundSeen();
  const cur = yarEvents();
  const now = Date.now();
  const newItems = cur.filter(function(it) {{ return !seen[yarFp(it)]; }});
  let dirty = false;
  Object.keys(seen).forEach(function(fp) {{
    const tm = tEpoch(fp.split('|').slice(-1)[0]);
    if (tm && now - tm > 6 * 3600 * 1000) {{ delete seen[fp]; dirty = true; }}
  }});
  cur.forEach(function(it) {{ const fp = yarFp(it); if (!seen[fp]) {{ seen[fp] = 1; dirty = true; }} }});
  if (dirty) saveSoundSeen(seen);
  if (newItems.length) {{ const b = bestNewSound(newItems); if (b) playForType(b.type); }}
}}

const soundToggle = document.getElementById('sound-toggle');
function renderSoundToggleUI() {{
  if (!soundToggle) return;
  soundToggle.style.opacity = soundEnabled ? '1' : '0.55';
  soundToggle.title = soundEnabled ? 'Звук включён — клик выключить' : 'Звук выключен — клик включить';
}}
if (soundToggle) soundToggle.addEventListener('click', function() {{
  soundEnabled = !soundEnabled;
  st.soundEnabled = soundEnabled;
  lsSave(st);
  renderSoundToggleUI();
  if (soundEnabled) {{
    ensureAudio();
    if (audioCtx && audioCtx.state === 'running') siren();
    const seen = loadSoundSeen();
    yarEvents().forEach(function(it) {{ seen[yarFp(it)] = 1; }});
    saveSoundSeen(seen);
  }}
}});
function unlockAudioOnce() {{ ensureAudio(); window.removeEventListener('pointerdown', unlockAudioOnce); window.removeEventListener('keydown', unlockAudioOnce); }}
window.addEventListener('pointerdown', unlockAudioOnce);
window.addEventListener('keydown', unlockAudioOnce);
renderSoundToggleUI();

// ── Опрос state.json (обновление без перезагрузки) ───────────────────
function pollState() {{
  fetch('state.json?v=' + Date.now(), {{ cache: 'no-store' }})
    .then(function(r) {{ if (!r.ok) throw new Error(String(r.status)); return r.json(); }})
    .then(function(s) {{
      pollFailCount = 0;
      if (s.generated_at && s.generated_at === lastGeneratedAt) return;
      lastGeneratedAt = s.generated_at || lastGeneratedAt;
      if (Array.isArray(s.markers)) data = s.markers;
      if (Array.isArray(s.feed)) feed = s.feed;
      if (s.channels) channelStats = s.channels;
      renderAll();
      refreshFeedUI();
      renderHeaderTail(s);
      checkSound();
    }})
    .catch(function() {{
      pollFailCount++;
      if (pollFailCount >= 5) {{
        const el = document.getElementById('hdr-tail');
        if (el && el.textContent.indexOf('Связь') === -1) el.textContent += ' | Связь с данными потеряна';
      }}
    }})
    .then(function() {{ schedulePoll(); }});
}}
function schedulePoll() {{
  const delay = document.hidden ? 120000 : 60000;
  setTimeout(pollState, delay);
}}
function startPolling() {{ pollState(); }}
```

- [ ] **Step 2: Запуск polling после `renderAll();` (строка 7042)**

После `renderAll();` добавить:

```python
startPolling();
```

- [ ] **Step 3: AST + check_braces + verify_js (обновить проверки)**

Run: `python -W error::SyntaxWarning -c "import ast; ast.parse(open(r'F:\Locator\mopedmap.py', encoding='utf-8').read())"`
Expected: без вывода.
Run: `python "C:\Users\SamLab\AppData\Local\Temp\opencode\check_braces.py"`
Expected: `PASS`

В `verify_js.py` в словарь `checks` добавить (после `"legendToggle"`):

```python
    "sound_types": "SOUND_TYPES" in js,
    "yar_events": "function yarEvents" in js,
    "inYarBBox": "function inYarBBox" in js,
    "poll_state": "function pollState" in js,
    "refresh_feed": "function refreshFeedUI" in js,
    "render_header_tail": "function renderHeaderTail" in js,
    "start_polling": "startPolling()" in js,
    "let_data": "let channelStats" in js and "let feed" in js,
```

Run: `python "C:\Users\SamLab\AppData\Local\Temp\opencode\verify_js.py"`
Expected: все новые ключи `OK`; `not_escaped_brace` остаётся известным FAIL.

- [ ] **Step 4: Прогнать test_state_json.py (регресс Task 1)**

Run: `python "C:\Users\SamLab\AppData\Local\Temp\opencode\test_state_json.py"`
Expected: `RESULT: ALL PASS`

- [ ] **Step 5: Commit**

```bash
git -C F:\Locator add mopedmap.py
git -C F:\Locator commit -m "feat: звуковое оповещение по Ярославской области + polling state.json без перезагрузок"
```

---

### Task 4: Полные регрессии, CONTEXT.md, пуш, деплой, live-проверка

**Files:**
- Modify: `F:\Locator\CONTEXT.md`
- Verify: все тестовые скрипты из `C:\Users\SamLab\AppData\Local\Temp\opencode\`

- [ ] **Step 1: Прогнать полный набор регрессий**

Run (каждый — ожидание ALL PASS/0 FAIL):
- `python "C:\Users\SamLab\AppData\Local\Temp\opencode\test_state_json.py"` → ALL PASS
- `python "C:\Users\SamLab\AppData\Local\Temp\opencode\test_rayon_disambig.py"` → `PASS=29 FAIL=0`
- `python "C:\Users\SamLab\AppData\Local\Temp\opencode\test_dir_regress.py"` → ALL PASS
- `python "C:\Users\SamLab\AppData\Local\Temp\opencode\test_day_red.py"` → ALL PASS
- `python "C:\Users\SamLab\AppData\Local\Temp\opencode\test_summary_day.py"` → ALL PASS
- `python "C:\Users\SamLab\AppData\Local\Temp\opencode\test_lnr_red.py"` → ALL PASS
- `python "C:\Users\SamLab\AppData\Local\Temp\opencode\test_audit13.py"` → ALL PASS
- `python "C:\Users\SamLab\AppData\Local\Temp\opencode\probe_rayon.py"` → 24/24 корректны
- AST, `check_braces.py`, `verify_js.py` (12/13 — известный false positive `not_escaped_brace`)

- [ ] **Step 2: Обновить CONTEXT.md**

Добавить в раздел Done запись (по стилю существующих):

```markdown
- **Звуковое оповещение по Ярославской области + polling (14.09.2026)**: кнопка `🔔` в footer (localStorage `soundEnabled`); Web Audio — сирена для danger/rocket/aviation, двойной бип для sighting/interception/attention, тишина для info/clear. Триггер: subject содержит «ярослав» ИЛИ стрелка (`direction`) упирается в bbox области (56.05–58.9 N, 37.4–40.95 E). `generate_html` пишет `state.json` рядом с `index.html` ({generated_at, night_kills, day_kills, markers, feed, channels}); клиент опрашивает его каждые 60 с (120 с в фоне) и перерисовывает `renderAll()`/`refreshFeedUI()` без перезагрузки, детектит новые отпечатки `тип|имя|время` (localStorage `yar_sound_seen`, чистка >6ч) и играет звук самого серьёзного нового типа. Мета-refresh 300 → 1800 (аварийный). Аудио разблокируется первым жестом (ограничение браузера). Spec: `docs/superpowers/specs/2026-09-14-sound-alert-design.md`.
```

- [ ] **Step 3: Commit + push**

```bash
git -C F:\Locator add CONTEXT.md
git -C F:\Locator commit -m "docs: звуковое оповещение по Ярославской области + polling (CONTEXT)"
git -C F:\Locator push origin main
```

- [ ] **Step 4: Деплой и live-проверка**

Push триггерит `deploy.yml`. Если push-раун упал (startup_failure / Internal Server Error на git-side — известная флакость GitHub), запустить вручную:

```bash
gh workflow run "Deploy map to Pages" --ref main
```

Дождаться completion через `python "C:\Users\SamLab\AppData\Local\Temp\opencode\poll_run.py" <RUN_ID>`, затем:

```bash
git ls-remote origin gh-pages   # HEAD сменился
python "C:\Users\SamLab\AppData\Local\Temp\opencode\check_live.py"  # заголовок свежий (МСК-время обновилось)
```

Дополнительно проверить, что `state.json` отдаётся (HTTP 200):

```python
import urllib.request
print(urllib.request.urlopen("https://samlab.github.io/MopedMap/state.json", timeout=60).status)
```

Expected: `200`; в теле — валидный JSON с ключом `markers`.