"""Prepare a reviewable 12-pose image request set. Does not contact a provider."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "design/fatfish/action_samples_v01"
CONCEPT = ROOT / "design/fatfish/concepts/fatfish_mage_v01.png"
COMPOSITE = ROOT / "materials/female_mage/reference_composite"
ORIGIN = (185, 0)
WINDOW = (122, 196, 378, 452)
SCALE = 4

POSES = [
    ("idle_01", "idle", 10, "Neutral idle: relaxed upright posture, feet planted, same three-quarter facing and stance as the pose guide."),
    ("idle_02", "idle", 13, "Idle breathing variation: very small relaxed shoulder and hand change, feet planted. Follow the guide rather than inventing a new stance."),
    ("idle_03", "idle", 17, "Second relaxed idle/breathing sample: preserve facing, stature and foot placement from the guide; hair and skirt rest naturally."),
    ("walk_01", "walk", 0, "Walking contact pose: one foot forward and the other trailing, counter-swinging arms exactly following the guide."),
    ("walk_02", "walk", 3, "Walking passing pose: weight passes over the supporting foot. Follow the guide's leg spacing and arm directions."),
    ("walk_03", "walk", 6, "Walking opposite-step pose: follow the guide's limb positions, head height and body lean; preserve the same outfit and character proportions."),
    ("cast_01", "cast", 62, "Casting preparation: gather the hands in front of the upper torso, follow the reference arms and feet. No magic effects or props."),
    ("cast_02", "cast", 64, "Casting release: extend the casting hand according to the guide, keep the supporting arm and stance readable. No magic effects or props."),
    ("cast_03", "cast", 65, "Casting follow-through: extend the arm fully as in the guide, identical facing, hand direction and leg placement. No magic effects or props."),
    ("jump_01", "jump", 22, "Jump initiation/action pose: lift the arms, compact the legs and keep the body motion matching the guide. No ground shadow."),
    ("jump_02", "jump", 23, "Airborne jump pose: lean slightly forward with knees flexed as in the guide; hair and skirt trail behind. Keep the character registration matching the guide."),
    ("jump_03", "jump", 26, "Airborne raised-arm pose: match the guide's raised arms, bent knees and facing. Keep the same face, clothing geometry and tail attachment. No ground or effects."),
]

COMMON = """Create ONE production-oriented transparent PNG action sample for the same DNF female mage wearing the approved Fatfish whale-maid cosplay.

REFERENCE ROLES:
Image 1 is the APPROVED COSTUME AND IDENTITY master. Use its three large character views to preserve the same navy-to-cyan wavy long hair, one curled ahoge, blue eyes, whale-fin ear ornaments with pale undersides, cyan bow, white frilled maid headband, fully covered navy long-sleeved maid dress with white chest front, small cyan gem and navy neck bow, fitted navy waist and gold buttons, white apron with a small navy whale emblem, restrained gold bows and hem trim, opaque white tights, navy Mary-Jane shoes, and ONE compact navy whale tail attached behind the waist. Keep the knee-length skirt and long hair near calf level.
Image 2 is ONLY a POSE AND REGISTRATION guide from the existing DNF female mage. Reproduce its skeleton, facing, head size and location, shoulder and hip positions, arm/hand positions, leg and shoe positions, and framing as closely as possible. Its old red/black costume is not part of the new outfit. Its grid, labels, lines and registration marks are guides only and must not appear in the output.

STYLE AND OUTPUT:
One single full-body 2D DNF-style pixel-art sprite on a genuinely transparent alpha background. The intended native sprite is roughly 90-110 pixels high, shown enlarged 4x on a 1024x1024 output canvas: coherent pixel clusters, controlled dark outlines, limited clean cel-shaded colors, no soft illustration rendering and no airbrushed gradients. Keep the mage's compact approximately 3.5-4-head body proportions from Image 2; do not revert to the shorter chibi proportions in other references. Keep consistent face shape, hair colors, outfit construction, accessory placement and tail size across the whole batch.

REGISTRATION:
Use the same full square frame as Image 2. Keep the torso, head and shoes in the same frame locations. The entire character including hair, fingers and tail must remain visible. Long hair and the tail may extend beyond the old garment silhouette but must remain within the safe transparent margins. Preserve the action's original local registration instead of centering the silhouette by its bounding box. Do not add dramatic perspective or change camera angle.

