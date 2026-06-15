"""
Data Analysis Agent (LangGraph)
================================
The core agentic AI component. Uses LangGraph to orchestrate
a multi-step data analysis workflow:

  [Parse Prompt] → [Load Data] → [Analyze] → [Visualize] → [Report]

Each step is a node in the graph with conditional routing.
"""

import logging
from pathlib import Path
from typing import Any, TypedDict, Annotated

from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END

from config import settings
from tools.narrative_generator import generate_narrative

logger = logging.getLogger(__name__)


# ── Agent State ─────────────────────────────────────────────
class AgentState(TypedDict):
    """State that flows through the LangGraph workflow."""
    # Input
    prompt: str
    file_id: str | None
    language: str

    # Data
    file_path: str | None
    dataframe_loaded: bool
    dataframe: Any | None         # cleaned pd.DataFrame (after clean_data node)
    data_summary: str | None
    column_profile: dict | None   # {col_name: label} from Smart Column Profiler
    cleaning_report: dict | None  # summary from data_cleaner_node
    domain_context: dict | None   # {domain_type, preferred_aggregation, metric_note, avoid}

    # Results
    statistics: dict | None
    charts: list[dict] | None
    narrative: str | None
    existing_chart_urls: list[str] | None   # Pre-rendered PNG URLs (followup only)

    # Control
    error: str | None
    step: str


# ── LLM Setup ──────────────────────────────────────────────
def get_llm() -> ChatOllama:
    """Initialize the local LLM via Ollama."""
    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=settings.llm_temperature,
        num_predict=settings.llm_max_tokens,
    )


# ── Graph Nodes ─────────────────────────────────────────────

def parse_intent(state: AgentState) -> AgentState:
    """
    Node 1: Understand what the user wants.
    Determines which analysis steps to run.
    """
    logger.info(f"[Node: parse_intent] Prompt: {state['prompt'][:80]}...")

    state["step"] = "parse_intent"
    state["error"] = None

    # If no file uploaded, we can still answer general questions
    if not state.get("file_id"):
        state["dataframe_loaded"] = False
        state["data_summary"] = None

    return state


def load_data(state: AgentState) -> AgentState:
    """
    Node 2: Load the uploaded data file.
    """
    logger.info("[Node: load_data]")
    state["step"] = "load_data"

    if not state.get("file_id"):
        state["dataframe_loaded"] = False
        return state

    # Find the file — search with absolute path
    upload_dir = Path(settings.upload_dir).resolve()
    matching = list(upload_dir.glob(f"{state['file_id']}_*"))

    logger.info(f"Searching for file_id={state['file_id']} in {upload_dir}, found={len(matching)}")

    if not matching:
        state["error"] = f"File not found: {state['file_id']}"
        state["dataframe_loaded"] = False
        return state

    file_path = str(matching[0])
    state["file_path"] = file_path

    try:
        from tools.data_loader import load_dataframe, get_data_summary
        df = load_dataframe(file_path)
        state["dataframe"] = df
        state["data_summary"] = get_data_summary(df)
        state["dataframe_loaded"] = True
        logger.info(f"Data loaded: {df.shape}")
    except Exception as e:
        state["error"] = f"Failed to load data: {e}"
        state["dataframe_loaded"] = False

    return state


def clean_data(state: AgentState) -> AgentState:
    """
    Node 2b: Preprocess the loaded DataFrame before profiling.
    Runs between load_data and profile_columns.
    Steps: drop empty cols, drop duplicates, parse datetimes,
           drop sparse rows, fill numeric NaN, remove invalid
           transactions, cap extreme outliers (IQR×3).
    """
    logger.info("[Node: clean_data]")
    state["step"] = "clean_data"

    if not state.get("dataframe_loaded") or state.get("dataframe") is None:
        state["cleaning_report"] = {}
        return state

    try:
        from tools.data_cleaner import data_cleaner_node
        from tools.data_loader import get_data_summary

        result = data_cleaner_node({"dataframe": state["dataframe"]})
        state["dataframe"] = result["dataframe"]
        state["cleaning_report"] = result["cleaning_report"]
        # Refresh data_summary so LLM sees the cleaned shape
        state["data_summary"] = get_data_summary(state["dataframe"])
        logger.info(
            f"[clean_data] {result['cleaning_report']['rows_removed_pct']}% rows removed, "
            f"{result['cleaning_report']['cleaned_rows']} rows remain"
        )
    except Exception as e:
        logger.error(f"Data cleaning failed: {e}")
        state["cleaning_report"] = {}

    return state


