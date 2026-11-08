"""Compare the two four-frame native idle pilots on their original canvases."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from preview_idle_native import CANVAS, MATTE, font, image_uri, opaque_scaled, write_gif


ROOT = Path(__file__).resolve().parents[1]
OLD_DEFAULT = ROOT / "output/Fatfish_Idle_Native_v01/manifest.json"
NEW_DEFAULT = ROOT / "output/Fatfish_Idle_Body_Native_v02/manifest.json"


HTML = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>肥鱼待机 · 原版与两轮生成对照</title><style>
*{box-sizing:border-box}body{margin:0;background:#141923;color:#e9edf5;font:15px/1.6 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1600px;margin:auto;padding:24px}h1{font-size:24px;margin:0 0 5px}p{color:#aebbd0;margin:6px 0}a{color:#9dd9ff}.controls{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin:18px 0}button,select{font:inherit;padding:7px 12px;border:1px solid #44516a;background:#222c3c;color:#edf2ff;border-radius:7px;cursor:pointer}button:hover{background:#30415a}label{display:flex;align-items:center;gap:7px}.frame{margin-left:auto;color:#9dd9ff;font-variant-numeric:tabular-nums}.panels{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.panel{background:#1d2533;border:1px solid #354359;border-radius:12px;overflow:hidden}.caption{padding:9px 12px;font-weight:600}.stage{width:100%;aspect-ratio:1;background-color:#262c39;background-image:linear-gradient(45deg,#303747 25%,transparent 25%),linear-gradient(-45deg,#303747 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#303747 75%),linear-gradient(-45deg,transparent 75%,#303747 75%);background-size:24px 24px;background-position:0 0,0 12px,12px -12px,-12px 0}canvas{display:block;width:100%;height:100%}.dark .stage{background:#171c27}.light .stage{background:#e7e9ee}.pixel canvas{image-rendering:pixelated}.scrub{display:flex;align-items:center;gap:14px;margin:16px 0}.scrub input{flex:1;accent-color:#71c3fc}.note{padding:12px 15px;border-left:3px solid #689bcc;background:#1b2636;border-radius:5px}.links{margin-top:16px;display:flex;gap:24px;flex-wrap:wrap}@media(max-width:850px){main{padding:14px}.panels{grid-template-columns:1fr}.frame{margin-left:0}}
</style></head><body><main><h1>肥鱼待机 · 原版与两轮生成对照</h1><p id="subtitle"></p>
<div class="controls"><button id="play" type="button">暂停</button><button id="prev" type="button">上一帧</button><button id="next" type="button">下一帧</button>
<label>速度 <select id="speed"><option value="1">1×</option><option value="0.5">0.5×</option><option value="0.25">0.25×</option></select></label>
<label>参考图 <select id="reference"><option value="source">完整装扮</option><option value="body">女法素体</option></select></label>
<label>背景 <select id="background"><option value="checker">棋盘格</option><option value="dark">深色</option><option value="light">浅色</option></select></label>
<label>显示 <select id="display"><option value="raw">完整原图画布</option><option value="pixel">128px 最近邻</option></select></label><span class="frame" id="frame"></span></div>
<div class="panels"><section class="panel"><div id="sourceLabel" class="caption">女法原版完整装扮参考</div><div class="stage"><canvas id="source" width="1024" height="1024" aria-label="女法动作参考"></canvas></div></section><section class="panel"><div class="caption">第一轮 · 完整装扮参考</div><div class="stage"><canvas id="old" width="1024" height="1024" aria-label="第一轮肥鱼结果"></canvas></div></section><section class="panel"><div class="caption">第二轮 · 素体参考</div><div class="stage"><canvas id="new" width="1024" height="1024" aria-label="第二轮肥鱼结果"></canvas></div></section></div>
<div class="scrub"><label for="scrubber">当前帧</label><input id="scrubber" type="range" min="0" max="3" value="0" step="1"><span id="timing"></span></div>
<p class="note">两轮都使用固定 1024×1024 原始画布；未逐帧居中、缩放、对齐或添加中间帧。每帧手工配时 100ms，尚未解析游戏 ANI；末帧直接接回首帧。</p>
<p>两轮均为两图接力：第一帧输入肥鱼母版＋当前女法帧；后续输入上一张肥鱼结果＋当前女法帧。左侧可切换查看完整装扮与素体参考。</p>
<div class="links"><a href="index.html">查看第二轮单独预览</a><a href="compare_v01_v02.gif">查看对照 GIF</a><a href="compare_v01_v02.mp4">查看对照视频</a><a href="contact_sheet_compare.png">查看逐帧对照</a></div>
</main><script>
const DATA=__DATA__,frames=DATA.frames,$=s=>document.querySelector(s);let index=0,playing=true,speed=1,elapsed=0,last=0;
const contexts=['source','old','new'].map(id=>$('#'+id).getContext('2d'));
$('#subtitle').textContent=DATA.model+' · IMG '+frames.map(f=>f.source_index).join(' → ')+' → '+frames[0].source_index;$('#scrubber').max=frames.length-1;
function setPlaying(v){playing=v;$('#play').textContent=v?'暂停':'播放';last=performance.now();}
function draw(ctx,img){ctx.clearRect(0,0,1024,1024);if($('#display').value==='pixel'){const small=document.createElement('canvas');small.width=small.height=128;const c=small.getContext('2d');c.imageSmoothingEnabled=false;c.drawImage(img,0,0,128,128);ctx.imageSmoothingEnabled=false;ctx.drawImage(small,0,0,1024,1024);}else{ctx.imageSmoothingEnabled=true;ctx.drawImage(img,0,0);}}
function render(){const f=frames[index],reference=$('#reference').value;draw(contexts[0],f[reference+'Image']);draw(contexts[1],f.oldImage);draw(contexts[2],f.newImage);$('#sourceLabel').textContent=reference==='body'?'女法素体动作参考':'女法原版完整装扮参考';$('#frame').textContent=(index+1)+' / '+frames.length+' · IMG '+f.source_index;$('#scrubber').value=index;$('#timing').textContent=f.duration_ms+' ms';}
function step(i){setPlaying(false);index=(i+frames.length)%frames.length;elapsed=0;render();}
$('#play').onclick=()=>setPlaying(!playing);$('#prev').onclick=()=>step(index-1);$('#next').onclick=()=>step(index+1);$('#scrubber').oninput=e=>step(Number(e.target.value));$('#speed').onchange=e=>{speed=Number(e.target.value);last=performance.now();};$('#reference').onchange=render;$('#background').onchange=e=>{document.body.classList.remove('dark','light');if(e.target.value!=='checker')document.body.classList.add(e.target.value);};$('#display').onchange=()=>{document.body.classList.toggle('pixel',$('#display').value==='pixel');render();};
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','BUTTON'].includes(document.activeElement.tagName))return;if(e.code==='Space'){e.preventDefault();setPlaying(!playing);}if(e.code==='ArrowLeft')step(index-1);if(e.code==='ArrowRight')step(index+1);});
function tick(now){if(last&&playing){elapsed+=Math.min(now-last,1000)*speed;while(elapsed>=frames[index].duration_ms){elapsed-=frames[index].duration_ms;index=(index+1)%frames.length;render();}}last=now;requestAnimationFrame(tick);}
Promise.all(frames.flatMap(f=>['source','body','old','new'].map(key=>new Promise((resolve,reject)=>{const img=new Image;img.onload=()=>{f[key+'Image']=img;resolve();};img.onerror=reject;img.src=f[key+'_uri'];})))).then(()=>{render();requestAnimationFrame(tick);}).catch(()=>{$('#frame').textContent='图片加载失败';setPlaying(false);});
window.idleCompareState=()=>({index,sourceIndex:frames[index].source_index,playing,speed,count:frames.length,loaded:frames.every(f=>['source','body','old','new'].every(key=>f[key+'Image'])),reference:$('#reference').value,canvas:[1024,1024],timing:frames.map(f=>f.duration_ms),view:$('#display').value});
</script></body></html>'''


def rgba(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    if image.size != CANVAS:
        raise ValueError(f"Expected common canvas {CANVAS}: {path} is {image.size}")
    return image


def build(old_manifest: Path, new_manifest: Path) -> dict:
    old_manifest, new_manifest = old_manifest.resolve(), new_manifest.resolve()
    old_run, new_run = old_manifest.parent, new_manifest.parent
    old, new = (json.loads(p.read_text(encoding="utf-8")) for p in (old_manifest, new_manifest))
    old_frames, new_frames = old["frames"], new["frames"]
    old_order = [f["source_index"] for f in old_frames]
    new_order = [f["source_index"] for f in new_frames]
    if old_order != new_order or not old_order:
        raise ValueError("Comparison requires matching nonempty source frame order")
    durations = [int(f["duration_ms"]) for f in new_frames]
    if durations != [int(f["duration_ms"]) for f in old_frames] or durations != [100] * len(new_frames):
        raise ValueError("This idle comparison requires matching manual 100 ms timings")
    out = new_run / "preview"
    out.mkdir(parents=True, exist_ok=True)
    data = {"model": new["model"], "frames": []}
    hashes, images = {}, []
    for old_frame, new_frame in zip(old_frames, new_frames):
        files = {"source": old_run / old_frame["pose"], "body": new_run / new_frame["pose"],
                 "old": old_run / old_frame["output"], "new": new_run / new_frame["output"]}
        current = {key: rgba(path) for key, path in files.items()}
        images.append(current)
        item = {"source_index": new_frame["source_index"], "duration_ms": int(new_frame["duration_ms"])}
        for key, path in files.items():
            item[key + "_uri"] = image_uri(path)
            hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        data["frames"].append(item)
    (out / "compare_v01_v02.html").write_text(HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    labels = {"source": "女法原版完整装扮参考", "body": "女法素体动作参考", "old": "第一轮 · 完整装扮参考", "new": "第二轮 · 素体参考"}
    comparison_frames = []
    for frame, current in zip(new_frames, images):
        image = Image.new("RGB", (1536, 554), MATTE[:3])
        draw = ImageDraw.Draw(image)
        for i, key in enumerate(("source", "old", "new")):
            image.paste(opaque_scaled(current[key]), (i * 512, 42))
            draw.text((i * 512 + 14, 9), f"{labels[key]} · IMG {frame['source_index']}", font=font(20), fill="#e9edf5")
        comparison_frames.append(image)
    write_gif(comparison_frames, durations, out / "compare_v01_v02.gif")
    write_gif(comparison_frames, [d * 2 for d in durations], out / "compare_v01_v02_half_speed.gif")
    sheet = Image.new("RGB", (256 * len(new_frames), 282 * 4), MATTE[:3])
    draw = ImageDraw.Draw(sheet)
    for row, key in enumerate(("source", "body", "old", "new")):
        for col, (frame, current) in enumerate(zip(new_frames, images)):
            x, y = col * 256, row * 282
            draw.text((x + 7, y + 4), f"{labels[key]} IMG {frame['source_index']}", font=font(13), fill="#e9edf5")
            sheet.paste(opaque_scaled(current[key], 256), (x, y + 26))
    sheet.save(out / "contact_sheet_compare.png")
    report = {"old_manifest": str(old_manifest), "new_manifest": str(new_manifest), "source_order": new_order,
              "frame_count": len(new_frames), "duration_ms": durations, "cycle_duration_ms": sum(durations),
              "common_canvas": list(CANVAS), "gif_size": [1536, 554], "alignment_applied": False,
              "interpolation_frames": 0, "source_sha256": hashes,
              "artifacts": ["compare_v01_v02.html", "compare_v01_v02.gif", "compare_v01_v02_half_speed.gif", "contact_sheet_compare.png"]}
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        result = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-stream_loop", "-1", "-i", str(out / "compare_v01_v02.gif"),
                                 "-t", "6", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out / "compare_v01_v02.mp4")],
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode == 0:
            report["artifacts"].append("compare_v01_v02.mp4")
        else:
            report["mp4_error"] = result.stderr[-1500:]
    with Image.open(out / "compare_v01_v02.gif") as gif:
        actual_durations = []
        for i in range(gif.n_frames):
            gif.seek(i)
            actual_durations.append(gif.info.get("duration", 0))
        report["gif_metadata"] = {"frame_count": gif.n_frames, "duration_ms": actual_durations, "cycle_ms": sum(actual_durations)}
    for name, digest in hashes.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
    report["all_input_files_unchanged"] = True
    (out / "comparison_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"preview_directory": str(out), **report}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-manifest", type=Path, default=OLD_DEFAULT)
    parser.add_argument("--new-manifest", type=Path, default=NEW_DEFAULT)
    args = parser.parse_args()
    print(json.dumps(build(args.old_manifest, args.new_manifest), ensure_ascii=False, indent=2))
