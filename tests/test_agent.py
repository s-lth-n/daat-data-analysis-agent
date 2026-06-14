"""
tests/test_agent.py
Tests for the data analysis agent — focusing on the narrative generation node.

Run from project root:
    cd ~/ta-data-analyst && pytest tests/test_agent.py -v -k narrative
"""

import json
from unittest.mock import MagicMock, patch

import pytest

# conftest.py already adds backend/ to sys.path


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_stats_result():
    """Minimal stats_result matching state['statistics'] structure."""
    return {
        "descriptive": {
            "Quantity": {
                "count": 49876,
                "mean": 10.94,
                "median": 3.0,
                "std": 21.33,
                "min": 1.0,
                "max": 80995.0,
                "q25": 2.0,
                "q75": 12.0,
                "null_count": 0,
                "null_percentage": 0.0,
            },
            "UnitPrice": {
                "count": 49876,
                "mean": 4.61,
                "median": 2.95,
                "std": 96.76,
                "min": 0.001,
                "max": 13541.33,
                "q25": 1.25,
                "q75": 4.13,
                "null_count": 0,
                "null_percentage": 0.0,
            },
        },
        "correlation": {
            "strong_correlations": [],
            "matrix": {},
        },
    }


@pytest.fixture
def sample_state(sample_stats_result):
    """Minimal AgentState dict for testing the narrative node."""
    return {
        "prompt": "Analisis data penjualan online",
        "file_id": None,
        "language": "id",
        "file_path": None,
        "dataframe_loaded": False,
        "dataframe": None,
        "data_summary": "49876 rows × 2 numeric columns",
        "column_profile": {
            "Quantity": "numerik_valid",
            "UnitPrice": "numerik_valid",
        },
        "cleaning_report": {
            "original_rows": 50000,
            "cleaned_rows": 49876,
            "rows_removed": 124,
            "rows_removed_pct": 0.25,
            "steps": [],
        },
        "domain_context": {
            "domain_type": "retail",
            "preferred_aggregation": "sum",
            "metric_note": "Dataset retail — gunakan sum untuk Revenue/Quantity.",
            "avoid": [],
        },
        "statistics": sample_stats_result,
        "charts": [],
        "narrative": None,
        "existing_chart_urls": None,
        "error": None,
        "step": "init",
    }


@pytest.fixture
def valid_schema_dict():
    """Valid NarrativeSchema payload that Ollama would return as JSON string."""
    return {
        "judul": "Analisis Data Penjualan Online",
        "ringkasan_id": (
            "Dataset memiliki 49876 transaksi dengan rata-rata kuantitas 10.94 per pesanan. "
            "Harga satuan memiliki rata-rata 4.61."
        ),
        "ringkasan_en": (
            "The dataset contains 49876 transactions with a mean quantity of 10.94 per order. "
            "Unit price averages 4.61."
        ),
        "temuan_utama": [
            "Rata-rata kuantitas per pesanan adalah 10.94 dengan median 3.0, menunjukkan skewness kanan.",
            "Harga satuan berkisar antara 0.001 hingga 13541.33 — rentang yang sangat lebar.",
            "Terdapat 49876 transaksi valid setelah pembersihan data dari total 50000 baris awal.",
        ],
        "key_findings": [
            "Mean quantity of 10.94 with median 3.0 indicates a strong right-skewed distribution.",
            "Unit price ranges from 0.001 to 13541.33, suggesting extreme high-value outliers.",
            "49876 valid transactions remain after cleaning from 50000 original rows.",
        ],
        "domain_note": "Sebagai data retail, metrik utama adalah total penjualan per produk.",
        "kesimpulan_id": (
            "Data penjualan menunjukkan variasi tinggi pada kuantitas dan harga, "
            "sehingga segmentasi lebih lanjut diperlukan."
        ),
        "conclusion_en": (
            "Sales data exhibits high variability in quantity and price, "
            "warranting further segmentation analysis."
        ),
    }


@pytest.fixture
def valid_schema_json(valid_schema_dict):
    return json.dumps(valid_schema_dict)


# ── TestBuildStatsContext ─────────────────────────────────────────────────────

