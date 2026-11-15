"""The sky of a Rise of Eros battle stage as one long-lat picture in Unreal's space.

The game's skybox (shader Pinkcore/Skybox/FogCubemap, rewritten as ROE/Skybox in the Unity project) is a cubemap times
4.5948 x tint x exposure, turned about the vertical by _Rotation, with a band of fog colour from the horizon up to _FogHeight.
This bakes that, for every direction of Unreal's world, into a 16-bit PNG (value / SCALE, linear): the sky sphere's
material reads it back with the same direction -> (u, v) rule, and the sky light captures the sphere.

The fog band is left out unless asked for (--fog-band): stage s01's reaches 41 degrees up at 86 % - in the game the sky is a
flat pale blue wherever a level camera looks, and the picture under it (a sea of clouds with snow peaks, a sun on the
horizon) never shows.  Here it does: it is what the armour mirrors.

    python Tools/mishi_sky.py Import/a08_s01 [--width 4096] [--fog-band]

Writes <slice>/sky_longlat.png and <slice>/sky.json (scale, mean radiance, irradiance on an upward face, and where the
picture has its sun: the brightest patch, as azimuth atan2(Y, X) and elevation in degrees).  System Python with numpy and
Pillow.

Direction -> (u, v), in Unreal's axes (X forward, Y right, Z up):  u = atan2(Y, X) / 2 pi + 0.5,  v = acos(Z) / pi.
Unity (x, y, z) is Unreal (-x, z, y) (MishiSpace).
"""
import argparse
import json
import math
import os
import struct
import zlib

import numpy as np
from PIL import Image

SCALE = 8.0             # the PNG holds linear radiance / SCALE


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def write_png16(path, rgb):
    """rgb: float array (h, w, 3) in 0..1 -> 16-bit RGB PNG."""
    h, w, _ = rgb.shape
    data = np.clip(np.round(rgb * 65535.0), 0, 65535).astype(">u2")
    raw = np.zeros((h, 1 + w * 6), dtype=np.uint8)
    raw[:, 1:] = data.reshape(h, w * 3).view(np.uint8).reshape(h, w * 6)

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 16, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw.tobytes(), 6)) + chunk(b"IEND", b""))


def sample_cube(faces, d):
    """faces: (6, n, n, 3) linear, Unity's order +X -X +Y -Y +Z -Z; d: (..., 3) Unity directions.  Bilinear inside a face."""
    x, y, z = d[..., 0], d[..., 1], d[..., 2]
    ax, ay, az = np.abs(x), np.abs(y), np.abs(z)
    out = np.zeros(d.shape, dtype=np.float64)
    n = faces.shape[1]
    # the cubemap convention of Direct3D / OpenGL: face, then (sc, tc) / major axis
    table = [
        ((ax >= ay) & (ax >= az) & (x > 0), -z, -y, ax),
        ((ax >= ay) & (ax >= az) & (x <= 0), z, -y, ax),
        ((ay > ax) & (ay >= az) & (y > 0), x, z, ay),
        ((ay > ax) & (ay >= az) & (y <= 0), x, -z, ay),
        ((az > ax) & (az > ay) & (z > 0), x, -y, az),
        ((az > ax) & (az > ay) & (z <= 0), -x, -y, az),
    ]
    for i, (mask, sc, tc, ma) in enumerate(table):
        if not mask.any():
            continue
        u = (sc[mask] / ma[mask] + 1.0) * 0.5 * n - 0.5
        v = (tc[mask] / ma[mask] + 1.0) * 0.5 * n - 0.5
        u0 = np.clip(np.floor(u).astype(int), 0, n - 1)
        v0 = np.clip(np.floor(v).astype(int), 0, n - 1)
        u1 = np.clip(u0 + 1, 0, n - 1)
        v1 = np.clip(v0 + 1, 0, n - 1)
        fu = np.clip(u - u0, 0, 1)[:, None]
        fv = np.clip(v - v0, 0, 1)[:, None]
        f = faces[i]
        out[mask] = (f[v0, u0] * (1 - fu) + f[v0, u1] * fu) * (1 - fv) + (f[v1, u0] * (1 - fu) + f[v1, u1] * fu) * fv
    return out


def brightest_patch(lum, radius_deg=5.0):
    """Where a long-lat luminance picture is brightest over a patch of about this radius: (azimuth, elevation) in degrees."""
    h, w = lum.shape
    k = max(1, int(round(radius_deg / 180.0 * h)))
    pad = np.pad(lum, ((k, k), (0, 0)), mode="edge")
    pad = np.pad(pad, ((0, 0), (k, k)), mode="wrap")
    cs = np.zeros((pad.shape[0] + 1, pad.shape[1] + 1))
    cs[1:, 1:] = pad.cumsum(0).cumsum(1)
    box = cs[2 * k:2 * k + h, 2 * k:2 * k + w] - cs[:h, 2 * k:2 * k + w] - cs[2 * k:2 * k + h, :w] + cs[:h, :w]
    iy, ix = np.unravel_index(int(np.argmax(box)), box.shape)
    return ((ix + 0.5) / w - 0.5) * 360.0, 90.0 - (iy + 0.5) / h * 180.0


