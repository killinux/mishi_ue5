"""Mishi UE5: AnimSequences built from the per-frame tracks Unity sampled (Import/<slice>/<who>_anim.json + .bin), through the
animation data controller - no FBX in between.

Why: both of Unreal's FBX importers (the legacy one and Interchange - the same Autodesk SDK evaluates the file) read every
TRANSLATION of the Unity FBX Exporter's takes as zero; rotations come through.  The mesh and its skeleton still come from the
FBX; the motion comes from here.

Space.  A bone's local transform in Unity (left-handed, metres) and in the Unreal skeleton the FBX import built differ by the two
mirrors on the way (Unity -> FBX mirrors X, Unreal's import mirrors Y): position (x, y, z) -> (-x, -y, z) * 100, quaternion
(x, y, z, w) -> (-x, -y, z, w), scale as it is.  The top bone (its parent is the model root, no bone) is relative to the model
root, which stands at the component's origin, and goes the whole way an FBX node does: mirror X, the import's Y-up -> Z-up turn
(+90 degrees about X), mirror Y - position (-x, z, y) * 100.  (The clips' own curves for the model root - a quarter turn about X -
are root motion the game does not apply; Unity's export leaves them out.)
Bone names: the import turned spaces into dashes (Bip001 L Thigh -> Bip001-L-Thigh).
Blend shapes: Unity's weights 0..100 become float curves 0..1 named after the morph targets.
"""
import array
import json
import math
import os

import unreal

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
S = math.sqrt(0.5)


def log(msg):
    unreal.log("[MISHI] " + msg)


def top_bone(px, py, pz, qx, qy, qz, qw):
    """A top bone's transform in the model root's parent space (Unity) -> Unreal component space."""
    # mirror X (Unity -> FBX)
    fx, fy, fz, fw = qx, -qy, -qz, qw
    # the import's Y-up -> Z-up turn: +90 degrees about X, applied on the left
    ax, ay, az, aw = S, 0.0, 0.0, S
    tx = aw * fx + ax * fw + ay * fz - az * fy
    ty = aw * fy - ax * fz + ay * fw + az * fx
    tz = aw * fz + ax * fy - ay * fx + az * fw
    tw = aw * fw - ax * fx - ay * fy - az * fz
    # mirror Y (FBX -> Unreal)
    return (-px * 100.0, pz * 100.0, py * 100.0), (-tx, ty, -tz, tw)


