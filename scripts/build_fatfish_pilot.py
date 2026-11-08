"""Offline pilot preview and NPK build/roundtrip verification. Never installs it."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw,ImageFont

from dnf_resources import ImgArchive,read_npk,write_npk,write_v2,save_json
from fatfish_pilot_v03 import BATCH,PREVIOUS,ROOT,WINDOW,WALK_TARGETS,FIXES


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def font(size):return ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',size)


def stage(path):return Image.open(path).convert('RGBA')
def original(frame):
    im=Image.new('RGBA',(500,500));im.alpha_composite(stage(ROOT/f'materials/female_mage/reference_composite/frames/{frame:04d}.png'),(185,0));return im


def render(im,scale=3,box=WINDOW):
    view=im.crop(box).resize(((box[2]-box[0])*scale,(box[3]-box[1])*scale),Image.Resampling.NEAREST)
    bg=Image.new('RGBA',view.size,'#c3ccd9');d=ImageDraw.Draw(bg)
    for y in range(0,bg.height,24):
        for x in range(0,bg.width,24):
            if (x//24+y//24)%2:d.rectangle((x,y,x+23,y+23),fill='#e5ebf2')
    bg.alpha_composite(view);return bg.convert('RGB')


def selected():
    return {0:BATCH/'corrected/fix_walk_canvas.png',1:BATCH/'sequence/0001_canvas.png',2:BATCH/'sequence/0002_canvas.png',3:BATCH/'sequence/0003_canvas.png',10:PREVIOUS/'master/master_feet_clean_canvas.png',23:BATCH/'corrected/fix_jump_canvas.png',65:BATCH/'corrected/fix_cast_canvas.png'}


def previews():
    sources=selected();frames=[]
    overview=Image.new('RGB',(1536,512),'#253343');d=ImageDraw.Draw(overview)
    d.text((16,10),'大肥鱼 4 帧连续片段｜IMG 0–3，非完整步行循环',font=font(25),fill='white')
    d.text((16,48),'同一游戏坐标窗口；头部为主动复用锁定，裙摆/尾巴连续性仍需检查。',font=font(18),fill='#c0d0e2')
    for i in range(4):
        frame=Image.new('RGB',(768,512),'#253343');dr=ImageDraw.Draw(frame)
        dr.text((14,12),f'原动作 / 大肥鱼   IMG {i:03d}',font=font(23),fill='white')
        dr.text((14,47),'固定坐标；工程播放 140 ms/帧，非游戏 ANI 配时',font=font(17),fill='#c0d0e2')
        frame.paste(render(original(i)),(0,90));frame.paste(render(stage(sources[i])),(384,90))
        frames.append(frame)
        overview.paste(render(stage(sources[i])),(384*i,100));d.text((384*i+12,77),f'frame {i:03d}',font=font(18),fill='white')
    reset=Image.new('RGB',(768,512),'#253343');ImageDraw.Draw(reset).text((100,220),'4 帧片段结束，随后重新播放',font=font(28),fill='white')
    frames[0].save(BATCH/'qa/walk_fragment_compare.gif',save_all=True,append_images=frames[1:]+[reset],duration=[140,140,140,600,500],loop=0,optimize=False)
    overview.save(BATCH/'qa/walk_fragment_sheet.png')
    # Explicitly constrained ground-contact simulation, not a claim of game physics.
    targets={0:dict(eye=[251,304],sole=[278,381]),**WALK_TARGETS}
    grounded=[]
    for i in range(4):
        im=stage(sources[i]);sole=targets[i]['sole'];offset=(278-sole[0],386-sole[1])
        world=Image.new('RGBA',(500,500));world.alpha_composite(im,offset)
        view=render(world,3,(186,270,386,400))
        frame=Image.new('RGB',(600,480),'#253343');dr=ImageDraw.Draw(frame)
        dr.text((12,10),'接地模拟（不是实机录像）',font=font(22),fill='white')
        dr.text((12,44),f'frame {i:03d} / 按原素材脚点模拟位移 {offset}',font=font(16),fill='#c0d0e2')
        frame.paste(view,(0,84));dr.line((0,84+(386-270)*3,600,84+(386-270)*3),fill='#bd8d41',width=2)
        grounded.append(frame)
    reset2=Image.new('RGB',(600,480),'#253343');ImageDraw.Draw(reset2).text((70,210),'片段结束，重新播放',font=font(25),fill='white')
    grounded[0].save(BATCH/'qa/walk_grounded_simulation.gif',save_all=True,append_images=grounded[1:]+[reset2],duration=[140,140,140,600,500],loop=0,optimize=False)
    # Repair comparison, all at the same native coordinates.
    sheet=Image.new('RGB',(1152,1320),'#253343');sd=ImageDraw.Draw(sheet)
    sd.text((12,10),'三张动作：原参考 / 修前 / 局部修后',font=font(26),fill='white')
    for row,(name,item) in enumerate(FIXES.items()):
        y=72+row*410
        old=PREVIOUS/item['source'].replace('_reference_8x.png','_clean_canvas.png')
        for col,im in enumerate([original(item['frame']),stage(old),stage(BATCH/f'corrected/{name}_canvas.png')]):
            sheet.paste(render(im),(col*384,y))
        sd.text((12,y-26),f"{name} / IMG {item['frame']:03d}",font=font(18),fill='white')
    sheet.save(BATCH/'qa/repair_comparison.png')


def build():
    images=selected()
    for path in images.values():
        if not path.exists():raise FileNotFoundError(path)
    full=[Image.new('RGBA',(1,1)) for _ in range(174)]
    metadata=[dict(link=10,x=0,y=0,canvas_width=500,canvas_height=500) for _ in range(174)]
    for i,path in images.items():
        im=stage(path);bb=im.getchannel('A').getbbox()
        if not bb:raise RuntimeError(f'Empty selected frame {i}')
        full[i]=im.crop(bb)
        metadata[i]=dict(x=bb[0],y=bb[1],canvas_width=500,canvas_height=500)
    body=write_v2(full,metadata,preserve_links=True)
    transparent=Image.new('RGBA',(1,1))
    blank_meta=[dict(x=0,y=0,canvas_width=500,canvas_height=500)]+[dict(link=0,x=0,y=0,canvas_width=500,canvas_height=500) for _ in range(173)]
    blank=write_v2([transparent]*174,blank_meta,preserve_links=True)
    index=json.loads((ROOT/'sources/img_index.json').read_text(encoding='utf-8'))
    skin=[e for e in index if '/avatar/skin/' in e['path']]
    if len(skin)!=38 or any(e['frame_count']!=174 for e in skin):raise RuntimeError('Re-review skin scope/count')
    defaults=[]
    for path in sorted((ROOT/'materials/female_mage/layers').glob('*/frames.json')):
        m=json.loads(path.read_text(encoding='utf-8'))
        if '/avatar/skin/' not in m['img_path']:
            if m['frame_count']!=174:raise RuntimeError('Re-review default layer count')
            defaults.append(m['img_path'])
    entries=[(e['path'],body) for e in skin]+[(p,blank) for p in defaults]
    name='A_Fatfish_FMage_7Frame_Pilot_v03.NPK'
    out=ROOT/'output'/name;out.write_bytes(write_npk(entries))
    # Read the actual written NPK and decode every frame of every entry.
    records=read_npk(out);expected_paths={p for p,_ in entries}
    if {r['path'] for r in records}!=expected_paths:raise AssertionError('Path roundtrip mismatch')
    encoded=out.read_bytes();checks=[]
    expected_arrays={i:np.asarray(stage(path)) for i,path in images.items()}
    for record in records:
        archive=ImgArchive(encoded[record['offset']:record['offset']+record['length']])
        assert archive.count==174
        is_skin='/avatar/skin/' in record['path']
        for i in range(174):
            pic=archive.image(i);r=archive.resolve(i)
            canvas=Image.new('RGBA',(500,500));canvas.alpha_composite(pic,(r['x'],r['y']))
            if is_skin:
                expected=expected_arrays[i] if i in images else expected_arrays[10]
                assert np.array_equal(np.asarray(canvas),expected),(record['path'],i)
            else:assert canvas.getchannel('A').getbbox() is None
        checks.append(dict(path=record['path'],frames=174,role='whole_character' if is_skin else 'hide_default_avatar',roundtrip='passed'))
    report=dict(package=str(out),sha256=sha(out),bytes=out.stat().st_size,entry_count=len(records),skin_paths=len(skin),default_avatar_paths=len(defaults),frame_count=174,unique_drawn_slots=sorted(images),fallback_slots=[i for i in range(174) if i not in images],fallback='standing master frame 10',decoded_frames_checked=len(records)*174,all_pixel_and_position_roundtrips_passed=True,entries=checks,scope='Female mage skin resources plus default unequipped costume layers only',game_installation_changed=False,game_runtime_validated=False,animation_timing_certified=False)
    save_json(BATCH/'package/npk_validation.json',report)
    (ROOT/'output'/(name+'.sha256')).write_text(report['sha256']+'  '+name+'\n',encoding='ascii')
    print(json.dumps({k:report[k] for k in ['package','bytes','entry_count','skin_paths','default_avatar_paths','decoded_frames_checked','all_pixel_and_position_roundtrips_passed']},ensure_ascii=False))


if __name__=='__main__':
    previews();build()
