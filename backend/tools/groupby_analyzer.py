"""
tools/groupby_analyzer.py
Improve #5 — Targeted re-computation on follow-up queries.
Mendeteksi intent GROUP BY dari pertanyaan follow-up dan menjalankan
groupby computation pada DataFrame yang di-cache di session.
"""

import re
import pandas as pd
from typing import Optional


# ── Keyword triggers untuk GROUP BY intent ──────────────────────────────────
_GROUPBY_KEYWORDS = [
    r'\bper\b',           # "per negara", "per kategori"
    r'\bberdasarkan\b',   # "berdasarkan kota"
    r'\btiap\b',          # "tiap bulan"
    r'\bsetiap\b',        # "setiap produk"
    r'\bmasing-masing\b', # "masing-masing wilayah"
    r'\bbreakdown\b',     # "breakdown by country"
    r'\bby\b',            # "group by country"
    r'\bkelompok\b',      # "kelompok negara"
    # Ranking ID/EN (Fase 1.6): "top 10 produk", "produk terlaris", "negara terbanyak".
    # Hanya jadi pintu masuk; dimensi tetap di-resolve via sinonim → kolom NYATA,
    # jadi "top 10" tanpa dimensi yang cocok tetap jatuh ke backstop.
    r'\btop\b',
    r'\bterlaris\b',
    r'\bterbanyak\b',
    r'\bterbesar\b',
    r'\btertinggi\b',
    # Ranking penjualan (Revisi #3, Commit 2): "produk terbaik", "best-selling",
    # "paling laris". Membuka gerbang groupby/ranking agar dimensi ter-resolve →
    # baru _select_front_metrics bisa menerapkan Revenue-default retail. Selaras
    # dengan _SALES_RANK_INTENT. "best" menangkup "best-selling"/"best seller".
    r'\bterbaik\b',
    r'\bbest\b',
    r'\blaris\b',
    # Distribusi/frekuensi kategorik ID↔EN (Fase 1.8): "topik dominan", "sumber
    # yang paling sering", "distribusi/proporsi per kategori". Sama seperti ranking:
    # cuma PINTU MASUK — dimensi tetap di-resolve via sinonim → kolom NYATA, dan
    # intent distribusi murni dipaksa ke cabang COUNT+PROPORSI (lihat _DISTRIB_INTENT).
    r'\bdominan\b',
    r'\bdominasi\b',
    r'\bsering\b',        # menangkup "paling sering"
    r'\bdistribusi\b',
    r'\bproporsi\b',
    # Superlatif "paling banyak" (Fase 1.8.1): "topik mana yang paling banyak jumlah
    # barisnya". SENGAJA frasa dua-kata, BUKAN bare \bbanyak\b — "banyak" tunggal ada
    # di pertanyaan count biasa ("berapa banyak baris") yang TANPA dimensi grup, jadi
    # bare-match akan over-trigger. ("terbanyak" sudah ditangani di atas.) Begitu gate
    # ini terbuka, "banyak" memicu count_requested via _METRIC_COUNT → cabang COUNT+%.
    r'\bpaling\s+banyak\b',
]

_KEYWORD_PATTERN = re.compile(
    '|'.join(_GROUPBY_KEYWORDS), re.IGNORECASE
)


def _singularize(word: str) -> str:
    """Naive English singularizer so 'countries'/'products' match 'Country'/'Product'."""
    w = word.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"          # countries -> country, categories -> category
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]                # products -> product, orders -> order
    return w


# ── Sinonim dimensi ID↔EN → kolom NYATA via PERAN kolom (Fase 1.6) ──────────
# Memetakan istilah umum (Indonesia & English) ke kolom dimensi yang BENAR-BENAR
# ADA, dicocokkan lewat SUBSTRING NAMA kolom + guard PERAN (group dim = kategorik;
# temporal = datetime). Kalau tak ada kolom yang namanya berkaitan → TIDAK match
# (biar jatuh ke backstop jujur), supaya tak salah-petakan ke kolom acak.
#
# KEPUTUSAN USER (Fase 1.6): paritas ID↔EN penuh — TERMASUK negara→Country, yang
# di Fase 1.5 sengaja TIDAK dipetakan. Ini membalik keputusan Fase 1.5.
#
# Tiap entri: (regex_trigger_query, tuple_substring_nama_kolom_target).
_GROUP_SYNONYMS = [
    (re.compile(r"\b(negara|country|countries|nation|nations)\b", re.IGNORECASE),
     ("country", "negara", "nation")),
    (re.compile(r"\b(wilayah|region|regions|provinsi|province|provinces|"
                r"state|states|kota|cit(?:y|ies)|daerah|kabupaten)\b", re.IGNORECASE),
     ("region", "wilayah", "provinsi", "province", "state", "kota", "city",
      "daerah", "kabupaten")),
    (re.compile(r"\b(produk|product|products|barang|item|items|sku)\b", re.IGNORECASE),
     ("description", "product", "produk", "barang", "item", "desc", "sku")),
    (re.compile(r"\b(pelanggan|customer|customers|klien|client|clients|buyer|buyers)\b",
                re.IGNORECASE),
     ("customer", "pelanggan", "client", "klien", "buyer")),
    # Dimensi dataset epidemiologi/CDC (Fase 1.8): topik→Topic, sumber→DataSource,
    # jenis nilai→DataValueType. SENGAJA ditaruh SEBELUM entri "kategori" generik:
    # trigger "jenis nilai" juga memuat kata "jenis" yang dipakai entri kategori,
    # dan CDC punya kolom Stratification*Category* yang akan salah-tertangkap kalau
    # entri kategori menang duluan. Urutan ini menjaga "jenis nilai"→DataValueType.
    (re.compile(r"\b(topik|topic|topics|tema|subjek|subject)\b", re.IGNORECASE),
     ("topic", "topik", "tema", "subjek")),
    (re.compile(r"\b(sumber(?:\s+data)?|datasource|data\s*source|sources?)\b",
                re.IGNORECASE),
     ("datasource", "source", "sumber")),
    (re.compile(r"\b(jenis\s+nilai|tipe\s+nilai|datavaluetype|"
                r"data\s*value\s*type|value\s*type|valuetype)\b", re.IGNORECASE),
     ("datavaluetype", "valuetype")),
    (re.compile(r"\b(kategori|category|categories|jenis|tipe|type|types)\b", re.IGNORECASE),
     ("category", "kategori", "jenis", "tipe", "type")),
]

