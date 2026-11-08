"""Serial decoder diagnosis, then one relaxed-Pose walk sample. No batch."""
from __future__ import annotations
import argparse
import copy
import json
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path
import requests
import numpy as np
from PIL import Image,ImageDraw,ImageFont

from fatfish_h3_walk import ROOT,STUDIO,load_runner,memory,read,save,sha
from fatfish_h3_pose_walk import gui,renderer,encoder,smooth

RUN=ROOT/'design/fatfish/h3_pose_walk_v02'
OUT=ROOT/'output/Fatfish_H3_Pose_Walk_v02'
OLD=ROOT/'design/fatfish/h3_pose_walk_v01'


def freeze(name,g,extra):
    folder=RUN/name;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'job.json').exists():raise FileExistsError('Use existing frozen job; do not overwrite.')
    runner=load_runner();schemas=runner.request('/object_info',timeout=30)
    workflow=gui(g,schemas);workflow['last_node_id']=max(map(int,g))
    save(folder/'prompt.api.json',g);save(folder/'workflow.json',workflow)
    job={'job_id':'fatfish_'+name+'_'+uuid.uuid4().hex,'mode':'one-pass','status':'prepared',
         'frozen_api_sha256':sha(folder/'prompt.api.json'),'frozen_gui_sha256':sha(folder/'workflow.json'),
         'stages':[{'name':'execute','node':'20','width':608,'height':352,
                    'client_id':str(uuid.uuid4()),'status':'prepared'}],**extra}
    save(folder/'job.json',job)
    print(json.dumps({'prepared':name,'nodes':len(g)}),flush=True)


def prepare_probe():
    RUN.mkdir(parents=True,exist_ok=True)
    protected=[ROOT/'design/fatfish/action_catalog/progress.json',
        ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK',
        ROOT/'output/Fatfish_H3_Pose_Walk_v01/report.json',
        ROOT/'design/fatfish/action_samples_v01/raw/idle_01_0.png']
    if not (RUN/'spec.json').exists():
        save(RUN/'spec.json',{'stages':'Decoder probe first; one relaxed-motion generation second.',
            'max_new_motion_samples':1,'max_reproduction_samples':1,
            'cache_unavailable_reason':'Server cache-none; original native graph did not save latent.',
            'original_ani_verified':False,'protected_files':{str(p):sha(p) for p in protected}})
    g=read(OLD/'prompt.api.json')
    def node(kind,**inputs):return {'class_type':kind,'inputs':inputs}
    # Reproduce original sampling inputs exactly; both decoders consume one saved
    # video latent. No video re-encoding is used to reconstruct a latent.
    g['21']=node('LTXVSeparateAVLatent',av_latent=['16',0])
    g['22']=node('SaveLatent',samples=['21',0],filename_prefix='latents/fatfish_h3_pose_decoder_v02_video')
    g['23']=node('SaveLatent',samples=['21',1],filename_prefix='latents/fatfish_h3_pose_decoder_v02_audio')
    tiled=copy.deepcopy(g['17'])
    g['17']=node('VAEDecode',samples=['22',0],vae=['3',0])
    g['20']['inputs']['filename_prefix']='video/fatfish_decoder_v02_normal'
    tiled['inputs']['samples']=['22',0];g['30']=tiled
    g['31']=node('CreateVideo',images=['30',0],audio=['18',0],fps=24)
    g['33']=node('SaveVideo',video=['31',0],filename_prefix='video/fatfish_decoder_v02_tiled',format='auto',**{'format.codec':'auto'})
    g['34']=node('SaveImage',images=['17',0],filename_prefix='fatfish_decoder_v02/normal')
    g['35']=node('SaveImage',images=['30',0],filename_prefix='fatfish_decoder_v02/tiled')
    assert all(g[k]==read(OLD/'prompt.api.json')[k] for k in map(str,range(1,17)))
    freeze('decoder_probe',g,{'sampling_reproduction':True,'new_motion':False,'original_cache_reused':False,
        'same_reproduced_latent_both_decoders':True,'normal_node':'17','tiled_node':'30',
        'normal_png_node':'34','tiled_png_node':'35','secondary_video_node':'33'})


