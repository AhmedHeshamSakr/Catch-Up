# Plan 3 — Output Breadth (Excel + HTML) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Render each digest as a styled **Excel workbook** (master + per-category sheets) and a self-contained **"Signal"-themed HTML dashboard**, in addition to the existing Markdown — all from the enriched `NewsItem` data, integrated into `run_digest()`.

**Architecture:** Two new deterministic renderer modules in `app/services/render/` (siblings of `markdown.py`), wired into `run_digest` alongside the Markdown renderer. No LLM, no API keys, no network — fully unit-testable (read Excel back with openpyxl; assert HTML structure + HTML-escaping for XSS safety).

**Tech Stack:** openpyxl (Excel) · Python stdlib `html` (escaping) · existing domain/render modules.

---

## File structure (this plan)

```
app/services/render/
├── markdown.py   # existing
├── excel.py      # NEW — render_workbook(), write_excel()
└── html.py       # NEW — render_html(), write_html()
app/runner.py     # write xlsx + html alongside md
tests/unit/{test_excel,test_html}.py
docs/             # (smoke output goes to output/, gitignored)
```

---

### Task 1: Add openpyxl dependency

- [ ] **Step 1:** `uv add openpyxl`
- [ ] **Step 2:** Verify: `uv run python -c "import openpyxl; print(openpyxl.__version__)"`
- [ ] **Step 3:** Commit:
```bash
git add pyproject.toml uv.lock
git commit -m "build: add openpyxl for Excel rendering"
```

---

### Task 2: Excel renderer

**Files:** Create `app/services/render/excel.py`; Test `tests/unit/test_excel.py`.

- [ ] **Step 1: Failing test** — `tests/unit/test_excel.py`:
```python
from openpyxl import load_workbook

from app.core.domain import (
    Category, DigestRun, Entity, Importance, NewsItem, RawItem, Sentiment, SourceType,
)
from app.services.render import excel


def _item(title, cat, *, summary="A summary.", imp=Importance.HIGH):
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="Src",
                  url="https://a.com/x", title=title, category_hint=cat)
    it = NewsItem.from_raw(raw, run_id="r1")
    it.category = cat
    it.summary_en = summary
    it.summary_ar = "ملخص"
    it.importance = imp
    it.entities = [Entity(name="OpenAI", type="org")]
    it.sentiment = Sentiment.NEUTRAL
    return it


def test_write_excel_has_master_and_category_sheets(tmp_path):
    run = DigestRun(run_id="rX")
    items = [_item("AI thing", Category.AI_TECH), _item("Gulf thing", Category.GULF_MENA)]
    path = excel.write_excel(run, items, str(tmp_path))
    assert path.endswith("digest-rX.xlsx")

    wb = load_workbook(path)
    assert "All News" in wb.sheetnames
    assert "AI & Technology" in wb.sheetnames
    assert "Gulf & MENA" in wb.sheetnames

    master = wb["All News"]
    assert [c.value for c in master[1]] == excel.HEADERS
    titles = [master.cell(row=r, column=2).value for r in range(2, master.max_row + 1)]
    assert "AI thing" in titles and "Gulf thing" in titles

    ai_sheet = wb["AI & Technology"]
    ai_titles = [ai_sheet.cell(row=r, column=2).value for r in range(2, ai_sheet.max_row + 1)]
    assert ai_titles == ["AI thing"]  # only AI items on that sheet


def test_excel_row_maps_all_fields(tmp_path):
    run = DigestRun(run_id="rY")
    path = excel.write_excel(run, [_item("Headline", Category.AI_TECH)], str(tmp_path))
    row = list(load_workbook(path)["All News"][2])
    values = [c.value for c in row]
    assert "Headline" in values
    assert "A summary." in values
    assert "HIGH" in values
    assert "OpenAI" in values
```

- [ ] **Step 2: Run → FAIL** — `uv run pytest tests/unit/test_excel.py -q`.

