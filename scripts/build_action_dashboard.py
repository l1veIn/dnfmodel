"""Build the local review panel; classification and artwork acceptance are separate."""
from pathlib import Path
import hashlib
import json
import shutil
from datetime import datetime, timezone, timedelta
from PIL import Image
from dnf_resources import ImgArchive, read_npk

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/Fatfish_Action_Dashboard'
STATE=ROOT/'design/fatfish/action_catalog'
BOX=(170,250,362,410)
NPK=ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK'
MASTER=ROOT/'design/fatfish/nearest_standing_v04/standing_canvas.png'

def now():return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(p)

def archive_legacy_catalog():
    old=OUT/'catalog.json';backup=STATE/'legacy_visual_catalog_v1.json'
    if old.exists() and not backup.exists():
        data=json.loads(old.read_text('utf-8'))
        if data.get('schema_version')==1:
            save(backup,{'archived_at':now(),'reason':'Visual slices were not ANI actions; withdrawn from classification and completion totals.','catalog':data})
    progress=STATE/'progress.json';backup=STATE/'progress_before_classification_v2.json'
    if progress.exists() and not backup.exists():shutil.copy2(progress,backup)

def migrate_progress(progress):
    marker='classification_v2_no_visual_groups'
    if any(e.get('source')==marker for e in progress['events']):return
    old=progress['reviews'].get('jump')
    if old and old.get('note') and 'frame_023' not in progress['reviews']:
        progress['reviews']['frame_023']={**old,'source':'legacy_note_migration',
            'note':'旧目录备注（原动作名未经 ANI 核实）：'+old['note']}
    progress['revision']+=1
    progress['events'].append({'source':marker,'at':now(),'revision':progress['revision'],
        'walk_review_preserved':True,'note':'Removed visual action groups. Legacy reviews retained; no new action approval inferred.'})
    save(STATE/'progress.json',progress)

def confirmed_actions(mapping,fat):
    result=[]
    for action in mapping.get('actions',[]):
        proof=action['verification']
        assert all(proof.get(k) is True for k in ('current_client','character_state_reference','image_reference'))
        assert action['source_files']
        for evidence in action['source_files']:assert sha(ROOT/evidence['file'])==evidence['sha256']
        sequence=action['frames'];slots=[f['img_slot'] for f in sequence]
        assert slots and all(type(s) is int and 0<=s<174 for s in slots)
        assert all(type(f['delay_ms']) is int and f['delay_ms']>=0 for f in sequence)
        available=sorted(set(slots)&set(map(int,fat)))
        result.append({'id':action['id'],'name':action['name'],'category':'真实动作 · 已核实','kind':'verified_action',
            'slots':slots,'available_slots':available,'complete':set(slots)<=set(available),
            'preview_slot':available[0] if available else slots[0],'default_ms':120,
            'delays_ms':[f['delay_ms'] for f in sequence],'loop':action['loop'],
            'label_basis':'current_client_ani_and_state_reference','evidence':action['evidence_summary'],
            'sample_note':action['evidence_summary'],'links':[]})
    return result

