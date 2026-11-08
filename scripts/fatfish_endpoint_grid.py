"""One sparse endpoint-conditioned six-frame sheet; no original intermediate poses uploaded."""
import argparse
import json
import shutil
import sys
from PIL import Image,ImageDraw,ImageFont
import fatfish_fixed_three_trial as trial
import fatfish_grid_walk as common
import run_65535_samples as runner

ROOT=common.ROOT
RUN=ROOT/'design/fatfish/endpoint_grid_v01'
OUT=ROOT/'output/Fatfish_Endpoint_Grid_v01'
NAME='endpoint_six_frames'
save=common.save
sha=common.sha

PROMPT='''Create one temporally coherent six-frame 2D game-character animation strip within the bottom two rows of IMAGE 1. Return exactly ONE 2048x2048 transparent RGBA PNG in the same 3x3 grid.

IMAGE 1 has three fixed blue Fatfish whale-maid motion/appearance references in its TOP ROW. Leave those three reference figures and labels in place. They show additional views and silhouettes of the same approved character. The BOTTOM TWO ROWS are ONE ordered SIX-FRAME MOTION SEGMENT, read left-to-right then top-to-bottom. Only FRAME 1 / START and FRAME 6 / END contain original red-haired DNF mage poses. The four MIDDLE cells are intentionally empty. This is NOT a request to leave them blank: generate the four missing in-betweens, plus replace the original characters in the first and sixth bottom cells with Fatfish.

START and END are the only pose anchors. Match the specific original head/torso placement, arm heights, wrist positions, leg overlaps, feet and facing in these two anchors. Between them animate a single smooth natural right-facing in-place walking segment. Design the four in-between poses jointly as one coherent motion: consistent limb lengths and body proportions, gradual arm swings through shoulders/elbows, knees bending and legs passing then opening, continuous foot trajectories and coherent weight transfer. Do not make six unrelated poses, six endpoint copies, merely translate one rigid character, morph unrelated clothing, or jump the limb ordering. Keep sleeves attached to hands and legs attached to shoes. Camera, character scale, face size, hair volume and garment construction must stay fixed throughout the six frames. Preserve head and torso continuity; avoid abrupt vertical bobbing, accidental zoom and lateral drifting. Use small continuous secondary hair/hem/tail motion rather than random changes in each cell. This is only the START-to-END segment; do not add a new reset pose or force frame6 to equal frame1.

IMAGE 2 is the TRUE 1024px HIGH-RESOLUTION APPEARANCE MASTER. Follow its exact blue-eyed face, proportions, fine original detail and shading, navy-to-cyan wavy long hair, curled ahoge, whale-fin ears with white underside, white maid headband with cyan bow, navy long sleeves and dress, white whale-emblem apron, gold trim/bows/buttons, white tights and navy Mary Jane shoes. The top-row video references are coarser; use them for structure/views, not as a reason to pixelate or blur. Keep the substantial separate curved dark-navy whale tail with fluked tip behind the hips toward screen left in EVERY frame; it is not a skirt panel, ribbon or hair lock. Keep the costume, face, outlines, colors, tail and details coherent between adjacent frames. No added/missing limbs, accessories, effects or weapons. Do not copy Image2's standing pose into the whole segment.

LAYOUT: exactly 3x3, each cell640x640, cell top-left x/y=48,704,1360. Top3 stay references. Bottom cells are animation frames1..6 at equal time intervals t=0,.2,.4,.6,.8,1. Retain thin separators and labels. All cells share the same game coordinate window, camera and scale. Do not independently center, auto-fit or enlarge a frame. Keep each full body, hair, tail, hands and shoes inside its own cell. Output exactly nine figures total: top3 references and six blue Fatfish animation frames below. No original red-haired characters remain.

Use real clean alpha transparency outside characters/labels/dividers, no solid matte or painted checkerboard, floor, cast shadow, colored edge halo, motion blur or scene. Preserve clear fine illustrated-sprite detail, with no coarse pixel blocks or artificial nearest-upscaled texture.
'''

