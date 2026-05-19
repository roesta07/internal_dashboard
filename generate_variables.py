"""Marimo dashboard: generate fake subject records from structure/structure_main.csv.

Run with:
    conda activate corus_api_env
    marimo edit generate_variables.py    # interactive
    marimo run generate_variables.py     # read-only dashboard
"""

import marimo

__generated_with = "0.23.6"
app = marimo.App(width="medium")


@app.cell
def _():
    import csv
    import json
    import warnings
    from datetime import date, datetime, timedelta
    from pathlib import Path

    import marimo as mo
    import numpy as np
    import pandas as pd

    return Path, csv, date, datetime, json, mo, np, pd, timedelta, warnings


@app.cell
def _(mo):
    mo.md("""
    # Sample subject data generator

    Reads `structure/structure_main.csv` and generates fake subject records as
    a pandas DataFrame. Adjust the controls below to change the sample size or
    re-roll the random seed.
    """)
    return


@app.cell
def _(Path, csv, json):
    SCHEMA_PATH = Path(__file__).parent / "structure" / "structure_main.csv"

    def load_schema(path):
        fields = []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get("key"):
                    continue
                row["options"] = (
                    json.loads(row["options"]) if row.get("options") else []
                )
                row["required"] = (
                    str(row.get("required", "")).strip().lower() == "true"
                )
                row["subtype"] = (row.get("subtype") or "").strip()
                row["skipLogic"] = (row.get("skipLogic") or "").strip()
                fields.append(row)
        return fields

    schema = load_schema(SCHEMA_PATH)
    return (schema,)


@app.cell
def _(mo, pd, schema):
    schema_df = pd.DataFrame(
        [
            {
                "key": f["key"],
                "name": f["name"],
                "label": f["label"],
                "type": f["type"],
                "subtype": f["subtype"],
                "required": f["required"],
                "skipLogic": f["skipLogic"],
            }
            for f in schema
        ]
    )
    mo.vstack(
        [
            mo.md(f"## Schema · **{len(schema_df)} fields**"),
            mo.ui.table(schema_df, page_size=20, selection=None),
        ]
    )
    return


@app.cell
def _(mo):
    n_subjects = mo.ui.slider(
        start=1, stop=500, value=100, step=1, label="Number of subjects",
        show_value=True,
    )
    seed = mo.ui.number(value=42, start=0, stop=999999, label="Random seed")
    regenerate = mo.ui.run_button(label="Regenerate")
    mo.vstack(
        [
            mo.md("## Controls"),
            mo.hstack([n_subjects, seed, regenerate], justify="start"),
        ]
    )
    return n_subjects, regenerate, seed


