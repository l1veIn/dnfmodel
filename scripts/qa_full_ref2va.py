"""Produce review sheets of every generated video's first/middle/last and matte frames."""
import sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import av
from fatfish_full_ref2va import ROOT,RUN,OUT,read,save,sha

def sheets():
    data=read(RUN/'production.json');ready=[c for c in data['clips'] if c.get('video')]
    qa=OUT/'qa';qa.mkdir(exist_ok=True)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17)
    result=[]
    for start in range(0,len(ready),5):
        batch=ready[start:start+5];sheet=Image.new('RGB',(1216,len(batch)*215),'#122033');draw=ImageDraw.Draw(sheet)
        for row,c in enumerate(batch):
            y=row*215;draw.text((8,y+4),f'{c["id"]}  {c["name"]}',fill='#c2edf5',font=font)
            with av.open(c['video']) as video:
                for i,frame in enumerate(video.decode(video=0)):
                    if i in [0,61,123]:
                        col=[0,61,123].index(i);sheet.paste(frame.to_image().resize((304,176)),(col*304,y+30))
                        draw.text((col*304+4,y+30),str(i),fill='white',font=font)
            middle=(c['start']+c['end'])//2;native=OUT/f'native_frames/{middle:04d}.png'
            if native.exists():
                with Image.open(native) as im:
                    sprite=im.crop((182,250,374,410) if c['start']==148 else (170,250,362,410));bg=Image.new('RGBA',sprite.size,(220,230,238,255));bg.alpha_composite(sprite);sheet.paste(bg.convert('RGB'),(912,y+30))
                draw.text((912,y+194),f'alpha / IMG {middle}',fill='white',font=font)
            result.append({'clip':c['id'],'video':c['video'],'sha256':sha(c['video']),'review_frames':[0,61,123],'sheet':f'qa/video_review_{start//5+1:02d}.png'})
        sheet.save(qa/f'video_review_{start//5+1:02d}.png')
    save(qa/'video_review_index.json',result)
    frames=sorted((OUT/'native_frames').glob('*.png'))
    run=next((c for c in ready if c['start']==18),None)
    if run:
        probe=Image.new('RGB',(1440,620),'#707070');pd=ImageDraw.Draw(probe)
        with av.open(run['video']) as video:
            for index,f in enumerate(video.decode(video=0)):
                if 60<=index<84:
                    z=index-60;x=z%6*240;y=z//6*155
                    probe.paste(f.to_image().crop((120,40,470,352)).resize((168,150)),(x+35,y));pd.text((x+2,y+2),str(index),font=font,fill='white')
        probe.save(qa/'run_phase_probe.png')
    for start in range(0,len(frames),45):
        batch=frames[start:start+45];sheet=Image.new('RGB',(1120,((len(batch)+4)//5)*190),'#192b3c');draw=ImageDraw.Draw(sheet)
        for j,path in enumerate(batch):
            x=j%5*224;y=j//5*190;draw.text((x+7,y+3),'IMG '+path.stem,fill='#d8f5ff',font=font)
            with Image.open(path) as im:
                crop=im.crop((182,250,374,410) if 148<=int(path.stem)<=154 else (170,250,362,410));bg=Image.new('RGBA',crop.size,(214,225,235,255));bg.alpha_composite(crop);sheet.paste(bg.convert('RGB'),(x+16,y+26))
        sheet.save(qa/f'native_atlas_{start//45+1:02d}.png')
    print({'videos':len(ready),'sheets':(len(ready)+4)//5})
if __name__=='__main__':sheets()
