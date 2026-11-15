"""Mishi UE5: the materials of the skills' baked effects.

The game's effects use four particle shaders (Pinkcore/Particles/*; the Unity project's Assets/RoeFighter/Shaders/RoeParticle*.shader
are line-by-line rebuilds of them, and the source of what is here).  The game module draws the baked geometry into a procedural
mesh and hands each vertex what those shaders read (Source/MishiUE/MishiFx.cpp):

    UV0      the particle's uv (Unity's: v up - flipped here at each sample)
    UV1      the uv scroll / offset the particle's custom data gives     (UnlitMaster: TEXCOORD1.xy; the older ones: TEXCOORD0.zw)
    UV2      UnlitMaster: (dissolve amount, distortion strength)          (the older ones: TEXCOORD1.xy)
    UV3      UnlitMaster's emission colour (TEXCOORD2.rgb, HDR): x = red + green + blue, y = its hue as one whole number
             (45 x the red share + the green share, in 44ths; the mesh's UVs are 16-bit floats, so nothing finer fits)
    normal   the surface's own normal: what faces the camera has it towards the camera
    colour   the particle's colour and alpha

Masters (in /Game/Mishi/Materials, unlit, two-sided):

    M_Mishi_FxMaster_*    Pinkcore/Particles/UnlitMaster: the offset goes to one of base / dissolve / distortion map, the base
                          uv pushed by the distortion map, dissolve with a glowing edge, multiply / subtractive colour, alpha
                          mask, alpha test, soft particles, emission (self / Fresnel).  _Alpha = translucent, _Add = additive:
                          this shader alone takes its blend from the material
    M_Mishi_FxDefault     Pinkcore/Particles/Default: scrolled texture x colour + _Emissive
    M_Mishi_FxMutate      Pinkcore/Particles/MutateDistortion: (texture + _Emissive) x colour, the texture pushed by a flowing
                          map and cut by a dissolve map (its bending of the picture behind is not used by this game's effects)
    M_Mishi_FxDistort     Pinkcore/Particles/Distortion: the picture behind, pushed about by a normal map (shock waves, haze)

The three older shaders always blend by alpha, whatever _SrcBlend / _DstBlend their materials still carry (the game's shader data
says so: tools/shader_asm.py of the Unity project).  The game culls faces by the material's _Cull; the masters do it by the
normal (it agrees with the winding on every baked mesh), since a slash seen from behind is drawn by another, darker mesh and a
glowing shell must not show its inside.

step() imports the effect textures (clamped where the game clamps them: a streak passes once as its uv scrolls) and makes one
instance per game material, MI_fx_<name> in /Game/Mishi/<slice>/Fx.
"""
import json
import os

import unreal

import mishi_materials as mm
from mishi_materials import F1, F2, F3, Graph, S, asset_tools, eal, mel, setp

VERSION = 4
# how the effects sit in this scene's exposure: x the whole colour, x the HDR emission colours on top of that
FX_LOOK = {
    "brightness": 1.0,
    # The game's emission colours are HDR, up to (58, 9, 7).  Under this scene's exposure and tone curve everything above ~3
    # is white: at 1 a spark was a white shard with no colour left.  At 0.3 the cores are still white-hot and the falling
    # edges keep the colour.
    "emission": 0.3,
}
FLIP = "float2((%s).x, 1.0 - (%s).y)"
# the emission colour out of UV3 (see MishiFx.cpp)
HUE = """
float hue = floor(EmissionBright.y + 0.5);
float hueR = floor(hue / 45.0);
float hueG = hue - hueR * 45.0;
float3 emission = float3(hueR, hueG, max(44.0 - hueR - hueG, 0.0)) / 44.0 * EmissionBright.x * Bright.y;
"""
# the game's Cull (0 off, 1 front, 2 back), by the normal
CULL = """
float facing = dot(normalize(Surface), normalize(ToCamera));
if ((Cull > 1.5 && facing < 0.0) || (Cull > 0.5 && Cull < 1.5 && facing > 0.0))
    alpha = 0.0;
"""


