"""Resume a pinned official Ref2VA safetensors download with bounded buffers."""
import hashlib,json,time,sys,os
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]
DEST=Path('D:/VideoStudio/comfyUI/shared/models/diffusion_models/minimax_h3_ref2va_pruned_w6a8.safetensors')
RUN=ROOT/'design/fatfish/h3_reference_walk_v01'
SIZE=15983746636
SHA='ece96bbbce76670ec782de84acc888fd9d9b210bd2ab97c1957b39896734f9f1'
URL='https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/b697c7d61dc6289af15ce2690dcd4cd58366d2f0/diffusion_models/minimax_h3_ref2va_pruned_w6a8.safetensors'
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    RUN.mkdir(parents=True,exist_ok=True);DEST.parent.mkdir(parents=True,exist_ok=True)
    part=DEST.with_suffix('.safetensors.part')
    download_url=('https://modelscope.cn/models/Comfy-Org/MiniMax-H3/resolve/master/diffusion_models/'+DEST.name) if '--modelscope' in sys.argv else URL
    manifest={'source_url':URL,'download_url':download_url,'destination':str(DEST),'expected_bytes':SIZE,'expected_sha256':SHA,'verified':False}
    (RUN/'model_receipt.json').write_text(json.dumps(manifest,indent=2),'utf-8')
    if '--xet' in sys.argv and not DEST.exists():
        os.environ['HF_XET_NUM_CONCURRENT_RANGE_GETS']='8'
        os.environ['HF_XET_HIGH_PERFORMANCE']='0'
        from huggingface_hub import hf_hub_download
        print(json.dumps({'phase':'official_xet_download','concurrent_ranges':8,'expected_bytes':SIZE}),flush=True)
        hf_hub_download(repo_id='Comfy-Org/MiniMax-H3',filename='diffusion_models/'+DEST.name,
                        revision='b697c7d61dc6289af15ce2690dcd4cd58366d2f0',local_dir=str(DEST.parent.parent),token=False)
    if not DEST.exists():
        for attempt in range(1,6):
            start=part.stat().st_size if part.exists() else 0
            if start==SIZE:break
            if start>SIZE:raise RuntimeError('Partial file exceeds expected size; preserve it for inspection.')
            try:
                with requests.get(download_url,headers={'Range':f'bytes={start}-'} if start else {},stream=True,timeout=(25,90)) as response:
                    response.raise_for_status()
                    if start and response.status_code!=206:raise RuntimeError('Server did not honor resume range; preserve partial file.')
                    if response.status_code==206 and not response.headers.get('Content-Range','').startswith(f'bytes {start}-'):raise RuntimeError('Unexpected Content-Range')
                    received=start;last=0;begin=time.monotonic()
                    with part.open('ab' if start else 'wb') as target:
                        for block in response.iter_content(1024*1024):
                            if not block:continue
                            target.write(block);received+=len(block)
                            if received>SIZE:raise RuntimeError('Download longer than expected')
                            if time.monotonic()-last>=30:
                                print(json.dumps({'phase':'download','bytes':received,'total':SIZE,'percent':round(received/SIZE*100,1),'session_mib_s':round((received-start)/2**20/max(.01,time.monotonic()-begin),2)}),flush=True);last=time.monotonic()
                if part.stat().st_size==SIZE:break
            except (requests.RequestException,OSError) as error:
                print(json.dumps({'attempt':attempt,'error':str(error),'resumable':True}),flush=True)
                if attempt==5:raise
                time.sleep(5)
        if part.stat().st_size!=SIZE:raise RuntimeError('Incomplete model download')
        print(json.dumps({'phase':'sha256_verification','bytes':SIZE}),flush=True)
        actual=digest(part)
        if actual!=SHA:raise RuntimeError('Model SHA256 does not match official LFS metadata')
        part.replace(DEST)
    else:
        if DEST.stat().st_size!=SIZE or digest(DEST)!=SHA:raise RuntimeError('Existing model does not match official metadata')
    manifest.update(verified=True,actual_bytes=DEST.stat().st_size,actual_sha256=SHA,verified_at=time.time())
    (RUN/'model_receipt.json').write_text(json.dumps(manifest,indent=2),'utf-8');print(json.dumps({'completed':True,**manifest}),flush=True)
if __name__=='__main__':main()
