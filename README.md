# 🤖 Agentic AI Data Analysis Agent

> **Tugas Akhir** Teknik Telekomunikasi, Institut Teknologi Bandung
>
> Author: Sulthan Miftahul Ulum & Hanan Ainayya Ramadina
> 
> Pengembangan Prototipe Agentic AI (RAG/MCP) dengan Local-LLM Engine untuk Data Analysis Agent

## Overview

Sistem analisis data berbasis AI yang berjalan **100% lokal** tanpa cloud, tanpa data yang keluar dari mesin. Pengguna berinteraksi melalui chat bahasa alami untuk menganalisis file data (CSV/Excel) dan mendapatkan insight berupa statistik, visualisasi interaktif, dan laporan naratif.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Open WebUI (Svelte) + Custom Pipelines |
| Backend | Python 3.11+ / FastAPI |
| LLM Engine | Ollama + **Qwen3 8B** |
| Agent Orchestration | LangChain + **LangGraph** |
| Data Processing | Pandas + **DuckDB** |
| Visualization | **Plotly** (interactive) |
| Hardware | NVIDIA RTX 3060 12GB |
| OS | Ubuntu 22.04 LTS |

## Quick Start

### Prerequisites
- Ubuntu 22.04 LTS
- NVIDIA GPU with ≥8GB VRAM (tested: RTX 3060 12GB)
- NVIDIA drivers + CUDA installed
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+ 

### 1. Clone & Setup

```bash
git clone <your-repo-url>
cd ta-data-analyst

# Run the full setup script
chmod +x scripts/setup_environment.sh
./scripts/setup_environment.sh
```

### 2. Start Services

```bash
# Start Ollama + Open WebUI via Docker
docker compose up -d

# Wait for services to be ready, then pull the model
ollama pull qwen3:8b
```

### 3. Run Backend

```bash
source venv/bin/activate
cd backend
uvicorn main:app --reload --port 8000
```

### 4. Open in Browser

- **Open WebUI (Chat):** http://localhost:3000
- **Backend API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

## Project Structure

```
ta-data-analyst/
├── docker-compose.yml     # Ollama + Open WebUI
├── backend/
│   ├── main.py            # FastAPI app
│   ├── config.py          # Settings
│   ├── agents/
│   │   ├── data_agent.py  # LangGraph workflow
│   │   └── prompts.py     # Bilingual prompts
│   ├── tools/
│   │   ├── data_loader.py # File reading + DuckDB
│   │   ├── statistics.py  # Descriptive stats
│   │   └── visualization.py # Plotly charts
│   └── pipelines/         # Open WebUI plugins
├── data/samples/          # Test datasets
├── tests/                 # pytest test suite
└── scripts/               # Setup & utility scripts
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | System health check |
| POST | `/upload` | Upload CSV/Excel file |
| POST | `/analyze` | Run analysis on uploaded data |
| GET | `/models` | List available Ollama models |

## Testing

```bash
source venv/bin/activate
cd backend
pytest tests/ -v
```

## License

This project is part of an academic thesis at ITB.