def log(msg):
    unreal.log("[MISHI] " + msg)


def _base(name, additive, before_dof=False):
    g = Graph(name, shading=unreal.MaterialShadingModel.MSM_UNLIT,
              blend=unreal.BlendMode.BLEND_ADDITIVE if additive else unreal.BlendMode.BLEND_TRANSLUCENT, two_sided=True)
    if before_dof:
        setp(g.mat, "translucency_pass", unreal.MaterialTranslucencyPass.MTP_BEFORE_DOF)
    return g


def _soft(g):
    """Soft particles: fades where the effect comes close to what is behind it (SoftDistance cm; next to nothing = off)."""
    dist = g.scalar("SoftDistance", 0.01)
    n = g.node(unreal.MaterialExpressionDepthFade, -1500)
    mel.connect_material_expressions(dist, "", n, "FadeDistance")
    return n


def _facing(g):
    """What the cull needs: the surface's normal, the way to the camera, the game's _Cull."""
    return [("Surface", g.node(unreal.MaterialExpressionVertexNormalWS, -2300), ""), ("ToCamera", g.node(unreal.MaterialExpressionCameraVectorWS, -2300), ""),
            ("Cull", g.scalar("Cull", 0.0), "")]


def build_master(d, name, additive):
    g = _base(name, additive)
    uv0, uv1, uv2, uv3 = g.uv(0), g.uv(1), g.uv(2), g.uv(3)
    colour = g.node(unreal.MaterialExpressionVertexColor, -2300)
    base = g.tex_object("BaseMap", d["mask"], S.SAMPLERTYPE_MASKS)
    base_srgb = g.scalar("BaseSRGB", 0.0)
    dissolve = g.tex_object("DissolveMap", d["mask"], S.SAMPLERTYPE_MASKS)
    distort = g.tex_object("DistortionMap", d["mask"], S.SAMPLERTYPE_MASKS)
    mask = g.tex_object("AlphaMask", d["mask"], S.SAMPLERTYPE_MASKS)
    tiling = g.vector("Tiling", (1, 1, 1, 1))                   # base.xy, dissolve.xy
    tiling2 = g.vector("Tiling2", (1, 1, 1, 1))                 # distortion.xy, alpha mask.xy
    option = g.vector("OffsetOption", (1, 0, 0, 0))
    dis = g.vector("Dissolve", (0, 0, 0.001, 0.001))            # on, mode, softness, edge softness
    dis_width = g.scalar("DissolveWidth", 0.0)
    distort_on = g.scalar("DistortionOn", 0.0)
    cutoff = g.scalar("Cutoff", -1.0)                           # what is at or under it is not drawn; under 0 = nothing is cut
    opaque = g.scalar("Opaque", 0.0)                            # the game material's blend is One Zero: what is drawn covers
    modes = g.vector("Modes", (0, 0, 0.5, 0.1))                 # colour mode (1 subtractive), emission mode (1 self, 2 fresnel), fresnel middle, softness
    bright = g.vector("Brightness", (1, 1, 0, 0))               # whole, emission
    soft = _soft(g)
    code = HUE + """
float2 off = Offset;
float2 uvB = UV * Tiling.xy + off * Option.x;
float2 uvD = UV * Tiling.zw + off * Option.y;
float2 uvN = UV * Tiling2.xy + off * Option.z;
float2 uvM = UV * Tiling2.zw;
float amount = saturate(Amounts.x);
float strength = saturate(Amounts.y);
if (DistortionOn > 0.5)
{
    // the game packs its distortion normals the DXT5nm way: x = r * a, y = g
    float4 n = Texture2DSample(DistortTex, DistortTexSampler, FLIPN);
    uvB += strength * (float2(n.r * n.a, n.g) * 2.0 - 1.0);
}
float4 base = Texture2DSample(BaseTex, BaseTexSampler, FLIPB);
if (BaseSRGB > 0.5)
    base.rgb = pow(max(base.rgb, 0.0), 2.2);
float alpha = base.a;
float3 edge = 0.0;
if (Dis.x > 0.5)
{
    float band = Dis.z + Width;
    float front = (band + 1.001) * amount;
    float v = Texture2DSample(DissolveTex, DissolveTexSampler, FLIPD).r;
    v = lerp(v, v * base.a, Dis.y);
    alpha *= smoothstep(front - band, front - Width, v);
    if (Width > 0.0)
        edge = smoothstep(0.0, 1.0, saturate((front - v) / max(Dis.w, 1e-4))) * emission;
}
alpha *= Soft;
alpha *= Texture2DSample(MaskTex, MaskTexSampler, FLIPM).r * ColourA;
if (Cutoff >= 0.0 && alpha <= Cutoff)
    alpha = 0.0;
else if (Opaque > 0.5)
    alpha = 1.0;
""" + CULL + """
float3 rgb = Modes.x > 0.5 ? saturate(base.rgb - Colour.rgb) : saturate(base.rgb * Colour.rgb);
rgb += edge;
if (Modes.y > 1.5)
{
    float rim = 1.0 - saturate(facing);
    rgb += emission * smoothstep(Modes.z - Modes.w, Modes.z + Modes.w, rim);
}
else if (Modes.y > 0.5)
    rgb += emission;
Opacity = saturate(alpha);
return rgb * Bright.x * (Additive > 0.5 ? Opacity : 1.0);
"""
    code = code.replace("FLIPN", FLIP % ("uvN", "uvN")).replace("FLIPB", FLIP % ("uvB", "uvB")).replace("FLIPD", FLIP % ("uvD", "uvD")).replace(
        "FLIPM", FLIP % ("uvM", "uvM"))
    additive_flag = g.const(1.0 if additive else 0.0)
    c = g.custom(code, [("UV", uv0, ""), ("Offset", uv1, ""), ("Amounts", uv2, ""), ("EmissionBright", uv3, ""), ("Colour", colour, ""), ("ColourA", colour, "A"),
                        ("BaseTex", base, ""), ("DissolveTex", dissolve, ""), ("DistortTex", distort, ""), ("MaskTex", mask, ""),
                        ("Tiling", tiling, "RGBA"), ("Tiling2", tiling2, "RGBA"), ("Option", option, "RGBA"), ("Dis", dis, "RGBA"), ("Width", dis_width, ""),
                        ("DistortionOn", distort_on, ""), ("Cutoff", cutoff, ""), ("Opaque", opaque, ""), ("Modes", modes, "RGBA"), ("Bright", bright, "RGBA"),
                        ("Soft", soft, ""), ("Additive", additive_flag, ""), ("BaseSRGB", base_srgb, "")] + _facing(g),
                 F3, [("Opacity", F1)], "fx master")
    g.out(c, "", "EmissiveColor")
    if additive:
        g.out(g.const(1.0, x=-450), "", "Opacity")
    else:
        g.out(c, "Opacity", "Opacity")
    return g.finish()


