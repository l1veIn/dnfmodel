"""One original-sprite-driven, first/last-reference VACE walk-cycle trial."""
import ctypes
import hashlib
import json
import math
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from run_local_wan import MemoryStatus, request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "design/fatfish/local_walk_control_v01"
DELIVERY = ROOT / "output/Fatfish_Original_Walk_Control_v01"
SHARED = Path(r"D:\VideoStudio\comfyUI\shared")
SIZE, LENGTH, FPS, STEPS, SEED = 256, 25, 24, 20, 20261023
PREFIX = "fatfish_original_walk_control_v01"
# World-pixel landmarks traced from the original IMG 0..9 strip. Hidden joints are estimates.
# Per row: nose, right wrist, left wrist, right knee/ankle, left knee/ankle.
LANDMARKS = [
    [[251,304],[279,316],[228,335],[234,359],[227,376],[266,360],[278,378]],
    [[254,304],[271,326],[236,337],[242,360],[237,373],[257,365],[260,380]],
    [[255,304],[255,340],[247,332],[247,360],[241,373],[252,365],[256,380]],
    [[252,304],[231,327],[265,335],[259,359],[265,373],[242,365],[235,382]],
    [[250,304],[225,326],[281,323],[266,355],[279,372],[231,362],[223,377]],
    [[251,305],[226,323],[277,326],[266,360],[280,380],[234,361],[223,380]],
    [[253,304],[235,327],[270,334],[259,363],[264,380],[241,360],[232,375]],
    [[255,305],[256,339],[245,331],[253,365],[256,380],[247,358],[242,372]],
    [[253,305],[265,329],[231,337],[242,366],[236,382],[256,356],[266,371]],
    [[250,305],[279,318],[232,330],[234,365],[225,382],[266,356],[280,371]],
]
COLORS = [(255,0,0),(255,85,0),(255,170,0),(255,255,0),(170,255,0),(85,255,0),
          (0,255,0),(0,255,85),(0,255,170),(0,255,255),(0,170,255),(0,85,255),
          (0,0,255),(85,0,255),(170,0,255),(255,0,255),(255,0,170),(255,0,85)]
LIMBS = [(1,2),(2,3),(3,4),(1,5),(5,6),(6,7),(1,8),(8,9),(9,10),
         (1,11),(11,12),(12,13),(1,0)]
POSITIVE = (
    "A single full-body 2D pixel art whale maid female mage performs one complete walking "
    "cycle in place, facing three-quarter right, strictly following the supplied colored "
    "human skeleton motion. Both legs alternate through contact, passing and swing poses; "
    "arms swing opposite to the legs, connected wrists and slender legs. The exact same "
    "character and outfit as the reference image in every frame: wavy navy-to-cyan hair, "
    "curled ahoge, whale-fin ears, white maid headband, blue eyes, navy long-sleeve dress, "
    "white whale-emblem apron, gold trim, opaque white tights, navy Mary Jane shoes, compact "
    "whale tail. Stable head size, face, hair locks, apron emblem and skirt details. "
    "Fixed camera and character scale, uniform medium-gray background. The first and last "
    "pose match the reference, a seamless small game sprite walk cycle, crisp pixel clusters."
)
NEGATIVE = (
    "camera movement, zoom, background scenery, black background, changing outfit, red hair, "
    "red costume, giant hat, visible colored skeleton, extra limbs, detached hands, thick legs, "
    "melted feet, changing shoes, drifting head, changing face, turning away, translation across "
    "screen, cropped body, blur, photorealism, 3D, text, watermark, particles"
)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def skeleton(index):
    eye, rw, lw, rk, ra, lk, la = LANDMARKS[index]
    x, y = eye
    neck = [x - 3, 313 + (y - 304)]
    rs, ls = [x - 1, 317], [x - 10, 317]
    re = [(rs[0] + rw[0]) / 2, (rs[1] + rw[1]) / 2 + 4]
    le = [(ls[0] + lw[0]) / 2, (ls[1] + lw[1]) / 2 + 4]
    return np.asarray([eye, neck, rs, re, rw, ls, le, lw,
                       [247,344], rk, ra, [253,344], lk, la], dtype=float)


