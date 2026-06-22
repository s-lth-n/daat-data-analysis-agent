"""
tools/narrative_generator.py
Constrained narrative generation for data analysis reports.

Uses Ollama grammar-constrained decoding (format=JSON schema) via NarrativeSchema.
The grammar only enforces JSON STRUCTURE (all fields are strings/List[str]; there
are no numeric fields), so it makes the output parseable but does NOT validate
numeric correctness. Number hallucinations are caught downstream by the redaction
layer (_redact_unverified_numbers). If JSON parsing fails for any reason, falls
back to free-form generation (original behaviour).
"""

import json
import logging
import re
from typing import Any, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from agents.prompts import get_system_prompt
from config import settings
from tools.statistics import format_stats_as_text

logger = logging.getLogger(__name__)


# ── Schema ───────────────────────────────────────────────────────────────────

class NarrativeSchema(BaseModel):
    # Field descriptions kept language-NEUTRAL (English-meta) so they do not pull
    # Qwen3 toward Indonesian when the report language is English (Commit A:
    # anti language-bleed). Paired fields still name their target language because
    # the schema is bilingual by design (Opsi A); only the rendered side is emitted.
    judul: str = Field(
        description="Short analysis title, max 10 words, in the report language."
    )
    ringkasan_id: str = Field(
        description=(
            "Executive summary, 2-3 sentences, written in Indonesian. "
            "Use EXACT numbers from STATS_CONTEXT; do not fabricate numbers."
        )
    )
    ringkasan_en: str = Field(
        description=(
            "Executive summary, 2-3 sentences, written in English. "
            "Use EXACT numbers from STATS_CONTEXT; do not fabricate numbers."
        )
    )
    temuan_utama: List[str] = Field(
        description=(
            "List of 3-5 key findings, written in Indonesian. "
            "Each finding must cite specific numbers from STATS_CONTEXT."
        )
    )
    key_findings: List[str] = Field(
        description=(
            "List of 3-5 key findings, written in English. "
            "Each finding must cite specific numbers from STATS_CONTEXT."
        )
    )
    domain_note: Optional[str] = Field(
        default=None,
        description=(
            "Optional domain interpretation note (e.g., revenue trend, rate per capita), "
            "written in the report language. Leave empty if not relevant."
        ),
    )
    kesimpulan_id: str = Field(
        description="Conclusion, 1-2 sentences, written in Indonesian."
    )
    conclusion_en: str = Field(
        description="Conclusion, 1-2 sentences, written in English."
    )


# ── Stats Context Builder ─────────────────────────────────────────────────────

# Diagnosa #5 (Commit B): kolom "harga satuan". Σ harga satuan = nonsens bisnis
# (mis. Σ Price 163.401 yang dulu disalahartikan LLM sebagai "total penjualan").
# Substring SAMA dengan _find_numeric(("price","harga","unitprice")) di
# groupby_analyzer agar deteksi konsisten lintas modul.
_PRICE_LIKE_KEYS = ("price", "harga", "unitprice")


def _is_price_like(col: str) -> bool:
    """True bila nama kolom menandakan harga satuan (price/harga/unitprice)."""
    c = (col or "").lower()
    return any(k in c for k in _PRICE_LIKE_KEYS)