@app.cell
def _(date, datetime, np, timedelta, warnings):
    NEPAL_LAT_RANGE = (27.0, 28.5)
    NEPAL_LNG_RANGE = (85.0, 85.5)
    DATE_START = date(2024, 1, 1)
    DATE_END = date(2026, 12, 31)
    DATE_SPAN_DAYS = (DATE_END - DATE_START).days
    MISSING_RATE = 0.2  # probability a non-required field (other than name / toggles) is blank
    PLACEHOLDER_TEXTS = [
        "free text",
        "sample input",
        "user response",
        "note here",
        "lorem ipsum",
    ]

    def _pick(rng, items):
        return items[int(rng.integers(0, len(items)))]

    def _sample_without_replacement(rng, items, k):
        idx = rng.choice(len(items), size=k, replace=False)
        return [items[int(i)] for i in idx]

    def _random_date(rng):
        days = int(rng.integers(0, DATE_SPAN_DAYS + 1))
        return DATE_START + timedelta(days=days)

    def _random_time_tuple(rng):
        return int(rng.integers(0, 24)), int(rng.integers(0, 60))

    def _random_geopoint(rng):
        lat = float(rng.uniform(*NEPAL_LAT_RANGE))
        lng = float(rng.uniform(*NEPAL_LNG_RANGE))
        return f"{lat},{lng}"

    def _random_geo_area(rng, n_points=3):
        return ",".join(_random_geopoint(rng) for _ in range(n_points))

    def _generate_value(field, i, rng, row_values):
        key = field["key"]
        name = field["name"]
        ftype = field["type"]

        # Never generate a value for autocalc_test
        if key == "autocalc_test" or name == "autocalc_test":
            return ""

        skip = field.get("skipLogic", "")
        if skip:
            try:
                if not eval(skip, {"__builtins__": {}}, dict(row_values)):
                    return ""
            except Exception as exc:
                warnings.warn(
                    f"skipLogic '{skip}' failed for field "
                    f"{field['key']!r}: {exc}"
                )

        # Randomly drop non-required fields (except `name` and toggles)
        is_name = key == "name" or name == "name"
        if not field.get("required") and not is_name and ftype != "toggle":
            if float(rng.random()) < MISSING_RATE:
                return ""

        subtype = field["subtype"]
        options = field.get("options") or []

        if ftype == "text":
            if subtype == "email":
                return f"subj_{i:02d}@gmail.com"
            if is_name:
                return f"subj_{i:02d}"
            return _pick(rng, PLACEHOLDER_TEXTS)

        if ftype == "select_one":
            values = [opt["value"] for opt in options]
            return _pick(rng, values) if values else ""

        if ftype == "select_multiple":
            values = [opt["value"] for opt in options]
            if not values:
                return ""
            k = int(rng.integers(1, len(values) + 1))
            chosen = _sample_without_replacement(rng, values, k)
            return ", ".join(chosen)

        if ftype == "toggle":
            return _pick(rng, ["On", "Off"])

        if ftype == "integer":
            return int(rng.integers(1, 101))

        if ftype == "decimal":
            return round(float(rng.uniform(0, 200)), 2)

        if ftype == "range":
            return int(rng.integers(0, 201))

        if ftype == "date":
            return _random_date(rng).strftime("%d-%b-%y")

        if ftype == "time":
            h, m = _random_time_tuple(rng)
            return f"{h:02d}:{m:02d}"

        if ftype == "datetime":
            d = _random_date(rng)
            h, m = _random_time_tuple(rng)
            return datetime(d.year, d.month, d.day, h, m).strftime(
                "%d/%m/%Y %H:%M"
            )

        if ftype in ("image", "file", "barcode"):
            return ""

        if ftype == "auto_calculated":
            return int(rng.integers(1, 201))

        if ftype == "geopoint":
            return _random_geopoint(rng)

        if ftype == "geo_area":
            return _random_geo_area(rng)

        if ftype == "percent":
            return int(rng.integers(0, 101))

        warnings.warn(f"Unknown type {ftype!r} for field {key!r}; emitting blank")
        return ""

    def generate(schema, n, seed_value):
        rng = np.random.default_rng(int(seed_value))
        rows = []
        for i in range(int(n)):
            row_values = {}
            for field in schema:
                row_values[field["key"]] = _generate_value(
                    field, i, rng, row_values
                )
            rows.append({f["name"]: row_values[f["key"]] for f in schema})
        return rows


    return (generate,)


@app.cell
def _(generate, n_subjects, pd, regenerate, schema, seed):
    effective_seed = int(seed.value) + int(regenerate.value or 0)
    df = pd.DataFrame(generate(schema, n_subjects.value, effective_seed))
    return (df,)


@app.cell
def _(df, mo):
    mo.vstack(
        [
            mo.md(
                f"## Result · **{len(df)} rows × {len(df.columns)} columns**"
            ),
            mo.ui.table(df, page_size=20, selection=None),
        ]
    )
    return


@app.cell
def _(df, mo):
    mo.download(
        data=df.to_csv(index=False).encode("utf-8"),
        filename="sample_data.csv",
        label="Download CSV",
        mimetype="text/csv",
    )
    return


if __name__ == "__main__":
    app.run()
