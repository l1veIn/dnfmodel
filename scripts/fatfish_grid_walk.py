"""One 65535 nine-pose sheet trial. Uses the configured skill CLI; no auto retries."""
import argparse
import base64
import hashlib
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont
import run_65535_samples as runner

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'design/fatfish/grid_walk_v01'
OUT=ROOT/'output/Fatfish_Grid_Walk_v01'
MASTER=ROOT/'design/fatfish/nearest_standing_v04/standing_canvas.png'
MASTER_SHA='9879ff298f8ba3b5200d0ecd5edee248da34f588cc6fbe63694e75020f277446'
WINDOW=(170,250,330,410)
CELL=640
POSITIONS=(48,704,1360)
NAME='fatfish_walk_grid_9'
PROMPT='''Use case: identity-preserve, precise 2D game-sprite pose-sheet edit.
Make exactly ONE 2048x2048 transparent RGBA PNG containing a 3x3 grid of EXACTLY NINE full-body sprites, in exactly the layout of Image 1.

INPUT ROLES:
Image 1 is the EDIT TARGET: a 2048 square original DNF female-mage nine-pose reference sheet. It controls EVERY individual pose, body placement, original left/right limb overlaps, facing direction and panel order. Replace the red-haired original character in each panel with the SAME approved blue Fatfish whale-maid from Image 2. The nine panels are IMG000 through IMG008, read left-to-right then top-to-bottom. Do not invent a new walk or reorder, merge, duplicate or skip a pose.
Image 2 is the APPROVED FATFISH MASTER and controls character identity, head/body proportions, palette, line/shading style and exact costume. It does not control the legs/arms pose. Preserve the navy-to-cyan fine wavy hair, curled ahoge, white-underlined whale-fin ears, cyan bow, white maid headband, blue eyes, navy long sleeves and dress, white whale-emblem apron, gold edging and bows/buttons, opaque white tights, navy Mary Jane shoes, and compact whale tail. Preserve the same face and recognizable details across ALL NINE panels. No costume redesign or new accessories. Ignore the red-haired guide's clothes, hat, braids and colors.

FIXED GEOMETRY:
The output canvas is exactly 2048x2048. Each panel is 640x640. Panel top-left x coordinates are 48, 704, 1360; top-left y coordinates are 48, 704, 1360. Keep the 16px gutters and original thin separator lines and IMG labels at their original positions. Do not add a page header, frames, decoration, floor or scene. Each panel represents the SAME fixed 160x160 native game window at 4x scale. Never individually auto-center, auto-fit, crop or resize a character to fill a panel.
Within each panel, follow that exact source sprite's head/shoulders/pelvis/elbows/wrists/knees/ankles/shoe-ground positions and torso lean. Keep arms and wrists continuously connected, consistent slender legs and foot spacing; clothing follows the pose. Hair, hem and tail may respond subtly while maintaining recognizable shapes, volume and garment construction. Pay special attention to different arm swing heights in each guide panel. Keep the three-quarter right-facing view and identical camera across panels. No motion blur or interpolation smears.

OUTPUT:
Remove the gray cell backdrops. Preserve real alpha transparency outside characters (and the original thin separators/IMG labels). No painted checkerboard, white/gray backdrop, cast shadows, weapons, spell effects or extra figures. Exactly nine complete sprites with all hair, tail, hands and shoes contained inside their respective panel. Match the approved pixel-sprite style and restrained shading, with consistent face/hair/cuffs/apron ornament between adjacent panels. This is a precise sprite replacement sheet, not a character showcase illustration.
'''


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(p)
def original(slot):
    canvas=Image.new('RGBA',(500,500))
    with Image.open(ROOT/f'materials/female_mage/reference_composite/frames/{slot:04d}.png') as im:canvas.alpha_composite(im.convert('RGBA'),(185,0))
    return canvas.crop(WINDOW)


def audit(request):
    relay=runner.load_relay();captured={}
    class Captured(Exception):pass
    def intercept(method,path,body=None,query=None):
        assert method=='POST' and path=='/v1/tasks'
        captured.update(body);raise Captured()
    relay.http=intercept
    try:relay.cmd_image(SimpleNamespace(**request['input'],model=request['model'],image=request['local_reference_paths']))
    except Captured:pass
    refs=captured['input']['image'];assert isinstance(refs,list) and len(refs)==2
    entries=[]
    for uri,path,digest in zip(refs,request['local_reference_paths'],request['reference_sha256'],strict=True):
        data=base64.b64decode(uri.split(',',1)[1],validate=True)
        assert hashlib.sha256(data).hexdigest()==digest==sha(path)
        entries.append({'file':path,'decoded_bytes':len(data),'decoded_sha256':digest})
    wire=json.dumps(captured).encode('utf-8')
    captured['input']['image']=entries
    save(RUN/'reference_payload_audit.json',{'actual_cli_body_captured_before_http':True,'network_requests_during_audit':0,
        'reference_count':2,'request':captured,'wire_bytes':len(wire),'wire_sha256':hashlib.sha256(wire).hexdigest()})