def pose_image(points):
    image = Image.new("RGB", (SIZE, SIZE), "black")
    draw = ImageDraw.Draw(image)
    positions = [((x - 186) * 2, (y - 272) * 2) for x, y in points]
    for limb, (a, b) in enumerate(LIMBS):
        draw.line([positions[a], positions[b]], fill=COLORS[limb], width=4)
    for i, (x, y) in enumerate(positions):
        draw.ellipse((x-3,y-3,x+3,y+3), fill=COLORS[i])
    return image


def prepare():
    for name in ["input", "poses", "source_frames"]:
        (OUT / name).mkdir(parents=True, exist_ok=True)
    master_file = ROOT / "design/fatfish/local_video_v01/input/master_native_128.png"
    master = Image.open(master_file).convert("RGBA").resize((SIZE,SIZE), Image.Resampling.NEAREST)
    background = Image.new("RGBA", master.size, (128,128,128,255))
    background.alpha_composite(master)
    master = background.convert("RGB")
    master.save(OUT / "input/master.png")
    mapping, sources = [], []
    for i in range(10):
        path = ROOT / f"materials/female_mage/reference_composite/frames/{i:04d}.png"
        canvas = Image.new("RGBA", (500,500))
        canvas.alpha_composite(Image.open(path).convert("RGBA"), (185,0))
        crop = canvas.crop((186,272,314,400)).resize((SIZE,SIZE), Image.Resampling.NEAREST)
        rgb = Image.new("RGBA", crop.size, (128,128,128,255))
        rgb.alpha_composite(crop)
        rgb.convert("RGB").save(OUT / f"source_frames/{i:04d}.png")
        sources.append({"img_index":i,"source_png":str(path),"sha256":sha(path),
                        "world_keypoints":skeleton(i).tolist()})
    for i in range(LENGTH):
        phase = (2 + 10 * i / (LENGTH-1)) % 10
        low, fraction = int(math.floor(phase)), phase % 1
        points = skeleton(low) * (1-fraction) + skeleton((low+1)%10) * fraction
        # Constant registration only; the original gait trajectories and bob are retained.
        points[:,0] -= 6
        pose = pose_image(points)
        pose.save(OUT / f"poses/{i:04d}.png")
        rgb = master if i in (0,LENGTH-1) else pose
        control = rgb.convert("RGBA")
        # LoadImage outputs MASK=1-alpha: known first/last RGB anchors=0, pose middle=1.
        control.putalpha(255 if i in (0,LENGTH-1) else 0)
        control.save(OUT / f"input/control_{i:04d}.png")
        mapping.append({"frame":i,"source_phase":phase,"known_master_anchor":i in (0,LENGTH-1),
                        "keypoints_256":((points-[186,272])*2).tolist()})
    for path in (OUT / "input").glob("*.png"):
        target = SHARED / "input" / f"{PREFIX}_{path.name}"
        if target.exists() and sha(target) != sha(path):
            raise ValueError("Comfy input name collision")
        shutil.copy2(path,target)
    save(OUT / "source_motion.json", {"sources":sources,"mapping":mapping,
        "sequence":"IMG 0..9 visually form both alternating leg phases; origin rotated to IMG2 passing pose",
        "joint_method":"Manual tracing; occluded shoulders/hips/elbows/knees estimated; linear interpolation between source poses",
        "registration_world_pixels":[-6,0],"loop_seconds":1,"test_timing":True,"original_ani_verified":False,
        "ani_read_limit":"Current Script.pvf header is not the legacy PVF format; no full decrypt or client modification attempted",
        "endpoint_constraint":"Approved standing master is used at both ends; approximately aligned to the IMG2 passing pose",
        "alpha_note":"Transparent middle control files intentionally carry RGB skeleton data; they are control assets, not transparent output sprites"})
    sheet = Image.new("RGB",(256*5,290*2),"#26323e")
    draw=ImageDraw.Draw(sheet)
    for i in range(10):
        sheet.paste(Image.open(OUT/f"source_frames/{i:04d}.png"),(i%5*256,i//5*290+28))
        draw.text((i%5*256+8,i//5*290+8),f"Original IMG {i}",fill="white")
    sheet.save(OUT / "source_cycle_sheet.png")


def build_graph():
    g={}
    for i in range(LENGTH):
        g[str(100+i)]={"class_type":"LoadImage","inputs":{"image":f"{PREFIX}_control_{i:04d}.png"}}
        g[str(200+i)]={"class_type":"MaskToImage","inputs":{"mask":[str(100+i),1]}}
    images=["100",0]
    masks=["200",0]
    for i in range(1,LENGTH):
        g[str(300+i)]={"class_type":"ImageBatch","inputs":{"image1":images,"image2":[str(100+i),0]}}
        g[str(400+i)]={"class_type":"ImageBatch","inputs":{"image1":masks,"image2":[str(200+i),0]}}
        images,masks=[str(300+i),0],[str(400+i),0]
    g.update({
        "1":{"class_type":"UNETLoader","inputs":{"unet_name":"wan2.1_vace_1.3B_fp16.safetensors","weight_dtype":"default"}},
        "2":{"class_type":"CLIPLoader","inputs":{"clip_name":"umt5_xxl_fp8_e4m3fn_scaled.safetensors","type":"wan","device":"cpu"}},
        "3":{"class_type":"VAELoader","inputs":{"vae_name":"wan_2.1_vae.safetensors"}},
        "4":{"class_type":"CLIPTextEncode","inputs":{"clip":["2",0],"text":POSITIVE}},
        "5":{"class_type":"CLIPTextEncode","inputs":{"clip":["2",0],"text":NEGATIVE}},
        "6":{"class_type":"LoadImage","inputs":{"image":f"{PREFIX}_master.png"}},
        "7":{"class_type":"ImageToMask","inputs":{"image":masks,"channel":"red"}},
        "8":{"class_type":"WanVaceToVideo","inputs":{"positive":["4",0],"negative":["5",0],"vae":["3",0],
            "width":SIZE,"height":SIZE,"length":LENGTH,"batch_size":1,"strength":1.0,
            "control_video":images,"control_masks":["7",0],"reference_image":["6",0]}},
        "9":{"class_type":"ModelSamplingSD3","inputs":{"model":["1",0],"shift":8.0}},
        "10":{"class_type":"KSampler","inputs":{"model":["9",0],"positive":["8",0],"negative":["8",1],"latent_image":["8",2],
            "seed":SEED,"steps":STEPS,"cfg":5.0,"sampler_name":"euler","scheduler":"simple","denoise":1.0}},
        "11":{"class_type":"TrimVideoLatent","inputs":{"samples":["10",0],"trim_amount":["8",3]}},
        "12":{"class_type":"VAEDecodeTiled","inputs":{"samples":["11",0],"vae":["3",0],"tile_size":256,"overlap":64,"temporal_size":16,"temporal_overlap":4}},
        "13":{"class_type":"SaveImage","inputs":{"images":["12",0],"filename_prefix":PREFIX+"/raw"}},
    })
    return g


def monitor(stop, records):
    with (OUT / "resource_samples.jsonl").open("w",encoding="utf-8") as f:
        while not stop.is_set():
            m=MemoryStatus();m.length=ctypes.sizeof(m)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            r=subprocess.run(["nvidia-smi","--query-gpu=memory.used,memory.free,utilization.gpu","--format=csv,noheader,nounits"],capture_output=True,text=True)
            row={"utc":datetime.now(timezone.utc).isoformat(),"ram_free_bytes":m.avail_phys,"commit_free_bytes":m.avail_page}
            if r.returncode==0:
                used,free,util=map(float,r.stdout.strip().split(","));row.update(gpu_used_mib=used,gpu_free_mib=free,gpu_util_percent=util)
            else:
                row["gpu_query_error"]=r.returncode
            records.append(row);f.write(json.dumps(row)+"\n");f.flush()
            if m.avail_phys<4*1024**3 or m.avail_page<4*1024**3 or row.get("gpu_free_mib",0)<2048:
                save(OUT/"memory_guard_triggered.json",row)
                request("/interrupt",{})
                return
            stop.wait(0.5)


def main():
    if (OUT/"submission.json").exists():
        raise RuntimeError("Already submitted; do not create another job")
    prepare()
    queue=request("/queue")
    if queue["queue_running"] or queue["queue_pending"]:
        raise RuntimeError("Existing Comfy jobs are active")
    env=request("/system_stats")
    if env["system"]["ram_free"]<12*1024**3 or env["devices"][0]["vram_free"]<8*1024**3:
        raise RuntimeError("Need at least 12GiB RAM and 8GiB VRAM free")
    save(OUT/"environment.json",env)
    save(OUT/"prompts.json",{"positive":POSITIVE,"negative":NEGATIVE})
    g=build_graph();save(OUT/"workflow_api.json",g)
    save(OUT/"spec.json",{"width":SIZE,"height":SIZE,"frames":LENGTH,"fps":FPS,"steps":STEPS,"seed":SEED,
        "model":"Wan2.1 VACE 1.3B FP16","text_encoder_device":"cpu","sampler":"euler","batch_size":1,
        "guard_min_ram_gib":4,"guard_min_commit_gib":4,"guard_min_gpu_free_mib":2048,"guard_interval_seconds":0.5})
    submitted=request("/prompt",{"prompt":g,"client_id":PREFIX})
    save(OUT/"submission.json",submitted);print(json.dumps(submitted),flush=True)
    records=[];stop=threading.Event();worker=threading.Thread(target=monitor,args=(stop,records),daemon=True);worker.start()
    start=time.monotonic()
    try:
        while True:
            h=request("/history/"+submitted["prompt_id"])
            if submitted["prompt_id"] in h:
                history=h[submitted["prompt_id"]];save(OUT/"history.json",history)
                if history["status"]["status_str"]!="success":
                    raise RuntimeError("Local VACE job failed; inspect saved history and memory guard")
                break
            print(json.dumps({"elapsed":round(time.monotonic()-start),"latest":records[-1] if records else None}),flush=True)
            time.sleep(10)
    finally:
        stop.set();worker.join(timeout=5)
    (DELIVERY/"frames_raw").mkdir(parents=True,exist_ok=True)
    (DELIVERY/"frames_native_128").mkdir(exist_ok=True)
    frames=history["outputs"]["13"]["images"]
    if len(frames)!=LENGTH:
        raise ValueError(f"Unexpected generated length {len(frames)}")
    for i,item in enumerate(frames):
        source=SHARED/item["type"]/item["subfolder"]/item["filename"]
        shutil.copy2(source,DELIVERY/f"frames_raw/{i:04d}.png")
        Image.open(source).convert("RGB").resize((128,128),Image.Resampling.NEAREST).save(DELIVERY/f"frames_native_128/{i:04d}.png")
    times={kind:data["timestamp"] for kind,data in history["status"]["messages"] if "timestamp" in data}
    metrics={"elapsed_seconds":(times["execution_success"]-times["execution_start"])/1000,
        "peak_gpu_used_mib_sampled":max(r.get("gpu_used_mib",0) for r in records),
        "min_ram_free_gib_sampled":min(r["ram_free_bytes"] for r in records)/1024**3,
        "min_commit_free_gib_sampled":min(r["commit_free_bytes"] for r in records)/1024**3,
        "sample_interval_seconds":0.5,"frames":LENGTH,"size":SIZE,"fps":FPS,"alpha_output":False,
        "memory_guard_triggered":(OUT/"memory_guard_triggered.json").exists(),"game_ready":False}
    save(OUT/"metrics.json",metrics);save(DELIVERY/"metrics.json",metrics)
    print(json.dumps({"completed":True,"metrics":metrics}),flush=True)


if __name__=="__main__":
    main()
