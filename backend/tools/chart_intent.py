"""
tools/chart_intent.py
Revisi #1 — Chart ON-DEMAND gate.

Satu gerbang tunggal: apakah pesan user MEMBUTUHKAN grafik?
Dipakai oleh /analyze dan /analyze/followup untuk memutuskan apakah chart
ditempel ke laporan, supaya grafik TIDAK lagi auto-emit di tiap balasan.

Grafik hanya ditampilkan bila SALAH SATU benar:
  1. User minta grafik secara EKSPLISIT (keyword ID+EN).
  2. Intent groupby/temporal terdeteksi — memakai ULANG deteksi yang sudah ada
     di groupby_analyzer._resolve_followup_dimension (jangan bikin detektor baru).

Tidak pernah raise: exception apa pun → return False (default teks-saja = aman).
"""

import re
from typing import Optional


# ── Keyword "minta grafik" eksplisit (ID + EN) ──────────────────────────────
# Word-boundary di kedua sisi untuk hindari false-match dari substring
# (mis. "graph" TIDAK ikut "paragraph"/"graphic"; "plot" TIDAK ikut "exploit").
# "tampilkan grafik" & "show me a chart" tercakup lewat token grafik/chart.
_CHART_KEYWORD_PATTERN = re.compile(
    r"\b("
    r"grafik\w*"               # grafik, grafiknya, grafik2
    r"|visuali[sz]\w*"         # visualisasi, visualisasikan, visualize, visualization
    r"|diagram\w*"             # diagram, diagrams
    r"|bagan"                  # bagan
    r"|plot(?:kan|nya|ting)?"  # plot, plotkan, plotnya, plotting
    r"|charts?"                # chart, charts
    r"|graphs?"                # graph, graphs
    r")\b",
    re.IGNORECASE,
)


def has_explicit_chart_keyword(question: str) -> bool:
    """True bila pesan user menyebut grafik/chart/plot/diagram/… secara eksplisit."""
    try:
        return bool(_CHART_KEYWORD_PATTERN.search(question or ""))
    except Exception:
        return False


def wants_chart(
    question: str,
    df=None,
    column_profile: Optional[dict] = None,
) -> bool:
    """
    Gerbang on-demand: apakah balasan ini perlu menampilkan grafik?

    Return True bila:
      - keyword grafik eksplisit ADA, ATAU
      - intent groupby/temporal terdeteksi (pakai ulang _resolve_followup_dimension).

    `df` + `column_profile` opsional: tanpa keduanya, hanya jalur keyword eksplisit
    yang dievaluasi (intent groupby/temporal butuh kolom NYATA untuk dipetakan).

    Tidak pernah raise — exception → False (teks-saja, aman).
    """
    try:
        q = question or ""

        # (1) Permintaan eksplisit — tidak butuh data.
        if has_explicit_chart_keyword(q):
            return True

        # (2) Intent groupby/temporal — pakai ULANG resolver yang sudah ada.
        if df is not None:
            from tools.groupby_analyzer import _resolve_followup_dimension
            resolved = _resolve_followup_dimension(df, q, column_profile or {})
            if resolved is not None:
                return True

        return False
    except Exception:
        return False
