"""Two bounded, single-reference 65535 sheet edits. No automatic resubmission."""
import argparse
import base64
import concurrent.futures
import hashlib
import json
import sys
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont
import run_65535_samples as runner
from fatfish_grid_walk import ROOT, MASTER, MASTER_SHA, WINDOW, original, save, sha

RUN=ROOT/'design/fatfish/embedded_grid_compare_v01'
OUT=ROOT/'output/Fatfish_Embedded_Grid_Compare_v01'
CELL=640
CONFIGS=[dict(name='embedded_3x3',columns=3,rows=3,size=[2048,2048],xs=[48,704,1360],ys=[48,704,1360],ratio='1:1',targets=8),
         dict(name='embedded_2x3',columns=2,rows=3,size=[1365,2048],xs=[34,690],ys=[48,704,1360],ratio='2:3',targets=5)]

def prompt(c):
    return f'''Use case: identity-preserve. Edit the ONE attached sprite sheet.
There are {c['columns']} columns x {c['rows']} rows, read left-to-right then top-to-bottom. The FIRST / TOP-LEFT cell marked REF is the approved blue Fatfish whale-maid. KEEP THIS FIRST SPRITE UNCHANGED. It is the identity, costume and pixel-art style reference, not a walking pose.
Replace the original red-haired female mage in EACH of the remaining {c['targets']} cells (IMG000 through IMG{c['targets']-1:03d}) with this SAME blue Fatfish character. Copy the first cell's face, proportions, navy-to-cyan wavy hair, curled ahoge, white maid headband, whale-fin ears, navy long sleeves, white whale apron, gold trim, white tights, navy shoes and whale tail consistently. Do not copy the original character's red hair, hat or clothes.
EACH TARGET CELL controls its OWN exact pose: preserve that cell's head position, torso lean, shoulder/elbow/wrist/hand positions, knees/ankles, shoe positions and left/right limb overlaps. In particular match each distinct arm swing and leg spread; do not repeat the first cell's standing pose. Sleeves must meet hands, legs stay slender, and all joints remain connected. Only adapt the character appearance to the pose. No invented intermediate poses, reordered cells, missing figures or duplicate poses.
Keep exactly the existing sheet layout and fixed camera. Output {c['size'][0]}x{c['size'][1]} RGBA PNG. Each cell is 640x640, representing the same fixed 160x160 game-coordinate window at 4x scale. Do not auto-center or enlarge individual sprites. Keep the thin dividers and small original cell labels, remove the solid gray cell backgrounds to real alpha transparency. No painted checkerboard, floor, cast shadow, effects, weapons, motion blur, extra text or decoration. Keep the reference's restrained pixel shading and avoid smooth illustration-style repainting. Fit every full figure, hair, hands, tail and shoes wholly inside its cell.
'''

def audit(request):
    relay=runner.load_relay();captured={}
    class Captured(Exception):pass
    def intercept(method,path,body=None,query=None):
        assert method=='POST' and path=='/v1/tasks'
        captured.update(body);raise Captured()
    relay.http=intercept
    try:relay.cmd_image(SimpleNamespace(**request['input'],model=request['model'],image=request['local_reference_paths']))
    except Captured:pass
    uri=captured['input']['image']
    assert isinstance(uri,str) and uri.startswith('data:image/png;base64,')
    decoded=base64.b64decode(uri.split(',',1)[1],validate=True)
    digest=hashlib.sha256(decoded).hexdigest()
    assert len(request['local_reference_paths'])==1 and digest==request['reference_sha256'][0]==sha(request['local_reference_paths'][0])
    wire=json.dumps(captured).encode()
    captured['input']['image']={'file':request['local_reference_paths'][0],'decoded_bytes':len(decoded),'decoded_sha256':digest}
    save(RUN/f"{request['name']}_payload_audit.json",{'reference_count':1,'actual_cli_body_captured_before_http':True,
        'network_requests_during_audit':0,'wire_bytes':len(wire),'wire_sha256':hashlib.sha256(wire).hexdigest(),'request':captured})

