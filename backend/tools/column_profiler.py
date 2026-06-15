"""
tools/column_profiler.py
Smart Column Profiling — TA Data Analysis Agent
Menggunakan heuristik + Qwen3 8B sebagai classifier kolom.

Label output:
  - "numerik_valid"  : metric bermakna (e.g. Revenue, Age, Score)
  - "id_kolom"       : identifier/kode (e.g. NIM, CustomerID, LocationID)
  - "kategorik"      : variabel kategori (e.g. Jurusan, Country, Status)
  - "datetime"       : kolom tanggal/waktu
"""

import json
import re
import logging
from typing import Any

import pandas as pd
from langchain_ollama import ChatOllama

from config import settings

logger = logging.getLogger(__name__)

# ── Konstanta ─────────────────────────────────────────────────────────────

VALID_LABELS = {"numerik_valid", "id_kolom", "kategorik", "datetime"}

# Heuristik: pattern nama kolom yang kuat sebagai ID (case-insensitive)
ID_NAME_PATTERNS = re.compile(
    r"\b(id|_id|nim|nip|nik|code|kode|no\b|number|uuid|guid|"
    r"customerid|customer_id|orderid|order_id|locationid|location_id|"
    r"productid|product_id|userid|user_id|empid|emp_id|invoice|"
    r"stockcode|stock_code|itemcode|item_code|sku)\b",
    re.IGNORECASE,
)

# Pattern nama kolom yang kuat sebagai tahun/temporal (bukan metric)
YEAR_PATTERNS = re.compile(
    r"\b(year|tahun|yearstart|yearend|year_start|year_end)\b",
    re.IGNORECASE,
)

# ── Domain Detection Constants ────────────────────────────────────────────

_DOMAIN_HINTS: dict[str, re.Pattern] = {
    "retail": re.compile(
        r"\b(price|quantity|qty|invoice|stock|sales|revenue|customer|"
        r"unitprice|unit_price|stockcode|stock_code|description|country|"
        r"product|item|order|basket|cart|discount|margin)\b",
        re.IGNORECASE,
    ),
    "finance": re.compile(
        r"\b(amount|balance|debit|credit|transaction|account|payment|"
        r"currency|exchange|interest|loan|deposit|withdraw|portfolio|"
        r"asset|liability|equity|cashflow|cash_flow)\b",
        re.IGNORECASE,
    ),
    "hr": re.compile(
        r"\b(salary|employee|department|position|hire|termination|"
        r"headcount|tenure|bonus|performance|job|title|manager|"
        r"karyawan|gaji|jabatan|divisi|departemen)\b",
        re.IGNORECASE,
    ),
    "healthcare": re.compile(
        r"\b(patient|diagnosis|treatment|dose|medication|hospital|"
        r"doctor|symptom|blood|pressure|heart|bmi|glucose|"
        r"diabetes|obesity|prevalence|mortality|morbidity|disease|"
        r"chronic|cardiovascular|cancer|stroke|health|clinical|"
        r"inactivity|cholesterol|hypertension|asthma|mental|"
        r"pasien|diagnosa|obat|rumah_sakit|tekanan_darah|penyakit)\b",
        re.IGNORECASE,
    ),
    "education": re.compile(
        r"\b(student|grade|score|subject|course|nim|gpa|ipk|"
        r"semester|faculty|major|jurusan|nilai|mahasiswa|"
        r"matkul|prodi|angkatan|wisuda)\b",
        re.IGNORECASE,
    ),
}