# Trigger query temporal → group per BULAN pada kolom datetime yang ADA.
_TEMPORAL_TRIGGER = re.compile(
    r"\b(bulan|bulanan|month|monthly|tanggal|date|tahun|tahunan|year|yearly|"
    r"harian|mingguan|kuartal|quarter|waktu|seiring\s+waktu|over\s+time)\b",
    re.IGNORECASE,
)
# Substring nama kolom yang menandai kolom waktu (fallback bila peran profiler kosong).
_TEMPORAL_COL_HINTS = ("date", "time", "tanggal", "bulan", "tahun", "year",
                       "periode", "month")


def _match_group_synonym(question: str, categorical_cols: list) -> Optional[str]:
    """
    Cocokkan sinonim dimensi (ID↔EN) ke kolom KATEGORIK yang namanya berkaitan.
    Guard anti-false-match: hanya kolom yang namanya memuat substring sinonim.
    Return nama kolom kalau ada yang relevan, None kalau tidak (→ backstop jujur).
    """
    q = question or ""
    for trigger, hints in _GROUP_SYNONYMS:
        if trigger.search(q):
            cand = next(
                (c for c in categorical_cols if any(h in c.lower() for h in hints)),
                None,
            )
            if cand:
                return cand
    return None


def _find_temporal_col(df: pd.DataFrame, column_profile: dict) -> Optional[str]:
    """Cari kolom waktu: peran profiler 'datetime' → dtype datetime → hint nama."""
    prof = column_profile or {}
    for c, lbl in prof.items():
        if lbl == "datetime" and c in df.columns:
            return c
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            return c
    for c in df.columns:
        if any(h in c.lower() for h in _TEMPORAL_COL_HINTS):
            return c
    return None


def _temporal_group_df(df: pd.DataFrame, dt_col: str) -> tuple:
    """
    Bucket per BULAN: tambah kolom 'Periode' (YYYY-MM) dari `dt_col`.
    Returns (df_dengan_periode, nama_kolom_periode) atau (df, None) bila gagal.
    """
    try:
        dt = pd.to_datetime(df[dt_col], errors="coerce")
        mask = dt.notna()
        if int(mask.sum()) == 0:
            return df, None
        pname = "Periode"
        while pname in df.columns:
            pname += "_"
        work = df[mask].copy()
        work[pname] = dt[mask].dt.to_period("M").astype(str)
        return work, pname
    except Exception:
        return df, None


# ── Deteksi metrik yang diminta (Bagian A/B, Fase 1.5) ──────────────────────
_METRIC_REVENUE = re.compile(
    r"\b(revenue|sales|penjualan|pendapatan|omz[eo]t|turnover)\b", re.IGNORECASE
)
_METRIC_COUNT = re.compile(
    r"\b(transaction|transactions|transaksi|count|number\s+of|how\s+many|"
    r"banyak(?:nya)?|berapa\s+banyak|jumlah\s+(?:transaksi|baris|record))\b",
    re.IGNORECASE,
)
# Metrik yang butuh kolom khusus & TIDAK bisa diturunkan dari data transaksi biasa.
_METRIC_UNCOMPUTABLE = re.compile(
    r"\b(profit|laba|keuntungan|margin|cost|biaya|hpp|cogs|discount|diskon|"
    r"tax|pajak|refund|retur)\b",
    re.IGNORECASE,
)
# Metrik numerik via sinonim ID↔EN (Fase 1.6) — selain revenue & count yg sudah ada.
_METRIC_PRICE = re.compile(r"\b(harga|price|prices|unit\s*price|unitprice)\b", re.IGNORECASE)
_METRIC_QTY = re.compile(
    r"\b(kuantitas|quantity|quantities|qty|units?|jumlah\s+(?:barang|unit|item|produk))\b",
    re.IGNORECASE,
)
# Ranking/superlatif berorientasi PENJUALAN (Revisi #3, Commit 2) untuk Revenue-default
# cerdas di domain RETAIL: "produk terlaris/terbaik/top/best-selling" TANPA metrik
# eksplisit. SENGAJA tidak memuat revenue/sales/penjualan (sudah ditangani
# _METRIC_REVENUE) — ini khusus kata ranking yang dulu jatuh ke numeric_now[0]=Quantity
# (atau lebih buruk, Σ Price di narasi). Hanya pintu masuk; Revenue baru dipilih bila
# domain=retail & Qty×Price bisa diturunkan (lihat _select_front_metrics).
_SALES_RANK_INTENT = re.compile(
    r"\b(terlaris|laris|terbaik|best|top)\b",
    re.IGNORECASE,
)


