"""Hourly posting: decide whether this run posts (preflight), then post the next queued mugshot.

Posts go out as a Reel when one was rendered (reels.py), falling back to the still image.
Captions start with "NAME: LAST, FIRST" on its own line; dms.py finds posts by that line.
"""
import os
import re
from datetime import datetime

from . import config, instagram, posting_queue
from .common import CENTRAL, load_json, now_central

# Bail values that mean "no real bail info" (any case of "Next Court Appearance" also counts)
NO_BAIL_MARKERS = ['No bail information', 'No Bail Information', 'None', 'Unknown']
NO_CHARGE_VALUES = ['No charge listed', 'Charge information not available', '']
MAX_CAPTION = 2200  # Instagram's caption limit
STORY_PARAGRAPHS = 4  # Lead of a Bring Me The News story in its caption, not the whole article (copyright)


def fit_story(story, limit):
    """The first STORY_PARAGRAPHS paragraphs that fit in limit characters, else as many whole sentences of the first one."""
    out = ""
    for para in story.split("\n\n")[:STORY_PARAGRAPHS]:
        trial = f"{out}\n\n{para}" if out else para
        if len(trial) > limit:
            break
        out = trial
    if not out:
        for sentence in re.split(r"(?<=[.!?\u201d])\s+", story):
            if len(out) + len(sentence) + 1 > limit:
                break
            out = f"{out} {sentence}".strip()
    return out


def caption(data):
    """Instagram caption for a queue entry's data: jail roster format, or the Bring Me The News format."""
    try:
        name = data.get('Full Name', 'Unknown').strip()
        charge = data.get('Charge 1', 'No charge listed').strip()
        bail = data.get('Bail', 'No bail information').strip()

        no_bail = not bail or any(m in bail for m in NO_BAIL_MARKERS) or 'NEXT COURT APPEARANCE' in bail.upper()
        bail_display = 'N/A' if no_bail else bail

        charge_line = ""
        if charge not in NO_CHARGE_VALUES:
            label = "BOOKING CHARGES" if config.CHARGE_SEPARATOR in charge else "BOOKING CHARGE"
            if data.get('Source_URL'):
                label = label.replace("BOOKING ", "")
            charge_line = f"{label}: {charge}\n"

        # Bring Me The News story (bmtn.py): its first paragraphs first, then the usual lines and link
        if data.get('Source_URL'):
            rest = f"""{charge_line}NAME: {name}

{config.DISCLAIMER}

#minneapolismugshots #Minnesota #Arrest #MNcrime #Minneapolis

Source: Bring Me The News, {data['Source_URL']}"""
            story = fit_story(data.get('Story') or data.get('Description', ''), MAX_CAPTION - len(rest) - 2)
            return f"{story}\n\n{rest}" if story else rest

        return f"""
{charge_line}NAME: {name}
BAIL: {bail_display}

Booking Date: {data.get('Booking_Date') or 'N/A'}
Hennepin County, MN

{config.DISCLAIMER}

#minneapolismugshots #HennepinCounty #Arrest #PublicRecord #Minnesota #Minneapolis

{config.SOURCE}"""

    except Exception as e:
        print(f"❌ Error generating caption: {e}")
        return f"🚨 Minneapolis Arrest Alert - {data.get('Full Name', 'Unknown')}"


def preflight():
    """What this posting run should do: ('post' | '', reason).

    Scheduled runs post if nothing has gone out since the most recent config.POSTING_HOURS slot
    started, so a run GitHub starts late still posts, and missed earlier slots don't pile up into
    a burst. Manual runs post whatever is pending."""
    try:
        q = load_json(config.QUEUE_FILE)
    except Exception as e:
        return '', f'no_queue ({e})'

    now = now_central()
    posted_times = [datetime.fromisoformat(i['posted_at']).astimezone(CENTRAL)
                    for i in q['inmates'] if i.get('posted') and i.get('posted_at')]
    pending = sum(1 for i in q['inmates'] if not i.get('posted'))

    if os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        return ('post', 'manual') if pending else ('', 'manual_nothing_pending')
    started = [h for h in config.POSTING_HOURS if h <= now.hour]
    if not started:
        return '', f'before_first_slot_{now.hour}'
    slot_start = now.replace(hour=started[-1], minute=0, second=0, microsecond=0)
    if any(t >= slot_start for t in posted_times):
        return '', f'slot_{started[-1]}_already_posted'
    return ('post', f'slot_{started[-1]}') if pending else ('', 'queue_empty')


def post_next(test_mode=False):
    """Post the next queued entry and mark it posted. Returns False if posting failed
    (the workflow then fails), True if it posted or there was nothing to post.
    test_mode logs the would-be post and leaves the queue and mugshots untouched."""
    try:
        entry = posting_queue.next_to_post()
        if not entry:
            print("📭 No inmates to post at this time")
            return True

        creds = instagram.credentials()
        if not creds['access_token']:
            print("⚠️  No Meta API credentials found - skipping Instagram posting")
            return False

        data = entry['data']
        name = data.get('Full Name', 'Unknown')
        print(f"\n📱 Posting inmate #{entry['id']}: {name}")
        try:
            image_url = f"{config.PAGES_URL}/{config.MUGSHOTS_DIR}/{os.path.basename(data.get('Mugshot_File', ''))}"
            text = caption(data)
            print(f"🖼️  Image URL: {image_url}\n📝 Caption preview: {text[:100]}...")

            success = False
            if data.get('Reel_File'):
                success = instagram.post(image_url, text, creds, test_mode,
                                         video_url=f"{config.PAGES_URL}/{data['Reel_File']}")
                if not success:
                    print("⚠️  Reel failed, falling back to image post")
            if not success:
                success = instagram.post(image_url, text, creds, test_mode)
        except Exception as e:
            print(f"❌ Error processing inmate #{entry['id']}: {e}")
            success = False

        if not success:
            print(f"❌ Failed to post {name}")
            return False
        print(f"✅ Successfully posted {name}")
        if not test_mode:
            posting_queue.mark_posted([entry['id']])
        return True

    except Exception as e:
        print(f"❌ Error in posting process: {e}")
        return False