def prepare():
    if RUN.exists():raise RuntimeError('Trial exists. Inspect journal; do not resubmit.')
    assert sha(MASTER)==MASTER_SHA
    for d in ['references','raw','logs','qa','split']:(RUN/d).mkdir(parents=True,exist_ok=True)
    with Image.open(MASTER) as im:master=im.convert('RGBA').crop(WINDOW)
    master.save(RUN/'references/master_native.png')
    font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',19)
    requests=[]
    for c in CONFIGS:
        sheet=Image.new('RGBA',tuple(c['size']));draw=ImageDraw.Draw(sheet);cells=[]
        for index in range(c['columns']*c['rows']):
            slot=None if index==0 else index-1
            im=master if slot is None else original(slot)
            x,y=c['xs'][index%c['columns']],c['ys'][index//c['columns']]
            bg=Image.new('RGBA',(CELL,CELL),'#c9d2de')
            bg.alpha_composite(im.resize((CELL,CELL),Image.Resampling.NEAREST));sheet.alpha_composite(bg,(x,y))
            draw.text((x+12,y+10),'REF / KEEP' if slot is None else f'IMG {slot:03d}',font=font,fill='#495e76')
            cells.append({'index':index,'slot':slot,'role':'approved_identity_reference' if slot is None else 'pose_edit_target',
                          'cell':[x,y,x+CELL,y+CELL]})
            if slot is not None:im.save(RUN/f'references/original_{slot:03d}.png')
        for x in c['xs'][1:]:draw.line((x-8,32,x-8,c['size'][1]-32),fill='#6a849e',width=2)
        for y in c['ys'][1:]:draw.line((24,y-8,c['size'][0]-24,y-8),fill='#6a849e',width=2)
        p=RUN/f"references/{c['name']}_input.png";sheet.save(p);c['cells']=cells;c['input_path']=str(p)
        text=prompt(c);(RUN/f"{c['name']}_prompt.txt").write_text(text,encoding='utf-8')
        req={'name':c['name'],'model':'gpt-image-2.5','input':{'prompt':text,'n':1,'size':c['ratio'],
             'resolution':'2k','background':'transparent','quality':'high'},'local_reference_paths':[str(p)],
             'reference_sha256':[sha(p)],'output_directory':str(RUN/'raw')}
        audit(req);requests.append(req)
    protected=[MASTER,ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK',ROOT/'design/fatfish/action_catalog/progress.json']
    save(RUN/'spec.json',{'configs':CONFIGS,'jobs_max':2,'cell_size':640,'native_window_world':list(WINDOW),
        'native_size':[160,160],'common_slots':list(range(5)),'master_sha256':MASTER_SHA,
        'protected_files_before':{str(p):sha(p) for p in protected},
        'experiment_limitations':['One stochastic sample per layout; not statistical proof of attention limits.',
          'Equal input cell scale; canvas aspect ratio and target arrangement change alongside target count.',
          'First cell is a standing identity exemplar and must not be included in walking playback.',
          'Existing walk-test slot order only; ANI sequence/timing and complete gait not established.'],
        'authorization':'Two requested sheets only, one reference each; no retry, batch expansion, NPK or game writes.'})
    save(RUN/'requests.json',{'requests':requests})
    save(RUN/'journal.json',{'provider':'65535','model':'gpt-image-2.5','max_jobs':2,'created_at':runner.now(),
                            'jobs':{r['name']:{'state':'prepared'} for r in requests}})
    print(json.dumps({'prepared':True,'inputs':[c['input_path'] for c in CONFIGS],'reference_count_per_job':1,'jobs_max':2}))

def submit():
    requests=json.loads((RUN/'requests.json').read_text('utf-8'))['requests']
    journal=json.loads((RUN/'journal.json').read_text('utf-8'))
    assert len(requests)==len(journal['jobs'])==journal['max_jobs']==2 and sha(MASTER)==MASTER_SHA
    for r in requests:
        assert r['model']=='gpt-image-2.5' and r['input']['n']==len(r['local_reference_paths'])==1
        assert journal['jobs'][r['name']]['state']=='prepared'
        assert sha(r['local_reference_paths'][0])==r['reference_sha256'][0]
    runner.BATCH=RUN
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda r:runner.run_one(r,journal),requests))
    relay=runner.load_relay();receipts={}
    for request,result in zip(requests,results,strict=True):
        if result.get('task_id'):
            task=relay.unwrap(relay.http('GET','/v1/tasks/'+result['task_id']))
            receipts[request['name']]={k:task[k] for k in ['id','model','status','cost_usd','error_code','error_message','created_at','started_at','finished_at'] if k in task}
    save(RUN/'receipts.json',receipts)
    print(json.dumps({'receipts':receipts,'files':{q['name']:r.get('files',[]) for q,r in zip(requests,results,strict=True)}},ensure_ascii=False))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','submit']);a=p.parse_args()
    prepare() if a.action=='prepare' else submit()