def _find_numeric(numeric_cols: list, keys: tuple) -> Optional[str]:
    """Kolom numerik pertama yang namanya memuat salah satu `keys` (case-insensitive)."""
    return next((c for c in numeric_cols if any(k in c.lower() for k in keys)), None)


def _base_numeric_metric_cols(
    df: pd.DataFrame, column_profile: dict, group_col: str
) -> list:
    """
    Kolom numerik (by dtype) yang LAYAK diperlakukan sebagai METRIK untuk diagregasi.

    Buang kolom yang di `column_profile` berlabel id_kolom/datetime/KATEGORIK — termasuk
    kolom KATEGORIK ber-dtype int64 seperti YearStart/YearEnd (CDC) atau angkatan
    (akademik): tahun/kohort, BUKAN metrik; men-sum-nya menghasilkan angka ngawur.
    `group_col` juga dibuang. Kolom turunan yang tak ada di profil (mis. Revenue hasil
    Quantity×Price) TETAP ikut karena memang metrik.

    Satu-satunya sumber kebenaran exclusion, dipakai BERSAMA oleh _build_breakdown_block
    (context LLM) & build_deterministic_block (angka user) agar keduanya menyaring
    kolom dengan aturan yang IDENTIK.
    """
    prof = column_profile or {}
    excluded = {
        c for c, lbl in prof.items()
        if lbl in ("id_kolom", "datetime", "kategorik")
    }
    return [
        c for c in df.select_dtypes(include=["number"]).columns
        if c not in excluded and c != group_col
    ]


def _maybe_add_revenue(df: pd.DataFrame, numeric_cols: list) -> tuple:
    """
    Turunkan Revenue = Quantity × Price kalau belum ada kolom revenue.
    Konsisten dengan visualization._derive_revenue. Returns (df, revenue_col | None).
    """
    existing = _find_numeric(numeric_cols, ("revenue", "penjualan", "sales", "omzet", "omset"))
    if existing:
        return df, existing
    qty = _find_numeric(numeric_cols, ("quantity", "qty"))
    price = _find_numeric(numeric_cols, ("price", "harga"))
    if qty and price:
        df = df.copy()
        df["Revenue"] = df[qty] * df[price]
        return df, "Revenue"
    return df, None


def detect_groupby_intent(
    question: str,
    column_profile: dict,
    df_columns: list[str],
) -> Optional[dict]:
    """
    Deteksi apakah pertanyaan follow-up meminta GROUP BY.

    Returns:
        dict {"group_col": str} jika intent terdeteksi, None jika tidak.
        Hanya mengembalikan kolom kategorik (bukan numerik/id/datetime).
    """
    if not _KEYWORD_PATTERN.search(question):
        return None  # Tidak ada keyword GROUP BY

    # Ambil kolom yang valid untuk di-group (kategorik saja)
    categorical_cols = [
        col for col, label in column_profile.items()
        if label in ("kategorik", "categorical", "kategori")
        and col in df_columns
    ]
    if not categorical_cols:
        return None

    # Coba match kata setelah keyword dengan nama kolom
    question_lower = question.lower()
    # Token + bentuk singular dari pertanyaan, agar "countries"/"products" cocok
    # dengan kolom "Country"/"Product" (plural/singular & "top N by X").
    q_tokens = re.findall(r"[a-z]+", question_lower)
    q_singular = {_singularize(t) for t in q_tokens}
    best_match = None
    best_score = 0

    for col in categorical_cols:
        col_lower = col.lower()
        score = 0
        # Score tinggi: nama kolom muncul persis di pertanyaan
        if col_lower in question_lower:
            score = len(col_lower)
        # Score tinggi: cocok lewat normalisasi plural/singular (countries -> country)
        elif _singularize(col_lower) in q_singular:
            score = len(col_lower)
        else:
            # Score parsial: token kolom (min 3 char), exact atau singular/plural
            for token in col_lower.split('_'):
                if len(token) >= 3 and (
                    token in question_lower or _singularize(token) in q_singular
                ):
                    score = max(score, len(token))
        if score > best_score:
            best_match = col
            best_score = score

    # Sinonim dimensi ID↔EN: "negara"→Country, "produk"→Description, "pelanggan"→
    # Customer, dst. Hanya bila tak ada match nama langsung; tetap dibatasi ke kolom
    # kategorik yang namanya berkaitan (anti-false-match) → kalau tak ada, biar None.
    if best_match is None:
        cand = _match_group_synonym(question, categorical_cols)
        if cand:
            best_match = cand

    # Jika tidak ada match nama, ambil kolom kategorik pertama sebagai fallback
    # hanya jika keyword sangat jelas ("per kategori", "breakdown")
    if best_match is None and categorical_cols:
        strong_keywords = [r'\bbreakdown\b', r'\bkelompok\b',
                           r'\bper kategori\b', r'\bper grup\b']
        for pat in strong_keywords:
            if re.search(pat, question, re.IGNORECASE):
                best_match = categorical_cols[0]
                break

    if best_match is None:
        return None

    return {"group_col": best_match}


