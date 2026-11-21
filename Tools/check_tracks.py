"""What is wrong with a slice's motion tracks before Unreal ever sees them (system Python with numpy):

    python Tools/check_tracks.py Import/eros15_07 [Import/a08_s01 ...]

For <who>_anim.json / .bin of every body in the folder (written by the Unity project's MishiUeExport):

  stairs   bone tracks that stand still most of the time and jump now and then.  The ripped clips step a whole quaternion key
           when one of its components has an infinite slope (the x and y of one-axis joints: forearm, calf, finger joints);
           MishiUeExport.Unstepped takes that out.  A few are real holds (toes that move twice in a clip); hundreds are not.
  mirrors  bones whose scale is negative.  All three axes: a mirror through the bone's origin, which the FBX import leaves
           out of the reference pose - mishi_anim.py drops it from the track (her right shoulder caved in while it did not).
           One or two axes: a real mirror, nothing handles it.
  wrists   where the hand bone sits against where the forearm's skin ends.  The skin of a forearm follows the twist bones
           (ForeTwist -> ForeTwist1, children of the UPPER ARM); the hand follows the forearm bone.  With a stepped forearm the
           two part - by 8.8 cm in the first export of eros15_07, a wrist pulled apart and popping.
"""
import json
import os
import sys

import numpy as np


def load(stem):
    with open(stem + ".json", encoding="utf-8") as f:
        meta = json.load(f)
    bones, fpf = meta["bones"], meta["floats_per_frame"]
    nb = len(bones)
    data = np.fromfile(stem + ".bin", "<f4")
    clips, off = [], 0
    for c in meta["clips"]:
        n = c["frames"]
        clips.append((c["name"], data[off:off + n * fpf].reshape(n, fpf)[:, :nb * 10].reshape(n, nb, 10).astype(np.float64)))
        off += n * fpf
    return bones, clips


def unit(q):
    return q / np.maximum(np.linalg.norm(q, axis=-1, keepdims=True), 1e-12)


def rotate(q, v):
    """v turned by the unit quaternions q = (x, y, z, w): [n, 4], [3] or [n, 3] -> [n, 3]."""
    u, w = q[:, :3], q[:, 3:4]
    v = np.broadcast_to(v, u.shape)
    t = 2 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def mul(a, b):
    ax, ay, az, aw = a.T
    bx, by, bz, bw = b.T
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz], 1)


def steps(q):
    """Degrees turned from each frame to the next: [frames - 1, bones]."""
    return np.degrees(2 * np.arccos(np.clip(np.abs((q[1:] * q[:-1]).sum(-1)), 0, 1)))


def check(stem):
    bones, clips = load(stem)
    who = os.path.basename(stem)
    print("%s: %d bones, %d clips" % (who, len(bones), len(clips)))
    # stairs
    total, worst = 0, {}
    for name, X in clips:
        if len(X) < 8:
            continue
        st = steps(unit(X[:, :, 3:7]))
        stair = ((st < 1e-3).mean(0) > 0.5) & (st.max(0) > 0.5)
        # a real hold moves over several frames when it moves; a stair jumps in one
        moving = st > 0.3
        single = moving[1:-1] & ~moving[:-2] & ~moving[2:]
        stair &= single.sum(0) >= 2
        total += int(stair.sum())
        for bi in np.nonzero(stair)[0]:
            worst[bones[bi]] = max(worst.get(bones[bi], 0.0), float(st[:, bi].max()))
    top = sorted(worst.items(), key=lambda kv: -kv[1])[:5]
    print("   stairs : %d bone tracks jump between holds%s" % (total, (" - the largest: " + ", ".join("%s %.0f deg" % kv for kv in top)) if top else ""))
    # mirrors
    scale = np.concatenate([X[:, :, 7:10] for _, X in clips])
    neg = (scale < 0).any(0)
    names = ["%s (%s)" % (bones[bi], "through its origin: dropped at import" if neg[bi].all() else "ONE OR TWO AXES: not handled") for bi in np.nonzero(neg.any(1))[0]]
    print("   mirrors: %s" % (", ".join(names) or "none"))
    # wrists
    for side in ("L", "R"):
        found = None
        for prefix in ("Bip001", "Bip000"):
            want = ["%s %s %s" % (prefix, side, n) for n in ("Forearm", "ForeTwist", "ForeTwist1", "Hand")]
            if all(w in bones for w in want):
                found = [bones.index(w) for w in want]
        if not found:
            continue
        f, t, t1, h = found
        gaps, angles = [], []
        for _, X in clips:
            hand = X[0, h, :3]
            seg = X[0, t1, :3]
            qf, qt, qt1 = unit(X[:, f, 3:7]), unit(X[:, t, 3:7]), unit(X[:, t1, 3:7])
            by_forearm = X[:, f, :3] + rotate(qf, hand)
            by_twist = X[:, t, :3] + rotate(qt, seg) + rotate(mul(qt, qt1), hand - seg)
            gaps.append(np.linalg.norm(by_forearm - by_twist, axis=1) * 100)
            axis = hand / max(np.linalg.norm(hand), 1e-9)
            angles.append(np.degrees(np.arccos(np.clip((rotate(qf, axis) * rotate(qt, axis)).sum(1), -1, 1))))
        gaps, angles = np.concatenate(gaps), np.concatenate(angles)
        print("   wrist %s: the hand is %.2f cm from the end of the forearm's skin on average, %.2f cm at most; forearm against twist bone %.1f deg at most%s" % (
            side, gaps.mean(), gaps.max(), angles.max(), "   <-- STEPPED FOREARM?" if gaps.max() > 1.0 else ""))


for folder in sys.argv[1:] or ["."]:
    stems = sorted(os.path.join(folder, f[:-5]) for f in os.listdir(folder) if f.endswith("_anim.json") and os.path.isfile(os.path.join(folder, f[:-5] + ".bin")))
    print("== %s" % folder)
    if not stems:
        print("   no <who>_anim.json / .bin here")
    for stem in stems:
        check(stem)
