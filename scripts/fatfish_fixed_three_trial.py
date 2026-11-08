"""One bounded 3-reference + 6-pose edit with the actual HD appearance source."""
import argparse
import json
import shutil
import sys
from PIL import Image
import run_65535_samples as runner
import fatfish_grid_walk as common

ROOT=common.ROOT
RUN=ROOT/'design/fatfish/fixed_three_trial_v01'
OUT=ROOT/'output/Fatfish_Fixed_Three_Trial_v01'
NAME='fixed_three_six_hd'
HD=ROOT/'design/fatfish/action_samples_v01/raw/idle_01_0.png'
TEMPLATE=ROOT/'output/Fatfish_Fixed_Three_Master_v01'
save=common.save
sha=common.sha

PROMPT='''Precise identity-preserving game-character sprite-sheet edit. Return ONE 2048x2048 RGBA PNG.

IMAGE 1 is a fixed 3x3 grid. The TOP ROW contains THREE SAME-CHARACTER MOTION REFERENCES, taken from the approved Fatfish walk. Preserve the three top reference figures, their poses, positions and labels. Edit ONLY the SIX red-haired original female-mage figures in the bottom two rows, IMG000, IMG001, IMG002, IMG003, IMG004, IMG005, in that order. Replace each with the SAME blue Fatfish whale-maid. The six original figures control each target's exact pose and placement, not their old costume. Do not copy any top-row pose into a target.

IMAGE 2 is the TRUE HIGH-RESOLUTION APPEARANCE MASTER. Use its fine original detail and shading, face, proportions, costume construction and colors for ALL SIX replacements. The top row is coarser because it came from a video: use it for additional views, silhouette and overlapping parts, not as a requirement to pixelate or blur. Preserve the fine crisp illustrated-sprite detail of IMAGE 2 at the available cell resolution. No coarse pixel blocks, artificial nearest-neighbor upscaling, blur, texture noise or new costume design. Do not copy IMAGE 2's standing pose.

Identity: navy-to-cyan long wavy hair, curled ahoge, whale-fin ears with white undersides, white maid headband with cyan bow, blue eyes, navy long sleeves and maid dress, white apron with small navy whale emblem, gold trim/bows/buttons, opaque white tights and navy Mary Jane shoes. The substantial dark-navy curved WHALE TAIL behind the hips is a separate appendage, not a ribbon, skirt panel or hair lock. Preserve the exposed tail silhouette and fluked end visible in IMAGE 2 in EVERY target, projecting behind the body toward screen left. Keep visible negative space and a distinct contour separating it from the skirt where the pose allows. Do not replace it with a hem frill or omit it.

POSE AND GEOMETRY: The bottom six original figures control the exact head position, facing, torso lean, shoulder/elbow/wrist/hand heights, knee/ankle locations, foot separation, and limb overlaps for their own cells. Follow their different arm-swing phases. Hands must join sleeve cuffs and slender consistent legs must join shoes. Keep all six faces, head sizes, hair volume, garment lengths and tail construction consistent. No extra limbs, detached hands, thickened legs, effects or weapons.

Maintain the same 2048x2048 layout. Cell size 640x640; top-left x/y coordinates 48,704,1360. Preserve the thin gutters, dividers and labels. Each bottom cell represents the SAME fixed 160x160 game-coordinate window at 4x. Do not auto-fit, auto-center or change scale per cell. Preserve source shoe-bottom heights and each figure's location. Keep complete hair, tail, hands and shoes inside the assigned cell. Output exactly nine figures: three unchanged top references plus six edited targets.

BACKGROUND: real transparent alpha outside figures and thin labels/dividers. No solid matte, checkerboard, gray/blue edge halo, glow, floor, cast shadow, motion blur or scene. Clean transparent edges. Return only the edited sheet.
'''

def prepare():
    if RUN.exists():raise RuntimeError('Existing run: collect the known task, never resubmit.')
    assert sha(HD)=='def36f96650567eca3797074e596344bcc74ccf8d637b9671b77b1c30fa40c1d'
    for d in ['references','raw','logs','qa']:(RUN/d).mkdir(parents=True,exist_ok=True)
    grid=RUN/'references/input_grid_2048.png';master=RUN/'references/appearance_original_1024.png'
    shutil.copy2(TEMPLATE/'input_grid_3refs_6poses_2048.png',grid);shutil.copy2(HD,master)
    row=Image.open(TEMPLATE/'fixed_reference_row.png').convert('RGBA')
    assert Image.open(grid).convert('RGBA').crop((0,0,2048,688)).tobytes()==row.tobytes()
    refs=[grid,master]
    req={'name':NAME,'model':'gpt-image-2.5','input':{'prompt':PROMPT,'n':1,'size':'1:1','resolution':'2k','background':'transparent','quality':'high'},
         'local_reference_paths':list(map(str,refs)),'reference_sha256':list(map(sha,refs)),'output_directory':str(RUN/'raw')}
    common.RUN=RUN;common.audit(req)
    save(RUN/'request.json',req);(RUN/'prompt.txt').write_text(PROMPT,encoding='utf-8')
    protected=[HD,common.MASTER,TEMPLATE/'fixed_reference_row.png',ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK',ROOT/'design/fatfish/action_catalog/progress.json']
    save(RUN/'spec.json',{'jobs_max':1,'target_slots':list(range(6)),'reference_count':2,'fixed_top_row_sha256':sha(TEMPLATE/'fixed_reference_row.png'),
         'appearance_reference_is_original_hd':True,'native_round_trip_for_master':False,'protected_files_before':{str(p):sha(p) for p in protected},
         'pose_order_note':'Existing IMG0..5 test poses, not a verified ANI sequence or complete walk loop.',
         'authorization':'One user-requested grid trial only; no video generation, full batch or NPK.'})
    save(RUN/'journal.json',{'provider':'65535','model':'gpt-image-2.5','max_jobs':1,'created_at':runner.now(),'jobs':{NAME:{'state':'prepared'}}})
    print(json.dumps({'prepared':True,'grid':str(grid),'hd_reference':str(master),'max_jobs':1}))

def submit():
    req=json.loads((RUN/'request.json').read_text('utf-8'));journal=json.loads((RUN/'journal.json').read_text('utf-8'))
    assert journal['max_jobs']==1 and list(journal['jobs'])==[NAME]
    for p,d in zip(req['local_reference_paths'],req['reference_sha256'],strict=True):assert sha(p)==d
    runner.BATCH=RUN;rec=runner.run_one(req,journal)
    if rec.get('task_id'):
        relay=runner.load_relay();task=relay.unwrap(relay.http('GET','/v1/tasks/'+rec['task_id']))
        save(RUN/'receipt.json',{k:task[k] for k in ['id','model','status','cost_usd','error_code','error_message','created_at','started_at','finished_at'] if k in task})
    print(json.dumps({'state':rec['state'],'task_id':rec.get('task_id'),'files':rec.get('files')}))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','submit','collect']);args=ap.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='submit':submit()
    else:runner.BATCH=RUN;runner.collect()
