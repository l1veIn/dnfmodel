"""Two sequential 65535 grid edits, fixed HD master + carry + 7 targets + HD design."""
import argparse
import base64
import hashlib
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from PIL import Image,ImageDraw,ImageFont
import numpy as np
import run_65535_samples as runner
from fatfish_grid_walk import ROOT,MASTER,MASTER_SHA,WINDOW,original,save,sha

RUN=ROOT/'design/fatfish/grid_progression_v01'
OUT=ROOT/'output/Fatfish_Grid_Progression_v01'
HD=ROOT/'design/fatfish/action_samples_v01/raw/idle_01_0.png'
DESIGN=ROOT/'design/fatfish/concepts/fatfish_mage_v01.png'
POS=[48,704,1360]
CONFIGS={'group_a':{'carry_slot':7,'slots':[8,9,0,1,2,3,4]},
         'group_b':{'carry_slot':4,'slots':[5,6,7,8,9,0,1]}}

def premul_affine(im,size,coeff):
    return im.convert('RGBa').transform(size,Image.Transform.AFFINE,coeff,Image.Resampling.BICUBIC).convert('RGBA')

def audit(request):
    relay=runner.load_relay();captured={}
    class Captured(Exception):pass
    def intercept(method,path,body=None,query=None):
        assert method=='POST' and path=='/v1/tasks';captured.update(body);raise Captured()
    relay.http=intercept
    try:relay.cmd_image(SimpleNamespace(**request['input'],model=request['model'],image=request['local_reference_paths']))
    except Captured:pass
    refs=captured['input']['image'];assert isinstance(refs,list) and len(refs)==2
    records=[]
    for uri,path,digest in zip(refs,request['local_reference_paths'],request['reference_sha256'],strict=True):
        b=base64.b64decode(uri.split(',',1)[1],validate=True);assert hashlib.sha256(b).hexdigest()==digest==sha(path)
        records.append({'path':path,'decoded_bytes':len(b),'decoded_sha256':digest})
    wire=json.dumps(captured).encode();captured['input']['image']=records
    save(RUN/f"{request['name']}_payload_audit.json",{'reference_count':2,'network_requests_during_audit':0,
         'actual_cli_body_captured_before_http':True,'wire_bytes':len(wire),'wire_sha256':hashlib.sha256(wire).hexdigest(),'request':captured})

