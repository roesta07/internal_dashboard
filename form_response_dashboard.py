# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "marimo",
#     "polars",
#     "plotly",
#     "anywidget",
#     "traitlets",
#     "numpy",
# ]
# ///
"""form_response_dashboard: per-field response visualisation.

Run interactively:
    conda activate corus_api_env
    marimo edit form_response_dashboard.py
"""

import marimo

__generated_with = "0.23.6"
app = marimo.App(width="full")


@app.cell
def _():
    import csv
    import io
    import json
    import urllib.request

    import anywidget
    import marimo as mo
    import plotly.express as px
    import polars as pl
    import traitlets

    return anywidget, csv, io, json, mo, pl, px, traitlets, urllib


@app.cell
def _():
    SCHEMA_URL = "https://raw.githubusercontent.com/roesta07/internal_dashboard/refs/heads/main/structure/structure_main.csv"
    DATA_URL = "https://raw.githubusercontent.com/roesta07/internal_dashboard/refs/heads/main/sample_data.csv"
    return DATA_URL, SCHEMA_URL


@app.cell
def _(pl):
    # Inlined from null_detector.py
    NULL_SENTINELS = ["", "N/A", "n/a"]


    def normalize_nulls(df, col):
        """Rewrite a string column: trimmed values matching NULL_SENTINELS become null."""
        if df.schema[col] != pl.Utf8:
            return df
        return df.with_columns(
            pl.when(pl.col(col).str.strip_chars().is_in(NULL_SENTINELS))
            .then(None)
            .otherwise(pl.col(col))
            .alias(col)
        )


    def normalize_nulls_all(df):
        """Apply normalize_nulls to every Utf8 column in the frame."""
        for c, dt in df.schema.items():
            if dt == pl.Utf8:
                df = normalize_nulls(df, c)
        return df

    return (normalize_nulls_all,)


@app.cell
def _(csv, io, json, normalize_nulls_all, pl, urllib):
    # Inlined from field_aggregators.py
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


    def load_schema(url):
        """Fetch and parse the schema CSV from a URL."""
        with urllib.request.urlopen(url) as response:
            text = response.read().decode("utf-8")
        fields = []
        reader = csv.DictReader(io.StringIO(text))
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


    def load_responses(url):
        """Fetch the response CSV from a URL, parse with polars, normalize nulls."""
        with urllib.request.urlopen(url) as response:
            data = response.read()
        df = pl.read_csv(io.BytesIO(data), infer_schema_length=0)
        return normalize_nulls_all(df)


    # ---------------------------------------------------------------------------
    # Result builder
    # ---------------------------------------------------------------------------


    def _empty_chart_data():
        return {"exclude_nulls": None, "include_nulls": None, "raw_values": None}


    def _build_detail_rows(df, field):
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
        return {opt["value"]: opt["label"] for opt in field.get("options") or []}


    def _categorical_chart_data(group_table, total_with_nulls):
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

        listed = df.with_columns(
            pl.col(col)
            .str.split(",")
            .list.eval(pl.element().str.strip_chars())
            .list.eval(pl.element().filter(pl.element() != ""))
            .alias("_opts")
        )

        respondents = listed.filter(
            pl.col("_opts").is_not_null() & (pl.col("_opts").list.len() > 0)
        ).height

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
        total = df.height - n_null_after

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
        fn = _DISPATCH.get(field["type"], _agg_summary_only)
        return fn(df, field)

    return TEMPORAL_TYPES, aggregate_field, load_responses, load_schema


@app.cell
def _(SCHEMA_URL, load_schema):
    schema = [f for f in load_schema(SCHEMA_URL) if f["type"] != "matrix"]
    return (schema,)


@app.cell
def _(df, mo):
    mo.vstack(
        [
            mo.md("# Form Name: Persona"),
            mo.md(
                f"**Data Table:** persona87 &nbsp;·&nbsp; "
                f"**Project:** Rojan-Test &nbsp;·&nbsp; "
                f"**Total rows:** {df.height}"
            ),

            mo.md("---"),
        ]
    )
    return


