"""Stage explicit portrait/cutin IMGs, then package those signed bytes.

The tool never generates images, creates video tasks, installs patches or
launches/closes the game. Existing base payloads outside overlays are retained.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from dnf_resources import ImgArchive, read_npk, write_v2
from gunner_props_build import write_shared_npk
from survey_gunner_effects import reader

ROOT=Path(__file__).resolve().parents[1]
GAME=Path('C:/WeGameApps/地下城与勇士：创新世纪')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def resolve(value,exists=True):
    path=Path(value)
    return (path if path.is_absolute() else ROOT/path).resolve(strict=exists)


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def meta(frame):
    if 'link' in frame:
        return {'link':frame['link']}
    return {'x':frame['x'],'y':frame['y'],
            'canvas_width':frame.get('cw',frame.get('canvas_width')),
            'canvas_height':frame.get('ch',frame.get('canvas_height'))}


def shape(frame):
    return frame.get('w',frame.get('width')),frame.get('h',frame.get('height'))


def canvas(frame):
    m=meta(frame)
    return m['canvas_width'],m['canvas_height']


def image_at(img,index):
    image=img.image(index)
    return image.convert('RGBA') if image is not None else Image.new('RGBA',shape(img.resolve(index)))


def payloads(npk):
    raw=Path(npk).read_bytes(); rows=read_npk(npk)
    if len({r['path'] for r in rows})!=len(rows):
        raise ValueError('NPK contains duplicate IMG paths')
    return rows,{r['path']:raw[r['offset']:r['offset']+r['length']] for r in rows}


def load_cfg(config_path):
    cfg=json.loads(Path(config_path).read_text('utf-8'))
    base=resolve(cfg['base_npk']); output=resolve(cfg['output'],False)
    if not base.is_relative_to(ROOT/'output') or not output.is_relative_to(ROOT/'output'):
        raise ValueError('Base and candidate output must stay in project output')
    if output==base.parent:
        raise ValueError('A new candidate must have a separate output folder')
    name=cfg['npk_name']
    if not re.fullmatch(r'A_[A-Za-z0-9_.-]+\.NPK',name):
        raise ValueError('Candidate needs a project A_*.NPK basename')
    if cfg.get('base_sha256') and sha(base)!=cfg['base_sha256']:
        raise ValueError('Base NPK changed from the configured approved baseline')
    overlays=cfg.get('overlays',[])
    if not overlays or len(overlays)>256:
        raise ValueError('Explicit bounded overlay list required')
    paths=[s['path'] for s in overlays]
    if len(set(paths))!=len(paths):
        raise ValueError('Each overlay path must occur exactly once')
    for spec in overlays:
        path=spec['path']
        if (not path.startswith('sprite/') or not path.endswith('.img') or '\\' in path
                or any(p in ('..','.') for p in Path(path).parts)):
            raise ValueError('Invalid internal IMG path')
        if spec.get('frame_mode','local') not in ('local','canvas'):
            raise ValueError('frame_mode must be local or canvas')
    return cfg,base,output,output/name


def protected(cfg):
    paths=list((GAME/'ImagePacks2').glob('A_*.NPK'))
    paths+=list((GAME/'Video/Character/Cutscene_buf').glob('*.bk2'))
    # Protect the accepted Claude buff independently of candidate project.
    buff=ROOT/'output/claude_buff_v07/preview'
    paths += [p for p in (buff/'manifest.json',buff/'portrait.bik') if p.is_file()]
    paths += list((buff/'frames').glob('*.png'))
    for relative in cfg.get('protect_paths',[]):
        p=resolve(relative)
        paths += list(p.rglob('*')) if p.is_dir() else [p]
    return {str(p.resolve()):sha(p) for p in sorted(set(paths)) if p.is_file()}


def input_frames(spec):
    if 'frames' in spec:
        result={int(k):resolve(p) for k,p in spec['frames'].items()}
        sequence=None
    else:
        sequence=([resolve(p) for p in spec['frame_paths']] if 'frame_paths' in spec else
                  sorted(resolve(spec['frames_dir']).glob('*.png')))
        if not sequence:
            raise ValueError('No PNG frames for overlay')
        result={}
    for p in (result.values() if sequence is None else sequence):
        if not p.is_relative_to(ROOT/'output') or not p.is_file():
            raise ValueError('Frame PNGs must be existing files in project output')
    return result,sequence


def sample_index(index,source_count,target_count):
    if min(source_count,target_count)<1:
        raise ValueError('Frame counts must be positive')
    return 0 if min(source_count,target_count)==1 else round(index*(source_count-1)/(target_count-1))


def fit_canvas(image,size,spec):
    if image.size==size:
        return image
    if not spec.get('fit_to_canvas',False):
        raise ValueError(f'PNG canvas {image.size} differs from official {size}; prepare it explicitly or set fit_to_canvas')
    mode=spec.get('canvas_fit','contain')
    if mode=='resize':
        return image.resize(size,Image.Resampling.LANCZOS)
    if mode!='contain':
        raise ValueError('canvas_fit must be contain or resize')
    fitted=ImageOps.contain(image,size,Image.Resampling.LANCZOS)
    page=Image.new('RGBA',size)
    page.alpha_composite(fitted,((size[0]-fitted.width)//2,(size[1]-fitted.height)//2))
    return page


def edit_img(original,spec,inputs):
    explicit,sequence=input_frames(spec)
    if any(k<0 or k>=original.count or 'link' in original.frames[k] for k in explicit):
        raise ValueError('Explicit overrides must address valid non-link indices')
    for p in (explicit.values() if sequence is None else sequence):
        inputs[str(p)]=sha(p)
    mode=spec.get('frame_mode','local'); images=[]; metadata=[]; records=[]
    for k,frame in enumerate(original.frames):
        old_meta=meta(frame)
        if 'link' in frame:
            images.append(Image.new('RGBA',(1,1))); metadata.append(old_meta)
            records.append({'frame':k,'link':frame['link']}); continue
        old=image_at(original,k)
        old_empty=shape(frame)[0]*shape(frame)[1]<=1 or old.getbbox() is None
        chosen=explicit.get(k) if sequence is None else sequence[sample_index(k,len(sequence),original.count)]
        if chosen is None or (old_empty and spec.get('preserve_empty_frames',True)):
            images.append(old); metadata.append(old_meta)
            records.append({'frame':k,'unchanged':True,'original_empty':old_empty,'metadata':old_meta,'size':list(old.size)}); continue
        with Image.open(chosen) as source:
            image=source.convert('RGBA')
        new_meta=dict(old_meta)
        if mode=='canvas':
            if not spec.get('allow_geometry_change',False):
                raise ValueError('Canvas editing requires explicit allow_geometry_change:true')
            size=canvas(frame)
            if not size or min(size)<1 or size[0]*size[1]>16_000_000:
                raise ValueError('Invalid official canvas dimensions')
            page=fit_canvas(image,size,spec)
            bounds=page.getbbox()
            if bounds:
                image=page.crop(bounds); new_meta.update(x=bounds[0],y=bounds[1])
            else:
                image=Image.new('RGBA',(1,1)); new_meta.update(x=0,y=0)
        elif image.size!=old.size:
            if not spec.get('allow_geometry_change',False):
                raise ValueError(f'Local PNG size differs: {image.size} != {old.size}')
            if 'position' in spec:
                new_meta.update(x=int(spec['position'][0]),y=int(spec['position'][1]))
        # Transparent RGB is retained as supplied: V2 readback checks all RGBA.
        images.append(image); metadata.append(new_meta)
        records.append({'frame':k,'png':str(chosen),'metadata':new_meta,'size':list(image.size),
                        'old_metadata':old_meta,'old_size':list(old.size),'original_empty':False})
    written=write_v2(images,metadata,preserve_links=True)
    check=ImgArchive(written)
    if check.count!=original.count:
        raise ValueError('Written IMG frame count differs')
    for k,frame in enumerate(check.frames):
        if meta(frame)!=metadata[k]:
            raise ValueError(f'Written metadata/link differs at frame{k}')
        if 'link' not in frame:
            actual=image_at(check,k)
            if actual.size!=images[k].size or not np.array_equal(np.asarray(actual),np.asarray(images[k])):
                raise ValueError(f'Written IMG RGBA differs at frame{k}')
    return written,check,records


def world_page(img,k,size):
    frame=img.resolve(k); page=Image.new('RGBA',size)
    page.alpha_composite(image_at(img,k),(frame['x'],frame['y']))
    return page


def comparison(folder,original,new):
    selected=list(range(original.count))
    if len(selected)>12:
        selected=sorted({round(i*(original.count-1)/11) for i in range(12)})
    geometries=[canvas(original.resolve(k)) for k in range(original.count)]
    size=max(c[0] for c in geometries),max(c[1] for c in geometries)
    if min(size)<1 or size[0]*size[1]>16_000_000:
        return {'skipped':'Unexpectedly large official canvas'}
    sheet=Image.new('RGB',(640,len(selected)*205),'#252b34'); draw=ImageDraw.Draw(sheet)
    for row,k in enumerate(selected):
        for col,img in enumerate((original,new)):
            page=world_page(img,k,size); page.thumbnail((308,177),Image.Resampling.LANCZOS)
            sheet.paste(page,(col*320+(320-page.width)//2,row*205+24+(177-page.height)//2),page)
        draw.text((8,row*205+5),f'original k{k}',fill='white'); draw.text((328,row*205+5),f'candidate k{k}',fill='white')
    sheet.save(folder/'contact.jpg',quality=93)
    if original.count<=180:
        for name,img in [('original',original),('candidate',new)]:
            pages=[]
            for k in range(img.count):
                page=world_page(img,k,size); page.thumbnail((480,300),Image.Resampling.LANCZOS)
                pages.append(page)
            # Same canvas at every index, so resizing remains stable.
            pages[0].save(folder/f'{name}.webp',save_all=True,append_images=pages[1:],lossless=True,exact=True,duration=100,loop=0)
    return {'frames':selected,'canvas':list(size),'fps':10,'timing':'Engineering estimate only; ANI/game timing unknown'}


def stage(config_path,replace=False):
    cfg,base,out,package=load_cfg(config_path); stage_folder=out/'stage'
    if package.exists() or ((stage_folder/'manifest.json').exists() and not replace):
        raise FileExistsError('Candidate exists; replace only an un-published stage or choose a new version')
    before=protected(cfg); inputs={str(Path(config_path).resolve()):sha(config_path),str(base):sha(base),str(Path(__file__)):sha(Path(__file__))}
    cache={}; results=[]
    for spec in cfg['overlays']:
        source=resolve(spec['source_npk']); inputs[str(source)]=sha(source)
        if source not in cache:
            rows,contents=payloads(source); cache[source]=({r['path']:r for r in rows},contents)
        rows,contents=cache[source]
        if spec['path'] not in rows:
            raise ValueError(f'Official path not found: {spec["path"]}')
        row=rows[spec['path']]; raw=contents[spec['path']]; original=reader(raw,row['version'])
        written,check,records=edit_img(original,spec,inputs)
        key=hashlib.sha256(spec['path'].encode()).hexdigest()[:16]
        folder=stage_folder/'imgs'/key; folder.mkdir(parents=True,exist_ok=True)
        target=folder/'edited.img'; target.write_bytes(written)
        preview=comparison(folder,original,check)
        result={'path':spec['path'],'source_npk':str(source),'source_payload_sha256':hashlib.sha256(raw).hexdigest(),
                'payload':str(target.relative_to(ROOT)).replace('\\','/'),'payload_sha256':sha(target),
                'frame_count':check.count,'frame_mode':spec.get('frame_mode','local'),
                'allow_geometry_change':bool(spec.get('allow_geometry_change',False)),
                'frames':records,'preview':preview}
        save(folder/'frames.json',result); results.append(result)
    if protected(cfg)!=before:
        raise ValueError('Protected game/buff files changed while staging')
    manifest={'status':'staged_for_visual_review','created_at':datetime.now().astimezone().isoformat(),
              'config':str(Path(config_path).resolve()),'base_npk':str(base),'base_sha256':sha(base),
              'npk_name':package.name,'inputs_sha256':inputs,'protected_sha256':before,'edits':results,
              'installed':False,'ingame_verified':False}
    save(stage_folder/'manifest.json',manifest)
    return {'staged':True,'imgs':len(results),'frames':sum(r['frame_count'] for r in results),
            'manifest':str(stage_folder/'manifest.json'),'published':False,'installed':False}


def package_stage(config_path):
    cfg,base,out,package=load_cfg(config_path); manifest_path=out/'stage/manifest.json'
    manifest=json.loads(manifest_path.read_text('utf-8'))
    if package.exists() or manifest['status']!='staged_for_visual_review':
        raise FileExistsError('Existing candidate cannot be overwritten')
    for filename,digest in manifest['inputs_sha256'].items():
        if sha(filename)!=digest:
            raise ValueError(f'Signed input changed: {filename}')
    if protected(cfg)!=manifest['protected_sha256']:
        raise ValueError('Protected files changed after staging')
    overlays={}
    for item in manifest['edits']:
        p=resolve(item['payload'])
        if sha(p)!=item['payload_sha256']:
            raise ValueError('Signed stage IMG changed')
        overlays[item['path']]=p.read_bytes()
    rows,base_entries=payloads(base)
    order=[r['path'] for r in rows]+sorted(set(overlays)-set(base_entries))
    merged=base_entries|overlays; temp=package.with_suffix('.NPK.building')
    if temp.exists():
        raise FileExistsError('An unfinished package requires inspection')
    temp.write_bytes(write_shared_npk([(path,merged[path]) for path in order]))
    written,contents=payloads(temp)
    if [r['path'] for r in written]!=order or contents!=merged:
        raise ValueError('NPK readback differs from signed payloads')
    if protected(cfg)!=manifest['protected_sha256'] or sha(base)!=manifest['base_sha256']:
        raise ValueError('Protected baseline changed while packaging')
    temp.replace(package)
    report={'package':str(package),'sha256':sha(package),'bytes':package.stat().st_size,'entries':len(written),
            'base_npk':str(base),'base_sha256':manifest['base_sha256'],'base_entries':len(rows),
            'added_paths':sorted(set(overlays)-set(base_entries)),'replaced_paths':sorted(set(overlays)&set(base_entries)),
            'unchanged_base_payloads':len(set(base_entries)-set(overlays)),
            'all_old_paths_preserved':True,'unchanged_payloads_byte_identical':True,
            'changed_img_count':len(overlays),'actual_payload_readback_passed':True,
            'stage_manifest_sha256':sha(manifest_path),'protected_files_unchanged':True,
            'installed':False,'ingame_verified':False,'preview_timing_is_engineering_only':True}
    save(out/'validation.json',report)
    (out/(package.name+'.sha256')).write_text(report['sha256']+'  '+package.name+'\n',encoding='ascii')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('config',type=Path)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--stage',action='store_true'); action.add_argument('--package',action='store_true')
    parser.add_argument('--replace-stage',action='store_true'); args=parser.parse_args()
    result=stage(args.config,args.replace_stage) if args.stage else package_stage(args.config)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8'); main()
