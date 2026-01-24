# Literature Monitor (Raspberry Pi Edition)

An automated literature monitoring tool for researchers, designed to run on a Raspberry Pi. Scans PubMed and bioRxiv for new papers matching your research interests, uses Claude AI to rank and summarize them, and delivers a weekly email digest with one-click Zotero integration.

## Features

- **Automated Search**: Weekly scans of PubMed and bioRxiv using customizable search queries
- **AI-Powered Ranking**: Claude analyzes papers and scores relevance to your active research projects
- **Smart Summaries**: Each paper gets a plain-language summary and relevance rationale
- **Email Digest**: HTML email with papers organized by priority (high/moderate/low)
- **One-Click Zotero**: Signed links to add papers directly to your Zotero library (via Cloudflare Worker)
- **Capacities Integration**: Sync papers and digests to your Capacities workspace
- **Web UI**: Flask-based interface for editing search queries and settings
- **Cron-Based Scheduling**: Runs automatically via cron on your Raspberry Pi

## Raspberry Pi Setup

### 1. System Requirements

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3 and dependencies
sudo apt install python3 python3-pip python3-venv git -y
```

### 2. Clone Repository

```bash
cd ~
git clone https://github.com/keith-hazleton/lit-monitor-pi.git
cd lit-monitor-pi
```

### 3. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

Edit `.env` with your credentials:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for ranking ([get one](https://console.anthropic.com/)) |
| `NCBI_API_KEY` | Recommended | NCBI API key for higher rate limits ([get one](https://www.ncbi.nlm.nih.gov/account/settings/)) |
| `NCBI_EMAIL` | Yes | Your email for NCBI API |
| `EMAIL_TO` | For email | Recipient email address |
| `EMAIL_FROM` | For email | Sender email address |
| `SMTP_HOST` | For email | SMTP server (e.g., `smtp.gmail.com`) |
| `SMTP_PORT` | For email | SMTP port (usually `587`) |
| `SMTP_USER` | For email | SMTP username |
| `SMTP_PASSWORD` | For email | SMTP password or app password |
| `ZOTERO_WORKER_URL` | For Zotero | Your deployed Cloudflare Worker URL |
| `SIGNING_SECRET` | For Zotero | HMAC secret (generate with `openssl rand -hex 32`) |
| `CAPACITIES_API_TOKEN` | For Capacities | Capacities API token |
| `CAPACITIES_SPACE_ID` | For Capacities | Capacities space UUID |

### 5. Customize Your Research Profile

Edit `config/config.yaml` to define:

```yaml
# PubMed/bioRxiv search queries
search_queries:
  - "pediatric liver disease"
  - "biliary atresia"
  - "your research topic"

# Authors to highlight in digests
watched_authors:
  - "Smith JK"
  - "Doe AB"

# Your active research projects (used for AI relevance scoring)
active_projects:
  - name: "Project Name"
    keywords:
      - keyword1
      - keyword2
      - keyword3

# Journal weight multipliers for ranking
journal_weights:
  high_trust:
    weight: 1.5
    journals:
      - "Nature"
      - "Science"
  low_trust:
    weight: 0.5
    journals:
      - "Predatory Journal Name"
```

### 6. Test Run

```bash
source venv/bin/activate

# Quick test with PubMed search only (no ranking)
python main.py --pubmed-only --days 3 --skip-ranking

# Full test with ranking
python main.py --pubmed-only --days 3
python main.py --rank-only --rank-limit 5

# Generate digest
python main.py --digest --days 3
```

### 7. Set Up Cron Job

Make the wrapper script executable and add to cron:

```bash
chmod +x run_weekly.sh

# Edit crontab
crontab -e
```

Add this line to run every Monday at 8am:

```
0 8 * * 1 /home/pi/lit-monitor-pi/run_weekly.sh
```

Adjust the path and schedule as needed. Cron schedule format: `minute hour day-of-month month day-of-week`

Examples:
- `0 8 * * 1` - Every Monday at 8:00 AM
- `0 6 * * *` - Every day at 6:00 AM
- `0 8 * * 1,4` - Every Monday and Thursday at 8:00 AM

### 8. View Logs

Logs are stored in the `logs/` directory:

```bash
# View latest log
ls -lt logs/ | head -5
cat logs/weekly_2026-01-24.log

