"""blender -b --factory-startup <body.blend> --python Tools/skin_transfer/hs2_dump.py -- <out.npz>

The body a skin pack was painted for, as numbers a fit can work with (numpy only - Blender's Python has it): for the body
and the head mesh their vertices (metres, Z up, the character facing -Y), triangles, the UV of every triangle corner, the
skin weights, and where the bones stand.  The .blend is what ripper_tpose's scripts/honeyselect2/export_model.py --body
female writes (HoneySelect 2's cf_body + head, bones cf_J_*); any body with these object names would do.
"""
import sys

import bpy
import numpy as np

out = sys.argv[sys.argv.index("--") + 1]
MESHES = {"body": "o_body_cf", "head": "o_head"}
EXTRA = ("o_eyebase_L", "o_eyebase_R", "o_tooth", "o_tang")
data = {}
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
names = [b.name for b in arm.data.bones]
data["bone_names"] = np.array(names)
data["bone_heads"] = np.array([list(arm.matrix_world @ b.head_local) for b in arm.data.bones], np.float32)
data["bone_tails"] = np.array([list(arm.matrix_world @ b.tail_local) for b in arm.data.bones], np.float32)
data["bone_parents"] = np.array([names.index(b.parent.name) if b.parent else -1 for b in arm.data.bones], np.int32)
for key, name in MESHES.items():
    o = bpy.data.objects[name]
    me = o.data
    if me.shape_keys:
        # the face as the basis has it (no expression)
        for kb in me.shape_keys.key_blocks:
            kb.value = 0.0
    me.calc_loop_triangles()
    mw = o.matrix_world
    verts = np.array([list(mw @ v.co) for v in me.vertices], np.float32)
    tris = np.array([list(t.vertices) for t in me.loop_triangles], np.int32)
    loops = np.array([list(t.loops) for t in me.loop_triangles], np.int32)
    data[key + "_verts"], data[key + "_tris"] = verts, tris
    for layer in me.uv_layers:
        uv = np.array([list(d.uv) for d in layer.data], np.float32)
        data["%s_uv_%s" % (key, layer.name)] = uv[loops]                      # (triangles, 3, 2)
    groups = [g.name for g in o.vertex_groups]
    data[key + "_groups"] = np.array(groups)
    rows = []
    for v in me.vertices:
        for g in v.groups:
            if g.weight > 1e-4:
                rows.append((v.index, g.group, g.weight))
    data[key + "_weights"] = np.array(rows, np.float32)
    print(key, name, "verts", len(verts), "tris", len(tris), "uv layers", [l.name for l in me.uv_layers], "groups", len(groups), "weights", len(rows))
for name in EXTRA:
    o = bpy.data.objects.get(name)
    if o is not None:
        data["extra_" + name] = np.array([list(o.matrix_world @ v.co) for v in o.data.vertices], np.float32)
np.savez_compressed(out, **data)
print("wrote", out)
