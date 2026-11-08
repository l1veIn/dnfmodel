"""Prepare and run a bounded 65535 master edit + three pose tests, preserving originals."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps, ImageFont

import run_65535_samples as runner

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "design/fatfish/master_and_actions_v02"
WINDOW = (186, 272, 314, 400)
POSES = {"master": 10, "walk": 0, "cast": 65, "jump": 23}

STYLE = """Clean game sprite of the SAME Fatfish whale-maid DNF female mage. Single full body, transparent alpha, no text or props.
Compact female-mage anatomy, consistent head size and limb proportions. Navy-to-cyan long wavy hair in about six broad readable locks, one curled ahoge, whale-fin ears, cyan bow and white maid headband. Navy long-sleeved dress, white chest and apron, one simple navy whale emblem, two gold waist buttons, small gold bows, one simple gold hem stripe, opaque white tights, navy Mary-Jane shoes and one compact navy whale tail.
Art direction: clean low-resolution pixel sprite intended for a 128x128 native canvas, shown enlarged exactly 8x on a 1024 square. Big connected pixel clusters and solid interior colors. Each material has just a base, one shadow and one highlight. Navy outline, flat navy/blue/cyan/white/gold/skin palette. No stipple, grain, embroidery, intricate lace, tiny gold scribbles, isolated sparkle pixels, gritty texture, noisy gradients, blue/purple fringe, soft painted edges or tiny perforations. Simplify details that would collapse at native size. Preserve the costume rather than adding decoration.
Only one character. No grid, markers, lettering, scenery, floor, shadow, effects, weapon, bowl or extra limbs. Genuine alpha outside the silhouette, solid opaque colors inside the character.
"""


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request(name, prompt, refs):
    return dict(name=name, category=name, source_frame=POSES.get(name, 10), model="gpt-image-2.5",
                input=dict(prompt=prompt, n=1, size="1:1", resolution="1k", background="transparent", output_format="png", quality="high"),
                local_reference_paths=[str(p) for p in refs], reference_sha256=[digest(p) for p in refs],
                output_directory=str(BATCH / "raw"))


def prepare():
    if (BATCH / "master.request.json").exists():
        raise RuntimeError("v02 is already prepared; preserve request provenance")
    for folder in ("references", "requests", "raw", "logs", "master", "registered", "qa"):
        (BATCH / folder).mkdir(parents=True, exist_ok=True)
    previous = ROOT / "design/fatfish/action_samples_v01/raw/idle_01_0.png"
    im = Image.open(previous).convert("RGBA")
    bb = im.getchannel("A").point(lambda a: 255 if a > 127 else 0).getbbox()
    im.crop((bb[0] - 20, bb[1] - 20, bb[2] + 20, bb[3] + 20)).save(BATCH / "references/v01_costume_edit_target.png")
    for name, frame in POSES.items():
        src = Image.open(ROOT / f"materials/female_mage/reference_composite/frames/{frame:04d}.png").convert("RGBA")
        crop = src.crop((WINDOW[0] - 185, WINDOW[1], WINDOW[2] - 185, WINDOW[3]))
        crop.save(BATCH / f"references/{name}_original_native.png")
        rgb = ImageOps.grayscale(crop).convert("RGBA")
        rgb.putalpha(crop.getchannel("A"))
        guide = Image.new("RGBA", (128, 128), "#d1d8e1")
        guide.alpha_composite(rgb)
        guide.resize((1024, 1024), Image.Resampling.NEAREST).convert("RGB").save(BATCH / f"references/{name}_pose_gray_8x.png")
        crop.resize((1024, 1024), Image.Resampling.NEAREST).save(BATCH / f"references/{name}_original_8x.png")
    prompt = STYLE + """
