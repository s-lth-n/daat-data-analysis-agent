"""
Statistics Tool
===============
Computes descriptive statistics on DataFrames.
Designed to be called by the LangGraph data analysis agent.
"""

import logging
import math
from typing import Any

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def _safe_float(value: float, decimals: int = 4) -> float | None:
    """Round float, returning None for NaN/Inf to keep JSON-safe output."""
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, decimals)
    except (TypeError, ValueError):
        return None


def descriptive_statistics(
    df: pd.DataFrame,
    numeric_cols: list[str] | None = None,
    domain_context: dict | None = None,
) -> dict[str, Any]:
    """
    Compute comprehensive descriptive statistics.

    Args:
        df: Source DataFrame.
        numeric_cols: Explicit list of validated numeric columns from column profiler.
                      If None, falls back to all numeric dtypes (legacy behaviour).
        domain_context: Domain detection result from detect_domain(). When
                        preferred_aggregation is "sum", total_sum is included per column.

    Returns:
        Dict with per-column stats and overall dataset info.
    """
    if numeric_cols is not None:
        # Use profiler-validated columns only (excludes IDs, year codes, etc.)
        valid_cols = [c for c in numeric_cols if c in df.columns]
        numeric_df = df[valid_cols] if valid_cols else pd.DataFrame()
    else:
        numeric_df = df.select_dtypes(include="number")

    if numeric_df.empty:
        return {"error": "No numeric columns found in dataset."}

    preferred_agg = (domain_context or {}).get("preferred_aggregation", "mean")

    stats = {}
    for col in numeric_df.columns:
        series = numeric_df[col].dropna()
        col_stats: dict[str, Any] = {
            "count": int(series.count()),
            "mean": _safe_float(series.mean()),
            "median": _safe_float(series.median()),
            "std": _safe_float(series.std()),
            "min": _safe_float(series.min()),
            "max": _safe_float(series.max()),
            "q25": _safe_float(series.quantile(0.25)),
            "q75": _safe_float(series.quantile(0.75)),
            "skewness": _safe_float(series.skew()),
            "kurtosis": _safe_float(series.kurtosis()),
            "null_count": int(df[col].isnull().sum()),
            "null_percentage": _safe_float(df[col].isnull().mean() * 100, 2),
        }
        if preferred_agg == "sum":
            col_stats["total_sum"] = _safe_float(series.sum(), 2)
        stats[col] = col_stats

    logger.info(
        f"Computed statistics for {len(stats)} numeric columns "
        f"(domain={( domain_context or {}).get('domain_type', 'n/a')}, "
        f"agg={preferred_agg})"
    )
    return stats


def correlation_matrix(
    df: pd.DataFrame,
    numeric_cols: list[str] | None = None,
) -> dict[str, Any]:
    """
    Compute correlation matrix for numeric columns.

    Args:
        df: Source DataFrame.
        numeric_cols: Validated numeric columns from profiler. Falls back to all numeric.

    Returns:
        Dict with correlation values and interpretation hints.
    """
    if numeric_cols is not None:
        valid_cols = [c for c in numeric_cols if c in df.columns]
        numeric_df = df[valid_cols] if valid_cols else pd.DataFrame()
    else:
        numeric_df = df.select_dtypes(include="number")

    if numeric_df.shape[1] < 2:
        return {"error": "Need at least 2 numeric columns for correlation."}

    corr = numeric_df.corr().round(4)

    # Find strong correlations (|r| > 0.7, excluding self-correlation)
    strong = []
    for i in range(len(corr.columns)):
        for j in range(i + 1, len(corr.columns)):
            r = corr.iloc[i, j]
            if abs(r) > 0.7:
                strong.append({
                    "col1": corr.columns[i],
                    "col2": corr.columns[j],
                    "correlation": float(r),
                    "strength": "strong positive" if r > 0 else "strong negative",
                })

    matrix_raw = corr.to_dict()
    matrix_safe = {
        col: {k: _safe_float(v) for k, v in row.items()}
        for col, row in matrix_raw.items()
    }

    return {
        "matrix": matrix_safe,
        "strong_correlations": strong,
    }


def categorical_summary(df: pd.DataFrame) -> dict[str, Any]:
    """
    Summarize categorical columns.
    """
    cat_df = df.select_dtypes(include=["object", "category"])

    if cat_df.empty:
        return {"error": "No categorical columns found."}

    summary = {}
    for col in cat_df.columns:
        vc = df[col].value_counts()
        summary[col] = {
            "unique_count": int(df[col].nunique()),
            "top_values": vc.head(10).to_dict(),
            "null_count": int(df[col].isnull().sum()),
        }

    return summary


def format_stats_as_text(
    stats: dict[str, Any],
    language: str = "id",
) -> str:
    """
    Format statistics dict into human-readable text.
    Supports Indonesian (id) and English (en).
    """
    if "error" in stats:
        return stats["error"]

    lines = []

    if language == "id":
        lines.append("## Ringkasan Statistik Deskriptif\n")
        for col, s in stats.items():
            lines.append(f"### Kolom: {col}")
            lines.append(f"- Jumlah data: {s['count']}")
            if "total_sum" in s:
                lines.append(f"- Total (sum): {s['total_sum']}")
            lines.append(f"- Rata-rata: {s['mean']}")
            lines.append(f"- Median: {s['median']}")
            lines.append(f"- Standar deviasi: {s['std']}")
            lines.append(f"- Nilai minimum: {s['min']}")
            lines.append(f"- Nilai maksimum: {s['max']}")
            lines.append(f"- Kuartil 25%: {s['q25']}")
            lines.append(f"- Kuartil 75%: {s['q75']}")
            lines.append(f"- Data kosong: {s['null_count']} ({s['null_percentage']}%)")
            lines.append("")
    else:
        lines.append("## Descriptive Statistics Summary\n")
        for col, s in stats.items():
            lines.append(f"### Column: {col}")
            lines.append(f"- Count: {s['count']}")
            if "total_sum" in s:
                lines.append(f"- Total (sum): {s['total_sum']}")
            lines.append(f"- Mean: {s['mean']}")
            lines.append(f"- Median: {s['median']}")
            lines.append(f"- Std Dev: {s['std']}")
            lines.append(f"- Min: {s['min']}")
            lines.append(f"- Max: {s['max']}")
            lines.append(f"- Q25: {s['q25']}")
            lines.append(f"- Q75: {s['q75']}")
            lines.append(f"- Null values: {s['null_count']} ({s['null_percentage']}%)")
            lines.append("")

    return "\n".join(lines)
