"""Serial, resumable production of the user's 25 female-mage action segments."""
from __future__ import annotations
import argparse,copy,json,shutil,subprocess,sys,threading,time,uuid
from pathlib import Path
import requests
import numpy as np
from PIL import Image
from fatfish_h3_walk import ROOT,STUDIO,read,save,sha,load_runner,memory
from fatfish_h3_pose_walk import gui,encoder

RUN=ROOT/'design/fatfish/full_ref2va_v01'
OUT=ROOT/'output/Fatfish_Complete_v01'
WEB=ROOT/'output/Fatfish_Action_Dashboard'
TRIAL=WEB/'trials/full_ref2va_v01'
BASE=ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK'
HD=ROOT/'design/fatfish/h3_reference_walk_v01/input/appearance_hd_gray.png'
CYCLIC={0,10,14,18,53,155,163}
DESCRIPTIONS={0:'Walk in place with alternating long steps and arm swings.',10:'Stand relaxed and breathe gently, feet planted, tiny head and hair motion, no walking.',14:'Hold the combat-ready stance and breathe, both hands ready, feet planted.',18:'Run briskly in place with a forward torso lean and strongly alternating arms and legs.',22:'Perform the short forward lunge and shoulder-forward dash poses, reaching and leaning exactly as in the reference.',26:'Lunge, lose balance and fall forwards, ending lying horizontally on the ground. Show the full fall and the final prone pose, not just walking.',35:'Perform the broad two-handed melee sweep, twist the torso and extend both hands to the right as shown in the reference.',42:'Perform a summoning gesture, gathering both hands and raising the arms high overhead exactly as in the source.',53:'Stay crouched low with bent knees and torso folded, head lowered, matching the crouching reference; do not stand upright.',55:'Gather magic with the hand, then extend and throw with the arm, following the charge and release poses.',62:'Perform the multi-stage palm strike, turning the torso and pushing the hand forward, then recovering.',76:'Perform the crouch, takeoff posture, tucked legs and landing poses for a jump. Keep the sprite root framing from the reference; the game supplies actual world travel.',84:'Perform the aerial attack poses with tucked and extended legs and sweeping arms in the source order. The game supplies actual world travel.',97:'Follow the exact multi-stage rapid arm thrusts, torso twists and extended-arm motions from the reference sequence.',109:'Perform the three successive basic melee attacks, including the arm and torso changes and finishing recovery, following all three phases.',128:'Recoil and flinch from being hit, with head and torso thrown back in the two source poses, not a normal standing idle.',130:'Recoil from a hit and fall backwards onto the ground, ending lying horizontally as shown in the final source frames.',135:'Perform the low magic-missile casting poses, extend the hands and twist the torso in the exact order shown.',144:'Perform the short self-buff casting gesture, bringing the hands up around the chest and head as in the reference.',148:'Perform the broad two-handed whipping or sweeping attack, twist the torso and extend the hands according to the reference.',155:'Bend the torso far forward and crouch, repeatedly reaching down with both hands as if repairing an object on the ground; no actual object is visible.',158:'Perform the sequence of winding up and throwing an item with the arm, leaning and reaching to the right as shown; no item remains visible.',163:'Lean and bend the torso while working with both hands, matching the source repair gesture and shifted body location.',166:'Perform the summoning-hand gestures, extending the arm and then raising and gathering the hands as in the reference.',170:'Raise both arms high above the head for a dispelling gesture, then lower them, with the torso and leg poses matching the source.'}

def publish(data):
    save(RUN/'production.json',data);save(OUT/'production.json',data);save(TRIAL/'production.json',data)
    print(json.dumps({'production':data['status'],'generated':sum(c['status'] in ['generated','processed','packaged'] for c in data['clips']),'processed':sum(c['status'] in ['processed','packaged'] for c in data['clips']),'clips':len(data['clips'])}),flush=True)
