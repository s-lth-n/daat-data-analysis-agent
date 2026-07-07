# CLAUDE.md — Project Context for Claude Code

## Project Overview
**Tugas Akhir (Final Year Project)** — Teknik Telekomunikasi, Institut [text](about:blank#blocked)Teknologi Bandung
**Title:** Pengembangan Prototipe Agentic AI berbasis Tool-Calling (LangGraph) dengan Local-LLM Engine untuk Data Analysis Agent
**Authors:** Sulthan Miftahul Ulum & Hanan Ainayya Ramadina

## What This Project Does
An **Agentic AI Data Analysis Agent** that runs 100% locally (no cloud). Users interact via natural language chat to:
- Upload data files (CSV, Excel, Google Sheets)
- Get descriptive statistics (mean, median, std, min, max, correlation)
- Generate interactive visualizations (bar, line, scatter charts)
- Receive narrative analysis reports in Indonesian or English

## Architecture (3 Subsystems)
```
┌─────────────────────────────────────────────────────┐
│                  FRONTEND SUBSYSTEM                  │
│          Open WebUI (Svelte) + Pipelines             │
│    Chat UI → File Upload → Chart Display → Reports   │
├─────────────────────────────────────────────────────┤
│                  BACKEND SUBSYSTEM                    │
│  FastAPI ← LangChain + LangGraph ← Ollama (Qwen3)  │
│  Tools: Pandas, DuckDB, Plotly                       │
│  Features: Agentic Tool-Calling (LangGraph)          │
├─────────────────────────────────────────────────────┤
│            HARDWARE & ENVIRONMENT SUBSYSTEM           │
│  Ubuntu 22.04 LTS → NVIDIA RTX 3060 12GB → CUDA     │
│  Constraint: ≤8GB VRAM usage, ≤14B parameters        │
│  All processing local, no cloud, temp data only      │
└─────────────────────────────────────────────────────┘
```

## Tech Stack
| Component        | Technology                    |
|------------------|-------------------------------|
| Frontend         | Open WebUI (Svelte) + Custom Pipelines |
| Backend API      | Python 3.11+ / FastAPI        |
| LLM Engine       | Ollama + Qwen3 8B             |
| Orchestration    | LangChain + LangGraph         |
| Data Processing  | Pandas + DuckDB               |
| Visualization    | Plotly                        |
| Hardware         | NVIDIA RTX 3060 12GB          |
| OS               | Ubuntu 22.04 LTS              |

## Project Structure
```
ta-data-analyst/
├── CLAUDE.md                # This file (Claude Code context)
├── README.md                # Project documentation
├── docker-compose.yml       # Ollama + Open WebUI orchestration
├── DAAT Analyze Tool.py     # this is a copypasted tool from openwebui, access it by claude code to use edit, and user will copy pasted it manually to open web-ui, so edit this if the backend need to communicate with this tool or u need to edit this tool so that things would work
├── DAAT Session Filter.py   # Open WebUI Filter: injects session/file context on inlet
├── Modelfile                # Ollama model definition (Qwen3)
├── pytest.ini               # Pytest configuration
├── backend/
│   ├── main.py              # FastAPI application entry point (all @app endpoints)
│   ├── config.py            # Pydantic settings (.env anchored to this file's dir)
│   ├── session_store.py     # In-memory session / uploaded-file registry
│   ├── agents/
│   │   ├── data_agent.py    # LangGraph-based data analysis agent
│   │   └── prompts.py       # System prompts (ID & EN)
│   ├── tools/
│   │   ├── data_loader.py         # CSV/Excel file reader
│   │   ├── data_cleaner.py        # Data cleaning / normalization
│   │   ├── column_profiler.py     # Column type & domain profiling
│   │   ├── statistics.py          # Descriptive statistics calculator
│   │   ├── groupby_analyzer.py    # Group-by aggregation & intent parsing
│   │   ├── chart_intent.py        # Detect requested chart from the prompt
│   │   ├── visualization.py       # Plotly chart generator
│   │   ├── narrative_generator.py # LLM narrative report (constrained JSON + fallback)
│   │   └── lang_detect.py         # ID/EN output-language detection
│   └── requirements.txt
├── frontend-theme/          # Open WebUI theme & login-page customizations
├── scripts/
│   ├── setup_environment.sh # Full environment setup script
│   └── run_dev.sh           # Development run script
├── data/
│   └── samples/             # Sample CSV files (uploads/ & charts/ created at runtime)
└── tests/                   # pytest suite: test_tools, test_agent, test_lang_detect, test_config, test_free_form_narrative + revisi/fase/fix regression tests
```

## Key Constraints (from TA documents)
- **Privacy:** 100% local processing, NO cloud API calls, NO data leaves the machine
- **Hardware:** Must run on GPU with ≤8GB VRAM (target: RTX 3060 12GB uses ~6.7GB)
- **Model:** ≤14B parameters (using Qwen3 8B = 8.2B params)
- **Latency:** Response time < 30 seconds for dataset up to 10MB
- **Language:** Must support both Bahasa Indonesia and English
- **Visualization:** Minimum 3 types (bar, line, scatter)
- **Report:** Auto-generated with title, analysis, conclusion sections

## Development Commands
```bash
# Start Ollama + Open WebUI
docker compose up -d

# Run backend in development
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest tests/ -v

# Pull/update LLM model
ollama pull qwen3:8b
```

## Coding Conventions
- Python 3.11+, type hints required
- FastAPI for all API endpoints
- Pydantic for data validation
- async/await preferred for I/O operations
- Docstrings in English, UI text bilingual (ID/EN)
- Use `logging` module, not print statements
- Tests with pytest

## Important Notes for Claude Code
- This is a **local-first** project — never suggest cloud API solutions
- All LLM inference goes through **Ollama** running locally
- The agent should use **LangGraph** for workflow orchestration
- Visualizations must be **Plotly** (interactive, web-native), NOT Matplotlib
- Data queries should leverage **DuckDB** for SQL-based analysis
- The Open WebUI **Pipelines** system is the preferred extension mechanism
- Keep responses bilingual when user-facing (ID/EN support)
