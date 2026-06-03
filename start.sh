#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo ""
echo "  ================================================"
echo "   Jericho AI Council — Startup"
echo "  ================================================"
echo ""

# ─── Check Python ────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "  [ERROR] Python 3 is not installed or not on PATH."
    echo "          Please install Python 3.11+ from https://python.org"
    exit 1
fi

PYTHON=python3

# ─── Ensure virtual environment exists ───────────────────────
if [ ! -f "venv/bin/activate" ]; then
    echo "  [SETUP] Creating virtual environment..."
    $PYTHON -m venv venv
    echo "  [OK]    Virtual environment created."
fi

# ─── Activate venv ───────────────────────────────────────────
echo "  [INFO]  Activating virtual environment..."
source venv/bin/activate

# ─── Install / update dependencies ───────────────────────────
echo "  [INFO]  Checking dependencies..."
pip install -e ".[dev]" --quiet
echo "  [OK]    Dependencies up to date."

# ─── Check for API keys ─────────────────────────────────────
if [ ! -f "config/.env" ]; then
    echo ""
    echo "  [WARN]  No config/.env found!"
    echo "          Copying config/.env.example to config/.env"
    echo "          Please edit config/.env with your API keys before"
    echo "          running any council sessions."
    cp config/.env.example config/.env
    echo ""
fi

# ─── Show project status ────────────────────────────────────
echo ""
echo "  ------------------------------------------------"
echo "   Project Status"
echo "  ------------------------------------------------"
$PYTHON -m core.cli status
echo ""

# ─── Launch web dashboard ───────────────────────────────────
echo "  ------------------------------------------------"
echo "   Starting Web Dashboard"
echo "  ------------------------------------------------"
echo ""
echo "  Dashboard:  http://127.0.0.1:8080"
echo "  API docs:   http://127.0.0.1:8080/docs"
echo ""
echo "  Press Ctrl+C to stop the server."
echo ""
$PYTHON -m core.cli web