class TestBuildStatsContext:
    """Unit tests for _build_stats_context helper."""

    def test_header_always_present(self, sample_stats_result):
        from tools.narrative_generator import _build_stats_context
        result = _build_stats_context(sample_stats_result)
        assert "=== STATS_CONTEXT" in result

    def test_numeric_column_mean_present(self, sample_stats_result):
        from tools.narrative_generator import _build_stats_context
        result = _build_stats_context(sample_stats_result)
        assert "[Quantity]" in result
        assert "mean=10.94" in result
        assert "median=3.0" in result
        assert "min=1.0" in result
        assert "max=80995.0" in result

    def test_second_numeric_column(self, sample_stats_result):
        from tools.narrative_generator import _build_stats_context
        result = _build_stats_context(sample_stats_result)
        assert "[UnitPrice]" in result
        assert "mean=4.61" in result

    def test_empty_dict_returns_header_only(self):
        from tools.narrative_generator import _build_stats_context
        result = _build_stats_context({})
        assert "=== STATS_CONTEXT" in result

    def test_total_rows_key(self):
        from tools.narrative_generator import _build_stats_context
        result = _build_stats_context({"total_rows": 12345})
        assert "12345 rows" in result

    def test_total_sum_included_when_present(self):
        from tools.narrative_generator import _build_stats_context
        stats = {
            "descriptive": {
                "Revenue": {
                    "count": 100, "mean": 500.0, "median": 450.0, "std": 100.0,
                    "min": 10.0, "max": 1000.0, "q25": 400.0, "q75": 600.0,
                    "null_count": 0, "null_percentage": 0.0, "total_sum": 50000.0,
                }
            }
        }
        result = _build_stats_context(stats)
        assert "total=50000.0" in result

    def test_categorical_stats_formatted(self):
        from tools.narrative_generator import _build_stats_context
        stats = {
            "categorical_stats": {
                "Country": {
                    "unique_count": 37,
                    "top_values": {"United Kingdom": 42000, "Germany": 2000},
                    "null_count": 0,
                }
            }
        }
        result = _build_stats_context(stats)
        assert "[Country]" in result
        assert "United Kingdom" in result
        assert "unique=37" in result

    def test_cleaning_report_included(self):
        from tools.narrative_generator import _build_stats_context
        stats = {
            "cleaning_report": {
                "cleaned_rows": 9800,
                "rows_removed": 200,
            }
        }
        result = _build_stats_context(stats)
        assert "9800 rows remain" in result

    def test_unknown_keys_included_verbatim(self):
        from tools.narrative_generator import _build_stats_context
        result = _build_stats_context({"custom_metric": "something useful"})
        assert "[custom_metric]" in result

    def test_numeric_stats_alias(self):
        """'numeric_stats' key should be treated the same as 'descriptive'."""
        from tools.narrative_generator import _build_stats_context
        stats = {
            "numeric_stats": {
                "Score": {
                    "count": 50, "mean": 75.5, "median": 76.0, "std": 10.0,
                    "min": 40.0, "max": 100.0, "q25": 68.0, "q75": 83.0,
                    "null_count": 0, "null_percentage": 0.0,
                }
            }
        }
        result = _build_stats_context(stats)
        assert "[Score]" in result
        assert "mean=75.5" in result


# ── TestFormatNarrativeFromSchema ─────────────────────────────────────────────

