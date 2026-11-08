"""Split one six-pose trial; preserve HD cells and compare a single nearest lookup."""
import argparse
import json
import shutil
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from fatfish_fixed_three_trial import ROOT,RUN,OUT,NAME,save,sha
from fatfish_grid_walk import original
from fatfish_grid_postprocess_probe import cleanup,nearest
from review_fatfish_embedded_grid import sole,TARGET_EYES

POS=[48,704,1360]

def split():
    journal=json.loads((RUN/'journal.json').read_text('utf-8'));rec=journal['jobs'][NAME]
    assert rec['state']=='downloaded' and len(rec['files'])==1
    src=Image.open(rec['files'][0]);assert src.mode=='RGBA','No true alpha output; inspect without silently keying.'
    sheet=src.copy();a=np.asarray(sheet);assert (a[:,:,3]==0).any()
    for d in ['original','exact_cells','isolated_hd','clean_hd','registered_hd','nearest','raw_nearest','qa','evidence','references']:(OUT/d).mkdir(parents=True,exist_ok=True)
    shutil.copy2(rec['files'][0],OUT/'output_sheet.png');shutil.copy2(RUN/'references/input_grid_2048.png',OUT/'input_sheet.png')
    shutil.copy2(RUN/'references/appearance_original_1024.png',OUT/'references/appearance_original_1024.png')
    items=[]
    for slot in range(6):
        c=slot+3;x,y=POS[c%3],POS[c//3]
        override=globals().get('CELL_BOXES_OVERRIDE')
        box=override[slot] if override is not None else [round(v) for v in [x*sheet.width/2048,y*sheet.height/2048,(x+640)*sheet.width/2048,(y+640)*sheet.height/2048]]
        raw=sheet.crop(box);raw.save(OUT/f'exact_cells/{slot:03d}.png');arr=np.array(raw);h,w=arr.shape[:2]
        # Only remove known labels/gutters and distant disconnected pieces; preserve nearby accessories.
        mx=max(1,round(w*10/640));my=max(1,round(h*10/640))
        arr[:my]=0;arr[-my:]=0;arr[:,:mx]=0;arr[:,-mx:]=0;arr[:round(h*62/640),:round(w*420/640)]=0
        n,labels,stats,_=cv2.connectedComponentsWithStats((arr[:,:,3]>=128).astype('uint8'));assert n>1
        main=1+int(np.argmax(stats[1:,4]));core=(labels==main).astype('uint8')
        r=max(1,round(w*45/640));near=cv2.dilate(core,np.ones((2*r+1,2*r+1),'uint8'))>0
        for j in range(1,n):
            if j==main:continue
            cx,cy,cw,ch,pixels=stats[j]
            line=(ch>h*.65 and cw<w*.04) or (cw>w*.65 and ch<h*.04)
            if pixels>=max(40,round(w*h/409600*120)) and not line and near[labels==j].any():core[labels==j]=1
        r=max(1,round(w*8/640));keep=cv2.dilate(core,np.ones((2*r+1,2*r+1),'uint8'))>0;arr[~keep]=0
        isolated=Image.fromarray(arr);isolated.save(OUT/f'isolated_hd/{slot:03d}.png')
        clean,alpha=cleanup(isolated);clean.save(OUT/f'clean_hd/{slot:03d}.png');original(slot).save(OUT/f'original/{slot:03d}.png')
        clean.resize((160,160),Image.Resampling.NEAREST).save(OUT/f'raw_nearest/{slot:03d}.png')
        items.append({'slot':slot,'cell_box':box,'cell_size':list(raw.size),'alpha_cleanup':alpha})
    report={'task_id':rec['task_id'],'sheet_size':list(sheet.size),'sheet_sha256':sha(rec['files'][0]),'alpha_extrema':list(sheet.getchannel('A').getextrema()),
            'transparent_fraction':float((a[:,:,3]==0).mean()),'cells':items}
    save(RUN/'split_report.json',report)
    return report

def inspect():
    report=split();board=Image.new('RGB',(1440,960),'#172536');d=ImageDraw.Draw(board);font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',15)
    heads=Image.new('RGB',(1200,760),'#172536');hd=ImageDraw.Draw(heads)
    for slot in range(6):
        im=Image.open(OUT/f'isolated_hd/{slot:03d}.png').convert('RGBA').resize((640,640),Image.Resampling.NEAREST)
        bg=Image.new('RGBA',(640,640),'#cbd5e1');bg.alpha_composite(im)
        x=slot%3*480;y=slot//3*480;board.paste(bg.resize((456,456),Image.Resampling.LANCZOS).convert('RGB'),(x,y+24));d.text((x+8,y+3),f'IMG {slot:03d}',font=font,fill='#d5eaf3')
        dd=ImageDraw.Draw(bg)
        for v in range(100,481,20):
            dd.line((v,80,v,340),fill='#ab6e6e80');dd.text((v,82),str(v),font=font,fill='#8a3030')
        for v in range(100,341,20):
            dd.line((200,v,480,v),fill='#ab6e6e80');dd.text((200,v),str(v),font=font,fill='#8a3030')
        hc=bg.crop((200,80,480,340)).resize((392,364),Image.Resampling.NEAREST)
        x=slot%3*400;y=slot//3*380;heads.paste(hc.convert('RGB'),(x,y+16));hd.text((x+6,y),f'IMG {slot:03d} / x200..480 y80..340',font=font,fill='#d0e6ef')
    board.save(RUN/'qa/six_raw_contact.png');heads.save(RUN/'qa/eye_coordinates.png')
    print(json.dumps({k:v for k,v in report.items() if k!='cells'}))

def register():
    split_report=json.loads((RUN/'split_report.json').read_text('utf-8'));ann=json.loads((RUN/'annotations.json').read_text('utf-8'));assert len(ann['eyes'])==6
    normalized=[Image.open(OUT/f'clean_hd/{i:03d}.png').convert('RGBA').resize((640,640),Image.Resampling.NEAREST) for i in range(6)]
    ratios=[(sole(original(i))-TARGET_EYES[i][1])/(sole(normalized[i])-ann['eyes'][i][1]) for i in range(6)]
    s=float(np.median(ratios));assert .1<s<.4
    t=np.median([np.array(TARGET_EYES[i])-s*np.array(ann['eyes'][i]) for i in range(6)],axis=0);records=[]
    for slot in range(6):
        im=normalized[slot];eye=ann['eyes'][slot];guide=original(slot);base=nearest(im,s,t)
        dx=int(round(TARGET_EYES[slot][0]-(s*eye[0]+t[0])));dy=int(sole(guide)-sole(base));shift=t+np.array([dx,dy])
        actual=Image.open(OUT/f'clean_hd/{slot:03d}.png').convert('RGBA');hs=actual.width/640;vs=actual.height/640
        yy,xx=np.indices((160,160));sx=np.rint((xx-shift[0])/s*hs).astype('int32');sy=np.rint((yy-shift[1])/s*vs).astype('int32')
        valid=(sx>=0)&(sx<actual.width)&(sy>=0)&(sy<actual.height);arr=np.zeros((160,160,4),'uint8');src=np.asarray(actual);arr[valid]=src[sy[valid],sx[valid]];nn=Image.fromarray(arr)
        nn.save(OUT/f'nearest/{slot:03d}.png')
        hd=actual.convert('RGBa').transform((640,640),Image.Transform.AFFINE,(hs/(s*4),0,-shift[0]*hs/s,0,vs/(s*4),-shift[1]*vs/s),Image.Resampling.BICUBIC).convert('RGBA')
        hd.save(OUT/f'registered_hd/{slot:03d}.png')
        records.append({'slot':slot,'eye_annotation_640':eye,'integer_translation_native':[dx,dy],'translation_native':shift.tolist(),
             'target_sole_y':sole(guide),'nearest_sole_y':sole(nn),'nearest_bbox':list(nn.getchannel('A').getbbox()),
             'hd_bbox':list(hd.getchannel('A').getbbox()),'local_limb_warp':False})
    save(RUN/'registration.json',{'shared_scale_from_640_to_native':s,'shared_translation_native':t.tolist(),'per_frame_scaling':False,'frames':records,
         'limitations':'Manual eye x and source shoe rows are fitting controls, not independent proof of no foot sliding. No correction of limb pose, anatomy or costume drift.'})
    print(json.dumps({'shared_scale':s,'translations':[r['integer_translation_native'] for r in records],'sole_pairs':[[r['target_sole_y'],r['nearest_sole_y']] for r in records]}))

def finish():
    split_report=json.loads((RUN/'split_report.json').read_text('utf-8'));reg=json.loads((RUN/'registration.json').read_text('utf-8'));receipt=json.loads((RUN/'receipt.json').read_text('utf-8'))
    spec=json.loads((RUN/'spec.json').read_text('utf-8'))
    for p,h in spec['protected_files_before'].items():assert sha(p)==h
    review=json.loads((RUN/'visual_review.json').read_text('utf-8'))
    report={**split_report,'model':'gpt-image-2.5','provider':'65535','cost_usd':receipt.get('cost_usd'),'new_jobs':1,'target_slots':list(range(6)),
       'reference_count':2,'appearance_source_original_hd':True,'registration':reg,'review':review,'accepted':False,'complete_walk_cycle':False,
       'verified_ani_sequence':False,'timing':'180ms per pose for inspection only; original ANI timing unknown.',
       'protected_files_unchanged':spec['protected_files_before'],'npk_created':False,'full_batch_started':False,'game_changed':False}
    save(OUT/'report.json',report);save(RUN/'review_report.json',report)
    # Contact sheet preserves the HD render; NN comparison is deliberately enlarged without inventing detail.
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18);frames=[]
    for slot in range(6):
        board=Image.new('RGBA',(960,386),'#172536');d=ImageDraw.Draw(board)
        for j,(folder,title) in enumerate([('original','原版姿势'),('registered_hd','高清保留 · 相同显示尺寸'),('nearest','最近邻 · 160px 窗口')]):
            im=Image.open(OUT/f'{folder}/{slot:03d}.png').convert('RGBA');im=im.resize((320,320),Image.Resampling.NEAREST if folder!='registered_hd' else Image.Resampling.LANCZOS)
            yy,xx=np.indices((320,320));pat=(xx//16+yy//16)%2;b=np.where(pat[:,:,None]==0,[224,233,242],[193,207,222]).astype('uint8');bg=Image.fromarray(b).convert('RGBA');bg.alpha_composite(im)
            board.alpha_composite(bg,(j*320,40));d.text((j*320+8,7),title,font=font,fill='#d2e9f3')
        d.text((12,360),f'IMG {slot:03d} / 六帧局部序列，首尾未闭环',font=font,fill='#a7bfd2');frames.append(board)
    frames[0].save(OUT/'comparison_animation.png',save_all=True,append_images=frames[1:],duration=180,loop=0,disposal=0,blend=0)
    with Image.open(OUT/'comparison_animation.png') as dec:
        assert dec.n_frames==6
        for i,im in enumerate(frames):dec.seek(i);assert np.array_equal(np.array(dec.convert('RGBA')),np.array(im))
    contact=Image.new('RGB',(960,386*6))
    for i,im in enumerate(frames):contact.paste(im.convert('RGB'),(0,386*i))
    contact.save(OUT/'six_frame_comparison.png')
    shutil.copy2(ROOT/'scripts/fatfish_fixed_three_trial_preview.html',OUT/'preview.html')
    for p in RUN.iterdir():
        if p.is_file() and p.suffix in ['.json','.txt']:shutil.copy2(p,OUT/'evidence'/p.name)
    shutil.copy2(ROOT/'design/fatfish/references/UPSTREAM_CREDITS.md',OUT/'evidence/UPSTREAM_CREDITS.md')
    (OUT/'README.txt').write_text('固定三参考＋六帧高清小样 v01\n两张输入：已冻结的三参考六目标九宫格＋真正的1024px高清造型原图。\nexact_cells保留原始单格，isolated_hd只去标签和远处碎点，clean_hd另存alpha清边版本，registered_hd保留640px工作窗口，nearest为一次最近邻采样的160px窗口。\n所有六帧只使用统一缩放和逐帧平移；未局部修手脚，未补画尾巴。局部播放不是完整步行循环，帧序和180ms配时未由ANI验证。\n当前仅一轮试验，等待用户评价；原已通过走路记录和NPK保持原样。\n',encoding='utf-8')
    save(OUT/'SHA256.json',{p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256.json'})
    shutil.copytree(OUT,ROOT/'output/Fatfish_Action_Dashboard/trials/fixed_three_trial_v01',dirs_exist_ok=True)
    st=ROOT/'preparation_status.json';status=json.loads(st.read_text('utf-8'));status['fixed_three_six_trial']={'jobs':1,'task_id':receipt['id'],'cost_usd':receipt.get('cost_usd'),'model':'gpt-image-2.5','target_slots':list(range(6)),
        'preview_url':'http://127.0.0.1:8790/trials/fixed_three_trial_v01/preview.html','path':str(OUT),'accepted':False,'npk_created':False,'full_batch_started':False}
    save(st,status);print(json.dumps(status['fixed_three_six_trial']))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['inspect','register','finish']);a=ap.parse_args();globals()[a.action]()