def bake(slice_dir, width, fog_band=False):
    with open(os.path.join(slice_dir, "showcase.json"), encoding="utf-8") as f:
        showcase = json.load(f)
    with open(os.path.join(slice_dir, "materials.json"), encoding="utf-8") as f:
        materials = json.load(f)
    sky = showcase.get("sky") or {}
    m = materials.get(sky.get("material") or "")
    if not m or "_Cubemap" not in m.get("textures", {}):
        raise SystemExit("no skybox material with a _Cubemap in " + slice_dir)
    fl, col = m["floats"], m["colors"]
    strip = Image.open(os.path.join(slice_dir, "textures", m["textures"]["_Cubemap"])).convert("RGB")
    n = strip.width
    if strip.height != n * 6:
        raise SystemExit("the cubemap is not a strip of six faces: %s" % (strip.size,))
    faces = srgb_to_linear(np.asarray(strip, dtype=np.float64) / 255.0).reshape(6, n, n, 3)
    tint = np.array(col.get("_Tint", [1, 1, 1, 1])[:3], dtype=np.float64)          # (a Color: sRGB in the file, linear in the shader)
    tint = srgb_to_linear(tint)
    exposure = float(fl.get("_Exposure", 1.0))
    angle = math.radians(float(fl.get("_Rotation", 0.0)))
    fog_on = float(fl.get("_EnableFog", 0.0)) > 0.5 or "SKYBOX_FOG" in m.get("keywords", [])
    fog_color = srgb_to_linear(np.array(col.get("_FogColor", [1, 1, 1, 1])[:3], dtype=np.float64))
    fog_h, fog_s, fog_i = float(fl.get("_FogHeight", 0.5)), float(fl.get("_FogSoftness", 0.05)), float(fl.get("_FogIntensity", 1.0))

    height = width // 2
    u = (np.arange(width) + 0.5) / width
    v = (np.arange(height) + 0.5) / height
    lon = (u - 0.5) * 2.0 * math.pi                     # atan2(Y, X)
    lat = v * math.pi                                   # from +Z down
    sin_lat = np.sin(lat)[:, None]
    X = sin_lat * np.cos(lon)[None, :]
    Y = sin_lat * np.sin(lon)[None, :]
    Z = np.repeat(np.cos(lat)[:, None], width, axis=1)
    # Unreal -> Unity: (x, y, z) = (-X, Z, Y); then back through the skybox's turn about the vertical (it turns the dome, the
    # texture is read with the unturned direction)
    vx, vy, vz = -X, Z, Y
    c, s = math.cos(angle), math.sin(angle)
    px = c * vx + s * vz
    pz = -s * vx + c * vz
    d = np.stack([px, vy, pz], axis=-1)
    color = sample_cube(faces, d) * tint * 4.59479380 * exposure
    sun_az, sun_el = brightest_patch(color @ np.array([0.2126, 0.7152, 0.0722]))
    fog_on = fog_on and fog_band
    if fog_on:
        t = np.clip((vy - (fog_h - fog_s)) / max(2.0 * fog_s, 1e-6), 0.0, 1.0)
        fog = 1.0 - t * t * (3.0 - 2.0 * t)
        color = color + (fog_color - color) * (fog * fog_i)[..., None]
    write_png16(os.path.join(slice_dir, "sky_longlat.png"), color / SCALE)
    # what the sky gives: mean radiance, and the irradiance on a face looking up (cosine-weighted over the upper half)
    w_solid = (sin_lat * (math.pi / height) * (2.0 * math.pi / width))
    up = np.clip(Z, 0, None)
    e_up = (color * (w_solid * up)[..., None]).sum(axis=(0, 1))
    mean = (color * w_solid[..., None]).sum(axis=(0, 1)) / (4.0 * math.pi)
    info = {"file": "sky_longlat.png", "scale": SCALE, "width": width, "height": height, "rotation": float(fl.get("_Rotation", 0.0)),
            "mean_radiance": [round(float(x), 4) for x in mean], "irradiance_up": [round(float(x), 4) for x in e_up],
            "max": round(float(color.max()), 3), "fog_band": fog_on, "source": m["textures"]["_Cubemap"],
            "sun_azimuth": round(float(sun_az), 1), "sun_elevation": round(float(sun_el), 1)}
    with open(os.path.join(slice_dir, "sky.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1)
    # a small tone-mapped preview to look at
    prev = np.clip(color / (1.0 + color), 0, 1) ** (1 / 2.2)
    Image.fromarray((prev * 255).astype(np.uint8)).resize((1024, 512), Image.LANCZOS).save(os.path.join(slice_dir, "sky_preview.jpg"), quality=88)
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("slice_dir")
    ap.add_argument("--width", type=int, default=4096)
    ap.add_argument("--fog-band", action="store_true", help="keep the game's band of fog colour over the lower sky")
    args = ap.parse_args()
    print(json.dumps(bake(args.slice_dir, args.width, args.fog_band)))


if __name__ == "__main__":
    main()
