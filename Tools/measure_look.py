"""Tonal facts of rendered frames: python measure_look.py <png> ...  (display values 0..1: luma percentiles, skin luma, saturation)"""
import sys
import numpy as np
from PIL import Image

def facts(path):
    im = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    mx, mn = im.max(-1), im.min(-1)
    sat = np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0)
    # skin: warm, moderately saturated, not dark
    skin = (r > g) & (g > b) & (r - b > 0.08) & (r - b < 0.55) & (sat > 0.12) & (sat < 0.6) & (luma > 0.18)
    p = np.percentile(luma, [1, 5, 25, 50, 75, 95, 99])
    s = luma[skin]
    sk = np.percentile(s, [10, 50, 90]) if s.size > 500 else [float("nan")] * 3
    return p, sk, skin.mean(), sat.mean(), (luma > 0.98).mean(), (luma < 0.02).mean()

for path in sys.argv[1:]:
    p, sk, share, sat, clip, crush = facts(path)
    print("%-52s luma p1 %.2f p5 %.2f p25 %.2f p50 %.2f p75 %.2f p95 %.2f p99 %.2f | skin p10 %.2f p50 %.2f p90 %.2f (%2.0f%% of px) | sat %.2f | >0.98: %.1f%% <0.02: %.1f%%" % (
        "/".join(path.replace("\\", "/").split("/")[-2:]), *p, *sk, share * 100, sat, clip * 100, crush * 100))
