"""Summarize actual local job telemetry and native frame geometry without inference."""
from pathlib import Path
import json
import numpy as np
from PIL import Image
from fatfish_full_ref2va import ROOT,RUN,OUT,read,save,sha

def audit():
    data=read(RUN/'production.json');guards=[];telemetry=[];jobs=[]
    for path in sorted((RUN/'jobs').glob('*/attempt_*/job.json')):
        job=read(path);stage=job['stages'][0];jobs.append({'path':str(path),'status':job['status'],'seconds':stage.get('elapsed_seconds'),'prompt_id':stage.get('prompt_id')})
        g=path.parent/'memory_guard.jsonl'
        if g.exists():guards += [json.loads(line) for line in g.read_text('utf-8').splitlines() if line]
        t=path.parent/'execute/telemetry.jsonl'
        if t.exists():telemetry += [json.loads(line) for line in t.read_text('utf-8').splitlines() if line]
    frame_checks=[];preview_overflow=[]
    for path in sorted((OUT/'native_frames').glob('*.png')):
        im=Image.open(path).convert('RGBA');a=np.asarray(im.getchannel('A'));yy,xx=np.where(a>=160)
        box=im.getchannel('A').getbbox();assert box and im.size==(500,500)
        slot=int(path.stem);clip=next(c for c in data['clips'] if c['start']<=slot<=c['end']);mapping=read(OUT/'clips'/clip['id']/'mapping.json');window=mapping.get('preview_window_world',[170,250,362,410])
        if box[0]<window[0] or box[1]<window[1] or box[2]>window[2] or box[3]>window[3]:preview_overflow.append({'slot':slot,'bbox':box,'window':window})
        frame_checks.append({'slot':int(path.stem),'alpha_bbox':box,'solid_bbox':[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)],'alpha_pixels':int((a>0).sum()),'partial_alpha_pixels':int(((a>0)&(a<255)).sum()),'native_sha256':sha(path)})
    gpu=[]
    for row in telemetry:
        try:gpu.append(float(row['gpu'].split(',')[0]))
        except (KeyError,ValueError,AttributeError):pass
    report={'local_only':True,'new_cloud_generation_calls':0,'jobs':jobs,'completed_new_jobs':sum(j['status']=='completed' for j in jobs),'reused_walk_clips':1,
      'new_job_sampling_seconds_total':sum(j['seconds'] or 0 for j in jobs),'gpu_memory_peak_observed_MiB':max(gpu) if gpu else None,
      'minimum_available_ram_GiB':min(r['ram_available_gib'] for r in guards) if guards else None,
      'minimum_available_commit_GiB':min(r['commit_available_gib'] for r in guards) if guards else None,
      'memory_abort_files':[str(p) for p in (RUN/'jobs').glob('*/attempt_*/memory_abort.json')],
      'annotated_clips':len(data['clips']),'native_frame_count':len(frame_checks),'preview_crop_overflow':preview_overflow,'frame_checks':frame_checks,'game_directory_changed':False}
    save(OUT/'resource_and_geometry_audit.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['jobs','frame_checks']},ensure_ascii=False))
if __name__=='__main__':audit()
