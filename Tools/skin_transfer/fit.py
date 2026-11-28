"""blender -b --factory-startup --python Tools/skin_transfer/fit.py -- <source.npz> <target.fbx> <out.npz> [--skin a,b] [--iterations N] [--pose]

Lays one body over another: the body a skin pack was painted for (hs2_dump.py's numbers) is bent until its surface lies on
the target's (a ROE body as Unity exported it, read by Tools/mishi_fbx.py), so that a point of the target's skin can be
asked "which point of the pack's body are you?" - and with that, which pixel of the pack's textures (correspond.py).

Both stand in a T pose, facing the same way - or, with --pose, the source is first stood as the target stands: ROE's man is
bound with his arms 50 degrees down, the pack's man with his arms out.  Each limb bone of the source is turned, parent
before child, until it points where the target's does, and the source's skin follows by its own weights (linear blend
skinning; CHAINS below).  A warp of space alone would carry an arm's joints down and leave its girth standing: an arm
sheared flat.  Then three steps:

  1. landmarks: joints of the two rigs that mean the same place (hips, knees, shoulders, every finger joint), and the
     bones that sit ON a feature (nipples, mouth corners, nose wings, eyeballs, brows) - LANDMARKS below.  Not the spine's
     joints: the two rigs cut the spine at different heights.
  2. a warp of all space that carries every source landmark onto its partner and is as smooth as it can be in between
     (radial basis functions |r| with an affine part) - the skeletons now coincide, the girths do not.
  3. the surface is pulled onto the target's: each source vertex looks for the nearest target point that faces the same way,
     the pulls are smoothed over the source mesh (so the skin slides as a whole, it is not torn), applied, and again -
     smoothed less each round.  A target that is only part of a body (the skin an armour leaves bare) pulls only where it
     is: a nearest point on the rim of such a piece is no partner (the skin beyond the rim would be gathered up along it),
     and the vertices without a partner go with their neighbours.

Blender's Python is used for its BVH tree (nearest point on a mesh) - and has numpy.
"""
import os
import sys

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import mishi_fbx  # noqa: E402

# source (HoneySelect 2, cf_J_* - its men have the same names) -> target (ROE, 3ds Max biped: the women's rig is Bip001,
# the man's Bip000 with two joints a finger and no bones in his face); {s} = L / R.  A partner the target lacks is skipped.
FINGERS = (("Thumb", 0), ("Index", 1), ("Middle", 2), ("Ring", 3), ("Little", 4))
LANDMARKS = [
    ("mid:cf_J_LegUp00_L,cf_J_LegUp00_R", "Bip001 Pelvis"),
    ("cf_J_LegUp00_{s}", "Bip001 {s} Thigh"), ("cf_J_LegLow01_{s}", "Bip001 {s} Calf"), ("cf_J_Foot01_{s}", "Bip001 {s} Foot"),
    ("cf_J_Toes01_{s}", "Bip001 {s} Toe0"),
    ("cf_J_Neck", "Bip001 Neck"), ("cf_J_Head", "Bip001 Head"),
    ("cf_J_Shoulder_{s}", "Bip001 {s} Clavicle"), ("cf_J_ArmUp00_{s}", "Bip001 {s} UpperArm"), ("cf_J_ArmLow01_{s}", "Bip001 {s} Forearm"),
    ("cf_J_Hand_{s}", "Bip001 {s} Hand"),
    ("cf_J_Mune_Nip02_{s}", "Nipple_{s}"), ("cf_J_Ana", "Bip001 Anus_outside"),
    # the face
    ("eye:{s}", "Bip001 Eyeball_{s}"), ("cf_J_Mouth_{s}", "Bip001 Lips_{s}"), ("cf_J_Mouthup", "Bip001 Lips_TC"), ("cf_J_MouthLow", "Bip001 Lips_BC"),
    ("cf_J_NoseWing_tx_{s}", "Bip001 Nose_{s}"), ("cf_J_MayuMid_s_{s}", "Bip001 Eyebrow_{s}{r}"), ("cf_J_MayuTip_s_{s}", "Bip001 Eyebrow_{s}{s}"),
]
for finger, k in FINGERS:
    for j, tail in enumerate(("", "1", "2")):
        LANDMARKS.append(("cf_J_Hand_%s0%d_{s}" % (finger, j + 1), "Bip001 {s} Finger%d%s" % (k, tail)))
