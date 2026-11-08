"""RGBA motion previews, offline NPK verification, provenance and delivery bundle."""
from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw,ImageFont

from dnf_resources import ImgArchive,read_npk,write_npk,write_v2,save_json
from fatfish_motion_v05 import ROOT,BATCH,WINDOW,MASTER,DETAIL,POSES,original,sha
import run_65535_samples as runner

OUT=ROOT/"output/Fatfish_Motion_Pilot_v051"
NPK_NAME="A_Fatfish_FMage_Motion_Pilot_v051.NPK"
WALK=[f"walk_{i:03d}" for i in range(4)]


def font(size):return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",size)
def stage(path):return Image.open(path).convert("RGBA")
def selected(name):
    # PNGs may contain arbitrary RGB beneath zero alpha. Canonicalize invisible
    # RGB for exact canvas reconstruction without altering any alpha/visible pixel.
    revision=BATCH/f"revisions/r1/{name}_canvas.png"
    source=revision if revision.exists() else BATCH/f"corrected/{name}_canvas.png"
    data=np.asarray(stage(source)).copy()
    data[data[:,:,3]==0,:3]=0
    return Image.fromarray(data)
def full_frame(archive,index):
    frame=archive.resolve(index);im=Image.new("RGBA",(500,500))
    im.alpha_composite(archive.image(index),(frame['x'],frame['y']));return im


def panel(image,zoom=3,box=WINDOW,dark=False):
    width=(box[2]-box[0])*zoom;height=(box[3]-box[1])*zoom
    bg=Image.new("RGBA",(width,height),"#141c28" if dark else "#c8d2df")
    bg.alpha_composite(image.crop(box).resize(bg.size,Image.Resampling.NEAREST))
    return bg.convert("RGB")


def stills():
    labels=[("主帧：原样保留",stage(MASTER)),("走路关键帧",selected('walk_000')),("施法关键帧",selected('cast_065')),("跳跃关键帧",selected('jump_023'))]
    sheet=Image.new('RGB',(1536,710),'#253443');d=ImageDraw.Draw(sheet)
    d.text((16,12),'大肥鱼 v05.1｜已选主帧与同造型动作测试',font=font(28),fill='white')
    d.text((16,54),'上排原生窗口 3 倍最近邻，下排原生 1 倍；主帧像素锁定，动作没有复用主帧脸。',font=font(18),fill='#c2d0df')
    for i,(label,im) in enumerate(labels):
        x=i*384;d.text((x+12,93),label,font=font(22),fill='white');sheet.paste(panel(im),(x,132))
        d.text((x+12,537),'原生 1 倍 / 深色背景',font=font(16),fill='#c2d0df');sheet.paste(panel(im,1,dark=True),(x+128,569))
    sheet.save(BATCH/'qa/master_actions_sheet.png')
    strip=Image.new('RGB',(1536,1040),'#253443');d=ImageDraw.Draw(strip)
    d.text((16,12),'相邻步行 IMG 0–3｜原参考与局部矫正结果',font=font(28),fill='white')
    d.text((16,52),'这是 4 帧片段，未补成完整循环；眼位和支撑脚用于整体定位，其他手脚做局部拟合。',font=font(18),fill='#c2d0df')
    for i,name in enumerate(WALK):
        x=i*384;d.text((x+12,90),f'IMG {i:03d} / 原素材',font=font(20),fill='white')
        strip.paste(panel(original(i)),(x,125));d.text((x+12,530),'大肥鱼 / 矫正＋最近邻',font=font(20),fill='white')
        strip.paste(panel(selected(name)),(x,565))
    d.text((16,980),'注意发梢、头部轮廓、裙边金饰和鞋形的帧间变化；拟合点对齐不等于实机无滑步。',font=font(19),fill='#e0c48c')
    strip.save(BATCH/'qa/walk_strip.png')
    repair=Image.new('RGB',(1152,6*426),'#253443');d=ImageDraw.Draw(repair)
    for row,name in enumerate(POSES):
        y=row*426;d.text((12,y+7),f'{name}  |  原动作 / 整体矫正 / 手脚局部矫正',font=font(18),fill='white')
        for col,im in enumerate([original(POSES[name]['frame']),stage(BATCH/f'registered/{name}_canvas.png'),selected(name)]):
            repair.paste(panel(im),(col*384,y+38))
    repair.save(BATCH/'qa/local_corrections_sheet.png')