def _build_stats_context(stats_result: dict) -> str:
    """
    Format stats_result dict into a structured reference string for prompt injection.

    Handles keys that may be present in state["statistics"]:
      - descriptive / numeric_stats : per-column numeric stats
      - categorical_stats           : per-column categorical summaries
      - total_rows                  : overall row count
      - cleaning_report             : data cleaning summary
      - correlation                 : skipped (not number-reference-worthy)
      - error                       : skipped
      - any other key               : included verbatim
    """
    lines = ["=== STATS_CONTEXT (gunakan angka-angka ini PERSIS, jangan ubah) ==="]

    # ── Numeric / descriptive stats ──
    descriptive: dict = (
        stats_result.get("descriptive")
        or stats_result.get("numeric_stats")
        or {}
    )
    for col, s in descriptive.items():
        if not isinstance(s, dict):
            continue
        parts: list[str] = []
        if s.get("total_sum") is not None:
            parts.append(f"total={s['total_sum']}")
        for key in ("mean", "median", "std", "min", "max"):
            if s.get(key) is not None:
                parts.append(f"{key}={s[key]}")
        if s.get("q25") is not None:
            parts.append(f"q25={s['q25']}")
        if s.get("q75") is not None:
            parts.append(f"q75={s['q75']}")
        if s.get("count") is not None:
            parts.append(f"count={s['count']}")
        line = f"[{col}]  {' | '.join(parts)}"
        # Diagnosa #5 (Commit B): LABEL (bukan suppress) Σ untuk kolom harga satuan.
        # Angka total= tetap ada; penanda mengarahkan LLM agar TIDAK menyebutnya
        # sebagai "total penjualan" (metrik penjualan = Revenue di blok BREAKDOWN).
        if _is_price_like(col) and s.get("total_sum") is not None:
            line += (
                f" (NOTE: Σ {col} is NOT a sales total; "
                f"sales total = Revenue in the BREAKDOWN block)"
            )
        lines.append(line)

    # ── Categorical stats ──
    categorical: dict = stats_result.get("categorical_stats") or {}
    for col, s in categorical.items():
        if not isinstance(s, dict):
            continue
        top_values: dict = s.get("top_values") or {}
        if top_values:
            top_key = next(iter(top_values))
            top_count = top_values[top_key]
            total_count = sum(top_values.values())
            top_pct = round(top_count / total_count * 100, 1) if total_count > 0 else 0
            unique = s.get("unique_count", "?")
            lines.append(f"[{col}]   top={top_key} ({top_pct}%) | unique={unique}")

    # ── Total rows ──
    total_rows = stats_result.get("total_rows")
    if total_rows is not None:
        lines.append(f"[Total Records] {total_rows} rows")

    # ── Cleaning report ──
    cleaning: dict = stats_result.get("cleaning_report") or {}
    if cleaning.get("cleaned_rows"):
        removed = cleaning.get("rows_removed", 0)
        lines.append(
            f"[After Cleaning] {cleaning['cleaned_rows']} rows remain "
            f"({removed} removed)"
        )

    # ── Unknown keys — include verbatim ──
    _skip = {"descriptive", "numeric_stats", "categorical_stats",
              "total_rows", "cleaning_report", "correlation", "error",
              "__followup_context__"}
    for key, val in stats_result.items():
        if key not in _skip:
            lines.append(f"[{key}] {val}")

    # ── Correlation (strong pairs only, |r|>0.7) ──
    try:
        corr_data = stats_result.get("correlation", {})
        strong = corr_data.get("strong_correlations", [])
        if strong:
            corr_lines = []
            for item in strong:
                col1 = item.get("col1", "")
                col2 = item.get("col2", "")
                r_val = item.get("correlation", 0)
                strength = item.get("strength", "")
                corr_lines.append(
                    f"{col1} vs {col2}: r={r_val:.2f} ({strength})"
                )
            lines.append(
                "KORELASI SIGNIFIKAN (|r|>0.7): " + " | ".join(corr_lines)
            )
    except Exception:
        pass

    # ── Improve #5: GROUP BY follow-up context ──
    followup_ctx = stats_result.get("__followup_context__", "")
    if followup_ctx:
        lines.append("")          # blank line separator
        lines.append(followup_ctx)
    # ── End Improve #5 ─────────────────────────

    return "\n".join(lines)


# ── Schema → String Formatter ─────────────────────────────────────────────────

def _format_narrative_from_schema(schema: NarrativeSchema, language: str = "id") -> str:
    """
    Render a NarrativeSchema as a SINGLE-language, streaming-style narrative.

    Revisi #2 (Opsi A): the schema stays intact (both ID & EN fields exist); this
    renderer only EMITS the side matching `language` and drops every formal section
    heading (no "## Ringkasan/Summary/Temuan Utama/Key Findings/Kesimpulan/Conclusion").
    Output flows like a chat message: concise title → opener sentence → finding
    bullets → optional domain note → short closing line.

    Presentation only — anti-hallucination is untouched: the returned string is fed
    to _redact_unverified_numbers downstream just like before.
    """
    if language == "en":
        opener   = schema.ringkasan_en
        findings = schema.key_findings
        closing  = schema.conclusion_en
    else:
        opener   = schema.ringkasan_id
        findings = schema.temuan_utama
        closing  = schema.kesimpulan_id

    lines: list[str] = []

    if schema.judul:
        lines.append(f"**{schema.judul}**")
        lines.append("")

    if opener:
        lines.append(opener)
        lines.append("")

    for item in findings:
        lines.append(f"- {item}")
    if findings:
        lines.append("")

    if schema.domain_note:
        lines.append(f"📊 {schema.domain_note}")
        lines.append("")

    if closing:
        lines.append(closing)

    return "\n".join(lines).rstrip()


