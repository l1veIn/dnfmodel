"""Read-only official portrait inventory and visual indices for the interface UI."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/workbench')]
import render
import categories

OUT = ROOT / 'output/interface_portraits_v01/reference'
PROFESSIONS = ['gunner_at', 'swordman_at', 'mage']
GROUPS = {
    'whale':dict(profession='mage',shared_start=15,pk_base=48,creation='magef',
        roles=['elemental master','summoner','battle mage','witch','enchantress'],avatar_prefix='neo_magef_'),
    'claude':dict(profession='gunner_at',shared_start=25,pk_base=80,creation='gunnerf',
        roles=['ranger','launcher','mechanic','spitfire','paramedic'],avatar_prefix='neo_gunnerf_'),
    'dragon':dict(profession='swordman_at',shared_start=47,pk_base=150,creation='slayerf',
        roles=['swordmaster','darktemplar','demon slayer','vagabond','blade'],avatar_prefix='neo_ghostf_'),
}

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def frame_record(img,k):
    raw=img.frames[k]; f=img.resolve(k)
    keys=('x','y','width','height','canvas_width','canvas_height','w','h','cw','ch')
    return dict(index=k, link=raw.get('link'), resolved={a:f[a] for a in keys if a in f})
def full_frame(img,k):
    f=img.resolve(k); im=img.image(k).convert('RGBA')
    cw=f.get('cw',f.get('canvas_width'));ch=f.get('ch',f.get('canvas_height'))
    if cw and ch:
        out=Image.new('RGBA',(cw,ch));out.alpha_composite(im,(f.get('x',0),f.get('y',0)));return out
    return im
def gray(image):
    out=Image.new('RGBA',image.size,(64,70,82,255));out.alpha_composite(image);return out.convert('RGB')

def inventory():
    paths=[p for p in categories.portrait_paths(PROFESSIONS) if categories.classify(p)=='portrait']
    records=[]
    for path in paths:
        npk=render.official_npk(path);img=render.load_img(npk,path)
        rows=[frame_record(img,k) for k in range(len(img.frames))]
        rec=dict(path=path,official_npk=npk,npk_sha256=sha(npk),frame_count=len(rows),frames=rows,
            professions=[p for p in PROFESSIONS if categories.portrait_of(path,p)])
        if '/characterillust/' in path:
            tag=Path(path).stem;dest=OUT/'creation';dest.mkdir(parents=True,exist_ok=True)
            pic=full_frame(img,0);pic.save(dest/f'{tag}_official_canvas.png')
            gray(pic).save(dest/f'{tag}_official_gray.png')
            rec.update(canvas=list(pic.size),visible_bbox=pic.getbbox(),reference=f'output/interface_portraits_v01/reference/creation/{tag}_official_gray.png')
        else:
            # Decode only the per-frame alpha needed to identify true empty frames;
            # keep resolved header/link geometry as the authoritative placement.
            rec['empty_frames']=[k for k in range(len(rows)) if img.image(k).convert('RGBA').getchannel('A').getbbox() is None]
            rec['link_frames']={str(k):f['link'] for k,f in enumerate(img.frames) if 'link' in f}
        records.append(rec)
    save(OUT/'inventory.json',dict(scope='22 official portrait IMG paths for three female professions; read-only sources',records=records))
    print(json.dumps(dict(inventory=str(OUT/'inventory.json'),paths=len(records)),ensure_ascii=False))

def contacts():
    for path in categories.SHARED_PORTRAITS:
        npk=render.official_npk(path);img=render.load_img(npk,path);tag=Path(path).stem
        dest=OUT/'shared'/tag;dest.mkdir(parents=True,exist_ok=True)
        cols=8;per_page=40;cell=(230,290)
        records=[]
        for k in range(len(img.frames)):
            pic=img.image(k).convert('RGBA');bbox=pic.getbbox();records.append(dict(frame=k,alpha_bbox=bbox,size=list(pic.size),link=img.frames[k].get('link')))
            if bbox:
                pic.crop(bbox).save(dest/f'{k:03d}_crop.png')
        for start in range(0,len(img.frames),per_page):
            indices=list(range(start,min(start+per_page,len(img.frames))))
            board=Image.new('RGB',(cols*cell[0],math.ceil(len(indices)/cols)*cell[1]),(49,56,70));d=ImageDraw.Draw(board)
            for ii,k in enumerate(indices):
                pic=img.image(k).convert('RGBA');bbox=pic.getbbox();x=(ii%cols)*cell[0];y=(ii//cols)*cell[1]
                label=f'{k}' + (f' -> {img.frames[k]["link"]}' if 'link' in img.frames[k] else '')
                d.text((x+6,y+5),label,fill='white')
                if not bbox:
                    d.text((x+6,y+25),'EMPTY',fill=(230,170,100));continue
                pic=pic.crop(bbox);pic.thumbnail((cell[0]-12,cell[1]-30),Image.Resampling.LANCZOS)
                board.paste(pic,(x+(cell[0]-pic.width)//2,y+25),pic)
            board.save(dest/f'contact_{start:03d}_{indices[-1]:03d}.jpg',quality=92)
        save(dest/'frame_index.json',dict(path=path,official_npk=npk,frame_count=len(img.frames),frames=records))
        print(json.dumps(dict(shared=tag,frames=len(img.frames),output=str(dest)),ensure_ascii=False))

def mapping():
    """Candidate indices established from the full visual boards, not old labels."""
    import cv2
    import numpy as np
    inventory=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))['records']
    bypath={r['path']:r for r in inventory}
    pkpath=categories.SHARED_PORTRAITS[-1]
    pk=render.load_img(render.official_npk(pkpath),pkpath)
    sift=cv2.SIFT_create(nfeatures=1600)
    matcher=cv2.BFMatcher(cv2.NORM_L2)
    def features(image):
        arr=np.asarray(image.convert('RGBA'))
        return sift.detectAndCompute(cv2.cvtColor(arr[:,:,:3],cv2.COLOR_RGB2GRAY),(arr[:,:,3]>40).astype('uint8')*255)
    def match(a,b):
        ka,da=features(a);kb,db=features(b)
        if da is None or db is None:return dict(ratio_matches=0,ransac_inliers=0)
        pairs=matcher.knnMatch(da,db,k=2)
        good=[m for pair in pairs if len(pair)==2 for m,n in [pair] if m.distance<.7*n.distance]
        if len(good)<4:return dict(ratio_matches=len(good),ransac_inliers=0)
        aa=np.float32([ka[m.queryIdx].pt for m in good]);bb=np.float32([kb[m.trainIdx].pt for m in good])
        h,mask=cv2.findHomography(aa,bb,cv2.RANSAC,3)
        return dict(ratio_matches=len(good),ransac_inliers=int(mask.sum()) if mask is not None else 0,homography=h.tolist() if h is not None else None)
    result=dict(status='offline_visual_candidate_mapping_for_independent_review',zero_based=True,
        identification_basis='Viewed all495 shared frames. Same profession art and class order matched across classic/second-awakening/neo references; no reliance on unchecked old labels.',
        actual_game_ani_verified=False,groups=GROUPS,shared=[],creation=[],adventurer=[])
    for path in categories.SHARED_PORTRAITS:
        img=render.load_img(render.official_npk(path),path);targets=[]
        for project,g in GROUPS.items():
            if path==pkpath:
                slots=[g['pk_base']]+list(range(g['pk_base']+1,g['pk_base']+16))
            else:slots=list(range(g['shared_start'],g['shared_start']+5))
            for k in slots:
                pic=img.image(k).convert('RGBA');empty=pic.getchannel('A').getbbox() is None
                if path==pkpath:
                    relative=k-g['pk_base'];tier='base' if relative==0 else ['classic','awakening2','neo'][(relative-1)//5]
                    role=None if relative==0 else g['roles'][(relative-1)%5]
                    anchor=None
                else:
                    idx=k-g['shared_start'];role=g['roles'][idx];tier='awakening2' if 'awakening2/' in path else 'classic'
                    anchor=g['pk_base']+1+idx+(5 if tier=='awakening2' else 0)
                row=dict(slot=k,project=project,profession=g['profession'],transfer=role,tier=tier,
                    policy='preserve_official_empty' if empty else 'replace_nonempty_target',
                    official_empty=empty,original_link=img.frames[k].get('link'),
                    geometry=frame_record(img,k)['resolved'],visual_crop=f'output/interface_portraits_v01/reference/shared/{Path(path).stem}/{k:03d}_crop.png' if not empty else None)
                if anchor is not None and not empty:
                    row['pk_same_art_anchor']=anchor
                    row['same_art_geometric_match']=match(pic,pk.image(anchor))
                targets.append(row)
        all_slots={r['slot'] for r in targets}
        result['shared'].append(dict(path=path,official_npk=render.official_npk(path),frame_count=len(img.frames),targets=targets,
            target_slots=sorted(all_slots),paint_slots=[r['slot'] for r in targets if not r['official_empty']],
            preserve_empty_slots=[r['slot'] for r in targets if r['official_empty']],
            non_target_slots=[i for i in range(len(img.frames)) if i not in all_slots]))
    # For image review, lay out the same five class branches in named rows.
    for project,g in GROUPS.items():
        rows=[]
        for path in categories.SHARED_PORTRAITS[:3]:
            img=render.load_img(render.official_npk(path),path)
            rows.append((Path(path).stem,[(img,k) for k in range(g['shared_start'],g['shared_start']+5)]))
        for j,tier in enumerate(['pk_classic','pk_awakening2','pk_neo']):
            rows.append((tier,[(pk,g['pk_base']+1+j*5+k) for k in range(5)]))
        avatars=[]
        for role in g['roles']:
            path=f'sprite/interface2/adventurer2020/{g["avatar_prefix"]}{role}.img'
            rec=bypath[path];img=render.load_img(rec['official_npk'],path);avatars.append((img,0))
            result['adventurer'].append(dict(path=path,project=project,profession=g['profession'],transfer=role,frame_count=rec['frame_count'],canvas=[121,90],
                empty_frames=rec['empty_frames'],links=rec['link_frames'],all_frame_geometry=rec['frames'],official_npk=rec['official_npk']))
        rows.append(('named_adventurer_frame0',avatars))
        w,h=250,230;board=Image.new('RGB',(5*w,len(rows)*h),(49,56,70));d=ImageDraw.Draw(board)
        for ri,(label,entries) in enumerate(rows):
            for ci,(img,k) in enumerate(entries):
                x=ci*w;y=ri*h;d.text((x+5,y+4),f'{label} / {k}',fill='white');d.text((x+5,y+18),g['roles'][ci],fill=(220,220,150))
                pic=img.image(k).convert('RGBA');bb=pic.getbbox()
                if not bb:d.text((x+5,y+40),'OFFICIAL EMPTY - KEEP',fill=(255,170,100));continue
                pic=pic.crop(bb);pic.thumbnail((w-12,h-42),Image.Resampling.LANCZOS);board.paste(pic,(x+(w-pic.width)//2,y+38),pic)
        board.save(OUT/f'{project}_cross_table_evidence.jpg',quality=94)
        creation=f'sprite/interface2/charactercreatever2/characterillust/{g["creation"]}.img'
        rec=bypath[creation];result['creation'].append(dict(path=creation,project=project,profession=g['profession'],frames=rec['frames'],canvas=rec['canvas'],visible_bbox=rec['visible_bbox'],official_reference=rec['reference'],pk_base_frame=g['pk_base']))
    result['totals']=dict(unique_img_paths=22,creation=3,adventurer=15,adventurer_frames=sum(r['frame_count'] for r in result['adventurer']),
        shared_frames=sum(r['frame_count'] for r in result['shared']),shared_target_slots=sum(len(r['target_slots']) for r in result['shared']),
        shared_paint_slots=sum(len(r['paint_slots']) for r in result['shared']),shared_empty_preserved=sum(len(r['preserve_empty_slots']) for r in result['shared']))
    dest=ROOT/'design/interface_portraits_v01/mapping_v01.json';save(dest,result)
    print(json.dumps(dict(mapping=str(dest),totals=result['totals']),ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['inventory','contacts','mapping','all']);a=p.parse_args()
    if a.command in ('inventory','all'):inventory()
    if a.command in ('contacts','all'):contacts()
    if a.command in ('mapping','all'):mapping()
