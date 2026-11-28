"""blender -b --factory-startup --python Tools/skin_transfer/correspond.py -- <source.npz> <fit.npz> <target.fbx> <material> <size> <out.npz>

For every pixel of a target material's texture: which point of the source body (the one a skin pack was painted for, laid
over the target by fit.py) lies there - as that body's UV.  The target's triangles are drawn into its UV square (pixel ->
triangle and where in it -> a point in space and the way the skin faces there), and the point asks the fitted source mesh
for its nearest point that faces the same way.

    out.npz:  part  (size, size) uint8    0 nothing, 1 the source's body, 2 its head
              uv    (size, size, 2) float32   the source's UV there (v up, as the mesh has it)
              far   (size, size) float32      how far the two skins are apart there, metres (a large value: do not trust it)

Rows run down the picture (row 0 = v 1), as the textures are stored.  A target mesh that only covers part of a body (the
skin of an armoured model) works the same: it stands where the whole body stands.

A material slot may hold parts that another picture is meant for: ROE's man is one slot (the game draws him as a flat
silhouette) - his skin, and two eyeballs whose UVs each cover the whole square.  Drawn into the square they lie over the
skin's islands (the first run of his body: "90 % on the head", every island under an eyeball's triangles).  Such a part
is told by the scale of its UV: a shell (what hangs together) whose centimetres per UV unit are under a quarter of the
largest shell's is not of this layout and is left out.
"""
import os
import sys
import time

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import mishi_fbx  # noqa: E402


def to_blender(p):
    return (p[0] / 100.0, -p[2] / 100.0, p[1] / 100.0)


