# Параллельная загрузка каналов — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ускорить сбор данных, распараллелив сетевую загрузку Telegram-каналов в `fetch_all` через `ThreadPoolExecutor`, с восстановлением исходного порядка постов.

**Architecture:** Вынести параллельный запуск списка callable-задач (по одной на канал + API) в отдельную тестируемую функцию `_fetch_posts_parallel(jobs, max_workers)`, которая собирает результаты по индексу и конкатенирует в исходном порядке. `fetch_all` строит список задач и делегирует пулу.

**Tech Stack:** Python 3 stdlib — `concurrent.futures`, `os`, `requests`. Никаких новых зависимостей.

## Global Constraints

- Кэш GeoJSON в этой задаче НЕ реализуется (отложен отдельно). Меняем только `fetch_all` и добавляем `_fetch_posts_parallel`.
- Порядок результирующего списка постов должен совпадать с текущим (каналы в порядке `CHANNELS`, затем `fetch_radarmap_api`).
- Код и комментарии — на русском (соглашение проекта).
- Одна ошибка в одном канале не должна ронять весь прогон (задача возвращает `[]` для упавшего индекса).
- Синтаксис и существующие маркер-кейсы не должны регрессировать.

---

### Task 1: Новая `_fetch_posts_parallel` + рефакторинг `fetch_all`

**Files:**
- Modify: `F:\Locator\mopedmap.py` (заменить `fetch_all` на строках 4331-4341; добавить `_fetch_posts_parallel` перед `fetch_all`)
- Add import: `from concurrent.futures import ThreadPoolExecutor` в верхней части файла (проверить, есть ли уже; если нет — добавить в блок импортов)
- Test: `C:\Users\SamLab\AppData\Local\Temp\opencode\test_fetch_parallel.py` (временный, удалить после подтверждения)

**Interfaces:**
- Consumes: существующие `fetch_channel(url, name, hours_filter)` (mopedmap.py:4204, возвращает `list[(clean, display, name, dt)]`) и `fetch_radarmap_api(hours_filter)` (mopedmap.py:4292, возвращает `list[(text, label, dt)]`).
- Produces:
  - `_fetch_posts_parallel(jobs, max_workers) -> list` — `jobs: list[(int, callable)]`; вызывает каждый `callable()` (возвращающий list); на исключение возвращает `[]` для этого индекса; конкатенирует результаты в порядке `index`.
  - `fetch_all(hours_filter=None) -> list` — тот же контракт, что и раньше.

- [ ] **Step 1: Проверить импорт потока**

Найти строку импортов в `F:\Locator\mopedmap.py` (в начале файла). Если `concurrent.futures` ещё не импортирован — добавить рядом с прочими импортами:
```python
from concurrent.futures import ThreadPoolExecutor
```
(Проверить `grep -n "concurrent" mopedmap.py`; добавить только если отсутствует.)

- [ ] **Step 2: Написать падающий тест**

Файл `C:\Users\SamLab\AppData\Local\Temp\opencode\test_fetch_parallel.py`:
```python
# -*- coding: utf-8 -*-
import sys, time
sys.path.insert(0, r'F:\Locator')
import mopedmap as m

def test_order_and_collect():
    def job(v, delay):
        def f():
            time.sleep(delay)
            return [v]
        return f
    jobs = [
        (0, job('channel_a', 0.3)),
        (1, job('channel_b', 0.0)),
        (2, job('api', 0.2)),
    ]
    res = m._fetch_posts_parallel(jobs, max_workers=3)
    assert res == ['channel_a', 'channel_b', 'api'], f"порядок нарушен: {res}"

def test_exception_isolated():
    def ok():
        return ['ok']
    def boom():
        raise RuntimeError('boom')
    jobs = [(0, boom), (1, ok), (2, boom)]
    res = m._fetch_posts_parallel(jobs, max_workers=3)
    assert res == ['ok'], f"ошибка не изолирована: {res}"

def test_empty_jobs():
    assert m._fetch_posts_parallel([], max_workers=1) == []

test_order_and_collect()
print("test_order_and_collect: PASS")
test_exception_isolated()
print("test_exception_isolated: PASS")
test_empty_jobs()
print("test_empty_jobs: PASS")
```

- [ ] **Step 3: Запустить тест — ожидать FAIL**

Run:
```powershell
$env:PYTHONIOENCODING='utf-8'; python -B C:\Users\SamLab\AppData\Local\Temp\opencode\test_fetch_parallel.py
```
Expected: `AttributeError: module 'mopedmap' has no attribute '_fetch_posts_parallel'`

- [ ] **Step 4: Написать минимальную реализацию**

