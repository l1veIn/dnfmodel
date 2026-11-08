"""Transparent extraction, fixed per-clip scale, native registration, and slot mapping."""
from __future__ import annotations
import sys,json,shutil,subprocess
from pathlib import Path
import av,cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
from fatfish_full_ref2va import ROOT,RUN,OUT,WEB,TRIAL,publish,read,save,sha

def matte(im):
    rgb=np.asarray(im.convert('RGB'),dtype=np.float32);h,w=rgb.shape[:2]
    border=np.concatenate([rgb[:6].reshape(-1,3),rgb[-6:].reshape(-1,3),rgb[:,:6].reshape(-1,3),rgb[:,-6:].reshape(-1,3)])
    bg=np.median(border,axis=0);dist=np.max(np.abs(rgb-bg),axis=2);chroma=rgb.max(2)-rgb.min(2);luma=rgb.mean(2)
    possible=(dist>9)&((chroma>9)|(luma>195)|(luma<48))
    n,labels,stats,_=cv2.connectedComponentsWithStats(possible.astype('uint8'),8)
    if n<2:raise RuntimeError('No visible subject after gray-background extraction')
    main=1+int(np.argmax(stats[1:,4]));x,y,bw,bh,area=stats[main];keep=labels==main
    for lab in range(1,n):
        xx,yy,ww,hh,a=stats[lab]
        if a>=4 and xx>=x-18 and yy>=y-18 and xx+ww<=x+bw+18 and yy+hh<=y+bh+18:keep|=labels==lab
    # Reconnect only tiny antialias gaps. Neutral mid-gray shadows remain excluded.
    keep=cv2.morphologyEx(keep.astype('uint8'),cv2.MORPH_CLOSE,np.ones((2,2),'uint8')).astype(bool)
    alpha=np.clip((dist-9)/22,0,1)*keep
    result=np.zeros((h,w,4),'uint8');covered=alpha>.02;a=alpha[covered,None]
    result[covered,:3]=np.clip(np.round((rgb[covered]-bg*(1-a))/np.maximum(a,.02)),0,255).astype('uint8');result[:,:,3]=np.round(alpha*255).astype('uint8')
    return Image.fromarray(result)
def original(slot):
    with Image.open(ROOT/f'materials/female_mage/reference_composite/frames/{slot:04d}.png') as im:
        world=Image.new('RGBA',(500,500));world.alpha_composite(im.convert('RGBA'),(185,0));return world
def bbox(im):
    a=np.asarray(im.getchannel('A'));y,x=np.where(a>=160)
    if len(x)<25:raise RuntimeError('Empty or implausibly small sprite')
    return (int(x.min()),int(y.min()),int(x.max())+1,int(y.max())+1)
def head_x(im,b):
    a=np.asarray(im.getchannel('A'));top=b[1];bottom=top+max(4,int((b[3]-top)*.28));yy,xx=np.where(a[top:bottom]>=160)
    return float(np.median(xx)) if len(xx) else (b[0]+b[2])/2
def comp_small(im):
    base=Image.new('RGBA',im.size,(128,128,128,255));base.alpha_composite(im);return np.asarray(base.convert('RGB').resize((96,56),Image.Resampling.BILINEAR)).astype('float32')