def compute_groupby_stats(
    df: pd.DataFrame,
    group_col: str,
    domain_context: Optional[dict] = None,
    max_groups: int = 15,
) -> dict:
    """
    Jalankan groupby computation pada DataFrame yang di-cache.

    Returns:
        dict dengan format:
        {
            "group_col": "Country",
            "agg_func": "sum",
            "results": [
                {"group": "United Kingdom", "sum": 8187806.0,
                 "count": 23494, "mean": 348.4},
                ...
            ]
        }
    """
    if group_col not in df.columns:
        return {}

    # Tentukan agg function dari domain_context
    agg_func = "sum"
    if domain_context:
        pref = domain_context.get("preferred_aggregation", "sum")
        if pref in ("mean", "median", "sum"):
            agg_func = pref

    # Pilih kolom numerik valid (bukan object/bool)
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    if not numeric_cols:
        return {}

    try:
        grouped = df.groupby(group_col, observed=True)[numeric_cols]

        if agg_func == "sum":
            agg_result = grouped.sum()
        elif agg_func == "mean":
            agg_result = grouped.mean()
        else:
            agg_result = grouped.sum()

        count_result = df.groupby(group_col, observed=True).size()
        mean_result = grouped.mean()

        # Pilih kolom utama untuk sorting (kolom pertama yang bukan ID-like)
        sort_col = numeric_cols[0]

        # Susun hasil sebagai list of dict, sorted descending
        results = []
        for group_val in agg_result.index:
            row = {
                "group": str(group_val),
                "count": int(count_result.get(group_val, 0)),
            }
            for nc in numeric_cols[:5]:  # max 5 kolom numerik
                agg_val = agg_result.loc[group_val, nc]
                mean_val = mean_result.loc[group_val, nc]
                row[f"{agg_func}_{nc}"] = round(float(agg_val), 2)
                if agg_func != "mean":
                    row[f"mean_{nc}"] = round(float(mean_val), 2)
            results.append(row)

        # Sort by kolom utama
        primary_key = f"{agg_func}_{sort_col}"
        results.sort(key=lambda x: x.get(primary_key, 0), reverse=True)

        return {
            "group_col": group_col,
            "agg_func": agg_func,
            "results": results[:max_groups],
        }

    except Exception as e:
        return {"error": str(e)}


def format_groupby_for_context(groupby_result: dict) -> str:
    """
    Format hasil groupby menjadi string untuk di-inject ke stats_context.
    """
    if not groupby_result or "results" not in groupby_result:
        return ""

    group_col = groupby_result["group_col"]
    agg_func = groupby_result["agg_func"]
    results = groupby_result["results"]

    lines = [f"BREAKDOWN PER {group_col.upper()} ({agg_func}):"]
    for row in results:
        group_name = row["group"]
        count = row["count"]
        # Ambil semua key kecuali group dan count
        metrics = {k: v for k, v in row.items()
                   if k not in ("group", "count")}
        metric_str = ", ".join(
            f"{k}={v:,.2f}" for k, v in metrics.items()
        )
        lines.append(f"  {group_name}: count={count}, {metric_str}")

    return "\n".join(lines)


# Pesan jujur anti-halusinasi bila breakdown tak bisa dihitung. SENGAJA tanpa
# angka apa pun supaya LLM tidak punya angka untuk "disalin" jadi karangan.
_NO_DATA_NOTICE = (
    "PENTING — RINCIAN PER-KELOMPOK TIDAK TERSEDIA: agregasi/breakdown yang "
    "diminta tidak dapat dihitung ulang dari data sesi ini (kolom pengelompokan "
    "tidak dikenali). DILARANG mengarang, menebak, atau memperkirakan angka per "
    "kelompok. DILARANG pula MENURUNKAN angka lewat pembagian/perkalian/asumsi "
    "(mis. revenue ÷ harga rata-rata) atau menyalin angka dari jawaban sebelumnya. "
    "Jawab dengan JUJUR bahwa rincian tersebut tidak tersedia, dan sarankan "
    "pengguna menyebut nama kolom yang tepat atau menganalisis ulang. "
    "/ The requested per-group breakdown is NOT available; do NOT fabricate, "
    "derive, or estimate any numbers — state honestly that this detail is unavailable."
)


