# Form Response Dashboard — Implementation Plan

**Phases:** Phase 1 — Draft (Marimo + Python + Polars + Plotly) → Phase 2 — Production (Metabase API Integration) → Phase 3 — Insights Section (Polars + statsmodels + Plotly)  
**Goal:** A lightweight, default, per-field visualization dashboard tied to a data table's linked form. Updates dynamically as new responses arrive.

---

## 1. Overview & Objectives

This dashboard provides a read-only, auto-generated view of collected form data. Each field (question) in the linked form maps to a fixed visualization — no configuration required from end users. The goal is to help clients monitor data collection health, spot missing values early, and act on distribution anomalies quickly.

- Phase 1 is a **draft** — built in Marimo for fast iteration and validation
- Phase 2 (**Metabase API integration**) is under discussion — details to be confirmed with the tech team before implementation begins
- Phase 3 (Insights / Correlation) is **under construction** — the concept is defined but requires further discussion to mature before implementation begins
- Lightweight and default — no heavy customization UI
- Works across varying form sizes (small to very large)
- Renders per-field, not per-row

---

## 2. Field Type → Visualization Mapping

Each field card has three zones: a **card header** (variable name + label — see Section 3.4), a **summary strip** (see Section 2.1), and an optional **chart**.

> **Null toggle behaviour** referenced in each field type below follows the global rules defined in Section 4.

### 2.1 Summary Strip (universal — every field type)

```
[ Total Accepted Submissions: 42 ]     [ Missing / Null: 3 ]
```

- **Total Accepted Submissions** = count of non-null, valid responses
- **Missing / Null** = count of null/missing responses (always visible)
- Both always shown regardless of field type

---

### 2.2 Select One (`type: "select_one"`)

**Purpose:** Single-choice categorical field.

**Chart logic:**
- If **2–4 categories** → **Pie chart**
- If **5+ categories** → **Horizontal bar chart**
- Null toggle: `☑ Exclude nulls` (default). When unchecked → "Null" slice/bar added in grey

**Group table with percentages:**

| Category | Count | % of Valid Responses |
|----------|-------|----------------------|
| Male | 18 | 60% |
| Female | 12 | 40% |

> When nulls are included, % column shows % of **all** responses (including null).

---

### 2.3 Multiple Select (`type: "select_multiple"`)

**Purpose:** Multi-choice field — one respondent can pick several options.

> "Total Accepted Submissions" = respondents who answered, not total option selections.

**Chart:** Always a **horizontal bar chart** — one bar per option. Percentages are out of total valid respondents.

**Null toggle:** `☑ Exclude nulls` — when unchecked, a "Null" bar is appended for respondents who skipped this field entirely.

**Group table with percentages:**

| Option | Count | % of Respondents |
|--------|-------|------------------|
| Mathematics | 12 | 40% |
| English | 8 | 27% |

---

### 2.4 Text (`type: "text"`)

**Purpose:** Free-text open response. Covers all subtypes: `none` (plain text), `email`, `phone number`, and similar. No chart — unstructured text does not aggregate meaningfully.

**Subtype handling:**
- `subtype: "none"` → plain text listing
- `subtype: "email"` → same listing but render values as mailto links in the detail table

**Detail table** (visible by default — the listing is the primary value for text fields):

| Collector Name | ID | Response |
|----------------|----|----------|
| Jane Doe | 001 | "The process was clear." |

> Truncate responses at ~120 characters with a per-row "show more" expand. Paginate at 20 rows per page.

---

### 2.5 Integer (`type: "integer"`)

**Purpose:** Whole number numeric field.

**Secondary stats strip** (shown below summary strip):

```
[ Min: 18 ]   [ Max: 65 ]   [ Mean: 34.2 ]   [ Median: 32 ]
```

**Chart:** Dropdown selector to switch between chart types:

| Option | Default? | Best for |
|--------|----------|----------|
| Bar chart (binned) | ✅ Yes | Quick frequency overview |
| Histogram | — | Shape of data spread |
| Box plot | — | Outliers and quartiles |
| Violin plot | — | Distribution + density combined |