@app.cell
def _(DATA_URL, load_responses):

    df = load_responses(DATA_URL)
    df.head()
    return (df,)


@app.cell
def _(mo):
    # Per-field UI elements as top-level named vars
    # (marimo only registers UI bindings for top-level vars, not dict entries)

    # Null-exclude checkboxes (categorical fields)
    null_sex = mo.ui.checkbox(value=True, label="Exclude nulls")
    null_is_teacher = mo.ui.checkbox(value=True, label="Exclude nulls")
    null_is_student = mo.ui.checkbox(value=True, label="Exclude nulls")
    null_fav_subject = mo.ui.checkbox(value=True, label="Exclude nulls")

    # Numeric chart-type dropdowns
    chart_int_test = mo.ui.dropdown(
        options=["Bar (binned)", "Histogram", "Box", "Violin"],
        value="Histogram",
        label="Chart type",
    )
    chart_decimal_test = mo.ui.dropdown(
        options=["Bar (binned)", "Histogram", "Box", "Violin"],
        value="Histogram",
        label="Chart type",
    )
    chart_range_test = mo.ui.dropdown(
        options=["Bar (binned)", "Histogram", "Box", "Violin"],
        value="Histogram",
        label="Chart type",
    )
    chart_autocalc_test = mo.ui.dropdown(
        options=["Bar (binned)", "Histogram", "Box", "Violin"],
        value="Histogram",
        label="Chart type",
    )
    chart_percent_test = mo.ui.dropdown(
        options=["Bar (binned)", "Histogram", "Box", "Violin"],
        value="Histogram",
        label="Chart type",
    )


    # Categorical chart-type dropdowns (select_one / toggle)
    cat_chart_sex = mo.ui.dropdown(
        options=["Pie", "Bar (horizontal)", "Bar (vertical)", "Histogram"],
        value="Pie",
        label="Chart type",
    )
    cat_chart_is_teacher = mo.ui.dropdown(
        options=["Pie", "Bar (horizontal)", "Bar (vertical)", "Histogram"],
        value="Pie",
        label="Chart type",
    )
    cat_chart_is_student = mo.ui.dropdown(
        options=["Pie", "Bar (horizontal)", "Bar (vertical)", "Histogram"],
        value="Pie",
        label="Chart type",
    )

    # Detail-rows toggles (all fields)
    detail_name = mo.ui.switch(value=False, label="Show detail responses")
    detail_email = mo.ui.switch(value=False, label="Show detail responses")
    detail_sex = mo.ui.switch(value=False, label="Show detail responses")
    detail_is_teacher = mo.ui.switch(value=False, label="Show detail responses")
    detail_is_student = mo.ui.switch(value=False, label="Show detail responses")
    detail_gender2 = mo.ui.switch(value=False, label="Show detail responses")
    detail_fav_subject = mo.ui.switch(value=False, label="Show detail responses")
    detail_int_test = mo.ui.switch(value=False, label="Show detail responses")
    detail_decimal_test = mo.ui.switch(value=False, label="Show detail responses")
    detail_range_test = mo.ui.switch(value=False, label="Show detail responses")
    detail_date_test = mo.ui.switch(value=False, label="Show detail responses")
    detail_time_test = mo.ui.switch(value=False, label="Show detail responses")
    detail_date_time = mo.ui.switch(value=False, label="Show detail responses")
    detail_image_test = mo.ui.switch(value=False, label="Show detail responses")
    detail_file_test = mo.ui.switch(value=False, label="Show detail responses")
    detail_autocalc_test = mo.ui.switch(value=False, label="Show detail responses")
    detail_geolocation_test = mo.ui.switch(value=False, label="Show detail responses")
    detail_barcode_test = mo.ui.switch(value=False, label="Show detail responses")
    detail_geo_area_test = mo.ui.switch(value=False, label="Show detail responses")
    detail_percent_test = mo.ui.switch(value=False, label="Show detail responses")
    return (
        cat_chart_is_student,
        cat_chart_is_teacher,
        cat_chart_sex,
        chart_autocalc_test,
        chart_decimal_test,
        chart_int_test,
        chart_percent_test,
        chart_range_test,
        detail_autocalc_test,
        detail_barcode_test,
        detail_date_test,
        detail_date_time,
        detail_decimal_test,
        detail_email,
        detail_fav_subject,
        detail_file_test,
        detail_gender2,
        detail_geo_area_test,
        detail_geolocation_test,
        detail_image_test,
        detail_int_test,
        detail_is_student,
        detail_is_teacher,
        detail_name,
        detail_percent_test,
        detail_range_test,
        detail_sex,
        detail_time_test,
        null_fav_subject,
        null_is_student,
        null_is_teacher,
        null_sex,
    )


