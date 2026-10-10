"""People who asked to be taken down. Every stage (scrape, queue, posting, Pages) skips them.

Stored in removed.json as name hashes, so the public repo doesn't list who asked.
dms.py adds people; purge() strips them from the CSV, the queue and mugshots/.
"""
import csv
import hashlib
import os
from datetime import datetime, timezone

from . import config
from .common import delete_file, load_json, save_json


def _key(name):
    return hashlib.sha256(" ".join(name.upper().split()).encode()).hexdigest()


def load():
    return load_json(config.REMOVED_FILE, {})


def is_removed(name, removed=None):
    return bool(name) and _key(name) in (load() if removed is None else removed)


def add(name):
    removed = load()
    removed[_key(name)] = datetime.now(timezone.utc).date().isoformat()
    save_json(config.REMOVED_FILE, removed)


def purge():
    """Strip removed people from the CSV, the queue, and mugshots/. Returns how many records were dropped."""
    removed = load()
    if not removed:
        return 0
    dropped = 0

    if os.path.exists(config.CSV_FILE):
        with open(config.CSV_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields, rows = reader.fieldnames, list(reader)
        keep = [r for r in rows if not is_removed(r.get("Full Name"), removed)]
        if len(keep) < len(rows):
            for r in rows:
                if r not in keep:
                    delete_file(r.get("Mugshot_File"), label="mugshot")
            with open(config.CSV_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(keep)
            dropped += len(rows) - len(keep)

    if os.path.exists(config.QUEUE_FILE):
        q = load_json(config.QUEUE_FILE)
        inmates = []
        for i in q["inmates"]:
            if not is_removed(i["data"].get("Full Name"), removed):
                inmates.append(i)
                continue
            dropped += 1
            delete_file(i["data"].get("Mugshot_File"), label="mugshot")
            if i.get("posted"):
                # Keep the post time so slot timing still sees it, but drop the person's details
                inmates.append({**i, "data": {}})
        q["inmates"] = inmates
        q["total_inmates"] = len(inmates)
        q["posted_count"] = sum(1 for i in inmates if i.get("posted"))
        save_json(config.QUEUE_FILE, q)

    return dropped
