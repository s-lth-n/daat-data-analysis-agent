"""
Data Loader Tool
================
Reads CSV and Excel files into Pandas DataFrames.
"""

import logging
import math
from pathlib import Path
from typing import Any

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively replace NaN/Inf float values with None for JSON safety."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


_TEMPORAL_KEYWORDS = ("year", "date", "time", "tahun", "periode", "month", "bulan")


def _detect_temporal_column(df: pd.DataFrame) -> str | None:
    """Return the first temporal column name found, or None."""
    for col in df.columns:
        if any(kw in col.lower() for kw in _TEMPORAL_KEYWORDS):
            return col
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col
    return None


def _stratified_temporal_sample(
    df: pd.DataFrame, temporal_col: str, max_rows: int = 50_000
) -> pd.DataFrame:
    """Sample `max_rows` rows from `df` with equal quota per `temporal_col` group.

    Pass-through guard: if the dataset already fits within `max_rows`, return ALL
    rows unchanged. Stratified sampling only engages for datasets that genuinely
    exceed the target — otherwise small files were silently truncated (e.g. a
    50K file with thousands of unique timestamps got chopped to ~31K because the
    per-group quota fell to a tiny integer).
    """
    if len(df) <= max_rows:
        return df.reset_index(drop=True)
    groups = df.groupby(temporal_col)
    # Honor the requested target (was hardcoded to 50_000, ignoring max_rows).
    n_per_group = max(1, max_rows // len(groups))
    frames = [g.sample(min(len(g), n_per_group), random_state=42) for _, g in groups]
    return pd.concat(frames).reset_index(drop=True)


def load_dataframe(file_path: str | Path) -> pd.DataFrame:
    """
    Load a data file (CSV or Excel) into a Pandas DataFrame.

    Args:
        file_path: Path to the data file.

    Returns:
        pd.DataFrame with loaded data.

    Raises:
        ValueError: If file format is unsupported.
        FileNotFoundError: If file does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path.suffix.lower()
    logger.info(f"Loading file: {path.name} (type: {suffix})")

    if suffix == ".csv":
        # Try common encodings
        for encoding in ["utf-8", "latin-1", "cp1252"]:
            try:
                df = pd.read_csv(path, encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError(f"Could not decode CSV file: {path.name}")

    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path, engine="openpyxl")

    else:
        raise ValueError(
            f"Unsupported file format: {suffix}. "
            f"Supported: {settings.allowed_extensions}"
        )

    # Sampling only engages when the dataset GENUINELY exceeds the row cap.
    # Files at/under the cap pass through untouched (no data loss).
    temporal_col = _detect_temporal_column(df)
    if len(df) <= settings.max_dataset_rows:
        logger.info(f"Dataset has {len(df)} rows (≤ {settings.max_dataset_rows}) — no sampling applied")
    elif temporal_col:
        logger.info(
            f"Dataset has {len(df)} rows (> {settings.max_dataset_rows}) — stratified sampling on "
            f"temporal column '{temporal_col}' → target {settings.max_dataset_rows} rows"
        )
        df = _stratified_temporal_sample(df, temporal_col, settings.max_dataset_rows)
    else:
        logger.info(
            f"Dataset has {len(df)} rows (> {settings.max_dataset_rows}) — no temporal column detected, "
            f"random sampling → {settings.max_dataset_rows} rows"
        )
        df = df.sample(settings.max_dataset_rows, random_state=42).reset_index(drop=True)

    logger.info(f"Loaded: {df.shape[0]} rows × {df.shape[1]} columns")
    return df


def load_and_preview(file_path: str | Path) -> dict[str, Any]:
    """
    Load a file and return a quick preview (for upload response).

    Returns:
        Dict with columns, dtypes, shape, and first 5 rows.
    """
    df = load_dataframe(file_path)

    return {
        "shape": {"rows": df.shape[0], "columns": df.shape[1]},
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "numeric_columns": list(df.select_dtypes(include="number").columns),
        "categorical_columns": list(df.select_dtypes(include=["object", "category"]).columns),
        "head": _sanitize_for_json(df.head(5).to_dict(orient="records")),
        "null_counts": {col: int(v) for col, v in df.isnull().sum().items()},
    }


def get_data_summary(df: pd.DataFrame) -> str:
    """
    Generate a text summary of the dataset for the LLM context.
    This helps the LLM understand the data structure.
    """
    lines = [
        f"Dataset: {df.shape[0]} rows × {df.shape[1]} columns",
        f"Columns: {', '.join(df.columns.tolist())}",
        "",
        "Column Types:",
    ]

    for col in df.columns:
        dtype = df[col].dtype
        null_pct = df[col].isnull().mean() * 100
        if pd.api.types.is_numeric_dtype(df[col]):
            lines.append(
                f"  - {col} ({dtype}): "
                f"min={df[col].min()}, max={df[col].max()}, "
                f"mean={df[col].mean():.2f}, nulls={null_pct:.1f}%"
            )
        else:
            unique = df[col].nunique()
            top = df[col].value_counts().head(3).index.tolist()
            lines.append(
                f"  - {col} ({dtype}): "
                f"{unique} unique values, top: {top}, nulls={null_pct:.1f}%"
            )

    return "\n".join(lines)
