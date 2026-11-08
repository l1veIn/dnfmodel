"""Inspect/package the one Grok result, retaining raw and nearest-only previews."""
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

from fatfish_grok_walk import MASTER, MASTER_SHA, OUT, ROOT, RUN, save, sha


def main():
    receipt = json.loads((RUN / "receipt.json").read_text("utf-8"))
    assert receipt["status"] == "done"
    assert sha(MASTER) == MASTER_SHA
    original = OUT / "grok_walk_original.mp4"
    original_sha = sha(original)
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(original)]))
    save(OUT / "ffprobe.json", probe)
    stream = next(s for s in probe["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic"))
    assert (stream["width"], stream["height"], int(stream["nb_read_frames"])) == (960, 960, 97)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(original), "-map", "0:v:0", "-f", "null", "-"], check=True)
    native_dir = OUT / "frames_native_128"
    native_dir.mkdir(exist_ok=True)
    frames = []
    source = sorted((OUT / "frames_raw").glob("*.png"))
    assert len(source) == 97
    for i, path in enumerate(source):
        with Image.open(path) as raw:
            image = raw.convert("RGB").resize((128, 128), Image.Resampling.NEAREST)
        image.save(native_dir / f"{i:04d}.png")
        frames.append(image)
    selection = json.loads((OUT / "cycle_selection.json").read_text("utf-8"))["selection"]
    first = selection["start_frame"]
    stop = selection["end_exclusive"]
    assert (first, stop) == (60, 88)
    sequences = [("walk_native_3x.png", frames), ("cycle_native_3x.png", frames[first:stop])]
    for name, sequence in sequences:
        enlarged = [im.resize((384, 384), Image.Resampling.NEAREST) for im in sequence]
        durations = [round((i+1)*1000/24)-round(i*1000/24) for i in range(len(sequence))]
        enlarged[0].save(OUT / name, save_all=True, append_images=enlarged[1:], duration=durations, loop=0, disposal=0, blend=0)
        with Image.open(OUT / name) as decoded:
            assert decoded.n_frames == len(sequence)
            for i, expected in enumerate(enlarged):
                decoded.seek(i)
                assert not ImageChops.difference(decoded.convert("RGB"), expected).getbbox()
    # Mute by stream copy; preserve the untouched provider MP4 separately.
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(original), "-map", "0:v:0", "-c:v", "copy", "-an", "-movflags", "+faststart", str(OUT / "grok_walk_silent.mp4")], check=True)
    reference = Image.open(RUN / "input/master_gray_1024.png").convert("RGB").resize((128,128), Image.Resampling.NEAREST)
    reference.save(OUT / "master_native_128.png")
    measurements = json.loads((OUT / "motion_measurements.json").read_text("utf-8"))
    cycle_rows = measurements["frames"][first:stop]
    foot_range = [min(r["foot_bottom"] for r in cycle_rows), max(r["foot_bottom"] for r in cycle_rows)]
    report = {
        "trial_completed": True, "provider": "65535", "model": receipt["model"], "task_id": receipt["id"], "generation_jobs": 1,
        "cost_usd": receipt.get("cost_usd"), "actual_video": {"width": 960, "height": 960, "frames": 97, "fps": 24, "duration_seconds": float(stream["duration"]), "alpha": False},
        "requested": {"seconds": 4, "resolution": "720p", "input_mode": "first_frame"},
        "metadata_discrepancy": "Task size says 720x1280; decoded H264 is actually square 960x960. Review uses decoded dimensions.",
        "reference": {"master_sha256": MASTER_SHA, "encoded_reference_sha256": sha(RUN/"input/master_gray_1024.png"), "audit": "evidence/request_audit.json"},
        "processing": {"native_window": "Whole square ->128x128 NEAREST; no coordinate correction, no sharpening, no alpha extraction", "local_inference": False,
                       "review_cycle_source_frames_zero_based": [first, stop-1], "review_cycle_frame_count": stop-first, "review_cycle_seconds": (stop-first)/24,
                       "interpolation": False, "synthetic_endpoint_blending": False, "original_video_preserved": True},
        "validation": {"full_video_decode": True, "apng_all_frames_pixel_readback": True, "approved_master_unchanged": True,
                       "native_foot_bottom_estimate_y": foot_range, "estimated_foot_height_range_pixels": foot_range[1]-foot_range[0]},
        "visual_review": {"quality_compared_to_vace": "Substantially better identity and continuous gait", "observations": [
            "Blue hair, maid dress, whale apron and tail remain recognizable and relatively consistent",
            "Hands remain attached; alternating leg swing is much more coherent than local VACE output",
            "Head/face and fringe are still reinterpreted; skirt, cuffs and hair shapes vary across frames",
            "Native-size vertical bob and shoe contact height vary; complete raw video does not exactly close at frame0",
            "A 28-frame middle segment is supplied as a candidate repeat, not a certified seamless game cycle"],
            "dnf_ready": False, "loop_seam_passed": False, "foot_sliding_passed": False},
        "limitations": ["First-frame guidance only, no original female-mage action video", "No verified last-frame constraint",
                        "Gray RGB video, not transparent sprites", "No original ANI timing, bone anchors or root velocity verified"],
        "game_installation_changed": False, "batch_started": False}
    save(OUT / "review_report.json", report)
    save(RUN / "review_report.json", report)
    evidence = OUT / "evidence"
    evidence.mkdir(exist_ok=True)
    for name in ["spec.json", "capabilities.json", "request_audit.json", "submission.json", "receipt.json", "download.json"]:
        shutil.copy2(RUN / name, evidence / name)
    for name in ["grok-video.json", "async-native-api.json"]:
        shutil.copy2(RUN / "evidence" / name, evidence / name)
    shutil.copy2(ROOT / "design/fatfish/references/UPSTREAM_CREDITS.md", evidence / "UPSTREAM_CREDITS.md")
    assert sha(original) == original_sha
    (OUT / "preview.html").write_text(HTML, encoding="utf-8")
    (OUT / "README.txt").write_text("65535 Grok 走路小样 v01\n任务：" + receipt["id"] + "\n仅 1 次生成，费用 $1.16。原始视频 960×960 /24fps /97 帧。\n" 
        "preview.html 默认播放原视频中第 60–87 帧，28 帧 /1.167 秒；可以切换完整 97 帧。只剪取连续原帧，没有插帧或首尾混合。\n"
        "128×128 最近邻缩小、3 倍显示；保留纯灰背景，未抠图。仍有头脸/裙摆变化、脚底高度波动，未达到 DNF 成品验收。\n"
        "原始视频保留音轨；silent 版只去掉音轨，图像流未重编码。原版女法动作没有传入本次接口。\n"
        "来源与许可见 evidence/UPSTREAM_CREDITS.md。未修改游戏、未批量。\n", encoding="utf-8")
    manifest = {str(p.relative_to(OUT)).replace("\\", "/"): sha(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "SHA256.json"}
    save(OUT / "SHA256.json", manifest)
    for relative, digest in manifest.items():
        assert sha(OUT / relative) == digest
    bundle = ROOT / "output/fatfish_grok_walk_v01.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob("*")):
            if p.is_file(): z.write(p, str(p.relative_to(OUT.parent)))
    with zipfile.ZipFile(bundle) as z: assert z.testzip() is None
    status_path = ROOT / "preparation_status.json"
    status = json.loads(status_path.read_text("utf-8"))
    status["grok_walk_trial"] = {"completed": True, "game_ready": False, "jobs": 1, "task_id": receipt["id"], "cost_usd": receipt.get("cost_usd"),
        "preview": "output/Fatfish_Grok_Walk_v01/preview.html", "preview_url": "http://127.0.0.1:8788/preview.html", "batch_started": False, "game_installation_changed": False}
    save(status_path, status)
    readme = ROOT / "README.md"
    content = readme.read_text("utf-8")
    if "Grok 走路小样 v01" not in content:
        content += "\n\nGrok 走路小样 v01：65535 `grok-imagine-video-1.5-preview`，实际携带已确认主帧，1 次云端任务，费用 $1.16。输出实际 960×960、24fps、97 帧（4.042 秒）。造型和步态比本地 VACE 稳定；仍有头脸、发梢与裙摆变化，落脚和接缝未通过成品验收。最近邻 128×128 预览、原始视频和 60–87 帧候选循环见 `output/Fatfish_Grok_Walk_v01/preview.html`。未传原版动作视频、未批量、未安装补丁。\n"
        readme.write_text(content, encoding="utf-8")
    print(json.dumps({"package_verified": True, "bundle_bytes": bundle.stat().st_size, "bundle_sha256": sha(bundle),
        "candidate_cycle": [first, stop-1], "foot_bottom_range": foot_range, "dnf_ready": False}, ensure_ascii=False))


HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>大肥鱼 · Grok 步行小样</title><style>
body{margin:0;background:#151d28;color:#e8eff8;font:16px system-ui,"Microsoft YaHei",sans-serif}main{max-width:1120px;margin:auto;padding:28px}h1{font-size:28px;margin:0 0 12px}p{line-height:1.7;color:#b8c9dc}.badge{color:#9fdfce}button,select,input{font:inherit}button,select{background:#28384d;color:white;border:1px solid #526c8b;border-radius:6px;padding:8px 12px}button{cursor:pointer}.bar{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:20px 0}.compare{display:flex;flex-wrap:wrap;gap:24px}figure{margin:0}figcaption{margin:0 0 10px;color:#b8c9dc}.stage{position:relative;width:384px;height:384px;background:#808080;border:1px solid #526074}.stage img{width:100%;height:100%;image-rendering:pixelated}.guide{display:none;position:absolute;top:90.625%;left:0;right:0;border-top:1px solid #ffcf73;pointer-events:none}.center{display:none;position:absolute;left:50%;top:0;bottom:0;border-left:1px solid #67d5e780;pointer-events:none}.ghost{position:absolute;inset:0;opacity:.22;display:none}.guides .guide,.guides .center{display:block}.ghost-on .ghost{display:block}input[type=range]{width:min(620px,100%)}a{color:#8bc9ff}small{color:#a9bed2}video{max-width:100%;width:480px;background:#808080}details{margin-top:24px}#note{color:#d9b987}label{cursor:pointer}@media(max-width:450px){main{padding:15px}.stage{width:320px;height:320px}}
</style><main><h1>大肥鱼 · Grok 步行小样</h1><div class="badge">一次云端生成 · 真实主帧参考 · $1.16 · 未批量</div>
<p>默认播放中段 60–87 帧，共 28 帧 / 1.167 秒。只截取连续原帧，未插帧、未混合首尾。<br>统一缩到 128×128 最近邻、放大 3 倍显示；背景保留纯灰。这是候选动作，仍需检查头脸、裙摆和落脚。</p>
<div class="bar"><label>片段 <select id="mode"><option value="cycle">候选循环 · 28 帧</option><option value="full">完整生成 · 97 帧</option></select></label><button id="play">暂停</button><button id="prev">上一帧</button><button id="next">下一帧</button><label><input id="guides" type="checkbox" checked>固定落脚线</label><label><input id="ghost" type="checkbox">叠加主帧</label></div>
<div class="compare guides" id="compare"><figure><figcaption>已确认主帧（不改造型）</figcaption><div class="stage"><img src="master_native_128.png" alt="确认的主帧"><i class="guide"></i><i class="center"></i></div></figure><figure><figcaption id="counter">Grok 输出</figcaption><div class="stage"><img id="frame" src="frames_native_128/0060.png" alt="生成的步行帧"><img class="ghost" src="master_native_128.png" alt="半透明主帧对齐参考"><i class="guide"></i><i class="center"></i></div></figure></div>
<div class="bar"><input id="timeline" type="range" min="0" max="27" value="0" aria-label="逐帧浏览"><span id="time"></span></div>
<p id="note">黄线固定在主帧脚底附近，便于观察高度波动。首尾和滑步尚未按游戏坐标验收。</p>
<p>这次通过首帧和提示词引导动作，没有传入原版女法师骨架或动作视频；输出为 RGB 视频，尚未抠透明背景。</p>
<details><summary>原始分辨率视频（静音副本）</summary><p><video controls loop muted playsinline preload="metadata" src="grok_walk_silent.mp4"></video></p></details>
<div class="bar"><a href="grok_walk_silent.mp4">静音视频</a><a href="grok_walk_original.mp4">未修改原视频</a><a href="cycle_native_3x.png">循环动图</a><a href="contact_sheet_raw.png">连续动作总览</a><a href="review_report.json">检查记录</a></div>
<small>实际视频 960×960 / 24fps / 97 帧。任务 vid_bfd86f4224d7e8e23b777a3c5ff37b53。主帧哈希与实际上传参考均已核对；未修改游戏目录。</small>
</main><script>
const $=id=>document.getElementById(id);let start=60,count=28,index=0,playing=true,last=performance.now();
const cache=[];for(let i=0;i<97;i++){const im=new Image;im.src=`frames_native_128/${String(i).padStart(4,'0')}.png`;cache.push(im)}
function render(){const n=start+index;$('frame').src=cache[n].src;$('counter').textContent=`Grok 输出 · 原视频第 ${n} 帧`;$('timeline').value=index;$('time').textContent=`${index+1} / ${count} · 24 fps`;$('play').textContent=playing?'暂停':'播放'}
function step(n){playing=false;index=(index+n+count)%count;render()}
$('play').onclick=()=>{playing=!playing;last=performance.now();render()};$('prev').onclick=()=>step(-1);$('next').onclick=()=>step(1);
$('timeline').oninput=e=>{playing=false;index=Number(e.target.value);render()};$('mode').onchange=e=>{start=e.target.value==='cycle'?60:0;count=e.target.value==='cycle'?28:97;index=0;$('timeline').max=count-1;last=performance.now();render()};
$('guides').onchange=e=>$('compare').classList.toggle('guides',e.target.checked);$('ghost').onchange=e=>$('compare').classList.toggle('ghost-on',e.target.checked);
function tick(t){if(playing&&t-last>=1000/24){const n=Math.floor((t-last)/(1000/24));index=(index+n)%count;last+=n*(1000/24);render()}requestAnimationFrame(tick)}render();requestAnimationFrame(tick);
</script></html>'''


if __name__ == "__main__": main()
