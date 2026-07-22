"""Load sales data files (CSV, TSV, XLSX, XLS) into pandas DataFrames.

Format is auto-detected from the file extension, with a fallback delimiter
sniff for .csv/.txt files that turn out to be tab- or semicolon-separated.
Column names are normalized (trimmed, lowercased, spaces collapsed) so that
files with slightly different header formatting still line up with the
columns the rest of the app expects.
"""

import csv
import os

import pandas as pd

EXCEL_EXTENSIONS = {'.xlsx', '.xls'}
TEXT_EXTENSIONS = {'.csv', '.tsv', '.txt'}
SUPPORTED_EXTENSIONS = EXCEL_EXTENSIONS | TEXT_EXTENSIONS


def normalize_columns(df):
    df = df.copy()
    df.columns = [str(c).strip().lower().replace('  ', ' ') for c in df.columns]
    return df


def strip_string_cells(df):
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
    return df


def _sniff_delimiter(path):
    with open(path, 'r', newline='', errors='ignore') as f:
        sample = f.read(4096)
    try:
        return csv.Sniffer().sniff(sample, delimiters=',\t;|').delimiter
    except csv.Error:
        return ','


def load_file(path):
    """Load a single file into a DataFrame.

    Returns (dataframe_or_none, error_message_or_none). Never raises —
    any failure is turned into a plain-English message the GUI can show.
    """
    filename = os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        supported = ', '.join(sorted(SUPPORTED_EXTENSIONS))
        return None, (
            f"\"{filename}\" is not a supported file type. "
            f"Please use one of: {supported}"
        )

    try:
        if ext in EXCEL_EXTENSIONS:
            df = pd.read_excel(path)
        elif ext == '.tsv':
            df = pd.read_csv(path, sep='\t')
        else:
            delimiter = _sniff_delimiter(path)
            df = pd.read_csv(path, sep=delimiter, engine='python')
    except Exception:
        return None, (
            f"\"{filename}\" could not be opened. It may be corrupted, "
            f"password-protected, or open in another program. "
            f"Please check the file and try again."
        )

    if df.shape[1] == 1:
        # Likely wrong delimiter was used (e.g. tab-separated file with a .csv extension)
        try:
            delimiter = _sniff_delimiter(path)
            retry = pd.read_csv(path, sep=delimiter, engine='python')
            if retry.shape[1] > 1:
                df = retry
        except Exception:
            pass

    df = normalize_columns(df)
    df = strip_string_cells(df)
    return df, None


def load_files(paths):
    """Load multiple files.

    Returns a dict keyed by filename with values {"dataframe": df or None,
    "error": message or None}, preserving the order files were given in.
    """
    results = {}
    for path in paths:
        filename = os.path.basename(path)
        df, error = load_file(path)
        results[filename] = {"dataframe": df, "error": error}
    return results


def combine_dataframes(dataframes):
    """Concatenate a list of validated DataFrames into one working dataset."""
    if not dataframes:
        return pd.DataFrame()
    return pd.concat(dataframes, ignore_index=True, sort=False)