- Dropdown sits **above the chart**, left-aligned
- **No null toggle** — nulls always excluded; count shown in summary strip only

---

### 2.6 Decimal (`type: "decimal"`)

**Purpose:** Floating-point numeric field.

> Note: If a decimal field has skip logic configured (e.g. only shown when an integer field is greater than zero), responses may be sparse. This is reflected in the null count naturally. A note is shown on the card: *"This field has skip logic — sparse responses are expected."*

**Secondary stats strip:**

```
[ Min: 1.2 ]   [ Max: 99.8 ]   [ Mean: 45.3 ]   [ Median: 43.1 ]
```

**Chart:** Same dropdown options as Integer (Section 2.5) — Bar (binned), Histogram, Box plot, Violin plot. Bar chart is default.

- **No null toggle** — nulls always excluded; count shown in summary strip only

---

### 2.7 Range (`type: "range"`)

**Purpose:** Numeric range/slider field.

**Chart:** **Horizontal bar chart** — one bar per range value, showing count of respondents who selected it.

**Null toggle:** `☑ Exclude nulls` — when unchecked, a "Null" bar is appended in grey.

---

### 2.8 Date (`type: "date"`)

**Purpose:** Date field.

**Secondary stats strip:**

```
[ Earliest: 2024-01-03 ]     [ Latest: 2024-03-15 ]
```

**Chart:** **Daily response count bar chart** — x-axis = date, y-axis = count of responses on that day.

**No null toggle.** If any null dates exist, show a callout banner below the chart:

> ⚠️ *3 responses have no date recorded and are excluded from this chart.*

---

### 2.9 Time (`type: "time"`)

**Purpose:** Time-of-day field.

**Secondary stats strip:**

```
[ Earliest: 08:30 ]     [ Latest: 17:45 ]
```

**Chart:** **Hourly response count bar chart** — x-axis = hour of day (0–23), y-axis = count. Useful for spotting collection time patterns.

**No null toggle.** If any null times exist, show a callout banner:

> ⚠️ *X responses have no time recorded and are excluded from this chart.*

---

### 2.10 DateTime (`type: "datetime"`)

**Purpose:** Combined date and time field.

**Secondary stats strip:**

```
[ Earliest: 2024-01-03 08:30 ]     [ Latest: 2024-03-15 17:45 ]
```

**Chart:** **Daily response count bar chart** (time component stripped for the chart). Full datetime is available per response.

**No null toggle.** If any null datetimes exist, show a callout banner:

> ⚠️ *X responses have no datetime recorded and are excluded from this chart.*

---

### 2.11 Toggle (`type: "toggle"`)

**Purpose:** Boolean on/off field.

**Chart:** **Pie chart** — always two categories: On and Off.

**Null toggle:** `☑ Exclude nulls` — when unchecked, a "Null" slice is appended in grey.

**Group table with percentages:**

| Value | Count | % of Valid Responses |
|-------|-------|----------------------|
| On | 18 | 60% |
| Off | 12 | 40% |

---

### 2.12 Percent (`type: "percent"`)

**Purpose:** Percentage value field (0–100).

**Secondary stats strip:**

```
[ Min: 5% ]   [ Max: 98% ]   [ Mean: 61.3% ]   [ Median: 63% ]
```

**Chart:** Same dropdown options as Integer/Decimal — Bar (binned), Histogram, Box plot, Violin plot. Bar chart is default. Values rendered with a `%` suffix on axes.

**Null toggle:** `☑ Exclude nulls` — when unchecked, a "Null" bar is appended in grey.

---

### 2.13 Image (`type: "image"`)

**Purpose:** Image upload field.

**No chart. No detail table. No preview.**

**Summary strip only:**

```
[ Total Accepted Submissions: 8 ]     [ Missing / Null: 1 ]
```

---

### 2.14 File (`type: "file"`)

**Purpose:** File upload field.

**No chart. No detail table. No preview.**

**Summary strip only:**

```
[ Total Accepted Submissions: 12 ]     [ Missing / Null: 2 ]
```