# ── Number Validator ──────────────────────────────────────────────────────────

def _validate_numbers_in_narrative(
    schema: NarrativeSchema,
    stats_result: dict,
) -> tuple[NarrativeSchema, bool, list[str]]:
    """
    Check that numbers cited in temuan_utama / key_findings come from STATS_CONTEXT.

    Tolerance: exact string match OR within 0.01% of any value in the stats context.
    Returns (schema, validation_passed, mismatched_numbers).
    Logs a WARNING when mismatches are found but does NOT block output.
    """
    stats_context = _build_stats_context(stats_result)

    # Whitelist: angka yang tidak perlu divalidasi
    SKIP_PATTERNS = [
        r'^\d{1,3}(?:\.\d{3})+$',   # Format ribuan ID: 100.000, 1.500.000
        r'^100$',                     # 100% selalu valid
        r'^0$',                       # 0 selalu valid
        r'^1\.0+$',                   # 1.0, 1.00 (korelasi perfect)
    ]

    def _should_skip(num_str: str) -> bool:
        for pat in SKIP_PATTERNS:
            if re.fullmatch(pat, num_str.strip()):
                return True
        return False

    # Extract all numeric literals from the stats context for float comparison
    stats_floats: set[float] = set()
    for raw in re.findall(r"\d+\.?\d*", stats_context):
        try:
            stats_floats.add(float(raw))
        except ValueError:
            pass

    all_text = " ".join(schema.temuan_utama + schema.key_findings)
    mismatched: list[str] = []

    for num_str in re.findall(r"\d+\.?\d*", all_text):
        if _should_skip(num_str):
            continue
        # Fast path: exact string appears somewhere in stats_context
        if num_str in stats_context:
            continue
        # Slow path: numeric proximity within 0.01%
        try:
            num = float(num_str)
            within = any(
                abs(num - sn) / max(abs(sn), 1e-10) < 0.0001
                for sn in stats_floats
            )
            if not within:
                mismatched.append(num_str)
        except ValueError:
            mismatched.append(num_str)

    validation_passed = len(mismatched) == 0
    if not validation_passed:
        logger.warning(
            "[narrative_validator] %d numbers not found in STATS_CONTEXT: %s",
            len(mismatched),
            mismatched[:5],
        )
    return schema, validation_passed, mismatched


# ── Domain metric_note language selector (Commit A: anti language-bleed) ──────

def _select_metric_note(domain_ctx: dict, language: str) -> Optional[str]:
    """Pilih varian metric_note sesuai bahasa laporan untuk dicegah dari bleed.

    language=='en' → 'metric_note_en' bila tersedia; selain itu fallback ke
    'metric_note' (ID). Tidak pernah raise — domain tak terdefinisi / dict kosong
    → kembalikan metric_note ID bila ada, atau None.
    """
    try:
        if not isinstance(domain_ctx, dict):
            return None
        if language == "en":
            return domain_ctx.get("metric_note_en") or domain_ctx.get("metric_note")
        return domain_ctx.get("metric_note")
    except Exception:
        return domain_ctx.get("metric_note") if isinstance(domain_ctx, dict) else None


# ── Internal: Constrained Generation ─────────────────────────────────────────