# --pose: (source bone, the source bone it points at, target bone, the target bone that one points at), parent before child
CHAINS = [
    ("cf_J_Shoulder_{s}", "cf_J_ArmUp00_{s}", "Bip001 {s} Clavicle", "Bip001 {s} UpperArm"),
    ("cf_J_ArmUp00_{s}", "cf_J_ArmLow01_{s}", "Bip001 {s} UpperArm", "Bip001 {s} Forearm"),
    ("cf_J_ArmLow01_{s}", "cf_J_Hand_{s}", "Bip001 {s} Forearm", "Bip001 {s} Hand"),
    ("cf_J_Hand_{s}", "cf_J_Hand_Middle01_{s}", "Bip001 {s} Hand", "Bip001 {s} Finger2"),
    ("cf_J_LegUp00_{s}", "cf_J_LegLow01_{s}", "Bip001 {s} Thigh", "Bip001 {s} Calf"),
    ("cf_J_LegLow01_{s}", "cf_J_Foot01_{s}", "Bip001 {s} Calf", "Bip001 {s} Foot"),
    ("cf_J_Foot01_{s}", "cf_J_Toes01_{s}", "Bip001 {s} Foot", "Bip001 {s} Toe0"),
]
for finger, k in FINGERS:
    CHAINS.append(("cf_J_Hand_%s01_{s}" % finger, "cf_J_Hand_%s02_{s}" % finger, "Bip001 {s} Finger%d" % k, "Bip001 {s} Finger%d1" % k))
# the target's materials that are skin (what the source is laid on), unless --skin names others
SKIN = ("pc_a01_nk_body", "pc_a_nk_face")


def to_blender(p):
    """Unity's FBX (centimetres, Y up, facing +Z) -> metres, Z up, facing -Y."""
    return (p[0] / 100.0, -p[2] / 100.0, p[1] / 100.0)


def load_target(path, materials):
    d = mishi_fbx.meshes(path)
    verts, tris, base = [], [], 0
    for m in d["meshes"]:
        keep = [i for i, name in enumerate(m["materials"]) if name in materials]
        if not keep:
            continue
        verts += [to_blender(p) for p in m["vertices"]]
        for i in keep:
            poly = m["polygons"][i]
            for k in range(1, len(poly) - 1):
                tris.append((base + poly[0], base + poly[k], base + poly[k + 1]))
        base += len(m["vertices"])
    bones = {k: np.array(to_blender(v)) for k, v in d["bones"].items()}
    return np.array(verts, np.float64), np.array(tris, np.int32), bones


def normals_of(verts, tris):
    fn = np.cross(verts[tris[:, 1]] - verts[tris[:, 0]], verts[tris[:, 2]] - verts[tris[:, 0]])
    vn = np.zeros_like(verts)
    for k in range(3):
        np.add.at(vn, tris[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12), fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)


def weld(verts, tol=1e-5):
    """Vertices that sit on one spot (a mesh is cut along its UV seams) as one: index of the spot for each vertex."""
    key = np.round(verts / tol).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return first, inverse.reshape(-1)


class Warp:
    """f(x) = sum w_i |x - c_i| + A [1, x]: the smoothest map (it bends least) that takes each c_i to its partner."""

    def __init__(self, src, dst, smooth=1e-6):
        n = len(src)
        k = np.linalg.norm(src[:, None] - src[None], axis=2) + np.eye(n) * smooth
        p = np.hstack([np.ones((n, 1)), src])
        a = np.zeros((n + 4, n + 4))
        a[:n, :n], a[:n, n:], a[n:, :n] = k, p, p.T
        b = np.zeros((n + 4, 3))
        b[:n] = dst
        sol = np.linalg.solve(a, b)
        self.c, self.w, self.a = src, sol[:n], sol[n:]

    def __call__(self, x):
        out = np.empty_like(x)
        for i in range(0, len(x), 20000):
            part = x[i:i + 20000]
            k = np.linalg.norm(part[:, None] - self.c[None], axis=2)
            out[i:i + 20000] = k @ self.w + np.hstack([np.ones((len(part), 1)), part]) @ self.a
        return out


def turn_between(a, b):
    """The rotation (3 x 3) that takes the direction a the short way to b."""
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    v, c = np.cross(a, b), float(np.dot(a, b))
    if c < -0.9999:
        # (opposite: half a turn about any axis square to a)
        axis = np.cross(a, [1.0, 0.0, 0.0] if abs(a[0]) < 0.9 else [0.0, 1.0, 0.0])
        axis /= np.linalg.norm(axis)
        return 2.0 * np.outer(axis, axis) - np.eye(3)
    k = np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])
    return np.eye(3) + k + k @ k / (1.0 + c)


