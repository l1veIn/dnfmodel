"""Build transparent-source playback previews for the two-reference idle pilot.

This only composes existing pixels. It never aligns, morphs, or regenerates frames.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "output/Fatfish_Idle_Native_v01/manifest.json"
CANVAS = (1024, 1024)
MATTE = (38, 44, 57, 255)


def image_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def font(size: int):
    for path in (Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/arial.ttf")):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def opaque_scaled(image: Image.Image, size: int = 512) -> Image.Image:
    # One common scale for the complete source canvas, without bounding-box fitting.
    canvas = Image.new("RGBA", CANVAS, MATTE)
    canvas.alpha_composite(image)
    return canvas.resize((size, size), Image.Resampling.NEAREST).convert("RGB")


def write_gif(frames: list[Image.Image], durations: list[int], path: Path):
    # A shared palette avoids palette changes being mistaken for animation flicker.
    atlas = Image.new("RGB", (frames[0].width, frames[0].height * len(frames)))
    for i, frame in enumerate(frames):
        atlas.paste(frame, (0, i * frame.height))
    palette = atlas.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    converted = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    converted[0].save(path, save_all=True, append_images=converted[1:],
                      duration=durations, loop=0, disposal=2, optimize=False)


HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>肥鱼待机 · 两图逐帧试验</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#141923;color:#e9edf5;font:15px/1.6 system-ui,"Microsoft YaHei",sans-serif}
main{max-width:1220px;margin:0 auto;padding:24px}h1{font-size:24px;margin:0 0 5px}p{margin:6px 0;color:#aebbd0}.controls{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin:18px 0}
button,select{font:inherit;padding:7px 12px;border:1px solid #44516a;background:#222c3c;color:#edf2ff;border-radius:7px;cursor:pointer}button:hover{background:#30415a}label{display:flex;align-items:center;gap:7px}.frame{margin-left:auto;font-variant-numeric:tabular-nums;color:#9dd9ff}.panels{display:grid;grid-template-columns:1fr 1fr;gap:16px}.panel{background:#1d2533;border:1px solid #354359;border-radius:12px;overflow:hidden}.caption{padding:9px 14px;font-weight:600}.stage{width:100%;aspect-ratio:1;position:relative;background-color:#262c39;background-image:linear-gradient(45deg,#303747 25%,transparent 25%),linear-gradient(-45deg,#303747 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#303747 75%),linear-gradient(-45deg,transparent 75%,#303747 75%);background-size:24px 24px;background-position:0 0,0 12px,12px -12px,-12px 0}
canvas{display:block;width:100%;height:100%}.dark .stage{background:#171c27}.light .stage{background:#e7e9ee}.pixel canvas{image-rendering:pixelated}.scrub{display:flex;align-items:center;gap:14px;margin:16px 0}.scrub input{flex:1;accent-color:#71c3fc}.note{padding:12px 15px;border-left:3px solid #689bcc;background:#1b2636;border-radius:5px}.thumbs{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px}.thumb{padding:0;overflow:hidden}.thumb img{display:block;width:100%;background:#262c39}.thumb span{display:block;padding:6px;font-size:13px}.thumb.selected{border-color:#8fd0ff;box-shadow:0 0 0 1px #8fd0ff}.footer{font-size:12px;margin-top:16px;word-break:break-word}@media(max-width:650px){main{padding:14px}.panels{grid-template-columns:1fr}.frame{margin-left:0}.thumbs{grid-template-columns:repeat(2,1fr)}h1{font-size:20px}}
</style></head><body><main>
<h1 id="heading">肥鱼待机 · 两图逐帧试验</h1>
<p id="model"></p>
<div class="controls"><button id="play" type="button">暂停</button><button id="prev" type="button">上一帧</button><button id="next" type="button">下一帧</button>
<label>速度 <select id="speed"><option value="1">1×</option><option value="0.5">0.5×</option><option value="0.25">0.25×</option></select></label>
<label>背景 <select id="background"><option value="checker">棋盘格</option><option value="dark">深色</option><option value="light">浅色</option></select></label>
<label>显示 <select id="display"><option value="raw">完整原图画布</option><option value="pixel">128px 最近邻</option></select></label>
<span class="frame" id="frame" aria-live="off"></span></div>
<div class="panels"><section class="panel"><div class="caption" id="sourceLabel">女法原版动作参考</div><div class="stage"><canvas id="source" width="1024" height="1024" aria-label="女法原版动作参考"></canvas></div></section><section class="panel"><div class="caption" id="targetLabel">肥鱼生成结果</div><div class="stage"><canvas id="target" width="1024" height="1024" aria-label="肥鱼生成结果"></canvas></div></section></div>
<div class="scrub"><label for="scrubber">当前帧</label><input id="scrubber" type="range" min="0" max="3" value="0" step="1"><span id="timing"></span></div>
<p class="note">默认展示固定画布上的原始生成结果，未逐帧缩放、对齐或添加中间帧。循环会直接从末帧接回首帧。<span id="timingNote"></span></p>
<div class="thumbs" id="thumbs"></div><p class="footer">每次生成仅两张参考：首帧为肥鱼母版＋当前女法帧；后续为上一张肥鱼结果＋当前女法帧。</p>
</main><script>
const DATA=__DATA__;
let index=0,playing=true,speed=1,elapsed=0,last=0;
const $=s=>document.querySelector(s),frames=DATA.frames;
const source=$('#source'),target=$('#target'),sc=source.getContext('2d'),tc=target.getContext('2d');
$('#heading').textContent=DATA.header;document.title=DATA.header;$('#sourceLabel').textContent=DATA.source_label;source.setAttribute('aria-label',DATA.source_label);$('#targetLabel').textContent=DATA.target_label;target.setAttribute('aria-label',DATA.target_label);
$('#model').textContent=DATA.model+' · '+frames.length+' 帧 · 手工配时 '+frames.map(f=>f.duration_ms).join('/')+'ms · IMG '+frames.map(f=>f.source_index).join(' → ')+' → '+frames[0].source_index;
$('#timingNote').textContent=DATA.timing_note||'配时来自手工预览标注，未解析游戏 ANI。';
$('#scrubber').max=frames.length-1;
const thumbs=frames.map((f,i)=>{const b=document.createElement('button');b.type='button';b.className='thumb';b.setAttribute('aria-label','查看 IMG '+f.source_index);const img=document.createElement('img');img.src=f.target_uri;img.alt='肥鱼 IMG '+f.source_index;const span=document.createElement('span');span.textContent='IMG '+f.source_index+' · '+f.duration_ms+'ms';b.append(img,span);b.onclick=()=>step(i);$('#thumbs').appendChild(b);return b;});
function setPlaying(value){playing=value;$('#play').textContent=playing?'暂停':'播放';last=performance.now();}
function step(i){setPlaying(false);index=(i+frames.length)%frames.length;elapsed=0;render();}
function draw(ctx,img){ctx.clearRect(0,0,1024,1024);if($('#display').value==='pixel'){const small=document.createElement('canvas');small.width=small.height=128;const smallContext=small.getContext('2d');smallContext.imageSmoothingEnabled=false;smallContext.drawImage(img,0,0,128,128);ctx.imageSmoothingEnabled=false;ctx.drawImage(small,0,0,1024,1024);}else{ctx.imageSmoothingEnabled=true;ctx.drawImage(img,0,0);}}
function render(){const f=frames[index];draw(sc,f.sourceImage);draw(tc,f.targetImage);$('#frame').textContent=(index+1)+' / '+frames.length+' · IMG '+f.source_index;$('#scrubber').value=index;$('#timing').textContent=f.duration_ms+' ms';thumbs.forEach((t,i)=>t.classList.toggle('selected',i===index));}
$('#play').onclick=()=>setPlaying(!playing);$('#prev').onclick=()=>step(index-1);$('#next').onclick=()=>step(index+1);$('#scrubber').oninput=e=>step(Number(e.target.value));
$('#speed').onchange=e=>{speed=Number(e.target.value);last=performance.now();};
$('#background').onchange=e=>{document.body.classList.remove('dark','light');if(e.target.value!=='checker')document.body.classList.add(e.target.value);};
$('#display').onchange=()=>{document.body.classList.toggle('pixel',$('#display').value==='pixel');render();};
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','BUTTON'].includes(document.activeElement.tagName))return;if(e.code==='Space'){e.preventDefault();setPlaying(!playing);}if(e.code==='ArrowLeft')step(index-1);if(e.code==='ArrowRight')step(index+1);});
function tick(now){if(last&&playing){elapsed+=Math.min(now-last,1000)*speed;while(elapsed>=frames[index].duration_ms){elapsed-=frames[index].duration_ms;index=(index+1)%frames.length;render();}}last=now;requestAnimationFrame(tick);}
Promise.all(frames.flatMap(f=>[['sourceImage','source_uri'],['targetImage','target_uri']].map(([key,uri])=>new Promise((resolve,reject)=>{const img=new Image;img.onload=()=>{f[key]=img;resolve();};img.onerror=reject;img.src=f[uri];})))).then(()=>{render();requestAnimationFrame(tick);}).catch(()=>{$('#frame').textContent='图片加载失败';setPlaying(false);});
window.idlePreviewState=()=>({index,sourceIndex:frames[index].source_index,playing,speed,count:frames.length,canvas:[source.width,source.height],loaded:frames.every(f=>f.sourceImage&&f.targetImage),timing:frames.map(f=>f.duration_ms),view:$('#display').value});
</script></body></html>'''


def build(manifest_path: Path) -> dict:
    manifest_path = manifest_path.resolve()
    run = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames = manifest["frames"]
    if not frames:
        raise ValueError("No frames in manifest")
    out = run / "preview"
    out.mkdir(parents=True, exist_ok=True)
    source_label = manifest.get("source_label", "女法原版动作参考")
    target_label = manifest.get("target_label", "肥鱼生成结果")
    source_artifact_label = manifest.get("source_label", "女法原版")
    target_artifact_label = manifest.get("target_label", "肥鱼生成")
    source_sheet_label = manifest.get("source_label", "女法")
    target_sheet_label = manifest.get("target_label", "肥鱼")
    data = {"model": manifest["model"], "timing_note": manifest.get("timing_note", ""),
            "header": manifest.get("header", "肥鱼待机 · 两图逐帧试验"),
            "source_label": source_label, "target_label": target_label, "frames": []}
    sources, targets, hashes, alpha_details = [], [], {}, {}
    for frame in frames:
        pose, raw = run / frame["pose"], run / frame["output"]
        p = Image.open(pose).convert("RGBA")
        with Image.open(raw) as original:
            native_mode = original.mode
            native_alpha = "A" in native_mode or "transparency" in original.info
            r = original.convert("RGBA")
        if p.size != CANVAS or r.size != CANVAS:
            raise ValueError(f"Expected common 1024 canvas, found {pose.name}={p.size}, {raw.name}={r.size}")
        sources.append(p)
        targets.append(r)
        hashes[str(raw.relative_to(run))] = hashlib.sha256(raw.read_bytes()).hexdigest()
        alpha_details[str(raw.relative_to(run))] = {"source_mode": native_mode,
                                                   "has_native_alpha": native_alpha,
                                                   "alpha_extrema": list(r.getchannel("A").getextrema())}
        data["frames"].append({"source_index": frame["source_index"], "duration_ms": int(frame["duration_ms"]),
                               "source_uri": image_uri(pose), "target_uri": image_uri(raw)})
    (out / "index.html").write_text(HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    durations = [int(f["duration_ms"]) for f in frames]
    if any(d <= 0 or d % 10 for d in durations):
        raise ValueError("GIF timing requires positive durations in multiples of 10 ms")
    source_previews = [opaque_scaled(f) for f in sources]
    target_previews = [opaque_scaled(f) for f in targets]
    write_gif(target_previews, durations, out / "idle_loop.gif")
    write_gif(target_previews, [d * 2 for d in durations], out / "idle_loop_half_speed.gif")
    comparisons = []
    for frame, source_img, target_img in zip(frames, source_previews, target_previews):
        canvas = Image.new("RGB", (1024, 554), MATTE[:3])
        canvas.paste(source_img, (0, 42))
        canvas.paste(target_img, (512, 42))
        draw = ImageDraw.Draw(canvas)
        draw.text((16, 9), f"{source_artifact_label} · IMG {frame['source_index']}", fill="#e9edf5", font=font(20))
        draw.text((528, 9), f"{target_artifact_label} · IMG {frame['source_index']}", fill="#e9edf5", font=font(20))
        comparisons.append(canvas)
    write_gif(comparisons, durations, out / "comparison_loop.gif")
    sheet = Image.new("RGB", (256 * len(frames), 564), MATTE[:3])
    draw = ImageDraw.Draw(sheet)
    for i, (frame, original, target_img) in enumerate(zip(frames, source_previews, target_previews)):
        sheet.paste(original.resize((256, 256), Image.Resampling.NEAREST), (i * 256, 26))
        sheet.paste(target_img.resize((256, 256), Image.Resampling.NEAREST), (i * 256, 308))
        draw.text((i * 256 + 8, 4), f"{source_sheet_label} IMG {frame['source_index']}", fill="#e9edf5", font=font(15))
        draw.text((i * 256 + 8, 286), f"{target_sheet_label} IMG {frame['source_index']}", fill="#e9edf5", font=font(15))
    sheet.save(out / "contact_sheet.png")
    report = {"frame_count": len(frames), "source_order": [f["source_index"] for f in frames],
              "duration_ms": durations, "cycle_duration_ms": sum(durations), "canvas": list(CANVAS),
              "generated_gif_size": [512, 512], "comparison_gif_size": [1024, 554],
              "raw_alignment_applied": False, "interpolation_frames": 0,
              "raw_sha256": hashes, "raw_alpha": alpha_details,
              "artifacts": ["index.html", "idle_loop.gif", "idle_loop_half_speed.gif", "comparison_loop.gif", "contact_sheet.png"]}
    report["gif_metadata"] = {}
    for name in ("idle_loop.gif", "idle_loop_half_speed.gif", "comparison_loop.gif"):
        with Image.open(out / name) as gif:
            actual_durations = []
            for i in range(gif.n_frames):
                gif.seek(i)
                actual_durations.append(gif.info.get("duration", 0))
            report["gif_metadata"][name] = {"frames": gif.n_frames,
                                             "durations_ms": actual_durations,
                                             "cycle_ms": sum(actual_durations),
                                             "loop": gif.info.get("loop")}
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        # Repeat the four-frame cycle for a usable six-second video, without tweening.
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-stream_loop", "-1", "-i", str(out / "comparison_loop.gif"),
                   "-t", "6", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out / "comparison_loop.mp4")]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode == 0:
            report["artifacts"].append("comparison_loop.mp4")
        else:
            report["mp4_error"] = result.stderr[-1500:]
    # Assert this builder left all generated source files untouched.
    for name, digest in hashes.items():
        assert hashlib.sha256((run / name).read_bytes()).hexdigest() == digest
    report["raw_files_unchanged"] = True
    (out / "preview_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"preview_directory": str(out), **report}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    print(json.dumps(build(args.manifest), ensure_ascii=False, indent=2))
