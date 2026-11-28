"""Mishi UE5 materials: the master materials (built in code, so they can be rebuilt and diffed) and the instances made from the
game's own material data.

Masters live in /Game/Mishi/Materials; each is a small graph round a Custom (HLSL) node feeding a MakeMaterialAttributes node:

  M_Mishi_Skin         ROE/Skin: Subsurface Profile (SSP_Mishi_Skin), base x tint, normal + a relief of furrows and pores (ours,
                       sized in centimetres of skin; or the game's tiled detail normal), MGAC (G gloss, B occlusion), sweat (a
                       film, then beads) and blush from MPC_Mishi (Wet, Flush) - SKIN_LOOK
  M_Mishi_Eye          Pinkcore/Heros/Eye rebuilt from its numbers: sclera / iris through the iris mask, the cornea's parallax,
                       the limbal ring, the lids' occlusion map - under a clear coat (the tear film: real highlights)
  M_Mishi_Hair         hair cards: Default Lit, a highlight drawn out across the strands (anisotropy; the game's shift noise slides
                       it strand by strand), temporal dither for soft edges, a hard mask in the shadow pass, the strand
                       occlusion map - HAIR_LOOK
  M_Mishi_Lash         eyebrows / lashes: translucent, per-pixel lit
  M_Mishi_Tears        the wet line on the lower lid: nothing but its highlight (alpha composite)
  M_Mishi_Lit / _Masked / _Glass    rooms (ROE/Environment): MGA, emission, the material's own tiling
  M_Mishi_Flat         unlit colour (the game draws the man as a flat silhouette)
  M_Mishi_Hidden       what is not drawn yet (the Effect layer's particles)

import_slice.py calls build_masters() and make_instance(); VERSION is stored on each master (asset user data would be heavier: a
texture parameter group name carries it) - bump it and the masters are rebuilt on the next import.
"""
import os

import unreal

VERSION = 21
MATS = "/Game/Mishi/Materials"

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
S = unreal.MaterialSamplerType
MP = unreal.MaterialProperty


def log(msg):
    unreal.log("[MISHI] " + msg)


def setp(obj, name, value):
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as e:
        unreal.log_warning("[MISHI] %s.%s: %s" % (obj.get_class().get_name(), name, e))
        return False


# ---------------------------------------------------------------------------------------------------------------- graph helper
class Graph:
    """A material being built: nodes are placed in a column per kind; out() wires a node into the material attributes."""

    def __init__(self, name, shading=None, blend=None, two_sided=False):
        path = "%s/%s" % (MATS, name)
        if eal.does_asset_exist(path):
            # In place: the asset stays, its graph is emptied and built again.  Deleting it and making it anew left every
            # instance of it without a parent - in every slice imported before, not only the one being imported - and a
            # material instance without a parent is the engine's grey default material (a whole slice in grey, noticed a
            # week later).  What a builder set on the material and no longer sets keeps its old value: set it back.
            self.mat = unreal.load_asset(path)
            mel.delete_all_material_expressions(self.mat)
        else:
            self.mat = asset_tools.create_asset(name, MATS, unreal.Material, unreal.MaterialFactoryNew())
        self.name = name
        self.rows = {}
        setp(self.mat, "shading_model", shading if shading is not None else unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
        setp(self.mat, "blend_mode", blend if blend is not None else unreal.BlendMode.BLEND_OPAQUE)
        setp(self.mat, "two_sided", bool(two_sided))
        setp(self.mat, "use_material_attributes", True)
        self.attrs = self.node(unreal.MaterialExpressionMakeMaterialAttributes, -200)
        mel.connect_material_property(self.attrs, "", MP.MP_MATERIAL_ATTRIBUTES)

    def node(self, cls, x):
        y = self.rows.get(x, -600)
        self.rows[x] = y + 220
        return mel.create_material_expression(self.mat, cls, x, y)

    def tex(self, name, default, sampler, uv=None, x=-1500):
        n = self.node(unreal.MaterialExpressionTextureSampleParameter2D, x)
        setp(n, "parameter_name", name)
        setp(n, "texture", default)
        setp(n, "sampler_type", sampler)
        if uv is not None:
            mel.connect_material_expressions(uv[0], uv[1], n, "UVs")
        return n

    def tex_object(self, name, default, sampler, x=-1500):
        n = self.node(unreal.MaterialExpressionTextureObjectParameter, x)
        setp(n, "parameter_name", name)
        setp(n, "texture", default)
        setp(n, "sampler_type", sampler)
        return n

    def scalar(self, name, value, x=-1900):
        n = self.node(unreal.MaterialExpressionScalarParameter, x)
        setp(n, "parameter_name", name)
        setp(n, "default_value", float(value))
        return n

    def vector(self, name, rgba, x=-1900):
        n = self.node(unreal.MaterialExpressionVectorParameter, x)
        setp(n, "parameter_name", name)
        setp(n, "default_value", unreal.LinearColor(*rgba))
        return n

    def primitive_scalar(self, name, index, value=0.0, x=-1900):
        """A scalar the component itself carries (custom primitive data): one value per placed object, not per material."""
        n = self.scalar(name, value, x)
        setp(n, "use_custom_primitive_data", True)
        setp(n, "primitive_data_index", index)
        return n

    def const(self, value, x=-1900):
        n = self.node(unreal.MaterialExpressionConstant, x)
        setp(n, "r", float(value))
        return n

    def const3(self, rgb, x=-1900):
        n = self.node(unreal.MaterialExpressionConstant3Vector, x)
        setp(n, "constant", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))
        return n

    def collection(self, mpc, name, x=-1900):
        n = self.node(unreal.MaterialExpressionCollectionParameter, x)
        setp(n, "collection", mpc)
        setp(n, "parameter_name", name)
        return n

    def custom(self, code, inputs, out_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3, outputs=(), desc="", x=-900):
        """inputs: [(name, node, output name)]; outputs: [(name, type)] additional outputs (assigned in the code by name)."""
        n = self.node(unreal.MaterialExpressionCustom, x)
        setp(n, "code", code)
        setp(n, "output_type", out_type)
        setp(n, "description", desc or "Mishi")
        ins = []
        for name, _, _ in inputs:
            ci = unreal.CustomInput()
            ci.set_editor_property("input_name", name)
            ins.append(ci)
        setp(n, "inputs", ins)
        outs = []
        for name, t in outputs:
            co = unreal.CustomOutput()
            co.set_editor_property("output_name", name)
            co.set_editor_property("output_type", t)
            outs.append(co)
        if outs:
            setp(n, "additional_outputs", outs)
        for name, src, out in inputs:
            if not mel.connect_material_expressions(src, out, n, name):
                unreal.log_warning("[MISHI] %s: custom input %s did not connect" % (self.name, name))
        return n

    def uv(self, index=0, x=-2300):
        n = self.node(unreal.MaterialExpressionTextureCoordinate, x)
        setp(n, "coordinate_index", index)
        return n

    def out(self, src, output, pin):
        if not mel.connect_material_expressions(src, output, self.attrs, pin):
            unreal.log_warning("[MISHI] %s: %s -> %s did not connect" % (self.name, output or "out", pin))

    def finish(self):
        # every master may sit on a skinned mesh with morph targets: in a game build a material without the usage flag is
        # replaced by the grey default material (the editor would set the flag by itself, the game cannot)
        for usage in (unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH, unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS):
            mel.set_material_usage(self.mat, usage)
        mel.recompile_material(self.mat)
        eal.save_loaded_asset(self.mat)
        return self.mat


F1 = unreal.CustomMaterialOutputType.CMOT_FLOAT1
F2 = unreal.CustomMaterialOutputType.CMOT_FLOAT2
F3 = unreal.CustomMaterialOutputType.CMOT_FLOAT3
F4 = unreal.CustomMaterialOutputType.CMOT_FLOAT4

# two tangent-space normals as one (reoriented normal mapping), the detail one weighted first
RNM = """
float3 n2 = normalize(lerp(float3(0, 0, 1), Detail, Weight));
float3 t = Base + float3(0, 0, 1);
float3 u = n2 * float3(-1, -1, 1);
return normalize(t * dot(t, u) / max(t.z, 1e-4) - u);
"""

TILED_UV = "return UV * Tiling.xy + Tiling.zw;"


# ---------------------------------------------------------------------------------------------------------------- shared assets
MPC_SCALARS = (("Wet", 0.0), ("Flush", 0.0), ("SkinBaked", 1.0), ("SkinRelief", 1.0))


