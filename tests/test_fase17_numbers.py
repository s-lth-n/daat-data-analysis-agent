"""
tests/test_fase17_numbers.py — deterministic groupby numbers + active number redaction.

A) build_deterministic_block: authoritative per-group numbers & PERCENTAGES are
   computed in Python from the real total (never written by the LLM).
B) _redact_unverified_numbers: numbers in LLM prose that are NOT verifiable against
   the data are removed ("[?]") — without guessing a replacement — while legit
   numbers (incl. ID-format thousands, years, small ints) are preserved.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pandas as pd

from tools.groupby_analyzer import build_deterministic_block
from tools.narrative_generator import _redact_unverified_numbers, _canonical_number

PROFILE = {
    "Description": "kategorik",
    "Country":     "kategorik",
    "Quantity":    "numerik_valid",
    "Price":       "numerik_valid",
    "CustomerID":  "id_kolom",
    "InvoiceDate": "datetime",
}
# Revenue per Country: UK = 10*2+5*2+8*5+1*9 = 79 ; Germany = 2*5 = 10 ; France = 4*3 = 12
# Total = 101 → UK 78.22% , France 11.88% , Germany 9.90%
DF = pd.DataFrame({
    "Description": ["WIDGET A", "WIDGET A", "GADGET B", "WIDGET A", "GADGET B", "TRINKET C"],
    "Country":     ["UK", "UK", "Germany", "France", "UK", "UK"],
    "Quantity":    [10, 5, 2, 4, 8, 1],
    "Price":       [2.0, 2.0, 5.0, 3.0, 5.0, 9.0],
    "CustomerID":  [111.0, 111.0, 222.0, 333.0, 111.0, 444.0],
    "InvoiceDate": ["2011-01-05", "2011-01-20", "2011-02-10",
                    "2011-02-15", "2011-03-01", "2011-03-22"],
})


# ── A: deterministic block — % from REAL total ───────────────────────────────

def test_deterministic_percent_from_real_total():
    block = build_deterministic_block(DF, "persen kontribusi revenue per negara", PROFILE)
    assert "Angka kunci" in block
    assert "Total Revenue = 101,00" in block          # real total, computed in Python
    # Revisi #2: rendered as a markdown table — value + % both deterministic.
    # Kolom Harga/unit deterministik (ΣRevenue/ΣQuantity): UK 79/24=3,29 ; Germany 10/2=5,00.
    assert "| UK | 79,00 | 78,22% | 3,29 | 4 |" in block
    assert "| Germany | 10,00 | 9,90% | 5,00 | 1 |" in block
    # No 10x-inflated total anywhere.
    assert "1.010,00" not in block and "1.634" not in block


def test_deterministic_block_full_and_sorted():
    """Block appears intact, sorted desc by the requested metric (revenue)."""
    block = build_deterministic_block(DF, "top produk by revenue", PROFILE)
    assert "BREAKDOWN" not in block                    # this is the USER block, not LLM ctx
    assert "Angka kunci per Description" in block
    assert block.index("GADGET B") < block.index("WIDGET A")  # 50 > 42


def test_deterministic_transactions_count_share():
    # Domain retail → unit label tetap "transaksi" (non-retail jadi "baris").
    block = build_deterministic_block(
        DF, "transaksi per negara", PROFILE, {"domain_type": "retail"}
    )
    assert "Total transaksi = 6" in block             # unit "transaksi" (head)
    assert "| UK | 4 | 66,67% |" in block             # table row, count branch


def test_deterministic_empty_for_non_groupby():
    assert build_deterministic_block(DF, "berapa rata-rata revenue?", PROFILE) == ""


# ── B: redaction of fabricated numbers ───────────────────────────────────────

def _state_with_total():
    return {
        "statistics": {
            "descriptive": {"Revenue": {"total_sum": 163401.02, "mean": 18.90}},
            # groupby block stored EN-format; redactor must match ID-format prose
            "__followup_context__":
                "BREAKDOWN PER COUNTRY (sum):\n  United Kingdom: count=45525, sum_Revenue=89,478.50",
        },
        "cleaning_report": {"original_rows": 50000, "cleaned_rows": 49876},
        "data_summary": "",
    }


def test_fabricated_10x_total_redacted():
    narr = ("Total revenue 163.401,02 sesuai data, tetapi LLM menulis "
            "total membengkak 1.634.010,02 dan mengarang 10.000 transaksi.")
    clean, n = _redact_unverified_numbers(narr, _state_with_total(), "id")
    assert n == 2
    assert "1.634.010,02" not in clean                 # fabricated 10x removed
    assert "10.000" not in clean                        # fabricated count removed
    assert "[?]" in clean
    assert "163.401,02" in clean                        # legit ID-thousands kept
    assert "tidak terverifikasi" in clean               # note appended


def test_no_redaction_when_all_numbers_valid():
    """False-positive guard: legit numbers (ID thousands, cross-format, year, small
    ints) are NOT removed and no note is appended."""
    narr = ("Total revenue 163.401,02 dari 45.525 baris (UK 89.478,50). "
            "Rata-rata 18,90 pada tahun 2011, untuk 5 negara teratas.")
    clean, n = _redact_unverified_numbers(narr, _state_with_total(), "id")
    assert n == 0
    assert clean == narr
    assert "[?]" not in clean


def test_canonical_number_cross_format():
    # ID, EN, and plain all normalise to the same float
    assert _canonical_number("163.401,02") == 163401.02
    assert _canonical_number("163,401.02") == 163401.02
    assert _canonical_number("163401.02") == 163401.02
    assert _canonical_number("1.634.010,02") == 1634010.02
    assert _canonical_number("18,90") == 18.9
