"""Command line for the whole pipeline. Run from the repo root:

    python -m bot <command> [options]
    python -m bot --help

Each command imports only the modules it needs, because each workflow installs only its own
dependencies (posting has no Selenium or torch, the DM check has no Pillow).
"""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(prog="python -m bot", description="Minneapolis Mugshots pipeline")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    def command(name, help):
        return sub.add_parser(name, help=help, description=help)

    c = command("scrape", "Scrape today's jail roster, save the CSV + mugshots, rebuild the posting queue")
    c.add_argument("--test", action="store_true", help="Open 25 bookings instead of 100")

    command("preflight", "Decide whether this posting run posts (prints and sets mode= / reason=)")
    c = command("post-next", "Post the next queued mugshot (Reel, falling back to the image)")
    c.add_argument("--dry-run", action="store_true", help="Log the would-be post; leave the queue alone")
    command("make-reels", "Render Reels for the unposted queue into reels/ (needs ffmpeg)")

    command("check-queue", "Print posting queue status")
    command("cleanup-posted", "Delete mugshot files of posted entries")
    command("purge-unqueued", "Delete every mugshot not needed by an upcoming post")
    command("purge-removed", "Strip people on the removal list from the CSV, queue and mugshots/")

    c = command("bmtn", "Queue Bring Me The News crime stories whose lead image is a mugshot")
    g = c.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="Only count new stories (no models)")
    g.add_argument("--dry-run", action="store_true", help="Show what would be queued, change nothing")

    c = command("news", "Daily news post: the most outlandish new crime story")
    g = c.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="Show scores and the would-be post, change nothing")
    g.add_argument("--force", action="store_true", help="Post now, skipping the 6 PM and once-a-day checks")

    c = command("dms", "Handle removal requests in Instagram DMs")
    g = c.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="Log what would happen; send, delete and save nothing")
    g.add_argument("--check-token", action="store_true", help="List scopes the Meta token is missing")

    args = parser.parse_args()

    if args.command == "scrape":
        from . import config, scraper
        scraper.run(config.TEST_INMATE_LIMIT if args.test else config.DEFAULT_INMATE_LIMIT)
    elif args.command == "preflight":
        from . import posting
        from .common import set_github_output
        mode, reason = posting.preflight()
        print(f"mode={mode or 'none'} reason={reason}")
        set_github_output(mode=mode, reason=reason)
    elif args.command == "post-next":
        from . import posting
        # A failed post turns the workflow run red
        if not posting.post_next(test_mode=args.dry_run):
            sys.exit(1)
    elif args.command == "make-reels":
        from . import reels
        reels.build_queue_reels()
    elif args.command == "check-queue":
        from . import posting_queue
        posting_queue.check()
    elif args.command == "cleanup-posted":
        from . import posting_queue
        posting_queue.cleanup_posted()
    elif args.command == "purge-unqueued":
        from . import posting_queue
        posting_queue.purge_unqueued()
    elif args.command == "purge-removed":
        from . import removals
        print(f"✅ Purged {removals.purge()} removed record(s)")
    elif args.command == "bmtn":
        from . import bmtn
        bmtn.run(dry_run=args.dry_run, check=args.check)
    elif args.command == "news":
        from . import news
        news.run(dry_run=args.dry_run, force=args.force)
    elif args.command == "dms":
        from . import dms
        dms.run(dry_run=args.dry_run, token_check=args.check_token)


if __name__ == "__main__":
    main()
