"""Inspect, clean and register sequential grid trials; export seam and drift evidence."""
import argparse
import json
import shutil
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from fatfish_grid_progression import ROOT,RUN,OUT,CONFIGS,original,save,sha,premul_affine
from fatfish_grid_postprocess_probe import cleanup,nearest,area,display
from review_fatfish_embedded_grid import sole

TARGET_EYES={0:[81,54],1:[84,54],2:[85,54],3:[82,54],4:[81,54],5:[81,54],6:[84,53],7:[83,55],8:[82,55],9:[84,54],10:[80,55]}

def split_group(name):
    journal=json.loads((RUN/'journal.json').read_text('utf-8'));rec=journal['jobs'][name]
    receipt=json.loads((RUN/f'{name}_receipt.json').read_text('utf-8'));assert rec['state']=='downloaded' and receipt['status']=='done'
    assert len(rec['files'])==1
    path=Path(rec['files'][0]);sheet=Image.open(path).convert('RGBA');layout=json.loads((RUN/f'{name}_layout.json').read_text('utf-8'))
    for d in ['raw_cells','clean_cells','raw_native','corrected','area','corrected_hd','tail_raw','tail_clean','tail_native']:(OUT/name/d).mkdir(parents=True,exist_ok=True)
    shutil.copy2(path,OUT/name/'output_sheet.png');shutil.copy2(RUN/f'references/{name}_input.png',OUT/name/'input_sheet.png')
    items=[]
    for cell in layout['cells']:
        x1,y1,x2,y2=cell['cell'];box=[round(x1*sheet.width/2048),round(y1*sheet.height/2048),round(x2*sheet.width/2048),round(y2*sheet.height/2048)]
        raw=sheet.crop(box);a=np.array(raw);h,w=a.shape[:2]
        # Labels and gutters only, then near-body island removal. Keep large disconnected accessories.
        a[:round(h*10/640)]=0;a[-round(h*10/640):]=0;a[:,:round(w*10/640)]=0;a[:,-round(w*10/640):]=0
        a[:round(h*62/640),:round(w*420/640)]=0
        n,labels,stats,centers=cv2.connectedComponentsWithStats((a[:,:,3]>=128).astype('uint8'))
        assert n>1;main=1+int(np.argmax(stats[1:,4]));core=(labels==main).astype('uint8')
        accessory_neighborhood=cv2.dilate(core,np.ones((91,91),'uint8'))>0
        for j in range(1,n):
            if j==main:continue
            x,y,cw,ch,pixels=stats[j];cx,cy=centers[j]
            border_line=(ch>h*.65 and cw<w*.04) or (cw>w*.65 and ch<h*.04)
            if not border_line and pixels>=max(40,round(w*h/409600*120)) and .08*w<cx<.92*w and .12*h<cy<.97*h and accessory_neighborhood[labels==j].any():
                core[labels==j]=1
        keep=cv2.dilate(core,np.ones((17,17),'uint8'))>0
        a[~keep]=0
        raw_kept=Image.fromarray(a);clean,alpha=cleanup(raw_kept)
        i=cell['index'];raw_kept.save(OUT/name/f'raw_cells/{i:02d}.png');clean.save(OUT/name/f'clean_cells/{i:02d}.png')
        raw_kept.resize((160,160),Image.Resampling.NEAREST).save(OUT/name/f'raw_native/{i:02d}.png')
        items.append({**cell,'actual_cell_box':box,'actual_size':list(raw.size),'alpha_cleanup':alpha,'raw_file_sha256':sha(OUT/name/f'raw_cells/{i:02d}.png')})
    report={'name':name,'task_id':receipt['id'],'cost_usd':receipt.get('cost_usd'),'actual_sheet_size':list(sheet.size),
        'actual_alpha_extrema':list(sheet.getchannel('A').getextrema()),'transparent_fraction':float((np.asarray(sheet)[:,:,3]==0).mean()),
        'raw_sheet_sha256':sha(path),'cells':items,'layout':layout}
    save(RUN/f'{name}_split.json',report)
    return report

