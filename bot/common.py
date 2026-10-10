"""Helpers shared across modules: Central-time clock, JSON state files, file deletes, GitHub step outputs."""
import json
import os
from datetime import datetime

import pytz

from . import config

CENTRAL = pytz.timezone('US/Central')
_MISSING = object()


def now_central():
    return datetime.now(CENTRAL)


def today():
    """Today in Central time as MM/DD/YYYY, whatever the server's timezone."""
    return now_central().strftime(config.DATE_FORMAT)


def now_iso():
    return now_central().isoformat()


def load_json(path, default=_MISSING):
    """Read a JSON file. A missing file returns default, or raises FileNotFoundError if none is given."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        if default is _MISSING:
            raise
        return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def delete_file(path, label="file"):
    """Delete path if it exists. Returns True if a file was deleted."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
            print(f"🗑️  Deleted {label}: {path}")
            return True
        print(f"⚠️  {label} not found: {path}")
    except Exception as e:
        print(f"❌ Failed to delete {label} {path}: {e}")
    return False


def set_github_output(**values):
    """Expose values to later workflow steps as steps.<id>.outputs.<name>. No-op outside Actions."""
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as gh:
            for k, v in values.items():
                gh.write(f"{k}={v}\n")
