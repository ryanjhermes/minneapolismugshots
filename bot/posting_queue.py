"""posting_queue.json: what's queued, what's posted, and the mugshot files behind it.

    {
      "created_at": "<ISO time of the last nightly rebuild>",
      "total_inmates": 10, "posted_count": 2,
      "inmates": [{"id": 1, "data": {...}, "posted": false, "posted_at": null}, ...]
    }

`data` holds Full Name, Charge 1 (charges joined by config.CHARGE_SEPARATOR), Bail, Severity,
Mugshot_File, Booking_Date, and Reel_File once a Reel is rendered. Bring Me The News entries
(bmtn.py) also have Description, Story and Source_URL. A person removed on request keeps their posted
entry with empty data, so slot timing still sees the post.
"""
import os
from datetime import datetime, timedelta

import pytz

from . import config, ranking, removals
from .common import delete_file, load_json, now_iso, save_json, today


def load():
    """The queue dict. Raises FileNotFoundError if there is none yet."""
    return load_json(config.QUEUE_FILE)


def save(q):
    save_json(config.QUEUE_FILE, q)


def build(inmates):
    """Nightly rebuild from a fresh scrape: today's top config.QUEUE_SIZE inmates, plus the
    entries that must survive a rebuild (recent posts and unposted news mugshots)."""
    print(f"💾 Creating posting queue with {len(inmates)} inmates...")
    try:
        old = load()['inmates']
    except Exception:
        old = []

    # Anyone posted in the last 24h stays, so a rebuild never re-queues them
    # and the record survives any number of same-day rebuilds
    cutoff = datetime.now(pytz.utc) - timedelta(hours=24)
    kept = [i for i in old if i.get('posted') and i.get('posted_at')
            and datetime.fromisoformat(i['posted_at']) >= cutoff]
    # Bring Me The News stories (bmtn.py) not yet posted stay queued, ahead of tonight's inmates
    news_pending = [i for i in old if not i.get('posted') and i['data'].get('Source_URL')]
    skip = {i['data'].get('Full Name') for i in old if i.get('posted') or i in news_pending}
    if skip:
        print(f"⏭️  Skipping {len(skip)} already posted or queued from news: {', '.join(sorted(skip))}")
        inmates = [d for d in inmates if d.get('Full Name') not in skip]

    top = ranking.rank(inmates, config.QUEUE_SIZE)
    booking_date = today()
    for d in top:
        d['Booking_Date'] = booking_date

    entries = kept + news_pending + [{'data': d, 'posted': False, 'posted_at': None} for d in top]
    for n, entry in enumerate(entries, 1):
        entry['id'] = n
    save({
        'created_at': now_iso(),
        'total_inmates': len(entries),
        'posted_count': len(kept),
        'inmates': entries,
    })
    print(f"✅ Posting queue saved: {len(top)} of {len(inmates)} inmates queued")


def insert_ahead(new_data):
    """Queue entries ahead of every unposted jail inmate so they go out in the next slots (bmtn.py)."""
    q = load()
    first_unposted = next((n for n, i in enumerate(q['inmates']) if not i.get('posted')), len(q['inmates']))
    next_id = max((i.get('id', 0) for i in q['inmates']), default=0) + 1
    for n, data in enumerate(new_data):
        q['inmates'].insert(first_unposted + n, {'id': next_id + n, 'data': data, 'posted': False, 'posted_at': None})
    q['total_inmates'] = len(q['inmates'])
    save(q)


def next_to_post():
    """The next unposted entry that isn't on the removal list, or None."""
    try:
        q = load()
        removed = removals.load()
        pending = [i for i in q['inmates']
                   if not i['posted'] and not removals.is_removed(i['data'].get('Full Name'), removed)]
    except FileNotFoundError:
        print("📭 No posting queue found")
        return None
    except Exception as e:
        print(f"❌ Error reading posting queue: {e}")
        return None
    if not pending:
        print("✅ All inmates have been posted!")
        return None
    entry = pending[0]
    path = entry['data'].get('Mugshot_File', '')
    print(f"📊 Remaining in queue: {len(pending)} total")
    print(f"🔍 Next: {entry['data'].get('Full Name', 'Unknown')} ({path}, exists: {bool(path) and os.path.exists(path)})")
    return entry


