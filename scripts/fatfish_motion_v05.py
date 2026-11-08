"""Six reference-conditioned motion tests using the approved v04 master.

Uses the user's configured 65535 CLI; never reads/copies credentials or installs NPK.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import json
import math
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageOps

import run_65535_samples as runner
from dnf_resources import save_json

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "design/fatfish/motion_master_v05"
WINDOW = (186, 272, 314, 400)
MASTER = ROOT / "design/fatfish/nearest_standing_v04/standing_canvas.png"
DETAIL = ROOT / "design/fatfish/action_samples_v01/raw/idle_01_0.png"
POSES = {
    "walk_000": dict(frame=0, eye=[251,304], sole=[278,381], other_shoe=[227,379], hands=[[228,335],[279,316]]),
    "walk_001": dict(frame=1, eye=[254,304], sole=[261,384], other_shoe=[237,376], hands=[[271,326]]),
    "walk_002": dict(frame=2, eye=[255,304], sole=[256,384], other_shoe=[241,376], hands=[[255,340]]),
    "walk_003": dict(frame=3, eye=[252,304], sole=[235,386], other_shoe=[265,376], hands=[[265,335]]),
    "cast_065": dict(frame=65, eye=[246,305], sole=[238,387], other_shoe=[263,367], hands=[[209,315],[260,337]]),
    "jump_023": dict(frame=23, eye=[253,309], sole=[230,386], hands=[[224,305]]),
}
REPAIR_NAMES = {"walk_003_wrist_fix"}

STYLE = """Use case: identity-preserve / animation sprite pose edit.
One full-body Fatfish whale-maid female mage game sprite, genuine transparent RGBA background.
Image 1 is the EDIT TARGET and strict pose/geometry guide: repaint this gray DNF sprite into the approved character while keeping its skeletal pose and frame placement. Ignore the guide's original hair, hat, clothes and equipment.
Image 2 is the APPROVED STANDING MASTER: preserve this exact character's face, proportions, costume, fine wavy navy-to-cyan hair, curled ahoge, whale-fin ears, cyan bow, white maid headband, dark long sleeves, white chest/apron, whale emblem, gold edging/bows/buttons, opaque white stockings, dark Mary-Jane shoes and compact whale tail. Match its existing rendering and delicacy. Do not simplify the hair into thick cyan blobs, enlarge the face, redesign the skirt or invent decorations.
Image 3 is supplementary identity/detail or motion continuity, NOT a substitute for the pose in Image 1.
Keep the same three-quarter facing-screen-right body/head view as the guide. Keep hair volume and the whale-tail silhouette consistent; allow only a small natural response to the pose. Match the master's light direction, colors, line weight and head size.
Framing: 1024 square representing a fixed 128x128 native game window enlarged 8 times. Keep all important body parts inside the same window. Head/shoulders/pelvis/elbows/hands/knees and both shoes must follow Image 1, not a generic action pose. Copy the guide's actual leg overlap and foot spacing.
Only the character; no weapon, spell, motion blur, shadow, floor, grid, labels, markers, checkerboard or scenery. No new accessories or alternate costume. Do not output a sheet, panels or multiple figures. Preserve true alpha outside the figure.
"""


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def original(frame):
    image=Image.new("RGBA",(500,500))
    image.alpha_composite(Image.open(ROOT/f"materials/female_mage/reference_composite/frames/{frame:04d}.png").convert("RGBA"),(185,0))
    return image


def point8(point):
    return [round((point[i]-WINDOW[i])*8) for i in (0,1)]


def audit(request):
    """Capture the unmodified CLI's actual encoded body before its first HTTP call."""
    relay=runner.load_relay()
    captured={}
    class Captured(Exception):
        pass
    def intercept(method,path,body=None,query=None):
        assert method=="POST" and path=="/v1/tasks"
        captured.update(body)
        raise Captured()
    relay.http=intercept
    args=SimpleNamespace(**request["input"],model=request["model"],image=request["local_reference_paths"])
    try:
        relay.cmd_image(args)
    except Captured:
        pass
    images=captured["input"]["image"]
    images=images if isinstance(images,list) else [images]
    actual=[]
    for uri,path,expected_hash in zip(images,request["local_reference_paths"],request["reference_sha256"],strict=True):
        data=base64.b64decode(uri.split(",",1)[1])
        assert hashlib.sha256(data).hexdigest()==expected_hash==sha(Path(path))
        actual.append(dict(path=path,sha256=expected_hash,bytes=len(data)))
    save_json(BATCH/f"qa/{request['name']}_reference_payload_audit.json",dict(
        cli=str(runner.SKILL),model=captured["model"],reference_count=len(actual),references=actual,
        actual_cli_body_captured_before_http=True,network_requests_during_audit=0,
        caution="Local payload proof; server task receipt does not echo image inputs."))


