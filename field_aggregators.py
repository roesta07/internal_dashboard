"""field_aggregators: per-field-type aggregation for the response dashboard.

Library usage:
    from field_aggregators import load_schema, load_responses, aggregate_field

Marimo interactive demo:
    conda activate corus_api_env
    marimo edit field_aggregators.py
"""

import csv
import json

import marimo
import polars as pl

from null_detector import normalize_nulls_all


DATE_FMT = "%d-%b-%y"
TIME_FMT = "%H:%M"
DATETIME_FMT = "%d/%m/%Y %H:%M"

CATEGORICAL_TYPES = {"select_one", "select_multiple", "toggle"}
NUMERIC_TYPES = {"integer", "decimal", "range", "percent", "auto_calculated"}
TEMPORAL_TYPES = {"date", "time", "datetime"}
TEXT_TYPES = {"text"}
SUMMARY_ONLY_TYPES = {"image", "file", "barcode", "geopoint", "geo_area"}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_schema(path):
    """Read structure_main.csv into a list of field dicts.

    Lifted (and trimmed) from generate_variables.py. Each row:
      key, name, label, type, subtype, required (bool), options (parsed JSON),
      skipLogic (stripped str).
    """
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


def load_responses(csv_path):
    """Read the response CSV as all-Utf8 and normalize empty/sentinel to null."""
    df = pl.read_csv(csv_path, infer_schema_length=0)
    return normalize_nulls_all(df)


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------


def _empty_chart_data():
    return {"exclude_nulls": None, "include_nulls": None, "raw_values": None}


def _build_detail_rows(df, field):
    """Detail table columns: '#', 'name', <field name>. If field IS the name
    column, returns just '#' + 'name'."""
    name_col = field["name"]
    cols = [pl.col("#").cast(pl.Int64), pl.col("name")]
    if name_col != "name":
        cols.append(pl.col(name_col))
    return df.with_row_index(name="#", offset=1).select(cols)


def _result(
    field,
    df,
    *,
    total_count,
    null_count,
    render_mode,
    parse_failed_count=0,
    stats=None,
    chart_data=None,
    group_table=None,
):
    return {
        "field": field,
        "total_count": int(total_count),
        "null_count": int(null_count),
        "parse_failed_count": int(parse_failed_count),
        "n_total": int(df.height),
        "stats": stats,
        "chart_data": chart_data if chart_data is not None else _empty_chart_data(),
        "group_table": group_table,
        "detail_rows": _build_detail_rows(df, field),
        "render_mode": render_mode,
        "has_skip_logic": bool(field.get("skipLogic")),
    }


# ---------------------------------------------------------------------------
# Per-type aggregators
# ---------------------------------------------------------------------------


def _agg_summary_only(df, field):
    col = field["name"]
    n_null = int(df[col].null_count())
    total = df.height - n_null
    return _result(
        field, df,
        total_count=total,
        null_count=n_null,
        render_mode="summary_only",
    )


def _agg_text(df, field):
    col = field["name"]
    n_null = int(df[col].null_count())
    total = df.height - n_null
    return _result(
        field, df,
        total_count=total,
        null_count=n_null,
        render_mode="text",
    )


def _option_label_map(field):
    """Build {value: label} from field['options']. Empty if no options."""
    return {opt["value"]: opt["label"] for opt in field.get("options") or []}


def _categorical_chart_data(group_table, total_with_nulls):
    """Build exclude_nulls / include_nulls DataFrames for a categorical chart.

    group_table: pl.DataFrame with ['category', 'count', 'pct'] (valid only).
    total_with_nulls: total non-null + null respondents.
    """
    exclude = group_table
    if total_with_nulls > group_table["count"].sum():
        null_n = total_with_nulls - group_table["count"].sum()
        null_row = pl.DataFrame(
            {
                "category": ["Null"],
                "count": [int(null_n)],
                "pct": [round(100 * null_n / total_with_nulls, 1)],
            }
        )
        # Recompute pct in include_nulls relative to total_with_nulls
        recomputed = group_table.with_columns(
            (pl.col("count") / total_with_nulls * 100).round(1).alias("pct")
        )
        include = pl.concat([recomputed, null_row], how="vertical_relaxed")
    else:
        include = None
    return {"exclude_nulls": exclude, "include_nulls": include, "raw_values": None}


