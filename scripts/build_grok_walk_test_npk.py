"""Build one walking-only NPK from normalized Grok frames; never install it."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from dnf_resources import ImgArchive, read_npk, write_npk, write_v2
from prepare_grok_walk_patch import ROOT, SOURCE, RUN, MASTER, sha, save, sole, display, diff

BASE=ROOT/'output/Fatfish_Nearest_Standing_v04/A_Fatfish_FMage_Nearest_Standing_v04.NPK'
INSTALLED=Path('C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2/A_Fatfish_FMage_Nearest_Standing_v04.NPK')
OUT=ROOT/'output/Fatfish_Grok_Walk_Test_v01'
NAME='A_Fatfish_FMage_Grok_Walk_Test_v01.NPK'
MAPPING=[0,3,6,8,11,14,17,20,22,25]


def budget_estimate():
    body=json.loads((ROOT/'materials/female_mage/layers/mg_body0000/frames.json').read_text('utf-8'))
    links=sum('link' in f for f in body['frames'])
    estimate={'character_scope':'Female mage / elementalist common actions; exclude other subclasses skill-specific completion',
        'template_counts':{'slots':body['frame_count'],'direct_images':body['frame_count']-links,'linked_slots':links},
        'count_is':'Planning estimate from visual pose groups, not an extracted ANI inventory or measured acceptance rate',
        'groups':[{'group':'Standing and locomotion','examples':['breathing idle','walking','running','jump launch/air/landing'],'accepted_videos_range':[4,6]},
                  {'group':'Common attacks and spellcasting','examples':['ground basic attacks','air attack','casting/charge/release gestures'],'accepted_videos_range':[6,10]},
                  {'group':'Hit reactions and recovery','examples':['hurt','knockback','fall/grounded/get-up','crouch/defensive or auxiliary poses'],'accepted_videos_range':[5,9]}],
        'elementalist_common_actions':{'accepted_videos_range':[15,25],'planning_generation_calls_range':[25,45]},
        'broader_full_template_if_required':{'accepted_videos_range':[25,40],'planning_generation_calls_range':[40,70],
            'note':'Includes uncommon base poses/weapon motions/emotes beyond elementalist common use'},
        'cost_basis':{'observed_model':'grok-imagine-video-1.5-preview','observed_request_seconds':4,'observed_resolution_tier':'720p','observed_cost_usd':1.16,
            'common_actions_call_budget_usd_range':[29.0,52.2],'not_a_quote':True,'note':'Arithmetic projection only; duration, billing and repeat rate can differ'},
        'production_gates':['Validate current walk NPK in game before further calls','One action family per video, not one video per IMG slot',
                            'Reuse linked slots and compatible poses','NPK alone does not expand client ANI frame references/timing'],
        'extra_video_calls_this_turn':0,'batch_started':False}
    save(OUT/'video_count_estimate.json',estimate)
    save(ROOT/'design/fatfish/video_count_estimate_v01.json',estimate)
    return estimate


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    for folder in ['frames_rgba_28','frames_in_npk_10','frames_before','evidence','qa']:(OUT/folder).mkdir(exist_ok=True)
    baseline={str(p):sha(p) for p in [BASE,MASTER,SOURCE/'grok_walk_original.mp4',INSTALLED] if p.is_file()}
    source=BASE.read_bytes();records=read_npk(BASE)
    skins=[r for r in records if '/avatar/skin/' in r['path']]
    assert len(records)==64 and len(skins)==38
    def payload(r): return source[r['offset']:r['offset']+r['length']]
    old=ImgArchive(payload(skins[0]));assert old.count==174
    assert all(payload(s)==payload(skins[0]) for s in skins)
    frames=[Image.open(RUN/f'final/{i:04d}.png').convert('RGBA') for i in range(28)]
    aligned=[Image.open(RUN/f'aligned/{i:04d}.png').convert('RGBA') for i in range(28)]
    assert all(frames[i].tobytes()==aligned[i].tobytes() for i in range(25))
    target=sole(Image.open(MASTER).convert('RGBA').crop((186,272,314,400)))
    for i,image in enumerate(frames):
        a=np.asarray(image)[:,:,3]
        assert image.size==(128,128) and a.min()==0 and a.max()==255 and sole(image)==target
        assert not a[:3].any() and not a[-3:].any() and not a[:,:3].any() and not a[:,-3:].any()
        image.save(OUT/f'frames_rgba_28/{i:04d}.png')
        shutil.copy2(SOURCE/f'frames_native_128/{60+i:04d}.png',OUT/f'frames_before/{i:04d}.png')
    images=[old.image(i) for i in range(174)]
    metadata=[dict(f) for f in old.frames]
    expected_images={};expected_meta={}
    for slot,frame in enumerate(MAPPING):
        image=frames[frame]
        image.save(OUT/f'frames_in_npk_10/{slot:04d}.png')
        canvas=Image.new('RGBA',(500,500));canvas.paste(image,(186,272))
        bbox=canvas.getchannel('A').getbbox()
        images[slot]=canvas.crop(bbox)
        metadata[slot]={'x':bbox[0],'y':bbox[1],'canvas_width':500,'canvas_height':500}
        expected_images[slot]=images[slot]
        expected_meta[slot]=metadata[slot]
    body=write_v2(images,metadata,preserve_links=True)
    npk=ROOT/'output'/NAME
    if npk.exists(): raise FileExistsError('Preserve published version: '+str(npk))
    npk.write_bytes(write_npk([(r['path'],body if '/avatar/skin/' in r['path'] else payload(r)) for r in records]))
    actual=npk.read_bytes();written=read_npk(npk)
    assert [r['path'] for r in written]==[r['path'] for r in records]
    checks=0;unchanged_checks=0
    for before,after in zip(records,written,strict=True):
        content=actual[after['offset']:after['offset']+after['length']]
        archive=ImgArchive(content);assert archive.count==174
        skin='/avatar/skin/' in after['path']
        if not skin: assert content==payload(before)
        for slot in range(174):
            image=archive.image(slot);meta=archive.resolve(slot)
            if skin:
                expected=expected_images.get(slot,old.image(slot))
                position=expected_meta.get(slot,old.resolve(slot))
                assert image.size==expected.size and image.tobytes()==expected.tobytes(),(after['path'],slot)
                assert [meta[k] for k in ['x','y','canvas_width','canvas_height']]==[position[k] for k in ['x','y','canvas_width','canvas_height']]
                if slot not in expected_images:unchanged_checks+=1
            else:assert image.getchannel('A').getbbox() is None
            checks+=1
    assert checks==11136
    for p,digest in baseline.items():assert sha(Path(p))==digest,p
    shutil.copy2(npk,OUT/NAME)
    (npk.parent/(NAME+'.sha256')).write_text(sha(npk)+'  '+NAME+'\n',encoding='ascii')
    mapping=[{'img_slot':i,'processed_frame':frame,'original_video_frame':60+frame,'bridge_frame':frame>=25} for i,frame in enumerate(MAPPING)]
    save(OUT/'frame_mapping.json',{'mapping':mapping,'source_frames':28,'in_npk_slots':10,'target_slots':list(range(10)),
        'selection':'Nearest phase samples round(28*i/10); frame shape reviewed against existing movement poses 0..9',
        'ani_verified':False,'npk_changes_ani_frame_count_or_timing':False,'game_runtime_validation_pending':True})
    normalization=json.loads((RUN/'normalization.json').read_text('utf-8'))
    report={'package':str(npk),'sha256':sha(npk),'bytes':npk.stat().st_size,'entry_count':64,'skin_paths':38,'default_avatar_hide_paths':26,
        'img_frame_slots':174,'updated_slots':list(range(10)),'source_frames_rgba':28,'actual_walk_keyframes_in_npk':10,
        'roundtrip_frame_checks':checks,'all_pixel_and_coordinate_roundtrips_passed':True,'non_walk_skin_frame_checks_unchanged':unchanged_checks,
        'standing_master_pixels_unchanged':True,'unmodified_default_hide_layer_payloads':26,
        'alpha_check':{'true_rgba_frames':28,'native_size':[128,128],'background_removed':True,'opaque_subject_present':True,'no_canvas_clipping':True},
        'alignment':{'native_lowest_solid_shoe_y':target,'world_shoe_y':target+272,'before_y_range':[112,115], 'after_y_range':[target,target],
                     'method':'Integer vertical translation and per-bridge final correction','support_points_are_fitting_constraints':True},
        'seam':{'modified_frames':[25,26,27],'method':normalization['seam_bridge']['method'],
                'before_tail_transition_max_rgb_mae':max(normalization['adjacent_fg_mae_after_alignment'][24:]),
                'after_tail_transition_max_rgb_mae':max(normalization['adjacent_fg_mae_final'][24:]),
                'last_to_first_rgb_mae':normalization['adjacent_fg_mae_final'][-1],
                'normal_transition_max_rgb_mae':max(normalization['adjacent_fg_mae_final'][:24]),
                'note':'Engineering continuity check and frame inspection; not proof of no foot sliding in game'},
        'limits':['Original ANI selection/delay not parsed; client determines actual playback','Only existing movement slots0..9 replaced',
                  'All 28 RGBA source frames supplied separately; NPK does not force playback of28 frames','Weapon/turnclass overlays may not match the new motion',
                  'Other actions retain v04 test behavior/standing fallbacks'],
        'new_generation_jobs':0,'local_gpu_inference':False,'batch_started':False,'game_installation_changed':False,
        'game_runtime_validated':False,'baseline_sha256_unchanged':baseline}
    save(OUT/'npk_validation.json',report);save(RUN/'npk_validation.json',report)
    for file in ['normalization.json']:
        shutil.copy2(RUN/file,OUT/'evidence'/file)
    for file in ['request_audit.json','receipt.json','spec.json']:
        shutil.copy2(ROOT/'design/fatfish/grok_walk_v01'/file,OUT/'evidence'/('grok_'+file))
    shutil.copy2(SOURCE/'grok_walk_original.mp4',OUT/'evidence/grok_walk_original.mp4')
    shutil.copy2(SOURCE/'evidence/UPSTREAM_CREDITS.md',OUT/'evidence/UPSTREAM_CREDITS.md')
    for name in ['aligned_sheet.png','aligned_endpoints.png','seam_bridge_sheet.png']:
        shutil.copy2(RUN/'qa'/name,OUT/'qa'/name)
    Image.open(MASTER).convert('RGBA').crop((186,272,314,400)).save(OUT/'master_native_128.png')
    for name,sequence in [('walk_rgba_3x.png',frames),('walk_checkered_3x.png',[display(f,zoom=1) for f in frames]),
                          ('walk_in_npk_3x.png',[display(frames[i],zoom=1) for i in MAPPING])]:
        enlarged=[im.resize((384,384),Image.Resampling.NEAREST) for im in sequence]
        total_ms=round(28/24*1000)
        durations=[round((i+1)*total_ms/len(sequence))-round(i*total_ms/len(sequence)) for i in range(len(sequence))]
        enlarged[0].save(OUT/name,save_all=True,append_images=enlarged[1:],duration=durations,loop=0,disposal=0,blend=0)
        with Image.open(OUT/name) as decoded:
            assert decoded.n_frames==len(sequence)
            for i,expected in enumerate(enlarged):
                decoded.seek(i)
                assert not ImageChops.difference(decoded.convert(expected.mode),expected).getbbox()
    estimate=budget_estimate()
    (OUT/'preview.html').write_text(HTML.replace('__MAPPING__',json.dumps(MAPPING)),encoding='utf-8')
    instructions=f'''大肥鱼女法师：Grok 步行测试 v01

文件：{NAME}
先退出 DNF；把游戏 ImagePacks2 中现有的 A_Fatfish_FMage_Nearest_Standing_v04.NPK 移到游戏目录外备份。
本项目同类试装包一次只留一个，再将本次 {NAME} 放进：
C:\\WeGameApps\\地下城与勇士：创新世纪\\ImagePacks2
官方原包不用替换。工具没有自动安装或移动游戏文件。

使用现有女法/元素师，先脱下装扮栏时装，用默认外观测试；装备栏防具无需脱下。
先单次按方向键持续步行，分别朝左、朝右，观察脚底是否浮动、停步是否跳位、透明边缘是否发灰。
再试上下/斜向移动及起停。双击方向键奔跑属于另一个动作，本轮没有重画。
当前武器仍用游戏原动作，可能与新手部位置不吻合；先以身体和脚底为验收重点。

本轮处理了完整28帧：灰底提取透明、RGB边缘去灰、最低实心鞋底统一为原生y={target}（500画布y={272+target}），最后3帧做单源最近邻运动补间来平顺回环。
只用NPK不能修改客户端ANI。现有174帧槽里，移动0..9抽取10个关键帧，映射见frame_mapping.json。
完整28帧透明PNG在frames_rgba_28，实际入包的10帧在frames_in_npk_10。预览默认显示实际入包版本，可切换完整28帧；配时为对照用，实际以游戏为准。
其余槽位、站姿主帧、38皮肤路径/26默认装扮隐藏层沿用已安装v04，不扩展付费时装、转职附加层或其他动作。
离线11136帧位回读像素和坐标通过。拟合脚底高度不等于已验证游戏滑步，需要这次实机测试。

卸载/回滚：退出游戏，移出本次{NAME}，再放回备份的v04。
本轮未新增任何视频或图片生成调用，未批量。
'''
    (OUT/'安装与测试说明.txt').write_text(instructions,encoding='utf-8')
    status_path=ROOT/'preparation_status.json';status=json.loads(status_path.read_text('utf-8'))
    status['grok_walk_npk_test']={'completed':True,'npk':str(npk),'source_frames':28,'actual_movement_slots':10,'target_slots':list(range(10)),
        'preview_url':'http://127.0.0.1:8789/preview.html','npk_validation':'output/Fatfish_Grok_Walk_Test_v01/npk_validation.json',
        'new_generation_jobs':0,'game_installation_changed':False,'game_runtime_validated':False,'batch_started':False}
    save(status_path,status)
    content=(ROOT/'README.md').read_text('utf-8')
    if 'Grok 步行测试 NPK v01' not in content:
        content+='\n\nGrok 步行测试 NPK v01：处理28帧透明素材，统一鞋底高度，末3帧单源最近邻运动补间；按现有移动IMG0–9抽取10帧，保留v04其他槽位与路径范围。NPK无法扩展ANI帧数/配时，尚待实机验证。文件 `output/'+NAME+'`，说明与完整28帧 `output/Fatfish_Grok_Walk_Test_v01`。本轮0生成调用、未修改游戏目录。\n'
        (ROOT/'README.md').write_text(content,encoding='utf-8')
    manifest={str(p.relative_to(OUT)).replace('\\','/'):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256.json'}
    save(OUT/'SHA256.json',manifest)
    bundle=ROOT/'output/fatfish_grok_walk_test_v01.zip'
    with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file():z.write(p,str(p.relative_to(OUT)))
    with zipfile.ZipFile(bundle) as z:
        assert z.testzip() is None
        for path,digest in manifest.items():assert hashlib.sha256(z.read(path)).hexdigest()==digest
    save(RUN/'package_integrity.json',{'zip':str(bundle),'bytes':bundle.stat().st_size,'sha256':sha(bundle),'crc_and_manifest_passed':True})
    print(json.dumps({'npk':str(npk),'npk_bytes':npk.stat().st_size,'checks':checks,'rgba_frames':28,'mapped_slots':MAPPING,
        'zip':str(bundle),'zip_bytes':bundle.stat().st_size,'foot_y':target,'game_files_unchanged':True,'estimated_common_action_videos':[15,25]},ensure_ascii=False))


HTML=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>大肥鱼 · 透明步行 NPK 测试</title>
<style>body{margin:0;background:#151d28;color:#e8eff8;font:16px system-ui,"Microsoft YaHei",sans-serif}main{max-width:1120px;margin:auto;padding:28px}h1{font-size:28px;margin:0 0 12px}p{color:#bacbdf;line-height:1.7}.tag{color:#a0e0cc}.bar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:18px 0}button,select,input{font:inherit}button,select{background:#2a3a50;color:white;border:1px solid #526c8b;border-radius:6px;padding:8px 12px;cursor:pointer}.panels{display:flex;flex-wrap:wrap;gap:24px}figure{margin:0}figcaption{margin-bottom:10px;color:#bacbdf}.stage{width:384px;height:384px;position:relative;background:#141c28;border:1px solid #526074}.stage img{width:100%;height:100%;image-rendering:pixelated}.checker{background-color:#cbd5e1;background-image:conic-gradient(#e7edf5 25%,transparent 0 50%,#e7edf5 0 75%,transparent 0);background-size:48px 48px}.white{background:#fff}.line{position:absolute;top:89.844%;left:0;right:0;border-top:1px solid #eec26a80;pointer-events:none}.hidden .line{display:none}input[type=range]{width:min(620px,100%)}a{color:#8bcdff}small{color:#aec3d8}details{margin-top:18px}</style>
<main><h1>大肥鱼 · 透明步行 NPK 测试</h1><div class="tag">28 帧透明素材 · 实际入包移动槽 0–9 · 本轮未新增生成调用</div>
<p>已统一脚底高度，尾部 3 帧做最近邻运动补间，去掉纯灰背景并处理透明边缘。<br>默认播放实际入包的 10 帧；NPK 沿用游戏原有帧位，完整 28 帧也已保留。这里的播放速度用于对照，实际配时由游戏决定。</p>
<div class="bar"><select id="mode" aria-label="预览模式"><option value="npk">实际入包 · 10 帧</option><option value="full">完整透明循环 · 28 帧</option></select><button id="play">暂停</button><button id="prev">上一帧</button><button id="next">下一帧</button><label>背景 <select id="bg"><option value="checker">棋盘格</option><option value="dark">深色</option><option value="white">白色</option></select></label><label><input id="guide" type="checkbox" checked>脚底线</label></div>
<div class="panels" id="panels"><figure><figcaption>处理前 · 原视频灰底</figcaption><div class="stage"><img id="before" src="frames_before/0000.png" alt="校正前步行帧"><i class="line"></i></div></figure><figure><figcaption id="caption">处理后 · 真透明</figcaption><div class="stage checker" id="afterStage"><img id="after" src="frames_in_npk_10/0000.png" alt="透明步行测试帧"><i class="line"></i></div></figure></div>
<div class="bar"><input id="slider" type="range" min="0" max="9" value="0" aria-label="逐帧浏览"><span id="counter"></span></div>
<p>主帧和其他动作仍沿用已安装的 v04。先退出游戏、把旧 v04 移到游戏目录外备份，只放入本次测试 NPK；先用默认装扮验证步行、左右翻转和起停。脚底拟合不代表已完成实机滑步验收。</p>
<div class="bar"><a href="A_Fatfish_FMage_Grok_Walk_Test_v01.NPK" download>下载测试 NPK</a><a href="安装与测试说明.txt">安装与回滚说明</a><a href="frame_mapping.json">入包帧位映射</a><a href="npk_validation.json">离线检查</a><a href="video_count_estimate.json">后续视频数量估算</a></div>
<details><summary>冻结的站姿主帧</summary><div class="stage checker"><img src="master_native_128.png" alt="已确认主帧"></div></details>
<small>未自动安装，未扩展其他动作或付费时装覆盖。完整透明 PNG 位于 frames_rgba_28。</small></main>
<script>const $=id=>document.getElementById(id),mapping=__MAPPING__;let mode='npk',index=0,count=10,playing=true,last=performance.now();const cache=[];for(let i=0;i<28;i++){const im=new Image;im.src=`frames_rgba_28/${String(i).padStart(4,'0')}.png`;cache.push(im)}
function render(){const n=mode==='npk'?mapping[index]:index;$('before').src=`frames_before/${String(n).padStart(4,'0')}.png`;$('after').src=cache[n].src;$('caption').textContent=`处理后 · 透明帧 ${n}${mode==='npk'?` → IMG ${index}`:''}`;$('slider').value=index;$('counter').textContent=`${index+1} / ${count}`;$('play').textContent=playing?'暂停':'播放'}
function step(n){playing=false;index=(index+n+count)%count;render()}$('prev').onclick=()=>step(-1);$('next').onclick=()=>step(1);$('play').onclick=()=>{playing=!playing;last=performance.now();render()};$('slider').oninput=e=>{playing=false;index=Number(e.target.value);render()};$('mode').onchange=e=>{mode=e.target.value;count=mode==='npk'?10:28;index=0;$('slider').max=count-1;last=performance.now();render()};$('bg').onchange=e=>$('afterStage').className='stage '+e.target.value;$('guide').onchange=e=>$('panels').classList.toggle('hidden',!e.target.checked);
function tick(t){const dt=(28/24*1000)/count;if(playing&&t-last>=dt){const n=Math.floor((t-last)/dt);index=(index+n)%count;last+=n*dt;render()}requestAnimationFrame(tick)}render();requestAnimationFrame(tick);</script></html>'''


if __name__=='__main__':build()
