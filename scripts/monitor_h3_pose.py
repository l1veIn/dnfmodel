"""Guard only this experiment against exhausting Windows commit memory."""
import json
import time
import requests
from fatfish_h3_walk import memory
from fatfish_h3_pose_walk import RUN,read

job=read(RUN/'job.json');ident=job['stages'][0]['prompt_id']
with (RUN/'memory_guard.jsonl').open('a',encoding='utf-8') as output:
    for i in range(240):
        sample={'time':time.time(),**memory()}
        output.write(json.dumps(sample)+'\n');output.flush()
        if i%6==0:print(json.dumps(sample),flush=True)
        history=requests.get('http://127.0.0.1:8188/history/'+ident,timeout=15).json()
        if ident in history:
            print(json.dumps({'guard_finished':True,**sample}),flush=True);break
        if sample['commit_available_gib']<1.25 or sample['ram_available_gib']<1.5:
            queue=requests.get('http://127.0.0.1:8188/queue',timeout=15).json()
            running=queue.get('queue_running',[])
            if len(running)==1 and running[0][1]==ident:
                requests.post('http://127.0.0.1:8188/interrupt',json={},timeout=15).raise_for_status()
                print(json.dumps({'interrupted_own_task_for_memory':ident,**sample}),flush=True)
                break
        time.sleep(5)