def profile_columns(state: AgentState) -> AgentState:
    """
    Node 3: Smart Column Profiler.
    Classifies each column as numerik_valid / id_kolom / kategorik / datetime.
    Uses heuristics first, then LLM only for ambiguous columns.
    """
    logger.info("[Node: profile_columns]")
    state["step"] = "profile_columns"

    if not state.get("dataframe_loaded") or not state.get("file_path"):
        state["column_profile"] = {}
        state["domain_context"] = None
        return state

    try:
        from tools.column_profiler import (
            profile_columns as run_profiler,
            detect_domain,
            get_numeric_columns, get_categorical_columns, get_id_columns,
        )

        df = state.get("dataframe")
        if df is None:
            from tools.data_loader import load_dataframe
            df = load_dataframe(state["file_path"])
        column_profile = run_profiler(df)
        state["column_profile"] = column_profile

        logger.info(f"Numeric   : {get_numeric_columns(column_profile)}")
        logger.info(f"Categorical: {get_categorical_columns(column_profile)}")
        logger.info(f"ID (skip) : {get_id_columns(column_profile)}")

        # Domain detection — runs after column classifier, uses same LLM config
        classifier_llm = ChatOllama(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
            temperature=0,
            num_predict=256,
        )
        sample_rows = df.head(5).to_dict(orient="records")
        domain_context = detect_domain(list(df.columns), sample_rows, classifier_llm)
        state["domain_context"] = domain_context
        logger.info(f"Domain detected: {domain_context['domain_type']} "
                    f"(agg={domain_context['preferred_aggregation']})")

    except Exception as e:
        logger.error(f"Column profiling failed: {e}")
        state["column_profile"] = {}
        state["domain_context"] = None

    return state


def compute_statistics(state: AgentState) -> AgentState:
    """
    Node 4: Compute descriptive statistics using only validated numeric columns.
    """
    logger.info("[Node: compute_statistics]")
    state["step"] = "compute_statistics"

    if not state.get("dataframe_loaded") or not state.get("file_path"):
        return state

    try:
        from tools.statistics import descriptive_statistics, correlation_matrix
        from tools.column_profiler import get_numeric_columns

        df = state.get("dataframe")
        if df is None:
            from tools.data_loader import load_dataframe
            df = load_dataframe(state["file_path"])
        column_profile = state.get("column_profile") or {}
        numeric_cols = get_numeric_columns(column_profile) if column_profile else None

        domain_context = state.get("domain_context")
        stats = descriptive_statistics(df, numeric_cols=numeric_cols, domain_context=domain_context)
        corr = correlation_matrix(df, numeric_cols=numeric_cols)

        state["statistics"] = {
            "descriptive": stats,
            "correlation": corr,
        }

        # Diagnosa #5 (Commit A): samakan /analyze dengan /analyze/followup —
        # inject hasil GROUP BY (mis. Revenue total + produk teratas) ke
        # STATS_CONTEXT narasi LEWAT key __followup_context__ yang SAMA dengan
        # followup. Tanpa ini, prosa LLM /analyze hanya melihat statistik
        # deskriptif global (Σ/max Price) lalu mengarang "total penjualan" dari
        # angka yang salah. build_followup_context murni pandas (TANPA LLM call)
        # & hanya mengeluarkan blok bila ada intent groupby/ranking/temporal;
        # pertanyaan non-groupby → "" → tak ada injeksi (no regresi). Pakai data
        # yang sudah ada di state pada node ini (prompt/df/profile/domain) →
        # tanpa field state baru. _build_stats_context sudah membaca key ini.
        try:
            from tools.groupby_analyzer import build_followup_context
            ctx = build_followup_context(
                df, state.get("prompt", ""), column_profile, domain_context
            )
            if ctx and isinstance(state.get("statistics"), dict):
                state["statistics"]["__followup_context__"] = ctx
        except Exception as _ge:
            logger.warning(f"[compute_statistics] groupby context dilewati: {_ge}")
    except Exception as e:
        logger.error(f"Statistics computation failed: {e}")
        state["statistics"] = {"error": str(e)}

    return state


