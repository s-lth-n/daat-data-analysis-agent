"""
tools/lang_detect.py
Lightweight, dependency-free language detection for user questions.

Single source of truth for choosing the OUTPUT language of a report. The result
is used by the /analyze and /analyze/followup endpoints to OVERRIDE the incoming
`language` value before it flows into narrative generation, chart labels, and the
deterministic block — so the whole response speaks ONE language consistently.

Heuristic: count Indonesian vs English stopwords/markers in the question.
  - Indonesian wins ONLY when it strictly out-scores English.
  - Default "en" otherwise — including ties, very short questions, empty input,
    and questions dominated by technical terms (per project decision (b)).
Never raises: any failure falls back to "en".
"""

import re
from typing import Set

# Distinct function words / markers per language. Kept deliberately NON-overlapping
# (no shared tokens like "data"/"total") so the score reflects real language signal.
_ID_WORDS: Set[str] = {
    "yang", "dan", "di", "ke", "dari", "untuk", "dengan", "pada", "ini", "itu",
    "atau", "per", "berapa", "jumlah", "tampilkan", "berdasarkan", "negara",
    "produk", "tertinggi", "terbanyak", "terbesar", "terlaris", "rata", "rata-rata",
    "sebutkan", "bagaimana", "mengapa", "kenapa", "apa", "siapa", "kapan", "mana",
    "tiap", "setiap", "masing-masing", "kelompok", "wilayah", "kota", "pelanggan",
    "penjualan", "pendapatan", "tahun", "bulan", "harga", "kuantitas", "banyak",
    "dominan", "distribusi", "proporsi", "sering", "tolong", "buatkan", "berikan",
    "analisis", "korelasi", "antara", "paling", "sebaran", "frekuensi", "komposisi",
}

_EN_WORDS: Set[str] = {
    "the", "and", "of", "to", "for", "with", "on", "this", "that", "or", "by",
    "how", "many", "much", "show", "country", "countries", "product", "products",
    "highest", "lowest", "most", "average", "mean", "top", "what", "which", "who",
    "when", "where", "why", "each", "per", "group", "region", "city", "customer",
    "sales", "revenue", "year", "month", "price", "quantity", "count", "number",
    "dominant", "distribution", "proportion", "frequent", "please", "give", "make",
    "analysis", "correlation", "between", "breakdown", "trend", "compare", "across",
}
# "per" appears in BOTH lists intentionally — it is neutral, so it cancels out and
# never tips the balance on its own.

_MIN_TOKENS = 3   # shorter than this → treat as ambiguous → default "en"


def detect_language(question: str) -> str:
    """
    Detect the dominant language of `question`, returning "id" or "en".

    Returns "id" only when Indonesian markers STRICTLY out-score English ones and
    the question is long enough to be confident. Everything else → "en"
    (ties, short/empty input, technical-term-heavy queries). Never raises.
    """
    try:
        if not question:
            return "en"
        tokens = re.findall(r"[a-zA-Z]+(?:-[a-zA-Z]+)?", question.lower())
        if len(tokens) < _MIN_TOKENS:
            return "en"

        id_score = sum(1 for t in tokens if t in _ID_WORDS)
        en_score = sum(1 for t in tokens if t in _EN_WORDS)

        return "id" if id_score > en_score else "en"
    except Exception:
        return "en"
