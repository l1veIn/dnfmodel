"""Manual action annotations and bounded CPU reference-video export."""
import bisect
import hashlib
import json
import math
import subprocess
import threading
import uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/'output/Fatfish_Action_Dashboard'
STATE=ROOT/'design/fatfish/action_catalog/manual_motion.json'
STATE_LOCK=threading.RLock()
EXPORT_LOCK=threading.Lock()
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
def read(path):return json.loads(path.read_text('utf-8'))
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
def count():return int(read(WEB/'catalog.json')['frame_count'])
def document():
    if STATE.exists():return read(STATE)
    return {'schema_version':1,'revision':0,'frame_count':count(),'clips':[],'source':'manual_editor','ani_parsed':False,'updated_at':None}
def integer(value,low,high,label):
    if type(value) is not int or not low<=value<=high:raise ValueError(f'{label}应在{low}–{high}之间')
    return value
def clip(value):
    if not isinstance(value,dict):raise ValueError('动作数据格式不正确')
    start=integer(value.get('start'),0,count()-1,'起始帧');end=integer(value.get('end'),start,count()-1,'结束帧')
    name=value.get('name','')
    if not isinstance(name,str) or not 1<=len(name.strip())<=80:raise ValueError('动作名称需填写1–80个字符')
    times=value.get('frame_ms')
    if not isinstance(times,list) or len(times)!=end-start+1:raise ValueError('逐帧时长数量与范围不匹配')
    times=[integer(t,1,10000,'每帧毫秒数') for t in times]
    ident=value.get('id') or uuid.uuid4().hex
    if not isinstance(ident,str) or not 1<=len(ident)<=80 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in ident):raise ValueError('动作编号格式不正确')
    note=value.get('note','')
    if not isinstance(note,str) or len(note)>3000:raise ValueError('备注最多3000字')
    if type(value.get('loop',True)) is not bool or type(value.get('reviewed',False)) is not bool:raise ValueError('循环和确认状态格式不正确')
    return {'id':ident,'name':name.strip(),'start':start,'end':end,'frame_ms':times,'loop':value.get('loop',True),'reviewed':value.get('reviewed',False),'note':note,'source':'manual_editor'}
class Conflict(Exception):
    def __init__(self,current):self.current=current
def save_document(payload):
    items=payload.get('clips')
    if not isinstance(items,list) or len(items)>300:raise ValueError('分段列表最多300项')
    normalized=[clip(v) for v in items]
    if len({v['id'] for v in normalized})!=len(normalized):raise ValueError('动作编号重复')
    with STATE_LOCK:
        previous=document()
        if payload.get('expected_revision')!=previous['revision']:raise Conflict(previous)
        updated={**previous,'revision':previous['revision']+1,'frame_count':count(),'clips':normalized,'updated_at':now()}
        write(STATE.parent/'manual_motion_history'/f'rev_{previous["revision"]:06d}_{uuid.uuid4().hex[:8]}.json',previous)
        write(STATE,updated)
    return updated
def export_video(payload):
    value=clip(payload.get('clip'));mode=payload.get('mode','h3_5s');scale=payload.get('scale',2)
    if mode not in ('h3_5s','single'):raise ValueError('导出模式不正确')
    if type(scale) is not int or scale not in (2,4):raise ValueError('只支持2倍或4倍尺寸')
    total=sum(value['frame_ms']);fps=24
    if mode=='h3_5s':
        length=124
        if total>length/fps*1000:raise ValueError('当前动作超过5.17秒，请选“单轮原速”或缩短片段')
    else:
        length=max(1,math.ceil(total*fps/1000))
        if length>362:raise ValueError('参考片段最长约15秒，请拆成更短的动作段')
    if not EXPORT_LOCK.acquire(blocking=False):raise ValueError('另一个参考视频正在导出，请稍后再试')
    try:
        catalog=read(WEB/'catalog.json');size=tuple(catalog['frame_dimensions']);dest_size=(size[0]*scale,size[1]*scale)
        inputs=[]
        for slot in range(value['start'],value['end']+1):
            path=(WEB/catalog['original'][str(slot)]).resolve()
            if not path.is_relative_to(WEB.resolve()) or not path.is_file():raise ValueError('原版帧文件不存在')
            inputs.append(path)
        suffix=f'{value["start"]:03d}_{value["end"]:03d}_{uuid.uuid4().hex[:10]}'
        folder=WEB/'motion-editor/exports';folder.mkdir(parents=True,exist_ok=True);dest=folder/f'reference_{suffix}.mp4'
        command=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{dest_size[0]}x{dest_size[1]}','-r','24','-i','pipe:0','-an','-c:v','libx264','-crf','12','-preset','fast','-pix_fmt','yuv420p','-movflags','+faststart',str(dest)]
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        cumulative=[];elapsed=0
        for duration in value['frame_ms']:elapsed+=duration;cumulative.append(elapsed)
        mapping=[];last_index=None;last_pixels=None
        try:
            for frame in range(length):
                t=(frame+.5)*1000/fps;source_time=t%total if value['loop'] else min(t,total-1e-6)
                index=min(bisect.bisect_right(cumulative,source_time),len(inputs)-1)
                if index!=last_index:
                    with Image.open(inputs[index]) as image:
                        base=Image.new('RGBA',size,(128,128,128,255));base.alpha_composite(image.convert('RGBA'))
                    last_pixels=base.convert('RGB').resize(dest_size,Image.Resampling.NEAREST).tobytes();last_index=index
                process.stdin.write(last_pixels);mapping.append({'video_frame':frame,'source_slot':value['start']+index,'source_time_ms':round(source_time,3)})
            process.stdin.close();error=process.stderr.read()
            if process.wait(timeout=60):raise RuntimeError(error.decode('utf-8','replace'))
        finally:
            if process.poll() is None:process.kill()
        metadata={'clip':value,'fps':fps,'frames':length,'seconds':length/fps,'dimensions':dest_size,'mode':mode,'single_cycle_ms':total,'fixed_canvas':True,'per_frame_auto_center':False,'background_rgb':[128,128,128],'alpha_output':False,'resize':'nearest neighbor','fps_resampling':'Source holds sampled at output-frame midpoint; no generated inbetweens.','short_actions':'Loop repeats or non-loop holds final frame in5.17s mode.','source_sha256':[hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs],'mapping':mapping,'created_at':now(),'ani_parsed':False}
        sidecar=dest.with_suffix('.json');write(sidecar,metadata)
        return {'video_url':'/motion-editor/exports/'+dest.name,'metadata_url':'/motion-editor/exports/'+sidecar.name,'frames':length,'fps':fps,'seconds':length/fps,'dimensions':dest_size}
    finally:EXPORT_LOCK.release()
