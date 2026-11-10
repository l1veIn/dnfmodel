"""Package the approved native character frames over v06's unchanged extras.

Build/read-back first, then --install. No rendering, official-package writes,
Video changes or game launch. Installation archives only this project's NPKs.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
os.environ['PATCH_ID'] = 'claude_gunner'
sys.path.insert(0, str(ROOT / '.claude/skills/dnf-character-patch/scripts'))
from kit.release import body_img, write_shared_npk, preview
from kit.config import GAME, P
from dnf_resources import ImgArchive, read_npk

BASE = ROOT / 'output/claude_gunner_v06/A_Claude_FGunner_v06.NPK'
BASE_SHA = '2d4a198167b0c5ed54f064c0dcd9f39b48f9affe884b3a2d34f402934988e940'
OUT = ROOT / 'output/claude_gunner_v07'
PACKAGE = OUT / 'A_Claude_FGunner_v07.NPK'
SKIN = 'sprite/character/gunner/atequipment/avatar/skin/'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def native_hashes():
    return {f'{i:04d}.png': sha(P.out / f'native_frames/{i:04d}.png') for i in range(P.frames)}


def build():
    assert P.frames == 143 and sha(BASE) == BASE_SHA, 'Unexpected v06 base'
    OUT.mkdir(exist_ok=True)
    before = native_hashes()
    body, unique = body_img()
    archive = ImgArchive(body)
    assert archive.count == 143
    original = BASE.read_bytes()
    rows = read_npk(BASE)
    assert len(rows) == 7700 and sum(r['path'].startswith(SKIN) for r in rows) == 37
    entries = [(r['path'], body if r['path'].startswith(SKIN) else
                original[r['offset']:r['offset'] + r['length']]) for r in rows]
    assert len(set(name for name, _ in entries)) == 7700
    temporary = PACKAGE.with_suffix('.NPK.building')
    temporary.write_bytes(write_shared_npk(entries))
    written = read_npk(temporary)
    raw = temporary.read_bytes()
    assert [r['path'] for r in rows] == [r['path'] for r in written]
    preserved = 0
    for old, new in zip(rows, written, strict=True):
        payload = raw[new['offset']:new['offset'] + new['length']]
        if old['path'].startswith(SKIN):
            assert payload == body
        else:
            assert payload == original[old['offset']:old['offset'] + old['length']], old['path']
            preserved += 1
    skin = next(r for r in written if r['path'].startswith(SKIN))
    decoded = ImgArchive(raw[skin['offset']:skin['offset'] + skin['length']])
    for i in range(143):
        info = decoded.resolve(i)
        world = Image.new('RGBA', (500, 500))
        world.paste(decoded.image(i), (info['x'], info['y']))
        expected = np.asarray(Image.open(P.out / f'native_frames/{i:04d}.png').convert('RGBA'))
        actual = np.asarray(world)
        assert np.array_equal(actual[..., 3], expected[..., 3]), i
        visible = expected[..., 3] > 0
        assert np.array_equal(actual[visible], expected[visible]), i
    assert native_hashes() == before, 'Native frames changed during build'
    temporary.replace(PACKAGE)
    report = dict(package=str(PACKAGE), version=7, sha256=sha(PACKAGE),
                  bytes=PACKAGE.stat().st_size, entries=7700, skin_paths_updated=37,
                  unchanged_other_payloads=preserved, preserved_extra_paths=285,
                  frames=143, unique_frames=unique, decoded_frames_match_rendered_pngs=True,
                  alpha_and_visible_rgba_match=True, native_files_unchanged=True,
                  native_sha256=before, base_package=str(BASE), base_sha256=BASE_SHA,
                  coverage={'avatar':7359, 'growtype':56, 'extras':285},
                  game_runtime_validated=False, video_directory_changed=False)
    write_json(OUT / 'validation.json', report)
    (OUT / (PACKAGE.name + '.sha256')).write_text(report['sha256'] + '  ' + PACKAGE.name + '\n', 'ascii')
    preview()  # Reads the approved frames; does not invoke any rendering/final pass.
    shutil.copytree(P.out / 'preview', OUT / 'preview', dirs_exist_ok=True)
    page = OUT / 'preview/index.html'
    page.write_text(page.read_text('utf-8').replace('v02', 'v07'), 'utf-8')
    assert native_hashes() == before, 'Native frames changed during preview export'
    notes = ('女枪手 Claude 大小姐 v07 · 动作修复版\n\n'
             '采用用户已确认的143张人物帧，保留v06武器、机器人、切入图与技能内容。\n'
             '人物动作包括固定待机脚、上弹、拍手、收手、走路、持枪交叉及按用户三视图修正的背面。\n'
             '安装：退出游戏，把A_Claude_FGunner_v07.NPK放入ImagePacks2，勿与旧版同装。\n'
             '卸载：退出游戏后移走v07；回退：放回安装备份目录的v06。\n'
             '未启动游戏，实机表现由用户测试；武器工程预览的遮挡不代表游戏实际顺序。\n'
             'buff视频独立于这个NPK，本包未写入Video目录。\n'
             '角色是民间二创，非Anthropic官方形象，原作者/授权未核实，仅自用。\n\n'
             'SHA256：' + report['sha256'] + '\n')
    (OUT / '安装说明.txt').write_text(notes, 'utf-8')
    doc = ROOT / 'docs/claude_gunner_v07.md'
    with zipfile.ZipFile(OUT.parent / 'claude_gunner_v07.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for path in (PACKAGE, OUT / '安装说明.txt', OUT / 'validation.json', doc,
                     OUT / 'preview/index.html', OUT / 'preview/hero_compare.gif'):
            if path.is_file():
                relative = path.relative_to(OUT) if path.is_relative_to(OUT) else Path(path.name)
                z.write(path, 'claude_gunner_v07/' + relative.as_posix())
    with zipfile.ZipFile(OUT.parent / 'claude_gunner_v07.zip') as z:
        assert z.testzip() is None
    print(json.dumps({k:v for k,v in report.items() if k != 'native_sha256'}, ensure_ascii=False, indent=2))


def check_game_closed():
    tasks = subprocess.run(['tasklist'], capture_output=True, text=True, errors='replace', check=True).stdout.lower()
    if 'dnf.exe' in tasks.split():
        raise SystemExit('Game is running; exit DNF before installation. No game files changed.')


def install():
    check_game_closed()
    report = json.loads((OUT / 'validation.json').read_text('utf-8'))
    assert sha(PACKAGE) == report['sha256']
    assert native_hashes() == report['native_sha256'], 'Approved frames changed since packaging'
    game = GAME.resolve(strict=True)
    target = game / PACKAGE.name
    assert target.parent == game and PACKAGE.name.startswith('A_Claude_FGunner_v')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup = OUT / 'install_backup' / stamp
    backup.mkdir(parents=True, exist_ok=False)
    old_paths = sorted(game.glob('A_Claude_FGunner*.NPK'))
    old = []
    # Copy/verify every backup before moving any old package out of the game.
    for path in old_paths:
        assert path.is_file() and path.resolve().parent == game
        saved = backup / path.name
        shutil.copy2(path, saved)
        digest = sha(path)
        assert sha(saved) == digest
        old.append(dict(original=str(path), backup=str(saved), sha256=digest, bytes=path.stat().st_size))
    temp = game / ('.' + PACKAGE.name + '.installing')
    assert not temp.exists(), 'Unfinished installation file already exists'
    shutil.copy2(PACKAGE, temp)
    assert sha(temp) == report['sha256']
    check_game_closed()
    moved = []
    new_installed = False
    try:
        for path in old_paths:
            # Nonrecursive moves to unique, verified workspace paths; official NPKs untouched.
            holding = backup / (path.name + '.original')
            shutil.move(str(path), str(holding))
            moved.append((path, holding))
        temp.replace(target)
        new_installed = True
        assert sha(target) == report['sha256']
    except BaseException:
        if new_installed and target.exists():
            shutil.move(str(target), str(backup / (PACKAGE.name + '.failed')))
        for path, holding in moved:
            shutil.move(str(holding), str(path))
        raise
    # Retain verified .NPK backups and original moved copies for simple recovery.
    result = dict(installed=True, installed_at=datetime.now().isoformat(), package=str(PACKAGE),
                  destination=str(target), sha256=sha(target), bytes=target.stat().st_size,
                  source_and_installed_hash_match=True, previous_packages=old,
                  backup_directory=str(backup), active_project_npks=[p.name for p in game.glob('A_Claude_FGunner*.NPK')],
                  game_runtime_validated=False, official_packages_changed=False, video_directory_changed=False)
    assert result['active_project_npks'] == [PACKAGE.name]
    write_json(OUT / 'installation.json', result)
    write_json(backup / 'installation.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    install() if args.install else build()