def movies():
    fixed=[];ground=[]
    for i,name in enumerate(WALK):
        f=Image.new('RGB',(768,590),'#253443');d=ImageDraw.Draw(f)
        d.text((14,12),f'固定坐标对照 / IMG {i:03d}',font=font(24),fill='white')
        d.text((14,51),'左：原女法动作    右：大肥鱼（局部矫正＋最近邻）',font=font(18),fill='#c2d0df')
        for col,im in enumerate([original(i),selected(name)]):
            f.paste(panel(im),(384*col,93));f.paste(panel(im,1,dark=True),(384*col+128,476))
        fixed.append(f)
        # Both tracks use root motion inferred from the ORIGINAL fitted foot,
        # not separate motion optimized to make the generated sprite look stable.
        sole=POSES[name]['sole'];offset=[278-sole[0],386-sole[1]]
        g=Image.new('RGB',(960,526),'#253443');gd=ImageDraw.Draw(g)
        gd.text((14,10),f'接地工程模拟 / IMG {i:03d} / 根位移 {offset}',font=font(23),fill='white')
        gd.text((14,49),'两边使用同一原素材脚点位移；不是实机配时或无滑步证明。',font=font(17),fill='#c2d0df')
        box=(194,272,354,400)
        for col,im in enumerate([original(i),selected(name)]):
            world=Image.new('RGBA',(500,500));world.alpha_composite(im,tuple(offset))
            view=panel(world,3,box,dark=True);vd=ImageDraw.Draw(view)
            gy=(386-box[1])*3;gx=(278-box[0])*3
            vd.line((0,gy,480,gy),fill='#a67a36',width=1);vd.line((gx,gy-7,gx,gy+6),fill='#d5b577',width=1)
            g.paste(view,(col*480,92))
        gd.text((14,490),'左：原女法参考      右：大肥鱼；观察脚形、接触位置和其他脚的相对运动。',font=font(17),fill='#c2d0df')
        ground.append(g)
    for name,frames in [('walk_fixed_compare',fixed),('walk_ground_compare',ground)]:
        reset=Image.new('RGB',frames[0].size,'#253443');ImageDraw.Draw(reset).text((70,230),'4 帧片段结束，随后重播',font=font(28),fill='white')
        sequence=frames+[reset];durations=[140,140,140,650,500]
        sequence[0].save(BATCH/f'qa/{name}.png',save_all=True,append_images=sequence[1:],duration=durations,loop=0,disposal=0,blend=0)
        # GIF is provided for convenient previews. PNG/APNG and HTML retain full RGBA/color.
        sequence[0].save(BATCH/f'qa/{name}.gif',save_all=True,append_images=sequence[1:],duration=durations,loop=0,optimize=False)
        with Image.open(BATCH/f'qa/{name}.png') as decoded:
            assert decoded.n_frames==5
            for i,expected in enumerate(sequence):
                decoded.seek(i);assert np.array_equal(np.asarray(decoded.convert('RGB')),np.asarray(expected))