@app.cell
def _(aggregate_field, df, schema):
    aggregates = {f["name"]: aggregate_field(df, f) for f in schema}
    return (aggregates,)


@app.cell
def _(anywidget, traitlets):
    class EmailTableWidget(anywidget.AnyWidget):
        _esm = """
        function render({ model, el }) {
          const rows = model.get("rows");
          let html = '<table style="border-collapse:collapse; width:100%; font-size:13px;">';
          html += '<thead><tr>';
          html += '<th style="text-align:left; padding:6px; border-bottom:1px solid #ccc;">#</th>';
          html += '<th style="text-align:left; padding:6px; border-bottom:1px solid #ccc;">name</th>';
          html += '<th style="text-align:left; padding:6px; border-bottom:1px solid #ccc;">email</th>';
          html += '</tr></thead><tbody>';
          for (const r of rows) {
            const email = r.email || '';
            const link = email
              ? `<a href="mailto:${email}" style="color:#2563eb;">${email}</a>`
              : '<span style="color:#999;">(null)</span>';
            html += '<tr>';
            html += `<td style="padding:6px; border-bottom:1px solid #eee;">${r["#"]}</td>`;
            html += `<td style="padding:6px; border-bottom:1px solid #eee;">${r.name}</td>`;
            html += `<td style="padding:6px; border-bottom:1px solid #eee;">${link}</td>`;
            html += '</tr>';
          }
          html += '</tbody></table>';
          el.innerHTML = html;
        }
        export default { render };
        """
        rows = traitlets.List([]).tag(sync=True)

    return (EmailTableWidget,)


