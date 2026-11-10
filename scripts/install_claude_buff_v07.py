"""Install the verified buff v07 movie with per-file backups and safe restore.

Never encodes/renders, changes character NPKs, or launches/closes the game.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'design/claude_gunner/buff_v07.json'
GAME = Path('C:/WeGameApps/地下城与勇士：创新世纪')
VIDEO = GAME / 'Video/Character'
NAMES = {f'06_gunner_F_buf_{name}.bk2' for name in ('launcher', 'meca', 'paramedic', 'ranger', 'spit')}
APPROVED_SOURCE_SHA = 'f2b27883758fb3630d28f4f760cba6bc67f090ddfd20163619cc31ba8a0ecf29'
APPROVED_MANIFEST_SHA = 'ea892f69dbaf0e301a4645fae28eed1e9205b2d48e0c95034ace93d32ff7a1b6'
PREVIOUS_V05_SHA = '33d119e8f0e8d76e4600d2ec605595f314bc007496ba169cbab656abad70501d'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def game_closed():
    tasks = subprocess.run(['tasklist'], capture_output=True, text=True, errors='replace', check=True).stdout.lower()
    if {'dnf.exe', 'dnfclient.exe', 'dnfchina.exe'}.intersection(tasks.split()):
        raise SystemExit('Exit DNF before changing buff movies. No game launch or process termination is performed.')


def targets(config):
    root = VIDEO.resolve(strict=True)
    values = []
    for relative in config['targets']:
        target = (root / relative).resolve(strict=True)
        assert target.parent == root / 'Cutscene_buf' and target.name in NAMES
        values.append((relative, target))
    assert len(values) == 5 and {p.name for _, p in values} == NAMES
    return values


def npk_hashes():
    return {str(p): sha(p) for p in sorted((GAME / 'ImagePacks2').glob('A_Claude_FGunner*.NPK'))}


def install():
    game_closed()
    config = json.loads(CONFIG.read_text('utf-8'))
    preview = (ROOT / config['output']).resolve(strict=True)
    assert preview == (ROOT / 'output/claude_buff_v07/preview').resolve(strict=True)
    folder = preview.parent
    report = json.loads((preview / 'encoding_report.json').read_text('utf-8'))
    source = preview / report['file']
    digest = sha(source)
    assert digest == APPROVED_SOURCE_SHA, 'Source differs from the user-approved v07 movie'
    assert sha(preview / 'manifest.json') == APPROVED_MANIFEST_SHA, 'Approved manifest changed'
    assert source.read_bytes()[:4] == b'BIKi'
    assert report['verified'] and digest == report['file_sha256']
    assert report['source_manifest_sha256'] == sha(preview / 'manifest.json')
    assert (report['frames'], report['width'], report['height'], report['fps']) == (19, 470, 668, 15)
    assert report['has_alpha'] and report['audio_streams'] == 0
    paths = targets(config)
    assert all(sha(target) == PREVIOUS_V05_SHA for _, target in paths), 'Current buff differs from installed v05; inspect before replacing'
    companion = npk_hashes()
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup = folder / 'installation_backup' / stamp
    backup.mkdir(parents=True, exist_ok=False)
    files = []
    # All five originals must be backed up and verified before the first replacement.
    for relative, target in paths:
        saved = backup / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        before = sha(target)
        shutil.copy2(target, saved)
        assert sha(saved) == before
        files.append(dict(relative=relative, target=str(target), backup=str(saved),
                          before_sha256=before, before_bytes=target.stat().st_size,
                          before_magic=target.read_bytes()[:20].decode('ascii', errors='replace'),
                          after_sha256=digest, bytes=source.stat().st_size))
    staged = []
    written = []
    try:
        for item in files:
            target = Path(item['target'])
            temp = target.with_name('.' + target.name + '.claude-v07.installing')
            assert not temp.exists(), 'A previous temporary install file needs inspection'
            shutil.copy2(source, temp)
            staged.append(temp)
            assert sha(temp) == digest
        game_closed()
        for item, temp in zip(files, staged, strict=True):
            target = Path(item['target'])
            assert sha(target) == item['before_sha256'], 'Target changed during backup'
            temp.replace(target)
            written.append(item)
            assert sha(target) == digest
    except BaseException:
        for item in written:
            target = Path(item['target'])
            temp = target.with_name('.' + target.name + '.claude-v07.restoring')
            assert not temp.exists()
            shutil.copy2(item['backup'], temp)
            assert sha(temp) == item['before_sha256']
            temp.replace(target)
        raise
    finally:
        for temp in staged:
            if temp.is_file():
                temp.unlink()  # Exact newly created temporary file, never recursive.
    assert companion == npk_hashes(), 'Character packages changed during buff installation'
    result = dict(installed=True, installed_at=datetime.now().isoformat(), version='v07',
                  previous_version='v05',
                  source=str(source), sha256=digest, game_root=str(VIDEO),
                  backup_directory=str(backup), files=files, frames=19, fps=15,
                  has_alpha=True, installed_targets_match_source=True,
                  character_npks_unchanged=companion, ingame_verified=False,
                  game_runtime_validated=False, authorization='User explicitly requested buff installation in chat.')
    write_json(folder / 'installation.json', result)
    write_json(backup / 'installation.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def restore(manifest):
    game_closed()
    manifest = manifest.resolve(strict=True)
    assert manifest.is_relative_to(ROOT / 'output')
    data = json.loads(manifest.read_text('utf-8'))
    assert len(data['files']) == 5
    for item in data['files']:
        target = Path(item['target']).resolve(strict=True)
        saved = Path(item['backup']).resolve(strict=True)
        assert target.parent == VIDEO.resolve() / 'Cutscene_buf' and target.name in NAMES
        assert saved.is_relative_to(ROOT / 'output') and sha(saved) == item['before_sha256']
        assert sha(target) in {item['after_sha256'], item['before_sha256']}, 'Target changed since installation; do not overwrite a game update or another patch'
    companion = npk_hashes()
    for item in data['files']:
        target = Path(item['target'])
        temp = target.with_name('.' + target.name + '.claude-v07.restoring')
        assert not temp.exists()
        shutil.copy2(item['backup'], temp)
        assert sha(temp) == item['before_sha256']
        temp.replace(target)
    assert companion == npk_hashes()
    data['installed'] = False
    data['restored_at'] = datetime.now().isoformat()
    write_json(manifest, data)
    print(json.dumps({'restored': True, 'files': [item['target'] for item in data['files']], 'record': str(manifest)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', type=Path, metavar='INSTALLATION_JSON')
    args = parser.parse_args()
    restore(args.restore) if args.restore else install()
