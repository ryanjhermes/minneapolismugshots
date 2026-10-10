"""Minneapolis Mugshots: scrape the Hennepin County Jail Roster and post to Instagram.

Run commands with `python -m bot <command>` from the repo root (see __main__.py).

    config.py         Every tunable: schedule, thresholds, file paths, URLs
    common.py         Central-time clock, JSON files, GitHub step outputs
    scraper.py        Selenium scrape of today's bookings -> CSV, mugshots/, queue
    ranking.py        Which inmates make the queue (charge, severity, CLIP, bail)
    clip_model.py     CLIP image scores (distinctiveness, is-it-a-mugshot)
    posting_queue.py  posting_queue.json: build, read, mark posted, clean up mugshots
    posting.py        Hourly slot decision, captions, post the next entry
    instagram.py      Meta Graph API publish (image or Reel)
    reels.py          ffmpeg Reels for the queue
    bmtn.py           Second mugshot source: Bring Me The News stories
    news.py           Daily news post from the same feed
    dms.py            Removal requests over Instagram DM
    removals.py       Hashed list of people taken down; purged everywhere
"""
