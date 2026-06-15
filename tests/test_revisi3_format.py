"""
Revisi #3 — format angka ikut bahasa laporan.
build_deterministic_block: en → 1,058,314.21 / 2.08% ; id → 1.058.314,21 / 2,08%.
Nilai TIDAK berubah — hanya representasi string. Anti-halusinasi (redactor) WAJIB
tetap mengenali KEDUA gaya: angka sah tak diredaksi, angka palsu tetap [?].
"""

import pandas as pd
import pytest

from tools.groupby_analyzer import (
    _fmt_num, _fmt_intnum, _fmt_id, _fmt_int, build_deterministic_block,
)
from tools.narrative_generator import _redact_unverified_numbers, _canonical_number


# ── A: dispatcher locale-aware ──────────────────────────────────────────────

def test_fmt_num_locale():
    assert _fmt_num(1058314.21, "en") == "1,058,314.21"
    assert _fmt_num(1058314.21, "id") == "1.058.314,21"
    assert _fmt_num(2.08, "en") == "2.08"
    assert _fmt_num(2.08, "id") == "2,08"


def test_fmt_intnum_locale():
    assert _fmt_intnum(48708, "en") == "48,708"
    assert _fmt_intnum(48708, "id") == "48.708"


def test_fmt_default_id_byte_compat():
    """Tanpa language → gaya ID (perilaku lama, byte-compat existing tests)."""
    assert _fmt_num(1058314.21) == _fmt_id(1058314.21) == "1.058.314,21"
    assert _fmt_intnum(48708) == _fmt_int(48708) == "48.708"


def test_fmt_fallback_no_crash():
    """Input non-numerik → tak raise (fallback str)."""
    assert isinstance(_fmt_num("xx", "en"), str)
    assert isinstance(_fmt_intnum(None, "en"), str)


# ── B: blok deterministik EN vs ID ──────────────────────────────────────────

PROFILE = {"Description": "kategorik", "Quantity": "numerik_valid",
           "Price": "numerik_valid", "InvoiceDate": "datetime"}
# Revenue: A=1000*2+500*2=3000 ; B=2000*3=6000 ; Total=9000 (uji pemisah ribuan).
DF_K = pd.DataFrame({
    "Description": ["A", "A", "B"],
    "Quantity":    [1000, 500, 2000],
    "Price":       [2.0, 2.0, 3.0],
})
PROFILE_K = {"Description": "kategorik", "Quantity": "numerik_valid", "Price": "numerik_valid"}
RETAIL = {"domain_type": "retail", "preferred_aggregation": "sum"}


def test_block_en_number_format():
    block = build_deterministic_block(DF_K, "produk terlaris", PROFILE_K, RETAIL, "en")
    assert "Total Revenue = 9,000.00 from 3 rows" in block   # koma ribuan, titik desimal
    assert "6,000.00" in block                                # nilai grup tertinggi (B)
    # Persen EN pakai titik desimal: B = 6000/9000 = 66.67%
    assert "66.67%" in block
    assert "9.000,00" not in block                            # tak ada gaya ID bocor


def test_block_id_number_format():
    block = build_deterministic_block(DF_K, "produk terlaris", PROFILE_K, RETAIL, "id")
    assert "Total Revenue = 9.000,00 dari 3 baris" in block   # titik ribuan, koma desimal
    assert "6.000,00" in block
    assert "66,67%" in block                                  # persen ID pakai koma
    assert "9,000.00" not in block


def test_block_values_identical_across_languages():
    """Nilai (bukan format) sama: EN & ID merepresentasikan angka yang sama."""
    en = build_deterministic_block(DF_K, "produk terlaris", PROFILE_K, RETAIL, "en")
    id_ = build_deterministic_block(DF_K, "produk terlaris", PROFILE_K, RETAIL, "id")
    # Kanonikalisasi total di kedua blok → float identik.
    assert _canonical_number("9,000.00") == _canonical_number("9.000,00") == 9000.0
    assert ("9,000.00" in en) and ("9.000,00" in id_)


# ── C: tahun TIDAK diberi pemisah ribuan (group label apa adanya) ───────────

DF_T = pd.DataFrame({
    "Description": ["A", "A", "B", "C", "B", "A"],
    "Quantity":    [10, 5, 2, 4, 8, 1],
    "Price":       [2.0, 2.0, 5.0, 3.0, 5.0, 9.0],
    "InvoiceDate": ["2011-01-05", "2011-01-20", "2011-02-10",
                    "2011-02-15", "2011-03-01", "2011-03-22"],
})


@pytest.mark.parametrize("lang", ["en", "id"])
def test_year_period_not_mangled(lang):
    block = build_deterministic_block(DF_T, "tren penjualan per bulan", PROFILE, RETAIL, lang)
    assert "2011-01" in block and "2011-03" in block   # periode YYYY-MM apa adanya
    assert "2,011" not in block and "2.011" not in block   # tahun TANPA pemisah ribuan


# ── D: REGRESI redactor — wajib di KEDUA gaya ───────────────────────────────

def _state():
    return {
        "statistics": {
            "descriptive": {"Revenue": {"total_sum": 163401.02, "mean": 18.90}},
            "__followup_context__":
                "BREAKDOWN PER COUNTRY (sum):\n  United Kingdom: count=45525, sum_Revenue=89,478.50",
        },
        "cleaning_report": {"original_rows": 50000, "cleaned_rows": 49876},
        "data_summary": "",
    }


def test_redactor_en_valid_numbers_not_redacted():
    """Angka SAH gaya EN (cross-format dgn sumber) TIDAK diredaksi."""
    narr = ("Total revenue 163,401.02 from 45,525 rows (UK 89,478.50). "
            "Average 18.90 in year 2011 across top 5 countries.")
    clean, n = _redact_unverified_numbers(narr, _state(), "en")
    assert n == 0
    assert clean == narr
    assert "[?]" not in clean


def test_redactor_en_fake_numbers_redacted():
    """Angka PALSU gaya EN tetap diganti [?]; angka sah tetap utuh."""
    narr = ("Real total is 163,401.02 but the model inflated it to 1,634,010.02 "
            "and invented 10,000 transactions.")
    clean, n = _redact_unverified_numbers(narr, _state(), "en")
    assert n == 2
    assert "1,634,010.02" not in clean      # fabricated 10x removed
    assert "10,000" not in clean            # fabricated count removed
    assert "163,401.02" in clean            # legit EN-thousands kept
    assert "[?]" in clean


def test_redactor_id_still_works():
    """Regresi: gaya ID tetap berfungsi seperti sebelum perubahan format."""
    narr = "Total 163.401,02 valid, tapi 1.634.010,02 dikarang."
    clean, n = _redact_unverified_numbers(narr, _state(), "id")
    assert n == 1
    assert "163.401,02" in clean and "1.634.010,02" not in clean
