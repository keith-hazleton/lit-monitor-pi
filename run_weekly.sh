#!/bin/bash
# Weekly literature scan script for cron
# Add to crontab with: crontab -e
# Example: 0 8 * * 1 /home/pi/lit-monitor-pi/run_weekly.sh
# (Runs every Monday at 8am)

set -e

# Change to script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set up logging
LOG_FILE="$SCRIPT_DIR/logs/weekly_$(date +%Y-%m-%d).log"
mkdir -p "$SCRIPT_DIR/logs"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Literature scan started: $(date)"
echo "=========================================="

# Activate virtual environment
source "$SCRIPT_DIR/venv/bin/activate"

# Load environment variables
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

# Step 1: Search PubMed for new papers
echo ""
echo "[1/4] Searching PubMed..."
python main.py --pubmed-only --days 7 --skip-ranking

# Step 2: Rank papers with Claude
echo ""
echo "[2/4] Ranking papers with Claude..."
python main.py --rank-only --rank-limit 50

# Step 3: Generate digest
echo ""
echo "[3/4] Generating digest..."
python main.py --digest --days 7

# Step 4: Send email
echo ""
echo "[4/4] Sending email..."
python main.py --digest --days 7 --send-email

echo ""
echo "=========================================="
echo "Literature scan completed: $(date)"
echo "=========================================="