def ensure_mpc():
    """MPC_Mishi: what the couple drives through the scene - Wet (sweat), Flush (blush) - and which skin is shown (the
    game's "skin" switch, AMishiCouple::SkinVersion): SkinBaked 1 = with a skin pack's baked maps where a material has them,
    SkinRelief 1 = with the tiled relief and the beads (0: the game's own detail map, no beads) - 1 / 1 is the newest."""
    path = MATS + "/MPC_Mishi"
    if eal.does_asset_exist(path):
        mpc = unreal.load_asset(path)
    else:
        mpc = asset_tools.create_asset("MPC_Mishi", MATS, unreal.MaterialParameterCollection, unreal.MaterialParameterCollectionFactoryNew())
    params = list(mpc.get_editor_property("scalar_parameters"))
    have = {str(p.get_editor_property("parameter_name")) for p in params}
    missing = [(n, v) for n, v in MPC_SCALARS if n not in have]
    if missing:
        for name, value in missing:
            p = unreal.CollectionScalarParameter()
            p.set_editor_property("parameter_name", name)
            p.set_editor_property("default_value", value)
            params.append(p)
        setp(mpc, "scalar_parameters", params)
        eal.save_loaded_asset(mpc)
        unreal.log("[MISHI] MPC_Mishi: added %s" % ", ".join(n for n, _ in missing))
    return mpc


def ensure_skin_profile(rebuild=False):
    """SSP_Mishi_Skin: Burley subsurface scattering for a fair skin, two specular lobes (a broad one and a tight oily one)."""
    path = MATS + "/SSP_Mishi_Skin"
    if eal.does_asset_exist(path) and not rebuild:
        return unreal.load_asset(path)
    if eal.does_asset_exist(path):
        prof = unreal.load_asset(path)
    else:
        prof = asset_tools.create_asset("SSP_Mishi_Skin", MATS, unreal.SubsurfaceProfile, unreal.SubsurfaceProfileFactory())
    s = prof.get_editor_property("settings")
    for k, v in (("enable_burley", True), ("enable_mean_free_path", True),
                 ("surface_albedo", unreal.LinearColor(0.90, 0.66, 0.58, 1.0)),
                 ("mean_free_path_color", unreal.LinearColor(1.0, 0.30, 0.18, 1.0)),
                 ("mean_free_path_distance", 0.55), ("world_unit_scale", 0.1),
                 ("tint", unreal.LinearColor(1.0, 1.0, 1.0, 1.0)), ("boundary_color_bleed", unreal.LinearColor(1.0, 1.0, 1.0, 1.0)),
                 ("roughness0", 0.68), ("roughness1", 1.2), ("lobe_mix", 0.8),
                 ("extinction_scale", 1.0), ("normal_scale", 0.08), ("scattering_distribution", 0.93), ("ior", 1.45),
                 ("transmission_tint_color", unreal.LinearColor(1.0, 0.45, 0.35, 1.0))):
        try:
            s.set_editor_property(k, v)
        except Exception as e:
            unreal.log_warning("[MISHI] SubsurfaceProfile.%s: %s" % (k, e))
    prof.set_editor_property("settings", s)
    eal.save_loaded_asset(prof)
    return prof


# How skin is shown from close by - beyond what the game's materials say (user 11-22: "5", skin and hair in close-ups).  The
# game has one 256 px detail normal (pc_common_detailskin: a net of cells) on the nude body (tiled 120, 0.5) and on the face
# (tiled 70, 0.4) - seen in a grazing highlight only, twice as fine on the face as on the body - and none on an armoured
# body's skin or on his body.
SKIN_LOOK = {
    # "relief": Tools/textures/skin_detail.png (Tools/make_skin_detail.py: furrows round little fields, pores) on every skin,
    # the same size everywhere; "game": the game's own map where a material names one, nothing elsewhere
    "detail": "relief",
    # What one tile of the relief covers.  At 2.4 cm its fields are skin's own half millimetre - and nothing of it reaches the
    # picture: a face 50 cm from the lens has 0.2 mm to a pixel, the relief only takes the highlight down as a whole.  At 6 cm
    # the fields are 1.25 mm, larger than life as every game draws them, and they read in a close-up.
    "tile_cm": 6.0,
    # how deep the furrows are cut, and the pores: a face is pores more than furrows (with the furrows at 0.3 a sunlit cheek
    # was a net of scales), a body the other way round
    "lines": {"face": 0.2, "body": 0.4, "tooth": 0.0},
    "pores": {"face": 0.6, "body": 0.3, "tooth": 0.0},
    "cavity": 0.5,                  # how far a furrow's or a pore's wall takes the highlight down (and roughens it)
    "shade": 0.06,                  # and how far it darkens the skin itself: under soft light there is no highlight to show the relief
    "patches": 0.5,                 # how unevenly it is spread (0: the same everywhere - a pattern; skin is finer here, coarser there)
    # Sweat.  The scene's wetness (MPC_Mishi "Wet", 0 - 1: the eros mode's phases, or a shot's "wet") is first a film - the
    # skin shines - and then beads that come up one by one (Tools/textures/sweat.png, Tools/make_sweat.py).
    "sweat_tile_cm": 8.0,           # what one tile of the beads covers: they are 0.5 - 2.3 mm across
    "sweat": {"face": 0.75, "body": 1.0, "tooth": 0.0},      # how much of the wetness a zone shows as beads
    "bead_roughness": 0.05,
    # A skin pack's maps drawn into a material's own layout (Tools/skin_transfer -> Import/_local/skin/<material>_hm_*.png):
    # used where they are there.  "relief": the pack's fine relief where it belongs on the body (at life size - the tiled
    # relief stays under it at "tile" of its strength, for the grain that is larger than life); "colour" / "gloss": its fine
    # colour and gloss; "veins"; "thin": more light through the thin places; "sweat": the pack's drops and rivulets (the
    # tiled beads stay at "beads" of their number).
    # With them may come <material>_hm_m.png: what the body has painted as its own (an areola, the navel) - there the game's
    # own detail map stays and no tiled relief is laid, whichever of the two newer skins is shown.
    # (the relief at twice the pack's own strength: at 1 a skin half a metre from the lens is as smooth as without it - what
    # is finer than the picture's pixels is averaged away, as the first tile at life size was)
    "baked": {"relief": 2.0, "colour": 1.5, "gloss": 1.0, "veins": 0.3, "thin": 0.6, "sweat": 1.0, "tile": 0.7, "beads": 0.5},
}


# What Import/_local/skin_detail.json says about a relief that was put there (import_slice.py reads it): keys of SKIN_LOOK
# that go before it - tile_cm, lines, pores, each a number or a table by zone.
SKIN_LOCAL = {}


def skin_look(key, zone):
    v = SKIN_LOCAL.get(key, SKIN_LOOK[key]) if key in ("tile_cm", "lines", "pores", "cavity", "shade", "patches") else SKIN_LOOK[key]
    return v[zone] if isinstance(v, dict) else v


def skin_zone(name):
    low = name.lower()
    return "tooth" if "tooth" in low or "teeth" in low else "face" if "face" in low or "head" in low else "body"


