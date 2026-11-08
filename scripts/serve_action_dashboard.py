"""Loopback action reviews, manual motion annotations, and CPU reference exports."""
import argparse
import json
import re
import subprocess
import threading
import urllib.parse
from datetime import datetime, timezone, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import manual_motion_editor as motion_editor

ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/'output/Fatfish_Action_Dashboard'
STATE=ROOT/'design/fatfish/action_catalog/progress.json'
LOCK=threading.RLock()


def now():return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
def read(path):return json.loads(path.read_text('utf-8'))
def write(path,data):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(WEB),**kwargs)

    def log_message(self,format,*args):
        if args and isinstance(args[1] if len(args)>1 else None,int) and args[1]>=400:super().log_message(format,*args)

    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        super().end_headers()

    def send_head(self):
        # Video seeking requires byte ranges. SimpleHTTPRequestHandler otherwise
        # advertises a zero-length seekable interval in the in-app browser.
        self._video_remaining=None
        path=Path(self.translate_path(self.path)).resolve()
        if path.suffix.lower()!='.mp4' or not path.is_file():
            return super().send_head()
        if not path.is_relative_to(WEB.resolve()):
            self.send_error(403);return None
        size=path.stat().st_size;start,end=0,size-1
        requested=self.headers.get('Range')
        if requested:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested.strip())
            if not match or not any(match.groups()):
                self.send_error(416);return None
            left,right=match.groups()
            if left:
                start=int(left);end=min(int(right),size-1) if right else size-1
            else:
                count=int(right);start=max(0,size-count)
                if count==0:start=size
            if start>=size or end<start:
                self.send_response(416);self.send_header('Content-Range',f'bytes */{size}')
                self.send_header('Content-Length','0');self.end_headers();return None
        handle=path.open('rb');handle.seek(start)
        self.send_response(206 if requested else 200)
        self.send_header('Content-Type','video/mp4')
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Content-Length',str(end-start+1))
        if requested:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers();self._video_remaining=end-start+1
        return handle

    def copyfile(self,source,outputfile):
        remaining=getattr(self,'_video_remaining',None)
        if remaining is None:return super().copyfile(source,outputfile)
        try:
            while remaining:
                block=source.read(min(128*1024,remaining))
                if not block:break
                outputfile.write(block);remaining-=len(block)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            pass

    def send_json(self,value,status=200,download=False):
        content=json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(content)))
        if download:self.send_header('Content-Disposition','attachment; filename="fatfish-action-progress.json"')
        self.end_headers();self.wfile.write(content)

    def do_GET(self):
        route=urllib.parse.urlparse(self.path).path
        if route=='/api/health':return self.send_json({'app':'fatfish-action-dashboard','version':1})
        if route=='/api/project':return self.send_json({'catalog':read(WEB/'catalog.json'),'progress':read(STATE)})
        if route=='/api/export':return self.send_json({'catalog':read(WEB/'catalog.json'),'progress':read(STATE),'exported_at':now()},download=True)
        if route=='/api/motion-editor':return self.send_json(motion_editor.document())
        return super().do_GET()

    def do_POST(self):
        route=urllib.parse.urlparse(self.path).path
        if route in ('/api/motion-editor','/api/motion-editor/export-video'):
            origin=self.headers.get('Origin')
            if origin:
                source=urllib.parse.urlparse(origin)
                if source.hostname not in ('127.0.0.1','localhost') or source.port!=self.server.server_port:
                    return self.send_json({'error':'只接受当前本地编辑页的保存请求'},403)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=2*1024*1024:raise ValueError('编辑数据过长或为空')
                payload=json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(payload,dict):raise ValueError('编辑数据格式不正确')
                if route.endswith('/export-video'):return self.send_json(motion_editor.export_video(payload))
                return self.send_json({'saved':True,'document':motion_editor.save_document(payload)})
            except motion_editor.Conflict as error:
                return self.send_json({'error':'另一页面已保存新版本，请先重新加载已保存分段；当前草稿仍在。','document':error.current},409)
            except (ValueError,UnicodeDecodeError,json.JSONDecodeError) as error:
                return self.send_json({'error':str(error)},400)
            except (OSError,RuntimeError,subprocess.TimeoutExpired) as error:
                return self.send_json({'error':'导出失败：'+str(error)},500)
        if not route.startswith('/api/review/'):
            return self.send_json({'error':'接口不存在'},404)
        origin=self.headers.get('Origin')
        if origin:
            url=urllib.parse.urlparse(origin)
            if url.hostname not in ('127.0.0.1','localhost') or url.port!=self.server.server_port:
                return self.send_json({'error':'只接受当前本地面板的保存请求'},403)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=24000:raise ValueError('保存内容过长或为空')
            body=json.loads(self.rfile.read(length).decode('utf-8'))
            ident=urllib.parse.unquote(route[len('/api/review/'):])
            catalog=read(WEB/'catalog.json')
            clip=next((c for c in catalog['clips'] if c['id']==ident),None)
            if clip is None:return self.send_json({'error':'片段不存在'},404)
            decision=body.get('decision','pending')
            if decision not in ('pending','approved','changes_requested'):raise ValueError('验收状态无效')
            if decision=='approved' and clip.get('kind')=='unclassified':raise ValueError('未归类帧位只保存备注，不能作为完整动作验收')
            if decision=='approved' and not clip['complete']:raise ValueError('连续帧尚未补齐，不能将整段标为已通过')
            note=body.get('note','')
            if not isinstance(note,str) or len(note)>4000:raise ValueError('备注最多4000字')
            with LOCK:
                progress=read(STATE)
                if body.get('expected_revision')!=progress['revision']:
                    return self.send_json({'error':'进度已更新，请刷新后再保存','progress':progress},409)
                record={'decision':decision,'note':note.strip(),'updated_at':now(),'source':'local_dashboard'}
                progress['reviews'][ident]=record;progress['revision']+=1
                progress['events'].append({'clip_id':ident,**record,'revision':progress['revision']})
                write(STATE,progress)
            return self.send_json({'saved':True,'progress':progress})
        except (ValueError,UnicodeDecodeError,json.JSONDecodeError) as e:
            return self.send_json({'error':str(e)},400)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8790);args=ap.parse_args()
    if not (WEB/'index.html').is_file():raise SystemExit('先运行 scripts/build_action_dashboard.py')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Fatfish action dashboard: http://127.0.0.1:{args.port}/',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
