"""Redraw the v06 master so her masses survive at the female mage's 95 px body.

Measured against native frame 10 (fractions of height): head 0-0.16, waist 0.33, skirt hem 0.67,
skirt width about 0.37. Height ratios already matched; what failed at game size was thin legs,
a narrow skirt, a long flat tail and hair with no visible light-blue area.
Usage: python fatfish_fit_master.py <name>   (each name is submitted once, about $0.2)
"""
from __future__ import annotations

import sys

from PIL import Image

import fatfish_doll_parts as P
from fatfish_final import OUT

RUN = OUT / "parts"
P.RUN = RUN
P.JOURNAL = RUN / "journal.json"
GROK = P.ROOT / "output/Fatfish_Grok_Walk_Test_v01/walk_in_npk_3x.png"

PROMPT = """Full-body character art for a 2D action game, used as the appearance master for animation at very small size, so every shape must be large and readable.

Image 1 is the identity and costume authority: same whale-girl maid, same face, headband, bow, whale-fin ears, outfit details and line style. Redraw her with the changed proportions below.
Image 2 is the exact silhouette to match: same three-quarter view facing RIGHT, same height ratios, same wide bell-shaped skirt, same sturdy legs and big shoes. Copy only pose and silhouette, none of its colors, hair, hat or costume.
Image 3 shows the rich hair volume and bright blue fade to aim for. Copy only hair fullness and color, not its rendering style.

Proportions, as fractions of total height from the top of her hair to the soles of her shoes:
- Head with hair ends at the chin at 0.16. Normal head, NOT chibi and not enlarged.
- Waist at 0.33. Skirt hem at 0.67.
- Skirt: wide bell shape, as wide as 0.40 of her height at the hem, with a broad white frilled hem.
- Legs: visibly sturdy white stockings, each leg as wide as 0.055 of her height at the calf, not thin lines.
- Shoes: chunky navy Mary Jane shoes, each about 0.13 of her height long, with thick soles and gold buckles.
- Sleeves: full puffed navy sleeves and wide white frilled cuffs.

Hair: thick, voluminous, very long wavy hair behind her back, reaching mid-thigh, deep blue at the top and fading to a large clearly visible area of bright sky blue over the lower half. Big clean locks. The hair mass may extend behind her up to 0.18 of her height, and it never covers the front of her body.

Tail: a short, chubby navy whale tail with pale lavender belly, coming out from under the back of the skirt and hanging DOWN close behind her legs, its fluke ending near ankle height. It extends behind her no more than 0.20 of her height. Never long, never thin, never horizontal.

Colors: use a medium royal navy, clearly lighter than black, so it stays blue at small size. Keep large areas of pure white apron and sky-blue hair. Gold buttons, trim and bows are few and large.

Outfit is modest: closed high collar, covered shoulders, long sleeves, knee-length skirt, white apron with the small blue whale emblem, big white bow at the back of the waist.

Style: clean cel shading, bold dark navy outlines of even weight around every shape, flat saturated colors. No painterly texture, no pixel art.
Fill most of the image height, head and feet fully visible with a small margin. Background: completely flat uniform medium gray, RGB 128 128 128. No shadow, no floor, no effects, no text.
"""


REFINE = """Full-body character art for a 2D action game, used as the appearance master for animation at very small size.

Image 1 is the authority for hair, colors, costume details and line style: keep its thick wavy hair with the large bright sky-blue fade, its medium royal navy, large white apron, and its clean bold outlines.
Image 2 is the authority for body proportions and stance: same small head, same long neckline-to-waist, same long legs, same height of every landmark, standing straight in three-quarter view facing RIGHT with both arms relaxed at her sides. Image 1's head is too big, its skirt too wide and too long, its legs too short: do not copy those.

Measured targets, as fractions of total height from the top of her hair to the soles of her shoes:
- Chin at 0.16: the head with hair is exactly one sixth of her height. Small head, normal proportions, NOT chibi.
- Waist at 0.33. Skirt hem at 0.65. Long legs below the hem take the remaining 0.35.
- Skirt width at the hem: 0.40 of her height, a gentle bell shape, narrower than Image 1.
- Each leg in white stockings is slightly thicker than Image 2, about 0.05 of her height at the calf. Both feet close together.
- Navy Mary Jane shoes with LOW flat soles and gold buckles, each about 0.11 of her height long. No high heels, no platform.

Hair: as in Image 1, behind her back down to mid-thigh, reaching behind her at most 0.18 of her height, never covering the front of her body.
Tail: short chubby navy whale tail with pale lavender belly, as in Image 1, coming out from under the back of the skirt and hanging down close behind her legs, fluke ending near ankle height. Fully visible and separate from the hair.

Outfit stays modest: closed high collar, covered shoulders, long puffed navy sleeves with white frilled cuffs, white apron with the small blue whale emblem, big white bow at the back of the waist, few large gold details.

Style: clean cel shading, bold dark navy outlines of even weight, flat saturated colors. No painterly texture, no pixel art.
Fill most of the image height, head and feet fully visible with a small margin. Background: completely flat uniform medium gray, RGB 128 128 128. No shadow, no floor, no effects, no text.
"""


def grok_ref():
    path = RUN / "refs/grok_hair.png"
    if not path.exists():
        crop = Image.open(GROK).convert("RGB").crop((70, 40, 290, 345))
        crop.resize((crop.width * 3, crop.height * 3), Image.Resampling.NEAREST).save(path)
    return path


def main(name):
    (RUN / "prompts").mkdir(exist_ok=True)
    if name == "fit_a":
        prompt, refs = PROMPT, [RUN / "raw/master_0.png", RUN / "refs/pose_10.png", grok_ref()]
    else:
        prompt, refs = REFINE, [RUN / "raw/fit_a_0.png", RUN / "raw/master_0.png"]
    (RUN / "prompts" / f"{name}.txt").write_text(prompt, "utf-8")
    raise SystemExit(P.submit(name, prompt, refs, "1:1", resolution="1k", background="opaque"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1])
