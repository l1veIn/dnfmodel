"""Package the decoder proof and one relaxed motion candidate beside baselines."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
import av
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from fatfish_h3_pose_v02 import ROOT,RUN,OUT,read,save,sha
from fatfish_h3_pose_walk import encoder
from review_fatfish_h3_pose_walk import frames,crop

WEB=ROOT/'output/Fatfish_Action_Dashboard'
OLD=ROOT/'output/Fatfish_H3_Pose_Walk_v01'


def silent(src,dest):
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(src),'-an','-c:v','copy','-movflags','+faststart',str(dest)],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def resources(folder):
    records=[json.loads(s) for s in (folder/'execute/telemetry.jsonl').read_text('utf-8').splitlines()]
    guard=[json.loads(s) for s in (folder/'memory_guard.jsonl').read_text('utf-8').splitlines()]
    return {'gpu_observed_peak_mib':max(int(s['gpu'].split(',')[0]) for s in records if s.get('gpu')),
            'ram_observed_min_free_gib':min(s['ram_available']/2**30 for s in records),
            'commit_observed_min_free_gib':min(s['commit_available_gib'] for s in guard),
            'guard_started_before_submission':True,'sampled_not_continuous_peaks':True}


def build():
    job=read(RUN/'motion_relaxed/job.json');assert job['status']=='completed'
    probe=read(RUN/'decoder_probe/report.json');assert probe['all_pixels_identical']
    spec=read(RUN/'spec.json');assert all(sha(p)==d for p,d in spec['protected_files'].items())
    for d in ['media','decoder','qa','evidence','loop_frames']:(OUT/d).mkdir(parents=True,exist_ok=True)
    video=Path(job['stages'][0]['videos'][0]);shutil.copy2(video,OUT/'media/h3_pose_original.mp4')
    silent(video,OUT/'media/h3_pose_silent.mp4')
    shutil.copy2(OLD/'media/h3_pose_silent.mp4',OUT/'media/h3_first_silent.mp4')
    for name in ['grok','h3_refined']:shutil.copy2(OLD/f'media/{name}_silent.mp4',OUT/f'media/{name}_silent.mp4')
    shutil.copy2(OLD/'original_walk.mp4',OUT/'original_walk.mp4')
    shutil.copy2(OLD/'actual_reference.png',OUT/'actual_reference.png')
    shutil.copy2(RUN/'motion_relaxed/input/pose_control.mp4',OUT/'pose_control.mp4')
    shutil.copy2(RUN/'motion_relaxed/qa/source_pose_overlay.png',OUT/'qa/source_pose_overlay.png')
    shutil.copy2(RUN/'qa/upper_body_source.png',OUT/'qa/upper_body_source.png')
    shutil.copy2(RUN/'qa/decoder_same_latent_comparison.png',OUT/'qa/decoder_same_latent_comparison.png')
    silent(probe['normal_video'],OUT/'decoder/normal.mp4');silent(probe['tiled_video'],OUT/'decoder/tiled.mp4')
    save(OUT/'decoder/report.json',probe)
    for name in ['video','audio']:shutil.copy2(probe[name+'_latent'],OUT/f'evidence/decoder_{name}.latent')
    selected=[0,12,24,36,48,52,56,60,64,68,71,72,84,96,108,123]
    strip=Image.new('RGB',(1408,1536),'#192a3b');draw=ImageDraw.Draw(strip);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',16)
    loop=[];count=0
    for i,im in enumerate(frames(video)):
        count+=1;im=crop(im)
        if i in selected:
            n=selected.index(i);x,y=n%4*352,n//4*384
            strip.paste(im,(x,y+30));draw.text((x+6,y+3),f'弱Pose0.55 / 帧{i}',font=font,fill='#d7edff')
        if 48<=i<72:
            im.save(OUT/f'loop_frames/{i-48:03d}.png');loop.append(im.copy())
    assert count==124 and len(loop)==24
    strip.save(OUT/'qa/generated_motion_strip.png')
    durations=[round((i+1)*1000/24)-round(i*1000/24) for i in range(24)]
    loop[0].save(OUT/'pose_walk_loop.png',save_all=True,append_images=loop[1:],duration=durations,loop=0,disposal=0,blend=0)
    with Image.open(OUT/'pose_walk_loop.png') as decoded:
        assert decoded.n_frames==24
        for i,im in enumerate(loop):decoded.seek(i);assert np.array_equal(np.array(decoded.convert('RGB')),np.array(im))
    encoder(OUT/'pose_walk_loop.mp4',loop)
    names=['media/h3_pose_silent.mp4','media/h3_first_silent.mp4','media/grok_silent.mp4',
           'original_walk.mp4','pose_control.mp4','media/h3_refined_silent.mp4']
    labels=['新：躯干＋弱Pose0.55','旧：简化骨架＋Pose1.0','Grok：上轮原始视频',
            '原版：实验配时','新：实际输入骨架','H3：无Pose二采']
    def compare():
        gens=[frames(OUT/n) for n in names]
        try:
            for i in range(96):
                board=Image.new('RGB',(1056,768),'#192a3b');d=ImageDraw.Draw(board)
                for j,gen in enumerate(gens):
                    im=crop(next(gen)).resize((352,352),Image.Resampling.LANCZOS);x,y=j%3*352,j//3*384
                    board.paste(im,(x,y+30));d.text((x+6,y+3),labels[j],font=font,fill='#d7edff')
                if i==54:board.save(OUT/'qa/comparison_frame54.png')
                yield board
        finally:
            for gen in gens:gen.close()
    encoder(OUT/'comparison_first4s.mp4',compare())
    for which in ['decoder_probe','motion_relaxed']:
        dest=OUT/'evidence'/which;dest.mkdir(exist_ok=True)
        for name in ['job.json','prompt.api.json','workflow.json','memory_guard.jsonl']:
            shutil.copy2(RUN/which/name,dest/name)
        if (RUN/which/'motion.json').exists():shutil.copy2(RUN/which/'motion.json',dest/'motion.json')
    report={'accepted':False,'original_ani_verified':False,'new_motion_samples':1,'old_sampling_reproductions':1,
        'original_latent_cache_reused':False,'decoder_probe':{'frames':124,'lossless_pixels_identical':True,'max_rgb_error':0,
            'sampled_once_then_shared_saved_latent':True,'elapsed_seconds':probe['elapsed_seconds']},
        'motion':{'seed':20261023,'width':608,'height':352,'frames':124,'fps':24,'steps':20,
            'control_strength':.55,'control_end_percent':.8,'same_old_reference':True,'refinement':False,
            'elapsed_seconds':job['stages'][0]['elapsed_seconds'],
            'changes':'Manually re-traced neck/shoulder and inferred hips; small authored head roll/bob; relaxed motion prompt and lower control.',
            'controls_not_individually_ablated':True,'decoder':'VAEDecode, using native H3 internal chunking'},
        'resources':{k:resources(RUN/k) for k in ['decoder_probe','motion_relaxed']},
        'loop':{'source_frames':[48,71],'frames':24,'seconds':1,'postprocessing':'Fixed central crop only; no stabilization, foot correction, seam blending or matting.'},
        'motion_review':'Pending visual inspection; no acceptance inferred.',
        'cloud_calls':0,'npk_created':False,'full_batch_started':False,'game_installation_changed':False,
        'protected_files':spec['protected_files'],'video_full_decode':True,'apng_pixel_roundtrip':True}
    save(OUT/'report.json',report)
    print(json.dumps({'built':True,'motion_seconds':report['motion']['elapsed_seconds'],'resources':report['resources']},ensure_ascii=False))


def html(report):
    text=(ROOT/'scripts/fatfish_h3_pose_walk_preview.html').read_text('utf-8')
    text=text.replace('大肥鱼 · Pose 步行与 H3 / Grok 对照','大肥鱼 · 解码排查与弱 Pose 对照')
    text=text.replace('原版骨架驱动大肥鱼 · 一轮 Pose 步行测试','解码对照完成 · 补全躯干与弱 Pose 小样')
    text=text.replace('本轮：首帧 + Pose 控制 · 仅一采','新动作：Pose 0.55 · 后20%采样解除控制')
    text=text.replace('生成约111秒 · 无新增云端调用',f'旧参数复现1次 + 新动作1段 · 无云端调用')
    text=text.replace('新：H3 + Pose','新：补全躯干 + 弱 Pose')
    text=text.replace('608×352 · 20步 · 控制强度1.0','608×352 · 20步 · 强度0.55 · 控制到80%')
    text=text.replace('与旧H3同首帧、同种子。手脚有响应；纹样和手部仍有碎块，接地待看。','同一旧母版和种子；补全肩线、骨盆和头部运动，放开头发与尾巴动态。画质与动作仍待验收。')
    text=text.replace('H3 · 上轮一采','旧：简化骨架 + 强 Pose')
    text=text.replace('相同首帧、相同种子，仅由提示词驱动。本轮换用原生节点加控制权重。','上轮Pose1.0全程控制，髋部固定；用来比较身体僵硬、尾巴和头发的变化。')
    text=text.replace('aria-label="H3上轮一采步行"','aria-label="上轮强Pose步行"')
    text=text.replace('手腕、脚踝沿原图描点；隐藏关节及头部点为估计值，不包含鱼尾和呆毛。','躯干关节重新描点；遮挡的骨盆为估计，头部有小幅人工修正。尾巴和头发仍由模型生成。')
    text=text.replace('关节点来自既有人工描点，裙内髋、膝、肘等遮挡位置仍为估计。','肩颈按原图重新描点，裙内骨盆为估计，另有小幅头部倾斜和起伏修正。')
    text=text.replace('迈腿与摆臂能响应骨架，仍有面部、手部和围裙碎块；尚不能认为已解决滑步或循环接缝。',report.get('motion_review','待视觉检查。'))
    r=report['resources'];peak=max(x['gpu_observed_peak_mib'] for x in r.values())/1024
    ram=min(x['ram_observed_min_free_gib'] for x in r.values());commit=min(x['commit_observed_min_free_gib'] for x in r.values())
    text=text.replace('记录到整卡显存峰值约10.9GiB，系统RAM最低可用约9.9GiB；后半程提交内存保护监测最低剩余约2.7GiB，未触发中止。',f'两步串行，显存记录峰值约{peak:.1f}GiB，RAM最低可用约{ram:.1f}GiB，提交内存最低剩余约{commit:.1f}GiB；全程监测。')
    text=text.replace('只生成了一段，未二采。原版ANI时序未核实；Pose只控制身体，尾巴、头发与耳部的动态仍由模型生成。','先复现旧参数采样1次做同latent解码对照，再生成1段新动作；未二采。原版ANI时序未核实，骨架、强度和提示词组合调整，未分别消融。')
    text=text.replace('href="evidence/workflow.json"','href="evidence/motion_relaxed/workflow.json"').replace('href="evidence/prompt.api.json"','href="evidence/motion_relaxed/prompt.api.json"').replace('href="evidence/motion.json"','href="evidence/motion_relaxed/motion.json"')
    # Do not overwrite the user's latest slider target while an earlier async
    # video seek is painting. Flush the final slider position after the queue.
    text=text.replace("$('frame').value=s.frame;","if(!s.seeking&&s.pending===null)$('frame').value=s.frame;")
    text=text.replace('finally{s.seeking=false;}','finally{s.seeking=false;paint();}')
    figures=re.findall(r'<figure class="card[^>]*>.*?</figure>',text,re.S)
    assert len(figures)==6
    begin=text.index(figures[0]);end=text.index(figures[-1])+len(figures[-1])
    text=text[:begin]+'\n'.join(figures[i] for i in [0,5,1,3,4,2])+text[end:]
    note='''<div class="finding"><p><strong>先看解码结论：</strong>同一份latent的普通/分块解码，124帧无损PNG逐像素一致，最大RGB差值0。H3内部共用解码流程，外层节点切换没有消除碎块。</p><p>上轮后端cache-none，未保存latent；本轮按旧参数复现一次采样后共享并落盘保存latent。没有把MP4重编码当作原latent。</p></div>'''
    text=text.replace('<div id="grid" class="grid">',note+'\n<div id="grid" class="grid">')
    details='''<details><summary>解码排查：普通 / 分块视频与像素差异</summary><p class="note">两路读取同一份复现后保存的latent；差异图黑色表示完全相同。这里“普通解码”仍包含H3自身内部的内存分块。</p><div style="display:grid;grid-template-columns:1fr 1fr;gap:12px"><div>普通解码<video controls muted playsinline preload="metadata" src="decoder/normal.mp4" style="width:100%"></video></div><div>分块解码<video controls muted playsinline preload="metadata" src="decoder/tiled.mp4" style="width:100%"></video></div></div><img src="qa/decoder_same_latent_comparison.png" class="qa" loading="lazy" alt="同latent普通解码分块解码及逐像素差异"><a href="decoder/report.json" target="_blank">124帧像素摘要与latent校验值 ↗</a></details>'''
    text=text.replace('<details><summary>原版骨架叠加检查',details+'\n<details><summary>原版骨架叠加检查',1)
    return text


def publish():
    report=read(OUT/'report.json');assert all(sha(p)==d for p,d in report['protected_files'].items())
    (OUT/'preview.html').write_text(html(report),encoding='utf-8')
    (OUT/'README.txt').write_text('H3 解码排查与弱Pose小样\n\n上轮没有保存latent，且后端cache-none。本轮复现旧参数采样1次后保存latent，并送入两种解码。\n124帧无损PNG逐像素相同，最大RGB误差0。外层解码入口差异不是这轮碎块的来源。\n随后只做1段新动作：肩颈重描、隐藏髋部估计、轻微头部人工修正，Pose强度0.55，控制到采样80%，放开附属物动态。\n仍用旧像素母版；未二采。原版ANI时序未核实。24帧循环为原输出48–71帧，未稳定、修脚、抠图或混合接缝。\n结果待验收。未批量、未做NPK、未改游戏。\n',encoding='utf-8')
    save(OUT/'SHA256.json',{p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256.json'})
    shutil.copytree(OUT,WEB/'trials/h3_pose_walk_v02',dirs_exist_ok=True)
    link='<p class="catalog-note" style="margin:12px 0">最新Pose调整：<a href="trials/h3_pose_walk_v02/preview.html">解码排查 / 补全躯干＋弱Pose / 旧Pose / Grok →</a>　单段测试，待验收。</p>'
    for path in [ROOT/'scripts/action_dashboard.html',WEB/'index.html']:
        text=path.read_text('utf-8');token='      <section class="mapping-notice"'
        if 'trials/h3_pose_walk_v02/preview.html' not in text:
            assert token in text;path.write_text(text.replace(token,'      '+link+'\n'+token,1),encoding='utf-8')
    path=WEB/'trials/h3_pose_walk_v01/preview.html';text=path.read_text('utf-8')
    if '../h3_pose_walk_v02/preview.html' not in text:path.write_text(text.replace('<h1>','<p><a href="../h3_pose_walk_v02/preview.html">新：解码排查与弱Pose对照 →</a></p><h1>',1),encoding='utf-8')
    status_path=ROOT/'preparation_status.json';status=read(status_path)
    status['h3_pose_walk_v02_trial']={'completed':True,'accepted':False,'decoder_probe_equal_frames':124,
        'reproduction_samples':1,'new_motion_samples':1,'pose_strength':.55,'refinement':False,
        'preview_url':'http://127.0.0.1:8790/trials/h3_pose_walk_v02/preview.html','path':str(OUT),
        'npk_created':False,'full_batch_started':False,'original_ani_verified':False}
    save(status_path,status)
    assert all(sha(p)==d for p,d in report['protected_files'].items())
    print(json.dumps(status['h3_pose_walk_v02_trial'],ensure_ascii=False))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    publish() if '--publish' in sys.argv else build()
