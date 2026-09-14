# Звуковое оповещение о событиях в Ярославской области

Дата: 2026-09-14
Статус: утверждено пользователем по секциям

## Цель

Звуковое оповещение в браузерной карте (MopedMap): сигнал при **новых** событиях в
Ярославской области — события внутри области и направления/стрелки «в её сторону».
Страница перестаёт перезагружаться каждые 5 минут (переход на polling), что одновременно
убирает сброс зума/состояния карты и делает звук стабильно работающим после одного клика.

## Требования пользователя

- Звучат типы: опасность (danger), ракетная (rocket), авиационная (aviation), внимание (attention),
  фиксация (sighting), сбитие/перехват (interception).
- Молчат: инфо (info), отбой (clear). Отбой также снимает звуковую тревогу.
- Триггер: маркер внутри полигона Ярославской области ИЛИ стрелка маркера (destination)
  направлена внутрь области.
- Подход: А — `state.json` + polling без полной перезагрузки.

## Архитектура

### 1. Серверная часть (mopedmap.py)

#### 1.1 Выделение JSON-строек
Сборка `markers_json`, `feed_json`, `channel_json` (сейчас инлайн в `generate_html`)
выносится в helper, который возвращает и строку JSON для вставки в HTML, и сами объекты
Python (dict/list) для `state.json`. Дублирования логики нет.

#### 1.2 `state.json`
`generate_html` дополнительно пишет рядом с `index.html` файл `state.json`:

```json
{
  "generated_at": "13.09.2026 15:04 МСК",
  "night_kills": 389,
  "day_kills": 53,
  "markers": [ ...то же, что markers_json... ],
  "feed": [ ...feed_json... ],
  "channels": { ...channel_json... }
}
```

Ключи `night_kills`/`day_kills` — по факту наличия (null, если нет) — чтобы клиент мог
обновлять заголовок динамически.

#### 1.3 Мета-refresh
- `<meta http-equiv="refresh" content="300">` убирается.
- Добавляется аварийный сторож `<meta http-equiv="refresh" content="1800">` (30 мин):
  страница перезагрузится только если клиентский polling полностью сломан.
- `state.json` попадает в gh-pages обычным `git add -A` (разворачивается тем же коммитом).

### 2. Клиентский polling (обновление без перезагрузки)

- Первый рендер — из встроенных данных (`data`, `feed`, `channelStats`), без ожидания сети.
- `const data` → `let data` (и `feed`, `channelStats` тоже переприсваиваемы).
- Рендер ленты постов (`#region-feed-body`) выносится из IIFE в функцию `refreshFeed()`
  (тексты вставляются безопасно через `textContent`, как сейчас).
- `pollState()`: раз в 60 с (120 с, если вкладка не в фокусе, по `document.visibilitychange`):
  1. `fetch('state.json?v=' + Date.now(), {cache:'no-store'})`, ответ `res.json()`.
  2. Если `generated_at` совпадает с последним — выход.
  3. `data = s.markers; feed = s.feed; channelStats = s.channels;`
  4. `renderAll()` (перерисовка маркеров/стрелок/заливки), `refreshFeed()`,
     обновление `#pt-count`, заголовка (ночь/день/дата из `s.generated_at`).
  5. Обработка новых событий по области (раздел 4) с **звуком**.
- Ретрай: при ошибке fetch — повтор через 30 с; после 5 неудач подряд — плашка
  «Связь с данными потеряна, страница перезагрузится» (полагаемся на сторож 1800 с).
- Цикл через цепочку `setTimeout` + пауза/возобновление по видимости вкладки.

### 3. Звуковой движок (Web Audio, без внешних файлов)

- Кнопка `🔔` в footer: вкл/выкл. Состояние в `localStorage` (`sound.enabled`) внутри
  существующего объекта `st` (новый ключ `soundEnabled`), чтобы переживать 30-мин
  аварийный reload.
- `AudioContext` создаётся/резюмируется на **первом** жесте пользователя (`pointerdown`/`keydown`,
  один раз). До клика — звука нет (ограничение браузеров, не обходимое).