def prepare():
    if RUN.exists():raise RuntimeError('Preserve existing trial; inspect its journal rather than prepare/resubmit')
    assert sha(MASTER)==MASTER_SHA
    for d in ['references','raw','logs','split','registered','qa']:(RUN/d).mkdir(parents=True,exist_ok=True)
    sheet=Image.new('RGBA',(2048,2048),(0,0,0,0));draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',19)
    frames=[]
    for slot in range(9):
        x,y=POSITIONS[slot%3],POSITIONS[slot//3]
        im=original(slot);im.save(RUN/f'references/original_{slot:03d}_native.png')
        bg=Image.new('RGBA',(CELL,CELL),'#c9d2de');bg.alpha_composite(im.resize((CELL,CELL),Image.Resampling.NEAREST))
        sheet.alpha_composite(bg,(x,y))
        draw.text((x+12,y+10),f'IMG {slot:03d}',font=font,fill='#495e76')
        frames.append({'slot':slot,'cell':[x,y,x+CELL,y+CELL],'guide_native_bbox':list(im.getchannel('A').getbbox()),
            'original_source_sha256':sha(ROOT/f'materials/female_mage/reference_composite/frames/{slot:04d}.png')})
    for coordinate in [696,1352]:
        draw.line((coordinate,32,coordinate,2016),fill='#6a849e',width=2)
        draw.line((32,coordinate,2016,coordinate),fill='#6a849e',width=2)
    grid=RUN/'references/original_walk_grid_2048.png';sheet.save(grid)
    with Image.open(MASTER) as im:
        crop=im.convert('RGBA').crop(WINDOW)
        crop.save(RUN/'references/master_approved_native.png')
        crop.resize((1280,1280),Image.Resampling.NEAREST).save(RUN/'references/master_approved_8x.png')
    shutil.copy2(MASTER,RUN/'references/master_approved_canvas.png')
    refs=[grid,RUN/'references/master_approved_8x.png']
    request={'name':NAME,'model':'gpt-image-2.5','input':{'prompt':PROMPT,'n':1,'size':'1:1','resolution':'2k',
        'background':'transparent','quality':'high'},'local_reference_paths':list(map(str,refs)),
        'reference_sha256':list(map(sha,refs)),'output_directory':str(RUN/'raw')}
    save(RUN/'request.json',request);(RUN/'prompt.txt').write_text(PROMPT,encoding='utf-8');audit(request)
    protected=[MASTER,ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK',ROOT/'design/fatfish/action_catalog/progress.json']
    save(RUN/'spec.json',{'provider':'65535','model':'gpt-image-2.5','jobs_max':1,'n':1,'requested_resolution':'2k',
        'transparent_background':True,'native_window_world':list(WINDOW),'native_size':[160,160],
        'sheet_size':[2048,2048],'cell_size':CELL,'guide_scale':4,'frames':frames,
        'master_sha256':MASTER_SHA,'protected_files_before':{str(p):sha(p) for p in protected},
        'source_order':'Existing walk-test IMG0..8, not parsed ANI order/timing; missing IMG9 means not a complete gait loop.',
        'preview_timing_ms':120,'authorisation':'One requested sheet only; prior unrestricted spending instruction persists.',
        'batch_generation':False,'game_installation_changed':False})
    save(RUN/'journal.json',{'provider':'65535','model':'gpt-image-2.5','max_jobs':1,'jobs':{NAME:{'state':'prepared'}},
        'created_at':runner.now()})
    print(json.dumps({'prepared':True,'grid':str(grid),'references':2,'max_generation_jobs':1,'slots':list(range(9))}))


def submit():
    request=json.loads((RUN/'request.json').read_text('utf-8'));journal=json.loads((RUN/'journal.json').read_text('utf-8'))
    assert len(journal['jobs'])==1 and journal['max_jobs']==1
    assert sha(MASTER)==MASTER_SHA
    for p,d in zip(request['local_reference_paths'],request['reference_sha256'],strict=True):assert sha(p)==d
    runner.BATCH=RUN
    result=runner.run_one(request,journal)
    relay=runner.load_relay()
    if result.get('task_id'):
        task=relay.unwrap(relay.http('GET','/v1/tasks/'+result['task_id']))
        save(RUN/'receipt.json',{k:task[k] for k in ['id','model','status','cost_usd','error_code','error_message','created_at','started_at','finished_at'] if k in task})
    print(json.dumps({'task_id':result.get('task_id'),'state':result['state'],'files':result['files']}))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','submit']);args=ap.parse_args()
    prepare() if args.action=='prepare' else submit()
