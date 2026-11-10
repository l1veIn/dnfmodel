"""Build five distinct second-awakening still-illustration performances.

No generation, video submission, full character rebuild, config selection, or
game writes. The five new stills remain fixed in world coordinates; only the
mask-derived presentation window and procedural skill motifs move.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'output/dragon_cutin_v07'
REF = WORK / 'reference'
FINAL = ROOT / 'output/gpt_dragon_slayer_v07'
CONFIG = ROOT / 'design/gpt_dragon_slayer_v03/cutin_v07.json'
BASE = ROOT / 'output/gpt_dragon_slayer_v06'
BASE_NPK = BASE / 'A_GPTDragon_FSlayer_v06.NPK'
BASE_SHA = 'd9226050031e515abebf37282a3e041bae7a674d297cf4f19c162083c18bbb2c'
CANVAS = (1067, 600)
FAMILIES = {
    'weapon': dict(asset='weapon_2nd_v01.png', stem='atsword_majesty', frames=30, aliases=['atsword_majesty', '(18)atsword_majesty'], title='剑宗二觉 · 刃横冷瞳', motif='horizontal_blade', colour=(205, 187, 255)),
    'darktempler': dict(asset='darktempler_2nd_v01.png', stem='atsword_punishment', frames=35, aliases=['atsword_punishment', '(18)atsword_punishment'], title='暗帝二觉 · 影缚回望', motif='seal_rings', colour=(160, 119, 255)),
    'demonslayer': dict(asset='demonslayer_2nd_v01.png', stem='atsword_deicide', frames=46, aliases=['atsword_deicide'], title='剑魔二觉 · 链弧临界', motif='chain_slash', colour=(199, 147, 255)),
    'blade': dict(asset='blade_2nd_v01.png', stem='atsword_vendetta', frames=50, aliases=['atsword_vendetta', '(18)atsword_vendetta'], title='刃影二觉 · 鞘锋蓄势', motif='vertical_sheath', colour=(187, 181, 255)),
    'vagabond': dict(asset='vagabond_2nd_v01.png', stem='atsword_swordempress', frames=40, aliases=['atsword_swordempress'], title='剑帝二觉 · 双锋静定', motif='dual_arcs_petals', colour=(221, 185, 255)),
}


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def ease(value):
    value = np.clip(value, 0, 1)
    return value * value * (3 - 2 * value)


def mask_analysis(family):
    """Only use original masks to learn presentation extent and timing.

    Their holes/face silhouettes are intentionally not projected onto a new
    dragon face. The complete new face/hands/horns remain in the hold window.
    """
    spec = FAMILIES[family]
    folder = REF / 'official_alpha' / spec['stem']
    files = sorted(folder.glob('frame_*.png'))
    assert len(files) == spec['frames'], 'Incomplete official alpha sequence'
    union = np.zeros((CANVAS[1], CANVAS[0]), dtype=np.uint32)
    frames = []
    for k, path in enumerate(files):
        alpha = np.asarray(Image.open(path).convert('L'))
        assert alpha.shape == union.shape
        union += alpha
        frames.append(dict(frame=k, path=rel(path), sha256=sha(path), alpha_mass=float(alpha.sum() / 255), bbox=Image.fromarray(alpha).getbbox()))
    # Mass quantiles suppress isolated particles from dictating actor size.
    def extent(weights):
        cumulative = np.cumsum(weights, dtype=float)
        total = cumulative[-1]
        assert total > 0
        return int(np.searchsorted(cumulative, .002 * total)), int(np.searchsorted(cumulative, .998 * total)) + 1
    left, right = extent(union.sum(axis=0))
    top, bottom = extent(union.sum(axis=1))
    extent_box = [max(16, left - 40), max(12, top - 48), min(CANVAS[0] - 16, right + 40), min(CANVAS[1] - 10, bottom + 16)]
    masses = np.array([f['alpha_mass'] for f in frames])
    strength = np.sqrt(masses / max(masses))
    active = np.where(strength >= .78)[0]
    entry_end = float(np.clip(active[0] / (len(files) - 1), .12, .25))
    exit_start = float(np.clip(active[-1] / (len(files) - 1), .74, .89))
    for row, value in zip(frames, strength, strict=True):
        row['relative_strength'] = float(value)
    return dict(family=family, original_frames=frames, display_box=extent_box, entry_end=entry_end, exit_start=exit_start,
                policy='Alpha-mass timing and expanded union presentation box, not the original person silhouette. Stable still artwork; no body mesh/motion synthesis.',
                original_alpha_pixel_preservation=False, original_canvas_frame_count_and_alias_preserved=True)


def plan():
    assert sha(BASE_NPK) == BASE_SHA
    specs = {family: mask_analysis(family) for family in FAMILIES}
    path = WORK / 'stage' / 'presentation_plan.json'
    assert not path.exists(), 'Use existing analysis; do not overwrite a signed plan'
    save(path, dict(created_at=now(), profiles=FAMILIES, analyses=specs, base=rel(BASE_NPK), base_sha256=BASE_SHA,
                    canvas=list(CANVAS), preview_fps=10, native_game_timing_unknown=True, installed=False,
                    new_imagegen_calls_by_builder=0, new_video_calls=0))
    print(json.dumps(dict(plan=rel(path), families=5, paths=8, frames=316)))


def fit_still(path, box, family, presentation):
    art = Image.open(path).convert('RGBA')
    alpha = np.asarray(art.getchannel('A'))
    assert alpha.min() == 0 and alpha.max() > 200, 'A genuinely transparent finished illustration is required'
    # Ignore only nearly invisible dust for cropping; keep all visible accessories.
    ys, xs = np.where(alpha >= 4)
    assert len(xs)
    bounds = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
    cropped = art.crop(bounds)
    left, top, right, bottom = box
    if presentation == 'stage_edge':
        # Source illustrations intentionally crop horns/hair/waist at their
        # canvas edges. Align their upper/lower crop with the actual screen,
        # rather than letting a flat-cut horn float in empty stage space.
        scale = CANVAS[1] / cropped.height
    else:
        scale = min((right - left) / cropped.width, (bottom - top) / cropped.height)
    size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
    fitted = cropped.resize(size, Image.Resampling.LANCZOS)
    if presentation == 'stage_edge':
        assert size[0] <= CANVAS[0], 'Stage-edge fit must not newly clip important hands at the sides'
        bias = {'weapon': .5, 'darktempler': .25, 'demonslayer': 1, 'blade': .5, 'vagabond': 1}[family]
        position = (round((CANVAS[0] - size[0]) * bias), 0)
    else:
        position = (round((left + right - size[0]) / 2), bottom - size[1])
    page = Image.new('RGBA', CANVAS)
    page.alpha_composite(fitted, position)
    return page, dict(source_size=list(art.size), source_crop=bounds, scale=scale, position=list(position), fitted_size=list(size), actor_fixed_transform=True, presentation=presentation, source_top_bottom_crop_aligned_to_stage=presentation=='stage_edge', new_important_source_crop=False)


def presentation_matte(family, phase, analysis):
    left, top, right, bottom = analysis.get('render_display_box', analysis['display_box'])
    yy, xx = np.mgrid[:CANVAS[1], :CANVAS[0]]
    x = np.clip((xx - left) / max(1, right - left), 0, 1)
    y = np.clip((yy - top) / max(1, bottom - top), 0, 1)
    entry = float(ease((phase + .012) / analysis['entry_end']))
    leave = float(ease((1 - phase + .012) / (1 - analysis['exit_start'])))
    if family == 'weapon':
        distance = .82 * x + .18 * (1 - y)
        shown = ease((entry - distance + .045) / .09)
        gone = ease((leave - (1 - y) + .04) / .08)
    elif family == 'darktempler':
        distance = np.maximum(np.abs(x - .5) * 2, np.abs(y - .55) * 1.7)
        shown = ease((entry - distance + .06) / .12)
        gone = ease((leave - np.abs(x - .5) * 2 + .05) / .10)
    elif family == 'demonslayer':
        distance = .58 * (1 - x) + .42 * y
        shown = ease((entry - distance + .05) / .10)
        gone = ease((leave - y + .045) / .09)
    elif family == 'blade':
        distance = np.abs(x - .55) * 1.85
        shown = ease((entry - distance + .04) / .08)
        gone = ease((leave - y + .045) / .09)
    else:
        distance = .55 * y + .45 * np.abs(x - .5) * 2
        shown = ease((entry - distance + .06) / .12)
        gone = ease((leave - np.abs(y - .5) * 2 + .045) / .09)
    # At hold, protect the complete face, horns and hands irrespective of the
    # original character's alpha silhouette. The outer rectangle is feathered.
    window = ease(np.minimum.reduce([(xx-left+10)/20, (right-xx+10)/20, (yy-top+10)/20, (bottom-yy+10)/20]))
    return np.clip(shown * gone * window, 0, 1).astype(np.float32)


def glowing_lines(lines, radius=7):
    glow = lines.filter(ImageFilter.GaussianBlur(radius))
    return Image.alpha_composite(glow, lines)


def path_points(kind, count=120):
    q = np.linspace(0, 1, count)
    if kind == 'slash':
        return [(round(115 + 830*t), round(505 - 395*t - 52*math.sin(math.pi*t))) for t in q]
    if kind == 'blade':
        return [(round(100 + 870*t), round(380 - 70*t)) for t in q]
    return [(round(610 + 36*math.sin(math.pi*t)), round(80 + 475*t)) for t in q]


def trace(draw, points, progress, colour, width=4, tail=.30):
    # A growing screen-space trace: it is never a whole arc thrown across frame.
    for i in range(1, len(points)):
        birth = i / (len(points) - 1)
        age = progress - birth
        if 0 <= age <= tail:
            opacity = (1 - age / tail) ** .65
            draw.line([points[i-1], points[i]], fill=(*colour, round(210*opacity)), width=max(1, round(width*opacity)))


def effects(family, phase, strength):
    spec = FAMILIES[family]
    colour = spec['colour']
    rear = Image.new('RGBA', CANVAS)
    front = Image.new('RGBA', CANVAS)
    dr, df = ImageDraw.Draw(rear), ImageDraw.Draw(front)
    level = float(np.clip(math.sin(math.pi * (phase * .94 + .02)), 0, 1))
    a = round((85 + 55*strength) * level)
    if family == 'weapon':
        dr.polygon([(0, 316), (1067, 243), (1067, 435), (0, 510)], fill=(34, 25, 66, round(70*level)))
        trace(df, path_points('blade'), (phase-.02)/.32, (242, 234, 255), 7, .44)
        for i in range(7):
            x = int((phase*720 + i*173) % 1250 - 100)
            dr.line((x, 450-i*16, x+130, 436-i*16), fill=(*colour, a//2), width=1)
    elif family == 'darktempler':
        cx, cy = 560, 320
        for radius, turn in [(180, 1), (218, -1)]:
            pts = [(round(cx + radius*math.cos(j/48*2*math.pi + turn*phase*.8)), round(cy + .63*radius*math.sin(j/48*2*math.pi + turn*phase*.8))) for j in range(49)]
            dr.line(pts, fill=(*colour, a), width=2)
        for i in range(12):
            angle = i*math.pi/6 + phase*.8
            p1=(cx+190*math.cos(angle), cy+120*math.sin(angle))
            p2=(cx+213*math.cos(angle), cy+135*math.sin(angle))
            dr.line([p1,p2], fill=(235,221,255,a), width=3)
    elif family == 'demonslayer':
        for i in range(28):
            angle = -.3 + i/27*3.8
            cx=570+330*math.cos(angle); cy=330+185*math.sin(angle)
            dr.ellipse((cx-9,cy-5,cx+9,cy+5), outline=(*colour,a), width=2)
        trace(df, path_points('slash'), (phase-.16)/.35, (244,221,255), 10, .35)
    elif family == 'blade':
        for x in [588, 610, 634]:
            dr.line((x, 30, x+8, 590), fill=(*colour, round(a*.45)), width=2)
        trace(df, path_points('vertical'), (phase-.01)/.35, (244,241,255), 7, .35)
        for i in range(5):
            y=round((i*137 + phase*420)%650-25)
            dr.line((535,y,676,y-18), fill=(*colour,a//2), width=1)
    else:
        for sign in [-1,1]:
            pts=[(round(530+sign*420*math.cos(t*math.pi)), round(540-330*math.sin(t*math.pi))) for t in np.linspace(.05,.95,90)]
            trace(dr, pts, (phase-.01)/.42, (247,224,255), 4, .55)
        for i in range(18):
            t=(phase*.6+i*.173)%1
            x=round(100+865*t); y=round(500-400*t+42*math.sin(i+phase*4))
            df.ellipse((x-3,y-7,x+3,y+7), fill=(*colour,round(a*.55)))
    # Fixed seeded particles move along continuous paths, not random per frame.
    seed = list(FAMILIES).index(family) + 1
    for i in range(16):
        theta = i*2.399 + seed
        x=round(533+390*math.cos(theta)+math.sin(phase*2.6+i)*18)
        y=round(310+235*math.sin(theta)-phase*(20+i%5*8))
        pulse=max(0, math.sin(phase*math.pi+i*.21))
        size=1+i%2
        df.ellipse((x-size,y-size,x+size,y+size),fill=(*colour,round(a*.65*pulse)))
    return glowing_lines(rear, 9), glowing_lines(front, 5)


def write_contact(images, path, family):
    picks=sorted({round(i*(len(images)-1)/7) for i in range(8)})
    board=Image.new('RGB',(4*360,2*230),(42,47,58))
    draw=ImageDraw.Draw(board)
    for n,k in enumerate(picks):
        thumb=images[k].resize((352,198),Image.Resampling.LANCZOS)
        x=(n%4)*360+4; y=(n//4)*230
        draw.text((x,y+5),f'{family} k{k+1}/{len(images)}',fill='white')
        board.paste(thumb,(x,y+26),thumb)
    board.save(path,quality=95)


def build(candidate, art_dir, families, presentation):
    assert candidate.startswith('candidate') and candidate.replace('_','').isalnum()
    assert sha(BASE_NPK) == BASE_SHA
    analyses = load(WORK/'stage/presentation_plan.json')['analyses']
    folder = WORK/candidate
    folder.mkdir(parents=True,exist_ok=True)
    manifest_path=folder/'manifest.json'
    manifest=load(manifest_path) if manifest_path.exists() else dict(created_at=now(),candidate=candidate,canvas=list(CANVAS),preview_fps=10,families={},installed=False,ingame_verified=False,video_generated=False)
    for family in families:
        spec=FAMILIES[family]
        target=folder/family
        assert not target.exists(), f'Existing {family} candidate is immutable; choose another candidate name'
        art_path=(art_dir/spec['asset']).resolve(strict=True)
        assert art_path.is_relative_to(WORK/'art')
        target.mkdir()
        (target/'frames').mkdir(); (target/'mattes').mkdir()
        analysis=json.loads(json.dumps(analyses[family]))
        if presentation=='stage_edge':
            analysis['render_display_box']=[0,0,*CANVAS]
            analysis['editorial_window_reason']='Source top/bottom crop edges align to screen edges; preserve complete generated hands/horns without inventing missing source pixels.'
            analysis['force_final_actor_exit']=True
            if family=='demonslayer':
                analysis['previous_exit_start']=analysis['exit_start']
                analysis['exit_start']=.78
        actor,transform=fit_still(art_path,analysis['display_box'],family,presentation)
        actor.save(target/'subject_fixed.png')
        actor_data=np.asarray(actor).copy()
        images=[]; frame_records=[]
        for k in range(spec['frames']):
            phase=k/(spec['frames']-1)
            matte=presentation_matte(family,phase,analysis)
            strength=analysis['original_frames'][k]['relative_strength']
            data=actor_data.copy()
            final_exit=float(ease((1-phase)/.08)) if analysis.get('force_final_actor_exit') else 1
            data[...,3]=np.rint(data[...,3].astype(float)*matte*(.84+.16*strength)*final_exit).astype(np.uint8)
            data[data[...,3]==0,:3]=0
            masked=Image.fromarray(data,'RGBA')
            rear,front=effects(family,phase,strength)
            page=Image.alpha_composite(rear,masked)
            page=Image.alpha_composite(page,front)
            assert page.getchannel('A').getbbox(), 'Every official non-empty slot needs visible output'
            frame_path=target/'frames'/f'frame_{k:04d}.png'
            matte_path=target/'mattes'/f'frame_{k:04d}.png'
            page.save(frame_path)
            Image.fromarray(np.rint(matte*255).astype(np.uint8),'L').save(matte_path)
            frame_records.append(dict(frame=k,png=rel(frame_path),sha256=sha(frame_path),matte=rel(matte_path),matte_sha256=sha(matte_path),official_mask_sha256=analysis['original_frames'][k]['sha256'],visible_bbox=page.getbbox(),phase=phase))
            images.append(page)
        write_contact(images,target/'contact.jpg',family)
        small=[im.resize((640,360),Image.Resampling.LANCZOS) for im in images]
        small[0].save(target/'preview.webp',save_all=True,append_images=small[1:],duration=100,loop=0,lossless=True,exact=True)
        images[0].save(target/'preview_native.webp',save_all=True,append_images=images[1:],duration=100,loop=0,lossless=True,exact=True)
        row=dict(family=family,title=spec['title'],art=rel(art_path),art_sha256=sha(art_path),transform=transform,motif=spec['motif'],frame_count=spec['frames'],aliases=spec['aliases'],analysis=analysis,frames=frame_records,preview=rel(target/'preview.webp'),native_preview=rel(target/'preview_native.webp'),native_preview_sha256=sha(target/'preview_native.webp'),contact=rel(target/'contact.jpg'),subject_fixed=rel(target/'subject_fixed.png'),subject_fixed_sha256=sha(target/'subject_fixed.png'))
        save(target/'manifest.json',row)
        manifest['families'][family]=row
        save(manifest_path,manifest)
    manifest['status']='ready_for_root_visual_review' if set(manifest['families'])==set(FAMILIES) else 'partial_art_ready'
    save(manifest_path,manifest)
    print(json.dumps(dict(candidate=rel(manifest_path),status=manifest['status'],families=list(manifest['families'])),ensure_ascii=False))


def native_previews(candidate):
    folder=WORK/candidate
    manifest_path=folder/'manifest.json'
    manifest=load(manifest_path)
    checks={}
    for family,row in manifest['families'].items():
        target=folder/family/'preview_native.webp'
        images=[Image.open(ROOT/frame['png']).convert('RGBA') for frame in row['frames']]
        if not target.exists():
            images[0].save(target,save_all=True,append_images=images[1:],duration=100,loop=0,lossless=True,exact=True)
        decoded=Image.open(target)
        assert decoded.size==CANVAS and decoded.n_frames==len(images)
        for k,image in enumerate(images):
            decoded.seek(k)
            actual=np.asarray(decoded.convert('RGBA'))
            expected=np.asarray(image)
            visible=(actual[...,3]>0)|(expected[...,3]>0)
            assert np.array_equal(actual[...,3],expected[...,3]), f'Native preview alpha mismatch {family}/{k}'
            assert np.array_equal(actual[...,:3][visible],expected[...,:3][visible]), f'Native preview visible RGB mismatch {family}/{k}'
        row['native_preview']=rel(target)
        row['native_preview_sha256']=sha(target)
        row['native_preview_alpha_and_visible_rgb_exact']=True
        save(folder/family/'manifest.json',row)
        checks[family]=dict(path=rel(target),frames=len(images),alpha_and_visible_rgb_exact=True,hidden_rgb_not_compared=True,sha256=sha(target))
    manifest['native_preview_checks']=checks
    save(manifest_path,manifest)
    print(json.dumps(dict(native_previews=checks),ensure_ascii=False))


def select(candidate, approved):
    assert approved, 'Root must review all five actual animations before selecting'
    folder=WORK/candidate
    manifest=load(folder/'manifest.json')
    assert manifest['status']=='ready_for_root_visual_review'
    selected=WORK/'selected'
    assert not selected.exists(), 'Selected source is immutable; revise under a new candidate/version'
    selected.mkdir(); (selected/'frames').mkdir()
    records={}
    for family,row in manifest['families'].items():
        destination=selected/'frames'/family
        shutil.copytree(folder/family/'frames',destination,copy_function=shutil.copy2)
        for frame in row['frames']:
            path=destination/Path(frame['png']).name
            assert sha(path)==frame['sha256']
            records[rel(path)]=sha(path)
    save(selected/'manifest.json',dict(selected_at=now(),root_visual_selected=True,source=rel(folder/'manifest.json'),source_sha256=sha(folder/'manifest.json'),files_sha256=records,subject_motion='Fixed generated key illustration, no synthesized body animation',installed=False,ingame_verified=False))
    make_config()
    print(json.dumps(dict(selected=rel(selected),config=rel(CONFIG),frames=316,paths=8)))


def make_config():
    summary=load(REF/'summary.json')
    official=load(REF/'audit.json')['official_npk']
    overlays=[]
    for target in summary['replace_second']:
        family=target['family']
        overlays.append(dict(source_npk=official,path=target['path'],frame_paths=[rel(WORK/'selected/frames'/family/f'frame_{k:04d}.png') for k in range(target['frames'])],frame_mode='canvas',allow_geometry_change=True,fit_to_canvas=False,preserve_empty_frames=True,source_clip=family+'_2nd_key_illustration',category='cutin_second'))
    cfg=dict(title='GPT 龙娘 v07 · 二觉五套独立演出',base_npk=rel(BASE_NPK),base_sha256=BASE_SHA,output=rel(FINAL),npk_name='A_GPTDragon_FSlayer_v07.NPK',protect_paths=[rel(BASE), 'output/dragon_buff_v05/preview', 'output/interface_portraits_v01/package_v01/manifest.json','output/interface_portraits_v01/package_v01/A_AI_InterfacePortraits_v01.NPK'],overlays=overlays,installed=False,ingame_verified=False,notes=['Only eight second-awakening paths change. Seven third-awakening paths and all other base raw payloads remain exact.','Generated key illustrations plus procedural presentation, not newly generated video.','Original alpha sequences supply timing and expanded presentation extent; original person silhouettes are not projected onto new faces/horns/hands.'])
    assert not CONFIG.exists(), 'Configuration already exists and is immutable'
    save(CONFIG,cfg)


def copy_scaffold():
    assert sha(BASE_NPK)==BASE_SHA
    assert not (FINAL/'A_GPTDragon_FSlayer_v07.NPK').exists()
    FINAL.mkdir(exist_ok=True)
    existing={p.name for p in FINAL.iterdir()}
    assert not existing.intersection({'native_frames','parts','clips'}), 'Scaffold already copied'
    records={}
    for sub in ['native_frames','parts','clips']:
        source=BASE/sub
        shutil.copytree(source,FINAL/sub,copy_function=shutil.copy2)
        for path in source.rglob('*'):
            if path.is_file():
                copied=FINAL/sub/path.relative_to(source)
                assert sha(path)==sha(copied) and path.stat().st_mtime_ns==copied.stat().st_mtime_ns
                records[rel(copied)]=dict(sha256=sha(copied),mtime_ns=copied.stat().st_mtime_ns)
    assert len(list((FINAL/'native_frames').glob('*.png')))==246
    save(FINAL/'scaffold_manifest.json',dict(copied_at=now(),source=rel(BASE),files=records,all_bytes_and_mtimes_preserved=True,patch_selection_not_modified=True,installed=False))
    print(json.dumps(dict(scaffold=rel(FINAL),files=len(records),native_frames=246)))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['plan','build','previews','select','scaffold'])
    parser.add_argument('--candidate',default='candidate01')
    parser.add_argument('--art-dir',type=Path,default=WORK/'art')
    parser.add_argument('--families',nargs='+',choices=FAMILIES,default=list(FAMILIES))
    parser.add_argument('--presentation',choices=['source_window','stage_edge'],default='source_window')
    parser.add_argument('--approved',action='store_true')
    args=parser.parse_args()
    if args.action=='plan': plan()
    elif args.action=='build': build(args.candidate,args.art_dir,args.families,args.presentation)
    elif args.action=='previews': native_previews(args.candidate)
    elif args.action=='select': select(args.candidate,args.approved)
    else: copy_scaffold()
