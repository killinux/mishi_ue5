"""Beads of sweat, made here (system Python with numpy + Pillow):

    python Tools/make_sweat.py            -> Tools/textures/sweat.png (+ sweat_preview.jpg)

One tile of little domes, 1024 px, seamless when tiled - M_Mishi_Skin lays it over the skin and lets the beads come up one by
one as the scene's wetness (MPC_Mishi "Wet") rises:

    R, G   a bead's normal x, y (0.5 = flat; x right, y DOWN the image as Unreal's normal maps have it) - a cap of a sphere,
           so the slope grows evenly from its top to its rim
    B      where a bead is (1 inside, a soft rim, 0 on bare skin)
    A      the wetness at which this bead appears (one value over the whole bead and a little beyond its rim; 1 on bare skin):
           the first ones come at WET_FIRST, the large ones late - a drop needs time to gather

The tile covers SKIN_LOOK "sweat_tile_cm" of skin (Tools/mishi_materials.py), whatever the material's UV scale.
"""
import os

import numpy as np
from PIL import Image

SIZE = 1024
SITES = 34            # bead sites across the tile (a jittered grid: no two beads on one spot)
FILLED = 0.8          # of the sites that carry a bead
WET_FIRST = 0.12      # no bead below this wetness
RIM = 0.82            # the slope at a bead's rim (the sine of the angle water stands at on skin: about 55 degrees)
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    rng = np.random.default_rng(20261123)
    n = SIZE
    cell = n / SITES                                                         # pixels
    centre = (rng.random((SITES, SITES, 2)) * 0.7 + 0.15)                    # in its square
    there = rng.random((SITES, SITES)) < FILLED
    # sizes: most are fine beads, a few are drops (a radius in site spacings; a spacing is tile / SITES)
    u = rng.random((SITES, SITES))
    radius = np.where(u < 0.7, 0.10 + 0.10 * rng.random((SITES, SITES)), np.where(u < 0.94, 0.22 + 0.12 * rng.random((SITES, SITES)),
                                                                                0.36 + 0.12 * rng.random((SITES, SITES))))
    # when it comes: fine beads from the first wetness on, drops only on a skin that is already wet
    start = WET_FIRST + (1.0 - WET_FIRST) * np.clip(rng.random((SITES, SITES)) * 0.75 + (radius - 0.10) / 0.38 * 0.3, 0.0, 1.0)
    y, x = np.mgrid[0:n, 0:n].astype(np.float32) / cell
    cx, cy = np.floor(x).astype(np.int32), np.floor(y).astype(np.int32)
    nx = np.zeros((n, n), np.float32)
    ny = np.zeros((n, n), np.float32)
    body = np.zeros((n, n), np.float32)
    when = np.ones((n, n), np.float32)
    near = np.full((n, n), 9.0, np.float32)                                  # the nearest bead's rim distance, in radii
    soft = 1.5 / cell                                                        # the rim's width: a pixel and a half
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            gx, gy = cx + dx, cy + dy
            ix, iy = gx % SITES, gy % SITES
            c = centre[iy, ix]
            ox, oy = x - (gx + c[..., 0]), y - (gy + c[..., 1])
            r = radius[iy, ix]
            d = np.hypot(ox, oy)
            inside = np.clip((r - d) / soft, 0.0, 1.0) * there[iy, ix]
            take = inside > body
            # a cap of a sphere: the normal leans outward in step with the distance from the top
            nx = np.where(take, ox / r * RIM, nx)
            ny = np.where(take, oy / r * RIM, ny)
            body = np.where(take, inside, body)
            rel = np.where(there[iy, ix], d / r, 9.0)
            closer = rel < near
            near = np.where(closer, rel, near)
            when = np.where(closer & (rel < 1.6), start[iy, ix], when)
    nx *= body
    ny *= body
    rgba = np.stack([nx * 0.5 + 0.5, ny * 0.5 + 0.5, body, when], -1)
    out = os.path.join(HERE, "textures")
    os.makedirs(out, exist_ok=True)
    Image.fromarray(np.clip(rgba * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(out, "sweat.png"))
    # for the eye: the beads there are at three wetnesses, lit from the upper left
    tiles = []
    for wet in (0.3, 0.6, 1.0):
        on = body * np.clip((wet * 1.2 - when) * 6.0, 0.0, 1.0)
        lit = 0.55 + 0.9 * (-(nx * on) * 0.6 - (ny * on) * 0.6) - 0.12 * on
        tiles.append(np.clip(lit, 0.0, 1.0))
    prev = np.concatenate(tiles, 1)
    Image.fromarray((prev * 255.0 + 0.5).astype(np.uint8)).resize((1536, 512), Image.LANCZOS).save(os.path.join(out, "sweat_preview.jpg"), quality=90)
    count = int(there.sum())
    print("sweat.png: %d px, %d beads (radius %.2f - %.2f of a %d px spacing), appearing from wetness %.2f to %.2f" % (
        SIZE, count, float(radius[there].min()), float(radius[there].max()), int(cell), float(start[there].min()), float(start[there].max())))


if __name__ == "__main__":
    main()