def shells(polys, spot):
    """Which polygons hang together (by the spots of their corners): an id for each polygon."""
    parent = {}

    def find(x):
        root = x
        while parent.get(root, root) != root:
            root = parent[root]
        while parent.get(x, x) != root:
            parent[x], x = root, parent[x]
        return root
    for poly in polys:
        a = find(int(spot[poly[0]]))
        for v in poly[1:]:
            b = find(int(spot[v]))
            if a != b:
                parent[b] = a
    return [find(int(spot[poly[0]])) for poly in polys]


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    src_path, fit_path, fbx, material, size, out = args[:6]
    size = int(size)
    src, fit = np.load(src_path), np.load(fit_path)
    uv_name = "UV0"
    sv = np.vstack([fit["body_verts"], fit["head_verts"]]).astype(np.float64)
    nb, ntb = len(fit["body_verts"]), len(src["body_tris"])
    st = np.vstack([src["body_tris"], src["head_tris"] + nb]).astype(np.int32)
    suv = np.vstack([src["body_uv_" + uv_name], src["head_uv_" + uv_name]]).astype(np.float64)      # (triangles, 3, 2)
    tree = BVHTree.FromPolygons([tuple(p) for p in sv], [tuple(int(i) for i in t) for t in st])

    # the target: every triangle of the material, with its corners' UVs
    d = mishi_fbx.meshes(fbx)
    P, UV, base_normals = [], [], []
    for m in d["meshes"]:
        if material not in m["materials"]:
            continue
        verts = np.array([to_blender(p) for p in m["vertices"]], np.float64)
        # smooth normals over the whole mesh (its other materials too: the skin goes on under an armour's edge)
        tris_all = []
        for poly in m["polygons"]:
            for k in range(1, len(poly) - 1):
                tris_all.append((poly[0], poly[k], poly[k + 1]))
        tris_all = np.array(tris_all, np.int32)
        fn = np.cross(verts[tris_all[:, 1]] - verts[tris_all[:, 0]], verts[tris_all[:, 2]] - verts[tris_all[:, 0]])
        # (vertices are split along UV seams: sum the face normals by spot, not by vertex)
        key = np.round(verts / 1e-5).astype(np.int64)
        _, spot = np.unique(key, axis=0, return_inverse=True)
        spot = spot.reshape(-1)
        acc = np.zeros((spot.max() + 1, 3))
        for k in range(3):
            np.add.at(acc, spot[tris_all[:, k]], fn)
        vn = acc[spot]
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        # the material's shells and the scale of each one's UV; what is far finer than the largest is another picture's
        mine = [i for i, name in enumerate(m["materials"]) if name == material]
        shell = shells([m["polygons"][i] for i in mine], spot)
        area, area_uv, count = {}, {}, {}
        for i, s in zip(mine, shell):
            poly, uvs = m["polygons"][i], np.array(m["uvs"][i], np.float64)
            p = verts[list(poly)]
            for k in range(1, len(poly) - 1):
                area[s] = area.get(s, 0.0) + 0.5 * float(np.linalg.norm(np.cross(p[k] - p[0], p[k + 1] - p[0])))
                e0, e1 = uvs[k] - uvs[0], uvs[k + 1] - uvs[0]
                area_uv[s] = area_uv.get(s, 0.0) + 0.5 * abs(float(e0[0] * e1[1] - e0[1] * e1[0]))
            count[s] = count.get(s, 0) + 1
        scale = {s: np.sqrt(area[s] / max(area_uv[s], 1e-12)) for s in area}
        largest = max(area, key=area.get)
        other = {s for s in scale if scale[s] < 0.25 * scale[largest]}
        if other:
            print("%s: %d shells; %d of them (%d polygons, %.1f cm2) have a UV %.0f times finer than the skin's %.1f cm a unit - another picture's, left out" % (
                material, len(area), len(other), sum(count[s] for s in other), sum(area[s] for s in other) * 1e4,
                scale[largest] / max(scale[s] for s in other), scale[largest] * 100.0))
        for i, s in zip(mine, shell):
            if s in other:
                continue
            poly, uvs = m["polygons"][i], m["uvs"][i]
            for k in range(1, len(poly) - 1):
                idx = (poly[0], poly[k], poly[k + 1])
                P.append(verts[list(idx)])
                UV.append([uvs[0], uvs[k], uvs[k + 1]])
                base_normals.append(vn[list(idx)])
    P, UV, N = np.array(P), np.array(UV, np.float64), np.array(base_normals)
    # (a mesh of several materials may keep each in its own UV square - the face's u runs from 1 to 2: back into 0..1)
    UV = UV - np.floor(UV.mean(axis=1, keepdims=True))
    print("%s: %d triangles, uv %.3f..%.3f / %.3f..%.3f" % (material, len(P), UV[..., 0].min(), UV[..., 0].max(), UV[..., 1].min(), UV[..., 1].max()))

    # draw the triangles into the UV square: pixel -> triangle, two barycentric weights
    tri_of = np.full((size, size), -1, np.int32)
    bary = np.zeros((size, size, 2), np.float32)
    px = UV[..., 0] * size - 0.5                           # pixel centres at integers
    py = (1.0 - UV[..., 1]) * size - 0.5
    for t in range(len(P)):
        x, y = px[t], py[t]
        x0, x1 = max(int(np.floor(x.min())), 0), min(int(np.ceil(x.max())), size - 1)
        y0, y1 = max(int(np.floor(y.min())), 0), min(int(np.ceil(y.max())), size - 1)
        if x1 < x0 or y1 < y0:
            continue
        den = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        a = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / den
        b = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / den
        c = 1.0 - a - b
        inside = (a >= -1e-4) & (b >= -1e-4) & (c >= -1e-4)
        if not inside.any():
            continue
        sub = tri_of[y0:y1 + 1, x0:x1 + 1]
        sub[inside] = t
        sb = bary[y0:y1 + 1, x0:x1 + 1]
        sb[inside, 0], sb[inside, 1] = a[inside], b[inside]
    rows, cols = np.nonzero(tri_of >= 0)
    t = tri_of[rows, cols]
    a, b = bary[rows, cols, 0].astype(np.float64), bary[rows, cols, 1].astype(np.float64)
    c = 1.0 - a - b
    pos = P[t, 0] * a[:, None] + P[t, 1] * b[:, None] + P[t, 2] * c[:, None]
    nrm = N[t, 0] * a[:, None] + N[t, 1] * b[:, None] + N[t, 2] * c[:, None]
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    print("%d x %d: %.1f %% of the pixels are skin (%d)" % (size, size, 100.0 * len(rows) / size / size, len(rows)))

    n = len(rows)
    hit_tri = np.full(n, -1, np.int32)
    hit_loc = np.zeros((n, 3), np.float64)
    hit_far = np.full(n, 9.0, np.float32)
    reach = 0.03
    t0 = time.time()
    find, find_range = tree.find_nearest, tree.find_nearest_range
    CHUNK = 500000                                       # (lists of that many points at a time: 8K has 30 million of them)
    for c0 in range(0, n, CHUNK):
        plist, nlist = pos[c0:c0 + CHUNK].tolist(), nrm[c0:c0 + CHUNK].tolist()
        tris_, locs_, fars_ = [], [], []
        for k in range(len(plist)):
            p = plist[k]
            hit = find(p, reach)
            loc = hit[0]
            if loc is None:
                tris_.append(-1); locs_.append((0.0, 0.0, 0.0)); fars_.append(9.0)
                continue
            nv = nlist[k]
            fnrm = hit[1]
            if fnrm[0] * nv[0] + fnrm[1] * nv[1] + fnrm[2] * nv[2] < 0.2:
                best = None
                for loc2, nrm2, idx2, dist2 in find_range(p, reach):
                    if nrm2[0] * nv[0] + nrm2[1] * nv[1] + nrm2[2] * nv[2] >= 0.2 and (best is None or dist2 < best[3]):
                        best = (loc2, nrm2, idx2, dist2)
                if best is None:
                    tris_.append(-1); locs_.append((0.0, 0.0, 0.0)); fars_.append(9.0)
                    continue
                hit = best
                loc = hit[0]
            tris_.append(hit[2]); locs_.append((loc[0], loc[1], loc[2])); fars_.append(hit[3])
        hit_tri[c0:c0 + len(plist)] = tris_
        hit_loc[c0:c0 + len(plist)] = locs_
        hit_far[c0:c0 + len(plist)] = fars_
        if (c0 // CHUNK) % 8 == 7:
            print("  %d / %d pixels, %.0f s" % (c0 + len(plist), n, time.time() - t0))
    ok = hit_tri >= 0
    # where on the source triangle: barycentric weights of the hit point -> the source's UV
    tri = st[hit_tri[ok]]
    p0, p1, p2 = sv[tri[:, 0]], sv[tri[:, 1]], sv[tri[:, 2]]
    v0, v1, v2 = p1 - p0, p2 - p0, hit_loc[ok] - p0
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    den = np.maximum(d00 * d11 - d01 * d01, 1e-30)
    w1 = np.clip((d11 * d20 - d01 * d21) / den, 0.0, 1.0)
    w2 = np.clip((d00 * d21 - d01 * d20) / den, 0.0, 1.0)
    w0 = 1.0 - w1 - w2
    uvs = suv[hit_tri[ok]]
    uv = uvs[:, 0] * w0[:, None] + uvs[:, 1] * w1[:, None] + uvs[:, 2] * w2[:, None]
    part = np.zeros((size, size), np.uint8)
    out_uv = np.zeros((size, size, 2), np.float32)
    far = np.full((size, size), 9.0, np.float32)
    r, cc = rows[ok], cols[ok]
    part[r, cc] = np.where(hit_tri[ok] < ntb, 1, 2)
    out_uv[r, cc] = uv
    far[r, cc] = hit_far[ok]
    f = hit_far[ok] * 1000
    print("%.1f %% of the skin pixels found their point (%.0f s); apart: median %.2f mm, 90 %% under %.2f mm, 99 %% under %.2f mm; %.1f %% on the head" % (
        100.0 * ok.mean(), time.time() - t0, np.median(f), np.percentile(f, 90), np.percentile(f, 99), 100.0 * (hit_tri[ok] >= ntb).mean()))
    np.savez_compressed(out, part=part, uv=out_uv, far=far)
    print("wrote", out)


main()
