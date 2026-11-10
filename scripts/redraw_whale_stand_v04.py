"""Reference study and genuine image-generated whale standing redraw.

Writes only the v04 redraw workspace. Released frames, configs, issues and NPKs
are read-only. The four original game frames stay in their common world space.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import shutil

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
os.environ['PATCH_ID'] = 'fatfish_whale_maid'
sys.path.insert(0, str(ROOT / '.claude/skills/dnf-character-patch/scripts'))
from kit import art, source
from kit.config import P

WORK = ROOT / 'output/whale_stand_redraw_v04'
CURRENT = ROOT / 'output/fatfish_whale_maid_v03'
SLOTS = [10, 11, 12, 13]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', 'utf-8')

def full_original(k):
    im = Image.new('RGBA', (500, 500))
    for layer in P.order:
        im.alpha_composite(source.layer_world(layer, k))
    return im

def make_board(rows, labels, crop, path, factor=6):
    w, h = crop[2]-crop[0], crop[3]-crop[1]
    out = Image.new('RGB', (4*(w*factor+18), len(rows)*(h*factor+30)), (49,56,70))
    draw = ImageDraw.Draw(out)
    for ri, (row, label) in enumerate(zip(rows, labels)):
        for ci, frame in enumerate(row):
            x, y = ci*(w*factor+18)+9, ri*(h*factor+30)
            draw.text((x,y+4),f'{label} / user{SLOTS[ci]+1}',fill='white')
            piece=frame.crop(crop).resize((w*factor,h*factor),Image.Resampling.NEAREST)
            out.paste(piece,(x,y+25),piece)
    out.save(path)

def animation(frames, crop, path, factor=1, duration=180):
    seq=[]
    for frame in frames:
        piece=frame.crop(crop)
        bg=Image.new('RGBA',piece.size,(49,56,70,255)); bg.alpha_composite(piece)
        seq.append(bg.convert('RGB').resize((piece.width*factor,piece.height*factor),Image.Resampling.NEAREST))
    seq[0].save(path,save_all=True,append_images=seq[1:],duration=duration,loop=0,lossless=True)

def reference():
    ref=WORK/'reference'; ref.mkdir(parents=True,exist_ok=True)
    original=[full_original(k) for k in SLOTS]
    current=[Image.open(CURRENT/f'native_frames/{k:04d}.png').convert('RGBA') for k in SLOTS]
    for k,im in zip(SLOTS,original): im.save(ref/f'official_{k:04d}.png')
    boxes=[im.getbbox() for im in original+current]
    crop=(min(b[0] for b in boxes)-5,min(b[1] for b in boxes)-5,max(b[2] for b in boxes)+5,max(b[3] for b in boxes)+5)
    make_board([original,current],['official all selected layers','rejected v03'],crop,ref/'official_and_rejected.png',5)
    make_board([original],['official fixed world'],crop,ref/'official_pose_board.png',8)
    animation(original,crop,ref/'official_native.webp')
    animation(original,crop,ref/'official_x6.webp',6)
    arr=np.asarray(original)
    changed=np.any(arr!=arr[0],axis=(0,3))
    diff=[]
    for i in range(4):
        im=Image.fromarray(arr[i]).copy()
        overlay=np.asarray(im).copy()
        moved=np.any(arr[i]!=arr[0],axis=2)
        overlay[moved]=[255,200,0,255]
        diff.append(Image.fromarray(overlay))
    make_board([diff],['yellow difference vs user11'],crop,ref/'official_difference.png',8)
    save_json(ref/'reference_record.json',{'slots':SLOTS,'crop':crop,'original_world_size':[500,500],'selected_layers':P.order,'official_png_sha256':{str(k):sha(ref/f'official_{k:04d}.png') for k in SLOTS},'source_is_all_selected_layers_not_desmeared_composite':True,'changed_bbox':Image.fromarray(changed.astype('uint8')*255).getbbox(),'current_rejected_native_sha256':{str(k):sha(CURRENT/f'native_frames/{k:04d}.png') for k in SLOTS}})
    print(json.dumps({'reference':str(ref),'crop':crop},ensure_ascii=False))

def segment(tag='v01'):
    """Remove disconnected generation dust, retaining actual drawn anatomy."""
    src=WORK/f'art/standing_sheet_{tag}.png'
    im=Image.open(src).convert('RGBA')
    pieces=[];records=[]
    cells=WORK/f'art/cells_{tag}';cells.mkdir(parents=True,exist_ok=True)
    for i in range(4):
        x0=round((i%2)*im.width/2);x1=round((i%2+1)*im.width/2)
        y0=round((i//2)*im.height/2);y1=round((i//2+1)*im.height/2)
        arr=np.asarray(im.crop((x0,y0,x1,y1))).copy()
        labels,n=ndimage.label(arr[...,3]>24)
        counts=np.bincount(labels.ravel());counts[0]=0
        main=labels==int(counts.argmax())
        support=ndimage.distance_transform_edt(~main)<=2
        removed=(~support)&(arr[...,3]>0)
        arr[~support]=0
        frame=Image.fromarray(arr,'RGBA');frame.save(cells/f'pose_{i+1}.png')
        pieces.append(frame)
        records.append({'pose':i+1,'cell':[x0,y0,x1,y1],'body_bbox':frame.getbbox(),'removed_disconnected_alpha_pixels':int(removed.sum()),'png_sha256':sha(cells/f'pose_{i+1}.png')})
    # Review only; coordinates are cell-local and no independent bbox fitting.
    w,h=pieces[0].size
    out=Image.new('RGB',(4*w,h+24),(49,56,70));d=ImageDraw.Draw(out)
    feet=Image.new('RGB',(4*400,300),(49,56,70));fd=ImageDraw.Draw(feet)
    for i,p in enumerate(pieces):
        out.paste(p,(i*w,24),p);d.text((i*w+6,4),f'new drawn pose{i+1}',fill='white')
        foot=p.crop((210,470,410,620)).resize((400,300),Image.Resampling.NEAREST)
        feet.paste(foot,(i*400,0),foot)
        for y in range(480,621,20):
            yy=(y-470)*2;fd.line((i*400,yy,(i+1)*400,yy),fill=(100,110,125));fd.text((i*400,yy),str(y),fill='white')
        for x in range(220,401,20):
            xx=i*400+(x-210)*2;fd.line((xx,0,xx,300),fill=(100,110,125));fd.text((xx,0),str(x),fill='white')
    out.save(WORK/f'art/drawn_poses_{tag}_full.png')
    feet.save(WORK/f'art/drawn_feet_{tag}_positions.png')
    save_json(WORK/f'art/segmentation_{tag}_record.json',{'source':str(src.relative_to(ROOT)),'source_sha256':sha(src),'method':'Largest connected body at alpha>24 plus2px antialias neighborhood, disconnected dust only. No body shape warp.','frames':records})
    print(json.dumps(records,ensure_ascii=False))

def prepare():
    if (WORK/'frozen.json').exists():
        raise ValueError('Frozen redraw; prepare must not overwrite selected art')
    tag='v03'
    segment(tag)
    candidate=WORK/'candidate01'
    nd=candidate/'native_frames';hdroot=candidate/'clips/clip_010_013/hd'
    nd.mkdir(parents=True,exist_ok=True);hdroot.mkdir(parents=True,exist_ok=True)
    palpath=WORK/'palette_original.png'
    if not palpath.exists(): shutil.copy2(ROOT/'output/whale_action_repair_v03/palette_original.png',palpath)
    pal=Image.open(palpath).copy()
    baseline={f.name:sha(f) for f in sorted((CURRENT/'native_frames').glob('*.png'))}
    before=[Image.open(CURRENT/f'native_frames/{k:04d}.png').convert('RGBA') for k in SLOTS]
    originals=[full_original(k) for k in SLOTS]
    # Single complete-cell resample, no per-figure bbox fit or mesh warp.
    # This common transform gives the native heroine a ~98px body and maps
    # the newly drawn near/far toe support to the official fixed world stage.
    outsize=108;left,top=197,286
    frames=[];details=[]
    report=json.loads((CURRENT/'clips/clip_010_013/selection.json').read_text('utf-8'))
    report['sheet']='redrawn_idle_v04_sheet_v03'
    report['base_scale']=outsize/165
    report['redraw_source']='output/whale_stand_redraw_v04/art/standing_sheet_v03.png'
    report['redraw_method']='Genuine image-generated4-pose sheet; one cell/world scale; no micro, shear, per-body fit or old-body graft.'
    report.pop('action_repair_source',None)
    for i,k in enumerate(SLOTS):
        hd=Image.open(WORK/f'art/cells_{tag}/pose_{i+1}.png').convert('RGBA')
        hd.save(hdroot/f'{k:04d}.png')
        color,alpha=art.downscale(hd,(outsize,outsize))
        sprite=art.finish(art.sharpen(art.grade(color)),alpha,pal)
        world=Image.new('RGBA',(500,500));world.paste(sprite,(left,top))
        world.save(nd/f'{k:04d}.png');frames.append(world)
        row=report['frames'][i]
        row.update({'scale':outsize/165,'offset':[169,229],'track':[0,0],'offset_before_ground':[169,229],'video_frame':f'redrawn_idle_v04:phase{i+1}','hands':[],'score':None})
        details.append({'slot':k,'user_frame':k+1,'clip':'clip_010_013','source_pose':i+1,'native':str((nd/f'{k:04d}.png').relative_to(ROOT)).replace('\\','/'),'native_sha256':sha(nd/f'{k:04d}.png'),'hd':str((hdroot/f'{k:04d}.png').relative_to(ROOT)).replace('\\','/'),'hd_sha256':sha(hdroot/f'{k:04d}.png'),'native_bbox':world.getbbox()})
    save_json(candidate/'clips/clip_010_013/selection.json',report)
    review=candidate/'review';review.mkdir(exist_ok=True)
    crop=(214,280,278,393)
    make_board([originals,before,frames],['official all layers','rejected v03','redrawn candidate01'],crop,review/'whole_body_comparison.png',4)
    make_board([originals,frames],['official','redrawn'],(230,364,268,391),review/'foot_poses.png',10)
    animation(frames,crop,review/'standing_native.webp',1,180)
    animation(frames,crop,review/'standing_x4.webp',4,180)
    # Actual alpha/color invariants on the freshly drawn foot support.
    arr=np.asarray(frames)
    fixed=np.all(arr==arr[0],axis=(0,3)) & np.all(arr[...,3]>0,axis=0)
    fixed[:375]=False
    fixed[389:]=False
    im=Image.fromarray((fixed*255).astype('uint8'))
    fixed_pixels=[list(map(int,xy[::-1])) for xy in np.argwhere(fixed)]
    records={'state':'prepared_for_root_review','target_slots':SLOTS,'genuine_image_generation':True,'new_imagegen_calls':3,'new_65535_calls':0,'selected_sheet':'output/whale_stand_redraw_v04/art/standing_sheet_v03.png','selected_sheet_sha256':sha(WORK/'art/standing_sheet_v03.png'),'generation_record':'output/whale_stand_redraw_v04/generation_record.json','motion_analysis':'output/whale_stand_redraw_v04/reference/motion_analysis.json','single_transform':{'cell_size':[627,627],'native_size':[outsize,outsize],'world_offset':[left,top],'world_canvas':[500,500]},'frames':details,'unchanged_current174_native':baseline=={f.name:sha(f) for f in sorted((CURRENT/'native_frames').glob('*.png'))},'non_target_current_frames':170,'verified_battle_ahoge_14_17_sha256':{str(k):baseline[f'{k:04d}.png'] for k in range(14,18)},'foot_static_pixel_count':len(fixed_pixels),'foot_static_pixel_locations':fixed_pixels,'foot_static_bbox':im.getbbox(),'installed':False,'user_aesthetic_approved':False}
    save_json(candidate/'manifest.json',records)
    save_json(WORK/'protected_native_baseline.json',baseline)
    print(json.dumps({k:v for k,v in records.items() if k not in ['frames','foot_static_pixel_locations']},ensure_ascii=False,indent=2))

def lock_caps():
    """Publish root-selected drawings with only the two new forefeet locked."""
    if (WORK/'frozen.json').exists():
        raise ValueError('Frozen redraw: cannot overwrite')
    base=WORK/'candidate01';candidate=WORK/'candidate02'
    if candidate.exists():
        raise ValueError('candidate02 already exists')
    shutil.copytree(base,candidate,copy_function=shutil.copy2)
    slots=[10,11,12,13]
    before=[Image.open(base/f'native_frames/{k:04d}.png').convert('RGBA') for k in slots]
    neutral=np.asarray(before[0])
    # Distal forefoot support only: near heel lies left of245, far heel left
    # of253. Neither ankle, calf nor heel belongs to these4-pixel-high caps.
    caps={'near_forefoot':[245,383,253,387],'far_forefoot':[253,377,260,381]}
    mask=np.zeros((500,500),bool)
    for x0,y0,x1,y1 in caps.values(): mask[y0:y1,x0:x1]=True
    frames=[];outside=[]
    for k,original in zip(slots,before):
        arr=np.asarray(original).copy();arr[mask]=neutral[mask]
        new=Image.fromarray(arr,'RGBA');new.save(candidate/f'native_frames/{k:04d}.png')
        frames.append(new)
        outside.append(int(np.any(arr[~mask]!=np.asarray(original)[~mask],axis=1).sum()))
    assert max(outside)==0
    caps_error=[]
    for x0,y0,x1,y1 in caps.values():
        aa=np.asarray(frames)[:,y0:y1,x0:x1]
        caps_error.append(int(np.abs(aa.astype(np.int16)-aa[0].astype(np.int16)).max()))
    assert max(caps_error)==0
    originals=[full_original(k) for k in slots]
    rejected=[Image.open(CURRENT/f'native_frames/{k:04d}.png').convert('RGBA') for k in slots]
    crop=(214,280,278,393);review=candidate/'review'
    make_board([originals,rejected,frames],['official all layers','rejected v03','new drawing locked toes'],crop,review/'whole_body_comparison.png',4)
    make_board([originals,frames],['official','new drawing locked toes'],(230,364,268,391),review/'foot_poses.png',10)
    animation(frames,crop,review/'standing_native.webp',1,180)
    animation(frames,crop,review/'standing_x4.webp',4,180)
    report=json.loads((candidate/'clips/clip_010_013/selection.json').read_text('utf-8'))
    report['native_postprocess']={'source':'this newly redrawn neutral phase, never old v03 body','forefoot_cap_rois':caps,'all_pixels_outside_caps_preserved':True,'native_is_authoritative':True}
    save_json(candidate/'clips/clip_010_013/selection.json',report)
    m=json.loads((base/'manifest.json').read_text('utf-8'))
    m['state']='root_selected_candidate02'
    m['source_candidate01_manifest']='output/whale_stand_redraw_v04/candidate01/manifest.json'
    m['source_candidate01_manifest_sha256']=sha(base/'manifest.json')
    m['native_postprocess']={'only_two_forefoot_caps_locked':True,'rois':caps,'max_cap_rgba_delta':caps_error,'changed_pixels_outside_caps_vs_new_drawing':outside,'source_neutral_slot':10,'old_v03_body_used':False,'heel_calf_torso_free':True}
    for row in m['frames']:
        k=row['slot'];native=candidate/f'native_frames/{k:04d}.png';hd=candidate/f'clips/clip_010_013/hd/{k:04d}.png'
        row.update({'native':native.relative_to(ROOT).as_posix(),'native_sha256':sha(native),'hd':hd.relative_to(ROOT).as_posix(),'hd_sha256':sha(hd)})
    m['selection']='output/whale_stand_redraw_v04/candidate02/clips/clip_010_013/selection.json'
    m['selection_sha256']=sha(candidate/'clips/clip_010_013/selection.json')
    save_json(candidate/'manifest.json',m)
    cfg=ROOT/'design/fatfish_whale_maid/action_redraw_v04.json'
    c=json.loads(cfg.read_text('utf-8'));c['status']='root_selected_candidate02';c['candidate_manifest']='output/whale_stand_redraw_v04/candidate02/manifest.json';c['native_postprocess']=m['native_postprocess'];save_json(cfg,c)
    generation=json.loads((WORK/'generation_record.json').read_text('utf-8'));generation['status']='root_selected_candidate02';generation['selected_native_manifest']=c['candidate_manifest'];generation['native_postprocess']=m['native_postprocess'];save_json(WORK/'generation_record.json',generation)
    source_paths=[WORK/'generation_record.json',WORK/'palette_original.png',WORK/'reference/motion_analysis.json',base/'manifest.json']
    source_paths.extend(WORK/'art'/f for f in ['standing_sheet_v01.png','standing_sheet_v02_rejected_crossed_feet.png','standing_sheet_v03.png'])
    source_paths.extend(WORK/f'generation_prompt_v0{i}.txt' for i in [1,2,3])
    for it in generation['iterations']:
        source_paths.extend(ROOT/x for x in it['references'])
    source_paths.extend(CURRENT/f'native_frames/{k:04d}.png' for k in range(174))
    sources={p.relative_to(ROOT).as_posix():sha(p) for p in source_paths}
    record={'status':'root_selected_frozen','candidate':'output/whale_stand_redraw_v04/candidate02','manifest':c['candidate_manifest'],'manifest_sha256':sha(candidate/'manifest.json'),'native_dir':'output/whale_stand_redraw_v04/candidate02/native_frames','hd_root':'output/whale_stand_redraw_v04/candidate02/clips','selection_root':'output/whale_stand_redraw_v04/candidate02/clips','target_slots':slots,'frames':m['frames'],'native_sha256':{f'{k:04d}.png':sha(candidate/f'native_frames/{k:04d}.png') for k in slots},'hd_sha256':{f'clip_010_013/hd/{k:04d}.png':sha(candidate/f'clips/clip_010_013/hd/{k:04d}.png') for k in slots},'selection_sha256':{'clip_010_013/selection.json':sha(candidate/'clips/clip_010_013/selection.json')},'config':{'path':cfg.relative_to(ROOT).as_posix(),'sha256':sha(cfg)},'script':{'path':Path(__file__).relative_to(ROOT).as_posix(),'sha256':sha(__file__)},'source_sha256':sources,'generation_record':'output/whale_stand_redraw_v04/generation_record.json','new_imagegen_calls':3,'new_65535_calls':0,'approved_scope':'Root approved new v03-sheet bodies and only neutral forefoot-cap lock; no further drawing or pose changes.','installed':False,'user_aesthetic_approved':False}
    save_json(WORK/'frozen.json',record)
    print(json.dumps({'candidate':record['candidate'],'frozen':'output/whale_stand_redraw_v04/frozen.json','caps':m['native_postprocess'],'source_files':len(sources)},ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['reference','segment','prepare','lock-caps'])
    args=parser.parse_args()
    {'reference':reference,'segment':segment,'prepare':prepare,'lock-caps':lock_caps}[args.command]()