---

### 2.15 Auto-calculated (`type: "auto_calculated"`)

**Purpose:** Field whose value is computed automatically from other fields.

Rendered the same as Decimal (Section 2.6) — secondary stats strip + chart dropdown (Bar, Histogram, Box, Violin).

> Auto-calculated fields cannot have nulls entered by collectors, but may be null if source fields are null. Null count reflects this naturally.

---

### 2.16 Geopoint (`type: "geopoint"`)

**Purpose:** GPS coordinate field (latitude + longitude).

**No chart.**

**Summary strip** + informational note:

```
[ Total Accepted Submissions: 20 ]     [ Missing / Null: 3 ]
```

> ℹ️ *Map visualisation of geopoints is out of scope for Phase 1.*

---

### 2.17 Barcode (`type: "barcode"`)

**Purpose:** Barcode or QR code scan field.

**No chart** — barcode values are typically unique identifiers, not categories.

**Summary strip only:**

```
[ Total Accepted Submissions: 15 ]     [ Missing / Null: 0 ]
```

---

### 2.18 Geo Area (`type: "geo_area"`)

**Purpose:** Geographic polygon/area capture field.

**No chart.**

**Summary strip only:**

```
[ Total Accepted Submissions: 10 ]     [ Missing / Null: 2 ]
```

> ℹ️ *Polygon map visualisation is out of scope for Phase 1.*

---

### 2.19 Matrix (`type: "matrix"`)

**Purpose:** Grid field — multiple sub-questions each answered on a shared scale.

**Summary strip:** At the matrix level (not per sub-field).

**Chart:** **Grouped horizontal bar chart** — one group per sub-question (row), bars per scale option.

> **Rationale:** Grouped horizontal bar gives side-by-side comparison across sub-questions without requiring a heatmap library. Best default for Phase 1.

**Null toggle:** `☑ Exclude nulls` — applies at the respondent level (excludes respondents who skipped the entire matrix). When unchecked, "Null" group is appended.

---

## 3. Dashboard Layout

### 3.1 Page-level Structure