_DOMAIN_CONFIG: dict[str, dict] = {
    "retail": {
        "preferred_aggregation": "sum",
        "metric_note": (
            "Dataset ini adalah data retail/transaksi. Metrik utama adalah total penjualan "
            "(sum), bukan rata-rata per transaksi. Gunakan sum untuk Revenue/Quantity; "
            "gunakan mean untuk harga satuan. Soroti produk/segmen dengan kontribusi terbesar."
        ),
        "metric_note_en": (
            "This is retail/transaction data. The main metric is total sales (sum), not the "
            "average per transaction. Use sum for Revenue/Quantity; use mean for unit price. "
            "Highlight the products/segments with the largest contribution."
        ),
        "avoid": [
            "Jangan ratakan revenue tanpa segmentasi produk atau periode",
            "Hindari interpretasi kode invoice/order sebagai metrik kuantitatif",
        ],
    },
    "finance": {
        "preferred_aggregation": "sum",
        "metric_note": (
            "Dataset finansial. Total (sum) lebih bermakna daripada rata-rata untuk "
            "amount/nilai transaksi. Perhatikan outlier pada nilai transaksi yang ekstrem. "
            "Gunakan konteks waktu saat membandingkan antar periode."
        ),
        "metric_note_en": (
            "Financial dataset. Total (sum) is more meaningful than the average for "
            "transaction amounts/values. Watch for outliers in extreme transaction values. "
            "Use time context when comparing across periods."
        ),
        "avoid": [
            "Hindari membandingkan absolut tanpa konteks periode waktu",
            "Jangan sum saldo (balance) antar entitas yang berbeda",
        ],
    },
    "hr": {
        "preferred_aggregation": "median",
        "metric_note": (
            "Dataset HR/SDM. Gunakan median untuk gaji (lebih robust terhadap outlier "
            "eksekutif). Segmentasikan per departemen/jabatan untuk insight yang bermakna. "
            "Perhatikan distribusi tenure dan komposisi workforce."
        ),
        "metric_note_en": (
            "HR/workforce dataset. Use the median for salary (more robust to executive "
            "outliers). Segment by department/role for meaningful insight. Watch the tenure "
            "distribution and workforce composition."
        ),
        "avoid": [
            "Jangan sum gaji tanpa konteks yang jelas",
            "Hindari generalisasi seluruh karyawan tanpa segmentasi jabatan/departemen",
        ],
    },
    "healthcare": {
        "preferred_aggregation": "mean",
        "metric_note": (
            "Dataset kesehatan/epidemiologi. Utamakan rate per 100.000 populasi atau "
            "age-adjusted rate, bukan total count atau sum. Jika kolom populasi tersedia, "
            "hitung rate = (kasus / populasi) × 100000. Untuk indikator seperti prevalensi "
            "dan insidensi, bandingkan antar lokasi menggunakan rate yang sudah dinormalisasi, "
            "bukan angka absolut."
        ),
        "metric_note_en": (
            "Healthcare/epidemiology dataset. Prefer rate per 100,000 population or "
            "age-adjusted rate, not total count or sum. If a population column is available, "
            "compute rate = (cases / population) × 100000. For indicators such as prevalence "
            "and incidence, compare across locations using normalized rates, not absolute "
            "numbers."
        ),
        "avoid": [
            "sum_total raw counts tanpa normalisasi populasi",
            "membandingkan angka absolut antar state/wilayah dengan populasi berbeda",
        ],
    },
    "education": {
        "preferred_aggregation": "mean",
        "metric_note": (
            "Dataset pendidikan/akademik. Gunakan mean/median untuk nilai dan IPK. "
            "Analisis distribusi per mata kuliah, jurusan, atau angkatan untuk "
            "insight yang bermakna tentang performa akademik."
        ),
        "metric_note_en": (
            "Education/academic dataset. Use mean/median for scores and GPA. Analyze the "
            "distribution per course, major, or cohort for meaningful insight into academic "
            "performance."
        ),
        "avoid": [
            "Hindari sum untuk nilai akademis",
            "Jangan abaikan nilai minimum/maksimum — menunjukkan rentang performa",
        ],
    },
    "general": {
        "preferred_aggregation": "mean",
        "metric_note": (
            "Dataset umum. Gunakan mean sebagai agregasi default. "
            "Periksa distribusi setiap kolom numerik sebelum interpretasi. "
            "Perhatikan skewness untuk memilih antara mean dan median."
        ),
        "metric_note_en": (
            "General dataset. Use mean as the default aggregation. Inspect the distribution "
            "of each numeric column before interpretation. Consider skewness when choosing "
            "between mean and median."
        ),
        "avoid": [],
    },
}

VALID_DOMAINS: frozenset[str] = frozenset(_DOMAIN_CONFIG.keys())


# ── Helpers ───────────────────────────────────────────────────────────────

def _extract_json_label(text: str) -> str | None:
    """
    Ekstrak label dari respons LLM.
    Qwen3 sering output <think>...</think> sebelum JSON — strip dulu.
    """
    if not text or not text.strip():
        return None  # Empty response → langsung ke fallback

    # Buang blok <think>
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Cari JSON object {"label": "..."}
    match = re.search(r'\{[^{}]*"label"\s*:\s*"([^"]+)"[^{}]*\}', text)
    if match:
        label = match.group(1).strip().lower()
        if label in VALID_LABELS:
            return label

    # Fallback: cari label mentah di teks
    for label in VALID_LABELS:
        if label in text.lower():
            return label

    return None


