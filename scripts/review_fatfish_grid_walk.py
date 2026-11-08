"""Split one generated sheet, register to existing poses and export a bounded preview."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fatfish_grid_walk import ROOT,RUN,OUT,MASTER,MASTER_SHA,WINDOW,save,sha

# Approximate matching visible-eye landmarks, manually inspected on both sheets.
# Used as fitting inputs, never as independent accuracy measurements.
RAW_EYES=[[332,184],[359,210],[381,207],[344,225],[353,205],[361,204],[351,187],[351,185],[340,187]]
TARGET_EYES=[[81,54],[84,54],[85,54],[82,54],[81,54],[81,54],[84,53],[83,55],[82,55]]
RAW_HAND_HINTS=[[[490,267],[214,366]],[[458,349]],[[401,399]],[[415,379]],[[495,315]],[[521,315]],[[432,368]],[[376,385]],[[476,297]]]
TARGET_HAND_HINTS=[[[109,66],[58,85]],[[101,76]],[[85,90]],[[95,85]],[[111,75]],[[112,71]],[[100,85]],[[87,90]],[[102,76]]]


def sole(image,scale):
    a=np.asarray(image)[:,:,3]>=180;a[:int(image.height*.65)]=False
    rows=np.flatnonzero(a.sum(axis=1)>=max(2,3*scale));y=int(rows[-1])
    yy,xx=np.where(a[max(0,y-2*scale):y+1])
    return [float(xx.mean()),float(y)]


def find_hand(image,hint,scale):
    a=np.asarray(image);rgb=a[:,:,:3].astype('int16');h=np.array(hint)
    skin=(a[:,:,3]>=180)&(rgb[:,:,0]>=200)&(rgb[:,:,1]>=170)&(rgb[:,:,2]>=140)&(rgb[:,:,0]-rgb[:,:,2]>20)&(rgb[:,:,0]-rgb[:,:,1]<70)
    yy,xx=np.indices(skin.shape)
    skin &= (xx-h[0])**2+(yy-h[1])**2<(14*scale)**2
    count,labels,stats,centers=cv2.connectedComponentsWithStats(skin.astype('uint8'))
    candidates=[(np.linalg.norm(centers[i]-h),i) for i in range(1,count) if stats[i,4]>=max(2,3*scale)]
    if not candidates:return list(map(float,hint)),False
    distance,index=min(candidates)
    if distance>10*scale:return list(map(float,hint)),False
    return centers[index].tolist(),True


def clean_cell(raw):
    a=np.array(raw.convert('RGBA'));before=int((a[:,:,3]>0).sum())
    # Known gutters / labels only. Character bounds were visually checked clear.
    a[:10]=0;a[-10:]=0;a[:,:10]=0;a[:,-10:]=0;a[:55,:140]=0
    n,labels,stats,centers=cv2.connectedComponentsWithStats((a[:,:,3]>=128).astype('uint8'))
    main=1+int(np.argmax(stats[1:,4]));near=cv2.dilate((labels==main).astype('uint8'),np.ones((17,17),'uint8'))>0
    a[~near]=0
    return Image.fromarray(a),{'nontransparent_before':before,'nontransparent_after':int((a[:,:,3]>0).sum()),
        'main_bbox_xywh':stats[main,:4].tolist(),'method':'Remove fixed labels/borders and alpha islands more than 8 raw pixels from the main opaque character; retain sampled alpha values.'}


def transform(raw,eye,target_eye,target_sole_y,hand_pairs):
    foot=sole(raw,4);scale=(target_sole_y-target_eye[1])/(foot[1]-eye[1])
    if not .14<=scale<=.26:raise ValueError('Unexpected global scale; inspect source geometry')
    translate=np.asarray(target_eye)-scale*np.asarray(eye)
    yy,xx=np.indices((160,160),dtype='float64');gx=xx.copy();gy=yy.copy();fits=[]
    # A continuous inverse displacement avoids cutting/pasting detached limbs.
    # Small local adjustments only, face and bottom shoe region stay pinned.
    for observed,target,detected in hand_pairs:
        registered=np.asarray(observed)*scale+translate;target=np.asarray(target,dtype='float64');delta=target-registered
        error=float(np.linalg.norm(delta))
        if error>9:raise ValueError(f'Hand correction exceeds bounded limit ({error:.2f}px); inspect annotation')
        radius=max(16.,error*3.5)
        r=np.sqrt((xx-target[0])**2+(yy-target[1])**2)/radius
        compact=np.where(r<1,(1-r)**4*(4*r+1),0)
        face_distance=np.sqrt((xx-target_eye[0])**2+(yy-target_eye[1])**2)
        face_pin=np.clip((face_distance-9)/9,0,1)
        foot_pin=np.clip((target_sole_y-yy-7)/12,0,1)
        weight=compact*face_pin*foot_pin
        gx-=delta[0]*weight;gy-=delta[1]*weight
        fits.append({'raw_hand':observed,'target_hand':target.tolist(),'before_error_native_px':error,
            'radius_native_px':radius,'skin_component_refined':detected})
    sx=np.rint((gx-translate[0])/scale).astype('int32');sy=np.rint((gy-translate[1])/scale).astype('int32')
    valid=(sx>=0)&(sx<raw.width)&(sy>=0)&(sy<raw.height)
    a=np.asarray(raw);result=np.zeros((160,160,4),'uint8');result[valid]=a[sy[valid],sx[valid]]
    # Separate global-only output for inspection; final pixels sample raw once.
    global_x=np.rint((xx-translate[0])/scale).astype('int32');global_y=np.rint((yy-translate[1])/scale).astype('int32')
    valid_g=(global_x>=0)&(global_x<raw.width)&(global_y>=0)&(global_y<raw.height)
    global_a=np.zeros_like(result);global_a[valid_g]=a[global_y[valid_g],global_x[valid_g]]
    return Image.fromarray(result),Image.fromarray(global_a),{'uniform_scale':float(scale),'translation':translate.tolist(),
        'rotation_degrees':0,'source_eye_manual':eye,'target_eye_manual':target_eye,'source_sole':foot,
        'target_sole_y':target_sole_y,'hands':fits,'samples_from_raw_once':True,'interpolation':'NEAREST',
        'face_pixels_not_composited_or_replaced':True,'alpha_values_preserved_by_sampling':True}


def checker(image,zoom=1):
    yy,xx=np.indices((160,160));pattern=((xx//8+yy//8)%2)
    bg=np.where(pattern[:,:,None]==0,np.array([224,233,242]),np.array([194,207,220])).astype('uint8')
    rgba=Image.fromarray(bg).convert('RGBA');rgba.alpha_composite(image)
    return rgba.resize((160*zoom,160*zoom),Image.Resampling.NEAREST)


def apng(path,frames):
    frames[0].save(path,save_all=True,append_images=frames[1:],duration=120,loop=0,disposal=0,blend=0)
    with Image.open(path) as decoded:
        assert decoded.n_frames==9
        for i,expected in enumerate(frames):
            decoded.seek(i);assert np.array_equal(np.asarray(decoded.convert('RGBA')),np.asarray(expected.convert('RGBA')))


def main():
    spec=json.loads((RUN/'spec.json').read_text('utf-8'));journal=json.loads((RUN/'journal.json').read_text('utf-8'))
    receipt=json.loads((RUN/'receipt.json').read_text('utf-8'));assert receipt['status']=='done'
    job=next(iter(journal['jobs'].values()));assert len(journal['jobs'])==1 and len(job['files'])==1
    source=Path(job['files'][0]);source_sha=sha(source)
    with Image.open(source) as im:sheet=im.convert('RGBA')
    assert sheet.size==(2048,2048) and sheet.getchannel('A').getextrema()==(0,255)
    for name in ['original','raw_native','corrected','global_only','split_640','evidence']:(OUT/name).mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,OUT/'sheet_original.png');shutil.copy2(RUN/'references/original_walk_grid_2048.png',OUT/'input_grid.png')
    shutil.copy2(RUN/'references/master_approved_8x.png',OUT/'input_master_1280.png')
    shutil.copy2(RUN/'references/master_approved_native.png',OUT/'master_native.png')
    frames=[];raws=[];origs=[];records=[]
    for item in spec['frames']:
        i=item['slot'];cut=sheet.crop(item['cell']);raw,cleanup=clean_cell(cut)
        cut.save(RUN/f'split/{i:03d}_exact_cell.png');raw.save(OUT/f'split_640/{i:03d}.png')
        original=Image.open(RUN/f'references/original_{i:03d}_native.png').convert('RGBA')
        target_foot=sole(original,1)
        hands=[]
        for raw_hint,target_hint in zip(RAW_HAND_HINTS[i],TARGET_HAND_HINTS[i],strict=True):
            observed,rd=find_hand(raw,raw_hint,2);target,td=find_hand(original,target_hint,1)
            hands.append((observed,target,rd and td))
        corrected,global_only,registration=transform(raw,RAW_EYES[i],TARGET_EYES[i],target_foot[1],hands)
        raw_native=raw.resize((160,160),Image.Resampling.NEAREST)
        original.save(OUT/f'original/{i:03d}.png');raw_native.save(OUT/f'raw_native/{i:03d}.png')
        corrected.save(OUT/f'corrected/{i:03d}.png');global_only.save(OUT/f'global_only/{i:03d}.png')
        for group,image in [('raw',raw),('corrected',corrected)]:image.save(RUN/f'registered/{i:03d}_{group}.png')
        frames.append(corrected);raws.append(raw_native);origs.append(original)
        points={'eye':TARGET_EYES[i],'sole_height':[target_foot[0],target_foot[1]]}
        points.update({f'hand_{j}':target for j,(_,target,_) in enumerate(hands)})
        records.append({'slot':i,'cell_box':item['cell'],'cleanup':cleanup,'registration':registration,
            'target_landmarks':points,'corrected_solid_bottom_y':sole(corrected,1)[1],
            'note':'按原版眼部与鞋底高度做整体矫正，手部采用连续的小范围位置调整。点位用于拟合，仍需目视检查袖口、关节、腿部和边缘。'})
    apng(OUT/'corrected_animation_3x.png',[im.resize((480,480),Image.Resampling.NEAREST) for im in frames])
    apng(OUT/'corrected_animation_checker_3x.png',[checker(im,3) for im in frames])
    apng(OUT/'raw_animation_3x.png',[im.resize((480,480),Image.Resampling.NEAREST) for im in raws])
    contact=Image.new('RGB',(1440,1065),'#172536');d=ImageDraw.Draw(contact);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',15)
    for i in range(9):
        x=(i%3)*480;y=(i//3)*355
        d.text((x+8,y+8),f'IMG {i:03d}：原版 / 九宫格矫正＋最近邻',font=font,fill='#c7e3ee')
        contact.paste(checker(origs[i],1).resize((240,240),Image.Resampling.NEAREST).convert('RGB'),(x,y+40))
        contact.paste(checker(frames[i],1).resize((240,240),Image.Resampling.NEAREST).convert('RGB'),(x+240,y+40))
        d.text((x+8,y+291),f'整体缩放 {records[i]["registration"]["uniform_scale"]:.3f}；鞋底 y={int(records[i]["corrected_solid_bottom_y"])}',font=font,fill='#93b6c7')
    contact.save(OUT/'contact_comparison.png')
    raw_contact=Image.new('RGBA',(480,480))
    for i,im in enumerate(frames):raw_contact.alpha_composite(im,(i%3*160,i//3*160))
    raw_contact.resize((1440,1440),Image.Resampling.NEAREST).save(OUT/'corrected_sheet_3x.png')
    findings=['实际返回 2048×2048 RGBA，存在真正透明像素；九个对应人物均保留。',
        '输入九宫格与已确认主帧的编码字节均已核对，只有一次生成请求。',
        '分格采用原固定坐标；移除格线、标签和远离主体的透明噪点，原始整图保留。',
        '整体大小/眼部位置/鞋底高度矫正后，做有限的连续手部位移；每个成品像素从原始单格最近邻取样一次。',
        '造型与九格姿势具备一致性，但头脸、头发细节和轮廓仍有变化；蓝灰色透明边缘残留需要继续检查。',
        '当前仅含 IMG0–8；未含 IMG9，原 ANI 配时未核实，未证明完整循环接缝或实机无滑步。']
    report={'schema_version':1,'task_id':receipt['id'],'model':receipt['model'],'cost_usd':receipt.get('cost_usd'),
        'generation_jobs':1,'actual_size':[2048,2048],'actual_mode':'RGBA','alpha_min':0,'alpha_max':255,
        'transparent_fraction':float((np.asarray(sheet)[:,:,3]==0).mean()),'sheet_sha256':source_sha,
        'reference_count':2,'reference_payload_hash_verified':True,'frame_slots':list(range(9)),
        'native_window_world':list(WINDOW),'native_size':[160,160],'preview_timing_ms':120,
        'frames':records,'findings':findings,'assessment':'九宫格单张生成已完成，九帧均可对照。当前作为方法试验保留，待你检查造型、手脚位置和原生尺寸连播；尚未标记通过。',
        'correction_limitations':'Manual eye hints and detected sole/skin centroids are fitting controls, not independent pose/foot-slip validation. Hair/garment differences remain generated content.',
        'accepted_walk_replaced':False,'game_installation_changed':False,'npk_created':False,'batch_generation':False,'human_approved':False,
        'validation':{'all_nine_apng_frames_pixel_readback':True,'one_raw_sample_per_output_pixel':True}}
    for path,digest in spec['protected_files_before'].items():assert sha(path)==digest
    assert sha(source)==source_sha and sha(MASTER)==MASTER_SHA
    report['validation']['protected_files_unchanged']=spec['protected_files_before']
    save(OUT/'review_report.json',report);save(OUT/'preview_data.json',report);save(RUN/'review_report.json',report)
    for f in ['request.json','spec.json','reference_payload_audit.json','journal.json','receipt.json','prompt.txt']:shutil.copy2(RUN/f,OUT/'evidence'/f)
    shutil.copy2(ROOT/'design/fatfish/references/UPSTREAM_CREDITS.md',OUT/'evidence/UPSTREAM_CREDITS.md')
    shutil.copy2(ROOT/'scripts/fatfish_grid_walk_preview.html',OUT/'preview.html')
    (OUT/'README.txt').write_text('九宫格步行重绘小样\n一次 gpt-image-2.5 生成，2048×2048 RGBA，九帧 IMG0–8。\n'
        'preview.html 可比较原版、拆格直接最近邻、坐标矫正＋最近邻；逐帧、倍率、背景和叠加可调。\n'
        '未包含IMG9，不代表完整原版步态循环；ANI顺序/配时仍未核实。\n'
        'split_640保留清除标签与远处噪点后的原分格，global_only保留整体矫正；corrected为有限手部调整后的版本。\n'
        '原始生成图为sheet_original.png，实际上传参考为input_grid.png和evidence记录。\n'
        '原先通过的走路素材、进度和NPK保持原样。本轮未打包新NPK、未安装补丁、未批量。\n',encoding='utf-8')
    manifest={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ['SHA256.json','fatfish_grid_walk_v01.zip']}
    save(OUT/'SHA256.json',manifest)
    bundle=ROOT/'output/fatfish_grid_walk_v01.zip'
    with zipfile.ZipFile(bundle,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file() and p.suffix!='.zip':z.write(p,p.relative_to(OUT).as_posix())
    with zipfile.ZipFile(bundle) as z:assert z.testzip() is None
    shutil.copy2(bundle,OUT/'fatfish_grid_walk_v01.zip')
    mounted=ROOT/'output/Fatfish_Action_Dashboard/trials/grid_walk_v01'
    shutil.copytree(OUT,mounted,dirs_exist_ok=True)
    status_path=ROOT/'preparation_status.json';status=json.loads(status_path.read_text('utf-8'))
    status['grid_walk_trial']={'task_id':receipt['id'],'jobs':1,'model':receipt['model'],'cost_usd':receipt.get('cost_usd'),
        'preview_url':'http://127.0.0.1:8790/trials/grid_walk_v01/preview.html','path':str(OUT),
        'frames':9,'slots':list(range(9)),'accepted':False,'npk_created':False,'batch_started':False,'game_installation_changed':False}
    save(status_path,status)
    print(json.dumps({'preview_url':status['grid_walk_trial']['preview_url'],'task_id':receipt['id'],'cost_usd':receipt.get('cost_usd'),
        'hand_errors_before_px':[[round(h['before_error_native_px'],2) for h in r['registration']['hands']] for r in records],
        'sole_bottom_errors_px':[r['corrected_solid_bottom_y']-r['registration']['target_sole_y'] for r in records],
        'protected_files_unchanged':True,'bundle':str(bundle)}))


if __name__=='__main__':main()
