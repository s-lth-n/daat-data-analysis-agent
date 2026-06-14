"""
TA Data Analysis Agent — FastAPI Backend
=========================================
Agentic AI for local data analysis using Qwen3 8B via Ollama.
All processing runs locally. No cloud. No data leaves the machine.
"""

import logging
import base64
import uuid

from fastapi.responses import FileResponse

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import settings
from session_store import save_session, get_session, make_session_id, SessionData, list_sessions

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Directory for rendered chart images
CHART_DIR = settings.upload_dir.parent / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ─────────────────────────────────────────────────

def _render_charts_to_png(charts: list[dict]) -> list[str]:
    """
    Render Plotly chart specs to PNG files in CHART_DIR.
    Returns list of chart keys (UUID prefix, without '.png' extension).
    Errors per-chart are logged and skipped so other charts still render.
    """
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except ImportError:
        logger.warning("plotly not available — skipping chart render")
        return []

    keys: list[str] = []
    for spec in charts:
        try:
            fig = go.Figure(spec)
            fig.update_layout(template="plotly_white", margin=dict(l=60, r=30, t=50, b=50))
            chart_id = str(uuid.uuid4())[:8]
            filepath = CHART_DIR / f"{chart_id}.png"
            img_bytes = pio.to_image(fig, format="png", width=800, height=500, engine="kaleido")
            filepath.write_bytes(img_bytes)
            keys.append(chart_id)
            logger.info(f"[chart] Rendered → {filepath}")
        except Exception as e:
            logger.warning(f"[chart] Failed to render chart to PNG: {e}")
    return keys


def _chart_caption_md(chart_keys: list[str], language: str = "id") -> str:
    """
    Build markdown captions + images for rendered chart PNGs, in a SINGLE language.

    Revisi #2: the caption word follows `language` ("Grafik" for id, "Chart"
    otherwise — default EN, consistent with the global language default). Numbering
    is omitted when there is exactly one chart. Never bilingual.
    """
    word = "Grafik" if language == "id" else "Chart"
    total = len(chart_keys)
    md = ""
    for i, key in enumerate(chart_keys):
        label = word if total == 1 else f"{word} {i + 1}"
        url = f"{settings.public_url}/chart/image/{key}.png"
        md += f"\n\n**📊 {label}**\n\n![{label}]({url})"
    return md


def _assemble_analysis_response(
    *,
    file_name: str,
    row_count: int,
    narrative: str,
    session_id: str,
    deterministic_block: str = "",
    chart_md: str = "",
    source_note: str = "",
) -> str:
    """
    Rakit balasan analisis dalam SATU urutan presentasi yang dipakai BERSAMA oleh
    /analyze dan /analyze/followup (Revisi #3, Opsi B):

        📄 banner file → blok deterministik (bila ada) → narasi LLM → grafik
        → penanda [SESSION_ID].

    Presentasi MURNI — tidak menghitung/memanggil apa pun. Blok deterministik &
    chart_md dirakit di handler (sumber angka), helper ini hanya menyusun string.
    `source_note` = anotasi banner (mis. "(data dari sesi sebelumnya)" untuk followup;
    kosong untuk analisis pertama).
    """
    banner_suffix = f" {source_note}" if source_note else ""
    det_md = f"{deterministic_block}\n\n---\n\n" if deterministic_block else ""
    return (
        f"📄 **{file_name}** — {row_count} baris{banner_suffix}\n\n"
        f"---\n\n"
        f"{det_md}"
        f"{narrative}"
        f"{chart_md}"
        f"\n\n[SESSION_ID: {session_id}]"
    )


# ── Lifespan ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"LLM Model: {settings.llm_model}")
    logger.info(f"Ollama URL: {settings.ollama_base_url}")

    # Ensure upload directory exists
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    # Verify Ollama connection
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            models = resp.json().get("models", [])
            model_names = [m["name"] for m in models]
            logger.info(f"Ollama models available: {model_names}")
            if not any(settings.llm_model in name for name in model_names):
                logger.warning(
                    f"Model '{settings.llm_model}' not found in Ollama. "
                    f"Run: ollama pull {settings.llm_model}"
                )
    except Exception as e:
        logger.warning(f"Could not connect to Ollama: {e}")
        logger.warning("Make sure Ollama is running: ollama serve")

    yield

    # Shutdown — cleanup temp files
    logger.info("Shutting down... cleaning temporary data")
    # Clean uploaded files (privacy constraint: temp data only)
    for f in settings.upload_dir.glob("*"):
        try:
            f.unlink()
        except Exception:
            pass


