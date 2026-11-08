"""Bounded 30-slot test: reuse six approved trial targets; generate four fixed-row sheets."""
import argparse
import concurrent.futures
import json
import shutil
import sys
from PIL import Image,ImageDraw,ImageFont
import run_65535_samples as runner
import fatfish_grid_walk as common
from fatfish_fixed_three_trial import HD,TEMPLATE,PROMPT

ROOT=common.ROOT
RUN=ROOT/'design/fatfish/grid30_v01'
OUT=ROOT/'output/Fatfish_Grid30_Test_v01'
PREVIOUS=ROOT/'output/Fatfish_Fixed_Three_Trial_v01'
CONFIGS={f'group_{i+1:02d}':list(range(6+i*6,12+i*6)) for i in range(4)}
NAME='A_Fatfish_FMage_Grid30_Test_v01.NPK'
BASE=ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK'
save=common.save
sha=common.sha

def prepare():
    if RUN.exists():raise FileExistsError('Preserve this run; collect existing tasks, do not submit replacements.')
    for d in ['references','raw','logs','qa']:(RUN/d).mkdir(parents=True,exist_ok=True)
    row=Image.open(TEMPLATE/'fixed_reference_row.png').convert('RGBA');assert row.size==(2048,688)
    master=RUN/'references/appearance_original_1024.png';shutil.copy2(HD,master)
    font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',19);requests=[]
    for name,slots in CONFIGS.items():
        grid=Image.new('RGBA',(2048,2048));grid.alpha_composite(row);d=ImageDraw.Draw(grid)
        for j,slot in enumerate(slots):
            x=[48,704,1360][j%3];y=[704,1360][j//3]
            grid.alpha_composite(common.original(slot).resize((640,640),Image.Resampling.NEAREST),(x,y));d.text((x+12,y+10),f'TARGET / IMG {slot:03d}',font=font,fill='#708da9')
        for x in [696,1352]:d.line((x,704,x,2016),fill='#708da9',width=2)
        for y in [696,1352]:d.line((32,y,2016,y),fill='#708da9',width=2)
        assert grid.crop((0,0,2048,688)).tobytes()==row.tobytes()
        path=RUN/f'references/{name}_input.png';grid.save(path)
        prompt=PROMPT.replace('IMG000, IMG001, IMG002, IMG003, IMG004, IMG005',', '.join(f'IMG{i:03d}' for i in slots)).replace('Follow their different arm-swing phases.','Follow each individual pose, including its particular torso lean, arm positions and airborne foot heights; do not turn non-walking poses into walking. Do not force all shoes onto a common ground line.')
        req={'name':name,'model':'gpt-image-2.5','input':{'prompt':prompt,'n':1,'size':'1:1','resolution':'2k','background':'transparent','quality':'high'},
             'local_reference_paths':[str(path),str(master)],'reference_sha256':[sha(path),sha(master)],'output_directory':str(RUN/'raw')}
        common.RUN=RUN;common.audit(req);(RUN/'reference_payload_audit.json').replace(RUN/f'{name}_payload_audit.json')
        save(RUN/f'{name}_request.json',req);requests.append(req)
    protected=[HD,common.MASTER,BASE,ROOT/'design/fatfish/action_catalog/progress.json',TEMPLATE/'fixed_reference_row.png',PREVIOUS/'report.json']
    save(RUN/'spec.json',{'authorized_target_slots':list(range(30)),'reused_slots':list(range(6)),'new_slots':list(range(6,30)),'configs':CONFIGS,'max_new_jobs':4,
         'references_per_job':2,'new_appearance_images':24,'fixed_reference_row_sha256':sha(TEMPLATE/'fixed_reference_row.png'),
         'reused_trial':str(PREVIOUS),'reused_trial_task_id':'img_02a8fa9e01d3420f5c9955669cdcfe9d',
         'pose_order':'IMG slot order only, no ANI action classification or sequence certification.',
         'base_npk':str(BASE),'npk_name':NAME,'protected_files_before':{str(p):sha(p) for p in protected},
         'user_feedback':'我觉得不错，就这么来，做30帧出来打包个npk我尝尝咸淡',
         'scope':'30-slot test only. Existing six accepted-look targets reused; 24 new targets. No game installation writes or full 174-slot generation.'})
    save(RUN/'requests.json',{'requests':requests});save(RUN/'journal.json',{'provider':'65535','model':'gpt-image-2.5','max_jobs':4,'created_at':runner.now(),'jobs':{n:{'state':'prepared'} for n in CONFIGS}})
    print(json.dumps({'prepared':True,'reuse':list(range(6)),'new':list(range(6,30)),'new_jobs':4,'concurrency':4}))

def receipts():
    relay=runner.load_relay();journal=json.loads((RUN/'journal.json').read_text('utf-8'));records={}
    for name,rec in journal['jobs'].items():
        if not rec.get('task_id'):continue
        task=relay.unwrap(relay.http('GET','/v1/tasks/'+rec['task_id']));records[name]={k:task[k] for k in ['id','model','status','cost_usd','error_code','error_message','created_at','finished_at'] if k in task}
    save(RUN/'receipts.json',records)
    return records

def submit():
    journal=json.loads((RUN/'journal.json').read_text('utf-8'));reqs=json.loads((RUN/'requests.json').read_text('utf-8'))['requests']
    assert journal['max_jobs']==4 and len(reqs)==4 and all(r['state']=='prepared' for r in journal['jobs'].values())
    for r in reqs:
        for p,h in zip(r['local_reference_paths'],r['reference_sha256'],strict=True):assert sha(p)==h
    runner.BATCH=RUN
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda r:runner.run_one(r,journal),reqs))
    recs=receipts();print(json.dumps({'downloaded':sum(r['state']=='downloaded' for r in results),'tasks':recs},ensure_ascii=False))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','submit','collect']);a=ap.parse_args()
    if a.action=='prepare':prepare()
    elif a.action=='submit':submit()
    else:runner.BATCH=RUN;runner.collect();receipts()
