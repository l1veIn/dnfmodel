"""Prepare only the deferred continuous-video overlays on published preview bases.

This entry point never submits paid requests, rebuilds static art/buffs, replaces
published inputs, packages NPKs or writes into the game. Run plan, then prepare;
review the complete-canvas previews before staging/packaging with the shared tool.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / 'output/validation/awakening_completion_2026-11-10/scope.json'
QUEUE = ROOT / 'design/illustration_completion_2026-11-10/remaining_videos.json'

PROJECTS = {
    'dragon': {
        'base': 'output/gpt_dragon_slayer_v04_preview/A_GPTDragon_FSlayer_v04_preview.NPK',
        'output': 'output/gpt_dragon_slayer_v04',
        'npk': 'A_GPTDragon_FSlayer_v04.NPK',
        'art': 'output/dragon_illustrations_v04/completion_2026-11-10',
        'config': 'design/gpt_dragon_slayer_v03/illustrations_v04.json',
        'title': 'GPT 龙娘 v04 · 五职业一觉与全部切入',
        'native': 'output/gpt_dragon_slayer_v03/native_frames',
        'buff': 'output/dragon_buff_v05/preview',
        'paths': {
            'dragon_darktempler_neo': ['(18)atsword_punishment', 'atsword_darktemplar_neo', 'atsword_punishment'],
            'dragon_demonslayer_neo': ['(18)atsword_demonslayer_neo', 'atsword_deicide', 'atsword_demonslayer_neo'],
            'dragon_blade_neo': ['(18)atsword_blade_neo', '(18)atsword_vendetta', 'atsword_blade_neo', 'atsword_vendetta'],
            'dragon_vagabond_neo': ['atsword_swordempress', 'neo_vagabond_cut_s'],
        },
        'counts': (12, 388),
        'coverage': {'awakening_paths': 12, 'cutin_paths': 15},
    },
    'whale': {
        'base': 'output/fatfish_whale_maid_v02_preview03/A_FatfishWhaleMaid_FMage_v02_preview03.NPK',
        'output': 'output/fatfish_whale_maid_v02',
        'npk': 'A_FatfishWhaleMaid_FMage_v02.NPK',
        'art': 'output/whale_illustrations_v02/completion_2026-11-10',
        'config': 'design/fatfish_whale_maid/illustrations_v02_complete.json',
        'title': '鲸鱼娘 v02 · 五职业一觉与全部切入',
        'native': 'output/fatfish_whale_maid/native_frames',
        'buff': 'output/whale_buff_v02/preview',
        'paths': {
            'whale_element': ['mage_elementalmaster_neo', 'mage_overmind'],
            'whale_summon': ['mage_eclipse', 'mage_summoner_neo'],
            'whale_witch': ['mage_geniewi', 'mage_witch_neo'],
            'whale_enchantress': ['mage_enchantress_neo', 'mage_hecate'],
        },
        'counts': (8, 243),
        'coverage': {'awakening_paths': 10, 'cutin_paths': 12},
    },
}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def selections(project):
    info = PROJECTS[project]
    scope = load(SCOPE)['projects'][project]
    lookup = {Path(row['path']).stem: row for row in scope['awakening'] + scope['cutin']}
    rows = [(clip, lookup[stem]) for clip, stems in info['paths'].items() for stem in stems]
    if (len(rows), sum(row['frames'] for _, row in rows)) != info['counts']:
        raise ValueError('Deferred path/frame count differs from the authoritative scope')
    return rows


def config_for(project):
    info = PROJECTS[project]
    rows = selections(project)
    native = ROOT / info['native']
    protected = [info['base'], info['buff'] + '/manifest.json',
                 info['buff'] + '/portrait.bik', info['buff'] + '/frames']
    if native.exists():
        protected.append(info['native'])
    overlays = []
    for clip, row in rows:
        folder = Path(info['art']) / 'frames' / Path(row['path']).stem
        overlays.append({
            'source_npk': row['source_npk'], 'path': row['path'],
            'frame_paths': [(folder / f'frame_{k:04d}.png').as_posix() for k in range(row['frames'])],
            'frame_mode': 'canvas', 'allow_geometry_change': True,
            'fit_to_canvas': False, 'preserve_empty_frames': True,
            'source_clip': clip, 'category': row['category'],
        })
    return {
        'title': info['title'], 'base_npk': info['base'],
        'base_sha256': sha(ROOT / info['base']), 'output': info['output'],
        'npk_name': info['npk'], 'scope': relative(SCOPE),
        'protect_paths': protected, 'overlays': overlays,
        'coverage': info['coverage'], 'pending_paths': [],
        'completion_status': 'explicit_plan_waiting_for_all_source_movies',
        'source_mapping': info['art'] + '/manifest.json',
        'note': 'Incremental candidate: all published-preview payloads inherited byte-for-byte; only the formerly deferred12/8 paths are added. Existing static art, closeup windows and independent buff are not rebuilt. No installation or in-game validation.',
    }


def guard(project):
    info = PROJECTS[project]
    if (ROOT / info['output'] / info['npk']).exists():
        raise FileExistsError('Published candidate is frozen; choose a new version')
    if (ROOT / info['output'] / 'stage/manifest.json').exists():
        raise FileExistsError('Signed stage already exists; do not mutate its inputs')
    if (ROOT / info['art'] / 'manifest.json').exists():
        raise FileExistsError('Prepared completion inputs are frozen; choose a new revision')


def plan(project):
    guard(project)
    config = config_for(project)
    save(ROOT / PROJECTS[project]['config'], config)
    return {'project': project, 'config': PROJECTS[project]['config'],
            'new_paths': len(config['overlays']), 'new_frames': PROJECTS[project]['counts'][1],
            'base': config['base_npk'], 'paid_calls': 0}


def geometry(row, index):
    frames = row['frame_geometry']
    seen = set()
    while frames[index].get('link') is not None:
        if index in seen:
            raise ValueError('Official frame link cycle')
        seen.add(index)
        index = frames[index]['link']
    return frames[index]['cw'], frames[index]['ch']


def checker(size):
    image = Image.new('RGBA', size, '#212938')
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], 12):
        for x in range(0, size[0], 12):
            if (x // 12 + y // 12) % 2:
                draw.rectangle((x, y, x + 11, y + 11), fill='#303a4a')
    return image


def prepare(project, only_clip=None, source_overrides=None):
    guard(project)
    info = PROJECTS[project]
    cfg = config_for(project)
    source_overrides = source_overrides or {}
    if set(source_overrides) - set(info['paths']):
        raise ValueError('Source override must address a known clip in this project')
    rows = selections(project)
    if only_clip:
        if only_clip not in info['paths']:
            raise ValueError('Clip does not belong to this project')
        rows = [(clip, row) for clip, row in rows if clip == only_clip]
    clips = {clip['id']: clip for clip in load(QUEUE)['clips']}
    sources = {}
    for clip_id in dict.fromkeys(clip for clip, _ in rows):
        clip = clips[clip_id]
        work = (ROOT / source_overrides.get(clip_id, clip['output'])).resolve()
        if not work.is_relative_to(ROOT / 'output'):
            raise ValueError('A collected source override must stay in project output')
        folder = work / 'frames'
        manifest = folder / 'manifest.json'
        data = load(manifest)
        paths = sorted(folder.glob('frame_*.png'))
        if data['clip_id'] != clip_id or len(paths) != data['frames'] or len(paths) < 8:
            raise ValueError(f'Need a genuine complete continuous movie for {clip_id}')
        hashes = [sha(path) for path in paths]
        if hashes != data['frame_sha256']:
            raise ValueError(f'Source frames changed from the cut manifest: {clip_id}')
        movie = work / 'video.mp4'
        if sha(movie) != data['source_video_sha256']:
            raise ValueError(f'Movie differs from cut frames: {clip_id}')
        sources[clip_id] = {
            'folder': folder, 'files': paths, 'manifest': data,
            'record': {'frames_manifest': relative(manifest), 'manifest_sha256': sha(manifest),
                       'source_movie': relative(movie), 'source_movie_sha256': sha(movie),
                       'actual_video': data['actual_video'], 'prepared_frames': len(paths),
                       'source_indices': data['source_indices'], 'frame_sha256': hashes},
        }
    output = ROOT / info['art']
    if only_clip:
        output = output / 'partial_review' / only_clip
        if (output / 'manifest.json').exists():
            return {'project': project, 'clip': only_clip, 'existing_review': relative(output / 'manifest.json')}
    review = output / 'review'
    review.mkdir(parents=True, exist_ok=True)
    cell = (320, 206)
    contact = Image.new('RGB', (cell[0] * 5, cell[1] * len(rows)), '#17202f')
    draw = ImageDraw.Draw(contact)
    records = []
    for row_number, (clip_id, row) in enumerate(rows):
        source = sources[clip_id]
        count = row['frames']
        picks = [round(k * (len(source['files']) - 1) / max(1, count - 1)) for k in range(count)]
        stem = Path(row['path']).stem
        target_folder = output / 'frames' / stem
        target_folder.mkdir(parents=True, exist_ok=True)
        selected = sorted(set(round(k * (count - 1) / 4) for k in range(5)))
        previews = []
        frame_records = []
        for k, index in enumerate(picks):
            with Image.open(source['files'][index]) as opened:
                image = opened.convert('RGBA')
            size = geometry(row, k)
            if project == 'dragon':
                page = image.resize(size, Image.Resampling.LANCZOS)
            else:
                fitted = ImageOps.contain(image, (round(size[0] * .95), round(size[1] * .95)), Image.Resampling.LANCZOS)
                page = Image.new('RGBA', size)
                page.alpha_composite(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
            target = target_folder / f'frame_{k:04d}.png'
            if target.exists():
                # Resume only an interrupted, un-signed preparation. Never
                # overwrite even these inputs; existing pixels must be exact.
                with Image.open(target) as previous:
                    if previous.convert('RGBA').tobytes() != page.tobytes() or previous.size != page.size:
                        raise FileExistsError(f'Prepared frame differs: {target}')
            else:
                page.save(target)
            frame_records.append({'frame': k, 'source_prepared_frame': index,
                                  'native_video_frame': source['manifest']['source_indices'][index],
                                  'canvas': list(size), 'png': relative(target), 'sha256': sha(target),
                                  'official_link': row['frame_geometry'][k].get('link'),
                                  'official_empty': k in row['empty_frames']})
            thumb = ImageOps.contain(page, (480, 300), Image.Resampling.LANCZOS)
            previews.append(thumb)
            if k in selected:
                n = selected.index(k)
                tile = checker((320, 180))
                small = ImageOps.contain(page, tile.size, Image.Resampling.LANCZOS)
                tile.alpha_composite(small, ((320 - small.width) // 2, (180 - small.height) // 2))
                xy = n * cell[0], row_number * cell[1]
                contact.paste(tile.convert('RGB'), (xy[0], xy[1] + 26))
                draw.text((xy[0] + 3, xy[1] + 5), f'{stem} k{k:02d}', fill='white')
        # Fixed complete canvas per frame; engineering10fps mirrors the shared
        # comparison player and is not a claim about the unknown game ANI.
        animation = review / f'{stem}.webp'
        previews[0].save(animation, save_all=True, append_images=previews[1:],
                         lossless=True, exact=True, duration=100, loop=0)
        records.append({'path': row['path'], 'source_clip': clip_id, 'frames': count,
                        'source_manifest': source['record']['frames_manifest'],
                        'source_manifest_sha256': source['record']['manifest_sha256'],
                        'whole_canvas_preview': relative(animation), 'all_frames': frame_records})
    contact.save(review / 'whole_canvas_contact.jpg', quality=94)
    if not only_clip:
        cfg['completion_status'] = 'all_requested_illustration_paths_prepared_for_workbench'
        cfg['video_source_overrides'] = source_overrides
        save(ROOT / info['config'], cfg)
    frozen_code = output / 'frozen_code/complete_hero_videos.py'
    frozen_code.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(__file__, frozen_code)
    frozen_config = output / 'package_config_snapshot.json'
    shutil.copyfile(ROOT / info['config'], frozen_config)
    manifest = {
        'created_at': datetime.now().astimezone().isoformat(), 'project': project,
        'status': 'partial_source_review_not_a_complete_package' if only_clip else 'prepared_full_canvas_review_before_stage', 'new_paths': len(records),
        'new_frames': sum(row['frames'] for _, row in rows), 'inherited_preview': info['base'],
        'inherited_preview_sha256': cfg['base_sha256'], 'config': info['config'],
        'config_sha256': sha(ROOT / info['config']),
        'config_snapshot': relative(frozen_config), 'config_snapshot_sha256': sha(frozen_config),
        'frozen_adapter': relative(frozen_code), 'adapter_sha256': sha(frozen_code),
        'scope_sha256': sha(SCOPE), 'sources': {key: value['record'] for key, value in sources.items()},
        'entries': records, 'whole_canvas_contact': relative(review / 'whole_canvas_contact.jpg'),
        'framing': 'Full official canvas resize' if project == 'dragon' else 'Constant95% contain safety inset on full official canvas',
        'preserved_by_package': ['official frame count', 'link descriptors', 'official canvas', 'official empty frames'],
        'old_payloads': 'All inherited preview entries are retained byte-for-byte; no completed art, closeup window, native character or buff rebuilt.',
        'preview_fps': 10, 'timing': 'Engineering estimate only; ANI/game timing unknown',
        'only_clip': only_clip, 'installed': False, 'ingame_verified': False, 'user_aesthetic_approval': False,
    }
    save(output / 'manifest.json', manifest)
    return {'project': project, 'paths': len(records), 'frames': manifest['new_frames'],
            'contact': manifest['whole_canvas_contact'], 'manifest': relative(output / 'manifest.json')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'prepare'])
    parser.add_argument('project', choices=['dragon', 'whale', 'all'])
    parser.add_argument('--only-clip', help='Prepare a source-review subset without changing the full package config')
    parser.add_argument('--source-override', action='append', default=[], metavar='CLIP=OUTPUT_FOLDER',
                        help='Read a separately authorized successful attempt without modifying the original task directory')
    args = parser.parse_args()
    projects = list(PROJECTS) if args.project == 'all' else [args.project]
    if args.only_clip and (args.action != 'prepare' or len(projects) != 1):
        parser.error('--only-clip requires prepare and one project')
    overrides = {}
    for value in args.source_override:
        if '=' not in value or not all(value.split('=', 1)):
            parser.error('--source-override needs CLIP=OUTPUT_FOLDER')
        clip, folder = value.split('=', 1)
        if clip in overrides:
            parser.error('Each clip may have only one source override')
        overrides[clip] = folder
    if overrides and (args.action != 'prepare' or len(projects) != 1):
        parser.error('--source-override requires prepare and one project')
    for project in projects:
        result = plan(project) if args.action == 'plan' else prepare(project, args.only_clip, overrides)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
