"""Install the seven frozen assets selected for the user's three-patch game test.

Only explicit game paths are touched; every replaced file is backed up first.
Does not launch, close, render, or encode anything.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GAME = Path('C:/WeGameApps/地下城与勇士：创新世纪').resolve()
NPK = GAME / 'ImagePacks2'
VIDEO = GAME / 'Video/Character'
OUTPUT = ROOT / 'output/game_installation_2026-11-10'
CHARACTERS = {
    'claude': ('claude_gunner_v09', 'A_Claude_FGunner_v09.NPK', '52eac85c41442d47fd1dffbd241dab6ab0fb12953f8a5e942e15e598c15b5b4f', 'A_Claude_FGunner_v07.NPK'),
    'dragon': ('gpt_dragon_slayer_v06', 'A_GPTDragon_FSlayer_v06.NPK', 'd9226050031e515abebf37282a3e041bae7a674d297cf4f19c162083c18bbb2c', 'A_GPTDragon_FSlayer_v03.NPK'),
    'whale': ('fatfish_whale_maid_v05', 'A_FatfishWhaleMaid_FMage_v05.NPK', 'cfe42fe43fed8c714510de3efa1c365f641453a58a1f74afee05d2d218ce2d97', 'A_FatfishWhaleMaid_FMage_v01.NPK'),
}
BUFFS = {
    'claude': ('claude_buff_v07', 'f2b27883758fb3630d28f4f760cba6bc67f090ddfd20163619cc31ba8a0ecf29', ['06_gunner_F_buf_' + n + '.bk2' for n in ['launcher', 'meca', 'paramedic', 'ranger', 'spit']]),
    'dragon': ('dragon_buff_v05', 'b75f6b9ee5a9b0e9348d4a27a3d91a350b9c81389493326a24c7ad6a093bbc3d', ['02_ghost_F_buf_' + n + '.bk2' for n in ['blade', 'darktemp', 'demon', 'sword', 'vega']]),
    'whale': ('whale_buff_v02', '9b7cc8aed6b5e861ec5ee53a974070128d9726603bf85cf35470542ddef8fdf4', ['08_mage_F_buf_' + n + '.bk2' for n in ['battlemage', 'element', 'enchant', 'summoner', 'witch']]),
}
ADDON = ('interface_portraits_v01/package_v01', 'A_AI_InterfacePortraits_v01.NPK', 'fa1dd1725e8031e64e4d6e8c8a78bf4525e2dd14912d14706f65e56c64880b9f')


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.writing')
    assert not temp.exists()
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def closed():
    tasks = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, errors='replace', check=True)
    names = {row[0].casefold() for row in csv.reader(io.StringIO(tasks.stdout)) if row}
    running = names & {'dnf.exe', 'dnfclient.exe', 'dnfchina.exe', 'dnf_x64.exe'}
    if running:
        raise RuntimeError('Exit the DNF client before installation: ' + ', '.join(sorted(running)))


def game_path(relative):
    path = (GAME / relative).resolve()
    assert path.is_relative_to(GAME)
    valid_npks = {row[1] for row in CHARACTERS.values()} | {row[3] for row in CHARACTERS.values()} | {ADDON[1]}
    valid_videos = {name for _, _, names in BUFFS.values() for name in names}
    assert (path.parent == NPK and path.name in valid_npks) or (path.parent == VIDEO / 'Cutscene_buf' and path.name in valid_videos)
    return path


def snapshot(excluded):
    return {p.relative_to(GAME).as_posix(): [p.stat().st_size, p.stat().st_mtime_ns]
            for folder, pattern in [(NPK, '*.NPK'), (VIDEO / 'Cutscene_buf', '*.bk2')]
            for p in folder.glob(pattern) if p.relative_to(GAME).as_posix() not in excluded}


def prepare():
    closed()
    assert NPK.is_dir() and VIDEO.is_dir()
    session = OUTPUT / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    session.mkdir(parents=True, exist_ok=False)
    rows = []
    for pid, (folder, name, digest, old) in CHARACTERS.items():
        rows.append(dict(project=pid, kind='character', source=str(ROOT / 'output' / folder / name), relative='ImagePacks2/' + name, after_sha256=digest))
    folder, name, digest = ADDON
    rows.append(dict(project='shared', kind='interface', source=str(ROOT / 'output' / folder / name), relative='ImagePacks2/' + name, after_sha256=digest))
    for pid, (folder, digest, names) in BUFFS.items():
        preview = ROOT / 'output' / folder / 'preview'
        report, manifest = read(preview / 'encoding_report.json'), read(preview / 'manifest.json')
        assert report['verified'] and report['source_manifest_sha256'] == sha(preview / 'manifest.json')
        assert report['file_sha256'] == digest
        assert (report['frames'], report['width'], report['height'], report['fps'], report['has_alpha'], report['audio_streams']) == (19, 470, 668, 15, True, 0)
        mapped = {t if isinstance(t, str) else t['relative_to_video_character'] for t in manifest['targets']}
        assert mapped == {'Cutscene_buf/' + name for name in names}
        official = {t['relative_to_video_character']: t['official_sha256'] for t in manifest['targets'] if isinstance(t, dict)}
        for name in names:
            relative = 'Video/Character/Cutscene_buf/' + name
            current = sha(game_path(relative))
            assert current == digest or current == official.get('Cutscene_buf/' + name), 'Unexpected existing buff: ' + relative
            rows.append(dict(project=pid, kind='buff', source=str(preview / 'portrait.bik'), relative=relative, after_sha256=digest))
    for row in rows:
        source = Path(row['source']).resolve(strict=True)
        assert source.is_relative_to(ROOT / 'output') and sha(source) == row['after_sha256']
        target = game_path(row['relative'])
        row.update(target=str(target), bytes=source.stat().st_size, before_sha256=sha(target) if target.exists() else None)
        row['action'] = 'unchanged' if row['before_sha256'] == row['after_sha256'] else 'install'
    old_rows = []
    for pid, (_, _, _, name) in CHARACTERS.items():
        path = game_path('ImagePacks2/' + name)
        assert path.is_file()
        old_rows.append(dict(project=pid, relative=path.relative_to(GAME).as_posix(), target=str(path), before_sha256=sha(path), bytes=path.stat().st_size))
    assert {p.name for p in NPK.glob('A_*.NPK')} == {r[3] for r in CHARACTERS.values()}, 'Inspect unexpected installed A_ packages first'
    excluded = {r['relative'] for r in rows + old_rows}
    plan = dict(status='prepared', prepared_at=now(), authorization='用户：完成之后把这三个补丁都实装到游戏，我测试一轮', game_root=str(GAME), session=str(session), files=rows, retire=old_rows, untouched_inventory=snapshot(excluded))
    write(session / 'plan.json', plan)
    print(json.dumps(dict(plan=str(session / 'plan.json'), install=sum(r['action'] == 'install' for r in rows), unchanged=sum(r['action'] == 'unchanged' for r in rows), retire=len(old_rows)), ensure_ascii=True))


def validate(plan):
    session = Path(plan['session']).resolve(strict=True)
    assert session.is_relative_to(OUTPUT.resolve()) and Path(plan['game_root']).resolve() == GAME
    assert len(plan['files']) == 19 and len(plan['retire']) == 3
    for row in plan['files'] + plan['retire']:
        assert game_path(row['relative']) == Path(row['target']).resolve()
    return session


def install(plan_path):
    plan = read(plan_path)
    session = validate(plan)
    closed()
    assert not (session / 'installation.json').exists()
    assert all(sha(r['source']) == r['after_sha256'] for r in plan['files'])
    for row in plan['files'] + plan['retire']:
        target = game_path(row['relative'])
        assert (sha(target) if target.exists() else None) == row['before_sha256'], 'Target changed after preparation'
    excluded = {r['relative'] for r in plan['files'] + plan['retire']}
    assert snapshot(excluded) == plan['untouched_inventory']
    changing = [r for r in plan['files'] if r['action'] == 'install']
    backups = plan['retire'] + [r for r in changing if r['before_sha256']]
    for row in backups:
        saved = session / 'backup' / row['relative']
        saved.parent.mkdir(parents=True, exist_ok=True)
        assert not saved.exists()
        shutil.copy2(row['target'], saved)
        assert sha(saved) == row['before_sha256']
        row['backup'] = str(saved)
    write(session / 'backed_up_plan.json', plan)
    # A usable recovery record and command exist before the first game mutation.
    recovery = dict(plan, status='prepared_recovery_record', installed=True,
                    installed_at=now(), ingame_verified=False, game_runtime_validated=False)
    write(session / 'recovery.json', recovery)
    cmd = '@echo off\r\n"' + sys.executable + '" "' + str(Path(__file__).resolve()) + '" --restore "' + str(session / 'recovery.json') + '"\r\npause\r\n'
    (session / 'restore_previous.cmd').write_text(cmd, encoding='utf-8')
    staged, committed, retired = [], [], []
    try:
        for row in changing:
            target = game_path(row['relative'])
            temp = target.with_name('.' + target.name + '.' + session.name + '.installing')
            assert not temp.exists() and temp.parent == target.parent
            staged.append(temp)
            shutil.copy2(row['source'], temp)
            assert sha(temp) == row['after_sha256']
        closed()
        for row in plan['retire']:
            target, saved = game_path(row['relative']), Path(row['backup'])
            assert sha(target) == row['before_sha256'] == sha(saved)
            os.replace(target, saved)
            retired.append(row)
        for row, temp in zip(changing, staged, strict=True):
            target = game_path(row['relative'])
            assert (sha(target) if target.exists() else None) == row['before_sha256']
            os.replace(temp, target)
            committed.append(row)
            assert sha(target) == row['after_sha256']
        assert all(sha(r['target']) == r['after_sha256'] for r in plan['files'])
        assert not any(Path(r['target']).exists() for r in retired)
        assert snapshot(excluded) == plan['untouched_inventory']
    except BaseException:
        for row in reversed(committed):
            target = game_path(row['relative'])
            assert sha(target) == row['after_sha256']
            if row['before_sha256']:
                shutil.copy2(row['backup'], target)
            else:
                removed = session / 'failed_new_files' / row['relative']
                removed.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, removed)
        for row in retired:
            shutil.copy2(row['backup'], game_path(row['relative']))
        raise
    finally:
        for temp in staged:
            if temp.exists():
                assert temp.parent in {NPK, VIDEO / 'Cutscene_buf'} and temp.name.endswith('.installing')
                temp.unlink()
    record = dict(plan, status='installed_pending_user_game_test', installed=True, installed_at=now(), ingame_verified=False, game_runtime_validated=False, game_started_by_installer=False, all_19_targets_match=True, old_3_npks_retired=True)
    write(session / 'installation.json', record)
    write(OUTPUT / 'latest.json', dict(installation=str(session / 'installation.json'), installed_at=record['installed_at']))
    for pid, (folder, _, _, _) in CHARACTERS.items():
        write(ROOT / 'output' / folder / 'installation.json', dict(installed=True, installed_at=record['installed_at'], project=pid, game_root=str(GAME), batch_receipt=str(session / 'installation.json'), files=[r for r in plan['files'] if r['project'] == pid and r['kind'] == 'character'], ingame_verified=False))
    for pid in ['dragon', 'whale']:
        folder, digest, _ = BUFFS[pid]
        rows = [dict(r, relative=r['relative'].removeprefix('Video/Character/')) for r in plan['files'] if r['project'] == pid and r['kind'] == 'buff']
        write(ROOT / 'output' / folder / 'installation.json', dict(installed=True, installed_at=record['installed_at'], source=rows[0]['source'], sha256=digest, game_root=str(VIDEO), files=rows, batch_receipt=str(session / 'installation.json'), ingame_verified=False))
    print(json.dumps(dict(installed=True, receipt=str(session / 'installation.json'), installed_files=len(changing), unchanged_files=len(plan['files']) - len(changing), retired_npks=len(retired), verified_targets=len(plan['files'])), ensure_ascii=True))


def restore(receipt_path):
    record = read(receipt_path)
    session = validate(record)
    closed()
    assert record['installed'] is True
    changing = [r for r in record['files'] if r['action'] == 'install']
    for row in changing:
        assert sha(game_path(row['relative'])) == row['after_sha256'], 'Game update or another patch changed a target; inspect before restoring'
    for row in record['retire'] + [r for r in changing if r['before_sha256']]:
        saved = Path(row['backup']).resolve(strict=True)
        assert saved.is_relative_to(session / 'backup') and sha(saved) == row['before_sha256']
    assert all(not game_path(r['relative']).exists() for r in record['retire'])
    previous = [r for r in changing if r['before_sha256']] + record['retire']
    prepared, moved, restored = [], [], []
    try:
        for row in changing:
            removed = session / 'restored_new_files' / row['relative']
            removed.parent.mkdir(parents=True, exist_ok=True)
            assert not removed.exists(), 'An earlier restore needs inspection'
        # Stage and verify all original files before removing any installed one.
        for row in previous:
            target = game_path(row['relative'])
            temp = target.with_name('.' + target.name + '.' + session.name + '.restoring')
            assert not temp.exists() and temp.parent == target.parent
            prepared.append((row, temp))
            shutil.copy2(row['backup'], temp)
            assert sha(temp) == row['before_sha256']
        closed()
        for row in changing:
            target = game_path(row['relative'])
            assert sha(target) == row['after_sha256']
            os.replace(target, session / 'restored_new_files' / row['relative'])
            moved.append(row)
        for row, temp in prepared:
            target = game_path(row['relative'])
            assert not target.exists()
            os.replace(temp, target)
            restored.append(row)
            assert sha(target) == row['before_sha256']
    except BaseException:
        # Return to the complete installed state, making a restore retry possible.
        for row in restored:
            if row in record['retire']:
                target = game_path(row['relative'])
                assert sha(target) == row['before_sha256']
                failed = session / 'failed_restore_previous' / row['relative']
                failed.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, failed)
        for row in reversed(moved):
            target = game_path(row['relative'])
            current = sha(target) if target.exists() else None
            assert current in {None, row['before_sha256']}
            os.replace(session / 'restored_new_files' / row['relative'], target)
            assert sha(target) == row['after_sha256']
        raise
    finally:
        for _, temp in prepared:
            if temp.exists():
                assert temp.parent in {NPK, VIDEO / 'Cutscene_buf'} and temp.name.endswith('.restoring')
                temp.unlink()
    record.update(installed=False, restored_at=now())
    write(receipt_path, record)
    for name in ['installation.json', 'recovery.json']:
        path = session / name
        if path.exists() and path.resolve() != Path(receipt_path).resolve():
            data = read(path)
            data.update(installed=False, restored_at=record['restored_at'])
            write(path, data)
    for folder in [r[0] for r in CHARACTERS.values()] + [BUFFS[pid][0] for pid in ['dragon', 'whale']]:
        path = ROOT / 'output' / folder / 'installation.json'
        if path.exists():
            data = read(path)
            if data.get('batch_receipt') == str(session / 'installation.json'):
                data.update(installed=False, restored_at=record['restored_at'])
                write(path, data)
    print(json.dumps(dict(restored=True, receipt=str(receipt_path)), ensure_ascii=True))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--prepare', action='store_true')
    actions.add_argument('--install', type=Path)
    actions.add_argument('--restore', type=Path)
    args = parser.parse_args()
    prepare() if args.prepare else install(args.install) if args.install else restore(args.restore)