def prepare_request(name,previous=None):
    target=POSES[name]
    refs=[BATCH/f"references/{name}_pose.png",BATCH/"references/master_approved_8x.png",previous or DETAIL]
    action=("Walk/contact pose. Follow this exact guide frame; do not reuse the master's standing legs or invent a wide stride." if name.startswith("walk") else
            "Casting/action key pose: match the outstretched screen-left arm, low other hand and raised/background shoe; no magical effect." if name.startswith("cast") else
            "Airborne-style key pose: preserve the guide's lean, bent-back hand and leg pose; do not add world-space jump height, because the game controls vertical motion.")
    continuity=("Image 3 is the immediately preceding registered walking frame. Keep the same head size, face, hair locks, hem details and tail volume with minimal inter-frame changes. Do not copy its limb pose." if previous else
                "Image 3 is the original higher-resolution artwork behind the approved master: use only to resolve the same facial and clothing details. Its standing pose and larger figure scale are not the target.")
    targets=f"Visible eye near output {point8(target['eye'])}; support/lowest shoe sole {point8(target['sole'])}."
    if "other_shoe" in target:
        targets+=f" Other shoe sole {point8(target['other_shoe'])}."
    targets+=f" Visible hand target(s) {[point8(p) for p in target['hands']]} (output pixels)."
    prompt=STYLE+"\n"+continuity+f"\nACTION: {action}\nOriginal IMG slot {target['frame']}. {targets}\n"
    request=dict(name=name,category=name,source_frame=target["frame"],model="gpt-image-2.5",
                 input=dict(prompt=prompt,n=1,size="1:1",resolution="1k",background="transparent",output_format="png",quality="high"),
                 local_reference_paths=[str(p) for p in refs],reference_sha256=[sha(p) for p in refs],output_directory=str(BATCH/"raw"))
    destination=BATCH/f"requests/{name}.json"
    if destination.exists():
        raise FileExistsError(destination)
    save_json(destination,request)
    (BATCH/f"requests/{name}.txt").write_text(prompt,encoding="utf-8")
    audit(request)


def prepare():
    if BATCH.exists():
        raise FileExistsError("Preserve prior batch")
    for name in ("references","requests","raw","logs","registered","corrected","sequence","qa"):
        (BATCH/name).mkdir(parents=True)
    assert sha(DETAIL)=="def36f96650567eca3797074e596344bcc74ccf8d637b9671b77b1c30fa40c1d"
    approved=Image.open(MASTER).convert("RGBA")
    approved.crop(WINDOW).resize((1024,1024),Image.Resampling.NEAREST).save(BATCH/"references/master_approved_8x.png")
    shutil.copy2(MASTER,BATCH/"references/master_approved_canvas.png")
    for name,target in POSES.items():
        crop=original(target["frame"]).crop(WINDOW)
        crop.save(BATCH/f"references/{name}_original_native.png")
        gray=ImageOps.grayscale(crop).convert("RGBA")
        gray.putalpha(crop.getchannel("A"))
        guide=Image.new("RGBA",(128,128),"#c9d2de")
        guide.alpha_composite(gray)
        guide.resize((1024,1024),Image.Resampling.NEAREST).convert("RGB").save(BATCH/f"references/{name}_pose.png")
    save_json(BATCH/"spec.json",dict(
        scope="Six small tests only: walk slots 0-3 and one cast/jump key pose each. No full production batch or automatic game installation.",
        provider="65535",model="gpt-image-2.5",standing_master=str(MASTER),master_sha256=sha(MASTER),
        master_pixels_frozen=True,source_detail=str(DETAIL),detail_sha256=sha(DETAIL),
        original_canvas=[500,500],window=list(WINDOW),target_landmarks=POSES,
        alpha="preserve generated alpha",normalization="Single-pass similarity and NEAREST; no palette reduction, sharpen or alpha threshold",
        planned_generation_jobs=6,budget_authorization="Existing user instruction: 随便用，额度管够; current request authorizes a small motion preview only.",
        original_ani_timing_known=False,preview_timing_ms=140,game_installation_changed=False))
    for name in ("walk_000","cast_065","jump_023"):
        prepare_request(name)
    print("Prepared 3 initial requests, all with 3 actual image references. Total planned jobs: 6.")


