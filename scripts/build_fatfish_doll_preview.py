"""Standalone player page: original vs new native doll vs previous v02, clip by clip, at true pixels."""
from __future__ import annotations

import base64
import json

from PIL import Image

from fatfish_doll import ROOT
from fatfish_doll_render import OUT, clips

NATIVE = ROOT / "materials/female_mage/reference_composite/frames"
OLD = ROOT / "output/Fatfish_Complete_v01/native_frames"
BOX = (140, 240, 380, 400)
CELL = (BOX[2] - BOX[0], BOX[3] - BOX[1])
COLS = 15
PREVIEW = OUT / "preview"

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>肥鱼纸娃娃 v03</title>
<style>
:root{--bg:#10141f;--panel:#1a2132;--line:#2c3650;--ink:#e6ebf7;--dim:#93a0bd;--accent:#6ea8ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,"Microsoft YaHei",sans-serif}
header{padding:18px 20px 6px}h1{margin:0;font-size:20px}header p{margin:4px 0 0;color:var(--dim)}
.wrap{display:grid;grid-template-columns:220px 1fr;gap:14px;padding:14px 20px 28px}
@media(max-width:760px){.wrap{grid-template-columns:1fr}.clips{max-height:180px}}
.clips{background:var(--panel);border:1px solid var(--line);border-radius:8px;max-height:calc(100vh - 110px);overflow:auto;padding:6px}
.clips button{display:flex;justify-content:space-between;width:100%;background:none;border:0;color:var(--ink);padding:7px 9px;border-radius:6px;font:inherit;cursor:pointer;text-align:left}
.clips button:hover{background:#242d44}.clips button.on{background:var(--accent);color:#0b1020}
.clips small{opacity:.7}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin-bottom:12px}
.bar button,.bar select{background:#242d44;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:5px 10px;font:inherit;cursor:pointer}
.stage{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
figure{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden}
figcaption{padding:6px 10px;color:var(--dim);border-bottom:1px solid var(--line)}
.view{width:100%;display:flex;justify-content:center;background:linear-gradient(#55617a 0 72%,#3a4254 72% 100%)}
canvas{image-rendering:pixelated;max-width:100%;display:block}
</style></head><body>
<header><h1>大肥鱼女法师 · 原生纸娃娃 v03</h1><p>原生逐帧分层 + 手绘部件。三栏同一帧位、同一世界坐标、100 ms 手工配时；1× 才是游戏里的真实观感。</p></header>
<div class="wrap"><nav class="clips" id="clips"></nav><main>
<div class="bar"><button id="play">暂停</button><button id="prev">上一帧</button><button id="next">下一帧</button>
<label>缩放 <select id="zoom"><option value="1">1× 游戏实际</option><option value="2" selected>2×</option><option value="3">3×</option></select></label>
<label>速度 <select id="speed"><option value="1">原速</option><option value="0.5">半速</option><option value="0.25">1/4 速</option></select></label>
<span id="info"></span></div>
<div class="stage">
<figure><figcaption>原版默认装</figcaption><div class="view"><canvas data-src="atlas_native.png"></canvas></div></figure>
<figure><figcaption>v03 原生纸娃娃（本次）</figcaption><div class="view"><canvas data-src="atlas_doll.png"></canvas></div></figure>
<figure><figcaption>v02 视频路线（上一版）</figcaption><div class="view"><canvas data-src="atlas_v02.png"></canvas></div></figure>
</div></main></div>
<script>
const CLIPS=__CLIPS__,CELL=__CELL__,COLS=__COLS__;
const views=[...document.querySelectorAll('canvas')].map(c=>{const i=new Image();i.src=c.dataset.src;return {c,i,x:c.getContext('2d')}});
let clip=CLIPS[0],pos=0,playing=true,last=0;
const $=id=>document.getElementById(id);
function draw(){const z=+$('zoom').value,frame=clip.start+pos;for(const v of views){v.c.width=CELL[0]*z;v.c.height=CELL[1]*z;v.x.imageSmoothingEnabled=false;
 if(v.i.complete)v.x.drawImage(v.i,(frame%COLS)*CELL[0],Math.floor(frame/COLS)*CELL[1],CELL[0],CELL[1],0,0,CELL[0]*z,CELL[1]*z)}
 $('info').textContent=clip.name+' · IMG '+String(frame).padStart(3,'0')+' ('+(pos+1)+'/'+(clip.end-clip.start+1)+')'}
function tick(t){const ms=100/+$('speed').value;if(playing&&t-last>=ms){last=t;pos=(pos+1)%(clip.end-clip.start+1);draw()}requestAnimationFrame(tick)}
CLIPS.forEach(k=>{const b=document.createElement('button');b.innerHTML=k.name+' <small>'+k.start+'–'+k.end+'</small>';b.onclick=()=>{clip=k;pos=0;[...$('clips').children].forEach(e=>e.classList.remove('on'));b.classList.add('on');draw()};$('clips').appendChild(b)});
$('clips').firstChild.classList.add('on');
$('play').onclick=()=>{playing=!playing;$('play').textContent=playing?'暂停':'播放'};
$('prev').onclick=()=>{playing=false;$('play').textContent='播放';pos=(pos-1+clip.end-clip.start+1)%(clip.end-clip.start+1);draw()};
$('next').onclick=()=>{playing=false;$('play').textContent='播放';pos=(pos+1)%(clip.end-clip.start+1);draw()};
$('zoom').onchange=draw;views.forEach(v=>v.i.onload=draw);draw();requestAnimationFrame(tick);
</script></body></html>"""


def atlas(load, path):
    board = Image.new("RGBA", (COLS * CELL[0], 12 * CELL[1]))
    for i in range(174):
        tile = load(i).crop(BOX)
        board.paste(tile, ((i % COLS) * CELL[0], (i // COLS) * CELL[1]))
    board.save(path, optimize=True)


def world_native(i):
    world = Image.new("RGBA", (500, 500))
    world.alpha_composite(Image.open(NATIVE / f"{i:04d}.png").convert("RGBA"), (185, 0))
    return world


def main():
    PREVIEW.mkdir(parents=True, exist_ok=True)
    atlas(world_native, PREVIEW / "atlas_native.png")
    atlas(lambda i: Image.open(OUT / f"native_frames/{i:04d}.png").convert("RGBA"), PREVIEW / "atlas_doll.png")
    atlas(lambda i: Image.open(OLD / f"{i:04d}.png").convert("RGBA"), PREVIEW / "atlas_v02.png")
    data = [dict(name=c["name"], start=c["start"], end=c["end"]) for c in clips()]
    page = PAGE.replace("__CLIPS__", json.dumps(data, ensure_ascii=False)).replace("__CELL__", json.dumps(CELL)).replace("__COLS__", str(COLS))
    # Inline the atlases: one file that works from a double click.
    for name in ("atlas_native.png", "atlas_doll.png", "atlas_v02.png"):
        encoded = base64.b64encode((PREVIEW / name).read_bytes()).decode("ascii")
        page = page.replace(f'data-src="{name}"', f'data-src="data:image/png;base64,{encoded}"')
    (PREVIEW / "index.html").write_text(page, "utf-8")
    print(PREVIEW / "index.html")


if __name__ == "__main__":
    main()
