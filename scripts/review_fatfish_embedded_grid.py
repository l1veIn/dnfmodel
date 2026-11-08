"""Geometry-aware splitting and fair shared-transform preview of two sheet trials."""
import argparse
import json
import shutil
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fatfish_embedded_grid import ROOT,RUN,OUT,save,sha

TARGET_EYES=[[81,54],[84,54],[85,54],[82,54],[81,54],[81,54],[84,53],[83,55]]
# Filled from inspected, normalized 640px cell contact sheets. Fitting hints only.
EYES={'embedded_3x3':[[333,239],[372,239],[342,230],[342,229],[350,231],[348,221],[362,217],[351,219]],
      'embedded_2x3':[[382,194],[368,182],[375,190],[334,187],[372,192]]}

def cleanup(im):
    a=np.array(im);h,w=a.shape[:2];before=int((a[:,:,3]>0).sum())
    mx=max(1,round(w*10/640));my=max(1,round(h*10/640))
    a[:my]=0;a[-my:]=0;a[:,:mx]=0;a[:,-mx:]=0
    a[:round(h*60/640),:round(w*160/640)]=0
    n,labels,stats,_=cv2.connectedComponentsWithStats((a[:,:,3]>=128).astype('uint8'))
    assert n>1
    main=1+int(np.argmax(stats[1:,4]));r=max(1,round(w*8/640))
    near=cv2.dilate((labels==main).astype('uint8'),np.ones((2*r+1,2*r+1),'uint8'))>0
    a[~near]=0
    return Image.fromarray(a),dict(nontransparent_before=before,nontransparent_after=int((a[:,:,3]>0).sum()),
        main_bbox_xywh=stats[main,:4].tolist(),alpha_background_decontaminated=False,
        method='Fixed border/label removal, keep original alpha near largest alpha>=128 component; attached halos remain.')

def check(im,scale=2):
    h,w=im.height,im.width;yy,xx=np.indices((h,w));pat=(xx//8+yy//8)%2
    bg=np.where(pat[:,:,None]==0,np.array([229,236,244]),np.array([195,209,223])).astype('uint8')
    canvas=Image.fromarray(bg).convert('RGBA');canvas.alpha_composite(im)
    return canvas.resize((w*scale,h*scale),Image.Resampling.NEAREST)

def sole(im):
    a=np.asarray(im)[:,:,3]>=180;a[:int(im.height*.68)]=False
    ys=np.flatnonzero(a.sum(1)>=max(2,round(im.width/160*3)))
    if not len(ys):raise ValueError('No foot; inspect this crop')
    return int(ys[-1])

def load_split():
    spec=json.loads((RUN/'spec.json').read_text('utf-8'));journal=json.loads((RUN/'journal.json').read_text('utf-8'))
    receipts=json.loads((RUN/'receipts.json').read_text('utf-8'));groups={}
    for c in spec['configs']:
        name=c['name'];job=journal['jobs'][name];assert job['state']=='downloaded' and receipts[name]['status']=='done'
        assert len(job['files'])==1
        p=Path(job['files'][0])
        with Image.open(p) as im:sheet=im.convert('RGBA')
        sx=sheet.width/c['size'][0];sy=sheet.height/c['size'][1]
        groupdir=OUT/name
        for d in ['split','raw_native','registered']:(groupdir/d).mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,groupdir/'output_sheet.png');shutil.copy2(c['input_path'],groupdir/'input_sheet.png')
        records=[];images=[]
        for cell in c['cells']:
            x1,y1,x2,y2=cell['cell'];box=[round(x1*sx),round(y1*sy),round(x2*sx),round(y2*sy)]
            crop=sheet.crop(box);clean,report=cleanup(crop)
            key='ref' if cell['slot'] is None else f"{cell['slot']:03d}"
            crop.save(RUN/f'split/{name}_{key}_exact.png');clean.save(groupdir/f'split/{key}.png')
            clean.resize((160,160),Image.Resampling.NEAREST).save(groupdir/f'raw_native/{key}.png')
            records.append(dict(slot=cell['slot'],actual_cell_box=box,actual_cell_size=list(clean.size),cleanup=report))
            images.append(clean)
        alpha=np.asarray(sheet)[:,:,3]
        groups[name]={'config':c,'images':images,'records':records,'actual_size':list(sheet.size),'actual_alpha_extrema':list(sheet.getchannel('A').getextrema()),
            'transparent_fraction':float((alpha==0).mean()),'raw_file_sha256':sha(p),'task_id':receipts[name]['id'],'cost_usd':receipts[name]['cost_usd']}
    return spec,groups

