"""Contact sheet of a folder of look-dev stills (Saved/MishiShots/<slice>_<tag>/*.png), each labelled with its file name.

    python Tools/sheet.py Saved/MishiShots/eros15_07_v3 [--cols 3] [--width 800] [--out sheet.jpg] [name ...]

With names, only those shots (file stems) in that order.  System Python with Pillow (not Unreal's).
"""
import argparse
import os

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder")
    ap.add_argument("names", nargs="*")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--width", type=int, default=800, help="width of one tile in pixels")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    files = sorted(f for f in os.listdir(args.folder) if f.lower().endswith(".png"))
    if args.names:
        files = [n + ".png" for n in args.names if os.path.isfile(os.path.join(args.folder, n + ".png"))]
    if not files:
        raise SystemExit("no stills in " + args.folder)
    tiles = []
    for f in files:
        im = Image.open(os.path.join(args.folder, f)).convert("RGB")
        h = round(im.height * args.width / im.width)
        im = im.resize((args.width, h), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 9 * len(f) + 10, 18], fill=(0, 0, 0))
        d.text((5, 3), os.path.splitext(f)[0], fill=(255, 255, 0))
        tiles.append(im)
    cols = min(args.cols, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    th = max(t.height for t in tiles)
    sheet = Image.new("RGB", (cols * args.width, rows * th), (24, 24, 28))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * args.width, (i // cols) * th))
    out = args.out or os.path.join(args.folder, "_sheet.jpg")
    sheet.save(out, quality=90)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