No lettering, no multiple panels, no reference sheet, no duplicate character, no props, no weapon, no bowl, no basin helmet, no magical aura, no whale-shaped spell effect, no backdrop, no floor, no cast shadow, no checkerboard painted into the background, no watermarks. The only requested new element is the specific action described below.
"""

NEGATIVE = "No costume drift, no extra tails or limbs, no missing fin ears or headband, no skirt changing length, no chibi body redesign, no opaque or fake checkerboard background, no cropping, no ghosted previous pose."


def main():
    for folder in ("pose_guides", "prompts", "raw", "qa"):
        (BATCH / folder).mkdir(parents=True, exist_ok=True)
    composite_meta = json.loads((COMPOSITE / "reference.json").read_text(encoding="utf-8"))
    if tuple(composite_meta["source_origin"]) != ORIGIN:
        raise ValueError("Reference origin changed; review guide registration")
    body_meta = json.loads((ROOT / "materials/female_mage/layers/mg_body0000/frames.json").read_text(encoding="utf-8"))
    requests = []
    sheet = Image.new("RGB", (4 * 256, 3 * 296), "#272e39")
    sheet_draw = ImageDraw.Draw(sheet)
    for index, (name, category, frame, action) in enumerate(POSES):
        image = Image.open(COMPOSITE / "frames" / f"{frame:04d}.png").convert("RGBA")
        local_box = (WINDOW[0] - ORIGIN[0], WINDOW[1] - ORIGIN[1], WINDOW[2] - ORIGIN[0], WINDOW[3] - ORIGIN[1])
        registered = image.crop(local_box)
        guide = Image.new("RGBA", registered.size, "#66717e")
        guide.alpha_composite(registered)
        guide = guide.resize((1024, 1024), Image.Resampling.NEAREST)
        draw = ImageDraw.Draw(guide)
        # Review guides only; final requested images must contain alpha, no guide graphics.
        for tick in range(0, 1024, 64):
            draw.line((tick, 0, tick, 1024), fill="#7d8792", width=1)
            draw.line((0, tick, 1024, tick), fill="#7d8792", width=1)
        draw.line((512, 0, 512, 1024), fill="#89b4cc", width=2)
        draw.line((0, 764, 1024, 764), fill="#d3b27e", width=2)
        draw.text((24, 24), f"POSE ONLY / {name} / source frame {frame:03d}", fill="white")
        guide_path = BATCH / "pose_guides" / f"{name}.png"
        guide.convert("RGB").save(guide_path)
        thumb = guide.convert("RGB").resize((256, 256), Image.Resampling.NEAREST)
        col, row = index % 4, index // 4
        sheet.paste(thumb, (col * 256, row * 296))
        sheet_draw.text((col * 256 + 8, row * 296 + 262), f"{name} | frame {frame:03d}", fill="white")
        prompt = COMMON + "\nACTION: " + action + "\n\n" + NEGATIVE
        prompt_path = BATCH / "prompts" / f"{name}.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        f = body_meta["frames"][frame]
        requests.append(dict(
            name=name, category=category, source_frame=frame,
            source_body_geometry={k: f[k] for k in ("x", "y", "width", "height", "canvas_width", "canvas_height")},
            kind="image", model="gpt-image-2.5",
            input=dict(prompt=prompt, n=1, size="1:1", resolution="1k", background="transparent", output_format="png", quality="high"),
            local_reference_paths=[str(CONCEPT), str(guide_path)],
            reference_sha256=[hashlib.sha256(CONCEPT.read_bytes()).hexdigest(), hashlib.sha256(guide_path.read_bytes()).hexdigest()],
            output_directory=str(BATCH / "raw"),
            negative_prompt=NEGATIVE,
            mapping_note="Pose-reference frame IDs only. Animation group names/timing have not been certified from the game's ANI data.",
        ))
    sheet.save(BATCH / "qa/requested_pose_overview.png")
    manifest = dict(
        status="prepared_not_submitted",
        provider="65535", model="gpt-image-2.5", count=12, max_parallel_jobs=4,
        image_size="1k square", quality="high", background="transparent",
        paid_generation_authorized_by_user=True,
        spend_ceiling_usd=None,
        billing_observation="Read-only pricing reports mode=usage and zero-valued public unit fields; no reliable per-image quote was supplied. Do not interpret those fields as confirmed free generation.",
        registration=dict(source_window=list(WINDOW), output_scale=SCALE, preview_root_x=512, preview_ground_y=764),
        validation_plan=["PNG signature and dimensions", "genuine alpha channel and transparent corners", "nonempty subject and no clipping", "foot/head/hand registration against guide", "consistent face, hair, ears, outfit, tail and palette", "12-cell contact sheet and per-category motion inspection"],
        requests=requests,
    )
    (BATCH / "requests.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status":manifest["status"], "requests":len(requests), "manifest":str(BATCH / "requests.json"), "pose_overview":str(BATCH / "qa/requested_pose_overview.png")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