def _heuristic_label(col: str, series: pd.Series) -> str:
    """
    Heuristik cepat — digunakan sebagai pre-filter sebelum memanggil LLM.
    """
    col_lower = col.lower().strip()

    # 1. Kolom datetime (dtype datetime64)
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"

    # 1b. String/object dtype tapi isinya tanggal (e.g. "2010-12-01 08:26:00")
    # Pandas 3.0 menggunakan dtype 'str' (bukan 'object'), pakai is_string_dtype
    if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
        sample = series.dropna().head(10)
        if len(sample) > 0:
            try:
                parsed = pd.to_datetime(sample)
                # Confirm most values parsed without NaT
                if parsed.notna().mean() >= 0.8:
                    return "datetime"
            except (ValueError, TypeError, Exception):
                pass

    # 2. Nama kolom cocok pola year/temporal → kategorik (bukan metric)
    if YEAR_PATTERNS.search(col_lower):
        return "kategorik"

    # 3. Nama kolom cocok pola ID yang kuat
    if ID_NAME_PATTERNS.search(col_lower):
        return "id_kolom"

    # 4. Integer dengan kardinalitas tinggi relatif terhadap ukuran → kemungkinan ID
    if pd.api.types.is_integer_dtype(series):
        n_unique = series.nunique()
        n_total = len(series.dropna())
        if n_total > 0 and (n_unique / n_total) > 0.85:
            return "id_kolom"

    # 5. String/object/categorical dtype → kategorik (pandas 3.0: string dtype = 'str')
    if (pd.api.types.is_string_dtype(series)
            or pd.api.types.is_object_dtype(series)
            or isinstance(series.dtype, pd.CategoricalDtype)):
        return "kategorik"

    # 6. Numerik float/int — default ke numerik_valid, biarkan LLM konfirmasi
    if pd.api.types.is_numeric_dtype(series):
        return "numerik_valid"

    return "kategorik"


# ── Fungsi utama ──────────────────────────────────────────────────────────

def profile_columns(df: pd.DataFrame) -> dict[str, str]:
    """
    Klasifikasi setiap kolom DataFrame.
    Gunakan heuristik sebagai pre-filter; panggil LLM hanya untuk kolom ambigu.

    Returns:
        dict[str, str] — {nama_kolom: label}
    """
    llm = ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=0,          # Deterministic untuk classifier
        num_predict=64,         # Hanya perlu JSON pendek (thinking dimatikan)
        reasoning=False,        # Matikan <think> Qwen3 — classifier tak butuh nalar.
                                # Tanpa ini, 256 token habis utk think → JSON kosong
                                # → parse-fail → fallback. Ini sumber ~5s/kolom.
    )

    column_profile: dict[str, str] = {}

    for col in df.columns:
        series = df[col]
        heuristic = _heuristic_label(col, series)

        # Kolom yang sudah jelas — skip LLM (hemat ~70% waktu)
        if heuristic in ("datetime", "kategorik", "id_kolom"):
            # Nama match ID patterns → sudah pasti, langsung assign
            if heuristic == "id_kolom" and ID_NAME_PATTERNS.search(col.lower()):
                column_profile[col] = "id_kolom"
                logger.debug(f"[heuristic-name] {col} → id_kolom")
                continue
            # Kardinalitas tinggi → ID
            if heuristic == "id_kolom":
                column_profile[col] = "id_kolom"
                logger.debug(f"[heuristic-cardinality] {col} → id_kolom")
                continue
            # Datetime atau kategorik jelas
            column_profile[col] = heuristic
            logger.debug(f"[heuristic] {col} → {heuristic}")
            continue

        # Kolom ambigu (numerik_valid dari heuristik) → panggil LLM
        sample_values = series.dropna().head(5).tolist()

        prompt = f"""You are a data column classifier. Classify the column below into exactly one of these roles:
- "numerik_valid"  : meaningful numeric metric (e.g. price, score, age, count, percentage)
- "id_kolom"       : identifier or code column (e.g. NIM, CustomerID, invoice number, zip code)
- "kategorik"      : categorical/nominal variable (e.g. gender, country, status, year as category)
- "datetime"       : date or time column

Column name : {col}
Pandas dtype: {str(series.dtype)}
Sample values: {sample_values}

Respond with ONLY a JSON object, nothing else:
{{"label": "<one of the four roles above>"}}"""

        try:
            response = llm.invoke(prompt)
            raw = response.content if hasattr(response, "content") else str(response)
            label = _extract_json_label(raw)

            if label:
                column_profile[col] = label
                logger.debug(f"[llm] {col} → {label}")
            else:
                column_profile[col] = heuristic
                logger.warning(
                    f"[llm-parse-fail] {col} → fallback: {heuristic} | raw: {raw[:80]}"
                )

        except Exception as exc:
            column_profile[col] = heuristic
            logger.warning(f"[llm-error] {col} → fallback: {heuristic} | {exc}")

    logger.info(f"Column profile complete: {column_profile}")
    return column_profile


