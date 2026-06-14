"""
Visualization Tool
==================
Generates interactive Plotly charts from DataFrames.
Returns Plotly JSON specs (list[dict]) — rendered to PNG via /chart/render endpoint.

Chart priority (auto_visualize):
  1. Time trend  — if datetime col + numeric available (aggregated by month)
  2. Top-N bar   — top categories by revenue/sum (horizontal, sorted)
  3. Distribution — histogram with IQR outlier clipping
  4. Scatter      — if 2+ numeric cols (sampled to avoid overplot)
  Fallback: correlation heatmap if 3+ numeric cols
"""

import json
import logging
import warnings
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

from config import settings

logger = logging.getLogger(__name__)

# Max charts returned per analysis
MAX_CHARTS = 3


# ── Serialization ──────────────────────────────────────────────────────────

def _fig_to_dict(fig) -> dict:
    """Convert Plotly figure to a pure JSON-serializable dict (no numpy arrays)."""
    return json.loads(pio.to_json(fig))


def _base_layout(fig, title: str) -> None:
    """Apply consistent layout to any figure."""
    fig.update_layout(
        title=dict(text=title, font_size=14),
        template="plotly_white",
        width=settings.chart_default_width,
        height=settings.chart_default_height,
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=50, r=40, t=55, b=50),
    )


# ── Chart builders ─────────────────────────────────────────────────────────

def create_bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "Bar Chart",
    color: str | None = None,
    orientation: str = "v",
    labels: dict | None = None,
) -> dict:
    """Vertical or horizontal bar chart."""
    if orientation == "h":
        _labels = labels if labels is not None else {x: x, y: f"Total {y}"}
        fig = px.bar(df, x=y, y=x, orientation="h", color=y,
                     color_continuous_scale="Blues",
                     labels=_labels)
        fig.update_layout(coloraxis_showscale=False, yaxis_title="")
    else:
        fig = px.bar(df, x=x, y=y, color=color,
                     labels={x: x, y: y})
    _base_layout(fig, title)
    logger.info(f"Created bar chart: {title}")
    return _fig_to_dict(fig)


def create_line_chart(
    df: pd.DataFrame,
    x: str,
    y: str | list[str],
    title: str = "Line Chart",
) -> dict:
    """Line chart for trends."""
    if isinstance(y, list):
        fig = go.Figure()
        for col in y:
            fig.add_trace(go.Scatter(x=df[x], y=df[col], mode="lines+markers", name=col))
    else:
        fig = px.line(df, x=x, y=y, markers=True,
                      color_discrete_sequence=["#2563EB"])
        fig.update_traces(line_width=2.5, marker_size=6)
    fig.update_xaxes(tickangle=45)
    _base_layout(fig, title)
    logger.info(f"Created line chart: {title}")
    return _fig_to_dict(fig)


def create_scatter_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "Scatter Plot",
    color: str | None = None,
    trendline: str | None = None,
    sample_n: int = 2000,
) -> dict:
    """Scatter plot with sampling to avoid overplot."""
    plot_df = df[[c for c in [x, y, color] if c]].dropna()
    if len(plot_df) > sample_n:
        plot_df = plot_df.sample(sample_n, random_state=42)
    fig = px.scatter(plot_df, x=x, y=y, color=color, trendline=trendline,
                     opacity=0.45, color_discrete_sequence=["#2563EB"])
    _base_layout(fig, title)
    logger.info(f"Created scatter chart: {title}")
    return _fig_to_dict(fig)


def create_histogram(
    df: pd.DataFrame,
    column: str,
    bins: int = 40,
    title: str | None = None,
    clip_outliers: bool = True,
) -> dict:
    """Histogram with optional IQR outlier clipping."""
    s = df[column].dropna()
    if clip_outliers and len(s) > 0:
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr > 0:
            s = s[(s >= q1 - 1.5 * iqr) & (s <= q3 + 1.5 * iqr)]

    title = title or f"Distribusi {column}"
    fig = px.histogram(s, x=column, nbins=bins,
                       color_discrete_sequence=["#3B82F6"],
                       labels={column: column, "count": "Frekuensi"})
    fig.update_traces(marker_line_width=0.5, marker_line_color="white")
    _base_layout(fig, title)
    logger.info(f"Created histogram: {title}")
    return _fig_to_dict(fig)


