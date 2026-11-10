const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

let clock = 0, timerId = 0, draws = 0;
const timers = new Map();
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.classList = {toggle() {}}; this.style = {}; }
  append(...children) { this.children.push(...children.filter(x => x !== undefined && x !== null)); }
  addEventListener(event, callback) { this.listeners[event] = callback; }
  setAttribute(key, value) { this[key] = value; }
  getContext() { return {fillRect() {}, drawImage() { draws++; }}; }
}
const context = vm.createContext({
  el: (tag, props = {}, ...children) => { const element = Object.assign(new Element(tag), props); element.append(...children); return element; },
  Image: class { async decode() {} }, performance: {now: () => clock},
  setTimeout: callback => { const id = ++timerId; timers.set(id, callback); return id; },
  clearTimeout: id => timers.delete(id)
});
vm.runInContext(fs.readFileSync(path.join(__dirname, "../scripts/workbench/static/buff.js"), "utf8"), context);
const run = source => vm.runInContext(source, context);
const json = source => JSON.parse(JSON.stringify(run(source)));
const find = (root, predicate) => predicate(root) ? root : root.children?.map(child => typeof child === "object" ? find(child, predicate) : null).find(Boolean);

(async () => {
  // A one-shot animation keeps its last frame for one full frame duration, then pauses; loop is an explicit separate mode.
  const end = 19 * 1000 / 15;
  assert.deepEqual(json(`buffPlaybackFrame(${end - .01},15,19,false)`), {frame: 18, ended: false});
  assert.deepEqual(json(`buffPlaybackFrame(${end + .01},15,19,false)`), {frame: 18, ended: true});
  assert.deepEqual(json(`buffPlaybackFrame(${end + .01},15,19,true)`), {frame: 0, ended: false});
  assert.equal(run("buffClampFrame(-1,19)"), 0);
  assert.equal(run("buffClampFrame(19,19)"), 18);
  assert.equal(run("buffRoute('project a','portrait/试作')"), "#/p/project%20a/buff/portrait%2F%E8%AF%95%E4%BD%9C");
  assert.equal(run("buffMetadata({frames:0,fps:0})"), "素材尚未就绪");
  assert.equal(run("buffWarningText('Generated cell aspect ratio differs from target; cells are uniformly fitted with transparent padding, never stretched')"), "原始动作表比例与目标不同，已等比例缩放并留透明边。");
  assert.equal(run("buffWarningText('Frame 11: soft alpha edge is 1px from the source cell boundary; boundary alpha is at most 5/255, not an opaque clipping edge')"), "第 11 帧原表的软透明边缘靠边，人物主体没有硬裁切。");
  assert.equal(run("buffWarningText('Frame 17: soft alpha edge is 1px from the source cell boundary; boundary alpha is at most 3/255, not an opaque clipping edge')"), "第 17 帧原表的软透明边缘靠边，人物主体没有硬裁切。");
  assert.equal(run("buffWarningText('unexpected warning')"), "unexpected warning");
  const badges = run("buffBadges({status:'encoded',status_label:'已编码',installed:false,ingame_verified:false})");
  assert.equal(find(badges, e => e.textContent === "待实机验证").textContent, "待实机验证");
  assert.equal(find(badges, e => e.textContent === "实机已通过"), undefined);

  // Exercise the actual player's controls with decoded frame stubs and a controllable monotonic clock.
  const root = run("buffPlayer({name:'test',frames:19,fps:15,width:470,height:668,frame_url:'/frame?k={k}'})");
  const play = find(root, e => e.tag === "button" && e.ariaLabel === "播放 buff 动画");
  const repeat = find(root, e => e.tag === "input" && e.type === "checkbox");
  const progress = find(root, e => e.tag === "input" && e.type === "range");
  assert.equal(repeat.checked, false);
  await play.listeners.click();
  assert.equal(play.textContent, "暂停");
  assert.equal(timers.size, 1);
  clock = end + .1;
  const first = timers.entries().next().value; timers.delete(first[0]); first[1]();
  assert.equal(progress.value, 18);
  assert.equal(play.textContent, "播放");
  assert.equal(timers.size, 0);

  repeat.checked = true; repeat.listeners.change();
  await play.listeners.click();
  assert.equal(progress.value, 0); // Replaying from the retained last frame starts again at the beginning.
  clock += end + .1;
  const looping = timers.entries().next().value; timers.delete(looping[0]); looping[1]();
  assert.equal(progress.value, 0);
  assert.equal(play.textContent, "暂停");
  assert.equal(timers.size, 1);

  // Route disposal cancels live playback; late frame decodes cannot restart it or paint the detached viewer.
  run("buffDisposeAll()");
  const lastDraws = draws;
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(timers.size, 0);
  assert.equal(draws, lastDraws);
  assert.equal(run("BUFF.players.size"), 0);
  console.log("buff frontend: one-shot duration, loop opt-in, stepping, replay and route cleanup passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
