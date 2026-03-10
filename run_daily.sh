#!/bin/bash
# Daily literature scan for Morning Edition integration
# Add to crontab: 0 5 * * * /home/pi/projects/lit-monitor-pi/run_daily.sh
# (Runs every day at 5:00 AM, 30 min before Morning Edition generation)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set up logging
LOG_FILE="$SCRIPT_DIR/logs/daily_$(date +%Y-%m-%d).log"
mkdir -p "$SCRIPT_DIR/logs"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Daily lit scan started: $(date)"
echo "=========================================="

# Activate virtual environment
if [ ! -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    echo "ERROR: Virtual environment not found at $SCRIPT_DIR/venv/"
    exit 1
fi
source "$SCRIPT_DIR/venv/bin/activate"

# Load environment variables
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Step 1: Search PubMed for papers from last day
echo ""
echo "[1/3] Searching PubMed (1-day lookback)..."
if ! python main.py --pubmed-only --days 1 --skip-ranking; then
    echo "WARNING: PubMed search failed, continuing with existing papers..."
fi

# Step 2: Rank new papers with Claude (limit 20 for cost control)
echo ""
echo "[2/3] Ranking papers with Claude..."
if ! python main.py --rank-only --rank-limit 20; then
    echo "WARNING: Ranking failed, continuing with previously ranked papers..."
fi

# Step 3: Export top papers as JSON for Morning Edition
echo ""
echo "[3/3] Exporting daily digest JSON..."
python main.py --daily-json

echo ""
echo "=========================================="
echo "Daily lit scan completed: $(date)"
echo "=========================================="
