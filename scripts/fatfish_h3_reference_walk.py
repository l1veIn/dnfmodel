"""One local Ref2VA walk with frozen human timings, appearance image, and RGB video."""
from __future__ import annotations
import argparse,copy,json,shutil,sys,threading,time,uuid
from pathlib import Path
import requests
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from fatfish_h3_walk import ROOT,STUDIO,read,save,sha,load_runner,memory
from fatfish_h3_pose_walk import gui,encoder

RUN=ROOT/'design/fatfish/h3_reference_walk_v01'
OUT=ROOT/'output/Fatfish_H3_Reference_Walk_v01'
WEB=ROOT/'output/Fatfish_Action_Dashboard'
MODEL='minimax_h3_ref2va_pruned_w6a8.safetensors'
W,H,N,FPS=608,352,124,24
HD=ROOT/'design/fatfish/action_samples_v01/raw/idle_01_0.png'

def original_frame(catalog,slot,square,pad,width):
    with Image.open(WEB/catalog['original'][str(slot)]) as source:
        # Existing fixed world window is [170,250,362,410]. Match the older
        # Pose comparison viewport [186,272,314,400], never per-frame bbox fit.
        window=source.convert('RGBA').crop((16,22,144,150))
        base=Image.new('RGBA',(128,128),(128,128,128,255));base.alpha_composite(window)
        canvas=Image.new('RGB',(width,square),(128,128,128))
        canvas.paste(base.convert('RGB').resize((square,square),Image.Resampling.NEAREST),(pad,0))
        return canvas