def build(who, src_stem, skeleton, mesh, folder, force=False, warn=None):
    """Returns the AnimSequences of <who> (female / male), made or refreshed from <src_stem>.json / .bin."""
    warn = warn or unreal.log_warning
    if not os.path.isfile(src_stem + ".json") or not os.path.isfile(src_stem + ".bin"):
        warn("%s: no %s.json / .bin (re-export the actors from Unity)" % (who, src_stem))
        return []
    with open(src_stem + ".json", encoding="utf-8") as f:
        meta = json.load(f)
    stamp = "%d:%d" % (os.path.getmtime(src_stem + ".bin"), os.path.getsize(src_stem + ".bin"))
    stamp_file = os.path.join(os.path.dirname(src_stem), "_ue_" + os.path.basename(src_stem) + ".stamp")
    names = ["%s_%s" % (who, c["name"]) for c in meta["clips"]]
    have_all = all(eal.does_asset_exist("%s/%s" % (folder, n)) for n in names)
    have = ""
    if os.path.isfile(stamp_file):
        with open(stamp_file) as f:
            have = f.read()
    if have_all and not force and have == stamp:
        return [unreal.load_asset("%s/%s.%s" % (folder, n, n)) for n in names]

    data = array.array("f")
    with open(src_stem + ".bin", "rb") as f:
        data.frombytes(f.read())
    fps = int(meta["fps"])
    bones, parents, shapes = meta["bones"], meta["parents"], meta["shapes"]
    fpf = int(meta["floats_per_frame"])
    nb = len(bones)
    ref_names = set()
    try:
        ref_names = {str(n) for n in mesh.get_editor_property("skeleton").get_reference_pose().get_bone_names()}
    except Exception:
        pass
    # what the import made of the names; a bone the skeleton does not know is skipped
    ue_names = [b.replace(" ", "-") for b in bones]
    out = []
    offset = 0
    mirrored, odd = set(), set()
    V, Q = unreal.Vector, unreal.Quat           # (the scripted SetBoneTrackKeys takes the double types)
    for ci, clip in enumerate(meta["clips"]):
        n = int(clip["frames"])
        name = names[ci]
        path = "%s/%s" % (folder, name)
        # always a new asset: a sequence keeps the sampling rate it was born with (the project's DefaultFrameRate, 60 - see
        # Config/DefaultEngine.ini), and one born at another rate cannot hold these frames
        if eal.does_asset_exist(path):
            eal.delete_asset(path)
        factory = unreal.AnimSequenceFactory()
        factory.set_editor_property("target_skeleton", skeleton)
        factory.set_editor_property("preview_skeletal_mesh", mesh)
        anim = asset_tools.create_asset(name, folder, unreal.AnimSequence, factory)
        rate = anim.get_editor_property("platform_target_frame_rate").get_editor_property("default")
        if rate.numerator != fps * rate.denominator:
            eal.delete_asset(path)
            raise RuntimeError("new AnimSequences sample at %d/%d fps, not %d: set [/Script/Engine.AnimationSettings] DefaultFrameRate in "
                               "Config/DefaultEngine.ini and restart the editor" % (rate.numerator, rate.denominator, fps))
        c = anim.controller
        c.open_bracket(unreal.Text("Mishi tracks"), False)
        c.remove_all_bone_tracks(False)
        c.remove_all_curves_of_type(unreal.RawCurveTrackTypes.RCT_FLOAT, False)
        c.set_frame_rate(unreal.FrameRate(fps, 1), False)
        c.set_number_of_frames(unreal.FrameNumber(n - 1), False)
        skipped = 0
        for bi in range(nb):
            if ref_names and ue_names[bi] not in ref_names:
                skipped += 1
                continue
            pos, rot, scl = [], [], []
            base = offset + bi * 10
            # A bone mirrored through its own origin (scale negative on all three axes: the right shoulder's helper sphere, a
            # copy of the left one).  The FBX import builds the reference pose WITHOUT the mirror - same rotation, scale
            # positive - and a mirror through the origin cancels out of the skin matrix (animated x inverse bind) wherever
            # both carry it.  So the track drops it too; with it the skin of that bone is turned inside out through the joint
            # (her right shoulder caved in).  A scale negative on one or two axes is a real mirror: left as it is, and said.
            signs = [data[base + 7 + k] < 0.0 for k in range(3)]
            flip = -1.0 if all(signs) else 1.0
            if any(signs):
                (mirrored if all(signs) else odd).add(bones[bi])
            if parents[bi] < 0:
                for f in range(n):
                    o = base + f * fpf
                    px, py, pz, qx, qy, qz, qw = (data[o + k] for k in range(7))
                    p, q = top_bone(px, py, pz, qx, qy, qz, qw)
                    pos.append(V(p[0], p[1], p[2]))
                    rot.append(Q(q[0], q[1], q[2], q[3]))
                    scl.append(V(flip * data[o + 7], flip * data[o + 8], flip * data[o + 9]))
            else:
                for f in range(n):
                    o = base + f * fpf
                    pos.append(V(-data[o] * 100.0, -data[o + 1] * 100.0, data[o + 2] * 100.0))
                    rot.append(Q(-data[o + 3], -data[o + 4], data[o + 5], data[o + 6]))
                    scl.append(V(flip * data[o + 7], flip * data[o + 8], flip * data[o + 9]))
            c.add_bone_curve(ue_names[bi], False)
            c.set_bone_track_keys(ue_names[bi], pos, rot, scl, False)
        c.close_bracket(False)
        # the blend shapes as float curves (0..1), named after the morph targets
        times = [f / float(fps) for f in range(n)]
        for si, shape in enumerate(shapes):
            base = offset + nb * 10 + si
            values = [data[base + f * fpf] / 100.0 for f in range(n)]
            if max(values) <= 0.0 and min(values) >= 0.0:
                continue
            unreal.AnimationLibrary.add_curve(anim, shape, unreal.RawCurveTrackTypes.RCT_FLOAT, False)
            unreal.AnimationLibrary.add_float_curve_keys(anim, shape, times, values)
        offset += n * fpf
        eal.save_loaded_asset(anim, only_if_is_dirty=False)
        out.append(anim)
        if skipped:
            warn("%s: %d of %d bones are not in the skeleton" % (name, skipped, nb))
    with open(stamp_file, "w") as f:
        f.write(stamp)
    if mirrored:
        log("%s: bones mirrored through their origin, written without the mirror (as the reference pose has them): %s" % (who, ", ".join(sorted(mirrored))))
    if odd:
        warn("%s: bones with a scale negative on one or two axes (a mirror the reference pose may not have): %s" % (who, ", ".join(sorted(odd))))
    log("%s: %d animations from tracks (%d bones, %d shapes, %d fps)" % (who, len(out), nb, len(shapes), fps))
    return out
