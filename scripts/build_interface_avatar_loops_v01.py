"""Reuse clean accepted character/true-eyelid art for four-keyframe UI avatars.

Writes new avatar source proposals only, never old portraits, game files or NPKs.
The official 90-180 frame counts are expanded from long-hold four-state loops.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from scipy.ndimage import map_coordinates

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'output/interface_portraits_v01/avatar_sources'
sys.path.insert(0,str(ROOT/'scripts'))

SPECS={
 'claude':dict(source_dir='output/claude_buff_v05/preview/frames',
    source_indices={'open_rest':0,'open_micro':4,'half':7,'closed':8},
    crop=[34,-4,397,266],source_type='exact_existing_clean_character_frames'),
 'dragon':dict(source_dir='output/dragon_buff_v04/drafts/draft01/portrait_frames',
    source_indices={'open_rest':7,'open_micro':10,'half':12,'closed':13},
    crop=[53,-10,416,260],source_type='exact_existing_clean_hero_layer_full_opacity'),
 'whale':dict(source_indices={'open_rest':5,'open_micro':8,'half':10,'closed':11},
    crop=[94,-6,457,264],source_type='reconstructed_clean_actor_before_all_water_fx'),
}
STATES=['open_rest','open_micro','half','closed']

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rel(path):return Path(path).resolve().relative_to(ROOT).as_posix()
def save(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def whale_sources():
 """Exact character branch of accepted build_whale_illustrations.build_buff.

 Excludes slanted window/reveal, ocean pane, water whale, slash/ripples/droplets.
 No new optical flow, generated paint or eye interpolation is introduced.
 """
 from build_whale_illustrations import alpha_clean
 source_paths=[ROOT/'output/whale_buff_v01/raw/portrait.png',ROOT/'output/whale_buff_v01/raw/blink_closed.png',ROOT/'output/whale_buff_v02/raw/blink_half.png']
 raw,closed,half=[alpha_clean(Image.open(p),6).resize((460,690),Image.Resampling.LANCZOS) for p in source_paths]
 frames=[];size=(470,668);base=Image.new('RGBA',size);base.alpha_composite(raw,(8,8))
 eye_mask=Image.new('L',size);d=ImageDraw.Draw(eye_mask)
 for box in [(257,138,316,178),(314,135,360,174)]:d.rounded_rectangle(box,radius=5,fill=255)
 eye_mask=eye_mask.filter(ImageFilter.GaussianBlur(1.5))
 states={}
 for name,pic in [('half',half),('closed',closed)]:
  page=Image.new('RGBA',size);page.alpha_composite(pic,(8,8));states[name]=Image.composite(page,base,eye_mask)
 yy,xx=np.mgrid[:668,:470].astype(np.float32)
 hair=np.clip((242-xx)/90,0,1)*np.clip((yy-165)/120,0,1)*np.clip((565-yy)/100,0,1)
 skirt=np.clip((yy-500)/100,0,1)*np.clip((668-yy)/25,0,1)
 hair[(xx>245)&(yy<260)]=0
 for k in range(19):
  phase=k/18;wave=math.sin(2*math.pi*phase)
  actor=states['half'] if k in (10,12) else states['closed'] if k==11 else base
  a=np.asarray(actor)
  dx=1.8*wave*hair+.8*math.sin(2*math.pi*phase+.4)*skirt;dy=.65*wave*hair
  coords=[yy-dy,xx-dx]
  warped=np.stack([map_coordinates(a[...,c],coords,order=1,mode='constant',cval=0) for c in range(4)],axis=2).astype(np.uint8)
  warped[55:258,245:410]=a[55:258,245:410]
  frames.append(Image.fromarray(warped,'RGBA'))
 return frames,source_paths

def cycle_map(n):
 """All current official lengths begin/end neutral; blinks stay six slots long."""
 assert n in (90,100,116,122,180),n
 out=[]
 for k in range(n):
  t=k%96
  state='open_rest' if t<32 else 'open_micro' if t<54 else 'open_rest' if t<60 else 'half' if t<62 else 'closed' if t<64 else 'half' if t<66 else 'open_micro' if t<78 else 'open_rest'
  out.append(state)
 assert out[0]==out[-1]=='open_rest'
 for k,state in enumerate(out):
  if state=='closed' and (k==0 or out[k-1]!='closed'):
   assert out[k-2:k]==['half','half'] and out[k:k+4]==['closed','closed','half','half']
 return out

def card(image,background):
 bg=Image.new('RGBA',image.size,background);bg.alpha_composite(image);return bg.convert('RGB')

def proposal(variant,mirrored_projects=()):
 out=WORK/variant
 if out.exists():raise FileExistsError(f'Never overwrite source proposal: {out}')
 out.mkdir(parents=True)
 whale,whale_inputs=whale_sources();records=[];keys={}
 for project,spec in SPECS.items():
  folder=out/project;folder.mkdir();(folder/'keyframes').mkdir();(folder/'clean_actor_states').mkdir()
  inputs={};state_records=[];images=[]
  for state,k in spec['source_indices'].items():
   if project=='whale':
    actor=whale[k]
    for p in whale_inputs:inputs[rel(p)]=sha(p)
    inputs['scripts/build_whale_illustrations.py']=sha(ROOT/'scripts/build_whale_illustrations.py')
   else:
    path=ROOT/spec['source_dir']/f'frame_{k:04d}.png';actor=Image.open(path).convert('RGBA');inputs[rel(path)]=sha(path)
   actor_path=folder/'clean_actor_states'/f'{state}.png';actor.save(actor_path)
   # One fixed box per character, common across every eyelid/micro state.
   crop=actor.crop(tuple(spec['crop']))
   av=crop.convert('RGBa').resize((121,90),Image.Resampling.LANCZOS).convert('RGBA')
   if project in mirrored_projects:av=ImageOps.mirror(av)
   dest=folder/'keyframes'/f'{state}.png';av.save(dest);images.append(av)
   arr=np.asarray(av);opaque=arr[:,:,3]>240
   state_records.append(dict(state=state,source_frame=k,actor=rel(actor_path),actor_sha256=sha(actor_path),avatar=rel(dest),avatar_sha256=sha(dest),alpha_bbox=av.getbbox(),alpha_extrema=av.getchannel('A').getextrema(),alpha_corner_values=[int(arr[y,x,3]) for x,y in [(0,0),(120,0),(0,89),(120,89)]],opaque_fraction=float(opaque.mean())))
  # Exact actor images are retained as proof that no effects were cropped in.
  board=Image.new('RGB',(4*484,2*396),(48,55,68));d=ImageDraw.Draw(board)
  for i,(state,im) in enumerate(zip(STATES,images)):
   for row,bg in enumerate([(48,55,68,255),(218,219,224,255)]):
    thumb=card(im,bg).resize((484,360),Image.Resampling.NEAREST)
    board.paste(thumb,(i*484,row*396+30));d.text((i*484+8,row*396+8),f'{project} / {state} / 121x90 x4',fill='white' if row==0 else 'black')
  board.save(folder/'keyframe_contact_x4.png')
  frames=cycle_map(100);by_state=dict(zip(STATES,images))
  # 50ms/slot is review timing only. IMG retains the official frame table.
  seq=[card(by_state[s],(48,55,68,255)) for s in frames]
  seq[0].save(folder/'preview_100_slots.webp',save_all=True,append_images=seq[1:],duration=50,loop=0,lossless=True)
  seq4=[im.resize((484,360),Image.Resampling.NEAREST) for im in seq]
  seq4[0].save(folder/'preview_100_slots_x4.webp',save_all=True,append_images=seq4[1:],duration=50,loop=0,lossless=True)
  record=dict(project=project,size=[121,90],source_type=spec['source_type'],crop=spec['crop'],source_canvas=[470,668],uniform_scale=1/3,horizontal_mirror=project in mirrored_projects,mirror_purpose='Align ornament side and facing within this UI art suite; old source files remain untouched' if project in mirrored_projects else None,states=state_records,source_sha256=inputs,new_generation_calls=0,new_65535_calls=0,fx_layers_included=False,
    unique_avatar_sha256=len({r['avatar_sha256'] for r in state_records}),preview_timing_ms_per_slot=50,preview_timing_is_not_ingame_ani=True)
  save(folder/'provenance.json',record);records.append(record);keys[project]=by_state
 mapping=json.loads((ROOT/'design/interface_portraits_v01/mapping_v01.json').read_text(encoding='utf-8'))
 rows=[]
 for row in mapping['adventurer']:
  states=cycle_map(row['frame_count'])
  rows.append(dict(path=row['path'],project=row['project'],frames=row['frame_count'],canvas=[121,90],horizontal_mirror=row['project'] in mirrored_projects,keyframes={state:rel(out/row['project']/'keyframes'/f'{state}.png') for state in STATES},frame_states=states,
    blink_closed_starts=[i for i,s in enumerate(states) if s=='closed' and (i==0 or states[i-1]!='closed')],first_last_identical=True,official_frame_geometry=row['all_frame_geometry']))
 save(out/'avatar_frame_map.json',dict(status='proposal_pending_root_and_independent_visual_review',new_generation_calls=0,new_65535_calls=0,unique_keyframes_per_character=4,cycle_slots=96,
    cycle_spans=[dict(state=s,start=a,end=b) for s,a,b in [('open_rest',0,31),('open_micro',32,53),('open_rest',54,59),('half',60,61),('closed',62,63),('half',64,65),('open_micro',66,77),('open_rest',78,95)]],
    official_ani_loop_unmodified=True,game_runtime_validated=False,source_records=records,rows=rows,total_official_frames=sum(r['frames'] for r in rows)))
 print(json.dumps(dict(proposal=rel(out),characters=3,unique_keys=12,targets=15,official_slots=sum(r['frames'] for r in rows)),ensure_ascii=False))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--variant',default='proposal01');p.add_argument('--mirror-projects',nargs='*',choices=list(SPECS),default=[]);a=p.parse_args();proposal(a.variant,a.mirror_projects)