def prepare():
    if (RUN/'job.json').exists():raise FileExistsError('Frozen job exists; resume run instead of preparing a second sample.')
    RUN.mkdir(parents=True,exist_ok=True)
    for d in ['input','qa','source_frames']:(RUN/d).mkdir(exist_ok=True)
    catalog=read(WEB/'catalog.json');annotations=read(ROOT/'design/fatfish/action_catalog/manual_motion.json')
    clip=next(c for c in annotations['clips'] if c['name']=='默认走路')
    assert (clip['start'],clip['end'])==(0,9) and len(clip['frame_ms'])==10
    save(RUN/'annotations.snapshot.json',annotations)
    protected=[ROOT/'design/fatfish/action_catalog/manual_motion.json',ROOT/'design/fatfish/action_catalog/progress.json',ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK',HD,ROOT/'output/Fatfish_H3_Pose_Walk_v02/report.json']
    cumulative=np.cumsum(clip['frame_ms']);period=int(cumulative[-1]);mapping=[]
    for slot in range(clip['start'],clip['end']+1):original_frame(catalog,slot,352,128,608).save(RUN/f'source_frames/{slot:03d}.png')
    for i in range(N):
        phase=((i+.5)*1000/FPS)%period
        mapping.append({'frame':i,'source_slot':int(np.searchsorted(cumulative,phase,side='right'))+clip['start'],'source_cycle_ms':round(phase,3)})
    encoder(RUN/'input/original_timed_full.mp4',(Image.open(RUN/f'source_frames/{r["source_slot"]:03d}.png') for r in mapping))
    # 56 is the shortest H3-valid (17k+5) length above two seconds. The smaller
    # RGB reference keeps extra Ref2VA tokens bounded while retaining source pixels.
    encoder(RUN/'input/motion_reference.mp4',(original_frame(catalog,r['source_slot'],224,80,384) for r in mapping[:56]))
    shutil.copy2(HD,RUN/'input/appearance_original_rgba.png')
    with Image.open(HD) as im:
        rgba=im.convert('RGBA');gray=Image.new('RGBA',rgba.size,(128,128,128,255));gray.alpha_composite(rgba);gray.convert('RGB').save(RUN/'input/appearance_hd_gray.png')
    prompt=('Picture: Use <Picture 1> for the exact identity and costume of the blue whale maid. '
        'Use <Video 1> for the female mage walking motion: reproduce its torso and head movement, arm swing height, alternating leg poses, foot contacts and one-second gait rhythm. '
        'Replace the red-haired character from the motion reference with the whale maid from the picture. '
        'Full body, facing screen-right in three-quarter side view. A locked camera, no cuts, no zoom, uniform flat medium-gray background. '
        'Walk in place for the whole five-second shot, about five repetitions. Keep body size and framing steady. '
        'Preserve the whale fin ears, curled ahoge, long dark-to-light-blue hair, navy and white maid dress, gold trim, white stockings, and whale apron emblem. '
        'A separate dark-blue fleshy whale tail attaches behind the lower back and has a distinct fluke, separate from the skirt; it sways naturally behind the body. '
        'Hair, ears, ahoge, skirt and tail have small continuous secondary motion. Clean coherent anime sprite illustration, consistent face and outfit details. '
        'No original red hair or red costume, no weapons, no text, no extra people.\nSound: Quiet neutral room tone, no speech.\nScore: No music.')
    (RUN/'prompt.txt').write_text(prompt,'utf-8')
    input_dir=STUDIO/'shared/input/h3_reference_walk_v01';input_dir.mkdir(parents=True,exist_ok=True)
    for name in ['appearance_hd_gray.png','motion_reference.mp4']:
        shutil.copy2(RUN/'input'/name,input_dir/name);assert sha(RUN/'input'/name)==sha(input_dir/name)
    def node(kind,**inputs):return {'class_type':kind,'inputs':inputs}
    g={
      '1':node('UNETLoader',unet_name=MODEL,weight_dtype='default'),
      '2':node('CLIPLoader',clip_name='qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors',type='minimax',device='default'),
      '3':node('VAELoader',vae_name='minimax_h3_video_vae_int8_convrot.safetensors'),
      '4':node('VAELoader',vae_name='minimax_h3_audio_vae_fp32.safetensors'),
      '5':node('LoadImage',image='h3_reference_walk_v01/appearance_hd_gray.png'),
      '7':node('LoadVideo',file='h3_reference_walk_v01/motion_reference.mp4'),
      '8':node('GetVideoComponents',video=['7',0]),
      '6':node('MiniMaxH3ReferenceToVideo',clip=['2',0],vae=['3',0],prompt=prompt,width=W,height=H,length=N,ref_image_size='match',**{'ref_images.ref_image_0':['5',0],'ref_videos.ref_video_0':['8',0]}),
      '10':node('MiniMaxH3SigmaShift',model=['1',0],shift_video=12.0,shift_audio=3.0),
      '12':node('RandomNoise',noise_seed=20261023),
      '13':node('BasicGuider',model=['10',0],conditioning=['6',0]),
      '14':node('KSamplerSelect',sampler_name='euler'),
      '15':node('BasicScheduler',model=['10',0],scheduler='simple',steps=20,denoise=1.0),
      '16':node('SamplerCustomAdvanced',noise=['12',0],guider=['13',0],sampler=['14',0],sigmas=['15',0],latent_image=['6',1]),
      '21':node('LTXVSeparateAVLatent',av_latent=['16',0]),
      '22':node('SaveLatent',samples=['21',0],filename_prefix='latents/fatfish_h3_reference_walk_v01_video'),
      '23':node('SaveLatent',samples=['21',1],filename_prefix='latents/fatfish_h3_reference_walk_v01_audio'),
      '17':node('VAEDecodeTiled',samples=['22',0],vae=['3',0],tile_size=256,overlap=64,temporal_size=32,temporal_overlap=8),
      '18':node('VAEDecodeAudio',samples=['23',0],vae=['4',0]),
      '19':node('CreateVideo',images=['17',0],audio=['18',0],fps=FPS),
      '20':node('SaveVideo',video=['19',0],filename_prefix='video/fatfish_h3_reference_walk_v01',format='auto',**{'format.codec':'auto'})}
    schemas=load_runner().request('/object_info',timeout=30);workflow=gui(g,schemas);workflow['last_node_id']=23
    save(RUN/'prompt.api.json',g);save(RUN/'workflow.json',workflow)
    spec={'motion_generations_max':1,'two_pass':False,'pose_control':False,'input_mode':'Ref2VA appearance image plus RGB reference video',
      'annotation_revision':annotations['revision'],'manual_clip':clip,'annotations_sha256':sha(ROOT/'design/fatfish/action_catalog/manual_motion.json'),
      'all_clip_count':len(annotations['clips']),'reference_video':{'width':384,'height':224,'frames':56,'fps':24,'seconds':56/24,'crop_world':[186,272,314,400],'square_scale':1.75,'padding_x':80,'timing':'User annotations, held frames; no interpolation'},
      'appearance':{'source':str(HD),'source_sha256':sha(HD),'source_dimensions':[1024,1024],'background_only_composite':True,'node_ref_image_size':'match','effective_reference_dimensions':[448,448],'note':'The native node downsizes the original reference to the output pixel-area budget and rounds to32, yielding448 square; max2048 mode deliberately disabled for memory.'},
      'output':{'width':W,'height':H,'frames':N,'fps':FPS,'steps':20,'seed':20261023},'source_mapping':mapping,
      'protected_files':{str(p):sha(p) for p in protected},'strict_ab_test':False,'comparison_limit':'New checkpoint, full RGB motion reference, and HD appearance differ from old weak Pose / Grok inputs; timings are user annotations, not parsed ANI.'}
    save(RUN/'spec.json',spec)
    save(RUN/'job.json',{'job_id':'fatfish_reference_'+uuid.uuid4().hex,'status':'prepared','mode':'one-pass','frozen_api_sha256':sha(RUN/'prompt.api.json'),'frozen_gui_sha256':sha(RUN/'workflow.json'),
      'stages':[{'name':'execute','node':'20','width':W,'height':H,'client_id':str(uuid.uuid4()),'status':'prepared'}]})
    print(json.dumps({'prepared':True,'annotation_revision':annotations['revision'],'reference_frames':56,'output_frames':124,'input_image_sha256':sha(input_dir/'appearance_hd_gray.png'),'input_video_sha256':sha(input_dir/'motion_reference.mp4')},ensure_ascii=True),flush=True)

def guard(stop):
    with (RUN/'memory_guard.jsonl').open('a',encoding='utf-8') as f:
        while not stop.is_set():
            sample={'time':time.time(),**memory()};f.write(json.dumps(sample)+'\n');f.flush()
            if sample['ram_available_gib']<1.5 or sample['commit_available_gib']<1.5:
                job=read(RUN/'job.json');ident=job['stages'][0].get('prompt_id')
                if ident:
                    q=requests.get('http://127.0.0.1:8188/queue',timeout=10).json().get('queue_running',[])
                    if len(q)==1 and q[0][1]==ident:
                        requests.post('http://127.0.0.1:8188/interrupt',json={},timeout=10).raise_for_status();save(RUN/'memory_abort.json',{**sample,'interrupted_own_job':ident});break
            stop.wait(2)

def run():
    receipt=read(RUN/'model_receipt.json');assert receipt['verified']
    runner=load_runner();deadline=time.monotonic()+2400
    with runner.job_lock(STUDIO,deadline):
        stats,output_root=runner.ensure_server(STUDIO,deadline);runner.wait_idle(deadline)
        available=memory()
        if available['ram_available_gib']<8 or available['commit_available_gib']<10:raise RuntimeError('Insufficient RAM/commit headroom; frozen task preserved.')
        # No other queued work is displaced; model cache is never globally cleared.
        job=read(RUN/'job.json');assert sha(RUN/'prompt.api.json')==job['frozen_api_sha256'];assert sha(RUN/'workflow.json')==job['frozen_gui_sha256']
        if job['status']=='completed':print(json.dumps({'already_completed':True,'videos':job['stages'][0]['videos']}));return
        job['memory_before']=available;job['backend']=stats;save(RUN/'job.json',job)
        stop=threading.Event();thread=threading.Thread(target=guard,args=(stop,),daemon=True);thread.start()
        try:
            runner.execute_stage(RUN,job,job['stages'][0],read(RUN/'prompt.api.json'),read(RUN/'workflow.json'),output_root,deadline)
            job.update(status='completed',memory_after=memory());save(RUN/'job.json',job)
        except Exception as e:job.update(status='needs_attention',last_error=str(e));save(RUN/'job.json',job);raise
        finally:stop.set();thread.join(timeout=5)
        print(json.dumps({'completed':True,'videos':job['stages'][0]['videos'],'seconds':job['stages'][0].get('elapsed_seconds')},ensure_ascii=True),flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);a=p.parse_args();prepare() if a.action=='prepare' else run()