def inspect(name):
    report=split_group(name);font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',14)
    heads=Image.new('RGB',(1080,1224),'#172536');hd=ImageDraw.Draw(heads)
    for item in report['cells']:
        i=item['index'];im=Image.open(OUT/name/f'raw_cells/{i:02d}.png').convert('RGBA').resize((640,640),Image.Resampling.NEAREST)
        bg=Image.new('RGBA',(640,640),'#cad6e2');bg.alpha_composite(im);d=ImageDraw.Draw(bg)
        for x in range(240,461,20):d.line((x,100,x,320),fill='#9f4a4a80');d.text((x+1,102),str(x),font=font,fill='#8b3e3e')
        for y in range(100,321,20):d.line((240,y,460,y),fill='#9f4a4a80');d.text((240,y+1),str(y),font=font,fill='#8b3e3e')
        crop=bg.crop((240,100,460,320)).resize((352,352),Image.Resampling.NEAREST)
        x=i%3*360;y=i//3*408;heads.paste(crop.convert('RGB'),(x,y+32));hd.text((x+6,y+5),f'{name} cell{i} {item["role"]} IMG{item["slot"]}',font=font,fill='#d4e5f4')
    heads.save(RUN/f'qa/{name}_eye_grid.png')
    # Full row-major contact with actual sprites for tail/pose inspection.
    full=Image.new('RGB',(1440,1512),'#172536');d=ImageDraw.Draw(full)
    for item in report['cells']:
        i=item['index'];im=Image.open(OUT/name/f'raw_cells/{i:02d}.png').convert('RGBA').resize((160,160),Image.Resampling.NEAREST)
        x=i%3*480;y=i//3*504;full.paste(display(im,'checker',3).convert('RGB'),(x,y+24));d.text((x+8,y),f'cell{i} {item["role"]} / IMG {item["slot"]}',font=font,fill='#cee7ef')
    full.save(RUN/f'qa/{name}_full_contact.png')
    print(json.dumps({k:v for k,v in report.items() if k not in ['cells','layout']}))