# ---------------------------------------------------------------------------------------------------------------- masters
def build_skin(d, mpc, profile):
    g = Graph("M_Mishi_Skin", shading=unreal.MaterialShadingModel.MSM_SUBSURFACE_PROFILE)
    setp(g.mat, "subsurface_profile", profile)
    uv = g.uv()
    base = g.tex("BaseMap", d["white"], S.SAMPLERTYPE_COLOR, (uv, ""))
    tint = g.vector("BaseColor", (1, 1, 1, 1))
    normal = g.tex("NormalMap", d["flat"], S.SAMPLERTYPE_NORMAL, (uv, ""))
    tiling = g.scalar("DetailTiling", 100.0)
    duv = g.custom("return UV * Tiling;", [("UV", uv, ""), ("Tiling", tiling, "")], F2, desc="detail uv", x=-1900)
    detail = g.tex("DetailNormalMap", d["flat"], S.SAMPLERTYPE_NORMAL, (duv, ""))
    dstrength = g.scalar("DetailStrength", 0.5)
    depth = g.node(unreal.MaterialExpressionPixelDepth, -1900)
    # which skin is shown (MPC_Mishi, the game's "skin" switch): the pack's baked maps, the tiled relief and beads
    sw_baked = g.collection(mpc, "SkinBaked")
    sw_relief = g.collection(mpc, "SkinRelief")
    relief_on = g.scalar("ReliefOn", 0.0)             # 1: this instance has the tiled relief in the game's detail map's place
    # what the body has painted as its own - an areola, the navel (Tools/skin_transfer/bake.py --own; black: nothing)
    b_own = g.tex("BakedOwn", d["none"], S.SAMPLERTYPE_LINEAR_COLOR, (uv, ""))
    # the relief made here (SKIN_LOOK): furrows in R, G and pores in B, A, tiled so that it is as fine on a face as on a thigh
    rtiling = g.scalar("ReliefTiling", 60.0)
    ruv = g.custom("return UV * Tiling;", [("UV", uv, ""), ("Tiling", rtiling, "")], F2, desc="relief uv", x=-1900)
    relief = g.tex("SkinDetailMap", d["grey"], S.SAMPLERTYPE_MASKS, (ruv, ""))
    lines = g.scalar("ReliefLines", 0.0)
    pores = g.scalar("ReliefPores", 0.0)
    patches = g.scalar("ReliefPatches", 0.0)
    # two slow, uneven fields over the body, in centimetres of skin (the material's UV scale: Tools/mishi_fbx.py): where the
    # relief is coarser (blobs of a few centimetres) and where the sweat stands (of half a palm)
    uv_cm = g.scalar("UvCm", 100.0)
    fields = g.custom("""
float2 q = UV * UvCm;
float a = sin(q.x * 0.9 + 1.7 * sin(q.y * 0.6 + 0.5)) * sin(q.y * 1.1 + 1.3 * sin(q.x * 0.7 + 2.0));
float b = sin(q.x * 0.45 + 1.9 * sin(q.y * 0.38 + 4.0)) * sin(q.y * 0.5 + 1.5 * sin(q.x * 0.33 + 1.0));
return float2(a, b);
""", [("UV", uv, ""), ("UvCm", uv_cm, "")], F2, desc="uneven fields", x=-1900)
    wet = g.collection(mpc, "Wet")
    # sweat's beads: each comes up when the wetness here passes its own mark
    stiling = g.scalar("SweatTiling", 20.0)
    suv = g.custom("return UV * Tiling;", [("UV", uv, ""), ("Tiling", stiling, "")], F2, desc="sweat uv", x=-1900)
    sweat = g.tex("SweatMap", d["dry"], S.SAMPLERTYPE_MASKS, (suv, ""))
    beads = g.scalar("SweatBeads", 0.0)
    baked_beads = g.scalar("BakedBeads", 1.0)         # of the tiled beads that stay beside a pack's own drops
    baked_tile = g.scalar("BakedTile", 1.0)           # of the tiled relief that stays under a pack's own
    bead = g.custom("""
float near = saturate((320.0 - Depth) / 170.0);          // beads are for close-ups: by 3 m only the film's shine is left
float local = saturate(Wet) * (0.9 + 0.55 * Field.y) * Amount * Relief * lerp(1.0, Beside, Baked);
float on = S.b * saturate((local * 1.2 - S.a) * 6.0) * near;
float2 n = (S.rg - 0.5) * 2.0 * on;
Bead = on;
Rim = saturate(dot(n, n) * 1.5);
return float3(n, sqrt(saturate(1.0 - dot(n, n))));
""", [("S", sweat, "RGBA"), ("Wet", wet, ""), ("Field", fields, ""), ("Amount", beads, ""), ("Depth", depth, ""),
      ("Relief", sw_relief, ""), ("Baked", sw_baked, ""), ("Beside", baked_beads, "")], F3,
                    [("Bead", F1), ("Rim", F1)], "sweat beads", x=-1500)
    # a skin pack's maps in this material's own layout (SKIN_LOOK "baked"; neutral defaults: nothing of it without them)
    b_normal = g.tex("BakedNormal", d["flat"], S.SAMPLERTYPE_NORMAL, (uv, ""))
    b_colour = g.tex("BakedColour", d["neutral"], S.SAMPLERTYPE_LINEAR_COLOR, (uv, ""))
    b_wet = g.tex("BakedWet", d["none"], S.SAMPLERTYPE_LINEAR_COLOR, (uv, ""))
    b_wetn = g.tex("BakedWetNormal", d["flat"], S.SAMPLERTYPE_NORMAL, (uv, ""))
    b_relief = g.scalar("BakedRelief", 0.0)
    b_tint = g.scalar("BakedColourAmount", 0.0)
    b_gloss = g.scalar("BakedGloss", 0.0)
    b_veins = g.scalar("BakedVeins", 0.0)
    b_thin = g.scalar("BakedThin", 0.0)
    b_sweat = g.scalar("BakedSweat", 0.0)
    water = g.custom("""
// the pack's sweat: where it stands (drops, wet patches - the wettest spots first) and, on a skin wet enough, where it runs
float wetness = saturate(Wet);
float stand = saturate((W.g - (1.0 - wetness * 1.2)) * 4.0);
float run = W.r * saturate((wetness - 0.55) * 2.5);       // (from 0.45 the last phase's 0.8 was a shower, not sweat)
float on = saturate(max(stand, run)) * Amount * Baked * saturate((700.0 - Depth) / 300.0);
Water = on;
float2 n = N.xy * on;
return float3(n, sqrt(saturate(1.0 - dot(n, n))));
""", [("W", b_wet, "RGBA"), ("N", b_wetn, "RGB"), ("Wet", wet, ""), ("Amount", b_sweat, ""), ("Depth", depth, ""), ("Baked", sw_baked, "")], F3,
                     [("Water", F1)], "sweat that stands and runs", x=-1500)
    # The game's own detail map.  In its place stands the relief made here (ReliefOn; the "skin" switch can go back) - but not
    # on what the body has painted as its own: the tile is skin of nowhere in particular, and stretched over an areola it was
    # a comb of streaks where the game's map is the areola's grain (seen 11-28 with him hidden: his hand lies there).  There
    # the game's map stays, and is treated as the relief is: nothing of it under a bead, less under a film of sweat.
    # (the pores are for close-ups: gone by 2.5 m, where they would only shimmer)
    fade = g.custom("""
float mine = ReliefOn * Relief;
float kept = mine * saturate(Own) * (1.0 - max(Bead, Water)) * (1.0 - 0.65 * saturate(Wet));
return Strength * ((1.0 - mine) + kept) * saturate((400.0 - Depth) / 250.0);
""", [("Strength", dstrength, ""), ("Depth", depth, ""), ("ReliefOn", relief_on, ""), ("Relief", sw_relief, ""), ("Own", b_own, "R"),
      ("Bead", bead, "Bead"), ("Water", water, "Water"), ("Wet", wet, "")], F1, desc="detail fade", x=-1100)
    nrm = g.custom(RNM, [("Base", normal, "RGB"), ("Detail", detail, "RGB"), ("Weight", fade, "")], F3, desc="normal + detail")
    rel = g.custom("""
float near = saturate((400.0 - Depth) / 250.0);
near *= 1.0 + Patches * Field.x;
near *= 1.0 - max(Bead, Water);                           // under a bead the skin's own relief is not seen
near *= 1.0 - 0.65 * saturate(Wet);                       // and a film of sweat fills the furrows: wet skin is smoother
near *= Relief * lerp(1.0, Under, Baked);                 // (the "skin" switch; under a pack's own relief the tile is weaker)
near *= 1.0 - saturate(Own);                              // (not on what the body has painted as its own: the game's map is there)
float2 l = (D.rg - 0.5) * 2.0 * Lines * near;
float2 p = (D.ba - 0.5) * 2.0 * Pores * near;
// where the surface tilts it is a furrow's or a pit's wall: less of the sky gets in there
Cavity = saturate(length(l) * 1.3 + length(p) * 1.7);
return normalize(float3(l + p, 1.0));
""", [("D", relief, "RGBA"), ("Lines", lines, ""), ("Pores", pores, ""), ("Depth", depth, ""), ("Field", fields, ""), ("Patches", patches, ""),
      ("Bead", bead, "Bead"), ("Wet", wet, ""), ("Water", water, "Water"), ("Relief", sw_relief, ""), ("Baked", sw_baked, ""),
      ("Under", baked_tile, ""), ("Own", b_own, "R")], F3, [("Cavity", F1)], "relief", x=-1100)
    one = g.const(1.0, x=-1500)
    nrm = g.custom(RNM, [("Base", nrm, ""), ("Detail", rel, ""), ("Weight", one, "")], F3, desc="normal + relief", x=-700)
    baked = g.custom("""
float k = Strength * Baked * (1.0 - max(Bead, Water)) * (1.0 - 0.65 * saturate(Wet));
return normalize(float3(N.xy * k, max(N.z, 0.05)));
""", [("N", b_normal, "RGB"), ("Strength", b_relief, ""), ("Bead", bead, "Bead"), ("Water", water, "Water"), ("Wet", wet, ""), ("Baked", sw_baked, "")], F3,
                     desc="the pack's relief", x=-1100)
    nrm = g.custom(RNM, [("Base", nrm, ""), ("Detail", baked, ""), ("Weight", one, "")], F3, desc="normal + the pack's relief", x=-600)
    nrm = g.custom(RNM, [("Base", nrm, ""), ("Detail", bead, ""), ("Weight", one, "")], F3, desc="normal + beads", x=-500)
    nrm = g.custom(RNM, [("Base", nrm, ""), ("Detail", water, ""), ("Weight", one, "")], F3, desc="normal + water", x=-400)
    cavity = g.scalar("ReliefCavity", 0.5)
    shade = g.scalar("ReliefShade", 0.0)
    mgac = g.tex("MaskMap", d["mask"], S.SAMPLERTYPE_MASKS, (uv, ""))
    smooth = g.scalar("Smoothness", 0.85)
    occ = g.scalar("OcclusionStrength", 0.7)
    spec = g.scalar("SpecularLevel", 0.45)
    scatter = g.scalar("Scatter", 0.85)
    gloss = g.scalar("GlossBoost", 1.12)
    wet_rough = g.scalar("WetRoughness", 0.3)       # (0.2 was oil, not sweat - seen once the wetness reached the materials at all)
    bead_rough = g.scalar("BeadRoughness", 0.05)
    # blush: the Unity viewer's (RoeSkin.shader: albedo x (1.07, 0.92, 0.90) at full flush) - a warmer, redder skin all over.
    # (A tint of (1, 0.62, 0.60) stood here, weighted by MGAC.A as "the curved places"; A is no such mask - it follows the gloss -
    # and the first time the blush reached the materials at all, 11-22, the last phase was a sunburn.)
    flush_tint = g.vector("FlushTint", (1.07, 0.92, 0.90, 1.0))
    flush = g.collection(mpc, "Flush")
    code = """
// MGAC: G gloss, B occlusion
float3 col = Base * Tint;
// sweat is a film first: the skin shines and is a little darker (and the film fills the furrows)
float film = saturate(Wet);
col *= lerp(float3(1.0, 1.0, 1.0), FlushTint, saturate(Flush)) * lerp(1.0, 0.92, film);
float rough = 1.0 - saturate(Mgac.g * Smooth * Gloss);
rough = lerp(rough, min(rough, WetRough), film);
// the relief's furrows and pores: duller and darker in the highlight than the fields between them
float pit = saturate(Pit * PitDepth) * (1.0 - 0.5 * film);
col *= 1.0 - PitShade * saturate(Pit);
rough = saturate(rough + 0.18 * pit);
float level = Spec * lerp(1.0, Mgac.b, 0.5) * (1.0 + 0.35 * film) * (1.0 - 0.85 * pit);
// the pack's fine colour (a factor round 1) and gloss (a pore shines less), its veins (a cooler, darker line under the skin)
col *= lerp(float3(1.0, 1.0, 1.0), BC.rgb * 2.0, ColourAmount * Baked);
float fine = (BC.a - 0.5) * 2.0 * GlossAmount * Baked * (1.0 - 0.5 * film);
rough = saturate(rough * (1.0 - 0.8 * fine));
level *= saturate(1.0 + 1.5 * fine);
col = lerp(col, col * float3(0.78, 0.9, 0.98), saturate(BW.b * Veins * Baked));
// then beads: water, smooth as glass, a little darker at the rim where it bends the light away
float beads = max(Bead, Water);
rough = lerp(rough, BeadRough, beads);
level = lerp(level, 0.5, beads);
col *= 1.0 - 0.12 * Bead * BeadRim - 0.05 * Water;
Roughness = rough;
AO = lerp(1.0, Mgac.b, Occ);
Specular = level;
// more of the light goes through where the body is thin (an ear, a finger)
Through = saturate(Scatter + (1.0 - Scatter) * saturate(BW.a * 2.0) * Thin * Baked);
return col;
"""
    c = g.custom(code, [("Base", base, "RGB"), ("Tint", tint, ""), ("Mgac", mgac, "RGBA"), ("Smooth", smooth, ""), ("Occ", occ, ""),
                        ("Spec", spec, ""), ("Wet", wet, ""), ("Flush", flush, ""), ("WetRough", wet_rough, ""), ("FlushTint", flush_tint, ""),
                        ("Gloss", gloss, ""), ("Pit", rel, "Cavity"), ("PitDepth", cavity, ""), ("PitShade", shade, ""),
                        ("Bead", bead, "Bead"), ("BeadRim", bead, "Rim"), ("BeadRough", bead_rough, ""),
                        ("BC", b_colour, "RGBA"), ("BW", b_wet, "RGBA"), ("Water", water, "Water"), ("ColourAmount", b_tint, ""),
                        ("GlossAmount", b_gloss, ""), ("Veins", b_veins, ""), ("Thin", b_thin, ""), ("Scatter", scatter, ""),
                        ("Baked", sw_baked, "")],
                 F3, [("Roughness", F1), ("AO", F1), ("Specular", F1), ("Through", F1)], "skin")
    g.out(c, "", "BaseColor")
    g.out(c, "Roughness", "Roughness")
    g.out(c, "AO", "AmbientOcclusion")
    g.out(c, "Specular", "Specular")
    g.out(nrm, "", "Normal")
    g.out(c, "Through", "Opacity")
    return g.finish()


