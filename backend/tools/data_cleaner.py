"""
tools/data_cleaner.py
Data Cleaning & Preprocessing Node — DAAT Phase 2

Posisi di pipeline:
    load_data → clean_data → profile_columns → compute_statistics → ...

Output tambahan ke state:
    cleaning_report: dict  — ringkasan apa yang dibersihkan (untuk narrative_generator)

Langkah cleaning (berurutan):
    1. Hapus kolom yang seluruhnya kosong (100% missing)
    2. Hapus duplikat eksak
    3. Parse kolom datetime (object → datetime64)
    4. Hapus baris dengan terlalu banyak nilai kosong (> threshold)
    5. Fill missing values numerik dengan median
    6. Hapus baris transaksi tidak valid (price ≤ 0, quantity ≤ 0)
    7. Outlier capping IQR pada kolom numerik lain (bukan remove — replace dengan batas IQR)
"""

import logging
import warnings
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Konfigurasi default ──────────────────────────────────────────────────────

MISSING_ROW_THRESHOLD = 0.5       # Drop baris jika > 50% kolomnya kosong
MISSING_COL_THRESHOLD = 1.0       # Drop kolom jika 100% nilainya kosong
IQR_MULTIPLIER        = 3.0       # Cap outlier di Q1 - k*IQR dan Q3 + k*IQR
                                   # (3.0 = hanya outlier ekstrem; konservatif)
MIN_ROWS_AFTER_CLEAN  = 100       # Batalkan cleaning jika hasil < 100 baris