def prepare():
    if (RUN/'production.json').exists():return
    for d in [RUN,OUT,TRIAL]:d.mkdir(parents=True,exist_ok=True)
    annotations=read(ROOT/'design/fatfish/action_catalog/manual_motion.json');slots=[s for c in annotations['clips'] for s in range(c['start'],c['end']+1)]
    assert sorted(slots)==list(range(174)) and len(slots)==174
    save(RUN/'annotations.snapshot.json',annotations)
    protected=[ROOT/'design/fatfish/action_catalog/manual_motion.json',ROOT/'design/fatfish/action_catalog/progress.json',BASE,ROOT/'design/fatfish/action_samples_v01/raw/idle_01_0.png']
    save(RUN/'spec.json',{'scope':'All174 template slots across the25 user-labelled segments; default-avatar carrier, not every paid costume or separate class-effect IMG.',
      'annotation_revision':annotations['revision'],'protected_files':{str(p):sha(p) for p in protected},'local_only':True,'serial_gpu':True,'model':'minimax_h3_ref2va_pruned_w6a8.safetensors',
      'output_dimensions':[608,352],'output_frames':124,'fps':24,'steps':20,'refinement':False,'appearance':str(HD),'appearance_sha256':sha(HD),
      'reference_dimensions':[320,192],'reference_frames':124,'reference_camera_world':[143.3333333333,272,356.6666666667,400],
      'npk_geometry':'Native500px world canvas; preserve antialiasing when resizing, no palette quantization. Source/HD frames supplied separately.',
      'user_authorization':'我觉得可以了，来吧，完成一次闭关吧，填满我们的动作工作台，制作一个完整的 npk'})
    clips=[]
    for c in sorted(annotations['clips'],key=lambda c:c['start']):
        clips.append({'id':f'clip_{c["start"]:03d}_{c["end"]:03d}','name':c['name'],'start':c['start'],'end':c['end'],'frame_ms':c['frame_ms'],'user_loop':c['loop'],'cycle':c['start'] in CYCLIC,'status':'pending','attempts':[],'available_slots':[]})
    publish({'version':1,'status':'prepared','started_at':time.time(),'updated_at':time.time(),'scope_slots':174,'annotation_revision':annotations['revision'],'clips':clips,'package':None,'game_runtime_validated':False})

def reference_frame(slot):
    source=ROOT/f'materials/female_mage/reference_composite/frames/{slot:04d}.png'
    with Image.open(source) as im:
        world=Image.new('RGBA',(500,500),(128,128,128,255));world.alpha_composite(im.convert('RGBA'),(185,0))
        return world.convert('RGB').transform((320,192),Image.Transform.AFFINE,(2/3,0,143.3333333333333,0,2/3,272),resample=Image.Resampling.NEAREST)

