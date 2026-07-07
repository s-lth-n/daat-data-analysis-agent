"""
Test suite for DAAT data analysis tools.
Run from project root: cd ~/ta-data-analyst && pytest tests/ -v
"""

from pathlib import Path

import pandas as pd
import pytest

# Sample data path (relative to project root)
SAMPLE_CSV = Path(__file__).parent.parent / "data" / "samples" / "penjualan_2024.csv"


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def sample_df():
    """Load sample CSV once, reuse across tests."""
    from tools.data_loader import load_dataframe
    return load_dataframe(SAMPLE_CSV)


# ── TestDataLoader ───────────────────────────────────────────────────

class TestDataLoader:
    """Tests for the data_loader tool."""

    def test_load_csv(self, sample_df):
        assert isinstance(sample_df, pd.DataFrame)
        assert sample_df.shape[0] == 12  # 12 months
        assert "penjualan" in sample_df.columns

    def test_load_and_preview(self):
        from tools.data_loader import load_and_preview
        preview = load_and_preview(SAMPLE_CSV)
        assert "shape" in preview
        assert preview["shape"]["rows"] == 12
        assert "numeric_columns" in preview
        assert "penjualan" in preview["numeric_columns"]

    def test_file_not_found(self):
        from tools.data_loader import load_dataframe
        with pytest.raises(FileNotFoundError):
            load_dataframe("/nonexistent/file.csv")

    def test_data_summary(self, sample_df):
        from tools.data_loader import get_data_summary
        summary = get_data_summary(sample_df)
        assert "12 rows" in summary
        assert "penjualan" in summary


# ── TestStatistics ───────────────────────────────────────────────────

class TestStatistics:
    """Tests for the statistics tool."""

    def test_descriptive_stats(self, sample_df):
        from tools.statistics import descriptive_statistics
        stats = descriptive_statistics(sample_df)
        assert "penjualan" in stats
        assert "mean" in stats["penjualan"]
        assert stats["penjualan"]["count"] == 12

    def test_correlation(self, sample_df):
        from tools.statistics import correlation_matrix
        corr = correlation_matrix(sample_df)
        assert "matrix" in corr

    def test_categorical_summary(self, sample_df):
        from tools.statistics import categorical_summary
        cat = categorical_summary(sample_df)
        # Should detect 'kategori' and 'bulan' as categorical
        assert isinstance(cat, dict)

    def test_format_stats_id(self, sample_df):
        from tools.statistics import descriptive_statistics, format_stats_as_text
        stats = descriptive_statistics(sample_df)
        text = format_stats_as_text(stats, language="id")
        assert "Rata-rata" in text

    def test_format_stats_en(self, sample_df):
        from tools.statistics import descriptive_statistics, format_stats_as_text
        stats = descriptive_statistics(sample_df)
        text = format_stats_as_text(stats, language="en")
        assert "Mean" in text


# ── TestVisualization ────────────────────────────────────────────────

class TestVisualization:
    """Tests for the visualization tool."""

    def test_bar_chart(self, sample_df):
        from tools.visualization import create_bar_chart
        chart = create_bar_chart(sample_df, x="bulan", y="penjualan", title="Test Bar")
        assert "data" in chart
        assert "layout" in chart

    def test_line_chart(self, sample_df):
        from tools.visualization import create_line_chart
        chart = create_line_chart(sample_df, x="bulan", y="penjualan", title="Test Line")
        assert "data" in chart

    def test_scatter_chart(self, sample_df):
        from tools.visualization import create_scatter_chart
        chart = create_scatter_chart(
            sample_df, x="penjualan", y="profit", title="Test Scatter", trendline=None
        )
        assert "data" in chart

    def test_histogram(self, sample_df):
        from tools.visualization import create_histogram
        chart = create_histogram(sample_df, column="penjualan", title="Test Histogram")
        assert "data" in chart

    def test_correlation_heatmap(self, sample_df):
        from tools.visualization import create_correlation_heatmap
        chart = create_correlation_heatmap(sample_df, title="Test Heatmap")
        assert "data" in chart

    def test_auto_visualize(self, sample_df):
        from tools.visualization import auto_visualize
        charts = auto_visualize(sample_df, language="id")
        assert len(charts) >= 2  # Should generate multiple charts


# ── TestNarrativeGenerator ───────────────────────────────────────────

class TestNarrativeGenerator:
    """Tests for narrative_generator fixes: correlation in stats_context & validator whitelist."""

    def test_build_stats_context_includes_correlation(self):
        """_build_stats_context harus include strong_correlations di output string."""
        from tools.narrative_generator import _build_stats_context

        mock_stats = {
            "descriptive": {},
            "correlation": {
                "matrix": {},
                "strong_correlations": [
                    {
                        "col1": "Revenue",
                        "col2": "Quantity",
                        "correlation": 0.75,
                        "strength": "strong positive",
                    }
                ],
            },
        }
        ctx = _build_stats_context(mock_stats)

        assert "r=0.75" in ctx, f"Nilai r tidak ditemukan di stats_context: {ctx}"
        assert "Revenue" in ctx
        assert "Quantity" in ctx

    def test_validator_no_false_positive_indonesian_format(self):
        """100.000 (format ribuan ID) tidak boleh di-flag sebagai hallusinasi."""
        from tools.narrative_generator import NarrativeSchema, _validate_numbers_in_narrative

        mock_schema = NarrativeSchema(
            judul="Test Analisis",
            ringkasan_id="Terdapat 100.000 transaksi dalam dataset ini.",
            ringkasan_en="There are 100.000 transactions in this dataset.",
            temuan_utama=["Total transaksi mencapai 100.000 unit"],
            key_findings=["Total transactions reached 100.000 units"],
            domain_note=None,
            kesimpulan_id="Dataset cukup besar.",
            conclusion_en="The dataset is sufficiently large.",
        )
        mock_stats = {"descriptive": {}, "correlation": {}}

        _, passed, mismatched = _validate_numbers_in_narrative(mock_schema, mock_stats)

        assert "100.000" not in [str(m) for m in mismatched], (
            f"100.000 salah di-flag sebagai hallusinasi. mismatched={mismatched}"
        )