def main():
    for d in ['assets/original','assets/fatfish','assets/walk28','downloads','evidence']:(OUT/d).mkdir(parents=True,exist_ok=True)
    STATE.mkdir(parents=True,exist_ok=True);archive_legacy_catalog()
    mapping=json.loads((STATE/'action_mapping.json').read_text('utf-8'))
    before={str(p):sha(p) for p in [NPK,MASTER]}
    entries=read_npk(NPK);raw=NPK.read_bytes();entry=next(e for e in entries if '/avatar/skin/' in e['path'])
    archive=ImgArchive(raw[entry['offset']:entry['offset']+entry['length']])
    original={};fat={};slot_sources={}
    for slot in range(174):
        canvas=Image.new('RGBA',(500,500));source=ROOT/f'materials/female_mage/reference_composite/frames/{slot:04d}.png'
        with Image.open(source) as im:canvas.alpha_composite(im.convert('RGBA'),(185,0))
        crop=canvas.crop(BOX);assert crop.getchannel('A').getbbox()
        path=OUT/f'assets/original/{slot:04d}.png';crop.save(path);original[str(slot)]=path.relative_to(OUT).as_posix()
    for slot in list(range(10))+[10,23,65]:
        if slot in [23,65]:
            name='jump_023' if slot==23 else 'cast_065';source=ROOT/f'design/fatfish/motion_master_v05/corrected/{name}_canvas.png'
            with Image.open(source) as im:canvas=im.convert('RGBA')
            slot_sources[str(slot)]={'role':'single_frame_sample','source':str(source),'sha256':sha(source),'in_accepted_npk':False}
        else:
            canvas=Image.new('RGBA',(500,500));m=archive.resolve(slot);canvas.alpha_composite(archive.image(slot),(m['x'],m['y']))
            slot_sources[str(slot)]={'role':'accepted_walk_artwork' if slot<10 else 'approved_design_master','source':str(NPK),'img_slot':slot,'in_accepted_npk':True}
        path=OUT/f'assets/fatfish/{slot:04d}.png';canvas.crop(BOX).save(path);fat[str(slot)]=path.relative_to(OUT).as_posix()
    walk28=[]
    for i in range(28):
        p=ROOT/f'output/Fatfish_Grok_Walk_Test_v01/frames_rgba_28/{i:04d}.png';canvas=Image.new('RGBA',(500,500))
        with Image.open(p) as im:canvas.paste(im.convert('RGBA'),(186,272))
        dest=OUT/f'assets/walk28/{i:04d}.png';canvas.crop(BOX).save(dest);walk28.append(dest.relative_to(OUT).as_posix())
    walk={'id':'walk','name':'步行循环 · 已验收素材','category':'制作片段','kind':'production',
        'slots':list(range(10)),'available_slots':list(range(10)),'complete':True,'default_ms':28/24*1000/10,
        'loop':True,'preview_slot':0,'label_basis':'user_accepted_artwork_not_verified_ani',
        'evidence':'用户已验收此制作片段；IMG0–9 是现有测试包的写入槽位。原版 ANI 的引用顺序、配时与动作边界尚未核实。',
        'sample_note':'保留原始走路通过记录。28帧源片段、入包10帧均保持原样；本卡不计入真实 ANI 动作数量。',
        'source28':walk28,'links':[{'label':'走路测试 NPK','url':'downloads/'+NPK.name},
        {'label':'完整28帧与说明','url':'downloads/fatfish_grok_walk_test_v01.zip'}]}
    verified=confirmed_actions(mapping,fat);assigned=set(s for c in verified for s in c['slots']);unknown=[s for s in range(174) if s not in assigned]
    frame_clips=[]
    for slot in unknown:
        note='帧位尚未归入真实动作；这里只展示单张原始素材，不按相邻编号播放。'
        if slot==10:note+=' 已有确认过的造型主帧；这不代表待机动作已核实或完成。'
        elif slot in (23,65):note+=' 已有单帧小样；旧文件名中的动作名不是 ANI 证据。'
        elif slot<10:note+=' 测试包在此槽位使用已验收的走路素材；槽位用途仍待 ANI 核对。'
        frame_clips.append({'id':f'frame_{slot:03d}','name':f'IMG {slot:03d} · 未归类','category':'未归类帧位',
            'kind':'unclassified','slots':[slot],'available_slots':[slot] if str(slot) in fat else [],'complete':False,
            'default_ms':120,'loop':False,'preview_slot':slot,'label_basis':'unclassified','sample_note':note,
            'evidence':'未取得此帧的当前客户端 ANI / 状态引用证据。','links':[]})
    clips=[walk]+verified+frame_clips
    assert len(fat)==13
    catalog={'schema_version':2,'title':'大肥鱼 · 女法动作工作台','built_at':now(),'frame_count':174,
        'verified_action_count':len(verified),'unclassified_slots':unknown,'action_total_known':False,'completion_percentage':None,
        'crop_world':list(BOX),'frame_dimensions':[192,160],'ground_guide_y':386-BOX[1],'root_guide_x':250-BOX[0],
        'grouping_note':'真实动作只采用已核实的 ANI 与角色状态引用；未核实帧位保持未归类，不按目测分组，不计算全项目完成率。',
        'timing_note':'测试片段预览配时，不是原版 ANI 配时；游戏动作引用顺序仍待核实。',
        'accepted_quote':'走路这段没问题，可以通过','master_design_approved':True,'master':'assets/fatfish/0010.png',
        'mapping':mapping,'original':original,'fatfish':fat,'slot_provenance':slot_sources,'clips':clips}
    progress_path=STATE/'progress.json';progress=json.loads(progress_path.read_text('utf-8'));walk_before=dict(progress['reviews']['walk'])
    migrate_progress(progress);assert progress['reviews']['walk']==walk_before
    save(OUT/'catalog.json',catalog)
    (OUT/'catalog.js').write_text('window.FATFISH_CATALOG = '+json.dumps(catalog,ensure_ascii=False)+';\nwindow.FATFISH_PROGRESS = '+json.dumps(progress,ensure_ascii=False)+';\n',encoding='utf-8')
    shutil.copy2(NPK,OUT/'downloads'/NPK.name);shutil.copy2(ROOT/'output/fatfish_grok_walk_test_v01.zip',OUT/'downloads/fatfish_grok_walk_test_v01.zip')
    for source,dest in [('action_dashboard.html','index.html'),('action_dashboard.css','app.css'),('action_dashboard.js','app.js')]:shutil.copy2(ROOT/'scripts'/source,OUT/dest)
    for source in ['research_report.md','current_client_pvf_probe.json','parsed_format_sample_move.json','loose_animation_inventory.json']:shutil.copy2(ROOT/'docs/ani_research'/source,OUT/'evidence'/source)
    save(OUT/'evidence/action_mapping.json',mapping)
    for p,digest in before.items():assert sha(Path(p))==digest
    save(STATE/'asset_validation.json',{'built_at':now(),'schema_version':2,'verified_actions':len(verified),'unclassified_slots':len(unknown),
        'original_frames':174,'fatfish_slots':13,'walk_source_frames':28,'legacy_visual_groups_in_catalog':0,'completion_percentage':None,
        'walk_review_unchanged':True,'source_files_unchanged':before,'no_per_frame_auto_fit':True,'generation_jobs':0})
    status_path=ROOT/'preparation_status.json';status=json.loads(status_path.read_text('utf-8'))
    status['action_dashboard']={'url':'http://127.0.0.1:8790/','path':str(OUT/'index.html'),'verified_actions':len(verified),
        'unclassified_slots':len(unknown),'action_total_known':False,'completion_percentage':None,'original_slots':174,
        'available_fatfish_slots':13,'review_state':str(progress_path),'user_accepted_production_clips':['walk'],'game_installation_changed':False}
    save(status_path,status)
    (OUT/'使用说明.txt').write_text('大肥鱼动作工作台\n\n双击“打开动作面板.cmd”，地址 http://127.0.0.1:8790/ 。\n'
        '制作片段保存用户验收的素材；走路通过记录保留，主帧和NPK未改动。\n'
        '真实动作只接纳有来源且适配当前客户端的 ANI + 角色状态引用。当前尚未取得，动作总数未知，不显示完成百分比。\n'
        '未核实的174个帧位全部标为未归类，静态展示、逐帧可对照，不按编号拼成动作。\n'
        '原36组目测分组已撤下并归档；旧备注和验收记录保留，IMG23旧备注可在该单帧查看。\n'
        '解析与查证记录位于面板归类依据，也可阅读 docs/ani_research/research_report.md。\n'
        '备注保存在 design/fatfish/action_catalog/progress.json；重建不重置验收。\n',encoding='utf-8')
    print(json.dumps({'verified_actions':len(verified),'unclassified_slots':len(unknown),'accepted_production_clips':['walk'],'walk_review_preserved':True}))

if __name__=='__main__':main()
