"""Apply the audited November 10 workspace cleanup, using explicit file lists.

No recursive deletion, game writes, source regeneration, or process shutdown.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/cleanup_2026-11-10'
PLAN = OUT / 'plan.json'


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def local(rel):
    raw = ROOT / rel
    path = raw.resolve(strict=True)
    assert path.is_relative_to(ROOT) and path.is_file() and not raw.is_symlink(), rel
    assert not path.stat().st_file_attributes & 0x400, 'reparse point: ' + rel
    return path


def info(path):
    path = Path(path)
    st = path.stat()
    return dict(path=str(path), bytes=st.st_size, mtime_ns=st.st_mtime_ns, sha256=digest(path))


def unchanged(row, path):
    st = path.stat()
    assert st.st_size == row['bytes'], str(path)
    if 'mtime_ns' in row:
        assert st.st_mtime_ns == row['mtime_ns'], str(path)
    if row.get('sha256'):
        assert digest(path) == row['sha256'], str(path)


def allowed(row):
    rel, kind = row['path'], row['kind']
    if kind == 'regenerable_preview_cache':
        return rel.startswith('kb/cache/')
    if kind == 'python_bytecode_cache':
        return '__pycache__' in Path(rel).parts and rel.endswith('.pyc')
    if kind == 'duplicate_distribution_zip':
        return rel.endswith('.zip')
    if kind == 'discarded_procedural_candidate':
        return rel.startswith('output/dragon_cutin_v07/candidate01/') and (rel.endswith('.png') or Path(rel).name == 'preview_native.webp')
    if kind == 'duplicate_preliminary_static_stage':
        return rel.startswith('output/interface_portraits_v01/package_v01/static_stage/') and Path(rel).suffix in {'.img', '.png'}
    return False


def prepare():
    assert not PLAN.exists(), 'Preserve the existing cleanup plan/receipt'
    inventory = read(OUT / 'inventory_before.json')
    zip_audit = read(OUT / 'zip_remove_candidates.json')
    derived = read(OUT / 'derived_audit.json')
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0'))
    rows = []
    for f in inventory['files']:
        kind = 'regenerable_preview_cache' if f['path'].startswith('kb/cache/') else 'python_bytecode_cache' if '__pycache__' in Path(f['path']).parts and f['path'].endswith('.pyc') else None
        if kind:
            rows.append(dict(f, kind=kind))
    for f in zip_audit['files']:
        assert f['matched_file_members'] == len(f['retained_members'])
        rows.append(dict(f, kind='duplicate_distribution_zip'))
    for key in ['discarded_procedural_candidate', 'duplicate_preliminary_static_stage']:
        rows.extend(dict(f, kind=key) for f in derived[key]['files'])
    assert len({f['path'] for f in rows}) == len(rows)
    deleted = {f['path'] for f in rows}
    survivor_checks = {}
    for row in rows:
        assert allowed(row) and row['path'] not in tracked
        p = local(row['path'])
        unchanged(row, p)
        row.setdefault('mtime_ns', p.stat().st_mtime_ns)
        for keeper in row.get('retained_members', []) + ([row['survivor']] if 'survivor' in row else []):
            assert keeper['path'] not in deleted
            survivor_checks[keeper['path']] = keeper
    for keeper in survivor_checks.values():
        unchanged(keeper, local(keeper['path']))

    # Current NPKs, all current native frames, installed targets, and complete
    # rollback sessions are independently pinned before any deletion.
    protected = set()
    for ident in ['claude_gunner', 'gpt_dragon_slayer_v03', 'fatfish_whale_maid']:
        patch = read(ROOT / 'design' / ident / 'patch.json')
        protected.update((ROOT / 'output' / patch['out'] / 'native_frames').glob('*.png'))
    for p in ['output/claude_gunner_v09/A_Claude_FGunner_v09.NPK', 'output/gpt_dragon_slayer_v07/A_GPTDragon_FSlayer_v07.NPK', 'output/fatfish_whale_maid_v06/A_FatfishWhaleMaid_FMage_v06.NPK', 'output/interface_portraits_v01/package_v01/A_AI_InterfacePortraits_v01.NPK']:
        protected.add(local(p))
    install_root = ROOT / 'output/game_installation_2026-11-10'
    protected.update(p for p in install_root.rglob('*') if p.is_file())
    receipt = read(install_root / '20261110_220045_657450_walk_cutin/installation.json')
    game_root = Path(receipt['game_root']).resolve()
    for row in receipt['files'] + receipt['unchanged_targets']:
        path = (game_root / row['relative']).resolve(strict=True)
        assert path.is_relative_to(game_root)
        protected.add(path)
    assert not any(p.is_relative_to(ROOT) and p.relative_to(ROOT).as_posix() in deleted for p in protected)
    protected_rows = [info(p) for p in sorted(protected)]
    proofs = [info(OUT / name) for name in ['inventory_before.json', 'zip_audit.json', 'zip_remove_candidates.json', 'derived_audit.json']]
    plan = dict(created_at=datetime.now().astimezone().isoformat(), root=str(ROOT), authorization='用户：这个项目的文件夹也膨胀的厉害，清理一下',
                installer_sha256=digest(__file__), proof_reports=proofs, files=rows, retained_file_checks=list(survivor_checks.values()),
                protected_files=protected_rows, delete_bytes=sum(f['bytes'] for f in rows),
                counts=dict(Counter(f['kind'] for f in rows)), destructive_scope='Only individually listed workspace files; no recursive directory operations or game writes')
    write(PLAN, plan)
    print(json.dumps(dict(plan=str(PLAN), files=len(rows), bytes=plan['delete_bytes'], GiB=round(plan['delete_bytes']/2**30,3), counts=plan['counts'], protected=len(protected_rows)), ensure_ascii=False))


def apply():
    plan = read(PLAN)
    assert Path(plan['root']).resolve() == ROOT and digest(__file__) == plan['installer_sha256']
    assert not (OUT / 'receipt.json').exists()
    for row in plan['proof_reports'] + plan['protected_files']:
        unchanged(row, Path(row['path']))
    for row in plan['retained_file_checks']:
        unchanged(row, local(row['path']))
    for row in plan['files']:
        assert allowed(row)
        unchanged(row, local(row['path']))
    completed = []
    with (OUT / 'deleted_files.jsonl').open('x', encoding='utf-8') as journal:
        for row in plan['files']:
            p = local(row['path'])
            unchanged(row, p)
            p.unlink()  # Exact resolved file only; no glob or recursive removal.
            completed.append({k: row[k] for k in ['path', 'bytes', 'kind']})
            journal.write(json.dumps(completed[-1], ensure_ascii=False) + '\n')
            journal.flush()
    for row in plan['protected_files']:
        unchanged(row, Path(row['path']))
    for row in plan['retained_file_checks']:
        unchanged(row, local(row['path']))
    assert not any((ROOT / row['path']).exists() for row in completed)
    receipt = dict(completed_at=datetime.now().astimezone().isoformat(), status='audited_cleanup_completed_protected_files_unchanged',
                   plan_sha256=digest(PLAN), deleted_files=len(completed), deleted_bytes=sum(r['bytes'] for r in completed),
                   counts=plan['counts'], protected_files_sha_size_mtime_exact=len(plan['protected_files']),
                   retained_duplicate_members_exact=len(plan['retained_file_checks']), game_written=False,
                   source_generation_or_package_rebuild=False, compression_pilot_saved_bytes=0,
                   note='Only reproducible caches, fully redundant ZIPs, rejected procedural candidate01 and exact copies in preliminary static_stage were removed. Source art, selected frames, all NPKs and rollback backups remain.')
    write(OUT / 'receipt.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'apply'])
    args = parser.parse_args()
    prepare() if args.action == 'prepare' else apply()
