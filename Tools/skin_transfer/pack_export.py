"""python -I Tools/skin_transfer/pack_export.py <Skin Textures zip> <Shaders zip> [--out _work/hs2/pack] [--only NAME ...]

The maps bake.py reads, taken out of Hanmen's NEXT-GEN downloads as PNG (system Python with UnityPy and Pillow).  The two
zips hold Sideloader zipmods, the zipmods Unity bundles, the bundles the textures; nothing is unpacked to disk on the way.
The pack is its author's work and is bought from him: its files stay on this machine (_work/ is not in the repository).

    Skin Textures v1.2:  [Hanmen] NEXT-GEN Textures v1.2.zipmod           nxtg_body: cf_nextgen_body_02_occ
                                                                           nxtg_head_00: cf_nextgen_head_00_00_n / _o / _t
                         [Hanmen] NEXT-GEN Textures NoMoles v1.2.zipmod   nxtg_body_02: cf_nextgen_body_02_t (the skin without moles)
    Shaders 4.15:        [Hanmen] NEXT-GEN Shaders 4.15 Beta.zipmod       nxtg-tex-body: cf_nextgen_body_base_n, SSA_Body, thickness_body_female
                                                                           nxtg-tex-wet: WetnessMap, WetnessFace
                                                                           nxtg-tex-head: thickness_head_female
"""
import argparse
import io
import os
import zipfile

import UnityPy

WANT = {
    "NEXT-GEN Textures v1.2.zipmod": {"abdata/chara/nxtg_body.unity3d": ["cf_nextgen_body_02_occ"],
                                      "abdata/chara/nxtg_head_00.unity3d": ["cf_nextgen_head_00_00_n", "cf_nextgen_head_00_00_o", "cf_nextgen_head_00_00_t"]},
    "NEXT-GEN Textures NoMoles v1.2.zipmod": {"abdata/chara/nxtg_body_02.unity3d": ["cf_nextgen_body_02_t"]},
    "NEXT-GEN Shaders": {"abdata/chara/nxtg-tex-body.unity3d": ["cf_nextgen_body_base_n", "SSA_Body", "thickness_body_female"],
                         "abdata/chara/nxtg-tex-wet.unity3d": ["WetnessMap", "WetnessFace"],
                         "abdata/chara/nxtg-tex-head.unity3d": ["thickness_head_female"]},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zips", nargs="+")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_work", "hs2", "pack"))
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    done = 0
    for path in a.zips:
        outer = zipfile.ZipFile(path)
        for entry in outer.namelist():
            key = next((k for k in WANT if k in entry and entry.endswith(".zipmod")), None)
            if key is None:
                continue
            inner = zipfile.ZipFile(io.BytesIO(outer.read(entry)))
            for bundle, names in WANT[key].items():
                names = [n for n in names if a.only is None or n in a.only]
                if not names or bundle not in inner.namelist():
                    continue
                env = UnityPy.load(inner.read(bundle))
                for obj in env.objects:
                    if obj.type.name != "Texture2D":
                        continue
                    t = obj.read()
                    if t.m_Name in names:
                        t.image.save(os.path.join(a.out, t.m_Name + ".png"))
                        print("%s  %d x %d  <- %s : %s" % (t.m_Name, t.m_Width, t.m_Height, os.path.basename(entry), bundle))
                        done += 1
    print("%d maps in %s" % (done, os.path.abspath(a.out)))


if __name__ == "__main__":
    main()
