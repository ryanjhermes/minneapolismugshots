"""Second mugshot source: Bring Me The News crime stories whose lead image is a booking photo.

The tag page is behind bot protection, so this reads the site's public RSS feed and keeps
items tagged config.BMTN_CATEGORY. A story qualifies when its lead image is named after a
person mentioned in the story and CLIP says it is a mugshot (victim and family photos fail).
Qualifying stories go to the front of posting_queue.json and post in the next slot.

python -m bot bmtn --check     # Print new=N (no model needed); used to skip the heavy install
python -m bot bmtn --dry-run   # Show what would be queued, change nothing
python -m bot bmtn             # Queue new mugshot stories, save bmtn_state.json

news.py reads the same feed (fetch_items) for the daily news post.
"""
import html
import os
import re
from email.utils import parsedate_to_datetime

import requests
from PIL import Image

from . import config, posting_queue, removals
from .common import load_json, save_json, set_github_output, today

HEADERS = {'User-Agent': 'Mozilla/5.0'}
# Lead images with these words in the filename are never a named person
GENERIC_WORDS = {'untitled', 'screenshot', 'screen', 'shot', 'police', 'stock', 'pixabay', 'tape',
                 'image', 'photo', 'file', 'crash', 'fire', 'scene', 'court', 'jail', 'car', 'squad'}
NAME_SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv'}
# Free extractive QA model (~500 MB) that pulls the charge out of the story text
QA_MODEL = "deepset/roberta-base-squad2"
QA_MIN_SCORE = 0.1


def _cdata(item, tag):
    m = re.search(rf'<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>', item, re.S)
    return html.unescape(m.group(1).strip()) if m else ''


def story_paragraphs(content):
    """The article's paragraphs from content:encoded, stopping at the "Related Articles" list and
    skipping newsletter plugs."""
    content = re.split(r'<h2>\s*Related Articles', content)[0]
    paras = (re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', p))).strip()
             for p in re.findall(r'<p[^>]*>(.*?)</p>', content, re.S))
    return [p for p in paras if p and not re.match(r'Sign up for .*newsletter', p, re.I)]


def fetch_items():
    """Crime items from the RSS feed: [{url, title, description, text, story, image, published}]"""
    feed = requests.get(config.BMTN_FEED_URL, headers=HEADERS, timeout=30).text
    items = []
    for item in re.findall(r'<item>(.*?)</item>', feed, re.S):
        if config.BMTN_CATEGORY not in re.findall(r'<category><!\[CDATA\[(.*?)\]\]>', item):
            continue
        image = re.search(r'<enclosure url="([^"]+)"', item)
        content = _cdata(item, 'content:encoded')
        items.append({
            'url': _cdata(item, 'link'),
            'title': _cdata(item, 'title'),
            'description': _cdata(item, 'description'),
            'text': re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', content))),
            'story': story_paragraphs(content),
            # Drop the ?profile=rss resize: it's a 16:9 crop that cuts the mugshot off at the chin
            'image': html.unescape(image.group(1)).split('?')[0] if image else '',
            'published': parsedate_to_datetime(_cdata(item, 'pubDate')),
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
    if r['score'] < QA_MIN_SCORE or not 3 < len(charge) <= config.MAX_CHARGE_LENGTH:
        return 'No charge listed'
    return charge


def save_mugshot(url, name):
    """Download, trim the black pillarbox the site adds, center-crop to 4:5 like the jail
    mugshots so it fills the Reel frame, save as JPEG. Returns the path."""
    path = os.path.join(config.MUGSHOTS_DIR, f"mugshot_{'_'.join(name.replace(',', '').split())}.jpg")
    os.makedirs(config.MUGSHOTS_DIR, exist_ok=True)
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
    image.thumbnail((800, 1000))  # The Reel's photo size; the full-size original is up to 1920px
    image.save(path, 'JPEG', quality=92)
    os.remove(tmp)
    return path


def run(dry_run=False, check=False):
    """check: only count new stories. dry_run: run the models, queue and save nothing."""
    state = load_json(config.BMTN_STATE_FILE, {'seen': []})
    seen = set(state['seen'])
    # Stories news.py already posted as the daily news post aren't posted again as mugshots
    seen |= {p['url'] for p in load_json(config.NEWS_STATE_FILE, {'posted': []})['posted']}
    items = [i for i in fetch_items() if i['url'] not in seen]
    if check:
        print(f"new={len(items)}")
        set_github_output(new=len(items))
        return

    # Heavy imports only after the cheap check: the workflow installs them only when there are new stories
    from transformers import pipeline as hf_pipeline
    from .clip_model import mugshot_probability
    qa = hf_pipeline("question-answering", model=QA_MODEL)
    queued = {i['data'].get('Full Name') for i in load_json(config.QUEUE_FILE, {'inmates': []})['inmates']}
    removed = removals.load()

    entries = []
    for item in items:
        name = find_name(item)
        if not name or name in queued or removals.is_removed(name, removed):
            print(f"⏭️  {item['title']} ({'no named lead image' if not name else 'already queued or removed'})")
            continue
        path = save_mugshot(item['image'], name)
        p = mugshot_probability(path)
        if p < config.BMTN_MIN_MUGSHOT_PROB:
            print(f"⏭️  {item['title']} (lead image is not a mugshot, {p:.2f})")
            os.remove(path)
            continue
        data = {'Full Name': name, 'Charge 1': find_charges(item, name, qa), 'Bail': '', 'Mugshot_File': path,
                'Severity': '', 'Booking_Date': today(),
                'Description': item['description'], 'Story': '\n\n'.join(item['story']), 'Source_URL': item['url']}
        print(f"📰 {name} | {data['Charge 1']} | mugshot {p:.2f}\n   {item['title']}")
        entries.append(data)
        queued.add(name)

    if dry_run:
        for d in entries:
            os.remove(d['Mugshot_File'])
        print(f"🧪 DRY RUN - would queue {len(entries)} of {len(items)} new crime stories")
        return
    if entries:
        posting_queue.insert_ahead(entries)
    state['seen'] = sorted(seen | {i['url'] for i in items})
    save_json(config.BMTN_STATE_FILE, state)
    print(f"✅ Queued {len(entries)} of {len(items)} new crime stories")
    set_github_output(queued=len(entries))