Заменить `fetch_all` (строки 4331-4341) и добавить перед ним `_fetch_posts_parallel`:
```python
def _fetch_posts_parallel(jobs, max_workers):
    """Запустить каждый callable в пуле потоков, сохранить порядок index."""
    results = {}
    def run(index, fn):
        try:
            results[index] = list(fn())
        except Exception:
            results[index] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(run, idx, fn) for idx, fn in jobs]
        for fut in futures:
            fut.result()
    ordered = []
    for idx, _fn in sorted(jobs, key=lambda p: p[0]):
        ordered.extend(results.get(idx, []))
    return ordered


def fetch_all(hours_filter=None):
    window = hours_filter if hours_filter is not None else HOURS_FILTER
    print(f"Загрузка постов из Telegram (окно {window}ч)...")
    jobs = []
    for i, ch in enumerate(CHANNELS):
        jobs.append((i, lambda h=hours_filter, u=ch["url"], n=ch["name"]: fetch_channel(u, n, h)))
    jobs.append((len(CHANNELS), lambda h=hours_filter: fetch_radarmap_api(h)))
    workers = min(os.cpu_count() or 1, len(jobs))
    all_posts = _fetch_posts_parallel(jobs, max_workers=workers)
    print(f"Всего загружено: {len(all_posts)} постов")
    return all_posts
```

- [ ] **Step 5: Запустить тест — ожидать PASS**

Run:
```powershell
$env:PYTHONIOENCODING='utf-8'; python -B C:\Users\SamLab\AppData\Local\Temp\opencode\test_fetch_parallel.py
```
Expected: все три `PASS`.

- [ ] **Step 6: Проверить синтаксис и импорты**

Run:
```powershell
$env:PYTHONIOENCODING='utf-8'; python -B -c "import ast; ast.parse(open(r'F:\Locator\mopedmap.py', encoding='utf-8').read()); print('OK')"
```
Expected: `OK` (нет синтаксических ошибок). Заодно убедиться, что `os` и `ThreadPoolExecutor` доступны (проверить `grep -n "^import os"` / `grep -n "concurrent" mopedmap.py`).

- [ ] **Step 7: Быстрая регрессия существующих кейсов**

Run (пустой/короткий прогон без сети — проверить, что модуль импортируется и старые маркер-функции не тронуты):
```powershell
$env:PYTHONIOENCODING='utf-8'; python -B -c "import sys; sys.path.insert(0, r'F:\Locator'); import mopedmap; print('import OK; fetch_all=', mopedmap.fetch_all is not None)"
```
Expected: `import OK; fetch_all= True`.

- [ ] **Step 8: Commit**

```bash
git add F:/Locator/mopedmap.py
git commit -m "perf: параллельная загрузка каналов во fetch_all через ThreadPoolExecutor"
git push
```

- [ ] **Step 9: Удалить временный тест**

Удалить `C:\Users\SamLab\AppData\Local\Temp\opencode\test_fetch_parallel.py` (это вне репозитория, но чистота).

---

### Task 2: Документация и регрессия корпуса

**Files:**
- Modify: `F:\Locator\CONTEXT.md` (добавить запись в «Done»)
- Test: регрессия по корпусу (см. шаги)

- [ ] **Step 1: Обновить CONTEXT.md**

Добавить в раздел «Done» запись:
```
- **Параллельная загрузка каналов (28.08.2026)**: `fetch_all` последовательно тянул ~10 Telegram-каналов (до 20 страниц HTTP каждый). Добавлены `_fetch_posts_parallel(jobs, max_workers)` (ThreadPoolExecutor, восстановление порядка по index, изоляция ошибок — упавший канал → `[]`) и рефакторинг `fetch_all` на список задач. Порядок результирующих постов сохранён (каналы в порядке CHANNELS, затем radar-map.ru API). CPU-этап уже оптимизирован (`9eddeed`); узкий край — именно сеть. Ограничение числа воркеров (3-4) — при необходимости позже, если Telegram начнёт резать параллельные web-превью. Spec: `docs/superpowers/specs/2026-08-28-parallel-fetch-design.md`.
```

- [ ] **Step 2: Полный live-прогон (по желанию, сеть вариабельна)**

Run: `cd F:\Locator; $env:PYTHONIOENCODING='utf-8'; python -B mopedmap.py`
Expected: полный цикл fetch→process→generate, `Сгенерирована карта: ...`. Замерить время `fetch`-этапа (для понимания выигрыша). Не блокировать завершение задачи на медленной сети.

- [ ] **Step 3: Commit**

```bash
git add F:/Locator/CONTEXT.md
git commit -m "docs: параллельная загрузка каналов (CONTEXT)"
git push
```

---

## Self-Review

**Spec coverage:** Дизайн требует: (1) рефакторинг `fetch_all` + новая `_fetch_posts_parallel` — Task 1; (2) порядок постов сохранён — Task 1 шаг 4 (`sorted(jobs, key=index)`); (3) изоляция ошибок — Task 1 (`try/except` в `run`); (4) число воркеров `min(cpu, len(jobs))` — Task 1; (5) тестирование пула без сети (порядок/ошибка/пусто) — Task 1 шаг 2; (6) документация — Task 2. Всё покрыто.

**Placeholder scan:** Нет TBD/TODO; каждый кодшаг содержит полный код. Шаг 7 Task 1 и Step 2 Task 2 — команды с ожидаемым выводом.

**Type consistency:** `_fetch_posts_parallel(jobs: list[(int, callable)], max_workers: int) -> list` используется единообразно; `fetch_all(hours_filter=None) -> list` сохраняет прежнюю сигнатуру. `jobs` в Task 1 построен с `(i, lambda ...)` и `(len(CHANNELS), lambda ...)` — соответствует `(int, callable)`. Ок.
