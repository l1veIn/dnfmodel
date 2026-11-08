"""Freeze three original-resolution frames from the accepted Grok walk as a reference row."""
import json
import shutil
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from fatfish_grid_walk import ROOT,original,save,sha

RUN=ROOT/'design/fatfish/fixed_three_master_v01'
OUT=ROOT/'output/Fatfish_Fixed_Three_Master_v01'
SOURCE=ROOT/'output/Fatfish_Grok_Walk_v01'
SELECTION=[{'file_frame':60,'clip_index':0,'label':'前摆臂 · 张步','reason':'展示正面围裙、张开的袖口与迈步腿部。'},
           {'file_frame':68,'clip_index':8,'label':'侧身 · 收腿交叉','reason':'展示侧面裙摆、垂下的袖口，以及较清楚的尾部轮廓。'},
           {'file_frame':74,'clip_index':14,'label':'反向摆臂 · 张步','reason':'展示另一摆臂阶段，补充前侧袖口和裙摆遮挡关系。'}]

def extract_hd(im):
    rgb=np.asarray(im.convert('RGB'),dtype='float32');h,w=rgb.shape[:2]
    border=np.concatenate([rgb[:8].reshape(-1,3),rgb[-8:].reshape(-1,3),rgb[:,:8].reshape(-1,3),rgb[:,-8:].reshape(-1,3)])
    bg=np.median(border,axis=0);delta=np.max(np.abs(rgb-bg),axis=2);alpha=np.clip((delta-8)/16,0,1)
    n,labels,stats,_=cv2.connectedComponentsWithStats((alpha>0).astype('uint8'))
    keep=np.zeros((h,w),bool)
    for i in range(1,n):
        x,y,cw,ch,area=stats[i]
        if area>=16 and x>=w*17/128 and x+cw<=w*104/128 and y>=h*5/128 and y+ch<=h*124/128:keep|=labels==i
    alpha*=keep;a=np.zeros((h,w,4),'uint8');visible=alpha>0
    a[visible,:3]=np.clip(np.rint((rgb[visible]-bg*(1-alpha[visible,None]))/alpha[visible,None]),0,255).astype('uint8')
    a[:,:,3]=np.rint(alpha*255).astype('uint8')
    return Image.fromarray(a),{'background_median_rgb':bg.tolist(),'method':'Same gray-key thresholds as accepted walk, applied at original 960px resolution; central components retained; edge RGB unmatting.',
        'nontransparent':int(visible.sum()),'no_native_size_round_trip':True}