# Nama kolom yang menandakan nilai harus positif (price, amount, revenue, ...)
MUST_POSITIVE_PATTERNS = [
    "price", "harga", "unitprice",
    "amount", "total", "revenue",
    "salary", "gaji", "pendapatan",
]
MUST_NONNEGATIVE_PATTERNS = [
    "quantity", "qty", "jumlah", "count",
    "age", "umur", "usia",
    "duration", "durasi",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _match_pattern(col: str, patterns: list[str]) -> bool:
    col_lower = col.lower()
    return any(p in col_lower for p in patterns)


def _try_parse_datetime(series: pd.Series) -> pd.Series | None:
    """Coba parse series object sebagai datetime. Return None jika gagal."""
    if not pd.api.types.is_object_dtype(series):
        return None
    sample = series.dropna().head(20)
    if len(sample) == 0:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(sample, errors="coerce")
        success_rate = parsed.notna().sum() / len(sample)
        if success_rate >= 0.8:
            return pd.to_datetime(series, errors="coerce")
    except Exception:
        pass
    return None


# ── Node utama ───────────────────────────────────────────────────────────────

def data_cleaner_node(state: dict) -> dict:
    """
    LangGraph-compatible node: bersihkan DataFrame dan simpan cleaning_report.

    Expects state["dataframe"] as pd.DataFrame.
    Returns updated state with cleaned dataframe and cleaning_report.
    """
    df: pd.DataFrame = state["dataframe"].copy()
    original_shape = df.shape
    report: dict[str, Any] = {
        "original_rows": original_shape[0],
        "original_cols": original_shape[1],
        "steps": [],
    }

    # ── Step 1: Hapus kolom 100% kosong ─────────────────────────────────────
    empty_cols = df.columns[df.isnull().mean() >= MISSING_COL_THRESHOLD].tolist()
    if empty_cols:
        df.drop(columns=empty_cols, inplace=True)
        report["steps"].append({
            "step": "drop_empty_columns",
            "detail": f"Hapus {len(empty_cols)} kolom kosong: {empty_cols}",
        })
        logger.info(f"[cleaner] Drop empty cols: {empty_cols}")

    # ── Step 2: Hapus duplikat eksak ─────────────────────────────────────────
    n_before = len(df)
    df.drop_duplicates(inplace=True)
    n_dup = n_before - len(df)
    if n_dup > 0:
        report["steps"].append({
            "step": "drop_duplicates",
            "detail": f"Hapus {n_dup} baris duplikat ({n_dup / n_before * 100:.1f}%)",
        })
        logger.info(f"[cleaner] Dropped {n_dup} duplicates")

    # ── Step 3: Parse kolom datetime (object → datetime64) ───────────────────
    datetime_parsed = []
    for col in df.select_dtypes(include="object").columns:
        result = _try_parse_datetime(df[col])
        if result is not None:
            df[col] = result
            datetime_parsed.append(col)
    if datetime_parsed:
        report["steps"].append({
            "step": "parse_datetime",
            "detail": f"Kolom dikonversi ke datetime: {datetime_parsed}",
        })
        logger.info(f"[cleaner] Datetime parsed: {datetime_parsed}")

    # ── Step 4: Hapus baris dengan terlalu banyak nilai kosong ───────────────
    n_before = len(df)
    missing_ratio = df.isnull().mean(axis=1)
    df = df[missing_ratio <= MISSING_ROW_THRESHOLD]
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        report["steps"].append({
            "step": "drop_sparse_rows",
            "detail": f"Hapus {n_dropped} baris dengan >50% nilai kosong",
        })

    # ── Step 5: Fill missing values pada kolom numerik dengan median ──────────
    numeric_cols_with_missing = [
        c for c in df.select_dtypes(include="number").columns
        if df[c].isnull().sum() > 0
    ]
    fill_report = {}
    for col in numeric_cols_with_missing:
        n_missing = int(df[col].isnull().sum())
        median_val = df[col].median()
        df[col] = df[col].fillna(median_val)
        fill_report[col] = {"missing": n_missing, "filled_with": round(float(median_val), 4)}
    if fill_report:
        report["steps"].append({
            "step": "fill_numeric_missing",
            "detail": f"Isi nilai kosong dengan median: {fill_report}",
        })
        logger.info(f"[cleaner] Filled missing numeric: {list(fill_report.keys())}")

    # ── Step 6: Hapus baris transaksi tidak valid ─────────────────────────────
    # Price / harga harus > 0
    n_before = len(df)
    for col in df.select_dtypes(include="number").columns:
        if _match_pattern(col, MUST_POSITIVE_PATTERNS):
            df = df[df[col] > 0]
    n_invalid_price = n_before - len(df)

    # Quantity / jumlah harus > 0 (qty=0 tidak bermakna; negatif = retur/cancel)
    n_before = len(df)
    for col in df.select_dtypes(include="number").columns:
        if _match_pattern(col, MUST_NONNEGATIVE_PATTERNS):
            df = df[df[col] > 0]
    n_invalid_qty = n_before - len(df)

    if n_invalid_price > 0 or n_invalid_qty > 0:
        report["steps"].append({
            "step": "remove_invalid_transactions",
            "detail": (
                f"Hapus {n_invalid_price} baris harga tidak valid (≤0), "
                f"{n_invalid_qty} baris quantity tidak valid (≤0) "
                f"— kemungkinan transaksi retur/pembatalan"
            ),
        })
        logger.info(f"[cleaner] Removed invalid: price={n_invalid_price}, qty={n_invalid_qty}")

    # ── Step 7: Outlier capping (IQR × 3.0) pada kolom numerik lain ──────────
    # Cap (bukan drop) — nilai ekstrem di-replace dengan batas IQR
    outlier_report = {}
    for col in df.select_dtypes(include="number").columns:
        # Jangan cap kolom yang sudah difilter di step 6
        if _match_pattern(col, MUST_POSITIVE_PATTERNS + MUST_NONNEGATIVE_PATTERNS):
            continue
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower = q1 - IQR_MULTIPLIER * iqr
        upper = q3 + IQR_MULTIPLIER * iqr
        n_out = int(((df[col] < lower) | (df[col] > upper)).sum())
        if n_out > 0:
            df[col] = df[col].clip(lower=lower, upper=upper)
            outlier_report[col] = {
                "capped": n_out,
                "range": [round(float(lower), 2), round(float(upper), 2)],
            }
    if outlier_report:
        report["steps"].append({
            "step": "outlier_capping",
            "detail": f"Cap outlier ekstrem (IQR×{IQR_MULTIPLIER}): {outlier_report}",
        })
        logger.info(f"[cleaner] Outlier capped: {list(outlier_report.keys())}")

    # ── Validasi: batalkan jika data terlalu sedikit ──────────────────────────
    if len(df) < MIN_ROWS_AFTER_CLEAN:
        logger.warning(
            f"[cleaner] After cleaning only {len(df)} rows remain — reverting to original!"
        )
        df = state["dataframe"].copy()
        report["steps"] = []
        report["warning"] = f"Cleaning dibatalkan: hanya tersisa {len(df)} baris"

    # ── Finalisasi report ─────────────────────────────────────────────────────
    report["cleaned_rows"] = len(df)
    report["cleaned_cols"] = len(df.columns)
    report["rows_removed"] = original_shape[0] - len(df)
    report["rows_removed_pct"] = round(
        (original_shape[0] - len(df)) / original_shape[0] * 100, 1
    )

    logger.info(
        f"[cleaner] Done: {original_shape[0]}→{len(df)} rows "
        f"({report['rows_removed_pct']}% removed), {len(df.columns)} cols"
    )

    return {**state, "dataframe": df, "cleaning_report": report}
