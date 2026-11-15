"""Mishi UE5 materials: the master materials (built in code, so they can be rebuilt and diffed) and the instances made from the
game's own material data.

Masters live in /Game/Mishi/Materials; each is a small graph round a Custom (HLSL) node feeding a MakeMaterialAttributes node:

  M_Mishi_Skin         ROE/Skin: Subsurface Profile (SSP_Mishi_Skin), base x tint, normal + the game's tiled detail normal (faded
                       with distance), MGAC (G gloss, B occlusion, A curvature), sweat and flush from MPC_Mishi (Wet, Flush)
  M_Mishi_Eye          Pinkcore/Heros/Eye rebuilt from its numbers: sclera / iris through the iris mask, the cornea's parallax,
                       the limbal ring, the lids' occlusion map - under a clear coat (the tear film: real highlights)
  M_Mishi_Hair         hair cards: Hair shading model (strand direction along the card's V), temporal dither for soft edges, a hard
                       mask in the shadow pass, the strand occlusion map
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

VERSION = 9
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
            eal.delete_asset(path)
        self.mat = asset_tools.create_asset(name, MATS, unreal.Material, unreal.MaterialFactoryNew())
        self.name = name
        self.rows = {}
        if shading is not None:
            setp(self.mat, "shading_model", shading)
        if blend is not None:
            setp(self.mat, "blend_mode", blend)
        if two_sided:
            setp(self.mat, "two_sided", True)
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
def ensure_mpc():
    """MPC_Mishi: what the couple drives through the scene - Wet (sweat), Flush (blush)."""
    path = MATS + "/MPC_Mishi"
    if eal.does_asset_exist(path):
        return unreal.load_asset(path)
    mpc = asset_tools.create_asset("MPC_Mishi", MATS, unreal.MaterialParameterCollection, unreal.MaterialParameterCollectionFactoryNew())
    params = []
    for name, value in (("Wet", 0.0), ("Flush", 0.0)):
        p = unreal.CollectionScalarParameter()
        p.set_editor_property("parameter_name", name)
        p.set_editor_property("default_value", value)
        params.append(p)
    setp(mpc, "scalar_parameters", params)
    eal.save_loaded_asset(mpc)
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
    # the pores are for close-ups: gone by 2.5 m, where they would only shimmer
    fade = g.custom("return Strength * saturate((400.0 - Depth) / 250.0);", [("Strength", dstrength, ""), ("Depth", depth, "")], F1,
                    desc="detail fade", x=-1500)
    nrm = g.custom(RNM, [("Base", normal, "RGB"), ("Detail", detail, "RGB"), ("Weight", fade, "")], F3, desc="normal + detail")
    mgac = g.tex("MaskMap", d["mask"], S.SAMPLERTYPE_MASKS, (uv, ""))
    smooth = g.scalar("Smoothness", 0.85)
    occ = g.scalar("OcclusionStrength", 0.7)
    spec = g.scalar("SpecularLevel", 0.45)
    scatter = g.scalar("Scatter", 0.85)
    gloss = g.scalar("GlossBoost", 1.12)
    wet_rough = g.scalar("WetRoughness", 0.2)
    flush_tint = g.vector("FlushTint", (1.0, 0.62, 0.60, 1.0))
    wet = g.collection(mpc, "Wet")
    flush = g.collection(mpc, "Flush")
    code = """
// MGAC: G gloss, B occlusion, A curvature (the thin, curved places: ears, nose, fingers - where blood shows and sweat gathers)
float3 col = Base * Tint;
float curve = Mgac.a;
col = lerp(col, col * FlushTint, saturate(Flush * (0.35 + 0.65 * curve)));
float rough = 1.0 - saturate(Mgac.g * Smooth * Gloss);
rough = lerp(rough, WetRough, saturate(Wet));
Roughness = rough;
AO = lerp(1.0, Mgac.b, Occ);
Specular = Spec * lerp(1.0, Mgac.b, 0.5) * (1.0 + 0.6 * saturate(Wet));
return col;
"""
    c = g.custom(code, [("Base", base, "RGB"), ("Tint", tint, ""), ("Mgac", mgac, "RGBA"), ("Smooth", smooth, ""), ("Occ", occ, ""),
                        ("Spec", spec, ""), ("Wet", wet, ""), ("Flush", flush, ""), ("WetRough", wet_rough, ""), ("FlushTint", flush_tint, ""),
                        ("Gloss", gloss, "")],
                 F3, [("Roughness", F1), ("AO", F1), ("Specular", F1)], "skin")
    g.out(c, "", "BaseColor")
    g.out(c, "Roughness", "Roughness")
    g.out(c, "AO", "AmbientOcclusion")
    g.out(c, "Specular", "Specular")
    g.out(nrm, "", "Normal")
    g.out(scatter, "", "Opacity")
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
    g.out(g.scalar("SpecularLevel", 0.45), "", "Specular")
    g.out(g.scalar("Roughness", 0.42), "", "Roughness")
    # the strands run up the cards' texture: the highlight is drawn out across them
    g.out(g.scalar("Anisotropy", 0.8), "", "Anisotropy")
    g.out(g.vector("StrandDirection", (0.0, 1.0, 0.0, 0.0)), "", "Tangent")
    normal = g.tex("NormalMap", d["flat"], S.SAMPLERTYPE_NORMAL, (uv, ""))
    bump = g.scalar("BumpScale", 1.0)
    g.out(g.custom("return normalize(float3(N.xy * Scale, N.z));", [("N", normal, "RGB"), ("Scale", bump, "")], F3, desc="strand normal"), "", "Normal")
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
    inst = "MI_" + safe_name(name)
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
        if tex("DetailNormalMap", "_DetailNormalMap"):
            scalar("DetailTiling", tiling.get("_DetailNormalMap", [100.0])[0])
            scalar("DetailStrength", f.get("_DetailBumpScale", 0.5))
        else:
            scalar("DetailStrength", 0.0)
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
