"""Instagram DM handler: auto-removes posts on request, leaves everything else unread.

Each run reads conversations updated since the last run:
- Removal request that names a posted person (or links the post): delete it, reply DONE_REPLY.
- Removal request we can't match: reply ASK_REPLY once.
- Still no match after that: stop replying, leave the thread for a human.
- Anything else: untouched (no reply, never marked seen).

Usage: python dms.py [--dry-run]
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

API = "https://graph.facebook.com/v23.0"
STATE_FILE = "dm_state.json"
REMOVAL_RE = re.compile(r"remov|delet|take\W*(\w+\W+){0,3}down|takedown|unpost", re.I)
POST_LINK_RE = re.compile(r"instagram\.com/(?:p|reel|reels)/([\w-]+)", re.I)
DONE_REPLY = "Done, the post has been removed."
ASK_REPLY = "Sorry, we couldn't find that post. What's the full name on it? A link to the post works too."

TOKEN = os.getenv("ACCESS_TOKEN", "")
IG_ID = os.getenv("BUSINESS_ID", "")
DRY_RUN = "--dry-run" in sys.argv


def api(method, path, token=TOKEN, **kwargs):
    r = requests.request(method, path if path.startswith("http") else f"{API}/{path}",
                         params={"access_token": token, **kwargs.pop("params", {})}, **kwargs)
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"{method} {path}: {data['error'].get('message')}")
    return data


def paged(path, token=TOKEN, **params):
    data = api("GET", path, token, params=params)
    while True:
        yield from data.get("data", [])
        nxt = data.get("paging", {}).get("next")
        if not nxt:
            return
        data = api("GET", nxt, token)


def page_auth():
    """Messaging runs through the linked Facebook Page: return (page_id, page_token)."""
    try:
        for p in paged("me/accounts", fields="id,access_token,instagram_business_account"):
            if p.get("instagram_business_account", {}).get("id") == IG_ID:
                return p["id"], p["access_token"]
    except RuntimeError:
        pass  # ACCESS_TOKEN is already a Page token
    return api("GET", "me", params={"fields": "id"})["id"], TOKEN


def parse_time(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def load_posts():
    """Every post on the account as {id, permalink, name: 'LAST, FIRST MIDDLE'}."""
    posts = []
    for m in paged(f"{IG_ID}/media", fields="id,caption,permalink", limit=100):
        name = re.search(r"NAME:\s*(.+)", m.get("caption") or "")
        posts.append({"id": m["id"], "permalink": m.get("permalink", ""),
                      "name": name.group(1).strip().upper() if name else ""})
    return posts


def find_posts(text, posts):
    """Posts the message points at: a pasted link, or first + last name (middle breaks ties)."""
    codes = {c.lower() for c in POST_LINK_RE.findall(text)}
    linked = [p for p in posts if any(f"/{c}/" in p["permalink"].lower() for c in codes)]
    if linked:
        return linked

    words = set(re.findall(r"[A-Z'-]+", text.upper()))
    hits = {}
    for p in posts:
        last, _, rest = p["name"].partition(",")
        given = rest.split()
        if given and set(last.split()) <= words and given[0] in words:
            hits.setdefault(p["name"], []).append(p)
    if len(hits) > 1:  # e.g. SMITH, JOHN A vs SMITH, JOHN B
        hits = {n: ps for n, ps in hits.items() if set(n.partition(",")[2].split()) <= words}
    # Only act on exactly one person; anything vaguer gets the follow-up question
    return next(iter(hits.values())) if len(hits) == 1 else []


def reply(page_id, page_token, user_id, text):
    print(f"   💬 Reply: {text}")
    if not DRY_RUN:
        api("POST", f"{page_id}/messages", page_token,
            json={"recipient": {"id": user_id}, "messaging_type": "RESPONSE", "message": {"text": text}})


def main():
    if not TOKEN or not IG_ID:
        sys.exit("❌ Missing ACCESS_TOKEN or BUSINESS_ID")

    try:
        state = json.load(open(STATE_FILE))
    except FileNotFoundError:
        # First run: only look back as far as Instagram still lets us reply
        state = {"last_check": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(), "threads": {}}
    since = datetime.fromisoformat(state["last_check"])
    run_started = datetime.now(timezone.utc)
    threads = state["threads"]  # conversation id -> "asked" | "handoff"

    page_id, page_token = page_auth()
    posts = None
    handoffs = []

    for conv in paged(f"{page_id}/conversations", page_token, platform="instagram", limit=25,
                      fields="id,updated_time,messages.limit(20){id,created_time,from,message}"):
        if parse_time(conv["updated_time"]) <= since:
            break  # newest first, so everything after this is already handled
        cid, stage = conv["id"], threads.get(conv["id"])
        new = [m for m in conv.get("messages", {}).get("data", [])
               if m["from"]["id"] != IG_ID and parse_time(m["created_time"]) > since]
        if not new or stage == "handoff":
            continue

        user = new[0]["from"]
        text = "\n".join(m.get("message") or "" for m in reversed(new))
        print(f"📩 @{user.get('username', user['id'])}: {text[:200]!r}")

        if stage != "asked" and not REMOVAL_RE.search(text):
            print("   👀 Not a removal request, left for a human")
            handoffs.append(user.get("username", user["id"]))
            continue

        if posts is None:
            posts = load_posts()
        matches = find_posts(text, posts)
        if matches:
            for p in matches:
                print(f"   🗑️  Deleting {p['name']} {p['permalink']}")
                if not DRY_RUN:
                    api("DELETE", p["id"])
            reply(page_id, page_token, user["id"], DONE_REPLY)
            threads.pop(cid, None)
        elif stage == "asked":
            print("   👀 Still no match, left for a human")
            handoffs.append(user.get("username", user["id"]))
            threads[cid] = "handoff"
        else:
            reply(page_id, page_token, user["id"], ASK_REPLY)
            threads[cid] = "asked"

    print(f"✅ Done. Left for a human: {', '.join(handoffs) or 'none'}")
    if DRY_RUN:
        print("🧪 Dry run: nothing sent, deleted, or saved")
        return
    state["last_check"] = run_started.isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


if __name__ == "__main__":
    main()