EYE_CODE = """
// Pinkcore/Heros/Eye (Rise of Eros), from the game's own numbers: the eye is composed in the eyeball's UV square, its centre the
// looking direction.  UV here is Unreal's (v down), the tangent frame is Unreal's too, so the parallax keeps its sign.
float3 viewTS = mul(Parameters.TangentToWorld, Parameters.CameraVector);
float2 p = UV - 0.5;
float pivot = LimbusPivot * 0.5;
float pivot2 = pivot * pivot;
float width = LimbusPivotWidth * 0.01;
float d2 = (dot(p, p) - pivot2) * LimbusFadeRatio + pivot2;
float inStart = (pivot2 - 0.0001 - width) * (1.0 - LimbusSizeIris);
float inEnd = pivot2 - width;
float outEnd = lerp(pivot2 + width + 0.0001, 0.25, LimbusSizeSclera);
float ringIn = smoothstep(0.0, 1.0, saturate((d2 - inStart) / (inEnd - inStart)));
float ringOut = smoothstep(0.0, 1.0, saturate((d2 - outEnd) / (pivot2 + width - outEnd)));
float ring = saturate(ringIn + ringOut - 1.0);

float2 offset = viewTS.xy / (viewTS.z + 0.42);
float2 mask = Texture2DSample(MaskTex, MaskTexSampler, p * IrisLimbusScaleInv + 0.5).rg;
float irisW = mask.r;
float height = mask.g * IrisParallax;
float2 pp = p - height * offset;
float pupilScale = lerp(PupilMinSizeInv, PupilMaxSizeInv, PupilSizeScale);
float2 irisUV = pp * (pupilScale * IrisLimbusScaleInv) + 0.5 - height * offset;
float3 iris = Texture2DSample(IrisTex, IrisTexSampler, irisUV).rgb * IrisColor;
// the 512 px iris map's pupil is a jagged blot in close-ups: a clean disc over it, sized from the map's own pupil
float pr = length(irisUV - 0.5);
iris *= smoothstep(PupilRadius * 0.86, PupilRadius * 1.06, pr);
float3 sclera = Texture2DSample(ScleraTex, ScleraTexSampler, p * ScleraSizeInv + 0.5).rgb * ScleraColor;
float3 albedo = lerp(sclera, iris, irisW);
albedo = lerp(albedo, LimbusColor, ring);
float occ = Texture2DSample(OccTex, OccTexSampler, UV).r;
Occlusion = 1.0 - occ * lerp(ScleraOcclusionAmt, IrisOcclusionAmt, irisW);
IrisWeight = irisW;
return albedo;
"""