def _constrained_narrative(state: dict, language: str) -> str:
    """
    Primary path: grammar-constrained JSON generation via Ollama format parameter.
    Raises on any failure so caller can fall back to free-form.
    """
    statistics: dict = state.get("statistics") or {}
    stats_context = _build_stats_context(statistics)

    # Build human-message content
    parts: list[str] = [stats_context]
    parts.append(f"\nUser query: {state.get('prompt', '')}")

    if state.get("data_summary"):
        parts.append(f"\nData summary: {state['data_summary']}")

    cleaning: dict = state.get("cleaning_report") or {}
    if cleaning.get("rows_removed", 0) > 0 or cleaning.get("steps"):
        parts.append(
            f"\nData was pre-processed: "
            f"{cleaning.get('original_rows', '?')} → {cleaning.get('cleaned_rows', '?')} rows "
            f"({cleaning.get('rows_removed', 0)} removed). "
            "Do NOT recommend further data cleaning."
        )

    corr: dict = statistics.get("correlation") or {}
    strong_corrs: list = corr.get("strong_correlations") or []
    if strong_corrs:
        corr_lines = "\n".join(
            f"  - {c['col1']} ↔ {c['col2']}: r={c['correlation']} ({c['strength']})"
            for c in strong_corrs
        )
        parts.append(f"\nStrong correlations:\n{corr_lines}")

    domain_ctx: dict = state.get("domain_context") or {}
    _metric_note = _select_metric_note(domain_ctx, language)
    if _metric_note:
        parts.append(f"\nDomain guidance: {_metric_note}")

    human_content = "\n".join(parts)

    # Revisi #2: single-language. Hanya minta LLM menulis SATU bahasa sesuai
    # `language` (hemat token + cegah Qwen3 thinking berlebih). Schema TETAP utuh
    # (Opsi A): field bahasa-lawan tetap ada tapi tidak dirender (lihat
    # _format_narrative_from_schema). Instruksi anti-mengarang-angka tetap ada.
    if language == "id":
        system_content = (
            "Kamu adalah analis data expert. Tulis laporan analisis dalam BAHASA "
            "INDONESIA saja berdasarkan statistik yang diberikan.\n"
            "WAJIB: Gunakan angka PERSIS dari blok STATS_CONTEXT. "
            "JANGAN mengarang angka yang tidak ada di STATS_CONTEXT.\n"
            "Fokuskan isi pada field Bahasa Indonesia (ringkasan_id, temuan_utama, "
            "kesimpulan_id) — minimal 3 temuan. Isi field lain seperlunya.\n"
            "Jika mengisi domain_note, tulis dalam BAHASA INDONESIA."
        )
    else:
        system_content = (
            "You are a data analysis expert. Write an analysis report in ENGLISH "
            "only based on the provided statistics.\n"
            "MANDATORY: Use ONLY exact numbers from the STATS_CONTEXT block. "
            "Do NOT fabricate numbers absent from STATS_CONTEXT.\n"
            "Focus on the English fields (ringkasan_en, key_findings, conclusion_en) "
            "— at least 3 findings. Fill the other fields minimally.\n"
            "If you fill domain_note, write it in ENGLISH."
        )

    llm_structured = ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        format=NarrativeSchema.model_json_schema(),
        temperature=0.3,
        reasoning=False,        # Matikan <think> Qwen3. Output sudah dibatasi
                                # JSON-schema + STATS_CONTEXT, jadi thinking hanya
                                # menambah ~15-25s tanpa menambah kualitas.
    )

    response = llm_structured.invoke([
        SystemMessage(content=system_content),
        HumanMessage(content=human_content),
    ])

    # Strip <think>...</think> blocks — Qwen3 thinking mode can leak these
    content = re.sub(
        r"<think>.*?</think>", "", response.content, flags=re.DOTALL
    ).strip()

    parsed = NarrativeSchema.model_validate(json.loads(content))

    # Optional: validate that cited numbers come from the injected stats
    _, validation_passed, mismatched = _validate_numbers_in_narrative(parsed, statistics)
    if not validation_passed:
        logger.warning(
            "[narrative_validator] Numbers possibly not from STATS_CONTEXT: %s",
            mismatched[:5],
        )

    return _format_narrative_from_schema(parsed, language)


# ── Internal: Free-Form Fallback ──────────────────────────────────────────────

