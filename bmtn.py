"""Second mugshot source: Bring Me The News crime stories whose lead image is a booking photo.

The tag page is behind bot protection, so this reads the site's public RSS feed and keeps
items tagged Config.BMTN_CATEGORY. A story qualifies when its lead image is named after a
person mentioned in the story and CLIP says it is a mugshot (victim and family photos fail).
Qualifying stories go to the front of posting_queue.json and post in the next slot.

python bmtn.py --check     # Print new=N (no model needed); used to skip the heavy install
python bmtn.py --dry-run   # Show what would be queued, change nothing
python bmtn.py             # Queue new mugshot stories, save bmtn_state.json
"""
import html
import json
import os
import re
import sys

import requests
from PIL import Image

import removals
from data import Config, get_current_date

STATE_FILE = "bmtn_state.json"
HEADERS = {'User-Agent': 'Mozilla/5.0'}
# Lead images with these words in the filename are never a named person
GENERIC_WORDS = {'untitled', 'screenshot', 'screen', 'shot', 'police', 'stock', 'pixabay', 'tape',
                 'image', 'photo', 'file', 'crash', 'fire', 'scene', 'court', 'jail', 'car', 'squad'}
NAME_SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv'}
# Free extractive QA model (~500 MB) that pulls the charge out of the story text
QA_MODEL = "deepset/roberta-base-squad2"
QA_MIN_SCORE = 0.1


def load_state():
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'seen': []}


def _cdata(item, tag):
    m = re.search(rf'<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>', item, re.S)
    return html.unescape(m.group(1).strip()) if m else ''


def fetch_items():
    """Crime items from the RSS feed: [{url, title, description, text, image}]"""
    feed = requests.get(Config.BMTN_FEED_URL, headers=HEADERS, timeout=30).text
    items = []
    for item in re.findall(r'<item>(.*?)</item>', feed, re.S):
        if Config.BMTN_CATEGORY not in re.findall(r'<category><!\[CDATA\[(.*?)\]\]>', item):
            continue
        image = re.search(r'<enclosure url="([^"]+)"', item)
        content = _cdata(item, 'content:encoded')
        items.append({
            'url': _cdata(item, 'link'),
            'title': _cdata(item, 'title'),
            'description': _cdata(item, 'description'),
            'text': re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', content))),
            'image': html.unescape(image.group(1)) if image else '',
        })
    return items


def find_name(item):
    """'LAST, FIRST MIDDLE' when the lead image is named after someone in the story, else ''"""
    slug = os.path.basename(item['image'].split('?')[0]).rsplit('.', 1)[0].lower()
    words = [w for w in slug.split('-') if w not in NAME_SUFFIXES]
    if not 2 <= len(words) <= 4 or not all(w.isalpha() for w in words) or GENERIC_WORDS & set(words):
        return ''
    # Hyphenated surnames lose the hyphen in the slug: match either
    text = f"{item['title']} {item['description']} {item['text']}"
    m = re.search(r'\b' + r'[\s-]'.join(map(re.escape, words)) + r'\b', text, re.I)
    if not m:
        return ''
    parts = m.group(0).upper().split()
    # Surname = longest ending the story uses on its own ("Lopez Xique went..."), else the last word
    full = len(re.findall(re.escape(m.group(0)), text, re.I))
    k = next((k for k in range(1, len(parts) - 1)
              if len(re.findall(r'\b' + re.escape(' '.join(parts[k:])) + r'\b', text, re.I)) > full), len(parts) - 1)
    return f"{' '.join(parts[k:])}, {' '.join(parts[:k])}"


def find_charges(item, name, qa):
    last, _, given = name.partition(', ')
    r = qa(question=f"What crime is {given.title()} {last.title()} charged with or convicted of?",
           context=f"{item['description']} {item['text']}"[:4000])
    charge = r['answer'].strip(' .,').upper()
    if r['score'] < QA_MIN_SCORE or not 3 < len(charge) <= Config.MAX_CHARGE_LENGTH:
        return 'No charge listed'
    return charge


