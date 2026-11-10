"""Install the two approved walk/cutin repairs, retaining exact rollback backups.

Only four explicitly named project NPK paths may change. No game is started or
closed; frozen source assets, metadata, prior receipts and all buff files stay read-only.
"""
from __future__ import annotations

import argparse
import base64
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
BUFF = GAME / 'Video/Character/Cutscene_buf'
OUTPUT = ROOT / 'output/game_installation_2026-11-10'
PREVIOUS_RECEIPT = OUTPUT / '20261110_202133_459949/installation.json'
REPAIRS = {
    'dragon': dict(folder='gpt_dragon_slayer_v07', new='A_GPTDragon_FSlayer_v07.NPK',
                   after='2deed06dd68ee5d53cc6c62db39ad98d7c8ade7dba25dfc21ddbd6089cc615ae',
                   old='A_GPTDragon_FSlayer_v06.NPK', before='d9226050031e515abebf37282a3e041bae7a674d297cf4f19c162083c18bbb2c'),
    'whale': dict(folder='fatfish_whale_maid_v06', new='A_FatfishWhaleMaid_FMage_v06.NPK',
                  after='fb1b0d18208d5c058207f81c1c0355b2b7bd0ea3c372d8a9ae36fefdf07a8823',
                  old='A_FatfishWhaleMaid_FMage_v05.NPK', before='cfe42fe43fed8c714510de3efa1c365f641453a58a1f74afee05d2d218ce2d97'),
}


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def write(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.writing')
    assert not temporary.exists()
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    os.replace(temporary, path)


def closed():
    proc = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], check=True, capture_output=True, text=True, errors='replace')
    names = {r[0].casefold() for r in csv.reader(io.StringIO(proc.stdout)) if r}
    running = names & {'dnf.exe', 'dnfclient.exe', 'dnfchina.exe', 'dnf_x64.exe'}
    if running:
        raise RuntimeError('Exit DNF before installation; installer never closes it: ' + ', '.join(sorted(running)))


def mutable_path(relative):
    p = (GAME / relative).resolve()
    assert p.is_relative_to(GAME) and p.parent == NPK
    assert p.name in {v[k] for v in REPAIRS.values() for k in ('new', 'old')}
    return p


def readonly_path(relative):
    p = (GAME / relative).resolve()
    assert p.is_relative_to(GAME) and p.parent in (NPK, BUFF)
    assert p.suffix.casefold() in ('.npk', '.bk2')
    return p


def inventory(excluded):
    return {p.relative_to(GAME).as_posix(): [p.stat().st_size, p.stat().st_mtime_ns]
            for folder, pattern in ((NPK, '*.NPK'), (BUFF, '*.bk2'))
            for p in folder.glob(pattern) if p.relative_to(GAME).as_posix() not in excluded}


def validate_record(plan):
    session = Path(plan['session']).resolve(strict=True)
    assert session.is_relative_to(OUTPUT.resolve()) and Path(plan['game_root']).resolve() == GAME
    assert len(plan['files']) == len(plan['retire']) == 2 and len(plan['unchanged_targets']) == 17
    for row in plan['files'] + plan['retire']:
        assert mutable_path(row['relative']) == Path(row['target']).resolve()
    for project, spec in REPAIRS.items():
        new = next(r for r in plan['files'] if r['project'] == project)
        old = next(r for r in plan['retire'] if r['project'] == project)
        assert new['relative'] == 'ImagePacks2/' + spec['new'] and new['after_sha256'] == spec['after']
        assert new['before_sha256'] is None
        assert old['relative'] == 'ImagePacks2/' + spec['old'] and old['before_sha256'] == spec['before']
    return session


def check_unchanged(plan):
    excluded = {r['relative'] for r in plan['files'] + plan['retire']}
    assert inventory(excluded) == plan['untouched_inventory'], 'Other NPK/BK2 inventory changed'
    for row in plan['unchanged_targets']:
        p = readonly_path(row['relative'])
        assert [p.stat().st_size, p.stat().st_mtime_ns] == row['size_mtime']
        assert sha(p) == row['sha256'], 'Unrelated installed target changed: ' + row['relative']