```
┌─────────────────────────────────────────────────────────┐
│  [Table Name] — Response Dashboard                      │
│  Form: [Linked Form Name]    Last updated: [timestamp]  │
│  [ 🔄 Refresh ]                                         │
├─────────────────────────────────────────────────────────┤
│  Total Accepted Submissions: 42                         │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Field Card Structure

```
┌── Field Card ────────────────────────────────────────────┐
│  sex                                   [Select One]      │
│  Sex                                                     │
│  ─────────────────────────────────────────────────────   │
│  Total Accepted Submissions: 30      Missing / Null: 2   │
│  ─────────────────────────────────────────────────────   │
│                                    ☑ Exclude nulls       │
│  ┌──────────────┐   ┌───────────────────────────────┐   │
│  │  Pie chart   │   │  Group % table                │   │
│  └──────────────┘   └───────────────────────────────┘   │
│  [ ▼ Show detail responses (30) ]                        │
└──────────────────────────────────────────────────────────┘
```

**Card header anatomy:**
- **Variable name** (machine identifier from the schema) — monospace, smaller font, muted colour
- **Label** (`label` field from schema, e.g. *"Favourite subject"*) — prominent, normal font, card title
- **Field type badge** — e.g. `[Select One]`, right-aligned

### 3.3 Detail Table Rules

- **Collapsed by default** for all field types except Text
- Toggle label shows count: `▼ Show detail responses (30)`
- **Paginated at 20 rows per page**
- Long text responses truncated at ~120 characters with per-row "show more"

### 3.4 Card Header Rules

- **Variable name** — always shown, monospace font, muted/secondary colour (e.g. grey), small size
- **Label** — always shown, prominent, normal font. This is the question text as written in the form
- If a field has no label configured, fall back to displaying the variable name in the label position
- **Field type badge** — pill/tag style, right-aligned in the header row

---

## 4. Null Handling Rules (Global)

> The null toggle UI and per-field behaviour described here are referenced throughout Section 2 (Field Type → Visualization Mapping).

Null handling is consistent and predictable across all field types.

### 4.1 Null Detection

A response is counted as null/missing if it is any of: Python `None`, empty string `""`, whitespace-only string, or configured sentinel values (e.g. `"N/A"`, `-1`). Detection logic is configurable per-deployment — see `null_detector.py` in Section 5.3.

### 4.2 Null Handling by Field Category

| Field Category | Fields | Null Toggle? | Behaviour |
|---|---|---|---|
| **Categorical** | Select One, Multiple Select, Range, Matrix, Toggle, Percent | ✅ Yes — checkbox | Nulls excluded by default (☑ Exclude nulls). When unchecked, a separate **"Null"** category appears in the chart (grey, visually distinct, always last) |
| **Numeric** | INT, Decimal | ❌ No toggle | Nulls always excluded from chart. Count shown in summary strip only |
| **Date/Time** | Date, Time, DateTime | ❌ No toggle | Nulls cannot be placed on a timeline. A **callout banner** below the chart reads: *"X responses have no value recorded and are excluded from this chart."* |
| **Non-chart** | Text (all subtypes), File, Image, Auto-calculated, Barcode | ❌ Not applicable | No chart to toggle. Null count shown in summary strip only |
| **Spatial** | Geopoint, Geo Area | ❌ Not applicable | No chart. Null count in summary strip only |

### 4.3 Null Toggle UI Spec

- Appears **above the chart**, right-aligned, for categorical field types only
- Default state: `☑ Exclude nulls` (checked)
- On uncheck: chart re-renders with "Null" bar/slice appended (grey, labelled "Null")
- The "Null" category is always rendered **last** in chart order
- If there are zero nulls, the "Null" category is never shown even when unchecked
- The summary strip null count does not change when toggled — it always reflects raw data

---

## 5. Data Layer Design

### 5.1 Real Schema Structure

Based on the actual form schema, each field has the following structure:

```python
{
  "key": "field_key",            # internal key
  "name": "field_name",          # variable name (shown in card header)
  "label": "Field Label",        # human label (shown as card title)
  "type": "select_multiple",     # field type — drives visualization mapping
  "subtype": "",                 # subtype (e.g. "email" for text fields)
  "required": True,              # not used in dashboard display
  "options": [                   # category options for select_one / select_multiple
    {"value": "math", "label": "Mathematics"},
    {"value": "english", "label": "English"}
  ],
  "skipLogic": ""                # if non-empty, field may have sparse responses
}
```

### 5.2 Aggregation Module (`field_aggregators.py`)

One function per field type. Each returns:

```python
{
  "total_count": int,       # non-null responses
  "null_count": int,        # missing/null responses
  "chart_data": dict,       # chart-ready structure (with and without nulls)
  "group_table": list,      # [{category, count, pct}]
  "detail_rows": list       # [{collector_name, id, value}]
}
```

All data manipulation uses **Polars** (lazy evaluation where possible for performance on large response sets).

### 5.3 Null Detection (`null_detector.py`)

Polars treats `None` as null natively. The detection layer handles sentinel values on top of that:

```python
import polars as pl

NULL_SENTINELS = ["", "N/A", "n/a"]

def normalize_nulls(df: pl.DataFrame, col: str) -> pl.DataFrame:
    """Replace sentinel strings with null so Polars null_count() works correctly."""
    return df.with_columns(
        pl.when(pl.col(col).is_in(NULL_SENTINELS))
        .then(None)
        .otherwise(pl.col(col))
        .alias(col)
    )

def get_null_count(df: pl.DataFrame, col: str) -> int:
    return df[col].null_count()

def get_valid_count(df: pl.DataFrame, col: str) -> int:
    return df[col].len() - get_null_count(df, col)
