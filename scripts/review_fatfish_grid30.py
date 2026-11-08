"""Reuse the inspected six-pose cleanup pipeline for four bounded sheets."""
import argparse
import json
import shutil
import sys
from PIL import Image,ImageDraw,ImageFont
import review_fatfish_fixed_three_trial as previous
from fatfish_grid30 import ROOT,RUN,OUT,CONFIGS,PREVIOUS,save,sha
from fatfish_grid_walk import original

TARGET_EYES=[[81,54],[84,54],[85,54],[82,54],[81,54],[81,54],[84,53],[83,55],[82,55],[84,54],
 [80,55],[80,56],[77,54],[77,54],[79,55],[78,55],[79,55],[79,56],[102,60],[103,59],[103,60],[103,61],
 [80,58],[87,57],[88,65],[88,61],[80,58],[87,57],[88,65],[104,73]]

def configure(name):
    slots=CONFIGS[name];work=RUN/'groups'/name;out=OUT/'groups'/name
    journal=json.loads((RUN/'journal.json').read_text('utf-8'));rec=journal['jobs'][name];assert rec['state']=='downloaded'
    for d in ['references','qa']:(work/d).mkdir(parents=True,exist_ok=True)
    save(work/'journal.json',{'jobs':{name:rec}})
    shutil.copy2(RUN/f'references/{name}_input.png',work/'references/input_grid_2048.png')
    shutil.copy2(RUN/'references/appearance_original_1024.png',work/'references/appearance_original_1024.png')
    previous.RUN=work;previous.OUT=out;previous.NAME=name;previous.original=lambda i:original(slots[i]);previous.TARGET_EYES=[TARGET_EYES[i] for i in slots]
    return work,out

def inspect():
    journal=json.loads((RUN/'journal.json').read_text('utf-8'))
    for name in CONFIGS:
        if journal['jobs'][name]['state']!='downloaded':continue
        configure(name);previous.inspect()

def register():
    for name in CONFIGS:
        configure(name);previous.register()

def flatten():
    for d in ['original','exact_cells','isolated_hd','clean_hd','registered_hd','nearest','raw_nearest','qa','evidence','sheets','references']:(OUT/d).mkdir(parents=True,exist_ok=True)
    folders=['original','exact_cells','isolated_hd','clean_hd','registered_hd','nearest','raw_nearest'];items=[]
    old=json.loads((PREVIOUS/'report.json').read_text('utf-8'))
    for slot in range(30):
        if slot<6:
            source=PREVIOUS;local=slot;group='reused_approved_trial';r=old['registration']['frames'][slot];task=old['task_id'];scale=old['registration']['shared_scale_from_640_to_native']
        else:
            name=list(CONFIGS)[(slot-6)//6];local=(slot-6)%6;source=OUT/'groups'/name;group=name
            reg=json.loads((RUN/'groups'/name/'registration.json').read_text('utf-8'));r=reg['frames'][local];scale=reg['shared_scale_from_640_to_native']
            task=json.loads((RUN/'journal.json').read_text('utf-8'))['jobs'][name]['task_id']
        for folder in folders:shutil.copy2(source/f'{folder}/{local:03d}.png',OUT/f'{folder}/{slot:03d}.png')
        items.append({**r,'slot':slot,'group':group,'source_cell_index':local+3,'task_id':task,'shared_group_scale':scale,'reused':slot<6})
    shutil.copy2(RUN/'references/appearance_original_1024.png',OUT/'references/appearance_original_1024.png')
    for name in CONFIGS:
        shutil.copy2(OUT/'groups'/name/'output_sheet.png',OUT/f'sheets/{name}_output.png')
        shutil.copy2(RUN/f'references/{name}_input.png',OUT/f'sheets/{name}_input.png')
    receipts=json.loads((RUN/'receipts.json').read_text('utf-8'));assert all(r['status']=='done' for r in receipts.values())
    spec=json.loads((RUN/'spec.json').read_text('utf-8'))
    for p,h in spec['protected_files_before'].items():assert sha(p)==h
    report={'title':'30 IMG slot costume test','model':'gpt-image-2.5','provider':'65535','slots':list(range(30)),'new_frames':24,'reused_frames':6,'new_jobs':4,
       'cost_usd':sum(r['cost_usd'] for r in receipts.values()),'receipts':receipts,'frames':items,'frame_count':30,'verified_ani_sequence':False,
       'timing':'180ms inspection only; game uses original ANI. Adjacent IMG slots do not certify an action.',
       'sampling':'HD cell -> group-shared scale, per-frame translation -> single nearest sample to160px. HD640 work copies also supplied.',
       'pose_correction':'Global scale and translation only. No local limb reshaping.',
       'accepted':False,'npk_game_validated':False,'protected_files_unchanged':spec['protected_files_before']}
    save(OUT/'report.json',report);save(RUN/'processing_report.json',report)
    # All target pairs at consistent native scale, independent of CSS or browser rendering.
    board=Image.new('RGB',(1440,216*5),'#172536');d=ImageDraw.Draw(board);font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',14)
    for slot in range(30):
        x=slot%6*240;y=slot//6*216
        for j,folder in enumerate(['original','registered_hd']):
            im=Image.open(OUT/f'{folder}/{slot:03d}.png').convert('RGBA').resize((120,120),Image.Resampling.LANCZOS if j else Image.Resampling.NEAREST)
            bg=Image.new('RGBA',(120,120),'#c5d3e2');bg.alpha_composite(im);board.paste(bg.convert('RGB'),(x+j*120,y+28))
        d.text((x+8,y+5),f'IMG {slot:03d} / original : HD',font=font,fill='#d0e4ef')
    board.save(OUT/'qa/all30_original_hd.png')
    print(json.dumps({'flattened_frames':30,'new_cost_usd':report['cost_usd'],'scales':{n:json.loads((RUN/'groups'/n/'registration.json').read_text('utf-8'))['shared_scale_from_640_to_native'] for n in CONFIGS}}))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');ap=argparse.ArgumentParser();ap.add_argument('action',choices=['inspect','register','flatten']);a=ap.parse_args();globals()[a.action]()
