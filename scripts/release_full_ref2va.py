"""Collect reproducible production sources and archive the verified complete package."""
import json,shutil,time,zipfile
from pathlib import Path
from fatfish_full_ref2va import ROOT,RUN,OUT,TRIAL,read,save,sha,HD
from audit_full_ref2va import audit
from sync_full_dashboard import sync

def release():
    data=read(RUN/'production.json');assert data['status']=='packaged';npk=Path(data['package']);validation=read(OUT/'npk_validation.json');assert sha(npk)==validation['sha256']
    audit();resource=read(OUT/'resource_and_geometry_audit.json')
    for sub in ['source_videos','workflows','references']:(OUT/sub).mkdir(exist_ok=True)
    shutil.copy2(HD,OUT/'references/appearance_hd_gray.png');shutil.copy2(RUN/'spec.json',OUT/'production_spec.json')
    shutil.copy2(ROOT/'design/fatfish/h3_reference_walk_v01/input/appearance_original_rgba.png',OUT/'references/master_original_rgba.png')
    for c in data['clips']:
        job=Path(c['job_folder']);shutil.copy2(c['video'],OUT/'source_videos'/(c['id']+'.mp4'))
        for source,suffix in [('prompt.api.json','api.json'),('workflow.json','workflow.json'),('prompt.txt','prompt.txt'),('job.json','job.json')]:
            if (job/source).exists():shutil.copy2(job/source,OUT/'workflows'/(c['id']+'.'+suffix))
        for name in ['motion.mp4','motion_reference.mp4','original_walk.mp4']:
            if (job/'input'/name).exists():shutil.copy2(job/'input'/name,OUT/'references'/(c['id']+'.mp4'));break
        if (job/'reference_mapping.json').exists():shutil.copy2(job/'reference_mapping.json',OUT/'references'/(c['id']+'.json'))
    sync()
    manifest={p.relative_to(OUT).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256SUMS.json'}
    save(OUT/'SHA256SUMS.json',manifest)
    archive=ROOT/'output/fatfish_complete_v01.zip'
    if archive.exists():assert read(RUN/'release.json')['npk_sha256']==sha(npk),'Refuse replacing an archive for a different NPK.'
    temporary=archive.with_suffix('.tmp.zip')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file():z.write(p,'Fatfish_Complete_v01/'+p.relative_to(OUT).as_posix())
    with zipfile.ZipFile(temporary) as z:
        assert z.testzip() is None
        assert z.read('Fatfish_Complete_v01/'+npk.name)==npk.read_bytes()
        assert len([n for n in z.namelist() if '/native_frames/' in n])==174
        assert len([n for n in z.namelist() if '/hd_frames/' in n])==174
        assert len([n for n in z.namelist() if '/references/' in n and n.endswith('.mp4')])==25
    temporary.replace(archive)
    result={'npk':str(npk),'npk_sha256':sha(npk),'archive':str(archive),'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'archive_crc_passed':True,'game_runtime_validated':False}
    save(RUN/'release.json',result);save(TRIAL/'release.json',result)
    state=read(ROOT/'preparation_status.json');state['complete_ref2va_v01']={**result,'actions':25,'native_frames':174,'resource_audit':resource|{'jobs':'See output/Fatfish_Complete_v01/resource_and_geometry_audit.json','frame_checks':'174 native records in audit JSON'}};state['design_status']='Complete Ref2VA v01:25 manually annotated actions and174 slots packaged and offline validated; awaiting game test.';state['game_installation_changed']=False;save(ROOT/'preparation_status.json',state)
    doc=f'''# 大肥鱼女法师完整默认模板 v01

已按用户 revision26 手工标注完成25段、IMG000–173共174帧。工作台为 http://127.0.0.1:8791/ ，完整连续预览为 http://127.0.0.1:8791/trials/full_ref2va_v01/preview.html 。双击根目录“打开动作面板.cmd”可重开本机服务。

成品：`output/{npk.name}`；源素材与完整记录：`output/Fatfish_Complete_v01/`；便携归档：`output/{archive.name}`。

范围为38个皮肤IMG路径与26个默认装扮透明隐藏层；所有174皮肤帧位均有本轮实际画面，没有旧站立占位。武器、独立转职特效和其他装扮覆盖不在这个模板范围。本包不改ANI，游戏仍按原ANI选择帧与配时。25段名称、范围和网页配时来自用户手工标注，未宣称自动解析了当前客户端ANI。

## 制作与验证

复用已认可的Ref2VA走路片段，其余动作通过本机 MiniMax H3 Ref2VA 生成，高清造型图与原版连续动作视频同时作为视觉参考。新片段输出608×352、124帧、24fps、20步、一采；后处理提取透明帧，使用固定片段缩放与X偏移、逐姿势原版底部Y定位，保留全彩色阶并直接抗锯齿缩放，没有调色板减色。高清透明图单独保存在hd_frames。

共完成{resource['completed_new_jobs']}次本地生成，含有针对性的返工；本轮云端调用0次。采样累计{resource['new_job_sampling_seconds_total']:.2f}秒。采样显存峰值{resource['gpu_memory_peak_observed_MiB']:.0f}MiB，系统可用RAM最低{resource['minimum_available_ram_GiB']:.2f}GiB，可用提交额度最低{resource['minimum_available_commit_GiB']:.2f}GiB；内存中止次数{len(resource['memory_abort_files'])}。

64个IMG共11136项像素和坐标回读通过，其中4524项检查默认装扮隐藏层全透明且原载荷未变。174个实际PNG与NPK内裁切图逐像素一致。IMG链接按实际像素及坐标重建。ZIP的CRC及NPK、174张原生PNG、174张高清PNG数量核对通过。NPK SHA256：`{validation['sha256']}`。

## 游戏验收

本轮未修改游戏目录，新25段保留待验收；旧Grok步行通过记录和原手工标注文件均保留。退出游戏后移出之前的Fatfish测试NPK备份，一次只放本版一个同类补丁；使用默认时装测试。安装与回滚步骤见成品文件夹的《安装与测试说明.txt》。本版尚未游戏内验收。

模型对原版姿势的跟随仍有近似，主要是手臂高度、腰身和裙摆形变；连续段间的造型也可能变化。首中末、透明对照与具体返工记录见qa/content_review.json及每段contact_sheet.png。离线封装通过不代表武器衔接、转职覆盖和实机所有动作均通过。
'''
    (ROOT/'docs/fatfish_complete_ref2va_v01.md').write_text(doc,'utf-8')
    readme=ROOT/'README.md';text=readme.read_text('utf-8');marker='最新完整版本：[Ref2VA 全动作 v01](docs/fatfish_complete_ref2va_v01.md)。25段手工标注、174帧默认模板已入包；打开动作面板查看新旧对照和验收状态。NPK为 `output/'+npk.name+'`，完整归档为 `output/'+archive.name+'`。离线11136项回读通过，游戏内待实测。\n\n'
    if marker not in text:text=text.replace('准备详情：',marker+'准备详情：',1);readme.write_text(text,'utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':release()