class TestFormatNarrativeFromSchema:
    """Unit tests for _format_narrative_from_schema helper."""

    def _make_schema(self, **overrides):
        from tools.narrative_generator import NarrativeSchema
        defaults = dict(
            judul="Analisis Penjualan",
            ringkasan_id="Ringkasan Bahasa Indonesia.",
            ringkasan_en="English summary.",
            temuan_utama=["Temuan 1", "Temuan 2", "Temuan 3"],
            key_findings=["Finding 1", "Finding 2", "Finding 3"],
            kesimpulan_id="Kesimpulan.",
            conclusion_en="Conclusion.",
        )
        defaults.update(overrides)
        return NarrativeSchema(**defaults)

    def test_returns_string(self):
        from tools.narrative_generator import _format_narrative_from_schema
        schema = self._make_schema()
        assert isinstance(_format_narrative_from_schema(schema), str)

    def test_title_present(self):
        from tools.narrative_generator import _format_narrative_from_schema
        schema = self._make_schema(judul="Analisis Penjualan 2024")
        result = _format_narrative_from_schema(schema)
        assert "# Analisis Penjualan 2024" in result

    def test_bilingual_sections_present(self):
        from tools.narrative_generator import _format_narrative_from_schema
        schema = self._make_schema()
        result = _format_narrative_from_schema(schema)
        assert "## Ringkasan" in result
        assert "## Summary" in result
        assert "## Temuan Utama" in result
        assert "## Key Findings" in result
        assert "## Kesimpulan" in result
        assert "## Conclusion" in result

    def test_temuan_utama_as_list_items(self):
        from tools.narrative_generator import _format_narrative_from_schema
        schema = self._make_schema(temuan_utama=["Alpha", "Beta", "Gamma"])
        result = _format_narrative_from_schema(schema)
        assert "- Alpha" in result
        assert "- Beta" in result
        assert "- Gamma" in result

    def test_domain_note_present_when_set(self):
        from tools.narrative_generator import _format_narrative_from_schema
        schema = self._make_schema(domain_note="Catatan domain spesifik.")
        result = _format_narrative_from_schema(schema)
        assert "Catatan domain spesifik." in result

    def test_domain_note_section_absent_when_none(self):
        from tools.narrative_generator import _format_narrative_from_schema
        schema = self._make_schema(domain_note=None)
        result = _format_narrative_from_schema(schema)
        assert "Catatan Domain" not in result

    def test_order_title_before_ringkasan_before_kesimpulan(self):
        from tools.narrative_generator import _format_narrative_from_schema
        schema = self._make_schema()
        result = _format_narrative_from_schema(schema)
        title_pos = result.index("# Analisis")
        ringkasan_pos = result.index("## Ringkasan")
        kesimpulan_pos = result.index("## Kesimpulan")
        assert title_pos < ringkasan_pos < kesimpulan_pos


# ── TestValidateNumbers ───────────────────────────────────────────────────────

class TestValidateNumbers:
    """Unit tests for _validate_numbers_in_narrative helper."""

    def _make_schema(self, temuan=None, findings=None):
        from tools.narrative_generator import NarrativeSchema
        return NarrativeSchema(
            judul="T",
            ringkasan_id="ID",
            ringkasan_en="EN",
            temuan_utama=temuan or ["T1"],
            key_findings=findings or ["F1"],
            kesimpulan_id="K",
            conclusion_en="C",
        )

    def test_returns_three_element_tuple(self, sample_stats_result):
        from tools.narrative_generator import _validate_numbers_in_narrative
        schema = self._make_schema()
        result = _validate_numbers_in_narrative(schema, sample_stats_result)
        assert len(result) == 3

    def test_second_element_is_bool(self, sample_stats_result):
        from tools.narrative_generator import _validate_numbers_in_narrative
        schema = self._make_schema()
        _, passed, _ = _validate_numbers_in_narrative(schema, sample_stats_result)
        assert isinstance(passed, bool)

    def test_third_element_is_list(self, sample_stats_result):
        from tools.narrative_generator import _validate_numbers_in_narrative
        schema = self._make_schema()
        _, _, mismatched = _validate_numbers_in_narrative(schema, sample_stats_result)
        assert isinstance(mismatched, list)

    def test_exact_stats_numbers_pass(self, sample_stats_result):
        from tools.narrative_generator import _validate_numbers_in_narrative
        schema = self._make_schema(
            temuan=["Rata-rata kuantitas 10.94 | median 3.0 | max 80995.0"],
            findings=["Mean 10.94, median 3.0, UnitPrice mean 4.61"],
        )
        _, passed, mismatched = _validate_numbers_in_narrative(schema, sample_stats_result)
        assert passed is True
        assert mismatched == []

    def test_hallucinated_numbers_flagged(self, sample_stats_result):
        from tools.narrative_generator import _validate_numbers_in_narrative
        schema = self._make_schema(
            temuan=["Revenue mencapai 999999999 rupiah"],
            findings=["Total sales reached 888888888"],
        )
        _, passed, mismatched = _validate_numbers_in_narrative(schema, sample_stats_result)
        assert passed is False
        assert len(mismatched) > 0

    def test_no_numbers_in_findings_passes(self, sample_stats_result):
        from tools.narrative_generator import _validate_numbers_in_narrative
        schema = self._make_schema(
            temuan=["Data menunjukkan tren positif tanpa angka"],
            findings=["Data shows a positive trend"],
        )
        _, passed, mismatched = _validate_numbers_in_narrative(schema, sample_stats_result)
        assert passed is True


