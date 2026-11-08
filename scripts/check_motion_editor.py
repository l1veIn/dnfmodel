"""Exercise save conflicts, timing export, and protected artifacts without adding user labels."""
import hashlib,json,subprocess,threading,urllib.request,urllib.error,uuid
from pathlib import Path
from http.server import ThreadingHTTPServer
import manual_motion_editor as motion
from serve_action_dashboard import Handler
ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'validation/manual_motion_editor'/uuid.uuid4().hex[:10]
QA.mkdir(parents=True)
protected=[ROOT/'design/fatfish/action_catalog/progress.json',ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK']
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
motion.STATE=QA/'fixture_manual_motion.json'
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
base=f'http://127.0.0.1:{server.server_port}'
def request(path,body=None,origin=None):
    headers={'Content-Type':'application/json'}
    if origin:headers['Origin']=origin
    req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
    try:
        with urllib.request.urlopen(req) as response:return response.status,json.load(response)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
checks={}
try:
    item={'id':'qa_fixture','name':'QA fixture only','start':0,'end':9,'frame_ms':[50,100,150,100,100,50,100,150,100,100],'loop':True,'reviewed':False}
    status,initial=request('/api/motion-editor');assert status==200 and initial['clips']==[]
    status,saved=request('/api/motion-editor',{'expected_revision':0,'clips':[item]},base);assert status==200 and saved['document']['revision']==1
    status,reloaded=request('/api/motion-editor');assert reloaded['clips'][0]['frame_ms']==item['frame_ms'];checks['save_and_reload']=True
    status,conflict=request('/api/motion-editor',{'expected_revision':0,'clips':[]},base);assert status==409 and conflict['document']['revision']==1;checks['revision_conflict']=True
    status,_=request('/api/motion-editor',{'expected_revision':1,'clips':[]},'https://example.com');assert status==403;checks['foreign_origin_rejected']=True
    for bad in [{**item,'end':174},{**item,'frame_ms':[100]},{**item,'frame_ms':[True]*10}]:
        status,_=request('/api/motion-editor',{'expected_revision':1,'clips':[bad]},base);assert status==400
    assert request('/api/motion-editor')[1]['revision']==1;checks['invalid_edits_preserve_state']=True
    export=motion.export_video({'clip':item,'mode':'h3_5s','scale':2})
    video=motion.WEB/export['video_url'].lstrip('/');sidecar=motion.read(motion.WEB/export['metadata_url'].lstrip('/'))
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-of','json',str(video)]))
    stream=probe['streams'][0];assert stream['width']==384 and stream['height']==320 and int(stream['nb_read_frames'])==124 and stream['r_frame_rate']=='24/1'
    subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],check=True,capture_output=True)
    assert len(sidecar['mapping'])==124 and sidecar['mapping'][0]['source_slot']==0 and sidecar['mapping'][1]['source_slot']==1
    assert sidecar['mapping'][24]['source_slot']==0 and sidecar['per_frame_auto_center'] is False
    with urllib.request.urlopen(urllib.request.Request(base+export['video_url'],headers={'Range':'bytes=0-63'})) as response:
        assert response.status==206 and len(response.read())==64
    checks['cpu_video_124_frames_fixed_canvas_and_timing']=True;checks['video_byte_range_seek']=True
    status,_=request('/api/motion-editor',{'expected_revision':1,'clips':[]},base);assert status==200 and request('/api/motion-editor')[1]['clips']==[]
    assert len(list((QA/'manual_motion_history').glob('*.json')))==2;checks['history_backup']=True
finally:server.shutdown();server.server_close()
after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected};assert before==after;checks['walk_review_and_npk_unchanged']=True
report={'checks':checks,'qa_export':export,'protected_sha256':after,'fixture_state':str(motion.STATE),'note':'Fixture labels are not written to the user annotation file.'}
(QA/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'passed':len(checks),'report':str(QA/'report.json'),'qa_export':export},ensure_ascii=False))