def _agg_select_one(df, field):
    col = field["name"]
    n_null = int(df[col].null_count())
    valid = df.filter(pl.col(col).is_not_null())
    total = valid.height

    label_map = _option_label_map(field)
    if label_map:
        valid_labeled = valid.with_columns(
            pl.col(col).replace(label_map).alias(col)
        )
    else:
        valid_labeled = valid

    group = (
        valid_labeled.group_by(col)
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
        .rename({col: "category"})
    )
    if total > 0:
        group = group.with_columns(
            (pl.col("count") / total * 100).round(1).alias("pct")
        )
    else:
        group = group.with_columns(pl.lit(0.0).alias("pct"))

    chart_data = _categorical_chart_data(group, df.height)
    return _result(
        field, df,
        total_count=total,
        null_count=n_null,
        render_mode="categorical",
        chart_data=chart_data,
        group_table=group,
    )


def _agg_toggle(df, field):
    col = field["name"]
    n_null = int(df[col].null_count())
    valid = df.filter(pl.col(col).is_not_null())
    total = valid.height

    group = (
        valid.group_by(col)
        .agg(pl.len().alias("count"))
        .rename({col: "category"})
    )
    # Ensure both On and Off present (in that order) even if one is zero
    have = set(group["category"].to_list())
    extras = []
    for cat in ("On", "Off"):
        if cat not in have:
            extras.append({"category": cat, "count": 0})
    if extras:
        group = pl.concat(
            [group, pl.DataFrame(extras, schema={"category": pl.Utf8, "count": pl.UInt32})],
            how="vertical_relaxed",
        )
    # Sort by On first then Off
    order_map = {"On": 0, "Off": 1}
    group = group.with_columns(
        pl.col("category").replace_strict(order_map, default=99).alias("_order")
    ).sort("_order").drop("_order")

    if total > 0:
        group = group.with_columns(
            (pl.col("count") / total * 100).round(1).alias("pct")
        )
    else:
        group = group.with_columns(pl.lit(0.0).alias("pct"))

    chart_data = _categorical_chart_data(group, df.height)
    return _result(
        field, df,
        total_count=total,
        null_count=n_null,
        render_mode="categorical",
        chart_data=chart_data,
        group_table=group,
    )


def _agg_select_multiple(df, field):
    col = field["name"]
    n_null = int(df[col].null_count())

    label_map = _option_label_map(field)

    # Build a list-of-options column: split on ",", strip, drop empties
    listed = df.with_columns(
        pl.col(col)
        .str.split(",")
        .list.eval(pl.element().str.strip_chars())
        .list.eval(pl.element().filter(pl.element() != ""))
        .alias("_opts")
    )

    # Respondent total: rows with at least one option
    respondents = listed.filter(
        pl.col("_opts").is_not_null() & (pl.col("_opts").list.len() > 0)
    ).height

    # Per-option counts
    exploded = listed.filter(pl.col("_opts").is_not_null()).explode("_opts")
    exploded = exploded.filter(pl.col("_opts").is_not_null() & (pl.col("_opts") != ""))

    if label_map:
        exploded = exploded.with_columns(
            pl.col("_opts").replace(label_map).alias("_opts")
        )

    group = (
        exploded.group_by("_opts")
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
        .rename({"_opts": "category"})
    )
    if respondents > 0:
        group = group.with_columns(
            (pl.col("count") / respondents * 100).round(1).alias("pct")
        )
    else:
        group = group.with_columns(pl.lit(0.0).alias("pct"))

    # Build chart data — for select_multiple, "Null" bar = rows with empty/null list
    null_respondents = df.height - respondents
    chart_data = {"exclude_nulls": group, "include_nulls": None, "raw_values": None}
    if null_respondents > 0:
        null_row = pl.DataFrame(
            {
                "category": ["Null"],
                "count": [int(null_respondents)],
                "pct": [round(100 * null_respondents / df.height, 1)],
            }
        )
        recomputed = group.with_columns(
            (pl.col("count") / df.height * 100).round(1).alias("pct")
        )
        chart_data["include_nulls"] = pl.concat([recomputed, null_row], how="vertical_relaxed")

    return _result(
        field, df,
        total_count=respondents,
        null_count=n_null,
        render_mode="categorical",
        chart_data=chart_data,
        group_table=group,
    )


