"""Non-generative alpha/registration/sampling probe on the existing eight-pose sheet."""
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from fatfish_grid_walk import ROOT,save,sha
from review_fatfish_embedded_grid import TARGET_EYES,EYES,sole

SOURCE=ROOT/'output/Fatfish_Embedded_Grid_Compare_v01'
OUT=ROOT/'output/Fatfish_Grid_Postprocess_v02'
RUN=ROOT/'design/fatfish/grid_postprocess_v02'

def cleanup(im):
    a=np.array(im);old=a[:,:,3].copy()
    # Conservative diagnostic: transparent <=96, opaque >=240, smooth transition.
    # No color key, erosion, silhouette editing or RGB repainting.
    alpha=np.clip((old.astype('float32')-96)/(240-96),0,1)
    a[:,:,3]=np.rint(alpha*255).astype('uint8');a[a[:,:,3]==0,:3]=0
    return Image.fromarray(a),{'alpha_input_1_to_127':int(((old>0)&(old<128)).sum()),
        'nonzero_alpha_before':int((old>0).sum()),'nonzero_alpha_after':int((a[:,:,3]>0).sum()),
        'rule':'alpha=clip((original_alpha-96)/144,0,1); RGB unchanged where visible; transparent RGB cleared',
        'warning':'May remove fine translucent hair/lace. This threshold is only a trial, not a universal matte solution.'}

def nearest(im,s,t):
    yy,xx=np.indices((160,160),dtype='float64');sx=np.rint((xx-t[0])/s).astype('int32');sy=np.rint((yy-t[1])/s).astype('int32')
    valid=(sx>=0)&(sx<im.width)&(sy>=0)&(sy<im.height);a=np.zeros((160,160,4),'uint8');src=np.asarray(im);a[valid]=src[sy[valid],sx[valid]]
    return Image.fromarray(a)

def area(im,s,t):
    """Exact piecewise-constant box integration with premultiplied alpha."""
    src=np.asarray(im).astype('float64')/255;src[:,:,:3]*=src[:,:,3:4]
    h,w=src.shape[:2];integral=np.pad(src.cumsum(0).cumsum(1),((1,0),(1,0),(0,0)))
    yy,xx=np.indices((160,160),dtype='float64')
    def f(x,y):
        x=np.clip(x,0,w);y=np.clip(y,0,h);x0=np.floor(x).astype('int32');y0=np.floor(y).astype('int32')
        x1=np.minimum(x0+1,w);y1=np.minimum(y0+1,h);fx=(x-x0)[:,:,None];fy=(y-y0)[:,:,None]
        return (integral[y0,x0]*(1-fx)*(1-fy)+integral[y0,x1]*fx*(1-fy)+integral[y1,x0]*(1-fx)*fy+integral[y1,x1]*fx*fy)
    x0=(xx-.5-t[0])/s+.5;x1=(xx+.5-t[0])/s+.5;y0=(yy-.5-t[1])/s+.5;y1=(yy+.5-t[1])/s+.5
    out=np.clip((f(x1,y1)-f(x0,y1)-f(x1,y0)+f(x0,y0))*s*s,0,1)
    np.divide(out[:,:,:3],out[:,:,3:4],out=out[:,:,:3],where=out[:,:,3:4]>1e-8)
    out[out[:,:,3]<1e-8,:3]=0
    return Image.fromarray(np.rint(np.clip(out,0,1)*255).astype('uint8'))

