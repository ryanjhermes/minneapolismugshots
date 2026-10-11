"""Render 9:16 Instagram Reels from queued mugshots with ffmpeg (free, runs on the Actions runner).

Reels are written to reels/ and served only from GitHub Pages (never committed). Pages is replaced
wholesale on every deploy, so any workflow that redeploys Pages re-renders Reels for the whole queue.
FONT is the Ubuntu runner's path (apt fonts-dejavu-core); elsewhere ffmpeg substitutes a default font.
"""
import os
import subprocess
import tempfile
import textwrap

from . import config, posting_queue

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H, FPS = 1080, 1920, 30
# Keep text clear of Instagram's Reel UI (top bar, right-side buttons, bottom caption)
PHOTO_W, PHOTO_H, PHOTO_Y = 800, 1000, 240  # mugshots are 4:5


def _text(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


def _drawtext(textfile, size, y, color="white"):
    """y may be a number or an ffmpeg expression."""
    return (f"drawtext=fontfile={FONT}:textfile={textfile}:expansion=none:fontcolor={color}"
            f":fontsize={size}:line_spacing=14:x=(w-text_w)/2:y={y}")


LINE_H, CHARGE_GAP = 54, 34  # Charge text line height, and the space (with a divider) between charges


def make_clip(out_path, seconds, image=None, title="", body=(), header=""):
    """One clip: optional still mugshot, header on top, title, then each body block (a charge) on its own
    lines with a short yellow divider between blocks. body may also be a single string."""
    if isinstance(body, str):
        body = [body] if body else []
    with tempfile.TemporaryDirectory() as tmp:
        texts = []
        if header:
            texts.append(_drawtext(_text(f"{tmp}/h.txt", header), 64, 120, "yellow"))
        if title:
            texts.append(_drawtext(_text(f"{tmp}/t.txt", title), 52, PHOTO_Y + PHOTO_H + 40))
        y = PHOTO_Y + PHOTO_H + 125
        for n, block in enumerate(body):
            if n:
                texts.append(f"drawbox=x=(iw-120)/2:y={y - CHARGE_GAP // 2 - 2}:w=120:h=4:color=yellow:t=fill")
            texts.append(_drawtext(_text(f"{tmp}/b{n}.txt", block), 40, y, "#ff5555"))
            y += block.count("\n") * LINE_H + LINE_H + CHARGE_GAP

        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        if image:
            cmd += ["-loop", "1", "-t", str(seconds), "-i", image]
            video = (f"[0:v]scale={PHOTO_W}:{PHOTO_H}:force_original_aspect_ratio=decrease,"
                     f"pad={PHOTO_W}:{PHOTO_H}:(ow-iw)/2:(oh-ih)/2,"
                     f"pad={W}:{H}:(ow-iw)/2:{PHOTO_Y}:black")
        else:
            cmd += ["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={seconds}"]
            video = "[0:v]null"
        video = ",".join([video] + texts + ["format=yuv420p[v]"])
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-filter_complex", video, "-map", "[v]", "-map", "1:a",
                "-t", str(seconds), "-r", str(FPS),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", out_path]
        subprocess.run(cmd, check=True)
    return out_path


def charge_lines(charges, separator, width=32, max_lines=5):
    """One wrapped block per charge (for make_clip's dividers), max_lines in total across blocks."""
    blocks, used = [], 0
    for c in (charges or "").split(separator):
        lines = textwrap.wrap(c.strip(), width)
        if not lines:
            continue
        if used + len(lines) > max_lines:
            lines = lines[:max_lines - used]
            if not lines:
                blocks[-1] = blocks[-1][:-3].rstrip() + "..."
                break
            lines[-1] = lines[-1][:width - 3] + "..."
        blocks.append("\n".join(lines))
        used += len(lines)
        if used >= max_lines:
            break
    return blocks


def build_queue_reels():
    """Render a Reel for each unposted queued entry and record it as Reel_File. Any failure leaves
    that entry without a Reel, so posting falls back to the still image."""
    q = posting_queue.load()
    os.makedirs(config.REELS_DIR, exist_ok=True)

    for entry in q['inmates']:
        d = entry['data']
        d.pop('Reel_File', None)
        if entry.get('posted') or not os.path.exists(d.get('Mugshot_File', '')):
            continue
        out = os.path.join(config.REELS_DIR, os.path.basename(d['Mugshot_File']).rsplit('.', 1)[0] + '.mp4')
        try:
            make_clip(out, config.REEL_SECONDS, d['Mugshot_File'], d.get('Full Name', ''),
                      charge_lines(d.get('Charge 1', ''), config.CHARGE_SEPARATOR), config.REEL_HEADER)
            d['Reel_File'] = out
            print(f"🎬 Reel: {out}")
        except Exception as e:
            print(f"⚠️  Reel failed for {d.get('Full Name')}: {e}")

    posting_queue.save(q)
