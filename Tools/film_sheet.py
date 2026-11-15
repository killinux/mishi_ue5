"""Contact sheet of chosen shots of a recorded film (the frames are gone after encoding: read them from the mp4).
film_sheet.py <film.mp4> <timeline.json> <out.jpg> [--per-shot N] [--cols N] [--width W] [prefix ...]"""
import json
import subprocess
import sys

from PIL import Image, ImageDraw

args = sys.argv[1:]
film, timeline, out = args[:3]
per, cols, width, prefixes = 3, 6, 400, []
i = 3
while i < len(args):
    if args[i] == "--per-shot":
        per = int(args[i + 1]); i += 2
    elif args[i] == "--cols":
        cols = int(args[i + 1]); i += 2
    elif args[i] == "--width":
        width = int(args[i + 1]); i += 2
    else:
        prefixes.append(args[i]); i += 1
t = json.load(open(timeline, encoding="utf-8"))
shots, total = t["shots"], t["frames"]
picks = []
for k, s in enumerate(shots):
    if prefixes and not any(s["name"].startswith(p) for p in prefixes):
        continue
    a, b = s["frame"], (shots[k + 1]["frame"] if k + 1 < len(shots) else total)
    for j in range(per):
        f = a + int((b - a) * (j + 0.5) / per)
        picks.append((f, "%s  f%d" % (s["name"], f)))
h = width * 9 // 16
rows = (len(picks) + cols - 1) // cols
sheet = Image.new("RGB", (cols * width, rows * h), (20, 20, 24))
for n, (f, label) in enumerate(picks):
    raw = subprocess.run([r"D:\Program Files\ffmpeg\bin\ffmpeg.exe", "-loglevel", "error", "-ss", "%.4f" % (f / 30.0), "-i", film, "-frames:v", "1",
                          "-vf", "scale=%d:%d" % (width, h), "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True).stdout
    if len(raw) != width * h * 3:
        continue
    im = Image.frombytes("RGB", (width, h), raw)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 6 * len(label), 13], fill=(0, 0, 0))
    d.text((3, 1), label, fill=(255, 255, 0))
    sheet.paste(im, ((n % cols) * width, (n // cols) * h))
sheet.save(out, quality=88)
print(out, sheet.size, len(picks), "frames")
