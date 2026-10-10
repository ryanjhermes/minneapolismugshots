"""Publishing to Instagram through the Meta Graph API (used by posting.py and news.py).

Instagram fetches media from a public URL, it can't take an upload. Publishing is two calls:
create a media container, wait for Instagram to finish processing it, then publish it.
"""
import os
import time

import requests

from . import config


def credentials():
    return {
        'access_token': os.getenv('ACCESS_TOKEN', ''),
        'app_id': os.getenv('APP_ID', ''),
        'business_id': os.getenv('BUSINESS_ID', ''),
    }


def post(image_url, caption, creds, test_mode=False, video_url=None):
    """Post an image, or a Reel when video_url is given. Returns True once published."""
    try:
        access_token, business_id = creds['access_token'], creds['business_id']
        if not access_token or not business_id:
            print("❌ Missing Meta API credentials")
            return False

        if test_mode:
            print("🧪 TEST MODE - Would post to Instagram:")
            print(f"   📸 {'Reel: ' + video_url if video_url else 'Image: ' + image_url}")
            print(f"   📝 Caption: {caption[:100]}...")
            return True

        # Step 1: create the media container
        print(f"📸 Creating Instagram {'Reel' if video_url else 'image post'} for: {video_url or image_url}")
        params = {'caption': caption, 'access_token': access_token}
        if video_url:
            params.update({'media_type': 'REELS', 'video_url': video_url, 'share_to_feed': 'true'})
        else:
            params['image_url'] = image_url
        r = requests.post(f"{config.GRAPH_API}/{business_id}/media", data=params)
        if r.status_code != 200:
            print(f"❌ Failed to create media: {r.status_code}\nResponse: {r.text}")
            return False
        media_id = r.json().get('id')
        if not media_id:
            print(f"❌ No media ID returned: {r.json()}")
            return False
        print(f"✅ Media created with ID: {media_id}")

        # Instagram processes media asynchronously; publishing before it finishes fails with
        # "Media ID is not available". Wait for FINISHED: up to 5 minutes for video, 1 for images
        for _ in range(60 if video_url else 12):
            status = requests.get(f"{config.GRAPH_API}/{media_id}",
                                  params={'fields': 'status_code', 'access_token': access_token}
                                  ).json().get('status_code')
            if status == 'FINISHED':
                break
            if status in ('ERROR', 'EXPIRED'):
                print(f"❌ Media processing failed: {status}")
                return False
            print(f"⏳ Media status: {status}, waiting...")
            time.sleep(5)

        # Step 2: publish it
        print("📤 Publishing media to Instagram...")
        r = requests.post(f"{config.GRAPH_API}/{business_id}/media_publish",
                          data={'creation_id': media_id, 'access_token': access_token})
        if r.status_code != 200:
            print(f"❌ Failed to publish media: {r.status_code}\nResponse: {r.text}")
            return False
        post_id = r.json().get('id')
        if not post_id:
            print(f"❌ No post ID returned: {r.json()}")
            return False
        print(f"🎉 Successfully posted to Instagram! Post ID: {post_id}")
        return True

    except Exception as e:
        print(f"❌ Error posting to Instagram: {e}")
        return False