- Паттерны (gain-огибающая, безопасные значения, всё в try/catch):
  - **сирена** (danger, rocket, aviation): sawtooth, частота 520→740→520 Гц, ~1.6 с;
  - **двойной бип** (sighting, interception, attention): 880 Гц ×2 коротких импульса;
  - **info / clear** — тишина.
- Если `AudioContext` недоступен — тихий no-op.

### 4. Детекция событий области и новизны

- `SOUND_TYPES = {danger, rocket, aviation, attention, sighting, interception}`.
- `yarEvents()`: берём `visibleItems()` (учитывает фильтр времени и скрытые типы) и оставляем:
  - `type ∈ SOUND_TYPES`, `!cleared`, `!no_marker`, `!_fill_only`;
  - точка `(lat, lon)` внутри полигона Ярославской области ИЛИ `direction`
    (`[lat, lon]`) тоже внутри полигона.
- `inYaroslavl(lat, lon)`: ray-casting point-in-polygon по фиче `regionGeoJSON`,
  чей `_key` — ярославская область. Fallback, если геометрии нет: bbox области
  (56.0–58.6 N, 37.5–40.9 E) ИЛИ `subject` содержит «ярослав».
- Новизна: отпечаток `fp = type + '|' + name + '|' + time`.
  - `seen` (объект fp→1) в localStorage.
  - `newFps = fps_yar − seen`. Если есть новые — играем звук типа с **минимальным**
    `typePriority` среди новых (rocket=0 — самый серьёзный, потом danger, …; меньшее число = серьёзнее)
    и добавляем их в `seen`.
  - Чистка: удаляем из `seen` отпечатки старше 6 часов (по `tEpoch(time)` на каждой проверке).
- При включении звука кнопкой: если есть активные события по области прямо сейчас — сыграть
  один раз (проверка работоспособности) и сразу внести их в `seen` (без повторного сигнала).

### 5. Тестирование и верификация

- Регрессии (Python, без изменений): `test_rayon_disambig.py` 29/29, `test_dir_regress.py`,
  `test_day_red.py`, `test_summary_day.py`, `test_lnr_red.py`, `probe_rayon.py`,
  AST-компиляция (`-W error::SyntaxWarning`), `check_braces.py` PASS, `verify_js.py`.
- Новые TDD-тесты (до кода): `test_state_json.py`:
  - `generate_html` создаёт рядом валидный `state.json` (парсится; `markers` == содержимое
    `markers_json`; `feed`, `channels`, `generated_at`, `night_kills` на месте);
  - в HTML нет `meta refresh 300`, есть `refresh 1800`;
  - в footer присутствует кнопка `🔔`;
  - `state_json`/JS не содержат `{{`-коллизий f-string (проверка скобок, как `check_braces`).
- JS-статическая проверка: `verify_js.py` — список функций дополнить
  (`pollState`, `refreshFeed`, `yarEvents`, `inYaroslavl`, `playTone`, `siren`, `beep`).
- По возможности headless-Edge-прогон с mock'ами (`AudioContext` заглушен, `fetch` подменён
  на тестовый `state.json`): «новое событие → запрос звука», «то же событие → тишина»,
  «отбой → тишина». Если headless недоступен — пометить в отчёте, не блокирует.

## Границы (out of scope)

- Push/Web-уведомления (только звук) — возможная следующая итерация.
- Настройка громкости/выбор звука пользователем (фиксированные паттерны).
- Оповещения по соседним регионам (по выбору пользователя — только Ярославская область).

## Файлы

- `F:\Locator\mopedmap.py` — генерация `state.json`, мета-refresh 1800, кнопка `🔔`,
  polling/звук/детекция (JS-блок `generate_html`).
- `F:\Locator\docs\superpowers\specs\2026-09-14-sound-alert-design.md` — этот документ.
- `F:\Locator\CONTEXT.md` — запись о фиче.
- gh-pages: добавляется файл `state.json`.