def build_default(d, name):
    g = _base(name, False)
    uv0, uv1 = g.uv(0), g.uv(1)
    colour = g.node(unreal.MaterialExpressionVertexColor, -2300)
    base = g.tex_object("BaseMap", d["mask"], S.SAMPLERTYPE_MASKS)
    base_srgb = g.scalar("BaseSRGB", 0.0)
    tiling = g.vector("Tiling", (1, 1, 0, 0))
    speed = g.vector("Speed", (0, 0, 0, 0))
    emissive = g.vector("Emissive", (0, 0, 0, 1))
    cutoff = g.scalar("Cutoff", -1.0)
    bright = g.vector("Brightness", (1, 1, 0, 0))
    soft = _soft(g)
    code = """
float2 uv = UV * Tiling.xy + Scroll * Speed.xy;
float4 t = Texture2DSample(BaseTex, BaseTexSampler, FLIPU);
if (BaseSRGB > 0.5)
    t.rgb = pow(max(t.rgb, 0.0), 2.2);
float alpha = t.a * ColourA;
if (Cutoff >= 0.0 && alpha < Cutoff)
    alpha = 0.0;
alpha *= Soft;
""" + CULL + """
Opacity = saturate(alpha);
return (t.rgb * Colour.rgb + Emissive.rgb * Bright.y) * Bright.x;
"""
    code = code.replace("FLIPU", FLIP % ("uv", "uv"))
    c = g.custom(code, [("UV", uv0, ""), ("Scroll", uv1, ""), ("Colour", colour, ""), ("ColourA", colour, "A"), ("BaseTex", base, ""),
                        ("Tiling", tiling, "RGBA"), ("Speed", speed, "RGBA"), ("Emissive", emissive, ""), ("Cutoff", cutoff, ""), ("Bright", bright, "RGBA"),
                        ("Soft", soft, ""), ("BaseSRGB", base_srgb, "")] + _facing(g),
                 F3, [("Opacity", F1)], "fx default")
    g.out(c, "", "EmissiveColor")
    g.out(c, "Opacity", "Opacity")
    return g.finish()


