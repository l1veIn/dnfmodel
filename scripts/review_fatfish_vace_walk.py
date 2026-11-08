"""Package the single constrained-motion trial, including its failed visual result."""
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/"design/fatfish/local_walk_control_v01"
OUT=ROOT/"output/Fatfish_Original_Walk_Control_v01"


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    motion=json.loads((RUN/"source_motion.json").read_text("utf-8"))
    metrics=json.loads((RUN/"metrics.json").read_text("utf-8"))
    (OUT/"source_sequence").mkdir(exist_ok=True)
    (OUT/"control_sequence").mkdir(exist_ok=True)
    (OUT/"evidence/input").mkdir(parents=True,exist_ok=True)
    full=[];native=[]
    master=Image.open(RUN/"input/master.png").convert("RGB")
    for i,entry in enumerate(motion["mapping"]):
        original=RUN/f"source_frames/{int(entry['source_phase'])%10:04d}.png"
        shutil.copy2(original,OUT/f"source_sequence/{i:04d}.png")
        control=Image.open(RUN/f"input/control_{i:04d}.png")
        alpha=control.getchannel("A")
        if alpha.getextrema() != ((255,255) if i in (0,24) else (0,0)):
            raise ValueError("VACE control mask differs")
        if i in (0,24) and ImageChops.difference(control.convert("RGB"),master).getbbox():
            raise ValueError("Known frame differs from approved master")
        control.convert("RGB").save(OUT/f"control_sequence/{i:04d}.png")
        shutil.copy2(RUN/f"input/control_{i:04d}.png",OUT/f"evidence/input/control_{i:04d}.png")
        image=Image.open(OUT/f"frames_raw/{i:04d}.png").convert("RGB")
        small=Image.open(OUT/f"frames_native_128/{i:04d}.png").convert("RGB")
        if image.size!=(256,256) or small.size!=(128,128):
            raise ValueError("Unexpected frame dimensions")
        if ImageChops.difference(image.resize((128,128),Image.Resampling.NEAREST),small).getbbox():
            raise ValueError("Nearest output differs")
        full.append(image);native.append(small)
    durations=[round((i+1)*1000/24)-round(i*1000/24) for i in range(25)]
    for filename,images in [("raw_native_3x.png",[im.resize((384,384),Image.Resampling.NEAREST) for im in native]),
                            ("raw_native_lossless.png",native)]:
        images[0].save(OUT/filename,save_all=True,append_images=images[1:],duration=durations,loop=0,disposal=0,blend=0)
        decoded=Image.open(OUT/filename)
        if decoded.n_frames!=25:
            raise ValueError("APNG frame count differs")
        for i,expected in enumerate(images):
            decoded.seek(i)
            if ImageChops.difference(decoded.convert("RGB"),expected).getbbox():
                raise ValueError("APNG pixel readback differs")
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-framerate","24","-i",str(OUT/"frames_raw/%04d.png"),
                    "-c:v","libx264","-crf","16","-pix_fmt","yuv420p","-movflags","+faststart",str(OUT/"raw_output.mp4")],check=True)
    endpoint_mae=float(np.abs(np.asarray(native[0],dtype=float)-np.asarray(native[24],dtype=float)).mean())
    seam=Image.new("RGB",(768,284),"#26323e");d=ImageDraw.Draw(seam)
    for j,(label,image) in enumerate([("Approved master",master),("Generated first",full[0]),("Generated last",full[24])]):
        seam.paste(image,(j*256,28));d.text((j*256+8,8),label,fill="white")
    seam.save(OUT/"endpoint_comparison.png")
    shutil.copy2(RUN/"source_cycle_sheet.png",OUT/"source_cycle_sheet.png")
    shutil.copy2(RUN/"control_overview.png",OUT/"control_overview.png")
    shutil.copy2(RUN/"input/master.png",OUT/"master.png")
    for name in ["source_motion.json","workflow_api.json","prompts.json","spec.json","submission.json","history.json","environment.json","resource_samples.jsonl"]:
        shutil.copy2(RUN/name,OUT/"evidence"/name)
    for p in (RUN/"models").glob("*.json"):
        shutil.copy2(p,OUT/"evidence"/p.name)
    shutil.copy2(ROOT/"design/fatfish/references/UPSTREAM_CREDITS.md",OUT/"evidence/UPSTREAM_CREDITS.md")
    report={"trial_completed":True,"generative_jobs":1,"model":"Wan2.1 VACE 1.3B FP16",
        "actual_inputs":{"reference_image":"Approved Fatfish master","control_video":"25 real input PNGs; manual skeletons traced from original IMG0..9",
                         "control_masks":"0 known RGB endpoints, 1 middle pose-conditioning frames","first_last_anchor_identical":True},
        "metrics":metrics,"validation":{"nearest_pixels_passed":True,"apng_readback_passed":True,"input_mask_and_reference_check_passed":True,
                                         "first_last_native_rgb_mae_0_255":endpoint_mae},
        "visual_result":{"usable_walk_cycle":False,"identity_preserved":False,"loop_seam_passed":False,"foot_sliding_passed":False,
            "observations":["Legs and arms respond to the motion guide more strongly than the initial-image-only baseline",
                "Face, hair color, sleeve and apron details deform significantly","Background becomes contaminated, especially at the final frame",
                "First/last conditioning did not produce a closed loop","Changing shoes/limbs prevent reliable contact/sliding validation"]},
        "motion_limits":{"original_ani_verified":False,"test_period_seconds":1,"sequence":"Visually inferred original IMG0..9 alternating gait",
                         "joints":"Manual estimates; not an extracted game skeleton","game_root_velocity_verified":False},
        "recommendation":"Do not batch this VACE1.3B pipeline. Preserve master pixels and test deterministic limb deformation/rigging before more generated motion.",
        "game_installation_changed":False,"paid_api_used":False,"additional_generation_started":False,
        "sources":["https://docs.comfy.org/tutorials/video/wan/vace","https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged"]}
    save(OUT/"review_report.json",report);save(RUN/"review_report.json",report)
    status=json.loads((ROOT/"preparation_status.json").read_text("utf-8"))
    status["original_walk_control_trial"]={"completed":True,"accepted":False,"jobs":1,"model":"Wan2.1 VACE1.3B",
        "preview":"output/Fatfish_Original_Walk_Control_v01/preview.html","preview_url":"http://127.0.0.1:8787/preview.html",
        "report":"output/Fatfish_Original_Walk_Control_v01/review_report.json","original_ani_verified":False,
        "reason":"Motion follows guide but identity and loop closure fail","batch_started":False,"game_installation_changed":False}
    save(ROOT/"preparation_status.json",status)
    readme=ROOT/"README.md";content=readme.read_text("utf-8")
    if "原版步态约束测试 v01" not in content:
        content+="\n\n原版步态约束测试 v01：只提交 1 段 Wan2.1 VACE1.3B 本地任务，256×256、25 帧，以原版 IMG0–9 手工骨架和相同的大肥鱼首尾参考约束中段。原 ANI 未能读取，配时为试验值。41.29 秒完成；显存采样峰值 6.28GiB，系统内存最低余 8.12GiB。腿部运动跟随更明显，但脸、袖子、围裙和背景明显漂移，首尾未闭合，测试判定不合格，未继续批量。预览为 `output/Fatfish_Original_Walk_Control_v01/preview.html`，输入与失败结果均保留。\n"
        readme.write_text(content,encoding="utf-8")
    manifest={str(p.relative_to(OUT)).replace("\\","/"):sha(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name!="SHA256.json"}
    save(OUT/"SHA256.json",manifest)
    bundle=ROOT/"output/fatfish_original_walk_control_v01.zip"
    with zipfile.ZipFile(bundle,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():z.write(p,str(p.relative_to(OUT.parent)))
    with zipfile.ZipFile(bundle) as z:
        if z.testzip() is not None:raise ValueError("ZIP CRC failed")
    print(json.dumps({"package_verified":True,"visual_accepted":False,"endpoint_mae":endpoint_mae,"bundle_bytes":bundle.stat().st_size}))


if __name__=="__main__":main()