def _build_breakdown_block(
    df: pd.DataFrame,
    group_col: str,
    question: str,
    column_profile: dict,
    domain_context: Optional[dict] = None,
) -> str:
    """
    Hitung breakdown per `group_col` (HARUS sudah ada di df) + resolusi metrik
    (revenue/harga/kuantitas/count + penanda metrik tak terhitung), lalu format
    jadi blok teks recompute siap-inject. Return "" kalau breakdown kosong.
    Dipakai jalur KATEGORIK maupun TEMPORAL.
    """
    prof = column_profile or {}
    q = question or ""
    base_numeric = _base_numeric_metric_cols(df, prof, group_col)

    work = df
    front: list = []        # metrik DIMINTA → ditaruh depan (jadi kunci sort)
    notes: list = []        # metrik diminta tapi tak terhitung
    extra_lines: list = []  # klarifikasi (mis. count = transaksi)

    # Revenue/penjualan → derive Quantity × Price kalau perlu.
    if _METRIC_REVENUE.search(q):
        work, rev_col = _maybe_add_revenue(work, base_numeric)
        if rev_col:
            front.append(rev_col)
        else:
            notes.append(
                "'revenue/penjualan' (diminta): TIDAK TERSEDIA — tak ada kolom "
                "revenue maupun Quantity & Price untuk menurunkannya. "
                "JANGAN estimasi/hitung sendiri."
            )

    # Harga → kolom Price; Kuantitas/jumlah barang → kolom Quantity.
    if _METRIC_PRICE.search(q):
        pcol = _find_numeric(base_numeric, ("price", "harga", "unitprice"))
        if pcol:
            front.append(pcol)
    if _METRIC_QTY.search(q):
        qcol = _find_numeric(base_numeric, ("quantity", "qty", "kuantitas"))
        if qcol:
            front.append(qcol)

    # Count/transaksi → selalu tersedia (count = jumlah baris per grup).
    if _METRIC_COUNT.search(q):
        extra_lines.append(
            "CATATAN METRIK: 'jumlah transaksi' = nilai 'count' pada tiap "
            "kelompok di bawah (jumlah baris/transaksi NYATA). DILARANG "
            "menurunkannya dari pembagian (mis. revenue ÷ harga)."
        )

    # Metrik yang butuh kolom khusus & tak ada → tandai eksplisit (tutup celah).
    for m in sorted({x.lower() for x in _METRIC_UNCOMPUTABLE.findall(q)}):
        notes.append(
            f"'{m}' (diminta): TIDAK TERSEDIA — tak ada kolom terkait di data "
            f"sesi ini. JANGAN menurunkan, mengestimasi, atau menebak angkanya."
        )

    # Urutan kolom: metrik diminta (dedup) di depan → jadi kunci sort breakdown.
    seen: set = set()
    front_unique = [
        c for c in front
        if c in work.columns and not (c in seen or seen.add(c))
    ]
    rest = [c for c in base_numeric if c not in seen]
    metric_cols = front_unique + rest

    sub_df = work[[group_col] + metric_cols] if metric_cols else work
    gb = compute_groupby_stats(sub_df, group_col, domain_context)
    ctx = format_groupby_for_context(gb)
    if not ctx:
        return ""

    blocks = [
        "DATA DIHITUNG ULANG KHUSUS UNTUK PERTANYAAN INI (gunakan HANYA angka "
        "di bawah; DILARANG mengarang/menebak, dan DILARANG MENURUNKAN angka "
        "lewat pembagian/perkalian/asumsi mis. revenue ÷ harga rata-rata, atau "
        "menyalin dari jawaban sebelumnya):"
    ]
    blocks.extend(extra_lines)
    if notes:
        blocks.append(
            "METRIK YANG TIDAK BISA DIHITUNG (jawab 'tidak tersedia', "
            "JANGAN isi dengan angka apa pun):"
        )
        blocks.extend("  - " + n for n in notes)
    blocks.append(ctx)
    return "\n".join(blocks)


def _resolve_followup_dimension(df: pd.DataFrame, question: str, column_profile: dict):
    """
    Tentukan dimensi group untuk followup: KATEGORIK dulu (negara/produk/...),
    lalu TEMPORAL (per bulan). Returns (work_df, group_col, is_temporal) atau None.
    Dipakai BERSAMA oleh build_followup_context (blok LLM) dan
    build_deterministic_block (blok angka user) agar KEDUANYA setuju kolom yang sama.
    """
    q = question or ""
    prof = column_profile or {}
    intent = detect_groupby_intent(q, prof, list(df.columns))
    if intent:
        return df, intent["group_col"], False
    if _TEMPORAL_TRIGGER.search(q):
        dt_col = _find_temporal_col(df, prof)
        if dt_col:
            work, period_col = _temporal_group_df(df, dt_col)
            if period_col:
                return work, period_col, True
    return None


def build_followup_context(
    df: pd.DataFrame,
    question: str,
    column_profile: dict,
    domain_context: Optional[dict] = None,
) -> str:
    """
    Bangun teks yang diinjeksi ke STATS_CONTEXT untuk pertanyaan follow-up.

    Tiga keluaran:
      1. Intent GROUP BY terdeteksi & bisa dihitung → tabel breakdown dengan
         angka NYATA dari dataframe + instruksi "pakai HANYA angka ini".
      2. Pertanyaan jelas meminta segmentasi (ada keyword per/by/breakdown/...)
         TAPI kolom tak bisa dipetakan/dihitung → instruksi jujur anti-halusinasi
         (tanpa angka), supaya LLM bilang "tidak tersedia" alih-alih mengarang.
      3. Selain itu → "" (tak ada injeksi; pakai statistik biasa).

    Tidak pernah raise — selalu kembalikan string (mungkin kosong).
    """
    try:
        if df is None or len(df) == 0:
            return ""
        prof = column_profile or {}
        q = question or ""

        # Recompute hanya kalau ada sinyal segmentasi/ranking ATAU temporal.
        if not (_KEYWORD_PATTERN.search(q) or _TEMPORAL_TRIGGER.search(q)):
            return ""

        # Kategorik dulu (negara/produk/...), lalu temporal (per bulan) — shared resolver.
        resolved = _resolve_followup_dimension(df, q, prof)
        if resolved:
            work, group_col, _is_temporal = resolved
            block = _build_breakdown_block(work, group_col, q, prof, domain_context)
            if block:
                return block

        # Segmentasi diminta tapi tak bisa dihitung → backstop jujur.
        return _NO_DATA_NOTICE
    except Exception:
        return ""


# ── Blok ANGKA KUNCI deterministik untuk LAPORAN USER (Fase 1.7) ────────────
# Semua angka & persen DIHITUNG di Python langsung dari dataframe — TIDAK
# bergantung LLM menuliskannya (LLM cuma menulis prosa pengantar/kesimpulan).

_MEAN_INTENT = re.compile(r"\b(rata-rata|rata2|average|avg|mean)\b", re.IGNORECASE)

# Intent DISTRIBUSI/FREKUENSI kategorik (Fase 1.8): pertanyaan menanyakan sebaran
# kategori (mana yang dominan/paling sering, proporsi/distribusi/komposisi) — BUKAN
# metrik numerik. Saat ini terdeteksi DAN tak ada metrik numerik yang diminta, blok
# deterministik dipaksa ke cabang COUNT+PROPORSI, supaya tidak men-sum kolom numerik
# sembarang (mis. YearStart/YearEnd yang berlabel kategorik tapi dtype int64).
_DISTRIB_INTENT = re.compile(
    r"\b(distribusi|distribution|distributions|proporsi|proportion|proportions|"
    r"dominan|dominasi|terdominan|paling\s+sering|sering|tersering|"
    r"frekuensi|frequency|frequent|komposisi|composition|sebaran)\b",
    re.IGNORECASE,
)


