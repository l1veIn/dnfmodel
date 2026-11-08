"""Download the one official control patch with a bounded streaming buffer."""
import hashlib
import json
import time
from pathlib import Path
import requests

NAME = 'minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors'
DEST = Path('D:/VideoStudio/comfyUI/shared/models/model_patches') / NAME
SIZE = 2296635360
DIGEST = '9c645c0a308c8af361efd43b409710f6f8fec0db297c29503e141a84991fed0c'
URL = 'https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/model_patches/' + NAME

def main():
    DEST.parent.mkdir(parents=True, exist_ok=True)
    part = DEST.with_suffix('.safetensors.part')
    if not DEST.exists():
        offset = part.stat().st_size if part.exists() else 0
        headers = {'Range': f'bytes={offset}-'} if offset else {}
        with requests.get(URL, headers=headers, stream=True, timeout=(30, 90)) as response:
            response.raise_for_status()
            if offset and response.status_code != 206:
                raise RuntimeError('Server did not honor resume; preserving partial file.')
            if offset and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                raise RuntimeError('Invalid resume range.')
            next_log = 0
            with part.open('ab' if offset else 'wb') as output:
                for block in response.iter_content(1024*1024):
                    if not block:
                        continue
                    output.write(block)
                    offset += len(block)
                    if offset > SIZE:
                        raise RuntimeError('Download larger than expected.')
                    if time.monotonic() > next_log:
                        print(json.dumps({'bytes': offset, 'total': SIZE, 'percent': round(offset/SIZE*100, 1)}), flush=True)
                        next_log = time.monotonic()+25
        if part.stat().st_size != SIZE:
            raise RuntimeError('Incomplete download.')
        target = part
    else:
        target = DEST
    digest = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
    if target.stat().st_size != SIZE or digest != DIGEST:
        raise RuntimeError('Control patch integrity mismatch.')
    if target == part:
        part.replace(DEST)
    receipt = {'path': str(DEST), 'url': URL, 'bytes': SIZE, 'sha256': digest, 'verified': True}
    audit = Path(__file__).resolve().parents[1]/'design/fatfish/h3_pose_walk_v01/control_patch_receipt.json'
    audit.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt), flush=True)

if __name__ == '__main__':
    main()