def generate_visualizations(state: AgentState) -> AgentState:
    """
    Node 4: Generate interactive Plotly charts.
    """
    logger.info("[Node: generate_visualizations]")
    state["step"] = "generate_visualizations"

    if not state.get("dataframe_loaded") or not state.get("file_path"):
        state["charts"] = []
        return state

    try:
        from tools.visualization import auto_visualize

        df = state.get("dataframe")
        if df is None:
            from tools.data_loader import load_dataframe
            df = load_dataframe(state["file_path"])
        charts = auto_visualize(
            df,
            language=state.get("language", "id"),
            column_profile=state.get("column_profile"),
            domain_context=state.get("domain_context"),
        )
        state["charts"] = charts
    except Exception as e:
        logger.error(f"Visualization generation failed: {e}")
        state["charts"] = []

    return state


# generate_narrative is imported from tools.narrative_generator
# (constrained JSON generation via NarrativeSchema + free-form fallback)


# ── Conditional Routing ─────────────────────────────────────

def should_analyze_data(state: AgentState) -> str:
    """Route: If data is loaded, proceed to cleaning+profiling. Otherwise, narrative only."""
    if state.get("error"):
        return "generate_narrative"
    if state.get("dataframe_loaded"):
        return "clean_data"
    return "generate_narrative"


# ── Build the Graph ─────────────────────────────────────────

def build_analysis_graph() -> StateGraph:
    """
    Construct the LangGraph workflow for data analysis.

    Graph structure:
        START → parse_intent → load_data → [conditional]
                                             ├── clean_data → profile_columns → compute_statistics → generate_visualizations → generate_narrative → END
                                             └── generate_narrative → END  (no data)
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("parse_intent", parse_intent)
    graph.add_node("load_data", load_data)
    graph.add_node("clean_data", clean_data)
    graph.add_node("profile_columns", profile_columns)
    graph.add_node("compute_statistics", compute_statistics)
    graph.add_node("generate_visualizations", generate_visualizations)
    graph.add_node("generate_narrative", generate_narrative)

    # Add edges
    # START → parse_intent → load_data → [conditional]
    #   ├── clean_data → profile_columns → compute_statistics → generate_visualizations → generate_narrative → END
    #   └── generate_narrative → END  (no data)
    graph.add_edge(START, "parse_intent")
    graph.add_edge("parse_intent", "load_data")
    graph.add_conditional_edges("load_data", should_analyze_data)
    graph.add_edge("clean_data", "profile_columns")
    graph.add_edge("profile_columns", "compute_statistics")
    graph.add_edge("compute_statistics", "generate_visualizations")
    graph.add_edge("generate_visualizations", "generate_narrative")
    graph.add_edge("generate_narrative", END)

    return graph.compile()


# ── Public API ──────────────────────────────────────────────

# Compile the graph once at module level
analysis_graph = build_analysis_graph()


async def run_analysis_agent(
    prompt: str,
    file_id: str | None = None,
    language: str = "id",
) -> dict[str, Any]:
    """
    Run the data analysis agent.

    Args:
        prompt: User's natural language instruction.
        file_id: ID of uploaded file (from /upload endpoint).
        language: "id" for Indonesian, "en" for English.

    Returns:
        Dict with keys: text, charts, statistics, language.
    """
    logger.info(f"Running analysis agent (file={file_id}, lang={language})")

    initial_state: AgentState = {
        "prompt":               prompt,
        "file_id":              file_id,
        "language":             language,
        "file_path":            None,
        "dataframe_loaded":     False,
        "dataframe":            None,
        "data_summary":         None,
        "column_profile":       None,
        "cleaning_report":      None,
        "domain_context":       None,
        "statistics":           None,
        "charts":               None,
        "narrative":            None,
        "error":                None,
        "step":                 "init",
        "existing_chart_urls":  None,
    }

    # Run the graph
    final_state = analysis_graph.invoke(initial_state)

    return {
        "text": final_state.get("narrative", "No analysis generated."),
        "charts": final_state.get("charts"),
        "statistics": final_state.get("statistics"),
        "language": language,
        # Raw state exposed for session storage (used by /analyze endpoint)
        "dataframe": final_state.get("dataframe"),
        "column_profile": final_state.get("column_profile"),
        "cleaning_report": final_state.get("cleaning_report"),
        "domain_context": final_state.get("domain_context"),
    }
