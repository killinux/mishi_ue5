"""Frames of a film where something dark and featureless stands in front of the lens: a run of columns (>= 12 % of the width)
that are dark from top to bottom.  Prints the frame ranges and the shot each falls in."""
import json
import subprocess
import sys

import numpy as np

film, timeline = sys.argv[1], sys.argv[2]
W, H = 160, 90
raw = subprocess.run([r"D:\Program Files\ffmpeg\bin\ffmpeg.exe", "-loglevel", "error", "-i", film, "-vf", "scale=%d:%d" % (W, H), "-pix_fmt", "gray",
                      "-f", "rawvideo", "-"], capture_output=True).stdout
frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, H, W).astype(np.float32) / 255.0
shots = json.load(open(timeline, encoding="utf-8"))["shots"]


def shot_of(f):
    name = "?"
    for s in shots:
        if s["frame"] <= f:
            name = s["name"]
    return name


bad = []
for i, fr in enumerate(frames):
    dark = (fr < 0.09).mean(axis=0) > 0.92          # a column that is dark nearly all the way down
    run = best = 0
    for d in dark:
        run = run + 1 if d else 0
        best = max(best, run)
    if best >= 0.12 * W:
        bad.append((i, best / W))
print("%d frames, %d flagged" % (len(frames), len(bad)))
start = None
prev = None
for i, share in bad + [(None, 0)]:
    if start is None:
        start, prev, top = i, i, share
    elif i is not None and i == prev + 1:
        prev, top = i, max(top, share)
    else:
        print("  frames %d-%d (%.2f s, %d frames) widest %.0f %% of the picture, shot %s" % (start, prev, start / 30.0, prev - start + 1, top * 100, shot_of(start)))
        start, prev, top = i, i, share