```

> **Why Polars:** Polars' lazy evaluation and columnar execution make aggregations on large response sets significantly faster than row-by-row Python logic. All aggregation functions in `field_aggregators.py` should use `pl.LazyFrame` where possible and call `.collect()` only at the point of rendering.

---

## 6. Phase 1 (Draft) — Marimo + Python + Polars + Plotly

### 6.1 Tech Stack

| Component | Choice |
|-----------|--------|
| Notebook framework | Marimo |
| Data processing | Polars |
| Charting | Plotly Express |
| Tables | `mo.ui.table` with Polars DataFrame |
| Null toggle | `mo.ui.checkbox` |
| Chart type switch (INT / Decimal / Percent / Auto-calculated) | `mo.ui.dropdown` |

### 6.2 Cell Structure per Field Card

```
Cell A: [data fetch + aggregation] → field_aggregators.py
Cell B: [summary strip] → mo.hstack() of stat boxes
Cell C: [null checkbox] → mo.ui.checkbox(value=True, label="Exclude nulls")
Cell D: [chart] → plotly figure, reactive to Cell A + Cell C
Cell E: [detail toggle + table] → mo.ui.button() → mo.ui.table() paginated
```

### 6.3 Plotly + Polars Chart Reference

Plotly Express accepts Polars DataFrames directly (since Plotly 5.15). No `.to_pandas()` conversion needed.

```python
import polars as pl
import plotly.express as px

# Pie (Select One / Toggle — 2-4 categories)
px.pie(df, names='category', values='count')

# Horizontal bar (categorical)
px.bar(df, x='count', y='category', orientation='h')