# Follow log in real-time (if running)
tail -f logs/weekly_$(date +%Y-%m-%d).log
```

## Cloudflare Worker Setup (for Zotero Integration)

The one-click Zotero links require a Cloudflare Worker to securely add papers to your library. This runs separately from the Pi.

### 1. Install Wrangler (on your development machine, not the Pi)

```bash
cd worker
npm install
```

### 2. Deploy the Worker

```bash
npx wrangler deploy
```

### 3. Add Secrets

```bash
npx wrangler secret put ZOTERO_API_KEY
npx wrangler secret put ZOTERO_USER_ID
npx wrangler secret put SIGNING_SECRET
# Optional: for Capacities integration
npx wrangler secret put CAPACITIES_API_TOKEN
npx wrangler secret put CAPACITIES_SPACE_ID
```

Get your Zotero credentials at [zotero.org/settings/keys](https://www.zotero.org/settings/keys).

### 4. Update Your .env on the Pi

Add your deployed worker URL:
```
ZOTERO_WORKER_URL=https://lit-monitor-zotero.YOUR-SUBDOMAIN.workers.dev
```

**Important**: The `SIGNING_SECRET` must be identical in your Pi's `.env` and Cloudflare Worker.

## Manual Commands

Run these from the `lit-monitor-pi` directory with venv activated:

| Command | Description |
|---------|-------------|
| `python main.py --pubmed-only --days 7` | Search PubMed only |
| `python main.py --biorxiv-only --days 7` | Search bioRxiv only |
| `python main.py --skip-ranking` | Search without AI ranking |
| `python main.py --rank-only --rank-limit N` | Rank up to N unranked papers |
| `python main.py --digest --days 7` | Generate HTML digest |
| `python main.py --digest --send-email` | Generate and email digest |
| `python main.py --stats` | Show database statistics |
| `python -m web.app` | Start Flask config editor |

## Web UI for Configuration

The Flask web UI provides an easy way to edit your search parameters:

```bash
source venv/bin/activate
python -m web.app
```

Access at `http://<pi-ip-address>:5000` from another device on your network.

**Note**: For remote access, you may need to modify `web/app.py` to bind to `0.0.0.0` instead of `127.0.0.1`.

## Project Structure

```
lit-monitor-pi/
├── config/
│   └── config.yaml          # Your research configuration
├── src/
│   ├── config_loader.py     # YAML config parser
│   ├── database.py          # SQLite database layer
│   ├── email_digest.py      # HTML digest generator
│   ├── ranker.py            # Claude AI ranking
│   └── sources/
│       ├── pubmed.py        # PubMed E-utilities client
│       └── biorxiv.py       # bioRxiv API client
├── web/
│   ├── app.py               # Flask web UI
│   ├── templates/           # HTML templates
│   └── static/              # CSS styles
├── worker/
│   └── src/index.js         # Cloudflare Worker for Zotero
├── data/
│   └── papers.db            # SQLite database (persists on Pi)
├── output/
│   └── digest_*.html        # Generated digests
├── logs/
│   └── weekly_*.log         # Cron job logs
├── main.py                  # CLI entry point
└── run_weekly.sh            # Cron wrapper script
```

## Troubleshooting

### "Invalid Signature" on Zotero links
The `SIGNING_SECRET` must match in both places:
1. Your Pi's `.env`
2. Cloudflare Worker (`npx wrangler secret put SIGNING_SECRET`)

### Rate limiting from PubMed
Add an `NCBI_API_KEY` to increase rate limits from 3 to 10 requests/second.

### Email not sending
For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833) instead of your regular password.

### Cron job not running
Check cron logs:
```bash
grep CRON /var/log/syslog
```

Make sure the script is executable and paths are absolute.

### Permission issues
Ensure the pi user owns all files:
```bash
sudo chown -R pi:pi ~/lit-monitor-pi
```

## Differences from Original Version

This Pi edition differs from the [main lit-monitor](https://github.com/keith-hazleton/lit-monitor) repository:

| Feature | Original | Pi Edition |
|---------|----------|------------|
| Scheduling | GitHub Actions | Cron |
| Database persistence | GitHub Artifacts (90-day) | Local filesystem (permanent) |
| Hosting | Serverless | Self-hosted |
| Setup complexity | Fork + secrets | Clone + cron |

## License

MIT License - feel free to fork and adapt for your research needs.