def inspect():
    spec,groups=load_split();font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',16)
    for name,g in groups.items():
        items=g['images'];contact=Image.new('RGB',(640*3,680*3),'#172536');d=ImageDraw.Draw(contact)
        for i,im in enumerate(items):
            x=i%3*640;y=i//3*680
            view=im.resize((640,640),Image.Resampling.NEAREST)
            bg=Image.new('RGBA',view.size,'#cad6e2');bg.alpha_composite(view)
            bd=ImageDraw.Draw(bg)
            for v in range(0,640,40):
                bd.line((v,0,v,640),fill='#6789a566');bd.line((0,v,640,v),fill='#6789a566')
                bd.text((v+2,62),str(v),font=font,fill='#9d4343');bd.text((2,v+2),str(v),font=font,fill='#9d4343')
            contact.paste(bg.convert('RGB'),(x,y+36));d.text((x+10,y+8),'REF' if i==0 else f'IMG {i-1:03d}',font=font,fill='#d4e8f6')
        contact.save(RUN/f'qa/{name}_coordinate_contact.png')
        # Head strips permit visual placement of the same visible eye in each generated pose.
        heads=Image.new('RGB',(640*3,340*3),'#172536');hd=ImageDraw.Draw(heads)
        for i,im in enumerate(items):
            view=im.resize((640,640),Image.Resampling.NEAREST)
            bg=Image.new('RGBA',view.size,'#cad6e2');bg.alpha_composite(view)
            crop=bg.crop((240,80,480,240)).resize((480,320),Image.Resampling.NEAREST)
            x=i%3*640;y=i//3*340;heads.paste(crop.convert('RGB'),(x,y+20))
            hd.text((x+4,y),('REF' if i==0 else f'IMG{i-1:03d}')+' x240..480 / y80..240 @2x',font=font,fill='#cee3f1')
        heads.save(RUN/f'qa/{name}_eyes.png')
    print(json.dumps({k:{x:v for x,v in g.items() if x not in ['images','config','records']} for k,g in groups.items()}))

def sample(im,scale,translate):
    yy,xx=np.indices((160,160),dtype='float64')
    # Map from normalized 640px local coordinates directly to the ORIGINAL crop, sampling once.
    sx=np.rint((xx-translate[0])/scale*im.width/640).astype('int32')
    sy=np.rint((yy-translate[1])/scale*im.height/640).astype('int32')
    valid=(sx>=0)&(sx<im.width)&(sy>=0)&(sy<im.height);src=np.asarray(im);a=np.zeros((160,160,4),'uint8');a[valid]=src[sy[valid],sx[valid]]
    return Image.fromarray(a)