def _free_form_narrative(state: dict, language: str) -> str:
    """
    Fallback free-form narrative generation (original behaviour from data_agent.py).
    Called only when constrained generation fails.
    """
    llm = ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=settings.llm_temperature,
        num_predict=settings.llm_max_tokens,
        reasoning=False,        # Konsisten dgn jalur constrained — tanpa <think>.
    )

    context_parts: list[str] = [state.get("prompt", "")]

    if state.get("data_summary"):
        context_parts.append(f"\n--- Data Summary ---\n{state['data_summary']}")

    cleaning: dict = state.get("cleaning_report") or {}
    rows_removed = cleaning.get("rows_removed", 0)
    steps: list = cleaning.get("steps", [])
    if rows_removed > 0 or steps:
        steps_text = (
            "\n".join(f"  - {s['detail']}" for s in steps)
            if steps
            else (
                "  (tidak ada baris yang dihapus)"
                if language == "id"
                else "  (no rows removed)"
            )
        )
        if language == "id":
            context_parts.append(
                f"\n--- Preprocessing Otomatis (Sudah Selesai) ---\n"
                f"Data awal: {cleaning.get('original_rows', '?')} baris → "
                f"Data bersih: {cleaning.get('cleaned_rows', '?')} baris\n"
                f"Baris dihapus: {rows_removed} baris "
                f"({cleaning.get('rows_removed_pct', 0)}% dari total)\n"
                f"Alasan penghapusan baris:\n{steps_text}\n\n"
                "PENTING: Jangan rekomendasikan pembersihan data lagi — "
                "preprocessing sudah selesai. Fokus HANYA pada insight bisnis."
            )
        else:
            context_parts.append(
                f"\n--- Automatic Preprocessing (Already Completed) ---\n"
                f"Original: {cleaning.get('original_rows', '?')} rows → "
                f"Cleaned: {cleaning.get('cleaned_rows', '?')} rows\n"
                f"Rows removed: {rows_removed} rows "
                f"({cleaning.get('rows_removed_pct', 0)}% of total)\n"
                f"Reasons for row removal:\n{steps_text}\n\n"
                "IMPORTANT: Do NOT recommend data cleaning — preprocessing is already done. "
                "Focus ONLY on business insights from the clean data."
            )

    statistics: dict = state.get("statistics") or {}
    descriptive: dict = statistics.get("descriptive") or {}
    if descriptive and "error" not in descriptive:
        stats_text = format_stats_as_text(descriptive, language=language)
        context_parts.append(f"\n--- Statistics ---\n{stats_text}")
        logger.info("Stats injected to fallback prompt: %s", stats_text[:200])
        if language == "id":
            context_parts.append(
                "\n⚠️ INSTRUKSI WAJIB — PENGGUNAAN ANGKA:\n"
                "Gunakan HANYA angka yang tercantum di blok '--- Statistics ---' di atas "
                "(mean, median, min, max, std, q25, q75). "
                "JANGAN mengarang, memperkirakan, atau menulis angka yang tidak ada di sana. "
                "Jika kamu menyebut suatu angka dalam analisis, angka tersebut HARUS "
                "identik dengan yang ada di statistics di atas."
            )
        else:
            context_parts.append(
                "\n⚠️ MANDATORY INSTRUCTION — NUMBER USAGE:\n"
                "Use ONLY the numbers listed in the '--- Statistics ---' block above "
                "(mean, median, min, max, std, q25, q75). "
                "Do NOT fabricate, estimate, or write any number that is not present there. "
                "Any number you cite in your analysis MUST be identical to one "
                "from the statistics block above."
            )

    corr: dict = statistics.get("correlation") or {}
    strong_corrs: list = corr.get("strong_correlations") or []
    if strong_corrs:
        corr_text = "\n".join(
            f"- {c['col1']} ↔ {c['col2']}: r={c['correlation']} ({c['strength']})"
            for c in strong_corrs
        )
        context_parts.append(f"\n--- Strong Correlations ---\n{corr_text}")

    # Chart awareness
    existing_urls: list = state.get("existing_chart_urls") or []
    chart_dicts: list = state.get("charts") or []
    if existing_urls:
        url_list = "\n".join(f"  - {u}" for u in existing_urls)
        if language == "id":
            context_parts.append(
                f"\n--- Grafik Tersedia (URL Resmi) ---\n"
                f"Grafik berikut sudah dirender dan akan otomatis ditampilkan setelah teks:\n"
                f"{url_list}\n\n"
                "PENTING: JANGAN tulis URL gambar, path PNG, atau sintaks ![...](...) "
                "di dalam teks analisis."
            )
        else:
            context_parts.append(
                f"\n--- Available Charts (Official URLs) ---\n"
                f"The following charts have been rendered and will be shown automatically after the text:\n"
                f"{url_list}\n\n"
                "IMPORTANT: Do NOT write any image URLs, PNG paths, or ![...](...) syntax "
                "in your analysis text."
            )
    elif chart_dicts:
        titles = [
            c.get("layout", {}).get("title", {}).get("text", "")
            for c in chart_dicts
            if isinstance(c, dict)
            and c.get("layout", {}).get("title", {}).get("text")
        ]
        title_list = (
            "\n".join(f"  - {t}" for t in titles)
            if titles else "  (grafik tersedia)"
        )
        if language == "id":
            context_parts.append(
                f"\n--- Grafik Yang Dibuat ---\n"
                f"Grafik berikut telah dibuat dan akan ditampilkan otomatis setelah teks:\n"
                f"{title_list}\n\n"
                "PENTING: JANGAN tulis URL gambar, path PNG, atau sintaks ![...](...) "
                "di dalam teks analisis."
            )
        else:
            context_parts.append(
                f"\n--- Charts Generated ---\n"
                f"The following charts have been created and will appear automatically after the text:\n"
                f"{title_list}\n\n"
                "IMPORTANT: Do NOT write any image URLs, PNG paths, or ![...](...) syntax "
                "in your analysis text."
            )
    else:
        context_parts.append(
            "\nPENTING: JANGAN tulis URL gambar, path PNG, atau sintaks ![...](...) "
            "di dalam teks analisis."
            if language == "id" else
            "\nIMPORTANT: Do NOT write any image URLs, PNG paths, or ![...](...) syntax "
            "in your analysis text."
        )

    context = "\n".join(context_parts)

    system_content = get_system_prompt(language)
    domain_ctx: dict = state.get("domain_context") or {}
    _metric_note = _select_metric_note(domain_ctx, language)
    if _metric_note:
        system_content += f"\n\n## Domain Context\n{_metric_note}"
        avoid_items: list = domain_ctx.get("avoid") or []
        if avoid_items:
            avoid_str = "\n".join(f"- {a}" for a in avoid_items)
            system_content += f"\n\nHindari dalam analisis:\n{avoid_str}"
        if domain_ctx.get("preferred_aggregation") != "sum":
            system_content += (
                "\n\nPENTING: Ingatkan pengguna bahwa perbandingan antar lokasi/wilayah "
                "harus menggunakan rate yang sudah dinormalisasi (per 100.000 penduduk "
                "atau age-adjusted), bukan angka absolut. Sertakan peringatan ini di "
                "bagian Perbandingan Antar Lokasi."
            )

    response = llm.invoke([
        SystemMessage(content=system_content),
        HumanMessage(content=context),
    ])
    return response.content