def data_uri(im):
    buff=io.BytesIO();im.save(buff,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(buff.getvalue()).decode('ascii')


def html_viewer():
    entries=[]
    for name,target in POSES.items():
        entries.append(dict(name=name,frame=target['frame'],sole=target['sole'],original=data_uri(original(target['frame'])),before=data_uri(stage(BATCH/f'registered/{name}_canvas.png')),after=data_uri(selected(name))))
    entries.append(dict(name='master',frame=10,sole=[244,386],original=data_uri(original(10)),before=data_uri(stage(MASTER)),after=data_uri(stage(MASTER))))
    template=(ROOT/'scripts/fatfish_motion_viewer_v05.html').read_text(encoding='utf-8')
    (BATCH/'qa/preview.html').write_text(template.replace('__FRAME_DATA__',json.dumps(entries,ensure_ascii=False)),encoding='utf-8')


def validate_and_receipts():
    journal=json.loads((BATCH/'journal.json').read_text(encoding='utf-8'))
    assert len(journal['jobs'])==7 and all(j['state']=='downloaded' for j in journal['jobs'].values())
    relay=runner.load_relay()
    def receipt(item):
        name,job=item;task=relay.unwrap(relay.http('GET','/v1/tasks/'+job['task_id']))
        assert task.get('status')=='done'
        return dict(name=name,**{k:task.get(k) for k in ('id','status','model','cost_usd','created_at','completed_at')},local_file=job['files'][0],sha256=sha(Path(job['files'][0])))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        receipts=list(pool.map(receipt,journal['jobs'].items()))
    save_json(BATCH/'qa/provider_receipts.json',receipts)
    current,_=runner.observed_cost(relay)
    journal['observed_cost_delta']=current-journal['baseline_usage_cost'];journal['status']='six_motion_tests_and_one_wrist_repair_reviewed'
    runner.BATCH=BATCH;runner.save_journal(journal)
    frames=[]
    for name,target in POSES.items():
        raw=stage(Path(journal['jobs'][name]['files'][0]));a=np.asarray(raw)[:,:,3]
        final=selected(name);alpha=np.asarray(final)[:,:,3]
        solid=Image.fromarray((alpha>=128).astype('uint8')*255).getbbox()
        assert solid and solid[0]>=WINDOW[0] and solid[1]>=WINDOW[1] and solid[2]<=WINDOW[2] and solid[3]<=WINDOW[3]
        sole=target['sole'];yy,xx=np.where((alpha>=128)&(np.indices(alpha.shape)[0]>=sole[1]-8))
        nearest=float(np.hypot(xx-sole[0],yy-sole[1]).min())
        correction=json.loads((BATCH/f'corrected/{name}.json').read_text(encoding='utf-8'))
        assert correction['outside_fit_masks_pixels_identical']
        audit=json.loads((BATCH/f'qa/{name}_reference_payload_audit.json').read_text(encoding='utf-8'))
        assert audit['reference_count']==3
        # Recheck the exact reference files after all generation and normalization.
        for item in audit['references']:
            assert sha(Path(item['path']))==item['sha256'],item['path']
        frames.append(dict(name=name,solid_bbox=solid,nearest_support_shoe_pixel_distance=nearest,
            support_point_is_fitting_constraint=True,real_transparency=bool(a.min()==0 and a.max()>0),
            local_fit_count=len(correction['fits'])-(1 if name=='walk_002' else 0),revision_applied=(BATCH/f'revisions/r1/{name}_canvas.png').exists(),global_registration=json.loads((BATCH/f'registered/{name}.json').read_text(encoding='utf-8')),
            head_or_face_reused=False))
    master_spec=json.loads((BATCH/'spec.json').read_text(encoding='utf-8'))
    assert sha(MASTER)==master_spec['master_sha256']==sha(BATCH/'references/master_approved_canvas.png')
    report=dict(frames=frames,master_pixels_unchanged=True,new_generation_jobs=7,motion_test_images=6,additional_local_wrist_repair_jobs=1,actual_reference_images_per_request=3,
        reference_byte_audits_passed=True,all_reference_files_unchanged=True,raw_outputs_real_alpha_passed=6,
        head_or_face_reuse=False,no_palette_reduction=True,no_alpha_threshold=True,zero_alpha_rgb_canonicalized_at_export=True,
        sampling='Single-pass nearest sampling from raw, including composed local limb-fit matrices',
        observed_account_cost_delta_usd=journal['observed_cost_delta'],
        reported_receipt_cost_usd=sum(float(r['cost_usd']) for r in receipts) if all(r['cost_usd'] is not None for r in receipts) else None,
        original_ani_timing_known=False,preview_ms_per_frame=140,complete_walk_loop=False,
        ground_motion='Inferred from original sole coordinates; shared by reference and generated tracks',
        sliding_validation='Engineering inspection only; no game motion/timing/root trajectory verification',
        game_runtime_validated=False,game_installation_changed=False,
        revisions=['Frame 2 lower-body overbroad local fit removed; original registered legs retained','Frame 3 forearm/cuff/wrist repaired via one local image edit; all pixels outside arm mask unchanged'],
        remaining_visual_review=['Small changes in face/head silhouette and hair tips','Gold hem marks change between generated poses','Local-fit joint seams and shoe shapes need further visual/game review'])
    save_json(BATCH/'qa/visual_validation.json',report)
    return report


def npk_build():
    base=ROOT/'output/Fatfish_Nearest_Standing_v04/A_Fatfish_FMage_Nearest_Standing_v04.NPK'
    before_hash=sha(base);raw=base.read_bytes();records=read_npk(base)
    skin=[r for r in records if '/avatar/skin/' in r['path']];assert len(skin)==38 and len(records)==64
    payload=lambda r:raw[r['offset']:r['offset']+r['length']]
    old=ImgArchive(payload(skin[0]));assert old.count==174
    assert np.array_equal(np.asarray(full_frame(old,10)),np.asarray(stage(MASTER)))
    images=[old.image(i) for i in range(174)];meta=[dict(f) for f in old.frames]
    updates={target['frame']:selected(name) for name,target in POSES.items()}
    for index,image in updates.items():
        bbox=image.getchannel('A').getbbox();images[index]=image.crop(bbox)
        meta[index]=dict(x=bbox[0],y=bbox[1],canvas_width=500,canvas_height=500)
    body=write_v2(images,meta,preserve_links=True)
    out=ROOT/'output'/NPK_NAME
    if out.exists():raise FileExistsError(out)
    out.write_bytes(write_npk([(r['path'],body if '/avatar/skin/' in r['path'] else payload(r)) for r in records]))
    encoded=out.read_bytes();new=read_npk(out);assert [r['path'] for r in records]==[r['path'] for r in new]
    expected={i:np.asarray(updates[i] if i in updates else full_frame(old,i)) for i in range(174)}
    count=0
    for before,after in zip(records,new,strict=True):
        data=encoded[after['offset']:after['offset']+after['length']];archive=ImgArchive(data);assert archive.count==174
        is_skin='/avatar/skin/' in after['path']
        if not is_skin:assert data==payload(before)
        for i in range(174):
            if is_skin:assert np.array_equal(np.asarray(full_frame(archive,i)),expected[i]),(after['path'],i)
            else:assert archive.image(i).getchannel('A').getbbox() is None
            count+=1
    assert sha(base)==before_hash and count==11136
    report=dict(package=str(out),sha256=sha(out),bytes=out.stat().st_size,entry_count=64,skin_paths=38,default_avatar_paths=26,
        direct_slots=[0,1,2,3,10,23,65],fallback_slots=167,fallback='Standing master slot 10 remains byte-for-pixel identical to v04',
        decoded_frame_checks=count,all_pixel_position_roundtrips_passed=True,base_unchanged=True,
        game_installation_changed=False,game_runtime_validated=False)
    save_json(BATCH/'qa/npk_validation.json',report)
    (out.parent/(NPK_NAME+'.sha256')).write_text(report['sha256']+'  '+NPK_NAME+'\n',encoding='ascii')
    return out,report


def package(npk,visual,npk_report):
    if OUT.exists():raise FileExistsError(OUT)
    OUT.mkdir()
    shutil.copy2(npk,OUT/NPK_NAME)
    for name in ['master_actions_sheet.png','walk_strip.png','local_corrections_sheet.png','walk_fixed_compare.gif','walk_fixed_compare.png','walk_ground_compare.gif','walk_ground_compare.png','preview.html','visual_validation.json','npk_validation.json','provider_receipts.json']:
        shutil.copy2(BATCH/'qa'/name,OUT/name)
    frames=OUT/'frames';frames.mkdir();stage(MASTER).save(frames/'0010_master_canvas.png')
    for name,target in POSES.items():
        selected(name).save(frames/f"{target['frame']:04d}_{name}_canvas.png")
    instructions=f'''大肥鱼 v05：已选 v04 主帧＋6 张动作小样

先看 preview.html：双击可在浏览器打开，无联网依赖。可暂停、逐帧、切换固定坐标/接地模拟、修前/修后和 1–6 倍最近邻显示。
walk_fixed_compare.png、walk_ground_compare.png 是保留完整色彩的 APNG 动画；同名 GIF 用于方便预览，颜色判断以 PNG/HTML 和原 PNG 帧为准。
walk_strip.png 为连续 4 帧总览；master_actions_sheet.png 为站姿、走路、施法、跳跃造型对照。

范围：6 个新生成动作（步行 0–3、施法 65、跳跃 23），主帧 10 沿用 v04 原像素。没有扩展完整动作集。
每次请求均传入 3 张参考；步行后续帧带前帧参考。没有复制主帧脸覆盖动作脸。
动作从生成原图经整体/局部矩阵矫正后一次最近邻采样，保留透明度，不减色、不锐化。少量局部手脚拟合会影响袖口/腿部接缝，应结合修前图检查。

预览边界：IMG 0–3 仅是一段相邻帧，工程配时 140ms/帧；完整循环、原 ANI 以及实机根位移没有认证。片尾明确停顿重播。
接地模拟两侧采用同一组从原素材脚点推算的根位移；支撑脚用于拟合，因此不能凭脚点残差为零认定无滑步。
仍需观察发梢、脸/头部轮廓、裙边金饰、鞋形及接缝的帧间变化。

可选实机试装：
1. 退出游戏，将 ImagePacks2 中本项目的旧 v03/v04 试装 NPK 移到游戏目录外备份，只保留一个测试版本。
2. 把 {NPK_NAME} 复制到 C:\\WeGameApps\\地下城与勇士：创新世纪\\ImagePacks2。
3. 用现有元素师，先脱下装扮栏的时装，保留武器/防具装备。检查站姿、短距离移动、基础施法和跳跃。
4. 本包 38 个女法皮肤＋26 个默认装扮隐藏层的范围与前版一致；未扩大全时装/转职附加层隐藏。
5. 174 个帧槽中只有 7 个实画槽，其余 167 个仍引用站姿；未完成动作会站姿占位。本工具没有写入游戏目录。
6. 卸载：退出游戏，只移出 {NPK_NAME}；需要时再放回备份的 v04。

离线检查：64 个资源条目、11136 个帧位像素与坐标回读通过；完整色彩 APNG 逐帧回读一致。本版尚未实机验收。
'''
    (OUT/'安装与预览说明.txt').write_text(instructions,encoding='utf-8')
    (BATCH/'README.md').write_text('# v05：锁定 v04 主帧的小段动作预览\n\n'+instructions,encoding='utf-8')
    for filename in ['spec.json','journal.json']:
        shutil.copy2(BATCH/filename,OUT/filename)
    shutil.copy2(BATCH/'revisions/r1/wrist_before_after.png',OUT/'fourth_frame_wrist_before_after.png')
    credit=ROOT/'design/fatfish/references/UPSTREAM_CREDITS.md'
    if credit.exists():shutil.copy2(credit,OUT/credit.name)
    manifest={str(p.relative_to(OUT)).replace('\\','/'):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file()}
    save_json(OUT/'manifest.json',manifest)
    bundle=ROOT/'output/fatfish_motion_pilot_v051.zip'
    with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(OUT.rglob('*')):
            if p.is_file():archive.write(p,str(p.relative_to(OUT)))
        # Preserve exact prompts, actual references, raw results, fit records and audits.
        for p in sorted(BATCH.rglob('*')):
            if p.is_file() and p.parts[-2]!='qa':archive.write(p,'production/'+str(p.relative_to(BATCH)))
        archive.write(DETAIL,'production/references/original_detail_source.png')
    with zipfile.ZipFile(bundle) as archive:
        assert archive.testzip() is None
        for name,item in manifest.items():assert hashlib.sha256(archive.read(name)).hexdigest()==item['sha256']
    save_json(BATCH/'qa/package_integrity.json',dict(bundle=str(bundle),bytes=bundle.stat().st_size,sha256=sha(bundle),manifest_files_verified=len(manifest),zip_crc_passed=True))
    print(json.dumps(dict(bundle=str(bundle),npk=str(npk),offline_frame_checks=npk_report['decoded_frame_checks'],jobs=7,reported_cost_usd=visual['reported_receipt_cost_usd'],observed_cost_delta_usd=visual['observed_account_cost_delta_usd']),ensure_ascii=False,indent=2))


if __name__=='__main__':
    stills();movies();html_viewer();visual=validate_and_receipts();npk,report=npk_build();package(npk,visual,report)