def build_eye(d):
    g = Graph("M_Mishi_Eye", shading=unreal.MaterialShadingModel.MSM_CLEAR_COAT)
    uv = g.uv()
    iris = g.tex_object("IrisMap", d["white"], S.SAMPLERTYPE_COLOR)
    sclera = g.tex_object("ScleraMap", d["white"], S.SAMPLERTYPE_COLOR)
    mask = g.tex_object("IrisMask", d["mask"], S.SAMPLERTYPE_MASKS)
    occ = g.tex_object("OcclusionMap", d["mask_black"], S.SAMPLERTYPE_MASKS)
    ins = [("UV", uv, ""), ("IrisTex", iris, ""), ("ScleraTex", sclera, ""), ("MaskTex", mask, ""), ("OccTex", occ, "")]
    scalars = (("IrisLimbusScaleInv", 0.6), ("PupilMinSizeInv", 0.75), ("PupilMaxSizeInv", 0.35), ("PupilSizeScale", 0.3),
               ("LimbusPivot", 0.433), ("LimbusPivotWidth", 0.369), ("LimbusFadeRatio", 5.0), ("LimbusSizeIris", 0.661),
               ("LimbusSizeSclera", 0.21), ("IrisParallax", 0.061), ("ScleraSizeInv", 0.864), ("IrisOcclusionAmt", 0.3),
               ("ScleraOcclusionAmt", 0.5), ("PupilRadius", 0.0335))
    for name, value in scalars:
        ins.append((name, g.scalar(name, value), ""))
    for name, value in (("IrisColor", (1, 1, 1, 1)), ("ScleraColor", (1, 1, 1, 1)), ("LimbusColor", (0.461, 0.472, 0.528, 1))):
        ins.append((name, g.vector(name, value), ""))
    c = g.custom(EYE_CODE, ins, F3, [("Occlusion", F1), ("IrisWeight", F1)], "eye")
    # the lids' shade darkens the eyeball itself (the game multiplies its light by it), most of it also as ambient occlusion
    shade = g.custom("return Albedo * lerp(1.0, Occ, 0.75);", [("Albedo", c, ""), ("Occ", c, "Occlusion")], F3, desc="lid shade", x=-500)
    g.out(shade, "", "BaseColor")
    g.out(c, "Occlusion", "AmbientOcclusion")
    # the sclera's fine bump, flat over the cornea
    bump = g.tex("ScleraNormal", d["flat"], S.SAMPLERTYPE_NORMAL, (uv, ""))
    bump_strength = g.scalar("BumpStrength", 1.0)
    n = g.custom("return normalize(lerp(float3(0, 0, 1), Bump, Strength * (1.0 - Iris)));",
                 [("Bump", bump, "RGB"), ("Strength", bump_strength, ""), ("Iris", c, "IrisWeight")], F3, desc="sclera bump", x=-500)
    g.out(n, "", "Normal")
    rough_s = g.scalar("ScleraRoughness", 0.32)
    rough_i = g.scalar("IrisRoughness", 0.5)
    r = g.custom("return lerp(S, I, W);", [("S", rough_s, ""), ("I", rough_i, ""), ("W", c, "IrisWeight")], F1, desc="base roughness", x=-500)
    g.out(r, "", "Roughness")
    g.out(g.scalar("SpecularLevel", 0.3), "", "Specular")
    g.out(g.scalar("ClearCoat", 1.0), "", "ClearCoat")
    g.out(g.scalar("ClearCoatRoughness", 0.04), "", "ClearCoatRoughness")
    # a little of the iris's own light, as the game's _IrisIllumColor: the iris never goes dead under the brow
    glow = g.vector("IrisGlow", (0.0, 0.0, 0.0, 1.0))
    e = g.custom("return Albedo * Glow * W;", [("Albedo", c, ""), ("Glow", glow, ""), ("W", c, "IrisWeight")], F3, desc="iris glow", x=-500)
    g.out(e, "", "EmissiveColor")
    return g.finish()


# Hair cards' highlight (user 11-22: "5" - the hair is cards, its highlight can be tuned).
HAIR_LOOK = {
    "roughness": 0.5,               # with the anisotropy: a band about as wide as the game's own (its Kajiya-Kay power 15)
    "specular": 0.5,
    # The band of light across a head of hair: a highlight drawn out ACROSS the strands.  Unreal stretches a highlight along
    # the material's Tangent for a positive Anisotropy; the Tangent given is the strand (up the cards' texture), so the value
    # is negative.  (+0.8 stood here since the first hair: the highlight ran along each strand and was never seen as one.)
    "anisotropy": -0.7,
    "shift": 0.0,                   # the band slid along the strands (the normal leant along them; + towards the tips)
    "shift_noise": 1.0,             # how far each strand's own noise (the game's _ShiftNoiseMap) slides it: a ragged band, not a ruled one
}


def build_hair(d):
    """Hair cards.  Default Lit with anisotropy along the strands rather than the Hair model: on cards the Hair model goes
    near black wherever no light falls straight on it (the back of her head in a room lit by one window), while the game's own
    hair is a diffuse base under two strand highlights - which is what an anisotropic highlight over a lit base gives."""
    g = Graph("M_Mishi_Hair", blend=unreal.BlendMode.BLEND_MASKED, two_sided=True)
    setp(g.mat, "dithered_lod_transition", False)
    uv = g.uv()
    base = g.tex("BaseMap", d["white"], S.SAMPLERTYPE_COLOR, (uv, ""))
    tint = g.vector("BaseColor", (1, 1, 1, 1))
    mga = g.tex("StrandMap", d["mask"], S.SAMPLERTYPE_MASKS, (uv, ""))
    occ = g.scalar("OcclusionStrength", 0.3)
    root = g.scalar("RootDarkening", 0.2)
    col = g.custom("""
// MGA.B: each strand's shade inside its lock; the roots (bottom of the cards' texture) a little deeper, as hair is at the scalp
float shade = lerp(1.0, Mga.b, Occ);
float rootward = saturate((UV.y - 0.55) / 0.4);
return Base * Tint * shade * (1.0 - Root * rootward);
""", [("Base", base, "RGB"), ("Tint", tint, ""), ("Mga", mga, "RGB"), ("Occ", occ, ""), ("Root", root, ""), ("UV", uv, "")], F3, desc="hair colour")
    g.out(col, "", "BaseColor")
    g.out(g.scalar("SpecularLevel", HAIR_LOOK["specular"]), "", "Specular")
    g.out(g.scalar("Roughness", HAIR_LOOK["roughness"]), "", "Roughness")
    # the strands run up the cards' texture: the highlight is drawn out across them (HAIR_LOOK "anisotropy")
    g.out(g.scalar("Anisotropy", HAIR_LOOK["anisotropy"]), "", "Anisotropy")
    g.out(g.vector("StrandDirection", (0.0, 1.0, 0.0, 0.0)), "", "Tangent")
    normal = g.tex("NormalMap", d["flat"], S.SAMPLERTYPE_NORMAL, (uv, ""))
    bump = g.scalar("BumpScale", 1.0)
    # the game's shift noise (streaks along the strands, 0.5 = none): each strand's band a little higher or lower than its neighbour's
    shift_tiling = g.vector("ShiftTiling", (1.0, 1.0, 0.0, 0.0))
    suv = g.custom(TILED_UV, [("UV", uv, ""), ("Tiling", shift_tiling, "RGBA")], F2, desc="shift uv", x=-1900)
    shift_map = g.tex("ShiftMap", d["grey"], S.SAMPLERTYPE_MASKS, (suv, ""))
    shift = g.scalar("Shift", 0.0)
    shift_noise = g.scalar("ShiftNoise", 0.0)
    g.out(g.custom("""
float3 n = normalize(float3(N.xy * Scale, N.z));
// a normal leant along the strand (the texture's v) slides the highlight along it
n.y += Shift + (Noise - 0.5) * 2.0 * NoiseStrength;
return normalize(n);
""", [("N", normal, "RGB"), ("Scale", bump, ""), ("Noise", shift_map, "R"), ("Shift", shift, ""), ("NoiseStrength", shift_noise, "")],
                   F3, desc="strand normal"), "", "Normal")
    # soft edges: a temporal dither of the alpha (TSR resolves it); the shadow pass takes a plain cut so shadows do not crawl
    cutoff = g.scalar("Cutoff", 0.5)
    alpha_gain = g.scalar("AlphaGain", 1.35)
    alpha = g.custom("return saturate(A * Tint * Gain);", [("A", base, "A"), ("Tint", tint, "A"), ("Gain", alpha_gain, "")], F1, desc="alpha", x=-1100)
    dither = g.custom("""
// each frame keeps a pixel when its alpha beats an interleaved-gradient noise that moves with the frame (against the clip value 1/3)
float n = InterleavedGradientNoise(Parameters.SvPosition.xy, ResolvedView.StateFrameIndexMod8);
return A - n + 0.3333;
""", [("A", alpha, "")], F1, desc="temporal dither", x=-700)
    core = g.scalar("ShadowCore", 0.95)
    hard = g.custom("return (A > Cut && Mga.g >= Core) ? 1.0 : 0.0;", [("A", alpha, ""), ("Cut", cutoff, ""), ("Mga", mga, "RGB"), ("Core", core, "")],
                    F1, desc="shadow: solid core only", x=-700)
    switch = g.node(unreal.MaterialExpressionShadowReplace, -450)
    mel.connect_material_expressions(dither, "", switch, "Default")
    mel.connect_material_expressions(hard, "", switch, "Shadow")
    g.out(switch, "", "OpacityMask")
    return g.finish()


