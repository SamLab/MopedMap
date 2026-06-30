# YarLocator — контекст проекта

## Структура
- `F:\Locator\MopedMap\mopedmap.py` — основной скрипт (генерация карты)
- `F:\Locator\MopedMap\cities.json` — база городов
- `F:\Locator\MopedMap\mopedmap.html` — выходной файл карты
- `F:\Locator\MopedMap\locator_map.html` — старая версия (не обновлялась с мая)

## Каналы (CHANNELS)
locatorru, vrv_radar, radarrussiia, radarYR, russiamonitoring_radar_bpla,
radar_rossia_bpla, radar_yaroslavl, radar_yar76, radarr_yar,
radar_rossii_rossii, LPRalarm, lpr1_treugolnik, migalka_alerts_bot

HOURS_FILTER = 4 (окно 4 часа), обновление каждые 5 мин.

## Сделанные фиксы

### 1. Архангельская → Краснодарский край
Добавлена DISAMBIGUATION_MAP для "архангельская": если в тексте есть "краснодарский край" → станица Архангельская (45.707, 40.350), Краснодарский край.

### 2. Lightning-слои разделены
type=0 (0-15 мин, зелёный) и type=1 (15-30 мин, тёмно-зелёный) в отдельных panes с CSS-фильтрами. Обновление каждые 120с через setInterval(lightningLayer.setUrl).

### 3. max.ru/join/ — полный пропуск поста
Строка 4082: `if "max.ru/join/" in post: filtered += 1; continue`

### 4. Радар Ярославль/Ярославская область — очистка префиксов
clean_message_text: `r'Радар Ярославль\s*[-–—]\s*'` → пусто

### 5. Бетлица/Куйбышевский район
REGION_ALIASES: добавлен Куйбышевский район, Ростовская область (координаты г. Куйбышево).
DISAMBIGUATION_MAP: "куйбышевский район" → Ростовская область.

### 6. Приморск/Акимовка
REGION_ALIASES: добавлена Акимовка, Запорожская область.
DISAMBIGUATION_MAP: "приморск" → Запорожская область.

### 7. Новые каналы
LPRalarm, lpr1_treugolnik, migalka_alerts_bot

### 8. migalka_alerts_bot — полицейская активность
Добавлен в clean_message_text: `r'@migalka_alerts_bot.*$'`. Классифицируется как "info".

### 9. Отображение текста с переносами строк
`<br>` → `\n` в display_text. CSS: `white-space: pre-wrap`.

### 10. Очистка футера из display_text
Удаляются строки, содержащие:
- Локатор России
- Радар Ярославль
- Радар Чувашия
- Обход белых списков
- Радар по всей России
- Мониторинг.РФ / мониторинг.ру / мониторинг.рф
- Мы в MAX

### 11. Пропуск info-постов (без события)
Если classify_post вернул "info" → пропуск (filtered += 1).

### 12. Пропуск сводок (is_summary_post)
SUMMARY_PATTERNS: сводки МО, ночные итоги и т.д.

### 13. История регионов (region_history.json)
Если за последние 4 часа для региона нет событий — на карте показывается контур серым пунктиром с popup `[История]` и последним известным событием. Данные сохраняются в `region_history.json` между запусками. При каждом запуске файл обновляется самым свежим событием на регион.

## Ключевые функции

### fetch_all() → fetch_channel(url, name)
Парсинг `t.me/s/{channel}`. Извлекает data-post, текст, datetime через regex.
Пагинация через `?before={id}` (до 20 страниц по 20 постов).
**Важно:** если t.me недоступен — возвращает пустой список, карта будет с 0 точек.

### clean_message_text(raw, channel)
- Замена <br> → \n, удаление HTML-тегов
- Удаление @username до конца строки
- Удаление футеров (Радар по всей России, Мониторинг.РФ и т.д.)
- Фильтр не-текстовых символов
- Если результат < 10 символов — пост отбрасывается

### fetch_channel — display_text
Второй вариант очистки для отображения:
- <br> → \n, удаление HTML
- Удаление строк-футеров по .*паттерну.*

### classify_post(text)
- crash/smert → "crash"
- опасность по бпла, угроза бпла, опасность бпла → "danger"
- внимание бпла → "attention"
- фиксация бпла, беспилотн → "sighting"
- отмена/отбой опасности → "clear"
- ракетн, крылат, кинжал → "rocket"
- авиационная опасность → "aviation"
- перехват, сбит → "interception"
- остальное → "info"

### extract_locations(text, extra_context)
Ищет паттерны из REGION_ALIASES + CITY_DB + динамические районные формы (-ский/-ской/-цкий + район).
Word boundaries + защита от перекрытий matched_spans.
Возвращает список {"name", "lat", "lon", "type", "matched", "is_region"?, "subject"?}.

### process_posts(posts)
1. Пропуск max.ru/join/
2. Пропуск is_summary_post
3. classify_post → пропуск info
4. extract_directions → если есть, создаёт direction-маркеры
5. Иначе: разбивка на предложения, для каждого — classify_post + extract_locations → маркеры

### dedup_markers(markers)
По ключу (name, lat, lon, type, is_region) — остаётся новейший (или самый длинный текст при равном времени).

### generate_html(markers, geojson_lookup)
- dedup_markers
- region_map: для каждого региона выбирается наиболее серьёзный тип угрозы
- Формирует JSON markers + GeoJSON region fills
- Генерирует HTML с Leaflet.js

### DISAMBIGUATION_MAP
Словарь для неоднозначных названий: ключ — паттерн, значение — (условие в тексте, имя, лат, лон, субъект).
Обрабатывается в extract_locations.

## Исправленный баг: clear отменял danger заливку без учёта времени

### Проблема
Clear (отбой) убирал danger-заливку региона даже если clear был **старше** danger.
Например: отбой в 07:00, опасность в 08:21 — заливка пропадала.

### Причина
**Первый проход** `region_map` (строка ~3401): clear удалял самую серьёзную non-clear угрозу
независимо от времени. Если danger был единственной угрозой — регион получал clear-заливку.

### Фикс
- **Первый проход**: clear-записи не влияют на выбор заливки. Выбирается самая серьёзная
  non-clear угроза (danger).
- **Второй проход** (clear override, строка ~3647): уже проверяет время —
  `clear_time >= fill_time`. Если clear новее — убирает заливку. Если старше — оставляет.
- **Coordinate-level логика**: убран `cleared=True` (только `no_marker=True`), чтобы danger
  не скипался во втором проходе.

Итог: clear убирает заливку только если он **новее** danger. Если danger свежее — заливка остаётся.

## PUSH
Пользователь: "давай ты будешь сам пушить дальше" — коммитить и пушить без запроса.
