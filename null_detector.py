"""null_detector: empty-string and sentinel normalization to Polars nulls.

Library usage:
    from null_detector import normalize_nulls_all, null_count, valid_count

Marimo interactive demo:
    conda activate corus_api_env
    marimo edit null_detector.py
"""

import marimo
import polars as pl

NULL_SENTINELS = ["", "N/A", "n/a"]


def normalize_nulls(df: pl.DataFrame, col: str) -> pl.DataFrame:
    """Rewrite a string column: trimmed values matching NULL_SENTINELS become null."""
    if df.schema[col] != pl.Utf8:
        return df
    return df.with_columns(
        pl.when(pl.col(col).str.strip_chars().is_in(NULL_SENTINELS))
        .then(None)
        .otherwise(pl.col(col))
        .alias(col)
    )


def normalize_nulls_all(df: pl.DataFrame) -> pl.DataFrame:
    """Apply normalize_nulls to every Utf8 column in the frame."""
    for c, dt in df.schema.items():
        if dt == pl.Utf8:
            df = normalize_nulls(df, c)
    return df


def null_count(s: pl.Series) -> int:
    return int(s.null_count())


def valid_count(s: pl.Series) -> int:
    return int(s.len() - s.null_count())


__generated_with = "0.23.6"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    from pathlib import Path
    import polars as pl_demo

    return Path, mo, pl_demo


@app.cell
def _(mo):
    mo.md(
        """
        # null_detector — interactive demo

        Loads `sample_data.csv` as raw strings and demonstrates how
        `normalize_nulls_all` converts empty-string responses to true
        Polars nulls.
        """
    )
    return


@app.cell
def _(Path):
    DATA_PATH = Path(__file__).parent / "sample_data.csv"
    return (DATA_PATH,)


@app.cell
def _(DATA_PATH, pl_demo):
    raw_df = pl_demo.read_csv(DATA_PATH, infer_schema_length=0)
    return (raw_df,)


@app.cell
def _(mo, pl_demo, raw_df):
    raw_counts = pl_demo.DataFrame(
        {
            "column": raw_df.columns,
            "raw_nulls": [int(raw_df[c].null_count()) for c in raw_df.columns],
        }
    )
    mo.vstack(
        [
            mo.md("## Raw null counts (no normalisation)"),
            mo.md(
                "Polars infers nothing as null by default — every empty cell "
                "is just an empty string. Expect 0 across the board."
            ),
            mo.ui.table(
                raw_counts.to_pandas(), page_size=25, selection=None
            ),
        ]
    )
    return


@app.cell
def _(mo, pl_demo, raw_df):
    normalized = normalize_nulls_all(raw_df)
    norm_counts = pl_demo.DataFrame(
        {
            "column": normalized.columns,
            "normalized_nulls": [
                int(normalized[c].null_count()) for c in normalized.columns
            ],
        }
    )
    mo.vstack(
        [
            mo.md("## Null counts after `normalize_nulls_all`"),
            mo.md(
                "Empty strings now register as Polars null. "
                "Columns like `email` and `percent_test` (non-required, ~20% missing) "
                "should show meaningful counts."
            ),
            mo.ui.table(
                norm_counts.to_pandas(), page_size=25, selection=None
            ),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