def create_correlation_heatmap(
    df: pd.DataFrame,
    numeric_cols: list[str] | None = None,
    title: str = "Matriks Korelasi",
) -> dict:
    """Heatmap of correlation matrix. Only meaningful with 3+ numeric cols."""
    cols = numeric_cols if numeric_cols else df.select_dtypes(include="number").columns.tolist()
    corr = df[cols].corr().round(3)
    fig = px.imshow(corr, text_auto=True, color_continuous_scale="RdBu_r",
                    zmin=-1, zmax=1)
    _base_layout(fig, title)
    logger.info("Created correlation heatmap")
    return _fig_to_dict(fig)


# ── Domain-specific helpers ────────────────────────────────────────────────

def _derive_revenue(df: pd.DataFrame, numeric_cols: list[str]) -> tuple[pd.DataFrame, str | None]:
    """
    Derive Revenue = Quantity × Price if both columns are detected.
    Returns (df_with_revenue, revenue_col_name) or (df, None).
    """
    qty_col = next(
        (c for c in numeric_cols if any(k in c.lower() for k in ["quantity", "qty"])),
        None,
    )
    price_col = next(
        (c for c in numeric_cols if any(k in c.lower() for k in ["price", "unitprice", "harga"])),
        None,
    )
    if qty_col and price_col:
        df = df.copy()
        df["Revenue"] = df[qty_col] * df[price_col]
        logger.info(f"Derived Revenue = {qty_col} × {price_col}")
        return df, "Revenue"
    return df, None


def _build_trend_chart(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    language: str,
) -> dict | None:
    """Monthly aggregated line chart for a date + numeric column pair."""
    try:
        temp = df[[date_col, value_col]].copy()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            temp[date_col] = pd.to_datetime(temp[date_col], errors="coerce")
        temp = temp.dropna(subset=[date_col])
        temp["_month"] = temp[date_col].dt.to_period("M").astype(str)
        monthly = (temp.groupby("_month")[value_col].sum()
                   .reset_index()
                   .rename(columns={"_month": "Bulan"})
                   .sort_values("Bulan"))
        title = (f"Tren {value_col} per Bulan" if language == "id"
                 else f"{value_col} Trend by Month")
        return create_line_chart(monthly, x="Bulan", y=value_col, title=title)
    except Exception as e:
        logger.warning(f"_build_trend_chart failed: {e}")
        return None


def _build_top_categories_chart(
    df: pd.DataFrame,
    cat_col: str,
    value_col: str,
    top_n: int,
    language: str,
    label_override: str | None = None,
    aggregation: str = "sum",
) -> dict | None:
    """Horizontal bar chart: top-N categories by sum or mean of value_col."""
    try:
        grouped = (df[[cat_col, value_col]].dropna()
                   .groupby(cat_col)[value_col].agg(aggregation)
                   .nlargest(top_n)
                   .reset_index()
                   .sort_values(value_col))  # ascending for horizontal bar
        if grouped.empty:
            return None
        if label_override:
            title = label_override
        elif language == "en":
            agg_label = "Average" if aggregation != "sum" else "Total"
            title = f"Top {top_n} {cat_col} by {agg_label} {value_col}"
        else:
            agg_label = "Rata-rata" if aggregation != "sum" else "Total"
            title = f"Top {top_n} {cat_col} berdasarkan {agg_label} {value_col}"
        x_label = f"Rata-rata {value_col}" if aggregation != "sum" else f"Total {value_col}"
        return create_bar_chart(grouped, x=cat_col, y=value_col,
                                title=title, orientation="h",
                                labels={cat_col: cat_col, value_col: x_label})
    except Exception as e:
        logger.warning(f"_build_top_categories_chart failed: {e}")
        return None


# ── Main entry point ───────────────────────────────────────────────────────

