"""Mishi UE5: bring one slice exported by Unity (Import/<scene>_<room>/, MishiUeExport.ExportSlice) into the project.

    UnrealEditor.exe MishiUE.uproject -ExecutePythonScript="Tools/import_slice.py eros15_07 --quit"
    (or in the editor's Python console:  py Tools/import_slice.py eros15_07)

Steps (each one reuses what an earlier run made unless --force):
  textures   textures/*.png -> /Game/Mishi/<slice>/Textures; normal maps (OpenGL green -> flipped), masks linear (TC_Masks)
  audio      audio/*.ogg -> WAV (ffmpeg) -> /Game/Mishi/<slice>/Audio; the room's music loops
  bodies     female.fbx / male.fbx -> skeletal meshes with morph targets + every take as an AnimSequence
  room       room_meshes.fbx -> one static mesh per distinct mesh (RM_*); room.fbx (whole room, combined) for the space check
  materials  master materials /Game/Mishi/Materials/M_Mishi_* (made once) + an instance per Unity material (materials.json)
  level      /Game/Mishi/Maps/<slice>: the room's 683 placements, its lights, a sky light, a post-process volume, the couple
  check      the placed room has to cover room.fbx: the Unity -> Unreal space map (MishiUE.h) proven on every import
Writes Import/<slice>/ue_import_report.json.
"""
import json
import math
import os
import struct
import subprocess
import sys
import time
import zlib

import unreal

FFMPEG = r"D:\Program Files\ffmpeg\bin\ffmpeg.exe"
LIGHT_SCALE = math.pi        # URP light intensity -> lux / candela (URP's diffuse has no 1/pi, Unreal's has)

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
    except Exception as e:  # a property that moved between engine versions: say so, go on
        warn("%s.%s: %s" % (obj.get_class().get_name(), name, e))


# ---------------------------------------------------------------------------------------------------------------- arguments
def parse_args():
    """Arguments after the script, or (what Tools/ue.ps1 uses: -ExecutePythonScript takes a bare path best) MISHI_SLICE,
    MISHI_FORCE=1, MISHI_QUIT=1 in the environment."""
    args = [a for a in sys.argv[1:] if not a.lower().endswith(".py")]
    slice_name = next((a for a in args if not a.startswith("--")), os.environ.get("MISHI_SLICE", "eros15_07"))
    force = "--force" in args or os.environ.get("MISHI_FORCE") == "1"
    quit_after = "--quit" in args or os.environ.get("MISHI_QUIT") == "1"
    return slice_name, force, quit_after


SLICE, FORCE, QUIT = parse_args()
PROJECT = os.path.abspath(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
SRC = os.path.join(PROJECT, "Import", SLICE)
DST = "/Game/Mishi/" + SLICE
MATS = "/Game/Mishi/Materials"
MAP = "/Game/Mishi/Maps/" + SLICE


# ---------------------------------------------------------------------------------------------------------------- Unity -> Unreal
# Unity (m, left-handed, Y up) -> what Unreal's FBX import makes of the Unity FBX Exporter's files: (-x, z, y) * 100 (see MishiUE.h)
def ue_pos(p):
    return unreal.Vector(-p[0] * 100.0, p[2] * 100.0, p[1] * 100.0)


def ue_dir(d):
    return unreal.Vector(-d[0], d[2], d[1])


def ue_quat(q):
    return unreal.Quat(-q[0], q[2], q[1], q[3])


def ue_scale(s):
    return unreal.Vector(s[0], s[2], s[1])


def unity_rotate(q, v):
    """v rotated by the Unity quaternion q (x, y, z, w) - plain Hamilton algebra, as Unity does it."""
    x, y, z, w = q
    vx, vy, vz = v
    # t = 2 * cross(q.xyz, v); v' = v + w * t + cross(q.xyz, t)
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty), vy + w * ty + (z * tx - x * tz), vz + w * tz + (x * ty - y * tx))