def prepare_job(c,attempt=1):
    folder=RUN/'jobs'/c['id']/f'attempt_{attempt:02d}'
    if (folder/'job.json').exists():return folder
    (folder/'input').mkdir(parents=True,exist_ok=True)
    cumulative=np.cumsum(c['frame_ms']);period=int(cumulative[-1]);mapping=[]
    for i in range(124):
        if c['cycle']:
            cycle_frames=48 if c['start'] in [10,14,53,155,163] else 24
            phase=(i%cycle_frames+.5)/cycle_frames*period
        else:phase=np.clip((i-12+.5)/96,0,1-1e-9)*period
        index=min(len(cumulative)-1,int(np.searchsorted(cumulative,phase,side='right')))
        mapping.append({'video_frame':i,'source_slot':c['start']+index,'source_time_ms':round(float(phase),3)})
    encoder(folder/'input/motion.mp4',(reference_frame(r['source_slot']) for r in mapping))
    shutil.copy2(HD,folder/'input/appearance.png')
    shared=STUDIO/'shared/input/fatfish_full_v01'/c['id']/f'attempt_{attempt:02d}';shared.mkdir(parents=True,exist_ok=True)
    for f in ['motion.mp4','appearance.png']:shutil.copy2(folder/'input'/f,shared/f);assert sha(folder/'input'/f)==sha(shared/f)
    neutral={55:'Raise both empty hands above the head, lean the head and torso backwards, then extend both arms forward while lifting and bending both legs as in the reference. Animate only the body, never any energy.',135:'Follow the low bent-knee empty-hand gestures, reaching the hands forward and turning the torso in source order.',144:'Follow the short empty-hand arm gesture, bringing the hands up around the chest and head as in the reference.',170:'Raise both empty hands high above the head, then lower them, with torso and legs matching the source.'}
    motion=neutral.get(c['start'],DESCRIPTIONS[c['start']])
    prompt=('Picture: Use <Picture 1> for the exact blue whale-maid identity and costume. Use <Video 1> as the complete motion and pose timeline. Replace only the character appearance in the video with the whale maid. '
      +motion+' Match the source torso tilt, head orientation, arm height, hand trajectory, leg bends, horizontal or upright body orientation, and fixed root framing. '
      +('Repeat this one action smoothly with natural secondary motion.' if c['cycle'] else 'Perform the whole sequence once in source order and finish holding the final source pose. Do not replace this action with walking or idle.')
      +' Keep the whale fin ears, curled ahoge, long dark-to-light blue hair, navy and white maid dress with gold trim, white stockings, navy shoes, white whale-emblem apron, and a distinct fleshy navy whale tail behind the lower back with a clear fluke. '
      'The tail is separate from the skirt. Keep the face and outfit consistent, including when bending or falling. Hair, ears, ahoge and tail react naturally to body movement. '
      'Locked camera, full body always visible, flat uniform medium-gray background, no ground shadows, no scene, no cuts, no zoom, no extra people, no red hair or red costume, no weapons, no generated spell effects, no text. Clean coherent anime game sprite illustration.\nSound: Quiet neutral room tone, no speech.\nScore: No music.')
    (folder/'prompt.txt').write_text(prompt,'utf-8')
    g=copy.deepcopy(read(ROOT/'design/fatfish/h3_reference_walk_v01/prompt.api.json'))
    g['5']['inputs']['image']=shared.relative_to(STUDIO/'shared/input').as_posix()+'/appearance.png'
    g['7']['inputs']['file']=shared.relative_to(STUDIO/'shared/input').as_posix()+'/motion.mp4'
    g['6']['inputs']['prompt']=prompt;g['12']['inputs']['noise_seed']=20261024+c['start']+attempt-1
    prefix=f'fatfish_full_v01/{c["id"]}_a{attempt:02d}'
    g['20']['inputs']['filename_prefix']='video/'+prefix
    for k,label in [('22','video'),('23','audio')]:g[k]['inputs']['filename_prefix']='latents/'+prefix+'_'+label
    runner=load_runner();schemas=runner.request('/object_info',timeout=30);workflow=gui(g,schemas);workflow['last_node_id']=23
    save(folder/'prompt.api.json',g);save(folder/'workflow.json',workflow);save(folder/'reference_mapping.json',{'clip':c,'mapping':mapping,'fps':24,'reference_frames':124,'same_duration_as_output':True,'source_time_stretched_for_generation':True})
    save(folder/'job.json',{'job_id':'fatfish_full_'+c['id']+'_'+uuid.uuid4().hex,'status':'prepared','mode':'one-pass','frozen_api_sha256':sha(folder/'prompt.api.json'),'frozen_gui_sha256':sha(folder/'workflow.json'),
      'stages':[{'name':'execute','node':'20','width':608,'height':352,'client_id':str(uuid.uuid4()),'status':'prepared'}]})
    return folder