def build_mutate(d, name):
    """MutateDistortion without its screen part: this game's effects give it no screen normal map, and without one it comes to
    (texture + emissive) x colour over what is behind, by the texture's alpha x the colour's."""
    g = _base(name, False)
    uv0, uv1, uv2 = g.uv(0), g.uv(1), g.uv(2)
    colour = g.node(unreal.MaterialExpressionVertexColor, -2300)
    time = g.node(unreal.MaterialExpressionTime, -2300)
    base = g.tex_object("BaseMap", d["mask"], S.SAMPLERTYPE_MASKS)
    base_srgb = g.scalar("BaseSRGB", 0.0)
    distort = g.tex_object("DistortionMap", d["mask_black"], S.SAMPLERTYPE_MASKS)
    dissolve = g.tex_object("DissolveMap", d["mask"], S.SAMPLERTYPE_MASKS)
    mask = g.tex_object("MaskMap", d["mask"], S.SAMPLERTYPE_MASKS)
    base_st = g.vector("BaseST", (1, 1, 0, 0))
    distort_st = g.vector("DistortST", (1, 1, 0, 0))
    dissolve_st = g.vector("DissolveST", (1, 1, 0, 0))
    mask_st = g.vector("MaskST", (1, 1, 0, 0))
    flow = g.vector("Flow", (0, 0, 0, 0))                       # base map's scroll by the custom data .xy, the distortion map's by time .zw
    params = g.vector("Mutate", (0, 0.5, 0, 0))                 # base map distortion on, its strength, dissolve on, mask on
    emissive = g.vector("Emissive", (0, 0, 0, 1))
    bright = g.vector("Brightness", (1, 1, 0, 0))
    code = """
float2 uvB = UV * BaseST.xy + BaseST.zw + Scroll * Flow.xy;
if (Params.x > 0.5)
{
    float2 uvD = frac(Time * Flow.zw) + UV * DistortST.xy + DistortST.zw;
    uvB += Texture2DSample(DistortTex, DistortTexSampler, FLIPD).rg * Params.y;
}
float4 base = Texture2DSample(BaseTex, BaseTexSampler, FLIPB);
if (BaseSRGB > 0.5)
    base.rgb = pow(max(base.rgb, 0.0), 2.2);
float gone = 0.0;
if (Params.z > 0.5)
{
    float2 uvS = UV * DissolveST.xy + DissolveST.zw;
    gone = Texture2DSample(DissolveTex, DissolveTexSampler, FLIPS).r - Custom.y < 0.0 ? -1.0 : 0.0;
}
float alpha = saturate(gone + base.a) * ColourA;
if (Params.w > 0.5)
{
    float2 uvM = UV * MaskST.xy + MaskST.zw;
    alpha *= Texture2DSample(MaskTex, MaskTexSampler, FLIPM).r;
}
""" + CULL + """
Opacity = saturate(alpha);
return (base.rgb + Emissive.rgb * Bright.y) * Colour.rgb * Bright.x;
"""
    code = code.replace("FLIPD", FLIP % ("uvD", "uvD")).replace("FLIPB", FLIP % ("uvB", "uvB")).replace("FLIPS", FLIP % ("uvS", "uvS")).replace(
        "FLIPM", FLIP % ("uvM", "uvM"))
    c = g.custom(code, [("UV", uv0, ""), ("Scroll", uv1, ""), ("Custom", uv2, ""), ("Time", time, ""), ("Colour", colour, ""), ("ColourA", colour, "A"),
                        ("BaseTex", base, ""), ("DistortTex", distort, ""), ("DissolveTex", dissolve, ""), ("MaskTex", mask, ""),
                        ("BaseST", base_st, "RGBA"), ("DistortST", distort_st, "RGBA"), ("DissolveST", dissolve_st, "RGBA"), ("MaskST", mask_st, "RGBA"),
                        ("Flow", flow, "RGBA"), ("Params", params, "RGBA"), ("Emissive", emissive, ""), ("Bright", bright, "RGBA"),
                        ("BaseSRGB", base_srgb, "")] + _facing(g),
                 F3, [("Opacity", F1)], "fx mutate")
    g.out(c, "", "EmissiveColor")
    g.out(c, "Opacity", "Opacity")
    return g.finish()


