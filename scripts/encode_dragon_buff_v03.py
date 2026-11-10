"""Encode/verify the frozen v03 candidate, including legal partial-alpha fade frames.

Uses the existing authorized local RAD tool. No network, installation or game writes.
The older encode_buff.py and all v02 files are intentionally left unchanged.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
import os
from pathlib import Path
import subprocess
import time

import av
import numpy as np
from PIL import Image

from buff_portrait import ROOT,digest

CONFIG=ROOT/'design/gpt_dragon_slayer_v03/buff_v03.json'
TOOL=ROOT/'tools/downloads/rad_video_tools_2026-10-28/bin/radvideo64.exe'


def save(path,data):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temporary.replace(path)


def folder_and_manifest():
    cfg=json.loads(CONFIG.read_text('utf-8'));folder=(ROOT/cfg['output']).resolve()
    if folder!=ROOT/'output/dragon_buff_v03/preview':raise ValueError('Encoder is restricted to the frozen v03 preview')
    manifest=json.loads((folder/'manifest.json').read_text('utf-8'))
    if (manifest['frames'],manifest['size'],manifest['fps'])!=(19,[470,668],15):raise ValueError('Invalid buff contract')
    freeze=json.loads((folder/'freeze_record.json').read_text('utf-8'))
    if freeze['manifest_sha256']!=digest(folder/'manifest.json'):raise ValueError('Frozen manifest changed')
    for name,sha in manifest['inputs_sha256'].items():
        if digest(ROOT/name)!=sha:raise ValueError('Frozen source input changed: '+name)
    for k,sha in enumerate(manifest['frame_sha256']):
        if digest(folder/'frames'/f'frame_{k:04d}.png')!=sha:raise ValueError('Frozen PNG changed')
    return folder,manifest


def verify(folder,manifest,movie):
    with movie.open('rb') as stream:magic=stream.read(4)
    if magic[:3]!=b'BIK':raise ValueError('Expected ordinary Bink1 stream')
    decoded=[];times=[]
    with av.open(str(movie)) as container:
        if len(container.streams.video)!=1 or container.streams.audio:raise ValueError('Expected one video and no audio')
        stream=container.streams.video[0];fmt=stream.codec_context.format.name
        if stream.codec_context.name!='binkvideo' or (stream.width,stream.height)!=(470,668) or stream.average_rate!=Fraction(15,1) or 'a' not in fmt:raise ValueError('Codec/dimensions/fps/alpha mismatch')
        for frame in container.decode(video=0):
            if len(decoded)>=19:raise ValueError('Extra encoded frame')
            decoded.append(Image.fromarray(frame.to_ndarray(format='rgba')));times.append(float(frame.pts*frame.time_base) if frame.pts is not None else None)
    if len(decoded)!=19:raise ValueError('Wrong encoded count')
    decoded_dir=folder/'encoded_frames';decoded_dir.mkdir(exist_ok=True)
    alpha_errors=[];rgb_errors=[];ranges=[];source_ranges=[];range_errors=[];sources=[]
    for k,image in enumerate(decoded):
        p=folder/'frames'/f'frame_{k:04d}.png';source=Image.open(p).convert('RGBA');sources.append(digest(p))
        a=np.asarray(source).astype(np.int16);b=np.asarray(image).astype(np.int16)
        if a.shape!=b.shape:raise ValueError('Frame dimensions changed')
        error=float(np.abs(a[:,:,3]-b[:,:,3]).mean());alpha_errors.append(error)
        sr=[int(a[:,:,3].min()),int(a[:,:,3].max())];dr=[int(b[:,:,3].min()),int(b[:,:,3].max())]
        source_ranges.append(sr);ranges.append(dr);re=[abs(dr[i]-sr[i]) for i in range(2)];range_errors.append(re)
        # A uniform fade is legal: compare each decoded frame with ITS actual PNG
        # bounds, rather than requiring every source frame to contain alpha>=240.
        if error>4 or re[0]>8 or re[1]>12:raise ValueError(f'Frame{k}: alpha differs from actual source range/MAE')
        visible=a[:,:,3]>16;rgb_errors.append(float(np.abs(a[:,:,:3]-b[:,:,:3])[visible].mean()) if visible.any() else 0)
        image.save(decoded_dir/f'frame_{k:04d}.png')
    if sources!=manifest['frame_sha256']:raise ValueError('Encoded inputs do not match frozen manifest')
    durations=[round((k+1)*1000/15)-round(k*1000/15) for k in range(19)]
    decoded[0].save(folder/'encoded_preview.webp',save_all=True,append_images=decoded[1:],duration=durations,lossless=True,loop=0,exact=True)
    small=[im.resize((335,476),Image.Resampling.LANCZOS) for im in decoded]
    small[0].save(folder/'encoded_preview_335.webp',save_all=True,append_images=small[1:],duration=durations,lossless=True,loop=0,exact=True)
    return dict(status='encoded',file=movie.name,codec='binkvideo',pixel_format=fmt,magic=magic.decode('ascii'),width=470,height=668,frames=19,fps=15,alpha=True,has_alpha=True,audio_streams=0,verified=True,validation_scope='Bink1 actual19-frame source binding, dimensions/fps/noaudio, alpha plane and per-source-frame alpha bounds plus MAE; legal uniform-alpha fade preserved.',visual_review='root_and_independent_review_selected_draft01',ingame_verified=False,source_manifest_sha256=digest(folder/'manifest.json'),source_frame_sha256=sources,source_frames_sha256=sources,file_sha256=digest(movie),sha256=digest(movie),size=movie.stat().st_size,decoded_preview='encoded_preview.webp',decoded_frames='encoded_frames',frame_times_seconds=times,quality=dict(alpha_mae_mean=float(np.mean(alpha_errors)),alpha_mae_worst=max(alpha_errors),visible_rgb_mae_mean=float(np.mean(rgb_errors)),visible_rgb_mae_worst=max(rgb_errors),alpha_ranges=ranges,source_alpha_ranges=source_ranges,alpha_range_absolute_errors=range_errors,note='Bink1 is lossy; transparent and partially opaque fade frames are compared to their actual frozen source. No opaque marker added.'))


def encode(verify_only=False):
    folder,manifest=folder_and_manifest();movie=folder/'portrait.bik';report_path=folder/'encoding_report.json';command=[]
    if not verify_only:
        if movie.exists():raise FileExistsError('Bink already exists; use --verify-only')
        if not TOOL.is_file():raise FileNotFoundError('Authorized local RAD tool missing')
        sequence=folder/'input_frames.lst';sequence.write_text('\n'.join(str(folder/'frames'/f'frame_{k:04d}.png') for k in range(19))+'\n',encoding='utf-8')
        command=[str(TOOL),'binkc',str(sequence),str(movie),'/Bink1','/Alpha','/ForceFrameRate15','/NoSound','/DataRate1000000','/CPUs4','/AutoClose']
        options={}
        if os.name=='nt':
            startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0;options=dict(startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
        completed=subprocess.run(command,cwd=folder,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=False,**options)
        if completed.returncode or not movie.is_file():raise RuntimeError('RAD did not produce Bink1')
    previous=json.loads(report_path.read_text('utf-8')) if verify_only and report_path.exists() else {}
    report=verify(folder,manifest,movie);now=time.strftime('%Y-%m-%d %H:%M:%S')
    encoder=previous.get('encoder') if verify_only else dict(name='RAD Video Tools',version='2026.10',file=TOOL.relative_to(ROOT).as_posix(),sha256=digest(TOOL),command=command)
    report.update(created=previous.get('created',now),verified_at=now,encoder=encoder,verifier=dict(script='scripts/encode_dragon_buff_v03.py',sha256=digest(Path(__file__)),snapshot='frozen_code/encode_dragon_buff_v03.py'))
    save(report_path,report);print(json.dumps(dict(file=movie.relative_to(ROOT).as_posix(),sha256=report['sha256'],bytes=report['size'],verified=True,frames=19,fps=15,alpha_mae_mean=report['quality']['alpha_mae_mean'],alpha_mae_worst=report['quality']['alpha_mae_worst'],source_alpha_ranges=report['quality']['source_alpha_ranges'][:5],decoded_alpha_ranges=report['quality']['alpha_ranges'][:5]),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify-only',action='store_true');a=p.parse_args();encode(a.verify_only)
