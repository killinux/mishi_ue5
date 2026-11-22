"""A skin relief cut from real skin normal maps (system Python with numpy + Pillow):

    python Tools/make_skin_tile.py --body <normal.png> --body-box X,Y,N --body-layout ag --body-mm 0.2
                                   --face <normal.png> --face-box X,Y,N --face-layout rg --face-mm 0.087 --face-repeat 2

    -> Import/_local/skin_detail.png + skin_detail.json     (Import/ is not in the repository: such maps are somebody's work)

Tools/textures/skin_detail.png is drawn by make_skin_detail.py - a net of cells and pits, tidy as a honeycomb.  A skin pack
made for another game (painted or scanned for ITS body's UV layout, so it cannot be laid on these bodies as it is) still holds
what that drawing lacks: the way real furrows run and pores sit.  This cuts a square out of an even stretch of such a map -
a back, a cheek - keeps its fine part only (the body's shape is in the low frequencies), closes it into a tile that repeats
without a seam, and writes the two tiles into the layers M_Mishi_Skin weighs apart:

    R, G   the body's relief (normal x, y; 0.5 = flat; y DOWN the image as Unreal has it - Unity's green is flipped here)
    B, A   the face's

The .json beside it says what one repeat of the texture covers on each zone (tile_cm - from the millimetres a pixel of the
source covers on its own body) and which layer a zone takes; import_slice.py uses the pair instead of the drawn relief when
it is there.

--*-layout: where a map keeps x and y - "ag" (Unity's DXT5nm: x in alpha, y in green) or "rg".
--*-box: left, top and size of the square in the source's pixels; a margin of an eighth more to its right and below is read
for the cross-fade that closes the tile.
"""
import argparse
import json
import os

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
HERE = os.path.dirname(os.path.abspath(__file__))


def low(v, cells):
    """v without its fine part: block means, drawn smooth again."""
    n = v.shape[0]
    im = Image.fromarray(v.astype(np.float32))
    return np.asarray(im.resize((cells, cells), Image.BOX).resize((n, n), Image.BICUBIC))


def close(v, n, m):
    """The n x n tile of a (n+m)^2 square: its first m rows and columns fade over from what lies beyond its end, keeping the
    relief's strength in the fade (weights on a quarter circle, not a line: two unrelated reliefs add like noise)."""
    t = (np.arange(m, dtype=np.float32) + 0.5) / m
    a, b = np.cos(t * np.pi / 2), np.sin(t * np.pi / 2)
    out = v[:, :n].copy()
    out[:, :m] = v[:, :m] * b + v[:, n:n + m] * a
    v2 = out
    out = v2[:n].copy()
    out[:m] = v2[:m] * b[:, None] + v2[n:n + m] * a[:, None]
    return out


def tile(path, box, layout, size, repeat):
    x0, y0, n = box
    m = n // 8
    im = Image.open(path)
    if x0 + n + m > im.width or y0 + n + m > im.height:
        raise SystemExit("%s: the box and its margin (%d px) leave the picture (%d x %d)" % (path, n + m, im.width, im.height))
    c = im.crop((x0, y0, x0 + n + m, y0 + n + m))
    cx, cy = ("A", "G") if layout == "ag" else ("R", "G")
    x = (np.asarray(c.getchannel(cx)).astype(np.float32) - 127.5) / 127.5
    y = -(np.asarray(c.getchannel(cy)).astype(np.float32) - 127.5) / 127.5          # Unity's green points up the image
    cells = max((n + m) // 48, 4)
    x, y = x - low(x, cells), y - low(y, cells)
    x, y = close(x, n, m), close(y, n, m)
    if repeat > 1:
        x, y = np.tile(x, (repeat, repeat)), np.tile(y, (repeat, repeat))
    if x.shape[0] != size:
        x = np.asarray(Image.fromarray(x).resize((size, size), Image.LANCZOS))
        y = np.asarray(Image.fromarray(y).resize((size, size), Image.LANCZOS))
    return x, y


def main():
    ap = argparse.ArgumentParser()
    for zone in ("body", "face"):
        ap.add_argument("--%s" % zone, required=True)
        ap.add_argument("--%s-box" % zone, required=True)
        ap.add_argument("--%s-layout" % zone, default="rg", choices=("ag", "rg"))
        ap.add_argument("--%s-mm" % zone, type=float, required=True, help="millimetres of skin a pixel of this map covers")
        ap.add_argument("--%s-repeat" % zone, type=int, default=1)
        ap.add_argument("--%s-gain" % zone, type=float, default=1.0)
    ap.add_argument("--size", type=int, default=2048)
    ap.add_argument("--scale", type=float, default=1.0, help="lay the relief this much larger than life")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "Import", "_local"))
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    layers, cover = {}, {}
    for zone in ("body", "face"):
        box = [int(v) for v in getattr(a, zone + "_box").split(",")]
        repeat = getattr(a, zone + "_repeat")
        x, y = tile(getattr(a, zone), box, getattr(a, zone + "_layout"), a.size, repeat)
        gain = getattr(a, zone + "_gain")
        layers[zone] = (x * gain, y * gain)
        cover[zone] = box[2] * repeat * getattr(a, zone + "_mm") / 10.0 * a.scale       # centimetres one repeat of the texture covers
        print("%s: %d px square x %d, %.1f cm a repeat, slope rms %.3f / %.3f, largest %.2f" % (
            zone, box[2], repeat, cover[zone], float((x * gain).std()), float((y * gain).std()), float(np.abs(np.stack([x, y]) * gain).max())))
    rgba = np.stack([layers["body"][0], layers["body"][1], layers["face"][0], layers["face"][1]], -1) * 0.5 + 0.5
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    Image.fromarray(np.clip(rgba * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(out, "skin_detail.png"))
    look = {"tile_cm": {"body": round(cover["body"], 2), "face": round(cover["face"], 2), "tooth": round(cover["body"], 2)},
            "lines": {"body": 1.0, "face": 0.0, "tooth": 0.0}, "pores": {"body": 0.0, "face": 1.0, "tooth": 0.0},
            "patches": 0.25, "note": a.note}
    with open(os.path.join(out, "skin_detail.json"), "w", encoding="utf-8") as f:
        json.dump(look, f, indent=1, ensure_ascii=False)
    # for the eye: both layers as normal maps, a quarter of the tile each at full size
    q = a.size // 4
    prev = []
    for zone in ("body", "face"):
        x, y = layers[zone]
        z = np.sqrt(np.clip(1.0 - x * x - y * y, 0.0, 1.0))
        prev.append(np.clip((np.stack([x, -y, z], -1)[:q * 2, :q * 2] * 0.5 + 0.5) * 255.0 + 0.5, 0, 255).astype(np.uint8))
    Image.fromarray(np.concatenate(prev, 1)).save(os.path.join(out, "skin_detail_preview.jpg"), quality=90)
    print(os.path.join(out, "skin_detail.png"), json.dumps(look["tile_cm"]))


if __name__ == "__main__":
    main()
