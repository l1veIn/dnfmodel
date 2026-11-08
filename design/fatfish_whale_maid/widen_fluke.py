"""Widen only the fluke of master_d, locally and without an API call. Horizontal only, anchored near its inner edge, so hair and bow stay untouched."""
import os, sys
os.environ["PATCH_ID"] = "fatfish_whale_maid"
sys.path.insert(0, ".claude/skills/dnf-character-patch/scripts")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from kit.art import downscale, finish, grade, sharpen
from kit.config import P
from kit.review import _cool_hue
from kit.sheets import _cut_figure
from kit.source import native_world

DEV = P.out / "dev"
font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
SRC = P.parts / "raw/master_d_0.png"
OUT = P.parts / "raw/master_e_0.png"
a = np.asarray(Image.open(SRC).convert("RGB"), float)
bg = np.median(a[:8].reshape(-1, 3), axis=0)
fg = np.abs(a - bg).max(2) > 14

S, ANCHOR, Y_FULL, Y_BASE = 1.25, 300.0, 490.0, 522.0
X_CUT = 328
TOP = 435
# Only the part left of the anchor stretches. Above y 435 and right of the anchor nothing moves, so there is no cut edge and hair and bow cannot be touched.
print("foreground in the band above the fluke, x<300, y 435-444:", int(fg[TOP:445, 120:300].sum()))
Y, X = np.mgrid[TOP:int(Y_BASE), 100:int(ANCHOR)].astype(float)
scale = 1 + (S - 1) * np.clip((Y_BASE - Y) / (Y_BASE - Y_FULL), 0, 1)
sx = ANCHOR + (X - ANCHOR) / scale
out = a.copy()
for c in range(3):
    out[TOP:int(Y_BASE), 100:int(ANCHOR), c] = ndimage.map_coordinates(a[..., c], [Y, sx], order=3, mode="nearest")
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").save(OUT)

E = Image.open(OUT).convert("RGB")
m = np.abs(np.asarray(E, float) - bg).max(2) > 14
rows = np.nonzero(m[430:522, 120:X_CUT + 12].any(0))[0] + 120
print("new left edge", rows.min())
r, c = np.nonzero(m.any(1))[0], np.nonzero(m.any(0))[0]
print("bbox", int(c.min()), int(r.min()), int(c.max()), int(r.max()))
print("hue e", _cool_hue(E, flat_gray=True))
# Everything outside the tail must be the same as master_d.
diff = np.abs(np.asarray(E, float) - a).max(2) > 3
outside = diff.copy()
outside[425:530, 120:345] = False
print("changed pixels outside the fluke box", int(outside.sum()))

source = native_world(P.standing[0])
sprite = source.crop(source.getbbox())
target = int(round((source.getbbox()[3] - source.getbbox()[1]) * P.height_ratio))


def shrink(path):
    fig = _cut_figure(path)
    side = max(fig.size)
    square = Image.new("RGBA", (side, side))
    square.paste(fig, ((side - fig.width) // 2, side - fig.height))
    size = round(side * target / fig.height)
    color, al = downscale(square, (size, size))
    im = finish(sharpen(grade(color)), al)
    return im.crop(im.getbbox())


sd, se = shrink(SRC), shrink(OUT)
print("sprite", sprite.size, "d", sd.size, "e", se.size, "hue small e", _cool_hue(se))
z = 5
items = [("原版", sprite), ("master_d", sd), ("master_e 尾鳍放宽", se)]
panel = Image.new("RGB", (sum(i.width for _, i in items) * z + 30 * z, 105 * z), (86, 97, 122))
dd = ImageDraw.Draw(panel)
x = 6 * z
for label, im in items:
    big = im.resize((im.width * z, im.height * z), Image.NEAREST)
    panel.paste(big, (x, panel.height - big.height - 3 * z), big)
    dd.text((x, 4), label, fill="yellow", font=font)
    x += big.width + 8 * z
crop = E.crop((130, 380, 560, 800))
small1 = Image.new("RGB", ((sprite.width + se.width + 30) * 2, 110 * 2), (34, 40, 36))
xx = 10
for im in (sprite, se):
    big = im.resize((im.width * 2, im.height * 2), Image.NEAREST)
    small1.paste(big, (xx, small1.height - big.height - 6), big)
    xx += big.width + 20
canvas = Image.new("RGB", (panel.width + crop.width + 12, max(panel.height, crop.height)), (40, 44, 54))
canvas.paste(panel, (0, 0))
canvas.paste(crop, (panel.width + 12, 0))
canvas.save(DEV / "master_e_compare.png")
print(DEV)
