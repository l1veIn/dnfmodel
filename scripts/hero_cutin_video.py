"""Config-driven Grok first-frame videos, journaled before each paid request.

Usage: python scripts/hero_cutin_video.py CONFIG submit|collect|cut CLIP_ID
Submit never retries. A missing task ID after an uncertain request requires an
account-task audit, not another submit. Collect/cut do not create paid tasks.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

import av
import numpy as np
from PIL import Image, ImageDraw

from run_65535_samples import load_relay

ROOT = Path(__file__).resolve().parents[1]
SAFE_RECEIPT = ('id', 'model', 'status', 'progress', 'seconds', 'size', 'cost_usd',
                'error_code', 'error_message', 'created_at', 'finished_at')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def resolve(value, exists=True):
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve(strict=exists)


def output_path(value):
    path = resolve(value, False)
    if not path.is_relative_to(ROOT / 'output'):
        raise ValueError('Video outputs must stay in the project output directory')
    return path


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def curl_transfer(url, method='GET', headers=None, body=None, target=None, timeout=180):
    """Use Windows curl with verified TLS; secrets exist only in stdin memory.

    Never retry or silently switch transports. Temporary request JSON contains
    image data but no API key; exact owned temporary files are removed afterward.
    """
    temp_root=ROOT/'output/validation/hero_transport'
    temp_root.mkdir(parents=True,exist_ok=True)
    files=[]
    def temporary(suffix):
        fd,name=tempfile.mkstemp(prefix='hero_',suffix=suffix,dir=temp_root)
        import os
        os.close(fd);path=Path(name).resolve()
        if not path.is_relative_to(temp_root.resolve()):
            raise ValueError('Unexpected transport temporary path')
        files.append(path);return path
    response=Path(target) if target else temporary('.response')
    config=['silent','show-error','location',f'url = {json.dumps(url,ensure_ascii=False)}',
            f'request = {json.dumps(method)}',f'max-time = {int(timeout)}',
            f'output = {json.dumps(response.as_posix(),ensure_ascii=False)}','write-out = "%{http_code}"']
    # Certificate verification remains curl's default. No insecure/TLS-bypass flag.
    for key,value in (headers or {}).items():
        config.append('header = '+json.dumps(f'{key}: {value}',ensure_ascii=False))
    if body is not None:
        request_file=temporary('.request.json')
        request_file.write_text(json.dumps(body,ensure_ascii=False),encoding='utf-8')
        config.append('data-binary = '+json.dumps('@'+request_file.as_posix(),ensure_ascii=False))
    try:
        result=subprocess.run(['curl.exe','--config','-'],input=('\n'.join(config)+'\n').encode('utf-8'),
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout+10,check=False)
        if result.returncode:
            message=result.stderr.decode('utf-8','replace')[:700]
            for value in (headers or {}).values():
                if value.startswith('Bearer '):message=message.replace(value[7:],'[redacted]')
            raise urllib.error.URLError(f'curl transfer failed ({result.returncode}): {message}')
        status=int(result.stdout.decode('ascii','replace').strip()[-3:])
        if status>=400:
            error_data=response.read_bytes()[:2000] if response.is_file() else b''
            raise urllib.error.HTTPError(url,status,'API request rejected',None,io.BytesIO(error_data))
        return response.read_bytes() if target is None else None
    finally:
        for path in files:
            # Exact files created above; no recursive cleanup or computed moves.
            if path.is_file():path.unlink()


def api_json(relay,method,path,body=None,transport='urllib',idempotency=None):
    headers={'Authorization':'Bearer '+relay.load_key(),'User-Agent':'dnf-hero-cutin/1.0'}
    if body is not None:headers['Content-Type']='application/json'
    if idempotency:headers['Idempotency-Key']=idempotency
    if transport=='curl':
        return json.loads(curl_transfer(relay.BASE+path,method,headers,body))
    if transport!='urllib':raise ValueError('transport must be explicitly urllib or curl')
    request=urllib.request.Request(relay.BASE+path,data=json.dumps(body).encode('utf-8') if body is not None else None,
                                   method=method,headers=headers)
    with urllib.request.urlopen(request,timeout=180) as response:
        return json.load(response)


def clip_config(config_path, clip_id):
    data = json.loads(Path(config_path).read_text('utf-8'))
    clips = data.get('clips', [])
    ids = [item['id'] for item in clips]
    if len(ids) != len(set(ids)):
        raise ValueError('Clip IDs must be unique')
    selected = [item for item in clips if item['id'] == clip_id]
    if len(selected) != 1 or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', clip_id):
        raise ValueError('Unknown or unsafe clip ID')
    cfg = selected[0]
    if cfg.get('model', 'grok-imagine-video-1.5-preview') not in ('grok-imagine-video-1.5-preview', 'grok-imagine-video'):
        raise ValueError('This runner supports the explicitly requested Grok video models')
    if not 1 <= int(cfg['seconds']) <= 15 or cfg.get('resolution', '1080p') not in ('480p', '720p', '1080p'):
        raise ValueError('Invalid video duration/resolution')
    if not isinstance(cfg.get('prompt'), str) or not cfg['prompt'].strip():
        raise ValueError('A concrete video prompt is required')
    cfg = dict(cfg)
    if cfg.get('transport','urllib') not in ('urllib','curl'):
        raise ValueError('transport must be explicitly urllib or curl')
    if cfg.get('key_profile','default') not in ('default','blue_hair'):
        raise ValueError('Unknown chroma key profile')
    cfg['output'] = output_path(cfg['output'])
    return cfg


def submit(config_path, clip_id):
    cfg = clip_config(config_path, clip_id)
    work = cfg['output']; work.mkdir(parents=True, exist_ok=True)
    journal_path = work / 'journal.json'
    if journal_path.exists():
        raise FileExistsError('Journal already exists. Collect the existing task; do not resubmit.')
    first = resolve(cfg['first_frame'])
    if not first.is_relative_to(ROOT / 'output'):
        raise ValueError('The prepared first frame must be stored in project output')
    with Image.open(first) as image:
        width, height = image.size
        if not cfg.get('allow_non_16_9', False) and abs(width / height - 16 / 9) > .035:
            raise ValueError('Prepare the complete 16:9 video canvas before submission')
        if width * height > 8_500_000:
            raise ValueError('First frame is unexpectedly large')
        image.convert('RGB').save(work / 'first_frame.png')
    relay = load_relay()
    model = cfg.get('model', 'grok-imagine-video-1.5-preview')
    body = {'kind': 'video', 'model': model, 'operation': 'generate', 'input': {
        'prompt': cfg['prompt'], 'seconds': int(cfg['seconds']),
        'resolution': cfg.get('resolution', '1080p'), 'input_mode': 'first_frame',
        'input_reference': {'image_url': relay.to_data_uri(str(work / 'first_frame.png'))}}}
    key = uuid.uuid4().hex
    journal = {'state': 'launching', 'clip_id': clip_id, 'character': cfg.get('character'),
               'model': model, 'seconds': int(cfg['seconds']), 'resolution': cfg.get('resolution', '1080p'),
               'prompt': cfg['prompt'], 'first_frame': str(first), 'first_frame_sha256': sha(first),
               'submitted_first_frame_sha256': sha(work / 'first_frame.png'),
               'config': str(Path(config_path).resolve()), 'config_sha256': sha(config_path),
               'transport': cfg.get('transport','urllib'),
               'idempotency': key, 'started_at': datetime.now().astimezone().isoformat()}
    # Exclusive creation is the final guard against two processes submitting it.
    with journal_path.open('x', encoding='utf-8') as stream:
        json.dump(journal, stream, ensure_ascii=False, indent=2); stream.write('\n')
    try:
        task=relay.unwrap(api_json(relay,'POST','/v1/tasks',body,cfg.get('transport','urllib'),key))
    except urllib.error.HTTPError as error:
        journal.update(state='rejected', http_status=error.code)
        save(journal_path, journal)
        raise RuntimeError(f'Video request rejected (HTTP {error.code}); inspect the existing journal, do not resubmit') from None
    except (OSError, TimeoutError, urllib.error.URLError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        # Exception text contains no request body/headers in urllib; nevertheless
        # redact a key should a transport layer unexpectedly include it.
        detail=str(error).replace(relay.load_key(),'[redacted]')[:700]
        journal.update(state='submission_uncertain', transport_error_type=type(error).__name__,
                       transport_error=detail,
                       recovery='Audit account task history before any further submission')
        save(journal_path, journal)
        raise RuntimeError('Submission outcome uncertain; audit existing account tasks rather than resubmitting') from None
    if not task.get('id'):
        journal.update(state='submission_uncertain', recovery='Task response did not include an ID; audit account history')
        save(journal_path, journal)
        raise RuntimeError('Task ID missing; do not resubmit')
    journal.update(state='submitted', task_id=task['id'])
    save(journal_path, journal)
    save(work / 'receipt.json', {k: task.get(k) for k in SAFE_RECEIPT})
    return {'clip': clip_id, 'submitted': True, 'task_id': task['id'], 'output': str(work)}


def collect(config_path, clip_id, wait=45):
    cfg = clip_config(config_path, clip_id); work = cfg['output']
    journal = json.loads((work / 'journal.json').read_text('utf-8'))
    if not journal.get('task_id'):
        raise ValueError('Existing journal has no task ID; audit tasks, never resubmit automatically')
    relay = load_relay(); deadline = time.monotonic() + min(max(float(wait), 0), 55)
    while True:
        task = relay.unwrap(api_json(relay,'GET','/v1/tasks/'+journal['task_id'],transport=cfg.get('transport','urllib')))
        safe = {k: task.get(k) for k in SAFE_RECEIPT}
        save(work / 'receipt.json', safe)
        state = task.get('status')
        if state in ('done', 'failed'):
            break
        if time.monotonic() >= deadline:
            return {'clip': clip_id, 'task_id': journal['task_id'], 'complete': False, 'resubmit': False}
        time.sleep(min(5, max(0, deadline-time.monotonic())))
    if state == 'failed':
        journal.update(state='failed'); save(work / 'journal.json', journal)
        return {'clip': clip_id, 'task_id': journal['task_id'], 'failed': True,
                'error_code': task.get('error_code'), 'error_message': task.get('error_message'),
                'cost_usd': task.get('cost_usd'), 'resubmit': False}
    target = work / 'video.mp4'
    if not target.is_file():
        urls = task.get('result_urls') or []
        url = task.get('video_url') or (urls[0] if urls else None)
        if not url:
            raise ValueError('Completed task has no video URL; collect again, do not resubmit')
        temporary = work / 'video.mp4.downloading'
        if cfg.get('transport','urllib')=='curl':
            curl_transfer(url,headers={'User-Agent':'dnf-hero-cutin/1.0'},target=temporary,timeout=240)
        else:
            request = urllib.request.Request(url, headers={'User-Agent': 'dnf-hero-cutin/1.0'})
            with urllib.request.urlopen(request, timeout=240) as response, temporary.open('wb') as stream:
                while chunk := response.read(1024*1024):
                    stream.write(chunk)
        temporary.replace(target)
    actual = inspect_video(target)
    journal.update(state='downloaded', movie_sha256=sha(target), actual_video=actual)
    save(work / 'journal.json', journal)
    return {'clip': clip_id, 'task_id': journal['task_id'], 'complete': True, 'video': str(target),
            'cost_usd': task.get('cost_usd'), 'actual_video': actual}


def playback_stream(container):
    """A cover image is a video stream in MP4, but is not the animation."""
    candidates=[stream for stream in container.streams.video
                if not stream.disposition & av.stream.Disposition.attached_pic]
    if len(candidates)!=1:
        raise ValueError('Expected one continuous video stream, excluding attached cover images')
    return candidates[0]


def inspect_video(path):
    with av.open(str(path)) as container:
        stream = playback_stream(container)
        return {'width': stream.width, 'height': stream.height, 'fps': float(stream.average_rate or 0),
                'declared_frames': stream.frames, 'audio_streams': len(container.streams.audio),
                'video_stream_index':stream.index,'attached_cover_images':len(container.streams.video)-1}


def key_magenta(image):
    """Key connected near-magenta background, preserving opaque lilac/blue art.

    Foreground interiors are never globally desaturated or green-shifted. Only
    strongly chromatic magenta and their soft edge transition receive alpha;
    despill is limited to those partially transparent edge pixels.
    """
    a = np.asarray(image.convert('RGB')).astype(np.float32)
    r, g, b = a.transpose(2, 0, 1)
    strength = np.minimum(r, b)-g
    pure = (r > 140) & (b > 140) & (strength > 85) & (np.abs(r-b) < 100)
    # Flood background through near-key pixels, so interior purple is untouched.
    from scipy.ndimage import binary_dilation, binary_propagation
    seed = np.zeros(pure.shape, bool)
    seed[0] = pure[0]; seed[-1] = pure[-1]; seed[:,0] |= pure[:,0]; seed[:,-1] |= pure[:,-1]
    connected = binary_propagation(seed, mask=pure)
    # Include enclosed uniform key holes (e.g. between arm and torso), but only
    # the very saturated key color, never pale lilac costume shadows.
    connected |= (r > 175) & (b > 175) & (g < 65) & (strength > 120)
    alpha = np.full(pure.shape, 255., np.float32)
    alpha[connected] = 0
    edge = binary_dilation(connected, iterations=2) & ~connected
    saturation=(a.max(2)-a.min(2))/np.maximum(a.max(2),1)
    edge &= (strength > 60) & (r > 110) & (b > 110) & (saturation > .28)
    alpha[edge] = np.clip(255*(1-(strength[edge]-60)/100), 0, 255)
    partial = edge & (alpha < 250)
    # Only remove excess key chroma on that boundary, with no interior edits.
    excess = np.maximum(0, np.minimum(r,b)-g-20)
    a[...,0][partial] -= excess[partial]*.45
    a[...,2][partial] -= excess[partial]*.45
    out = np.dstack((np.clip(a,0,255),alpha)).astype(np.uint8)
    out[out[...,3] == 0, :3] = 0
    return Image.fromarray(out, 'RGBA')


def clean_blue_hair_edges(image):
    """Remove residual magenta only within five output pixels of transparency.

    This opt-in profile models a blue foreground mixed with magenta at its
    boundary. Pale lilac, opaque blue and all interior pixels are untouched.
    """
    from scipy.ndimage import distance_transform_edt
    a=np.asarray(image.convert('RGBA')).astype(np.float32)
    r,g,b,alpha=a.transpose(2,0,1)
    distance=distance_transform_edt(alpha>8)
    saturation=(a[...,:3].max(2)-a[...,:3].min(2))/np.maximum(a[...,:3].max(2),1)
    boundary=(distance<=5)&(alpha>0)
    pollution=boundary&(saturation>.45)&(np.minimum(r,b)-g>60)&((r-g)>.42*(b-g))
    # Estimate the key-color fraction assuming the clean blue edge has
    # R-G approximately .3*(B-G). Unmix, rather than whitening/desaturating.
    fraction=np.clip(((r-g)-.3*(b-g))/(255*.7),0,.99)
    fraction=np.where(pollution,fraction,0)
    retain=1-fraction
    a[...,0][pollution]=(r[pollution]-255*fraction[pollution])/retain[pollution]
    a[...,1][pollution]=g[pollution]/retain[pollution]
    a[...,2][pollution]=(b[pollution]-255*fraction[pollution])/retain[pollution]
    a[...,3][pollution]=alpha[pollution]*retain[pollution]
    a[...,3][pollution&(fraction>.9)]=0
    out=np.clip(a,0,255).astype(np.uint8)
    out[out[...,3]==0,:3]=0
    return Image.fromarray(out,'RGBA')


def cut(config_path, clip_id):
    cfg = clip_config(config_path, clip_id); work = cfg['output']
    if (work / 'frames/manifest.json').exists():
        raise FileExistsError('Cut output already exists; use a new version instead of overwriting reviewed frames')
    target = resolve(cfg['video_source']) if cfg.get('video_source') else work / 'video.mp4'
    if not target.resolve().is_relative_to(ROOT/'output'):
        raise ValueError('Video source must stay in project output')
    movie_sha = sha(target)
    with av.open(str(target)) as box:
        stream = playback_stream(box)
        actual = {'width': stream.width, 'height': stream.height,
                  'fps': float(stream.average_rate or 0), 'audio_streams': len(box.streams.audio),
                  'video_stream_index':stream.index,'attached_cover_images':len(box.streams.video)-1}
        frames = [frame.to_image().convert('RGB') for frame in box.decode(stream)]
    if not frames or len(frames) > 1000:
        raise ValueError('Unexpected decoded video frame count')
    count = int(cfg.get('sample_frames', min(len(frames),180)))
    if not 1 <= count <= 240:
        raise ValueError('sample_frames must be 1..240')
    canvas = tuple(cfg.get('canvas', frames[0].size))
    if len(canvas) != 2 or min(canvas) < 1 or canvas[0]*canvas[1] > 8_500_000:
        raise ValueError('Invalid output canvas')
    # Preserve the entire decoded frame, including valid extra coded rows.
    picks = [0 if count == 1 else round(k*(len(frames)-1)/(count-1)) for k in range(count)]
    folder = work / 'frames'; folder.mkdir(exist_ok=True)
    smalls=[]; hashes=[]; metrics=[]
    sheet = Image.new('RGB',(256*6, (count+5)//6*165),'#252b34'); draw=ImageDraw.Draw(sheet)
    for k,index in enumerate(picks):
        image = key_magenta(frames[index]).resize(canvas,Image.Resampling.LANCZOS)
        if cfg.get('key_profile')=='blue_hair':
            image=clean_blue_hair_edges(image)
        path=folder/f'frame_{k:04d}.png'; image.save(path)
        hashes.append(sha(path)); alpha=np.asarray(image)[...,3]
        metrics.append({'frame':k,'video_frame':index,'alpha_range':[int(alpha.min()),int(alpha.max())],
                        'bbox':list(image.getbbox()) if image.getbbox() else None})
        small=image.copy(); small.thumbnail((248,140),Image.Resampling.LANCZOS)
        sheet.paste(small,(k%6*256+(256-small.width)//2,k//6*165+20),small)
        draw.text((k%6*256+5,k//6*165+3),f'k{k} video{index}',fill='white')
        smalls.append(small)
    sheet.save(work/'contact.jpg',quality=93)
    # Preview uses a fixed page, because per-frame thumbnails may differ size.
    previews=[]
    for image in smalls:
        page=Image.new('RGBA',(256,144)); page.alpha_composite(image,((256-image.width)//2,(144-image.height)//2)); previews.append(page)
    previews[0].save(work/'preview.webp',save_all=True,append_images=previews[1:],lossless=True,exact=True,
                     duration=max(1,round(int(cfg['seconds'])*1000/count)),loop=0)
    manifest={'clip_id':clip_id,'frames':count,'canvas':list(canvas),'source_video_sha256':movie_sha,
              'key_profile':cfg.get('key_profile','default'),
              'actual_video':actual|{'decoded_frames':len(frames)},'source_indices':picks,'frame_sha256':hashes,
              'frame_metrics':metrics,'chroma_key':'near-magenta background; opaque lilac/blue interiors preserved; edge-only despill',
              'timing':'Uniform sampling for engineering preview; original ANI/game timing unknown','ingame_verified':False}
    save(folder/'manifest.json',manifest)
    save(work/'cut_manifest.json',manifest)
    return {'clip':clip_id,'frames':count,'canvas':canvas,'frames_dir':str(folder),'video_sha256':movie_sha}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config',type=Path)
    parser.add_argument('command',choices=['submit','collect','cut'])
    parser.add_argument('clip_id'); parser.add_argument('--wait',type=float,default=45)
    args=parser.parse_args()
    result=(submit(args.config,args.clip_id) if args.command=='submit' else
            collect(args.config,args.clip_id,args.wait) if args.command=='collect' else cut(args.config,args.clip_id))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8'); main()