def guard(folder,stop):
    with (folder/'memory_guard.jsonl').open('a',encoding='utf-8') as output:
        while not stop.is_set():
            sample={'time':time.time(),**memory()};output.write(json.dumps(sample)+'\n');output.flush()
            if sample['commit_available_gib']<1.25 or sample['ram_available_gib']<1.5:
                job=read(folder/'job.json');ident=job['stages'][0].get('prompt_id')
                if ident:
                    q=requests.get('http://127.0.0.1:8188/queue',timeout=10).json().get('queue_running',[])
                    if len(q)==1 and q[0][1]==ident:
                        requests.post('http://127.0.0.1:8188/interrupt',json={},timeout=10).raise_for_status()
                        sample['interrupted_own_job']=ident;save(folder/'memory_abort.json',sample);break
            stop.wait(2)


def run(name):
    folder=RUN/name;runner=load_runner();deadline=time.monotonic()+1800
    with runner.job_lock(STUDIO,deadline):
        stats,output_root=runner.ensure_server(STUDIO,deadline)
        runner.wait_idle(deadline)
        available=memory()
        if available['ram_available_gib']<8 or available['commit_available_gib']<10:
            raise RuntimeError('Low memory headroom; preserve frozen task for resuming.')
        job=read(folder/'job.json')
        assert sha(folder/'prompt.api.json')==job['frozen_api_sha256']
        assert sha(folder/'workflow.json')==job['frozen_gui_sha256']
        job['memory_before']=available;save(folder/'job.json',job)
        stop=threading.Event();monitor=threading.Thread(target=guard,args=(folder,stop),daemon=True);monitor.start()
        try:
            runner.execute_stage(folder,job,job['stages'][0],read(folder/'prompt.api.json'),read(folder/'workflow.json'),output_root,deadline)
            if job.get('secondary_video_node'):
                h=read(folder/'execute/history.json');job['secondary_videos']=runner.videos_for_node(h,job['secondary_video_node'],output_root)
            job.update(status='completed',memory_after=memory());save(folder/'job.json',job)
        except Exception as error:
            job.update(status='needs_attention',last_error=str(error));save(folder/'job.json',job);raise
        finally:
            stop.set();monitor.join(timeout=5)
        print(json.dumps({'finished':name,'videos':job['stages'][0].get('videos'),'secondary':job.get('secondary_videos')},ensure_ascii=False),flush=True)


