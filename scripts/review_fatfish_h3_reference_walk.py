"""Collect one Ref2VA sample and publish an honest comparison with old baselines."""
import json,shutil,subprocess,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from fatfish_h3_reference_walk import ROOT,RUN,OUT,WEB,read,save,sha
from fatfish_h3_pose_walk import encoder
from review_fatfish_h3_pose_walk import frames

def silent(src,dest):
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(src),'-an','-c:v','copy','-movflags','+faststart',str(dest)],check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def fit(im):
    im=im.convert('RGB');w,h=im.size;scale=min(608/w,352/h);size=(round(w*scale),round(h*scale));canvas=Image.new('RGB',(608,352),(128,128,128));canvas.paste(im.resize(size,Image.Resampling.LANCZOS),((608-size[0])//2,(352-size[1])//2));return canvas
def resources():
    rows=[json.loads(s) for s in (RUN/'execute/telemetry.jsonl').read_text('utf-8').splitlines()]
    guard=[json.loads(s) for s in (RUN/'memory_guard.jsonl').read_text('utf-8').splitlines()]
    return {'gpu_observed_peak_mib':max(int(s['gpu'].split(',')[0]) for s in rows if s.get('gpu')),
      'ram_observed_min_free_gib':min(s['ram_available']/2**30 for s in rows),'commit_observed_min_free_gib':min(s['commit_available_gib'] for s in guard),
      'monitor_started_before_submission':True,'guard_interrupted':(RUN/'memory_abort.json').exists(),'measurements_are_sampled':True}
def build():
    job=read(RUN/'job.json');assert job['status']=='completed';spec=read(RUN/'spec.json')
    for p,digest in spec['protected_files'].items():
        if p.endswith('manual_motion.json'):continue
        assert sha(p)==digest,p
    for d in ['media','qa','evidence','loop_frames']:(OUT/d).mkdir(parents=True,exist_ok=True)
    video=Path(job['stages'][0]['videos'][0]);shutil.copy2(video,OUT/'media/r2v_original.mp4');silent(video,OUT/'media/r2v_silent.mp4')
    old=ROOT/'output/Fatfish_H3_Pose_Walk_v02'
    for src,dest in [(old/'media/h3_pose_silent.mp4',OUT/'media/pose_silent.mp4'),(old/'media/grok_silent.mp4',OUT/'media/grok_silent.mp4'),(RUN/'input/original_timed_full.mp4',OUT/'original_walk.mp4'),(RUN/'input/motion_reference.mp4',OUT/'motion_reference.mp4'),(RUN/'input/appearance_hd_gray.png',OUT/'appearance_hd_gray.png')]:shutil.copy2(src,dest)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17);selected=[0,12,24,36,48,52,56,60,64,68,71,72,84,96,108,123];sheet=Image.new('RGB',(1408,1536),'#172b3b');draw=ImageDraw.Draw(sheet);loop=[];count=0
    for i,im in enumerate(frames(video)):
        count+=1;square=im.crop((128,0,480,352))
        if i in selected:
            n=selected.index(i);x,y=n%4*352,n//4*384;sheet.paste(square,(x,y+30));draw.text((x+7,y+4),f'Ref2VA / 帧{i}',font=font,fill='#ddf1ff')
        if 48<=i<72:im.save(OUT/f'loop_frames/{i-48:03d}.png');loop.append(im.copy())
    assert count==124 and len(loop)==24;sheet.save(OUT/'qa/generated_motion_strip.png');encoder(OUT/'reference_walk_loop.mp4',loop)
    times=[round((i+1)*1000/24)-round(i*1000/24) for i in range(24)]
    loop[0].save(OUT/'reference_walk_loop.png',save_all=True,append_images=loop[1:],duration=times,loop=0,disposal=0,blend=0)
    paths=['media/r2v_silent.mp4','original_walk.mp4','media/pose_silent.mp4','media/grok_silent.mp4'];labels=['新：Ref2VA + RGB视频 + 高清造型','原版：用户标注配时 / IMG0–9','上轮：弱Pose0.55 / 旧造型参考','Grok：上轮原始视频 / 仅首帧']
    def comparison():
        sources=[frames(OUT/p) for p in paths]
        try:
            for i in range(96):
                board=Image.new('RGB',(1216,768),'#172b3b');d=ImageDraw.Draw(board)
                for lane,gen in enumerate(sources):
                    im=fit(next(gen));x,y=lane%2*608,lane//2*384;board.paste(im,(x,y+30));d.text((x+9,y+4),labels[lane],font=font,fill='#dcf0fd')
                if i==54:board.save(OUT/'qa/comparison_frame54.png')
                yield board
        finally:
            for source in sources:source.close()
    encoder(OUT/'comparison_first4s.mp4',comparison())
    for name in ['prompt.api.json','workflow.json','spec.json','annotations.snapshot.json','job.json','memory_guard.jsonl','model_receipt.json','used_node_schemas.json']:
        shutil.copy2(RUN/name,OUT/'evidence'/name)
    shutil.copy2(RUN/'qa/actual_motion_reference.png',OUT/'qa/actual_motion_reference.png')
    history=read(RUN/'execute/history.json')
    for ident,label in [('22','video'),('23','audio')]:
        entries=history.get('outputs',{}).get(ident,{}).get('latents',[])
        for entry in entries:
            p=STUDIO_OUTPUT/entry.get('subfolder','')/entry['filename']
            if p.is_file():shutil.copy2(p,OUT/f'evidence/{label}.latent')
    metrics=resources();seconds=job['stages'][0]['elapsed_seconds']
    review=(RUN/'visual_review.txt').read_text('utf-8') if (RUN/'visual_review.txt').exists() else '待人工检查；技术完成不代表动作和造型已通过。'
    report={'accepted':False,'model':'minimax_h3_ref2va_pruned_w6a8','model_receipt':read(RUN/'model_receipt.json'),'motion_generations':1,'refinement':False,'pose_control':False,
      'dimensions':[608,352],'frames':124,'fps':24,'steps':20,'seed':20261023,'elapsed_seconds':seconds,'inputs':{'appearance_image_sha256':sha(RUN/'input/appearance_hd_gray.png'),'reference_video_sha256':sha(RUN/'input/motion_reference.mp4'),'reference_video_frames':56,'reference_video_dimensions':[384,224],'native_image_resize':'match','annotation_revision':spec['annotation_revision'],'manual_clip':spec['manual_clip']},
      'resources':metrics,'visual_review':review,'full_video_audio_decode_verified':True,'strict_ab_test':False,'comparison_limit':spec['comparison_limit'],
      'loop_excerpt':{'frames':[48,71],'unmodified_source_excerpt':True,'stabilization':False,'seam_blend':False,'matting':False},'protected_files':spec['protected_files'],
      'annotations_current_sha256':sha(ROOT/'design/fatfish/action_catalog/manual_motion.json'),'cloud_calls':0,'npk_created':False,'full_batch_started':False,'game_installation_changed':False}
    save(OUT/'report.json',report)
    html=(ROOT/'scripts/h3_reference_walk_preview.html').read_text('utf-8').replace('REVIEW_TEXT',review).replace('RESOURCE_TEXT',f'生成 {seconds:.1f} 秒；观测整卡显存最高 {metrics["gpu_observed_peak_mib"]/1024:.2f} GiB，RAM 最低剩余 {metrics["ram_observed_min_free_gib"]:.2f} GiB，提交内存最低剩余 {metrics["commit_observed_min_free_gib"]:.2f} GiB。每2–5秒采样，并非瞬时峰值。')
    (OUT/'preview.html').write_text(html,'utf-8')
    target=WEB/'trials/h3_reference_walk_v01';shutil.copytree(OUT,target,dirs_exist_ok=True)
    nav='<p class="catalog-note" style="margin:12px 0">最新完整视频参考：<a href="trials/h3_reference_walk_v01/preview.html">Ref2VA＋高清造型 / 用户配时原版 / 弱Pose / Grok →</a>　仅一段，待验收。</p>\n      '
    for p in [ROOT/'scripts/action_dashboard.html',WEB/'index.html']:
        text=p.read_text('utf-8')
        if 'trials/h3_reference_walk_v01/preview.html' not in text:text=text.replace('<section class="mapping-notice"',nav+'<section class="mapping-notice"',1);p.write_text(text,'utf-8')
    status=read(ROOT/'preparation_status.json');status['h3_reference_walk_v01']={'completed':True,'accepted':False,'preview_url':'http://127.0.0.1:8791/trials/h3_reference_walk_v01/preview.html','model':report['model'],'annotation_revision':spec['annotation_revision'],'cloud_calls':0,'new_motion_samples':1,'refinement':False,'full_batch_started':False,'npk_created':False};save(ROOT/'preparation_status.json',status)
    print(json.dumps({'built':True,'resources':metrics,'seconds':seconds,'preview':str(target/'preview.html')},ensure_ascii=True))

STUDIO_OUTPUT=Path('D:/VideoStudio/comfyUI/shared/output')
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');build()