def guard(folder,stop):
    with (folder/'memory_guard.jsonl').open('a',encoding='utf-8') as f:
        while not stop.is_set():
            row={'time':time.time(),**memory()};f.write(json.dumps(row)+'\n');f.flush()
            if row['ram_available_gib']<1.5 or row['commit_available_gib']<1.5:
                ident=read(folder/'job.json')['stages'][0].get('prompt_id')
                if ident:
                    q=requests.get('http://127.0.0.1:8188/queue',timeout=10).json().get('queue_running',[])
                    if len(q)==1 and q[0][1]==ident:
                        requests.post('http://127.0.0.1:8188/interrupt',json={},timeout=10).raise_for_status();save(folder/'memory_abort.json',row);return
            stop.wait(2)
def execute(folder):
    runner=load_runner();deadline=time.monotonic()+2400
    with runner.job_lock(STUDIO,deadline):
        stats,output_root=runner.ensure_server(STUDIO,deadline);runner.wait_idle(deadline)
        available=memory()
        if available['ram_available_gib']<8 or available['commit_available_gib']<10:raise RuntimeError('Insufficient memory headroom; resume after resources recover.')
        job=read(folder/'job.json');assert sha(folder/'prompt.api.json')==job['frozen_api_sha256'] and sha(folder/'workflow.json')==job['frozen_gui_sha256']
        if job['status']=='completed':return job
        job['memory_before']=available;save(folder/'job.json',job)
        stop=threading.Event();thread=threading.Thread(target=guard,args=(folder,stop),daemon=True);thread.start()
        try:
            runner.execute_stage(folder,job,job['stages'][0],read(folder/'prompt.api.json'),read(folder/'workflow.json'),output_root,deadline)
            job.update(status='completed',memory_after=memory());save(folder/'job.json',job);return job
        except Exception as e:job.update(status='needs_attention',last_error=str(e));save(folder/'job.json',job);raise
        finally:stop.set();thread.join(timeout=5)

def process(c):
    script=ROOT/'scripts/process_full_ref2va.py'
    if script.exists():subprocess.run([sys.executable,str(script),c['id']],check=True)
def run(only=None,repair=False):
    prepare();data=read(RUN/'production.json');data['status']='generating';publish(data)
    order=sorted(data['clips'],key=lambda c:({10:-4,14:-3,0:-2,18:-1}.get(c['start'],c['start'])))
    for c in order:
        if only and c['id']!=only:continue
        data=read(RUN/'production.json');c=next(v for v in data['clips'] if v['id']==c['id'])
        if (RUN/'PAUSE_BATCH').exists():data['status']='paused_by_control_file';publish(data);return
        if c['status'] in ['generated','processed','packaged'] and not repair:
            if c['status']=='generated':process(c)
            continue
        if c['start']==0 and not repair:
            old=read(ROOT/'design/fatfish/h3_reference_walk_v01/job.json');c.update(status='generated',video=old['stages'][0]['videos'][0],job_folder=str(ROOT/'design/fatfish/h3_reference_walk_v01'),reuse='User accepted Ref2VA walk baseline');publish(data);process(c);continue
        attempt=len(c['attempts'])+1 if repair else max(1,len(c['attempts']))
        folder=prepare_job(c,attempt)
        if str(folder) not in c['attempts']:c['attempts'].append(str(folder))
        c.update(status='generating',job_folder=str(folder));publish(data)
        try:
            job=execute(folder);c.update(status='generated',video=job['stages'][0]['videos'][0],seconds=job['stages'][0]['elapsed_seconds']);publish(data);process(c)
        except Exception as e:
            data=read(RUN/'production.json');row=next(v for v in data['clips'] if v['id']==c['id']);row.update(status='failed',error=str(e));data['status']='needs_attention';publish(data);raise
    data=read(RUN/'production.json');data['status']='generated' if all(c['status'] in ['generated','processed','packaged'] for c in data['clips']) else 'in_progress';publish(data)
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('--only');p.add_argument('--repair',action='store_true');a=p.parse_args();prepare() if a.action=='prepare' else run(a.only,a.repair)
