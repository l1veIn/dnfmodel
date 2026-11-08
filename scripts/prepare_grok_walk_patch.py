"""Deterministic gray-matte extraction and pixel-coordinate preparation for one walk test."""
from pathlib import Path
import hashlib
import json

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'output/Fatfish_Grok_Walk_v01'
RUN=ROOT/'design/fatfish/grok_walk_patch_v01'
MASTER=ROOT/'design/fatfish/nearest_standing_v04/standing_canvas.png'


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def font(n): return ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',n)


def extract(im):
    """Flat gray background key; preserve opaque subject colors, unmatte edge RGB."""
    rgb=np.asarray(im.convert('RGB'),dtype=np.float32)
    border=np.concatenate((rgb[:8].reshape(-1,3),rgb[-8:].reshape(-1,3),rgb[:,:8].reshape(-1,3),rgb[:,-8:].reshape(-1,3)))
    bg=np.median(border,axis=0)
    distance=np.max(np.abs(rgb-bg),axis=2)
    alpha=np.clip((distance-8)/16,0,1)
    # The background is uniform gray. Retain only central sprite components;
    # compression ringing at D<=8 is removed. No palette change or sharpening.
    count,labels,stats,_=cv2.connectedComponentsWithStats((alpha>0).astype('uint8'),8)
    keep=np.zeros(alpha.shape,dtype=bool)
    for label in range(1,count):
        x,y,w,h,area=stats[label]
        if area>=2 and x>=17 and x+w<=104 and y>=5 and y+h<=124:
            keep|=labels==label
    alpha*=keep
    rgba=np.zeros((*rgb.shape[:2],4),dtype=np.uint8)
    covered=alpha>0
    a=alpha[covered,None]
    rgba[covered,:3]=np.clip(np.round((rgb[covered]-bg*(1-a))/a),0,255).astype('uint8')
    rgba[:,:,3]=np.round(alpha*255).astype('uint8')
    return Image.fromarray(rgba),{'background_median_rgb':bg.tolist(),'background_max_abs_deviation_99p':float(np.percentile(np.max(abs(border-bg),axis=1),99)),
        'opaque_pixels':int(np.sum(alpha==1)),'partial_alpha_pixels':int(np.sum((alpha>0)&(alpha<1))), 'transparent_pixels':int(np.sum(alpha==0))}


def translate(im,dx,dy):
    stage=Image.new('RGBA',im.size)
    stage.paste(im,(int(dx),int(dy)))
    return stage


def sole(im):
    a=np.asarray(im)
    m=(a[:,:,3]>=128)&(np.indices(a.shape[:2])[0]>=100)
    y,x=np.where(m)
    return int(y.max())


def diff(a,b):
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
    mask=(a[:,:,3]>=128)|(b[:,:,3]>=128)
    # Compare on dark background; avoid irrelevant RGB under zero alpha.
    def comp(x):return x[:,:,:3]*(x[:,:,3:4]/255)+np.array([20,28,40])*(1-x[:,:,3:4]/255)
    return float(np.abs(comp(a)-comp(b)).mean(axis=2)[mask].mean())


