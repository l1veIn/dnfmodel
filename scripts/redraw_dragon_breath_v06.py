"""Prepare fixed-world references and inspect actual imagegen breath drawings.

This is a local asset production helper, not a final/full character renderer.
It never writes existing assets, packages, design pointers or issue records.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone, timedelta

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/dragon_breath_redraw_v06'
BASE = ROOT / 'output/gpt_dragon_slayer_v05'
PROFILES = {
    'idle': {'clip': 'clip_000_003', 'slots': [0,1,2,3], 'crop': [165,240,160,160]},
    'hip': {'clip': 'clip_009_012', 'slots': [9,10,11,12], 'crop': [165,240,160,160]},
    'back': {'clip': 'clip_232_235', 'slots': [232,233,234,235], 'crop': [165,240,160,160]},
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')


def prepare():
    """One neutral detailed base copied into a fixed 2x2 world grid per asset."""
    inputs = OUT/'inputs'
    inputs.mkdir(parents=True,exist_ok=True)
    entries=[]
    for name,p in PROFILES.items():
        slot=p['slots'][0]
        native=Image.open(BASE/f'native_frames/{slot:04d}.png').convert('RGBA')
        hd=Image.open(BASE/f"clips/{p['clip']}/hd/{slot:04d}.png").convert('RGBA')
        nb=native.getbbox(); hb=hd.getbbox()
        L,T,S,_=p['crop']; zoom=6; cell=S*zoom
        neutral=Image.new('RGBA',(cell,cell))
        detail=hd.crop(hb).resize(((nb[2]-nb[0])*zoom,(nb[3]-nb[1])*zoom),Image.Resampling.LANCZOS)
        neutral.alpha_composite(detail,((nb[0]-L)*zoom,(nb[1]-T)*zoom))
        sheet=Image.new('RGBA',(cell*2,cell*2))
        for i in range(4):
            sheet.alpha_composite(neutral,((i%2)*cell,(i//2)*cell))
        target=inputs/f'{name}_neutral_edit_target.png'
        neutral_path=inputs/f'{name}_neutral_cell.png'
        if not target.exists(): sheet.save(target)
        if not neutral_path.exists(): neutral.save(neutral_path)
        official=ROOT/f'output/action_redraw_2026-11-10/dragon_reference/{name}/all_layers_contact.png'
        entry={'asset':name,'slots':p['slots'],'target':rel(target),'neutral_cell':rel(neutral_path),
               'world_crop':p['crop'],'input_zoom':zoom,'input_cell_size':cell,
               'neutral_native_bbox':list(nb),'neutral_hd_bbox':list(hb),
               'master':rel(BASE/'parts/raw/master_b_0.png'),
               'official_motion_reference':rel(official),
               'sources':{rel(BASE/f'native_frames/{slot:04d}.png'):sha(BASE/f'native_frames/{slot:04d}.png'),
                          rel(BASE/f"clips/{p['clip']}/hd/{slot:04d}.png"):sha(BASE/f"clips/{p['clip']}/hd/{slot:04d}.png"),
                          rel(official):sha(official)}}
        entries.append(entry)
    write_json(inputs/'references.json',{'layout':'2 columns x2 rows, common world crop and scale, no per-cell bbox alignment','assets':entries})
    print(json.dumps({'prepared':[x['target'] for x in entries]},ensure_ascii=False))


def clean_cell(image):
    """Keep the actual drawn character alpha, discard external generation specks.

    Hidden RGB is zeroed; apparent pink/white dots in raw RGBA viewers are not
    recolored into the costume. No internal lilac or peach color is washed.
    """
    b=np.asarray(image.convert('RGBA')).copy()
    labels,n=ndimage.label(b[...,3]>128)
    areas=np.bincount(labels.ravel());areas[0]=0
    main=labels==areas.argmax()
    near=ndimage.binary_dilation(main,iterations=2)
    b[~near,3]=0
    b[b[...,3]==0,:3]=0
    return Image.fromarray(b,'RGBA')


def old_palette():
    # Read-only recovery of the published palette; does not render old frames.
    sys.path.insert(0,str(ROOT/'scripts'))
    from repair_dragon_actions_v05 import native_palette
    return native_palette()


def native_render(hd,crop,palette):
    os.environ['PATCH_ID']='gpt_dragon_slayer_v03'
    sys.path.insert(0,str(ROOT/'.claude/skills/dnf-character-patch/scripts'))
    from kit import art
    L,T,S,_=crop
    color,alpha=art.downscale(hd,(S,S))
    sprite=art.finish(art.sharpen(art.grade(color)),alpha,palette)
    world=Image.new('RGBA',(500,500));world.paste(sprite,(L,T))
    return np.asarray(world).copy()


def fixed_layer_mask(size,crop,zoom):
    """Declared hold regions from the original: face, pelvis, legs/shoes.

    This only holds new canonical artwork; shoulder/chest/elbow/wrist lines
    remain the actual newly drawn lines from each generated phase.
    """
    L,T,S,_=crop
    yy,xx=np.mgrid[:size[1],:size[0]].astype(float)
    xx=L+xx/zoom;yy=T+yy/zoom
    # Whole head core, plus the complete planted lower figure.
    held=(yy<294)|(yy>=338)
    # Pelvic front/waist-chain is still, hanging hands at x~235/267 are outside.
    held|=(xx>=243)&(xx<=261)&(yy>=318)
    return held


def process(asset,raw_path,candidate_name):
    p=PROFILES[asset];crop=p['crop'];L,T,S,_=crop
    raw_path=Path(raw_path).resolve()
    raw=Image.open(raw_path).convert('RGBA')
    if raw.width%2 or raw.height%2: raise ValueError('Expected a fixed2x2 sheet')
    cw,ch=raw.width//2,raw.height//2
    cells=[clean_cell(raw.crop(((i%2)*cw,(i//2)*ch,(i%2+1)*cw,(i//2+1)*ch))) for i in range(4)]
    old=np.asarray(Image.open(BASE/f"native_frames/{p['slots'][0]:04d}.png").convert('RGBA'))
    oldbbox=Image.fromarray(old).getbbox();newbbox=cells[0].getbbox()
    # ONE common affine, calibrated on F1 only. Never per-cell bbox alignment.
    scale=(oldbbox[3]-oldbbox[1])/(newbbox[3]-newbbox[1])
    tx=(oldbbox[0]+oldbbox[2])/2-scale*(newbbox[0]+newbbox[2])/2
    ty=oldbbox[1]-scale*newbbox[1]
    zoom=6;side=S*zoom
    coefficients=(1/(zoom*scale),0,(L-tx)/scale,0,1/(zoom*scale),(T-ty)/scale)
    hds=[c.convert('RGBa').transform((side,side),Image.Transform.AFFINE,coefficients,resample=Image.Resampling.BICUBIC).convert('RGBA') for c in cells]
    canonical=np.asarray(hds[0]).copy()
    held=fixed_layer_mask((side,side),crop,zoom)
    for i in range(1,4):
        a=np.asarray(hds[i]).copy();a[held]=canonical[held];hds[i]=Image.fromarray(a,'RGBA')
    palette=old_palette()
    natives=[native_render(hd,crop,palette) for hd in hds]
    native_hold=fixed_layer_mask((500,500),[0,0,500,500],1)
    for i in range(1,4):natives[i][native_hold]=natives[0][native_hold]
    candidate=OUT/candidate_name/asset
    if (candidate/'manifest.json').exists():raise ValueError('Candidate exists; refuse overwrite')
    native_dir=candidate/'native_frames';hd_dir=candidate/f"clips/{p['clip']}/hd";review=candidate/'review'
    native_dir.mkdir(parents=True,exist_ok=True);hd_dir.mkdir(parents=True,exist_ok=True);review.mkdir(parents=True,exist_ok=True)
    selection=json.loads((BASE/f"clips/{p['clip']}/selection.json").read_text('utf-8'))
    from kit import art
    common_scale=S/selection['window'][2]
    left0,top0=art.placement(selection['window'],common_scale)
    common_offset=[L-left0,T-top0]
    for i,slot in enumerate(p['slots']):
        hds[i].save(hd_dir/f'{slot:04d}.png')
        Image.fromarray(natives[i],'RGBA').save(native_dir/f'{slot:04d}.png')
        row=next(x for x in selection['frames'] if x['slot']==slot)
        row['scale']=common_scale;row['offset']=common_offset;row['track']=[0,0]
        row['video_frame']=f'builtin_breath_redraw_v06:{asset}:{i}'
        row.pop('action_repair_v05',None)
        row['action_redraw_v06']={'source':rel(raw_path),'cell':i,'common_world_crop':crop,'one_affine_calibrated_on_first_cell':True,'held_new_canonical_regions':['head core above294','central pelvis from318','lower figure from338'],'motion':'actual drawn shoulder/collar/chest and elbow/wrist phase lines'}
    selection.pop('action_repair_source',None)
    write_json(hd_dir.parent/'selection.json',selection)
    # Whole-body review in the same world crop; no separate bbox fitting.
    vbox=(190,255,300,392);w,h=vbox[2]-vbox[0],vbox[3]-vbox[1]
    contact=Image.new('RGB',(4*w*3,3*(h*3+24)),(42,46,60));d=ImageDraw.Draw(contact)
    before=[];after=[];native_an=[]
    for i,slot in enumerate(p['slots']):
        official_path=ROOT/f'output/action_redraw_2026-11-10/dragon_reference/{asset}/all_layers/{slot:04d}.png'
        if not official_path.is_file(): raise ValueError(f'Missing true original frame: {official_path}')
        original=Image.open(official_path).convert('RGBA')
        prev=Image.open(BASE/f'native_frames/{slot:04d}.png').convert('RGBA');new=Image.fromarray(natives[i],'RGBA')
        for row,(im,label) in enumerate([(original,'official'),(prev,'before'),(new,'new drawing')]):
            part=im.crop(vbox).resize((w*3,h*3),Image.Resampling.NEAREST)
            xy=(i*w*3,row*(h*3+24));contact.paste(part,(xy[0],xy[1]+24),part);d.text((xy[0]+3,xy[1]+4),f'{label} u{slot+1}/k{slot}',fill='white')
        for im,store in [(prev,before),(new,after)]:
            bg=Image.new('RGBA',(w,h),(42,46,60,255));bg.alpha_composite(im.crop(vbox));store.append(bg.convert('RGB'))
        native_an.append(after[-1])
    contact.save(review/'whole_body_before_after.jpg',quality=95)
    for name,imgs in [('before_native',before),('after_native',after)]:
        imgs[0].save(review/f'{name}.webp',save_all=True,append_images=imgs[1:],duration=180,loop=0,lossless=True)
        big=[im.resize((w*4,h*4),Image.Resampling.NEAREST) for im in imgs]
        big[0].save(review/f'{name}_x4.webp',save_all=True,append_images=big[1:],duration=180,loop=0,lossless=True)
    cells[0].save(candidate/'canonical_generated_cell.png')
    hds[0].save(candidate/'canonical_world_hd.png')
    Image.fromarray(natives[0],'RGBA').save(candidate/'canonical_world_native.png')
    manifest={'status':'candidate_pending_root_visual_review','asset':asset,'slots':p['slots'],'raw_generated_sheet':rel(raw_path),'raw_sha256':sha(raw_path),'raw_cell_shape':[cw,ch],'raw_cell_bboxes':[list(c.getbbox()) for c in cells],'world_crop':crop,'hd_zoom':zoom,'common_affine':{'scale':scale,'tx':tx,'ty':ty,'calibrated_only_on_frame':p['slots'][0]},'native_dir':rel(native_dir),'hd_root':rel(candidate/'clips'),'selection_root':rel(candidate/'clips'),'canonical_hd':rel(candidate/'canonical_world_hd.png'),'canonical_native':rel(candidate/'canonical_world_native.png'),'native_sha256':{str(k):sha(native_dir/f'{k:04d}.png') for k in p['slots']},'hd_sha256':{str(k):sha(hd_dir/f'{k:04d}.png') for k in p['slots']},'new_imagegen_calls':1,'new_65535_calls':0,'fixed_native_mask_rows':'y<294, y>=338, central pelvis x243..261/y>=318','note':'Newly drawn motion in each cell; fixed regions use the new canonical drawing, no Gaussian/whole-body motion synthesis. Native is authoritative; original sources untouched.','user_aesthetic_approved':False,'installed':False}
    write_json(candidate/'manifest.json',manifest)
    print(json.dumps({'candidate':rel(candidate),'canonical_hd':manifest['canonical_hd'],'canonical_native':manifest['canonical_native'],'raw_bboxes':manifest['raw_cell_bboxes'],'common_affine':manifest['common_affine']},ensure_ascii=False))


def combine(candidate_name):
    candidate=OUT/candidate_name
    manifest_path=candidate/'manifest.json'
    if manifest_path.exists():raise ValueError('Combined candidate exists')
    native_dir=candidate/'native_frames';cliproot=candidate/'clips';native_dir.mkdir(exist_ok=True);cliproot.mkdir(exist_ok=True)
    reports=[]
    for asset,p in PROFILES.items():
        child=candidate/asset
        report=json.loads((child/'manifest.json').read_text('utf-8'));reports.append(report)
        for slot in p['slots']:
            shutil.copy2(child/f'native_frames/{slot:04d}.png',native_dir/f'{slot:04d}.png')
        shutil.copytree(child/'clips',cliproot,dirs_exist_ok=True,copy_function=shutil.copy2)
    targets=sorted(k for p in PROFILES.values() for k in p['slots'])
    checks={}
    hold=fixed_layer_mask((500,500),[0,0,500,500],1)
    for name,p in PROFILES.items():
        frames=[np.asarray(Image.open(native_dir/f'{slot:04d}.png').convert('RGBA')) for slot in p['slots']]
        checks[name]={'canonical_held_regions_rgba_max_delta':max(int(np.max(np.abs(a[hold].astype(int)-frames[0][hold].astype(int)))) for a in frames),
                      'adjacent_changed_visible_pixels':[int(np.sum(np.any(frames[(i+1)%4]!=frames[i],axis=2)&((frames[(i+1)%4][...,3]>0)|(frames[i][...,3]>0)))) for i in range(4)],
                      'common_affine':reports[list(PROFILES).index(name)]['common_affine']}
        assert checks[name]['canonical_held_regions_rgba_max_delta']==0
    request_paths=[OUT/'generated'/x for x in ['idle_request.json','hip_request.json','hip_request_v2.json','back_request.json']]
    gen=[]
    for path in request_paths:
        entry=json.loads(path.read_text('utf-8'));entry['request_record']=rel(path)
        entry['selected']=path.name!='hip_request.json';gen.append(entry)
    record={'tool':'built-in imagegen','calls':4,'selected_sheets':3,'rejected_sheets':1,'paid_65535_calls':0,'entries':gen}
    write_json(OUT/'generation_record.json',record)
    baseline={str(k):sha(BASE/f'native_frames/{k:04d}.png') for k in range(246)}
    manifest={'status':'pending_root_visual_review','candidate':candidate_name,'slots':targets,'frame_count':12,'issues':[10,12,15],
              'native_dir':rel(native_dir),'hd_root':rel(cliproot),'selection_root':rel(cliproot),
              'native_sha256':{str(k):sha(native_dir/f'{k:04d}.png') for k in targets},
              'asset_manifests':{name:{'path':rel(candidate/name/'manifest.json'),'sha256':sha(candidate/name/'manifest.json')} for name in PROFILES},
              'source_native_sha256':baseline,'source':rel(BASE),'generation_record':rel(OUT/'generation_record.json'),
              'fixed_region_checks':checks,'new_imagegen_calls':4,'new_65535_calls':0,
              'canonical_idle_hd':rel(candidate/'idle/canonical_world_hd.png'),'canonical_idle_native':rel(candidate/'idle/canonical_world_native.png'),
              'known_limits':['Idle drawn collar peak is approximately1 native pixel versus the original2; upper arms/wrists do follow, no synthetic amplification added.'],
              'installed':False,'user_aesthetic_approved':False}
    write_json(manifest_path,manifest)
    config=json.loads((ROOT/'design/gpt_dragon_slayer_v03/breath_redraw_v06.json').read_text('utf-8'))
    config.update({'status':'candidate02_complete_pending_root_visual_review','candidate_manifest':rel(manifest_path),'targets':targets,'world_crop':[165,240,160,160],'generation_record':rel(OUT/'generation_record.json'),'new_imagegen_calls':4})
    write_json(ROOT/'design/gpt_dragon_slayer_v03/breath_redraw_v06.json',config)
    print(json.dumps({'manifest':rel(manifest_path),'native_dir':rel(native_dir),'hd_root':rel(cliproot),'checks':checks},ensure_ascii=False))


def freeze(candidate_name):
    destination=OUT/'frozen.json'
    if destination.exists():raise ValueError('Already frozen')
    candidate=OUT/candidate_name
    manifest=json.loads((candidate/'manifest.json').read_text('utf-8'))
    inputs=[candidate/'manifest.json',ROOT/'scripts/redraw_dragon_breath_v06.py',ROOT/'design/gpt_dragon_slayer_v03/breath_redraw_v06.json',OUT/'generation_record.json']
    inputs.extend(p for p in candidate.rglob('*') if p.is_file() and (p.suffix=='.png' or p.name=='selection.json' or p.name=='manifest.json'))
    for entry in json.loads((OUT/'generation_record.json').read_text('utf-8'))['entries']:
        inputs.append(ROOT/entry['request_record'])
        if entry.get('raw'):inputs.append(ROOT/entry['raw'])
    record={'status':'root_selected_exact_candidate','frozen_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'manifest':rel(candidate/'manifest.json'),'manifest_sha256':sha(candidate/'manifest.json'),
            'native_dir':manifest['native_dir'],'hd_root':manifest['hd_root'],'selection_root':manifest['selection_root'],
            'slots':manifest['slots'],'frame_count':12,'files_sha256':{rel(p):sha(p) for p in sorted(set(inputs))},
            'source_native_sha256':manifest['source_native_sha256'],'new_imagegen_calls':4,'new_65535_calls':0,'installed':False,'user_aesthetic_approved':False}
    write_json(destination,record)
    print(json.dumps({'frozen':rel(destination),'sha256':sha(destination),'files':len(record['files_sha256'])},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','process','combine','freeze'])
    parser.add_argument('--asset',choices=list(PROFILES))
    parser.add_argument('--raw')
    parser.add_argument('--candidate',default='candidate01')
    args=parser.parse_args()
    if args.command=='prepare': prepare()
    elif args.command=='process': process(args.asset,args.raw,args.candidate)
    elif args.command=='combine':combine(args.candidate)
    elif args.command=='freeze':freeze(args.candidate)


if __name__=='__main__': main()
