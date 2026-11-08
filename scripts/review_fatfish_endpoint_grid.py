"""Endpoint-only registration and fair same-pipeline old/new comparison."""
import argparse
import json
import shutil
import sys
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import review_fatfish_fixed_three_trial as previous
from fatfish_endpoint_grid import ROOT,RUN,OUT,NAME,save,sha
from fatfish_grid_walk import original
from fatfish_grid_postprocess_probe import nearest
from review_fatfish_embedded_grid import sole,TARGET_EYES

OLD=ROOT/'output/Fatfish_Fixed_Three_Trial_v01'

def inspect():
    # Model redrew its grid at about 684px pitch, without the input's 48px outer margin.
    # Measured output divider bands: x680..684,1365..1368; y682..686,1366..1373.
    # Use one common 684px window; padded pixels outside the source remain transparent.
    boxes=[[x,y,x+684,y+684] for y in [688,1376] for x in [0,684,1368]]
    previous.RUN=RUN;previous.OUT=OUT;previous.NAME=NAME;previous.CELL_BOXES_OVERRIDE=boxes;previous.inspect()
    save(RUN/'actual_output_layout.json',{'canvas':[2048,2048],'divider_x_bands':[[680,684],[1365,1368]],'divider_y_bands':[[682,686],[1366,1373]],
         'method':'Inspected long alpha line bands in the actual output; one common684px window, padded beyond source edge.',
         'bottom_cell_boxes':boxes,'input640_cell_positions_not_used':True,'reason':'Fixed input boxes clipped shoes because the model moved dividers and enlarged cells.'})

def fit_sequence(name,source,eyes):
    actual=[Image.open(source/f'{i:03d}.png').convert('RGBA') for i in range(6)]
    im=[a.resize((640,640),Image.Resampling.NEAREST) for a in actual]
    anchors=[0,5];s=float(np.median([(sole(original(i))-TARGET_EYES[i][1])/(sole(im[i])-eyes[i][1]) for i in anchors]))
    assert .1<s<.35
    endpoints=[]
    for i in anchors:
        shift=np.array([TARGET_EYES[i][0]-s*eyes[i][0],sole(original(i))-s*sole(im[i])],dtype='float64')
        shift[1]+=sole(original(i))-sole(nearest(im[i],s,shift));endpoints.append(shift)
    center=(endpoints[0]+endpoints[1])/2;records=[]
    for d in [f'{name}_hd',f'{name}_nn',f'{name}_shared_hd',f'{name}_shared_nn']:(OUT/d).mkdir(parents=True,exist_ok=True)
    for i in range(6):
        u=i/5;shift=(1-u)*endpoints[0]+u*endpoints[1]
        for mode,t in [('',shift),('_shared',center)]:
            src=actual[i];hs=src.width/640;vs=src.height/640;yy,xx=np.indices((160,160));sx=np.rint((xx-t[0])/s*hs).astype('int32');sy=np.rint((yy-t[1])/s*vs).astype('int32')
            valid=(sx>=0)&(sx<src.width)&(sy>=0)&(sy<src.height);a=np.zeros((160,160,4),'uint8');pixels=np.asarray(src);a[valid]=pixels[sy[valid],sx[valid]];Image.fromarray(a).save(OUT/f'{name}{mode}_nn/{i:03d}.png')
            hd=src.convert('RGBa').transform((640,640),Image.Transform.AFFINE,(hs/(s*4),0,-t[0]*hs/s,0,vs/(s*4),-t[1]*vs/s),Image.Resampling.BICUBIC).convert('RGBA')
            hd.save(OUT/f'{name}{mode}_hd/{i:03d}.png')
        nn=Image.open(OUT/f'{name}_nn/{i:03d}.png').convert('RGBA')
        records.append({'index':i,'phase_t':u,'used_as_fitting_control':i in anchors,'translation_native':shift.tolist(),'fitted_eye_native':(s*np.array(eyes[i])+shift).tolist(),
                        'lowest_shoe_y':sole(nn),'bbox':list(nn.getchannel('A').getbbox())})
    return {'shared_scale':s,'endpoint_translations':[p.tolist() for p in endpoints],'shared_translation':center.tolist(),'fitted_indices':anchors,
            'intermediate_original_landmarks_used':False,'per_frame_resizing':False,'local_limb_warp':False,'frames':records}

def register():
    eyes=json.loads((RUN/'annotations.json').read_text('utf-8'))['eyes'];assert len(eyes)==6
    oldeyes=json.loads((ROOT/'design/fatfish/fixed_three_trial_v01/annotations.json').read_text('utf-8'))['eyes']
    regs={'old':fit_sequence('old',OLD/'clean_hd',oldeyes),'new':fit_sequence('new',OUT/'clean_hd',eyes)}
    for d in ['old_as_packaged_hd','old_as_packaged_nn']:(OUT/d).mkdir(exist_ok=True)
    for i in range(6):
        shutil.copy2(OLD/f'registered_hd/{i:03d}.png',OUT/f'old_as_packaged_hd/{i:03d}.png');shutil.copy2(OLD/f'nearest/{i:03d}.png',OUT/f'old_as_packaged_nn/{i:03d}.png')
    save(RUN/'registration.json',regs)
    print(json.dumps({'scales':{k:r['shared_scale'] for k,r in regs.items()},'fit_indices':[0,5],'original_intermediates_used_for_fit':False}))