@app.cell
def _(EmailTableWidget, TEMPORAL_TYPES, mo, pl, px):
    NULL_COLOR_MAP = {"Null": "#cccccc"}

    # CORUS brand palette (from company logo)
    CORUS_GREEN = "#7CB342"
    CORUS_ORANGE = "#F39322"
    CORUS_BLUE = "#29B6F6"
    CORUS_NAVY = "#1B3550"
    CORUS_PALETTE = [CORUS_GREEN, CORUS_BLUE, CORUS_ORANGE, CORUS_NAVY]

    def _kde_curve(values, n_points=200):
        """Gaussian KDE using Silverman\'s rule. Returns (xs, ys) or (None, None)."""
        import numpy as np
        arr = np.asarray(values, dtype=float)
        arr = arr[np.isfinite(arr)]
        n = arr.size
        if n < 2:
            return None, None
        std = float(np.std(arr, ddof=1))
        if std == 0:
            return None, None
        bw = 1.06 * std * n ** (-1 / 5)
        pad = (arr.max() - arr.min()) * 0.05
        xs = np.linspace(arr.min() - pad, arr.max() + pad, n_points)
        z = (xs[:, None] - arr[None, :]) / bw
        ys = (np.exp(-0.5 * z * z) / (np.sqrt(2 * np.pi) * bw)).mean(axis=1)
        return xs, ys

    def _summary_strip(agg):
        return mo.md(
            f"**Counts(N):** {agg['total_count']} "
            f"&nbsp;·&nbsp; **Missing / Null:** {agg['null_count']}"
            + (
                f" &nbsp;·&nbsp; **Parse failed:** {agg['parse_failed_count']}"
                if agg["parse_failed_count"]
                else ""
            )
        )

    def _stats_strip(agg, ftype):
        s = agg.get("stats")
        if not s:
            return None
        if ftype in TEMPORAL_TYPES:
            return mo.md(
                f"**Earliest:** {s['earliest']} &nbsp;·&nbsp; "
                f"**Latest:** {s['latest']}"
            )
        suffix = "%" if ftype == "percent" else ""
        return mo.md(
            f"**Min:** {s['min']:.2f}{suffix} &nbsp;·&nbsp; "
            f"**Max:** {s['max']:.2f}{suffix} &nbsp;·&nbsp; "
            f"**Mean:** {s['mean']:.2f}{suffix} &nbsp;·&nbsp; "
            f"**Median:** {s['median']:.2f}{suffix}"
        )

    def _callouts(agg):
        msgs = []
        if agg["has_skip_logic"]:
            msgs.append(
                mo.callout(
                    "This field has skip logic — sparse responses are expected.",
                    kind="info",
                )
            )
        if agg["parse_failed_count"]:
            msgs.append(
                mo.callout(
                    f"{agg['parse_failed_count']} values failed to parse and "
                    f"were treated as null.",
                    kind="warn",
                )
            )
        if agg["render_mode"] == "temporal" and agg["null_count"]:
            msgs.append(
                mo.callout(
                    f"{agg['null_count']} responses have no value recorded and "
                    f"are excluded from this chart.",
                    kind="neutral",
                )
            )
        return msgs

    def _categorical_chart(field, agg, exclude_nulls, chart_type=None):
        data = agg["chart_data"]["exclude_nulls" if exclude_nulls else "include_nulls"]
        if data is None:
            data = agg["chart_data"]["exclude_nulls"]
        if data is None or data.height == 0:
            return mo.md("_No data to chart._")
        ftype = field["type"]
        real_cats = (
            data.filter(pl.col("category") != "Null")
            .get_column("category")
            .to_list()
        )
        n_real = len(real_cats)
        # Pin green+blue when there are exactly 2 real categories
        if n_real == 2:
            color_map = {real_cats[0]: CORUS_GREEN, real_cats[1]: CORUS_BLUE, **NULL_COLOR_MAP}
        else:
            color_map = NULL_COLOR_MAP
        # Determine effective chart type: explicit choice for select_one/toggle,
        # otherwise pie (2-4 real cats) or horizontal bar.
        if chart_type is None:
            if ftype in ("select_one", "toggle") and 2 <= n_real <= 4:
                chart_type = "Pie"
            else:
                chart_type = "Bar (horizontal)"
        pdf = data.to_pandas()
        if chart_type == "Pie":
            fig = px.pie(
                pdf,
                names="category",
                values="count",
                color="category",
                color_discrete_map=color_map,
                color_discrete_sequence=CORUS_PALETTE,
                hole=0.5,
            )
            fig.update_traces(
                textposition="outside",
                textinfo="label+percent",
                textfont=dict(size=13, color=CORUS_NAVY),
                marker=dict(line=dict(color="white", width=2)),
                sort=False,
                rotation=90,
            )
            fig.update_layout(showlegend=False)
        elif chart_type == "Bar (vertical)":
            fig = px.bar(
                pdf,
                x="category",
                y="count",
                color="category",
                color_discrete_map=color_map,
                color_discrete_sequence=CORUS_PALETTE,
            )
            fig.update_layout(showlegend=False)
        elif chart_type == "Histogram":
            fig = px.histogram(
                pdf,
                x="category",
                y="count",
                color="category",
                color_discrete_map=color_map,
                color_discrete_sequence=CORUS_PALETTE,
            )
            fig.update_layout(showlegend=False, bargap=0.05)
        else:  # "Bar (horizontal)" or fallback
            fig = px.bar(
                pdf,
                x="count",
                y="category",
                orientation="h",
                color="category",
                color_discrete_map=color_map,
                color_discrete_sequence=CORUS_PALETTE,
            )
            fig.update_layout(showlegend=False)
        fig.update_layout(
            height=300, margin=dict(l=10, r=10, t=20, b=10)
        )
        return fig

    def _numeric_chart(field, agg, chart_type):
        ftype = field["type"]
        suffix = "%" if ftype == "percent" else ""
        if chart_type == "Bar (binned)":
            binned = agg["chart_data"]["exclude_nulls"]
            if binned is None or binned.height == 0:
                return mo.md("_No data to chart._")
            disp = binned.with_columns(
                (
                    pl.col("bin_start").round(2).cast(pl.Utf8)
                    + pl.lit(f"–")
                    + pl.col("bin_end").round(2).cast(pl.Utf8)
                ).alias("bin_label")
            )
            fig = px.bar(
                disp.to_pandas(),
                x="bin_label",
                y="count",
                color_discrete_sequence=[CORUS_BLUE],
            )
            fig.update_xaxes(title=f"Range ({suffix})" if suffix else "Range")
        else:
            raw = agg["chart_data"]["raw_values"]
            if raw is None or len(raw) == 0:
                return mo.md("_No data to chart._")
            ser = raw.to_pandas()
            if chart_type == "Histogram":
                fig = px.histogram(
                    ser,
                    nbins=20,
                    histnorm="probability density",
                    color_discrete_sequence=[CORUS_BLUE],
                )
                xs, ys = _kde_curve(ser.dropna().to_numpy())
                if xs is not None:
                    import plotly.graph_objects as go
                    fig.add_trace(
                        go.Scatter(
                            x=xs,
                            y=ys,
                            mode="lines",
                            line=dict(color="#9e9e9e", width=2),
                            name="KDE",
                            hovertemplate="density: %{y:.4f}<extra></extra>",
                        )
                    )
            elif chart_type == "Box":
                fig = px.box(y=ser, color_discrete_sequence=[CORUS_GREEN])
            elif chart_type == "Violin":
                fig = px.violin(
                    y=ser,
                    box=True,
                    points="outliers",
                    color_discrete_sequence=[CORUS_ORANGE],
                )
            else:
                return mo.md(f"_Unknown chart type: {chart_type}._")
            fig.update_yaxes(title=f"Value ({suffix})" if suffix else "Value")
        fig.update_layout(
            height=300, showlegend=False, margin=dict(l=10, r=10, t=20, b=10)
        )
        return fig

    def _temporal_chart(field, agg):
        data = agg["chart_data"]["exclude_nulls"]
        if data is None or data.height == 0:
            return mo.md("_No data to chart._")
        ftype = field["type"]
        x_col = "hour" if ftype == "time" else "date"
        fig = px.bar(
            data.to_pandas(),
            x=x_col,
            y="count",
            color_discrete_sequence=[CORUS_BLUE],
        )
        fig.update_layout(
            height=300, showlegend=False, margin=dict(l=10, r=10, t=20, b=10)
        )
        return fig

    def _detail_table(field, agg):
        if field["subtype"] == "email":
            rows = agg["detail_rows"].head(100).to_dicts()
            return EmailTableWidget(rows=rows)
        return mo.ui.table(
            agg["detail_rows"].to_pandas(), page_size=20, selection=None
        )

    def render_field_card(field, agg, null_toggle, chart_type_dd, detail_toggle, cat_chart_dd=None):
        ftype = field["type"]
        name = field["name"]
        label = field.get("label") or name
        type_badge = f"`[{ftype}]`"

        parts = [
            mo.md(
                f"## {label}\n\n"
                f"**Field name:** `{name}` &nbsp;·&nbsp; **Data type:** {type_badge}"
            ),
            _summary_strip(agg),
        ]

        stats = _stats_strip(agg, ftype)
        if stats is not None:
            parts.append(stats)

        parts.extend(_callouts(agg))

        if agg["render_mode"] == "categorical":
            if cat_chart_dd is not None:
                parts.append(cat_chart_dd)
            if null_toggle is not None:
                parts.append(null_toggle)
            chart = _categorical_chart(
                field,
                agg,
                exclude_nulls=null_toggle.value if null_toggle is not None else True,
                chart_type=cat_chart_dd.value if cat_chart_dd is not None else None,
            )
            parts.append(chart)
            if agg["group_table"] is not None:
                parts.append(mo.md("**Group table:**"))
                parts.append(
                    mo.ui.table(
                        agg["group_table"].to_pandas(),
                        page_size=10,
                        selection=None,
                    )
                )

        elif agg["render_mode"] == "numeric":
            if chart_type_dd is not None:
                parts.append(chart_type_dd)
                parts.append(_numeric_chart(field, agg, chart_type_dd.value))
            else:
                parts.append(_numeric_chart(field, agg, "Bar (binned)"))

        elif agg["render_mode"] == "temporal":
            parts.append(_temporal_chart(field, agg))

        # text and summary_only have no chart

        if detail_toggle is not None:
            parts.append(detail_toggle)
            if detail_toggle.value:
                parts.append(_detail_table(field, agg))

        inner_html = mo.as_html(mo.vstack(parts, gap=0.5)).text
        return mo.Html(
            f'<div style="border:1px solid #e0e0e0; border-left:4px solid #9e9e9e; '
            f'border-radius:8px; padding:16px 18px; margin:10px 0; background:transparent;">'
            f'{inner_html}</div>'
        )


    return (render_field_card,)


