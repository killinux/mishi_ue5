"""Mishi UE5: the level of a slice - the room's placements, its lights, sky, fog and post-processing, the couple - and the numbers
that decide how it looks (LOOK), in one place so they can be turned without touching the import.

Everything the Unity export gives is in Unity's space; ue_pos / ue_quat / ue_scale put it into Unreal's (see MishiUE.h):
a Unity point (x, y, z) m lands at (-x, z, y) * 100 cm, a quaternion's vector part goes the same way.
"""
import math
import os

import unreal

LOOK = {
    # URP's light intensity -> lux (directional) / candela (the others): URP's diffuse has no 1/pi, Unreal's has
    "light_scale": math.pi,
    # the sun: the room's baked window light (the game bakes it into the lightmaps; here it is the one real sun)
    "sun_scale": 1.0,
    "sun_source_angle": 1.2,            # degrees: soft-edged window shadows
    "sun_shaft": 2.5,                   # volumetric scattering: the shafts through the window
    # the sun on skin: the bodies are on lighting channel 1 only, the sun on channel 0 - a twin of it on channel 1 gives them
    # this share of it.  The full sun is 2.7 x the key: it burnt every patch of skin it touched out to white.
    "sun_on_characters": 0.3,
    # the key on the couple: the game's real-time directional light (22 degrees up, from the window side).  A second sun would
    # be stopped by the walls and double every shadow: it becomes a soft box standing between the window and the bed.
    "key_scale": 0.85,
    "key_distance": 3.0,                # m from the couple, back along the light's direction
    "key_size": (1.8, 1.4),             # m
    "key_shaft": 0.3,
    # the baked sky panel under the ceiling, the bed fills, the lamps
    "panel_scale": 0.10,
    "fill_scale": 0.35,
    "lamp_scale": 1.5,
    "sky_intensity": 1.0,
    "exposure_bias": -1.1,
    "fog_density": 0.15,                # x 1/1000 per cm: a haze thick enough for the window light to show in the air of a 5 m room
    "fog_falloff": 0.05,
    "fog_scattering": 0.35,             # x the room's fog colour
    # Lumen on hardware ray tracing (r.RayTracing in the project): the rays hit the real triangles, the bodies' too.
    # "surface_cache": what a ray hits is lit from the surface cache - the bodies have none: they only shade (65 fps at
    # 1600x900 on the RTX 4090 laptop); "reflections": reflections light what they hit themselves - the bodies show in them
    # (51 fps); "hit": the bounce light does so too, skin colours the sheet next to it (45 fps).  Software Lumen: 46 fps, and
    # its bounce light is a third brighter than the path tracer's; these three agree with it.
    "lumen_ray_lighting": "reflections",
    "lumen_final_gather_quality": 2.0,
    "lumen_reflection_quality": 2.0,
    "lumen_scene_lighting_quality": 1.0,
    "lumen_scene_detail": 2.0,
    "lumen_max_reflection_bounces": 2,
    # the path tracer, for stills (a shot's "pt" in the shots file): samples a pixel, bounces, the clamp against fireflies
    "path_tracing_samples": 512,
    "path_tracing_bounces": 16,
    "path_tracing_max_intensity": 12.0,
}