def posed(src, target_bones, rig):
    """The source stood as the target stands: its bones' heads, body and head vertices after each limb bone of CHAINS was
    turned to point where the target's does (a child goes with its parent first), the skin following by its own weights."""
    names = [str(n) for n in src["bone_names"]]
    heads = src["bone_heads"].astype(np.float64)
    parents = src["bone_parents"]
    turn = {}
    for a, c, ta, tc in CHAINS:
        for s in ("L", "R"):
            sa, sc, t0, t1 = a.format(s=s), c.format(s=s), ta.format(s=s).replace("Bip001", rig), tc.format(s=s).replace("Bip001", rig)
            if sa in names and sc in names and t0 in target_bones and t1 in target_bones:
                turn[names.index(sa)] = (names.index(sc), target_bones[t1] - target_bones[t0])
    depth = np.zeros(len(names), np.int32)
    for i in range(len(names)):
        p = parents[i]
        while p >= 0:
            depth[i] += 1
            p = parents[p]
    world = [np.eye(3)] * len(names)
    new = heads.copy()
    most = (0.0, "")
    for i in np.argsort(depth, kind="stable"):
        p = parents[i]
        wp = world[p] if p >= 0 else np.eye(3)
        if p >= 0:
            new[i] = wp @ (heads[i] - heads[p]) + new[p]
        if i in turn:
            child, want = turn[i]
            now = wp @ (heads[child] - heads[i])
            d = turn_between(now, want)
            angle = float(np.degrees(np.arccos(np.clip(np.dot(now, want) / (np.linalg.norm(now) * np.linalg.norm(want)), -1.0, 1.0))))
            if angle > most[0]:
                most = (angle, names[i])
            world[i] = d @ wp
        else:
            world[i] = wp
    out = {"bone_heads": new}
    for key in ("body", "head"):
        verts = src[key + "_verts"].astype(np.float64)
        groups = [str(g) for g in src[key + "_groups"]]
        rows = src[key + "_weights"]
        acc, total = np.zeros_like(verts), np.zeros(len(verts))
        for g in np.unique(rows[:, 1].astype(np.int64)):
            if groups[g] not in names:
                continue
            b = names.index(groups[g])
            sel = rows[rows[:, 1].astype(np.int64) == g]
            vi, w = sel[:, 0].astype(np.int64), sel[:, 2].astype(np.float64)
            acc[vi] += ((verts[vi] - heads[b]) @ world[b].T + new[b]) * w[:, None]
            total[vi] += w
        out[key + "_verts"] = np.where(total[:, None] > 1e-6, acc / np.maximum(total[:, None], 1e-9), verts)
    print("posed: %d bones turned, the most by %.0f degrees (%s)" % (len(turn), most[0], most[1]))
    return out


