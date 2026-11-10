// Boundary checks for canvas coordinates, manual timing, scene bounds and asynchronous request invalidation.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const documentListeners = {};
const context = vm.createContext({
  window: {addEventListener() {}}, document: {addEventListener(name, handler) { documentListeners[name] = handler; }},
  clearTimeout, setTimeout, location: {hash: "#/studio"}, $: () => null
});
vm.runInContext(fs.readFileSync(path.join(__dirname, "../scripts/workbench/static/studio.js"), "utf8"), context);
const run = source => vm.runInContext(source, context);
const json = source => JSON.parse(JSON.stringify(run(source)));

// A CSS-scaled or scrolled canvas must still target the original world pixel, including negative coordinates.
assert.deepEqual(json("stPixelPoint(110, 70, {left:10,top:20,width:200,height:100}, [-20,-10,80,40])"), {x: 30, y: 15});
assert.deepEqual(json("stPixelPoint(10, 20, {left:10,top:20,width:200,height:100}, [-20,-10,80,40])"), {x: -20, y: -10});
assert.deepEqual(json("stPixelPoint(209.9, 119.9, {left:10,top:20,width:200,height:100}, [-20,-10,80,40])"), {x: 79, y: 39});

// Delays are relative to the chosen action, not absolute rig frame numbers; non-looping skills disappear at the end.
run("var effect = {start:2,fps:15,loop:false}");
assert.equal(run("stEffectFrame(effect, 50, 50, 10, 3)"), null);
assert.equal(run("stEffectFrame(effect, 52, 50, 10, 3)"), 0);
assert.equal(run("stEffectFrame(effect, 53, 50, 10, 3)"), 1);
assert.equal(run("stEffectFrame(effect, 54, 50, 10, 3)"), null);
assert.equal(run("stEffectFrame({...effect,loop:true}, 54, 50, 10, 3)"), 0);

// Effect origin, scale and displacement must share the same world coordinates as the character.
run("T.plan={box:[-10,-20,30,40]}; T.scene={effects:[{path:'test',source:'official',x:100,y:-50,scale:2}]}; T.effectMeta.set('test',{box:[-10,-10,20,20]})");
assert.deepEqual(json("stSceneBox()"), [-10, -70, 140, 40]);

// Requests hold snapshots: a slider or brush changing while a request is pending cannot mutate its submitted recipe.
run("T.role='gunner_at'; T.outfit={coat:'coat1'}; T.customization={dyes:{coat:{hue:30}},pixels:[{frame:1,x:2,y:3,color:'#ffffffff'}]}; var payload=stPayload(); T.customization.dyes.coat.hue=60; T.customization.pixels[0].x=20; T.outfit.coat='coat2'");
assert.equal(run("payload.customization.dyes.coat.hue"), 30);
assert.equal(run("payload.customization.pixels[0].x"), 2);
assert.equal(run("payload.outfit.coat"), "coat1");

// Typing an offset must update the save recipe immediately, even if the field has not blurred yet.
run("var layoutCalls=0; stLayout=()=>{layoutCalls++}; var numberListeners={}; var numberInput={value:'0',addEventListener:(event,handler)=>{numberListeners[event]=handler}}; var offset={x:0}; stBindEffectNumber(numberInput,offset,'x',-4096,4096); numberInput.value='80'; numberListeners.input()");
assert.equal(run("offset.x"), 80);
assert.equal(run("layoutCalls"), 1);
run("numberInput.value=''; numberListeners.input()");
assert.equal(run("offset.x"), 80);
run("numberInput.value='-24'; numberListeners.input()");
assert.equal(run("offset.x"), -24);
run("numberInput.value='9000'; numberListeners.input(); numberListeners.change()");
assert.equal(run("offset.x"), 4096);
assert.equal(run("numberInput.value"), 4096);

// Switching routes invalidates every in-flight read that could otherwise replace the next page's state.
run("var before=[T.page,T.roleRequest,T.composeRequest,T.pickerRequest,T.skillRequest]; T.busy=true; T.stroke={}; stCleanup()");
assert.deepEqual(json("[T.page,T.roleRequest,T.composeRequest,T.pickerRequest,T.skillRequest].map((x,i)=>x-before[i])"), [1, 1, 1, 1, 1]);
assert.equal(run("T.busy"), false);
assert.equal(run("T.stroke"), null);

