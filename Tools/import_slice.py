"""Mishi UE5: bring one slice exported by Unity (Import/<scene>_<room>/, MishiUeExport.ExportSlice) into the project.

    python Tools/ue_remote.py Tools/import_slice.py eros15_07 [steps] [--force]      in the open editor (the fast loop)
    powershell -File Tools\\ue.ps1 import [-Slice eros15_07] [-Force]                  starts an editor for it, quits after

steps (default: all) - any of: textures audio bodies room materials effects level
  textures   the room's textures (Import/<slice>/textures) and the characters' own from the game's material cache
             (ripper_tpose's hq_material_data.py: <cache>/<id>.json + textures/) - normal maps flipped to Unreal's green, masks linear
  audio      voices, the parts' sound loops, the room's music: OGG -> WAV (ffmpeg) -> SoundWave; music and loops loop
  bodies     female.fbx / male.fbx -> skeletal meshes with morph targets; then every take as an AnimSequence at 60 fps
  room       room_meshes.fbx -> a static mesh per distinct mesh (RM_*); room.fbx whole, for the space check
  materials  the masters (mishi_materials.py) + an instance per material: the characters' from the game's own data, the room's
             from materials.json
  effects    a showcase slice's baked skill effects (Import/<slice>/fx, Unity's ExportEffects): their textures and a material
             instance per game material (mishi_fx.py); the geometry itself is read by the game at run time
  level      /Game/Mishi/Maps/<slice>: the room's placements, lights, sky, fog, post-process volume, the couple
Writes Import/<slice>/ue_import_report.json.
"""
import importlib
import json
import math
import os
import re
import struct
import subprocess
import sys
import time
import traceback
import zlib

import unreal

