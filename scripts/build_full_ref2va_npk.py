"""Build all174 user-labelled slots; verify all64 IMG branches before publishing."""
import hashlib,json,shutil,time,zipfile
from pathlib import Path
from PIL import Image
from dnf_resources import ImgArchive,read_npk,write_npk,write_v2
from fatfish_full_ref2va import ROOT,RUN,OUT,WEB,TRIAL,BASE,read,save,sha,publish

NAME='A_Fatfish_FMage_Complete_v01.NPK'
FIELDS=['x','y','canvas_width','canvas_height']

def build():
    data=read(RUN/'production.json');spec=read(RUN/'spec.json');review=read(OUT/'qa/content_review.json')
    assert len(data['clips'])==25 and sorted(s for c in data['clips'] for s in c['available_slots'])==list(range(174))
    assert all(c['status']=='processed' for c in data['clips'])
    assert sorted(review['reviewed_clip_ids'])==sorted(c['id'] for c in data['clips'])
    assert review['unresolved_blockers']==[],review['unresolved_blockers']
    for path,digest in spec['protected_files'].items():assert sha(path)==digest,('Protected file changed',path)
    target=ROOT/'output'/NAME
    if target.exists():raise FileExistsError('Published package preserved: '+str(target))
    images=[];meta=[];mapping=[]
    for slot in range(174):
        source=OUT/f'native_frames/{slot:04d}.png';im=Image.open(source).convert('RGBA');assert im.size==(500,500)
        box=im.getchannel('A').getbbox();assert box and min(box[:2])>0 and max(box[2:])<500,(slot,box)
        crop=im.crop(box);assert crop.width>=5 and crop.height>=5
        m={'x':box[0],'y':box[1],'canvas_width':500,'canvas_height':500};images.append(crop);meta.append(m)
        clip=next(c for c in data['clips'] if c['start']<=slot<=c['end']);record=read(OUT/'clips'/clip['id']/'mapping.json')
        frame=next(r for r in record['mappings'] if r['slot']==slot)
        assert sha(source)==frame['native_sha256'],('Native source changed since registration',slot)
        mapping.append({'slot':slot,'action':clip['name'],'clip_id':clip['id'],'native_png_sha256':sha(source),'npk_bbox':list(box),'registration':frame,'source_video':clip['video']})
    concrete=[dict(m) for m in meta];seen={};links=0
    for i,(im,m) in enumerate(zip(images,meta,strict=True)):
        key=(im.size,hashlib.sha256(im.tobytes()).digest(),tuple(m[k] for k in FIELDS))
        if key in seen:meta[i]={'link':seen[key]};links+=1
        else:seen[key]=i
    body=write_v2(images,meta,preserve_links=True)
    raw=BASE.read_bytes();records=read_npk(BASE);assert len(records)==64
    payload=lambda r:raw[r['offset']:r['offset']+r['length']]
    skin=[r for r in records if '/avatar/skin/' in r['path']];assert len(skin)==38
    assert len({r['path'] for r in records})==64
    temporary=OUT/(NAME+'.validating');temporary.write_bytes(write_npk([(r['path'],body if '/avatar/skin/' in r['path'] else payload(r)) for r in records]))
    actual=temporary.read_bytes();written=read_npk(temporary);assert [r['path'] for r in written]==[r['path'] for r in records]
    checks=0;empty_checks=0
    for before,after in zip(records,written,strict=True):
        content=actual[after['offset']:after['offset']+after['length']];archive=ImgArchive(content);assert archive.count==174
        is_skin='/avatar/skin/' in after['path']
        if not is_skin:assert content==payload(before)
        for i in range(174):
            im=archive.image(i);m=archive.resolve(i)
            if is_skin:
                assert im.size==images[i].size and im.tobytes()==images[i].tobytes(),(after['path'],i,'pixels')
                assert all(m[k]==concrete[i][k] for k in FIELDS),(after['path'],i,'position')
            else:
                assert im.getchannel('A').getbbox() is None;empty_checks+=1
            checks+=1
    assert checks==11136 and empty_checks==4524
    for path,digest in spec['protected_files'].items():assert sha(path)==digest
    temporary.rename(OUT/NAME);shutil.copy2(OUT/NAME,target)
    digest=sha(target);(OUT/(NAME+'.sha256')).write_text(digest+'  '+NAME+'\n','ascii');shutil.copy2(OUT/(NAME+'.sha256'),ROOT/'output'/(NAME+'.sha256'))
    report={'package':str(target),'sha256':digest,'bytes':target.stat().st_size,'entries':64,'skin_paths':38,'hidden_default_avatar_paths':26,
      'slots_per_img':174,'all174_slots_replaced':True,'action_segments':25,'unique_skin_images':174-links,'deduplicated_links':links,
      'pixel_coordinate_roundtrip_checks':checks,'transparent_hidden_layer_checks':empty_checks,'all_roundtrips_passed':True,
      'game_runtime_validated':False,'game_directory_changed':False,'npk_changes_ani':False,'source':str(BASE),'source_sha256':sha(BASE),
      'sampling':'Premultiplied Lanczos directly to original game geometry. Full color RGBA, no palette quantization.',
      'scope':'Default avatar174-slot template. Weapons, independent class effects, non-default costume overlays excluded.',
      'protected_files_unchanged':spec['protected_files'],'content_review':review,'created_at':time.time()}
    save(OUT/'npk_validation.json',report);save(RUN/'npk_validation.json',report);save(TRIAL/'npk_validation.json',report)
    save(OUT/'frame_mapping.json',{'slots':mapping,'annotation_revision':data['annotation_revision'],'npk_changes_ani':False,'note':'User-defined frame groups and timing are retained as source annotation; the client retains its original ANI timing.'})
    instructions=f'''大肥鱼女法师 · 完整默认模板 v01

文件：{NAME}
本包覆盖你标注的25段动作、IMG000–173共174个帧位；没有旧站姿回退占位。
局部手势和模型形变仍可能偏离原版，请把它作为第一版完整试装进行游戏验收。

安装：
1. 完全退出DNF。
2. 将 ImagePacks2 中此前放入的本项目 Fatfish 同类试装NPK移到游戏目录外备份，一次只保留一个版本。
3. 将本次 {NAME} 复制到：
C:\\WeGameApps\\地下城与勇士：创新世纪\\ImagePacks2
不需要覆盖官方原包。本轮没有自动修改游戏目录。
4. 女法使用默认时装外观测试；其他装扮可能盖住本包，装备防具无需脱下。

验收顺序：
站立与战斗待机 → 左右走动起停 → 奔跑前冲 → 跳跃与空中攻击 → 三段平A → 各职业施法 → 受击与倒地。
留意动作切换时的大小、脚底高度、手与武器衔接、头发/尾巴、角色朝向和层遮挡。
工作台：http://127.0.0.1:8791/
全部动作连续预览：http://127.0.0.1:8791/trials/full_ref2va_v01/preview.html
新25段均待你的验收；旧Grok步行验收记录已保留。

范围：38个女法皮肤路径与26个默认装扮隐藏层，每个IMG174帧。
不替换武器、独立转职特效或所有付费时装路径；本包不修改ANI。
25段名称和预览配时来自你的手工标注，不声称已自动解析官方ANI。
全彩透明清边后直接缩放抗锯齿，不做调色板减色；native_frames是实际入包画面，hd_frames保留高清透明源图。
离线像素、坐标与隐藏层回读校验11136项全部通过；本版尚未游戏内验收。

卸载/回滚：退出游戏，移出本次NPK，需要时放回备份的旧测试包。
SHA256：{digest}
'''
    (OUT/'安装与测试说明.txt').write_text(instructions,'utf-8')
    shutil.copy2(RUN/'annotations.snapshot.json',OUT/'annotations.snapshot.json')
    for c in data['clips']:c['status']='packaged'
    data.update(status='packaged',package=str(target),package_sha256=digest,updated_at=time.time());publish(data)
    print(json.dumps({k:report[k] for k in ['package','bytes','action_segments','pixel_coordinate_roundtrip_checks','all_roundtrips_passed']},ensure_ascii=False))

if __name__=='__main__':build()