def prepare():
    closed()
    assert NPK.is_dir() and BUFF.is_dir()
    session = OUTPUT / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_walk_cutin')
    session.mkdir(parents=True, exist_ok=False)
    files, retire = [], []
    for project, spec in REPAIRS.items():
        src = (ROOT / 'output' / spec['folder'] / spec['new']).resolve(strict=True)
        dst, old = mutable_path('ImagePacks2/' + spec['new']), mutable_path('ImagePacks2/' + spec['old'])
        assert src.is_relative_to(ROOT / 'output') and sha(src) == spec['after']
        assert not dst.exists() and old.is_file() and sha(old) == spec['before']
        files.append(dict(project=project, kind='character', action='install', source=str(src), target=str(dst),
                          relative=dst.relative_to(GAME).as_posix(), after_sha256=spec['after'], before_sha256=None, bytes=src.stat().st_size))
        retire.append(dict(project=project, target=str(old), relative=old.relative_to(GAME).as_posix(),
                           before_sha256=spec['before'], bytes=old.stat().st_size))
    old_names = {r['relative'] for r in retire}
    previous = read(PREVIOUS_RECEIPT)
    assert previous['installed'] and len(previous['files']) == 19
    unchanged = []
    for row in previous['files']:
        if row['relative'] in old_names:
            continue
        path = readonly_path(row['relative'])
        assert sha(path) == row['after_sha256']
        unchanged.append(dict(relative=row['relative'], sha256=row['after_sha256'], size_mtime=[path.stat().st_size, path.stat().st_mtime_ns]))
    assert len(unchanged) == 17
    expected_a = {r['old'] for r in REPAIRS.values()} | {'A_Claude_FGunner_v09.NPK', 'A_AI_InterfacePortraits_v01.NPK'}
    assert {p.name for p in NPK.glob('A_*.NPK')} == expected_a, 'Unexpected project NPKs need inspection'
    plan = dict(status='prepared', prepared_at=now(), authorization='用户：审核通过，打包放进游戏吧。',
                game_root=str(GAME), session=str(session), files=files, retire=retire, unchanged_targets=unchanged,
                previous_receipt=str(PREVIOUS_RECEIPT), installer_sha256=sha(__file__),
                untouched_inventory=inventory({r['relative'] for r in files + retire}))
    write(session / 'plan.json', plan)
    shutil.copy2(__file__, session / 'frozen_installer.py')
    print(json.dumps(dict(plan=str(session / 'plan.json'), install=2, retire=2, unchanged_targets=17,
                          other_inventory=len(plan['untouched_inventory'])), ensure_ascii=True))
    return session / 'plan.json'


def install(plan_path):
    plan = read(plan_path)
    session = validate_record(plan)
    closed()
    assert not (session / 'installation.json').exists() and sha(__file__) == plan['installer_sha256']
    for row in plan['files']:
        assert sha(row['source']) == row['after_sha256'] and not mutable_path(row['relative']).exists()
    for row in plan['retire']:
        assert sha(mutable_path(row['relative'])) == row['before_sha256']
    check_unchanged(plan)
    for row in plan['retire']:
        saved = (session / 'backup' / row['relative']).resolve()
        assert saved.is_relative_to(session / 'backup') and not saved.exists()
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(row['target'], saved)
        assert sha(saved) == row['before_sha256']
        row['backup'] = str(saved)
    recovery = dict(plan, status='prepared_recovery_before_mutation', installed=True, installed_at=now(), ingame_verified=False)
    write(session / 'recovery.json', recovery)
    expression = "& '" + sys.executable.replace("'", "''") + "' '" + str(Path(__file__).resolve()).replace("'", "''") + "' --restore '" + str(session / 'recovery.json').replace("'", "''") + "'; exit $LASTEXITCODE"
    encoded = base64.b64encode(expression.encode('utf-16-le')).decode('ascii')
    (session / 'restore_previous.cmd').write_bytes(('@echo off\r\npowershell.exe -NoProfile -EncodedCommand ' + encoded + '\r\npause\r\n').encode('ascii'))
    staged, committed, retired = [], [], []
    try:
        for row in plan['files']:
            target = mutable_path(row['relative'])
            temporary = target.with_name('.' + target.name + '.' + session.name + '.installing')
            assert temporary.parent == NPK and not temporary.exists()
            staged.append(temporary)
            shutil.copy2(row['source'], temporary)
            assert sha(temporary) == row['after_sha256']
        closed()
        for row in plan['retire']:
            target, backup = mutable_path(row['relative']), Path(row['backup']).resolve(strict=True)
            assert backup.is_relative_to(session / 'backup') and sha(target) == sha(backup) == row['before_sha256']
            os.replace(target, backup)
            retired.append(row)
        for row, temporary in zip(plan['files'], staged, strict=True):
            target = mutable_path(row['relative'])
            assert not target.exists()
            os.replace(temporary, target)
            committed.append(row)
            assert sha(target) == row['after_sha256']
        assert not any(mutable_path(r['relative']).exists() for r in plan['retire'])
        check_unchanged(plan)
    except BaseException:
        for row in reversed(committed):
            target = mutable_path(row['relative'])
            assert sha(target) == row['after_sha256']
            failed = session / 'failed_new_files' / row['relative']
            failed.parent.mkdir(parents=True, exist_ok=True)
            assert failed.resolve().is_relative_to(session) and not failed.exists()
            os.replace(target, failed)
        for row in retired:
            shutil.copy2(row['backup'], mutable_path(row['relative']))
        write(session / 'failed_install_rolled_back.json', dict(status='rolled_back_after_error', at=now()))
        raise
    finally:
        for temporary in staged:
            if temporary.exists():
                assert temporary.parent == NPK and temporary.name.endswith('.installing')
                temporary.unlink()
    assert not any(NPK.glob('*' + session.name + '*.installing'))
    record = dict(plan, status='installed_pending_user_game_test', installed=True, installed_at=now(),
                  ingame_verified=False, game_runtime_validated=False, game_started_or_stopped=False,
                  new_2_targets_match=True, old_2_npks_retired=True, unchanged_17_targets_match=True,
                  other_inventory_unchanged=True, no_temporary_files_remain=True)
    write(session / 'installation.json', record)
    print(json.dumps(dict(receipt=str(session / 'installation.json'), installed=2, retired=2, unchanged_targets=17,
                          other_inventory=len(plan['untouched_inventory'])), ensure_ascii=True))


