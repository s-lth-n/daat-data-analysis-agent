#!/bin/bash
# ============================================================
# setup_environment.sh
# Full Environment Setup for TA Data Analysis Agent
# Target: Ubuntu 22.04 LTS + NVIDIA RTX 3060 12GB
# ============================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err()   { echo -e "${RED}[ERROR]${NC} $1"; }

echo "============================================================"
echo "  TA Data Analysis Agent — Environment Setup"
echo "  Stack: Qwen3 8B | FastAPI | LangGraph | Plotly | DuckDB"
echo "============================================================"
echo ""

# -----------------------------------------------------------
# Step 1: System Prerequisites
# -----------------------------------------------------------
log_info "Step 1/7: Updating system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip \
    git curl wget \
    build-essential \
    nodejs npm \
    unzip

# Ensure python3.11 is default (if not already)
if ! command -v python3.11 &> /dev/null; then
    log_warn "Python 3.11 not found, installing via deadsnakes PPA..."
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update
    sudo apt install -y python3.11 python3.11-venv python3.11-dev
fi
log_ok "System packages installed"

# -----------------------------------------------------------
# Step 2: NVIDIA Driver & CUDA Check
# -----------------------------------------------------------
log_info "Step 2/7: Checking NVIDIA GPU..."
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
    log_ok "NVIDIA GPU detected"
else
    log_err "nvidia-smi not found! Please install NVIDIA drivers first."
    echo "  Run: sudo apt install nvidia-driver-535"
    echo "  Then reboot and re-run this script."
    echo ""
    echo "  For CUDA toolkit:"
    echo "  See: https://developer.nvidia.com/cuda-downloads"
    exit 1
fi

# -----------------------------------------------------------
# Step 3: Install Ollama
# -----------------------------------------------------------
log_info "Step 3/7: Installing Ollama..."
if command -v ollama &> /dev/null; then
    log_ok "Ollama already installed: $(ollama --version)"
else
    curl -fsSL https://ollama.com/install.sh | sh
    log_ok "Ollama installed"
fi

# -----------------------------------------------------------
# Step 4: Pull Qwen3 8B Model
# -----------------------------------------------------------
log_info "Step 4/7: Pulling Qwen3 8B model (this may take a while)..."
ollama pull qwen3:8b
log_ok "Qwen3 8B model ready"

# Verify model
log_info "Verifying model..."
ollama list | grep qwen3

# -----------------------------------------------------------
# Step 5: Python Virtual Environment & Dependencies
# -----------------------------------------------------------
log_info "Step 5/7: Setting up Python virtual environment..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Create venv
python3.11 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install backend dependencies
log_info "Installing Python dependencies..."
pip install -r backend/requirements.txt

log_ok "Python environment ready (venv activated)"

# -----------------------------------------------------------
# Step 6: Install Docker & Docker Compose (for Open WebUI)
# -----------------------------------------------------------
log_info "Step 6/7: Checking Docker..."
if command -v docker &> /dev/null; then
    log_ok "Docker already installed: $(docker --version)"
else
    log_info "Installing Docker..."
    sudo apt install -y docker.io docker-compose-v2
    sudo usermod -aG docker $USER
    log_ok "Docker installed (you may need to log out/in for group changes)"
fi

# Install NVIDIA Container Toolkit (for GPU in Docker)
if ! dpkg -l | grep -q nvidia-container-toolkit; then
    log_info "Installing NVIDIA Container Toolkit..."
    distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    sudo apt update
    sudo apt install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    log_ok "NVIDIA Container Toolkit installed"
else
    log_ok "NVIDIA Container Toolkit already installed"
fi

# -----------------------------------------------------------
# Step 7: Install Claude Code (Optional - for development)
# -----------------------------------------------------------
log_info "Step 7/7: Installing Claude Code..."
if command -v node &> /dev/null; then
    NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
    if [ "$NODE_VERSION" -ge 18 ]; then
        npm install -g @anthropic-ai/claude-code
        log_ok "Claude Code installed"
    else
        log_warn "Node.js version must be >= 18 for Claude Code. Current: $(node -v)"
        log_warn "Upgrade with: sudo npm install -g n && sudo n stable"
    fi
else
    log_warn "Node.js not found, skipping Claude Code installation"
fi

# -----------------------------------------------------------
# Summary
# -----------------------------------------------------------
echo ""
echo "============================================================"
echo -e "${GREEN}  Setup Complete!${NC}"
echo "============================================================"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Start Ollama + Open WebUI:"
echo "     docker compose up -d"
echo ""
echo "  2. Activate Python venv:"
echo "     source venv/bin/activate"
echo ""
echo "  3. Run backend (development):"
echo "     cd backend && uvicorn main:app --reload --port 8000"
echo ""
echo "  4. Open browser:"
echo "     Open WebUI:  http://localhost:3000"
echo "     Backend API: http://localhost:8000/docs"
echo ""
echo "  5. Start Claude Code (optional, for AI-assisted dev):"
echo "     cd $(pwd) && claude"
echo ""
echo "============================================================"