def register(name):
    report=split_group(name);ann=json.loads((RUN/f'{name}_annotations.json').read_text('utf-8'))
    assert len(ann['eyes'])==9
    # Normalize source cell coordinates to 640; then use one scale for all cells in a group.
    normalized=[]
    for item in report['cells']:
        i=item['index'];im=Image.open(OUT/name/f'clean_cells/{i:02d}.png').convert('RGBA')
        normalized.append(im.resize((640,640),Image.Resampling.NEAREST))
    ratios=[]
    for item in report['cells'][2:]:
        i=item['index'];slot=item['slot'];target=original(slot);eye=ann['eyes'][i];target_eye=TARGET_EYES[slot]
        ratios.append((sole(target)-target_eye[1])/(sole(normalized[i])-eye[1]))
    s=float(np.median(ratios));assert .12<s<.32
    offsets=[np.array(TARGET_EYES[it['slot']])-s*np.array(ann['eyes'][it['index']]) for it in report['cells'][2:]]
    t=np.median(offsets,axis=0);records=[]
    for item in report['cells']:
        i=item['index'];slot=item['slot'];im=normalized[i]
        # References are inspected but not put into the 14-target playback sequence.
        guide=original(slot);eye=ann['eyes'][i]
        base=nearest(im,s,t);dx=int(round(TARGET_EYES[slot][0]-(s*eye[0]+t[0])));dy=int(sole(guide)-sole(base));shift=t+np.array([dx,dy])
        # Sample final native PNG directly from the actual high-res cell, not normalized intermediate.
        actual=Image.open(OUT/name/f'clean_cells/{i:02d}.png').convert('RGBA')
        if actual.size!=(640,640):
            # Generated output may vary in size; affine factors account for real crop resolution.
            hs=actual.width/640;vs=actual.height/640
            yy,xx=np.indices((160,160));sx=np.rint((xx-shift[0])/s*hs).astype('int32');sy=np.rint((yy-shift[1])/s*vs).astype('int32')
            valid=(sx>=0)&(sx<actual.width)&(sy>=0)&(sy<actual.height);arr=np.zeros((160,160,4),'uint8');src=np.array(actual);arr[valid]=src[sy[valid],sx[valid]];nn=Image.fromarray(arr)
            # AREA output uses normalized pixels only for optional diagnostic when dimensions differ.
            box=area(im,s,shift)
        else:nn=nearest(actual,s,shift);box=area(actual,s,shift)
        nn.save(OUT/name/f'corrected/{i:02d}.png');box.save(OUT/name/f'area/{i:02d}.png')
        sx=actual.width/640;sy=actual.height/640
        hd=premul_affine(actual,(640,640),(sx/(s*4),0,-shift[0]*sx/s,0,sy/(s*4),-shift[1]*sy/s))
        hd.save(OUT/name/f'corrected_hd/{i:02d}.png')
        # Consistent posterior-hip crop: inspect raw vs alpha-cleaned vs final pixel image.
        native_roi=[22,70,96,126]
        raw=Image.open(OUT/name/f'raw_cells/{i:02d}.png').convert('RGBA')
        roi=[round((native_roi[0]-shift[0])/s*sx),round((native_roi[1]-shift[1])/s*sy),round((native_roi[2]-shift[0])/s*sx),round((native_roi[3]-shift[1])/s*sy)]
        raw.crop(roi).save(OUT/name/f'tail_raw/{i:02d}.png');actual.crop(roi).save(OUT/name/f'tail_clean/{i:02d}.png');nn.crop(native_roi).save(OUT/name/f'tail_native/{i:02d}.png')
        tail=ann['tail_reviews'][i]
        records.append({**item,'manual_eye_640':eye,'integer_translation':[dx,dy],'final_translation':shift.tolist(),
            'reference_bottom_y':sole(guide),'corrected_bottom_y':sole(nn),'tail_review':tail,'tail_crop_native':native_roi,
            'pose_note':ann.get('pose_notes',{}).get(str(i),'姿势、手脚与细节仍待验收。'),
            'fit_note':'Eye-x and same-frame original shoe row are fitting controls, not independent no-slip validation.'})
    report.update(shared_scale=s,shared_translation=t.tolist(),records=records,local_limb_warps=False,per_frame_rescale=False)
    save(RUN/f'{name}_registration.json',report);save(OUT/name/'registration.json',report)
    if name=='group_a':
        p=OUT/name/'corrected_hd/08.png';shutil.copy2(p,RUN/'references/group_a_last_corrected_hd.png')
        save(RUN/'carry_provenance.json',{'source_task':report['task_id'],'source_raw_sheet_sha256':report['raw_sheet_sha256'],
            'source_cell_index':8,'source_slot':4,'corrected_hd_path':str(p),'corrected_hd_sha256':sha(p),'native_round_trip':False,
            'alpha_cleanup':report['records'][8]['alpha_cleanup'],'scale_native':s,'translation_native':report['records'][8]['final_translation']})
    print(json.dumps({'group':name,'shared_scale':s,'translations':[r['integer_translation'] for r in records],
          'new_target_tail_reviews':[r['tail_review'] for r in records[2:]],'carry_ready':name=='group_a'}))

