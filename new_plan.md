# Phase 1 — Form Response Dashboard Implementation Plan

## Context

The repo at `/Users/roesta/Library/CloudStorage/SynologyDrive-work_sync/corus/internal-dashboard` has a thorough design document (`form_response_plan.md`) describing a three-phase dashboard for form responses. **Phase 1 is greenfield** — there is no existing dashboard code. We need a Marimo notebook that reads a schema (`structure/structure_main.csv`, 20 fields) and a sample response file (`sample_data.csv`, 500 rows) and renders one card per field with the field-type-appropriate visualization, summary strip, null toggle, and detail table — per the plan's Section 2 specification.

The intended outcome is a working draft dashboard that validates the visualisation mapping against realistic data before Phase 2 (Metabase integration) and Phase 3 (insights/correlation) are scoped.

## Decisions locked with the user

- **Module layout**: split into `field_aggregators.py`, `null_detector.py`, and the marimo notebook `form_response_dashboard.py` (3 new files).
- **Detail tables**: show `name` (from data) + 1-based row index. No `collector_name` / `id` exist in sample data.
- **Data source**: hardcoded path to `sample_data.csv` with a `mo.ui.run_button` Refresh that re-reads on click.
- **Scope**: implement all 17 field types in the schema. Skip `matrix` (not in schema).
- **`range` rendering**: bin like numeric (Bar/Histogram/Box/Violin dropdown). The plan's literal one-bar-per-value would produce a 200-bar chart with sample data.
- **Parse failures**: surface separately via a `parse_failed_count` and a callout on the card — do not silently bucket into nulls (avoids biasing completeness analysis).
- **Email subtype**: build a small anywidget that renders the email detail table with mailto links (plan-faithful).
- **Skip-logic callout**: applies to any field with non-empty `skipLogic`, not only decimal. (Today only `decimal_test` qualifies.)

## Critical files

**To create:**
- `field_aggregators.py` — schema/data loading + per-field-type aggregators + dispatcher
- `null_detector.py` — empty-string and sentinel normalization to Polars nulls
- `form_response_dashboard.py` — the Marimo notebook

**To reuse:**
- `generate_variables.py:46-62` — `load_schema()` function; lift verbatim into `field_aggregators.py`

**Read-only references:**
- `form_response_plan.md` — design source of truth
- `structure/structure_main.csv` — field schema
- `sample_data.csv` — response data

## Module API

### `null_detector.py`

```python
NULL_SENTINELS = ["", "N/A", "n/a"]

def normalize_nulls(df: pl.DataFrame, col: str) -> pl.DataFrame
def normalize_nulls_all(df: pl.DataFrame) -> pl.DataFrame   # all Utf8 cols
def null_count(s: pl.Series) -> int
def valid_count(s: pl.Series) -> int
```

Implementation: strip → membership check against `NULL_SENTINELS` → `pl.when(...).then(None).otherwise(...)`. Operates only on Utf8 columns.

### `field_aggregators.py`

Common return shape from every aggregator:

```python
AggregatorResult = {
    "field": dict,                   # schema row
    "total_count": int,              # valid (non-null, parsed-successfully) responses
    "null_count": int,               # missing/null/empty
    "parse_failed_count": int,       # values that failed type parsing (date/numeric)
    "n_total": int,                  # df.height
    "stats": dict | None,            # min/max/mean/median or earliest/latest
    "chart_data": {                  # both variants pre-computed at aggregate time
        "exclude_nulls": pl.DataFrame | None,
        "include_nulls": pl.DataFrame | None,
    },
    "group_table": pl.DataFrame | None,
    "detail_rows": pl.DataFrame,     # always: ["#", "name", <field_name>]
    "render_mode": str,              # "categorical" | "numeric" | "temporal" | "text" | "summary_only"
    "has_skip_logic": bool,
}
```

Public functions:

```python
def load_schema(path) -> list[dict]                 # lifted from generate_variables.py
def load_responses(csv_path) -> pl.DataFrame        # read all as Utf8, normalize_nulls_all
def aggregate_field(df, field) -> AggregatorResult  # dispatcher on field["type"]
```

Per-type handlers (private):

| Handler | Field types | Notes |
|---------|-------------|-------|
| `_agg_select_one` | select_one | value→label map from `field["options"]`; unknown values pass through raw |
| `_agg_select_multiple` | select_multiple | split on `,`, strip, drop empties, explode, group, map to labels |
| `_agg_toggle` | toggle | hard-code categories `["On", "Off"]` (schema options empty for toggles) |
| `_agg_text` | text | detail rows only; subtype="email" sets a flag for the email widget |
| `_agg_numeric` | integer, decimal, range, percent, auto_calculated | cast to Float64 strict=False; min/max/mean/median; pre-bin to ~20 buckets |
| `_agg_date` | date | `str.to_date("%d-%b-%y", strict=False)`; daily count series |
| `_agg_time` | time | `str.to_time("%H:%M", strict=False)`; hourly count series |
| `_agg_datetime` | datetime | `str.to_datetime("%d/%m/%Y %H:%M", strict=False)`; daily count series |
| `_agg_summary_only` | image, file, barcode, geopoint, geo_area | counts only; no chart_data |

**Format parsing strategy**: cast at aggregator time (not CSV load). `strict=False` emits null for failures; we count those separately as `parse_failed_count` by comparing pre- and post-cast null counts.

**`select_multiple` parsing**: `pl.col(c).str.split(",").list.eval(pl.element().str.strip_chars()).list.eval(pl.element().filter(pl.element() != ""))`. Respondent total = rows with non-empty resulting list. Per-option count via `.explode().group_by()`.

## Notebook structure — `form_response_dashboard.py`

Use a **single rendering function** approach, not 5 cells × 20 fields. 12 cells total:

| # | Purpose |
|---|---------|
| 1 | Imports: `marimo as mo`, `polars as pl`, `plotly.express as px`, helpers |
| 2 | Constants: `SCHEMA_PATH`, `DATA_PATH` |
| 3 | `schema = load_schema(SCHEMA_PATH)` (filter out matrix defensively) |
| 4 | `refresh_btn = mo.ui.run_button(label="Refresh")` |
| 5 | `_ = refresh_btn.value; df = load_responses(DATA_PATH)` — depends on button |
| 6 | Page header: title, file mtime, total row count, refresh button |
| 7 | `null_toggles = {f["name"]: mo.ui.checkbox(value=True, label="Exclude nulls") for f in categorical_fields}` |
| 8 | `numeric_chart_types = {f["name"]: mo.ui.dropdown(["Bar (binned)", "Histogram", "Box", "Violin"], value="Bar (binned)") for f in numeric_fields}` |
| 9 | `detail_toggles = {f["name"]: mo.ui.switch(value=False) for f in schema}` |
| 10 | `aggregates = {f["name"]: aggregate_field(df, f) for f in schema}` |
| 11 | `render_field_card(field, agg, null_toggle, chart_type, detail_toggle) -> mo.vstack` function definition |
| 12 | `mo.vstack([render_field_card(...) for f in schema])` |

**Reactivity**: dict-valued cells (`null_toggles`, `numeric_chart_types`) collapse 20 widgets into 1 marimo dependency each. Toggling any widget re-runs only the render cell (12), not the aggregation cell (10). The Refresh button re-runs cell 5 → 10 → 12.

**Email widget**: a small `anywidget.AnyWidget` subclass rendered inside `render_field_card` when `field["subtype"] == "email"`. HTML table with `<a href="mailto:...">` cells. Used in place of `mo.ui.table` for that one case.

## Phase-1 deferrals (cut from this iteration)

- "Last updated" auto-refresh ticker — show static file mtime.
- "Show more" per-row expander on long text — let `mo.ui.table` truncate.
- Custom pagination — use `mo.ui.table(page_size=20)`.
- Custom CSS for card borders / null-category grey — Plotly's `color_discrete_map={"Null": "lightgrey"}` is enough.
- Field-type badge styling — render as inline `[type]` markdown.

## Implementation order

Build inside-out so each layer is verifiable before the next.

1. `null_detector.py` — `normalize_nulls`, verify empty `email` becomes null on sample data.
2. `field_aggregators.load_schema` + `load_responses` — verify shapes (20 fields, 500 rows, columns match).
3. `_agg_summary_only` (image, file, barcode) — verify `total_count + null_count == 500`.
4. `_agg_select_one` (sex) — verify value→label mapping (`m` → `male`).
5. `_agg_toggle` (is_teacher, is_student) — verify hard-coded `On`/`Off` categories.
6. `_agg_select_multiple` (fav_subject) — verify respondent total ≤ option-count sum.
7. `_agg_numeric` (int_test, then percent_test, decimal_test, range_test, autocalc_test) — verify stats, binning, parse_failed_count on a manually corrupted row.
8. `_agg_text` (name, email, gender2) — verify detail rows shape.
9. `_agg_date` / `_agg_time` / `_agg_datetime` — verify parsing with `strict=False`, parse_failed_count tracking.
10. `aggregate_field` dispatcher — iterate all 20 schema fields; assert no exceptions.
11. Notebook cells 1–6 (imports, schema, refresh, data, header). Click refresh; verify cell 5 re-fires.
12. Notebook cells 7–10 (UI dicts + aggregation). Toggle widgets; verify state.
13. `render_field_card` — summary_only fields first.
14. Categorical rendering (select_one, toggle, select_multiple) + null toggle reactivity.
15. Numeric rendering + chart-type dropdown.
16. Temporal rendering + parse-failure callout.
17. Text rendering + email anywidget for email subtype.
18. Detail tables for non-text fields behind `mo.ui.switch`.

## Verification (end-to-end)

Run inside the marimo session (port 2720 already running):

**Aggregator sanity checks** (ad-hoc cells, deleted after):
```python
assert aggregates["sex"]["chart_data"]["exclude_nulls"].height == 2
assert aggregates["fav_subject"]["group_table"]["count"].sum() >= aggregates["fav_subject"]["total_count"]
assert set(aggregates["int_test"]["stats"]) == {"min", "max", "mean", "median"}
assert aggregates["decimal_test"]["has_skip_logic"] is True
assert aggregates["int_test"]["has_skip_logic"] is False
assert aggregates["image_test"]["render_mode"] == "summary_only"
assert aggregates["autocalc_test"]["total_count"] == 0  # generator emits empty
```

**UI smoke test** in the browser:
- Click Refresh → header timestamp / row count refreshes.
- Toggle `sex` null exclusion → pie chart adds grey "Null" slice when count > 0.
- Cycle `int_test` chart type through all four options → chart re-renders.
- Switch `decimal_test` detail toggle → card shows "skip logic" callout + 500-row paginated table.
- Email card's detail table renders mailto links (click one to confirm).
- Corrupt one date in `sample_data.csv`, click Refresh → `date_test` card shows parse-failure callout with count = 1.

## Open gaps that are **NOT** blockers

These have explicit resolutions baked in above; flagged here so reviewers can spot deviations from the plan document:

- **G3**: page-level "Total Accepted Submissions" defined as `df.height`. Subtitle text: *"Total rows in source file."*
- **G5**: `gender2` (`type: "text"`) renders as text per schema, despite the name suggesting categorical.
- **G7** (resolved): `range` binned like numeric.
- **G8**: `autocalc_test` reports 0 valid / 500 null — aggregator handles gracefully.
