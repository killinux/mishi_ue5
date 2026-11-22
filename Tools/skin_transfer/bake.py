"""python Tools/skin_transfer/bake.py <corr.npz> <material> [--own ALBEDO.png] [--pack DIR] [--out DIR] [--wet-size N]

A skin pack's maps, painted for another body, drawn into a target material's own UV layout: every pixel of the target knows
which point of the pack's body lies there (correspond.py), so each map is read there.  System Python (numpy, Pillow).

What is taken, and how (the pack here: Hanmen's NEXT-GEN for HoneySelect 2 - PACK below names its files):

  <material>_hm_n.png    the fine relief as a tangent-space normal map in Unreal's convention.  The pack's normal map minus
                         its smooth part (a body's own shapes stay the target's); its x, y are turned from the pack's UV
                         directions into the target's - where the two layouts run differently over the skin, a furrow must
                         still run where it ran (the turn is the rotation nearest to how the pack's UV changes along the
                         target's, a mirror where one layout is the other's mirror image).
  <material>_hm_c.png    RGB: the skin's fine colour as a factor round 1 (128 = 1): the pack's colour over its own blurred
                         self - pores, freckle-fine mottling, small veins; not its skin tone, not its lips.  A: its gloss
                         map's fine part the same way (the furrows and pores shine less).
  <material>_hm_w.png    R: sweat that runs (the pack's rivulets), G: sweat that stands (drops, wet patches), B: veins,
                         A: how thin the body is there (light goes through an ear, a finger).
  <material>_hm_wn.png   the rivulets and drops as a normal map (from the two masks as heights, in the target's layout).

A pixel whose point on the pack's body is far off (an ear's inside, a nail: correspond.py's "far") stays neutral.

--own: the target material's own colour map.  Where the target has painted a feature of its own - an areola, the navel,
the genitals: much redder or much darker than the skin round it - the pack's relief, colour, gloss and veins are left out
(with a soft rim): its skin there was made for another body's features, a few millimetres beside these.  On the pack's side
the same holds for the body's relief where the pack's own colour map shows a feature (its "keep").  Sweat stays.
"""
import argparse
import os
import time

import numpy as np
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None
HERE = os.path.dirname(os.path.abspath(__file__))

# part (1 the pack's body, 2 its head) -> its maps.  (The body's colour from the pack's "NoMoles" skin, cf_nextgen_body_02_t:
# the other one, _00_t, has moles - on the first bake a mole stood on her hip that the character does not have.)
PACK = {
    1: {"normal": ("cf_nextgen_body_base_n.png", "ag"), "diffuse": "cf_nextgen_body_02_t.png", "gloss": ("cf_nextgen_body_02_occ.png", "R"),
        "wet": "WetnessMap.png", "veins": ("SSA_Body.png", "A"), "thin": ("thickness_body_female.png", "R")},
    2: {"normal": ("cf_nextgen_head_00_00_n.png", "rg"), "diffuse": "cf_nextgen_head_00_00_t.png", "gloss": ("cf_nextgen_head_00_00_o.png", "R"),
        "wet": "WetnessFace.png", "veins": None, "thin": ("thickness_head_female.png", "R")},
}
FAR = 0.012          # metres between the two skins beyond which a pixel is left neutral
FINE = 64            # the smooth part of a map: its mean over squares of size / FINE... (a map of 8192 -> 128 px squares = 2.5 cm)


def low(v, cells):
    """v without its fine part (block means drawn smooth again); v: (h, w) float32."""
    h, w = v.shape
    im = Image.fromarray(v)
    return np.asarray(im.resize((cells, cells), Image.BOX).resize((w, h), Image.BICUBIC))


