"""Register generated arm edits and merge only reviewed arm-shaped masks.

Only output/whale_walk_arms_v06/candidate*, selected and freeze.json are written.
No image generation, invented arm drawing, full-final pass or game operation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage, optimize

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'output/whale_walk_arms_v06'
BASE = ROOT / 'output/fatfish_whale_maid_v05'
AUDIT = WORK / 'reference/audit.json'
SLOTS = (3, 6)
ROI = (230, 314, 251, 338)
os.environ['PATCH_ID'] = 'fatfish_whale_maid'
sys.path.insert(0, str(ROOT / '.claude/skills/dnf-character-patch/scripts'))
from kit import art


def stamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def new_candidate(name):
    target = (WORK / name).resolve()
    assert target.parent == WORK.resolve() and target.name.startswith('candidate')
    assert not target.exists(), 'Use a fresh sibling candidate; never overwrite reviewed outputs'
    target.mkdir(parents=True)
    return target


def sources():
    rows = {row['tool']: row for row in load(AUDIT)['frames'] if row['target']}
    assert set(rows) == set(SLOTS)
    for row in rows.values():
        assert sha(ROOT / row['hd']) == row['hd_sha256']
        assert sha(ROOT / row['native']) == row['native_sha256']
    return rows


def native_baseline():
    result = {}
    for k in range(174):
        path = BASE / f'native_frames/{k:04d}.png'
        result[path.name] = dict(sha256=sha(path), mtime_ns=path.stat().st_mtime_ns)
    return result


def affine(image, params, size=(576, 576), resample=Image.Resampling.BICUBIC):
    scale, dx, dy = params
    assert .4 <= scale <= 2 and abs(dx) <= 300 and abs(dy) <= 300
    return image.transform(size, Image.Transform.AFFINE,
                           (1 / scale, 0, -dx / scale, 0, 1 / scale, -dy / scale),
                           resample=resample, fillcolor=(0, 0, 0, 0))


def auto_register(generated, original, row):
    """One scale/translation fit to unedited image features, never a body warp.

    The fitted image is only a source for a local arm patch. All final pixels
    outside the separately reviewed arm mask come from the accepted old frame.
    """
    side = 144
    reference = np.asarray(original.resize((side, side), Image.Resampling.BOX), np.float32) / 255
    source = generated.resize((side, side), Image.Resampling.BOX)
    support = reference[..., 3] > .15
    weights = np.where(ndimage.binary_dilation(support, iterations=4), 1., .12)
    x0, y0, x1, y1 = row['target_hd_roi']
    weights[max(0, y0 // 4 - 5):min(side, y1 // 4 + 6),
            max(0, x0 // 4 - 5):min(side, x1 // 4 + 6)] = 0
    # Head and lower legs/shoes are stable anchors; the edited rear arm is excluded.
    yy = np.arange(side)[:, None]
    weights *= np.where((yy < 53) | (yy > 95), 2., 1.)
    target_rgb = reference[..., :3] * reference[..., 3:]

    def loss(p):
        scale, dx, dy = p
        if not (.4 <= scale <= 2 and abs(dx) <= 75 and abs(dy) <= 75):
            return 1e3
        fitted = np.asarray(affine(source, p, (side, side)), np.float32) / 255
        opacity = np.abs(fitted[..., 3] - reference[..., 3])
        rgb = np.abs(fitted[..., :3] * fitted[..., 3:] - target_rgb).mean(2)
        return float(np.sum(weights * (opacity + .35 * rgb)) / weights.sum())

    # Initial canvas registration plus bounded numerical fit; no per-feature transforms.
    trials = []
    for scale in (.8, 1., 1.2):
        opt = optimize.minimize(loss, [scale, 0, 0], method='Powell',
                                bounds=[(.6, 1.6), (-50, 50), (-50, 50)],
                                options={'maxiter': 36, 'xtol': .025, 'ftol': 1e-5})
        trials.append(opt)
    best = min(trials, key=lambda result: result.fun)
    params = [float(best.x[0]), float(best.x[1] * 4), float(best.x[2] * 4)]
    return params, dict(method='Unedited alpha/RGB features, one bounded uniform scale and translation',
                        objective=float(best.fun), excluded_hd_roi=row['target_hd_roi'],
                        normalized_144px_fit=True, original_canvas_no_bbox_fit=True)


def composite_on(image, background=(47, 54, 68, 255)):
    canvas = Image.new('RGBA', image.size, background)
    canvas.alpha_composite(image)
    return canvas.convert('RGB')


def contact(rows, labels, slots, crop, target, factor=4):
    width, height = crop[2] - crop[0], crop[3] - crop[1]
    result = Image.new('RGB', (len(slots) * (width * factor + 14), len(rows) * (height * factor + 24)), (47, 54, 68))
    draw = ImageDraw.Draw(result)
    for ri, (images, label) in enumerate(zip(rows, labels)):
        for ci, (slot, im) in enumerate(zip(slots, images)):
            x, y = ci * (width * factor + 14) + 7, ri * (height * factor + 24)
            draw.text((x, y + 3), f'{label}: user{slot + 1} tool{slot}', fill='white')
            piece = composite_on(im.crop(crop)).resize((width * factor, height * factor), Image.Resampling.NEAREST)
            result.paste(piece, (x, y + 22))
    result.save(target)


def align(args):
    rows = sources()
    audit = load(AUDIT)
    candidate = new_candidate(args.candidate)
    (candidate / 'registered').mkdir()
    (candidate / 'review').mkdir()
    record = dict(status='registered_waiting_for_explicit_arm_masks', created_at=stamp(),
                  audit=rel(AUDIT), audit_sha256=sha(AUDIT), inputs=[],
                  native_baseline=native_baseline(), pipeline=rel(Path(__file__)))
    old, fitted = [], []
    for slot in SLOTS:
        source = Path(getattr(args, f'image{slot}')).resolve(strict=True)
        assert source.is_relative_to((WORK / 'art').resolve()), 'Copy the parent-owned generated return into art/ first'
        generated = Image.open(source).convert('RGBA')
        assert np.mean(np.asarray(generated)[..., 3] == 0) > .05, 'Expected actual transparent generated output'
        original = Image.open(ROOT / rows[slot]['hd']).convert('RGBA')
        normalized = generated.resize(original.size, Image.Resampling.LANCZOS)
        row = dict(rows[slot], target_hd_roi=audit['target_hd_arm_roi'][str(slot)])
        manual = getattr(args, f'transform{slot}')
        if manual:
            params = [float(value) for value in manual.split(',')]
            assert len(params) == 3
            method = dict(method='Explicit root-selected uniform canvas registration', objective=None)
        else:
            params, method = auto_register(normalized, original, row)
        registered = affine(normalized, params)
        path = candidate / f'registered/{slot:04d}.png'
        registered.save(path)
        old.append(original)
        fitted.append(registered)
        record['inputs'].append(dict(slot=slot, generated=rel(source), generated_sha256=sha(source),
                                     generated_size=list(generated.size), normalized_canvas=list(original.size),
                                     registration=params, registration_details=method,
                                     registered=rel(path), registered_sha256=sha(path),
                                     accepted_hd=rows[slot]['hd'], accepted_hd_sha256=rows[slot]['hd_sha256'],
                                     accepted_native=rows[slot]['native'], accepted_native_sha256=rows[slot]['native_sha256']))
    contact([old, fitted], ['accepted v05', 'registered generator return'], SLOTS,
            (70, 150, 300, 380), candidate / 'review/registration_contact.png', 2)
    save(candidate / 'registration.json', record)
    print(json.dumps(dict(candidate=rel(candidate), manifest=rel(candidate / 'registration.json'),
                          transforms={str(row['slot']): row['registration'] for row in record['inputs']})))


def palette():
    colours = []
    for slot in range(10):
        arr = np.asarray(Image.open(BASE / f'native_frames/{slot:04d}.png').convert('RGBA'))
        colours.append(arr[..., :3][arr[..., 3] > 0])
    pixels = np.concatenate(colours)
    return Image.fromarray(pixels.reshape(-1, 1, 3), 'RGB').quantize(256, method=Image.Quantize.MEDIANCUT)


def mask_from_config(item, native_origin):
    if 'mask_hd' in item:
        path = (ROOT / item['mask_hd']).resolve(strict=True)
        assert path.is_relative_to(WORK)
        mask = Image.open(path).convert('L')
        assert mask.size == (576, 576)
    else:
        polygon = item.get('polygon_hd')
        assert isinstance(polygon, list) and len(polygon) >= 3, 'An explicit arm-shaped HD polygon or mask is required'
        assert all(len(p) == 2 and all(isinstance(v, (int, float)) and 0 <= v <= 576 for v in p) for p in polygon)
        mask = Image.new('L', (576, 576))
        ImageDraw.Draw(mask).polygon([tuple(p) for p in polygon], fill=255)
    world = Image.new('L', (500, 500))
    world.paste(mask.resize((128, 128), Image.Resampling.BOX), tuple(native_origin))
    native = np.asarray(world) >= 127
    bounds = np.zeros((500, 500), bool)
    x0, y0, x1, y1 = ROI
    bounds[y0:y1, x0:x1] = True
    outside = int(np.sum(native & ~bounds))
    assert not outside, f'Arm mask exceeds authorised native envelope: {outside} pixels'
    assert 8 <= int(native.sum()) <= (x1 - x0) * (y1 - y0), 'Mask is empty or implausibly small'
    return mask, native


def loop(images, crop, output, factor=1):
    frames = [composite_on(im.crop(crop)).resize(((crop[2] - crop[0]) * factor, (crop[3] - crop[1]) * factor), Image.Resampling.NEAREST) for im in images]
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=180, loop=0, lossless=True)


def build(args):
    registration = (WORK / args.registration).resolve(strict=True)
    assert registration.parent == WORK.resolve() and registration.name.startswith('candidate')
    record = load(registration / 'registration.json')
    assert record['native_baseline'] == native_baseline(), 'Accepted source bytes or mtimes changed'
    rows = sources()
    masks_path = args.masks.resolve(strict=True)
    assert masks_path.is_relative_to(WORK)
    masks = load(masks_path)
    assert set(masks) == {'3', '6'}
    candidate = new_candidate(args.candidate)
    for sub in ['native_frames', 'clips/clip_000_009/hd', 'masks_hd', 'masks_native', 'review']:
        (candidate / sub).mkdir(parents=True)
    colour_table = palette()
    colour_table.save(candidate / 'palette.png')
    selected = load(BASE / 'clips/clip_000_009/selection.json')
    old_frames = [Image.open(BASE / f'native_frames/{slot:04d}.png').convert('RGBA') for slot in range(10)]
    new_frames = [im.copy() for im in old_frames]
    frame_records = []
    registered_records = {row['slot']: row for row in record['inputs']}
    for slot in SLOTS:
        row = rows[slot]
        registered_record = registered_records[slot]
        registered_path = ROOT / registered_record['registered']
        assert sha(registered_path) == registered_record['registered_sha256']
        original_hd = np.asarray(Image.open(ROOT / row['hd']).convert('RGBA'))
        generated = Image.open(registered_path).convert('RGBA')
        hd_mask, native_mask = mask_from_config(masks[str(slot)], row['render_origin'])
        hd_mask.save(candidate / f'masks_hd/{slot:04d}.png')
        Image.fromarray((native_mask * 255).astype('uint8'), 'L').save(candidate / f'masks_native/{slot:04d}.png')
        # Paint only visible generated arm pixels; transparent gaps retain old hair/bow.
        patch = np.asarray(generated).copy()
        patch[..., 3] = np.minimum(patch[..., 3], np.asarray(hd_mask))
        combined = Image.alpha_composite(Image.fromarray(original_hd.copy(), 'RGBA'), Image.fromarray(patch, 'RGBA'))
        hd = original_hd.copy()
        visible_mask = np.asarray(hd_mask) > 0
        hd[visible_mask] = np.asarray(combined)[visible_mask]
        assert np.array_equal(hd[~visible_mask], original_hd[~visible_mask])
        hd_path = candidate / f'clips/clip_000_009/hd/{slot:04d}.png'
        Image.fromarray(hd, 'RGBA').save(hd_path)
        colour, alpha = art.downscale(Image.fromarray(hd, 'RGBA'), (128, 128))
        sprite = art.finish(art.sharpen(art.grade(colour)), alpha, colour_table)
        projected = Image.new('RGBA', (500, 500))
        projected.paste(sprite, tuple(row['render_origin']))
        original = np.asarray(old_frames[slot])
        candidate_pixels = original.copy()
        rendered = np.asarray(projected)
        copy_mask = native_mask & (rendered[..., 3] > 0)
        candidate_pixels[copy_mask] = rendered[copy_mask]
        changed = np.any(candidate_pixels != original, axis=2)
        assert np.array_equal(candidate_pixels[~native_mask], original[~native_mask])
        assert changed.any(), f'No visible repair was produced for tool{slot}'
        result = Image.fromarray(candidate_pixels, 'RGBA')
        native_path = candidate / f'native_frames/{slot:04d}.png'
        result.save(native_path)
        new_frames[slot] = result
        rgb16 = candidate_pixels[..., :3].astype(np.int16)
        warm = (rgb16[..., 0] > rgb16[..., 1] + 10) & (rgb16[..., 0] > rgb16[..., 2]) & (rgb16[..., 0] > 120)
        white = (candidate_pixels[..., :3].min(2) > 160) & (np.ptp(candidate_pixels[..., :3], axis=2) < 70)
        protected = {'head_face': (210, 275, 285, 314), 'present_forward_arm': (251, 314, 290, 349),
                     'lower_body': (210, 338, 302, 400), 'tail': (213, 325, 230, 350), 'back_bow_watch': (232, 329, 251, 343)}
        touched = {name: int(changed[y0:y1, x0:x1].sum()) for name, (x0, y0, x1, y1) in protected.items()}
        assert all(touched[name] == 0 for name in protected if name != 'back_bow_watch')
        old_white = (original[..., :3].min(2) > 160) & (np.ptp(original[..., :3], axis=2) < 70) & (original[..., 3] > 0)
        bx0, by0, bx1, by1 = protected['back_bow_watch']
        bow_white_changed = int((changed & old_white)[by0:by1, bx0:bx1].sum())
        frame_records.append(dict(slot=slot, user_frame=slot + 1, native=rel(native_path), native_sha256=sha(native_path),
                                  hd=rel(hd_path), hd_sha256=sha(hd_path), original_native=row['native'],
                                  original_native_sha256=row['native_sha256'], arm_envelope=list(ROI),
                                  changed_pixels=int(changed.sum()), outside_native_mask_changed_pixels=0,
                                  outside_hd_mask_changed_pixels=0, new_warm_pixels_in_mask=int((warm & changed).sum()),
                                  new_white_pixels_in_mask=int((white & changed).sum()), protected_region_changes=touched,
                                  back_bow_watch_original_white_pixels_changed=bow_white_changed,
                                  generated_input=registered_record['generated'], generated_sha256=registered_record['generated_sha256']))
        for selection in selected['frames']:
            if selection['slot'] == slot:
                selection['video_frame'] = f'whale_walk_arms_v06:{slot}'
                selection['walk_arm_repair_v06'] = dict(only_posterior_arm=True, generated=registered_record['generated'],
                                                        arm_mask_native=rel(candidate / f'masks_native/{slot:04d}.png'),
                                                        native_is_authoritative=True)
    selected['walk_arm_repair_v06'] = dict(source_registration=rel(registration / 'registration.json'),
                                          masks=rel(masks_path), native_is_authoritative=True,
                                          note='Only tool3/6 posterior arm patches; never rerender accepted full figures.')
    save(candidate / 'clips/clip_000_009/selection.json', selected)
    contact([old_frames, new_frames], ['accepted v05', 'arm repair candidate'], list(range(10)),
            (210, 285, 300, 397), candidate / 'review/walk_contact.png', 3)
    contact([[old_frames[s] for s in SLOTS], [new_frames[s] for s in SLOTS]], ['accepted v05', 'arm repair candidate'],
            SLOTS, (225, 307, 275, 346), candidate / 'review/arm_close.png', 9)
    loop(new_frames, (210, 285, 300, 397), candidate / 'review/walk_native.webp')
    loop(new_frames, (210, 285, 300, 397), candidate / 'review/walk_x4.webp', 4)
    save(candidate / 'render_settings.json', dict(grade=art.P.grade, ink=art.INK.tolist(), native_size=128,
                                                line_keep=.45, sharpen_amount=.55, alpha_cut=.42, outline=True,
                                                palette=rel(candidate / 'palette.png'), palette_sha256=sha(candidate / 'palette.png'),
                                                method='Full generated arm registration, local positive-alpha overlay, accepted native copied outside explicit arm masks.'))
    assert record['native_baseline'] == native_baseline()
    save(candidate / 'manifest.json', dict(status='root_visual_review_required', created_at=stamp(), slots=list(SLOTS),
                                           registration=rel(registration / 'registration.json'), registration_sha256=sha(registration / 'registration.json'),
                                           masks_source=rel(masks_path), masks_source_sha256=sha(masks_path), frames=frame_records,
                                           unchanged_native_frames=172, accepted_native_baseline=record['native_baseline'],
                                           source_native_and_mtimes_unchanged=True, installed=False, user_aesthetic_approved=False))
    print(json.dumps(dict(candidate=rel(candidate), frames=frame_records, review=rel(candidate / 'review')), ensure_ascii=True))


def freeze(args):
    assert args.approved, 'Root must inspect the exact arm candidate before freeze'
    candidate = (WORK / args.candidate).resolve(strict=True)
    assert candidate.parent == WORK.resolve() and candidate.name.startswith('candidate')
    manifest = load(candidate / 'manifest.json')
    assert manifest['accepted_native_baseline'] == native_baseline()
    selected = WORK / 'selected'
    assert not selected.exists() and not (WORK / 'freeze.json').exists()
    shutil.copytree(candidate, selected, copy_function=shutil.copy2)
    selected_manifest = load(selected / 'manifest.json')
    selected_manifest.update(status='root_selected_local_candidate_pending_user_review', root_selected_at=stamp())
    save(selected / 'manifest.json', selected_manifest)
    frozen_code = selected / 'frozen_code'
    frozen_code.mkdir()
    for source, name in [(Path(__file__).resolve(), Path(__file__).name),
                         (ROOT / 'scripts/package_whale_walk_arms_v06.py', 'package_whale_walk_arms_v06.py'),
                         (ROOT / '.claude/skills/dnf-character-patch/scripts/kit/art.py', 'kit_art.py'),
                         (ROOT / '.claude/skills/dnf-character-patch/scripts/kit/config.py', 'kit_config.py')]:
        shutil.copy2(source, frozen_code / name)
    shutil.copy2(ROOT / 'design/fatfish_whale_maid/patch.json', frozen_code / 'patch_input_snapshot.json')
    bound = {path for path in selected.rglob('*') if path.is_file()}
    bound.update(path for path in candidate.rglob('*') if path.is_file())
    bound.update(path for folder in ['art', 'prompts'] for path in (WORK / folder).rglob('*') if path.is_file())
    generation_record = WORK / 'generation_record.json'
    assert generation_record.is_file()
    bound.add(generation_record)
    bound.update({Path(__file__).resolve(), AUDIT, ROOT / manifest['masks_source'], ROOT / manifest['registration']})
    registration = load(ROOT / manifest['registration'])
    for row in registration['inputs']:
        bound.update(ROOT / row[key] for key in ['generated', 'registered', 'accepted_hd', 'accepted_native'])
    save(WORK / 'freeze.json', dict(status='root_selected_local_arm_repair_pending_user_review', frozen_at=stamp(),
                                   selected=rel(selected), original_candidate=rel(candidate),
                                   files_sha256={rel(path): sha(path) for path in sorted(bound)},
                                   generation_record=rel(generation_record), generation_record_sha256=sha(generation_record),
                                   selected_native={str(slot): sha(selected / f'native_frames/{slot:04d}.png') for slot in SLOTS},
                                   accepted_native_baseline=manifest['accepted_native_baseline'],
                                   installed=False, user_aesthetic_approved=False, game_runtime_validated=False))
    print(json.dumps(dict(selected=rel(selected), freeze=rel(WORK / 'freeze.json'), bound_files=len(bound))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    command = sub.add_parser('align')
    command.add_argument('--image3', type=Path, required=True)
    command.add_argument('--image6', type=Path, required=True)
    command.add_argument('--transform3', help='Uniform scale,dx,dy after normalising canvas to576')
    command.add_argument('--transform6', help='Uniform scale,dx,dy after normalising canvas to576')
    command.add_argument('--candidate', required=True)
    command = sub.add_parser('build')
    command.add_argument('--registration', required=True)
    command.add_argument('--masks', type=Path, required=True)
    command.add_argument('--candidate', required=True)
    command = sub.add_parser('freeze')
    command.add_argument('--candidate', required=True)
    command.add_argument('--approved', action='store_true')
    args = parser.parse_args()
    {'align': align, 'build': build, 'freeze': freeze}[args.action](args)


if __name__ == '__main__':
    main()