def _agg_numeric(df, field):
    col = field["name"]
    n_null_before = int(df[col].null_count())

    casted = df.with_columns(
        pl.col(col).cast(pl.Float64, strict=False).alias("_v")
    )
    n_null_after = int(casted["_v"].null_count())
    parse_failed = max(0, n_null_after - n_null_before)
    null_count = n_null_before
    total = df.height - n_null_after  # successfully parsed = valid

    valid = casted.filter(pl.col("_v").is_not_null())

    stats = None
    chart_data = _empty_chart_data()

    if valid.height > 0:
        s = valid["_v"]
        stats = {
            "min": float(s.min()),
            "max": float(s.max()),
            "mean": float(s.mean()),
            "median": float(s.median()),
        }

        mn, mx = stats["min"], stats["max"]
        if mx > mn:
            n_bins = 20
            bin_width = (mx - mn) / n_bins
            binned = (
                valid.with_columns(
                    pl.min_horizontal(
                        ((pl.col("_v") - mn) / bin_width).floor().cast(pl.Int64),
                        pl.lit(n_bins - 1),
                    ).alias("_bin")
                )
                .group_by("_bin")
                .agg(pl.len().alias("count"))
                .sort("_bin")
                .with_columns(
                    (mn + pl.col("_bin") * bin_width).round(2).alias("bin_start")
                )
                .with_columns(
                    (pl.col("bin_start") + bin_width).round(2).alias("bin_end")
                )
                .select(["bin_start", "bin_end", "count"])
            )
        else:
            # All values identical — single bar
            binned = pl.DataFrame(
                {"bin_start": [mn], "bin_end": [mn], "count": [valid.height]}
            )

        chart_data = {
            "exclude_nulls": binned,
            "include_nulls": None,
            "raw_values": valid["_v"],
        }

    return _result(
        field, df,
        total_count=total,
        null_count=null_count,
        render_mode="numeric",
        parse_failed_count=parse_failed,
        stats=stats,
        chart_data=chart_data,
    )


def _temporal_common(df, field, parse_expr, render_mode, bucket_fn):
    """Shared logic for date / time / datetime."""
    col = field["name"]
    n_null_before = int(df[col].null_count())

    parsed = df.with_columns(parse_expr.alias("_t"))
    n_null_after = int(parsed["_t"].null_count())
    parse_failed = max(0, n_null_after - n_null_before)
    null_count = n_null_before
    total = df.height - n_null_after

    valid = parsed.filter(pl.col("_t").is_not_null())

    stats = None
    chart_data = _empty_chart_data()

    if valid.height > 0:
        stats = {
            "earliest": valid["_t"].min(),
            "latest": valid["_t"].max(),
        }
        bucketed = bucket_fn(valid)
        chart_data = {
            "exclude_nulls": bucketed,
            "include_nulls": None,
            "raw_values": valid["_t"],
        }

    return _result(
        field, df,
        total_count=total,
        null_count=null_count,
        render_mode=render_mode,
        parse_failed_count=parse_failed,
        stats=stats,
        chart_data=chart_data,
    )


def _agg_date(df, field):
    return _temporal_common(
        df,
        field,
        pl.col(field["name"]).str.to_date(DATE_FMT, strict=False),
        render_mode="temporal",
        bucket_fn=lambda v: (
            v.group_by("_t")
            .agg(pl.len().alias("count"))
            .sort("_t")
            .rename({"_t": "date"})
        ),
    )


def _agg_time(df, field):
    return _temporal_common(
        df,
        field,
        pl.col(field["name"]).str.to_time(TIME_FMT, strict=False),
        render_mode="temporal",
        bucket_fn=lambda v: (
            v.with_columns(pl.col("_t").dt.hour().alias("hour"))
            .group_by("hour")
            .agg(pl.len().alias("count"))
            .sort("hour")
        ),
    )


