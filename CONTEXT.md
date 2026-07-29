## Goal
Fix disambiguation bugs, emoji/popup text cleanup, and ensure all Yaroslavl Oblast locations are present in the map generator.

## Constraints & Preferences
- User communicates in Russian; codebase comments in Russian
- Fixes committed and pushed to GitHub automatically
- Disambiguation rules use `DISAMBIGUATION_MAP` with `context_subject` matching
- Duplicate rayon patterns in `REGION_ALIASES` cause first-match-wins issues — never add same pattern to multiple subjects; use `DISAMBIGUATION_MAP` instead
- If a post explicitly names an oblast/krai/republic, false location matches from other regions must be filtered out

## Progress
### Done
- **Пречистое/Первомайский → Тамбовская**: DISAMBIGUATION_MAP redirect (commit `8d36e86`)
- **classify_post: "бпла"/"беспилотн" → sighting**: Fallback before `return "info"` (commit `8d36e86`)
- **Борисоглебский → Воронежская**: REGION_ALIASES + DISAMBIGUATION_MAP (commit `a52f736`)
- **Монастырщина → Воронежская**: City entries + DISAMBIGUATION_MAP (commit `a52f736`)
- **Summary filter: "за последние сутки"**: Added to SUMMARY_PATTERNS (commit `aa692cc`)
- **Красносельский/Белозерский disambiguation**: REGION_ALIASES + DISAMBIGUATION_MAP (commit `08a40fd`)
- **Robust emoji filter in display_text**: Unicode range `[\U0001F300-\U0001F9FF\u2600-\u27BF\uFE00-\uFE0F\u200D]+` (commit `08a40fd`)
- **HTML entity decoding + emoji stripping**: `html.unescape()`, explicit `&#x...;` + `&#...;` removal, `📡`/`🛰`/`⚡`/`🔔` replacement (commits `edfa39a`, `e5926ac`)
- **sanitize_popup_text() function**: Created cleanup function applied to ALL `popup_text` assignments in `generate_html` — strips HTML entities, emoji, channel footers (`Локатор России`, `Радар.*`, `@mention`), metadata line (`type · channel · date`), `Подписаться`. Applied at `original_post` source in `process_posts` + all 7 `popup_text` sites (commits `47e4d8c`, `f51e44b`)
- **Выгоничи → Ивановская/Амурская fix**: Root cause — `extract_directions` splits post; `extract_locations(after, extra_context=full_context)` called on `"в сторону Голубого моста"` had `auto-remove` only checking `_region_subjs` from `results` (empty for `after`), ignoring `extra_context` which held `Брянская область`. Fixed: auto-remove in `extract_locations` now also collects `is_region` subjects from `extra_context`. Added `filter_locations_by_post_region()` safety net at `process_posts` marker level (commit `1902191`)
- **Yaroslavl Oblast missing settlements (14.07.2026)**: Added 13 missing settlements to REGION_ALIASES
- **Yaroslavl Oblast batch 2 (29.07.2026)**: Added 20 locations to REGION_ALIASES
- **Yaroslavl Oblast batch 3 (29.07.2026)**: Added Цеденево and Ямищи to REGION_ALIASES
- **GeoNames mass import (29.07.2026)**: Added ~17 368 settlements to settlements.json from GeoNames RU dump для Ярославской и 6 соседних областей (Тверская, Вологодская, Московская, Костромская, Ивановская, Владимирская). Использованы только ALT-записи (кириллица из alternatenames), отфильтрованы записи с латиницей и дубликаты. Из ~29k ALT → 17 368 чистых. Админ-коды GeoNames: 88 (Ярославская), 77 (Тверская), 85 (Вологодская), 47 (Московская), 37 (Костромская), 21 (Ивановская), 83 (Владимирская). Текущее покрытие: 42 917 записей всего.

