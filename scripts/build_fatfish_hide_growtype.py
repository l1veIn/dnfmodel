"""Hide current female-mage growtype overlays using transparent, count-matched IMG V2."""
from __future__ import annotations
import hashlib,json,shutil,time,zipfile
from pathlib import Path
from PIL import Image
from dnf_resources import IMG_MAGIC,ImgArchive,read_npk,write_npk,write_v2,save_json

ROOT=Path(__file__).resolve().parents[1]
GAME=Path('C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2')
OUT=ROOT/'output/Fatfish_Hide_Growtype_v01'
NAME='A_Fatfish_FMage_Hide_Growtype_v01.NPK'
BASE=ROOT/'output/Fatfish_Complete_v01/A_Fatfish_FMage_Complete_v01.NPK'
PREFIX='sprite/character/mage/equipment/growtype/'
CUSTOM={'sprite/character/mage/equipment/custom/happyavatar_body.img','sprite/character/mage/equipment/custom/happyavatar_head.img'}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def build():
    OUT.mkdir(parents=True,exist_ok=True)
    target=ROOT/'output'/NAME
    if target.exists():raise FileExistsError('Preserve existing release: '+str(target))
    baseline_sha=sha(BASE);base_paths={r['path'] for r in read_npk(BASE)}
    blade_report=ROOT/'validation/blade_patch_inspection/costume_normal/report.json';blade=json.loads(blade_report.read_text('utf-8'))
    blade_path=Path(blade['source']);assert sha(blade_path)==blade['sha256']
    sources=sorted(GAME.glob('sprite_character_mage_equipment_growtype*.NPK'))
    assert len(sources)==7,('Review changed source package inventory',len(sources))
    sources.append(GAME/'sprite_character_mage_equipment_custom.NPK')
    source_records=[];manifest=[];entries=[];cache={}
    for source in sources:
        source_hash=sha(source);snapshot=ROOT/'sources/npk'/source.name
        assert snapshot.exists() and sha(snapshot)==source_hash,('Prepared copy differs from current client',source.name)
        raw=source.read_bytes();records=read_npk(source)
        source_records.append({'name':source.name,'path':str(source),'sha256':source_hash,'bytes':len(raw)})
        for r in records:
            path=r['path']
            if source.name.endswith('_custom.NPK'):
                if path not in CUSTOM:continue
            else:assert path.startswith(PREFIX),('Unexpected resource outside growtype directory',path)
            assert path not in base_paths,('Would override character artwork',path)
            payload=raw[r['offset']:r['offset']+r['length']]
            assert payload.startswith(IMG_MAGIC) and r['frame_count'] and 0<r['frame_count']<=10000
            count=r['frame_count']
            if count not in cache:
                blank=Image.new('RGBA',(1,1));images=[blank]*count
                meta=[{'x':0,'y':0,'canvas_width':500,'canvas_height':500}]+[{'link':0} for _ in range(count-1)]
                cache[count]=write_v2(images,meta,preserve_links=True)
            entries.append((path,cache[count]))
            manifest.append({'path':path,'source_npk':source.name,'source_img_version':r['version'],'source_frame_count':count,
              'source_payload_sha256':hashlib.sha256(payload).hexdigest(),'replacement_img_version':2,'replacement_frame_count':count,
              'operation':'New transparent image from header frame count; source V5 pixels are not decoded or converted.'})
    assert len(entries)==112 and len({n for n,_ in entries})==112
    assert sum(r['source_frame_count'] for r in manifest)==4200
    temporary=OUT/(NAME+'.validating');temporary.write_bytes(write_npk(entries));written=read_npk(temporary);data=temporary.read_bytes()
    assert [r['path'] for r in written]==[n for n,_ in entries]
    checks=0
    for row,expected in zip(written,manifest,strict=True):
        archive=ImgArchive(data[row['offset']:row['offset']+row['length']]);assert archive.count==expected['source_frame_count']
        for i in range(archive.count):
            assert archive.image(i).getchannel('A').getbbox() is None,(row['path'],i)
            assert archive.resolve(i)['index']==0
            checks+=1
    assert checks==4200
    assert sha(BASE)==baseline_sha and sha(blade_path)==blade['sha256']
    assert all(sha(r['path'])==r['sha256'] for r in source_records)
    temporary.rename(OUT/NAME);shutil.copy2(OUT/NAME,target)
    report={'created_at':time.time(),'package':str(target),'sha256':sha(target),'bytes':target.stat().st_size,
      'entries':112,'growtype_paths':110,'custom_puppet_paths':2,'transparent_frame_checks':checks,'all_output_frames_transparent':True,
      'source_frame_counts_preserved':True,'source_versions':sorted(set(r['source_img_version'] for r in manifest)),
      'new_img_version':2,'v5_source_pixels_decoded':False,'normal_skill_effect_paths_included':False,
      'complete_character_package':str(BASE),'complete_character_sha256_unchanged':baseline_sha,'overlapping_character_package_paths':[],
      'method_reference':{'source':str(blade_path),'sha256':blade['sha256'],'observed':'Seven swordman growtype resources are fully transparent IMG V2 in the inspected Blade costume package. No Blade artwork reused.'},
      'source_packages':source_records,'game_directory_changed':False,'game_runtime_validated':False}
    save_json(OUT/'validation.json',report);save_json(OUT/'resource_manifest.json',manifest)
    (OUT/(NAME+'.sha256')).write_text(report['sha256']+'  '+NAME+'\n','ascii')
    instructions=f'''大肥鱼女法师 · 转职附加外观屏蔽包 v01

文件：{NAME}
与 A_Fatfish_FMage_Complete_v01.NPK 配套使用，也可独立屏蔽女法转职附加外观。

安装：
1. 完全退出DNF。
2. 将本包NPK与刚才的完整时装NPK一同放入：
C:\\WeGameApps\\地下城与勇士：创新世纪\\ImagePacks2
3. 重新进入游戏检查元素、召唤、战法、魔道、奶萝及缔造者的附加外观。
卸载：退出游戏，移出这一份屏蔽NPK即可；本体时装包可继续保留。

范围：当前客户端7个mage/equipment/growtype包的110个IMG路径，以及custom/happyavatar_body、happyavatar_head两个人偶附加图层。
共112路径，4200个帧位，逐项验证全透明；各IMG保留自己的原帧数。
包含这些目录内的职业/觉醒附加图层、跟随物、光效及职业武器附加效果。目录外的普通技能效果和基础武器贴图未列入屏蔽清单。
资源按本地路径生效，其他使用这些路径的女法角色也会一并隐藏。

参考“刃”包透明growtype覆盖法，未复用刃的人物画稿。
部分原资源为IMG V5，仅读取头部帧数；输出为重新建立的透明IMG V2。
本轮没有修改游戏目录，没有改动174帧完整时装包，没有改ANI，没有重新生图。
尚未游戏内验收；若仍有附加外观残留，可截图并记录转职名称，以便定位目录外资源。

SHA256：{report['sha256']}
'''
    (OUT/'安装与范围说明.txt').write_text(instructions,'utf-8')
    archive=ROOT/'output/fatfish_hide_growtype_v01.zip'
    if archive.exists():raise FileExistsError('Preserve existing archive: '+str(archive))
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in OUT.iterdir():
            if p.is_file():z.write(p,'Fatfish_Hide_Growtype_v01/'+p.name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert z.read('Fatfish_Hide_Growtype_v01/'+NAME)==target.read_bytes()
    record={'package':str(target),'sha256':sha(target),'archive':str(archive),'archive_sha256':sha(archive),'entries':112,'frames':4200,'validated_offline':True,'game_runtime_validated':False}
    save_json(ROOT/'validation/growtype_hide_inspection/release.json',record)
    print(json.dumps(record,ensure_ascii=False))

if __name__=='__main__':build()