(async () => {
  // Exercise the production timer, not only the frame arithmetic: a four-frame actor
  // loops several times while a delayed nineteen-frame effect reaches its last frame.
  run(`var controls = {stFps:{value:'10'},stPixelMode:{value:'view'},stCanvas:{},
    stSceneTime:{},stSceneClock:{},stEffectState:{},stPixelCount:{},stUndo:{},stRedo:{},
    stPixelColor:{value:'#ffffff'},stColorFrom:{value:'#ffffff'},stColorTo:{value:'#0000ff'},stColorTolerance:{value:'0'},
    stDyeSlot:{value:'skin'},stSampleInfo:{textContent:''},stBrush:{value:'1'},stPixelGrid:{checked:false}};
    $ = id => controls[id] || null; var timers = [], shown = [], actor = [];
    setTimeout = fn => {timers.push(fn);return timers.length}; clearTimeout = () => {};
    stLoadFullFrame = async () => {}; toast = () => {};
    T.start=50;T.end=53;T.k=50;T.sceneTick=0;T.stroke=null;T.scene={effects:[{path:'long',source:'official',start:8,fps:15,loop:false,enabled:true}]};
    T.effectMeta.set('long',{frames:19}); T.effectPick=0;
    stDraw = () => {shown.push(stEffectFrame(T.scene.effects[0],T.sceneTick,0,10,19));actor.push(T.k)};
    stPlay(true);for(var i=0;i<20;i++)timers.shift()();stPlay(false);`);
  assert.equal(run("T.sceneTick"), 20);
  assert.equal(run("shown.includes(18)"), true, "delayed skill must reach its last frame");
  assert.equal(run("actor.every(k=>k>=50&&k<=53)"), true);
  assert.equal(run("stSceneLength()"), 21);
  run("T.scene.effects[0].enabled=false");
  assert.equal(run("stSceneLength()"), 4, "hidden layers cannot extend the timeline");
  assert.equal(run("stEffectFrame(T.scene.effects[0],20,0,10,19)"), null);
  run("T.scene.effects[0].enabled=true;T.scene.effects[0].start=9999;T.sceneTick=0;stTimelineStatus()");
  assert.equal(run("stSceneLength()"), 6000);
  assert.match(run("controls.stSceneClock.textContent"), /上限/);
  assert.match(run("controls.stEffectState.textContent"), /出场时间超出/);

  // Saved playback overrides the role's first action, and layer ordering retains
  // the selected object and only changes its order inside the same foreground group.
  assert.deepEqual(json("stPlayback({playback:{start:58,end:61,fps:7}},143,{start:0,end:3})"), {start:58,end:61,fps:7});
  run("controls.stFps.value='7';T.start=58;T.end=61;T.scene={effects:[{path:'a',front:true},{path:'b',front:false},{path:'c',front:true,enabled:false}]}; stRememberPlayback();renderEffects=()=>{};stDraw=()=>{};stMoveEffect(0,1)");
  assert.deepEqual(json("T.scene.playback"), {start:58,end:61,fps:7});
  assert.deepEqual(json("T.scene.effects.map(e=>e.path)"), ['c','b','a']);
  assert.equal(run("T.effectPick"), 2);
  assert.equal(run("T.scene.effects[0].enabled"), false);

  // Blend selection is local to each effect draw. A legacy layer explicitly uses
  // normal compositing, even after an additive layer or an interrupted draw.
  run(`controls.stPixelMode.value='view';T.sceneTick=0;T.viewBox=[0,0,10,10];
    T.effectMeta.set('blend',{frames:1,box:[0,0,10,10],atlas:{cols:1,cw:10,ch:10},mods:[]});
    var additive={path:'blend',source:'official',start:0,fps:15,loop:false,front:true,scale:1,x:0,y:0,opacity:.6,blend:'add'};
    T.effectImages.set(stEffectKey(additive),{naturalWidth:10});
    var blendStack=[],blendDraws=[],blendCtx={globalAlpha:.75,globalCompositeOperation:'multiply',
      save(){blendStack.push([this.globalAlpha,this.globalCompositeOperation])},
      restore(){[this.globalAlpha,this.globalCompositeOperation]=blendStack.pop()},
      drawImage(){blendDraws.push([this.globalAlpha,this.globalCompositeOperation])}};
    stDrawEffect(blendCtx,additive,true,1,1);stDrawEffect(blendCtx,{...additive,blend:undefined,opacity:.3},true,1,1);`);
  assert.deepEqual(json("blendDraws"), [[.6,'lighter'],[.3,'source-over']]);
  assert.deepEqual(json("[blendCtx.globalAlpha,blendCtx.globalCompositeOperation,blendStack.length]"), [.75,'multiply',0]);
  run("blendCtx.drawImage=()=>{throw Error('interrupted draw')}");
  assert.throws(() => run("stDrawEffect(blendCtx,additive,true,1,1)"), /interrupted draw/);
  assert.deepEqual(json("[blendCtx.globalAlpha,blendCtx.globalCompositeOperation,blendStack.length]"), [.75,'multiply',0]);

  // A pen gesture owns a single pointer, frame and colour/width/coordinate snapshot.
  run(`T.k=10;T.plan={key:'pixels',box:[0,0,10,10],atlas:{scale:1}};T.viewBox=[0,0,10,10];
    T.customization={dyes:{skin:{hue:30}},pixels:[{frame:3,x:8,y:8,color:'#112233ff'}]};T.undo=[];T.redo=[];
    controls.stPixelMode.value='paint';controls.stPixelColor.value='#ff0000';controls.stBrush.value='1';
    refresh=async()=>{T.pendingPixels=[]};
    stBeginStroke(7,{x:1,y:1},{left:0,top:0,width:100,height:100});
    var firstStroke=T.stroke;stBeginStroke(9,{x:8,y:8},{left:0,top:0,width:100,height:100});
    T.k=11;T.viewBox=[100,100,110,110];controls.stPixelColor.value='#0000ff';controls.stBrush.value='5';
    stMoveStroke(9,20,10);stMoveStroke(7,20,10);`);
  assert.equal(run("T.stroke===firstStroke"), true);
  assert.deepEqual(json("[...T.stroke.points.values()]"), [
    {frame:10,x:1,y:1,color:'#ff0000ff'}, {frame:10,x:2,y:1,color:'#ff0000ff'}]);
  assert.equal(await run("stEndStroke(9)"), false);
  assert.equal(await run("stEndStroke(7)"), true);
  const afterStroke = json("T.customization.pixels");
  assert.equal(afterStroke.length, 3);
  await run("stUndoPixel()");
  assert.deepEqual(json("T.customization.pixels"), [{frame:3,x:8,y:8,color:'#112233ff'}]);
  assert.deepEqual(json("T.customization.dyes"), {skin:{hue:30}});
  await run("stRedoPixel()");
  assert.deepEqual(json("T.customization.pixels"), afterStroke);

  // Cancel (including a foreign pointer's cancel) cannot alter pixels or history.
  run("T.viewBox=[0,0,10,10];controls.stBrush.value='1';var historyLength=T.undo.length;stBeginStroke(7,{x:4,y:4},{left:0,top:0,width:100,height:100})");
  assert.equal(run("stCancelStroke(9)"), false);
  assert.equal(run("stCancelStroke(7)"), true);
  assert.deepEqual(json("T.customization.pixels"), afterStroke);
  assert.equal(run("T.undo.length"), run("historyLength"));
  await run("stUndoPixel()");
  run("stBeginStroke(7,{x:5,y:5},{left:0,top:0,width:100,height:100})");
  await run("stEndStroke(7)");
  assert.equal(run("T.redo.length"), 0, "a new committed stroke invalidates redo");

  // Over-cap gestures are rejected as a whole, preserving other frames and history.
  run(`T.plan.box=[0,0,3000,2];T.viewBox=T.plan.box.slice();
    T.customization.pixels=Array.from({length:2000},(_,x)=>({frame:2,x,y:0,color:'#ffffffff'}));
    var capBefore=JSON.stringify(T.customization.pixels),capUndo=T.undo.length;
    stBeginStroke(7,{x:0,y:1},{left:0,top:0,width:3000,height:2});`);
  await assert.rejects(run("stEndStroke(7)"), /2000/);
  assert.equal(run("JSON.stringify(T.customization.pixels)"), run("capBefore"));
  assert.equal(run("T.undo.length"), run("capUndo"));
  assert.equal(run("T.pendingPixels.length"), 0);
  for (const zoom of [1,4,12]) {
    assert.deepEqual(json(`stPixelPoint(${32*zoom-80},${26*zoom-120},{left:-80,top:-120,width:${100*zoom},height:${60*zoom}},[-20,-10,80,50])`), {x:12,y:16});
  }

  // Actual pointer binding keeps displayed-pixel sampling separate from dye source sampling.
  run(`controls.stCanvas={listeners:{},addEventListener(name,fn){this.listeners[name]=fn},focus(){},
    getBoundingClientRect(){return {left:0,top:0,width:100,height:100}},setPointerCapture(){}};
    controls.stPixelMode.addEventListener=()=>{};controls.stPixelGrid.addEventListener=()=>{};
    T.plan={key:'sample',box:[0,0,10,10],atlas:{scale:1}};T.viewBox=[0,0,10,10];T.busy=false;T.stroke=null;
    stCharacterCanvas=()=>({width:10,height:10,getContext:()=>({getImageData:()=>({data:new Uint8ClampedArray([10,20,30,255])})})});
    controls.stPixelMode.value='sample';controls.stColorFrom.value='#abcdef';stBindPixelTools();`);
  await run("controls.stCanvas.listeners.pointerdown({button:0,pointerId:1,clientX:10,clientY:10,preventDefault(){}})");
  assert.equal(run("controls.stPixelColor.value"), '#0a141e');
  assert.equal(run("controls.stColorFrom.value"), '#abcdef');

  // A slow source sample cannot replace a manually changed colour or another role's colour.
  run("controls.stPixelMode.value='source';T.k=1;T.scene={effects:[]};var resolveSample,lastSample;api=(url,options)=>{lastSample={url,payload:JSON.parse(options.body)};return new Promise(resolve=>{resolveSample=resolve})}");
  let pending = run("stSampleSource({x:1,y:2})");
  run("controls.stColorFrom.value='#112233';resolveSample({matched:true,color:'#ff0000',alpha:255})");
  await pending;
  assert.equal(run("controls.stColorFrom.value"), '#112233');
  pending = run("stSampleSource({x:1,y:2})");
  run("T.roleRequest++;resolveSample({matched:true,color:'#00ff00',alpha:255})");
  await pending;
  assert.equal(run("controls.stColorFrom.value"), '#112233');
  pending = run("stSampleSource({x:1,y:2})");
  run("resolveSample({matched:true,color:'#ff00aa',alpha:128})");
  await pending;
  assert.equal(run("controls.stColorFrom.value"), '#ff00aa');
  assert.equal(run("controls.stPixelColor.value"), '#0a141e');
  assert.equal(run("lastSample.url"), '/api/studio/sample');
  assert.equal(run("lastSample.payload.frame"), 1);
  assert.equal(run("lastSample.payload.slot"), 'skin');

  // Editor shortcuts leave native input editing alone, including Escape.
  context.keydown = documentListeners.keydown;
  run("var undoKeys=0,redoKeys=0;stUndoPixel=()=>{undoKeys++};stRedoPixel=()=>{redoKeys++};T.stroke=null");
  run("keydown({key:'z',ctrlKey:true,target:{matches:()=>true},preventDefault(){throw Error('native shortcut hijacked')}})");
  assert.equal(run("undoKeys"), 0);
  run("keydown({key:'z',ctrlKey:true,shiftKey:true,target:{matches:()=>false},preventDefault(){}});keydown({key:'y',ctrlKey:true,target:{matches:()=>false},preventDefault(){}})");
  assert.equal(run("redoKeys"), 2);
  run("T.stroke={pointerId:7};keydown({key:'Escape',target:{matches:()=>true},preventDefault(){throw Error('native escape hijacked')}})");
  assert.equal(run("T.stroke.pointerId"), 7);
  run("T.stroke=null");
  console.log("studio frontend: legacy boundaries, independent long-effect playback, saved action/fps, layer order/visibility, per-layer blend isolation, frozen multi-pointer strokes, undo/redo/cancel/cap, scaled coordinates, separate sampling, stale responses and native shortcuts passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