def mark_posted(ids):
    """Mark entries posted now, then delete their mugshots."""
    try:
        q = load()
        marked = 0
        for i in q['inmates']:
            if i['id'] in ids:
                i['posted'] = True
                i['posted_at'] = now_iso()
                marked += 1
        q['posted_count'] = sum(1 for i in q['inmates'] if i['posted'])
        save(q)
        print(f"✅ Marked {marked} inmates as posted ({q['posted_count']}/{q['total_inmates']} total)")
        if marked:
            delete_mugshots(ids)
    except Exception as e:
        print(f"❌ Error updating posting queue: {e}")


def delete_mugshots(ids):
    """Delete the mugshots (repo and docs/ copies) of the given entries. Returns True if any were deleted."""
    try:
        q = load()
        deleted, missing = 0, []
        for i in q['inmates']:
            path = i['data'].get('Mugshot_File', '')
            if i['id'] not in ids or not path or path == 'No Image':
                continue
            if not path.startswith(f'{config.MUGSHOTS_DIR}/'):
                path = f"{config.MUGSHOTS_DIR}/{path}"
            if delete_file(path, label="mugshot"):
                deleted += 1
            else:
                missing.append(path)
            delete_file(os.path.join('docs', config.MUGSHOTS_DIR, os.path.basename(path)), label="docs mugshot")
        print(f"🗑️  Cleanup Summary: {deleted} files deleted" + (f", {len(missing)} not found" if missing else ""))
        return deleted > 0
    except Exception as e:
        print(f"❌ Error during mugshot cleanup: {e}")
        return False


def cleanup_posted():
    """Delete the mugshots of every posted entry (posting already does this; this catches leftovers)."""
    try:
        posted = [i['id'] for i in load()['inmates'] if i.get('posted', False)]
        if not posted:
            print("✅ No posted inmates found to clean up")
            return
        if not delete_mugshots(posted):
            print("⚠️  No mugshot files found to delete")
    except Exception as e:
        print(f"❌ Error cleaning up posted mugshots: {e}")


def purge_unqueued():
    """Delete every mugshot not needed by an unposted queue entry.
    Skips entirely if the queue can't be read, so a broken scrape never wipes upcoming posts."""
    try:
        keep = {os.path.basename(i['data'].get('Mugshot_File', ''))
                for i in load()['inmates'] if not i.get('posted')}
    except Exception as e:
        print(f"⚠️  Queue unreadable, skipping mugshot purge: {e}")
        return

    deleted = 0
    if os.path.isdir(config.MUGSHOTS_DIR):
        for fn in os.listdir(config.MUGSHOTS_DIR):
            if fn.lower().endswith(('.jpg', '.jpeg', '.png')) and fn not in keep:
                os.remove(os.path.join(config.MUGSHOTS_DIR, fn))
                deleted += 1
    print(f"🧹 Purged {deleted} mugshots not in the posting queue (kept {len(keep)})")


def check():
    """Print queue status: counts, the next entry, and leftover mugshots of posted entries."""
    try:
        q = load()
    except FileNotFoundError:
        print("📭 No posting queue found. Run 'python -m bot scrape' to create one")
        return
    except Exception as e:
        print(f"❌ Error checking queue: {e}")
        return

    total, posted = q.get('total_inmates', 0), q.get('posted_count', 0)
    print(f"📊 QUEUE STATUS:\n   Total inmates: {total}\n   Posted: {posted}\n   Pending: {total - posted}"
          f"\n   Created: {q.get('created_at', 'Unknown')}")
    unposted = [i for i in q['inmates'] if not i['posted']]
    if unposted:
        print(f"\n📋 Next inmate to post: {unposted[0]['data'].get('Full Name', 'Unknown')}")
    else:
        print("✅ All inmates have been posted!")

    leftovers = 0
    for i in q['inmates']:
        path = i['data'].get('Mugshot_File', '')
        if i.get('posted') and path and path != 'No Image':
            if not path.startswith(f'{config.MUGSHOTS_DIR}/'):
                path = f"{config.MUGSHOTS_DIR}/{path}"
            leftovers += os.path.exists(path)
    if leftovers:
        print(f"\n⚠️  {leftovers} posted inmates still have mugshot files. Run 'python -m bot cleanup-posted'")