def _select_front_metrics(
    question: str,
    df: pd.DataFrame,
    base_numeric: list,
    domain_context: Optional[dict] = None,
):
    """Metrik yang diminta (revenue/harga/kuantitas) → diprioritaskan sbg kunci
    sort. Returns (work_df, front_cols). work bisa punya kolom Revenue turunan."""
    q = question or ""
    work = df
    front: list = []
    if _METRIC_REVENUE.search(q):
        work, rev = _maybe_add_revenue(work, base_numeric)
        if rev:
            front.append(rev)
    if _METRIC_PRICE.search(q):
        p = _find_numeric(base_numeric, ("price", "harga", "unitprice"))
        if p:
            front.append(p)
    if _METRIC_QTY.search(q):
        qn = _find_numeric(base_numeric, ("quantity", "qty", "kuantitas"))
        if qn:
            front.append(qn)
    # Revisi #3 (Commit 2): Revenue-default CERDAS untuk domain RETAIL. Pertanyaan
    # ranking "terlaris/top/terbaik/best-selling" TANPA metrik eksplisit (front masih
    # kosong, bukan count/distribusi) → pakai Revenue (Qty×Price), bukan
    # numeric_now[0]=Quantity. Ini yang membuat "produk terlaris" menjawab dgn
    # kontribusi penjualan (1.058.314), bukan unit (648.922) apalagi Σ Price (163.401).
    # Hanya bila Revenue bisa diturunkan; kalau tidak → fallback lama. _maybe_add_revenue
    # dipakai ulang → derivasi TUNGGAL, jadi tabel & chart memakai angka yang sama.
    if (
        not front
        and (domain_context or {}).get("domain_type") == "retail"
        and _SALES_RANK_INTENT.search(q)
        and not _METRIC_COUNT.search(q)
        and not _DISTRIB_INTENT.search(q)
    ):
        work, rev = _maybe_add_revenue(work, base_numeric)
        if rev:
            front.append(rev)
    return work, front


def _fmt_id(x) -> str:
    """Angka gaya Indonesia: 1.003.551,44 (titik ribuan, koma desimal)."""
    try:
        s = f"{float(x):,.2f}"             # 1,003,551.44
    except (ValueError, TypeError):
        return str(x)
    return s.translate(str.maketrans({",": ".", ".": ","}))


def _fmt_int(n) -> str:
    """Bilangan bulat gaya Indonesia: 45.525."""
    try:
        return f"{int(n):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(n)


# ── Varian gaya Inggris + dispatcher locale-aware (Revisi #3, format ikut bahasa) ──
# Python f"{x:,.2f}" SUDAH gaya EN (koma ribuan, titik desimal); jadi _fmt_en cukup
# memformat tanpa translate. _fmt_id men-translate ke gaya ID. Nilai TIDAK berubah —
# hanya representasi string. Dispatcher fallback ke gaya ID bila gagal (tak crash).

def _fmt_en(x) -> str:
    """Angka gaya Inggris: 1,003,551.44 (koma ribuan, titik desimal)."""
    try:
        return f"{float(x):,.2f}"
    except (ValueError, TypeError):
        return str(x)


def _fmt_int_en(n) -> str:
    """Bilangan bulat gaya Inggris: 45,525."""
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return str(n)


def _fmt_num(value, language: str = "id") -> str:
    """2-desimal locale-aware: id → 1.058.314,21 ; en → 1,058,314.21.
    Fallback ke gaya ID bila apa pun gagal (tak pernah raise)."""
    try:
        return _fmt_en(value) if language == "en" else _fmt_id(value)
    except Exception:
        return _fmt_id(value)


def _fmt_intnum(n, language: str = "id") -> str:
    """Integer locale-aware: id → 45.525 ; en → 45,525. Fallback gaya ID."""
    try:
        return _fmt_int_en(n) if language == "en" else _fmt_int(n)
    except Exception:
        return _fmt_int(n)