def display(im,background='checker',zoom=3):
    base=Image.new('RGBA',(128,128),background if background!='checker' else '#cbd5e1')
    if background=='checker':
        d=ImageDraw.Draw(base)
        for y in range(0,128,8):
            for x in range(0,128,8):
                if (x//8+y//8)%2:d.rectangle((x,y,x+7,y+7),fill='#e7edf5')
    base.alpha_composite(im)
    return base.convert('RGB').resize((128*zoom,128*zoom),Image.Resampling.NEAREST)


def seam_bridge(images):
    """Replace only last 3 samples by one-source nearest optical-flow warps.

    Endpoint color images are never cross-faded, so the bridge cannot create
    double translucent legs. All other source frames remain exactly identical.
    """
    a=images[24];b=images[0]
    def rgb(im):
        bg=Image.new('RGBA',im.size,(128,128,128,255));bg.alpha_composite(im)
        return np.asarray(bg.convert('RGB').resize((384,384),Image.Resampling.NEAREST))
    ga=cv2.cvtColor(rgb(a),cv2.COLOR_RGB2GRAY);gb=cv2.cvtColor(rgb(b),cv2.COLOR_RGB2GRAY)
    algorithm=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    algorithm.setFinestScale(0)
    forward=cv2.resize(algorithm.calc(ga,gb,None),(128,128),interpolation=cv2.INTER_AREA)/3
    reverse=cv2.resize(algorithm.calc(gb,ga,None),(128,128),interpolation=cv2.INTER_AREA)/3
    y,x=np.mgrid[:128,:128].astype('float32')
    result=list(images);records=[]
    for index,t in [(25,.25),(26,.5),(27,.75)]:
        source,flow,amount=(a,forward,t) if t<.5 else (b,reverse,1-t)
        mx=x.copy();my=y.copy()
        # Fixed-point inverse of the forward displacement map.
        for _ in range(6):
            field=cv2.remap(flow,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
            mx=x-amount*field[:,:,0];my=y-amount*field[:,:,1]
        warped=Image.fromarray(cv2.remap(np.asarray(source),mx,my,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,borderValue=(0,0,0,0)))
        adjustment=sole(images[0])-sole(warped)
        result[index]=translate(warped,0,adjustment)
        records.append({'frame':index,'bridge_phase':t,'source_frame':24 if t<.5 else 0,'post_warp_y':adjustment})
    return result,records


def main():
    RUN.mkdir(parents=True,exist_ok=True)
    for n in ['keyed','aligned','final','qa']:(RUN/n).mkdir(exist_ok=True)
    master=Image.open(MASTER).convert('RGBA').crop((186,272,314,400))
    target=sole(master)
    records=[];keyed=[];aligned=[]
    for i,source_frame in enumerate(range(60,88)):
        path=SOURCE/f'frames_native_128/{source_frame:04d}.png'
        im,matte=extract(Image.open(path));old=sole(im);dy=target-old
        after=translate(im,0,dy)
        assert sole(after)==target
        im.save(RUN/f'keyed/{i:04d}.png');after.save(RUN/f'aligned/{i:04d}.png')
        keyed.append(im);aligned.append(after)
        records.append({'frame':i,'source_video_frame':source_frame,'source_sha256':sha(path),'sole_before_y':old,'target_sole_y':target,'translation_xy':[0,dy],**matte})
    before=[diff(keyed[i],keyed[(i+1)%28]) for i in range(28)]
    after=[diff(aligned[i],aligned[(i+1)%28]) for i in range(28)]
    final,bridge=seam_bridge(aligned)
    final_diff=[diff(final[i],final[(i+1)%28]) for i in range(28)]
    for i,im in enumerate(final):
        assert sole(im)==target
        im.save(RUN/f'final/{i:04d}.png')
    bridge_sheet=Image.new('RGB',(384*6,414*2),'#263341');bd=ImageDraw.Draw(bridge_sheet)
    for row,sequence in enumerate([aligned,final]):
        for col,ind in enumerate([23,24,25,26,27,0]):
            x=col*384;y=row*414;bridge_sheet.paste(display(sequence[ind]),(x,y+30));bd.text((x+8,y+7),f"{'Before' if row==0 else 'After'} seam: {ind:02d}",fill='white')
    bridge_sheet.save(RUN/'qa/seam_bridge_sheet.png')
    save(RUN/'normalization.json',{'source_task':'vid_bfd86f4224d7e8e23b777a3c5ff37b53','source_video_sha256':sha(SOURCE/'grok_walk_original.mp4'),
        'master_sha256':sha(MASTER),'native_size':[128,128],'source_frames_zero_based':[60,87],'frame_count':28,
        'key':'Per-frame border-median gray key: alpha=clip((max_abs_rgb_difference-8)/16,0,1), remove distant components, unmatte partial edges',
        'alignment':'Integer Y only, lowest solid shoe pixel to approved master; no rescale or x shift',
        'records':records,'adjacent_fg_mae_before':before,'adjacent_fg_mae_after_alignment':after,
        'seam_bridge':{'method':'DIS motion estimation; final 3 frames nearest-warped from frame24/0; no color crossfade, no duplicated endpoint','frames':bridge},
        'adjacent_fg_mae_final':final_diff})
    sheet=Image.new('RGB',(6*256,5*282),'#263341');d=ImageDraw.Draw(sheet)
    for i,im in enumerate(aligned):
        x=i%6*256;y=i//6*282;sheet.paste(display(im,zoom=2),(x,y+26));d.text((x+8,y+5),f"{i:02d} / source {60+i}, dy {records[i]['translation_xy'][1]:+d}",fill='white')
    sheet.save(RUN/'qa/aligned_sheet.png')
    compare=Image.new('RGB',(384*4,414),'#263341');d=ImageDraw.Draw(compare)
    for i,(label,im) in enumerate([('First / dark',aligned[0]),('Last / dark',aligned[-1]),('First / white',aligned[0]),('Last / white',aligned[-1])]):
        compare.paste(display(im,'#141c28' if i<2 else '#ffffff'),(i*384,30));d.text((i*384+8,8),label,fill='white')
    compare.save(RUN/'qa/aligned_endpoints.png')
    print(json.dumps({'frames':28,'sole_y':target,'old_range':[min(r['sole_before_y'] for r in records),max(r['sole_before_y'] for r in records)],
        'seam_mae_before':before[-1],'seam_mae_after_y':after[-1],'seam_mae_final':final_diff[-1],
        'bridge_edge_deltas':final_diff[23:],'after_adjacent_max':max(after[:-1]),'after_adjacent_median':float(np.median(after[:-1]))}))


if __name__=='__main__':main()
