"""Fit four new awakening illustrations to all nine official female gunner paths."""
from pathlib import Path
import hashlib
import json
import re

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/claude_awakening_v09'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    scope = json.loads((ROOT / 'output/validation/awakening_completion_2026-11-10/scope.json').read_text('utf-8'))['projects']['claude']
    marker = OUT / 'art_manifest.json'
    if marker.exists():
        raise FileExistsError('Awakening art is frozen; choose another version')
    drawings = {}
    for role in ('launcher', 'mecha', 'ranger', 'spit'):
        raw = OUT / 'raw' / f'{role}.png'
        image = Image.open(raw).convert('RGBA')
        pixels = np.asarray(image).copy()
        pixels[pixels[..., 3] < 16] = 0
        image = Image.fromarray(pixels)
        box = image.getchannel('A').point(lambda x: 255 if x > 32 else 0).getbbox()
        if not box:
            raise ValueError(f'Empty generated art: {role}')
        image = image.crop(box)
        factor = min(411 / image.width, 335 / image.height)
        size = (round(image.width * factor), round(image.height * factor))
        fit = image.resize(size, Image.Resampling.LANCZOS)
        page = Image.new('RGBA', (415, 339))
        page.alpha_composite(fit, ((415-size[0])//2, 339-size[1]-2))
        folder = OUT / 'canvas' / role
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'frame_0000.png'
        page.save(path)
        drawings[role] = {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(path),
                          'raw': raw.relative_to(ROOT).as_posix(), 'raw_sha256': digest(raw),
                          'source_crop': list(box), 'uniform_scale': factor, 'size': list(size)}
    overlays = []
    for asset in scope['awakening']:
        role = next((r for r in drawings if f'atgunner_{r}' in asset['path']), None)
        if role is None or asset['frames'] != 1:
            raise ValueError(f'Unexpected awakening target {asset["path"]}')
        frame = asset['frame_geometry'][0]
        if (frame['cw'], frame['ch']) != (415, 339):
            raise ValueError('Unexpected source canvas')
        overlays.append({'source_npk': asset['source_npk'], 'path': asset['path'],
                         'frame_paths': [drawings[role]['path']], 'frame_mode': 'canvas',
                         'allow_geometry_change': True})
    config = {'title': 'Claude 大小姐 v09 · 一觉立绘补全候选',
              'base_npk': scope['base_npk'], 'output': 'output/claude_gunner_v09',
              'npk_name': 'A_Claude_FGunner_v09.NPK', 'overlays': overlays,
              'protect_paths': ['output/Claude_Gunner_v02/native_frames',
                                'output/claude_gunner_v08/A_Claude_FGunner_v08.NPK'],
              'license_note': '民间二创形象，仅自用；不代表官方合作。', 'installed': False}
    path = ROOT / 'design/claude_gunner/awakening_v09.json'
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    board = Image.new('RGB', (415*2, 365*2), '#252b34')
    text = ImageDraw.Draw(board)
    for k, (role, data) in enumerate(drawings.items()):
        image = Image.open(ROOT / data['path'])
        xy = (k%2*415, k//2*365+24)
        board.paste(image, xy, image)
        text.text((xy[0]+8,xy[1]-19), role, fill='white')
    board.save(OUT / 'contact.jpg', quality=95)
    manifest = {'status': 'frozen_for_package', 'new_illustrations': 4, 'target_paths': len(overlays),
                'art': drawings, 'config': path.relative_to(ROOT).as_posix(),
                'config_sha256': digest(path), 'scope': 'Four base transfer portraits plus event/tn variants; no changes to character, cutins or buff.'}
    marker.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'illustrations':4,'targets':len(overlays),'config':str(path)}))


if __name__ == '__main__':
    main()