def _resolve_followup_aggregation(
    df: pd.DataFrame,
    question: str,
    column_profile: dict,
    domain_context: Optional[dict] = None,
):
    """
    Inti BERSAMA followup groupby/temporal: resolve dimensi + pilih metrik utama +
    siapkan groupby. Dipakai build_deterministic_block (angka USER) DAN
    build_followup_chart_spec (GRAFIK) → angka di teks & grafik dijamin konsisten
    karena keduanya membaca pemilihan metrik & groupby yang IDENTIK.

    `domain_context` (Revisi #3): mengaktifkan Revenue-default cerdas untuk retail
    (lihat _select_front_metrics). Tidak memengaruhi nilai metrik/persen di luar
    pemilihan kolom primer.

    Returns None bila bukan followup groupby/temporal, atau dict:
      {work, group_col, is_temporal, primary(str|None), mean_intent(bool),
       grp(DataFrameGroupBy), gcount(Series)}
    Tidak pernah raise.
    """
    try:
        if df is None or len(df) == 0:
            return None
        q = question or ""
        prof = column_profile or {}
        if not (_KEYWORD_PATTERN.search(q) or _TEMPORAL_TRIGGER.search(q)):
            return None
        resolved = _resolve_followup_dimension(df, q, prof)
        if not resolved:
            return None
        work, group_col, is_temporal = resolved

        base_numeric = _base_numeric_metric_cols(work, prof, group_col)
        work, front = _select_front_metrics(q, work, base_numeric, domain_context)
        # Re-scan: `work` kini bisa punya kolom turunan (mis. Revenue) yang tak ada
        # di profil → tetap lolos sebagai metrik; YearStart/angkatan dkk tetap dibuang.
        numeric_now = _base_numeric_metric_cols(work, prof, group_col)
        count_requested = bool(_METRIC_COUNT.search(q))
        # Intent distribusi MURNI = sebaran kategori diminta TANPA metrik numerik
        # (front kosong) → primary None → cabang COUNT (hindari men-sum kolom acak).
        distrib_only = bool(_DISTRIB_INTENT.search(q)) and not front
        primary = next((c for c in front if c in numeric_now), None)
        if primary is None and not count_requested and not distrib_only and numeric_now:
            primary = numeric_now[0]

        mean_intent = bool(_MEAN_INTENT.search(q))
        grp = work.groupby(group_col, observed=True)
        gcount = grp.size()
        return {
            "work": work,
            "group_col": group_col,
            "is_temporal": is_temporal,
            "primary": primary,
            "mean_intent": mean_intent,
            "grp": grp,
            "gcount": gcount,
        }
    except Exception:
        return None


def _md_cell(val) -> str:
    """Escape a value for a markdown table cell (guard stray pipes)."""
    return str(val).replace("|", "\\|")


def _format_groups_as_table(
    rows: list,
    dim_label: str,
    value_header: str,
    kind: str,
    mean_intent: bool,
    language: str,
) -> str:
    """
    Render pre-computed group rows as a MARKDOWN TABLE (Revisi #2).
    Header kolom hormati `language`; angka memakai format yang sudah jadi
    (`_fmt_id`/`_fmt_int` di row dict) — fungsi ini murni presentasi, nol LLM.
    """
    en = language == "en"
    if kind == "metric":
        if mean_intent:
            headers = [dim_label, value_header, "%",
                       ("Mean" if en else "Rata-rata"), "n"]
            row_cells = lambda r: [r["group"], r["value"], f"{r['pct']}%", r["mean"], r["n"]]
        else:
            headers = [dim_label, value_header, "%", "n"]
            row_cells = lambda r: [r["group"], r["value"], f"{r['pct']}%", r["n"]]
    else:  # count branch
        headers = [dim_label, value_header, "%"]
        row_cells = lambda r: [r["group"], r["value"], f"{r['pct']}%"]

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for r in rows:
        lines.append("| " + " | ".join(_md_cell(c) for c in row_cells(r)) + " |")
    return "\n".join(lines)


def _format_groups_as_list(
    rows: list,
    kind: str,
    value_unit: str,
    mean_intent: bool,
) -> str:
    """Numbered-list fallback — the ORIGINAL format, used only if table render fails."""
    out: list = []
    for r in rows:
        if kind == "metric":
            seg = f"{r['i']}. {r['group']} — {r['value']} ({r['pct']}%)"
            if mean_intent and r.get("mean") is not None:
                seg += f"; rata-rata {r['mean']}"
            seg += f"; n={r['n']}"
        else:
            seg = f"{r['i']}. {r['group']} — {r['value']} {value_unit} ({r['pct']}%)"
        out.append(seg)
    return "\n".join(out)