def auto_visualize(
    df: pd.DataFrame,
    language: str = "id",
    column_profile: dict | None = None,
    domain_context: dict | None = None,
) -> list[dict]:
    """
    Automatically generate up to MAX_CHARTS relevant charts.

    Priority order:
      1. Time trend line chart   (if datetime + numeric col available)
      2. Top-N category bar chart (domain-specific: product/country by revenue)
      3. Distribution histogram   (IQR-clipped, most informative numeric col)
      4. Scatter plot             (if 2+ numeric cols, sampled)
      Fallback: correlation heatmap (only if 3+ numeric and no other charts)

    Args:
        df: Source DataFrame.
        language: "id" (Indonesian) or "en" (English) for titles.
        column_profile: Output from Smart Column Profiler. Falls back to
                        pandas dtype detection if None.
        domain_context: Output from detect_domain(). Controls bar chart
                        aggregation: "sum" for retail/finance, "mean" otherwise.
    """
    preferred_agg = (domain_context or {}).get("preferred_aggregation", "sum")
    charts: list[dict] = []

    # ── Resolve column lists ───────────────────────────────────────────────
    if column_profile:
        from tools.column_profiler import get_numeric_columns, get_categorical_columns
        numeric_cols = [c for c in get_numeric_columns(column_profile) if c in df.columns]
        cat_cols = [c for c in get_categorical_columns(column_profile) if c in df.columns]
        datetime_cols = [c for c, lbl in column_profile.items()
                         if lbl == "datetime" and c in df.columns]
        logger.info(
            f"auto_visualize — numeric: {numeric_cols}, "
            f"cat: {cat_cols}, datetime: {datetime_cols}"
        )
    else:
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
        datetime_cols = df.select_dtypes(include="datetime").columns.tolist()

    if not numeric_cols and not cat_cols:
        logger.warning("No usable columns found for visualization")
        return charts

    # ── Derive Revenue if qty × price columns exist ────────────────────────
    df, revenue_col = _derive_revenue(df, numeric_cols)
    if revenue_col:
        # Filter valid transactions (positive qty)
        qty_col = next((c for c in numeric_cols if any(
            k in c.lower() for k in ["quantity", "qty"])), None)
        df_valid = df[df[qty_col] > 0].copy() if qty_col else df
    else:
        df_valid = df

    # Primary value column for aggregation
    value_col = revenue_col or (numeric_cols[0] if numeric_cols else None)

    # ── Chart 1: Time trend ────────────────────────────────────────────────
    if datetime_cols and value_col and len(charts) < MAX_CHARTS:
        chart = _build_trend_chart(df_valid, datetime_cols[0], value_col, language)
        if chart:
            charts.append(chart)

    # ── Chart 2a: Top products/items by value ──────────────────────────────
    desc_col = next((c for c in cat_cols if any(
        kw in c.lower() for kw in ["description", "product", "item", "produk", "nama"]
    )), None)
    if desc_col and value_col and len(charts) < MAX_CHARTS:
        chart = _build_top_categories_chart(
            df_valid, desc_col, value_col, top_n=10, language=language,
            aggregation=preferred_agg,
            label_override=(
                "Top 10 Produk by Revenue" if revenue_col and language == "id"
                else None
            ),
        )
        if chart:
            charts.append(chart)

    # ── Chart 2b: Sales by country/region ─────────────────────────────────
    country_col = next((c for c in cat_cols if any(
        kw in c.lower() for kw in ["country", "negara", "region", "wilayah", "location"]
    )), None)
    if country_col and value_col and len(charts) < MAX_CHARTS:
        if language == "id":
            agg_prefix = "Rata-rata" if preferred_agg != "sum" else "Total"
            loc_label_override = f"{agg_prefix} {value_col} per Negara (Top 15)"
        else:
            agg_prefix = "Average" if preferred_agg != "sum" else "Total"
            loc_label_override = f"{agg_prefix} {value_col} per Location (Top 15)"
        chart = _build_top_categories_chart(
            df_valid, country_col, value_col, top_n=15, language=language,
            aggregation=preferred_agg,
            label_override=loc_label_override,
        )
        if chart:
            charts.append(chart)

    # ── Chart 3: Distribution (fallback, IQR-clipped) ─────────────────────
    if numeric_cols and len(charts) < MAX_CHARTS:
        target = next(
            (c for c in numeric_cols if "revenue" not in c.lower()),
            numeric_cols[0],
        )
        title = (f"Distribusi {target}" if language == "id"
                 else f"Distribution of {target}")
        charts.append(create_histogram(df, target, title=title, clip_outliers=True))

    # ── Chart 4: Scatter (fallback, sampled) ──────────────────────────────
    if len(numeric_cols) >= 2 and len(charts) < MAX_CHARTS:
        x, y = numeric_cols[0], numeric_cols[1]
        title = (f"Sebaran {x} vs {y}" if language == "id"
                 else f"Scatter: {x} vs {y}")
        charts.append(create_scatter_chart(df, x=x, y=y, title=title))

    # ── Fallback: correlation heatmap (only if nothing generated yet) ──────
    if not charts and len(numeric_cols) >= 3:
        title = "Matriks Korelasi" if language == "id" else "Correlation Matrix"
        charts.append(create_correlation_heatmap(df, numeric_cols=numeric_cols, title=title))

    logger.info(f"Auto-generated {len(charts)} visualizations")
    return charts