# ── Number Redactor (Fase 1.7) ─────────────────────────────────────────────────
# Validator lama hanya MENCATAT angka nyasar. Redactor ini AKTIF membuang angka
# di prosa LLM yang tidak terverifikasi dari data (ganti "[?]"), TANPA menebak-
# ganti dgn angka lain. Angka otoritatif tetap ada di blok deterministik (groupby)
# + STATS_CONTEXT. Canonicalisasi ID/EN dipakai utk KEDUA sisi → format beda match.

_NUM_TOKEN_RE = re.compile(r"\d[\d.,]*\d|\d")


def _canonical_number(token: str):
    """Normalisasi token angka (format ID/EN) → float, atau None bila gagal.
    Dipakai konsisten utk sumber-sah & narasi, jadi '163.401,02' (ID),
    '163,401.02' (EN), dan '163401.02' (polos) semuanya jadi nilai sama."""
    s = (token or "").strip()
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):          # ID: 1.634.010,02
            s = s.replace(".", "").replace(",", ".")
        else:                                     # EN: 1,634,010.02
            s = s.replace(",", "")
    elif "," in s:
        if re.fullmatch(r"\d{1,3}(,\d{3})+", s):  # EN ribuan: 1,634
            s = s.replace(",", "")
        elif re.fullmatch(r"\d+,\d{1,2}", s):     # ID desimal: 18,90
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):  # ID ribuan: 163.401
            s = s.replace(".", "")
        # else desimal biasa (18.9 / 163401.02) — biarkan
    try:
        return float(s)
    except ValueError:
        return None


def _collect_valid_number_text(state: dict) -> str:
    """Kumpulkan semua sumber angka SAH dari state: STATS_CONTEXT (incl. blok
    groupby __followup_context__), seluruh dict statistik (angka bersarang spt
    original_rows), cleaning_report, dan data_summary."""
    parts: list = []
    stats = state.get("statistics") or {}
    try:
        parts.append(_build_stats_context(stats))
    except Exception:
        pass
    parts.append(repr(stats))
    parts.append(repr(state.get("cleaning_report") or {}))
    if state.get("data_summary"):
        parts.append(str(state["data_summary"]))
    return "\n".join(parts)