@app.cell(hide_code=True)
def _(aggregates, detail_name, render_field_card, schema):
    # Field: name (text)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "name"),
            aggregates["name"],
            None,
            None,
            detail_name,
    )
    return


@app.cell(hide_code=True)
def _(aggregates, detail_email, render_field_card, schema):
    # Field: email (text)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "email"),
            aggregates["email"],
            None,
            None,
            detail_email,
    )
    return


@app.cell(hide_code=True)
def _(
    aggregates,
    cat_chart_sex,
    detail_sex,
    null_sex,
    render_field_card,
    schema,
):
    # Field: sex (select_one)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "sex"),
            aggregates["sex"],
            null_sex,
            None,
            detail_sex,
            cat_chart_sex,
    )
    return


@app.cell(hide_code=True)
def _(
    aggregates,
    cat_chart_is_teacher,
    detail_is_teacher,
    null_is_teacher,
    render_field_card,
    schema,
):
    # Field: is_teacher (toggle)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "is_teacher"),
            aggregates["is_teacher"],
            null_is_teacher,
            None,
            detail_is_teacher,
            cat_chart_is_teacher,
    )
    return


@app.cell(hide_code=True)
def _(
    aggregates,
    cat_chart_is_student,
    detail_is_student,
    null_is_student,
    render_field_card,
    schema,
):
    # Field: is_student (toggle)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "is_student"),
            aggregates["is_student"],
            null_is_student,
            None,
            detail_is_student,
            cat_chart_is_student,
    )
    return