EDIT TARGET = Image 1: keep this particular character's identity, costume construction and compact stature; redraw its overly busy surfaces into clean simple pixel clusters. This is the standing MASTER for subsequent action edits.
POSE/LAYOUT ONLY = Image 2: copy the original female mage's upright relaxed pose, head size, torso angle, lowered arms and shoes. Ignore this gray character's hat, hairstyle and old costume. The guide is a 128x128 native window enlarged 8x. Target visible eye near (504,264), supporting shoe sole near (464,912) on the 1024 canvas. Preserve the eye-to-shoe distance and head/hip/hand placement. Do not simply fill the square by centering the hair/tail bounding box.
Neutral three-quarter view facing screen-right; both feet planted, arms relaxed down. Do not invent a hand-to-chin gesture or a casting pose. Render a full-body master approximately 100 native pixels high, about 800 output pixels, with safe clear margins. No panel or turnaround sheet.
"""
    req = request("master", prompt, [BATCH / "references/v01_costume_edit_target.png", BATCH / "references/master_pose_gray_8x.png"])
    save(BATCH / "master.request.json", req)
    (BATCH / "requests/master.prompt.txt").write_text(prompt, encoding="utf-8")
    save(BATCH / "spec.json", dict(model="gpt-image-2.5", provider="65535", source_window=list(WINDOW), output_scale=8,
                                   native_window_size=[128, 128], game_canvas=[500, 500], poses=POSES,
                                   authorization="User explicitly requested master correction and one walk/cast/jump; then authorized spending with no fixed numeric ceiling: 随便用，额度管够",
                                   numeric_user_ceiling=None, additional_actions_authorized=3,
                                   engine_validation="not performed", phase="master_request_prepared"))
    print(str(BATCH / "master.request.json"))


def run(names):
    runner.BATCH = BATCH
    relay = runner.load_relay()
    cost, unit = runner.observed_cost(relay)
    journal_path = BATCH / "journal.json"
    if journal_path.exists():
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
    else:
        journal = dict(provider="65535", model="gpt-image-2.5", created_at=runner.now(),
                       budget_authorization="User authorized this bounded round without a numeric ceiling: 随便用，额度管够",
                       numeric_user_ceiling=None, baseline_usage_cost=cost, usage_unit=unit,
                       spending_note="Observed cumulative account usage delta; other concurrent activity may contribute. No per-request billing cap exposed.", jobs={})
    reqs = []
    for name in names:
        if name not in ("master", "master_refine", "master_feet", "walk", "cast", "jump", "jump_fix"):
            raise ValueError("Outside this bounded round")
        if name in journal["jobs"]:
            raise RuntimeError(f"Already submitted/prepared: {name}; do not POST again")
        path = BATCH / ("master.request.json" if name == "master" else f"requests/{name}.request.json")
        req = json.loads(path.read_text(encoding="utf-8"))
        if req["model"] != "gpt-image-2.5" or req["input"]["n"] != 1:
            raise ValueError("Wrong model/count")
        for p, h in zip(req["local_reference_paths"], req["reference_sha256"], strict=True):
            if digest(Path(p)) != h:
                raise RuntimeError(f"Reference changed: {p}")
        journal["jobs"][name] = dict(state="prepared", source_frame=req["source_frame"], category=req["category"])
        reqs.append(req)
    runner.save_journal(journal)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(reqs))) as pool:
        results = list(pool.map(lambda r: runner.run_one(r, journal), reqs))
    current, _ = runner.observed_cost(relay)
    journal["observed_cost_delta"] = current - journal["baseline_usage_cost"]
    journal["last_updated_at"] = runner.now()
    journal["status"] = "current_phase_downloaded" if all(r["state"] == "downloaded" for r in results) else "needs_attention_no_replacement_submission"
    runner.save_journal(journal)
    print(json.dumps({"names":names,"observed_cost_delta":journal["observed_cost_delta"],"status":journal["status"]},ensure_ascii=False))


def normalize(name, raw_eye, raw_sole, target_eye, target_sole, similarity=False):
    journal = json.loads((BATCH / "journal.json").read_text(encoding="utf-8"))
    file = Path(journal["jobs"][name]["files"][0])
    raw = Image.open(file).convert("RGBA")
    scale = (target_sole[1] - target_eye[1]) / (raw_sole[1] - raw_eye[1])
    size = tuple(round(v * scale) for v in raw.size)
    scale_x, scale_y = size[0] / raw.width, size[1] / raw.height
    pos = (round(target_sole[0] - raw_sole[0] * scale_x), round(target_sole[1] - raw_sole[1] * scale_y))
    matrix = [[scale_x, 0, pos[0]], [0, scale_y, pos[1]]]
    angle = 0.0
    inverse = None
    if similarity:
        u = [raw_eye[j] - raw_sole[j] for j in (0, 1)]
        v = [target_eye[j] - target_sole[j] for j in (0, 1)]
        denominator = u[0] ** 2 + u[1] ** 2
        aa = (v[0] * u[0] + v[1] * u[1]) / denominator
        bb = (v[1] * u[0] - v[0] * u[1]) / denominator
        angle = math.degrees(math.atan2(bb, aa))
        if abs(angle) > 8:
            raise RuntimeError(f"Pose needs {angle:.2f} degrees global correction: inspect/refine rather than hide a major pose error")
        tx = target_sole[0] - aa * raw_sole[0] + bb * raw_sole[1]
        ty = target_sole[1] - bb * raw_sole[0] - aa * raw_sole[1]
        matrix = [[aa, -bb, tx], [bb, aa, ty]]
        den = aa ** 2 + bb ** 2
        inverse = (aa / den, bb / den, (-aa * tx - bb * ty) / den,
                   -bb / den, aa / den, (bb * tx - aa * ty) / den)
        scale_x = scale_y = math.sqrt(den)
        pos = (tx, ty)
    output_dir = BATCH / ("master" if name.startswith("master") else "registered")
    output_dir.mkdir(exist_ok=True)
    records = []
    methods = (("nearest", Image.Resampling.NEAREST), ("bicubic", Image.Resampling.BICUBIC)) if similarity else (("nearest", Image.Resampling.NEAREST), ("box", Image.Resampling.BOX))
    for method, mode in methods:
        if similarity:
            stage = raw.transform((500, 500), Image.Transform.AFFINE, inverse, resample=mode)
        else:
            sprite = raw.resize(size, mode)
            stage = Image.new("RGBA", (500, 500))
            stage.alpha_composite(sprite, pos)
        path = output_dir / f"{name}_{method}_canvas.png"
        stage.save(path)
        # A nearest-neighbor, strict-alpha candidate removes faint matte noise,
        # while leaving colors and anatomy unpainted. Raw provider PNG is retained.
        if method == "nearest":
            a = np.asarray(stage).copy()
            a[:, :, 3] = np.where(a[:, :, 3] >= 128, 255, 0).astype("uint8")
            a[a[:, :, 3] == 0, :3] = 0
            clean = Image.fromarray(a)
            clean_path = output_dir / f"{name}_clean_canvas.png"
            clean.save(clean_path)
            cropped = clean.crop((WINDOW[0], WINDOW[1], WINDOW[2], WINDOW[3]))
            cropped.save(output_dir / f"{name}_native_128.png")
            cropped.resize((1024, 1024), Image.Resampling.NEAREST).save(output_dir / f"{name}_reference_8x.png")
        records.append(dict(method=method, path=str(path)))
    apply = lambda point: [sum(matrix[j][k] * point[k] for k in (0, 1)) + matrix[j][2] for j in (0, 1)]
    actual_eye = apply(raw_eye)
    actual_sole = apply(raw_sole)
    record = dict(name=name, source=str(file), sha256=digest(file), raw_eye=raw_eye, raw_sole=raw_sole,
                  target_eye=target_eye, target_sole=target_sole, actual_eye=actual_eye, actual_sole=actual_sole,
                  resized_canvas=list(size), scale_x=scale_x, scale_y=scale_y, translation=list(pos),
                  transform_type="global_similarity" if similarity else "uniform_scale_and_translation", matrix_2x3=matrix, rotation_degrees=angle,
                  landmark_method="Manually annotated visible eye and sole, approximate 1-2 native pixels; no skeleton detector.",
                  processing="Single-pass global similarity (if requested) or uniform resize + translation. Nearest and filtered candidates. Clean candidate thresholds alpha at 128, no palette reduction, local deformation or repainting. Eye/sole are fitting anchors, not independent validation.",
                  source_modified=False, game_ready=False, outputs=records)
    save(output_dir / f"{name}.registration.json", record)
    print(json.dumps(record, ensure_ascii=False, indent=2))


def actions():
    selection_path = BATCH / "master/selection.json"
    if not selection_path.exists():
        raise RuntimeError("Record the visually inspected master selection first")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    master_path = Path(selection["reference_8x"])
    if not master_path.exists():
        raise RuntimeError("Normalize and inspect the master before preparing dependent requests")
    descriptions = {
        "walk": "Walking contact pose: follow the exact leading/trailing feet and opposite arm positions in the gray pose guide. Do not reuse a neutral idle stance.",
        "cast": "Casting/action pose: extend the arm toward screen-left exactly as the gray pose guide; keep the other arm, lifted leg and torso direction in the guide. No magic effect. Do not mirror the guide.",
        "jump": "Airborne action pose: forward-leaning torso, arms trailing backward, legs positioned exactly as the gray guide. Keep local root coordinates; airborne world height is controlled separately by the game, so do not shift the whole figure upward to simulate a jump. No shadow or effect.",
    }
    for name in ("walk", "cast", "jump"):
        prompt = STYLE + "\nImage 1 is the SINGLE APPROVED STANDING MASTER, the sole character/design/pixel-scale reference. It is native 128x128 enlarged 8x. Preserve head size, face, hair color blocks, dress construction, apron emblem, gold trim count and tail size. Change only the pose and natural cloth/hair displacement. Do not add decorative texture.\nImage 2 is POSE/LAYOUT ONLY, a gray DNF female-mage guide in the exact same 128 native-pixel window enlarged 8x. Follow its head, shoulder, pelvis, elbows, hands, knees and shoe positions. Ignore its old costume and hat. Keep hands and feet on guide landmarks instead of centering the whole silhouette. Do not add guide graphics to the result.\nACTION: " + descriptions[name]
        req = request(name, prompt, [master_path, BATCH / f"references/{name}_pose_gray_8x.png"])
        save(BATCH / f"requests/{name}.request.json", req)
        (BATCH / f"requests/{name}.prompt.txt").write_text(prompt, encoding="utf-8")
    print("Prepared exactly one walk, cast and jump request using inspected master")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode", required=True)
    sub.add_parser("prepare")
    sub.add_parser("actions")
    r = sub.add_parser("run")
    r.add_argument("names", nargs="+")
    n = sub.add_parser("normalize")
    n.add_argument("name")
    n.add_argument("--similarity", action="store_true")
    for flag in ("raw-eye", "raw-sole", "target-eye", "target-sole"):
        n.add_argument("--" + flag, type=float, nargs=2, required=True)
    args = ap.parse_args()
    if args.mode == "prepare": prepare()
    elif args.mode == "actions": actions()
    elif args.mode == "run": run(args.names)
    elif args.mode == "normalize": normalize(args.name, args.raw_eye, args.raw_sole, args.target_eye, args.target_sole, args.similarity)
