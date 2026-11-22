"""The skin's fine relief, made here (system Python with numpy + Pillow):

    python Tools/make_skin_detail.py            -> Tools/textures/skin_detail.png (+ skin_detail_preview.jpg)

The game ships one 256 px detail normal map (pc_common_detailskin: a net of cells) for the nude body and the face - seen in a
grazing highlight only - and none for an armoured body's skin or for his body.  This draws the relief itself, 1024 px, seamless
when tiled, in two layers a material can weigh apart:

    R, G   the lines: skin is a net of fine furrows round little raised fields - a net of cells with a finer net inside it,
           each furrow a valley
    B, A   the pores: small pits, one for every few fields

Each pair is a tangent-space normal's x, y (0.5 = flat; x right, y DOWN the image as Unreal's normal maps have it - the import
keeps the green channel).  M_Mishi_Skin tiles it by the centimetres a tile covers (SKIN_LOOK "tile_cm": 6 cm, the fields 1.25 mm
- larger than skin's own half millimetre, which no lens half a metre away resolves) and what a unit of the material's UV covers
on the body (Tools/mishi_fbx.py), so the relief is the same size on a face and on a thigh.
"""
import os

import numpy as np
from PIL import Image

SIZE = 1024
CELLS = 48            # fields across the tile
PORES = 44            # pore sites across the tile (not every site gets one)
HERE = os.path.dirname(os.path.abspath(__file__))


def voronoi(n, cells, rng, jitter=0.85):
    """F1, F2 (distance to the nearest and the second nearest site, in cells) of a jittered grid that wraps round."""
    sites = rng.random((cells, cells, 2)) * jitter + (1 - jitter) * 0.5
    y, x = np.mgrid[0:n, 0:n].astype(np.float32) * (cells / n)
    cx, cy = np.floor(x).astype(np.int32), np.floor(y).astype(np.int32)
    f1 = np.full((n, n), 9.0, np.float32)
    f2 = np.full((n, n), 9.0, np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            gx, gy = cx + dx, cy + dy
            s = sites[gy % cells, gx % cells]
            d = np.hypot(gx + s[..., 0] - x, gy + s[..., 1] - y).astype(np.float32)
            closer = d < f1
            f2 = np.where(closer, f1, np.minimum(f2, d))
            f1 = np.where(closer, d, f1)
    return f1, f2


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def blur(h, times=1):
    for _ in range(times):
        h = (h + np.roll(h, 1, 0) + np.roll(h, -1, 0) + np.roll(h, 1, 1) + np.roll(h, -1, 1)) / 5.0
    return h


def normal_xy(h, strength):
    """The slope of a height field as a tangent-space normal's x, y (wrapping; y down the image)."""
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * strength
    inv = 1.0 / np.sqrt(dx * dx + dy * dy + 1.0)
    return -dx * inv, -dy * inv


def lines(rng):
    f1, f2 = voronoi(SIZE, CELLS, rng)
    h = smoothstep(0.0, 0.16, f2 - f1) * 0.75 + (1.0 - np.clip(f1, 0, 1)) * 0.25        # raised fields, a furrow between them
    g1, g2 = voronoi(SIZE, int(CELLS * 2.3), rng)
    h += (smoothstep(0.0, 0.2, g2 - g1) - 1.0) * 0.28                                    # the finer net inside the fields
    return blur(h, 2)


def pores(rng):
    n = SIZE
    sites = rng.random((PORES, PORES, 2))                                                 # anywhere in its square: no grid to be seen
    there = rng.random((PORES, PORES)) < 0.5
    radius = (0.07 + rng.random((PORES, PORES)) * 0.06).astype(np.float32)               # in site spacings
    depth = (0.45 + rng.random((PORES, PORES)) * 0.55).astype(np.float32)
    y, x = np.mgrid[0:n, 0:n].astype(np.float32) * (PORES / n)
    cx, cy = np.floor(x).astype(np.int32), np.floor(y).astype(np.int32)
    h = np.zeros((n, n), np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            gx, gy = cx + dx, cy + dy
            ix, iy = gx % PORES, gy % PORES
            s = sites[iy, ix]
            d = np.hypot(gx + s[..., 0] - x, gy + s[..., 1] - y)
            pit = np.exp(-(d / radius[iy, ix]) ** 2) * depth[iy, ix] * there[iy, ix]
            h = np.minimum(h, -pit)
    return blur(h, 1)


def main():
    rng = np.random.default_rng(20261122)
    lx, ly = normal_xy(lines(rng), 9.0)
    px, py = normal_xy(pores(rng), 9.0)
    rgba = np.stack([lx, ly, px, py], -1) * 0.5 + 0.5
    out = os.path.join(HERE, "textures")
    os.makedirs(out, exist_ok=True)
    Image.fromarray(np.clip(rgba * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(out, "skin_detail.png"))
    # what it looks like as one normal map, tiled 2 x 2 (for the eye, not for the engine)
    nx, ny = lx + px, ly + py
    nz = np.sqrt(np.clip(1.0 - nx * nx - ny * ny, 0.0, 1.0))
    prev = np.clip((np.stack([nx, -ny, nz], -1) * 0.5 + 0.5) * 255.0 + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(np.tile(prev, (2, 2, 1))).resize((1024, 1024), Image.LANCZOS).save(os.path.join(out, "skin_detail_preview.jpg"), quality=90)
    print("skin_detail.png: %d px, %d fields and %d pore sites across; slopes up to %.2f (lines) / %.2f (pores)" % (
        SIZE, CELLS, PORES, float(np.abs(np.stack([lx, ly])).max()), float(np.abs(np.stack([px, py])).max())))


if __name__ == "__main__":
    main()