### Done (continued)
- **Fleeting vowel handling**: Modified `get_case_forms` for masculine consonant-ending names — tries removing last "о" or "е" before final consonants (Орёл→Орла).
- **Cross-region non-unique names**: Added `include_cross_region_nonunique` parameter for direction extraction (Железногорск in Орловская context).
- **Auto-remove second-guard fix**: Added `not r.get("is_region")` to prevent is_region entries in extra_context from falsely triggering removal of all results.
- **Куйбышевский район disambiguation fix**: Root cause — `DISAMBIGUATION_MAP` key loop for `nl` ("бетлица") would `break` even when no candidate matched, preventing `matched_key` ("куйбышевский") from being checked. Fixed: only `break` from key loop if a candidate actually matched.
- **CHANNELS: ivanovo_radar**: Added source.
- **Airport markers**: REGION_ALIASES entries for аэропорт иваново/ярославль + classify_post rule → "info".
- **Committed & pushed**: Multiple commits for above fixes.
- **Ивановская область marker fix (Issue 2)**: always_show check no longer suppresses explicit region references (matched text содержит "область"/"край"/"республика"). Region suppression by city теперь требует CITY_DB membership. Новое подавление settlement-маркеров при наличии explicit region reference (commit `411a20f`)
- **Рязань/Кораблино dedup fix (Issue 3)**: Region alias coords Рязанской области приведены к cities.json (54.6095→54.61667). В per-sentence dedup добавлено подавление is_region entries, чьи координаты совпадают с CITY_DB capital для того же subject, при наличии других entries с другими координатами (commit `411a20f`)

### In Progress
- (none)

### Blocked
- (none)

## Key Decisions
- **Duplicate rayon patterns**: Never add same pattern to multiple subjects in REGION_ALIASES — use DISAMBIGUATION_MAP for context-based redirects
- **sanitize_popup_text applied at source + output**: Both `original_post` in `process_posts` AND all `popup_text` sites in `generate_html` — belts-and-suspenders approach
- **Auto-remove in extract_locations uses extra_context**: Fixes `extract_directions` path where `after`/`before` text lacks region mention but `extra_context` has it
- **filter_locations_by_post_region**: Separate safety net at process_posts level; redundant with auto-remove fix but provides defense-in-depth
- **Non-unique settlement names in Yaroslavl**: Locations that already exist in settlements.json for other regions (Дубки, Ермолово, Гаврилково, Красный Бор) were added to REGION_ALIASES with Yaroslavl subject to match when post context includes Ярославская область
- **Missing-from-DB entries**: Locations not in settlements.json at all (Телищево, Нижний Поселок, Кобыляево, Шалаево, Грешнево, Полесье, Любашино, Козьмодемьянск, Заволжье) added as new REGION_ALIASES entries

## Next Steps
1. Коммитнуть и запушить
2. Удалить временные файлы (check_settlements.py, check_s.py, check_result.txt, rayon_debug.py)
3. (опционально) Добавить Никольское и районы Ярославля, если пользователь попросит

## Critical Context
- `REGION_ALIASES` at line ~170 — linear search, first match wins
- `ALL_PATTERNS` built from REGION_ALIASES + CITY_DB + SETTLEMENT_DB, sorted by pattern length desc
- `extract_locations` at line ~3941 — has auto-remove logic that filters settlements/cities whose region doesn't match any `is_region` result
- Auto-remove now also scans `extra_context` for region subjects (commit `1902191`)
- `extract_directions` at line ~4366 — calls `extract_locations(before)` and `extract_locations(after)` with full-sentence context; direction markers bypass sentence-level filter in process_posts
- `sanitize_popup_text()` defined before `generate_html()` — strips HTML entities, emoji, channel footers, @mentions, metadata line
- Key bug pattern: Common Russian words matching settlement names (e.g., "моста" → Моста, Ивановская; "голубого" → Голубое, Амурская) in unrelated posts
- Бетлица DISAMBIGUATION_MAP entry was blocking Куйбышевский entry: key loop checked `nl="бетлица"` first, entered DISAMBIGUATION_MAP branch (no candidate matched), then `break` prevented `matched_key="куйбышевский"` from being checked
- User is testing with locatorru channel posts (Брянская/Курская/Белгородская области)

## Relevant Files
- `F:\Locator\mopedmap.py`: Main script
- `F:\Locator\CONTEXT.md`: Project context documentation
- `F:\Locator\region_history.json`: Region history cache
- `F:\Locator\cities.json`: City database
- `F:\Locator\settlements.json`: Settlement database