@app.cell(hide_code=True)
def _(aggregates, detail_gender2, render_field_card, schema):
    # Field: gender2 (text)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "gender2"),
            aggregates["gender2"],
            None,
            None,
            detail_gender2,
    )
    return


@app.cell(hide_code=True)
def _(
    aggregates,
    detail_fav_subject,
    null_fav_subject,
    render_field_card,
    schema,
):
    # Field: fav_subject (select_multiple)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "fav_subject"),
            aggregates["fav_subject"],
            null_fav_subject,
            None,
            detail_fav_subject,
    )
    return


@app.cell(hide_code=True)
def _(aggregates, chart_int_test, detail_int_test, render_field_card, schema):
    # Field: int_test (integer)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "int_test"),
            aggregates["int_test"],
            None,
            chart_int_test,
            detail_int_test,
    )
    return


@app.cell(hide_code=True)
def _(
    aggregates,
    chart_decimal_test,
    detail_decimal_test,
    render_field_card,
    schema,
):
    # Field: decimal_test (decimal)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "decimal_test"),
            aggregates["decimal_test"],
            None,
            chart_decimal_test,
            detail_decimal_test,
    )
    return


@app.cell(hide_code=True)
def _(
    aggregates,
    chart_range_test,
    detail_range_test,
    render_field_card,
    schema,
):
    # Field: range_test (range)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "range_test"),
            aggregates["range_test"],
            None,
            chart_range_test,
            detail_range_test,
    )
    return


