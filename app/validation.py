"""Validate a loaded sales data file and produce plain-English error messages.

Validation runs the moment a file is loaded, before any report processing.
Nothing here ever raises a raw exception up to the GUI — every failure mode
is translated into a short, actionable sentence a non-technical user can act on.
"""

import pandas as pd

REQUIRED_COLUMNS = ['date', 'region', 'category', 'product', 'sales',
                    'discount', 'profit', 'store_id']

NUMERIC_COLUMNS = ['sales', 'discount', 'profit']
CRITICAL_COLUMNS = ['sales', 'profit', 'region']


def _is_numeric_column(series):
    """True if every non-null value in the column can be read as a number."""
    coerced = pd.to_numeric(series, errors='coerce')
    non_null_original = series.notna()
    return not (coerced.isna() & non_null_original).any()


def validate_dataframe(df, source_name):
    """Check a single loaded file for the problems the report generator can't recover from.

    Returns (True, None) if the file is good to use, or (False, message) where
    message is a plain-English, newline-separated list of what's wrong, prefixed
    with the file name so the user knows exactly which upload to fix.
    """
    errors = []

    if df is None:
        errors.append("The file could not be read")
        return False, _format_errors(source_name, errors)

    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        errors.append(
            f"Missing column(s): {', '.join(missing_cols)} — "
            f"please check your export includes these fields"
        )

    if df.empty:
        errors.append("File contains no data rows")

    if missing_cols or df.empty:
        # Remaining checks assume the required columns exist and there's data to check.
        return False, _format_errors(source_name, errors)

    for col in CRITICAL_COLUMNS:
        if df[col].isnull().any():
            count = int(df[col].isnull().sum())
            row_word = 'row' if count == 1 else 'rows'
            errors.append(f"'{col}' is missing a value in {count} {row_word}")

    for col in NUMERIC_COLUMNS:
        if not _is_numeric_column(df[col]):
            errors.append(f"'{col}' contains values that aren't numbers (e.g. text or symbols)")

    parsed_dates = pd.to_datetime(df['date'], errors='coerce')
    bad_dates = int(parsed_dates.isna().sum())
    if bad_dates:
        row_word = 'row' if bad_dates == 1 else 'rows'
        errors.append(f"'date' has {bad_dates} {row_word} that aren't a recognizable date")

    if df['store_id'].isnull().any():
        count = int(df['store_id'].isnull().sum())
        row_word = 'row' if count == 1 else 'rows'
        errors.append(f"'store_id' is missing a value in {count} {row_word}")

    if errors:
        return False, _format_errors(source_name, errors)
    return True, None


def _format_errors(source_name, errors):
    return f"Problem with {source_name}:\n" + "\n".join(f"• {e}" for e in errors)


def validate_loaded_files(loaded_files):
    """Run validate_dataframe over every file loaded by ingestion.load_files.

    `loaded_files` is the dict returned by ingestion.load_files: filename ->
    {"dataframe": df or None, "error": load-time error or None}.

    Returns a dict filename -> {"ok": bool, "message": str or None, "dataframe": df or None}.
    A file that failed to load at all is reported using its load-time error.
    """
    results = {}
    for filename, info in loaded_files.items():
        if info["error"] is not None:
            results[filename] = {
                "ok": False,
                "message": _format_errors(filename, [info["error"]]),
                "dataframe": None,
            }
            continue

        ok, message = validate_dataframe(info["dataframe"], filename)
        results[filename] = {
            "ok": ok,
            "message": message,
            "dataframe": info["dataframe"] if ok else None,
        }
    return results