def prepare():
    if RUN.exists():raise FileExistsError('Existing run: collect its known task, do not submit a replacement.')
    for d in ['references','raw','logs','qa']:(RUN/d).mkdir(parents=True,exist_ok=True)
    row=Image.open(trial.TEMPLATE/'fixed_reference_row.png').convert('RGBA');sheet=Image.new('RGBA',(2048,2048));sheet.alpha_composite(row)
    d=ImageDraw.Draw(sheet);font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',19)
    blank_verified=[]
    for i in range(6):
        x=[48,704,1360][i%3];y=[704,1360][i//3]
        if i in [0,5]:sheet.alpha_composite(common.original(i).resize((640,640),Image.Resampling.NEAREST),(x,y))
        label=f'FRAME {i+1} / '+('START IMG000' if i==0 else 'END IMG005' if i==5 else 'IN-BETWEEN / DRAW')
        d.text((x+12,y+10),label,font=font,fill='#708da9')
        if i not in [0,5]:
            assert sheet.crop((x+10,y+62,x+630,y+630)).getchannel('A').getbbox() is None;blank_verified.append(i+1)
    for x in [696,1352]:d.line((x,704,x,2016),fill='#708da9',width=2)
    for y in [696,1352]:d.line((32,y,2016,y),fill='#708da9',width=2)
    assert sheet.crop((0,0,2048,688)).tobytes()==row.tobytes()
    grid=RUN/'references/input_grid_2048.png';sheet.save(grid)
    master=RUN/'references/appearance_original_1024.png';shutil.copy2(trial.HD,master)
    refs=[grid,master];req={'name':NAME,'model':'gpt-image-2.5','input':{'prompt':PROMPT,'n':1,'size':'1:1','resolution':'2k','background':'transparent','quality':'high'},
        'local_reference_paths':list(map(str,refs)),'reference_sha256':list(map(sha,refs)),'output_directory':str(RUN/'raw')}
    common.RUN=RUN;common.audit(req);save(RUN/'request.json',req);(RUN/'prompt.txt').write_text(PROMPT,encoding='utf-8')
    protected=[trial.HD,trial.TEMPLATE/'fixed_reference_row.png',ROOT/'output/A_Fatfish_FMage_Grid30_Test_v01.NPK',ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK',ROOT/'design/fatfish/action_catalog/progress.json']
    save(RUN/'spec.json',{'max_jobs':1,'model':'gpt-image-2.5','reference_count':2,'uploaded_original_pose_slots':[0,5],
         'blank_inbetween_cells_verified':blank_verified,'uploaded_intermediate_original_pose_count':0,'output_sequence_labels':list(range(1,7)),
         'comparison_old_slots':list(range(6)),'fixed_top_row_sha256':sha(trial.TEMPLATE/'fixed_reference_row.png'),
         'motion_note':'Experimental endpoint-conditioned motion segment. Synthesized in-betweens have no verified IMG/ANI correspondence.',
         'registration_plan':'One shared scale; only endpoint eye/sole alignment controls. Interpolate endpoint translation corrections; no fitting to original intermediate eyes or shoe heights.',
         'protected_files_before':{str(p):sha(p) for p in protected},'npk_requested':False,'full_batch_started':False})
    save(RUN/'journal.json',{'provider':'65535','model':'gpt-image-2.5','max_jobs':1,'created_at':runner.now(),'jobs':{NAME:{'state':'prepared'}}})
    print(json.dumps({'prepared':True,'pose_anchors':[0,5],'empty_middle_cells':blank_verified,'jobs':1}))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','submit','collect']);a=ap.parse_args()
    if a.action=='prepare':prepare()
    elif a.action=='submit':trial.RUN=RUN;trial.NAME=NAME;trial.submit()
    else:runner.BATCH=RUN;runner.collect()
