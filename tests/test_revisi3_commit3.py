"""
Revisi #3 — Commit 3 tests.
/analyze chart on-demand: 1 chart RELEVAN (bukan 3 overview), 0 bila tak perlu,
fallback overview cache untuk "minta grafik eksplisit tanpa intent".

Dua lapis:
  A) unit — building block pemilihan chart (wants_chart + build_followup_chart_spec),
  B) endpoint — POST /analyze (run_analysis_agent & _render_charts_to_png di-mock)
     membuktikan jumlah chart yang DIEMISI: 3 → 1.
"""

import base64
import numpy as np
import pandas as pd
import pytest

import main
from tools.chart_intent import wants_chart
from tools.groupby_analyzer import build_followup_chart_spec, build_deterministic_block


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


def _arr(v):
    if isinstance(v, dict) and "bdata" in v:
        raw = base64.b64decode(v["bdata"])
        dt = {"f8": "<f8", "i8": "<i8"}.get(v.get("dtype", "f8"), "<f8")
        return np.frombuffer(raw, dtype=dt).tolist()
    return list(v)


# ── A: building blocks ──────────────────────────────────────────────────────

def test_terlaris_builds_single_relevant_bar():
    """'produk terlaris' retail → SATU bar Revenue per produk; angka cocok tabel."""
    spec = build_followup_chart_spec(DF, "produk terlaris", PROFILE, RETAIL, "id")
    assert spec is not None
    assert len(spec["data"]) == 1 and spec["data"][0]["type"] == "bar"
    xs = [float(v) for v in _arr(spec["data"][0]["x"])]
    assert max(xs) == pytest.approx(50.0, abs=0.01)        # B = 10+40 = 50 (Revenue)
    assert "50,00" in build_deterministic_block(DF, "produk terlaris", PROFILE, RETAIL, "id")


def test_temporal_builds_single_line():
    """'tren penjualan per bulan' → SATU line chart (trace scatter)."""
    spec = build_followup_chart_spec(DF, "tren penjualan per bulan", PROFILE, RETAIL, "id")
    assert spec is not None
    assert spec["data"][0]["type"] == "scatter"


def test_plain_question_no_chart_gate():
    """'berapa baris dalam dataset ini' → wants_chart False → 0 chart."""
    assert wants_chart("berapa baris dalam dataset ini", df=DF, column_profile=PROFILE) is False


def test_explicit_chart_without_intent_spec_none():
    """'buatkan grafik penjualan' → wants_chart True TAPI spec None → caller pakai cache."""
    assert wants_chart("buatkan grafik penjualan", df=DF, column_profile=PROFILE) is True
    assert build_followup_chart_spec(DF, "buatkan grafik penjualan", PROFILE, RETAIL, "id") is None


# ── B: endpoint — jumlah chart yang DIEMISI (3 overview → 1 relevan) ─────────

@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import agents.data_agent as data_agent

    # File dummy supaya glob {file_id}_* ketemu (run_analysis_agent di-mock → isi tak dibaca).
    main.settings.upload_dir.mkdir(parents=True, exist_ok=True)
    f = main.settings.upload_dir / "testfile_data.csv"
    f.write_text("dummy")

    # 3 spec overview (cache). Isi tak penting — _render_charts_to_png di-mock.
    overview = [{"data": [{"type": "bar"}], "layout": {}} for _ in range(3)]

    async def fake_agent(prompt, file_id=None, language="id"):
        return {
            "text": "narasi prosa.",
            "charts": overview,
            "statistics": {"descriptive": {}},
            "dataframe": DF,
            "column_profile": PROFILE,
            "cleaning_report": {},
            "domain_context": RETAIL,
            "language": language,
        }

    # Mock render: 1 key per spec, ditandai jumlah input → bedakan overview(3) vs relevan(1).
    def fake_render(specs):
        return [f"key_{len(specs)}_{i}" for i in range(len(specs))]

    monkeypatch.setattr(data_agent, "run_analysis_agent", fake_agent)
    monkeypatch.setattr(main, "_render_charts_to_png", fake_render)

    try:
        yield TestClient(main.app)      # tanpa context-manager → lifespan tak dijalankan
    finally:
        f.unlink(missing_ok=True)


def _post(client, prompt):
    r = client.post("/analyze", json={"file_id": "testfile", "prompt": prompt, "language": "id"})
    assert r.status_code == 200, r.text
    return r.json()


def test_endpoint_terlaris_emits_exactly_one_relevant_chart(client):
    data = _post(client, "produk terlaris")
    # SESUDAH: tepat 1 chart relevan (relevan render dipanggil dgn 1 spec → key_1_*).
    assert data["chart_keys"] == ["key_1_0"]
    assert len(data["chart_keys"]) == 1
    # Bukan 3 overview cache (yang berakhiran _3_).
    assert all("_3_" not in k for k in data["chart_keys"])
    # charts field koheren: 1 bar relevan.
    assert data["charts"] is not None and len(data["charts"]) == 1
    assert data["charts"][0]["data"][0]["type"] == "bar"
    # Blok deterministik memimpin teks (Revenue, bukan Σ Price).
    assert "Total Revenue" in data["text"]


def test_endpoint_explicit_chart_no_intent_falls_back_to_3_cache(client):
    data = _post(client, "buatkan grafik penjualan")
    # spec relevan None → fallback overview cache (3 key berakhiran _3_).
    assert len(data["chart_keys"]) == 3
    assert all("_3_" in k for k in data["chart_keys"])


def test_endpoint_plain_question_emits_zero_charts(client):
    data = _post(client, "berapa baris dalam dataset ini")
    assert data["chart_keys"] is None
    assert data["charts"] is None
    # Teks tetap ada (narasi), tidak kosong.
    assert data["text"]
