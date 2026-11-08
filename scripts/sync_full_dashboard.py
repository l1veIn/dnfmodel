"""Populate the existing workbench from human labels and actual produced assets."""
import json,shutil,time
from pathlib import Path
from PIL import Image
from dnf_resources import ROOT,save_json

RUN=ROOT/'design/fatfish/full_ref2va_v01'
OUT=ROOT/'output/Fatfish_Complete_v01'
WEB=ROOT/'output/Fatfish_Action_Dashboard'
TRIAL=WEB/'trials/full_ref2va_v01'
def read(path):return json.loads(Path(path).read_text('utf-8'))
save=save_json

def sync():
    baseline=RUN/'baseline_catalog.json'
    if not baseline.exists():shutil.copy2(WEB/'catalog.json',baseline)
    cat=read(baseline);data=read(RUN/'production.json');original_review=read(ROOT/'design/fatfish/action_catalog/progress.json')
    merged_record=ROOT/'validation/fatfish_all_avatar_v02/release.json'
    merged=read(merged_record) if merged_record.exists() else None
    if merged:cat['recommended_package']=merged
    fat={};provenance={};clips=[]
    for c in data['clips']:
        if c['start']==148:
            src_dir=WEB/'assets/original_full_v01';src_dir.mkdir(exist_ok=True)
            for s in range(c['start'],c['end']+1):
                target=src_dir/f'{s:04d}.png'
                if not target.exists():
                    with Image.open(ROOT/f'materials/female_mage/reference_composite/frames/{s:04d}.png') as im:
                        world=Image.new('RGBA',(500,500));world.alpha_composite(im.convert('RGBA'),(185,0));world.crop((182,250,374,410)).save(target)
                cat['original'][str(s)]=target.relative_to(WEB).as_posix()
        available=[s for s in range(c['start'],c['end']+1) if (OUT/f'native_frames/{s:04d}.png').is_file()]
        media=TRIAL/'media';media.mkdir(parents=True,exist_ok=True)
        if c.get('video') and Path(c['video']).is_file():
            video=Path(c['video']);dest=media/(c['id']+'.mp4')
            if not dest.exists() or dest.stat().st_size!=video.stat().st_size or dest.stat().st_mtime<video.stat().st_mtime:shutil.copy2(video,dest)
        hd=media/c['id'];hd.mkdir(exist_ok=True)
        for s in available:
            source=OUT/f'hd_frames/{s:04d}.png';dest=hd/source.name
            if source.exists() and (not dest.exists() or dest.stat().st_mtime<source.stat().st_mtime):shutil.copy2(source,dest)
        for s in available:
            fat[str(s)]=f'assets/fatfish_full_v01/{s:04d}.png';provenance[str(s)]={'role':'full_ref2va_production','clip':c['id'],'source_video':c.get('video'),'in_complete_npk':bool(data.get('package'))}
        clips.append({'id':'full_'+c['id'],'name':c['name'],'category':'手工标注动作','kind':'production','slots':list(range(c['start'],c['end']+1)),
          'available_slots':available,'complete':len(available)==c['end']-c['start']+1,'preview_slot':available[0] if available else c['start'],
          'default_ms':100,'delays_ms':c['frame_ms'],'loop':c['cycle'],'label_basis':'user_manual_annotation',
          'evidence':f'用户手工标注 revision {data["annotation_revision"]}；帧位 {c["start"]}–{c["end"]}，并非自动解析ANI。',
          'sample_note':('已写入完整版 NPK，等待游戏内验收。' if data.get('package') else '透明连续帧已生成，等待验收。' if available else '正在生成这一段。' if c['status']=='generating' else '这一段正在排队。')+'已产出素材按原版画面窗口定位，保留头发和尾巴。',
          'links':[{'label':'本轮全部动作与制作进度','url':'trials/full_ref2va_v01/preview.html'},{'label':'透明与坐标检查','url':f'trials/full_ref2va_v01/clips/{c["id"]}/mapping.json'},{'label':'逐帧原版对照','url':f'trials/full_ref2va_v01/clips/{c["id"]}/contact_sheet.png'}] if available else [{'label':'本轮制作进度','url':'trials/full_ref2va_v01/preview.html'}],
          'production_state':c['status'],'quality_issues':c.get('issues',[])})
    legacy=next(v for v in cat['clips'] if v['id']=='walk');legacy['kind']='legacy_production';legacy['name']='旧Grok步行 · 已验收归档';legacy['fatfish_override']={k:v for k,v in cat['fatfish'].items() if int(k)<10}
    cat.update(clips=clips+[legacy],fatfish=fat,slot_provenance=provenance,unclassified_slots=[],manual_action_count=len(data['clips']),full_batch_updated=time.time(),built_at=str(time.time()),
      production_completed_slots=len(fat),production_total_slots=174,production_generated_clips=sum(c['status'] in ['generated','processed','packaged'] for c in data['clips']),
      production_processed_clips=sum(c['status'] in ['processed','packaged'] for c in data['clips']),action_total_known=False,completion_percentage=None,
      grouping_note='25段按用户手工标注归类；素材制作进度可以统计，游戏ANI未自动解析。',timing_note='采用用户标注配时预览；NPK保留原游戏帧位，游戏内配时由客户端ANI决定。')
    if '10' in fat:cat['master']=fat['10']
    cat['mapping']['summary']=f'用户已标注25段覆盖174帧。当前生成 {cat["production_generated_clips"]}/25 段，透明帧 {len(fat)}/174；原有走路验收记录归档保留。'
    save(WEB/'catalog.json',cat)
    (WEB/'catalog.js').write_text('window.FATFISH_CATALOG = '+json.dumps(cat,ensure_ascii=False)+';\nwindow.FATFISH_PROGRESS = '+json.dumps(original_review,ensure_ascii=False)+';\n','utf-8')
    for source,dest in [('action_dashboard.js','app.js'),('action_dashboard.html','index.html'),('action_dashboard.css','app.css')]:shutil.copy2(ROOT/'scripts'/source,WEB/dest)
    for source,dest in [('full_ref2va_preview.html','preview.html'),('full_ref2va_preview.js','preview.js')]:shutil.copy2(ROOT/'scripts'/source,TRIAL/dest)
    if data.get('package'):
        npk=Path(merged['package'] if merged else data['package'])
        if not npk.exists():npk=OUT/npk.name
        shutil.copy2(npk,WEB/'downloads'/npk.name)
        p=WEB/'index.html';text=p.read_text('utf-8');text=text.replace('downloads/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK','downloads/'+npk.name).replace('↓ 走路测试 NPK','↓ 全时装合并版 NPK' if merged else '↓ 174帧完整版 NPK');p.write_text(text,'utf-8')
    addon_record=ROOT/'validation/growtype_hide_inspection/release.json'
    if merged:
        package=Path(merged['package'])
        shutil.copy2(package.parent/merged['instructions'],WEB/'downloads/fatfish_v02_install.txt')
        shutil.copy2(package.parent/'validation.json',WEB/'downloads/fatfish_v02_validation.json')
        for target,prefix in [(WEB/'index.html',''),(TRIAL/'preview.html','../../')]:
            p=target.read_text('utf-8');link=f'<p class="catalog-note"><strong>v02 已合并本体、全时装覆盖与转职屏蔽</strong><br><small>退出游戏，移出旧 Complete_v01 和 Hide_Growtype_v01 两包，只安装本版。光环与宠物保留。<br>174 帧画稿不变 · 已完成离线回读，待游戏实测</small><br><a href="{prefix}downloads/fatfish_v02_install.txt" target="_blank">安装说明</a> · <a href="{prefix}downloads/fatfish_v02_validation.json" target="_blank">离线校验记录</a></p>'
            p=p.replace('<!-- GROWTYPE_ADDON -->',link);target.write_text(p,'utf-8')
    elif addon_record.exists():
        addon=read(addon_record);package=Path(addon['package'])
        if not package.exists():package=ROOT/'output/Fatfish_Hide_Growtype_v01'/package.name
        shutil.copy2(package,WEB/'downloads'/package.name)
        for target,prefix in [(WEB/'index.html',''),(TRIAL/'preview.html','../../')]:
            p=target.read_text('utf-8');link=f'<p class="catalog-note"><a href="{prefix}downloads/{package.name}" download><strong>↓ 转职附加外观屏蔽 NPK（配套）</strong></a><br><small>与完整时装包同时使用 · 112 个资源 · 待游戏内验收</small></p>'
            p=p.replace('<!-- GROWTYPE_ADDON -->',link);target.write_text(p,'utf-8')
    print(json.dumps({'dashboard_groups':25,'actual_rgba_slots':len(fat),'legacy_walk_approval_preserved':True}))
if __name__=='__main__':sync()
