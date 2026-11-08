"""Merge Fatfish artwork with current female-mage costume and growtype masks.

Read-only access to ImagePacks2. Reuses the existing 174-frame artwork verbatim.
NPK paths may share an IMG payload, as in the inspected Blade reference package.
"""
from __future__ import annotations

import hashlib
import json
import struct
import time
import zipfile
from collections import Counter
from pathlib import Path

from PIL import Image

from dnf_resources import NAME_KEY, NPK_MAGIC, ImgArchive, read_npk, save_json, write_v2

ROOT = Path(__file__).resolve().parents[1]
GAME = Path('C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2')
OUT = ROOT / 'output/Fatfish_AllAvatar_v02'
NAME = 'A_Fatfish_FMage_AllAvatar_NoGrowtype_v02.NPK'
BASE = ROOT / 'output/Fatfish_Complete_v01/A_Fatfish_FMage_Complete_v01.NPK'
ADDON = ROOT / 'output/Fatfish_Hide_Growtype_v01/A_Fatfish_FMage_Hide_Growtype_v01.NPK'
AVATAR = 'sprite/character/mage/equipment/avatar/'
ALTERNATE = 'sprite/character/character/mage/equipment/avatar/'
PARTS = ('belt', 'cap', 'coat', 'face', 'hair', 'neck', 'pants', 'shoes', 'skin')
EXPECTED_BASE_SHA = '3572338ebc443f571e68afe1ba363f673d14ac298321146c2d1778a2fb7b1395'
EXPECTED_ADDON_SHA = '876ab94c7243c00a1ac86be4d7d11c3de2891c25c6cd757524c7c9485df81a45'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_payload(path, row):
    with path.open('rb') as stream:
        stream.seek(row['offset'])
        return stream.read(row['length'])


