"""
test_diagnosa5_commitB.py — Diagnosa #5, Commit B.

Label (BUKAN suppress) Σ untuk kolom harga satuan di STATS_CONTEXT. Tujuan: cegah
LLM menyebut Σ Price (mis. 163.401) sebagai "total penjualan". Angka total= tetap
ada; hanya ditambah penanda yang mengarahkan interpretasi ke Revenue (blok BREAKDOWN).

Memverifikasi:
  1. Kolom price-like (Price/harga/UnitPrice) dengan total_sum → baris konteks
     mengandung penanda "NOT a sales total".
  2. Angka total Price TIDAK dibuang (label, bukan suppress).
  3. Kolom non-price (Quantity/Revenue) TIDAK kena label.
  4. Tanpa total_sum (domain non-sum) → tak ada penanda (tak ada Σ menyesatkan).
  5. Helper _is_price_like konsisten dgn substring price/harga/unitprice.
  6. Berlaku untuk konteks /analyze maupun followup (fungsi yang sama).
"""

import pytest

from tools.narrative_generator import _build_stats_context, _is_price_like


# ── 5. Helper deteksi price-like ──────────────────────────────────────────────

@pytest.mark.parametrize("col", ["Price", "price", "UnitPrice", "unitprice",
                                  "Harga", "harga_satuan", "Unit Price"])
def test_is_price_like_true(col):
    assert _is_price_like(col) is True


@pytest.mark.parametrize("col", ["Quantity", "Revenue", "Total", "Country",
                                  "Description", "Amount"])
def test_is_price_like_false(col):
    assert _is_price_like(col) is False


# ── 1 & 2. Label muncul, angka total dipertahankan ───────────────────────────

def _stats_retail():
    return {
        "descriptive": {
            "Price":    {"total_sum": 163401.02, "mean": 18.90, "max": 10468.8},
            "Quantity": {"total_sum": 648922.0, "mean": 12.5},
        }
    }


def test_price_line_has_not_a_sales_total_label():
    sc = _build_stats_context(_stats_retail())
    price_line = next(l for l in sc.splitlines() if l.startswith("[Price]"))
    assert "NOT a sales total" in price_line
    assert "Revenue in the BREAKDOWN block" in price_line


def test_price_total_value_retained_not_suppressed():
    sc = _build_stats_context(_stats_retail())
    price_line = next(l for l in sc.splitlines() if l.startswith("[Price]"))
    assert "total=163401.02" in price_line   # angka total= TETAP ada (bukan dibuang)
    assert "mean=18.9" in price_line


# ── 3. Kolom non-price tidak kena label ───────────────────────────────────────

def test_non_price_column_not_labeled():
    sc = _build_stats_context(_stats_retail())
    qty_line = next(l for l in sc.splitlines() if l.startswith("[Quantity]"))
    assert "NOT a sales total" not in qty_line
    assert "total=648922.0" in qty_line


# ── 4. Tanpa total_sum → tak ada penanda ──────────────────────────────────────

def test_price_without_total_sum_has_no_label():
    # Domain non-sum (mis. preferred_aggregation=mean) → Price tak punya total_sum.
    sc = _build_stats_context({
        "descriptive": {"Price": {"mean": 18.90, "max": 10468.8, "count": 100}}
    })
    price_line = next(l for l in sc.splitlines() if l.startswith("[Price]"))
    assert "NOT a sales total" not in price_line   # tak ada Σ menyesatkan → tak perlu label
    assert "total=" not in price_line


# ── 6. Seragam lintas endpoint (fungsi yang sama dipakai keduanya) ────────────

def test_label_applies_with_followup_context_present():
    """followup juga punya total_sum Price → label tetap muncul (perbaikan seragam)."""
    stats = _stats_retail()
    stats["__followup_context__"] = "BREAKDOWN PER COUNTRY (sum):\n  UK: count=10, sum_Revenue=89,478.50"
    sc = _build_stats_context(stats)
    price_line = next(l for l in sc.splitlines() if l.startswith("[Price]"))
    assert "NOT a sales total" in price_line
    # breakdown tetap ikut terbangun (tak terganggu label).
    assert "BREAKDOWN PER COUNTRY" in sc
