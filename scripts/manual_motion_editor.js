'use strict';
const $=id=>document.getElementById(id);
const KEY='fatfish-manual-motion-draft-v1';
const state={catalog:null,doc:null,draft:null,cursor:0,elapsed:0,playing:false,lastTick:null,dirty:true,anchor:0,drag:null,timeDrag:null,images:new Map(),deleted:null,busy:false};
const pad=n=>String(n).padStart(3,'0');
const total=()=>state.draft.frame_ms.reduce((a,b)=>a+b,0);
const clone=v=>JSON.parse(JSON.stringify(v));
const message=(text,error=false)=>{$('message').textContent=text;$('message').style.color=error?'#ffb3a9':'var(--accent)';};
function draftDefault(start=0,end=9){return {id:null,name:'',start,end,frame_ms:Array(end-start+1).fill(100),loop:true,reviewed:false,note:''};}
function validDraft(d){return d&&Number.isInteger(d.start)&&Number.isInteger(d.end)&&d.start>=0&&d.end>=d.start&&d.end<state.catalog.frame_count&&Array.isArray(d.frame_ms)&&d.frame_ms.length===d.end-d.start+1&&d.frame_ms.every(t=>Number.isInteger(t)&&t>=1&&t<=10000);}
function storeDraft(){try{localStorage.setItem(KEY,JSON.stringify({draft:state.draft,savedAt:new Date().toISOString()}));}catch{}}
function changed(){state.dirty=true;$('draft-state').textContent='有未保存修改';storeDraft();}
function pause(){state.playing=false;state.lastTick=null;$('play').textContent='播放';}
function cumulativeBefore(index){return state.draft.frame_ms.slice(0,index).reduce((a,b)=>a+b,0);}
function seek(index){pause();state.cursor=Math.max(0,Math.min(state.draft.frame_ms.length-1,index));state.elapsed=cumulativeBefore(state.cursor);paint();}
function paint(){
  const d=state.draft,slot=d.start+state.cursor;
  $('current-slot').textContent='#'+pad(slot);$('frame-counter').textContent=`第 ${state.cursor+1} / ${d.frame_ms.length} 帧 · IMG ${slot}`;
  $('time-counter').textContent=`${Math.floor(state.elapsed)} / ${total()} ms`;
  $('scrub').value=state.cursor;
  if(document.activeElement!==$('frame-ms')&&!state.timeDrag)$('frame-ms').value=d.frame_ms[state.cursor];
  const original='/'+state.catalog.original[String(slot)];
  if($('original-image').getAttribute('src')!==original)$('original-image').src=original;
  const fish=state.catalog.fatfish[String(slot)];$('fatfish-image').hidden=!fish;$('missing').hidden=!!fish;
  $('fatfish-label').textContent=fish?'已有素材':'未制作';if(fish&&$('fatfish-image').getAttribute('src')!=='/'+fish)$('fatfish-image').src='/'+fish;
  document.querySelectorAll('.frame-cell').forEach(el=>el.classList.toggle('current',Number(el.dataset.slot)===slot));
  document.querySelectorAll('.time-cell').forEach((el,i)=>el.classList.toggle('active',i===state.cursor));
}
function renderTiming(){
  const strip=$('timing-strip'),left=strip.scrollLeft;strip.replaceChildren();
  state.draft.frame_ms.forEach((ms,i)=>{
    const cell=document.createElement('div');cell.className='time-cell';cell.style.width=Math.max(39,Math.min(140,ms/2))+'px';cell.dataset.index=i;cell.tabIndex=0;cell.setAttribute('role','button');cell.setAttribute('aria-label',`帧 ${state.draft.start+i}，${ms} 毫秒`);
    const label=document.createElement('span');label.textContent=`${pad(state.draft.start+i)}\n${ms}ms`;label.style.whiteSpace='pre-line';cell.append(label);
    const handle=document.createElement('span');handle.className='time-handle';handle.title='左右拖动调整时长';handle.dataset.handle=i;cell.append(handle);
    cell.addEventListener('click',e=>{if(!e.target.classList.contains('time-handle'))seek(i);});cell.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();seek(i);}});strip.append(cell);
  });strip.scrollLeft=left;paint();
}
function renderRange(){
  const d=state.draft;$('start').value=d.start;$('end').value=d.end;$('range-label').textContent=`${pad(d.start)}–${pad(d.end)} · ${d.end-d.start+1} 帧`;$('scrub').max=d.end-d.start;
  document.querySelectorAll('.frame-cell').forEach(el=>{const n=Number(el.dataset.slot);el.classList.toggle('selected',n>=d.start&&n<=d.end);});renderTiming();
}
function setRange(a,b){
  const old=state.draft;const start=Math.max(0,Math.min(a,b,state.catalog.frame_count-1)),end=Math.max(start,Math.min(Math.max(a,b),state.catalog.frame_count-1));
  pause();const fallback=Math.max(1,Math.min(10000,Math.round(Number($('bulk-ms').value)||100)));
  old.frame_ms=Array.from({length:end-start+1},(_,i)=>{const slot=start+i;return slot>=old.start&&slot<=old.end?old.frame_ms[slot-old.start]:fallback;});old.start=start;old.end=end;old.reviewed=false;$('reviewed').checked=false;state.cursor=0;state.elapsed=0;changed();renderRange();
}
function loadDraft(d,dirty=false){pause();state.draft=clone(d);state.cursor=0;state.elapsed=0;state.anchor=d.start;state.dirty=dirty;$('name').value=d.name||'';$('note').value=d.note||'';$('loop').checked=d.loop;$('reviewed').checked=d.reviewed;$('bulk-ms').value=d.frame_ms[0];$('draft-state').textContent=dirty?'恢复的未保存草稿':'已保存';renderRange();renderSaved();}
function renderSaved(){
  const list=$('saved-list');list.replaceChildren();$('saved-count').textContent=state.doc.clips.length+' 段已保存';
  for(const item of [...state.doc.clips].sort((a,b)=>a.start-b.start||a.end-b.end)){
    const row=document.createElement('div');row.className='saved-item'+(state.draft?.id===item.id?' active':'');
    const load=document.createElement('button');load.className='load-clip';const name=document.createElement('strong');name.textContent=item.name;const meta=document.createElement('small');meta.textContent=`${pad(item.start)}–${pad(item.end)} · ${item.frame_ms.reduce((a,b)=>a+b,0)} ms · ${item.reviewed?'已人工确认':'待确认'}`;load.append(name,meta);load.onclick=()=>{storeDraft();loadDraft(item);message('已载入，可继续修改后保存。');};
    const remove=document.createElement('button');remove.className='remove-clip';remove.textContent='移除';remove.setAttribute('aria-label','移除 '+item.name);remove.onclick=()=>removeClip(item);row.append(load,remove);list.append(row);
  }
  document.querySelectorAll('.frame-cell').forEach(el=>{const slot=Number(el.dataset.slot);el.classList.toggle('annotated',state.doc.clips.some(c=>slot>=c.start&&slot<=c.end));});
}
async function post(url,payload){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await r.json();if(!r.ok){if(r.status===409&&data.document){state.doc=data.document;renderSaved();}throw new Error(data.error||data.message||'操作失败');}return data;}
async function persist(clips){if(state.busy)throw new Error('正在保存，请稍等');state.busy=true;$('save').disabled=true;try{const r=await post('/api/motion-editor',{expected_revision:state.doc.revision,clips});state.doc=r.document;renderSaved();return r.document;}finally{state.busy=false;$('save').disabled=false;}}
async function saveClip(){
  if(!$('name').value.trim()){message('请先填写你确认的动作名称。',true);$('name').focus();return;}
  const draft=clone(state.draft);draft.name=$('name').value.trim();draft.id=draft.id||crypto.randomUUID();const before=JSON.stringify(state.draft);
  try{const clips=state.doc.clips.filter(c=>c.id!==draft.id);clips.push(draft);await persist(clips);if(before===JSON.stringify(state.draft)){state.draft=draft;state.dirty=false;$('draft-state').textContent='已保存';storeDraft();}message('已保存到本机 · '+new Date().toLocaleTimeString());renderSaved();}catch(e){message(e.message+'；草稿已保留。',true);}
}
async function removeClip(item){try{await persist(state.doc.clips.filter(c=>c.id!==item.id));state.deleted=item;$('undo-delete').hidden=false;if(state.draft.id===item.id){state.draft.id=null;changed();}message('已移除“'+item.name+'”，可以撤回。');}catch(e){message(e.message,true);}}
function newDraft(next=false){storeDraft();const start=next?Math.min(state.catalog.frame_count-1,state.draft.end+1):0;const length=state.draft.end-state.draft.start;loadDraft(draftDefault(start,Math.min(state.catalog.frame_count-1,start+(next?length:9))),true);$('draft-state').textContent='新分段草稿';message('划选范围并命名后保存；上一份草稿可恢复。');}
function restore(){try{const saved=JSON.parse(localStorage.getItem(KEY));if(!validDraft(saved?.draft))throw new Error('没有可恢复的草稿');loadDraft(saved.draft,true);message('已恢复草稿。');}catch(e){message(e.message,true);}}
function bind(){
  $('start').onchange=()=>{const n=Math.round(Number($('start').value));if(Number.isFinite(n))setRange(Math.max(0,Math.min(173,n)),Math.max(Math.max(0,Math.min(173,n)),state.draft.end));};
  $('end').onchange=()=>{const n=Math.round(Number($('end').value));if(Number.isFinite(n))setRange(Math.min(Math.max(0,Math.min(173,n)),state.draft.start),Math.max(0,Math.min(173,n)));};
  $('new-clip').onclick=()=>newDraft();$('next-clip').onclick=()=>newDraft(true);$('restore-draft').onclick=restore;
  for(const id of ['name','note'])$(id).oninput=()=>{state.draft[id]=$(id).value;changed();};
  for(const id of ['loop','reviewed'])$(id).onchange=()=>{state.draft[id]=$(id).checked;changed();};
  $('apply-ms').onclick=()=>{const n=Number($('bulk-ms').value);if(!Number.isInteger(n)||n<1||n>10000){message('时长应为 1–10000 ms 的整数。',true);return;}pause();state.draft.frame_ms.fill(n);state.elapsed=cumulativeBefore(state.cursor);state.draft.reviewed=false;$('reviewed').checked=false;changed();renderTiming();};
  $('frame-ms').onfocus=pause;
  $('frame-ms').oninput=()=>{const n=Number($('frame-ms').value);if(!Number.isInteger(n)||n<1||n>10000)return;pause();state.draft.frame_ms[state.cursor]=n;state.elapsed=cumulativeBefore(state.cursor);state.draft.reviewed=false;$('reviewed').checked=false;changed();renderTiming();};
  $('save').onclick=saveClip;$('undo-delete').onclick=async()=>{if(!state.deleted)return;try{await persist([...state.doc.clips.filter(c=>c.id!==state.deleted.id),state.deleted]);state.deleted=null;$('undo-delete').hidden=true;message('已撤回移除。');}catch(e){message(e.message,true);}};
  $('play').onclick=()=>{if(state.playing){pause();return;}if(state.elapsed>=total())state.elapsed=0;state.playing=true;state.lastTick=null;$('play').textContent='暂停';};
  $('previous').onclick=()=>seek(state.cursor-1);$('next').onclick=()=>seek(state.cursor+1);$('scrub').oninput=()=>seek(Number($('scrub').value));
  $('background').onchange=()=>document.querySelectorAll('.stage').forEach(s=>s.className='stage '+$('background').value);$('guides').onchange=()=>document.body.classList.toggle('no-guides',!$('guides').checked);
  $('download-json').onclick=()=>{const blob=new Blob([JSON.stringify(state.doc,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='female_mage_manual_motion.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
  $('export-video').onclick=exportVideo;
  document.addEventListener('keydown',e=>{if(/^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(e.target.tagName))return;if(e.code==='Space'){e.preventDefault();$('play').click();}if(e.key==='ArrowLeft'){e.preventDefault();seek(state.cursor-1);}if(e.key==='ArrowRight'){e.preventDefault();seek(state.cursor+1);}});
  $('frame-grid').addEventListener('pointerdown',e=>{const el=e.target.closest('[data-slot]');if(!el||e.button!==0)return;e.preventDefault();const slot=Number(el.dataset.slot);if(!e.shiftKey)state.anchor=slot;state.drag={pointer:e.pointerId,anchor:state.anchor};setRange(state.anchor,slot);});
  document.addEventListener('pointermove',e=>{
    if(state.drag){const grid=$('frame-grid'),bounds=grid.getBoundingClientRect();if(e.clientY>bounds.bottom-24)grid.scrollTop+=15;if(e.clientY<bounds.top+24)grid.scrollTop-=15;const el=document.elementFromPoint(e.clientX,e.clientY)?.closest('#frame-grid [data-slot]');if(el){const n=Number(el.dataset.slot);const a=Math.min(state.drag.anchor,n),b=Math.max(state.drag.anchor,n);if(a!==state.draft.start||b!==state.draft.end)setRange(a,b);}}
    if(state.timeDrag){const t=state.timeDrag;const ms=Math.max(5,Math.min(10000,Math.round((t.ms+(e.clientX-t.x)*2)/5)*5));state.draft.frame_ms[t.index]=ms;state.cursor=t.index;state.elapsed=cumulativeBefore(t.index);const cell=$('timing-strip').children[t.index];cell.style.width=Math.max(39,Math.min(140,ms/2))+'px';cell.firstChild.textContent=`${pad(state.draft.start+t.index)}\n${ms}ms`;$('frame-ms').value=ms;paint();}
  });
  document.addEventListener('pointerup',()=>{state.drag=null;if(state.timeDrag){state.timeDrag=null;state.draft.reviewed=false;$('reviewed').checked=false;changed();renderTiming();}});window.addEventListener('blur',()=>{state.drag=null;state.timeDrag=null;});
  $('timing-strip').addEventListener('pointerdown',e=>{const h=e.target.closest('[data-handle]');if(!h)return;e.preventDefault();pause();const i=Number(h.dataset.handle);state.timeDrag={index:i,x:e.clientX,ms:state.draft.frame_ms[i]};h.setPointerCapture(e.pointerId);});
}
async function exportVideo(){
  const button=$('export-video'),result=$('export-result');button.disabled=true;result.textContent='正在用 CPU 导出参考视频…';
  try{const clip={...clone(state.draft),name:state.draft.name.trim()||'未命名参考片段'};const data=await post('/api/motion-editor/export-video',{clip,mode:$('export-mode').value,scale:Number($('export-scale').value)});result.replaceChildren();const info=document.createElement('p');info.textContent=`已导出 ${data.frames} 帧 · ${data.fps} fps · ${data.seconds.toFixed(2)} 秒 · ${data.dimensions.join(' × ')}`;result.append(info);for(const [url,label] of [[data.video_url,'↓ 下载 MP4'],[data.metadata_url,'↓ 配时与逐帧映射']]){const a=document.createElement('a');a.href=url;a.textContent=label;a.download='';result.append(a);}const video=document.createElement('video');video.src=data.video_url;video.controls=true;video.loop=state.draft.loop;video.muted=true;result.append(video);}catch(e){result.textContent=e.message;}finally{button.disabled=false;}
}
function tick(ts){
  if(state.playing&&state.draft){if(state.lastTick!==null)state.elapsed+=(ts-state.lastTick)*Number($('speed').value);state.lastTick=ts;const duration=total();if(state.elapsed>=duration){if(state.draft.loop)state.elapsed%=duration;else{state.elapsed=duration;pause();}}let sum=0;state.cursor=state.draft.frame_ms.length-1;for(let i=0;i<state.draft.frame_ms.length;i++){sum+=state.draft.frame_ms[i];if(state.elapsed<sum){state.cursor=i;break;}}paint();}requestAnimationFrame(tick);
}
async function init(){
  try{const [catalog,doc]=await Promise.all([fetch('/catalog.json').then(r=>{if(!r.ok)throw Error('素材目录读取失败');return r.json();}),fetch('/api/motion-editor').then(r=>{if(!r.ok)throw Error('编辑接口未启动');return r.json();})]);state.catalog=catalog;state.doc=doc;const grid=$('frame-grid');let loaded=0;
    for(let slot=0;slot<catalog.frame_count;slot++){const button=document.createElement('button');button.className='frame-cell';button.dataset.slot=slot;button.setAttribute('aria-label','原版帧 '+slot);const img=document.createElement('img');img.src='/'+catalog.original[String(slot)];img.alt='';img.draggable=false;img.onload=()=>{$('image-status').textContent=`原图 ${++loaded} / ${catalog.frame_count}`;};const label=document.createElement('span');label.textContent=pad(slot);button.append(img,label);button.addEventListener('click',e=>{if(e.detail===0){state.anchor=e.shiftKey?state.anchor:slot;setRange(state.anchor,slot);}});grid.append(button);}
    bind();loadDraft(draftDefault(),true);$('draft-state').textContent='未保存草稿';$('connection').textContent='● 已连接本机 · 自动备份草稿';requestAnimationFrame(tick);
  }catch(e){$('connection').textContent='连接失败';message(e.message+'。请从本机 8791 编辑页打开。',true);}
}init();