def write_shared_npk(entries):
    unique = {}
    payloads = []
    offset = 52 + 264 * len(entries)
    header = bytearray(NPK_MAGIC + struct.pack('<I', len(entries)))
    for name, payload in entries:
        if payload not in unique:
            unique[payload] = offset
            payloads.append(payload)
            offset += len(payload)
        encoded = name.encode('utf-8')
        assert len(encoded) < 256
        header.extend(struct.pack('<II', unique[payload], len(payload)))
        header.extend(bytes(a ^ b for a, b in zip(encoded.ljust(256, b'\0'), NAME_KEY)))
    checksum = hashlib.sha256(header[:len(header) // 17 * 17]).digest()
    return bytes(header) + checksum + b''.join(payloads)


def build():
    target = OUT / NAME
    if target.exists():
        raise FileExistsError('Preserve the existing release: ' + str(target))
    OUT.mkdir(parents=True, exist_ok=True)
    protected = {str(p): sha(p) for p in (
        BASE, ADDON, ROOT / 'design/fatfish/action_catalog/manual_motion.json',
        ROOT / 'design/fatfish/action_catalog/progress.json',
        ROOT / 'design/fatfish/full_ref2va_v01/production.json',
        *sorted(GAME.glob('*Fatfish*.NPK')),
    )}
    assert sha(BASE) == EXPECTED_BASE_SHA
    assert sha(ADDON) == EXPECTED_ADDON_SHA
    base_rows = read_npk(BASE)
    skin_rows = [r for r in base_rows if r['path'].startswith(AVATAR + 'skin/')]
    assert len(skin_rows) == 38 and len(base_rows) == 64
    body = read_payload(BASE, skin_rows[0])
    assert all(read_payload(BASE, r) == body for r in skin_rows)
    body_hash = hashlib.sha256(body).hexdigest()
    body_archive = ImgArchive(body)
    assert body_archive.count == 174 and body_archive.consumed == len(body)
    for i in range(174):
        # Compare the existing full world PNG to decoded IMG pixels and coordinates.
        native_path = ROOT / f'output/Fatfish_Complete_v01/native_frames/{i:04d}.png'
        with Image.open(native_path) as native:
            world = Image.new('RGBA', native.size)
            frame = body_archive.resolve(i)
            world.alpha_composite(body_archive.image(i), (frame['x'], frame['y']))
            assert world.tobytes() == native.convert('RGBA').tobytes(), ('Body artwork mismatch', i)

    blank_cache = {}

    def blank(count):
        if count not in blank_cache:
            assert 0 < count <= 10000
            image = Image.new('RGBA', (1, 1))
            meta = [{'x': 0, 'y': 0, 'canvas_width': 500, 'canvas_height': 500}]
            meta += [{'link': 0} for _ in range(count - 1)]
            blank_cache[count] = write_v2([image] * count, meta)
        return blank_cache[count]

    sources = [(GAME / f'sprite_character_mage_equipment_avatar_{part}.NPK', AVATAR)
               for part in PARTS]
    sources += [(GAME / f'sprite_character_character_mage_equipment_avatar_{part}.NPK', ALTERNATE)
                for part in PARTS if part != 'skin']
    entries = []
    manifest = []
    source_records = []
    for path, prefix in sources:
        rows = read_npk(path)
        source_records.append({'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size,
                               'entries': len(rows)})
        for row in rows:
            name = row['path']
            assert name.startswith(prefix) and name.endswith('.img'), name
            part = name[len(prefix):].split('/')[0]
            assert part in PARTS and '/atequipment/' not in name
            count = row['frame_count']
            is_skin = prefix == AVATAR and part == 'skin'
            assert not is_skin or count == 174
            payload = body if is_skin else blank(count)
            entries.append((name, payload))
            manifest.append({'path': name, 'source_npk': path.name, 'source_img_version': row['version'],
                             'source_frame_count': count, 'replacement_frame_count': count,
                             'operation': 'preserved_fatfish_body' if is_skin else 'transparent_costume',
                             'part': part, 'namespace': 'canonical' if prefix == AVATAR else 'alternate'})
    assert {r['path'] for r in manifest if r['operation'] == 'preserved_fatfish_body'} == {r['path'] for r in skin_rows}
    assert len(manifest) == 12055
    addon_validation = json.loads((ADDON.parent / 'validation.json').read_text('utf-8'))
    for source in addon_validation['source_packages']:
        assert sha(source['path']) == source['sha256']
        source_records.append(source)
    for row in read_npk(ADDON):
        name = row['path']
        assert name.startswith('sprite/character/mage/equipment/growtype/') or name in {
            'sprite/character/mage/equipment/custom/happyavatar_body.img',
            'sprite/character/mage/equipment/custom/happyavatar_head.img'}
        payload = read_payload(ADDON, row)
        assert payload == blank(row['frame_count'])
        entries.append((name, payload))
        manifest.append({'path': name, 'source_npk': ADDON.name, 'source_img_version': row['version'],
                         'source_frame_count': row['frame_count'], 'replacement_frame_count': row['frame_count'],
                         'operation': 'transparent_growtype_or_custom', 'part': 'growtype_or_custom', 'namespace': 'canonical'})
    assert len(entries) == 12167 and len({name for name, _ in entries}) == len(entries)
    entries.sort(key=lambda item: item[0])
    manifest.sort(key=lambda row: row['path'])
    temporary = target.with_suffix('.NPK.validating')
    temporary.write_bytes(write_shared_npk(entries))

    raw = temporary.read_bytes()
    written = read_npk(temporary)
    header_end = 20 + 264 * len(entries)
    assert raw[header_end:header_end + 32] == hashlib.sha256(raw[:header_end // 17 * 17]).digest()
    assert len(written) == len(entries)
    unique_ranges = {}
    hidden_frame_refs = 0
    for row, (name, expected), source in zip(written, entries, manifest, strict=True):
        assert row['path'] == name == source['path']
        assert row['frame_count'] == source['source_frame_count']
        payload = raw[row['offset']:row['offset'] + row['length']]
        assert payload == expected
        assert row['offset'] >= header_end + 32
        bounds = (row['offset'], row['length'])
        unique_ranges[bounds] = payload
        if source['operation'] != 'preserved_fatfish_body':
            hidden_frame_refs += row['frame_count']
    cursor = header_end + 32
    decoded_unique_blank_frames = 0
    for (offset, length), payload in sorted(unique_ranges.items()):
        assert offset == cursor, ('Unexpected gap or partial overlap', offset, cursor)
        cursor += length
        archive = ImgArchive(payload)
        assert archive.consumed == len(payload)
        if payload == body:
            continue
        for i in range(archive.count):
            assert archive.image(i).getchannel('A').getbbox() is None
            assert archive.resolve(i)['index'] == 0
            decoded_unique_blank_frames += 1
    assert cursor == len(raw)
    assert all(sha(path) == digest for path, digest in protected.items())
    assert all(sha(row['path']) == row['sha256'] for row in source_records)
    temporary.rename(target)
    report = {
        'created_at': time.time(), 'package': str(target), 'sha256': sha(target), 'bytes': target.stat().st_size,
        'entries': len(entries), 'skin_paths': 38, 'canonical_costume_paths': 11884,
        'alternate_costume_paths': 133, 'growtype_and_custom_paths': 112,
        'hidden_paths': len(entries) - 38, 'hidden_logical_frame_references': hidden_frame_refs,
        'unique_payload_ranges': len(unique_ranges), 'decoded_unique_blank_frames': decoded_unique_blank_frames,
        'body_frames_compared_with_native_pngs': 174, 'body_img_sha256': body_hash,
        'original_body_payload_preserved_verbatim': True, 'all_path_counts_match_current_sources': True,
        'all_hidden_payloads_fully_transparent': True, 'shared_ranges_exact_no_partial_overlaps': True,
        'excluded': ['male mage atequipment', 'swordman', 'common aura', 'creatures', 'ordinary weapons', 'ordinary skill effects'],
        'source_packages': source_records, 'protected_files_unchanged': protected,
        'game_directory_changed': False, 'game_runtime_validated': False,
        'reason': 'v01 only hid 26 default costume layers; worn paid costume layers could remain over the body.',
        'coverage_by_operation': dict(Counter(row['operation'] for row in manifest)),
    }
    save_json(OUT / 'validation.json', report)
    save_json(OUT / 'resource_manifest.json', manifest)
    (OUT / (NAME + '.sha256')).write_text(report['sha256'] + '  ' + NAME + '\n', 'ascii')
    (OUT / '安装说明.txt').write_text(f'''大肥鱼女法师 · 全时装覆盖与转职屏蔽合并版 v02

只安装一个文件：{NAME}

1. 完全退出游戏。
2. 从 ImagePacks2 移出之前的两份自制包，保存到游戏目录外：
   A_Fatfish_FMage_Complete_v01.NPK
   A_Fatfish_FMage_Hide_Growtype_v01.NPK
   如还装着其他女法外观测试包，也先移出，避免同路径冲突。
3. 将本版 NPK 放入 C:\\WeGameApps\\地下城与勇士：创新世纪\\ImagePacks2。
4. 重新启动游戏，检查红发、帽饰和旧衣服是否消失，确认大肥鱼头发、鱼尾和动作正常。
只移动自己安装的补丁；不要移出或替换任何 sprite 开头的官方文件。

本版修复：旧版只隐藏26个默认装扮路径。本版根据当前客户端清单覆盖12017个女法装扮路径，
并合并112个转职/自定义附加外观隐藏路径。38个皮肤路径共用原先的174帧大肥鱼本体，画稿与坐标逐字节保留。
各隐藏IMG保留其自己的原始帧数。NPK采用多路径共享IMG载荷，方法与参考刃包一致。
这是本地全时装覆盖；其他使用相同资源路径的女法角色也会显示大肥鱼。

未屏蔽通用光环、宠物、普通武器或普通技能效果。截图中的金色光环、头顶小人仍可能显示，
需要结合实际装备另行定位，不能据此判断本体覆盖失败。
没有改动游戏目录、原始动作标注、已有验收记录或本体174帧；本轮没有重新生成图像。
离线校验通过，尚待游戏内验证。工作台展示的是本体动画，不能代替游戏叠层验收。

文件SHA256：{report['sha256']}
''', 'utf-8')
    archive_path = ROOT / 'output/fatfish_all_avatar_v02.zip'
    if archive_path.exists():
        raise FileExistsError('Preserve existing archive: ' + str(archive_path))
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.iterdir()):
            if path.is_file():
                archive.write(path, OUT.name + '/' + path.name)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert archive.read(OUT.name + '/' + NAME) == target.read_bytes()
    release = {key: report[key] for key in ('package', 'sha256', 'bytes', 'entries', 'hidden_paths', 'game_runtime_validated')}
    release.update(archive=str(archive_path), archive_sha256=sha(archive_path), validated_offline=True,
                   label='全时装覆盖＋转职屏蔽合并版 v02', instructions='安装说明.txt')
    save_json(ROOT / 'validation/fatfish_all_avatar_v02/release.json', release)
    print(json.dumps(release, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    build()
