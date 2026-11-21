"""NVIDIA's DLSS plugin into this project's Plugins folder (system Python; the editor closed):

    python Tools/install_dlss.py <the plugin's zip> [--frame-generation] [--docs <folder>] [--remove]

The zip is NVIDIA's "DLSS 4.5 plugin for Unreal Engine 5.8" (developer.nvidia.com/rtx/dlss - a public link, 1.2 GB; through
a slow proxy use `curl --noproxy "*"`).  It is NVIDIA's to give out, under their RTX SDK licence (Documentation/NVIDIA RTX
SDK EULA.pdf in the zip): Plugins/ is not in this repository.

  always               DLSS (super resolution, DLAA, ray reconstruction) + StreamlineNGXCommon
  --frame-generation   + StreamlineCore, StreamlineReflex, StreamlineDLSSG
  --docs <folder>      the zip's guides (PDF) written there
  --remove             takes out what this script puts in

MishiUE.uproject names these plugins as optional: without them the project opens and runs as before, and the picture
options (Source/MishiUE: the HUD's 画质 row, -MishiUpscale= on the command line) offer the engine's own TSR alone.
"""
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALWAYS = ["DLSS", "StreamlineNGXCommon"]
FRAME_GENERATION = ["StreamlineCore", "StreamlineReflex", "StreamlineDLSSG"]


def main():
    args = sys.argv[1:]
    remove = "--remove" in args
    docs = args[args.index("--docs") + 1] if "--docs" in args and args.index("--docs") + 1 < len(args) else None
    names = ALWAYS + (FRAME_GENERATION if "--frame-generation" in args or remove else [])
    words = [a for a in args if not a.startswith("--") and a != docs]
    target = os.path.join(ROOT, "Plugins")
    if remove:
        for n in names:
            d = os.path.join(target, n)
            if os.path.isdir(d):
                shutil.rmtree(d)
                print("removed", d)
        return 0
    if not words or not os.path.isfile(words[0]):
        print(__doc__)
        return 2
    os.makedirs(target, exist_ok=True)
    with zipfile.ZipFile(words[0]) as z:
        have = {i.filename.split("/")[1] for i in z.infolist() if i.filename.startswith("Plugins/") and i.filename.count("/") > 1}
        missing = [n for n in names if n not in have]
        if missing:
            print("not in this zip: %s (it has: %s)" % (", ".join(missing), ", ".join(sorted(have))))
            return 1
        for n in names:
            d = os.path.join(target, n)
            if os.path.isdir(d):
                shutil.rmtree(d)
            count = size = 0
            for i in z.infolist():
                if not i.filename.startswith("Plugins/%s/" % n) or i.is_dir():
                    continue
                rel = i.filename[len("Plugins/"):]
                out = os.path.normpath(os.path.join(target, rel))
                if not out.startswith(os.path.normpath(target) + os.sep):
                    raise ValueError("a path that leaves the folder: %r" % i.filename)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with z.open(i) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
                count += 1
                size += i.file_size
            print("%-22s %4d files, %5d MB -> %s" % (n, count, size >> 20, d))
        if docs:
            os.makedirs(docs, exist_ok=True)
            for i in z.infolist():
                if i.filename.lower().endswith(".pdf") and i.filename.count("/") <= 1:
                    out = os.path.join(docs, os.path.basename(i.filename))
                    with z.open(i) as src, open(out, "wb") as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
            print("guides ->", docs)
    return 0


sys.exit(main())