def finish():
    spec=json.loads((RUN/'spec.json').read_text('utf-8'));groups={n:json.loads((RUN/f'{n}_registration.json').read_text('utf-8')) for n in CONFIGS}
    (OUT/'original').mkdir(exist_ok=True);(OUT/'evidence').mkdir(exist_ok=True)
    for slot in range(10):original(slot).save(OUT/f'original/{slot:03d}.png')
    shutil.copy2(RUN/'references/fixed_hd_master_cell.png',OUT/'master_hd_cell.png');shutil.copy2(RUN/'references/hd_design_sheet.png',OUT/'hd_design_sheet.png')
    frames=[]
    for name,g in groups.items():
        for rec in g['records'][2:]:frames.append({'index':len(frames),'group':name,'cell_index':rec['index'],'slot':rec['slot'],'tail_review':rec['tail_review'],'pose_note':rec.get('pose_note','姿势、手脚与细节仍待验收。')})
    assert len(frames)==14 and frames[6]['slot']==4 and frames[7]['slot']==5
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17)
    seam=[5,6,7,8];contact=Image.new('RGB',(1280,1050),'#172536');d=ImageDraw.Draw(contact)
    for col,index in enumerate(seam):
        f=frames[index];name=f['group'];cell=f['cell_index'];x=col*320
        d.text((x+8,8),f'{"A" if name=="group_a" else "B"} / IMG {f["slot"]:03d}',font=font,fill='#e8cb91' if index==7 else '#c4e4ee')
        for row,folder in enumerate(['original','raw_native','corrected']):
            p=OUT/f'original/{f["slot"]:03d}.png' if folder=='original' else OUT/name/f'{folder}/{cell:02d}.png'
            im=Image.open(p).convert('RGBA');contact.paste(display(im,'checker',2).convert('RGB'),(x,48+row*330))
    contact.save(OUT/'seam_contact.png')
    originals=[];corrected=[]
    for f in frames:
        originals.append(Image.open(OUT/f'original/{f["slot"]:03d}.png').convert('RGBA'))
        corrected.append(Image.open(OUT/f'{f["group"]}/corrected/{f["cell_index"]:02d}.png').convert('RGBA'))
    for name,sequence in [('sequence14',list(range(14))),('seam4',seam)]:
        boards=[]
        for i in sequence:
            f=frames[i];board=Image.new('RGBA',(640,370),'#172536');bd=ImageDraw.Draw(board)
            bd.text((10,7),f'原版 / {f["group"]} IMG{f["slot"]:03d}  [{i+1}/14]',font=font,fill='#e8cb91' if i==7 else '#c7e3ed')
            board.alpha_composite(display(originals[i]),(0,40));board.alpha_composite(display(corrected[i]),(320,40));boards.append(board)
        boards[0].save(OUT/f'{name}_animation.png',save_all=True,append_images=boards[1:],duration=180,loop=0,disposal=0,blend=0)
        with Image.open(OUT/f'{name}_animation.png') as dec:
            assert dec.n_frames==len(boards)
            for i,expected in enumerate(boards):dec.seek(i);assert np.array_equal(np.asarray(dec.convert('RGBA')),np.asarray(expected))
    # Same-pose pairs provide a visual drift check across groups including a regenerated carry.
    pairs=[{'slot':4,'a_cell':8,'b_cell':1,'label':'A末帧 / B重新返回的同姿势衔接帧'}]
    for slot in [8,9,0,1]:
        a=next(r for r in groups['group_a']['records'][2:] if r['slot']==slot)
        b=next(r for r in groups['group_b']['records'][2:] if r['slot']==slot)
        pairs.append({'slot':slot,'a_cell':a['index'],'b_cell':b['index'],'label':'跨组重复姿势'})
    for p,digest in spec['protected_files_before'].items():assert sha(p)==digest
    agrid=Image.open(RUN/'references/group_a_input.png').convert('RGBA').crop([48,48,688,688])
    bgrid=Image.open(RUN/'references/group_b_input.png').convert('RGBA').crop([48,48,688,688])
    assert agrid.tobytes()==bgrid.tobytes()
    carry=Image.open(RUN/'references/group_a_last_corrected_hd.png').convert('RGBA')
    bcarry=Image.open(RUN/'references/group_b_input.png').convert('RGBA').crop([704,48,1344,688])
    # Label pixels differ; character region is exactly the A end-frame HD pixels.
    ca=np.array(carry.crop([0,70,640,640]));cb=np.array(bcarry.crop([0,70,640,640]));visible=ca[:,:,3]>0
    assert np.array_equal(ca[:,:,3],cb[:,:,3]) and np.array_equal(ca[visible],cb[visible])
    report={'model':'gpt-image-2.5','jobs':2,'references_per_job':2,'groups':groups,'frames':frames,'seam_indices':seam,'drift_pairs':pairs,
        'cost_usd':sum(g['cost_usd'] for g in groups.values()),'native_size':[160,160],'preview_timing_ms':180,
        'accepted':False,'npk_created':False,'full_batch_started':False,'protected_files_unchanged':spec['protected_files_before'],
        'pose_order_note':spec['pose_order_note'],'validation':{'sequential_task_dependency':True,'fixed_master_cell_identical':True,
            'carry_visible_pixels_and_alpha_identical_to_a_hd_last_frame':True,'transparent_rgb_ignored_in_carry_comparison':True,
            'fourteen_and_four_frame_apng_pixel_readback':True},
        'findings':['两张实际均为2048×2048 RGBA，每次确实上传九宫格与同一张1536×1024高清设定图。',
            '14个新目标的高清图中均可见深蓝色尾体；尾鳍仍有简化，不能把“可见”当作符合设定。未补画或粘贴尾巴。',
            'B组IMG1前伸手臂明显高于原版，姿势仍有偏差；清边和平移校正无法修复这类局部错误。',
            'B返回的衔接格与A末帧并非像素原样保留；同姿势面板保留这次重绘差异，14帧播放不插入重复衔接格。',
            '已清除分隔线、标签和远处碎点并调整alpha；部分贴着人物的不透明灰边/色边仍需检查。',
            '每组统一缩放后逐帧平移，鞋底对齐原版对应帧；头脸、袖口、裙边仍存在生成差异，当前不标记通过。'],
        'assessment':'高清设定参考帮助保留了尾体，跨组连续性与局部姿势仍未完全锁定。这两组用于接缝和漂移检查，尚未验收。'}
    save(OUT/'review_report.json',report);save(RUN/'review_report.json',report)
    for p in RUN.iterdir():
        if p.is_file() and p.suffix in ['.json','.txt']:shutil.copy2(p,OUT/'evidence'/p.name)
    shutil.copy2(ROOT/'design/fatfish/references/UPSTREAM_CREDITS.md',OUT/'evidence/UPSTREAM_CREDITS.md')
    shutil.copy2(ROOT/'scripts/fatfish_grid_progression_preview.html',OUT/'preview.html')
    (OUT/'README.txt').write_text('宫格递进 v01 / 两张顺序生成\n每组为固定高清母版1格+上一轮末帧1格+7目标，额外上传同一高清三视设定图。\nA末帧IMG4的高清清边定位版本直接作为B衔接格，无原生小图回放大。\n14个新生成目标，10个参考帧位；有重复姿势用于漂移检查。ANI顺序/配时仍未知。\nraw_cells保留去标签后的源单格，clean_cells为透明通道清理，corrected为整组固定缩放+逐帧平移后的最近邻图，area为面积采样对照。\n不包含局部手脚变形、尾巴补画或NPK。原已通过走路和进度保留。\n',encoding='utf-8')
    save(OUT/'SHA256.json',{p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256.json'})
    shutil.copytree(OUT,ROOT/'output/Fatfish_Action_Dashboard/trials/grid_progression_v01',dirs_exist_ok=True)
    statuspath=ROOT/'preparation_status.json';status=json.loads(statuspath.read_text('utf-8'))
    status['grid_progression_trial']={'jobs':2,'task_ids':{n:g['task_id'] for n,g in groups.items()},'references_per_job':2,'cost_usd':report['cost_usd'],
        'preview_url':'http://127.0.0.1:8790/trials/grid_progression_v01/preview.html','path':str(OUT),'accepted':False,'npk_created':False,'full_batch_started':False}
    save(statuspath,status);print(json.dumps(status['grid_progression_trial']))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['inspect-a','inspect-b','register-a','register-b','finish']);a=ap.parse_args()
    if a.action=='finish':finish()
    else:
        name='group_a' if a.action.endswith('-a') else 'group_b'
        inspect(name) if a.action.startswith('inspect') else register(name)