def run(names):
    if not set(names)<=set(POSES)|REPAIR_NAMES:
        raise ValueError("Outside bounded six-test batch")
    runner.BATCH=BATCH
    relay=runner.load_relay()
    current,unit=runner.observed_cost(relay)
    jp=BATCH/"journal.json"
    journal=json.loads(jp.read_text(encoding="utf-8")) if jp.exists() else dict(
        provider="65535",model="gpt-image-2.5",created_at=runner.now(),baseline_usage_cost=current,usage_unit=unit,
        budget_authorization="Existing unlimited authorization; limited to six requested preview images",jobs={})
    if any(job["state"] not in ("downloaded",) for job in journal["jobs"].values()):
        raise RuntimeError("Prior job unresolved: collect/check it rather than create replacement tasks")
    requests=[]
    for name in names:
        if name in journal["jobs"]:
            raise RuntimeError(f"Do not resubmit {name}")
        request=json.loads((BATCH/f"requests/{name}.json").read_text(encoding="utf-8"))
        assert request["model"]=="gpt-image-2.5"
        for path,expected in zip(request["local_reference_paths"],request["reference_sha256"],strict=True):
            assert sha(Path(path))==expected,path
        journal["jobs"][name]=dict(state="prepared",source_frame=request["source_frame"],category=name)
        requests.append(request)
    assert len(journal["jobs"])<=6+len(REPAIR_NAMES)
    runner.save_journal(journal)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3,len(requests))) as pool:
        results=list(pool.map(lambda r:runner.run_one(r,journal),requests))
    after,_=runner.observed_cost(relay)
    journal["observed_cost_delta"]=after-journal["baseline_usage_cost"]
    journal["status"]="phase_downloaded" if all(r["state"]=="downloaded" for r in results) else "needs_attention_no_replacement"
    runner.save_journal(journal)
    print(json.dumps(dict(names=names,status=journal["status"],observed_account_cost_delta=journal["observed_cost_delta"]),ensure_ascii=False))


def normalize(name,eye,sole):
    item=POSES[name]
    j=json.loads((BATCH/"journal.json").read_text(encoding="utf-8"))
    job=j["jobs"][name]
    assert job["state"]=="downloaded"
    path=Path(job["files"][0]);image=Image.open(path).convert("RGBA")
    alpha=np.asarray(image)[:,:,3]
    assert alpha.min()==0 and alpha.max()>0
    u=np.array(eye,dtype=float)-sole
    v=np.array(item["eye"],dtype=float)-item["sole"]
    den=float(u@u)
    a=float(v@u)/den;b=float(v[1]*u[0]-v[0]*u[1])/den
    angle=math.degrees(math.atan2(b,a))
    if abs(angle)>8:
        raise ValueError(f"Large global correction {angle:.2f} deg: inspect pose")
    x=item["sole"][0]-a*sole[0]+b*sole[1]
    y=item["sole"][1]-b*sole[0]-a*sole[1]
    det=a*a+b*b
    inverse=(a/det,b/det,(-a*x-b*y)/det,-b/det,a/det,(b*x-a*y)/det)
    stage=image.transform((500,500),Image.Transform.AFFINE,inverse,resample=Image.Resampling.NEAREST)
    stage.save(BATCH/f"registered/{name}_canvas.png")
    stage.crop(WINDOW).save(BATCH/f"registered/{name}_native.png")
    stage.crop(WINDOW).resize((1024,1024),Image.Resampling.NEAREST).save(BATCH/f"registered/{name}_reference_8x.png")
    matrix=[[a,-b,x],[b,a,y]]
    transform=lambda p:[sum(matrix[i][k]*p[k] for k in (0,1))+matrix[i][2] for i in (0,1)]
    save_json(BATCH/f"registered/{name}.json",dict(name=name,source=str(path),source_sha256=sha(path),
        manual_raw_eye=eye,manual_raw_sole=sole,target_eye=item["eye"],target_sole=item["sole"],
        transformed_eye=transform(eye),transformed_sole=transform(sole),matrix_2x3=matrix,rotation_degrees=angle,
        uniform_scale=math.sqrt(det),visible_bbox=stage.getchannel("A").getbbox(),
        method="One raw-to-native similarity transform using NEAREST; source alpha preserved; no local/head compositing",
        caution="Eye and supporting shoe are manually annotated fitting constraints, not independent validation or proof of no foot sliding."))
    print(json.dumps(dict(name=name,rotation_degrees=angle,scale=math.sqrt(det),bbox=stage.getchannel("A").getbbox()),ensure_ascii=False))


def neighbor(frame):
    assert frame in (1,2,3)
    name=f"walk_{frame:03d}"
    previous=BATCH/f"corrected/walk_{frame-1:03d}_reference_8x.png"
    if not previous.exists():
        previous=BATCH/f"registered/walk_{frame-1:03d}_reference_8x.png"
    if not previous.exists():
        raise FileNotFoundError(previous)
    prepare_request(name,previous)
    print(f"Prepared {name} with approved master and previous normalized pose")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    commands.add_parser("prepare")
    r=commands.add_parser("run");r.add_argument("names",nargs="+")
    n=commands.add_parser("normalize");n.add_argument("name",choices=list(POSES));n.add_argument("--eye",nargs=2,type=float,required=True);n.add_argument("--sole",nargs=2,type=float,required=True)
    nxt=commands.add_parser("neighbor");nxt.add_argument("frame",type=int,choices=[1,2,3])
    args=parser.parse_args()
    if args.command=="prepare":prepare()
    elif args.command=="run":run(args.names)
    elif args.command=="normalize":normalize(args.name,args.eye,args.sole)
    elif args.command=="neighbor":neighbor(args.frame)
