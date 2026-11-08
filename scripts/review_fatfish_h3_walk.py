"""Package the existing local first/refined videos beside the original Grok run."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image,ImageDraw,ImageFont

from fatfish_h3_walk import ROOT,RUN,OUT,SKILL,GROK_REF,GROK_VIDEO,read,save,sha


def media(path,folder):
    samples={};native=[];rows=[];selected={0,12,24,36,48,60,72,84,96,108,123}
    folder.mkdir(parents=True,exist_ok=True)
    with av.open(str(path)) as container:
        stream=container.streams.video[0]
        properties={'width':stream.width,'height':stream.height,'fps':float(stream.average_rate),
                    'codec':stream.codec_context.name,'audio_present':bool(container.streams.audio)}
        for i,frame in enumerate(container.decode(video=0)):
            image=frame.to_image().convert('RGB');w,h=image.size
            crop=image.crop(((w-h)//2,0,(w+h)//2,h))
            low=crop.resize((128,128),Image.Resampling.NEAREST)
            native.append(low)
            if i in selected:
                image.save(folder/f'{i:03d}_full.png');crop.save(folder/f'{i:03d}_crop.png')
                samples[i]=crop
            a=np.array(low).astype('int16')
            mask=(np.max(np.abs(a-128),axis=2)>45)|((a.max(axis=2)-a.min(axis=2))>35)
            yy,xx=np.where(mask)
            if len(yy):
                rows.append({'frame':i,'bbox':[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)],
                    'foreground_bottom_y':int(yy.max()),'height':int(yy.max()-yy.min()+1)})
    properties.update(frames=len(native),seconds=len(native)/properties['fps'],
        viewport='Fixed central square using full frame height; no per-frame tracking or alignment.',
        foreground_bottom_range_128=[min(r['foreground_bottom_y'] for r in rows),max(r['foreground_bottom_y'] for r in rows)],
        measurement_note='Thresholded gray-background silhouette only. Not a foot-slip measurement or anatomical root tracker.')
    return properties,native,samples,rows


def compare_movie(paths,dest):
    containers=[av.open(str(p)) for p in paths]
    decoders=[iter(c.decode(video=0)) for c in containers]
    width,height=1152,428
    command=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24',
             '-s',f'{width}x{height}','-r','24','-i','pipe:0','-an','-c:v','libx264',
             '-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(dest)]
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',19)
    labels=['Grok 上轮原始输出','H3 一采 · 608×352','H3 二采 · 864×480']
    try:
        for i in range(96):
            board=Image.new('RGB',(width,height),'#172536');draw=ImageDraw.Draw(board)
            for lane,decoder in enumerate(decoders):
                image=next(decoder).to_image().convert('RGB');w,h=image.size
                image=image.crop(((w-h)//2,0,(w+h)//2,h)).resize((384,384),Image.Resampling.LANCZOS)
                board.paste(image,(lane*384,36));draw.text((lane*384+10,5),labels[lane],font=font,fill='#d6eafa')
            process.stdin.write(board.tobytes())
        process.stdin.close();stderr=process.stderr.read();code=process.wait()
        if code:raise RuntimeError(stderr.decode('utf-8','replace'))
    finally:
        for container in containers:container.close()
    with av.open(str(dest)) as container:
        stream=container.streams.video[0]
        assert (stream.width,stream.height)==(1152,428)
        assert sum(1 for _ in container.decode(video=0))==96


def main():
    link=read(RUN/'job_link.json');folder=Path(link['job_dir']);job=read(folder/'job.json')
    assert all(s['status']=='completed' for s in job['stages'])
    spec=read(RUN/'spec.json')
    assert all(sha(p)==digest for p,digest in spec['protected_files_before'].items())
    assert sha(folder/'prompt.api.json')==link['frozen_api_sha256']
    for d in ['media','qa','evidence']:(OUT/d).mkdir(parents=True,exist_ok=True)
    result={'job_dir':str(folder),'mode':job['mode'],'seed':job['seed'],'profile':job['profile'],
        'input_mode':job['input_mode'],'first_pass':job['stages'][0]['videos'],'refined':job['stages'][1]['videos'],
        'total_stage_seconds':round(sum(s['elapsed_seconds'] for s in job['stages']),2),
        'media_reports':[m for s in job['stages'] for m in s['media_reports']]}
    save(folder/'result.json',result);save(RUN/'result.json',result)
    sources=[GROK_VIDEO,Path(job['stages'][0]['videos'][0]),Path(job['stages'][1]['videos'][0])]
    names=['grok','h3_first','h3_refined'];lanes=[];all_samples={};telemetry={}
    for n,stage in zip(['h3_first','h3_refined'],job['stages']):
        records=[json.loads(line) for line in (folder/stage['name']/'telemetry.jsonl').read_text('utf-8').splitlines()]
        telemetry[n]={'elapsed_seconds':stage['elapsed_seconds'],
            'peak_whole_gpu_mib_sampled':max(float(r['gpu'].split(',')[0]) for r in records if r.get('gpu')),
            'min_system_ram_available_gib_sampled':min(r['ram_available'] for r in records)/2**30,
            'sampling_interval_seconds':5}
    for n,source in zip(names,sources):
        original=OUT/f'media/{n}_original.mp4';silent=OUT/f'media/{n}_silent.mp4'
        shutil.copy2(source,original)
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(original),
            '-map','0:v:0','-c:v','copy','-an','-movflags','+faststart',str(silent)],check=True)
        props,frames,samples,rows=media(original,OUT/'qa'/n)
        if n=='grok':assert (props['width'],props['height'],props['frames'])==(960,960,97)
        else:assert props['frames']==124 and props['fps']==24
        durations=[round((i+1)*1000/24)-round(i*1000/24) for i in range(len(frames))]
        frames[0].save(OUT/f'{n}_native128.png',save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=0,blend=0)
        with Image.open(OUT/f'{n}_native128.png') as decoded:
            assert decoded.n_frames==len(frames)
            for i,expected in enumerate(frames):
                decoded.seek(i);assert np.array_equal(np.array(decoded.convert('RGB')),np.array(expected)),(n,i)
        save(OUT/f'evidence/{n}_silhouette_measurements.json',rows)
        lanes.append({'id':n,'video':f'media/{n}_silent.mp4','original':f'media/{n}_original.mp4',
            'sha256':sha(original),'media':props,'telemetry':telemetry.get(n)})
        all_samples[n]=samples
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)
    times=[0,24,48,72]
    board=Image.new('RGB',(960,360*4),'#172536');draw=ImageDraw.Draw(board)
    for row,frame in enumerate(times):
        for col,n in enumerate(names):
            # These comparison times are all in every video; raw frames are preserved separately.
            sample=all_samples[n][frame].resize((320,320),Image.Resampling.LANCZOS)
            x,y=col*320,row*360;board.paste(sample,(x,y+32))
            draw.text((x+10,y+5),f'{n} / {frame/24:g}s',font=font,fill='#d8e9f9')
    board.save(OUT/'qa/common_time_comparison.png')
    # A separate H3 motion strip makes tail/gait changes visible beyond three QA samples.
    for n in ['h3_first','h3_refined']:
        ids=sorted(k for k in all_samples[n] if k in [0,12,24,36,48,60,72,84,96])
        board=Image.new('RGB',(960,350*3),'#172536');draw=ImageDraw.Draw(board)
        for j,i in enumerate(ids):
            x,y=j%3*320,j//3*350
            board.paste(all_samples[n][i].resize((320,320),Image.Resampling.LANCZOS),(x,y+28))
            draw.text((x+8,y+3),f'{n} frame{i} / {i/24:.2f}s',font=font,fill='#d8e9f9')
        board.save(OUT/f'qa/{n}_motion_strip.png')
    compare_movie(sources,OUT/'comparison_first4s.mp4')
    history=read(folder/'refine_final/history.json')
    director_report='\n'.join(history['outputs']['8'].get('text',[]))
    assert '命中一采缓存' in director_report and '跳过一采' in director_report
    (OUT/'evidence/director_refine_report.txt').write_text(director_report,encoding='utf-8')
    for n in ['spec.json','prompt.txt','upload.json','refinement_decision.json','job_link.json','result.json','frozen_prompt.api.json','frozen_workflow.json']:
        shutil.copy2(RUN/n,OUT/'evidence'/n)
    shutil.copy2(GROK_REF,OUT/'grok_actual_reference.png')
    shutil.copy2(RUN/'references/same_grok_letterboxed_608x352.png',OUT/'h3_actual_reference.png')
    original_grok=read(ROOT/'output/Fatfish_Grok_Walk_v01/review_report.json')
    report={'title':'H3 first-frame walk versus prior Grok','lanes':lanes,'local_job_id':job['job_id'],
        'seed':job['seed'],'h3_input':'First frame only; gray padding, identical underlying128px Grok design.',
        'last_frame_supplied':False,'intermediate_frames_supplied':False,'same_frozen_api_for_two_stages':True,
        'second_pass_cache_hit_verified':True,'refine_steps':6,'refine_denoise':.25,
        'local_total_seconds':result['total_stage_seconds'],'cloud_calls_this_run':0,
        'prior_grok_cost_usd':original_grok['cost_usd'],'cloud_cost_excludes_local_energy':True,
        'telemetry':telemetry,'full_video_decode':True,'native_apng_pixel_roundtrip':True,
        'comparison_window':'Fixed central square; common first96 frames at24fps. No pose alignment, stabilization, retiming, background removal or artificial loop closure.',
        'original_ani_verified':False,'dnf_ready':False,'npk_created':False,'batch_started':False,
        'game_installation_changed':False,'accepted':False,'protected_files_unchanged':spec['protected_files_before'],
        'limitations':['Single seed/sample, different output resolutions and durations; not a general model ranking.',
            'Both models use the old128px reference artwork, not the newer detailed1024px appearance master.',
            'H3 was first fitted into the verified low-memory608x352 landscape profile without stretching.',
            'A central crop can hide movement outside that viewport; complete raw videos are also included.',
            'Bounding boxes reflect silhouette/background segmentation, not physical foot sliding.']}
    save(OUT/'report.json',report);save(RUN/'review_report.json',report)
    print(json.dumps({'packaged':True,'path':str(OUT),'seconds':result['total_stage_seconds'],
        'media':[{'id':l['id'],**l['media']} for l in lanes],'telemetry':telemetry},ensure_ascii=False))


def publish():
    report=read(OUT/'report.json')
    assert all(sha(p)==digest for p,digest in report['protected_files_unchanged'].items())
    visual={'checked_first_middle_last_both_h3_stages':True,'checked_motion_contact_sheets':True,
        'observations':['H3 produces recognizable alternating leg motion from the supplied first frame.',
            'First-pass face/hair/apron contain coarse colored blocks.',
            'Refinement reduces some blocks but does not restore the reference details.',
            'The tail elongates into a pointed shape; hands and apron ornament also drift.',
            'The prior Grok sample has clearer facial/costume details at equal display height.'],
        'recommendation':'One-pass for motion screening; refine only accepted candidates. Test HD reference and sparse guide anchors separately.',
        'model_ranking_claimed':False,'user_accepted':False,'in_game_tested':False}
    save(RUN/'visual_review.json',visual);save(OUT/'evidence/visual_review.json',visual)
    report['visual_review']=visual;save(OUT/'report.json',report);save(RUN/'review_report.json',report)
    shutil.copy2(ROOT/'scripts/fatfish_h3_walk_preview.html',OUT/'preview.html')
    shutil.copy2(GROK_REF.parent/'master_native_128_rgba.png',OUT/'reference_overlay.png')
    (OUT/'README.txt').write_text(
        'MiniMax H3 首帧步行与 Grok 对照\n\n'
        '本轮1段H3动作，先一采608×352，再从缓存做864×480二采；均124帧/24fps。\n'
        '一采96.22秒，二采增量96.48秒，合计192.70秒。\n'
        '上轮Grok原视频960×960、97帧/24fps，历史费用1.16美元；本轮无云端生成。\n'
        '同一旧128px参考内容，H3只缩放补边。未使用高清新主图、尾帧、中间帧或原版动作。\n'
        '预览中央方形窗口固定，不按每帧居中、缩放、修脚或稳定。默认只重复共同前4秒，不代表循环已闭合。\n'
        '完整画幅与原始有声视频保留在media；silent版本只去音轨，视频流未重新编码。\n'
        'H3可生成连续走路，但尾巴及纹样仍漂移；二采部分改善碎块，不能修正动作和造型。\n'
        '这只是一个seed和低内存档位样本，不能代表高清参考或多锚点能力。\n'
        '未批量、未做NPK，原走路通过记录与游戏文件保持原样。\n',encoding='utf-8')
    save(OUT/'SHA256.json',{p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256.json'})
    shutil.copytree(OUT,ROOT/'output/Fatfish_Action_Dashboard/trials/h3_walk_v01',dirs_exist_ok=True)
    link='<p class="catalog-note" style="margin:12px 0">最新视频对照：<a href="trials/h3_walk_v01/preview.html">本机 H3 一采 / 二采 / 上轮 Grok · 同首帧对照 →</a>　单段测试，待验收；未批量、未生成NPK。</p>'
    for path in [ROOT/'scripts/action_dashboard.html',ROOT/'output/Fatfish_Action_Dashboard/index.html']:
        text=path.read_text('utf-8')
        if 'trials/h3_walk_v01/preview.html' not in text:
            token='      <section class="mapping-notice"';assert token in text
            path.write_text(text.replace(token,'      '+link+'\n'+token,1),encoding='utf-8')
    status_path=ROOT/'preparation_status.json';status=read(status_path)
    assert status['grok_walk_npk_test']['user_accepted']
    status['h3_walk_trial']={'completed':True,'local_job_id':report['local_job_id'],'input_mode':'first frame only',
        'source_reference':'Same underlying128px design as prior Grok, with fixed gray padding.',
        'frames':124,'fps':24,'stages':2,'new_motion_generations':1,'first_pass_cache_reused':True,
        'elapsed_seconds':report['local_total_seconds'],'cloud_calls':0,'path':str(OUT),
        'preview_url':'http://127.0.0.1:8790/trials/h3_walk_v01/preview.html',
        'accepted':False,'npk_created':False,'full_batch_started':False,'game_installation_changed':False}
    save(status_path,status)
    assert all(sha(p)==digest for p,digest in report['protected_files_unchanged'].items())
    print(json.dumps(status['h3_walk_trial'],ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    publish() if '--publish' in sys.argv else main()
