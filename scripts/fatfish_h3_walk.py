"""One local H3 first-frame comparison. Reuse the installed skill's locked runner."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT/'design/fatfish/h3_walk_v01'
OUT = ROOT/'output/Fatfish_H3_Walk_v01'
SKILL = Path('C:/Users/A/.codex/skills/minimax-h3-video')
STUDIO = Path('D:/VideoStudio/comfyUI')
GROK_REF = ROOT/'design/fatfish/grok_walk_v01/input/master_gray_1024.png'
GROK_VIDEO = ROOT/'output/Fatfish_Grok_Walk_v01/grok_walk_original.mp4'


def load_runner():
    spec = importlib.util.spec_from_file_location('installed_h3_runner',SKILL/'scripts/generate_video.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def memory():
    class MemoryStatus(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),
            ('total_phys',ctypes.c_ulonglong),('avail_phys',ctypes.c_ulonglong),
            ('total_page',ctypes.c_ulonglong),('avail_page',ctypes.c_ulonglong),
            ('total_virtual',ctypes.c_ulonglong),('avail_virtual',ctypes.c_ulonglong),
            ('avail_extended',ctypes.c_ulonglong)]
    m=MemoryStatus();m.length=ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return {'ram_available_gib':m.avail_phys/2**30,'commit_available_gib':m.avail_page/2**30,
            'commit_total_gib':m.total_page/2**30}


def upload(path):
    boundary='FatfishH3'+uuid.uuid4().hex
    name='fatfish_same_grok_'+sha(path)[:14]+'.png'
    chunks=[]
    for key,value in [('subfolder','h3_inputs'),('type','input'),('overwrite','false')]:
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: image/png\r\n\r\n'.encode())
    chunks.append(path.read_bytes());chunks.append(f'\r\n--{boundary}--\r\n'.encode())
    request=urllib.request.Request('http://127.0.0.1:8188/upload/image',data=b''.join(chunks),
            headers={'Content-Type':'multipart/form-data; boundary='+boundary})
    with urllib.request.urlopen(request,timeout=30) as response:
        result=json.load(response)
    actual=STUDIO/'shared/input'/result.get('subfolder','')/result['name']
    assert actual.is_file() and sha(actual)==sha(path)
    save(RUN/'upload.json',{'response':result,'actual_input_file':str(actual),
                          'uploaded_sha256':sha(actual),'verified_uploaded_bytes':True})
    return '/'.join(filter(None,[result.get('subfolder',''),result['name']]))


def sync_gui(workflow,prompt):
    for node in workflow['nodes']:
        api=prompt.get(str(node['id']))
        if not api or not isinstance(node.get('widgets_values_named'),dict):
            continue
        named=node['widgets_values_named']
        for i,key in enumerate(list(named)):
            if key in api['inputs']:
                value=api['inputs'][key]
                if isinstance(value,list):
                    continue
                named[key]=value
                node['widgets_values'][i]=value


def prepare():
    if (RUN/'job_link.json').exists():
        raise FileExistsError('A frozen job exists. Execute/collect it rather than creating another.')
    (RUN/'references').mkdir(parents=True,exist_ok=True)
    assert sha(GROK_REF)=='293392069fe39ab1f916d96db9e0c3fd3fc4b6db3b78ef269d5a3b1ef134c487'
    image=Image.open(GROK_REF).convert('RGB')
    # Match the old Grok content, fitting the verified low-memory landscape profile.
    # Fixed gray padding only; no new design, no bbox fitting and no stretching.
    reference=Image.new('RGB',(608,352),(128,128,128))
    reference.paste(image.resize((352,352),Image.Resampling.NEAREST),(128,0))
    reference_file=RUN/'references/same_grok_letterboxed_608x352.png'
    reference.save(reference_file)
    shutil.copy2(GROK_REF,RUN/'references/grok_actual_reference_1024.png')
    from fatfish_grok_walk import PROMPT as grok_prompt
    prompt=grok_prompt.replace('Show approximately four evenly timed repetitions in four seconds.',
        'Show five evenly timed walking repetitions across this five-second shot.')
    prompt='Picture: '+prompt.replace('Silent clip, no speech.','')+'\nSound: Soft unchanging room tone. No speech.\nScore: No music.'
    prompt_file=RUN/'prompt.txt';prompt_file.write_text(prompt,encoding='utf-8')
    runner=load_runner();deadline=time.monotonic()+240
    with runner.job_lock(STUDIO,deadline):
        stats,output_root=runner.ensure_server(STUDIO,deadline)
        image_file=upload(reference_file)
        args=SimpleNamespace(prompt_file=prompt_file,prompt=None,name='fatfish_first_frame',mode='two-pass',seed=20261023)
        folder,job=runner.create_job(args,STUDIO)
        graph=runner.read(folder/'prompt.api.json');workflow=runner.read(folder/'workflow.json')
        schema=runner.request('/object_info/MiniMaxH3Director',timeout=30)['MiniMaxH3Director']
        task=next(v for v in schema['input']['required']['task_type'][0] if v.startswith('fl2v'))
        director=graph['5']['inputs'];timeline=json.loads(director['timeline_data'])
        timeline.update(editMode='global',timelineMode='fl2v',totalFrames=124,frameRate=24,
            shots=[{'id':'fatfish_walk','durationSec':5,'prompt':prompt,
                    'startImage':{'imageFile':image_file,'width':608,'height':352},
                    'negativePrompt':'bad video, camera motion, changing clothes, changing face, additional people, detached limbs'}])
        timeline['global'].update(taskType=task,prompt=prompt,commonEnabled=False)
        # Explicit shots take priority; remove the old T2V segment to avoid ambiguity.
        timeline['segments']=[]
        director.update(task_type=task,global_prompt=prompt,
            timeline_data=json.dumps(timeline,ensure_ascii=False,separators=(',',':')))
        graph['13']['inputs']['skip_fl2v']=False
        sync_gui(workflow,graph)
        runner.save(folder/'prompt.api.json',graph);runner.save(folder/'workflow.json',workflow)
        runner.validate_nodes(graph)
        job.update(input_mode='first_frame_only',reference_image=image_file,
            reference_sha256=sha(reference_file),grok_reference_sha256=sha(GROK_REF),
            refinement_decision='Pending first-pass visual inspection; do not automatically execute the second stage.')
        runner.save(folder/'job.json',job)
        save(RUN/'job_link.json',{'job_dir':str(folder),'job_id':job['job_id'],
             'frozen_api_sha256':sha(folder/'prompt.api.json'),'frozen_gui_sha256':sha(folder/'workflow.json')})
        protected=[GROK_REF,GROK_VIDEO,ROOT/'design/fatfish/action_catalog/progress.json',
            ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK',
            ROOT/'design/fatfish/action_samples_v01/raw/idle_01_0.png']
        save(RUN/'spec.json',{'jobs_max':1,'seed':20261023,'reference_mode':'first frame only',
            'image_uploaded_and_verified':True,'last_frame_supplied':False,'intermediate_frames_supplied':False,
            'guide_video_supplied':False,'grok_reference_source':str(GROK_REF),
            'reference_preparation':'Original Grok reference ->352-square nearest; gray padding x128..480 in608x352. No stretching.',
            'original_ani_verified':False,'initial_profile':runner.PROFILE,'stage_decision':'Inspect first before spending on refinement',
            'memory_before':memory(),'protected_files_before':{str(p):sha(p) for p in protected},
            'api_sha256':sha(folder/'prompt.api.json'),'gui_sha256':sha(folder/'workflow.json')})
        shutil.copy2(folder/'prompt.api.json',RUN/'frozen_prompt.api.json')
        shutil.copy2(folder/'workflow.json',RUN/'frozen_workflow.json')
        print(json.dumps({'prepared':True,'job_dir':str(folder),'reference':str(reference_file),'first_frame_only':True,'memory':memory()}),flush=True)


def run(stage_index):
    link=read(RUN/'job_link.json');folder=Path(link['job_dir']);runner=load_runner()
    assert sha(folder/'prompt.api.json')==link['frozen_api_sha256']
    assert sha(folder/'workflow.json')==link['frozen_gui_sha256']
    deadline=time.monotonic()+1800
    with runner.job_lock(STUDIO,deadline):
        job=runner.read(folder/'job.json')
        stage=job['stages'][stage_index]
        if stage_index and job['stages'][0].get('status')!='completed':
            raise RuntimeError('The original first stage must finish and be reviewed before refinement.')
        stats,output_root=runner.ensure_server(STUDIO,deadline)
        available=memory()
        save(RUN/f'memory_before_stage_{stage_index}.json',available)
        if available['ram_available_gib']<6 or available['commit_available_gib']<8:
            raise RuntimeError('Insufficient memory headroom; leave the frozen job for later.')
        job.update(status='running',backend_version=stats['system'].get('comfyui_version'),output_root=str(output_root))
        runner.save(folder/'job.json',job)
        try:
            runner.execute_stage(folder,job,stage,runner.read(folder/'prompt.api.json'),
                runner.read(folder/'workflow.json'),output_root,deadline)
        except Exception as error:
            job.update(status='needs_attention',last_error=str(error))
            runner.save(folder/'job.json',job)
            raise
        job['status']='first_pass_awaiting_review' if stage_index==0 else 'completed'
        runner.save(folder/'job.json',job)
        if stage_index==1:
            result={'job_dir':str(folder),'mode':job['mode'],'seed':job['seed'],'profile':job['profile'],
                'input_mode':job['input_mode'],'first_pass':job['stages'][0]['videos'],
                'refined':job['stages'][1]['videos'],
                'total_stage_seconds':round(sum(s.get('elapsed_seconds',0) for s in job['stages']),2),
                'media_reports':[report for s in job['stages'] for report in s['media_reports']]}
            runner.save(folder/'result.json',result)
            save(RUN/'result.json',result)
        save(RUN/f'stage_{stage_index}_result.json',stage)
        print(json.dumps({'stage_finished':stage_index,'videos':stage['videos'],
            'seconds':stage.get('elapsed_seconds'),'frames':stage['media_reports'][0]['frames']}),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','first','refine'])
    args=parser.parse_args()
    if args.action=='prepare':prepare()
    else:run(0 if args.action=='first' else 1)