# what a showcase on an open battle stage sets differently (the table above is the eros room's)
LOOK_SHOWCASE = {
    "outdoor": True,                    # the stage's directional light is the sun, on the stage and on her alike: no twin, no soft box
    # The sun.  The game lights stage s01 from 73 degrees up (a flat noon light, baked) under a sky whose sun sits on the horizon.
    # Here the light comes from where the sky picture has its sun (sky.json: 35 degrees to the right of the way she faces),
    # raised to clear the castle's towers: rays from the play area say that from 30 degrees up she and the 5 m of carpet round
    # her stand in the sun, and the towers' shadows fall across the far end.
    "sun_azimuth": None,                # degrees, atan2(Y, X) of the way to the sun; None: the sky picture's
    "sun_elevation": 32.0,
    "sun_color": (1.0, 0.90, 0.76),     # linear: a low sun
    "sun_intensity": 1.75,              # Unity's scale (x light_scale = lux): what a white surface facing it shows
    "sun_scale": 1.0,
    "sun_source_angle": 0.8,
    "sun_shaft": 1.0,
    "sun_on_characters": 0.0,
    # A fill that goes with the camera and lights her alone (the bodies' lighting channel; no shadow, no bounce).  One sun
    # cannot be her key everywhere: the battle stance faces 49 degrees off it, the showcase pose 22, and the skills' held
    # poses turn their back on it (they are made for the game's camera behind her).  Unity's scale, as the sun's.
    "camera_fill": 0.5,
    "camera_fill_color": (1.0, 0.98, 0.95),
    "camera_fill_angle": 24.0,          # degrees its source spans: a soft patch in the gold, not a flash's point
    "lamp_scale": 1.5,
    "sky_intensity": 0.7,               # the sky light: a capture of the sky sphere
    "sky_cubemap": 512,                 # px a face of that capture (128 by default: a blur in polished gold)
    "sky_tint": (1.0, 1.0, 1.0),
    "sky_visible": 1.0,                 # x the sky picture's own radiance on the sphere
    "exposure_bias": -0.7,
    "fog_density": 0.02,
    "fog_falloff": 0.02,
    "fog_scattering": 1.0,
    "fog_volume_distance": 8000.0,      # cm of volumetric fog: the stage is 60 m across
    "fog_cutoff": 300000.0,             # cm: the haze is the stage's, the sky dome (10 km out) shows its picture
    "vignette": 0.3,
    "motion_blur": 0.35,                # a sword swung through a quarter turn in two frames of a 30 fps film
    # polished metal: reflections are traced up to this roughness (Lumen's default 0.4 hands rougher gold to the blurred
    # probes: the armour's gloss map runs 0.3 .. 0.7)
    "lumen_max_roughness_to_trace": 0.65,
}
LOOK_BASE = dict(LOOK)


def use_look(slice_data):
    """The look of this slice's kind: the eros room's table, or it with the showcase's differences (one dict object: the
    functions below read LOOK)."""
    LOOK.clear()
    LOOK.update(LOOK_BASE)
    if (slice_data.get("kind") or "eros") == "showcase":
        LOOK.update(LOOK_SHOWCASE)


eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()


def log(msg):
    unreal.log("[MISHI] " + msg)


def setp(obj, name, value, warn=None):
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as e:
        (warn or unreal.log_warning)("%s.%s: %s" % (obj.get_class().get_name(), name, e))
        return False


# ---------------------------------------------------------------------------------------------------------------- Unity -> Unreal
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
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty), vy + w * ty + (z * tx - x * tz), vz + w * tz + (x * ty - y * tx))


