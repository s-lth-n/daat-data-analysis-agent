"""
Revisi #3 — Commit 4 tests (penutup butir #3).
Presentasi /analyze konsisten dgn followup: **judul** TURUN di bawah blok
deterministik (sub-judul, bukan header puncak), output SINGLE-LANGUAGE
(banner "baris"/"rows" ikut bahasa), tanpa heading formal.

Renderer narasi / schema TIDAK disentuh — murni urutan perakitan + bahasa banner.
"""

import pandas as pd
import pytest

import main
from main import _assemble_analysis_response

RETAIL = {"domain_type": "retail", "preferred_aggregation": "sum"}
PROFILE = {
    "Description": "kategorik", "Country": "kategorik",
    "Quantity": "numerik_valid", "Price": "numerik_valid",
    "InvoiceDate": "datetime",
}
DF = pd.DataFrame({
    "Description": ["A", "A", "B", "C", "B", "A"],
    "Country":     ["UK", "UK", "Germany", "France", "UK", "UK"],
    "Quantity":    [10, 5, 2, 4, 8, 1],
    "Price":       [2.0, 2.0, 5.0, 3.0, 5.0, 9.0],
    "InvoiceDate": ["2011-01-05", "2011-01-20", "2011-02-10",
                    "2011-02-15", "2011-03-01", "2011-03-22"],
})

_FORMAL_HEADINGS = [
    "## Ringkasan", "## Summary", "## Temuan", "## Key Findings",
    "## Kesimpulan", "## Conclusion",
]


# ── A: helper-level ─────────────────────────────────────────────────────────

def test_helper_block_precedes_narrative_judul():
    """Blok deterministik muncul SEBELUM **judul** narasi (urutan = followup)."""
    out = _assemble_analysis_response(
        file_name="f.csv", row_count=10, narrative="**Judul Narasi**\n\nprosa.",
        session_id="s", deterministic_block="BLOK_DETERMINISTIK", language="id",
    )
    assert out.index("BLOK_DETERMINISTIK") < out.index("**Judul Narasi**")


def test_helper_banner_language_aware():
    """Banner 'baris' (id) vs 'rows' (en); default id byte-compat."""
    id_out = _assemble_analysis_response(
        file_name="f.csv", row_count=7, narrative="N", session_id="s", language="id")
    en_out = _assemble_analysis_response(
        file_name="f.csv", row_count=7, narrative="N", session_id="s", language="en")
    assert id_out.startswith("📄 **f.csv** — 7 baris")
    assert en_out.startswith("📄 **f.csv** — 7 rows")
    # default (tanpa language) tetap "baris" → byte-compat dgn Commit 1.
    assert _assemble_analysis_response(
        file_name="f.csv", row_count=7, narrative="N", session_id="s"
    ).startswith("📄 **f.csv** — 7 baris")


# ── B: endpoint-level ───────────────────────────────────────────────────────

@pytest.fixture
def analyze(monkeypatch):
    from fastapi.testclient import TestClient
    import agents.data_agent as data_agent

    cfg = {"narrative": "**Judul**\n\nprosa."}
    main.settings.upload_dir.mkdir(parents=True, exist_ok=True)
    f = main.settings.upload_dir / "c4file_data.csv"
    f.write_text("dummy")

    async def fake_agent(prompt, file_id=None, language="id"):
        return {
            "text": cfg["narrative"], "charts": [], "statistics": {"descriptive": {}},
            "dataframe": DF, "column_profile": PROFILE, "cleaning_report": {},
            "domain_context": RETAIL, "language": language,
        }

    monkeypatch.setattr(data_agent, "run_analysis_agent", fake_agent)
    monkeypatch.setattr(main, "_render_charts_to_png",
                        lambda specs: [f"k{i}" for i in range(len(specs))])
    client = TestClient(main.app)

    def _run(prompt, narrative=None):
        if narrative is not None:
            cfg["narrative"] = narrative
        r = client.post("/analyze",
                        json={"file_id": "c4file", "prompt": prompt, "language": "id"})
        assert r.status_code == 200, r.text
        return r.json()

    try:
        yield _run
    finally:
        f.unlink(missing_ok=True)


def test_endpoint_block_before_judul(analyze):
    """/analyze 'produk terlaris' (id): blok deterministik SEBELUM **judul** narasi."""
    data = analyze("tampilkan produk terlaris berdasarkan penjualan",
                   narrative="**JUDUL_NARASI**\n\nprosa analisis.")
    t = data["text"]
    assert "Total Revenue" in t                       # blok deterministik (Revenue)
    assert t.index("Total Revenue") < t.index("**JUDUL_NARASI**")
    # **judul** bukan elemen paling atas — banner + blok mendahuluinya.
    assert not t.lstrip().startswith("**JUDUL_NARASI**")


def test_endpoint_no_formal_headings(analyze):
    data = analyze("tampilkan produk terlaris berdasarkan penjualan",
                   narrative="**Judul**\n\nprosa.")
    for h in _FORMAL_HEADINGS:
        assert h not in data["text"], h


def test_endpoint_id_single_language_banner(analyze):
    data = analyze("tampilkan produk terlaris berdasarkan penjualan",
                   narrative="**Judul**\n\nprosa.")
    assert data["language"] == "id"
    banner = data["text"].splitlines()[0]
    assert "baris" in banner and "rows" not in banner
    assert "rows" not in data["text"]                 # tak ada bocor EN di mana pun


def test_endpoint_en_single_language_banner(analyze):
    data = analyze("show me the best selling products by revenue",
                   narrative="**Top Products**\n\nprose.")
    assert data["language"] == "en"
    banner = data["text"].splitlines()[0]
    assert "rows" in banner and "baris" not in banner
    assert "baris" not in data["text"]                # tak ada bocor ID di mana pun
    assert "Total Revenue" in data["text"]            # blok EN tetap memimpin angka


def test_endpoint_fallback_non_groupby_clean(analyze):
    """'ringkas data ini' (non-groupby) → tanpa blok, single-language, tanpa ## heading."""
    data = analyze("ringkas data ini", narrative="**Ringkasan Singkat**\n\nprosa.")
    t = data["text"]
    assert data["language"] == "id"
    assert "Total Revenue" not in t                   # blok deterministik kosong
    assert t.splitlines()[0].endswith("baris")        # banner single-language
    for h in _FORMAL_HEADINGS:
        assert h not in t, h
    assert "prosa." in t                              # narasi tetap ada (tidak kosong)
