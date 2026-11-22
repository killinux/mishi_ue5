"""How restless and how sharp a held picture is (system Python with Pillow + numpy):

    python Tools/still_noise.py <folder of a shots run> [--map]

A shot with "hold" and "series": N saves N frames in a row of ONE held pose (<name>_00.png ...): nothing in the scene moves, so
whatever differs between them is the renderer's own doing - Lumen's noise, the upscaler's jitter, flicker on bright edges.
Tools/shots_noise.json takes three such views with each of TSR, DLAA and DLAA + ray reconstruction.

  unrest   the frames' deviation from their mean, a pixel's average (in 8-bit steps of the picture's brightness)
  worst    the same in the most restless 1 % of the picture
  detail   how much fine structure the MEAN picture has (its Laplacian's spread): what is there in every frame, without the noise

--map also writes <name>_unrest.png (the deviation x 16) beside the frames.
"""
import os
import re
import sys

import numpy as np
from PIL import Image


def luma(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    folder = args[0]
    series = {}
    for f in sorted(os.listdir(folder)):
        m = re.match(r"(.+)_(\d\d)\.png$", f)
        if m:
            series.setdefault(m.group(1), []).append(os.path.join(folder, f))
    if not series:
        print("no <name>_00.png ... series in", folder)
        return 1
    print("%-28s %6s %8s %8s %8s" % ("series", "frames", "unrest", "worst", "detail"))
    for name, files in series.items():
        stack = np.stack([luma(f) for f in files])
        mean = stack.mean(0)
        dev = stack.std(0)
        lap = -4 * mean[1:-1, 1:-1] + mean[:-2, 1:-1] + mean[2:, 1:-1] + mean[1:-1, :-2] + mean[1:-1, 2:]
        top = np.sort(dev.ravel())[-max(dev.size // 100, 1):]
        print("%-28s %6d %8.3f %8.2f %8.1f" % (name, len(files), dev.mean(), top.mean(), lap.std()))
        if "--map" in sys.argv:
            Image.fromarray(np.clip(dev * 16, 0, 255).astype(np.uint8)).save(os.path.join(folder, name + "_unrest.png"))
    return 0


sys.exit(main())
