# Minneapolis Mugshots

Automated, public-record coverage of bookings at the Hennepin County Jail, posted to
[@minneapolismugshots](https://instagram.com/minneapolismugshots) on Instagram.

## What it does

Every night the system reads the [Hennepin County Jail Roster](https://jailroster.hennepin.us/) for that day's
bookings. It saves each booking's name, charges, charge severity, bail and booking photo, and picks up to 10 to
post the next day. It also picks up booking photos published in Bring Me The News crime coverage and posts one
local crime news story each evening.

## Public data

- **Site:** [ryanjhermes.github.io/minneapolismugshots](https://ryanjhermes.github.io/minneapolismugshots/)
- **CSV of the latest scrape:** [jail_roster_data.csv](https://ryanjhermes.github.io/minneapolismugshots/jail_roster_data.csv)
- **Booking photos for upcoming posts:** [mugshots/](https://ryanjhermes.github.io/minneapolismugshots/mugshots/)

## Schedule (Central time)

| When | What |
|---|---|
| 11 PM daily | Scrape the day's bookings and queue up to 10 for posting |
| 7, 9, 11 AM, 12, 1, 5, 7, 8 PM | One post per slot, as a short Reel with the booking photo and charges |
| Hourly | Check Bring Me The News for new stories with a booking photo |
| 6 PM daily | One local crime news story, if a new one stands out |

## How posts are chosen

Bookings with a listed charge come first. Among those, felonies and gross misdemeanors rank higher, as do booking
photos an image model rates as visually distinctive. Bail amount breaks ties.

## Removal requests

Send the account a DM asking for a post to be taken down, with the name on the post or a link to it. Once a
post is removed, that person is left out of all future posts and published data.

## Legal

Booking information is public data under the Minnesota Government Data Practices Act (Minn. Stat. § 13.82).
**A booking is not a conviction.** Charges are allegations, and everyone is presumed innocent until proven
guilty in a court of law.

## Development

Python on GitHub Actions: Selenium for the scrape, CLIP for image ranking, ffmpeg for Reels, and the Meta Graph
API for posting. Setup, commands and architecture are in [CLAUDE.md](CLAUDE.md).

```bash
pip install -r requirements.txt
python -m bot --help
```
