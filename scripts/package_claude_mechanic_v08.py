"""Stage explicit mechanic IMG edits over frozen v07, then package that exact stage.

No image generation, character rebuilding, installation, or game launch. The
separate --package action consumes signed staged IMGs and never redraws art.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

from dnf_resources import ImgArchive, read_npk, write_v2
from gunner_props_build import write_shared_npk
from survey_gunner_effects import reader

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'design/claude_gunner/mechanic_v08.json'
BASE = ROOT / 'output/claude_gunner_v07/A_Claude_FGunner_v07.NPK'
BASE_SHA = 'd56c0a3cbe2beba5a82f29854db174286f0f4ad28662819c6d937f0cc9ae9483'
OUT = ROOT / 'output/claude_gunner_v08'
GAME = Path('C:/WeGameApps/地下城与勇士：创新世纪')
NATIVE = ROOT / 'output/Claude_Gunner_v02/native_frames'
PACKAGE = OUT / 'A_Claude_FGunner_v08.NPK'
STOPS = np.array([[0, 0, 0], [92, 28, 10], [222, 98, 44], [248, 158, 84], [255, 236, 208]], dtype=np.float32)
POS = np.array([0, .2, .52, .8, 1], dtype=np.float32)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def resolve(value):
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve(strict=True)


def workspace_output(value):
    path = resolve(value)
    if not path.is_relative_to((ROOT / 'output').resolve()):
        raise ValueError(f'Art inputs must be in project output: {path}')
    return path


def snapshot():
    paths = [GAME / 'ImagePacks2/A_Claude_FGunner_v07.NPK']
    paths += sorted((GAME / 'Video/Character/Cutscene_buf').glob('06_gunner_F_buf_*.bk2'))
    paths += sorted(NATIVE.glob('*.png'))
    paths += [ROOT / 'output/claude_buff_v07/preview/manifest.json',
              ROOT / 'output/claude_buff_v07/preview/portrait.bik']
    paths += sorted((ROOT / 'output/claude_buff_v07/preview/frames').glob('*.png'))
    return {str(path): sha(path) for path in paths if path.is_file()}


def read_payload(npk, internal_path):
    matches = [entry for entry in read_npk(npk) if entry['path'] == internal_path]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one official IMG {internal_path} in {npk}')
    row = matches[0]
    with npk.open('rb') as stream:
        stream.seek(row['offset'])
        payload = stream.read(row['length'])
    return row, payload


def metadata(frame):
    if 'link' in frame:
        return {'link': frame['link']}
    return {'x': frame['x'], 'y': frame['y'],
            'canvas_width': frame.get('cw', frame.get('canvas_width')),
            'canvas_height': frame.get('ch', frame.get('canvas_height'))}


def shape(frame):
    return frame.get('w', frame.get('width')), frame.get('h', frame.get('height'))


def pic(img, index):
    image = img.image(index)
    if image is not None:
        return image.convert('RGBA')
    return Image.new('RGBA', shape(img.resolve(index)))


def cool_mask(array):
    rgb = array[..., :3].astype(np.float32) / 255
    high, low = rgb.max(2), rgb.min(2)
    delta = high - low
    safe = np.maximum(delta, 1e-8)
    r, g, b = rgb.transpose(2, 0, 1)
    hue = np.where(high == r, ((g-b) / safe) % 6,
                   np.where(high == g, (b-r) / safe + 2, (r-g) / safe + 4)) / 6
    saturation = delta / np.maximum(high, 1e-8)
    return ((array[..., 3] > 0) & (high > .04) & (saturation > .12)
            & (hue >= .28) & (hue <= .94))


def orange_glow(image, mapping='cool'):
    """Only cool chromatic effect pixels change; alpha and warm/neutral art stay."""
    array = np.asarray(image.convert('RGBA')).copy()
    if mapping not in ('cool', 'energy'):
        raise ValueError('Glow mapping must be cool or energy')
    mask = cool_mask(array)
    rgb = array[..., :3].astype(np.float32) / 255
    if mapping == 'energy':
        high, low = rgb.max(2), rgb.min(2)
        mask = ((array[..., 3] > 0) & (high > .02)
                & ((high-low) / np.maximum(high, 1e-8) > .08))
    level = .65 * (rgb[..., 0] * .3 + rgb[..., 1] * .59 + rgb[..., 2] * .11) + .35 * rgb.max(2)
    mapped = np.stack([np.interp(level, POS, STOPS[:, k]) for k in range(3)], axis=2)
    array[..., :3][mask] = np.rint(mapped[mask]).astype(np.uint8)
    return Image.fromarray(array), int(mask.sum())


def validate_cfg(config_path):
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    if resolve(cfg['base_npk']) != BASE.resolve() or sha(BASE) != BASE_SHA:
        raise ValueError('This builder requires the approved frozen v07 base')
    if (ROOT / cfg['output']).resolve() != OUT.resolve():
        raise ValueError('Output must be output/claude_gunner_v08')
    specs = [('redraw', spec) for spec in cfg.get('redraw', [])] + [('glow', spec) for spec in cfg.get('glow', [])]
    if not specs or len(specs) > 256:
        raise ValueError('Explicit, bounded IMG edit list is required')
    paths = [spec['path'] for _, spec in specs]
    if len(paths) != len(set(paths)):
        raise ValueError('Each IMG may occur only once across redraw/glow')
    for path in paths:
        if ('..' in Path(path).parts or '\\' in path or not path.endswith('.img')
                or not path.startswith(('sprite/character/gunner/effect/', 'sprite/monster/'))):
            raise ValueError(f'Not a mechanic effect/monster IMG path: {path}')
    return cfg, specs


def comparison(folder, old, new, selected, fps=12):
    real = [k for k, frame in enumerate(old.frames) if 'link' not in frame and np.prod(shape(frame)) > 1]
    indices = sorted(set(selected)) if selected else real
    indices = [k for k in indices if k in real]
    if not indices:
        return {'frames': [], 'timing': 'No visible real frame'}
    if len(indices) > 12:
        indices = [indices[round(k*(len(indices)-1)/11)] for k in range(12)]
    sheet = Image.new('RGB', (640, len(indices)*250), '#252b34')
    draw = ImageDraw.Draw(sheet)
    for row, index in enumerate(indices):
        for column, img in enumerate((old, new)):
            image = pic(img, index)
            image.thumbnail((306, 222), Image.Resampling.NEAREST)
            sheet.paste(image, (column*320+(320-image.width)//2, row*250+25+(222-image.height)//2), image)
        draw.text((8, row*250+7), f'original k{index}', fill='white')
        draw.text((328, row*250+7), f'Claude k{index}', fill='white')
    sheet.save(folder / 'contact.jpg', quality=94)
    all_geometry = [old.resolve(k) for k in range(old.count)]
    x0 = min(f['x'] for f in all_geometry)
    y0 = min(f['y'] for f in all_geometry)
    x1 = max(f['x']+shape(f)[0] for f in all_geometry)
    y1 = max(f['y']+shape(f)[1] for f in all_geometry)
    size = max(1, x1-x0), max(1, y1-y0)
    if size[0]*size[1] <= 4_000_000 and old.count*min(size[0], 700)*min(size[1], 700) <= 50_000_000:
        for name, img in [('original', old), ('claude', new)]:
            animation = []
            for index in range(img.count):
                f = img.resolve(index)
                page = Image.new('RGBA', size)
                image = pic(img, index)
                page.alpha_composite(image, (f['x']-x0, f['y']-y0))
                page.thumbnail((700, 700), Image.Resampling.NEAREST)
                animation.append(page)
            animation[0].save(folder / f'{name}.webp', save_all=True, append_images=animation[1:],
                              duration=round(1000/fps), loop=0, lossless=True, exact=True)
    return {'frames': indices, 'preview_fps': fps,
            'timing': 'Uniform engineering preview; actual ANI/game timing unknown', 'world_box': [x0, y0, x1, y1]}


def stage(config_path=CONFIG, replace=False):
    cfg, specs = validate_cfg(config_path)
    stage_folder = OUT / 'stage'
    if PACKAGE.exists() or ((stage_folder / 'manifest.json').exists() and not replace):
        raise FileExistsError('Existing staged/published version; use --replace-stage only before publishing')
    before = snapshot()
    inputs = {str(config_path.resolve()): sha(config_path), str(BASE): BASE_SHA, str(Path(__file__)): sha(Path(__file__))}
    results = []
    base_paths = {row['path'] for row in read_npk(BASE)}
    for mode, spec in specs:
        source_npk = resolve(spec['source_npk'])
        inputs[str(source_npk)] = sha(source_npk)
        source_row, source_payload = read_payload(source_npk, spec['path'])
        official = reader(source_payload, source_row['version'])
        if spec['path'] in base_paths:
            row, payload = read_payload(BASE, spec['path'])
            inherited = reader(payload, row['version'])
        else:
            inherited = official
        if inherited.count != official.count:
            raise ValueError(f'Base and official frame counts differ: {spec["path"]}')
        for k, (a, b) in enumerate(zip(inherited.frames, official.frames, strict=True)):
            if metadata(a) != metadata(b) or ('link' not in a and shape(a) != shape(b)):
                raise ValueError(f'Base and official geometry differs: {spec["path"]} k{k}')
        overrides = {int(k): workspace_output(v) for k, v in spec.get('frames', {}).items()}
        if mode == 'redraw' and not overrides:
            raise ValueError(f'Redraw entry requires explicit frame PNGs: {spec["path"]}')
        if any(k < 0 or k >= inherited.count or 'link' in inherited.frames[k] for k in overrides):
            raise ValueError('Frame overrides must address real non-link frame indices')
        if mode == 'glow' and overrides:
            raise ValueError('A glow entry does not accept redraw PNGs')
        for path in overrides.values():
            inputs[str(path)] = sha(path)
        images, meta, frame_records = [], [], []
        edited_pixels = 0
        for k, frame in enumerate(inherited.frames):
            meta.append(metadata(frame))
            if 'link' in frame:
                images.append(Image.new('RGBA', (1, 1)))
                frame_records.append({'frame': k, 'link': frame['link']})
                continue
            image = pic(inherited, k)
            if k in overrides:
                image = Image.open(overrides[k]).convert('RGBA')
                if image.size != shape(frame):
                    raise ValueError(f'PNG dimension mismatch: {spec["path"]} k{k}: {image.size} != {shape(frame)}')
            elif mode == 'glow':
                image, count = orange_glow(image, spec.get('mode', 'cool'))
                edited_pixels += count
            images.append(image)
            frame_records.append({'frame': k, 'size': list(shape(frame)), 'metadata': metadata(frame),
                                  'png': str(overrides[k]) if k in overrides else None})
        if mode == 'glow' and not edited_pixels:
            raise ValueError(f'Glow entry contains no cool-color pixels: {spec["path"]}')
        payload = write_v2(images, meta, preserve_links=True)
        decoded = ImgArchive(payload)
        for k, frame in enumerate(decoded.frames):
            if metadata(frame) != meta[k] or ('link' not in frame and shape(frame) != shape(inherited.frames[k])):
                raise ValueError('Written frame geometry/link differs')
            if 'link' not in frame and np.prod(shape(frame)) > 1:
                expected, actual = np.asarray(images[k]), np.asarray(decoded.image(k))
                if not np.array_equal(actual, expected):
                    raise ValueError('Written V2 RGBA differs from staged image')
                if mode == 'glow' and not np.array_equal(actual[..., 3], np.asarray(pic(inherited, k))[..., 3]):
                    raise ValueError('Glow transformation changed alpha')
        key = hashlib.sha256(spec['path'].encode()).hexdigest()[:16]
        folder = stage_folder / 'imgs' / key
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / 'edited.img'
        dest.write_bytes(payload)
        preview = comparison(folder, official, decoded, list(overrides))
        result = {'path': spec['path'], 'label': spec.get('label', Path(spec['path']).stem), 'mode': mode,
                  'source_npk': str(source_npk), 'source_payload_sha256': hashlib.sha256(source_payload).hexdigest(),
                  'inherited_from': 'v07' if spec['path'] in base_paths else 'official',
                  'payload': str(dest.relative_to(ROOT)).replace('\\', '/'), 'payload_sha256': sha(dest),
                  'frame_count': decoded.count, 'frames': frame_records,
                  'redrawn_real_frames': len(overrides), 'glow_pixels_changed': edited_pixels,
                  'glow_mapping': spec.get('mode', 'cool') if mode == 'glow' else None,
                  'preview': preview}
        write_json(folder / 'frames.json', result)
        results.append(result)
    if snapshot() != before:
        raise ValueError('Protected game/buff/native files changed during staging')
    manifest = {'status': 'staged_for_visual_review', 'created_at': datetime.now().astimezone().isoformat(),
                'config': str(config_path.resolve()), 'base_npk': str(BASE), 'base_sha256': BASE_SHA,
                'inputs_sha256': inputs, 'protected_sha256': before, 'edits': results,
                'installed': False, 'ingame_verified': False,
                'scope': 'Explicit mechanic skill objects and cool glow layers only; no timing/mixing changes'}
    write_json(stage_folder / 'manifest.json', manifest)
    print(json.dumps({'staged': True, 'imgs': len(results), 'redraw_frames': sum(r['redrawn_real_frames'] for r in results),
                      'manifest': str(stage_folder / 'manifest.json'), 'published': False, 'installed': False}, ensure_ascii=False))
    return manifest


def package(config_path=CONFIG):
    validate_cfg(config_path)
    manifest_path = OUT / 'stage/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if PACKAGE.exists() or manifest['status'] != 'staged_for_visual_review':
        raise FileExistsError('Stage already published or package already exists')
    for filename, digest in manifest['inputs_sha256'].items():
        if sha(Path(filename)) != digest:
            raise ValueError(f'Staged input changed: {filename}')
    if snapshot() != manifest['protected_sha256']:
        raise ValueError('Protected game/buff/native files changed since staging')
    overlays = {}
    for edit in manifest['edits']:
        path = resolve(edit['payload'])
        if sha(path) != edit['payload_sha256']:
            raise ValueError(f'Staged IMG changed: {edit["path"]}')
        overlays[edit['path']] = path.read_bytes()
    original = BASE.read_bytes()
    rows = read_npk(BASE)
    if len(rows) != 7700:
        raise ValueError('Expected the 7700-entry v07 baseline')
    base_entries = {row['path']: original[row['offset']:row['offset']+row['length']] for row in rows}
    if len(base_entries) != len(rows):
        raise ValueError('Duplicate baseline paths')
    order = list(base_entries) + sorted(set(overlays)-set(base_entries))
    merged = base_entries | overlays
    temporary = PACKAGE.with_suffix('.NPK.building')
    if temporary.exists():
        raise FileExistsError('Unfinished build file requires inspection')
    temporary.write_bytes(write_shared_npk([(name, merged[name]) for name in order]))
    raw = temporary.read_bytes()
    written = read_npk(temporary)
    if [row['path'] for row in written] != order:
        raise ValueError('Packaged paths differ from signed stage')
    for row in written:
        if raw[row['offset']:row['offset']+row['length']] != merged[row['path']]:
            raise ValueError(f'Packaged IMG bytes differ: {row["path"]}')
    if snapshot() != manifest['protected_sha256'] or sha(BASE) != BASE_SHA:
        raise ValueError('A protected baseline changed while packaging')
    temporary.replace(PACKAGE)
    report = {'version': 8, 'package': str(PACKAGE), 'sha256': sha(PACKAGE), 'bytes': PACKAGE.stat().st_size,
              'entries': len(written), 'base_entries': len(rows), 'base_sha256': BASE_SHA,
              'added_paths': sorted(set(overlays)-set(base_entries)),
              'replaced_paths': sorted(set(overlays)&set(base_entries)),
              'unchanged_v07_payloads': len(set(base_entries)-set(overlays)),
              'all_old_paths_preserved': True, 'unchanged_payloads_byte_identical': True,
              'stage_manifest_sha256': sha(manifest_path), 'stage': str(manifest_path),
              'changed_img_count': len(overlays), 'actual_payload_readback_passed': True,
              'protected_files_unchanged': True, 'installed': False, 'ingame_verified': False,
              'preview_timing_is_engineering_only': True}
    write_json(OUT / 'validation.json', report)
    (OUT / (PACKAGE.name+'.sha256')).write_text(report['sha256']+'  '+PACKAGE.name+'\n', encoding='ascii')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', nargs='?', type=Path, default=CONFIG)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--stage', action='store_true')
    actions.add_argument('--package', action='store_true')
    parser.add_argument('--replace-stage', action='store_true')
    args = parser.parse_args()
    stage(args.config, args.replace_stage) if args.stage else package(args.config)
