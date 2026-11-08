"""Package exactly 30 replacement slots, preserving every other rendered slot."""
import hashlib
import json
import shutil
from PIL import Image
from dnf_resources import ImgArchive,read_npk,write_npk,write_v2
from fatfish_grid30 import ROOT,RUN,OUT,BASE,NAME,save,sha

def build():
    target=ROOT/'output'/NAME
    if target.exists():raise FileExistsError('Published package must be preserved: '+str(target))
    spec=json.loads((RUN/'spec.json').read_text('utf-8'));expected={}
    for p,h in spec['protected_files_before'].items():assert sha(p)==h
    raw=BASE.read_bytes();records=read_npk(BASE);assert len(records)==64
    payload=lambda r:raw[r['offset']:r['offset']+r['length']]
    skin=[r for r in records if '/avatar/skin/' in r['path']];assert len(skin)==38
    assert all(payload(r)==payload(skin[0]) for r in skin)
    old=ImgArchive(payload(skin[0]));assert old.count==174
    images=[old.image(i) for i in range(174)]
    fields=['x','y','canvas_width','canvas_height']
    meta=[{k:old.resolve(i)[k] for k in fields} for i in range(174)]
    mappings=[]
    for slot in range(30):
        im=Image.open(OUT/f'nearest/{slot:03d}.png').convert('RGBA');assert im.size==(160,160)
        box=im.getchannel('A').getbbox();assert box and box[0]>0 and box[1]>0 and box[2]<160 and box[3]<160
        canvas=Image.new('RGBA',(500,500));canvas.alpha_composite(im,(170,250));bbox=canvas.getchannel('A').getbbox()
        images[slot]=canvas.crop(bbox);meta[slot]={'x':bbox[0],'y':bbox[1],'canvas_width':500,'canvas_height':500}
        mappings.append({'img_slot':slot,'source':f'nearest/{slot:03d}.png','source_sha256':sha(OUT/f'nearest/{slot:03d}.png'),'native_window_origin':[170,250],
                         'crop_bbox_world':list(bbox),'reused_from_approved_trial':slot<6})
    # Resolve BEFORE editing and rebuild links by rendered image AND coordinates.
    # Old fallback links to standing slot10 must not inherit its newly generated image.
    concrete=[dict(m) for m in meta];seen={};dedup_links=0
    for i,(im,m) in enumerate(zip(images,meta,strict=True)):
        key=(im.size,hashlib.sha256(im.tobytes()).digest(),tuple(m[k] for k in fields))
        if key in seen:meta[i]={'link':seen[key]};dedup_links+=1
        else:seen[key]=i
    body=write_v2(images,meta,preserve_links=True)
    target.write_bytes(write_npk([(r['path'],body if '/avatar/skin/' in r['path'] else payload(r)) for r in records]))
    actual=target.read_bytes();written=read_npk(target);assert [r['path'] for r in written]==[r['path'] for r in records]
    checked=0;outside=0
    for before,after in zip(records,written,strict=True):
        data=actual[after['offset']:after['offset']+after['length']];archive=ImgArchive(data);assert archive.count==174
        is_skin='/avatar/skin/' in after['path']
        if not is_skin:assert data==payload(before)
        for i in range(174):
            image=archive.image(i);position=archive.resolve(i)
            if is_skin:
                assert image.size==images[i].size and image.tobytes()==images[i].tobytes(),(after['path'],i)
                assert all(position[k]==concrete[i][k] for k in fields),(after['path'],i)
                if i>=30:
                    assert image.tobytes()==old.image(i).tobytes() and image.size==old.image(i).size
                    assert all(position[k]==old.resolve(i)[k] for k in fields)
                    outside+=1
            else:assert image.getchannel('A').getbbox() is None
            checked+=1
    assert checked==11136 and outside==38*144
    for p,h in spec['protected_files_before'].items():assert sha(p)==h
    shutil.copy2(target,OUT/NAME)
    (ROOT/'output'/(NAME+'.sha256')).write_text(sha(target)+'  '+NAME+'\n',encoding='ascii')
    save(OUT/'frame_mapping.json',{'updated_slots':list(range(30)),'mapping':mappings,'ani_verified':False,'npk_changes_ani':False,'untouched_skin_slots':list(range(30,174)),
          'fallback_link_handling':'Original slots resolved before replacements; identical pixels with identical metadata relinked to their first unchanged equivalent. Slots30..173 preserve base rendered pixels and coordinates.'})
    report={'package':str(target),'sha256':sha(target),'bytes':target.stat().st_size,'base':str(BASE),'base_sha256':sha(BASE),'entries':64,'skin_paths':38,'hidden_default_avatar_paths':26,
          'frame_slots_per_img':174,'updated_slots':list(range(30)),'updated_slot_count':30,'pixel_and_position_roundtrips':checked,'all_roundtrips_passed':True,
          'outside_test_skin_slots_preserved_checks':outside,'hidden_layer_payloads_unchanged':True,'deduplicated_skin_links':dedup_links,'unique_skin_images':174-dedup_links,
          'game_runtime_validated':False,'game_installation_changed':False,'npk_changes_ani':False,'sampling':'Nearest at original-size geometry; HD640 originals supplied separately.',
          'protected_files_unchanged':spec['protected_files_before']}
    save(OUT/'npk_validation.json',report);save(RUN/'npk_validation.json',report)
    instructions=f'''大肥鱼女法师 · 30帧位试装 v01

文件：{NAME}
更新：IMG000–029 共30个帧位，其中000–005沿用已认可的小样，006–029本轮新增。
帧号不是动作分类；当前ANI顺序、延时与全部动作尚未核实。游戏沿用自己的动作选择与配时。

安装：
1. 完全退出DNF。
2. 将 ImagePacks2 中此前放入的本项目 Fatfish 同类试装NPK移到游戏目录外备份，一次只保留一个版本。
3. 将本次 {NAME} 复制到：
C:\\WeGameApps\\地下城与勇士：创新世纪\\ImagePacks2
不需要覆盖或删除官方原包。本工具未自动修改游戏目录。
4. 用女法/元素师，先使用默认时装外观进行测试；装扮栏时装可能盖住本包，装备防具无需脱下。

检查：站立、左右走动和起停、奔跑、普通攻击；留意脚底、头部大小变化、尾巴、手与武器的衔接。
本包不替换武器贴图或独立转职特效。部分后摆臂、抬腿遮挡仍有生成差异，按试装小样评估。

范围：38个女法皮肤路径、26个默认装扮隐藏层。其余144个皮肤帧位的画面与坐标沿用之前已通过的Grok测试基包（其中含旧的站姿回退素材）。
已重建IMG引用，替换站姿10不会误改范围外的旧回退帧。
离线回读11136个帧位的像素和坐标通过；尚未进行本版游戏内验收。

画质：保留30张640px工作窗口高清PNG；本NPK使用矫正后最近邻小图，以维持已验证的游戏坐标大小。高清源图直接入包后同尺寸显示尚未验证。
registered_hd 为高清版，nearest 为实际入包前的160px坐标窗口，frame_mapping.json记录每帧坐标。

卸载/回滚：退出游戏，移出本次NPK，需要时放回备份的旧测试包。
'''
    (OUT/'安装与测试说明.txt').write_text(instructions,encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['package','bytes','entries','updated_slot_count','pixel_and_position_roundtrips','outside_test_skin_slots_preserved_checks','all_roundtrips_passed']}))

if __name__=='__main__':build()
