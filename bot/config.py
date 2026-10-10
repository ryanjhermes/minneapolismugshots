"""Every tunable in one place: schedule, thresholds, file paths, URLs.

Paths are relative to the repo root, so run everything from there (`python -m bot ...`).
Model names and prompt lists live next to the code that uses them (clip_model.py, bmtn.py, news.py).
"""
from dotenv import load_dotenv

# Local runs read ACCESS_TOKEN / APP_ID / BUSINESS_ID from .env; CI writes .env or sets env vars
load_dotenv()

# --- State files (all committed by the workflows except reels/) ---
CSV_FILE = "jail_roster_data.csv"        # Last scrape, also published on Pages
QUEUE_FILE = "posting_queue.json"        # What's queued and posted (see posting_queue.py)
MUGSHOTS_DIR = "mugshots"                # Images for queued posts, served by Pages
REELS_DIR = "reels"                      # Rendered Reels, Pages only (gitignored)
NEWS_STATE_FILE = "news_state.json"      # Stories news.py has scored or posted
BMTN_STATE_FILE = "bmtn_state.json"      # Stories bmtn.py has checked
DM_STATE_FILE = "dm_state.json"          # DM threads and the last check time
REMOVED_FILE = "removed.json"            # Hashed names of people who asked to be taken down

# --- Instagram / Meta ---
GRAPH_API = "https://graph.facebook.com/v23.0"
# Instagram only accepts media by public URL, so mugshots and Reels are served from GitHub Pages
PAGES_URL = "https://ryanjhermes.github.io/minneapolismugshots"

# --- Posting schedule ---
# Central-time hours that get one post each (peak Instagram hours). See posting.preflight
POSTING_HOURS = [7, 9, 11, 12, 13, 17, 19, 20]
QUEUE_SIZE = 10  # Inmates queued per nightly scrape
DISCLAIMER = "Charges are allegations, not convictions. All persons are presumed innocent until proven guilty in a court of law."
SOURCE = "Source: Hennepin County Jail Roster (public booking data, Minn. Stat. § 13.82)"
REEL_SECONDS = 7
REEL_HEADER = "MINNEAPOLIS MUGSHOTS"

# --- Ranking (ranking.py) ---
# Added to the 0..1 distinctiveness score, by most severe charge
SEVERITY_BONUS = {'Felony': 0.2, 'Gross Misdemeanor': 0.1, 'Misdemeanor': 0.0, '': 0.0}

# --- Daily news post (news.py): one story a day at this Central hour, only if it scores high enough ---
NEWS_POSTING_HOUR = 18
NEWS_MIN_SCORE = 0.5

# --- Second mugshot source (bmtn.py): Bring Me The News crime stories with a booking photo ---
BMTN_FEED_URL = "https://bringmethenews.com/.rss/full/"
BMTN_CATEGORY = "MN Crime"
BMTN_MIN_MUGSHOT_PROB = 0.8  # CLIP check that the lead image is a booking photo

# --- Scraping (scraper.py) ---
JAIL_ROSTER_URL = "https://jailroster.hennepin.us/"
DATE_FORMAT = "%m/%d/%Y"  # The roster's date format
DEFAULT_INMATE_LIMIT = 100
TEST_INMATE_LIMIT = 25
CLICK_WAIT_TIME = 3
MODAL_WAIT_TIME = 5
MODAL_CHARGE_WAIT_TIMEOUT = 10
MODAL_CHARGE_WAIT_TIMEOUT_CI = 25  # GitHub runners load the modal slower

MIN_NAME_LENGTH = 3
MAX_NAME_LENGTH = 50
MIN_CHARGE_LENGTH = 5
MAX_CHARGE_LENGTH = 150  # Longer means a block of page text was grabbed, not a charge
MAX_CHARGES = 3
CHARGE_SEPARATOR = '; '  # Joins multiple charges in 'Charge 1'

# Labels the modal shows before the inmate's name
NAME_PATTERNS = ['Full Name:', 'Name:', 'Inmate Name:', 'Arrestee Name:', 'Defendant Name:', 'Subject Name:']
MODAL_SELECTORS = ['[role="dialog"]', '.modal', '[class*="modal"]', '[class*="dialog"]']
# Values that are field labels or placeholders, not real data
INVALID_CHARGES = ['No charge listed', 'Charge information not available', 'Severity of Charge:',
                   'Description:', 'Charge Status:']
INVALID_BAILS = ['NO BAIL INFORMATION', 'NO BAIL REQUIRED', 'No bail information', 'No bail', 'No Bail',
                 'No bail required']
