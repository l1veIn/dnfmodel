"""Build a center-opening buff cut-in; never writes game files.

The frozen v05 character stays at its original coordinates. Only its alpha
matte opens horizontally. Rail texture and exact geometric emblems are separate
layers, so face/hand pixels and the existing local motion remain intact.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageDraw

from buff_portrait import write_mov
from build_buff_band import ROOT, character_layer, digest, prepare_fx, resolve, rgba, snapshot, write_json

CONFIG = ROOT / 'design/claude_gunner/buff_v07.json'


def reveal_mask(size, center, half_width, feather):
    """One symmetric matte shared by character, backing and ornament clipping."""
    width, height = size
    x = np.arange(width, dtype=np.float32)
    value = np.clip((half_width - np.abs(x - center)) / feather, 0, 1)
    return np.broadcast_to(value, (height, width)).copy()


def protected_mask(cfg):
    mask = np.zeros((cfg['height'], cfg['width']), dtype=bool)
    for left, top, right, bottom in cfg['effects']['protected_foreground_boxes']:
        mask[top:bottom, left:right] = True
    return mask


def stamp(canvas, motif, center, width, opacity, angle=0):
    if motif is None or width < 1 or opacity <= 0:
        return
    height = max(1, round(motif.height * width / motif.width))
    image = motif.resize((max(1, round(width)), height), Image.Resampling.LANCZOS)
    if angle:
        image = image.rotate(angle, Image.Resampling.BICUBIC, expand=True)
    array = np.asarray(image).copy()
    array[...,3] = np.rint(array[...,3] * min(1, opacity / 255)).astype(np.uint8)
    image = rgba(array)
    canvas.alpha_composite(image, (round(center[0] - image.width / 2), round(center[1] - image.height / 2)))


def motif_layers(cfg, motifs, k, left, right, mask):
    size = cfg['width'], cfg['height']
    back = Image.new('RGBA', size)
    front = Image.new('RGBA', size)
    effects = cfg['effects']
    # A single lower-torso pulse, followed by a restrained split into six
    # orange/gold fragments. These elements never touch face or hand interiors.
    stamp(front, motifs.get('claude'), effects['starburst_center'],
          effects['starburst_sizes'][k], effects['starburst_alpha'][k], angle=k*3)
    if k >= 5:
        age = k - 5
        particle_alpha = max(0, effects['particle_alpha_start'] - age * effects['particle_alpha_decay'])
        for index, angle in enumerate((12,68,124,192,248,304)):
            radius = 40 + age * 13
            theta = math.radians(angle)
            cx = effects['starburst_center'][0] + math.cos(theta) * radius
            cy = effects['starburst_center'][1] + math.sin(theta) * radius * .72
            stamp(front, motifs.get('claude'), (cx,cy), 8 + index % 3*2, particle_alpha, angle=age*8)
    # The literal A + backslash is a small lower-band signature, not lettering
    # across the portrait. Its gradual appearance follows the panel opening.
    stamp(front, motifs.get('a_slash'), effects['a_slash_center'],
          effects['a_slash_width'], effects['a_slash_alpha'][k])
    if k >= 4:
        for index, (cx,cy) in enumerate(((left+9,94),(right-9,555),(left+7,497))):
            opacity = effects['edge_star_alpha'] + effects['edge_star_alpha_variation']*math.sin(k*.7+index*1.9)
            stamp(front, motifs.get('claude'), (cx,cy), effects['edge_star_sizes'][index], opacity, angle=k*2)
    array = np.asarray(front).copy()
    array[...,3] = np.rint(array[...,3] * mask).astype(np.uint8)
    array[protected_mask(cfg),3] = 0
    return back, rgba(array)


def effect_layers(cfg, fx_source, motifs, k, mask):
    width, height = cfg['width'], cfg['height']
    center = cfg['band']['center_x']
    half = cfg['motion']['reveal_half_widths'][k]
    left, right = center-half, center+half
    y,x = np.mgrid[:height,:width].astype(np.float32)
    margin = cfg['band']['effect_margin']
    allowed = (x >= left-margin) & (x <= right+margin)
    side = np.maximum(np.exp(-((x-left)/18)**2),np.exp(-((x-right)/18)**2))
    backing = np.zeros((height,width,4),dtype=np.float32)
    backing[...,:3] = (21,13,12)
    backing[...,3] = mask * cfg['band']['backing_alpha']
    background = rgba(backing)
    fx = prepare_fx(fx_source,(width,height),left,right)
    top = min(fx.height-height,round(k*cfg['effects']['rail_scroll_px']))
    texture = np.asarray(fx.crop((0,top,width,top+height))).astype(np.float32)
    texture[...,3] *= side * allowed * (.64+.10*math.sin(k*.62))
    rail = rgba(texture)
    draw = ImageDraw.Draw(rail)
    draw.line((left,0,left,height-1), fill=(255,198,83,255),width=1)
    draw.line((right,0,right,height-1), fill=(255,235,184,255),width=1)
    # Both rails live behind the portrait while crossing the face at opening.
    # The foreground contributes only softer edge flecks, with protected zones.
    background.alpha_composite(rail)
    front = texture.copy()
    front[...,3] *= .30
    front[protected_mask(cfg),3] = 0
    foreground = rgba(front)
    motif_back,motif_front = motif_layers(cfg,motifs,k,left,right,mask)
    background.alpha_composite(motif_back)
    foreground.alpha_composite(motif_front)
    return background,foreground,top


def validate_config(cfg, sources):
    if (cfg['width'],cfg['height'],cfg['frames'],cfg['fps']) != (470,668,19,15):
        raise ValueError('Reviewed preset is 19 frames, 470x668 at 15fps')
    motion=cfg['motion']
    if motion.get('scale') != 1 or motion.get('x_offset') != 0 or motion.get('y_offsets') != [0]*19:
        raise ValueError('Character must stay at x=0,y=0,scale=1')
    halves=motion['reveal_half_widths']
    if len(halves)!=19 or any(type(v) is not int for v in halves):
        raise ValueError('Nineteen integer opening widths required')
    if halves != sorted(halves) or halves[-1] != 165 or halves[5:] != [165]*14:
        raise ValueError('Opening must expand monotonically and settle by frame 5')
    if cfg['band']['center_x'] != 235 or cfg['band']['edges'] != [70,400]:
        raise ValueError('Reviewed band edges are 70/400 around x235')
    if len(sources)!=19 or any(im.size != (470,668) for im in sources):
        raise ValueError('Frozen portrait dimensions/frame count changed')


def render(cfg, sources, fx_source, motifs):
    validate_config(cfg,sources)
    size=cfg['width'],cfg['height']
    frames,metrics,characters,backgrounds,foregrounds=[],[],[],[],[]
    for k,source in enumerate(sources):
        half=cfg['motion']['reveal_half_widths'][k]
        center=cfg['band']['center_x']
        mask=reveal_mask(size,center,half,cfg['band']['feather_px'])
        character=character_layer(source,0,mask,cfg['band']['source_bottom_fade_px'])
        background,foreground,top=effect_layers(cfg,fx_source,motifs,k,mask)
        final=background.copy()
        final.alpha_composite(character)
        final.alpha_composite(foreground)
        final=rgba(np.asarray(final))
        array=np.asarray(final)
        alpha=array[...,3]
        if alpha.min()!=0 or alpha.max()!=255:
            raise ValueError('Each frame requires transparent margin and opaque rail cores')
        yy,xx=np.nonzero(alpha>8)
        metrics.append(dict(frame=k,time_seconds=k/15,source_frame=k,blink=cfg['blink_sequence'][k],
                            character_transform={'x':0,'y':0,'scale':1},
                            reveal_half_width=half,reveal_edges=[center-half,center+half],
                            rail_x=[center-half,center+half],rail_texture_y=top,
                            alpha_bbox=list(final.getbbox()),alpha_range=[int(alpha.min()),int(alpha.max())],
                            effective_width_gt8=int(xx.max()-xx.min()+1),
                            foreground_protected_alpha_max=int(np.asarray(foreground)[protected_mask(cfg),3].max()),
                            starburst_alpha=cfg['effects']['starburst_alpha'][k],
                            a_slash_alpha=cfg['effects']['a_slash_alpha'][k]))
        frames.append(final);characters.append(character);backgrounds.append(background);foregrounds.append(foreground)
    return frames,metrics,characters,backgrounds,foregrounds


def game_snapshot(cfg):
    game=Path('C:/WeGameApps/地下城与勇士：创新世纪')
    files=[game/'Video/Character'/name for name in cfg['targets']]
    files.extend(sorted((game/'ImagePacks2').glob('A_Claude_FGunner*.NPK')))
    return {str(path):digest(path) for path in files if path.is_file()}


def build(config_path=CONFIG, replace_staged=False):
    cfg=json.loads(config_path.read_text('utf-8'))
    output=resolve(cfg['output'])
    if not output.is_relative_to(ROOT/'output/claude_buff_v07'):
        raise ValueError('v07 may write only its own output tree')
    if (output/'manifest.json').exists():
        old=json.loads((output/'manifest.json').read_text('utf-8'))
        if not replace_staged or old.get('status')!='staged_for_visual_review' or (output/'portrait.bik').exists():
            raise FileExistsError('Reviewed/frozen output exists; choose a new version')
    parent=resolve(cfg['source_manifest'])
    parent_manifest=json.loads(parent.read_text('utf-8'))
    frozen_trees={str(folder.relative_to(ROOT)).replace('\\','/'):snapshot(folder)
                  for folder in (parent.parent,ROOT/'output/claude_buff_v06/preview')}
    game_before=game_snapshot(cfg)
    sources=[Image.open(parent.parent/f'frames/frame_{k:04d}.png').convert('RGBA') for k in range(19)]
    for k,expected in enumerate(parent_manifest['frame_sha256']):
        if digest(parent.parent/f'frames/frame_{k:04d}.png')!=expected:
            raise ValueError('Frozen v05 source frame changed')
    if cfg['blink_sequence'] != [m['blink'] for m in parent_manifest['frame_metrics']]:
        raise ValueError('Blink labels must match the frozen character frames')
    fx_path=resolve(cfg['fx_source'])
    motifs={name:Image.open(resolve(path)).convert('RGBA') if resolve(path).is_file() else None
            for name,path in cfg['effects']['motifs'].items()}
    complete=all(motif is not None for motif in motifs.values())
    frames,metrics,characters,backgrounds,foregrounds=render(cfg,sources,Image.open(fx_path),motifs)
    output.mkdir(parents=True,exist_ok=True)
    for sub in ('frames','layers/character','layers/background','layers/foreground'):
        (output/sub).mkdir(parents=True,exist_ok=True)
    for k,frame in enumerate(frames):
        frame.save(output/f'frames/frame_{k:04d}.png')
        characters[k].save(output/f'layers/character/frame_{k:04d}.png')
        backgrounds[k].save(output/f'layers/background/frame_{k:04d}.png')
        foregrounds[k].save(output/f'layers/foreground/frame_{k:04d}.png')
    source_illustration=parent.parent/parent_manifest['source_illustration']
    shutil.copyfile(source_illustration,output/'source.png')
    durations=[round((k+1)*1000/15)-round(k*1000/15) for k in range(19)]
    frames[0].save(output/'preview.webp',save_all=True,append_images=frames[1:],lossless=True,exact=True,duration=durations,loop=0)
    sheet=Image.new('RGBA',(470*4,668*5))
    contact=Image.new('RGB',(188*4,285*5),'#252d3a')
    draw=ImageDraw.Draw(contact)
    for k,frame in enumerate(frames):
        sheet.alpha_composite(frame,(k%4*470,k//4*668))
        part=frame.resize((188,267),Image.Resampling.LANCZOS)
        at=(k%4*188,k//4*285+18)
        contact.paste(part,at,part)
        draw.text((at[0]+5,at[1]-14),f'k{k} w{metrics[k]["reveal_half_width"]*2} {metrics[k]["blink"]}',fill='white')
    sheet.save(output/'sheet.png');contact.save(output/'contact.jpg',quality=95)
    mov=write_mov(frames,output/'portrait_rgba.mov',15)
    if any(snapshot(resolve(folder))!=before for folder,before in frozen_trees.items()):
        raise ValueError('A frozen v05/v06 input tree changed during export')
    if game_before != game_snapshot(cfg):
        raise ValueError('Game files changed during export')
    proof=dict(frozen_trees=frozen_trees,game_files=game_before,source_unchanged=True,
               character_transform={'x':0,'y':0,'scale':1},portrait_globally_stationary=True,
               independent_local_motion_retained=True,motifs_complete=complete,
               single_play=True,seamless_loop_claimed=False,mov_roundtrip=mov)
    write_json(output/'center_validation.json',proof)
    manifest=dict(title=cfg['title'],frames=19,size=[470,668],fps=15,duration_seconds=19/15,
                  preview_duration_ms=sum(durations),source_reference=cfg['reference'],source_illustration='source.png',
                  source_raw_sha256=digest(source_illustration),source_size=list(Image.open(source_illustration).size),
                  source_manifest=cfg['source_manifest'],source_manifest_sha256=digest(parent),
                  source_frame_sha256=parent_manifest['frame_sha256'],generation=cfg['generation'],
                  fx_source=cfg['fx_source'],fx_sha256=digest(fx_path),
                  motif_sources={name:{'path':path,'sha256':digest(resolve(path)) if resolve(path).is_file() else None}
                                 for name,path in cfg['effects']['motifs'].items()},
                  motifs_complete=complete,
                  staged_recipe={'config_sha256':digest(config_path),'script_sha256':digest(Path(__file__)),
                                 'helper_script_sha256':digest(ROOT/'scripts/build_buff_band.py')},
                  sheet_sha256=digest(output/'sheet.png'),sheet_size=list(sheet.size),
                  frame_sha256=[digest(output/f'frames/frame_{k:04d}.png') for k in range(19)],
                  frame_metrics=metrics,mov_roundtrip=mov,targets=cfg['targets'],installed=False,
                  status='staged_for_visual_review',warnings=[] if complete else ['Design motifs missing; stage only, cannot freeze'],
                  composition={'mode':'center_opening_vertical_cut_in','band_edges':cfg['band']['edges'],
                               'opening_center_x':235,'opening_complete_frame':5,'rails_follow_reveal':True,
                               'character_crop_intentional':True,'background_alpha':cfg['band']['backing_alpha']},
                  motion_limitations='Single-play center opening. Character has no global x/y movement or scale change. Frozen local blink/hair/cloth motion retained. No loop closure or in-game playback claim.',
                  license_note=cfg['license_note'],
                  bink_encoding={'format':'Bink 1','fps_override':15,'alpha':'include straight alpha','audio':False})
    write_json(output/'manifest.json',manifest)
    print(json.dumps({'output':str(output.relative_to(ROOT)),'frames':19,'motifs_complete':complete,'installed':False},ensure_ascii=False))
    return manifest


def freeze(config_path=CONFIG):
    """Freeze exact staged artifacts after root's visual review; no rerender."""
    cfg=json.loads(config_path.read_text('utf-8'))
    output=resolve(cfg['output']);path=output/'manifest.json'
    manifest=json.loads(path.read_text('utf-8'))
    if manifest.get('status')!='staged_for_visual_review' or (output/'portrait.bik').exists():
        raise ValueError('Only the unencoded reviewed stage may be frozen')
    if not manifest.get('motifs_complete'):
        raise ValueError('Both exact design motifs are required before freezing')
    staged_recipe={'config_sha256':digest(config_path),'script_sha256':digest(Path(__file__)),
                   'helper_script_sha256':digest(ROOT/'scripts/build_buff_band.py')}
    if staged_recipe != manifest.get('staged_recipe'):
        raise ValueError('Build config/script changed after the reviewed stage; rerender first')
    for k,expected in enumerate(manifest['frame_sha256']):
        if digest(output/f'frames/frame_{k:04d}.png')!=expected:
            raise ValueError('Staged frame changed after review')
    if digest(resolve(cfg['fx_source']))!=manifest['fx_sha256'] or digest(resolve(cfg['source_manifest']))!=manifest['source_manifest_sha256']:
        raise ValueError('Stage source changed after review')
    for name,asset in manifest['motif_sources'].items():
        if cfg['effects']['motifs'].get(name)!=asset['path'] or digest(resolve(asset['path']))!=asset['sha256']:
            raise ValueError('Design motif changed after review')
    proof=json.loads((output/'center_validation.json').read_text('utf-8'))
    if any(snapshot(resolve(folder))!=before for folder,before in proof['frozen_trees'].items()):
        raise ValueError('Frozen v05/v06 inputs changed')
    if game_snapshot(cfg)!=proof['game_files']:
        raise ValueError('Game files changed since stage')
    manifest['status']='prepared_for_review_not_bink_encoded'
    manifest['recipe']={'config':str(config_path.resolve().relative_to(ROOT)).replace('\\','/'),
                        'config_sha256':digest(config_path),'script':'scripts/build_buff_center.py',
                        'script_sha256':digest(Path(__file__)),
                        'helper_script':'scripts/build_buff_band.py','helper_script_sha256':digest(ROOT/'scripts/build_buff_band.py')}
    write_json(path,manifest)
    print(json.dumps({'frozen':True,'manifest_sha256':digest(path),'frames':19,'installed':False}))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config',type=Path,nargs='?',default=CONFIG)
    parser.add_argument('--replace-staged',action='store_true')
    parser.add_argument('--freeze',action='store_true',help='Freeze after visual review; no rendering')
    args=parser.parse_args()
    freeze(args.config) if args.freeze else build(args.config,args.replace_staged)