def srgb_to_linear(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


# ---------------------------------------------------------------------------------------------------------------- level
def open_level(map_path):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    current = world.get_path_name().split(".")[0] if world else ""
    if current != map_path:
        if eal.does_asset_exist(map_path):
            les.load_level(map_path)
        else:
            les.new_level(map_path, False)
    for a in eas.get_all_level_actors():
        folder = str(a.get_folder_path())
        if folder.startswith("Mishi"):
            eas.destroy_actor(a)
    return les, eas


def spawn(eas, cls, loc, rot, label, folder):
    a = eas.spawn_actor_from_class(cls, loc, rot)
    a.set_actor_label(label)
    a.set_folder_path(folder)
    return a


def find_mesh(meshes, node):
    if node in meshes:
        return meshes[node]
    for name, m in meshes.items():
        if name.endswith("_" + node):
            return m
    return None


def place_room(eas, meshes, instances, placements, warn):
    placed, missing = 0, set()
    for p in placements:
        mesh = find_mesh(meshes, p["mesh"])
        if mesh is None:
            missing.add(p["mesh"])
            continue
        a = spawn(eas, unreal.StaticMeshActor, ue_pos(p["position"]), ue_quat(p["rotation"]).rotator(), p["name"], "Mishi/Room")
        comp = a.get_editor_property("static_mesh_component")
        comp.set_static_mesh(mesh)
        a.set_actor_scale3d(ue_scale(p["scale"]))
        for i, mname in enumerate(p.get("materials", [])):
            mi = instances.get(mname) if mname else None
            if mi is not None:
                comp.set_material(i, mi)
        if not p.get("cast_shadows", True):
            setp(comp, "cast_shadow", False)
        placed += 1
    if missing:
        warn("room: no mesh for %d nodes, e.g. %s" % (len(missing), sorted(missing)[:5]))
    return placed


def lighting_channels(room, characters):
    ch = unreal.LightingChannels()
    ch.set_editor_property("channel0", room)
    ch.set_editor_property("channel1", characters)
    ch.set_editor_property("channel2", False)
    return ch


def light_common(c, L, color, warn, shaft=0.0, shadows=True, room=True, characters=True):
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_light_color(color, True)
    setp(c, "cast_shadows", shadows and bool(L.get("shadows", True)), warn)
    setp(c, "volumetric_scattering_intensity", shaft, warn)
    setp(c, "lighting_channels", lighting_channels(room, characters), warn)


def sun_design(sky):
    """The showcase's own sun (LOOK's sun_elevation and so on): (rotation, colour, lux), or None where the stage's light stays."""
    if LOOK.get("sun_elevation") is None:
        return None
    az = LOOK.get("sun_azimuth")
    if az is None:
        az = (sky or {}).get("sun_azimuth")
    if az is None:
        return None
    az, el = math.radians(az), math.radians(LOOK["sun_elevation"])
    to_sun = unreal.Vector(math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    c = LOOK.get("sun_color", (1.0, 1.0, 1.0))
    return (unreal.MathLibrary.make_rot_from_x(to_sun * -1.0), unreal.LinearColor(c[0], c[1], c[2], 1.0),
            LOOK.get("sun_intensity", 1.0) * LOOK["light_scale"])


def place_lights(eas, lights, anchor, warn, sky=None):
    """The room's lights as a Lumen rig.  Unity's types and places are kept; what the game baked becomes real light."""
    n = 0
    k = LOOK["light_scale"]
    couple = anchor["position"]
    design = sun_design(sky) if LOOK.get("outdoor") else None
    for L in lights:
        if not L.get("enabled", True):
            continue
        pos = ue_pos(L["position"])
        fwd_u = unity_rotate(L["rotation"], (0.0, 0.0, 1.0))           # a Unity light shines along its +Z, an Unreal one along +X
        rot = unreal.MathLibrary.make_rot_from_x(ue_dir(fwd_u))
        kind = L.get("type", "Point")
        color = unreal.LinearColor(L["color"][0], L["color"][1], L["color"][2], 1.0)
        intensity = L["intensity"] * k
        baked = L.get("bake_type", "Baked") == "Baked"
        outdoor = bool(LOOK.get("outdoor"))
        if kind == "Directional" and (baked or outdoor):
            if design:
                rot, color, intensity = design
            a = spawn(eas, unreal.DirectionalLight, pos, rot, L["name"], "Mishi/Lights")
            c = a.get_component_by_class(unreal.DirectionalLightComponent)
            setp(c, "intensity", intensity * LOOK["sun_scale"], warn)
            setp(c, "light_source_angle", LOOK["sun_source_angle"], warn)
            setp(c, "atmosphere_sun_light", False, warn)
            setp(c, "forward_shading_priority", 1, warn)          # this one is the sun of the fog and of translucent surfaces
            # (under an open sky the sun is hers too; in the eros room it lights the room alone and a weaker twin lights the skin)
            light_common(c, L, color, warn, LOOK["sun_shaft"], characters=outdoor)
            if LOOK["sun_on_characters"] > 0.0 and not outdoor:
                a2 = spawn(eas, unreal.DirectionalLight, pos, rot, L["name"] + "_Skin", "Mishi/Lights")
                c2 = a2.get_component_by_class(unreal.DirectionalLightComponent)
                setp(c2, "intensity", intensity * LOOK["sun_scale"] * LOOK["sun_on_characters"], warn)
                setp(c2, "light_source_angle", LOOK["sun_source_angle"], warn)
                setp(c2, "atmosphere_sun_light", False, warn)
                setp(c2, "forward_shading_priority", 0, warn)
                setp(c2, "indirect_lighting_intensity", 0.0, warn)      # Lumen's surface cache knows no channels: no second bounce of the sun
                light_common(c2, L, color, warn, 0.0, room=False)
                n += 1
        elif kind == "Directional":
            d = LOOK["key_distance"]
            at = [couple[0] - fwd_u[0] * d, couple[1] + 0.35 - fwd_u[1] * d, couple[2] - fwd_u[2] * d]
            a = spawn(eas, unreal.RectLight, ue_pos(at), rot, L["name"] + "_Key", "Mishi/Lights")
            c = a.get_component_by_class(unreal.RectLightComponent)
            setp(c, "intensity_units", unreal.LightUnits.CANDELAS, warn)
            setp(c, "intensity", intensity * d * d * LOOK["key_scale"], warn)       # the same light on the couple as the directional gave
            setp(c, "attenuation_radius", 900.0, warn)
            setp(c, "source_width", LOOK["key_size"][0] * 100.0, warn)
            setp(c, "source_height", LOOK["key_size"][1] * 100.0, warn)
            setp(c, "barn_door_angle", 70.0, warn)
            light_common(c, L, color, warn, LOOK["key_shaft"])
        elif kind == "Spot":
            a = spawn(eas, unreal.SpotLight, pos, rot, L["name"], "Mishi/Lights")
            c = a.get_component_by_class(unreal.SpotLightComponent)
            setp(c, "intensity_units", unreal.LightUnits.CANDELAS, warn)
            setp(c, "intensity", intensity * LOOK["fill_scale"], warn)
            setp(c, "attenuation_radius", L["range"] * 100.0, warn)
            setp(c, "outer_cone_angle", L["spot_angle"] * 0.5, warn)
            setp(c, "inner_cone_angle", max(L.get("inner_spot_angle", 0.0) * 0.5, L["spot_angle"] * 0.25), warn)
            setp(c, "source_radius", 12.0, warn)
            light_common(c, L, color, warn, 0.2)
        elif kind in ("Rectangle", "Area", "Disc"):
            size = L.get("area_size", [1.0, 1.0])
            a = spawn(eas, unreal.RectLight, pos, rot, L["name"], "Mishi/Lights")
            c = a.get_component_by_class(unreal.RectLightComponent)
            setp(c, "intensity_units", unreal.LightUnits.CANDELAS, warn)
            setp(c, "intensity", intensity * size[0] * size[1] * LOOK["panel_scale"], warn)      # radiance x area
            setp(c, "attenuation_radius", max(L["range"], 6.0) * 100.0, warn)
            setp(c, "source_width", size[0] * 100.0, warn)
            setp(c, "source_height", size[1] * 100.0, warn)
            light_common(c, L, color, warn, 0.0)
        else:
            a = spawn(eas, unreal.PointLight, pos, rot, L["name"], "Mishi/Lights")
            c = a.get_component_by_class(unreal.PointLightComponent)
            setp(c, "intensity_units", unreal.LightUnits.CANDELAS, warn)
            setp(c, "intensity", intensity * LOOK["lamp_scale"], warn)
            setp(c, "attenuation_radius", max(L["range"], 2.5) * 100.0, warn)
            setp(c, "source_radius", 4.0, warn)
            setp(c, "soft_source_radius", 6.0, warn)
            light_common(c, L, color, warn, 0.5)
        n += 1
    return n


def ensure_sky_material(masters_folder):
    """An unlit sky colour for the sky sphere (the room's own sky is a solid tint x exposure), marked Is Sky for the sky light."""
    path = masters_folder + "/M_Mishi_Sky"
    if eal.does_asset_exist(path):
        return unreal.load_asset(path)
    mat = asset_tools.create_asset("M_Mishi_Sky", masters_folder, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    mat.set_editor_property("is_sky", True)
    col = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -500, 0)
    col.set_editor_property("parameter_name", "Tint")
    col.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
    k = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -500, 250)
    k.set_editor_property("parameter_name", "Exposure")
    k.set_editor_property("default_value", 1.0)
    mul = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -250, 80)
    mel.connect_material_expressions(col, "", mul, "A")
    mel.connect_material_expressions(k, "", mul, "B")
    mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat)
    return mat