def _is_safe_narrative_number(token: str, value: float) -> bool:
    """Angka yang SELALU aman (tak diredaksi): tahun, 0/100/1.0, integer kecil
    (ordinal/top-N/bulan/list ≤31)."""
    if re.fullmatch(r"(?:19|20)\d{2}", token):
        return True
    if value in (0.0, 100.0, 1.0):
        return True
    if re.fullmatch(r"\d{1,2}", token) and 0 <= value <= 31:
        return True
    return False


def _redact_unverified_numbers(narrative: str, state: dict, language: str = "id"):
    """
    Buang angka pada prosa LLM yang TIDAK terverifikasi dari data → ganti '[?]'.
    TIDAK menebak-ganti dgn angka lain. Returns (narasi_bersih, jumlah_redaksi).
    SKIP_PATTERNS (tahun, persen penuh, integer kecil) + canonicalisasi ID/EN
    menjaga angka SAH (mis. ribuan ID 163.401,02) tidak ikut terbuang.
    """
    if not narrative:
        return narrative, 0
    valid_text = _collect_valid_number_text(state)
    valid_vals = [
        v for v in (_canonical_number(t) for t in _NUM_TOKEN_RE.findall(valid_text))
        if v is not None
    ]

    def _matches(value: float) -> bool:
        for sv in valid_vals:
            if abs(value - sv) <= max(abs(sv), 1.0) * 0.001:  # 0.1% toleransi format/bulat
                return True
        return False

    counter = {"n": 0}

    def _repl(m):
        token = m.group(0)
        value = _canonical_number(token)
        if value is None:
            return token
        if _is_safe_narrative_number(token, value):
            return token
        if _matches(value):
            return token
        counter["n"] += 1
        return "[?]"

    cleaned = _NUM_TOKEN_RE.sub(_repl, narrative)
    if counter["n"]:
        cleaned += (
            "\n\n_⚠️ Catatan: sebagian angka pada narasi dihilangkan ([?]) karena "
            "tidak terverifikasi dari data. Angka resmi ada pada blok perhitungan di atas._"
            if language == "id" else
            "\n\n_⚠️ Note: some figures in the narrative were removed ([?]) as unverified "
            "against the data. Authoritative numbers are in the computed block above._"
        )
    return cleaned, counter["n"]


# ── Public Node ───────────────────────────────────────────────────────────────

def generate_narrative(state: dict) -> dict:
    """
    LangGraph node: generate analysis narrative (constrained JSON → string).

    Primary path uses grammar-constrained Ollama decoding (NarrativeSchema) to
    prevent number hallucination.  Falls back to free-form generation if JSON
    parsing fails for any reason.

    State keys read : prompt, language, statistics, data_summary, cleaning_report,
                      domain_context, charts, existing_chart_urls
    State keys set  : narrative (str), step
    """
    logger.info("[Node: generate_narrative]")
    state = dict(state)
    state["step"] = "generate_narrative"

    language: str = state.get("language", "id")

    try:
        narrative = _constrained_narrative(state, language)
        logger.info("Constrained narrative generated: %d chars", len(narrative))
    except Exception as e:
        logger.warning(
            "WARNING: Constrained generation failed, using fallback. Error: %s", e
        )
        try:
            narrative = _free_form_narrative(state, language)
            logger.info("Fallback narrative generated: %d chars", len(narrative))
        except Exception as e2:
            logger.error("Narrative generation failed entirely: %s", e2)
            narrative = (
                f"Maaf, terjadi kesalahan saat membuat analisis: {e2}"
                if language == "id"
                else f"Sorry, an error occurred during analysis: {e2}"
            )

    # Fase 1.7: redaksi AKTIF angka nyasar (anti-halusinasi-angka), bukan cuma log.
    try:
        narrative, _n_redacted = _redact_unverified_numbers(narrative, state, language)
        if _n_redacted:
            logger.info("[narrative_redactor] redacted %d unverified number(s)", _n_redacted)
    except Exception as _re:
        logger.warning("[narrative_redactor] skipped (kept original): %s", _re)

    state["narrative"] = narrative
    return state