- [ ] **Step 3: Implement** — `app/services/render/excel.py`:
```python
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.core.domain import DigestRun, NewsItem
from app.services.render.markdown import CATEGORY_TITLES

HEADERS = [
    "Date", "Title", "Summary (EN)", "Summary (AR)", "Category",
    "Source", "URL", "Importance", "Entities", "Sentiment",
]
_WIDTHS = [18, 50, 60, 60, 20, 18, 40, 12, 30, 12]
_HEADER_FILL = PatternFill("solid", fgColor="0F172A")
_HEADER_FONT = Font(bold=True, color="FFFFFF")


def _row(item: NewsItem) -> list[str]:
    when = item.published_at or item.collected_at
    category = CATEGORY_TITLES.get(item.category, "Uncategorized") if item.category else "Uncategorized"
    return [
        when.strftime("%Y-%m-%d %H:%M") if when else "",
        item.title,
        item.summary_en or "",
        item.summary_ar or "",
        category,
        item.source_name,
        item.url,
        item.importance.value.upper() if item.importance else "",
        ", ".join(e.name for e in item.entities),
        item.sentiment.value if item.sentiment else "",
    ]


def _write_sheet(ws: Worksheet, items: list[NewsItem]) -> None:
    ws.append(HEADERS)
    for col in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    for item in items:
        ws.append(_row(item))
    ws.freeze_panes = "A2"
    for i, width in enumerate(_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width


def render_workbook(run: DigestRun, items: list[NewsItem]) -> Workbook:
    wb = Workbook()
    master = wb.active
    master.title = "All News"
    _write_sheet(master, items)
    for category, title in CATEGORY_TITLES.items():
        group = [i for i in items if i.category == category]
        if group:
            _write_sheet(wb.create_sheet(title=title), group)
    return wb


def write_excel(run: DigestRun, items: list[NewsItem], output_dir: str) -> str:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"digest-{run.run_id}.xlsx"
    render_workbook(run, items).save(str(path))
    return str(path)
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/unit/test_excel.py -q` → 2 passed.

- [ ] **Step 5: Commit**
```bash
git add app/services/render/excel.py tests/unit/test_excel.py
git commit -m "feat(render): Excel workbook (master + per-category sheets)"
```

---

### Task 3: HTML dashboard renderer (Signal theme, XSS-safe)

**Files:** Create `app/services/render/html.py`; Test `tests/unit/test_html.py`.

- [ ] **Step 1: Failing test** — `tests/unit/test_html.py`:
```python
from app.core.domain import Category, DigestRun, Importance, NewsItem, RawItem, SourceType
from app.services.render import html as html_render


def _item(title, summary, imp, cat):
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="Src",
                  url="https://a.com/x", title=title, category_hint=cat)
    it = NewsItem.from_raw(raw, run_id="r1")
    it.category = cat
    it.summary_en = summary
    it.importance = imp
    return it


def test_render_html_includes_narrative_sections_and_badge():
    run = DigestRun(run_id="r1", narrative="The big picture today.")
    items = [_item("AI launch", "A summary.", Importance.HIGH, Category.AI_TECH)]
    out = html_render.render_html(run, items)
    assert "<!DOCTYPE html>" in out
    assert "The big picture today." in out
    assert "AI launch" in out
    assert "A summary." in out
    assert "HIGH" in out
    assert "AI &amp; Technology" in out  # category title HTML-escaped


def test_render_html_escapes_untrusted_content():
    run = DigestRun(run_id="r1", narrative="<b>x</b>")
    items = [_item("<script>alert(1)</script>", "<img src=x>", Importance.LOW, Category.AI_TECH)]
    out = html_render.render_html(run, items)
    assert "<script>alert(1)</script>" not in out         # raw injection absent
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out  # escaped form present
    assert "&lt;img src=x&gt;" in out
    assert "&lt;b&gt;x&lt;/b&gt;" in out                   # narrative escaped


def test_write_html_creates_file(tmp_path):
    run = DigestRun(run_id="rZ")
    path = html_render.write_html(run, [_item("t", "s", Importance.MEDIUM, Category.AI_TECH)], str(tmp_path))
    assert path.endswith("digest-rZ.html")
    from pathlib import Path
    assert "<!DOCTYPE html>" in Path(path).read_text(encoding="utf-8")
```

- [ ] **Step 2: Run → FAIL**.