def ensure_sky_map_material(masters_folder, default_tex):
    """The sky sphere showing a long-lat picture baked by Tools/mishi_sky.py: each pixel of the dome looks its own direction up
    in it (u = atan2(Y, X) / 2 pi + 0.5, v = acos(Z) / pi - the rule the bake used), unlit, Is Sky for the sky light's capture.
    default_tex: a linear texture for the parameter's default (the engine's own default is sRGB: with a Linear Color sampler the
    material does not compile, the dome gets the default material and the sky stays black behind the fog)."""
    path = masters_folder + "/M_Mishi_SkyMap"
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    mat = asset_tools.create_asset("M_Mishi_SkyMap", masters_folder, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    mat.set_editor_property("is_sky", True)
    cam = mel.create_material_expression(mat, unreal.MaterialExpressionCameraVectorWS, -1100, 0)
    uv = mel.create_material_expression(mat, unreal.MaterialExpressionCustom, -850, 0)
    uv.set_editor_property("code", "float3 d = normalize(-ToCamera);\nreturn float2(atan2(d.y, d.x) / 6.2831853 + 0.5, acos(clamp(d.z, -1.0, 1.0)) / 3.14159265);")
    uv.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT2)
    uv.set_editor_property("description", "direction -> long-lat")
    ci = unreal.CustomInput()
    ci.set_editor_property("input_name", "ToCamera")
    uv.set_editor_property("inputs", [ci])
    mel.connect_material_expressions(cam, "", uv, "ToCamera")
    tex = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, -550, 0)
    tex.set_editor_property("parameter_name", "SkyMap")
    if default_tex is not None:
        tex.set_editor_property("texture", default_tex)
    tex.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    tex.set_editor_property("mip_value_mode", unreal.TextureMipValueMode.TMVM_MIP_LEVEL)      # (the u seam would pick a tiny mip)
    mel.connect_material_expressions(uv, "", tex, "UVs")
    k = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -550, 300)
    k.set_editor_property("parameter_name", "Scale")
    k.set_editor_property("default_value", 8.0)
    b = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -550, 420)
    b.set_editor_property("parameter_name", "Brightness")
    b.set_editor_property("default_value", 1.0)
    m1 = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -250, 80)
    m2 = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -100, 160)
    mel.connect_material_expressions(tex, "RGB", m1, "A")
    mel.connect_material_expressions(k, "", m1, "B")
    mel.connect_material_expressions(m1, "", m2, "A")
    mel.connect_material_expressions(b, "", m2, "B")
    mel.connect_material_property(m2, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat)
    return mat


