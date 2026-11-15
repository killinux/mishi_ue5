"""Contact sheet of a folder of look-dev stills (Saved/MishiShots/<slice>_<tag>/*.png), each labelled with its file name -
or, with --film, of a recorded tour (Saved/MishiTour/<slice>: timeline.json + frame_*.bmp): some frames of every shot.

    python Tools/sheet.py Saved/MishiShots/eros15_07_v3 [--cols 3] [--width 800] [--out sheet.jpg] [name ...]
    python Tools/sheet.py Saved/MishiTour/eros15_07 --film [--per-shot 3] [--cols 6] [--width 480]

With names, only those shots (file stems) in that order.  System Python with Pillow (not Unreal's).
"""
import argparse
import json
import os

from PIL import Image, ImageDraw


def tile(path, label, width):
    im = Image.open(path).convert("RGB")
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 7 * len(label) + 10, 16], fill=(0, 0, 0))
    d.text((5, 3), label, fill=(255, 255, 0))
    return im


def film_frames(folder, per_shot):
    """(file, label) of per_shot frames spread over every shot of the recording (the first one a frame after the cut)."""
    with open(os.path.join(folder, "timeline.json"), encoding="utf-8") as f:
        timeline = json.load(f)
    shots, total = timeline["shots"], timeline["frames"]
    out = []
    for i, s in enumerate(shots):
        end = shots[i + 1]["frame"] if i + 1 < len(shots) else total
        for k in range(per_shot):
            n = s["frame"] + 1 + round((end - s["frame"] - 3) * k / max(per_shot - 1, 1))
            for ext in (".bmp", ".png"):
                path = os.path.join(folder, "frame_%05d%s" % (n, ext))
                if os.path.isfile(path):
                    out.append((path, "%s %d" % (s["name"], n)))
                    break
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder")
    ap.add_argument("names", nargs="*")
    ap.add_argument("--film", action="store_true", help="the folder is a recorded tour: frames of every shot from timeline.json")
    ap.add_argument("--per-shot", type=int, default=3)
    ap.add_argument("--cols", type=int, default=0)
    ap.add_argument("--width", type=int, default=0, help="width of one tile in pixels")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if args.film:
        items = film_frames(args.folder, args.per_shot)
        cols, width = args.cols or 6, args.width or 480
    else:
        files = sorted(f for f in os.listdir(args.folder) if f.lower().endswith(".png"))
        if args.names:
            files = [n + ".png" for n in args.names if os.path.isfile(os.path.join(args.folder, n + ".png"))]
        items = [(os.path.join(args.folder, f), os.path.splitext(f)[0]) for f in files]
        cols, width = args.cols or 3, args.width or 800
    if not items:
        raise SystemExit("no stills in " + args.folder)
    tiles = [tile(path, label, width) for path, label in items]
    cols = min(cols, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    th = max(t.height for t in tiles)
    sheet = Image.new("RGB", (cols * width, rows * th), (24, 24, 28))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * width, (i // cols) * th))
    out = args.out or os.path.join(args.folder, "_sheet.jpg")
    sheet.save(out, quality=90)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