def build_deterministic_block(
    df: pd.DataFrame,
    question: str,
    column_profile: dict,
    domain_context: Optional[dict] = None,
    language: str = "id",
) -> str:
    """
    Blok ANGKA KUNCI deterministik untuk LAPORAN USER (BUKAN context LLM).
    Nilai per-grup, total, dan PERSEN dihitung di Python (persen = grup/total NYATA
    × 100). Inilah angka otoritatif yang masuk ke laporan — bukan angka tulisan LLM.

    Revisi #2: dirender sebagai TABEL markdown (header kolom hormati `language`);
    bila perakitan tabel gagal → fallback ke list bernomor lama. Angka & format
    (via _fmt_id/_fmt_int) TIDAK berubah. Hanya dipakai di /analyze/followup.

    Return "" kalau followup bukan groupby/temporal (laporan tetap normal).
    Tidak pernah raise.
    """
    try:
        # Pemilihan dimensi + metrik + groupby di-share dengan build_followup_chart_spec
        # (lewat _resolve_followup_aggregation) → angka teks & grafik konsisten.
        # domain_context diteruskan → Revenue-default retail (Commit 2).
        agg = _resolve_followup_aggregation(df, question, column_profile, domain_context)
        if not agg:
            return ""
        work        = agg["work"]
        group_col   = agg["group_col"]
        is_temporal = agg["is_temporal"]
        primary     = agg["primary"]
        mean_intent = agg["mean_intent"]
        grp         = agg["grp"]
        gcount      = agg["gcount"]
        en = language == "en"
        dim_label = (("MONTH" if en else "BULAN") if is_temporal else group_col)

        rows: list = []
        if primary is not None:
            gsum = grp[primary].sum()
            gmean = grp[primary].mean()
            total = float(gsum.sum())
            order = gsum.sort_values(ascending=False).index[:15]
            if en:
                head = (
                    f"**📊 Key figures per {dim_label} — computed directly from the "
                    f"data (not LLM estimates):**\n"
                    f"_Total {primary} = {_fmt_num(total, language)} "
                    f"from {_fmt_intnum(len(work), language)} rows_"
                )
            else:
                head = (
                    f"**📊 Angka kunci per {dim_label} — dihitung otomatis dari data "
                    f"(bukan estimasi LLM):**\n"
                    f"_Total {primary} = {_fmt_num(total, language)} "
                    f"dari {_fmt_intnum(len(work), language)} baris_"
                )
            for i, g in enumerate(order, 1):
                s = float(gsum.get(g, 0.0))
                pct = (s / total * 100.0) if total else 0.0
                rows.append({
                    "i": i, "group": str(g),
                    "value": _fmt_num(s, language), "pct": _fmt_num(pct, language),
                    "mean": _fmt_num(float(gmean.get(g, 0.0)), language),
                    "n": _fmt_intnum(int(gcount.get(g, 0)), language),
                })
            kind = "metric"
            value_header = str(primary)
            value_unit = ""
        else:
            # Unit count: "transaksi" hanya bila domain RETAIL terdeteksi; selain itu
            # "baris" (netral). "313 transaksi" untuk Topic CDC/epidemiologi menyesatkan.
            unit = (
                ("transactions" if en else "transaksi")
                if (domain_context or {}).get("domain_type") == "retail"
                else ("rows" if en else "baris")
            )
            total = float(int(gcount.sum()))
            order = gcount.sort_values(ascending=False).index[:15]
            if en:
                head = (
                    f"**📊 Key figures per {dim_label} — computed directly from the "
                    f"data (not LLM estimates):**\n_Total {unit} = {_fmt_intnum(int(total), language)}_"
                )
            else:
                head = (
                    f"**📊 Angka kunci per {dim_label} — dihitung otomatis dari data "
                    f"(bukan estimasi LLM):**\n_Total {unit} = {_fmt_intnum(int(total), language)}_"
                )
            for i, g in enumerate(order, 1):
                cnt = int(gcount.get(g, 0))
                pct = (cnt / total * 100.0) if total else 0.0
                rows.append({
                    "i": i, "group": str(g),
                    "value": _fmt_intnum(cnt, language), "pct": _fmt_num(pct, language),
                    "mean": None, "n": None,
                })
            kind = "count"
            value_header = ("Count" if en else "Jumlah")
            value_unit = unit

        if not rows:
            return ""

        # Tabel markdown sebagai presentasi utama; list bernomor lama jadi fallback
        # aman kalau perakitan tabel gagal (Revisi #2, Bagian A).
        try:
            body = _format_groups_as_table(
                rows, dim_label, value_header, kind, mean_intent, language
            )
        except Exception:
            body = _format_groups_as_list(rows, kind, value_unit, mean_intent)

        return head + "\n\n" + body
    except Exception:
        return ""


# ── Chart RELEVAN untuk followup (Revisi #1, Phase 2) ───────────────────────
# Mengganti chart overview lama dengan SATU grafik yang menjawab pertanyaan
# followup, dibangun dari agregasi yang SAMA dengan build_deterministic_block.

def build_followup_chart_spec(
    df: pd.DataFrame,
    question: str,
    column_profile: dict,
    domain_context: Optional[dict] = None,
    language: str = "id",
) -> Optional[dict]:
    """
    Bangun SATU spec chart Plotly yang RELEVAN untuk pertanyaan followup:
      - temporal  → line chart (tren per bulan),
      - kategorik → horizontal bar (top-N).

    Memakai _resolve_followup_aggregation (dimensi + metrik + groupby yang SAMA
    dengan blok deterministik) → nilai per-grup di grafik = nilai di teks.

    Returns dict spec Plotly, atau None bila pertanyaan BUKAN groupby/temporal
    (mis. minta grafik eksplisit tanpa intent → caller pakai overview cache) atau
    bila pembuatan gagal. Tidak pernah raise (Phase 2 fail-safe).
    """
    try:
        # domain_context diteruskan → chart memakai Revenue-default retail yang SAMA
        # dengan blok deterministik (Commit 2) → nilai grafik = nilai tabel.
        agg = _resolve_followup_aggregation(df, question, column_profile, domain_context)
        if not agg:
            return None

        group_col   = agg["group_col"]
        is_temporal = agg["is_temporal"]
        primary     = agg["primary"]
        grp         = agg["grp"]

        if primary is not None:
            series = grp[primary].sum()          # SAMA dengan blok deterministik
            value_label = str(primary)
        else:
            series = agg["gcount"]               # cabang COUNT (sebaran kategori)
            value_label = "Jumlah" if language == "id" else "Count"

        if series is None or len(series) == 0:
            return None

        # Hindari nama kolom bentrok (group_col == value_label) saat dijadikan df.
        if value_label == group_col:
            value_label = f"{value_label}_"

        from tools.visualization import create_line_chart, create_bar_chart

        if is_temporal:
            s = series.sort_index()              # urut kronologis (YYYY-MM)
            plot_df = s.reset_index()
            plot_df.columns = [group_col, value_label]
            title = (f"Tren {value_label} per Bulan" if language == "id"
                     else f"{value_label} Trend by Month")
            return create_line_chart(plot_df, x=group_col, y=value_label, title=title)

        # Kategorik → horizontal bar: top 15 desc, lalu ascending utk tampilan bar.
        s = series.sort_values(ascending=False).head(15).sort_values()
        plot_df = s.reset_index()
        plot_df.columns = [group_col, value_label]
        title = (f"Top {group_col} berdasarkan {value_label}" if language == "id"
                 else f"Top {group_col} by {value_label}")
        return create_bar_chart(
            plot_df, x=group_col, y=value_label, title=title,
            orientation="h", labels={group_col: group_col, value_label: value_label},
        )
    except Exception:
        return None
