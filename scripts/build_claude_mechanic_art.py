"""Prepare exact mechanic reference atlases and fit separately generated art.

Only this new v08 art workspace is writable. Never generates art, pays for a
service, modifies official resources, packages a NPK, or installs anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from dnf_resources import read_npk
from gunner_props import cut_key, fit
from survey_gunner_effects import GAME, reader

OUT = ROOT / 'output/claude_mechanic_v08'
REFS = OUT / 'refs'
FRAMES = OUT / 'frames'
SIZE = (1536, 1024)
COLS, ROWS, CELL = 6, 4, 256
FACTORY = 'sprite_character_gunner_effect_sparrowfactory'
RX78 = 'sprite_monster_gunner_rx78'
SPECS = {
    'factory_body': [(FACTORY, 'factory_body')],
    'rx78_main': [(RX78, 'rx78')],
    'rx78_move': [(RX78, s) for s in ('rx78drop', 'rx78dropred', 'rx78jump', 'rx78walk')],
    'fighting_spirit': [('sprite_monster_gunner_fightingspirit', 'robot')],
    'rx60': [('sprite_character_gunner_effect_rx-60', s) for s in ('body', 'rx60jump')],
    'factory_drones': [(FACTORY, s) for s in ('sparrow_body', 'newsparrow_body')],
    'factory_piece': [(FACTORY, 'factory_piece')],
    'factory_solar_angles': [(FACTORY, 'sparrowfactoryvpformationn2')],
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def require_unfrozen():
    if (FRAMES / 'art_freeze.json').exists():
        raise FileExistsError('v08 art is reviewed and frozen; choose a new version instead of overwriting it')


def load_asset(pack, stem):
    path = GAME / (pack + '.NPK')
    entries = [e for e in read_npk(path) if Path(e['path']).stem == stem]
    if len(entries) != 1:
        raise ValueError(f'Expected unique official IMG: {pack}/{stem}')
    entry = entries[0]
    with path.open('rb') as stream:
        stream.seek(entry['offset'])
        data = stream.read(entry['length'])
    return reader(data, entry['version']), entry, hashlib.sha256(data).hexdigest()


def frame_path(base, img_path, k):
    return base / Path(img_path).with_suffix('') / f'frame_{k:04d}.png'


def make_refs(page):
    require_unfrozen()
    assets, cells, by_drawing = [], [], {}
    for pack, stem in SPECS[page]:
        source, entry, digest = load_asset(pack, stem)
        asset = {'source_pack': pack, 'img': entry['path'], 'version': entry['version'],
                 'source_payload_sha256': digest, 'frame_count': source.count,
                 'metadata': source.frames, 'frame_to_cell': []}
        for k in range(source.count):
            image = source.image(k)
            if image is None:
                image = Image.new('RGBA', (1, 1))
            image = image.convert('RGBA')
            original = frame_path(REFS / 'source_frames', entry['path'], k)
            original.parent.mkdir(parents=True, exist_ok=True)
            image.save(original)
            key = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
            if key not in by_drawing:
                by_drawing[key] = len(cells)
                cells.append({'cell': len(cells), 'original_size': list(image.size),
                              'original_png': relative(original), 'rgba_sha256': key,
                              'uses': []})
            index = by_drawing[key]
            cells[index]['uses'].append({'path': entry['path'], 'frame': k})
            asset['frame_to_cell'].append(index)
        assets.append(asset)
    if len(cells) > COLS * ROWS:
        raise ValueError(f'Too many unique cells on {page}; split it deliberately')
    # Keep a common scale across a page, preserving relative pose dimensions.
    largest = max(max(c['original_size']) for c in cells)
    scale = min(5, 196 / largest)
    atlas = Image.new('RGBA', SIZE)
    annotated = atlas.copy()
    pen = ImageDraw.Draw(annotated)
    for item in cells:
        k = item['cell']; x, y = k % COLS * CELL, k // COLS * CELL
        content = [x + 18, y + 34, x + CELL - 18, y + CELL - 14]
        item['cell_box'] = [x, y, x + CELL, y + CELL]
        item['content_box'] = content
        image = Image.open(ROOT / item['original_png']).convert('RGBA')
        shown = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.NEAREST)
        pos = (x + (CELL - shown.width) // 2, y + 34 + (208 - shown.height) // 2)
        atlas.alpha_composite(shown, pos)
        annotated.alpha_composite(shown, pos)
        use = item['uses'][0]
        pen.text((x + 18, y + 10), f'{k:02d}  {Path(use["path"]).stem} k{use["frame"]}', fill=(160, 168, 180, 255))
    folder = REFS / page
    folder.mkdir(parents=True, exist_ok=True)
    atlas.save(folder / 'atlas.png')
    annotated.save(folder / 'atlas_labeled.png')
    data = {'page': page, 'size': list(SIZE), 'cols': COLS, 'rows': ROWS, 'cell_size': CELL,
            'source_scale': scale, 'unique_cells': len(cells), 'blank_cells': list(range(len(cells), COLS * ROWS)),
            'atlas': relative(folder / 'atlas.png'), 'labeled_atlas': relative(folder / 'atlas_labeled.png'),
            'cells': cells, 'assets': assets,
            'deduplication': 'Only identical image size and exact RGBA bytes merge; no approximate pose or color merging.',
            'generation_instruction': 'Redraw only occupied cells, preserve positions/poses and all blank cells. No labels, grid, floor, or extra objects. Transparent background.'}
    save_json(folder / 'refs.json', data)
    print(json.dumps({'page': page, 'unique_cells': len(cells), 'total_source_frames': sum(a['frame_count'] for a in assets),
                      'atlas': data['atlas'], 'blank_cells': data['blank_cells']}, ensure_ascii=False), flush=True)
    return data


def comparison(page, cells, made):
    # Original / generated / red original-contour overlay for every unique cell.
    cols = min(6, len(cells)); w, h = 200, 215
    board = Image.new('RGB', (cols * w, ((len(cells) + cols - 1) // cols) * h * 3), '#252b35')
    pen = ImageDraw.Draw(board)
    for item in cells:
        k = item['cell']; old = Image.open(ROOT / item['original_png']).convert('RGBA'); new = made[k]
        mask = np.asarray(old)[..., 3] > 60
        # Four-neighbour erosion leaves a thin red line at the old silhouette.
        interior = mask.copy()
        interior[1:] &= mask[:-1]; interior[:-1] &= mask[1:]
        interior[:, 1:] &= mask[:, :-1]; interior[:, :-1] &= mask[:, 1:]
        overlay = new.copy(); a = np.asarray(overlay).copy(); a[mask & ~interior] = (255, 38, 54, 255)
        overlay = Image.fromarray(a)
        scale = min(3, (w - 12) / max(old.size))
        for row, image in enumerate((old, new, overlay)):
            shown = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.NEAREST)
            x = k % cols * w + (w - shown.width) // 2
            top = k // cols * h * 3 + row * h
            y = top + 24 + (h - 24 - shown.height) // 2
            board.paste(shown, (x, y), shown)
            pen.text((k % cols * w + 5, top + 5), f'{k:02d} ' + ('ORIGINAL', 'CLAUDE', 'RED = OLD OUTLINE')[row], fill='white')
    path = REFS / 'qa' / f'{page}_comparison.png'
    path.parent.mkdir(parents=True, exist_ok=True); board.save(path)
    return path


def fit_page(page, raw_path, single=False):
    require_unfrozen()
    refs_path = REFS / page / 'refs.json'
    data = json.loads(refs_path.read_text('utf-8')) if refs_path.exists() else make_refs(page)
    raw_path = raw_path.resolve(strict=True)
    if not raw_path.is_relative_to(OUT / 'raw'):
        raise ValueError('Generated art must be in the v08 raw directory')
    raw = cut_key(raw_path).convert('RGBA')
    # The generator occasionally adds a low-alpha room-sized aura. It is not
    # physical robot art; remove it before computing cell foreground bounds.
    pixels = np.asarray(raw).copy()
    pixels[pixels[..., 3] < 64] = 0
    raw = Image.fromarray(pixels)
    made, stats = {}, []
    for item in data['cells']:
        if single:
            if len(data['cells']) != 1:
                raise ValueError('Single artwork requires exactly one reference cell')
            crop = raw
        else:
            # Atlas aspect/dimensions may be resampled by the generator. Use
            # independent normalized x/y mapping, never hard-coded raw pixels.
            box = item['content_box']
            crop = raw.crop(tuple(round(v * (raw.width / SIZE[0] if j % 2 == 0 else raw.height / SIZE[1])) for j, v in enumerate(box)))
        old = Image.open(ROOT / item['original_png']).convert('RGBA')
        generated, score = fit(crop, old)
        if not generated.getbbox():
            raise ValueError(f'Empty output at {page} cell {item["cell"]}')
        made[item['cell']] = generated
        stats.append({'cell': item['cell'], 'iou': score, 'size': list(generated.size),
                      'alpha_bbox': list(generated.getbbox()), 'uses': item['uses']})
        for use in item['uses']:
            destination = frame_path(FRAMES, use['path'], use['frame'])
            destination.parent.mkdir(parents=True, exist_ok=True); generated.save(destination)
    manifest_path = FRAMES / 'art_manifest.json'
    manifest = json.loads(manifest_path.read_text('utf-8')) if manifest_path.exists() else {'version': 'v08', 'assets': {}, 'pages': {}}
    for asset in data['assets']:
        files = [frame_path(FRAMES, asset['img'], k) for k in range(asset['frame_count'])]
        manifest['assets'][asset['img']] = {**asset, 'page': page, 'frames': [relative(p) for p in files],
                                           'frame_sha256': [sha(p) for p in files]}
    qa = comparison(page, data['cells'], made)
    manifest['pages'][page] = {'raw': relative(raw_path), 'raw_sha256': sha(raw_path), 'refs': relative(refs_path),
                               'qa': relative(qa), 'low_alpha_haze_removed_below': 64, 'frame_stats': stats,
                               'mean_iou': float(np.mean([s['iou'] for s in stats]))}
    manifest['scope'] = 'Generated physical props only; pure glow layers handled separately. No package/install or in-game validation.'
    save_json(manifest_path, manifest)
    print(json.dumps({'page': page, 'frames': sum(a['frame_count'] for a in data['assets']), 'mean_iou': manifest['pages'][page]['mean_iou'], 'qa': relative(qa), 'manifest': relative(manifest_path)}, ensure_ascii=False), flush=True)


def reuse_rx_aliases():
    """Reuse actual newly drawn matching poses for official material variants."""
    require_unfrozen()
    path = FRAMES / 'art_manifest.json'
    manifest = json.loads(path.read_text('utf-8'))
    summary = []
    for stem, original, offset in [('silverburster', 'rx78', 0),
                                   ('silverbursterjump', 'rx78jump', 0),
                                   ('silverburster_drop', 'rx78drop', 0),
                                   ('rx78boom', 'rx78', 6)]:
        source, entry, digest = load_asset(RX78, stem)
        old_base, base_entry, _ = load_asset(RX78, original)
        new_base = manifest['assets'][base_entry['path']]
        files, proof = [], []
        for k in range(source.count):
            old = source.image(k).convert('RGBA')
            same_pose = old_base.image(k + offset).convert('RGBA')
            if old.size != same_pose.size:
                raise ValueError('Variant pose dimensions do not match')
            a = np.asarray(old)[..., 3] > 64
            b = np.asarray(same_pose)[..., 3] > 64
            overlap = float((a & b).sum() / max(1, (a | b).sum()))
            if overlap < .97:
                raise ValueError(f'Variant pose disagrees at {stem} k{k}: {overlap}')
            # Positions and local rectangles already agree. Copying the newly
            # generated frame avoids a second sharpening/resampling pass.
            image = Image.open(ROOT / new_base['frames'][k + offset]).convert('RGBA')
            target = frame_path(FRAMES, entry['path'], k)
            target.parent.mkdir(parents=True, exist_ok=True); image.save(target)
            files.append(relative(target))
            proof.append({'frame': k, 'source_frame': k + offset, 'source_alpha_mask_iou': overlap})
        manifest['assets'][entry['path']] = {'source_pack': RX78, 'img': entry['path'],
            'version': entry['version'], 'source_payload_sha256': digest,
            'frame_count': source.count, 'metadata': source.frames,
            'frames': files, 'frame_sha256': [sha(ROOT / f) for f in files],
            'derivation': 'New AI-drawn RX pose reused for same-shape official color variant; not a recolor of the official body.',
            'reused_from': base_entry['path'], 'reuse_checks': proof}
        summary.append({'img': entry['path'], 'frames': source.count,
                        'minimum_source_alpha_iou': min(p['source_alpha_mask_iou'] for p in proof)})
    manifest['rx_variant_reuse'] = summary
    save_json(path, manifest)
    print(json.dumps({'newly_drawn_pose_reuse': summary}, ensure_ascii=False), flush=True)


def match_fleet_planes(image, templates):
    """Calibrate original single-plane poses inside overlapping fleet images.

    Matching uses official RGB only to locate/choose a pose. Output RGB comes
    exclusively from the corresponding newly generated aircraft, never from a
    color transform of the official fleet texture.
    """
    import cv2
    from scipy import ndimage
    pixels = np.asarray(image)
    pad = 48
    scene = np.pad(pixels[..., :3].astype(np.float32), ((pad, pad), (pad, pad), (0, 0)))
    mask = np.pad(pixels[..., 3] > 24, pad)
    scene[~mask] = 0
    covered = np.zeros_like(mask)
    candidates = []
    for index, crop, box in templates:
        tm = (crop[..., 3] > 24).astype(np.uint8)
        score = cv2.matchTemplate(scene, crop[..., :3].astype(np.float32), cv2.TM_SQDIFF_NORMED, mask=tm)
        score = np.nan_to_num(score, nan=9, posinf=9, neginf=9)
        local = (score == ndimage.minimum_filter(score, size=7)) & (score < .95)
        ys, xs = np.nonzero(local)
        for y, x in zip(ys, xs):
            candidates.append((float(score[y, x]), index, int(x), int(y), crop, box))
    candidates.sort(key=lambda item: item[0])
    placements = []
    for error, index, x, y, crop, box in candidates:
        height, width = crop.shape[:2]
        tm = crop[..., 3] > 24
        cy, cx = y + height / 2, x + width / 2
        if any((p['cx'] - cx) ** 2 + (p['cy'] - cy) ** 2 < 64 for p in placements):
            continue
        source = mask[y:y + height, x:x + width]
        occupied = float((source & tm).sum() / tm.sum())
        contribution = int((source & tm & ~covered[y:y + height, x:x + width]).sum())
        if occupied < .7 or contribution < max(60, int(tm.sum() * .25)):
            continue
        placements.append({'canonical': index, 'x': x - pad, 'y': y - pad,
                           'cx': cx, 'cy': cy, 'error': error, 'new_source_pixels': contribution,
                           'template_bbox': [int(v) for v in box]})
        covered[y:y + height, x:x + width] |= tm
    coverage = float((mask & covered).sum() / max(1, mask.sum()))
    if not placements or coverage < .92:
        raise ValueError(f'Fleet placement calibration is incomplete ({coverage:.3f})')
    return placements, coverage


def derive_factory_fleets():
    require_unfrozen()
    path = FRAMES / 'art_manifest.json'
    manifest = json.loads(path.read_text('utf-8'))
    angles, angle_entry, _ = load_asset(FACTORY, 'sparrowfactoryvpformationn2')
    new_angles = manifest['assets'][angle_entry['path']]
    templates = []
    for k in range(angles.count):
        array = np.asarray(angles.image(k))
        yy, xx = np.nonzero(array[..., 3] > 24)
        box = (int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1)
        templates.append((k, array[box[1]:box[3], box[0]:box[2]], box))
    summary = []
    for stem in ('solarsparrow', 'sparrowfactoryvpformationn'):
        source, entry, digest = load_asset(FACTORY, stem)
        files, proof, cells, made = [], [], [], {}
        for k in range(source.count):
            original = source.image(k).convert('RGBA')
            placements, coverage = match_fleet_planes(original, templates)
            image = Image.new('RGBA', original.size)
            # Better visible matches are placed last; partly occluded planes
            # remain behind them, preserving the existing overlapping layout.
            for placement in sorted(placements, key=lambda p: p['error'], reverse=True):
                plane = Image.open(ROOT / new_angles['frames'][placement['canonical']]).convert('RGBA')
                box = placement['template_bbox']
                image.alpha_composite(plane, (placement['x'] - box[0], placement['y'] - box[1]))
            target = frame_path(FRAMES, entry['path'], k)
            target.parent.mkdir(parents=True, exist_ok=True); image.save(target)
            files.append(relative(target)); made[k] = image
            original_path = frame_path(REFS / 'source_frames', entry['path'], k)
            original_path.parent.mkdir(parents=True, exist_ok=True); original.save(original_path)
            cells.append({'cell': k, 'original_png': relative(original_path)})
            proof.append({'frame': k, 'located_planes': len(placements),
                          'official_foreground_placement_coverage': coverage, 'placements': placements})
        qa = comparison(stem + '_derived_fleet', cells, made)
        manifest['assets'][entry['path']] = {'source_pack': FACTORY, 'img': entry['path'],
            'version': entry['version'], 'source_payload_sha256': digest,
            'frame_count': source.count, 'metadata': source.frames, 'frames': files,
            'frame_sha256': [sha(ROOT / f) for f in files],
            'derivation': 'Reassembled entirely from newly AI-drawn matching single-aircraft poses, located against official fleet layout; no original body RGB retained.',
            'canonical_asset': angle_entry['path'], 'placement_qa': relative(qa), 'placement_checks': proof}
        summary.append({'img': entry['path'], 'frames': source.count,
                        'minimum_placement_coverage': min(p['official_foreground_placement_coverage'] for p in proof),
                        'mean_placement_coverage': float(np.mean([p['official_foreground_placement_coverage'] for p in proof])),
                        'qa': relative(qa)})
    manifest['fleet_reassembly'] = summary
    save_json(path, manifest)
    print(json.dumps({'new_aircraft_fleet_reassembly': summary}, ensure_ascii=False), flush=True)


def derive_tiny_fragments():
    """Explicit material matching for 17-22px debris, never complete bodies."""
    require_unfrozen()
    path = FRAMES / 'art_manifest.json'
    manifest = json.loads(path.read_text('utf-8'))
    summary = []
    neutral_stops = np.array([[18, 17, 16], [52, 49, 44], [174, 166, 148], [246, 236, 215], [255, 248, 227]], dtype=np.float32)
    orange_stops = np.array([[35, 20, 14], [96, 42, 20], [217, 119, 67], [255, 181, 92], [255, 237, 193]], dtype=np.float32)
    knots = [0, .2, .46, .76, 1]
    stems = ['rx78piece', *[f'rx78piece{i:02d}' for i in range(1, 6)], 'silverburster_particle']
    for stem in stems:
        source, entry, digest = load_asset(RX78, stem)
        files, cells, made = [], [], {}
        for k in range(source.count):
            original = source.image(k).convert('RGBA')
            if max(original.size) > 22:
                raise ValueError('Debris material remap is not permitted for full bodies')
            array = np.asarray(original).copy()
            rgb = array[..., :3].astype(np.float32)
            value = (rgb[..., 0] * .299 + rgb[..., 1] * .587 + rgb[..., 2] * .114) / 255
            chroma = rgb.max(2) - rgb.min(2)
            warm_key = (chroma > 30) & (rgb[..., 0] >= rgb[..., 1] * .95) & (rgb[..., 0] > rgb[..., 2] * 1.15)
            neutral = np.stack([np.interp(value, knots, neutral_stops[:, c]) for c in range(3)], axis=2)
            orange = np.stack([np.interp(value, knots, orange_stops[:, c]) for c in range(3)], axis=2)
            array[..., :3] = np.rint(np.where(warm_key[..., None], orange, neutral)).astype(np.uint8)
            array[array[..., 3] == 0, :3] = 0
            image = Image.fromarray(array)
            if not np.array_equal(np.asarray(image)[..., 3], np.asarray(original)[..., 3]):
                raise ValueError('Fragment alpha changed')
            target = frame_path(FRAMES, entry['path'], k)
            target.parent.mkdir(parents=True, exist_ok=True); image.save(target)
            files.append(relative(target)); made[k] = image
            original_path = frame_path(REFS / 'source_frames', entry['path'], k)
            original_path.parent.mkdir(parents=True, exist_ok=True); original.save(original_path)
            cells.append({'cell': k, 'original_png': relative(original_path)})
        qa = comparison(stem + '_tiny_material', cells, made)
        manifest['assets'][entry['path']] = {'source_pack': RX78, 'img': entry['path'],
            'version': entry['version'], 'source_payload_sha256': digest,
            'frame_count': source.count, 'metadata': source.frames, 'frames': files,
            'frame_sha256': [sha(ROOT / f) for f in files], 'ai_redrawn': False,
            'derivation': 'Explicit tiny debris material-palette alignment only (maximum side <=22px). Not claimed as AI-redrawn full body. Source alpha and pose unchanged.',
            'material_alpha_preserved': True, 'material_qa': relative(qa)}
        summary.append({'img': entry['path'], 'frames': source.count, 'qa': relative(qa)})
    manifest['tiny_fragment_material_alignment'] = summary
    save_json(path, manifest)
    print(json.dumps({'tiny_material_fragments': summary}, ensure_ascii=False), flush=True)


def freeze_art():
    require_unfrozen()
    path = FRAMES / 'art_manifest.json'
    manifest = json.loads(path.read_text('utf-8'))
    count = 0
    for asset in manifest['assets'].values():
        if len(asset['frames']) != asset['frame_count']:
            raise ValueError('Incomplete art asset')
        for frame, digest in zip(asset['frames'], asset['frame_sha256'], strict=True):
            if sha(ROOT / frame) != digest:
                raise ValueError('Reviewed art frame changed')
            count += 1
    if len(manifest['assets']) != 26 or count != 255:
        raise ValueError('Expected reviewed 26 assets / 255 frames')
    receipt = {'status': 'reviewed_art_frozen', 'manifest_sha256': sha(path),
               'script_sha256': sha(Path(__file__)), 'asset_count': 26, 'frames': count,
               'tiny_material_assets': 7, 'tiny_material_frames': 87,
               'policy': 'All art-builder write operations now refuse. Packaging may read these frames; art changes require a new version.'}
    save_json(FRAMES / 'art_freeze.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('refs', 'fit', 'reuse-rx', 'derive-fleets', 'derive-fragments', 'freeze'))
    parser.add_argument('pages', nargs='*', choices=SPECS)
    parser.add_argument('--raw', type=Path)
    parser.add_argument('--single', action='store_true')
    args = parser.parse_args()
    if args.mode == 'freeze':
        freeze_art()
        return
    if args.mode == 'reuse-rx':
        reuse_rx_aliases()
        return
    if args.mode == 'derive-fleets':
        derive_factory_fleets()
        return
    if args.mode == 'derive-fragments':
        derive_tiny_fragments()
        return
    if not args.pages:
        parser.error('refs/fit require at least one page')
    if args.mode == 'fit' and (len(args.pages) != 1 or args.raw is None):
        parser.error('fit requires exactly one page and --raw PATH')
    for page in args.pages:
        make_refs(page) if args.mode == 'refs' else fit_page(page, args.raw, args.single)


if __name__ == '__main__':
    main()