def build_distort(d, name):
    """The picture behind the effect, read a little to the side: the scene colour at the pixel's place plus the normal map's push."""
    g = _base(name, False, before_dof=True)
    uv0, uv1 = g.uv(0), g.uv(1)
    colour = g.node(unreal.MaterialExpressionVertexColor, -2300)
    normal = g.tex_object("DistortNormalMap", d["mask"], S.SAMPLERTYPE_MASKS)
    mask = g.tex_object("ColorMask", d["mask"], S.SAMPLERTYPE_MASKS)
    tiling = g.vector("Tiling", (1, 1, 1, 1))                   # normal.xy
    speed = g.vector("Speed", (0, 0, 0, 0))
    params = g.vector("Distort", (0.1, 0, 0, 0))                # strength, mask on
    code = """
float2 uv = UV * Tiling.xy + Scroll * Speed.xy;
float4 n = Texture2DSample(NormalTex, NormalTexSampler, FLIPU);
float2 push = (float2(n.r * n.a, n.g) * 2.0 - 1.0) * Params.x;
float alpha = ColourA;
if (Params.y > 0.5)
    alpha *= Texture2DSample(MaskTex, MaskTexSampler, FLIPM).r;
""" + CULL + """
Opacity = saturate(alpha);
// (the screen's v runs down)
return float2(push.x, -push.y) * Opacity;
"""
    code = code.replace("FLIPU", FLIP % ("uv", "uv")).replace("FLIPM", FLIP % ("UV", "UV"))
    c = g.custom(code, [("UV", uv0, ""), ("Scroll", uv1, ""), ("ColourA", colour, "A"), ("NormalTex", normal, ""), ("MaskTex", mask, ""),
                        ("Tiling", tiling, "RGBA"), ("Speed", speed, "RGBA"), ("Params", params, "RGBA")] + _facing(g),
                 F2, [("Opacity", F1)], "fx distortion")
    scene = g.node(unreal.MaterialExpressionSceneColor, -500)
    setp(scene, "input_mode", unreal.MaterialSceneAttributeInputMode.OFFSET_FRACTION)
    ok = False
    for pin in ("Input", "OffsetFraction", "UVs", ""):
        if mel.connect_material_expressions(c, "", scene, pin):
            ok = True
            break
    if not ok:
        unreal.log_warning("[MISHI] %s: the scene colour node took no offset" % name)
    tinted = g.custom("return Scene * Colour;", [("Scene", scene, ""), ("Colour", colour, "")], F3, desc="tint", x=-300)
    g.out(tinted, "", "EmissiveColor")
    g.out(c, "Opacity", "Opacity")
    return g.finish()


