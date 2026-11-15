"""Does anything flicker in the film's quiet shots?  Mean absolute difference between consecutive frames (320x180 gray), per shot:
a smooth series = smooth motion; a saw-tooth = something jumps every other frame."""
import json
import subprocess
import sys

import numpy as np

film, timeline = sys.argv[1], sys.argv[2]
names = sys.argv[3:]
W, H = 320, 180
raw = subprocess.run([r"D:\Program Files\ffmpeg\bin\ffmpeg.exe", "-loglevel", "error", "-i", film, "-vf", "scale=%d:%d" % (W, H), "-pix_fmt", "gray",
                      "-f", "rawvideo", "-"], capture_output=True).stdout
frames = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)
t = json.load(open(timeline, encoding="utf-8"))
shots = t["shots"]
for k, s in enumerate(shots):
    if names and s["name"] not in names:
        continue
    a, b = s["frame"], (shots[k + 1]["frame"] if k + 1 < len(shots) else len(frames))
    b = min(b, len(frames))
    d = np.abs(frames[a + 1:b] - frames[a:b - 1]).mean(axis=(1, 2))
    if len(d) < 4:
        continue
    d = d[1:]                                # (the cut itself)
    # the second difference: how much the frame-to-frame change itself changes
    saw = np.abs(d[2:] - 2 * d[1:-1] + d[:-2]).mean() / max(d.mean(), 1e-6)
    # the largest share of the picture that changes strongly between two frames
    big = (np.abs(frames[a + 1:b] - frames[a:b - 1]) > 40).mean(axis=(1, 2)).max()
    print("%-11s %3d frames  diff mean %.2f max %.2f  saw %.2f  strong-change max %.3f" % (s["name"], b - a, d.mean(), d.max(), saw, big))
