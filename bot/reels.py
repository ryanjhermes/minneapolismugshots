"""Build 9:16 Instagram Reels from mugshots with ffmpeg (free, runs on the Actions runner)."""
import subprocess
import tempfile
import textwrap

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


def make_clip(out_path, seconds, image=None, title="", body="", header=""):
    """One clip: optional slowly zooming mugshot, header on top, title + wrapped body below."""
    frames = seconds * FPS
    with tempfile.TemporaryDirectory() as tmp:
        texts = []
        if header:
            texts.append(_drawtext(_text(f"{tmp}/h.txt", header), 64, 120, "yellow"))
        if title:
            texts.append(_drawtext(_text(f"{tmp}/t.txt", title), 52, PHOTO_Y + PHOTO_H + 40))
        if body:
            texts.append(_drawtext(_text(f"{tmp}/b.txt", body), 40, PHOTO_Y + PHOTO_H + 125, "#ff5555"))

        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        if image:
            cmd += ["-i", image]
            video = (f"[0:v]scale={PHOTO_W}:{PHOTO_H}:force_original_aspect_ratio=decrease,"
                     f"pad={PHOTO_W}:{PHOTO_H}:(ow-iw)/2:(oh-ih)/2,"
                     f"zoompan=z='min(zoom+0.0006,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                     f":d={frames}:s={PHOTO_W}x{PHOTO_H}:fps={FPS},"
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
    """Wrap each charge on its own lines, capped at max_lines."""
    lines = []
    for c in (charges or "").split(separator):
        lines += textwrap.wrap(c.strip(), width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:width - 3] + "..."
    return "\n".join(lines)