MASTERS = ("M_Mishi_FxMaster_Alpha", "M_Mishi_FxMaster_Add", "M_Mishi_FxDefault", "M_Mishi_FxMutate", "M_Mishi_FxDistort")


def build_masters(defaults, force=False):
    stamp = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "MishiFxVersion.txt")
    have = ""
    if os.path.exists(stamp):
        with open(stamp) as f:
            have = f.read().strip()
    missing = [m for m in MASTERS if not eal.does_asset_exist("%s/%s" % (mm.MATS, m))]
    if force or missing or have != str(VERSION):
        log("building the effect masters (version %s -> %d, missing %d)" % (have or "none", VERSION, len(missing)))
        build_master(defaults, "M_Mishi_FxMaster_Alpha", False)
        build_master(defaults, "M_Mishi_FxMaster_Add", True)
        build_default(defaults, "M_Mishi_FxDefault")
        build_mutate(defaults, "M_Mishi_FxMutate")
        build_distort(defaults, "M_Mishi_FxDistort")
        with open(stamp, "w") as f:
            f.write(str(VERSION))
    return {m: unreal.load_asset("%s/%s.%s" % (mm.MATS, m, m)) for m in MASTERS}


def kind_of(d):
    shader = (d.get("shader") or "").split("/")[-1]
    return {"UnlitMaster": "master", "Distortion": "distort", "MutateDistortion": "mutate"}.get(shader, "default")


def blend_of(d):
    """'alpha', 'add' or 'opaque'.  Only UnlitMaster takes its blend from the material (Unity's blend factors: 10 = one minus
    the source's alpha, 0 = zero); the older shaders always blend by alpha."""
    if kind_of(d) != "master":
        return "alpha"
    dst = int(d.get("floats", {}).get("_DstBlend", 10))
    return "alpha" if dst == 10 else "opaque" if dst == 0 else "add"


def texture_roles(materials):
    """{file: role} over all the effect materials.  Every one is read as plain numbers: the game imports its effect textures
    without sRGB, the colour maps too (27 of a08's 28; the one that is not is squared up in the shader, BaseSRGB)."""
    roles = {}
    for d in materials.values():
        for slot, f in d.get("textures", {}).items():
            roles.setdefault(f, "mask")
    return roles