def main():
    if (RUN/'manifest.json').exists():raise RuntimeError('References already frozen. Create a new version for changes.')
    for d in ['raw','rgba_hd','cells','qa']:(RUN/d).mkdir(parents=True,exist_ok=True)
    OUT.mkdir(parents=True,exist_ok=True)
    for d in ['references','evidence']:(OUT/d).mkdir(exist_ok=True)
    protected=[ROOT/'design/fatfish/nearest_standing_v04/standing_canvas.png',ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK',ROOT/'design/fatfish/action_catalog/progress.json']
    before={str(p):sha(p) for p in protected};cells=[];records=[]
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18);small=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',19)
    for j,selection in enumerate(SELECTION):
        p=SOURCE/f'frames_raw/{selection["file_frame"]:04d}.png';im=Image.open(p).convert('RGB');assert im.size==(960,960)
        shutil.copy2(p,RUN/f'raw/{j+1:02d}_video_{selection["file_frame"]:04d}.png')
        rgba,key=extract_hd(im);rgba.save(RUN/f'rgba_hd/{j+1:02d}.png');shutil.copy2(RUN/f'rgba_hd/{j+1:02d}.png',OUT/f'references/{j+1:02d}_hd_rgba.png')
        a=np.asarray(rgba);mask=(a[:,:,3]>=180);mask[:int(.7*960)]=False;rows=np.flatnonzero(mask.sum(1)>12);sole=int(rows[-1])
        # All references have the same scale. Only ground-height alignment is applied.
        factor=512/960;dx=64;dy=544-sole*factor
        cell=rgba.convert('RGBa').transform((640,640),Image.Transform.AFFINE,(1/factor,0,-dx/factor,0,1/factor,-dy/factor),Image.Resampling.BICUBIC).convert('RGBA')
        cell.save(RUN/f'cells/{j+1:02d}.png');cells.append(cell)
        records.append({**selection,'raw_source_path':str(p),'raw_source_sha256':sha(p),'source_size':[960,960],
             'rgba_hd_sha256':sha(RUN/f'rgba_hd/{j+1:02d}.png'),'cell_sha256':sha(RUN/f'cells/{j+1:02d}.png'),
             'key':key,'fixed_scale_to_cell':factor,'translation_to_cell':[dx,dy],'source_sole_row':sole,
             'tail_note':'来自已通过视频，未补画尾巴；部分阶段尾根被头发和裙摆遮挡，不据此证明完整尾部结构。'})
    # Canonical immutable top row: frames and labels together. Every future input copies these exact pixels.
    row=Image.new('RGBA',(2048,688));d=ImageDraw.Draw(row)
    for j,cell in enumerate(cells):
        x=[48,704,1360][j];row.alpha_composite(cell,(x,48));d.text((x+12,58),f'REF {j+1} / VIDEO {SELECTION[j]["file_frame"]:03d}',font=small,fill='#708da9')
    row.save(OUT/'fixed_reference_row.png')
    sheet=Image.new('RGBA',(2048,2048));sheet.alpha_composite(row)
    d=ImageDraw.Draw(sheet)
    for k in range(6):
        x=[48,704,1360][k%3];y=[704,1360][k//3];im=original(k)
        sheet.alpha_composite(im.resize((640,640),Image.Resampling.NEAREST),(x,y));d.text((x+12,y+10),f'TARGET / IMG {k:03d}',font=small,fill='#708da9')
    for x in [696,1352]:d.line((x,704,x,2016),fill='#708da9',width=2)
    for y in [696,1352]:d.line((32,y,2016,y),fill='#708da9',width=2)
    # Do not draw over the frozen reference row.
    sheet.save(OUT/'input_grid_3refs_6poses_2048.png')
    assert sheet.crop((0,0,2048,688)).tobytes()==row.tobytes()
    overview=Image.new('RGB',(1440,560),'#172536');od=ImageDraw.Draw(overview)
    for j,cell in enumerate(cells):
        bg=Image.new('RGBA',(640,640),'#26384c');bg.alpha_composite(cell)
        overview.paste(bg.resize((480,480),Image.Resampling.LANCZOS).convert('RGB'),(j*480,52));od.text((j*480+12,12),f'{j+1}. {SELECTION[j]["label"]} / 源帧{SELECTION[j]["file_frame"]}',font=font,fill='#d0e7f2')
    overview.save(OUT/'selected_three_overview.png')
    manifest={'name':'fixed_three_master_v01','reference_source':'User-approved Grok 28-frame walk clip, original 960px exports',
        'source_task_id':'vid_bfd86f4224d7e8e23b777a3c5ff37b53','source_video_path':str(SOURCE/'grok_walk_original.mp4'),
        'source_video_sha256':sha(SOURCE/'grok_walk_original.mp4'),'selected_references':records,
        'layout':{'canvas':[2048,2048],'cell':[640,640],'top_row':'three fixed Grok references','bottom_rows':'six original female-mage poses IMG0..5 for layout preview',
             'top_row_canonical_path':str(OUT/'fixed_reference_row.png'),'top_row_sha256':sha(OUT/'fixed_reference_row.png'),'top_row_byte_identical_in_input_grid':True},
        'new_generation_jobs':0,'new_cost_usd':0,'generated_target_frames':0,'npk_created':False,'game_changed':False,
        'limitations':['Original-resolution video frames retain the pixel-style detail already present; not extra detail created by upscaling.',
             'These references are from the same approved animation, but individual anchor choices are newly selected.',
             'Six lower cells are a prepared edit target, not newly generated Fatfish frames. ANI sequence/timing remains unverified.'],
        'protected_files_unchanged':before}
    for p,h in before.items():assert sha(p)==h
    save(RUN/'manifest.json',manifest);save(OUT/'manifest.json',manifest)
    (OUT/'README.txt').write_text('固定三帧参考模板\n上排：Grok已通过片段的原始导出帧60、68、74，均由960×960源图直接抠出。\n下排：六个原版女法师姿势IMG0–5，只是下一轮输入模板，尚未提交生图。\nfixed_reference_row.png是固定参考行，后续仅替换下方六格，不使用上一轮生成结果替换参考。\nreferences下是三张原始分辨率透明PNG；manifest记录来源、尺寸、处理和哈希。\n',encoding='utf-8')
    shutil.copy2(RUN/'manifest.json',OUT/'evidence/manifest.json')
    shutil.copy2(ROOT/'design/fatfish/references/UPSTREAM_CREDITS.md',OUT/'evidence/UPSTREAM_CREDITS.md')
    print(json.dumps({'output':str(OUT),'selected_video_files':[x['file_frame'] for x in SELECTION],'source_size':[960,960],'new_generation_jobs':0}))

if __name__=='__main__':main()