def _agg_datetime(df, field):
    return _temporal_common(
        df,
        field,
        pl.col(field["name"]).str.to_datetime(DATETIME_FMT, strict=False),
        render_mode="temporal",
        bucket_fn=lambda v: (
            v.with_columns(pl.col("_t").dt.date().alias("date"))
            .group_by("date")
            .agg(pl.len().alias("count"))
            .sort("date")
        ),
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


_DISPATCH = {
    "select_one": _agg_select_one,
    "select_multiple": _agg_select_multiple,
    "toggle": _agg_toggle,
    "text": _agg_text,
    "integer": _agg_numeric,
    "decimal": _agg_numeric,
    "range": _agg_numeric,
    "percent": _agg_numeric,
    "auto_calculated": _agg_numeric,
    "date": _agg_date,
    "time": _agg_time,
    "datetime": _agg_datetime,
    "image": _agg_summary_only,
    "file": _agg_summary_only,
    "barcode": _agg_summary_only,
    "geopoint": _agg_summary_only,
    "geo_area": _agg_summary_only,
}


def aggregate_field(df, field):
    """Dispatch on field['type']. Unknown types fall back to summary_only."""
    fn = _DISPATCH.get(field["type"], _agg_summary_only)
    return fn(df, field)


# ---------------------------------------------------------------------------
# Marimo demo
# ---------------------------------------------------------------------------


__generated_with = "0.23.6"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    from pathlib import Path

    return Path, mo


@app.cell
def _(mo):
    mo.md(
        """
        # field_aggregators — interactive demo

        Walks through `aggregate_field` results for every field in
        `structure_main.csv`, computed against `sample_data.csv`.
        """
    )
    return


@app.cell
def _(Path):
    HERE = Path(__file__).parent
    SCHEMA_PATH = HERE / "structure" / "structure_main.csv"
    DATA_PATH = HERE / "sample_data.csv"
    return DATA_PATH, SCHEMA_PATH


@app.cell
def _(DATA_PATH, SCHEMA_PATH):
    schema = load_schema(SCHEMA_PATH)
    df = load_responses(DATA_PATH)
    aggregates = {f["name"]: aggregate_field(df, f) for f in schema}
    return aggregates, df, schema


@app.cell
def _(aggregates, mo, schema):
    summary_rows = []
    for f in schema:
        agg = aggregates[f["name"]]
        summary_rows.append(
            {
                "field": f["name"],
                "type": f["type"],
                "render_mode": agg["render_mode"],
                "total": agg["total_count"],
                "null": agg["null_count"],
                "parse_failed": agg["parse_failed_count"],
                "skip_logic": agg["has_skip_logic"],
            }
        )
    import polars as pl_demo
    mo.vstack(
        [
            mo.md("## Per-field summary"),
            mo.ui.table(
                pl_demo.DataFrame(summary_rows).to_pandas(),
                page_size=25,
                selection=None,
            ),
        ]
    )
    return


@app.cell
def _(aggregates, mo):
    sex = aggregates["sex"]
    mo.vstack(
        [
            mo.md("## select_one example — `sex`"),
            mo.md("Value→label mapping: `m`→male, `f`→female."),
            mo.ui.table(
                sex["group_table"].to_pandas(), page_size=10, selection=None
            ),
            mo.md(
                "include_nulls variant (if any nulls):" if sex["chart_data"]["include_nulls"] is not None
                else "_(no nulls in this column)_"
            ),
        ]
        + (
            [
                mo.ui.table(
                    sex["chart_data"]["include_nulls"].to_pandas(),
                    page_size=10,
                    selection=None,
                )
            ]
            if sex["chart_data"]["include_nulls"] is not None
            else []
        )
    )
    return


@app.cell
def _(aggregates, mo):
    fav = aggregates["fav_subject"]
    mo.vstack(
        [
            mo.md("## select_multiple example — `fav_subject`"),
            mo.md(
                f"Respondents: **{fav['total_count']}**. "
                f"Option counts (one row per option):"
            ),
            mo.ui.table(
                fav["group_table"].to_pandas(), page_size=10, selection=None
            ),
        ]
    )
    return


@app.cell
def _(aggregates, mo):
    it = aggregates["int_test"]
    mo.vstack(
        [
            mo.md("## numeric example — `int_test`"),
            mo.md(f"Stats: {it['stats']}"),
            mo.md(f"Binned chart data (first 10 rows):"),
            mo.ui.table(
                it["chart_data"]["exclude_nulls"].head(10).to_pandas(),
                page_size=10,
                selection=None,
            ),
        ]
    )
    return


@app.cell
def _(aggregates, mo):
    dt = aggregates["date_test"]
    mo.vstack(
        [
            mo.md("## date example — `date_test`"),
            mo.md(f"Stats: {dt['stats']}"),
            mo.md(f"parse_failed_count: **{dt['parse_failed_count']}**"),
            mo.md(f"Daily count series (first 10 rows):"),
            mo.ui.table(
                dt["chart_data"]["exclude_nulls"].head(10).to_pandas(),
                page_size=10,
                selection=None,
            ),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
