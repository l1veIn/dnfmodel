"""Per-sheet motions, settings and grip overrides for the rollout. Run from the project root, then make_sheets.py.

Written after reading each armed board. Cell numbers count from 1, in the sheet's frame order.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent

COMMON = (
    "Copy each cell's body angle, facing, lean and limb positions from Image 2: some cells turn away, lean far over, lie down or are in the air. "
    "The sprite's short dark skirt, red boots and gold pendants are not her costume: draw her own long skirt, apron and shoes from Image 1. "
    "Her skirt moves with her legs: when a leg lifts or strides, the hem lifts and opens so that leg in white tights and its shoe show where the sprite's leg and boot are, while the skirt and layered white ruffles always keep her hips covered. "
    "The sleeves stay joined to her shoulders. "
    "In every cell the short thick whale tail has exactly the size and shape it has in Image 1. It always grows from the back of her hips below the waist bow and turns with her body, never longer, thinner or detached, with the fluke visible; in fast moves it trails behind the motion. "
    "Seen from behind, the long hair falls down her back above the bow, the tail comes out below the bow, and her arms stay outside the hair. "
)

MOTIONS = {
    "run": "Cells 1 to 4 are one fast forward dash, almost the same pose: her whole body leans far forward to the right, the head at the upper right, the skirt streaming back and up to the left, one leg straight down below her with the shoe under the hem and the other foot just showing behind the hem, the near arm straight down along the skirt. Between these four cells only the hair ends, hem and fluke flutter differently. "
           "Cell 5: she leans right and winds up, the near arm raised high behind her head with a closed fist at the upper left. Cell 6: the same lean, the near fist comes down beside her head at the left. "
           "Cell 7: a flying lunge, both arms stretched straight to the right at shoulder height with one fist at the end, the rear leg kicked straight back to the left, the front leg bent down under her. Cell 8: the same flying lunge with both legs kicked back to the left.",
    "fall": "A forward dash that ends in a fall flat on her front. Cell 1: she leans right with the near arm raised high behind her head, closed fist at the upper left. Cell 2: the fist comes down beside her head at the left. "
            "Cell 3: a flying lunge, both arms straight to the right with a fist, the rear leg kicked back to the left, the front leg bent down. Cell 4: she flies forward, body sloping down to the right, arms straight to the right with a fist, both legs kicked back to the left. "
            "Cells 5, 6, 7 and 8: she has landed on her front with her face low at the lower right, both arms stretched out to the lower right with open hands, the skirt heaped over her hips and both legs bent up in the air at the upper left, shoes up. Cell 9: she lies nearly flat, her head and open hands at the right, her legs straight out to the left, the skirt mounded over her hips.",
    "smash": "Cell 1: she has turned away and stands on one straight leg, the near fist raised above her head, the other knee lifted forward under the skirt, the skirt flared out to the right. Cell 2: seen from behind on one straight leg, the arm hidden in front of her head with a fist at the left, the skirt flared right. Cell 3: the same from behind with the elbow up and a fist just left of her head. "
             "Cell 4: she swings round into a wide stride to the right, both arms straight out to the right at shoulder height with a fist at the end, feet far apart. "
             "Cell 5: a low wide lunge to the right, both arms pulled back across her chest with the fists at the left of her shoulder, the rear leg kicked out to the left, the front leg far to the lower right. Cells 6 and 7: the same lunge, both arms reaching back to the left above shoulder height with the fist at the far left, her head turned to the right.",
    "summon_a": "Cell 1: she stands on one leg, one arm raised straight up with an open hand, the other arm bent in front of her chest, the free leg lifted behind her to the right, the skirt swinging. Cell 2: seen from behind on one leg, one arm straight up, the free knee lifted at the right. Cell 3: she turns, one arm straight up with an open hand and the other across her chest, standing on one leg with the free leg straight out to the left. "
                "Cells 4, 5 and 6: she bends over in a deep forward bow with her head low at the right and both hands held at her middle, knees bent, feet apart, the skirt puffed up behind her. "
                "Cells 7 and 8: a deep crouch with her knees bent wide, the near arm down with the hand on her knee at the left, the far hand on her other knee at the right, her head up, the skirt pooled around her.",
    "summon_b": "Cell 1: both arms raised high in a wide V with open hands, her head up, the rear leg stepping back to the lower left and the front leg straight down. Cells 2, 3, 4 and 5: the same raised arms in a V tilted a little to the left, standing on one straight leg with the other foot just showing behind the hem, the hair ends and hem fluttering differently in each. "
                "Cell 6: both arms straight up above her head with her hands together, her head lowered, feet apart. Cells 7 and 8: she bends backward from the hips, her head at the upper left and both arms stretched straight out to the left with open hands, feet below her and the skirt at the right.",
    "jack": "Cells 1, 2, 3 and 4 are one held pose in mid air, as if sitting on nothing: her torso leans back, both hands reach forward to the right in front of her chest, both legs stretch forward and down to the lower right with the shoes at the far lower right, and the skirt hangs down at the left. Only hair ends, hem and fluke differ a little between them. "
            "Cell 5: standing feet apart, the far arm reaching forward to the right with the hand at waist height. Cell 6: the same with the hand a little further right. Cell 7: she turns towards the viewer with both hands crossing low in front of her waist, the skirt swinging to the right. Cell 8: one arm stretches far out to the left at shoulder height with an open hand, the other hand low at the right, standing on one leg with the other knee lifted out to the right and the shoe at the far right.",
    "kick": "Cell 1: one arm straight up with an open hand, the other low at the right, standing on one straight leg, the other knee lifted out to the right with the shoe at the far right, the skirt tilted. Cells 2, 3 and 4: one arm bent straight up above her head with a closed fist, the other hand low at the right touching the lifted knee, the shoe at the far right, standing on one straight leg, the skirt flared out wide and nearly level, its hem swinging a little differently in each. "
            "Cell 5: feet apart, one elbow raised with the fist above her head, the other arm out to the right with an open hand. Cell 6: a low twisting stride, her arms wrapped near her chest, her legs wide apart, the skirt swung out to the left. "
            "Cells 7 and 8: seen from behind at three-quarters, feet wide apart, one elbow bent behind her head at the left, the other arm stretched straight to the right with the palm up.",
    "jump_a": "Cells 1 and 2: seen from behind at three-quarters, feet wide apart, one elbow bent behind her head at the left, the other arm stretched straight to the right with the palm up. "
              "Cell 3: a crouch before jumping, knees bent and feet together, the near elbow back at the left with a fist at her waist, the far fist at chest height at the right, the skirt puffed out. Cell 4: rising, the same arms with her legs straightening and the feet off the ground. "
              "Cells 5 and 6: near the top of the jump, her torso bent forward, the near arm stretched back to the upper left with an open hand, the far fist raised at the upper right, the skirt nearly level, her legs together under it. "
              "Cells 7 and 8: both knees tucked up to the right as if sitting in the air, both hands together at her knees, her head above them, the skirt around her, the hair lifted upward.",
    "jump_b": "Cell 1: knees tucked up to the right as if sitting in the air, both hands together at her knees, the skirt around her, the hair lifted upward. Cell 2: falling with her legs straight down together, the near arm back at the left with a fist, the far fist out at the right. "
              "Cells 3 and 4: legs close together and a little bent, the near elbow back at the left with a fist at her waist, the far fist at chest height at the right, the skirt puffed out. Cell 5: the near arm reaching back to the left and the far fist out to the right, her legs below. "
              "Cells 6 and 7: her torso bent forward, the near arm stretched back to the upper left with an open hand, the far fist raised at the upper right, the skirt nearly level. "
              "Cell 8: her torso arches, the near arm raised high with a closed fist above her head, the skirt swung to the right, both legs down together.",
    "jump_c": "Cell 1: in mid air, the near fist beside her head at the left, her torso bent forward, the skirt hanging at the right, both knees bent under her. Cell 2: pitching forward, her hips high at the left, the near arm reaching down to the lower right with a closed fist, one knee lifted at the right. "
              "Cells 3 and 4: nearly upside-down in a flip with her hips and skirt at the upper left, the near arm straight down to the lower right with a closed fist, her head at the upper right, her legs bent out to the right. "
              "Cell 5: knees tucked as if sitting in the air, both hands together at her knees. Cell 6: falling with her legs together, the near arm back at the left and the far fist out at the right. Cell 7: landing crouch, legs close and bent, the near elbow back at the left and the far fist at chest height.",
    "lala_a": "Cells 1 and 2: standing with her legs apart, the free foot lifting at the lower right, the near arm reaching out to the left at waist height with a closed fist, and the far hand a closed fist in front of her belly. Cells 3 and 4: standing on one straight leg with the other leg out to the lower right, the near elbow up and back at the left with a fist at shoulder height, the skirt tilted. "
              "Cells 5, 6, 7 and 8: a low forward lunge, both arms stretched straight to the right at shoulder height with a closed fist at the end, her head low, the skirt streaming back nearly level to the left, the front leg down under her and only a foot showing behind the hem. Her hair streams to the left.",
    "lala_b": "Cells 1, 2, 3 and 4 are one long lunge: both arms stretched straight to the right at shoulder height with a closed fist at the end, her head low behind them, the rear leg stretched far to the lower left, the front knee bent, the skirt nearly level, only hair ends and hem fluttering differently. "
              "Cell 5: standing feet apart, facing right, one arm out to the lower right with a closed fist and the other raised with a fist in front of her face. Cell 6: facing left with both arms raised above her head to the right, the fists up, one foot lifted behind her. "
              "Cell 7: a wide stride, the near fist low at her left hip and the far arm stretched to the right at waist height with a closed fist. Cell 8: curled into a tumbling ball with her skirt round her, both arms straight down in front crossing at the wrists, one leg out to the lower left, her hair lifted.",
    "combo_a": "Cell 1: crouching very low, her arms wrapped round her waist with a closed fist at the left of her hip, her legs behind at the right. Cell 2: springing up, one fist at the upper right, the other at her waist, her legs together. Cell 3: upright on her legs with one fist beside her face at the right and the skirt round and full. "
               "Cell 4: a wide stride with both arms reaching forward to the right at chest height with a fist. Cells 5 and 6: a wide split stride with her feet far apart, both arms raised to the upper right with the fists about level with her head, hair streaming left. "
               "Cells 7 and 8: leaning forward on one straight leg, both fists together in front of her at the right, in cell 7 at chest height and in cell 8 near her head, the skirt flared to the left.",
    "combo_b": "Cell 1: her arms straight up overhead with closed fists, her head tilted down, standing on one straight leg with the skirt flared to the right. Cell 2: arching in the air with her fists behind her head at the left, her hips at the right and one knee bent forward with the shoe at the lower left. "
               "Cell 3: flying level to the right, arms straight to the right and low with a closed fist, both legs kicked back to the left, her hair lifted. Cell 4: curled into a ball with her skirt round her, one arm reaching diagonally to the lower left with a closed fist, one knee at the left. "
               "Cells 5, 6 and 7: a very low crouch, her arms wrapped round her waist with a closed fist at the left of her hip, her legs wide and bent, her head at the right, only the hair ends and hem differing a little.",
    "hit": "Cell 1 and cell 3 are the same pose: she recoils from a hit with her head thrown back and her eyes shut, both fists up near her face, her torso tilting back, her legs together. Cell 2 and cell 4 are the same pose: she arches further back to the left, her face up, one fist at her shoulder and the other low at her skirt. "
           "Cell 5: thrown down backwards, her head at the lower left, her body sloping up to the right, her legs at the right with shoes in the air, the skirt held around her thighs. Cells 6 and 7: lying flat on her back in the air with her head at the left and her legs straight out to the right, arms loose across her body, the skirt mounded over her hips, the hair hanging down at the left.",
    "star": "Cell 1: turned at three-quarters from behind, feet apart, the near arm bent up behind her with the open hand at the left of her shoulder, the far hand low at the right of her waist. Cells 2 and 3: the same stance, one arm stretched out to the left with the palm up, the other hand low at the right on the skirt, the hem swinging. "
            "Cells 4, 5, 6, 7 and 8: a balanced arabesque on one straight leg, her torso leaning forward to the right, the far arm stretched straight to the right with an open hand, the near fist raised beside her head at the left, and the free leg lifted far back to the left with the skirt tilted up with it. Only hair ends, hem and fluke differ between cells 5, 6 and 7.",
    "buff": "Cell 1: a balanced arabesque on one straight leg, her torso leaning forward to the right, the far arm stretched to the right with an open hand, the near fist beside her head, the free leg lifted back to the left. "
            "Cell 2: standing feet close, towards the viewer, the near arm down with the hand at the left of the skirt, the far hand raised at chest height at the right with one finger up. Cell 3: the near hand on her hip, the far hand raised beside her face at the right. Cell 4: the near hand on her hip, the far arm raised with the hand beside her head at the right. Cell 5: the near arm down, the far hand raised at shoulder height at the right. "
            "Cell 6: turning away on one straight leg, the near fist up at her head at the left, the other knee lifted forward with the skirt flared to the right. Cells 7 and 8: seen from behind on one straight leg, the arms hidden in front of her body except an elbow at the left in cell 8, the skirt flared to the right.",
    "whip": "Cell 1: a wide stride, one arm stretched to the right at chest height with a closed fist, feet far apart. Cell 2: the rear leg kicked out to the left, the front leg down to the right, both fists at her chest with the near elbow back at the left. Cells 3 and 4: the same legs, the near arm raised back to the upper left above her head with a fist, the other fist in front of her face, the skirt level. "
            "Cells 5, 6 and 7: a forward lunge on the front leg, both arms stretched straight to the right at shoulder height with a closed fist at the end, the rear knee bent high with the shoe up at the upper left, the skirt tilted forward.",
    "scholar": "Cell 1: a stride with her body twisted, both arms raised with the fists at head height at the left. Cell 2: a stride, both arms low in front of her at the waist with the fists at the left, her head at the right, feet apart. Cell 3: a very wide stride, both arms stretched to the upper right with a closed fist. "
               "Cell 4: standing on the front leg at the lower right, the rear leg kicked out to the left, both arms stretched to the left with a closed fist at about head height, her head at the upper right. Cell 5: on one straight leg with the other knee lifted behind her, the near arm stretched down to the left with a closed fist. Cell 6: a very wide stride to the lower left, both arms raised to the upper right with a closed fist. "
               "Cells 7 and 8: seen from behind, feet wide apart, both arms up in front of her head with the fists at the upper left of her head.",
    "knight": "Cell 1: at three-quarters, feet apart, one fist raised at chest height at the right and the other hand at her waist. Cell 2: facing the viewer, one arm across her waist, feet apart. Cells 3 and 4: facing the viewer, both forearms held level across her chest with her elbows out at shoulder height, feet together. "
              "Cell 5: facing right, the far hand reaching forward at waist height with an open hand. Cell 6: the far hand raised with an open palm at shoulder height at the right. Cell 7: both arms raised high in a wide V with open hands, feet together on her toes, her head forward. Cell 8: the far arm stretched to the lower right with an open hand and the near arm close beside it, feet apart.",
}

# The idles, measured on the source sprite. Standing: head and skirt sway against each other by one pixel while the toes stay planted; frames 10 and 12 are the same picture.
# Battle: nothing below the arms moves. Near arm (-1,0) (-1,1) (0,0.5), far hand (1,0.7) (1,1) (0.3,0.6), plus a little hair. Polygons are in the drawing's own pixels.
NEAR_ARM = [[438, 580], [485, 580], [485, 660], [470, 750], [415, 750], [412, 660]]
FAR_HAND = [[600, 555], [655, 555], [670, 670], [620, 670], [600, 610]]
FRONT_LOCK = [[485, 325], [515, 325], [518, 400], [485, 400]]
HAIR_ENDS = [[292, 460], [390, 460], [400, 540], [320, 550], [292, 520]]


def battle(near, far, hair):
    return {"moves": [{"poly": NEAR_ARM, "dx": near[0], "dy": near[1], "feather": 14}, {"poly": FAR_HAND, "dx": far[0], "dy": far[1], "feather": 14},
                      {"poly": FRONT_LOCK, "dx": hair, "feather": 14}, {"poly": HAIR_ENDS, "dx": -hair, "feather": 18}]}


# Standing idle, redesigned at the user's request. Copying the source's sway read as twisting, because head and skirt moved against each other. Moving only the tail and hair read as too stiff.
# So: her hands rest in front (a separate edited drawing, poses_idle_stand), and she rocks gently from the feet in one direction and breathes, with the tail and hair a beat apart. The feet stay planted.
FLUKE = [[235, 548], [345, 548], [345, 605], [315, 630], [280, 625], [235, 605]]
HAIR_TIPS = [[285, 445], [350, 445], [360, 535], [300, 545], [285, 500]]
AHOGE = [[435, 128], [512, 128], [512, 160], [470, 182], [435, 175]]
CHEST_LOCK = [[498, 320], [515, 320], [515, 392], [498, 392]]


def standing(tail, hair, ahoge, rock=0, breath=False):
    spec = {"moves": [{"poly": FLUKE, "dy": tail, "feather": 20}, {"poly": HAIR_TIPS, "dx": hair, "feather": 16},
                      {"poly": CHEST_LOCK, "dx": hair * 0.6, "feather": 10}, {"poly": AHOGE, "dx": ahoge, "feather": 10}]}
    if rock:
        spec["shear"] = [[0, rock], [0.5, rock * 0.6], [0.93, 0], [1, 0]]
    if breath:
        spec["lift"] = [[0, -0.7], [0.45, -0.7], [0.72, 0], [1, 0]]
    return spec


STAND_CLIPS = {"clip_010_013": [{"slot": i, "cell": 0} for i in range(10, 14)]}
STAND_MICRO = {"10": standing(0, 1, 0, breath=True), "11": standing(-2, 0, 0.8, rock=1.4), "12": standing(0, -1, 0, breath=True), "13": standing(1.5, 0, -0.8, rock=-1.4)}
IDLE_CLIPS = {"clip_014_017": [{"slot": i, "cell": 1} for i in range(14, 18)]}
IDLE_MICRO = {
    "15": battle((-1, 0), (1, 0.7), 0.6), "16": battle((-1, 1), (1, 1), 1), "17": battle((0, 0.5), (0.3, 0.6), 0.5),
}

SETTINGS = {
    "idle": {"clips": IDLE_CLIPS, "micro": IDLE_MICRO},
    # Drawn by editing the idle sheet (master_prompt_idle_stand.txt), so it keeps that sheet's layout; only its left cell is used.
    "idle_stand": {"frames": [12, 14], "cols": 2, "pad_x": 110, "ref_cells": [0, 1], "motion": "Edited from the idle sheet: see master_prompt_idle_stand.txt.", "clips": STAND_CLIPS, "micro": STAND_MICRO},
    "run": {"ref_cells": [0, 1, 2, 3], "mark_grips": True},
    "fall": {"ref_cells": [0, 1], "mark_grips": True},
    "smash": {"ref_cells": [1, 2, 3], "mark_grips": True},
    "summon_a": {"ref_cells": [3, 4, 5]},
    "jack": {"ref_cells": [4, 5, 6, 7]},
    "kick": {"ref_cells": [1, 2, 3, 4]},
    "jump_a": {"ref_cells": [0, 1, 2, 3]},
    "jump_b": {"ref_cells": [1, 2, 3, 4, 5, 6], "mark_grips": True},
    "jump_c": {"ref_cells": [5, 6], "mark_grips": True},
    "lala_a": {"mark_grips": True},
    "lala_b": {"ref_cells": [0, 1, 2, 3, 4, 6], "mark_grips": True},
    "combo_a": {"ref_cells": [1, 2, 3, 4, 5, 6, 7], "mark_grips": True},
    "combo_b": {"ref_cells": [0, 4, 5, 6], "mark_grips": True},
    "hit": {"ref_cells": [0, 1, 2, 3]},
    "whip": {"mark_grips": True},
    "scholar": {"mark_grips": True},
}

# The stowed rod only happens to touch her in these frames, so no fist belongs there.
# In 92 and 93 her foot covers the hand and the rod comes out from behind it: a dot there made the model draw a fist in place of the foot.
FALSE_GRIPS = [45, 78, 87, 92, 93, 133, 134, 138, 139, 140, 141, 142, 143]

(HERE / "motions.json").write_text(json.dumps({k: COMMON + v for k, v in MOTIONS.items()}, ensure_ascii=False, indent=1), "utf-8")
(HERE / "sheet_settings.json").write_text(json.dumps(SETTINGS, ensure_ascii=False, indent=1), "utf-8")
# Keep hand positions set by hand: only the false grips are generated here.
overrides = HERE / "hand_overrides.json"
hands = json.loads(overrides.read_text("utf-8")) if overrides.exists() else {}
hands["ignore"] = {str(i): [0] for i in FALSE_GRIPS}
overrides.write_text(json.dumps(hands, indent=1), "utf-8")
print(len(MOTIONS), "motions")