# ── Utility: filter kolom berdasarkan profil ──────────────────────────────

def get_numeric_columns(column_profile: dict) -> list[str]:
    """Kembalikan hanya kolom berlabel 'numerik_valid'."""
    return [col for col, label in column_profile.items() if label == "numerik_valid"]


def get_categorical_columns(column_profile: dict) -> list[str]:
    """Kembalikan kolom berlabel 'kategorik'."""
    return [col for col, label in column_profile.items() if label == "kategorik"]


def get_id_columns(column_profile: dict) -> list[str]:
    """Kembalikan kolom berlabel 'id_kolom' (di-exclude dari analisis)."""
    return [col for col, label in column_profile.items() if label == "id_kolom"]


# ── Domain Detection ──────────────────────────────────────────────────────

def detect_domain(
    column_names: list[str],
    sample_rows: list[dict],
    llm: ChatOllama,
) -> dict:
    """
    Deteksi domain bisnis dataset berdasarkan nama kolom dan sampel data.
    Menggunakan heuristik regex sebagai pre-filter (total score ≥2 = confident),
    kemudian memanggil LLM hanya jika skor heuristik tidak konklusif.

    Scoring:
      - Column name hit  → +1.0 per regex match
      - Sample value hit → +1.0 per unique pattern term that appears at least once
                           (tiap term dalam alternasi regex dihitung terpisah)

    Args:
        column_names: Daftar nama kolom DataFrame.
        sample_rows:  Sampel baris data (list of dict, maks 5 baris).
        llm:          Instance ChatOllama yang sudah dikonfigurasi.

    Returns:
        dict dengan keys: domain_type, preferred_aggregation, metric_note, avoid
    """
    # Score from column names (weight 1.0 per match)
    col_text = " ".join(column_names)
    scores: dict[str, float] = {domain: 0.0 for domain in _DOMAIN_HINTS}
    for domain, pattern in _DOMAIN_HINTS.items():
        scores[domain] += len(pattern.findall(col_text))

    # Score from sample row values: +1.0 per unique term that matches at least once
    if sample_rows:
        row_text = " ".join(
            str(v).lower()
            for row in sample_rows
            for v in (row.values() if isinstance(row, dict) else row)
            if v is not None
        )
        for domain, pattern in _DOMAIN_HINTS.items():
            m = re.search(r'\(([^()]+)\)', pattern.pattern)
            terms = m.group(1).split('|') if m else []
            scores[domain] += sum(
                1 for term in terms
                if re.search(r'\b' + re.escape(term) + r'\b', row_text, re.IGNORECASE)
            )

    best_domain = max(scores, key=lambda d: scores[d])
    best_score = scores[best_domain]

    if best_score >= 2:
        logger.info(f"[detect_domain] heuristic → {best_domain} (score={best_score:.1f})")
        return {"domain_type": best_domain, **_DOMAIN_CONFIG[best_domain]}

    # Low-confidence heuristic → call LLM to confirm
    sample_preview = str(sample_rows[:3]) if sample_rows else "N/A"
    prompt = f"""You are a business domain classifier for datasets.
Given the column names and sample data below, classify the dataset into ONE of these domains:
- "retail"     : e-commerce, sales transactions, inventory, products
- "finance"    : banking, transactions, accounts, payments, loans
- "hr"         : human resources, employees, salaries, departments
- "healthcare" : medical, patients, diagnoses, treatments
- "education"  : students, grades, courses, academic performance
- "general"    : none of the above

Column names: {column_names}
Sample data (first 3 rows): {sample_preview}

Respond with ONLY a JSON object:
{{"domain": "<one of the six domains above>"}}"""

    try:
        response = llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        raw_clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        match = re.search(r'\{[^{}]*"domain"\s*:\s*"([^"]+)"[^{}]*\}', raw_clean)
        if match:
            detected = match.group(1).strip().lower()
            if detected in VALID_DOMAINS:
                logger.info(f"[detect_domain] llm → {detected}")
                return {"domain_type": detected, **_DOMAIN_CONFIG[detected]}
        logger.warning(f"[detect_domain] llm parse failed, raw: {raw[:80]}")
    except Exception as exc:
        logger.warning(f"[detect_domain] llm error: {exc}")

    logger.info("[detect_domain] fallback → general")
    return {"domain_type": "general", **_DOMAIN_CONFIG["general"]}
