# Raspberry Pi Migration Plan

## Overview

Migrate the weekly literature monitoring run from GitHub Actions to a Raspberry Pi while keeping the Zotero endpoint on Cloudflare Workers.

### What Stays on Cloudflare
- **Zotero endpoint** - Receives clicks from email digest links and adds papers to Zotero
- No changes needed - already deployed and working

### What Moves to the Pi
- **Weekly search/rank/digest job** - Cron job running Python scripts
- **SQLite database** - Lives on Pi filesystem (simpler than GitHub artifact workaround)
- **Email sending** - Same SMTP code, just runs from Pi

### Connection Between Them
- `ZOTERO_WORKER_URL` environment variable points to existing Cloudflare Worker
- `SIGNING_SECRET` must match between Pi and Cloudflare Worker

---

## Pi Preparation

Before running the migration, set up the Pi with these prerequisites:

### 1. Basic Setup
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3 and pip (if not already installed)
sudo apt install python3 python3-pip python3-venv git -y
```

### 2. Clone the Repository
```bash
cd ~
git clone https://github.com/YOUR_USERNAME/lit-monitor.git
cd lit-monitor
```

### 3. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Create Environment File
```bash
cp .env.example .env
nano .env
```

Required environment variables:
```
ANTHROPIC_API_KEY=your_key_here
NCBI_EMAIL=your_email@example.com
NCBI_API_KEY=your_ncbi_key (optional but recommended)

# Email settings
EMAIL_TO=recipient@example.com
EMAIL_FROM=sender@example.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_smtp_user
SMTP_PASSWORD=your_smtp_password

# Zotero integration (points to existing Cloudflare Worker)
ZOTERO_WORKER_URL=https://your-worker.workers.dev
SIGNING_SECRET=your_signing_secret

# Capacities (optional)
CAPACITIES_API_TOKEN=your_token
CAPACITIES_SPACE_ID=your_space_id
```

### 5. Initialize Database Directory
```bash
mkdir -p data
```

### 6. Test Run
```bash
source venv/bin/activate
python main.py --pubmed-only --days 3 --skip-ranking
```

---

## Migration Prompt

Use this prompt once the Pi is set up and the test run works:

> Set up the lit-monitor cron job on the Raspberry Pi. The Pi prep is complete - the repo is cloned, virtual environment is created with dependencies installed, and .env is configured. I need:
>
> 1. A cron job that runs every Monday at 8am (same schedule as the current GitHub Action)
> 2. The cron job should run the full pipeline: search PubMed, rank with Claude, generate digest, and send email
> 3. A shell script wrapper that activates the venv and runs the commands
> 4. Logging to a file so I can debug if something goes wrong
>
> The current GitHub Actions workflow is in `.github/workflows/weekly_scan.yaml` for reference.

---

## Optional: Download Existing Database

If you want to preserve history from GitHub Actions runs:

1. Go to the repository on GitHub
2. Click **Actions** tab
3. Find a recent successful "Weekly Literature Scan" run
4. Download the `papers-database` artifact
5. Extract and copy `papers.db` to the Pi's `data/` directory

---

## Future Consideration: Tailscale Funnel

If you later want to move the Zotero endpoint to the Pi as well (consolidating everything), you could use Tailscale Funnel to expose it. This would require:

1. Installing Tailscale on the Pi
2. Enabling Funnel for a local Flask/FastAPI endpoint
3. Rewriting the Cloudflare Worker logic in Python
4. Updating `ZOTERO_WORKER_URL` to point to the Funnel URL
5. Updating the signing secret if needed

But the hybrid approach (Cloudflare for Zotero, Pi for everything else) works well and is simpler.
