"""Side by side: ab_sheet.py <folder A> <folder B> <out.jpg> [name ...]   (A on the left, B on the right, one row a shot)"""
import os, sys
from PIL import Image, ImageDraw
a, b, out = sys.argv[1:4]
names = sys.argv[4:] or sorted(f[:-4] for f in os.listdir(a) if f.endswith(".png") and os.path.isfile(os.path.join(b, f)))
W, H = 800, 450
sheet = Image.new("RGB", (W * 2 + 8, (H + 4) * len(names)), (16, 16, 18))
for i, n in enumerate(names):
    for j, folder in enumerate((a, b)):
        im = Image.open(os.path.join(folder, n + ".png")).convert("RGB").resize((W, H))
        d = ImageDraw.Draw(im)
        label = "%s  %s" % (n, os.path.basename(folder.rstrip("/\\")).split("_")[-1])
        d.rectangle([0, 0, 8 + 7 * len(label), 14], fill=(0, 0, 0)); d.text((4, 2), label, fill=(255, 255, 0))
        sheet.paste(im, (j * (W + 8), i * (H + 4)))
sheet.save(out, quality=90)
print(out, sheet.size)