def finish():
    spec,groups=load_split();assert len(EYES)==2
    (OUT/'original').mkdir(exist_ok=True);(OUT/'evidence').mkdir(exist_ok=True)
    for i in range(8):shutil.copy2(RUN/f'references/original_{i:03d}.png',OUT/f'original/{i:03d}.png')
    shutil.copy2(RUN/'references/master_native.png',OUT/'master_native.png')
    for name,g in groups.items():
        images=g.pop('images');c=g.pop('config');targets=images[1:];eyes=EYES[name]
        assert len(eyes)==len(targets)
        # Same first five fitting poses for both groups, one constant transform per group.
        target_eyes=np.array(TARGET_EYES[:5]);raw_eyes=np.array(eyes[:5],dtype='float64')
        raw_bottoms=np.array([sole(im)*640/im.height for im in targets[:5]])
        target_bottoms=np.array([sole(Image.open(OUT/f'original/{i:03d}.png').convert('RGBA')) for i in range(5)])
        scale=float(np.median((target_bottoms-target_eyes[:,1])/(raw_bottoms-raw_eyes[:,1])))
        assert .12<scale<.32
        translate=np.median(target_eyes-scale*raw_eyes,axis=0)
        g['shared_transform']={'scale_from_normalized_640':scale,'translation_native':translate.tolist(),'same_for_every_target':True,
            'fit_slots':[0,1,2,3,4],'fitting_method':'Median eye/sole scale and median eye translation; manual eye points, detected alpha sole.',
            'interpolation':'NEAREST','samples_from_actual_crop_once':True,'local_limb_warps':False}
        g['normalized_eye_hints']=eyes
        frames=[]
        for i,im in enumerate(targets):
            fitted=sample(im,scale,translate);fitted.save(OUT/name/f'registered/{i:03d}.png');frames.append(fitted)
            g['records'][i+1]['registered_bottom_y']=sole(fitted)
        anim=[check(im,3) for im in frames[:5]]
        anim[0].save(OUT/name/'common_five_animation.png',save_all=True,append_images=anim[1:],duration=120,loop=0,disposal=0,blend=0)
        with Image.open(OUT/name/'common_five_animation.png') as ap:
            assert ap.n_frames==5
            for i,frame in enumerate(anim):ap.seek(i);assert np.array_equal(np.asarray(ap.convert('RGBA')),np.asarray(frame))
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)
    contact=Image.new('RGB',(1080,5*380+50),'#172536');d=ImageDraw.Draw(contact)
    for col,label in enumerate(['原版参考','九宫格：1 参考＋8 目标','六宫格：1 参考＋5 目标']):d.text((col*360+12,8),label,font=font,fill='#c8e2ed')
    for i in range(5):
        paths=[OUT/f'original/{i:03d}.png',OUT/f'embedded_3x3/registered/{i:03d}.png',OUT/f'embedded_2x3/registered/{i:03d}.png']
        for j,path in enumerate(paths):
            im=Image.open(path).convert('RGBA');contact.paste(check(im,2).convert('RGB'),(j*360+20,50+i*380))
            d.text((j*360+22,50+i*380+326),f'IMG {i:03d}',font=font,fill='#9dc2d5')
    contact.save(OUT/'contact_common.png')
    protected={p:sha(p) for p in spec['protected_files_before']}
    assert protected==spec['protected_files_before']
    report={'model':'gpt-image-2.5','provider':'65535','generation_jobs':2,'references_per_job':1,'groups':groups,
        'common_slots':list(range(5)),'native_size':[160,160],'preview_timing_ms':120,'accepted':False,'npk_created':False,
        'assessment':'两组都实现了同图主帧驱动的角色替换；本次六宫格未显示明确的整体优势，不能据此判断更少帧必然更好。',
        'findings':['左上参考格在两张返回图中也被重绘和放大；未能原样锁定主帧，原批准主帧仍单独冻结。',
            '两组共同 IMG0–4 均可识别对应摆臂和迈步，但手部、腿型及发饰/裙边仍有差异；六宫格 IMG0 的后侧摆臂手部附近出现疑似多余手形。',
            '实际九宫格为 2048×2048；六宫格为 1696×2528。六宫格没有按所请求的 1365×2048 返回，已按实际格坐标拆帧并统一原生显示。',
            '两张有真正 alpha，但九宫格有蓝色边缘、六宫格有较宽灰色半透明残留；只清理标签和远处碎点，没有修饰连接着角色的光边。',
            '每组使用同一个整体缩放/位移，再一次最近邻取样；保留帧间偏移，无逐帧手脚变形修正，以便比较生成质量。',
            '本次每种布局仅一张随机样本；帧数、排布、画布比例及实际输出尺寸均可能影响效果，尚不能归因于注意力。'],
        'limitations':spec['experiment_limitations'],'protected_files_unchanged':protected,
        'validation':{'apng_five_frame_exact_pixel_readback':True,'master_not_in_walk_playback':True,'local_limb_warps':False}}
    save(OUT/'review_report.json',report);save(RUN/'review_report.json',report)
    for p in RUN.iterdir():
        if p.is_file() and p.suffix in ['.json','.txt']:shutil.copy2(p,OUT/'evidence'/p.name)
    shutil.copy2(ROOT/'design/fatfish/references/UPSTREAM_CREDITS.md',OUT/'evidence/UPSTREAM_CREDITS.md')
    shutil.copy2(ROOT/'scripts/fatfish_embedded_grid_preview.html',OUT/'preview.html')
    (OUT/'README.txt').write_text('单图内置主帧 / 9格与6格对照\n打开 preview.html 需本地HTTP服务；已挂在 http://127.0.0.1:8790/trials/embedded_grid_compare_v01/preview.html\n每组仅生成一次，每次只传一张拼图。共同原版帧位IMG0–4，参考主帧不混入步行播放。\nraw_native为拆格直接最近邻；registered每组使用恒定缩放和位移，不作局部手脚修正。\n原始返回图及实际上传图保留；当前不是完整走路循环或可用NPK。\n原已通过步行、进度记录、主帧和NPK保留原样。\n',encoding='utf-8')
    manifest={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256.json'}
    save(OUT/'SHA256.json',manifest)
    shutil.copytree(OUT,ROOT/'output/Fatfish_Action_Dashboard/trials/embedded_grid_compare_v01',dirs_exist_ok=True)
    statuspath=ROOT/'preparation_status.json';status=json.loads(statuspath.read_text('utf-8'))
    status['embedded_grid_compare_trial']={'model':report['model'],'jobs':2,'accepted':False,'references_per_job':1,
        'preview_url':'http://127.0.0.1:8790/trials/embedded_grid_compare_v01/preview.html','path':str(OUT),
        'task_ids':{k:v['task_id'] for k,v in groups.items()},'cost_usd':sum(v['cost_usd'] for v in groups.values()),'npk_created':False}
    save(statuspath,status)
    print(json.dumps({'preview_url':status['embedded_grid_compare_trial']['preview_url'],'groups':{k:v['shared_transform'] for k,v in groups.items()}}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['inspect','finish']);a=p.parse_args()
    inspect() if a.action=='inspect' else finish()
