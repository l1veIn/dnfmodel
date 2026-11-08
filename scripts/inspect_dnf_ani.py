"""Read-only ANI inspection. Never infer animation boundaries from IMG order.

Text ANI: reads the IMAGE / IMAGE POS / DELAY references, retaining repeats and
non-consecutive image indices. Binary ANI and encrypted PVF are not text ANI.
An extracted ANI still needs version + character/state-reference verification
before it can be admitted to the dashboard's confirmed action catalog.
"""
import argparse
import hashlib
import json
import re
import struct
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def parse_text_ani(path, encoding='utf-8-sig'):
    path = Path(path)
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('ANI exceeds the 16 MiB inspection limit')
    raw = path.read_bytes()
    text = raw.decode(encoding)  # No lossy decoding / arbitrary binary fallback.
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    text = re.sub(r'(?m)^\s*//.*$', '', text)
    sections = list(re.finditer(r'(?m)^\s*\[([^\]\r\n]+)\]\s*$', text))
    tags = [(m.group(1).upper(), text[m.end():sections[i+1].start() if i+1 < len(sections) else len(text)].strip(), text.count('\n', 0, m.start())+1) for i,m in enumerate(sections)]
    declared = [int(value) for tag,value,_ in tags if tag == 'FRAME MAX']
    if len(declared) != 1 or not 0 < declared[0] <= 65535:
        raise ValueError('Expected one valid FRAME MAX')
    frames = []
    overall = []
    current = None
    for tag,value,line in tags:
        frame = re.fullmatch(r'FRAME(\d+)', tag)
        if frame:
            current = {'ani_frame': int(frame[1]), 'line': line, 'image': None,
                       'image_pos': None, 'delay_ms': None, 'tags': []}
            frames.append(current)
            continue
        if current is None:
            overall.append({'tag': tag, 'value': value, 'line': line})
            continue
        current['tags'].append({'tag': tag, 'value': value, 'line': line})
        if tag == 'IMAGE':
            match = re.fullmatch(r'`([^`]*)`\s+(-?\d+)', value)
            if not match or current['image'] is not None:
                raise ValueError(f'Invalid or duplicate IMAGE at line {line}')
            current['image'] = {'path': match[1].replace('\\', '/'), 'img_slot': int(match[2])}
        elif tag == 'IMAGE POS':
            values = value.split()
            if len(values) != 2 or current['image_pos'] is not None:
                raise ValueError(f'Invalid or duplicate IMAGE POS at line {line}')
            current['image_pos'] = [int(v) for v in values]
        elif tag == 'DELAY':
            delay = int(value)
            if delay < 0 or current['delay_ms'] is not None:
                raise ValueError(f'Invalid or duplicate DELAY at line {line}')
            current['delay_ms'] = delay
    if [f['ani_frame'] for f in frames] != list(range(declared[0])):
        raise ValueError('FRAME MAX / ordered FRAME sections disagree')
    if any(f['image'] is None or f['image_pos'] is None for f in frames):
        raise ValueError('A frame is missing IMAGE or IMAGE POS')
    return {'schema_version': 1, 'inspected_at': now(), 'source_file': str(path.resolve()),
            'sha256': hashlib.sha256(raw).hexdigest(), 'format': 'text_ani',
            'frame_count': len(frames), 'overall_tags': overall, 'frames': frames,
            'timing_complete': all(f['delay_ms'] is not None for f in frames),
            'version_verified': False, 'character_state_reference_verified': False,
            'admitted_to_dashboard': False}


def probe_pvf(path):
    """Bounded format probe, not a decrypter. Hash/search reads 8 MiB chunks."""
    path = Path(path)
    size = path.stat().st_size
    with path.open('rb') as stream:
        header = stream.read(128)
    identifier_length = struct.unpack('<I', header[:4])[0] if len(header) >= 4 else None
    classic = False
    if identifier_length is not None and 1 <= identifier_length <= 128 and len(header) >= 4 + identifier_length + 16:
        identifier = header[4:4+identifier_length]
        version, tree_length, crc, count = struct.unpack_from('<4I', header, 4+identifier_length)
        classic = (all(32 <= c < 127 for c in identifier) and tree_length % 4 == 0
                   and 0 < tree_length < size and 0 < count <= tree_length // 20
                   and 4+identifier_length+16+tree_length <= size)
    magic = header.startswith(b'DNF_SCRIPT_PACK')
    signatures = [b'character/mage/animation/', b'character\\mage\\animation/', b'mg_body0000.img']
    digest = hashlib.sha256()
    matches = {s.decode('ascii'): [] for s in signatures}
    offset = 0
    tail = b''
    with path.open('rb') as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
            data = (tail + chunk).lower()
            for signature in signatures:
                start = 0
                while (found := data.find(signature, start)) >= 0:
                    absolute = offset - len(tail) + found
                    if absolute not in matches[signature.decode('ascii')] and len(matches[signature.decode('ascii')]) < 20:
                        matches[signature.decode('ascii')].append(absolute)
                    start = found + 1
            tail = data[-128:]
            offset += len(chunk)
    return {'inspected_at': now(), 'file': str(path.resolve()), 'bytes': size,
            'sha256': digest.hexdigest(), 'header_hex': header[:64].hex(),
            'first_uint32_le': identifier_length, 'act1_magic_match': magic,
            'classic_uuid_header_plausible': classic,
            'status': 'recognized_container_needs_extraction' if magic or classic else 'unsupported_container',
            'plaintext_signature_matches': matches, 'extracted_ani_count': 0,
            'notes': ['Header compared with public ACT1 / classic UUID PVF layouts.',
                      'No matching plaintext signatures does not prove no ANI exists; encrypted content remains unread.',
                      'No process memory access, injection, game writes, or full-file memory loading.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    ani = sub.add_parser('parse-text')
    ani.add_argument('input', type=Path)
    ani.add_argument('--encoding', default='utf-8-sig')
    ani.add_argument('--output', type=Path, required=True)
    pvf = sub.add_parser('probe-pvf')
    pvf.add_argument('input', type=Path)
    pvf.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = parse_text_ani(args.input, args.encoding) if args.command == 'parse-text' else probe_pvf(args.input)
    save(args.output, result)
    print(json.dumps({'output': str(args.output), 'status': result.get('status', 'parsed_reference_only'),
                      'frames': result.get('frame_count'), 'admitted_to_dashboard': False}))


if __name__ == '__main__':
    main()
