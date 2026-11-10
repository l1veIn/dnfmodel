"""Prepare whale keyarts, complete illustration overlays and a water-mirror buff.

No network, paid tasks, game writes or modifications of approved native sprites.
Generated art is sampled with explicit framing; original IMG pixels are never
used as paint. Package staging is performed separately by the shared packager.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from scipy.ndimage import map_coordinates

from buff_portrait import write_mov
from hero_cutin_video import key_magenta,clean_blue_hair_edges

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'output/whale_illustrations_v02'
BUFF = ROOT / 'output/whale_buff_v01'
CONFIG = ROOT / 'design/fatfish_whale_maid/illustrations_v02.json'
SCOPE = ROOT / 'output/validation/awakening_completion_2026-11-10/scope.json'
FALLBACK = ROOT / 'output/illustration_completion_2026-11-10/videos/whale_battle/attempt_02/frames'
ROLE = {'battle': 'battle', 'ashtarte': 'battle', 'elma': 'element',
        'elementalmaster': 'element', 'overmind': 'element', 'mado': 'witch',
        'witch': 'witch', 'geniewi': 'witch', 'summon': 'summon',
        'summoner': 'summon', 'eclipse': 'summon', 'enchantress': 'enchantress',
        'hecate': 'enchantress'}
FOCUS = {'battle': .42, 'element': .60, 'summon': .40, 'witch': .57, 'enchantress': .56}
SPECIAL_ROLES = {'avatarfinishcutscene':'battle','exticioncutscene':'battle',
                 'precenciatransform':'battle','mage_hecate':'enchantress'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def role_for(stem):
    if stem in SPECIAL_ROLES:
        return SPECIAL_ROLES[stem]
    for token in sorted(ROLE, key=len, reverse=True):
        if token in stem:
            return ROLE[token]
    return 'battle'


def checker(size):
    y, x = np.mgrid[:size[1], :size[0]]
    a = np.where(((x // 12 + y // 12) % 2)[..., None], np.array([41, 49, 61]), np.array([29, 36, 47]))
    return Image.fromarray(a.astype(np.uint8), 'RGB').convert('RGBA')


def contact(images, path, columns=3, cell=(360, 260)):
    rows = math.ceil(len(images) / columns)
    page = Image.new('RGB', (columns * cell[0], rows * cell[1]), '#17202f')
    draw = ImageDraw.Draw(page)
    for index, (name, image) in enumerate(images):
        tile = checker((cell[0], cell[1]-25))
        fitted = ImageOps.contain(image.convert('RGBA'), tile.size, Image.Resampling.LANCZOS)
        tile.alpha_composite(fitted, ((tile.width-fitted.width)//2, (tile.height-fitted.height)//2))
        x, y = index % columns * cell[0], index // columns * cell[1]
        page.paste(tile.convert('RGB'), (x, y+25)); draw.text((x+7, y+5), name, fill='#daefff')
    page.save(path, quality=94)


def prepare_static():
    scope = json.loads(SCOPE.read_text('utf-8'))['projects']['whale']
    art = {}
    for name in FOCUS:
        raw = ART / f'raw/{name}_keyart.png'
        image = key_magenta(Image.open(raw))
        target = ART / f'keyed/{name}.png'; target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target); art[name] = image
    rows, previews = [], []
    for row in scope['awakening']:
        if row['frames'] != 1:
            continue
        stem = Path(row['path']).stem; role = role_for(stem)
        size = tuple(row['frame_geometry'][0]['size'])
        image = ImageOps.fit(art[role], size, Image.Resampling.LANCZOS, centering=(FOCUS[role], .28))
        target = ART / f'static/{stem}/frame_0000.png'; target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target)
        rows.append({'source_npk': row['source_npk'], 'path': row['path'],
                     'frame_paths': [relative(target)], 'frame_mode': 'local',
                     'allow_geometry_change': False, 'role': role, 'category': 'awakening_static'})
        previews.append((stem, image))
    contact(previews, ART / 'static_contact.jpg')
    save(ART / 'static_manifest.json', {'overlays': rows, 'all_new_character_pixels': True,
                                      'approved_native_sha256': scope['base_npk_sha256']})
    return rows


def animation_source(role, allow_fallback, cfg):
    configured = cfg.get('animation_sources', {}).get(role)
    if configured:
        folder = (ROOT/configured).resolve()
        if not folder.is_relative_to(ROOT/'output') or not (folder/'manifest.json').is_file():
            raise ValueError('Configured animation source must have an existing output manifest')
        return folder, False
    preferred = ART / f'video/{role}/frames'
    if (preferred / 'manifest.json').is_file():
        return preferred, False
    # Root's successful recovery attempt is deliberately distinct from the
    # original uncertain journal, which this builder never reads or modifies.
    if role == 'battle' or allow_fallback:
        if not (FALLBACK / 'manifest.json').is_file():
            raise FileNotFoundError('Root-collected battle frames are not yet available')
        return FALLBACK, role != 'battle'
    raise FileNotFoundError(f'{role} video missing; collect/cut root-submitted clip or choose --fallback-battle')


def build_overlays(allow_fallback=False, preview=False, specials=False):
    static = [] if specials else prepare_static()
    config_path = (CONFIG.with_name('illustrations_v02_preview02.json') if specials else
                   CONFIG.with_name('illustrations_v02_preview.json') if preview else CONFIG)
    cfg = json.loads(CONFIG.read_text('utf-8'))
    if preview:
        cfg.update(output='output/fatfish_whale_maid_v02_preview',
                   npk_name='A_FatfishWhaleMaid_FMage_v02_preview.NPK',
                   title='鲸鱼娘 · 一觉九图与战法连续切入图 v02 预览')
    if specials:
        cfg.update(base_npk='output/fatfish_whale_maid_v02_preview/A_FatfishWhaleMaid_FMage_v02_preview.NPK',
                   output='output/fatfish_whale_maid_v02_preview02',
                   npk_name='A_FatfishWhaleMaid_FMage_v02_preview02.NPK',
                   title='鲸鱼娘 · 一觉与战法连续切入图 v02 预览02')
        cfg['protect_paths'] += ['output/fatfish_whale_maid_v02_preview',
                                 'output/whale_illustrations_v02/static',
                                 'output/whale_illustrations_v02/animated']
    scope = json.loads(SCOPE.read_text('utf-8'))['projects']['whale']
    overlays = list(static); records = []
    all_rows = [r for r in scope['awakening'] if r['frames'] > 1] + scope['cutin']
    rows = ([r for r in all_rows if Path(r['path']).stem in
             ('avatarfinishcutscene','exticioncutscene','precenciatransform')] if specials else
            [r for r in all_rows if Path(r['path']).stem in ('mage_battlemage_neo','mage_ashtarte')]
            if preview else all_rows)
    previews = []
    for row in rows:
        stem = Path(row['path']).stem; role = role_for(stem)
        source, fallback = animation_source(role, allow_fallback,cfg)
        frames = sorted(source.glob('frame_*.png'))
        if not frames:
            raise ValueError(f'No decoded frames in {source}')
        # A later full build must not overwrite PNGs signed into the published
        # partial preview. Keep its animated inputs in a separate directory.
        folder_name = 'animated_specials_v01' if specials else 'animated' if preview else 'animated_full'
        output = ART / f'{folder_name}/{stem}'
        output.mkdir(parents=True, exist_ok=True)
        count = row['frames']; hashes = []
        for k in range(count):
            index = round(k * (len(frames)-1) / max(1, count-1))
            image = Image.open(frames[index]).convert('RGBA')
            geometry = row['frame_geometry'][k]
            if geometry.get('link') is not None:
                # Shared packager retains the original link descriptor.
                size = (1067, 600)
            else:
                size = (geometry['cw'], geometry['ch'])
            # Constant five-percent safety margin across the entire clip. The
            # source movie itself crops the ahoge near its end; this keeps the
            # remaining drawing clear of new canvas edges, without pretending
            # to recover pixels that were not present in the movie.
            fitted = ImageOps.contain(image, (round(size[0]*.95),round(size[1]*.95)), Image.Resampling.LANCZOS)
            image = Image.new('RGBA',size)
            image.alpha_composite(fitted,((size[0]-fitted.width)//2,(size[1]-fitted.height)//2))
            yy, xx = np.mgrid[:size[1], :size[0]]
            phase = k / max(1, count-1)
            if stem == 'avatarfinishcutscene':
                # Fresh diagonal window over the real continuously moving
                # movie, never a static keyart pretending to be a video layer.
                # Follow the supplied movie's eye level as its camera pushes
                # in; the strip must not slice across half an iris mid-shot.
                center = size[1] * (.29 + .13 * phase)
                half = max(3, 85 * math.sin(math.pi*min(1, phase*1.1)))
                mask = np.clip((half-np.abs(yy-center+.05*(xx-size[0]/2)))/3, 0, 1)
            elif stem == 'precenciatransform':
                radius = .08 + .95 * math.sin(math.pi*min(phase*.92, .92))
                cx,cy = size[0]*(.355+.22*phase),size[1]*(.29+.13*phase)
                distance = np.abs((xx-cx)/(size[0]/2)) + np.abs((yy-cy)/(size[1]/2))
                mask = np.clip((radius-distance)*size[1]/4, 0, 1)
            else:
                mask = np.ones((size[1], size[0]), np.float32)
            a = np.array(image); a[..., 3] = np.round(a[..., 3]*mask).astype(np.uint8)
            a[a[..., 3] == 0, :3] = 0; image = Image.fromarray(a, 'RGBA')
            target = output / f'frame_{k:04d}.png'; image.save(target); hashes.append(sha(target))
            if k in (0,count//2,count-1):
                previews.append((f'{stem} {k:02d}',image))
        overlays.append({'source_npk': row['source_npk'], 'path': row['path'],
                         'frames_dir': relative(output), 'frame_mode': 'canvas',
                         'allow_geometry_change': True, 'fit_to_canvas': False,
                         'preserve_empty_frames': True, 'role': role, 'category': row['category']})
        records.append({'path': row['path'], 'frames': count, 'source_frames': relative(source),
                        'source_role': 'battle' if fallback else role, 'fallback': fallback,
                        'frame_sha256': hashes, 'official_character_pixels_retained': False})
    cfg['overlays'] = overlays
    cfg['base_sha256'] = sha(ROOT/cfg['base_npk'])
    pending = [{'path':r['path'],'frames':r['frames'],'category':r['category'],
                'reason':'Dedicated profession video or special-layer adaptation pending; not included in preview'}
               for r in all_rows if r not in rows and
               (not specials or Path(r['path']).stem not in ('mage_ashtarte','mage_battlemage_neo'))]
    cfg['pending_overlays'] = pending
    save(config_path, cfg)
    contact(previews, ART / ('animated_specials_contact.jpg' if specials else 'animated_preview_contact.jpg' if preview else 'animated_contact.jpg'),columns=3)
    save(ART / ('overlay_specials_manifest.json' if specials else 'overlay_preview_manifest.json' if preview else 'overlay_art_manifest.json'),
         {'paths': len(overlays), 'static_paths': len(static), 'animated_paths': len(records),
          'animations': records, 'pending':pending,'installed': False,
          'limitation':'Battle movie ends with source-level headband/ahoge crop; constant5% canvas margin does not recreate missing pixels'})
    return {'paths': len(overlays), 'static_paths': len(static), 'animated_paths': len(records),
            'fallback_paths': [r['path'] for r in records if r['fallback']]}


def alpha_clean(image, threshold):
    a = np.asarray(image.convert('RGBA')).copy()
    alpha = a[..., 3].astype(np.float32)
    alpha = np.clip((alpha-threshold)/(253-threshold)*255, 0, 255)
    a[..., 3] = np.round(alpha).astype(np.uint8); a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, 'RGBA')


def closeup_canvas(image,index,face_width,size=(1067,600)):
    """Reframe the real movie by reviewed eye/face landmarks, uniformly.

    The early medium shot has a roughly96px face, growing to184px in the
    movie's late closeup. A target350px face keeps character expression legible
    in the entire1067px canvas instead of inspecting a magnified QA crop.
    """
    keys=[0,30,40,50,60,72]
    eye_x=float(np.interp(index,keys,[385,410,435,475,565,610]))
    eye_y=float(np.interp(index,keys,[168,168,174,192,221,246]))
    width=float(np.interp(index,keys,[96,96,98,118,154,184]))
    scale=face_width/width; target=(560,268)
    # Landmarks are in the shared1067x600 review canvas. Sampling the native
    # movie directly avoids first shrinking its face and then enlarging it.
    sx,sy=image.width/1067,image.height/600
    affine=(sx/scale,0,sx*(eye_x-target[0]/scale),0,sy/scale,sy*(eye_y-target[1]/scale))
    page=image.transform(size,Image.Transform.AFFINE,affine,Image.Resampling.BICUBIC,fillcolor=0)
    return page,{'source_eye':[eye_x,eye_y],'source_face_width_estimate':width,
                 'uniform_scale':scale,'target_eye':list(target),'target_face_width':face_width,
                 'inverse_affine':list(affine)}


def build_closeups():
    import av
    cfg=json.loads((CONFIG.with_name('illustrations_v02_preview02.json')).read_text('utf-8'))
    cfg.update(base_npk='output/fatfish_whale_maid_v02_preview02/A_FatfishWhaleMaid_FMage_v02_preview02.NPK',
               output='output/fatfish_whale_maid_v02_preview03',
               npk_name='A_FatfishWhaleMaid_FMage_v02_preview03.NPK',
               title='鲸鱼娘 · 水镜近景构图 v02 预览03')
    cfg['base_sha256']=sha(ROOT/cfg['base_npk'])
    cfg['protect_paths']+=['output/fatfish_whale_maid_v02_preview02',
                           'output/whale_illustrations_v02/animated_specials_v01']
    scope=json.loads(SCOPE.read_text('utf-8'))['projects']['whale']
    source,_=animation_source('battle',False,cfg);frames=sorted(source.glob('frame_*.png'))
    rows=[r for r in scope['cutin'] if Path(r['path']).stem in ('avatarfinishcutscene','precenciatransform')]
    key_manifest=json.loads((source/'manifest.json').read_text('utf-8'))
    movie=FALLBACK.parent/'video.mp4'
    if sha(movie)!=key_manifest['source_video_sha256']:
        raise ValueError('Native movie must match the independently reviewed chroma-key source')
    source_indices=key_manifest['source_indices']
    wanted={source_indices[round(k*(len(frames)-1)/max(1,row['frames']-1))]
            for row in rows for k in range(row['frames'])}
    native={}
    with av.open(str(movie)) as container:
        for j,frame in enumerate(container.decode(video=0)):
            if j in wanted:native[j]=key_magenta(frame.to_image())
    if set(native)!=wanted:raise ValueError('Native movie frame selection incomplete')
    overlays=[];reports=[];review=[]
    for row in rows:
        stem=Path(row['path']).stem;folder=ART/f'animated_specials_v02_closeup/{stem}'
        folder.mkdir(parents=True,exist_ok=True);metrics=[];count=row['frames']
        for k in range(count):
            index=round(k*(len(frames)-1)/max(1,count-1));phase=k/max(1,count-1)
            native_index=source_indices[index]
            image,camera=closeup_canvas(native[native_index],index,
                                       350 if stem=='avatarfinishcutscene' else 330)
            image=clean_blue_hair_edges(image)
            yy,xx=np.mgrid[:600,:1067];cx,cy=camera['target_eye']
            if stem=='avatarfinishcutscene':
                opening=min(1,phase/.17,(1-phase)/.17)
                opening=max(0,opening);opening=opening*opening*(3-2*opening)
                half=max(3,120*opening)
                mask=np.clip((half-np.abs(yy-cy-.10*(xx-cx)))/3,0,1)
            else:
                radius=.085+.95*math.sin(math.pi*min(phase*.92,.92))
                distance=np.abs((xx-cx)/(1067/2))+np.abs((yy-cy)/(600/2))
                mask=np.clip((radius-distance)*600/4,0,1)
            a=np.array(image);a[...,3]=np.round(a[...,3]*mask).astype(np.uint8)
            a[a[...,3]==0,:3]=0;image=Image.fromarray(a,'RGBA')
            path=folder/f'frame_{k:04d}.png';image.save(path)
            metrics.append({'frame':k,'source_frame':index,'native_video_frame':native_index,
                            'native_source_size':list(native[native_index].size),
                            'camera':camera,'sha256':sha(path),
                            'alpha_range':[int(a[...,3].min()),int(a[...,3].max())]})
            if k in (0,5,count//2,count-6,count-1):
                sample=ART/f'closeup_review/{stem}_{k:02d}_whole_canvas.png'
                sample.parent.mkdir(exist_ok=True);image.save(sample)
                review.append((f'{stem} {k:02d}',image))
        overlays.append({'source_npk':row['source_npk'],'path':row['path'],'frames_dir':relative(folder),
                         'frame_mode':'canvas','allow_geometry_change':True,'fit_to_canvas':False,
                         'preserve_empty_frames':True,'role':'battle','category':row['category']})
        reports.append({'path':row['path'],'frames':count,'source_frames':relative(source),
                        'target_face_width':350 if stem=='avatarfinishcutscene' else 330,
                        'all_frames':metrics})
    cfg['overlays']=overlays
    save(CONFIG.with_name('illustrations_v02_preview03.json'),cfg)
    save(ART/'closeup_review/manifest.json',{'layers':reports,'stage_or_package':False,
          'source_movie':relative(movie),'source_movie_sha256':sha(movie),
          'whole_canvas_review_required':True,'note':'Real movie eye/face reframing precedes window mask; no magnified QA crop stands in for whole canvas.'})
    contact(review,ART/'closeup_review/whole_canvas_contact.jpg',columns=5,cell=(426,265))
    return {'config':'design/fatfish_whale_maid/illustrations_v02_preview03.json',
             'paths':2,'frames':sum(r['frames'] for r in reports),'stage_or_package':False,
             'whole_canvas_review':'output/whale_illustrations_v02/closeup_review'}


def build_buff(config_path=None):
    cfg_path = ROOT / (config_path or 'design/fatfish_whale_maid/buff_v01.json')
    cfg = json.loads(cfg_path.read_text('utf-8')); out = ROOT / cfg['output']
    if (out / 'encoding_report.json').exists():
        raise FileExistsError('Encoded buff is frozen; choose a new version')
    out.mkdir(parents=True, exist_ok=True); (out / 'frames').mkdir(exist_ok=True)
    size = (470, 668); w, h = size
    portrait = alpha_clean(Image.open(BUFF / 'raw/portrait.png'), 6)
    closed = alpha_clean(Image.open(BUFF / 'raw/blink_closed.png'), 6)
    halfway = alpha_clean(Image.open(ROOT/cfg['blink_half']),6) if cfg.get('blink_half') else None
    fx = alpha_clean(Image.open(BUFF / 'raw/water_whale_fx.png'), 65)
    # One fixed uniform actor mapping for all 19 frames. Only selected hair and
    # skirt peripheries have a small root-pinned displacement; face/body stay.
    portrait = portrait.resize((460, 690), Image.Resampling.LANCZOS)
    closed = closed.resize(portrait.size, Image.Resampling.LANCZOS)
    if halfway is not None:
        halfway = halfway.resize(portrait.size,Image.Resampling.LANCZOS)
    base = Image.new('RGBA', size); base.alpha_composite(portrait, (8, 8))
    blink = Image.new('RGBA', size); blink.alpha_composite(closed, (8, 8))
    half_blink = Image.new('RGBA',size)
    if halfway is not None:
        half_blink.alpha_composite(halfway,(8,8))
    eye_mask = Image.new('L', size); draw = ImageDraw.Draw(eye_mask)
    for box in [(257, 138, 316, 178), (314, 135, 360, 174)]:
        draw.rounded_rectangle(box, radius=5, fill=255)
    eye_mask = eye_mask.filter(ImageFilter.GaussianBlur(1.5))
    # The character is displayed through a slanted water-mirror window.
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    left = 31 + .075*yy; right = 443 - .025*yy
    band = np.minimum(np.clip((xx-left)/5, 0, 1), np.clip((right-xx)/5, 0, 1))
    band *= np.clip((h-yy)/45, 0, 1)
    hair_weight = np.clip((242-xx)/90, 0, 1)*np.clip((yy-165)/120, 0, 1)*np.clip((565-yy)/100, 0, 1)
    skirt_weight = np.clip((yy-500)/100, 0, 1)*np.clip((h-yy)/25, 0, 1)
    hair_weight[(xx > 245) & (yy < 260)] = 0
    frames, metrics = [], []
    blink_weights = {10:.55, 11:1., 12:.55}
    water = ImageOps.fit(fx, (455, 683), Image.Resampling.LANCZOS)
    for k in range(19):
        phase = k/18; wave = math.sin(2*math.pi*phase)
        actor = base.copy(); blink_weight = blink_weights.get(k, 0)
        if blink_weight:
            if halfway is not None:
                # A true separately drawn half-open eyelid, never a crossfade
                # between the open iris and closed eyelash line.
                actor = Image.composite(half_blink if k in (10,12) else blink,actor,eye_mask)
            else:
                actor = Image.composite(blink, actor, eye_mask.point(lambda v: round(v*blink_weight)))
        a = np.asarray(actor)
        dx = 1.8*wave*hair_weight + .8*math.sin(2*math.pi*phase+.4)*skirt_weight
        dy = .65*wave*hair_weight
        coords = [yy-dy, xx-dx]
        warped = np.stack([map_coordinates(a[..., c], coords, order=1, mode='constant', cval=0) for c in range(4)], axis=2).astype(np.uint8)
        # Exact original face pixels outside the tiny eye blend remain fixed.
        warped[55:258,245:410] = a[55:258,245:410]
        reveal = np.clip((k/5*785-(xx+.50*yy))/12, 0, 1)
        if k >= 5:
            reveal = np.ones_like(reveal)
        warped[..., 3] = np.round(warped[..., 3]*band*reveal).astype(np.uint8)
        warped[warped[...,3] == 0,:3] = 0
        page = Image.new('RGBA', size)
        # A translucent ocean pane supports the portrait, rather than opaque
        # photographic scenery. Its front travels diagonally across the band.
        pane_alpha = np.round(34*band*reveal).astype(np.uint8)
        pane = np.zeros((h,w,4), np.uint8); pane[...,:3] = [5,39,94]; pane[...,3] = pane_alpha
        page.alpha_composite(Image.fromarray(pane,'RGBA'))
        whale = Image.new('RGBA', size)
        whale.alpha_composite(water, (round(-6+18*math.sin(math.pi*phase)), round(7-22*phase)))
        whale_a = np.array(whale); whale_a[...,3] = (whale_a[...,3].astype(float)*(.9 if k < 5 else .42)).astype(np.uint8)
        page.alpha_composite(Image.fromarray(whale_a,'RGBA'))
        page.alpha_composite(Image.fromarray(warped,'RGBA'))
        # Refractive diagonal slash + ripples. The slash crosses only during
        # entry, then leaves small asymmetric water rings below the face.
        layer = Image.new('RGBA', size); draw = ImageDraw.Draw(layer)
        if k <= 5:
            line = k/5*785
            points = [(round(line-.5*y), y) for y in range(5,h-5,5)]
            draw.line(points, fill=(74,188,255,100), width=12)
            draw.line(points, fill=(220,250,255,255), width=3)
        for ring in range(3):
            travel = (phase*1.2+ring*.28)%1
            cx, cy = 185+ring*65, 495+ring*37
            rx, ry = 20+travel*89, 7+travel*23
            opacity = round(190*(1-travel))
            draw.arc((cx-rx,cy-ry,cx+rx,cy+ry), 10+ring*35, 305+ring*20,
                     fill=(123,220,255,opacity), width=2)
        # Fixed tiny luminous droplet keeps both alpha extremes in early frame.
        for j in range(13):
            px = 55+(j*77+round(phase*34))%365
            py = 64+(j*113-round(phase*65))%560
            if 245 < px < 410 and 55 < py < 258:
                continue
            r = 1 if j%3 else 2
            draw.ellipse((px-r,py-r,px+r,py+r),fill=(189,240,255,255 if j == 0 else 120))
        page.alpha_composite(layer)
        target = out / f'frames/frame_{k:04d}.png'; page.save(target); frames.append(page)
        alpha = np.asarray(page)[...,3]
        metrics.append({'frame':k,'time_seconds':k/15,
                        'blink_state':'half' if k in (10,12) else 'closed' if k == 11 else 'open',
                        'eye_patch_opacity':1 if blink_weight and halfway is not None else blink_weight,
                        'character_transform':{'x':0,'y':0,'scale':1},
                        'local_material_max_displacement_px':float(np.hypot(dx,dy).max()),
                        'alpha_range':[int(alpha.min()),int(alpha.max())]})
    durations = [round((k+1)*1000/15)-round(k*1000/15) for k in range(19)]
    frames[0].save(out/'preview.webp', save_all=True, append_images=frames[1:], lossless=True,
                   duration=durations,loop=0,exact=True)
    sheet=Image.new('RGBA',(470*4,668*5))
    for k,frame in enumerate(frames): sheet.alpha_composite(frame,(k%4*470,k//4*668))
    sheet.save(out/'sheet.png')
    contact([(f'{k:02d}',im) for k,im in enumerate(frames)],out/'contact.jpg',columns=5,cell=(188,282))
    intermediate=write_mov(frames,out/'portrait_rgba.mov',15)
    shutil.copyfile(BUFF/'raw/portrait.png',out/'source.png')
    baseline = json.loads((ROOT/'kb/curated/buff_videos.json').read_text('utf-8'))
    by_target = {f"{r['folder']}/{r['file']}":r for r in baseline['files']}
    targets=[]
    for target in cfg['targets']:
        if by_target[target]['profession'] != cfg['profession']:
            raise ValueError('Buff target does not match whale profession')
        targets.append({'relative_to_video_character':target,'official_sha256':by_target[target]['sha256']})
    manifest={'title':cfg['title'],'frames':19,'size':[470,668],'fps':15,
              'duration_seconds':19/15,'preview_duration_ms':sum(durations),
              'source_reference':cfg['reference'],'source_raw_sha256':sha(BUFF/'raw/portrait.png'),
              'source_illustration':'source.png',
              'source_size':[1024,1536],'frame_sha256':[sha(out/f'frames/frame_{k:04d}.png') for k in range(19)],
              'frame_metrics':metrics,'sheet_sha256':sha(out/'sheet.png'),'sheet_size':list(sheet.size),
              'source_mov':'portrait_rgba.mov','mov_roundtrip':intermediate,
              'transparent':True,'alpha':True,'status':'prepared_for_review_not_bink_encoded','visual_review':'pending',
              'targets':targets,'license_note':cfg['license_note'],
              'installed':False,'ingame_verified':False,
              'generation':cfg['generation'],
              'art_sources':{str(path.relative_to(ROOT).as_posix()):sha(path) for path in
                             [BUFF/'raw/portrait.png',BUFF/'raw/blink_closed.png',BUFF/'raw/water_whale_fx.png']+
                             ([ROOT/cfg['blink_half']] if cfg.get('blink_half') else [])},
              'warnings':[],
              'composition':{'mode':'diagonal_water_mirror_closeup','intentional_canvas_crop':True},
              'bink_encoding':{'format':'Bink 1','fps_override':15,'alpha':'include straight alpha','audio':False,'source':'frames/frame_0000.png (numbered sequence)'},
              'staged_recipe':{'config_sha256':sha(cfg_path),'script_sha256':sha(__file__)}}
    save(out/'manifest.json',manifest)
    return {'frames':19,'preview':relative(out/'preview.webp'),'contact':relative(out/'contact.jpg'),
            'alpha_ranges':[m['alpha_range'] for m in metrics]}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['static','overlays','preview','specials','closeups','buff'])
    parser.add_argument('--buff-config')
    parser.add_argument('--fallback-battle',action='store_true'); args=parser.parse_args()
    result = (prepare_static() if args.action == 'static' else build_buff(args.buff_config) if args.action == 'buff'
              else build_closeups() if args.action=='closeups' else build_overlays(args.fallback_battle,args.action=='preview',args.action=='specials'))
    print(json.dumps(result,ensure_ascii=False,indent=2))
