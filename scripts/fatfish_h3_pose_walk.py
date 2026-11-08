"""One bounded native H3 FL2VA + Fun Pose ControlNet experiment."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from fatfish_h3_walk import ROOT, STUDIO, SKILL, load_runner, memory, read, save, sha

RUN = ROOT/'design/fatfish/h3_pose_walk_v01'
OUT = ROOT/'output/Fatfish_H3_Pose_Walk_v01'
CORE = STUDIO/'install/ComfyUI/ComfyUI'
REF = ROOT/'design/fatfish/h3_walk_v01/references/same_grok_letterboxed_608x352.png'
TRACE = ROOT/'design/fatfish/local_walk_control_v01/source_motion.json'
PATCH = 'minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors'
WIDTH, HEIGHT, LENGTH, FPS, CYCLE = 608, 352, 124, 24, 24


def encoder(path, frames, fps=FPS):
    """Stream RGB frames to ffmpeg; no complete raw-video allocation."""
    it = iter(frames)
    first = next(it)
    w, h = first.size
    cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24',
           '-s',f'{w}x{h}','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264',
           '-crf','12','-preset','fast','-pix_fmt','yuv420p','-movflags','+faststart',str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        p.stdin.write(first.convert('RGB').tobytes())
        for frame in it:
            assert frame.size == (w,h)
            p.stdin.write(frame.convert('RGB').tobytes())
        p.stdin.close()
        error = p.stderr.read()
        if p.wait():
            raise RuntimeError(error.decode('utf-8','replace'))
    finally:
        if p.poll() is None:
            p.kill()


def smooth(values, phase):
    i, t = int(np.floor(phase)), phase % 1
    a,b,c,d = [values[(i+j)%10] for j in [-1,0,1,2]]
    return .5*(2*b+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t)


def renderer():
    source = CORE/'comfy_extras/pose/keypoint_draw.py'
    spec = importlib.util.spec_from_file_location('h3_official_pose_draw',source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.KeypointDraw()


def prepare():
    if (RUN/'job.json').exists():
        raise FileExistsError('Frozen experiment exists. Resume it instead of creating another.')
    for d in ['input','poses','original','qa','evidence']:
        (RUN/d).mkdir(parents=True,exist_ok=True)
    OUT.mkdir(parents=True,exist_ok=True)
    data = read(TRACE)
    values = np.array([s['world_keypoints'] for s in data['sources']])
    assert values.shape == (10,14,2)
    kd = renderer()
    rows = []
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17)
    sheet = Image.new('RGB',(1760,780),'#1a293b')
    draw = ImageDraw.Draw(sheet)
    # The same fixed map as the previous H3 input: world (186,272) in a
    # 128px square -> 352px square, then fixed 128px horizontal padding.
    def map_points(points):
        return (points-np.array([186.,272.]))*2.75+np.array([128.,0.])
    def pose(points):
        canvas = np.zeros((HEIGHT,WIDTH,3),dtype=np.uint8)
        kd.draw_wholebody_keypoints(canvas,points,draw_body=True,draw_head=True,
            draw_feet=False,draw_face=False,draw_hands=False,stick_width=3,
            marker_radius=3,limb_alpha=.6)
        return Image.fromarray(canvas)
    def with_head(points):
        # Sprite eyes/ears are ambiguous at native resolution. These four head
        # points are estimated, not outputs from a pose detector.
        nose=points[0]
        return np.concatenate([points,np.array([nose+[1,-3],nose+[-3,-3],nose+[2,-1],nose+[-6,-2]])])
    for i in range(10):
        src=Image.open(data['sources'][i]['source_png']).convert('RGBA')
        assert sha(data['sources'][i]['source_png'])==data['sources'][i]['sha256']
        viewport=Image.new('RGBA',(128,128),(128,128,128,255))
        # Composite PNGs store x in the cropped layer canvas. The existing
        # source traces use the shared world canvas with x offset +185.
        viewport.alpha_composite(src,(185-186,-272))
        canvas=Image.new('RGB',(WIDTH,HEIGHT),(128,128,128))
        canvas.paste(viewport.convert('RGB').resize((352,352),Image.Resampling.NEAREST),(128,0))
        canvas.save(RUN/f'original/{i:02d}.png')
        points=map_points(with_head(values[i]))
        skeleton=pose(points)
        skeleton.save(RUN/f'poses/source_{i:02d}.png')
        overlay=np.array(canvas)
        ink=np.array(skeleton);mask=ink.max(axis=2)>0
        overlay[mask]=ink[mask]
        x,y=(i%5)*352,(i//5)*390
        sheet.paste(Image.fromarray(overlay).crop((128,0,480,352)),(x,y+30))
        draw.text((x+8,y+3),f'原版 IMG {i} · 人工骨架',font=font,fill='#d1e7f7')
    sheet.save(RUN/'qa/source_pose_overlay.png')
    for f in range(LENGTH):
        phase=(2+f*10/CYCLE)%10
        points=map_points(with_head(smooth(values,phase)))
        skeleton=pose(points)
        skeleton.save(RUN/f'poses/{f:03d}.png')
        rows.append({'frame':f,'seconds':f/FPS,'source_phase':phase,
                     'body_keypoints_pixels':points.tolist()})
    encoder(RUN/'input/pose_control.mp4',(Image.open(RUN/f'poses/{f:03d}.png') for f in range(LENGTH)))
    encoder(RUN/'input/original_walk.mp4',(Image.open(RUN/f'original/{int(round(r["source_phase"]))%10:02d}.png') for r in rows))
    shutil.copy2(REF,RUN/'input/master.png')
    save(RUN/'motion.json',{'frames':rows,'source_slots':list(range(10)),
        'source_phase_at_start':2,'cycle_frames':CYCLE,'fps':FPS,
        'joint_method':'Reused manually traced IMG0..9; hidden joints and head landmarks are estimates.',
        'interpolation':'Periodic Catmull-Rom; no automatic pose-detector claims.',
        'registration':'Fixed world(186,272) -> 128px square ->352px; x padding128. No per-frame centering.',
        'original_ani_verified':False,'timing':'Experimental one-second cycle, not ANI-derived timing.',
        'draw_implementation_sha256':sha(CORE/'comfy_extras/pose/keypoint_draw.py'),
        'pose_color_and_topology':'Local official KeypointDraw DWPose/OpenPose18 renderer; body/head only.',
        'tail_hair_ears':'No tail or hair motion tracked by human skeleton; generated secondary motion.'})
    protected=[REF,ROOT/'design/fatfish/action_catalog/progress.json',
        ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK',
        ROOT/'design/fatfish/action_samples_v01/raw/idle_01_0.png',
        ROOT/'output/Fatfish_H3_Walk_v01/report.json']
    save(RUN/'spec.json',{'jobs_max':1,'new_motion_generations_max':1,
        'first_frame_only_plus_pose':True,'same_reference_and_seed_as_h3_baseline':True,
        'no_automatic_refine':True,'width':WIDTH,'height':HEIGHT,'length':LENGTH,
        'seed':20261023,'steps':20,'control_strength':1,'pose_cycle_seconds':1,
        'original_ani_verified':False,'protected_files_before':{str(p):sha(p) for p in protected}})
    print(json.dumps({'prepared_control':True,'frames':LENGTH,'preview':str(RUN/'qa/source_pose_overlay.png')}),flush=True)


def graph():
    prompt=(ROOT/'design/fatfish/h3_walk_v01/prompt.txt').read_text('utf-8')
    prompt+='\nMotion control: Follow the provided human pose control sequence throughout. The colored skeleton is an invisible motion guide, never draw it in the output. Keep the same whale-maid identity, fin ears, curled ahoge and a distinct whale tail. Match the wrist and ankle trajectories and timing, including alternating support legs. Preserve the original gray background and fixed full-body framing.'
    input_root=STUDIO/'shared/input/h3_pose_walk_v01'
    input_root.mkdir(parents=True,exist_ok=True)
    for name in ['master.png','pose_control.mp4']:
        shutil.copy2(RUN/'input'/name,input_root/name)
        assert sha(RUN/'input'/name)==sha(input_root/name)
    def n(kind,**inputs): return {'class_type':kind,'inputs':inputs}
    g={
        '1':n('UNETLoader',unet_name='minimax_h3_fl2va_pruned_w6a8.safetensors',weight_dtype='default'),
        '2':n('CLIPLoader',clip_name='qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors',type='minimax',device='default'),
        '3':n('VAELoader',vae_name='minimax_h3_video_vae_int8_convrot.safetensors'),
        '4':n('VAELoader',vae_name='minimax_h3_audio_vae_fp32.safetensors'),
        '5':n('LoadImage',image='h3_pose_walk_v01/master.png'),
        '6':n('MiniMaxH3ImageToVideo',clip=['2',0],vae=['3',0],prompt=prompt,
              width=WIDTH,height=HEIGHT,length=LENGTH,first_frame=['5',0]),
        '7':n('LoadVideo',file='h3_pose_walk_v01/pose_control.mp4'),
        '8':n('GetVideoComponents',video=['7',0]),
        '9':n('ModelPatchLoader',name=PATCH),
        '10':n('MiniMaxH3SigmaShift',model=['1',0],shift_video=12.0,shift_audio=3.0),
        '11':n('MiniMaxH3FunControlNetApply',model=['10',0],model_patch=['9',0],vae=['3',0],
               strength=1.0,start_percent=0.0,end_percent=1.0,control_video=['8',0]),
        '12':n('RandomNoise',noise_seed=20261023),
        '13':n('BasicGuider',model=['11',0],conditioning=['6',0]),
        '14':n('KSamplerSelect',sampler_name='euler'),
        '15':n('BasicScheduler',model=['11',0],scheduler='simple',steps=20,denoise=1.0),
        '16':n('SamplerCustomAdvanced',noise=['12',0],guider=['13',0],sampler=['14',0],sigmas=['15',0],latent_image=['6',1]),
        '17':n('VAEDecodeTiled',samples=['16',0],vae=['3',0],tile_size=256,overlap=64,temporal_size=32,temporal_overlap=8),
        '18':n('VAEDecodeAudio',samples=['16',0],vae=['4',0]),
        '19':n('CreateVideo',images=['17',0],audio=['18',0],fps=24),
        '20':n('SaveVideo',video=['19',0],filename_prefix='video/fatfish_h3_pose_walk_v01',format='auto',**{'format.codec':'auto'})
    }
    return g


def gui(g,schemas):
    nodes=[];links=[];idx=0
    for order,(ident,rec) in enumerate(g.items()):
        schema=schemas[rec['class_type']];inputs=[];widgets=[];named={}
        for name,value in rec['inputs'].items():
            if isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and value[0] in g:
                idx+=1
                typ=schemas[g[value[0]]['class_type']]['output'][value[1]]
                links.append([idx,int(value[0]),value[1],int(ident),len(inputs),typ])
                inputs.append({'name':name,'type':typ,'link':idx})
            else:
                widgets.append(value);named[name]=value
                if name=='noise_seed':widgets.append('fixed')
        outputs=[{'name':v,'type':v,'links':[]} for v in schema['output']]
        nodes.append({'id':int(ident),'type':rec['class_type'],'pos':[(order%5)*360,(order//5)*360],
            'size':[330,280],'flags':{},'order':order,'mode':0,'inputs':inputs,'outputs':outputs,
            'properties':{'Node name for S&R':rec['class_type']},'widgets_values':widgets,'widgets_values_named':named})
    byid={n['id']:n for n in nodes}
    for link in links:byid[link[1]]['outputs'][link[2]]['links'].append(link[0])
    return {'id':str(uuid.uuid4()),'revision':0,'last_node_id':20,'last_link_id':idx,
        'nodes':nodes,'links':links,'groups':[],'config':{},'extra':{},'version':.4}


def run():
    runner=load_runner();deadline=time.monotonic()+1800
    with runner.job_lock(STUDIO,deadline):
        stats,output_root=runner.ensure_server(STUDIO,deadline)
        available=memory()
        if available['ram_available_gib']<8 or available['commit_available_gib']<10:
            raise RuntimeError('Preserving task: insufficient RAM/commit headroom for new ControlNet path.')
        if not (RUN/'job.json').exists():
            receipt=read(RUN/'control_patch_receipt.json');assert receipt['verified']
            g=graph()
            schemas=runner.request('/object_info',timeout=30)
            # The skill's validator hardcodes Director node IDs. This native
            # extension uses its own schema checks, then backend validation.
            for ident,rec in g.items():
                if rec['class_type'] not in schemas:
                    raise RuntimeError('Missing native node: '+rec['class_type'])
                fields=schemas[rec['class_type']]['input']
                for name,definition in fields.get('required',{}).items():
                    if name not in rec['inputs']:
                        raise RuntimeError(f'Missing input {ident}.{name}')
                    choices=definition[0]
                    value=rec['inputs'][name]
                    if name not in ('image','file') and isinstance(choices,list) and not isinstance(value,list) and value not in choices:
                        raise RuntimeError(f'Unsupported value {ident}.{name}: {value}')
            save(RUN/'prompt.api.json',g);save(RUN/'workflow.json',gui(g,schemas))
            job={'job_id':'fatfish_pose_'+uuid.uuid4().hex,'mode':'one-pass','status':'prepared',
                 'profile':read(RUN/'spec.json'),'memory_before':available,
                 'backend_version':stats['system'].get('comfyui_version'),
                 'stages':[{'name':'pose_first','node':'20','width':WIDTH,'height':HEIGHT,
                            'client_id':str(uuid.uuid4()),'status':'prepared'}]}
            save(RUN/'job.json',job)
        job=read(RUN/'job.json')
        try:
            runner.execute_stage(RUN,job,job['stages'][0],read(RUN/'prompt.api.json'),
                                 read(RUN/'workflow.json'),output_root,deadline)
        except Exception as error:
            job.update(status='needs_attention',last_error=str(error));save(RUN/'job.json',job)
            raise
        job.update(status='completed',memory_after=memory());save(RUN/'job.json',job)
        print(json.dumps({'completed':True,'stage':job['stages'][0]},ensure_ascii=False),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run'])
    args=parser.parse_args()
    prepare() if args.action=='prepare' else run()