def display(im,bg='checker',zoom=2):
    if bg=='checker':
        yy,xx=np.indices((160,160));pat=(xx//8+yy//8)%2
        a=np.where(pat[:,:,None]==0,np.array([226,235,244]),np.array([194,208,222])).astype('uint8');b=Image.fromarray(a).convert('RGBA')
    else:b=Image.new('RGBA',(160,160),bg)
    b.alpha_composite(im);return b.resize((160*zoom,160*zoom),Image.Resampling.NEAREST)

def main():
    if (RUN/'report.json').exists():raise RuntimeError('Keep existing diagnostic unchanged.')
    RUN.mkdir(parents=True,exist_ok=True)
    for d in ['before','clean_nearest','clean_area','alpha_source']:(OUT/d).mkdir(parents=True,exist_ok=True)
    oldreport=json.loads((SOURCE/'review_report.json').read_text('utf-8'));g=oldreport['groups']['embedded_3x3'];fit=g['shared_transform'];s=fit['scale_from_normalized_640'];t=np.array(fit['translation_native'])
    sequences=[[],[],[],[]];records=[]
    for i in range(8):
        p=SOURCE/f'embedded_3x3/split/{i:03d}.png';src=Image.open(p).convert('RGBA');assert src.size==(640,640)
        original=Image.open(SOURCE/f'original/{i:03d}.png').convert('RGBA');before=Image.open(SOURCE/f'embedded_3x3/registered/{i:03d}.png').convert('RGBA')
        clean,alpha_report=cleanup(src);clean.save(OUT/f'alpha_source/{i:03d}.png')
        base=nearest(clean,s,t)
        # Integer translation only. No per-frame resizing/rotation/limb deformation.
        dx=round(TARGET_EYES[i][0]-(EYES['embedded_3x3'][i][0]*s+t[0]))
        dy=sole(original)-sole(base)
        adjusted=t+np.array([dx,dy]);nn=nearest(clean,s,adjusted);box=area(clean,s,adjusted)
        before.save(OUT/f'before/{i:03d}.png');nn.save(OUT/f'clean_nearest/{i:03d}.png');box.save(OUT/f'clean_area/{i:03d}.png')
        for seq,im in zip(sequences,[original,before,nn,box],strict=True):seq.append(im)
        records.append({'slot':i,'source_sha256':sha(p),'alpha':alpha_report,'integer_translation_xy':[int(dx),int(dy)],
            'original_bottom_y':sole(original),'before_bottom_y':sole(before),'clean_nearest_bottom_y':sole(nn),
            'eye_x_hint_fitted':True,'vertical_alignment':'Same-frame original lowest solid shoe row; no assumption of a flat y across poses.',
            'limitations':'Eye/sole are fitting controls, not independent foot contact validation; hand poses and anatomy are not corrected.'})
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17)
    labels=['原版参考','上一版：整组矫正＋最近邻','清边＋逐帧平移＋最近邻','清边＋逐帧平移＋面积采样']
    for bg,name in [('checker','contact_checker.png'),('#14202e','contact_dark.png'),('#ffffff','contact_white.png')]:
        contact=Image.new('RGB',(1280,64+360*3),'#172536');d=ImageDraw.Draw(contact)
        for col,label in enumerate(labels):d.text((col*320+8,10),label,font=font,fill='#d3e6ef')
        for row,i in enumerate([0,2,3]):
            for col,seq in enumerate(sequences):
                contact.paste(display(seq[i],bg).convert('RGB'),(col*320,64+row*360));d.text((col*320+10,64+row*360+324),f'IMG {i:03d}',font=font,fill='#9dc4d7')
        contact.save(OUT/name)
    animation=[]
    for i in range(8):
        board=Image.new('RGBA',(1280,386),'#172536');d=ImageDraw.Draw(board)
        for col,seq in enumerate(sequences):
            d.text((col*320+8,8),labels[col],font=font,fill='#d3e6ef');board.alpha_composite(display(seq[i]),(col*320,42))
        d.text((12,363),f'IMG {i:03d} / 仅局部序列；重复首尾不代表完整循环',font=font,fill='#a1bfd1');animation.append(board)
    animation[0].save(OUT/'comparison_animation.png',save_all=True,append_images=animation[1:],duration=180,loop=0,disposal=0,blend=0)
    with Image.open(OUT/'comparison_animation.png') as decoded:
        assert decoded.n_frames==8
        for i,im in enumerate(animation):decoded.seek(i);assert np.array_equal(np.asarray(decoded.convert('RGBA')),np.asarray(im))
    for p,digest in oldreport['protected_files_unchanged'].items():assert sha(p)==digest
    source_master=ROOT/'design/fatfish/action_samples_v01/raw/idle_01_0.png'
    protected=dict(oldreport['protected_files_unchanged']);protected[str(source_master)]=sha(source_master)
    report={'generation_requests':0,'source_trial':'embedded_grid_compare_v01','frame_slots':list(range(8)),
        'purpose':'Non-generative feasibility probe, not a finished correction or new accepted animation.',
        'scale_fixed_across_all_frames':s,'alpha_variant':'Remap 96..240 to 0..255 without RGB repainting or shape erosion.',
        'sampling':['single nearest source lookup','single premultiplied-alpha box integration'],
        'registration':'Constant scale; per-frame integer translations from approximate manual eye-x and same-frame original lowest shoe row.',
        'no_local_limb_warp':True,'not_complete_walk_loop':True,'accepted':False,'frames':records,
        'high_resolution_master':{'path':str(source_master),'size':[1024,1024],'sha256':sha(source_master),'is_source_of_approved_v04':True},
        'protected_files_unchanged':protected,'validation':{'all_eight_apng_frames_pixel_exact':True},
        'limitations':['Alpha adjustment can trim thin translucent hair/lace; opaque RGB contamination remains.',
            'Global translation cannot fix disconnected hands, extra fingers, limb length, pose differences or local costume drift.',
            'Original foot y and eye x are fitting references, not proof of no sliding.',
            'Box filtering and nearest have different softness/detail loss; judge at native size.',
            'No new high-resolution generation has been tested in this probe.']}
    save(RUN/'report.json',report);save(OUT/'report.json',report)
    (OUT/'README.txt').write_text('宫格递进后处理诊断 v02\n未调用生图，沿用上一轮九宫格8个目标。\ncomparison_animation.png 为八帧四栏同步动画；contact_checker/dark/white 对照三帧。\n第3/4栏用相同的固定缩放与逐帧整数平移，只改变采样方式。清边仅调整alpha，不修手脚或重新画轮廓。\n当前为试验，不能视为完整走路循环或验收通过；细发丝、鞋跟、袖口仍需检查。\n',encoding='utf-8')
    save(OUT/'SHA256.json',{p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256.json'})
    print(json.dumps({'output':str(OUT),'generation_requests':0,'translations':[r['integer_translation_xy'] for r in records],
        'bottom_y_before':[r['before_bottom_y'] for r in records],'bottom_y_after':[r['clean_nearest_bottom_y'] for r in records],
        'bottom_y_original':[r['original_bottom_y'] for r in records]}))

if __name__=='__main__':main()