- [ ] **Step 3: Implement** — `app/services/render/html.py`:
```python
from __future__ import annotations

import html
from pathlib import Path

from app.core.domain import Category, DigestRun, Importance, NewsItem
from app.services.render.markdown import CATEGORY_TITLES

# importance -> (label, text color, bg)
_BADGE: dict[Importance, tuple[str, str, str]] = {
    Importance.HIGH: ("HIGH", "#DC2626", "#FEF2F2"),
    Importance.MEDIUM: ("MEDIUM", "#A16207", "#FEFCE8"),
    Importance.LOW: ("LOW", "#0E7490", "#ECFEFF"),
}

_STYLE = """
:root{--bg:#F4F6F9;--surface:#fff;--line:#E6EBF1;--ink:#0B1220;--sub:#64748B;--emerald:#059669;--cyan:#0891B2}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:'Inter',system-ui,sans-serif;line-height:1.5}
.wrap{max-width:880px;margin:0 auto;padding:32px 20px}
h1{font-size:24px;letter-spacing:-.02em;margin:0 0 4px}
.meta{color:var(--sub);font-size:13px;margin-bottom:24px}
.lead{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--emerald);
border-radius:12px;padding:16px 18px;margin-bottom:24px}
.lead h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--emerald);margin:0 0 8px}
h3{font-size:15px;margin:24px 0 12px;color:var(--ink)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:10px}
.card a{color:var(--ink);text-decoration:none;font-weight:600}
.card a:hover{color:var(--cyan)}
.sum{color:var(--sub);font-size:13.5px;margin-top:6px}
.row{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}
.badge{font-size:10px;font-weight:700;padding:3px 8px;border-radius:999px;letter-spacing:.04em}
.src{color:#94A3B8;font-size:11.5px}
"""


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def _card(item: NewsItem) -> str:
    badge = ""
    if item.importance and item.importance in _BADGE:
        label, fg, bg = _BADGE[item.importance]
        badge = f'<span class="badge" style="color:{fg};background:{bg}">{label}</span>'
    summary = f'<div class="sum">{_esc(item.summary_en)}</div>' if item.summary_en else ""
    return (
        f'<div class="card"><a href="{_esc(item.url)}">{_esc(item.title)}</a>'
        f'<div class="row">{badge}<span class="src">{_esc(item.source_name)}</span></div>'
        f"{summary}</div>"
    )


def render_html(run: DigestRun, items: list[NewsItem]) -> str:
    n_categories = len({i.category for i in items if i.category})
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>News Catch-Up — {run.started_at:%Y-%m-%d}</title>",
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">',
        f"<style>{_STYLE}</style></head><body><div class='wrap'>",
        f"<h1>News Catch-Up</h1>",
        f'<div class="meta">{run.started_at:%A, %d %B %Y · %H:%M UTC} — {len(items)} items across {n_categories} categories</div>',
    ]
    if run.narrative:
        parts.append(f'<div class="lead"><h2>What matters most</h2>{_esc(run.narrative)}</div>')

    grouped: dict[Category | None, list[NewsItem]] = {}
    for item in items:
        grouped.setdefault(item.category, []).append(item)
    for category in [*CATEGORY_TITLES.keys(), None]:
        group = grouped.get(category)
        if not group:
            continue
        title = CATEGORY_TITLES.get(category, "Uncategorized")
        parts.append(f"<h3>{_esc(title)}</h3>")
        parts.extend(_card(i) for i in group)

    parts.append("</div></body></html>")
    return "\n".join(parts)


def write_html(run: DigestRun, items: list[NewsItem], output_dir: str) -> str:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"digest-{run.run_id}.html"
    path.write_text(render_html(run, items), encoding="utf-8")
    return str(path)
```

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/unit/test_html.py -q` → 3 passed.

- [ ] **Step 5: Commit**
```bash
git add app/services/render/html.py tests/unit/test_html.py
git commit -m "feat(render): Signal-themed HTML dashboard (XSS-safe)"
```

---

### Task 4: Wire Excel + HTML into `run_digest`

**Files:** Modify `app/runner.py`; Modify `tests/integration/test_run_digest_intel.py`.

- [ ] **Step 1: Failing test** — append to `tests/integration/test_run_digest_intel.py` (inside the existing enrich test or a new test). Add a new test:
```python
def test_run_digest_writes_all_three_outputs(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr(runner.rss, "collect",
                        lambda s: [_raw("https://x.com/1", "OpenAI launches new model")])

    def fake_processor(items):
        return ProcessingResult(items=[ItemEnrichment(
            id=items[0].id, category=Category.AI_TECH, importance_score=0.9,
            summary_en="A summary.", summary_ar="ملخص.", entities=[], sentiment="neutral")])

    run = runner.run_digest(settings=settings, processor=fake_processor,
                            narrator=lambda items: "Narrative.")
    from pathlib import Path
    assert set(run.outputs) == {"md", "xlsx", "html"}
    for kind in ("md", "xlsx", "html"):
        assert Path(run.outputs[kind]).exists()
```
(`Importance` may already be imported; ensure imports cover what the test uses.)

- [ ] **Step 2: Run → FAIL** — `run.outputs` only has `md`.

- [ ] **Step 3: Implement** — in `app/runner.py`:

Change the render import line:
```python
from app.services.render import excel, markdown
from app.services.render import html as html_render
```
After the existing `run.outputs["md"] = markdown.write_markdown(run, rendered, settings.output_dir)` line, add:
```python
        run.outputs["xlsx"] = excel.write_excel(run, rendered, settings.output_dir)
        run.outputs["html"] = html_render.write_html(run, rendered, settings.output_dir)
```
(Keep everything else identical — these go inside the same try block, right after the markdown write.)

- [ ] **Step 4: Run → PASS** — `uv run pytest tests/integration -q` (all pass).

- [ ] **Step 5: Full suite + lint**
`uv run pytest tests -q` (all green) and `uv run --extra lint ruff check app tests` (clean — fix any nits).

- [ ] **Step 6: Commit**
```bash
git add app/runner.py tests/integration/test_run_digest_intel.py
git commit -m "feat(render): write Excel + HTML alongside Markdown in run_digest"
```

---

### Task 5: No-key render smoke + README

**Files:** Create `scripts/render_smoke.py`; Modify `README.md`.

- [ ] **Step 1:** `scripts/render_smoke.py` — builds 4 sample enriched `NewsItem`s across categories (with EN/AR summaries, importance, entities, sentiment) and a `DigestRun(narrative=...)`, then calls `markdown.write_markdown`, `excel.write_excel`, `html.write_html` into `output/`. Prints the three paths. (No LLM, no key.)

- [ ] **Step 2:** Run it: `uv run python scripts/render_smoke.py`. Confirm `output/digest-*.{md,xlsx,html}` are created. Open the `.html` and `.xlsx` to eyeball the Signal styling / sheets. Paste the printed paths into your report.

- [ ] **Step 3:** README — under "Running locally", note that a run now emits `output/digest-<id>.{md,xlsx,html}` and that `uv run python scripts/render_smoke.py` produces sample outputs without an API key.

- [ ] **Step 4: Commit**
```bash
git add scripts/render_smoke.py README.md
git commit -m "chore(render): no-key render smoke + README outputs note"
```

---

## Self-Review (completed)

- **Spec coverage:** Excel master + per-category sheets §6/§7 ✓; HTML dashboard §6 ✓; Signal design language §17 (light theme, Inter, emerald/cyan, importance badges) ✓; output safety / XSS escaping §15 ✓; integrated into run_digest outputs §6 ✓.
- **Placeholder scan:** none — full code provided; smoke is concrete.
- **Type consistency:** `render_workbook`/`write_excel`, `render_html`/`write_html` mirror the existing `render_markdown`/`write_markdown` signatures `(run, items[, output_dir])`; `CATEGORY_TITLES` reused as the single source of category labels (sheet names + HTML headings).

## Notes for executor
- No API keys / network needed anywhere in this plan; everything is unit-tested.
- Excel sheet names use `CATEGORY_TITLES` values (all ≤31 chars, no illegal chars).
- Run Python via `uv`; lint via `uv run --extra lint ruff check`. Append a BUILD-LOG entry per task. Commit identity AhmedHeshamSakr, **no AI trailers**.