def landmarks(src, target_bones):
    names = [str(n) for n in src["bone_names"]]
    heads = src["bone_heads"].astype(np.float64)

    def source(spec, s):
        if spec.startswith("mid:"):
            a, b = spec[4:].split(",")
            return (heads[names.index(a)] + heads[names.index(b)]) / 2
        if spec.startswith("eye:"):
            return src["extra_o_eyebase_" + s].astype(np.float64).mean(0)
        return heads[names.index(spec.format(s=s))]
    a, b, labels = [], [], []
    for spec, tname in LANDMARKS:
        for s, r in (("L", "R"), ("R", "L")) if "{s}" in spec or "{s}" in tname else ((None, None),):
            t = tname.format(s=s, r=r) if s else tname
            try:
                p = source(spec, s)
            except (ValueError, KeyError):
                print("landmark: the source has no", spec, s)
                continue
            if t not in target_bones:
                print("landmark: the target has no", t)
                continue
            a.append(p)
            b.append(target_bones[t])
            labels.append(t)
    return np.array(a), np.array(b), labels


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    src_path, fbx, out = args[:3]
    rounds = int(args[args.index("--iterations") + 1]) if "--iterations" in args else 10
    skin = tuple(args[args.index("--skin") + 1].split(",")) if "--skin" in args else SKIN
    src = dict(np.load(src_path))
    tv, tt, bones = load_target(fbx, skin)
    # which rig the target is: the tables above name the women's
    rig = "Bip000" if "Bip000 Pelvis" in bones else "Bip001"
    if rig != "Bip001":
        bones.update({k.replace(rig, "Bip001", 1): v for k, v in list(bones.items()) if k.startswith(rig)})
    if "--pose" in args:
        src.update(posed(src, bones, "Bip001"))
    # the target's rims: edges with one triangle (by spot - the mesh is cut along its UV seams, which are no rims)
    _, tspot = weld(tv)
    te = np.sort(np.vstack([tspot[tt[:, [0, 1]]], tspot[tt[:, [1, 2]]], tspot[tt[:, [2, 0]]]]), axis=1)
    uniq, counts = np.unique(te, axis=0, return_counts=True)
    rim = set(map(tuple, uniq[counts == 1].tolist()))
    rim_of = {}                                           # triangle -> its rim edges as vertex pairs
    for i, tri in enumerate(tt):
        for a_, b_ in ((0, 1), (1, 2), (2, 0)):
            key = (min(tspot[tri[a_]], tspot[tri[b_]]), max(tspot[tri[a_]], tspot[tri[b_]]))
            if key in rim:
                rim_of.setdefault(i, []).append((tri[a_], tri[b_]))

    def on_rim(idx, loc):
        for a_, b_ in rim_of.get(idx, ()):
            p0, p1 = tv[a_], tv[b_]
            e = p1 - p0
            t = float(np.clip(np.dot(loc - p0, e) / max(np.dot(e, e), 1e-18), 0.0, 1.0))
            if np.linalg.norm(loc - (p0 + e * t)) < 2e-4:
                return True
        return False
    tvn, tfn = normals_of(tv, tt)
    print("target: %d vertices, %d triangles of %s, %d rim edges; height %.3f m" % (len(tv), len(tt), skin, len(rim), tv[:, 2].max() - tv[:, 2].min()))

    # the source: body and head as one surface, vertices on one spot as one
    sv = np.vstack([src["body_verts"], src["head_verts"]]).astype(np.float64)
    nb = len(src["body_verts"])
    st = np.vstack([src["body_tris"], src["head_tris"] + nb]).astype(np.int32)
    first, spot = weld(sv)
    wv, wt = sv[first], spot[st]
    wt = wt[(wt[:, 0] != wt[:, 1]) & (wt[:, 1] != wt[:, 2]) & (wt[:, 0] != wt[:, 2])]
    print("source: %d vertices (%d spots), %d triangles; height %.3f m" % (len(sv), len(wv), len(st), sv[:, 2].max() - sv[:, 2].min()))

    a, b, labels = landmarks(src, bones)
    warp = Warp(a, b)
    wv = warp(wv)
    print("landmarks: %d pairs; the largest move %.1f cm (%s)" % (len(a), np.linalg.norm(b - a, axis=1).max() * 100, labels[int(np.linalg.norm(b - a, axis=1).argmax())]))

    # neighbours of each spot (for smoothing the pulls)
    edges = np.vstack([wt[:, [0, 1]], wt[:, [1, 2]], wt[:, [2, 0]]])
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    ea, eb = np.concatenate([edges[:, 0], edges[:, 1]]), np.concatenate([edges[:, 1], edges[:, 0]])

    degree = np.bincount(ea, minlength=len(wv)).astype(np.float64)

    def smoothed(pull, weight, passes):
        """The pulls averaged over the mesh, a vertex without a partner taking its neighbours': the weighted pulls and the
        weights are averaged alike (each vertex with its neighbours), their quotient is the weighted mean."""
        num, den = pull * weight[:, None], weight.copy()
        for _ in range(passes):
            n2, d2 = num.copy(), den.copy()
            np.add.at(n2, ea, num[eb])
            np.add.at(d2, ea, den[eb])
            num, den = n2 / (1.0 + degree)[:, None], d2 / (1.0 + degree)
        return num / np.maximum(den[:, None], 1e-9)

    tree = BVHTree.FromPolygons([tuple(p) for p in tv], [tuple(int(i) for i in t) for t in tt])
    reach0 = 0.06
    for it in range(rounds):
        vn, _ = normals_of(wv, wt)
        pull = np.zeros_like(wv)
        weight = np.zeros(len(wv))
        reach = reach0 * (0.75 ** it) + 0.012
        for i in range(len(wv)):
            p = Vector(wv[i])
            hit = tree.find_nearest(p, reach)
            if hit[0] is None:
                continue
            loc, nrm, idx, dist = hit
            if nrm.dot(Vector(vn[i])) < 0.3:
                # the nearest point looks the other way (the other side of a finger, the inside of a mouth): the nearest that does not
                best = None
                for loc2, nrm2, idx2, dist2 in tree.find_nearest_range(p, reach):
                    if nrm2.dot(Vector(vn[i])) >= 0.3 and (best is None or dist2 < best[3]):
                        best = (loc2, nrm2, idx2, dist2)
                if best is None:
                    continue
                loc, nrm, idx, dist = best
            if idx in rim_of and on_rim(idx, np.array(loc)):
                continue
            pull[i] = np.array(loc) - wv[i]
            weight[i] = 1.0
        passes = max(int(40 * (0.62 ** it)), 2)
        move = smoothed(pull, weight, passes)
        wv = wv + move
        d = np.linalg.norm(pull[weight > 0], axis=1) * 1000
        print("round %2d: reach %.1f cm, %d smoothing passes; %5.1f %% of the vertices have a partner, their distance median %.2f mm, 90 %% under %.2f mm" % (
            it + 1, reach * 100, passes, 100.0 * weight.mean(), np.median(d), np.percentile(d, 90)))

    fitted = wv[spot]
    np.savez_compressed(out, body_verts=fitted[:nb].astype(np.float32), head_verts=fitted[nb:].astype(np.float32),
                        landmarks_source=a, landmarks_target=b, landmark_names=np.array(labels))
    print("wrote", out)


main()