def choose(c,cutouts):
    count=c['end']-c['start']+1
    overrides=RUN/'frame_selection_overrides.json'
    if overrides.exists() and c['id'] in read(overrides):
        selected=read(overrides)[c['id']];assert sha(c['video'])==selected['video_sha256']
        assert len(selected['frames'])==count and all(0<=i<124 for i in selected['frames'])
        return selected['frames'],{'selection':selected['reason'],'visually_checked':True}
    if not c['cycle']:
        cumulative=np.cumsum(c['frame_ms']);centers=cumulative-np.asarray(c['frame_ms'])/2
        return [min(116,max(4,round(12+t/cumulative[-1]*96))) for t in centers],{'selection':'Held prefix12, action96, held suffix16; original-pose centers sampled monotonically.'}
    small=[comp_small(im) for im in cutouts];expected=48 if c['start'] in [10,14,53,155,163] else 24;best=None
    for period in range(18,65):
        for start in range(16,124-period-5):
            a,b=small[start],small[start+period];mask=(np.max(abs(a-128),2)>20)|(np.max(abs(b-128),2)>20)
            score=float(np.abs(a-b)[mask].mean())+abs(period-expected)*.025+abs(start-40)*.002
            if c['start'] in [0,18]:
                middle=small[start+period//2];motion=float(np.abs(a-middle)[mask].mean())
                if motion<2:score+=20
            if best is None or score<best[0]:best=(score,start,period)
    score,start,period=best
    return [min(123,start+round(i*period/count)) for i in range(count)],{'selection':'Best coherent loop window by foreground endpoint similarity, bounded period and nonstatic locomotion check.','start':start,'period':period,'score':score}
def process(ident):
    data=read(RUN/'production.json');c=next(v for v in data['clips'] if v['id']==ident)
    if c['status'] not in ['generated','processed','packaged']:return
    if c['status'] in ['processed','packaged'] and (OUT/'clips'/ident/'mapping.json').exists():return
    registration=RUN/'registration.json'
    if not registration.exists() and c['start']!=10:print('Waiting for standing scale anchor',flush=True);return
    folder=OUT/'clips'/ident
    for p in [folder/'hd_rgba',folder/'native',folder/'preview',OUT/'native_frames',OUT/'hd_frames',WEB/'assets/fatfish_full_v01',TRIAL/'clips'/ident]:p.mkdir(parents=True,exist_ok=True)
    cutouts=[]
    with av.open(c['video']) as video:
        for frame in video.decode(video=0):cutouts.append(matte(frame.to_image()))
    assert len(cutouts)==124
    selected,selection=choose(c,cutouts);origs=[original(i) for i in range(c['start'],c['end']+1)];origboxes=[bbox(im) for im in origs];boxes=[bbox(cutouts[i]) for i in selected]
    ratios=[(a[3]-a[1])/(b[3]-b[1]) for a,b in zip(origboxes,boxes)];suggested=float(np.median(ratios))
    if not registration.exists():save(registration,{'base_scale':suggested,'anchor_clip':ident,'method':'One fixed standing-derived scale range, no per-frame rescale.'})
    base=read(registration)['base_scale'];scale=float(np.clip(suggested,base*.85,base*1.15))
    xoffset=float(np.median([head_x(im,b) for im,b in zip(origs,origboxes)]))-scale*float(np.median([head_x(cutouts[i],b) for i,b in zip(selected,boxes)]))
    mappings=[];native=[];issues=[];preview_rect=(182,250,374,410) if c['start']==148 else (170,250,362,410)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',14);columns=min(5,len(origs));rows=(len(origs)+columns-1)//columns;sheet=Image.new('RGB',(columns*384,rows*374),'#172b3b');draw=ImageDraw.Draw(sheet)
    for j,(index,source,ob,gb) in enumerate(zip(selected,origs,origboxes,boxes)):
        slot=c['start']+j;hd=cutouts[index];hd.save(folder/f'hd_rgba/{slot:04d}.png');shutil.copy2(folder/f'hd_rgba/{slot:04d}.png',OUT/f'hd_frames/{slot:04d}.png')
        resized=hd.convert('RGBa').resize((round(hd.width*scale),round(hd.height*scale)),Image.Resampling.LANCZOS).convert('RGBA')
        rb=bbox(resized);dy=(ob[3]-1)-(rb[3]-1);dx=round(xoffset);world=Image.new('RGBA',(500,500));world.alpha_composite(resized,(dx,dy));wb=bbox(world)
        if wb[0]<1 or wb[1]<1 or wb[2]>=499 or wb[3]>=499:issues.append({'slot':slot,'issue':'native_canvas_edge'})
        if np.asarray(hd.getchannel('A'))[:2].max()>150 or np.asarray(hd.getchannel('A'))[-2:].max()>150:issues.append({'slot':slot,'issue':'generated_subject_touches_vertical_edge'})
        world.save(folder/f'native/{slot:04d}.png');shutil.copy2(folder/f'native/{slot:04d}.png',OUT/f'native_frames/{slot:04d}.png');native.append(world)
        preview=world.crop(preview_rect);preview.save(folder/f'preview/{slot:04d}.png');shutil.copy2(folder/f'preview/{slot:04d}.png',WEB/f'assets/fatfish_full_v01/{slot:04d}.png')
        mappings.append({'slot':slot,'video_frame':index,'scale_constant_for_clip':scale,'translation':[dx,dy],'target_bottom_world':ob[3]-1,'actual_bottom_world':wb[3]-1,'native_bbox_world':list(wb),'hd_sha256':sha(folder/f'hd_rgba/{slot:04d}.png'),'native_sha256':sha(folder/f'native/{slot:04d}.png')})
        x,y=j%columns*384,j//columns*374;draw.text((x+6,y+3),f'IMG {slot:03d} / video {index:03d}',font=font,fill='#d7efff')
        for lane,im in enumerate([source.crop(preview_rect),preview]):
            bg=Image.new('RGBA',im.size,(205,215,226,255));bg.alpha_composite(im);sheet.paste(bg.convert('RGB'),(x+lane*192,y+25))
            black=Image.new('RGBA',im.size,(16,25,38,255));black.alpha_composite(im);sheet.paste(black.convert('RGB'),(x+lane*192,y+195))
    sheet.save(folder/'contact_sheet.png')
    orig_aspect=(origboxes[-1][2]-origboxes[-1][0])/(origboxes[-1][3]-origboxes[-1][1]);gen_aspect=(boxes[-1][2]-boxes[-1][0])/(boxes[-1][3]-boxes[-1][1])
    if orig_aspect>1.6 and gen_aspect<1.3:issues.append({'issue':'horizontal_end_pose_missing','original_aspect':orig_aspect,'generated_aspect':gen_aspect})
    deltas=[abs((wb['native_bbox_world'][3]-wb['native_bbox_world'][1])-(ob[3]-ob[1]))/(ob[3]-ob[1]) for wb,ob in zip(mappings,origboxes)]
    if float(np.median(deltas))>.4:issues.append({'issue':'pose_height_mismatch','median_ratio_error':float(np.median(deltas))})
    record={'clip':ident,'source_video':c['video'],'selected_video_frames':selected,'selection':selection,'scale':scale,'unclamped_scale_estimate':suggested,'mappings':mappings,'issues':issues,'preview_window_world':list(preview_rect),'alpha':'True RGBA, neutral gray shadow rejection, edge unmatting before premultiplied resize','registration':'Fixed per-clip scale and X offset, per-pose source-bottom Y registration; no per-frame size fitting.','game_runtime_validated':False}
    save(folder/'mapping.json',record);shutil.copy2(folder/'mapping.json',TRIAL/'clips'/ident/'mapping.json');shutil.copy2(folder/'contact_sheet.png',TRIAL/'clips'/ident/'contact_sheet.png')
    data=read(RUN/'production.json');row=next(v for v in data['clips'] if v['id']==ident);row.update(status='processed',available_slots=list(range(c['start'],c['end']+1)),issues=issues,mapping=(folder/'mapping.json').relative_to(OUT).as_posix(),contact_sheet=f'clips/{ident}/contact_sheet.png');publish(data)
    print(json.dumps({'processed':ident,'slots':len(mappings),'scale':scale,'issues':issues}),flush=True)
    sync=ROOT/'scripts/sync_full_dashboard.py'
    if sync.exists():subprocess.run([sys.executable,str(sync)],check=True)
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');process(sys.argv[1])
