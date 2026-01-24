"""
Flask web UI for editing Literature Monitor configuration.

Run with: python -m web.app
Or: flask --app web.app run
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import yaml

from src.config_loader import load_config, Config
from src.database import PaperDatabase

WEB_DIR = Path(__file__).parent
app = Flask(
    __name__,
    template_folder=WEB_DIR / 'templates',
    static_folder=WEB_DIR / 'static',
)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-change-in-production')

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
DATA_PATH = PROJECT_ROOT / "data" / "papers.db"


def load_config_raw() -> dict:
    """Load raw YAML config as dict."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config_raw(config: dict):
    """Save config dict to YAML file."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


@app.route('/')
def index():
    """Main config editor page."""
    config = load_config_raw()

    # Get database stats
    stats = {}
    try:
        db = PaperDatabase(DATA_PATH)
        stats = db.get_stats()
    except Exception as e:
        stats = {'error': str(e)}

    return render_template('index.html', config=config, stats=stats)


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current config as JSON."""
    return jsonify(load_config_raw())


@app.route('/api/config', methods=['POST'])
def update_config():
    """Update entire config from JSON."""
    try:
        new_config = request.json
        save_config_raw(new_config)
        return jsonify({'status': 'ok', 'message': 'Config saved'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/queries', methods=['POST'])
def update_queries():
    """Update search queries."""
    try:
        config = load_config_raw()
        queries = request.json.get('queries', [])
        # Filter empty strings
        config['search_queries'] = [q.strip() for q in queries if q.strip()]
        save_config_raw(config)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/authors', methods=['POST'])
def update_authors():
    """Update watched authors."""
    try:
        config = load_config_raw()
        authors = request.json.get('authors', [])
        config['watched_authors'] = [a.strip() for a in authors if a.strip()]
        save_config_raw(config)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/projects', methods=['POST'])
def update_projects():
    """Update active projects."""
    try:
        config = load_config_raw()
        projects = request.json.get('projects', [])
        config['active_projects'] = projects
        save_config_raw(config)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/journals', methods=['POST'])
def update_journals():
    """Update journal weights."""
    try:
        config = load_config_raw()
        journals = request.json.get('journal_weights', {})
        config['journal_weights'] = journals
        save_config_raw(config)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update general settings."""
    try:
        config = load_config_raw()
        settings = request.json.get('settings', {})
        config['settings'] = settings
        save_config_raw(config)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/stats')
def get_stats():
    """Get database statistics."""
    try:
        db = PaperDatabase(DATA_PATH)
        stats = db.get_stats()
        runs = db.get_search_runs(limit=5)
        return jsonify({
            'stats': stats,
            'recent_runs': [
                {
                    'date': r.run_date,
                    'papers_found': r.papers_found,
                    'new_papers': r.new_papers,
                }
                for r in runs
            ]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/test-config')
def test_config():
    """Test if current config is valid."""
    try:
        config = load_config(CONFIG_PATH)
        return jsonify({
            'status': 'ok',
            'queries': len(config.search_queries),
            'authors': len(config.watched_authors),
            'projects': len(config.active_projects),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


if __name__ == '__main__':
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    print(f"Config file: {CONFIG_PATH}")
    print(f"Database: {DATA_PATH}")
    print(f"\nStarting web UI...")
    print(f"  Local:   http://localhost:5000")
    print(f"  Network: http://{local_ip}:5000")
    app.run(host='0.0.0.0', port=5000)