def import_sky_map(path, folder, warn):
    """The 16-bit long-lat picture as a linear HDR texture, no mips to pick wrongly at the seam."""
    name = "T_Sky_" + os.path.splitext(os.path.basename(path))[0]
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", path)
    t.set_editor_property("destination_path", folder)
    t.set_editor_property("destination_name", name)
    t.set_editor_property("automated", True)
    t.set_editor_property("replace_existing", True)
    t.set_editor_property("save", True)
    asset_tools.import_asset_tasks([t])
    tex = unreal.load_asset("%s/%s.%s" % (folder, name, name))
    if tex is None:
        warn("sky map %s did not import" % path)
        return None
    setp(tex, "srgb", False, warn)
    setp(tex, "compression_settings", unreal.TextureCompressionSettings.TC_HDR, warn)
    setp(tex, "mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS, warn)
    setp(tex, "address_x", unreal.TextureAddress.TA_WRAP, warn)
    setp(tex, "address_y", unreal.TextureAddress.TA_CLAMP, warn)
    eal.save_loaded_asset(tex)
    return tex


def place_environment(eas, slice_data, materials_folder, slice_folder, warn, source_dir=None):
    rs = slice_data.get("render_settings") or {}
    post = slice_data.get("post") or {}
    sphere = unreal.load_asset("/Engine/BasicShapes/Sphere.Sphere")
    sky = spawn(eas, unreal.StaticMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), "SkySphere", "Mishi/Sky")
    sc = sky.get_editor_property("static_mesh_component")
    sc.set_static_mesh(sphere)
    setp(sc, "cast_shadow", False, warn)
    mi_path = slice_folder + "/Materials/MI_Sky"
    mi = unreal.load_asset(mi_path) if eal.does_asset_exist(mi_path) else asset_tools.create_asset(
        "MI_Sky", slice_folder + "/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    sky_info = slice_data.get("sky") or {}
    sky_file = os.path.join(source_dir, sky_info["file"]) if source_dir and sky_info.get("file") else None
    if sky_file and os.path.isfile(sky_file):
        # the stage's own sky: the game's skybox baked to a long-lat picture, on a dome far outside the stage; it is the picture
        # behind everything and what the sky light captures.  Rays: Lumen's scene leaves an Is Sky mesh out by itself
        # (r.RayTracing.ExcludeSky); the path tracer shows it to camera rays, and with no part in indirect light and no shadow
        # the light of the sky comes from the sky light alone, once.
        sky.set_actor_scale3d(unreal.Vector(20000, 20000, 20000))          # 10 km out
        setp(sc, "affect_dynamic_indirect_lighting", False, warn)
        setp(sc, "affect_distance_field_lighting", False, warn)
        tex = import_sky_map(sky_file, slice_folder + "/Textures", warn)
        mel.set_material_instance_parent(mi, ensure_sky_map_material(materials_folder, tex))
        mel.clear_all_material_instance_parameters(mi)
        if tex is not None:
            mel.set_material_instance_texture_parameter_value(mi, "SkyMap", tex)
        mel.set_material_instance_scalar_parameter_value(mi, "Scale", float(sky_info.get("scale", 8.0)))
        mel.set_material_instance_scalar_parameter_value(mi, "Brightness", float(LOOK.get("sky_visible", 1.0)))
    else:
        # the eros rooms: the game's solid-colour sky box (warm tint x exposure) on a big sphere, lighting the room through its windows
        sky.set_actor_scale3d(unreal.Vector(400, 400, 400))            # a 100 cm sphere -> 400 m across
        mel.set_material_instance_parent(mi, ensure_sky_material(materials_folder))
        tint = rs.get("sky_tint") or [1.0, 0.77, 0.45, 1.0]
        mel.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(srgb_to_linear(tint[0]), srgb_to_linear(tint[1]), srgb_to_linear(tint[2]), 1))
        mel.set_material_instance_scalar_parameter_value(mi, "Exposure", rs.get("sky_exposure", 2.0))
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi)
    sc.set_material(0, mi)
    light = spawn(eas, unreal.SkyLight, unreal.Vector(0, 0, 300), unreal.Rotator(0, 0, 0), "SkyLight", "Mishi/Sky")
    lc = light.get_component_by_class(unreal.SkyLightComponent)
    lc.set_mobility(unreal.ComponentMobility.MOVABLE)
    setp(lc, "real_time_capture", True, warn)
    setp(lc, "intensity", LOOK["sky_intensity"], warn)
    if LOOK.get("sky_cubemap"):
        setp(lc, "cubemap_resolution", int(LOOK["sky_cubemap"]), warn)      # what polished metal mirrors of the sky
    if LOOK.get("sky_tint"):
        st = LOOK["sky_tint"]
        setp(lc, "light_color", unreal.Color(r=int(min(st[0], 1.0) * 255), g=int(min(st[1], 1.0) * 255), b=int(min(st[2], 1.0) * 255), a=255), warn)
    # the room's haze
    if rs.get("fog", False):
        fog = spawn(eas, unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), "Fog", "Mishi/Sky")
        fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
        col = rs.get("fog_color", [1, 1, 1, 1])
        setp(fc, "fog_density", LOOK["fog_density"], warn)
        setp(fc, "fog_height_falloff", LOOK["fog_falloff"], warn)
        f = LOOK["fog_scattering"]
        setp(fc, "fog_inscattering_luminance", unreal.LinearColor(srgb_to_linear(col[0]) * f, srgb_to_linear(col[1]) * f, srgb_to_linear(col[2]) * f, 1), warn)
        setp(fc, "enable_volumetric_fog", True, warn)
        setp(fc, "volumetric_fog_scattering_distribution", 0.7, warn)       # forward scattering: shafts glow towards the light
        setp(fc, "volumetric_fog_albedo", unreal.Color(r=255, g=244, b=232, a=255), warn)
        setp(fc, "volumetric_fog_extinction_scale", 1.0, warn)
        setp(fc, "volumetric_fog_distance", LOOK.get("fog_volume_distance", 2500.0), warn)
        if LOOK.get("fog_cutoff"):
            # the haze ends before the sky dome: at 10 km it would be nothing but fog colour
            setp(fc, "fog_cutoff_distance", LOOK["fog_cutoff"], warn)
    # post-processing: the game's ACES look is Unreal's own tonemapper; its bloom numbers; a fixed exposure
    ppv = spawn(eas, unreal.PostProcessVolume, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), "Post", "Mishi/Sky")
    setp(ppv, "unbound", True, warn)
    s = ppv.get_editor_property("settings")
    pairs = [("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL), ("auto_exposure_apply_physical_camera_exposure", False),
             ("auto_exposure_bias", LOOK["exposure_bias"]), ("bloom_intensity", post.get("bloom_intensity", 0.6)),
             ("bloom_threshold", post.get("bloom_threshold", 0.55)), ("vignette_intensity", LOOK.get("vignette", 0.25)),
             ("scene_fringe_intensity", post.get("chromatic", 0.25)),
             ("motion_blur_amount", LOOK.get("motion_blur", 0.0)),
             ("lumen_ray_lighting_mode", {"surface_cache": unreal.LumenRayLightingModeOverride.SURFACE_CACHE,
                                          "reflections": unreal.LumenRayLightingModeOverride.HIT_LIGHTING_FOR_REFLECTIONS,
                                          "hit": unreal.LumenRayLightingModeOverride.HIT_LIGHTING}.get(
                                              LOOK["lumen_ray_lighting"], unreal.LumenRayLightingModeOverride.DEFAULT)),
             ("lumen_final_gather_quality", LOOK["lumen_final_gather_quality"]),
             ("lumen_reflection_quality", LOOK["lumen_reflection_quality"]),
             ("lumen_scene_lighting_quality", LOOK["lumen_scene_lighting_quality"]),
             ("lumen_scene_detail", LOOK["lumen_scene_detail"]),
             ("lumen_max_reflection_bounces", LOOK["lumen_max_reflection_bounces"]),
             ("path_tracing_samples_per_pixel", LOOK["path_tracing_samples"]),
             ("path_tracing_max_bounces", LOOK["path_tracing_bounces"]),
             ("path_tracing_max_path_intensity", LOOK["path_tracing_max_intensity"]),
             ("path_tracing_enable_denoiser", True),
             ("path_tracing_enable_reference_dof", True)]
    if LOOK.get("lumen_max_roughness_to_trace") is not None:
        pairs.append(("lumen_max_roughness_to_trace_reflections", LOOK["lumen_max_roughness_to_trace"]))
    for k, v in pairs:
        try:
            s.set_editor_property("override_" + k, True)
        except Exception as e:
            warn("post override_%s: %s" % (k, e))
        setp(s, k, v, warn)
    ppv.set_editor_property("settings", s)


def place_couple(eas, slice_name, slice_text, slice_data, her, her_anims, him, his_anims, sounds, masters, instances, warn):
    anchor = slice_data["anchor"]
    a = spawn(eas, unreal.MishiCouple, ue_pos(anchor["position"]), ue_quat(anchor["rotation"]).rotator(),
              "Couple_" + slice_data.get("posture", slice_name), "Mishi")
    setp(a, "slice_json", slice_text, warn)
    setp(a, "her_mesh", her, warn)
    setp(a, "his_mesh", him, warn)
    setp(a, "her_clips", her_anims, warn)
    setp(a, "his_clips", his_anims, warn)
    setp(a, "sounds", sounds, warn)
    if (slice_data.get("kind") or "eros") != "eros":
        try:
            a.set_editor_property("b_skin_state", False)       # no blush and sweat following phases that are buttons here
        except Exception:
            pass
    if LOOK.get("camera_fill"):
        # the fill that goes with the camera (the camera pawn makes it): what a white surface facing it shows -> lux
        c = LOOK.get("camera_fill_color", (1.0, 1.0, 1.0))
        setp(a, "camera_fill", LOOK["camera_fill"] * LOOK["light_scale"], warn)
        setp(a, "camera_fill_color", unreal.LinearColor(c[0], c[1], c[2], 1.0), warn)
        setp(a, "camera_fill_angle", LOOK.get("camera_fill_angle", 24.0), warn)
    for prop, value in (("skin_state", masters.get("MPC")), ("his_body_skin", instances.get("pc_a00_nk_body")),
                        ("his_body_silhouette", instances.get("pc_a00_UnlitSilhouette"))):
        if value is not None:
            try:
                a.set_editor_property(prop, value)
            except Exception:
                pass                                # a property the C++ of this build does not have yet
    return a


def world_bounds(actors):
    lo, hi = [1e18] * 3, [-1e18] * 3
    for a in actors:
        origin, ext = a.get_actor_bounds(False)
        for i, (o, e) in enumerate(((origin.x, ext.x), (origin.y, ext.y), (origin.z, ext.z))):
            lo[i] = min(lo[i], o - e)
            hi[i] = max(hi[i], o + e)
    return lo, hi


def space_check(check_mesh, room_actors, warn):
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
    (log if res["ok"] else warn)("space check: placed room vs room.fbx differ by %.1f cm at most (%s)" % (err, "OK" if res["ok"] else "WRONG MAP?"))
    return res


def build_level(map_path, slice_name, slice_text, slice_data, placements, meshes, instances, masters, her, her_anims, him, his_anims, sounds,
                check_mesh, warn, source_dir=None):
    use_look(slice_data)
    les, eas = open_level(map_path)
    placed = place_room(eas, meshes, instances, placements, warn)
    lights = place_lights(eas, slice_data.get("lights", []), slice_data["anchor"], warn, slice_data.get("sky"))
    place_environment(eas, slice_data, "/Game/Mishi/Materials", "/Game/Mishi/" + slice_name, warn, source_dir)
    couple = place_couple(eas, slice_name, slice_text, slice_data, her, her_anims, him, his_anims, sounds, masters, instances, warn)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    try:
        setp(world.get_world_settings(), "default_game_mode", unreal.MishiGameMode, warn)
    except Exception as e:
        warn("world settings: %s" % e)
    room_actors = [a for a in eas.get_all_level_actors() if str(a.get_folder_path()) == "Mishi/Room"]
    check = space_check(check_mesh, room_actors, warn)
    les.save_current_level()
    log("level %s: %d placements, %d lights" % (map_path, placed, lights))
    return {"map": map_path, "placed": placed, "lights": lights, "couple": couple.get_name() if couple else None, "space_check": check}
