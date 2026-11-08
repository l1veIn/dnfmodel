"""Publish the single Pose experiment, preserving all accepted baseline records."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
import av
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from fatfish_h3_pose_walk import ROOT,RUN,OUT,FPS,LENGTH,encoder,read,save,sha

BASE=ROOT/'output/Fatfish_H3_Walk_v01'
WEB=ROOT/'output/Fatfish_Action_Dashboard'

def frames(path):
    with av.open(str(path)) as c:
        for frame in c.decode(video=0):
            yield frame.to_image().convert('RGB')

def crop(im):
    w,h=im.size
    return im.crop(((w-h)//2,0,(w+h)//2,h))

def build():
    job=read(RUN/'job.json');stage=job['stages'][0]
    assert stage['status']=='completed'
    spec=read(RUN/'spec.json')
    assert all(sha(p)==digest for p,digest in spec['protected_files_before'].items())
    for d in ['media','qa','evidence','loop_frames']:(OUT/d).mkdir(parents=True,exist_ok=True)
    shutil.copy2(stage['videos'][0],OUT/'media/h3_pose_original.mp4')
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',stage['videos'][0],'-an','-c:v','copy','-movflags','+faststart',str(OUT/'media/h3_pose_silent.mp4')]
    subprocess.run(cmd,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for name in ['grok','h3_first','h3_refined']:
        shutil.copy2(BASE/f'media/{name}_silent.mp4',OUT/f'media/{name}_silent.mp4')
    for source,dest in [('pose_control.mp4','pose_control.mp4'),('original_walk.mp4','original_walk.mp4'),('master.png','actual_reference.png')]:
        shutil.copy2(RUN/'input'/source,OUT/dest)
    for file in ['source_pose_overlay.png','generated_motion_strip.png']:
        shutil.copy2(RUN/'qa'/file,OUT/'qa'/file)
    loop=[];low=[];bottoms=[];raw_count=0
    for i,im in enumerate(frames(stage['videos'][0])):
        raw_count+=1;im=crop(im)
        if 48<=i<72:
            loop.append(im.copy());im.save(OUT/f'loop_frames/{i-48:03d}.png')
        a=np.array(im).astype('int16');mask=(np.max(np.abs(a-128),axis=2)>45)|((a.max(2)-a.min(2))>35)
        yy,xx=np.where(mask)
        if len(yy):bottoms.append(int(yy.max()))
    assert raw_count==124 and len(loop)==24
    loop[0].save(OUT/'pose_walk_loop.png',save_all=True,append_images=loop[1:],duration=1000/24,loop=0,disposal=0,blend=0)
    with Image.open(OUT/'pose_walk_loop.png') as check:
        assert check.n_frames==24
        for i,im in enumerate(loop):
            check.seek(i);assert np.array_equal(np.array(check.convert('RGB')),np.array(im))
    encoder(OUT/'pose_walk_loop.mp4',loop)
    def difference(a,b):
        a,b=np.array(a).astype(float),np.array(b).astype(float)
        union=(np.max(np.abs(a-128),axis=2)>30)|(np.max(np.abs(b-128),axis=2)>30)
        return float(np.abs(a-b)[union].mean())
    adjacent=[difference(a,b) for a,b in zip(loop[:-1],loop[1:])]
    seam=difference(loop[-1],loop[0])
    # One fixed 3x2 comparison. Each decoder only retains its current frame.
    names=['original_walk.mp4','pose_control.mp4','media/h3_pose_silent.mp4',
           'media/grok_silent.mp4','media/h3_first_silent.mp4','media/h3_refined_silent.mp4']
    labels=['原版女法 · 实验节奏','输入骨架 · 1秒一轮','H3 + Pose · 新一采',
            'Grok · 上轮原始输出','H3 · 上轮一采','H3 · 上轮二采']
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17)
    def comparison():
        generators=[frames(OUT/p) for p in names]
        try:
            for i in range(96):
                board=Image.new('RGB',(1056,768),'#172738');draw=ImageDraw.Draw(board)
                for lane,gen in enumerate(generators):
                    im=crop(next(gen)).resize((352,352),Image.Resampling.LANCZOS)
                    x,y=lane%3*352,lane//3*384
                    board.paste(im,(x,y+30));draw.text((x+8,y+3),labels[lane],font=font,fill='#d9edff')
                yield board
        finally:
            for gen in generators:gen.close()
    encoder(OUT/'comparison_first4s.mp4',comparison())
    # Static matching-time comparison uses the same crop, never per-frame fit.
    board=Image.new('RGB',(1056,768),'#172738');draw=ImageDraw.Draw(board)
    for lane,(name,label) in enumerate(zip(names,labels)):
        for i,im in enumerate(frames(OUT/name)):
            if i==54:
                x,y=lane%3*352,lane//3*384
                board.paste(crop(im).resize((352,352),Image.Resampling.LANCZOS),(x,y+30));draw.text((x+8,y+3),label,font=font,fill='#d9edff');break
    board.save(OUT/'qa/comparison_frame54.png')
    resources=[json.loads(l) for l in (RUN/'pose_first/telemetry.jsonl').read_text('utf-8').splitlines()]
    guard=[json.loads(l) for l in (RUN/'memory_guard.jsonl').read_text('utf-8').splitlines()]
    peaks=[int(r['gpu'].split(',')[0]) for r in resources if r.get('gpu')]
    report={'title':'H3 Pose-controlled female mage walk experiment','accepted':False,
        'model':'minimax_h3_fl2va_pruned_w6a8','control_patch':read(RUN/'control_patch_receipt.json'),
        'prompt_id':stage['prompt_id'],'new_generations':1,'refinement':False,
        'seed':20261023,'steps':20,'sampler':'euler','scheduler':'simple','shift_video':12,'shift_audio':3,
        'control_strength':1,'width':608,'height':352,'frames':124,'fps':24,
        'elapsed_seconds':stage['elapsed_seconds'],'actual_reference_sha256':sha(OUT/'actual_reference.png'),
        'same_image_seed_as_previous_h3':True,'same_workflow_as_previous_h3':False,
        'backend_note':'This uses native H3 nodes plus ControlNet; previous H3 used AIMixer Director. It is a method comparison, not a strict one-variable ablation.',
        'pose_source':'Original female mage IMG0..9, manually traced visible joints; hidden joints estimated.',
        'pose_frames':124,'pose_period_frames':24,'original_ani_verified':False,
        'timing':'Experimental 1-second period; not verified game ANI timing.',
        'loop':{'source_frames':[48,71],'frames':24,'seconds':1,
            'processing':'Fixed central crop only. No stabilization, interpolation, matting, foot corrections or seam blending.',
            'foreground_seam_rgb_difference':seam,'foreground_adjacent_rgb_difference_mean':float(np.mean(adjacent)),
            'seam_over_average_adjacent':seam/np.mean(adjacent),
            'metric_note':'RGB differences, not a pose/foot-sliding score. Loop is a raw test crop, not an accepted seamless asset.'},
        'resources':{'gpu_observed_peak_mib':max(peaks),'ram_observed_min_free_gib':min(r['ram_available']/2**30 for r in resources),
            'commit_guard_min_free_gib':min(r['commit_available_gib'] for r in guard),
            'memory_guard_samples':len(guard),'memory_guard_covers_entire_run':False,
            'note':'5-second samples; whole-card GPU use includes other applications. Commit guard started after task submission.'},
        'content_review':{'pose_response':'Arm swing and leg spread visibly respond to the control motion.',
            'remaining_issues':'Face, sleeve, hand and apron show block artifacts; ground contact and cycle seam are not approved.',
            'tail_hair':'Human skeleton does not constrain tail/ahoge/fin-ear secondary motion.'},
        'foreground_bottom_observed_range': [min(bottoms),max(bottoms)],
        'foot_sliding_measured':False,'video_fully_decoded':True,'apng_pixel_roundtrip':True,
        'cloud_calls':0,'npk_created':False,'full_batch_started':False,'game_installation_changed':False,
        'protected_files_unchanged':spec['protected_files_before']}
    save(OUT/'report.json',report)
    for name in ['motion.json','spec.json','job.json','prompt.api.json','workflow.json','control_patch_receipt.json','memory_guard.jsonl']:
        shutil.copy2(RUN/name,OUT/'evidence'/name)
    print(json.dumps({'packaged':True,'resources':report['resources'],'seam_ratio':report['loop']['seam_over_average_adjacent']},ensure_ascii=False))


def publish():
    report=read(OUT/'report.json')
    assert all(sha(p)==d for p,d in report['protected_files_unchanged'].items())
    shutil.copy2(ROOT/'scripts/fatfish_h3_pose_walk_preview.html',OUT/'preview.html')
    (OUT/'README.txt').write_text('H3 Pose 步行小样\n\n原版 IMG0–9 人工骨架，隐藏关节为估计值；1秒一轮是实验配时，ANI尚未核实。\n复用上一轮 H3 首帧及种子；这次改用原生节点加 Fun ControlNet，未二采。\npose_walk_loop.png/mp4 是原始输出48–71帧的固定裁切，未修脚、稳定、抠图或混合接缝。\n面板提供原版、输入骨架、新Pose H3、旧Grok、旧H3一采及二采的同步对照。\n动作有响应，但手部和衣服纹样仍有碎块；循环、接地和造型均待用户验收。\n未批量，未生成NPK，游戏文件和走路已通过记录保持原样。\n',encoding='utf-8')
    save(OUT/'SHA256.json',{p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256.json'})
    shutil.copytree(OUT,WEB/'trials/h3_pose_walk_v01',dirs_exist_ok=True)
    link='<p class="catalog-note" style="margin:12px 0">最新 Pose 试验：<a href="trials/h3_pose_walk_v01/preview.html">原版骨架 / H3 Pose / 旧 H3 / Grok · 六路同步对照 →</a>　单段一采，待验收。</p>'
    for path in [ROOT/'scripts/action_dashboard.html',WEB/'index.html']:
        text=path.read_text('utf-8');token='      <section class="mapping-notice"'
        if 'trials/h3_pose_walk_v01/preview.html' not in text:
            assert token in text;path.write_text(text.replace(token,'      '+link+'\n'+token,1),encoding='utf-8')
    # Direct navigation from the previously open comparison, without rewriting its baseline files.
    old=WEB/'trials/h3_walk_v01/preview.html';text=old.read_text('utf-8')
    if '../h3_pose_walk_v01/preview.html' not in text:
        old.write_text(text.replace('<h1>','<p><a href="../h3_pose_walk_v01/preview.html">新：Pose 控制六路对照 →</a></p><h1>',1),encoding='utf-8')
    status_path=ROOT/'preparation_status.json';status=read(status_path)
    status['h3_pose_walk_trial']={'completed':True,'accepted':False,'generations':1,'refinement':False,
        'frames':124,'fps':24,'loop_frames':24,'original_ani_verified':False,'cloud_calls':0,
        'path':str(OUT),'preview_url':'http://127.0.0.1:8790/trials/h3_pose_walk_v01/preview.html',
        'npk_created':False,'full_batch_started':False,'game_installation_changed':False}
    save(status_path,status)
    assert all(sha(p)==d for p,d in report['protected_files_unchanged'].items())
    print(json.dumps(status['h3_pose_walk_trial'],ensure_ascii=False))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    publish() if '--publish' in sys.argv else build()