def assemble(name,carry_path):
    c=CONFIGS[name];master=Image.open(RUN/'references/fixed_hd_master_cell.png').convert('RGBA')
    carry=Image.open(carry_path).convert('RGBA');assert carry.size==(640,640)
    sheet=Image.new('RGBA',(2048,2048));draw=ImageDraw.Draw(sheet);font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',19)
    cells=[]
    for i in range(9):
        x,y=POS[i%3],POS[i//3]
        if i==0:im=master;role='fixed_master';slot=10;label='MASTER / KEEP'
        elif i==1:im=carry;role='carry';slot=c['carry_slot'];label=f'CARRY IMG {slot:03d} / KEEP'
        else:slot=c['slots'][i-2];role='new_target';im=original(slot).resize((640,640),Image.Resampling.NEAREST);label=f'NEW {i-1:02d} / IMG {slot:03d}'
        sheet.alpha_composite(im,(x,y));draw.text((x+12,y+10),label,font=font,fill='#69839d')
        cells.append({'index':i,'role':role,'slot':slot,'cell':[x,y,x+640,y+640]})
    for p in [696,1352]:
        draw.line((p,32,p,2016),fill='#69839d',width=2);draw.line((32,p,2016,p),fill='#69839d',width=2)
    grid=RUN/f'references/{name}_input.png';sheet.save(grid)
    prompt=f'''Use case: identity-preserve, precise 2D game sprite-sheet edit.
IMAGE 1 is a 3x3 grid. Read left-to-right then top-to-bottom. Cell 1 MASTER is the fixed approved character/style master. Cell 2 CARRY is the previous sequence's last frame (IMG{c['carry_slot']:03d}). KEEP BOTH reference sprites and their poses unchanged. Replace ONLY the original red-haired mage in cells 3..9 with this same blue Fatfish whale-maid, matching each target's own exact pose. The seven target IMG slots, in order, are {c['slots']}. Do not copy the master standing pose into targets.
IMAGE 2 is the HIGH-RESOLUTION COSTUME DESIGN SHEET (front/side/back). Use it to preserve garment construction and the distinctive physical WHALE TAIL, including its curved dark-navy peduncle attached behind the lower back/hips and its two-fluke tip, distinct from the long blue hair, skirt, back bow and whale apron emblem. In this right-facing walk view the tail extends behind the character toward screen left, with a clearly readable exposed end. Retain this visible tail and its construction in EVERY new target even when the near part is occluded by hair/skirt. Use the body's pose from each cell; Image 2 is not a pose or camera reference. Keep the proportions, restrained pixel-sprite shading and navy/cyan/white/gold palette of cell 1, not the tall illustration proportions.
For every new cell preserve its own original head position, torso lean, shoulder/elbow/wrist/hand positions, knee/ankle positions, foot spacing and left/right overlaps. Sleeves join hands and slender legs join shoes. Keep consistent face, headband, whale-fin ears, curled ahoge, long wavy navy-to-cyan hair, long navy sleeves, white whale apron, gold trim/bows, white tights, navy Mary Jane shoes and the physical whale tail. Maintain continuity from CARRY through the seven new poses. No extra hands/limbs, missing accessories, effects, weapons, duplicate poses or costume redesign.
Output ONE 2048x2048 RGBA PNG, same fixed 3x3 layout. Cell top-left x and y are 48,704,1360; every cell is 640x640, the same 160x160 game window at 4x. Preserve exact sprite scale/position and camera; no individual auto-fit or enlargement. Keep the thin dividers and small labels only. The input background is ALREADY TRANSPARENT: preserve true clean alpha, no gray matte, colored glow, checkerboard, floor or cast shadow. Keep every complete figure and its tail within its cell. Return nine full-body figures: two preserved references and seven edited targets.
'''
    (RUN/f'{name}_prompt.txt').write_text(prompt,encoding='utf-8')
    refs=[grid,RUN/'references/hd_design_sheet.png']
    req={'name':name,'model':'gpt-image-2.5','input':{'prompt':prompt,'n':1,'size':'1:1','resolution':'2k','background':'transparent','quality':'high'},
         'local_reference_paths':list(map(str,refs)),'reference_sha256':list(map(sha,refs)),'output_directory':str(RUN/'raw')}
    audit(req);save(RUN/f'{name}_request.json',req)
    save(RUN/f'{name}_layout.json',{'name':name,**c,'cells':cells,'carry_input_file':str(carry_path),'carry_input_sha256':sha(carry_path),
        'fixed_master_cell_sha256':sha(RUN/'references/fixed_hd_master_cell.png'),'grid_sha256':sha(grid)})
    return grid

def prepare():
    if RUN.exists():raise RuntimeError('Preserve this run; do not recreate or resubmit it.')
    assert sha(MASTER)==MASTER_SHA and sha(HD)=='def36f96650567eca3797074e596344bcc74ccf8d637b9671b77b1c30fa40c1d'
    for d in ['references','raw','logs','qa','split']:(RUN/d).mkdir(parents=True,exist_ok=True)
    shutil.copy2(HD,RUN/'references/hd_master_original.png');shutil.copy2(DESIGN,RUN/'references/hd_design_sheet.png')
    # Direct mapping from the ORIGINAL 1024px file using approved v04 geometry, no native-size round trip.
    factor=147/1024*4
    mother=premul_affine(Image.open(HD).convert('RGBA'),(640,640),(1/factor,0,-16/factor,0,1/factor,0))
    mother.save(RUN/'references/fixed_hd_master_cell.png')
    old=ROOT/'output/Fatfish_Embedded_Grid_Compare_v01'
    report=json.loads((old/'review_report.json').read_text('utf-8'));fit=report['groups']['embedded_3x3']['shared_transform']
    post=json.loads((ROOT/'output/Fatfish_Grid_Postprocess_v02/report.json').read_text('utf-8'))
    shift=post['frames'][7]['integer_translation_xy'];s=fit['scale_from_normalized_640']*4;t=(np.array(fit['translation_native'])+shift)*4
    raw=Image.open(old/'embedded_3x3/split/007.png').convert('RGBA')
    carry=premul_affine(raw,(640,640),(1/s,0,-t[0]/s,0,1/s,-t[1]/s));carry_path=RUN/'references/initial_carry_img007_hd.png';carry.save(carry_path)
    grid=assemble('group_a',carry_path)
    protected=[MASTER,HD,DESIGN,ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK',ROOT/'design/fatfish/action_catalog/progress.json']
    save(RUN/'spec.json',{'model':'gpt-image-2.5','jobs_max':2,'sequential_dependency':True,'references_per_job':2,'native_size':[160,160],
         'configs':CONFIGS,'master_source_geometry':{'source_size':[1024,1024],'factor':factor,'cell_offset':[16,0],'native_round_trip':False},
         'protected_files_before':{str(p):sha(p) for p in protected},'initial_carry':{'path':str(carry_path),'source':str(old/'embedded_3x3/split/007.png'),'slot':7},
         'pose_order_note':'Existing ten-slot walk-test references only. A=[8,9,0,1,2,3,4], B=[5,6,7,8,9,0,1]. Repeated slots are consistency probes, not 14 distinct ANI poses. 9->0 wrap is an experimental sequence; current ANI order/timing remains unknown.',
         'tail_review':'Check HD return, cleaned alpha, and native-size silhouette separately; do not mark accessory presence from color counts alone.',
         'authorization':'Exactly two requested sequential sheets with added HD design reference. Prior unrestricted spending applies; no additional retry, full batch, NPK or game writes.'})
    save(RUN/'journal.json',{'provider':'65535','model':'gpt-image-2.5','max_jobs':2,'created_at':runner.now(),
         'jobs':{'group_a':{'state':'prepared'},'group_b':{'state':'waiting_for_first_sheet_carry'}}})
    print(json.dumps({'prepared':True,'first_grid':str(grid),'hd_design':str(RUN/'references/hd_design_sheet.png'),'jobs_max':2,'sequential':True}))

def submit(name):
    req=json.loads((RUN/f'{name}_request.json').read_text('utf-8'));journal=json.loads((RUN/'journal.json').read_text('utf-8'))
    assert len(journal['jobs'])==2 and journal['max_jobs']==2
    if name=='group_b':assert journal['jobs']['group_a']['state']=='downloaded'
    for p,d in zip(req['local_reference_paths'],req['reference_sha256'],strict=True):assert sha(p)==d
    runner.BATCH=RUN;result=runner.run_one(req,journal)
    if result.get('task_id'):
        relay=runner.load_relay();task=relay.unwrap(relay.http('GET','/v1/tasks/'+result['task_id']))
        save(RUN/f'{name}_receipt.json',{k:task[k] for k in ['id','model','status','cost_usd','error_code','error_message','created_at','started_at','finished_at'] if k in task})
    print(json.dumps({'group':name,'task_id':result.get('task_id'),'files':result.get('files'),'state':result['state']}))

def prepare_b():
    journal=json.loads((RUN/'journal.json').read_text('utf-8'))
    assert journal['jobs']['group_a']['state']=='downloaded' and journal['jobs']['group_b']['state']=='waiting_for_first_sheet_carry'
    carry=RUN/'references/group_a_last_corrected_hd.png';assert carry.is_file()
    assert (RUN/'group_a_registration.json').exists()
    grid=assemble('group_b',carry)
    journal['jobs']['group_b']={'state':'prepared','depends_on_task':journal['jobs']['group_a']['task_id'],'carry_sha256':sha(carry)}
    save(RUN/'journal.json',journal)
    print(json.dumps({'prepared_group_b':True,'grid':str(grid),'carry_sha256':sha(carry)}))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','submit-a','prepare-b','submit-b']);a=ap.parse_args()
    if a.action=='prepare':prepare()
    elif a.action=='prepare-b':prepare_b()
    else:submit('group_a' if a.action=='submit-a' else 'group_b')
