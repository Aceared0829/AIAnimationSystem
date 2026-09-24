const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const elements = new Map();
const documentEvents = {};
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: '', checked: false, style: {}, classList: { add() {}, remove() {} },
    addEventListener() {}, setAttribute() {}, focus() {}, setPointerCapture() {},
    getBoundingClientRect() { return { left: 0, top: 0, width: 800, height: 600 }; },
  });
  return elements.get(id);
}
element('mode').value = 'world';
const context = vm.createContext({
  document: { getElementById: element, querySelectorAll() { return []; },
    addEventListener(type, handler) { documentEvents[type] = handler; } },
  window: { addEventListener() {} },
  location: { origin: 'http://127.0.0.1:8765', search: '', href: 'http://127.0.0.1:8765/' },
  fetch() { return new Promise(() => {}); }, requestAnimationFrame() {}, URL, Float32Array,
  devicePixelRatio: 1, confirm() { return true; }, alert() {},
});
const script = fs.readFileSync(path.join(__dirname, '../data/tools/review_web/app.js'), 'utf8');
vm.runInContext(script, context);
vm.runInContext(`data={frames:2,source:{names:['Root','Hand'],parents:[-1,0],pelvis:0,
  positions:Float32Array.from([0,0,50,0,0,150,100,0,150,100,0,250]),
  root_positions:Float32Array.from([0,0,0,100,0,100])},target:null}`, context);

const worldTrail = vm.runInContext('trailPoint(data.source,1,origin(data.source,1))', context);
assert.deepEqual(Array.from(worldTrail), [100, 0, 100], 'world view preserves Root displacement and height');
vm.runInContext('fitCamera()', context);
const target = vm.runInContext('camera.target', context);
assert(target[0] > 0 && target[2] > 0, 'overview frames the moving, elevated actor');
const vertical = vm.runInContext('projection(800,600)([100,0,100])[1]-projection(800,600)([100,0,0])[1]', context);
assert(Math.abs(vertical) > 1, 'different Root heights project to different screen positions');

element('mode').value = 'follow';
const followTrail = vm.runInContext('trailPoint(data.source,1,origin(data.source,1))', context);
assert.deepEqual(Array.from(followTrail), [0, 0, 100], 'follow view changes horizontal framing only');

const canvas = element('source');
const event = (buttons, x, y, altKey = false) => ({ buttons, clientX: x, clientY: y, altKey,
  pointerId: 1, preventDefault() {} });
const beforeOrbit = vm.runInContext('camera.yaw', context);
canvas.onpointerdown(event(1, 0, 0, true));
canvas.onpointermove(event(1, 20, 0, true));
canvas.onpointerup(event(0, 20, 0, true));
assert.notEqual(vm.runInContext('camera.yaw', context), beforeOrbit, 'Alt+LMB orbits');
const beforePan = Array.from(vm.runInContext('camera.target', context));
canvas.onpointerdown(event(4, 0, 0));
canvas.onpointermove(event(4, 20, 0));
canvas.onpointerup(event(0, 20, 0));
assert.notDeepEqual(Array.from(vm.runInContext('camera.target', context)), beforePan, 'MMB pans');
const beforeLook = vm.runInContext('camera.yaw', context);
canvas.onpointerdown(event(2, 0, 0));
canvas.onpointermove(event(2, 20, 10));
assert.notEqual(vm.runInContext('camera.yaw', context), beforeLook, 'RMB looks around');
documentEvents.keydown({ code: 'KeyW', target: { tagName: 'CANVAS' }, preventDefault() {} });
assert(vm.runInContext("flyKeys.has('KeyW')", context), 'RMB+W enters UE-style fly movement');
const beforeFlight = Array.from(vm.runInContext('camera.target', context));
element('source').getBoundingClientRect = element('target').getBoundingClientRect =
  () => ({ left: 0, top: 0, width: 0, height: 0 });
vm.runInContext('last=1000;tick(1100)', context);
assert.notDeepEqual(Array.from(vm.runInContext('camera.target', context)), beforeFlight, 'RMB+W flies through the scene');
documentEvents.keyup({ code: 'KeyW' });
canvas.onpointerup(event(0, 20, 10));
console.log('Motion Review Root trajectory, framing, and UE orbit/pan controls: OK');

if (process.env.MOTION_REVIEW_REAL_URL) {
  (async () => {
    const base = process.env.MOTION_REVIEW_REAL_URL;
    const catalog = await (await fetch(`${base}/api/catalog?page=1`)).json();
    const clip = await (await fetch(`${base}/api/clip/${catalog.entries[0].id}?page=1`)).json();
    assert.equal(clip.source.root_positions.length, clip.frames * 3);
    context.realClip = clip;
    element('mode').value = 'world';
    vm.runInContext(`data=realClip;frame=0;data.source.positions=Float32Array.from(data.source.positions);
      data.source.root_positions=Float32Array.from(data.source.root_positions);fitCamera()`, context);
    const visibility = vm.runInContext(`(() => {
      const rig=data.source,out=[];
      for(const f of [0,Math.floor(data.frames/2),data.frames-1]){
        let visible=0;
        for(let i=0;i<rig.names.length;i++){
          const p=projection(800,600)(sub(position(rig,f,i),origin(rig,f)));
          if(p&&p[0]>=0&&p[0]<=800&&p[1]>=0&&p[1]<=600)visible++;
        }
        out.push(visible/rig.names.length);
      }
      return out;
    })()`, context);
    assert(visibility.every(v => v > 0.5), `real high-jump actor must stay visible: ${visibility}`);
    const travel = vm.runInContext(`(() => {
      const rig=data.source,start=projection(800,600)(trailPoint(rig,0,origin(rig,0)));
      const end=projection(800,600)(trailPoint(rig,data.frames-1,origin(rig,data.frames-1)));
      return Math.hypot(start[0]-end[0],start[1]-end[1]);
    })()`, context);
    assert(travel > 10, `world mode must show screen-space travel, got ${travel}px`);
    console.log(`Real clip framing: ${visibility.map(v => Math.round(v * 100)).join('/')}% visible bones`);
  })().catch(error => { console.error(error); process.exitCode = 1; });
}