def save_mugshot(url, name):
    """Download, trim the black pillarbox the site adds, center-crop to 4:5 like the jail
    mugshots so it fills the Reel frame, save as JPEG. Returns the path."""
    path = os.path.join(Config.MUGSHOTS_DIR, f"mugshot_{'_'.join(name.replace(',', '').split())}.jpg")
    os.makedirs(Config.MUGSHOTS_DIR, exist_ok=True)
    tmp = path + '.download'
    with open(tmp, 'wb') as f:
        f.write(requests.get(url, headers=HEADERS, timeout=30).content)
    image = Image.open(tmp).convert('RGB')
    box = image.convert('L').point(lambda p: p > 20 and 255).getbbox()
    image = image.crop(box) if box else image
    w, h = image.size
    if w * 5 > h * 4:
        cw = h * 4 // 5
        image = image.crop(((w - cw) // 2, 0, (w - cw) // 2 + cw, h))
    image.save(path, 'JPEG', quality=92)
    os.remove(tmp)
    return path


def queue_entries(entries):
    """Put entries ahead of every unposted jail inmate so they go out in the next slots"""
    with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
        q = json.load(f)
    first_unposted = next((n for n, i in enumerate(q['inmates']) if not i.get('posted')), len(q['inmates']))
    next_id = max((i.get('id', 0) for i in q['inmates']), default=0) + 1
    for n, data in enumerate(entries):
        q['inmates'].insert(first_unposted + n, {'id': next_id + n, 'data': data, 'posted': False, 'posted_at': None})
    q['total_inmates'] = len(q['inmates'])
    with open(Config.QUEUE_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(q, f, indent=2, ensure_ascii=False)


def run(dry_run=False, check=False):
    state = load_state()
    seen = set(state['seen'])
    items = [i for i in fetch_items() if i['url'] not in seen]
    if check:
        print(f"new={len(items)}")
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as gh:
                gh.write(f"new={len(items)}\n")
        return

    from mugshot_ranker import mugshot_probability
    from transformers import pipeline
    qa = pipeline("question-answering", model=QA_MODEL)
    try:
        with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
            queued = {i['data'].get('Full Name') for i in json.load(f)['inmates']}
    except FileNotFoundError:
        queued = set()
    removed = removals.load()

    entries = []
    for item in items:
        name = find_name(item)
        if not name or name in queued or removals.is_removed(name, removed):
            print(f"⏭️  {item['title']} ({'no named lead image' if not name else 'already queued or removed'})")
            continue
        path = save_mugshot(item['image'], name)
        p = mugshot_probability(path)
        if p < Config.BMTN_MIN_MUGSHOT_PROB:
            print(f"⏭️  {item['title']} (lead image is not a mugshot, {p:.2f})")
            os.remove(path)
            continue
        data = {'Full Name': name, 'Charge 1': find_charges(item, name, qa), 'Bail': '', 'Mugshot_File': path,
                'Severity': '', 'Booking_Date': get_current_date(),
                'Description': item['description'], 'Source_URL': item['url']}
        print(f"📰 {name} | {data['Charge 1']} | mugshot {p:.2f}\n   {item['title']}")
        entries.append(data)
        queued.add(name)

    if dry_run:
        for d in entries:
            os.remove(d['Mugshot_File'])
        print(f"🧪 DRY RUN - would queue {len(entries)} of {len(items)} new crime stories")
        return
    if entries:
        queue_entries(entries)
    state['seen'] = sorted(seen | {i['url'] for i in items})
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    print(f"✅ Queued {len(entries)} of {len(items)} new crime stories")
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as gh:
            gh.write(f"queued={len(entries)}\n")


if __name__ == "__main__":
    run(dry_run='--dry-run' in sys.argv, check='--check' in sys.argv)
