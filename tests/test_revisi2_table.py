"""
tests/test_revisi2_table.py — Revisi #2, COMMIT 3 (Bagian A).

build_deterministic_block now renders a MARKDOWN TABLE from the already-computed
Python numbers (gsum/gmean/gcount/total/pct). Pure Python, no LLM:
  - one table row per group (capped at 15),
  - the metric cell equals _fmt_id(gsum) / the count cell equals _fmt_int(gcount),
  - column headers respect `language` (ID/EN),
  - if the table formatter raises, it falls back to the OLD numbered list.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pandas as pd
import pytest

from tools.groupby_analyzer import build_deterministic_block

PROFILE = {
    "Description": "kategorik",
    "Country":     "kategorik",
    "Quantity":    "numerik_valid",
    "Price":       "numerik_valid",
    "CustomerID":  "id_kolom",
    "InvoiceDate": "datetime",
}
# Revenue per Country: UK=79, France=12, Germany=10 (total 101).
DF = pd.DataFrame({
    "Description": ["WIDGET A", "WIDGET A", "GADGET B", "WIDGET A", "GADGET B", "TRINKET C"],
    "Country":     ["UK", "UK", "Germany", "France", "UK", "UK"],
    "Quantity":    [10, 5, 2, 4, 8, 1],
    "Price":       [2.0, 2.0, 5.0, 3.0, 5.0, 9.0],
    "CustomerID":  [111.0, 111.0, 222.0, 333.0, 111.0, 444.0],
    "InvoiceDate": ["2011-01-05", "2011-01-20", "2011-02-10",
                    "2011-02-15", "2011-03-01", "2011-03-22"],
})


def _table_rows(block: str) -> list:
    """Return data rows of the markdown table (skip header + separator lines)."""
    body_lines = [ln for ln in block.splitlines() if ln.strip().startswith("|")]
    # body_lines[0] = header, body_lines[1] = separator (---), rest = data rows
    return body_lines[2:]


# ── metric branch (revenue per country) ──────────────────────────────────────

def test_metric_block_is_markdown_table():
    block = build_deterministic_block(DF, "revenue per negara", PROFILE)
    # Kolom Harga/unit deterministik (ΣRevenue/ΣQuantity) muncul karena DF punya Qty×Price.
    assert "| Country | Revenue | % | Harga/unit | n |" in block   # ID default headers
    assert "| --- | --- | --- | --- | --- |" in block


def test_metric_one_row_per_group():
    block = build_deterministic_block(DF, "revenue per negara", PROFILE)
    # 3 countries → 3 data rows.
    assert len(_table_rows(block)) == 3


def test_metric_cells_match_gsum():
    block = build_deterministic_block(DF, "revenue per negara", PROFILE)
    # Harga/unit = ΣRevenue/ΣQuantity: UK 79/24=3,29 ; France 12/4=3,00 ; Germany 10/2=5,00.
    assert "| UK | 79,00 | 78,22% | 3,29 | 4 |" in block
    assert "| France | 12,00 | 11,88% | 3,00 | 1 |" in block
    assert "| Germany | 10,00 | 9,90% | 5,00 | 1 |" in block


def test_metric_mean_intent_adds_mean_column():
    block = build_deterministic_block(DF, "rata-rata revenue per negara", PROFILE)
    assert "| Country | Revenue | % | Harga/unit | Rata-rata | n |" in block


def test_english_headers():
    block = build_deterministic_block(DF, "revenue per country", PROFILE, None, "en")
    assert "| Country | Revenue | % | Price/unit | n |" in block
    assert "Key figures per Country" in block             # head in EN
    assert "from 6 rows" in block


# ── count branch (distribution per group) ────────────────────────────────────

def test_count_branch_table_and_rows():
    block = build_deterministic_block(DF, "distribusi negara", PROFILE)
    assert "| Country | Jumlah | % |" in block            # ID count header
    assert len(_table_rows(block)) == 3                    # UK, France, Germany
    assert "| UK | 4 | 66,67% |" in block                  # count cell == gcount


def test_count_branch_english_header():
    block = build_deterministic_block(DF, "distribution per country", PROFILE, None, "en")
    assert "| Country | Count | % |" in block


# ── fallback to numbered list when the table formatter fails ─────────────────

def test_fallback_to_numbered_list_on_table_error(monkeypatch):
    """If _format_groups_as_table raises, build_deterministic_block must fall back
    to the ORIGINAL numbered-list format (never crash, never empty)."""
    import tools.groupby_analyzer as gb

    def boom(*a, **k):
        raise RuntimeError("forced table failure")

    monkeypatch.setattr(gb, "_format_groups_as_table", boom)
    block = gb.build_deterministic_block(DF, "revenue per negara", PROFILE)
    # Numbered-list markers present; no table pipes. Harga/unit deterministik (79/24=3,29)
    # ikut di fallback list — sumber angka per-unit yang SAMA dengan tabel.
    assert "1. UK — 79,00 (78,22%); harga/unit 3,29; n=4" in block
    assert "|" not in block
    assert "Angka kunci per Country" in block              # head still intact


def test_table_numbers_have_no_inflation():
    block = build_deterministic_block(DF, "revenue per negara", PROFILE)
    assert "Total Revenue = 101,00" in block
    assert "1.010,00" not in block and "1.634" not in block