class Source:
    def __init__(self, folder, spec):
        t0 = time.time()
        name, layout = spec["normal"]
        im = Image.open(os.path.join(folder, name))
        cx, cy = ("A", "G") if layout == "ag" else ("R", "G")
        x = (np.asarray(im.getchannel(cx)).astype(np.float32) - 127.5) / 127.5
        y = (np.asarray(im.getchannel(cy)).astype(np.float32) - 127.5) / 127.5
        cells = max(x.shape[0] // 48, 8)                                     # (the relief's own scale: wrinkles stay, muscles go)
        self.nx, self.ny = x - low(x, cells), y - low(y, cells)
        del im, x, y
        d = np.asarray(Image.open(os.path.join(folder, spec["diffuse"])).convert("RGB")).astype(np.float32)
        cells = max(d.shape[0] // FINE, 8)
        ratio = np.empty(d.shape, np.float32)
        strong = np.zeros(d.shape[:2], np.float32)
        for k in range(3):
            smooth = np.maximum(low(d[..., k], cells), 1.0)
            ratio[..., k] = d[..., k] / smooth
            # where the pack's own picture changes fast in the middle scale - a lip's edge, a nostril, an areola - its colour
            # is a feature of ITS body, not skin texture: none of it there
            mid = np.maximum(low(d[..., k], cells * 4), 1.0)
            strong = np.maximum(strong, np.abs(mid / smooth - 1.0))
        keep = 1.0 - np.clip((strong - 0.02) / 0.03, 0.0, 1.0)
        keep = np.clip(low(keep.astype(np.float32), cells * 2), 0.0, 1.0)
        self.keep = np.clip(keep * 255.0, 0, 255).astype(np.uint8)
        # (a factor within 12 % of 1: a pore, a mottle; a mole or a freckle - a skin's own mark, not its texture - is cut down to that)
        self.spots = float((ratio.min(axis=2) < 0.8).mean())
        self.colour = np.clip((1.0 + (np.clip(ratio, 0.88, 1.12) - 1.0) * keep[..., None]) * 127.5, 0, 255).astype(np.uint8)
        del d, ratio, strong
        name, ch = spec["gloss"]
        g = np.asarray(Image.open(os.path.join(folder, name)).getchannel(ch)).astype(np.float32)
        smooth = np.maximum(low(g, max(g.shape[0] // FINE, 8)), 1.0)
        if keep.shape != g.shape:
            keep = np.asarray(Image.fromarray(keep).resize((g.shape[1], g.shape[0]), Image.BILINEAR))
        # (a nostril, an eye's rim are deep black in the gloss map: the same features, the same weight)
        self.gloss = np.clip((1.0 + (np.clip(g / smooth, 0.7, 1.3) - 1.0) * keep) * 127.5, 0, 255).astype(np.uint8)
        del g, smooth, keep
        w = Image.open(os.path.join(folder, spec["wet"]))
        self.run, self.drop = np.asarray(w.getchannel("R")), np.asarray(w.getchannel("B"))
        self.veins = np.asarray(Image.open(os.path.join(folder, spec["veins"][0])).getchannel(spec["veins"][1])) if spec.get("veins") else None
        self.thin = np.asarray(Image.open(os.path.join(folder, spec["thin"][0])).getchannel(spec["thin"][1])) if spec.get("thin") else None
        print("  source %s: relief %d px (rms %.3f / %.3f), colour %s %d px (%.3f %% of it darker than 0.8 of its surroundings: marks), wet %d px; %.0f s" % (
            spec["normal"][0], self.nx.shape[0], float(self.nx.std()), float(self.ny.std()), spec["diffuse"], self.colour.shape[0], 100.0 * self.spots,
            self.run.shape[0], time.time() - t0))


def sample(img, u, v):
    """img (h, w[, c]) read at UV (v up) with bilinear weights -> float32 (n[, c])."""
    h, w = img.shape[:2]
    x = np.clip(u * w - 0.5, 0.0, w - 1.001)
    y = np.clip((1.0 - v) * h - 0.5, 0.0, h - 1.001)
    x0, y0 = x.astype(np.int32), y.astype(np.int32)
    fx, fy = (x - x0).astype(np.float32), (y - y0).astype(np.float32)
    if img.ndim == 3:
        fx, fy = fx[:, None], fy[:, None]
    a, b = img[y0, x0].astype(np.float32), img[y0, x0 + 1].astype(np.float32)
    c, d = img[y0 + 1, x0].astype(np.float32), img[y0 + 1, x0 + 1].astype(np.float32)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def own_marks(path, part, n):
    """Where the target's own colour map paints a feature (0 plain skin .. 1 a feature), n x n, with a soft rim."""
    work = min(n, 2048)
    a = np.asarray(Image.open(path).convert("RGB").resize((work, work), Image.LANCZOS)).astype(np.float32)
    step = n // work
    skin = part[step // 2::step, step // 2::step] > 0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    red = (r - g) / np.maximum(r, 1.0)
    lum = (r + g + b) / 3.0
    red0, lum0 = float(np.median(red[skin])), float(np.median(lum[skin]))
    # (a knee's or a sole's blush is 0.05 - 0.09 redder than the skin's median, an areola 0.2: the mark begins at 0.12)
    mark = np.maximum(np.clip((red - red0 - 0.12) / 0.06, 0.0, 1.0), np.clip((lum0 - lum - 60.0) / 40.0, 0.0, 1.0))
    mark[~skin] = 0.0
    im = Image.fromarray((mark * 255).astype(np.uint8))
    px = max(int(round(work / 2048.0 * 9)) | 1, 3)                       # about 7 mm on a body's map
    im = im.filter(ImageFilter.MaxFilter(px)).filter(ImageFilter.GaussianBlur(px * 0.6))
    out = np.asarray(im.resize((n, n), Image.BILINEAR)).astype(np.float32) / 255.0
    print("  the target's own features (%s): %.2f %% of its skin (redness %.3f, brightness %.0f at the median)" % (
        os.path.basename(path), 100.0 * (mark[skin] > 0.5).mean(), red0, lum0))
    return np.clip(out * 1.5, 0.0, 1.0)


def turns(xs, ys, part):
    """For each pixel the 2 x 2 turn Q (rows q11 q12 / q21 q22) nearest to how the source's picture coordinates (xs right,
    ys down, in UV units) change along the target's picture (x right, y down)."""
    def along(a, axis):
        f = np.diff(a, axis=axis)
        same = (np.diff(part.astype(np.int16), axis=axis) == 0) & (np.abs(f) < 0.004)
        pad = [(0, 0), (0, 0)]
        pad[axis] = (0, 1)
        fwd, fok = np.pad(np.where(same, f, 0.0), pad), np.pad(same, pad)
        pad[axis] = (1, 0)
        bwd, bok = np.pad(np.where(same, f, 0.0), pad), np.pad(same, pad)
        n = fok.astype(np.float32) + bok
        return (fwd + bwd) / np.maximum(n, 1.0), n > 0
    a, oka = along(xs, 1)
    b, okb = along(xs, 0)
    c, okc = along(ys, 1)
    d, okd = along(ys, 0)
    ok = oka & okb & okc & okd
    det = a * d - b * c
    rot = np.arctan2(c - b, a + d)
    ref = np.arctan2(c + b, a - d)
    plus = det >= 0
    q11 = np.where(plus, np.cos(rot), np.cos(ref))
    q12 = np.where(plus, -np.sin(rot), np.sin(ref))
    q21 = np.where(plus, np.sin(rot), np.sin(ref))
    q22 = np.where(plus, np.cos(rot), -np.cos(ref))
    flat = ~ok | (np.abs(det) < 1e-16)
    q11[flat], q12[flat], q21[flat], q22[flat] = 1.0, 0.0, 0.0, 1.0
    return q11.astype(np.float32), q12.astype(np.float32), q21.astype(np.float32), q22.astype(np.float32), int((~plus & ok).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corr")
    ap.add_argument("material")
    ap.add_argument("--pack", default=os.path.join(HERE, "..", "..", "_work", "hs2", "pack"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "..", "Import", "_local", "skin"))
    ap.add_argument("--wet-size", type=int, default=4096)
    ap.add_argument("--own", help="the target material's own colour map: its painted features keep their own skin")
    a = ap.parse_args()
    t0 = time.time()
    corr = np.load(a.corr)
    part, uv, far = corr["part"], corr["uv"], corr["far"]
    n = part.shape[0]
    part = np.where(far > FAR, 0, part).astype(np.uint8)
    print("%s: %d px, %.1f %% skin (%.1f %% from the pack's head)" % (a.material, n, 100.0 * (part > 0).mean(), 100.0 * (part == 2).sum() / max((part > 0).sum(), 1)))
    sources = {k: Source(a.pack, spec) for k, spec in PACK.items() if (part == k).any()}
    os.makedirs(a.out, exist_ok=True)
    marks = own_marks(a.own, part, n) if a.own else None

    normal = np.zeros((n, n, 3), np.uint8)
    normal[...] = (128, 128, 255)
    colour = np.full((n, n, 4), 128, np.uint8)
    mirrored = 0
    STRIP = 512
    for r0 in range(0, n, STRIP):
        r1 = min(r0 + STRIP, n)
        h0, h1 = max(r0 - 1, 0), min(r1 + 1, n)
        p = part[h0:h1]
        xs = uv[h0:h1, :, 0].astype(np.float32)
        ys = 1.0 - uv[h0:h1, :, 1].astype(np.float32)
        q11, q12, q21, q22, m = turns(xs, ys, p)
        mirrored += m
        cut = slice(r0 - h0, r0 - h0 + (r1 - r0))
        p, q11, q12, q21, q22 = p[cut], q11[cut], q12[cut], q21[cut], q22[cut]
        u, v = uv[r0:r1, :, 0], uv[r0:r1, :, 1]
        for k, s in sources.items():
            m = p == k
            if not m.any():
                continue
            uu, vv = u[m].astype(np.float64), v[m].astype(np.float64)
            # the pack's relief there: x along its picture's right, y (OpenGL) up its picture -> along its picture's down: -y
            dx, dy = sample(s.nx, uu, vv), -sample(s.ny, uu, vv)
            # how much of the pack's skin is taken here: none on the target's own features, and (the body's relief) none where
            # the pack's body has a feature of its own
            weight = np.ones(len(uu), np.float32) if marks is None else 1.0 - marks[r0:r1][m]
            relief = weight * (sample(s.keep, uu, vv) / 255.0) if k == 1 else weight
            dx, dy = dx * relief, dy * relief
            tx = q11[m] * dx + q21[m] * dy
            ty = q12[m] * dx + q22[m] * dy
            tz = np.sqrt(np.clip(1.0 - tx * tx - ty * ty, 0.0, 1.0))
            out = normal[r0:r1]
            out[m] = np.clip(np.stack([tx, ty, tz], -1) * 127.5 + 127.5, 0, 255).astype(np.uint8)
            cc = colour[r0:r1]
            rgb = 127.5 + (sample(s.colour, uu, vv) - 127.5) * weight[:, None]
            g = 127.5 + (sample(s.gloss, uu, vv) - 127.5) * weight
            cc[m] = np.clip(np.concatenate([rgb, g[:, None]], 1) + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(normal).save(os.path.join(a.out, a.material + "_hm_n.png"), compress_level=3)
    Image.fromarray(colour).save(os.path.join(a.out, a.material + "_hm_c.png"), compress_level=3)
    fine = normal[part > 0].astype(np.float32) / 127.5 - 1.0
    print("  relief: slope rms %.3f / %.3f; %d pixels read through a mirror image; %.0f s" % (float(fine[:, 0].std()), float(fine[:, 1].std()), mirrored, time.time() - t0))
    del normal, colour

    # sweat, veins, thinness: at the wet size (the pack's rivulets are millimetres wide)
    w = min(a.wet_size, n)
    step = n // w
    part_w, uv_w = part[step // 2::step, step // 2::step], uv[step // 2::step, step // 2::step]
    wet = np.zeros((w, w, 4), np.uint8)
    for k, s in sources.items():
        m = part_w == k
        if not m.any():
            continue
        uu, vv = uv_w[m][:, 0].astype(np.float64), uv_w[m][:, 1].astype(np.float64)
        cols = [sample(s.run, uu, vv), sample(s.drop, uu, vv),
                sample(s.veins, uu, vv) if s.veins is not None else np.zeros(len(uu), np.float32),
                sample(s.thin, uu, vv) if s.thin is not None else np.zeros(len(uu), np.float32)]
        if marks is not None:
            cols[2] = cols[2] * (1.0 - marks[step // 2::step, step // 2::step][m])        # no vein across an areola
        wet[m] = np.clip(np.stack(cols, 1) + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(wet).save(os.path.join(a.out, a.material + "_hm_w.png"), compress_level=3)
    # the water as a height: a rivulet a round ridge, a drop a low dome - and its slope as a normal (x right, y down)
    run, drop = wet[..., 0].astype(np.float32) / 255.0, wet[..., 1].astype(np.float32) / 255.0
    height = np.maximum(np.sqrt(run) * 1.0, np.sqrt(drop) * 0.6)
    height = np.asarray(Image.fromarray(height).resize((w, w), Image.BILINEAR))
    for _ in range(2):
        height = (height + np.roll(height, 1, 0) + np.roll(height, -1, 0) + np.roll(height, 1, 1) + np.roll(height, -1, 1)) / 5.0
    gx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * 0.5 * 6.0
    gy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * 0.5 * 6.0
    length = np.sqrt(gx * gx + gy * gy + 1.0)
    wn = np.stack([-gx / length, -gy / length, 1.0 / length], -1)
    wn[part_w == 0] = (0.0, 0.0, 1.0)
    Image.fromarray(np.clip(wn * 127.5 + 127.5, 0, 255).astype(np.uint8)).save(os.path.join(a.out, a.material + "_hm_wn.png"), compress_level=3)
    print("  sweat %d px: %.1f %% of the skin can run, %.1f %% can stand in drops; veins on %.1f %%; %.0f s in all" % (
        w, 100.0 * (run[part_w > 0] > 0.3).mean(), 100.0 * (drop[part_w > 0] > 0.3).mean(), 100.0 * (wet[..., 2][part_w > 0] > 60).mean(), time.time() - t0))


if __name__ == "__main__":
    main()