# ---------------------------------------------------------------------------------------------------------------- import helpers
def import_tasks(files, dest, options=None):
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", dest)
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
NORMAL_PROPS = {"_BumpMap", "_DetailNormalMap", "_NormalMap"}
MASK_PROPS = {"_MetallicGlossMap", "_MaskMap", "_OcclusionMap", "_SkinLutMap"}


def texture_roles(materials):
    roles = {}
    for m in materials.values():
        for prop, file in m.get("textures", {}).items():
            stem = os.path.splitext(file)[0]
            role = "normal" if prop in NORMAL_PROPS else "mask" if prop in MASK_PROPS else "color"
            roles.setdefault(stem, role)
    return roles


def set_texture_role(tex, role):
    if role == "normal":
        setp(tex, "compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        setp(tex, "srgb", False)
        setp(tex, "flip_green_channel", True)      # Unity's normal maps are OpenGL style (green up), Unreal's DirectX
    elif role == "mask":
        setp(tex, "compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        setp(tex, "srgb", False)
    eal.save_loaded_asset(tex)


def step_textures(materials):
    t0 = time.time()
    folder = DST + "/Textures"
    src = os.path.join(SRC, "textures")
    files = sorted(os.path.join(src, f) for f in os.listdir(src) if f.lower().endswith((".png", ".tga", ".jpg", ".jpeg")))
    todo = [f for f in files if FORCE or not exists(folder, os.path.splitext(os.path.basename(f))[0])]
    import_tasks(todo, folder)
    roles = texture_roles(materials)
    textures = {}
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]
        tex = unreal.load_asset(asset_path(folder, stem))
        if tex is None:
            warn("texture %s did not import" % stem)
            continue
        textures[stem] = tex
        if os.path.join(src, os.path.basename(f)) in todo or FORCE:
            set_texture_role(tex, roles.get(stem, "color"))
    report["steps"]["textures"] = {"files": len(files), "imported": len(todo), "seconds": round(time.time() - t0, 1)}
    log("textures: %d (%d imported) in %.0f s" % (len(files), len(todo), time.time() - t0))
    return textures


def default_textures():
    """Our own 4x4 white (colour), white (linear mask), black and flat-normal textures: the masters' parameter defaults, each with
    the sampler type its parameter has (the engine's white square is sRGB and would not do as a mask default)."""
    folder = MATS + "/Defaults"
    tmp = os.path.join(PROJECT, "Saved", "MishiDefaults")
    os.makedirs(tmp, exist_ok=True)
    want = {"T_Mishi_White": ((255, 255, 255, 255), "color"), "T_Mishi_Black": ((0, 0, 0, 255), "color"),
            "T_Mishi_MaskWhite": ((255, 255, 255, 255), "mask"), "T_Mishi_FlatNormal": ((128, 128, 255, 255), "normal")}
    out = {}
    for name, (rgba, role) in want.items():
        if not exists(folder, name):
            path = os.path.join(tmp, name + ".png")
            write_png(path, 4, 4, rgba)
            import_tasks([path], folder)
            tex = unreal.load_asset(asset_path(folder, name))
            if role == "normal":
                setp(tex, "compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
                setp(tex, "srgb", False)
            elif role == "mask":
                setp(tex, "compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
                setp(tex, "srgb", False)
            eal.save_loaded_asset(tex)
        out[name] = unreal.load_asset(asset_path(folder, name))
    return out


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
        wav = os.path.join(wav_dir, stem + ".wav")
        if ext.lower() == ".wav":
            wav = os.path.join(src, f)
        elif not os.path.exists(wav):
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", os.path.join(src, f), "-acodec", "pcm_s16le", wav], check=False)
        if os.path.exists(wav):
            wavs.append(wav)
        else:
            warn("audio %s: no WAV" % f)
    todo = [w for w in wavs if FORCE or not exists(folder, os.path.splitext(os.path.basename(w))[0])]
    import_tasks(todo, folder)
    sounds = list_assets(folder, unreal.SoundWave)
    music = os.path.splitext((slice_data.get("music") or {}).get("file") or "")[0]
    for s in sounds:
        if s.get_name() == music:
            setp(s, "looping", True)
            eal.save_loaded_asset(s)
    report["steps"]["audio"] = {"sounds": len(sounds), "imported": len(todo), "music": music, "seconds": round(time.time() - t0, 1)}
    log("audio: %d sounds (%d imported), music %s" % (len(sounds), len(todo), music))
    return sounds


# ---------------------------------------------------------------------------------------------------------------- bodies
def skeletal_options():
    o = unreal.FbxImportUI()
    setp(o, "import_mesh", True)
    setp(o, "import_as_skeletal", True)
    setp(o, "mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    setp(o, "import_animations", True)
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
    an = o.get_editor_property("anim_sequence_import_data")
    setp(an, "animation_length", unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    setp(an, "import_bone_tracks", True)
    setp(an, "import_custom_attribute", True)
    setp(an, "remove_redundant_keys", False)
    setp(an, "do_not_import_curve_with_zero", False)
    setp(an, "import_meshes_in_bone_hierarchy", True)
    return o


def step_body(who, fbx_name):
    t0 = time.time()
    folder = "%s/%s" % (DST, who.capitalize())
    stem = os.path.splitext(fbx_name)[0]
    if FORCE or not exists(folder, stem):
        import_tasks([os.path.join(SRC, fbx_name)], folder, skeletal_options())
    mesh = unreal.load_asset(asset_path(folder, stem))
    if mesh is None:
        meshes = list_assets(folder, unreal.SkeletalMesh)
        mesh = meshes[0] if meshes else None
    anims = list_assets(folder, unreal.AnimSequence)
    info = {"mesh": mesh.get_path_name() if mesh else None, "anims": [a.get_name() for a in anims], "seconds": round(time.time() - t0, 1)}
    if mesh is not None:
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
    report["steps"][who] = info
    log("%s: mesh %s, %d anims, %s" % (who, info["mesh"], len(anims), info.get("bounds_extent_cm")))
    return mesh, anims


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
    meshes = {m.get_name(): m for m in list_assets(folder, unreal.StaticMesh)}
    check_folder = DST + "/RoomCheck"
    if FORCE or not list_assets(check_folder, unreal.StaticMesh):
        import_tasks([os.path.join(SRC, "room.fbx")], check_folder, static_options(True))
    check = list_assets(check_folder, unreal.StaticMesh)
    report["steps"]["room"] = {"meshes": len(meshes), "check_mesh": check[0].get_path_name() if check else None, "seconds": round(time.time() - t0, 1)}
    log("room: %d static meshes in %.0f s" % (len(meshes), time.time() - t0))
    return meshes, (check[0] if check else None)


def find_mesh(meshes, node):
    if node in meshes:
        return meshes[node]
    for name, m in meshes.items():
        if name.endswith("_" + node) or name.endswith(node):
            return m
    return None


# ---------------------------------------------------------------------------------------------------------------- materials
def new_material(name):
    path = "%s/%s" % (MATS, name)
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    return asset_tools.create_asset(name, MATS, unreal.Material, unreal.MaterialFactoryNew())


def tex_param(mat, name, default, sampler, x, y):
    node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
    setp(node, "parameter_name", name)
    setp(node, "texture", default)
    setp(node, "sampler_type", sampler)
    return node


def scalar_param(mat, name, value, x, y):
    node = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, x, y)
    setp(node, "parameter_name", name)
    setp(node, "default_value", value)
    return node


def vector_param(mat, name, value, x, y):
    node = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, x, y)
    setp(node, "parameter_name", name)
    setp(node, "default_value", value)
    return node


def op(mat, cls, a, a_out, b, b_out, x, y):
    node = mel.create_material_expression(mat, cls, x, y)
    mel.connect_material_expressions(a, a_out, node, "A")
    mel.connect_material_expressions(b, b_out, node, "B")
    return node


def build_master(name, kind, defaults):
    """kind: lit / masked / translucent / skin / hair / eye / unlit / hidden"""
    mat = new_material(name)
    S = unreal.MaterialSamplerType
    white, black, mask_white, flat = defaults["T_Mishi_White"], defaults["T_Mishi_Black"], defaults["T_Mishi_MaskWhite"], defaults["T_Mishi_FlatNormal"]
    MP = unreal.MaterialProperty
    if kind == "hidden":
        setp(mat, "blend_mode", unreal.BlendMode.BLEND_MASKED)
        zero = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -300, 200)
        setp(zero, "r", 0.0)
        mel.connect_material_property(zero, "", MP.MP_OPACITY_MASK)
        mel.recompile_material(mat)
        return mat
    base = tex_param(mat, "BaseMap", white, S.SAMPLERTYPE_COLOR, -1200, -300)
    tint = vector_param(mat, "BaseColor", unreal.LinearColor(1, 1, 1, 1), -1200, -60)
    col = op(mat, unreal.MaterialExpressionMultiply, base, "RGB", tint, "", -900, -250)
    if kind == "unlit":
        setp(mat, "shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
        mel.connect_material_property(col, "", MP.MP_EMISSIVE_COLOR)
        mel.recompile_material(mat)
        return mat
    mel.connect_material_property(col, "", MP.MP_BASE_COLOR)
    normal = tex_param(mat, "NormalMap", flat, S.SAMPLERTYPE_NORMAL, -1200, 200)
    mel.connect_material_property(normal, "RGB", MP.MP_NORMAL)
    mga = tex_param(mat, "MaskMap", mask_white, S.SAMPLERTYPE_MASKS, -1200, 480)
    metal = scalar_param(mat, "Metallic", 0.0, -900, 420)
    smooth = scalar_param(mat, "Smoothness", 0.5, -900, 560)
    m_out = op(mat, unreal.MaterialExpressionMultiply, mga, "R", metal, "", -650, 420)
    g = op(mat, unreal.MaterialExpressionMultiply, mga, "G", smooth, "", -650, 560)
    rough = mel.create_material_expression(mat, unreal.MaterialExpressionOneMinus, -450, 560)
    mel.connect_material_expressions(g, "", rough, "")
    mel.connect_material_property(m_out, "", MP.MP_METALLIC)
    mel.connect_material_property(rough, "", MP.MP_ROUGHNESS)
    mel.connect_material_property(mga, "B", MP.MP_AMBIENT_OCCLUSION)
    # emission (rooms: lamps, candles)
    emis = tex_param(mat, "EmissionMap", black, S.SAMPLERTYPE_COLOR, -1200, 800)
    emis_col = vector_param(mat, "EmissionColor", unreal.LinearColor(0, 0, 0, 1), -1200, 1040)
    e = op(mat, unreal.MaterialExpressionMultiply, emis, "RGB", emis_col, "", -900, 850)
    mel.connect_material_property(e, "", MP.MP_EMISSIVE_COLOR)
    alpha = op(mat, unreal.MaterialExpressionMultiply, base, "A", tint, "A", -900, -60)
    if kind in ("masked", "hair"):
        setp(mat, "blend_mode", unreal.BlendMode.BLEND_MASKED)
        setp(mat, "two_sided", True)
        cut = scalar_param(mat, "Cutoff", 0.5, -900, 80)
        # (alpha - cutoff) + 0.5 against the fixed clip value 0.5: each instance keeps the Unity material's own cutoff
        d = op(mat, unreal.MaterialExpressionSubtract, alpha, "", cut, "", -650, 0)
        half = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -650, 120)
        setp(half, "r", 0.5)
        m = op(mat, unreal.MaterialExpressionAdd, d, "", half, "", -450, 40)
        mel.connect_material_property(m, "", MP.MP_OPACITY_MASK)
    elif kind == "translucent":
        setp(mat, "blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
        setp(mat, "two_sided", True)
        setp(mat, "translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_FORWARD_SHADING)
        mel.connect_material_property(alpha, "", MP.MP_OPACITY)
    elif kind == "skin":
        setp(mat, "shading_model", unreal.MaterialShadingModel.MSM_SUBSURFACE_PROFILE)
        scatter = scalar_param(mat, "Scatter", 1.0, -650, 700)
        mel.connect_material_property(scatter, "", MP.MP_OPACITY)    # subsurface profile: opacity = how much the skin scatters
    elif kind == "eye":
        setp(mat, "shading_model", unreal.MaterialShadingModel.MSM_CLEAR_COAT)
        coat = scalar_param(mat, "ClearCoat", 1.0, -650, 700)
        coat_rough = scalar_param(mat, "ClearCoatRoughness", 0.03, -650, 800)
        mel.connect_material_property(coat, "", MP.MP_CUSTOM_DATA0)
        mel.connect_material_property(coat_rough, "", MP.MP_CUSTOM_DATA1)
    if kind == "hair":
        setp(mat, "shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat)
    return mat


MASTER_KINDS = {"M_Mishi_Lit": "lit", "M_Mishi_Masked": "masked", "M_Mishi_Translucent": "translucent", "M_Mishi_Skin": "skin",
                "M_Mishi_Hair": "hair", "M_Mishi_Eye": "eye", "M_Mishi_Unlit": "unlit", "M_Mishi_Hidden": "hidden"}


def masters(defaults):
    out = {}
    for name, kind in MASTER_KINDS.items():
        if FORCE or not exists(MATS, name):
            build_master(name, kind, defaults)
        out[kind] = unreal.load_asset(asset_path(MATS, name))
    return out


def master_for(m):
    shader = m.get("shader", "")
    kind = m.get("kind", "")
    if "Particles" in shader or kind == "liquid":
        return "hidden"                      # the Effect layer is not in the FBX; its liquids come later
    if shader.endswith("/Unlit") or shader == "Universal Render Pipeline/Unlit":
        return "unlit"
    if kind == "skin":
        return "skin"
    if kind == "eye":
        return "eye"
    if kind == "hair":
        return "hair"
    if kind == "lash":
        return "masked"
    if m.get("transparent"):
        return "translucent"
    if m.get("alpha_clip"):
        return "masked"
    return "lit"


def step_materials(materials, textures, defaults):
    t0 = time.time()
    folder = DST + "/Materials"
    parents = masters(defaults)
    out = {}
    for name, m in materials.items():
        kind = master_for(m)
        inst_name = "MI_" + name
        path = "%s/%s" % (folder, inst_name)
        mi = unreal.load_asset(path) if eal.does_asset_exist(path) else \
            asset_tools.create_asset(inst_name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, parents[kind])
        tx = m.get("textures", {})

        def tex(prop):
            return textures.get(os.path.splitext(tx[prop])[0]) if prop in tx else None

        base = tex("_BaseMap") or tex("_IrisAlbedoTex") or tex("_MainTex")
        if base is not None:
            mel.set_material_instance_texture_parameter_value(mi, "BaseMap", base)
        normal = tex("_BumpMap")
        if normal is not None and kind not in ("unlit", "hidden"):
            mel.set_material_instance_texture_parameter_value(mi, "NormalMap", normal)
        mask = tex("_MetallicGlossMap")
        if mask is not None and kind not in ("unlit", "hidden"):
            mel.set_material_instance_texture_parameter_value(mi, "MaskMap", mask)
        emis = tex("_EmissionMap")
        cols = m.get("colors", {})
        if emis is not None and kind not in ("unlit", "hidden"):
            mel.set_material_instance_texture_parameter_value(mi, "EmissionMap", emis)
            e = cols.get("_EmissionColor", [0, 0, 0, 1])
            mel.set_material_instance_vector_parameter_value(mi, "EmissionColor", unreal.LinearColor(e[0], e[1], e[2], 1))
        c = cols.get("_BaseColor") or cols.get("_Color") or cols.get("_IrisColor")
        if c is not None:
            mel.set_material_instance_vector_parameter_value(mi, "BaseColor", unreal.LinearColor(c[0], c[1], c[2], c[3]))
        fl = m.get("floats", {})
        if kind not in ("unlit", "hidden"):
            if "_Metallic" in fl:
                mel.set_material_instance_scalar_parameter_value(mi, "Metallic", fl["_Metallic"])
            if "_Smoothness" in fl:
                mel.set_material_instance_scalar_parameter_value(mi, "Smoothness", fl["_Smoothness"])
        if kind in ("masked", "hair"):
            mel.set_material_instance_scalar_parameter_value(mi, "Cutoff", fl.get("_Cutoff", 0.5) if kind == "hair" or m.get("alpha_clip") else 0.35)
        eal.save_loaded_asset(mi)
        out[name] = mi
    report["steps"]["materials"] = {"instances": len(out), "seconds": round(time.time() - t0, 1),
                                    "kinds": {k: sum(1 for m in materials.values() if master_for(m) == k) for k in MASTER_KINDS.values()}}
    log("materials: %d instances in %.0f s" % (len(out), time.time() - t0))
    return out


def slot_names(mesh):
    if isinstance(mesh, unreal.SkeletalMesh):
        return [str(m.get_editor_property("material_slot_name")) for m in mesh.get_editor_property("materials")]
    return [str(m.get_editor_property("material_slot_name")) for m in mesh.get_editor_property("static_materials")]


def match_material(slot, instances):
    if slot in instances:
        return instances[slot]
    low = slot.lower()
    for name, mi in instances.items():
        n = name.lower()
        if low == n or low.startswith(n) or n.startswith(low):
            return mi
    return None


def assign_skeletal(mesh, instances):
    mats = mesh.get_editor_property("materials")
    missing = []
    for m in mats:
        slot = str(m.get_editor_property("material_slot_name"))
        mi = match_material(slot, instances)
        if mi is None:
            missing.append(slot)
            continue
        m.set_editor_property("material_interface", mi)
    mesh.set_editor_property("materials", mats)
    eal.save_loaded_asset(mesh)
    if missing:
        warn("%s: no material for slots %s" % (mesh.get_name(), missing))


def assign_static(mesh, instances):
    missing = []
    for i, slot in enumerate(slot_names(mesh)):
        mi = match_material(slot, instances)
        if mi is None:
            missing.append(slot)
            continue
        mesh.set_material(i, mi)
    eal.save_loaded_asset(mesh)
    return missing


# ---------------------------------------------------------------------------------------------------------------- level
def open_level():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if eal.does_asset_exist(MAP):
        les.load_level(MAP)
    else:
        try:
            les.new_level(MAP, False)
        except TypeError:
            les.new_level(MAP)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if a.get_folder_path() and str(a.get_folder_path()).startswith("Mishi"):
            eas.destroy_actor(a)
    return les, eas


def spawn(eas, cls, loc, rot, label, folder):
    a = eas.spawn_actor_from_class(cls, loc, rot)
    a.set_actor_label(label)
    a.set_folder_path(folder)
    return a


def place_room(eas, meshes, instances, placements):
    placed, missing = 0, set()
    for p in placements:
        mesh = find_mesh(meshes, p["mesh"])
        if mesh is None:
            missing.add(p["mesh"])
            continue
        rot = ue_quat(p["rotation"]).rotator()
        a = spawn(eas, unreal.StaticMeshActor, ue_pos(p["position"]), rot, p["name"], "Mishi/Room")
        comp = a.get_editor_property("static_mesh_component")
        comp.set_static_mesh(mesh)
        a.set_actor_scale3d(ue_scale(p["scale"]))
        for i, mname in enumerate(p.get("materials", [])):
            mi = instances.get(mname) if mname else None
            if mi is not None:
                comp.set_material(i, mi)
        placed += 1
    if missing:
        warn("room: no mesh for %d nodes, e.g. %s" % (len(missing), sorted(missing)[:5]))
    return placed


def place_lights(eas, lights):
    n = 0
    for L in lights:
        pos = ue_pos(L["position"])
        fwd = ue_dir(unity_rotate(L["rotation"], (0.0, 0.0, 1.0)))     # a Unity light shines along its +Z, an Unreal one along +X
        rot = unreal.MathLibrary.make_rot_from_x(fwd)
        kind = L.get("type", "Point")
        color = unreal.LinearColor(L["color"][0], L["color"][1], L["color"][2], 1.0)
        intensity = L["intensity"] * LIGHT_SCALE
        if kind == "Directional":
            a = spawn(eas, unreal.DirectionalLight, pos, rot, L["name"], "Mishi/Lights")
            c = a.get_component_by_class(unreal.DirectionalLightComponent)
            setp(c, "intensity", intensity)
        elif kind == "Spot":
            a = spawn(eas, unreal.SpotLight, pos, rot, L["name"], "Mishi/Lights")
            c = a.get_component_by_class(unreal.SpotLightComponent)
            setp(c, "intensity_units", unreal.LightUnits.CANDELAS)
            setp(c, "intensity", intensity)
            setp(c, "attenuation_radius", L["range"] * 100.0)
            setp(c, "outer_cone_angle", L["spot_angle"] * 0.5)
            setp(c, "inner_cone_angle", L["spot_angle"] * 0.35)
            setp(c, "source_radius", 3.0)
        elif kind in ("Rectangle", "Area", "Disc"):
            a = spawn(eas, unreal.RectLight, pos, rot, L["name"], "Mishi/Lights")
            c = a.get_component_by_class(unreal.RectLightComponent)
            setp(c, "intensity_units", unreal.LightUnits.CANDELAS)
            setp(c, "intensity", intensity)
            setp(c, "attenuation_radius", L["range"] * 100.0)
            setp(c, "source_width", 120.0)
            setp(c, "source_height", 120.0)
        else:
            a = spawn(eas, unreal.PointLight, pos, rot, L["name"], "Mishi/Lights")
            c = a.get_component_by_class(unreal.PointLightComponent)
            setp(c, "intensity_units", unreal.LightUnits.CANDELAS)
            setp(c, "intensity", intensity)
            setp(c, "attenuation_radius", L["range"] * 100.0)
            setp(c, "source_radius", 2.0)
        c.set_mobility(unreal.ComponentMobility.MOVABLE)
        c.set_light_color(color, True)
        setp(c, "cast_shadows", bool(L.get("shadows", True)))
        n += 1
    return n


def place_environment(eas, post):
    sky = spawn(eas, unreal.SkyLight, unreal.Vector(0, 0, 300), unreal.Rotator(0, 0, 0), "SkyLight", "Mishi/Lights")
    sc = sky.get_component_by_class(unreal.SkyLightComponent)
    sc.set_mobility(unreal.ComponentMobility.MOVABLE)
    setp(sc, "real_time_capture", True)
    setp(sc, "intensity", 0.6)
    ppv = spawn(eas, unreal.PostProcessVolume, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), "Post", "Mishi/Lights")
    setp(ppv, "unbound", True)
    s = ppv.get_editor_property("settings")
    pairs = [("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL), ("auto_exposure_apply_physical_camera_exposure", False),
             ("auto_exposure_bias", 0.0), ("bloom_intensity", (post or {}).get("bloom_intensity", 0.6)),
             ("bloom_threshold", (post or {}).get("bloom_threshold", 0.55))]
    for k, v in pairs:
        try:
            s.set_editor_property("override_" + k, True)
        except Exception:
            pass
        setp(s, k, v)
    ppv.set_editor_property("settings", s)


def place_couple(eas, slice_text, slice_data, her, her_anims, him, his_anims, sounds):
    anchor = slice_data["anchor"]
    rot = ue_quat(anchor["rotation"]).rotator()
    a = spawn(eas, unreal.MishiCouple, ue_pos(anchor["position"]), rot, "Couple_" + slice_data.get("posture", SLICE), "Mishi")
    setp(a, "slice_json", slice_text)
    setp(a, "her_mesh", her)
    setp(a, "his_mesh", him)
    setp(a, "her_clips", her_anims)
    setp(a, "his_clips", his_anims)
    setp(a, "sounds", sounds)
    a.rerun_construction_scripts() if hasattr(a, "rerun_construction_scripts") else None
    return a


def world_bounds(actors):
    lo, hi = [1e18] * 3, [-1e18] * 3
    for a in actors:
        origin, ext = a.get_actor_bounds(False)
        for i, (o, e) in enumerate(((origin.x, ext.x), (origin.y, ext.y), (origin.z, ext.z))):
            lo[i] = min(lo[i], o - e)
            hi[i] = max(hi[i], o + e)
    return lo, hi


def space_check(eas, check_mesh, room_actors):
    """room.fbx, imported whole (its nodes baked at their world places by the FBX import), against the room placed from
    room_instances.json with the Unity -> Unreal map: the two boxes agree when the map is right (a mirrored axis moves the box)."""
    if check_mesh is None or not room_actors:
        warn("space check skipped")
        return None
    box = check_mesh.get_bounding_box()
    lo2, hi2 = [box.min.x, box.min.y, box.min.z], [box.max.x, box.max.y, box.max.z]
    lo, hi = world_bounds(room_actors)
    err = max(max(abs(a - b) for a, b in zip(lo, lo2)), max(abs(a - b) for a, b in zip(hi, hi2)))
    res = {"placed_min": [round(v, 1) for v in lo], "placed_max": [round(v, 1) for v in hi],
           "fbx_min": [round(v, 1) for v in lo2], "fbx_max": [round(v, 1) for v in hi2], "max_error_cm": round(err, 1), "ok": err < 25.0}
    report["steps"]["space_check"] = res
    (log if res["ok"] else warn)("space check: placed room vs room.fbx differ by %.1f cm at most (%s)" % (err, "OK" if res["ok"] else "WRONG MAP?"))
    return res


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
    log("slice %s: %s, %d parts, %d placements, %d materials" % (SLICE, slice_data.get("title"), len(slice_data["parts"]), len(placements), len(materials)))

    defaults = default_textures()
    textures = step_textures(materials)
    sounds = step_audio(slice_data)
    her, her_anims = step_body("female", "female.fbx")
    him, his_anims = step_body("male", "male.fbx")
    meshes, check_mesh = step_room()
    instances = step_materials(materials, textures, defaults)
    if her is not None:
        assign_skeletal(her, instances)
    if him is not None:
        assign_skeletal(him, instances)
    room_missing = set()
    for m in meshes.values():
        room_missing.update(assign_static(m, instances))
    if room_missing:
        warn("room slots without a material: %s" % sorted(room_missing)[:10])

    les, eas = open_level()
    placed = place_room(eas, meshes, instances, placements)
    lights = place_lights(eas, slice_data.get("lights", []))
    place_environment(eas, slice_data.get("post"))
    couple = place_couple(eas, slice_text, slice_data, her, her_anims, him, his_anims, sounds)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    try:
        ws = world.get_world_settings()
        setp(ws, "default_game_mode", unreal.MishiGameMode)
    except Exception as e:
        warn("world settings: %s" % e)
    room_actors = [a for a in eas.get_all_level_actors() if str(a.get_folder_path()) == "Mishi/Room"]
    space_check(eas, check_mesh, room_actors)
    les.save_current_level()
    eal.save_directory("/Game/Mishi", only_if_is_dirty=True, recursive=True)
    report["steps"]["level"] = {"map": MAP, "placed": placed, "lights": lights, "couple": couple.get_name() if couple else None}
    report["seconds"] = round(time.time() - t0, 1)
    with open(os.path.join(SRC, "ue_import_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    log("done in %.0f s: %d placements, %d lights, %d warnings -> %s" % (time.time() - t0, placed, lights, len(report["warnings"]), MAP))


try:
    main()
except Exception as e:
    import traceback
    report["error"] = traceback.format_exc()
    unreal.log_error("[MISHI] import failed: " + traceback.format_exc())
    try:
        with open(os.path.join(SRC, "ue_import_report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
finally:
    if QUIT:
        unreal.SystemLibrary.quit_editor()