@app.cell(hide_code=True)
def _(aggregates, detail_date_test, render_field_card, schema):
    # Field: date_test (date)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "date_test"),
            aggregates["date_test"],
            None,
            None,
            detail_date_test,
    )
    return


@app.cell(hide_code=True)
def _(aggregates, detail_time_test, render_field_card, schema):
    # Field: time_test (time)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "time_test"),
            aggregates["time_test"],
            None,
            None,
            detail_time_test,
    )
    return


@app.cell(hide_code=True)
def _(aggregates, detail_date_time, render_field_card, schema):
    # Field: date_time (datetime)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "date_time"),
            aggregates["date_time"],
            None,
            None,
            detail_date_time,
    )
    return


@app.cell(hide_code=True)
def _(aggregates, detail_image_test, render_field_card, schema):
    # Field: image_test (image)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "image_test"),
            aggregates["image_test"],
            None,
            None,
            detail_image_test,
    )
    return


@app.cell(hide_code=True)
def _(aggregates, detail_file_test, render_field_card, schema):
    # Field: file_test (file)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "file_test"),
            aggregates["file_test"],
            None,
            None,
            detail_file_test,
    )
    return


@app.cell(hide_code=True)
def _(
    aggregates,
    chart_autocalc_test,
    detail_autocalc_test,
    render_field_card,
    schema,
):
    # Field: autocalc_test (auto_calculated)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "autocalc_test"),
            aggregates["autocalc_test"],
            None,
            chart_autocalc_test,
            detail_autocalc_test,
    )
    return


@app.cell(hide_code=True)
def _(aggregates, detail_geolocation_test, render_field_card, schema):
    # Field: geolocation_test (geopoint)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "geolocation_test"),
            aggregates["geolocation_test"],
            None,
            None,
            detail_geolocation_test,
    )
    return


@app.cell(hide_code=True)
def _(aggregates, detail_barcode_test, render_field_card, schema):
    # Field: barcode_test (barcode)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "barcode_test"),
            aggregates["barcode_test"],
            None,
            None,
            detail_barcode_test,
    )
    return


@app.cell(hide_code=True)
def _(aggregates, detail_geo_area_test, render_field_card, schema):
    # Field: geo_area_test (geo_area)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "geo_area_test"),
            aggregates["geo_area_test"],
            None,
            None,
            detail_geo_area_test,
    )
    return


@app.cell(hide_code=True)
def _(
    aggregates,
    chart_percent_test,
    detail_percent_test,
    render_field_card,
    schema,
):
    # Field: percent_test (percent)
    render_field_card(
            next(_f for _f in schema if _f["name"] == "percent_test"),
            aggregates["percent_test"],
            None,
            chart_percent_test,
            detail_percent_test,
    )
    return


if __name__ == "__main__":
    app.run()