PROJECT = os.path.abspath(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
TOOLS = os.path.join(PROJECT, "Tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import mishi_anim  # noqa: E402
import mishi_fx  # noqa: E402
import mishi_look  # noqa: E402
import mishi_materials  # noqa: E402

importlib.reload(mishi_anim)
importlib.reload(mishi_materials)
importlib.reload(mishi_fx)
importlib.reload(mishi_look)
if "--style" in sys.argv and sys.argv.index("--style") + 1 < len(sys.argv):
    mishi_look.STYLE = sys.argv[sys.argv.index("--style") + 1]             # the picture's style: game / cinema (mishi_look.STYLES)

FFMPEG = r"D:\Program Files\ffmpeg\bin\ffmpeg.exe"
HQ_CACHE = os.environ.get("ROE_HQ_CACHE", r"E:\game_export\RiseOfEros\_meta\_hq_materials")
ALL_STEPS = ("textures", "audio", "bodies", "room", "materials", "effects", "level")

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
report = {"steps": {}, "warnings": []}


def log(msg):
    unreal.log("[MISHI] " + msg)


def warn(msg):
    unreal.log_warning("[MISHI] " + msg)
    report["warnings"].append(msg)


def setp(obj, name, value):
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as e:  # a property that moved between engine versions: say so, go on
        warn("%s.%s: %s" % (obj.get_class().get_name(), name, e))
        return False


# ---------------------------------------------------------------------------------------------------------------- arguments
def parse_args():
    """Arguments after the script, or (what Tools/ue.ps1 uses: -ExecutePythonScript takes a bare path best) MISHI_SLICE,
    MISHI_STEPS, MISHI_FORCE=1, MISHI_QUIT=1 in the environment."""
    args = [a for a in sys.argv[1:] if not a.lower().endswith(".py")]
    words = [a for a in args if not a.startswith("--")]
    slice_name = words[0] if words else os.environ.get("MISHI_SLICE", "eros15_07")
    steps = [w for w in words[1:] if w in ALL_STEPS] or [s for s in os.environ.get("MISHI_STEPS", "").split(",") if s in ALL_STEPS]
    force = "--force" in args or os.environ.get("MISHI_FORCE") == "1"
    quit_after = "--quit" in args or os.environ.get("MISHI_QUIT") == "1"
    return slice_name, tuple(steps) or ALL_STEPS, force, quit_after


SLICE, STEPS, FORCE, QUIT = parse_args()
SRC = os.path.join(PROJECT, "Import", SLICE)
DST = "/Game/Mishi/" + SLICE
MAP = "/Game/Mishi/Maps/" + SLICE


# ---------------------------------------------------------------------------------------------------------------- import helpers
def import_tasks(files, dest, options=None, names=None):
    tasks = []
    for i, f in enumerate(files):
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", dest)
        if names:
            t.set_editor_property("destination_name", names[i])
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        if options is not None:
            t.set_editor_property("options", options)
        tasks.append(t)
    if tasks:
        asset_tools.import_asset_tasks(tasks)
    out = []
    for t in tasks:
        out += [str(p) for p in t.get_editor_property("imported_object_paths")]
    return out


def asset_path(folder, name):
    return "%s/%s.%s" % (folder, name, name)


def exists(folder, name):
    return eal.does_asset_exist("%s/%s" % (folder, name))


def list_assets(folder, cls=None):
    out = []
    if not eal.does_directory_exist(folder):
        return out
    for p in eal.list_assets(folder, recursive=False, include_folder=False):
        a = unreal.load_asset(p)
        if a is not None and (cls is None or isinstance(a, cls)):
            out.append(a)
    return out


def write_png(path, w, h, rgba):
    raw = b"".join(b"\x00" + bytes(rgba) * w for _ in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


# ---------------------------------------------------------------------------------------------------------------- textures
NORMAL_SLOTS = {"_BumpMap", "_DetailNormalMap", "_NormalMap", "_EyeBumpMap"}
MASK_SLOTS = {"_MetallicGlossMap", "_MaskMap", "_OcclusionMap", "_SkinLutMap", "_OcclusionMaskMap", "_IrisMaskTex", "_EyeOcclusionMap", "_ShiftNoiseMap"}


def role_of(slot):
    return "normal" if slot in NORMAL_SLOTS else "mask" if slot in MASK_SLOTS else "color"


def set_texture_role(tex, role, character=False):
    TC = unreal.TextureCompressionSettings
    if role == "normal":
        setp(tex, "compression_settings", TC.TC_NORMALMAP)
        setp(tex, "srgb", False)
        setp(tex, "flip_green_channel", True)      # Unity's normal maps are OpenGL style (green up), Unreal's DirectX
    elif role == "mask":
        setp(tex, "compression_settings", TC.TC_MASKS)
        setp(tex, "srgb", False)
    elif character:
        setp(tex, "compression_settings", TC.TC_BC7)   # skin, hair and eyes in close-up: no DXT blocks in the gradients
    eal.save_loaded_asset(tex)


def default_textures():
    """4x4 white / black (colour), white / black (linear mask) and a flat normal: the masters' parameter defaults, each with the
    sampler type its parameter has (the engine's white square is sRGB and would not do as a mask default)."""
    folder = mishi_materials.MATS + "/Defaults"
    tmp = os.path.join(PROJECT, "Saved", "MishiDefaults")
    os.makedirs(tmp, exist_ok=True)
    want = {"white": ("T_Mishi_White", (255, 255, 255, 255), "color"), "black": ("T_Mishi_Black", (0, 0, 0, 255), "color"),
            "mask": ("T_Mishi_MaskWhite", (255, 255, 255, 255), "mask"), "mask_black": ("T_Mishi_MaskBlack", (0, 0, 0, 255), "mask"),
            "flat": ("T_Mishi_FlatNormal", (128, 128, 255, 255), "normal")}
    out = {}
    for key, (name, rgba, role) in want.items():
        if not exists(folder, name):
            path = os.path.join(tmp, name + ".png")
            write_png(path, 4, 4, rgba)
            import_tasks([path], folder)
            tex = unreal.load_asset(asset_path(folder, name))
            TC = unreal.TextureCompressionSettings
            if role == "normal":
                setp(tex, "compression_settings", TC.TC_NORMALMAP)
                setp(tex, "srgb", False)
            elif role == "mask":
                setp(tex, "compression_settings", TC.TC_MASKS)
                setp(tex, "srgb", False)
            eal.save_loaded_asset(tex)
        out[key] = unreal.load_asset(asset_path(folder, name))
    return out


def import_textures(wanted, folder, character=False):
    """wanted: {asset name: (file, role)}.  Imports what is not there yet (all with --force); returns {asset name: texture}."""
    todo = [(n, f, r) for n, (f, r) in sorted(wanted.items()) if os.path.isfile(f) and (FORCE or not exists(folder, n))]
    import_tasks([f for _, f, _ in todo], folder, names=[n for n, _, _ in todo])
    out = {}
    fresh = {n for n, _, _ in todo}
    for n, (f, role) in wanted.items():
        tex = unreal.load_asset(asset_path(folder, n)) if exists(folder, n) else None
        if tex is None:
            warn("texture %s (%s) is not there" % (n, f))
            continue
        if n in fresh:
            set_texture_role(tex, role, character)
        out[n] = tex
    return out, len(todo)


# ---------------------------------------------------------------------------------------------------------------- game material data
def character_ids(slice_data):
    ids = []
    for who in ("female", "male"):
        info = slice_data.get(who) or {}
        m = re.match(r"pc_([a-z]\d+)", info.get("root") or "")
        cid = info.get("character") or (m.group(1) if m else None)      # (a showcase slice names its character)
        if cid:
            ids.append((who, cid))
    return ids


def game_materials(slice_data):
    """The characters' materials as the game defines them (ripper_tpose's cache: every float, colour and texture slot of the
    material bundles), by material name; her data wins where both lists name a material (the shared head)."""
    out = {}
    for who, cid in character_ids(slice_data):
        path = os.path.join(HQ_CACHE, cid + ".json")
        if not os.path.isfile(path):
            warn("no game material data %s (run ripper_tpose/scripts/riseoferos/hq_material_data.py %s --all)" % (path, cid))
            continue
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        overrides = d.get("overrides", {})
        for name, m in d.get("materials", {}).items():
            if "@" in name or name in out:
                continue
            tex = {}
            tiling = {}
            for slot, t in m.get("textures", {}).items():
                tname = overrides.get(name, {}).get(slot, t["texture"])
                tex[slot] = tname
                sc, of = t.get("scale", [1, 1]), t.get("offset", [0, 0])
                if sc != [1, 1] and sc != [1.0, 1.0] or of != [0, 0] and of != [0.0, 0.0]:
                    tiling[slot] = [sc[0], sc[1], of[0], of[1]]
            out[name] = {"source": "game:" + cid, "who": who, "textures": tex, "tiling": tiling, "floats": dict(m.get("floats", {})),
                         "colors": dict(m.get("colors", {})), "keywords": list(m.get("keywords", []))}
    return out


def cache_texture_file(name, slot):
    """A texture of the game cache; normal maps as the standard RGB copy the cache keeps beside the DXT5nm original."""
    base = os.path.join(HQ_CACHE, "textures", name)
    if role_of(slot) == "normal" and os.path.isfile(base + "__nrm.png"):
        return base + "__nrm.png"
    return base + ".png"


# ---------------------------------------------------------------------------------------------------------------- audio
def step_audio(slice_data):
    t0 = time.time()
    folder = DST + "/Audio"
    src = os.path.join(SRC, "audio")
    wav_dir = os.path.join(SRC, "_wav")
    os.makedirs(wav_dir, exist_ok=True)
    wavs = []
    for f in sorted(os.listdir(src)):
        stem, ext = os.path.splitext(f)
        if ext.lower() not in (".ogg", ".wav", ".mp3"):
            continue
        wav = os.path.join(src, f) if ext.lower() == ".wav" else os.path.join(wav_dir, stem + ".wav")
        if not os.path.exists(wav):
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", os.path.join(src, f), "-acodec", "pcm_s16le", wav], check=False)
        if os.path.exists(wav):
            wavs.append(wav)
        else:
            warn("audio %s: no WAV" % f)
    todo = [w for w in wavs if FORCE or not exists(folder, os.path.splitext(os.path.basename(w))[0])]
    import_tasks(todo, folder)
    sounds = list_assets(folder, unreal.SoundWave)
    loops = {os.path.splitext((slice_data.get("music") or {}).get("file") or "")[0]}
    loops |= {os.path.splitext(s["file"])[0] for s in slice_data.get("sfx", []) if s.get("loop", True)}
    for s in sounds:
        want = s.get_name() in loops
        if bool(s.get_editor_property("looping")) != want:
            setp(s, "looping", want)
            eal.save_loaded_asset(s)
    report["steps"]["audio"] = {"sounds": len(sounds), "imported": len(todo), "looping": sorted(n for n in loops if n), "seconds": round(time.time() - t0, 1)}
    log("audio: %d sounds (%d imported), %d looping" % (len(sounds), len(todo), len([n for n in loops if n])))
    return sounds


def load_sounds():
    return list_assets(DST + "/Audio", unreal.SoundWave)


# ---------------------------------------------------------------------------------------------------------------- bodies
def mesh_options():
    o = unreal.FbxImportUI()
    setp(o, "import_mesh", True)
    setp(o, "import_as_skeletal", True)
    setp(o, "mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    setp(o, "import_animations", False)
    setp(o, "import_materials", False)
    setp(o, "import_textures", False)
    setp(o, "create_physics_asset", False)
    setp(o, "automated_import_should_detect_type", False)
    sk = o.get_editor_property("skeletal_mesh_import_data")
    setp(sk, "import_morph_targets", True)
    setp(sk, "convert_scene", True)
    setp(sk, "force_front_x_axis", False)
    setp(sk, "import_meshes_in_bone_hierarchy", True)
    setp(sk, "normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    setp(sk, "update_skeleton_reference_pose", False)
    setp(sk, "use_t0_as_ref_pose", False)
    setp(sk, "preserve_smoothing_groups", True)
    setp(sk, "threshold_position", 0.00002)
    setp(sk, "threshold_tangent_normal", 0.00002)
    setp(sk, "threshold_uv", 0.0000001)
    return o


def anim_options(skeleton):
    o = unreal.FbxImportUI()
    setp(o, "import_mesh", False)
    setp(o, "import_as_skeletal", False)
    setp(o, "import_animations", True)
    setp(o, "import_materials", False)
    setp(o, "import_textures", False)
    setp(o, "mesh_type_to_import", unreal.FBXImportType.FBXIT_ANIMATION)
    setp(o, "original_import_type", unreal.FBXImportType.FBXIT_ANIMATION)
    setp(o, "automated_import_should_detect_type", False)
    setp(o, "skeleton", skeleton)
    an = o.get_editor_property("anim_sequence_import_data")
    setp(an, "animation_length", unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    # the game's clips are keyed on a 60 fps grid (every part's length x 60 is whole); left to itself the importer finds 1920 fps
    # in the exporter's key times and refuses nine takes of ten
    setp(an, "use_default_sample_rate", False)
    setp(an, "custom_sample_rate", 60)
    setp(an, "snap_to_closest_frame_boundary", True)
    setp(an, "import_bone_tracks", True)
    setp(an, "import_custom_attribute", False)
    setp(an, "import_meshes_in_bone_hierarchy", True)
    setp(an, "remove_redundant_keys", False)
    setp(an, "convert_scene", True)
    setp(an, "force_front_x_axis", False)
    return o


def step_body(who, fbx_name, clips):
    t0 = time.time()
    folder = "%s/%s" % (DST, who.capitalize())
    stem = os.path.splitext(fbx_name)[0]
    fbx = os.path.join(SRC, fbx_name)
    mesh = unreal.load_asset(asset_path(folder, stem)) if exists(folder, stem) else None
    if FORCE or mesh is None or mesh.get_editor_property("skeleton") is None:
        # (a mesh whose skeleton asset was never saved comes back without one: import again)
        for sub in (folder + "/Anims", folder):
            for a in list_assets(sub):
                eal.delete_asset(a.get_path_name())
        import_tasks([fbx], folder, mesh_options())
        eal.save_directory(folder, only_if_is_dirty=False, recursive=True)
    mesh = unreal.load_asset(asset_path(folder, stem)) if exists(folder, stem) else None
    if mesh is None:
        meshes = list_assets(folder, unreal.SkeletalMesh)
        mesh = meshes[0] if meshes else None
    info = {"mesh": mesh.get_path_name() if mesh else None, "seconds": 0}
    anims = []
    if mesh is not None:
        skeleton = mesh.get_editor_property("skeleton")
        anim_folder = folder + "/Anims"
        # the motion: from the per-frame tracks Unity sampled, not from the FBX takes (their translations read as zero)
        anims = mishi_anim.build(who, os.path.join(SRC, who + "_anim"), skeleton, mesh, anim_folder, FORCE, warn)
        keep = {a.get_name() for a in anims}
        for a in list_assets(anim_folder, unreal.AnimSequence):
            if a.get_name() not in keep:
                eal.delete_asset(a.get_path_name())
        got = {a.get_name(): round(a.get_play_length(), 3) for a in anims}
        missing = [c for c in clips if not any(n == c or n.endswith("_" + c) for n in got)]
        if missing:
            warn("%s: no animation for %s" % (who, missing))
        try:
            b = mesh.get_bounds()
            info["bounds_origin_cm"] = [round(b.origin.x, 1), round(b.origin.y, 1), round(b.origin.z, 1)]
            info["bounds_extent_cm"] = [round(b.box_extent.x, 1), round(b.box_extent.y, 1), round(b.box_extent.z, 1)]
        except Exception as e:
            warn("%s bounds: %s" % (who, e))
        try:
            info["morph_targets"] = [str(n) for n in mesh.get_all_morph_target_names()]
        except Exception as e:
            warn("%s morph targets: %s" % (who, e))
        info["materials"] = slot_names(mesh)
        info["anims"] = got
    info["seconds"] = round(time.time() - t0, 1)
    report["steps"][who] = info
    log("%s: mesh %s, %d anims" % (who, info["mesh"], len(anims)))
    return mesh, anims


def load_body(who):
    folder = "%s/%s" % (DST, who.capitalize())
    meshes = list_assets(folder, unreal.SkeletalMesh)
    return (meshes[0] if meshes else None), list_assets(folder + "/Anims", unreal.AnimSequence)


# ---------------------------------------------------------------------------------------------------------------- room meshes
def static_options(combine):
    o = unreal.FbxImportUI()
    setp(o, "import_mesh", True)
    setp(o, "import_as_skeletal", False)
    setp(o, "mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    setp(o, "import_materials", False)
    setp(o, "import_textures", False)
    setp(o, "import_animations", False)
    setp(o, "automated_import_should_detect_type", False)
    sm = o.get_editor_property("static_mesh_import_data")
    setp(sm, "combine_meshes", combine)
    setp(sm, "auto_generate_collision", False)
    setp(sm, "generate_lightmap_u_vs", False)
    setp(sm, "convert_scene", True)
    setp(sm, "force_front_x_axis", False)
    setp(sm, "transform_vertex_to_absolute", True)
    setp(sm, "normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    return o


def step_room():
    t0 = time.time()
    folder = DST + "/Room"
    if FORCE or not list_assets(folder, unreal.StaticMesh):
        import_tasks([os.path.join(SRC, "room_meshes.fbx")], folder, static_options(False))
    check_folder = DST + "/RoomCheck"
    if FORCE or not list_assets(check_folder, unreal.StaticMesh):
        import_tasks([os.path.join(SRC, "room.fbx")], check_folder, static_options(True))
    meshes, check = load_room()
    report["steps"]["room"] = {"meshes": len(meshes), "check_mesh": check.get_path_name() if check else None, "seconds": round(time.time() - t0, 1)}
    log("room: %d static meshes" % len(meshes))
    return meshes, check


def load_room():
    meshes = {m.get_name(): m for m in list_assets(DST + "/Room", unreal.StaticMesh)}
    check = list_assets(DST + "/RoomCheck", unreal.StaticMesh)
    return meshes, (check[0] if check else None)


def find_mesh(meshes, node):
    if node in meshes:
        return meshes[node]
    for name, m in meshes.items():
        if name.endswith("_" + node):
            return m
    return None


def slot_names(mesh):
    if isinstance(mesh, unreal.SkeletalMesh):
        return [str(m.get_editor_property("material_slot_name")) for m in mesh.get_editor_property("materials")]
    return [str(m.get_editor_property("material_slot_name")) for m in mesh.get_editor_property("static_materials")]


# ---------------------------------------------------------------------------------------------------------------- materials
MALE_BODY_SLOT = "MaleBody"          # the Unity project's stand-in for the game's pc_a00_UnlitSilhouette


def step_materials(slice_data, room_materials, her, him):
    """Returns ({material name: instance}, extras).  Character slots take the game's own definition when the cache has it."""
    t0 = time.time()
    defaults = default_textures()
    masters = mishi_materials.build_masters(defaults, force=FORCE and "materials" in STEPS and len(STEPS) == 1)
    game = game_materials(slice_data)

    # what every material needs, so the textures can be brought in first
    defs = {}
    for name, m in room_materials.items():
        tex = {slot: os.path.splitext(f)[0] for slot, f in m.get("textures", {}).items()}
        defs[name] = {"source": "unity", "who": m.get("used_by", "room"), "shader": m.get("shader", ""), "textures": tex,
                      "tiling": m.get("tiling", {}), "floats": m.get("floats", {}), "colors": m.get("colors", {}),
                      "keywords": m.get("keywords", []), "transparent": m.get("transparent", False), "alpha_clip": m.get("alpha_clip", False)}
    used = set()
    for mesh in (her, him):
        if mesh is not None:
            used.update(slot_names(mesh))
    for slot in used:
        if slot in game:
            defs[slot] = game[slot]
    # the man: the game's flat silhouette, and his own skin for those who would rather see him
    for extra in ("pc_a00_UnlitSilhouette", "pc_a00_nk_body"):
        if extra in game and MALE_BODY_SLOT in used:
            defs[extra] = game[extra]

    room_tex, game_tex = {}, {}
    for name, d in defs.items():
        for slot, tname in d["textures"].items():
            if d["source"] == "unity":
                f = os.path.join(SRC, "textures", tname + ".png")
                if not os.path.isfile(f):
                    alt = [e for e in (".jpg", ".tga", ".jpeg") if os.path.isfile(os.path.join(SRC, "textures", tname + e))]
                    f = os.path.join(SRC, "textures", tname + (alt[0] if alt else ".png"))
                room_tex.setdefault(tname, (f, role_of(slot)))
            else:
                game_tex.setdefault(tname, (cache_texture_file(tname, slot), role_of(slot)))
    textures, n1 = import_textures(room_tex, DST + "/Textures")
    gtextures, n2 = import_textures(game_tex, "/Game/Mishi/Characters/Textures", character=True)
    report["steps"]["textures"] = {"room": len(textures), "characters": len(gtextures), "imported": n1 + n2}
    log("textures: %d room + %d character (%d imported)" % (len(textures), len(gtextures), n1 + n2))

    instances = {}
    kinds = {}
    for name, d in defs.items():
        lookup = gtextures if d["source"] != "unity" else textures
        folder = "/Game/Mishi/Characters/Materials" if d["source"] != "unity" else DST + "/Materials"
        mi, kind = mishi_materials.make_instance(name, d, lookup, masters, folder)
        instances[name] = mi
        kinds[kind] = kinds.get(kind, 0) + 1
    report["steps"]["materials"] = {"instances": len(instances), "kinds": kinds, "from_game": sorted(n for n, d in defs.items() if d["source"] != "unity"),
                                    "seconds": round(time.time() - t0, 1)}
    log("materials: %d instances %s in %.0f s" % (len(instances), kinds, time.time() - t0))
    return instances, masters


def male_style_material(instances, style):
    if style == "silhouette":
        return instances.get("pc_a00_UnlitSilhouette")
    return instances.get("pc_a00_nk_body") or instances.get("pc_a00_UnlitSilhouette")


def assign_skeletal(mesh, instances, male_style="skin"):
    mats = []
    missing = []
    for m in mesh.get_editor_property("materials"):          # (each element comes out as a copy: collect the changed copies)
        slot = str(m.get_editor_property("material_slot_name"))
        mi = male_style_material(instances, male_style) if slot == MALE_BODY_SLOT else instances.get(slot)
        if mi is None:
            missing.append(slot)
        else:
            m.set_editor_property("material_interface", mi)
        mats.append(m)
    mesh.set_editor_property("materials", mats)
    eal.save_loaded_asset(mesh)
    if missing:
        warn("%s: no material for slots %s" % (mesh.get_name(), missing))


def assign_static(mesh, instances):
    missing = []
    # the camera's wall check traces against the meshes' own triangles (they come without collision shapes)
    body = mesh.get_editor_property("body_setup")
    if body is not None and body.get_editor_property("collision_trace_flag") != unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE:
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        mesh.modify()
    for i, slot in enumerate(slot_names(mesh)):
        mi = instances.get(slot)
        if mi is None:
            missing.append(slot)
            continue
        if mesh.get_material(i) != mi:
            mesh.set_material(i, mi)
    eal.save_loaded_asset(mesh, only_if_is_dirty=True)
    return missing


# ---------------------------------------------------------------------------------------------------------------- main
def main():
    t0 = time.time()
    unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX 0")
    with open(os.path.join(SRC, "slice.json"), encoding="utf-8") as f:
        slice_text = f.read()
    slice_data = json.loads(slice_text)
    with open(os.path.join(SRC, "materials.json"), encoding="utf-8") as f:
        materials = json.load(f)
    with open(os.path.join(SRC, "room_instances.json"), encoding="utf-8") as f:
        placements = json.load(f)["placements"]
    log("slice %s: %s, %d parts, %d placements, %d materials; steps %s%s" % (
        SLICE, slice_data.get("title"), len(slice_data["parts"]), len(placements), len(materials), ",".join(STEPS), " (force)" if FORCE else ""))

    sounds = step_audio(slice_data) if "audio" in STEPS else load_sounds()
    clips_f = sorted({p["female_clip"] for p in slice_data["parts"] if p.get("female_clip")})
    clips_m = sorted({p["male_clip"] for p in slice_data["parts"] if p.get("male_clip")})
    has_him = bool((slice_data.get("male") or {}).get("ok", True)) and os.path.isfile(os.path.join(SRC, "male.fbx"))
    if "bodies" in STEPS:
        her, her_anims = step_body("female", "female.fbx", clips_f)
        him, his_anims = step_body("male", "male.fbx", clips_m) if has_him else (None, [])
    else:
        her, her_anims = load_body("female")
        him, his_anims = load_body("male") if has_him else (None, [])
    meshes, check_mesh = step_room() if "room" in STEPS else load_room()

    instances, masters = {}, {}
    if "materials" in STEPS or "textures" in STEPS or "level" in STEPS:
        instances, masters = step_materials(slice_data, materials, her, him)
        if her is not None:
            assign_skeletal(her, instances)
        if him is not None:
            assign_skeletal(him, instances)
        room_missing = set()
        for m in meshes.values():
            room_missing.update(assign_static(m, instances))
        if room_missing:
            warn("room slots without a material: %s" % sorted(room_missing)[:10])

    # the skills' effects: their materials (the level hands them to the couple)
    fx_materials = []
    if "effects" in STEPS:
        fx_materials = mishi_fx.step(SRC, DST, default_textures(), import_textures, warn, force=FORCE and len(STEPS) == 1)
        report["steps"]["effects"] = {"materials": len(fx_materials)}
    elif "level" in STEPS:
        fx_materials = mishi_fx.load(DST)

    if "level" in STEPS:
        info = mishi_look.build_level(MAP, SLICE, slice_text, slice_data, placements, meshes, instances, masters, her, her_anims, him, his_anims,
                                      sounds, check_mesh, warn, SRC, fx_materials)
        report["steps"]["level"] = info
    eal.save_directory("/Game/Mishi", only_if_is_dirty=True, recursive=True)
    report["seconds"] = round(time.time() - t0, 1)
    log("done in %.0f s, %d warnings" % (time.time() - t0, len(report["warnings"])))


try:
    main()
except Exception:
    report["error"] = traceback.format_exc()
    unreal.log_error("[MISHI] import failed: " + traceback.format_exc())
finally:
    try:
        with open(os.path.join(SRC, "ue_import_report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    if QUIT:
        unreal.SystemLibrary.quit_editor()