def build_lash(d):
    g = Graph("M_Mishi_Lash", blend=unreal.BlendMode.BLEND_TRANSLUCENT, two_sided=True)
    setp(g.mat, "translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    uv = g.uv()
    base = g.tex("BaseMap", d["white"], S.SAMPLERTYPE_COLOR, (uv, ""))
    tint = g.vector("BaseColor", (1, 1, 1, 1))
    g.out(g.custom("return Base * Tint;", [("Base", base, "RGB"), ("Tint", tint, "")], F3, desc="colour"), "", "BaseColor")
    gain = g.scalar("AlphaGain", 1.0)
    g.out(g.custom("return saturate(A * Tint * Gain);", [("A", base, "A"), ("Tint", tint, "A"), ("Gain", gain, "")], F1, desc="alpha"), "", "Opacity")
    g.out(g.scalar("Roughness", 0.55), "", "Roughness")
    g.out(g.scalar("SpecularLevel", 0.25), "", "Specular")
    return g.finish()


def build_tears(d):
    g = Graph("M_Mishi_Tears", blend=unreal.BlendMode.BLEND_ALPHA_COMPOSITE)
    setp(g.mat, "translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    g.out(g.const3((0, 0, 0)), "", "BaseColor")
    g.out(g.scalar("Opacity", 0.0), "", "Opacity")
    g.out(g.scalar("Roughness", 0.05), "", "Roughness")
    g.out(g.scalar("SpecularLevel", 0.5), "", "Specular")
    return g.finish()


def build_surface(d, name, kind):
    """Rooms and plain parts.  kind: lit / masked / glass.
    Every one can fade out object by object: the camera sets LensFade (custom primitive data 0) on a post or a rail that stands
    between the lens and the couple - a temporal dither in the view (TSR resolves it into a soft fade), while the shadow pass
    keeps the object whole: its shadow and its bounce stay in the room."""
    blend = {"lit": unreal.BlendMode.BLEND_MASKED, "masked": unreal.BlendMode.BLEND_MASKED, "glass": unreal.BlendMode.BLEND_TRANSLUCENT}[kind]
    # two-sided, the plain kind too: the room's shell is planes facing inwards, and a ray that comes from behind a one-sided
    # triangle goes through it - the shadow rays of Lumen's hit lighting let the sun in through the roof and the walls
    g = Graph(name, blend=blend, two_sided=True)
    setp(g.mat, "dithered_lod_transition", False)
    if kind == "glass":
        setp(g.mat, "translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    uv0 = g.uv()
    tiling = g.vector("Tiling", (1, 1, 0, 0))
    uv = g.custom("return UV * T.xy + T.zw;", [("UV", uv0, ""), ("T", tiling, "RGBA")], F2, desc="tiling", x=-1900)
    base = g.tex("BaseMap", d["white"], S.SAMPLERTYPE_COLOR, (uv, ""))
    tint = g.vector("BaseColor", (1, 1, 1, 1))
    g.out(g.custom("return Base * Tint;", [("Base", base, "RGB"), ("Tint", tint, "")], F3, desc="colour"), "", "BaseColor")
    normal = g.tex("NormalMap", d["flat"], S.SAMPLERTYPE_NORMAL, (uv, ""))
    bump = g.scalar("BumpScale", 1.0)
    g.out(g.custom("return normalize(float3(N.xy * Scale, N.z));", [("N", normal, "RGB"), ("Scale", bump, "")], F3, desc="bump scale"), "", "Normal")
    mga = g.tex("MaskMap", d["mask"], S.SAMPLERTYPE_MASKS, (uv, ""))
    metal = g.scalar("Metallic", 0.0)
    smooth = g.scalar("Smoothness", 0.5)
    occ = g.scalar("OcclusionStrength", 1.0)
    g.out(g.custom("return saturate(M * S);", [("M", mga, "R"), ("S", metal, "")], F1, desc="metallic"), "", "Metallic")
    g.out(g.custom("return saturate(1.0 - G * S);", [("G", mga, "G"), ("S", smooth, "")], F1, desc="roughness"), "", "Roughness")
    g.out(g.custom("return lerp(1.0, B, S);", [("B", mga, "B"), ("S", occ, "")], F1, desc="occlusion"), "", "AmbientOcclusion")
    emis = g.tex("EmissionMap", d["black"], S.SAMPLERTYPE_COLOR, (uv, ""))
    emis_col = g.vector("EmissionColor", (0, 0, 0, 1))
    emis_scale = g.scalar("EmissionScale", 1.0)
    g.out(g.custom("return E * C * K;", [("E", emis, "RGB"), ("C", emis_col, ""), ("K", emis_scale, "")], F3, desc="emission"), "", "EmissiveColor")
    fade = g.primitive_scalar("LensFade", 0, 0.0)
    if kind == "glass":
        g.out(g.custom("return saturate(A * Tint) * saturate(1.0 - Fade);", [("A", base, "A"), ("Tint", tint, "A"), ("Fade", fade, "")], F1, desc="alpha"),
              "", "Opacity")
        g.out(g.scalar("SpecularLevel", 0.5), "", "Specular")
        return g.finish()
    if kind == "masked":
        cut = g.scalar("Cutoff", 0.5)
        clip = g.custom("return A * Tint - Cut + 0.3333;", [("A", base, "A"), ("Tint", tint, "A"), ("Cut", cut, "")], F1, desc="clip", x=-1100)
    else:
        clip = g.const(1.0, x=-1100)
    seen = g.custom("""
// the object's fade: each frame keeps the pixels whose noise is under what is left of it
float keep = saturate(1.0 - Fade);
float n = InterleavedGradientNoise(Parameters.SvPosition.xy, ResolvedView.StateFrameIndexMod8);
return keep > n ? Clip : 0.0;
""", [("Fade", fade, ""), ("Clip", clip, "")], F1, desc="lens fade", x=-700)
    switch = g.node(unreal.MaterialExpressionShadowReplace, -450)
    mel.connect_material_expressions(seen, "", switch, "Default")
    mel.connect_material_expressions(clip, "", switch, "Shadow")
    g.out(switch, "", "OpacityMask")
    return g.finish()


# How a battle outfit's metal is shown (the instances' MetalBoost / MetalRoughness / MetalCavity).  The a08 maps where the mask
# says metal: albedo (0.31, 0.21, 0.11) on the body sheet and (0.48, 0.36, 0.19) on the armour sheet - gold is (1.0, 0.77, 0.34) -
# and a gloss of 0.3 .. 0.7 (median 0.5).
ARMOR_LOOK = {
    "metal_boost": 1.7,
    "metal_roughness": 0.7,
    "metal_cavity": 0.35,
    "metal_saturation": 1.25,
}


def build_armor(d):
    """A battle outfit: armour, cloth, chains and the weapon on the game's own maps (4096 px on the body) - albedo, normal, and
    the mask map's metal (R), gloss (G), occlusion (B).  Metal is what the mask says, so the gold answers the sky and the room
    through the reflections; cut-outs (chain links) by the albedo's alpha; two-sided (cloth seen from inside, and rays from behind)."""
    g = Graph("M_Mishi_Armor", blend=unreal.BlendMode.BLEND_MASKED, two_sided=True)
    setp(g.mat, "dithered_lod_transition", False)
    uv = g.uv()
    base = g.tex("BaseMap", d["white"], S.SAMPLERTYPE_COLOR, (uv, ""))
    tint = g.vector("BaseColor", (1, 1, 1, 1))
    normal = g.tex("NormalMap", d["flat"], S.SAMPLERTYPE_NORMAL, (uv, ""))
    bump = g.scalar("BumpScale", 1.0)
    mga = g.tex("MaskMap", d["mask"], S.SAMPLERTYPE_MASKS, (uv, ""))
    metal = g.scalar("Metallic", 1.0)
    smooth = g.scalar("Smoothness", 1.0)
    occ = g.scalar("OcclusionStrength", 1.0)
    boost = g.scalar("MetalBoost", 1.0)                 # x the base colour of the metal parts (ARMOR_LOOK; 1 = the game's paint)
    metal_rough = g.scalar("MetalRoughness", 1.0)       # x the roughness of the metal parts (1 = the game's gloss map as it is)
    cavity = g.scalar("MetalCavity", 0.0)               # how far the occlusion map darkens the metal in its creases
    metal_sat = g.scalar("MetalSaturation", 1.0)        # x the saturation of the lifted metal colour
    min_rough = g.scalar("MinRoughness", 0.08)
    spec = g.scalar("SpecularLevel", 0.5)
    code = """
// the mask map: R metal, G gloss, B occlusion.  Roughness from the gloss; the metal parts can be polished further
float m = saturate(Mga.r * Metal);
float rough = (1.0 - saturate(Mga.g * Smooth)) * lerp(1.0, MetalRough, m);
Roughness = max(rough, MinRough);
Metallic = m;
AO = lerp(1.0, Mga.b, Occ);
// occlusion also dims the reflection in the creases (the game's specular occlusion): a lining would mirror the sky otherwise
Specular = Spec * lerp(1.0, Mga.b, 0.7 * Occ);
float3 c = Base * Tint;
// The game paints its gold at a third of what gold gives back (its shader adds a Fresnel term on top).  A metal's base colour
// is its mirror colour: that paint is a dull bronze.  Lifted towards the metal (the hue kept: scaled down as a whole where a
// channel would pass 1); a metal has no diffuse for the occlusion to dim, so the creases are darkened in the colour itself.
float3 lifted = c * Boost;
lifted /= max(1.0, max(lifted.r, max(lifted.g, lifted.b)));
// (a mirror of a blue sky: a pale gold goes grey-green under it, a deeper one stays gold)
lifted = max(lerp(dot(lifted, float3(0.2126, 0.7152, 0.0722)).xxx, lifted, Sat), 0.0);
lifted *= lerp(1.0, Mga.b, Cavity * Occ);
return lerp(c, lifted, m);
"""
    c = g.custom(code, [("Base", base, "RGB"), ("Tint", tint, ""), ("Mga", mga, "RGB"), ("Metal", metal, ""), ("Smooth", smooth, ""),
                        ("Occ", occ, ""), ("Boost", boost, ""), ("MetalRough", metal_rough, ""), ("Cavity", cavity, ""),
                        ("Sat", metal_sat, ""), ("MinRough", min_rough, ""), ("Spec", spec, "")],
                 F3, [("Roughness", F1), ("Metallic", F1), ("AO", F1), ("Specular", F1)], "armour")
    g.out(c, "", "BaseColor")
    g.out(c, "Roughness", "Roughness")
    g.out(c, "Metallic", "Metallic")
    g.out(c, "AO", "AmbientOcclusion")
    g.out(c, "Specular", "Specular")
    g.out(g.custom("return normalize(float3(N.xy * Scale, N.z));", [("N", normal, "RGB"), ("Scale", bump, "")], F3, desc="bump scale"), "", "Normal")
    emis = g.tex("EmissionMap", d["black"], S.SAMPLERTYPE_COLOR, (uv, ""))
    emis_col = g.vector("EmissionColor", (0, 0, 0, 1))
    g.out(g.custom("return E * C;", [("E", emis, "RGB"), ("C", emis_col, "")], F3, desc="emission"), "", "EmissiveColor")
    cut = g.scalar("Cutoff", 0.5)
    g.out(g.custom("return A * Tint - Cut + 0.3333;", [("A", base, "A"), ("Tint", tint, "A"), ("Cut", cut, "")], F1, desc="clip"), "", "OpacityMask")
    return g.finish()


def build_flat(d):
    g = Graph("M_Mishi_Flat", shading=unreal.MaterialShadingModel.MSM_UNLIT)
    tint = g.vector("BaseColor", (1, 1, 1, 1))
    scale = g.scalar("Brightness", 1.0)
    g.out(g.custom("return C * K;", [("C", tint, ""), ("K", scale, "")], F3, desc="flat"), "", "EmissiveColor")
    return g.finish()


def build_hidden(d):
    g = Graph("M_Mishi_Hidden", blend=unreal.BlendMode.BLEND_MASKED)
    g.out(g.const(0.0), "", "OpacityMask")
    return g.finish()


MASTERS = ("M_Mishi_Skin", "M_Mishi_Eye", "M_Mishi_Hair", "M_Mishi_Lash", "M_Mishi_Tears", "M_Mishi_Armor", "M_Mishi_Lit", "M_Mishi_Masked",
           "M_Mishi_Glass", "M_Mishi_Flat", "M_Mishi_Hidden")


def version_tag():
    return MATS + "/_version_%d" % VERSION


def build_masters(defaults, force=False):
    """defaults: white / black (colour), mask (white, linear), mask_black, flat (normal) textures.  Returns {name: material}."""
    stamp = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "MishiMaterialsVersion.txt")
    have = ""
    if os.path.exists(stamp):
        with open(stamp) as f:
            have = f.read().strip()
    missing = [m for m in MASTERS if not eal.does_asset_exist("%s/%s" % (MATS, m))]
    mpc = ensure_mpc()
    profile = ensure_skin_profile(rebuild=force or have != str(VERSION))
    if force or missing or have != str(VERSION):
        log("building the master materials (version %s -> %d, missing %d)" % (have or "none", VERSION, len(missing)))
        build_skin(defaults, mpc, profile)
        build_eye(defaults)
        build_hair(defaults)
        build_lash(defaults)
        build_tears(defaults)
        build_armor(defaults)
        build_surface(defaults, "M_Mishi_Lit", "lit")
        build_surface(defaults, "M_Mishi_Masked", "masked")
        build_surface(defaults, "M_Mishi_Glass", "glass")
        build_flat(defaults)
        build_hidden(defaults)
        with open(stamp, "w") as f:
            f.write(str(VERSION))
    out = {m: unreal.load_asset("%s/%s.%s" % (MATS, m, m)) for m in MASTERS}
    out["MPC"] = mpc
    out["SkinProfile"] = profile
    out["_white"] = defaults["white"]
    out["_skin_detail"] = defaults.get("skin_detail")
    out["_sweat"] = defaults.get("sweat")
    return out


# ---------------------------------------------------------------------------------------------------------------- instances
KIND_MASTER = {"skin": "M_Mishi_Skin", "eye": "M_Mishi_Eye", "hair": "M_Mishi_Hair", "lash": "M_Mishi_Lash", "tears": "M_Mishi_Tears",
               "armor": "M_Mishi_Armor",
               "lit": "M_Mishi_Lit", "masked": "M_Mishi_Masked", "glass": "M_Mishi_Glass", "flat": "M_Mishi_Flat", "hidden": "M_Mishi_Hidden"}
EYE_SCALARS = ("IrisLimbusScaleInv", "PupilMinSizeInv", "PupilMaxSizeInv", "PupilSizeScale", "LimbusPivot", "LimbusPivotWidth",
               "LimbusFadeRatio", "LimbusSizeIris", "LimbusSizeSclera", "IrisParallax", "ScleraSizeInv", "IrisOcclusionAmt",
               "ScleraOcclusionAmt", "BumpStrength")


def srgb_to_linear(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def linear_rgba(c):
    """A Unity material colour (stored as sRGB) as the linear value its shader gets; alpha as it is."""
    return (srgb_to_linear(c[0]), srgb_to_linear(c[1]), srgb_to_linear(c[2]), c[3] if len(c) > 3 else 1.0)


def classify(name, d):
    """Which master a game material goes to - from its shader when Unity named one, from its slots and name otherwise."""
    low = name.lower()
    tex = d.get("textures", {})
    fl = d.get("floats", {})
    shader = d.get("shader", "")
    if ("Particles" in shader or low.startswith("fx_") or "semen" in low or "liquid" in low or "particle" in low
            or ("decal" in low and d.get("who") != "room")):
        return "hidden"                      # the Effect layer is not in the FBX; its liquids come later (a stage's decals are its flags and dirt)
    if "tears" in low:
        return "tears"
    if "_IrisAlbedoTex" in tex or shader == "ROE/Eye":
        return "eye"
    if "hair" in low and ("_OcclusionMaskMap" in tex or "_ShiftNoiseMap" in tex or shader == "ROE/Hair" or "HAIR_AM" in d.get("keywords", [])):
        return "hair"
    if "eyebrow" in low or "eyelash" in low or shader == "ROE/Eyebrow":
        return "lash"
    if "_SkinLutMap" in tex or shader == "ROE/Skin":
        return "skin"
    if "silhouette" in low or shader.endswith("/Unlit"):
        return "flat"
    # a character's outfit or weapon (the game's Pinkcore character shader with its mask map), not a room's surface
    if d.get("source", "").startswith("game") and ("PINKCORE_MGA" in d.get("keywords", []) or low.startswith("wp_")):
        return "armor"
    if d.get("transparent", fl.get("_Surface", 0) > 0.5):
        return "glass"
    if d.get("alpha_clip", fl.get("_AlphaClip", 0) > 0.5 or fl.get("_EnableAlphaTest", 0) > 0.5):
        return "masked"
    return "lit"


def safe_name(name):
    return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name)


def make_instance(name, d, lookup, masters, folder):
    """A MaterialInstanceConstant MI_<name> of the right master, filled from the game material's slots, floats and colours."""
    kind = classify(name, d)
    master = masters[KIND_MASTER[kind]]
    # (d["instance_tag"]: this slice's body has maps of its own for the material - an instance of its own beside the common one)
    inst = "MI_" + safe_name(name) + d.get("instance_tag", "")
    path = "%s/%s" % (folder, inst)
    if eal.does_asset_exist(path):
        mi = unreal.load_asset(path)
    else:
        mi = asset_tools.create_asset(inst, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, master)
    mel.clear_all_material_instance_parameters(mi)
    textures, f, c, tiling = d.get("textures", {}), d.get("floats", {}), d.get("colors", {}), d.get("tiling", {})

    def tex(param, *slots):
        for slot in slots:
            t = lookup.get(textures.get(slot)) if slot in textures else None
            if t is not None:
                mel.set_material_instance_texture_parameter_value(mi, param, t)
                return True
        return False

    def scalar(param, value):
        mel.set_material_instance_scalar_parameter_value(mi, param, float(value))

    def vector(param, rgba):
        mel.set_material_instance_vector_parameter_value(mi, param, unreal.LinearColor(rgba[0], rgba[1], rgba[2], rgba[3]))

    base_color = c.get("_BaseColor") or c.get("_Color") or [1, 1, 1, 1]
    if kind == "skin":
        tex("BaseMap", "_BaseMap")
        tex("NormalMap", "_BumpMap")
        tex("MaskMap", "_MetallicGlossMap")
        vector("BaseColor", linear_rgba(base_color))
        scalar("Smoothness", f.get("_Smoothness", 0.85))
        scalar("OcclusionStrength", f.get("_OcclusionStrength", 0.7))
        relief = SKIN_LOOK["detail"] == "relief" and masters.get("_skin_detail") is not None and d.get("uv_cm")
        # the game's own detail map and its numbers, whichever skin is shown: the "skin" switch can go back to it
        if tex("DetailNormalMap", "_DetailNormalMap"):
            scalar("DetailTiling", tiling.get("_DetailNormalMap", [100.0])[0])
            scalar("DetailStrength", f.get("_DetailBumpScale", 0.5))
        else:
            scalar("DetailStrength", 0.0)
        scalar("ReliefOn", 1.0 if relief else 0.0)
        if relief:
            # (the relief instead of the game's map, not on top of it)
            zone = skin_zone(name)
            mel.set_material_instance_texture_parameter_value(mi, "SkinDetailMap", masters["_skin_detail"])
            scalar("ReliefPatches", skin_look("patches", zone))
            scalar("ReliefTiling", d["uv_cm"] / skin_look("tile_cm", zone))
            scalar("ReliefLines", skin_look("lines", zone))
            scalar("ReliefPores", skin_look("pores", zone))
            scalar("ReliefCavity", skin_look("cavity", zone))
            scalar("ReliefShade", skin_look("shade", zone))
        baked = d.get("baked") or {}
        look = SKIN_LOOK["baked"]
        if baked.get("n") is not None:
            mel.set_material_instance_texture_parameter_value(mi, "BakedNormal", baked["n"])
            scalar("BakedRelief", look["relief"])
            # (the tiled relief under it: weaker - the body's own relief is there now, the tile only adds its grain)
            scalar("BakedTile", look["tile"])
        if baked.get("c") is not None:
            mel.set_material_instance_texture_parameter_value(mi, "BakedColour", baked["c"])
            scalar("BakedColourAmount", look["colour"])
            scalar("BakedGloss", look["gloss"])
        if baked.get("w") is not None:
            mel.set_material_instance_texture_parameter_value(mi, "BakedWet", baked["w"])
            scalar("BakedVeins", look["veins"])
            scalar("BakedThin", look["thin"])
            if baked.get("wn") is not None:
                mel.set_material_instance_texture_parameter_value(mi, "BakedWetNormal", baked["wn"])
                scalar("BakedSweat", look["sweat"])
        if baked.get("m") is not None:
            mel.set_material_instance_texture_parameter_value(mi, "BakedOwn", baked["m"])
        if d.get("uv_cm"):
            scalar("UvCm", d["uv_cm"])
            if masters.get("_sweat") is not None:
                mel.set_material_instance_texture_parameter_value(mi, "SweatMap", masters["_sweat"])
                scalar("SweatTiling", d["uv_cm"] / SKIN_LOOK["sweat_tile_cm"])
                scalar("SweatBeads", SKIN_LOOK["sweat"][skin_zone(name)])
                scalar("BakedBeads", look["beads"] if baked.get("wn") is not None else 1.0)
                scalar("BeadRoughness", SKIN_LOOK["bead_roughness"])
    elif kind == "eye":
        tex("IrisMap", "_IrisAlbedoTex")
        tex("ScleraMap", "_ScleraAlbedoTex")
        tex("IrisMask", "_IrisMaskTex")
        tex("OcclusionMap", "_EyeOcclusionMap")
        tex("ScleraNormal", "_EyeBumpMap")
        for p in EYE_SCALARS:
            if "_" + p in f:
                scalar(p, f["_" + p])
        for p in ("IrisColor", "ScleraColor", "LimbusColor"):
            if "_" + p in c:
                vector(p, linear_rgba(c["_" + p]))
    elif kind == "hair":
        tex("BaseMap", "_BaseMap")
        tex("StrandMap", "_OcclusionMaskMap")
        tex("NormalMap", "_BumpMap")
        vector("BaseColor", linear_rgba(base_color))
        scalar("OcclusionStrength", f.get("_OcclusionStrength", 0.3))
        scalar("Cutoff", f.get("_Cutoff", 0.5))
        scalar("Shift", HAIR_LOOK["shift"])
        scalar("Roughness", HAIR_LOOK["roughness"])
        scalar("SpecularLevel", HAIR_LOOK["specular"])
        scalar("Anisotropy", HAIR_LOOK["anisotropy"])
        if tex("ShiftMap", "_ShiftNoiseMap"):
            t = tiling.get("_ShiftNoiseMap", [1.0, 1.0, 0.0, 0.0])
            vector("ShiftTiling", t)
            scalar("ShiftNoise", HAIR_LOOK["shift_noise"])
        else:
            scalar("ShiftNoise", 0.0)
    elif kind == "lash":
        tex("BaseMap", "_BaseMap")
        vector("BaseColor", linear_rgba(base_color))
    elif kind == "flat":
        vector("BaseColor", linear_rgba(base_color))
    elif kind == "armor":
        tex("BaseMap", "_BaseMap", "_MainTex")
        tex("NormalMap", "_BumpMap")
        tex("MaskMap", "_MetallicGlossMap")
        vector("BaseColor", linear_rgba(base_color))
        scalar("Metallic", f.get("_Metallic", 1.0))
        scalar("Smoothness", f.get("_Smoothness", 1.0))
        scalar("OcclusionStrength", f.get("_OcclusionStrength", 1.0))
        scalar("BumpScale", f.get("_BumpScale", 1.0))
        scalar("MetalBoost", ARMOR_LOOK["metal_boost"])
        scalar("MetalRoughness", ARMOR_LOOK["metal_roughness"])
        scalar("MetalCavity", ARMOR_LOOK["metal_cavity"])
        scalar("MetalSaturation", ARMOR_LOOK["metal_saturation"])
        # no cut where the game does not test the alpha
        scalar("Cutoff", f.get("_Cutoff", 0.5) if f.get("_EnableAlphaTest", 0.0) > 0.5 or "_ALPHATEST_ON" in d.get("keywords", []) else 0.0)
        e = c.get("_EmissionColor", [0, 0, 0, 1])
        if max(e[:3]) > 0.0 and f.get("_EnableEmission", 1.0) > 0.5:
            if not tex("EmissionMap", "_EmissionMap"):
                mel.set_material_instance_texture_parameter_value(mi, "EmissionMap", masters["_white"])
            vector("EmissionColor", (e[0], e[1], e[2], 1.0))
    elif kind in ("lit", "masked", "glass"):
        tex("BaseMap", "_BaseMap", "_MainTex")
        tex("NormalMap", "_BumpMap")
        tex("MaskMap", "_MetallicGlossMap")
        vector("BaseColor", linear_rgba(base_color))
        scalar("Metallic", f.get("_Metallic", 0.0))
        scalar("Smoothness", f.get("_Smoothness", 0.5))
        scalar("OcclusionStrength", f.get("_OcclusionStrength", 1.0))
        scalar("BumpScale", f.get("_BumpScale", 1.0))
        t = tiling.get("_BaseMap")
        if t:
            vector("Tiling", (t[0], t[1], t[2], t[3]))
        e = c.get("_EmissionColor", [0, 0, 0, 1])
        lit_up = (tex("EmissionMap", "_EmissionMap") or max(e[:3]) > 0.0) and f.get("_EnableEmission", 1.0) > 0.5
        if lit_up:
            if "_EmissionMap" not in textures:
                mel.set_material_instance_texture_parameter_value(mi, "EmissionMap", masters["_white"])
            vector("EmissionColor", (e[0], e[1], e[2], 1.0))       # an HDR colour: stored linear
        if kind == "masked":
            scalar("Cutoff", f.get("_Cutoff", 0.5))
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi, only_if_is_dirty=False)
    return mi, kind