def inspect_probe():
    folder=RUN/'decoder_probe';job=read(folder/'job.json')
    assert job['status']=='completed'
    h=read(folder/'execute/history.json');output_root=STUDIO/'shared/output'
    def paths(node,key):
        records=h['outputs'][node][key]
        result=[output_root/r.get('subfolder','')/r['filename'] for r in records]
        assert all(p.resolve().is_relative_to(output_root.resolve()) and p.is_file() for p in result)
        return result
    normal,tiled=paths('34','images'),paths('35','images')
    assert len(normal)==len(tiled)==124
    selected=[0,54,62,123];board=Image.new('RGB',(1056,1536),'#192a3b')
    draw=ImageDraw.Draw(board);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17)
    errors=[];digests=[]
    for i,(a,b) in enumerate(zip(normal,tiled)):
        x=np.asarray(Image.open(a).convert('RGB'));y=np.asarray(Image.open(b).convert('RGB'))
        delta=np.abs(x.astype('int16')-y.astype('int16'))
        errors.append({'frame':i,'max':int(delta.max()),'mae':float(delta.mean()),'different_values':int(np.count_nonzero(delta))})
        import hashlib
        digests.append({'frame':i,'normal_pixels_sha256':hashlib.sha256(x.tobytes()).hexdigest(),'tiled_pixels_sha256':hashlib.sha256(y.tobytes()).hexdigest()})
        if i in selected:
            row=selected.index(i)
            for col,(im,label) in enumerate([(Image.fromarray(x),'普通解码'),(Image.fromarray(y),'分块解码'),(Image.fromarray(np.minimum(delta*8,255).astype('uint8')),'差异×8 · 黑色=相同')]):
                board.paste(im.crop((128,0,480,352)),(col*352,row*384+30))
                draw.text((col*352+7,row*384+3),f'{label} / 帧{i}',font=font,fill='#d7edff')
    qa=RUN/'qa';qa.mkdir(exist_ok=True);board.save(qa/'decoder_same_latent_comparison.png')
    video_latent=paths('22','latents')[0];audio_latent=paths('23','latents')[0]
    report={'original_cache_reused':False,'reason':'Backend cache-none and no latent saved in v01.',
        'sampling_reproduced_once_from_frozen_v01_inputs':True,'seed':20261023,
        'same_latent_consumed_by_both_decoders':True,
        'video_latent':str(video_latent),'video_latent_sha256':sha(video_latent),
        'audio_latent':str(audio_latent),'audio_latent_sha256':sha(audio_latent),
        'normal_video':job['stages'][0]['videos'][0],'tiled_video':job['secondary_videos'][0],
        'frames_compared':124,'lossless_png_comparison':True,
        'all_pixels_identical':all(e['max']==0 for e in errors),'max_rgb_error':max(e['max'] for e in errors),
        'mean_absolute_rgb_error':float(np.mean([e['mae'] for e in errors])),
        'per_frame':errors,'pixel_digests':digests,
        'native_implementation':'MiniMaxH3VideoVAE.decode_tiled delegates to decode; internal H3 chunking remains enabled.',
        'elapsed_seconds':job['stages'][0]['elapsed_seconds']}
    save(folder/'report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('per_frame','pixel_digests')},ensure_ascii=False),flush=True)


def prepare_motion():
    assert read(RUN/'decoder_probe/report.json')['all_pixels_identical']
    folder=RUN/'motion_relaxed';folder.mkdir(parents=True,exist_ok=True)
    if (folder/'job.json').exists():raise FileExistsError('An existing motion sample must be resumed.')
    for d in ['input','poses','qa']:(folder/d).mkdir(exist_ok=True)
    data=read(ROOT/'design/fatfish/local_walk_control_v01/source_motion.json')
    values=np.array([s['world_keypoints'] for s in data['sources']])
    # Re-traced upper-body landmarks in the source's world coordinates.
    # Pelvis points hidden by the skirt are anatomical estimates, not detected
    # ground truth. Small head roll is an authored motion correction.
    neck=np.array([[248,313],[251,314],[252,314],[249,314],[247,314],
                   [248,313],[250,313],[252,315],[250,314],[247,314]],float)
    rs=np.array([[250,316],[253,317],[254,317],[251,318],[249,318],
                 [250,317],[252,317],[254,318],[252,317],[249,316]],float)
    ls=np.array([[241,316],[244,318],[249,319],[245,317],[241,316],
                 [240,316],[243,317],[248,320],[245,319],[241,318]],float)
    pelvis=np.array([[248.5,343],[251,344],[254,345],[251,345],[250,345],
                     [250,344],[252,344],[252,346],[249,346],[248.5,345]],float)
    half=np.array([3.5,3,2,2.8,3.4,3.6,3,2.2,3,3.6])
    roll=np.array([.3,-.5,-.7,-.3,.2,.5,.6,.5,.3,-.1])
    head_degrees=np.array([-1.5,-.8,.4,1.8,2.2,1,0,-1.8,-2.2,-1.5])
    values[:,1]=neck;values[:,2]=rs;values[:,5]=ls
    values[:,8]=pelvis+np.stack([-half,roll],axis=1)
    values[:,11]=pelvis+np.stack([half,-roll],axis=1)
    # Eyes/ears carry slight head roll. A small authored head bob is added to
    # existing nose measurements; no framewise image warping is performed.
    detailed=[]
    for i in range(10):
        p=values[i].copy();a=np.deg2rad(head_degrees[i]);rotation=np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
        p[0]+=[0,.45*np.cos(4*np.pi*i/10)]
        offsets=np.array([[1,-3],[-3,-3],[2,-1],[-6,-2]])@rotation.T
        detailed.append(np.concatenate([p,p[0]+offsets]))
    detailed=np.asarray(detailed);kd=renderer();rows=[]
    def render_pose(world):
        points=(world-[186.,272.])*2.75+[128.,0.]
        canvas=np.zeros((352,608,3),'uint8')
        kd.draw_wholebody_keypoints(canvas,points,draw_body=True,draw_head=True,
            draw_feet=False,draw_face=False,draw_hands=False,stick_width=3,marker_radius=3,limb_alpha=.6)
        return Image.fromarray(canvas),points
    for f in range(124):
        phase=(2+f*10/24)%10;im,p=render_pose(smooth(detailed,phase));im.save(folder/f'poses/{f:03d}.png')
        rows.append({'frame':f,'source_phase':phase,'body_keypoints_pixels':p.tolist()})
    encoder(folder/'input/pose_control.mp4',(Image.open(folder/f'poses/{i:03d}.png') for i in range(124)))
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',16)
    board=Image.new('RGB',(1760,780),'#1b2b3c');draw=ImageDraw.Draw(board)
    for i in range(10):
        raw=Image.open(OLD/f'original/{i:02d}.png').convert('RGB');pose,_=render_pose(detailed[i]);ink=np.array(pose);a=np.array(raw)
        mask=ink.max(2)>0;a[mask]=ink[mask];x,y=i%5*352,i//5*390
        board.paste(Image.fromarray(a).crop((128,0,480,352)),(x,y+28));draw.text((x+6,y+3),f'IMG {i} · 补全躯干/头部',font=font,fill='#dcefff')
    board.save(folder/'qa/source_pose_overlay.png')
    array=np.array([r['body_keypoints_pixels'] for r in rows[:24]])
    save(folder/'motion.json',{'frames':rows,'manual_world_landmarks':detailed.tolist(),
        'source':'IMG0..9 visible shoulder/neck positions manually retraced; hidden hips estimated.',
        'authored_correction':'Small head roll -2.2..2.2 degrees and head-bob amplitude0.45 native pixels.',
        'no_pose_detector_claim':True,'original_ani_verified':False,'cycle_frames':24,'fps':24,
        'joint_xy_ranges':{str(i):np.ptp(array[:,i],axis=0).tolist() for i in [0,1,2,5,8,11]},
        'tail_and_hair_not_in_human_skeleton':True})
    prompt='''Picture: A single full-body 2D whale-maid game character walks in place, facing the same three-quarter right direction as the supplied first frame. Preserve her identity and costume: blue eyes, long navy-to-cyan wavy hair, curled ahoge, whale-fin ears, white frilled headband, navy long-sleeved maid dress, white whale-emblem apron, gold trim, white tights and navy Mary Jane shoes. A separate whale tail extends behind her and remains visibly distinct from the skirt.
Follow the supplied body pose timing with alternating left and right steps. The pelvis shifts weight naturally; the chest and shoulders counter-rotate softly with the stride. The head follows with gentle vertical bob and subtle tilt. Arms and hands remain connected. Each foot plants briefly, moves backward during support and returns forward while lifted. Show a continuous repeated walk with no pause or pose change.
Hair moves in soft delayed waves following the torso; the ahoge bounces lightly. The separate whale tail sways smoothly with a small delayed counter-swing at its base and flexible fin movement. The skirt and apron respond gently to the gait. Keep face and clothing design recognizable while allowing their natural deformation with motion.
Locked camera, fixed overall framing and scale, full body and shoes visible, no travel across the canvas. Flat neutral gray background RGB(128,128,128), no scenery, cast shadow, text, extra characters or effects. Keep the supplied 2D pixel-art style and palette. Five walking cycles over this shot; continue walking through the final frame.
Sound: Soft room tone, no speech. Score: No music.'''
    (folder/'prompt.txt').write_text(prompt,encoding='utf-8')
    input_root=STUDIO/'shared/input/h3_pose_walk_v02';input_root.mkdir(parents=True,exist_ok=True)
    shutil.copy2(OLD/'input/master.png',input_root/'master.png');shutil.copy2(folder/'input/pose_control.mp4',input_root/'pose_control.mp4')
    g=read(OLD/'prompt.api.json')
    g['5']['inputs']['image']='h3_pose_walk_v02/master.png'
    g['6']['inputs']['prompt']=prompt;g['7']['inputs']['file']='h3_pose_walk_v02/pose_control.mp4'
    g['11']['inputs'].update(strength=.55,start_percent=0.,end_percent=.8)
    def n(kind,**inputs):return {'class_type':kind,'inputs':inputs}
    g['21']=n('LTXVSeparateAVLatent',av_latent=['16',0])
    g['22']=n('SaveLatent',samples=['21',0],filename_prefix='latents/fatfish_h3_pose_v02_motion_video')
    g['23']=n('SaveLatent',samples=['21',1],filename_prefix='latents/fatfish_h3_pose_v02_motion_audio')
    g['17']=n('VAEDecode',samples=['22',0],vae=['3',0])
    g['20']['inputs']['filename_prefix']='video/fatfish_h3_pose_v02_relaxed'
    g['24']=n('SaveImage',images=['17',0],filename_prefix='fatfish_pose_motion_v02/frame')
    freeze('motion_relaxed',g,{'sampling_reproduction':False,'new_motion':True,
        'strength':.55,'control_end_percent':.8,'same_old_reference_and_seed':True,
        'motion_changes_combined':True,'hd_reference_not_introduced':True})


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare_probe','run','inspect_probe','prepare_motion']);ap.add_argument('--job',default='decoder_probe')
    args=ap.parse_args()
    if args.action=='prepare_probe':prepare_probe()
    elif args.action=='inspect_probe':inspect_probe()
    elif args.action=='prepare_motion':prepare_motion()
    else:run(args.job)
