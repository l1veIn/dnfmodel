"""Build Claude's single-play vertical buff cut-in from frozen v05 art.

The character layer moves vertically inside a fixed band. The existing eye
patches and local hair/cloth animation are read unchanged; the generated rails
are a separate effect layer. This module never writes game files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageDraw

from buff_portrait import write_mov

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'design/claude_gunner/buff_v06.json'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def resolve(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Asset path must stay in the project')
    return path


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): digest(p) for p in sorted(folder.rglob('*')) if p.is_file()}


def band_mask(size, edges, feather):
    width, height = size
    left, right = edges
    x = np.arange(width, dtype=np.float32)
    value = np.minimum(np.clip((x - left) / feather, 0, 1), np.clip((right - 1 - x) / feather, 0, 1))
    return np.broadcast_to(value, (height, width)).copy()


def rgba(array):
    out = np.clip(np.rint(array), 0, 255).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    return Image.fromarray(out, 'RGBA')


def character_layer(source, dy, mask, bottom_fade_px):
    # Integer paste: no scale, subpixel resampling, or new face deformation.
    # The source is a waist crop. Feather only its lower crop edge before the
    # translation so the last upward frames cannot expose a horizontal photo
    # bottom. This matte does not alter face/body geometry or source pixels.
    input_array = np.asarray(source).copy()
    t = np.clip((source.height - 1 - np.arange(source.height)) / bottom_fade_px, 0, 1)
    bottom = t * t * (3 - 2 * t)
    input_array[...,3] = np.rint(input_array[...,3] * bottom[:,None]).astype(np.uint8)
    shifted = Image.new('RGBA', source.size)
    shifted.paste(Image.fromarray(input_array,'RGBA'), (0, int(dy)))
    array = np.asarray(shifted).copy()
    array[..., 3] = np.rint(array[..., 3] * mask).astype(np.uint8)
    array[array[..., 3] == 0, :3] = 0
    return Image.fromarray(array, 'RGBA')


def prepare_fx(image, size, left, right):
    width, height = size
    # Retain the generated portrait texture's extra vertical extent. The
    # output takes a moving window from this overscan, never a modulo wrap.
    scale = width / image.width
    texture_height = max(height + 1, round(image.height * scale))
    image = image.convert('RGBA').resize((width, texture_height), Image.Resampling.LANCZOS)
    result = Image.new('RGBA', image.size)
    # The supplied graphic has two rails. Translate the separate halves to the
    # requested fixed band edges; never use its geometry to scale the character.
    for box, source_x, target_x in (((0, 0, width // 2, texture_height), 56, left),
                                    ((width // 2, 0, width, texture_height), 406, right)):
        crop = image.crop(box)
        result.alpha_composite(crop, (box[0] + target_x - source_x, 0))
    return result


def effect_layers(cfg, fx, k):
    width, height = cfg['width'], cfg['height']
    left, right = cfg['band']['edges']
    y, x = np.mgrid[:height, :width].astype(np.float32)
    margin = cfg['band']['effect_margin']
    allowed = (x >= left - margin) & (x <= right + margin)
    side = np.maximum(np.exp(-((x - left) / 18) ** 2), np.exp(-((x - right) / 18) ** 2))
    # A dark translucent band gives the vertical composition a continuous
    # backing, rather than the silhouette of a floating full-body sprite.
    backing = np.zeros((height, width, 4), dtype=np.float32)
    backing[..., :3] = (21, 13, 12)
    backing[..., 3] = band_mask((width, height), (left, right), 3) * cfg['band']['backing_alpha']
    background = rgba(backing)
    top = min(fx.height - height, round(k * cfg['effects']['rail_scroll_px']))
    texture = np.asarray(fx.crop((0, top, width, top + height))).astype(np.float32)
    texture[..., 3] *= side * allowed * (0.64 + .10 * math.sin(k * .62))
    rail = rgba(texture)
    # Fine opaque rail cores make every frame encode with full alpha range.
    draw = ImageDraw.Draw(rail)
    draw.line((left, 0, left, height - 1), fill=(255, 198, 83, 255), width=1)
    draw.line((right, 0, right, height - 1), fill=(255, 235, 184, 255), width=1)
    background.alpha_composite(rail)
    foreground = np.zeros((height, width, 4), dtype=np.float32)
    # Only the rail-adjacent part of the generated effects sits over the art.
    foreground[..., :3] = texture[..., :3]
    foreground[..., 3] = texture[..., 3] * .38
    # One concise diagonal impact sweep across the lower portrait, kept clear
    # of the transported face. No full-frame white flash or pulsing zoom.
    sweep_strength = cfg['effects']['sweep_strength'][k]
    if sweep_strength:
        center = cfg['effects']['sweep_center_y'][k]
        distance = y - (center - .43 * (x - width / 2))
        lower_than_face = y > max(270, 225 + cfg['motion']['y_offsets'][k])
        beam = np.exp(-(distance / 5.5) ** 2) * sweep_strength * lower_than_face
        beam *= band_mask((width, height), (left + 3, right - 3), 4)
        front = np.zeros_like(foreground)
        front[..., :3] = (255, 216, 134)
        front[..., 3] = beam
        layer = rgba(foreground)
        layer.alpha_composite(rgba(front))
        foreground = np.asarray(layer).astype(np.float32)
    # No overlaid effect can touch the face/eye interior. Its x range stays in
    # the middle of the band regardless of vertical entrance position.
    face_top = 55 + cfg['motion']['y_offsets'][k]
    face_bottom = 213 + cfg['motion']['y_offsets'][k]
    face = (x >= 151) & (x < 337) & (y >= face_top) & (y < face_bottom)
    foreground[face, 3] = 0
    foreground[..., 3] *= allowed
    return background, rgba(foreground)


def render(cfg, sources, fx):
    size = (cfg['width'], cfg['height'])
    if size != (470, 668) or cfg['frames'] != 19 or cfg['fps'] != 15:
        raise ValueError('This reviewed preset uses 19 frames, 470x668, 15fps')
    if len(cfg['motion']['y_offsets']) != 19 or cfg['motion'].get('scale') != 1 or cfg['motion'].get('x_offset') != 0:
        raise ValueError('Band entrance must use explicit integer y positions and unchanged scale/x')
    if any(im.size != size for im in sources):
        raise ValueError('Frozen portrait frames must retain their original dimensions')
    left, right = cfg['band']['edges']
    fx = prepare_fx(fx, size, left, right)
    mask = band_mask(size, (left, right), cfg['band']['feather_px'])
    frames, metrics, characters, backgrounds, foregrounds = [], [], [], [], []
    for k, source in enumerate(sources):
        dy = cfg['motion']['y_offsets'][k]
        character = character_layer(source, dy, mask, cfg['band']['source_bottom_fade_px'])
        background, foreground = effect_layers(cfg, fx, k)
        final = background.copy()
        final.alpha_composite(character)
        final.alpha_composite(foreground)
        arr = np.asarray(final).copy()
        arr[arr[..., 3] == 0, :3] = 0
        final = Image.fromarray(arr, 'RGBA')
        alpha = arr[..., 3]
        if alpha.min() != 0 or alpha.max() != 255:
            raise ValueError('Every frame needs actual transparent margins and opaque rail cores')
        visible_y, visible_x = np.nonzero(alpha > 8)
        metrics.append(dict(frame=k, time_seconds=k / cfg['fps'], source_frame=k,
                            blink=cfg['blink_sequence'][k], character_transform={'x':0, 'y':dy, 'scale':1},
                            rail_x=[left, right], alpha_bbox=list(final.getbbox()),
                            rail_texture_y=min(fx.height-size[1], round(k*cfg['effects']['rail_scroll_px'])),
                            alpha_range=[int(alpha.min()), int(alpha.max())],
                            effective_width_gt8=int(visible_x.max() - visible_x.min() + 1),
                            foreground_face_alpha_max=0))
        frames.append(final);characters.append(character);backgrounds.append(background);foregrounds.append(foreground)
    return frames, metrics, characters, backgrounds, foregrounds


def build(config_path=CONFIG, replace_staged=False):
    cfg = json.loads(config_path.read_text('utf-8'))
    output = resolve(cfg['output'])
    if not output.is_relative_to(ROOT / 'output/claude_buff_v06'):
        raise ValueError('v06 export must remain in its own output tree')
    if (output / 'manifest.json').exists():
        old = json.loads((output / 'manifest.json').read_text('utf-8'))
        if not replace_staged or old.get('status') != 'staged_for_visual_review' or (output / 'portrait.bik').exists():
            raise FileExistsError('Frozen output exists; create a new version')
    parent = resolve(cfg['source_manifest'])
    parent_manifest = json.loads(parent.read_text('utf-8'))
    before = snapshot(parent.parent)
    fx_path = resolve(cfg['fx_source'])
    if not fx_path.is_file():
        raise FileNotFoundError('Generated FX asset is required; no placeholder publication')
    sources = [Image.open(parent.parent / f'frames/frame_{k:04d}.png').convert('RGBA') for k in range(19)]
    for k, expected in enumerate(parent_manifest['frame_sha256']):
        if digest(parent.parent / f'frames/frame_{k:04d}.png') != expected:
            raise ValueError('Frozen source frame changed')
    frames, metrics, characters, backgrounds, foregrounds = render(cfg, sources, Image.open(fx_path))
    output.mkdir(parents=True, exist_ok=True)
    for sub in ('frames', 'layers/character', 'layers/background', 'layers/foreground'):
        (output / sub).mkdir(parents=True, exist_ok=True)
    for k, frame in enumerate(frames):
        frame.save(output / f'frames/frame_{k:04d}.png')
        characters[k].save(output / f'layers/character/frame_{k:04d}.png')
        backgrounds[k].save(output / f'layers/background/frame_{k:04d}.png')
        foregrounds[k].save(output / f'layers/foreground/frame_{k:04d}.png')
    source_illustration = parent.parent / parent_manifest['source_illustration']
    shutil.copyfile(source_illustration, output / 'source.png')
    durations = [round((k + 1) * 1000 / cfg['fps']) - round(k * 1000 / cfg['fps']) for k in range(19)]
    frames[0].save(output / 'preview.webp', save_all=True, append_images=frames[1:],
                   lossless=True, exact=True, duration=durations, loop=0)
    # Labels belong only to the review contact, never to animation content.
    sheet = Image.new('RGBA', (470 * 4, 668 * 5))
    contact = Image.new('RGB', (188 * 4, 285 * 5), '#252d3a')
    draw = ImageDraw.Draw(contact)
    for k, frame in enumerate(frames):
        sheet.alpha_composite(frame, (k % 4 * 470, k // 4 * 668))
        part = frame.resize((188, 267), Image.Resampling.LANCZOS)
        at = (k % 4 * 188, k // 4 * 285 + 18)
        contact.paste(part, at, part)
        draw.text((at[0] + 5, at[1] - 14), f'k{k} y{metrics[k]["character_transform"]["y"]} {metrics[k]["blink"]}', fill='white')
    sheet.save(output / 'sheet.png');contact.save(output / 'contact.jpg', quality=95)
    mov = write_mov(frames, output / 'portrait_rgba.mov', cfg['fps'])
    if snapshot(parent.parent) != before:
        raise ValueError('Source v05 tree changed during export')
    proof = dict(source_tree=str(parent.parent.relative_to(ROOT)), source_files=before,
                 source_unchanged=True, source_frame_count=19,
                 character_has_no_new_deformation=True, character_scale=1,
                 character_x_translation=0, first_last_max_difference=int(np.max(np.abs(np.asarray(frames[0]).astype(np.int16) - np.asarray(frames[-1]).astype(np.int16)))),
                 single_play=True, seamless_loop_claimed=False, mov_roundtrip=mov)
    write_json(output / 'band_validation.json', proof)
    manifest = dict(title=cfg['title'], frames=19, size=[470,668], fps=15,
                    duration_seconds=19/15, preview_duration_ms=sum(durations),
                    source_reference=cfg['reference'], source_illustration='source.png',
                    source_raw_sha256=digest(source_illustration), source_size=list(Image.open(source_illustration).size),
                    source_manifest=cfg['source_manifest'], source_manifest_sha256=digest(parent),
                    source_frame_sha256=parent_manifest['frame_sha256'],
                    generation=cfg['generation'], fx_source=cfg['fx_source'], fx_sha256=digest(fx_path),
                    sheet_sha256=digest(output / 'sheet.png'), sheet_size=list(sheet.size),
                    frame_sha256=[digest(output / f'frames/frame_{k:04d}.png') for k in range(19)],
                    frame_metrics=metrics, mov_roundtrip=mov, targets=parent_manifest['targets'],
                    installed=False, status='staged_for_visual_review', warnings=[],
                    composition={'mode':'vertical_skill_cut_in', 'band_edges':cfg['band']['edges'],
                                 'character_crop_intentional':True, 'rails_fixed':True, 'background_alpha':cfg['band']['backing_alpha']},
                    motion_limitations='Single-play vertical entrance based on measured reference motion. Existing local blink/hair/cloth frames retained. No loop closure or in-game playback claim.',
                    license_note=cfg['license_note'],
                    bink_encoding={'format':'Bink 1','fps_override':15,'alpha':'include straight alpha','audio':False})
    write_json(output / 'manifest.json', manifest)
    print(json.dumps({'output':str(output.relative_to(ROOT)), 'frames':19, 'widths_gt8':[m['effective_width_gt8'] for m in metrics], 'source_unchanged':True},ensure_ascii=False))
    return manifest


def freeze(config_path=CONFIG):
    """Call after the staged contact/animation has been manually reviewed."""
    cfg=json.loads(config_path.read_text('utf-8'))
    output=resolve(cfg['output'])
    path=output/'manifest.json'
    manifest=json.loads(path.read_text('utf-8'))
    if manifest.get('status')!='staged_for_visual_review' or (output/'portrait.bik').exists():
        raise ValueError('Only the unencoded reviewed stage can be frozen')
    for k,expected in enumerate(manifest['frame_sha256']):
        if digest(output/f'frames/frame_{k:04d}.png')!=expected:
            raise ValueError('Staged frame changed after review')
    if digest(resolve(cfg['fx_source']))!=manifest['fx_sha256'] or digest(resolve(cfg['source_manifest']))!=manifest['source_manifest_sha256']:
        raise ValueError('Stage inputs changed after review')
    proof=json.loads((output/'band_validation.json').read_text('utf-8'))
    if snapshot(resolve(proof['source_tree']))!=proof['source_files']:
        raise ValueError('Frozen v05 inputs changed')
    manifest['status']='prepared_for_review_not_bink_encoded'
    manifest['recipe']={'config':str(config_path.resolve().relative_to(ROOT)).replace('\\','/'),
                        'config_sha256':digest(config_path),'script':'scripts/build_buff_band.py',
                        'script_sha256':digest(Path(__file__))}
    write_json(path,manifest)
    print(json.dumps({'frozen':True,'manifest_sha256':digest(path),'frames':19,'installed':False}))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config',type=Path,nargs='?',default=CONFIG)
    parser.add_argument('--replace-staged',action='store_true')
    parser.add_argument('--freeze',action='store_true',help='Freeze the stage after manual visual review; no rendering')
    args=parser.parse_args()
    freeze(args.config) if args.freeze else build(args.config,args.replace_staged)
