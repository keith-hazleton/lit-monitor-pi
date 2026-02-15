#!/bin/bash
# Weekly literature scan script for cron
# Add to crontab with: crontab -e
# Example: 0 7 * * 0 /home/pi/projects/lit-monitor-pi/run_weekly.sh
# (Runs every Sunday at 7am)
#
# IMPORTANT: Use the full absolute path in crontab, not ~

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
if [ ! -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    echo "ERROR: Virtual environment not found at $SCRIPT_DIR/venv/"
    echo "Create it with: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi
source "$SCRIPT_DIR/venv/bin/activate"

# Load environment variables
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Step 1: Search PubMed for new papers
echo ""
echo "[1/3] Searching PubMed..."
if ! python main.py --pubmed-only --days 7 --skip-ranking; then
    echo "WARNING: PubMed search failed, continuing with existing papers..."
fi

# Step 2: Rank papers with Claude
echo ""
echo "[2/3] Ranking papers with Claude..."
if ! python main.py --rank-only --rank-limit 50; then
    echo "WARNING: Ranking failed, continuing with unranked papers..."
fi

# Step 3: Generate digest and send email
echo ""
echo "[3/3] Generating digest and sending email..."
python main.py --digest --days 7 --send-email

echo ""
echo "=========================================="
echo "Literature scan completed: $(date)"
echo "=========================================="