# ── App Instance ────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Agentic AI Data Analysis Agent berbasis Local LLM. "
        "Supports CSV/Excel analysis, descriptive statistics, "
        "interactive visualizations, and narrative reports."
    ),
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response Models ─────────────────────────────────
class AnalysisRequest(BaseModel):
    """User analysis request."""
    prompt: str
    language: str = "id"  # "id" or "en"
    file_id: str | None = None


class AnalysisResponse(BaseModel):
    """Analysis result returned to frontend."""
    text: str                           # Narrative analysis
    charts: list[dict] | None = None    # Plotly JSON specs
    statistics: dict | None = None      # Descriptive stats
    language: str = "id"
    session_id: str | None = None       # Session ID for follow-up chat
    chart_keys: list[str] | None = None # Rendered PNG keys (without extension)


class FollowUpRequest(BaseModel):
    """Follow-up chat request reusing an existing session."""
    session_id: str
    query: str
    language: str = "id"


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    llm_model: str
    ollama_connected: bool


class ChartRenderRequest(BaseModel):
    """Request to render a Plotly chart as image."""
    chart_spec: dict
    format: str = "png"
    width: int = 800
    height: int = 500


# ── Endpoints ───────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check system health and Ollama connectivity."""
    ollama_ok = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if ollama_ok else "degraded",
        version=settings.app_version,
        llm_model=settings.llm_model,
        ollama_connected=ollama_ok,
    )


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a data file (CSV or Excel) for analysis.
    Files are stored temporarily and deleted after session ends.
    """
    # Validate extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. "
                   f"Allowed: {settings.allowed_extensions}",
        )

    # Validate size
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.max_file_size_mb:
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {size_mb:.1f}MB. Max: {settings.max_file_size_mb}MB",
        )

    # Save to upload directory
    import uuid
    file_id = str(uuid.uuid4())[:8]
    save_path = settings.upload_dir / f"{file_id}_{file.filename}"
    save_path.write_bytes(contents)

    logger.info(f"File uploaded: {file.filename} ({size_mb:.2f}MB) → {file_id}")

    # Quick preview using data_loader
    try:
        from tools.data_loader import load_and_preview
        preview = load_and_preview(save_path)
    except Exception as e:
        preview = {"error": str(e)}

    return {
        "file_id": file_id,
        "filename": file.filename,
        "size_mb": round(size_mb, 2),
        "path": str(save_path),
        "preview": preview,
    }


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_data(request: AnalysisRequest):
    """
    Main analysis endpoint.
    Receives a natural language prompt and optionally a file_id,
    then uses the LangGraph agent to perform analysis.
    """
    # Revisi #2: deteksi bahasa adaptif = SATU sumber kebenaran. Override
    # request.language (default LLM bisa salah "id") sebelum mengalir ke agent,
    # narasi, chart-label, & response. Default "en" bila ragu/pendek.
    from tools.lang_detect import detect_language
    request.language = detect_language(request.prompt)

    logger.info(f"Analysis request: '{request.prompt[:80]}...' (lang={request.language})")

    try:
        from agents.data_agent import run_analysis_agent
        result = await run_analysis_agent(
            prompt=request.prompt,
            file_id=request.file_id,
            language=request.language,
        )

        session_id: str | None = None
        chart_keys: list[str] = []
        emit_charts = False  # Revisi #1: gerbang chart on-demand (default teks-saja)

        # Save session when a file was analysed and the DataFrame is available
        if request.file_id and result.get("dataframe") is not None:
            matching = list(settings.upload_dir.glob(f"{request.file_id}_*"))
            if matching:
                file_path = matching[0]
                file_name = file_path.name.split("_", 1)[1]   # strip file_id prefix
                file_size = file_path.stat().st_size

                # Render chart specs → PNG files, collect keys for follow-up URLs
                chart_keys = _render_charts_to_png(result.get("charts") or [])

                domain_context = result.get("domain_context")
                domain = (domain_context or {}).get("domain_type", "unknown")
                session_id = make_session_id(file_name, file_size)
                save_session(SessionData(
                    session_id      = session_id,
                    dataframe       = result["dataframe"],
                    column_profile  = result.get("column_profile") or {},
                    stats_result    = result.get("statistics") or {},
                    cleaning_report = result.get("cleaning_report") or {},
                    chart_keys      = chart_keys,
                    file_name       = file_name,
                    domain          = domain,
                    domain_context  = domain_context,   # Revisi #3: dict penuh utk followup
                ))

                # Revisi #1 (chart on-demand): SEMUA chart sudah dirender & disimpan
                # ke session di atas (bisa diminta menyusul via followup). Yang
                # digerbang di sini hanya APAKAH chart ditampilkan di balasan INI —
                # hanya bila user minta eksplisit ATAU intent groupby/temporal.
                try:
                    from tools.chart_intent import wants_chart
                    emit_charts = wants_chart(
                        request.prompt,
                        df=result.get("dataframe"),
                        column_profile=result.get("column_profile") or {},
                    )
                except Exception:
                    emit_charts = False

        # Revisi #3 (Commit 2): saat sebuah file dianalisis, rakit balasan dgn pola
        # yang SAMA dengan followup — blok angka deterministik (sumber otoritatif,
        # 100% Python) MEMIMPIN, lalu narasi LLM dari graph sebagai prosa. Ini yang
        # menggantikan headline Σ Price (163.401) yang menyesatkan dengan metrik benar
        # (mis. Revenue 1.058.314 utk "produk terlaris" retail). Helper presentasi &
        # build_deterministic_block identik dengan /analyze/followup → konsisten.
        if session_id:
            deterministic_block = ""
            try:
                from tools.groupby_analyzer import build_deterministic_block
                _df_clean = result.get("dataframe")
                if _df_clean is not None:
                    # request.prompt mengarahkan metrik/dimensi; domain_context dict
                    # mengaktifkan Revenue-default retail + label unit "transaksi".
                    deterministic_block = build_deterministic_block(
                        _df_clean,
                        request.prompt,
                        result.get("column_profile") or {},
                        result.get("domain_context"),
                        request.language,
                    )
            except Exception as _de:
                # Fallback aman: pertanyaan non-groupby (mis. "ringkas data ini") atau
                # error apa pun → blok kosong → balasan tetap memakai narasi deskriptif.
                logger.warning(f"[analyze] blok deterministik dilewati: {_de}")
                deterministic_block = ""

            # Commit 3 akan mengisi chart on-demand; di Commit 2 balasan = teks+tabel.
            text = _assemble_analysis_response(
                file_name           = file_name,
                row_count           = len(result["dataframe"]),
                narrative           = result["text"],
                session_id          = session_id,
                deterministic_block = deterministic_block,
                chart_md            = "",
                source_note         = "",   # /analyze: banner tanpa "sesi sebelumnya"
            )
        else:
            # Tanpa file (pertanyaan umum) → narasi graph apa adanya, tanpa banner.
            text = result["text"]

        return AnalysisResponse(
            text       = text,
            charts     = result.get("charts") if emit_charts else None,
            statistics = result.get("statistics"),
            language   = request.language,
            session_id = session_id,
            chart_keys = (chart_keys or None) if emit_charts else None,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@app.post("/chart/render")
async def render_chart(request: ChartRenderRequest):
    """
    Render a Plotly chart spec to a PNG image file.
    Returns a URL path to access the image.
    """
    try:
        import plotly.graph_objects as go
        import plotly.io as pio

        fig = go.Figure(request.chart_spec)
        fig.update_layout(
            width=request.width,
            height=request.height,
            template="plotly_white",
            margin=dict(l=60, r=30, t=50, b=50),
        )

        # Generate unique filename
        import uuid as _uuid
        chart_id = str(_uuid.uuid4())[:8]
        filename = f"{chart_id}.{request.format}"
        filepath = CHART_DIR / filename

        # Render and save
        img_bytes = pio.to_image(
            fig,
            format=request.format,
            width=request.width,
            height=request.height,
            engine="kaleido",
        )
        filepath.write_bytes(img_bytes)

        logger.info(f"Chart rendered: {filepath} ({len(img_bytes)} bytes)")

        return {
            "image_url": f"{settings.public_url}/chart/image/{filename}",
            "chart_id": chart_id,
            "format": request.format,
        }

    except ImportError as e:
        raise HTTPException(500, f"Missing: kaleido. Run: pip install kaleido==0.2.1")
    except Exception as e:
        logger.error(f"Chart render failed: {e}", exc_info=True)
        raise HTTPException(500, f"Chart render error: {str(e)}")


@app.get("/chart/image/{filename}")
async def get_chart_image(filename: str):
    """Serve a rendered chart image."""
    filepath = CHART_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, "Chart not found")

    media = "image/png" if filename.endswith(".png") else "image/svg+xml"
    return FileResponse(filepath, media_type=media)


@app.post("/analyze/followup")
async def analyze_followup(req: FollowUpRequest):
    """
    Follow-up analisis tanpa upload file ulang.
    Menggunakan session yang sudah ada: skip 4 node berat
    (load_data, clean_data, profile_columns, compute_statistics, visualization)
    dan hanya re-run generate_narrative dengan query baru.
    """
    import asyncio
    from tools.data_loader import get_data_summary
    from agents.data_agent import generate_narrative, AgentState

    session = get_session(req.session_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "session_not_found",
                "message": (
                    "Sesi analisis tidak ditemukan atau sudah expired (TTL 2 jam). "
                    "Silakan upload ulang file dan mulai analisis baru."
                ),
                "session_id": req.session_id,
            },
        )

    # Guard against corrupt / incomplete session state
    if session.dataframe is None or not session.file_name or session.column_profile is None:
        return JSONResponse(
            status_code=422,
            content={
                "error": "session_corrupt",
                "message": "Data sesi tidak lengkap. Silakan mulai analisis baru.",
                "session_id": req.session_id,
            },
        )

    # Revisi #2: deteksi bahasa adaptif (single source of truth) — override
    # req.language sebelum mengalir ke state narasi, chart spec, & label grafik.
    from tools.lang_detect import detect_language
    req.language = detect_language(req.query)

    logger.info(f"[followup] session={req.session_id} query={req.query[:60]!r} (lang={req.language})")

    # Revisi #1 (chart on-demand): tentukan DULU apakah balasan ini menampilkan
    # grafik — hanya bila user minta eksplisit ATAU intent groupby/temporal.
    # Dipakai untuk MENGGERBANGI chart_md DI BAWAH sekaligus menjaga narasi tetap
    # jujur: kalau chart tak ditampilkan, jangan beri tahu LLM "grafik akan tampil".
    try:
        from tools.chart_intent import wants_chart
        show_charts = wants_chart(
            req.query,
            df=session.dataframe,
            column_profile=session.column_profile,
        )
    except Exception:
        show_charts = False

    # Revisi #1 Phase 2: pilih chart yang DITAMPILKAN. Untuk intent groupby/temporal,
    # bangun SATU chart RELEVAN dari data recompute (nilai per-grup SAMA dengan blok
    # deterministik karena memakai _resolve_followup_aggregation yang sama). Selain itu
    # (mis. minta grafik eksplisit TANPA intent groupby/temporal) atau bila pembuatan
    # gagal → fallback ke chart overview cache (session.chart_keys). Render via
    # _render_charts_to_png + emisi via _stash_report/outlet (BUKAN event_emitter).
    chart_keys_to_show: list[str] = list(session.chart_keys or []) if show_charts else []
    if show_charts:
        try:
            from tools.groupby_analyzer import build_followup_chart_spec
            spec = build_followup_chart_spec(
                session.dataframe,
                req.query,
                session.column_profile or {},
                session.domain_context,
                language=req.language,
            )
            if spec:
                rendered = _render_charts_to_png([spec])
                if rendered:
                    chart_keys_to_show = rendered   # chart relevan MENGGANTIKAN cache
        except Exception as _ce:
            logger.warning(f"[followup] relevant-chart gagal, fallback cache: {_ce}")
            # chart_keys_to_show tetap = overview cache (fallback aman, tak crash)

    # Build a minimal AgentState compatible with generate_narrative()
    state: AgentState = {
        "prompt":               req.query,
        "file_id":              None,
        "language":             req.language,
        "file_path":            None,
        "dataframe_loaded":     True,
        "dataframe":            session.dataframe,
        "data_summary":         get_data_summary(session.dataframe),
        "column_profile":       session.column_profile,
        "cleaning_report":      session.cleaning_report,
        "statistics":           session.stats_result,
        "charts":               None,
        "narrative":            None,
        "error":                None,
        "step":                 "followup",
        # Pre-rendered chart URLs — generate_narrative uses these to tell the
        # LLM which charts exist and to forbid inventing new PNG URLs.
        # On-demand: kosongkan bila chart tidak ditampilkan, supaya narasi tidak
        # menjanjikan grafik yang tak ada.
        "existing_chart_urls":  (
            [f"{settings.public_url}/chart/image/{k}.png" for k in chart_keys_to_show]
            if show_charts else []
        ),
    }

    # ── Improve #5: Targeted re-computation GROUP BY (+ anti-halusinasi) ──
    # build_followup_context() mengembalikan SALAH SATU dari:
    #   (a) tabel breakdown angka NYATA (intent groupby terdeteksi & terhitung),
    #   (b) instruksi jujur "tidak tersedia, dilarang mengarang" (segmentasi
    #       diminta tapi kolom tak dikenali), atau
    #   (c) "" (pertanyaan non-segmentasi → pakai statistik biasa).
    # Semuanya dibungkus try/except di dalam helper → tak pernah block followup.
    deterministic_block = ""  # Fase 1.7: angka kunci groupby langsung dari Python
    try:
        from tools.groupby_analyzer import build_followup_context, build_deterministic_block
        _df     = session.dataframe
        _prof   = session.column_profile or {}
        _domain = session.domain_context

        if _df is not None:
            _ctx = build_followup_context(_df, req.query, _prof, _domain)
            if _ctx and state.get("statistics") is not None:
                state["statistics"]["__followup_context__"] = _ctx
            # Blok angka OTORITATIF (nilai+persen dihitung di Python, bukan LLM).
            # Revisi #2: tabel markdown, header kolom hormati bahasa terdeteksi.
            deterministic_block = build_deterministic_block(
                _df, req.query, _prof, _domain, req.language
            )
    except Exception as _e:
        pass  # Improve #5 graceful fallback — tidak boleh block followup
    # ── End Improve #5 ───────────────────────────────────────────────────

    # generate_narrative is sync + calls LLM → run in thread to avoid blocking
    result_state = await asyncio.to_thread(generate_narrative, state)
    narrative = result_state.get("narrative", "")

    # Build chart markdown using previously rendered PNGs (reuse, no re-render).
    # Revisi #1 (chart on-demand): HANYA tempel grafik bila show_charts True
    # (minta eksplisit ATAU intent groupby/temporal). Selain itu → teks-saja;
    # inilah yang menghentikan "grafik identik berulang" di tiap followup.
    # Fallback (keputusan final): minta-eksplisit-tanpa-intent-groupby tetap
    # menampilkan chart overview cache (session.chart_keys), bukan teks/eror.
    # Label dinamis (tunggal vs jamak) + bahasa mengikuti req.language (Revisi #2).
    chart_md = _chart_caption_md(chart_keys_to_show, req.language) if show_charts else ""

    # Fase 1.7: blok angka deterministik (kalau ada) tampil DULU sebagai sumber
    # angka otoritatif, baru narasi LLM (yang angka nyasarnya sudah diredaksi).
    # Revisi #3 (Commit 1): perakitan dipindah ke _assemble_analysis_response
    # (presentasi bersama dgn /analyze). Output BYTE-IDENTIK dengan sebelumnya.
    full_response = _assemble_analysis_response(
        file_name           = session.file_name,
        row_count           = len(session.dataframe),
        narrative           = narrative,
        session_id          = req.session_id,
        deterministic_block = deterministic_block,
        chart_md            = chart_md,
        source_note         = "(data dari sesi sebelumnya)",
    )

    return {"result": full_response, "session_id": req.session_id}


@app.get("/session/{session_id}/status")
async def session_status(session_id: str):
    """
    Validasi session aktif — digunakan oleh Open WebUI inlet() sebelum inject reminder.
    Returns active=false (tidak raise 404) agar inlet bisa cek field tanpa try/except.
    """
    session = get_session(session_id)
    if session is None:
        return {"active": False}

    columns = list(session.dataframe.columns) if session.dataframe is not None else []
    return {
        "active": True,
        "columns": columns,
        "domain": session.domain,
        "rows": len(session.dataframe) if session.dataframe is not None else 0,
    }


@app.get("/sessions")
async def list_active_sessions():
    """Debug endpoint: lihat semua session aktif (tidak expired)."""
    return {"sessions": list_sessions()}


@app.get("/models")
async def list_models():
    """List available Ollama models."""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            return resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable: {e}")


# ── Run ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
