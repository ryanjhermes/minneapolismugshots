"""People who asked to be taken down. Every stage (scrape, queue, posting, Pages) skips them.

Stored as name hashes so the public repo doesn't list who asked.
"""
import csv
import hashlib
import json
import os
from datetime import datetime, timezone

REMOVED_FILE = "removed.json"


def _key(name):
    return hashlib.sha256(" ".join(name.upper().split()).encode()).hexdigest()


def load():
    try:
        with open(REMOVED_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def is_removed(name, removed=None):
    return bool(name) and _key(name) in (load() if removed is None else removed)


def add(name):
    removed = load()
    removed[_key(name)] = datetime.now(timezone.utc).date().isoformat()
    with open(REMOVED_FILE, "w", encoding="utf-8") as f:
        json.dump(removed, f, indent=2)


def _delete_mugshot(path):
    if path and os.path.isfile(path):
        os.remove(path)
        print(f"🗑️  Deleted {path}")


def purge(csv_file="jail_roster_data.csv", queue_file="posting_queue.json"):
    """Strip removed people from the CSV, the queue, and mugshots/. Returns how many records were dropped."""
    removed = load()
    if not removed:
        return 0
    dropped = 0

    if os.path.exists(csv_file):
        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields, rows = reader.fieldnames, list(reader)
        keep = [r for r in rows if not is_removed(r.get("Full Name"), removed)]
        if len(keep) < len(rows):
            for r in rows:
                if r not in keep:
                    _delete_mugshot(r.get("Mugshot_File"))
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(keep)
            dropped += len(rows) - len(keep)

    if os.path.exists(queue_file):
        with open(queue_file, encoding="utf-8") as f:
            q = json.load(f)
        inmates = []
        for i in q["inmates"]:
            if not is_removed(i["data"].get("Full Name"), removed):
                inmates.append(i)
                continue
            dropped += 1
            _delete_mugshot(i["data"].get("Mugshot_File"))
            if i.get("posted"):
                # Keep the post time so slot timing still sees it, but drop the person's details
                inmates.append({**i, "data": {}})
        q["inmates"] = inmates
        q["total_inmates"] = len(inmates)
        q["posted_count"] = sum(1 for i in inmates if i.get("posted"))
        with open(queue_file, "w", encoding="utf-8") as f:
            json.dump(q, f, indent=2, ensure_ascii=False)

    return dropped


if __name__ == "__main__":
    print(f"✅ Purged {purge()} removed record(s)")