def make_instance(name, d, lookup, masters, folder, info=None):
    kind = kind_of(d)
    blend = blend_of(d)
    master = masters[{"distort": "M_Mishi_FxDistort", "mutate": "M_Mishi_FxMutate", "default": "M_Mishi_FxDefault"}.get(kind)
                     or ("M_Mishi_FxMaster_Add" if blend == "add" else "M_Mishi_FxMaster_Alpha")]
    inst = "MI_fx_" + mm.safe_name(name)
    path = "%s/%s" % (folder, inst)
    mi = unreal.load_asset(path) if eal.does_asset_exist(path) else asset_tools.create_asset(
        inst, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, master)
    mel.clear_all_material_instance_parameters(mi)
    textures, f, c, tiling, kw = d.get("textures", {}), d.get("floats", {}), d.get("colors", {}), d.get("tiling", {}), set(d.get("keywords", []))

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
        mel.set_material_instance_vector_parameter_value(mi, param, unreal.LinearColor(float(rgba[0]), float(rgba[1]), float(rgba[2]), float(rgba[3])))

    def st(slot):
        t = tiling.get(slot) or [1, 1, 0, 0]
        return t[0], t[1]

    def st4(slot):
        return tuple(tiling.get(slot) or [1, 1, 0, 0])

    soft = (f.get("_EnableSoftParticle", 0) > 0.5 or "_SOFTPARTICLES_ON" in kw)
    scalar("Cull", f.get("_Cull", 0.0))
    if kind != "distort":
        base_file = textures.get("_BaseMap") or textures.get("_MainTex")
        scalar("BaseSRGB", 1.0 if ((info or {}).get(base_file) or {}).get("srgb") else 0.0)
        vector("Brightness", (FX_LOOK["brightness"], FX_LOOK["emission"], 0, 0))
    if kind == "master":
        scalar("SoftDistance", max(f.get("_SoftParticlesFarFadeDistance", 1.0), 0.05) * 100.0 if soft else 0.01)
        tex("BaseMap", "_BaseMap")
        dissolve_on = ("DISSOLVE" in kw or f.get("_EnableDissolve", 0) > 0.5) and tex("DissolveMap", "_DissolveMap")
        distort_on = ("DISTORTION" in kw or f.get("_EnableBaseMapDistortion", 0) > 0.5) and tex("DistortionMap", "_DistortionMap")
        tex("AlphaMask", "_AlphaMask")
        vector("Tiling", st("_BaseMap") + st("_DissolveMap"))
        vector("Tiling2", st("_DistortionMap") + st("_AlphaMask"))
        vector("OffsetOption", c.get("_OffsetOption", [1, 0, 0, 0]))
        vector("Dissolve", (1.0 if dissolve_on else 0.0, f.get("_DissolveMode", 0.0), f.get("_DissolveSoftness", 0.001), f.get("_DissolveEdgeSoftness", 0.001)))
        scalar("DissolveWidth", f.get("_DissolveWidth", 0.0))
        scalar("DistortionOn", 1.0 if distort_on else 0.0)
        # (the game clips at the cutoff with alpha test on, and what a dissolve has taken away entirely without it)
        alpha_test = "_ALPHATEST_ON" in kw or f.get("_EnableAlphaTest", 0) > 0.5
        scalar("Cutoff", f.get("_Cutoff", 0.5) if alpha_test else 1e-6 if dissolve_on else -1.0)
        scalar("Opaque", 1.0 if blend == "opaque" else 0.0)
        emission = 2.0 if "_EMISSIONMODE_FRESNEL" in kw else 1.0 if "_EMISSIONMODE_SELF" in kw else 0.0
        vector("Modes", (1.0 if "_COLORMODE_SUBTRACTIVE" in kw else 0.0, emission, f.get("_FresnelMiddle", 0.5), f.get("_FresnelSoftness", 0.1)))
    elif kind == "distort":
        tex("DistortNormalMap", "_DistortNormalMap", "_DistortionMap", "_BumpMap")
        mask_on = ("ALPHA_MASK" in kw or f.get("_EnableAlphaMask", 0) > 0.5) and tex("ColorMask", "_ColorMask", "_MaskMap")
        vector("Tiling", st("_DistortNormalMap") + (1, 1))
        vector("Speed", c.get("_Speed", [0, 0, 0, 0]))
        vector("Distort", (f.get("_DistortStrength", 0.1), 1.0 if mask_on else 0.0, 0, 0))
    elif kind == "mutate":
        tex("BaseMap", "_BaseMap")
        distort_on = "BASEMAP_DISTORTION" in kw and tex("DistortionMap", "_DistortionMap")
        dissolve_on = "COLOR_DISSOLVE" in kw and tex("DissolveMap", "_DissolveMap")
        mask_on = "ALPHA_MASK" in kw and tex("MaskMap", "_MaskMap")
        vector("BaseST", st4("_BaseMap"))
        vector("DistortST", st4("_DistortionMap"))
        vector("DissolveST", st4("_DissolveMap"))
        vector("MaskST", st4("_MaskMap"))
        flow, distort_flow = c.get("_FlowSpeed", [0, 0, 0, 0]), c.get("_DistortFlowSpeed", [0, 0, 0, 0])
        vector("Flow", (flow[0], flow[1], distort_flow[0], distort_flow[1]))
        vector("Mutate", (1.0 if distort_on else 0.0, f.get("_DistortStrength", 0.5), 1.0 if dissolve_on else 0.0, 1.0 if mask_on else 0.0))
        e = c.get("_Emissive", [0, 0, 0, 1])
        vector("Emissive", (e[0], e[1], e[2], 1.0))
        if "_DistortNormalMap" in textures:
            unreal.log_warning("[MISHI] %s bends the picture behind it (MutateDistortion's screen normal map): not drawn" % name)
    else:
        scalar("SoftDistance", 0.01)
        tex("BaseMap", "_BaseMap", "_MainTex")
        vector("Tiling", st("_BaseMap") + (0, 0))
        vector("Speed", c.get("_Speed", [0, 0, 0, 0]))
        e = c.get("_Emissive", [0, 0, 0, 1])
        vector("Emissive", (e[0], e[1], e[2], 1.0))             # an HDR colour: stored linear
        scalar("Cutoff", f.get("_Cutoff", 0.5) if "_ALPHATEST_ON" in kw else -1.0)
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi, only_if_is_dirty=False)
    return mi, kind + {"add": "+", "opaque": "#"}.get(blend, "")