def finish():
    spec=json.loads((RUN/'spec.json').read_text('utf-8'));split=json.loads((RUN/'split_report.json').read_text('utf-8'));reg=json.loads((RUN/'registration.json').read_text('utf-8'))
    receipt=json.loads((RUN/'receipt.json').read_text('utf-8'));review=json.loads((RUN/'visual_review.json').read_text('utf-8'))
    for p,h in spec['protected_files_before'].items():assert sha(p)==h
    for folder in ['new_hd','new_nn','old_hd','old_nn']:
        for i in range(6):
            im=Image.open(OUT/f'{folder}/{i:03d}.png').convert('RGBA');b=im.getchannel('A').getbbox();assert b and b[0]>0 and b[1]>0 and b[2]<im.width and b[3]<im.height
    report={**split,'provider':'65535','model':'gpt-image-2.5','cost_usd':receipt['cost_usd'],'new_jobs':1,'uploaded_pose_anchor_slots':[0,5],
         'middle_output_is_synthesized':True,'middle_output_has_verified_IMG_or_ANI_correspondence':False,'sequence_count':6,'original_intermediate_poses_uploaded':False,
         'registration':reg,'review':review,'accepted':False,'npk_created':False,'game_changed':False,'protected_files_unchanged':spec['protected_files_before'],
         'playback':'Equal 180ms intervals for inspection only; stop at sixth frame by default. Not a certified loop or original ANI timing.'}
    save(OUT/'report.json',report);save(RUN/'review_report.json',report)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17);frames=[]
    for i in range(6):
        board=Image.new('RGBA',(960,390),'#172536');d=ImageDraw.Draw(board)
        for j,(folder,title) in enumerate([('original','原版参考（中间未上传）'),('old_hd','旧：六姿势 · 同样首尾校准'),('new_hd','新：首尾姿势＋AI补中间')]):
            im=Image.open(OUT/f'{folder}/{i:03d}.png').convert('RGBA').resize((320,320),Image.Resampling.NEAREST if folder=='original' else Image.Resampling.LANCZOS)
            yy,xx=np.indices((320,320));bg=np.where(((xx//16+yy//16)%2)[:,:,None]==0,[224,233,242],[193,207,222]).astype('uint8');b=Image.fromarray(bg).convert('RGBA');b.alpha_composite(im)
            board.alpha_composite(b,(j*320,40));d.text((j*320+8,6),title,font=font,fill='#d2e6f0')
        d.text((12,364),f'阶段 {i+1}/6 · '+('首尾锚点' if i in [0,5] else '新方案为AI补帧；不表示对应原版中间帧位'),font=font,fill='#b5ccd8');frames.append(board)
    frames[0].save(OUT/'comparison_animation.png',save_all=True,append_images=frames[1:],duration=180,loop=0,disposal=0,blend=0)
    with Image.open(OUT/'comparison_animation.png') as dec:
        assert dec.n_frames==6
        for i,f in enumerate(frames):dec.seek(i);assert np.array_equal(np.asarray(dec.convert('RGBA')),np.asarray(f))
    contact=Image.new('RGB',(960,390*6))
    for i,f in enumerate(frames):contact.paste(f.convert('RGB'),(0,i*390))
    contact.save(OUT/'six_stage_comparison.png')
    shutil.copy2(ROOT/'scripts/fatfish_endpoint_grid_preview.html',OUT/'preview.html')
    for p in RUN.iterdir():
        if p.is_file() and p.suffix in ['.json','.txt']:shutil.copy2(p,OUT/'evidence'/p.name)
    shutil.copy2(ROOT/'design/fatfish/references/UPSTREAM_CREDITS.md',OUT/'evidence/UPSTREAM_CREDITS.md')
    (OUT/'README.txt').write_text('首尾稀疏宫格 v01\n只上传原版IMG000和IMG005；中间4格人物空白，要求一次补成六阶段。另上传高清主图，上排固定三张Grok参考。\n原版中间帧仅在输出后作为对照，没有用于生图，也没有用于本轮定位拟合。\nnew_hd/new_nn为新方案，old_hd/old_nn为旧六姿势用同样首尾校准重处理的对照；shared版本仅统一变换，as_packaged为旧包实际版本。\n新方案只用首尾的眼/最低鞋底拟合统一缩放和端点位移，中间位移线性插值；没有逐帧吸附或局部变形。\n中间阶段不代表对应IMG001–004或已核实ANI动作。当前不做NPK，未改游戏目录。\n',encoding='utf-8')
    shutil.copytree(OUT,ROOT/'output/Fatfish_Action_Dashboard/trials/endpoint_grid_v01',dirs_exist_ok=True)
    sp=ROOT/'preparation_status.json';status=json.loads(sp.read_text('utf-8'));status['endpoint_grid_trial']={'task_id':receipt['id'],'cost_usd':receipt['cost_usd'],'input_pose_anchors':[0,5],'synthesized_between_frames':4,'jobs':1,'path':str(OUT),'preview_url':'http://127.0.0.1:8790/trials/endpoint_grid_v01/preview.html','accepted':False,'npk_created':False};save(sp,status)
    print(json.dumps(status['endpoint_grid_trial']))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');ap=argparse.ArgumentParser();ap.add_argument('action',choices=['inspect','register','finish']);a=ap.parse_args();globals()[a.action]()