def restore(receipt_path):
    record = read(receipt_path)
    session = validate_record(record)
    closed()
    assert record['installed'] and sha(__file__) == record['installer_sha256']
    for row in record['files']:
        assert sha(mutable_path(row['relative'])) == row['after_sha256']
    for row in record['retire']:
        backup = Path(row['backup']).resolve(strict=True)
        assert backup.is_relative_to(session / 'backup') and sha(backup) == row['before_sha256']
        assert not mutable_path(row['relative']).exists()
    check_unchanged(record)
    prepared, moved, restored = [], [], []
    try:
        for row in record['files']:
            removed = (session / 'restored_new_files' / row['relative']).resolve()
            assert removed.is_relative_to(session) and not removed.exists()
            removed.parent.mkdir(parents=True, exist_ok=True)
        for row in record['retire']:
            target = mutable_path(row['relative'])
            temporary = target.with_name('.' + target.name + '.' + session.name + '.restoring')
            assert temporary.parent == NPK and not temporary.exists()
            prepared.append((row, temporary))
            shutil.copy2(row['backup'], temporary)
            assert sha(temporary) == row['before_sha256']
        closed()
        for row in record['files']:
            target = mutable_path(row['relative'])
            assert sha(target) == row['after_sha256']
            os.replace(target, session / 'restored_new_files' / row['relative'])
            moved.append(row)
        for row, temporary in prepared:
            target = mutable_path(row['relative'])
            assert not target.exists()
            os.replace(temporary, target)
            restored.append(row)
            assert sha(target) == row['before_sha256']
        check_unchanged(record)
    except BaseException:
        for row in restored:
            target = mutable_path(row['relative'])
            assert sha(target) == row['before_sha256']
            failed = session / 'failed_restore_previous' / row['relative']
            failed.parent.mkdir(parents=True, exist_ok=True)
            assert failed.resolve().is_relative_to(session) and not failed.exists()
            os.replace(target, failed)
        for row in reversed(moved):
            target = mutable_path(row['relative'])
            assert not target.exists()
            os.replace(session / 'restored_new_files' / row['relative'], target)
            assert sha(target) == row['after_sha256']
        raise
    finally:
        for _, temporary in prepared:
            if temporary.exists():
                assert temporary.parent == NPK and temporary.name.endswith('.restoring')
                temporary.unlink()
    for name in ('installation.json', 'recovery.json'):
        path = session / name
        if path.exists():
            data = read(path)
            data.update(installed=False, restored_at=now(), status='restored_previous_two_character_versions')
            write(path, data)
    print(json.dumps(dict(restored=True, session=str(session)), ensure_ascii=True))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--install', type=Path)
    action.add_argument('--restore', type=Path)
    args = parser.parse_args()
    prepare() if args.prepare else install(args.install) if args.install else restore(args.restore)