def step(src_dir, slice_folder, defaults, import_textures, warn, force=False):
    """Import <src_dir>/fx: its textures and one material instance per game material.  Returns the instances (MI_fx_*)."""
    fx = os.path.join(src_dir, "fx")
    path = os.path.join(fx, "fx_materials.json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        materials = json.load(f)
    info = {}
    if os.path.isfile(os.path.join(fx, "fx_textures.json")):
        with open(os.path.join(fx, "fx_textures.json"), encoding="utf-8") as f:
            info = json.load(f)
    folder = slice_folder + "/Fx"
    roles = texture_roles(materials)
    wanted = {"T_fx_" + mm.safe_name(os.path.splitext(f)[0]): (os.path.join(fx, "textures", f), role) for f, role in roles.items()}
    assets, imported = import_textures(wanted, folder)
    lookup = {}
    TA = unreal.TextureAddress
    for f in roles:
        tex = assets.get("T_fx_" + mm.safe_name(os.path.splitext(f)[0]))
        if tex is None:
            continue
        lookup[f] = tex
        meta = info.get(f) or {}
        want_x = TA.TA_CLAMP if meta.get("wrap_u") == "Clamp" else TA.TA_MIRROR if meta.get("wrap_u") == "Mirror" else TA.TA_WRAP
        want_y = TA.TA_CLAMP if meta.get("wrap_v") == "Clamp" else TA.TA_MIRROR if meta.get("wrap_v") == "Mirror" else TA.TA_WRAP
        if tex.get_editor_property("address_x") != want_x or tex.get_editor_property("address_y") != want_y:
            setp(tex, "address_x", want_x)
            setp(tex, "address_y", want_y)
            eal.save_loaded_asset(tex)
    masters = build_masters(defaults, force)
    out, kinds = [], {}
    for name, d in sorted(materials.items()):
        mi, kind = make_instance(name, d, lookup, masters, folder, info)
        out.append(mi)
        kinds[kind] = kinds.get(kind, 0) + 1
    log("effects: %d textures (%d imported), %d material instances %s" % (len(lookup), imported, len(out), kinds))
    return out


def load(slice_folder):
    folder = slice_folder + "/Fx"
    out = []
    if eal.does_directory_exist(folder):
        for p in eal.list_assets(folder, recursive=False, include_folder=False):
            a = unreal.load_asset(p)
            if isinstance(a, unreal.MaterialInstanceConstant) and a.get_name().startswith("MI_fx_"):
                out.append(a)
    return out