# INT / Decimal / Percent — Bar (binned): bin with Polars first
binned = df.with_columns(
    (pl.col('value') // bin_size * bin_size).alias('bin')
).group_by('bin').agg(pl.len().alias('count')).sort('bin')
px.bar(binned, x='bin', y='count')

# INT / Decimal / Percent — Histogram
px.histogram(df, x='value', nbins=20)

# INT / Decimal / Percent — Box
px.box(df, y='value')

# INT / Decimal / Percent — Violin
px.violin(df, y='value')

# Date / DateTime daily bar
daily = df.group_by('date').agg(pl.len().alias('count')).sort('date')
px.bar(daily, x='date', y='count')

# Time hourly bar
hourly = df.with_columns(
    pl.col('time').dt.hour().alias('hour')
).group_by('hour').agg(pl.len().alias('count')).sort('hour')
px.bar(hourly, x='hour', y='count')

# Matrix grouped horizontal bar
px.bar(df_long, x='count', y='subfield', color='option',
       barmode='group', orientation='h')
```


---

## 7. Phase 2 — Metabase API Integration

> **Status:** Needs to be discussed. Details to be confirmed with the tech team before this phase begins.

---

## 8. Phase 3 — Insights Section

> **Status:** Planned — exact placement within the Insights section is yet to be configured. Tech stack: Polars + statsmodels + Plotly.

### 8.1 Purpose

Phase 3 adds a cross-field correlation analysis layer to the dashboard. Rather than looking at one field in isolation, it surfaces **pairs of fields that are highly correlated** — helping analysts quickly identify patterns, redundant questions, or unexpected relationships in their data.

### 8.2 Field Types Included in Correlation

Based on the real schema (Section 5.1):

| Included | Field Types |
|----------|------------|
| ✅ Yes | `integer`, `decimal`, `range`, `percent`, `auto_calculated`, `select_one`, `select_multiple`, `toggle` |
| ❌ Excluded | `text`, `file`, `image`, `geopoint`, `geo_area`, `barcode`, `date`, `time`, `datetime` |

> Date/Time fields are excluded because temporal values require specialised time-series correlation methods outside the scope of Phase 3.

### 8.3 Correlation Method by Variable Type

Since forms contain mixed field types, different correlation metrics are applied depending on the pair being tested:

| Variable Pair | Method | Library |
|---------------|--------|---------|
| Categorical ↔ Categorical | **Cramér's V** | `scipy.stats` + manual computation |
| Categorical ↔ Numeric | **Point-biserial correlation** | `scipy.stats.pointbiserialr` |
| Numeric ↔ Numeric | **Pearson** (default) or **Spearman** (if non-normal) | `scipy.stats` / `statsmodels` |

> **Spearman vs Pearson:** Default to Pearson. If a normality check (Shapiro-Wilk via `scipy.stats.shapiro`) flags non-normal distribution, automatically switch to Spearman and note it in the UI.

### 8.4 Threshold Control

- A **slider** (range 0.0 → 1.0, step 0.05) lets the user set the minimum correlation strength to display
- Default threshold: **0.5** (i.e. |r| ≥ 0.5 or V ≥ 0.5)
- Only field pairs that meet or exceed the threshold are shown
- Slider updates displayed pairs reactively — no page reload

```
Correlation threshold:  0.0 ───────●──────── 1.0
                                  0.5
```

### 8.5 Output

For each field pair that passes the threshold:

- **Pair label** — e.g. *"Integer field ↔ Decimal field (Pearson r = 0.74)"*
- **Chart:**
  - Numeric ↔ Numeric → **Scatter plot** with OLS trend line (statsmodels)
  - Categorical ↔ Numeric → **Box plot** grouped by category
  - Categorical ↔ Categorical → **Grouped bar chart** (count per combination)
- **Correlation coefficient** displayed on the chart (value + method used)

### 8.6 Correlation Matrix Overview

Above the individual pair charts, show a **heatmap of all field-pair correlations** (regardless of threshold) so analysts can see the full picture before drilling in. Cells below the threshold are visually muted (low opacity).

```
              Integer   Decimal   Range   Percent
Integer         1.0       0.74     0.12     0.31
Decimal         0.74      1.0      0.08     0.44
Range           0.12      0.08     1.0      0.61
Percent         0.31      0.44     0.61     1.0
```

> Plotly's `px.imshow()` with a diverging colorscale (e.g. RdBu).

### 8.7 Tech Stack (Phase 3)

| Component | Choice |
|-----------|--------|
| Correlation computation | `scipy.stats` + `statsmodels` |
| Data preparation | Polars (encoding categoricals for computation) |
| Normality check | `scipy.stats.shapiro` |
| OLS trend line | `statsmodels.formula.api.ols` |
| Charts | Plotly Express |
| Threshold slider | `mo.ui.slider` |

### 8.8 Data Preparation Notes

Correlation methods require numeric input. Categorical fields must be encoded before computation:

| Field type | Encoding for correlation |
|------------|------------------------|
| `toggle` | Label encode as 0/1 (Off=0, On=1) |
| `select_one` (2 categories) | Label encode as 0/1 |
| `select_one` (3+ categories) | Cramér's V uses frequency tables — no encoding needed |
| `select_multiple` | Cramér's V on option co-occurrence frequency tables |
| `range`, `percent`, `integer`, `decimal`, `auto_calculated` | Use numeric values directly |

All encoding done in Polars before passing to scipy/statsmodels.

### 8.9 Edge Cases

| Case | Behaviour |
|------|-----------|
| Field has < 10 valid responses | Exclude from correlation — too few for reliable estimate; show warning |
| All values identical in a field | Correlation is undefined — exclude that field and note it |
| No pairs meet the threshold | Show: *"No strongly correlated field pairs found at this threshold. Try lowering the slider."* |
| Normality check fails for numeric pair | Auto-switch to Spearman; label chart with *"Spearman ρ"* instead of *"Pearson r"* |
| Cramér's V on sparse table | Flag as unreliable if any expected cell frequency < 5 |

### 8.10 Implementation Order (Phase 3)

1. Build `correlation_engine.py` — detects field type pairs and applies the correct method
2. Build encoding utilities in Polars for categorical → numeric preparation
3. Compute full correlation matrix and verify results against known datasets
4. Build correlation heatmap (`px.imshow`) with muting for sub-threshold cells
5. Build per-pair chart components (scatter + OLS line, box plot, grouped bar)
6. Wire threshold slider — reactive filtering of displayed pairs
7. Add normality check and auto Pearson/Spearman switching
8. Integrate into Insights section placeholder
9. Edge case handling and warnings
10. End-to-end test with real form data (using the schema from Section 5.1)