# ── TestGenerateNarrativeNode ─────────────────────────────────────────────────

class TestGenerateNarrativeNode:
    """Integration tests for the generate_narrative LangGraph node."""

    def _mock_llm(self, response_content: str):
        """Return a mock ChatOllama instance whose invoke() returns response_content."""
        mock_response = MagicMock()
        mock_response.content = response_content
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        return mock_instance

    def test_narrative_is_string(self, sample_state, valid_schema_json):
        from tools.narrative_generator import generate_narrative
        with patch("tools.narrative_generator.ChatOllama") as MockLLM:
            MockLLM.return_value = self._mock_llm(valid_schema_json)
            result = generate_narrative(sample_state)
        assert isinstance(result["narrative"], str)

    def test_narrative_is_not_empty(self, sample_state, valid_schema_json):
        from tools.narrative_generator import generate_narrative
        with patch("tools.narrative_generator.ChatOllama") as MockLLM:
            MockLLM.return_value = self._mock_llm(valid_schema_json)
            result = generate_narrative(sample_state)
        assert len(result["narrative"]) > 0

    def test_narrative_contains_parsed_title(self, sample_state, valid_schema_json):
        from tools.narrative_generator import generate_narrative
        with patch("tools.narrative_generator.ChatOllama") as MockLLM:
            MockLLM.return_value = self._mock_llm(valid_schema_json)
            result = generate_narrative(sample_state)
        assert "Analisis Data Penjualan Online" in result["narrative"]

    def test_step_set_to_generate_narrative(self, sample_state, valid_schema_json):
        from tools.narrative_generator import generate_narrative
        with patch("tools.narrative_generator.ChatOllama") as MockLLM:
            MockLLM.return_value = self._mock_llm(valid_schema_json)
            result = generate_narrative(sample_state)
        assert result["step"] == "generate_narrative"

    def test_narrative_type_is_exactly_str(self, sample_state, valid_schema_json):
        """Guard: narrative must be str, not dict or NarrativeSchema object."""
        from tools.narrative_generator import generate_narrative
        with patch("tools.narrative_generator.ChatOllama") as MockLLM:
            MockLLM.return_value = self._mock_llm(valid_schema_json)
            result = generate_narrative(sample_state)
        assert type(result["narrative"]) is str

    def test_think_tags_stripped_before_parse(self, sample_state, valid_schema_json):
        """Qwen3 <think> tags must be stripped; schema still parses correctly."""
        from tools.narrative_generator import generate_narrative
        content_with_think = f"<think>Internal reasoning...</think>\n{valid_schema_json}"
        with patch("tools.narrative_generator.ChatOllama") as MockLLM:
            MockLLM.return_value = self._mock_llm(content_with_think)
            result = generate_narrative(sample_state)
        assert isinstance(result["narrative"], str)
        assert "<think>" not in result["narrative"]
        assert "Analisis Data Penjualan Online" in result["narrative"]

    def test_fallback_on_invalid_json(self, sample_state):
        """When JSON parse fails, fallback produces a string narrative."""
        from tools.narrative_generator import generate_narrative

        call_count = {"n": 0}

        def llm_factory(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return self._mock_llm("NOT VALID JSON AT ALL {{ broken")
            # Fallback call
            return self._mock_llm("Free-form narrative text from fallback LLM.")

        with patch("tools.narrative_generator.ChatOllama", side_effect=llm_factory):
            with patch("tools.narrative_generator.get_system_prompt", return_value="sys"):
                result = generate_narrative(sample_state)

        assert isinstance(result["narrative"], str)
        assert len(result["narrative"]) > 0

    def test_fallback_used_on_empty_response(self, sample_state):
        """Empty string response triggers fallback."""
        from tools.narrative_generator import generate_narrative

        call_count = {"n": 0}

        def llm_factory(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return self._mock_llm("")
            return self._mock_llm("Fallback narrative output.")

        with patch("tools.narrative_generator.ChatOllama", side_effect=llm_factory):
            with patch("tools.narrative_generator.get_system_prompt", return_value="sys"):
                result = generate_narrative(sample_state)

        assert isinstance(result["narrative"], str)

    def test_no_statistics_state(self):
        """Node must not crash when state['statistics'] is None."""
        from tools.narrative_generator import generate_narrative

        state = {
            "prompt": "Analisis data",
            "language": "id",
            "statistics": None,
            "data_summary": None,
            "cleaning_report": None,
            "domain_context": None,
            "charts": [],
            "existing_chart_urls": None,
            "step": "init",
        }
        schema_json = json.dumps({
            "judul": "Analisis",
            "ringkasan_id": "Tidak ada data statistik.",
            "ringkasan_en": "No statistics available.",
            "temuan_utama": ["Tidak ada data numerik yang tersedia"],
            "key_findings": ["No numeric data available"],
            "domain_note": None,
            "kesimpulan_id": "Tidak dapat membuat analisis tanpa data.",
            "conclusion_en": "Cannot generate analysis without data.",
        })
        with patch("tools.narrative_generator.ChatOllama") as MockLLM:
            MockLLM.return_value = self._mock_llm(schema_json)
            result = generate_narrative(state)
        assert isinstance(result["narrative"], str)

    def test_english_language(self, valid_schema_json):
        """Node works correctly with language='en'."""
        from tools.narrative_generator import generate_narrative

        state = {
            "prompt": "Analyze sales data",
            "language": "en",
            "statistics": {"descriptive": {}, "correlation": {}},
            "data_summary": "100 rows × 2 columns",
            "cleaning_report": None,
            "domain_context": None,
            "charts": [],
            "existing_chart_urls": None,
            "step": "init",
        }
        with patch("tools.narrative_generator.ChatOllama") as MockLLM:
            MockLLM.return_value = self._mock_llm(valid_schema_json)
            result = generate_narrative(state)
        assert isinstance(result["narrative"], str)

    def test_original_state_not_mutated(self, sample_state, valid_schema_json):
        """generate_narrative must not mutate the input state dict."""
        from tools.narrative_generator import generate_narrative
        original_narrative = sample_state.get("narrative")
        original_step = sample_state["step"]
        with patch("tools.narrative_generator.ChatOllama") as MockLLM:
            MockLLM.return_value = self._mock_llm(valid_schema_json)
            generate_narrative(sample_state)
        assert sample_state.get("narrative") == original_narrative
        assert sample_state["step"] == original_step

    def test_existing_chart_urls_injected(self, sample_state, valid_schema_json):
        """When existing_chart_urls is set, node still produces a narrative string."""
        from tools.narrative_generator import generate_narrative
        state = dict(sample_state)
        state["existing_chart_urls"] = ["http://localhost/charts/chart1.png"]
        with patch("tools.narrative_generator.ChatOllama") as MockLLM:
            MockLLM.return_value = self._mock_llm(valid_schema_json)
            result = generate_narrative(state)
        assert isinstance(result["narrative"], str)

    def test_strong_correlations_injected(self, sample_state, valid_schema_json):
        """Strong correlations in statistics are surfaced without error."""
        from tools.narrative_generator import generate_narrative
        state = dict(sample_state)
        state["statistics"] = {
            "descriptive": sample_state["statistics"]["descriptive"],
            "correlation": {
                "strong_correlations": [
                    {"col1": "Quantity", "col2": "UnitPrice",
                     "correlation": -0.74, "strength": "strong negative"}
                ],
                "matrix": {},
            },
        }
        with patch("tools.narrative_generator.ChatOllama") as MockLLM:
            MockLLM.return_value = self._mock_llm(valid_schema_json)
            result = generate_narrative(state)
        assert isinstance(result["narrative"], str)
